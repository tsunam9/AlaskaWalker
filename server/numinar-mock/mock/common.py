"""Shared authentication and response helpers."""

import functools
import time
import uuid

import jwt
from flask import g, jsonify, request

from . import config, oidc, state

VERIFY_DETAIL = "You need to verify your email to access this resource"


def detail(message, status=400):
    return jsonify({"detail": message}), status


def current_org_id():
    return request.headers.get("x-org-id") or "org_alaska_001"


def access_claims(user):
    now = int(time.time())
    return {
        "iss": config.ISSUER, "sub": user["sub"], "aud": config.AUDIENCE,
        "iat": now, "exp": now + config.ACCESS_TTL_S,
        "scope": "openid profile email offline_access",
        "https://numinar.com/roles": list(user.get("roles") or ["canvasser"]),
        "https://numinar.com/email_verified": bool(user.get("email_verified")),
    }


def make_access_token(user):
    return jwt.encode(access_claims(user), config.SECRET, algorithm="HS256")


def make_id_token(user, issuer=None, nonce=None):
    now = int(time.time())
    claims = {
        "iss": issuer or config.ISSUER, "sub": user["sub"], "aud": config.CLIENT_ID,
        "iat": now, "exp": now + config.ACCESS_TTL_S,
        "email": user["email"], "email_verified": bool(user["email_verified"]),
        "name": user["name"], "given_name": user["first_name"],
        "family_name": user["last_name"], "nickname": user["first_name"],
    }
    if nonce is not None:
        claims["nonce"] = nonce
    return jwt.encode(
        claims, oidc.PRIVATE_KEY, algorithm="RS256",
        headers={"kid": oidc.KID, "typ": "JWT"},
    )


def issue_tokens(user, include_refresh=True, id_token_issuer=None, nonce=None):
    response = {
        "access_token": make_access_token(user),
        "id_token": make_id_token(user, issuer=id_token_issuer, nonce=nonce),
        "scope": "openid profile email offline_access", "token_type": "Bearer",
        "expires_in": config.ACCESS_TTL_S,
    }
    if include_refresh:
        token = "mock_rt_" + uuid.uuid4().hex
        state.refresh_tokens[token] = {
            "sub": user["sub"], "expires_at": time.time() + config.REFRESH_TTL_S,
            "created_at": state.iso_now(),
        }
        response["refresh_token"] = token
    return response


def decode_bearer():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None, "Missing bearer token"
    try:
        claims = jwt.decode(
            header[7:], config.SECRET, algorithms=["HS256"], audience=config.AUDIENCE,
            issuer=config.ISSUER,
        )
    except jwt.PyJWTError as exc:
        return None, f"Invalid bearer token: {exc}"
    user = state.USERS_BY_SUB.get(claims.get("sub"))
    if not user:
        return None, "Unknown token subject"
    return (claims, user), None


def require_auth(verify_email=True):
    def decorate(func):
        @functools.wraps(func)
        def wrapped(*args, **kwargs):
            auth, error = decode_bearer()
            if error:
                return detail(error, 401)
            claims, user = auth
            if verify_email and not claims.get("https://numinar.com/email_verified", False):
                return detail(VERIFY_DETAIL, 401)
            g.auth_claims = claims
            g.current_user = user
            return func(*args, **kwargs)
        return wrapped
    return decorate
