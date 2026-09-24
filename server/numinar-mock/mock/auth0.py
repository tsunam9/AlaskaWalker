"""Auth0 passwordless, refresh, Web Auth exchange, and userinfo surface."""

import random
import re
import time
import uuid
from urllib.parse import urlsplit, urlunsplit

from flask import Blueprint, Response, g, jsonify, redirect, request

from . import config, oidc, state
from .common import issue_tokens, require_auth

bp = Blueprint("auth0", __name__)


def auth0_error(error, description, status=400):
    return jsonify({"error": error, "error_description": description}), status


def _repointed_issuer(redirect_uri=None):
    """Reconstruct Auth0.Android's exact account base URL.

    The build preserves the original Hermes string width by padding the mock
    host with slashes. CallbackHelper adds one more slash before ``android``;
    recover the account URL from that callback when it is available. Direct
    token grants have no redirect URI, so use the same 16/32-character carrier
    rule as build_repointed.sh.
    """
    if redirect_uri:
        parts = urlsplit(redirect_uri)
        leading_slashes = len(parts.path) - len(parts.path.lstrip("/"))
        padding = max(1, leading_slashes - 1)
        return f"{request.scheme}://{parts.netloc}" + "/" * padding
    hostport = request.host
    carrier_width = 16 if len(hostport) <= 16 else 32
    padding = max(1, carrier_width - len(hostport))
    return f"{request.scheme}://{hostport}" + "/" * padding


@bp.get("/.well-known/jwks.json")
def jwks():
    return jsonify(oidc.JWKS)


@bp.post("/passwordless/start")
def passwordless_start():
    data = request.get_json(silent=True) or {}
    required = {"client_id", "connection", "email", "send", "authParams"}
    if not required.issubset(data) or data.get("connection") != "email" or data.get("send") != "code":
        return auth0_error("invalid_request", "A valid email passwordless request is required.")
    email = str(data["email"]).lower()
    # [O-parity] Real Auth0 passwordless accepts any email and creates the
    # account at first verification; provision instead of rejecting.
    state.ensure_user(email)
    otp = f"{random.SystemRandom().randrange(100000, 1000000):06d}"
    state.otps[email] = {"otp": otp, "expires_at": time.time() + config.OTP_TTL_S, "used": False}
    state.persist_runtime_state()
    print(f"[numinar-mock] OTP for {email}: {otp}", flush=True)
    return jsonify({"status": "code_sent"})


@bp.post("/oauth/token")
def oauth_token():
    data = request.get_json(silent=True) or {}
    grant = data.get("grant_type")
    if grant == "http://auth0.com/oauth/grant-type/passwordless/otp":
        email = str(data.get("username", "")).lower()
        record = state.otps.get(email)
        if not record or record.get("used") or record.get("expires_at", 0) < time.time() or str(data.get("otp")) != record.get("otp"):
            return auth0_error("invalid_grant", "Wrong email or verification code.", 403)
        if data.get("realm") != "email":
            return auth0_error("invalid_request", "The realm must be email.")
        record["used"] = True
        response = issue_tokens(
            state.USERS_BY_EMAIL[email], include_refresh=True,
            id_token_issuer=_repointed_issuer(),
        )
        state.persist_runtime_state()
        return jsonify(response)
    if grant == "refresh_token":
        token = data.get("refresh_token")
        record = state.refresh_tokens.get(token)
        if not record or record.get("expires_at", 0) < time.time():
            return auth0_error("invalid_grant", "Unknown or expired refresh token.", 403)
        user = state.USERS_BY_SUB.get(record.get("sub"))
        if not user:
            return auth0_error("invalid_grant", "Unknown refresh-token subject.", 403)
        # [R] auth-session.md §3: the client retains the old refresh token
        # when it is omitted, so no mock rotation is required.
        return jsonify(issue_tokens(
            user, include_refresh=False,
            id_token_issuer=_repointed_issuer(),
        ))
    if grant == "authorization_code":
        code = data.get("code")
        if not code:
            return auth0_error("invalid_request", "Missing authorization code.")
        # Codes issued by the mock /authorize page map to the submitting user.
        record = state.auth_codes.pop(str(code), None)
        if record and record.get("expires_at", 0) >= time.time():
            user = state.USERS_BY_EMAIL.get(record.get("email", ""))
        else:
            user = None
        if user is None:
            # [H] Tolerate codes the mock did not issue (e.g. state lost to a
            # restart mid-flow) so the client state machine can still proceed.
            user = state.USERS_BY_EMAIL["canvasser@example.test"]
        response = issue_tokens(
            user, include_refresh=True,
            id_token_issuer=(record or {}).get("issuer") or _repointed_issuer(),
            nonce=(record or {}).get("nonce"),
        )
        state.persist_runtime_state()
        return jsonify(response)
    return auth0_error("unsupported_grant_type", "Unsupported grant_type.")


