"""Auth & session blueprint — /api/auth/*.

Wire contracts verified against the recovered stock frontend on 2026-09-20
(audit/auth-session.md ground truth). See module docstring of the package
for the full contract list.
"""

import time
import uuid
from functools import wraps

import jwt
from flask import Blueprint, jsonify, request

from . import config, state

bp = Blueprint("auth", __name__)


def _now():
    return int(time.time())


def make_access(u):
    now = _now()
    return jwt.encode({
        "sub": str(u["id"]),
        "iat": now,
        "exp": now + config.ACCESS_TTL_S,
        "type": "access",
        "user": state.public_user(u),
    }, config.SECRET, algorithm="HS256")


def make_refresh(u):
    now = _now()
    return jwt.encode({
        "sub": str(u["id"]),
        "iat": now,
        "exp": now + config.REFRESH_TTL_S,
        "type": "refresh",
        "jti": uuid.uuid4().hex,
    }, config.SECRET, algorithm="HS256")


def detail(status, msg):
    return jsonify({"detail": msg}), status


def decode(token, expect_type):
    """Returns (payload, error_response)."""
    try:
        payload = jwt.decode(token, config.SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None, detail(401, "Token has expired")
    except jwt.InvalidTokenError:
        return None, detail(401, "Could not validate credentials")
    if payload.get("type") != expect_type:
        return None, detail(401, "Could not validate credentials")
    return payload, None


def bearer_token():
    hdr = request.headers.get("Authorization", "")
    return hdr[len("Bearer "):] if hdr.startswith("Bearer ") else None


def require_auth(f):
    """Bearer access-token guard shared by all authenticated blueprints."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = bearer_token()
        if token is None:
            return detail(401, "Not authenticated")
        payload, err = decode(token, "access")
        if err:
            return err
        user = state.USERS_BY_ID.get(str(payload["sub"]))
        if user is None:
            return detail(401, "Could not validate credentials")
        request.mock_user = user
        request.mock_payload = payload
        return f(*args, **kwargs)
    return wrapper


@bp.post("/api/auth/token")
def auth_token():
    # Stock Android sends multipart/form-data (pages/login.vue:98-100); the
    # generated SDK would send urlencoded. FastAPI's OAuth2 form parser
    # accepts both. Fields: username, password — nothing else.
    username = request.form.get("username", "")
    password = request.form.get("password", "")
    user = state.USERS_BY_EMAIL.get(username)
    if user is None or user["password"] != password:
        # [H] exact failure status/body unrecoverable; 401 + detail matches
        # what the client displays (data.detail || data.message).
        return detail(401, "Incorrect username or password")
    return jsonify({
        "access_token": make_access(user),
        "refresh_token": make_refresh(user),
        "token_type": "bearer",  # [H] ignored by the client
    })


@bp.post("/api/auth/refresh")
def auth_refresh():
    # JSON {refresh_token}, NO Authorization header (useAuth.ts:228-240).
    body = request.get_json(silent=True) or {}
    token = body.get("refresh_token")
    if not token:
        return detail(401, "Could not validate credentials")
    payload, err = decode(token, "refresh")
    if err:
        return err
    if payload.get("jti") in state.revoked_jti:
        return detail(401, "Could not validate credentials")
    user = state.USERS_BY_ID.get(str(payload["sub"]))
    if user is None:
        return detail(401, "Could not validate credentials")
    # The client never rotates its stored refresh token (useAuth.ts:241-246),
    # so the same one stays valid until logout/expiry.
    return jsonify({"access_token": make_access(user), "token_type": "bearer"})


@bp.get("/api/auth/profile")
def auth_profile():
    token = bearer_token()
    if token is None:
        return detail(401, "Not authenticated")
    payload, err = decode(token, "access")
    if err:
        return err
    user = state.USERS_BY_ID.get(str(payload["sub"]))
    if user is None:
        return detail(401, "Could not validate credentials")
    alerts = dict(user.get("alerts") or {"banner_alert": None})
    # Once a voice sample exists, the record_voice_sample banner clears
    # (server-mandated onboarding, audit/audio-voice.md §1).
    if alerts.get("banner_alert") == "record_voice_sample" \
            and str(user["id"]) in state.voice_samples:
        alerts["banner_alert"] = None
    # The stock navigation reads alerts.alert_counters.account directly after
    # a hard reload (only `alerts` itself is optional-chained).  Preserve that
    # required nested response shape even when the fixture has no problems.
    alerts.setdefault("alert_counters", {
        "account": 1 if alerts.get("banner_alert") else 0,
    })
    return jsonify({
        "token": {"user": state.public_user(user)},
        "alerts": alerts,
        "settings": {"time_zone": user.get("time_zone", "America/Anchorage")},
        "profile_picture_url": None,
    })


@bp.post("/api/auth/logout")
def auth_logout():
    token = bearer_token()
    if token is None:
        return detail(401, "Not authenticated")
    _, err = decode(token, "access")
    if err:
        return err
    body = request.get_json(silent=True) or {}
    rt = body.get("refresh_token")
    if rt:
        try:
            rp = jwt.decode(rt, config.SECRET, algorithms=["HS256"])
            if rp.get("jti"):
                state.revoked_jti.add(rp["jti"])
        except jwt.InvalidTokenError:
            pass
    return jsonify({})  # body unused by the client (useAuth.ts:150-166)


@bp.get("/api/auth/ws_token")
def auth_ws_token():
    token = bearer_token()
    if token is None:
        return detail(401, "Not authenticated")
    payload, err = decode(token, "access")
    if err:
        return err
    now = _now()
    return jsonify({"access_token": jwt.encode({
        "sub": payload["sub"], "iat": now,
        "exp": now + config.WS_TOKEN_TTL_S, "type": "ws",
    }, config.SECRET, algorithm="HS256")})
