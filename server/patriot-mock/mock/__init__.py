"""Patriot Grassroots / ValidNation mock backend package.

create_app() assembles the Flask app from domain blueprints. Wire contracts
are taken from patriot_grassroots/audit/*.md (ground truth, line-cited
against the recovered stock frontend) and re-verified against /tmp/vn_src
on 2026-09-20.

Client-visible invariants (all domains):
  * success status is strictly 200 (doMobileRequest/doNativeRequest treat
    any non-200 as error)
  * error bodies are FastAPI-style {"detail": "..."}
  * Authorization: Bearer <jwt> on everything except /api/auth/token,
    /api/auth/refresh and /api/settings/versions
"""

import copy
import os
import time
import uuid

from flask import Flask, Response, g, jsonify, redirect, request, send_from_directory

from . import config


_SENSITIVE_KEYS = {
    "access_token", "audio_data", "authorization", "fcm_token", "password",
    "refresh_token", "token",
}


def _redact(value, key=None):
    """Make request/state data safe to inspect without retaining credentials."""
    if key and key.lower() in _SENSITIVE_KEYS:
        if key.lower() == "audio_data" and isinstance(value, str):
            return f"<redacted base64 audio: {len(value)} chars>"
        return "<redacted>"
    if isinstance(value, dict):
        return {k: _redact(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _request_payload():
    if request.is_json:
        return _redact(request.get_json(silent=True))
    if request.mimetype and request.mimetype.startswith("multipart/"):
        return {
            "form": _redact(request.form.to_dict(flat=False)),
            "files": {
                name: [
                    {"filename": item.filename, "content_type": item.mimetype}
                    for item in request.files.getlist(name)
                ]
                for name in request.files
            },
        }
    if request.form:
        return {"form": _redact(request.form.to_dict(flat=False))}
    return None


def _dashboard_snapshot(state):
    """Return a stable copy of all useful mock state for the local dashboard."""
    with state._lock:
        users = [_redact(copy.deepcopy(user)) for user in state.USERS_BY_ID.values()]
        devices = copy.deepcopy(state.devices)
        for device in devices.values():
            if device.get("fcm_token"):
                device["fcm_token"] = "<registered; redacted>"
        requests = list(copy.deepcopy(state.request_log))
        sensors = copy.deepcopy(state.sensor_records)
        events = copy.deepcopy(state.device_events)
        audio = copy.deepcopy(state.audio_uploads)
        shifts = copy.deepcopy(list(state.shifts.values()))
        projects = copy.deepcopy(list(state.PROJECTS.values()))
        wake_words = copy.deepcopy(state.wake_word_events)
        earnings = copy.deepcopy(state.earnings)
        transactions = copy.deepcopy(state.transactions)
        notifications = copy.deepcopy(state.notifications)
        voice_samples = copy.deepcopy(state.voice_samples)
        verifications = copy.deepcopy(list(state.verifications.values()))
        orphaned_finalizations = copy.deepcopy(state.orphaned_finalizations)

    sensor_types = {}
    for record in sensors:
        kind = record.get("sensor_type") or "unknown"
        sensor_types[kind] = sensor_types.get(kind, 0) + 1
    event_types = {}
    for event in events:
        kind = event.get("event_type") or "unknown"
        event_types[kind] = event_types.get(kind, 0) + 1
    status_codes = {}
    for item in requests:
        code = str(item.get("status", "pending"))
        status_codes[code] = status_codes.get(code, 0) + 1

    return {
        "server": {
            "started_at": state.server_started_at,
            "server_time": time.time(),
            "uptime_seconds": round(time.time() - state.server_started_at, 3),
            "request_history_limit": state.request_log.maxlen,
        },
        "summary": {
            "requests": len(requests),
            "request_errors": sum(1 for item in requests
                                  if int(item.get("status") or 0) >= 400),
            "active_shifts": sum(1 for shift in shifts
                                 if shift.get("status") in ("active", "paused")),
            "shifts": len(shifts),
            "sensor_records": len(sensors),
            "sensor_readings": sum(len(record.get("sensor_readings") or [])
                                   for record in sensors),
            "device_events": len(events),
            "audio_uploads": len(audio),
            "audio_bytes": sum(int(item.get("audio_bytes") or 0) for item in audio),
            "wake_word_events": len(wake_words),
        },
        "breakdowns": {
            "sensor_types": sensor_types,
            "event_types": event_types,
            "status_codes": status_codes,
        },
        "users": users,
        "projects": projects,
        "devices": devices,
        "shifts": shifts,
        "sensor_records": sensors,
        "device_events": events,
        "audio_uploads": audio,
        "wake_word_events": wake_words,
        "voice_samples": voice_samples,
        "verifications": verifications,
        "orphaned_finalizations": orphaned_finalizations,
        "earnings": earnings,
        "transactions": transactions,
        "notifications": notifications,
        "revoked_refresh_token_count": len(state.revoked_jti),
        "requests": requests,
        # Backward-compatible fields used by existing command-line checks.
        "sensor_record_count": len(sensors),
        "device_event_count": len(events),
        "audio_upload_count": len(audio),
        "revoked_refresh_tokens": len(state.revoked_jti),
    }


def create_app():
    app = Flask(__name__)

    from . import auth, shifts, device, sensors, audio, reads
    app.register_blueprint(auth.bp)
    app.register_blueprint(shifts.bp)
    app.register_blueprint(device.bp)
    app.register_blueprint(sensors.bp)
    app.register_blueprint(audio.bp)
    app.register_blueprint(reads.bp)

    @app.before_request
    def _log_request():
        g.mock_request_id = uuid.uuid4().hex[:12]
        g.mock_request_started = time.monotonic()
        g.mock_request_payload = _request_payload()
        has_auth = "yes" if request.headers.get("Authorization") else "no"
        print(f"[patriot-mock] {request.method} {request.path} auth={has_auth} "
              f"ct={request.headers.get('Content-Type', '-')}", flush=True)

    @app.before_request
    def _dashboard_auth():
        # Basic auth for the /__mock diagnostics namespace only. /api/* keeps
        # Bearer-only semantics so stock-app traffic is unaffected.
        if not request.path.startswith("/__mock"):
            return None
        auth = request.authorization
        if auth and auth.type == "basic" and auth.username == config.DASH_USER \
                and auth.password == config.DASH_PASS:
            return None
        return Response("authentication required", 401,
                        {"WWW-Authenticate": 'Basic realm="patriot-mock"'})

    @app.after_request
    def _record_request(response):
        from . import state
        # Dashboard polling is diagnostic traffic, not stock-app traffic. Do
        # not let it distort counters or recursively capture its own state JSON.
        if request.path.startswith("/__mock") or request.path in ("/", "/favicon.ico"):
            response.headers["X-Mock-Request-Id"] = g.mock_request_id
            response.headers["Cache-Control"] = "no-store"
            return response
        response_body = None
        if response.is_json:
            response_body = _redact(response.get_json(silent=True))
        state.request_log.append({
            "id": getattr(g, "mock_request_id", None),
            "received_at": state.iso_now(),
            "method": request.method,
            "path": request.path,
            "query": request.args.to_dict(flat=False),
            "status": response.status_code,
            "duration_ms": round(
                (time.monotonic() - getattr(g, "mock_request_started", time.monotonic()))
                * 1000, 2),
            "authenticated": bool(request.headers.get("Authorization")),
            "content_type": request.content_type,
            "request": getattr(g, "mock_request_payload", None),
            "response": response_body,
            "response_bytes": response.calculate_content_length(),
        })
        if request.method in ("POST", "PUT", "PATCH", "DELETE") \
                and response.status_code < 500:
            state.persist_runtime_state()
        response.headers["X-Mock-Request-Id"] = g.mock_request_id
        return response

    @app.get("/")
    def mock_dashboard_redirect():
        return redirect("/__mock/")

    @app.get("/favicon.ico")
    def mock_favicon():
        return "", 204

    @app.route("/generate_204", methods=["GET", "HEAD"])
    def connectivity_probe():
        """Stock connectivity canary, redirected here by the isolated APK."""
        return "", 204

    @app.get("/__mock/")
    def mock_dashboard():
        return send_from_directory(os.path.dirname(__file__), "dashboard.html")

    @app.get("/__mock/state")
    def mock_state():
        from . import state
        return jsonify(_dashboard_snapshot(state))

    @app.errorhandler(404)
    def not_found(_e):
        print(f"[patriot-mock] 404 {request.method} {request.path} "
              f"(unimplemented in mock)", flush=True)
        return jsonify({"detail": "Not Found"}), 404

    return app