_AUTHORIZE_PAGE = """<!doctype html>
<html><head><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mock Universal Login</title></head>
<body style="font-family:sans-serif;max-width:22rem;margin:3rem auto">
<h2>Numinar mock sign-in</h2>
<p>This is the mock Universal Login page. Any email and password work.</p>
<form method="post" action="/authorize?__QUERY__">
<input name="email" type="email" placeholder="Email" required
  style="display:block;width:100%%;margin:.5rem 0;padding:.6rem">
<input name="password" type="password" placeholder="Password"
  style="display:block;width:100%%;margin:.5rem 0;padding:.6rem">
<button type="submit" style="width:100%%;padding:.7rem">Log in</button>
</form></body></html>"""


@bp.get("/authorize")
def authorize_page():
    # [H] Mock stand-in for Auth0 Universal Login. The real service renders a
    # hosted credentials page at /authorize; the SDK only cares that the flow
    # ends in a 302 to redirect_uri carrying code+state.
    return Response(_AUTHORIZE_PAGE.replace("__QUERY__", request.query_string.decode()), mimetype="text/html")


@bp.post("/authorize")
def authorize_submit():
    email = str(request.form.get("email", "")).strip().lower()
    if not email:
        return auth0_error("invalid_request", "Email is required.")
    state.ensure_user(email)
    code = "mock_ac_" + uuid.uuid4().hex
    state.auth_codes[code] = {
        "email": email, "client_id": request.values.get("client_id"),
        "nonce": request.values.get("nonce"),
        "issuer": _repointed_issuer(request.values.get("redirect_uri")),
        "expires_at": time.time() + 300,
    }
    state.persist_runtime_state()
    redirect_uri = request.values.get("redirect_uri")
    if not redirect_uri:
        return auth0_error("invalid_request", "Missing redirect_uri.")
    # The repointed Auth0 domain is padded with trailing slashes to preserve
    # the stock Hermes string-table width. Auth0.Android incorporates that
    # padding into redirect_uri, producing //...//android/... as the callback
    # path. Android's stock RedirectActivity filter requires the canonical
    # /android/com.numinar.numinar/callback path, so normalize only the leading
    # path padding before handing the code back. The client-generated request
    # and its PKCE/state values remain untouched.
    parts = urlsplit(redirect_uri)
    callback_path = re.sub(r"^/+(?=android/)", "/", parts.path)
    redirect_uri = urlunsplit((parts.scheme, parts.netloc, callback_path,
                               parts.query, parts.fragment))
    separator = "&" if "?" in redirect_uri else "?"
    location = f"{redirect_uri}{separator}code={code}"
    if request.values.get("state"):
        location += f"&state={request.values['state']}"
    # Custom-scheme redirects inside Chrome Custom Tabs are not reliably
    # followed from a bare 302 (no user activation on the hop), so land on a
    # page that both JS-navigates and offers a tappable link — a real tap
    # always fires the intent that hands the code back to the app.
    import html as _html
    safe = _html.escape(location, quote=True)
    body = (
        "<!doctype html><html><head><meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<meta http-equiv='refresh' content='0;url={safe}'></head>"
        "<body style='font-family:sans-serif;text-align:center;margin-top:4rem'>"
        "<p>Signing you back in…</p>"
        f"<p><a href='{safe}' style='font-size:1.2rem'>Tap here to return to the app</a></p>"
        f"<script>window.location.href = {location!r};</script>"
        "</body></html>"
    )
    return Response(body, mimetype="text/html")


@bp.get("/v2/logout")
def logout():
    # webAuth clearSession opens this in the browser; complete the flow.
    return_to = request.args.get("returnTo")
    if return_to:
        return redirect(return_to)
    return Response("<html><body>Logged out (mock)</body></html>", mimetype="text/html")


@bp.get("/userinfo")
@require_auth(verify_email=False)
def userinfo():
    user = g.current_user
    return jsonify({
        "sub": user["sub"], "email": user["email"],
        "email_verified": bool(user["email_verified"]), "name": user["name"],
        "given_name": user["first_name"], "family_name": user["last_name"],
        "nickname": user["first_name"],
    })
