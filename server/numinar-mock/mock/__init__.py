"""Flask app factory for the Numinar mock."""

import copy
import os
import re
import time
import uuid
from collections import Counter

from flask import Flask, Response, g, jsonify, redirect, request, send_from_directory

from . import config


class _SlashCollapseMiddleware:
    """Collapse consecutive slashes in PATH_INFO before routing.

    The repointed stock build carries same-length Hermes string patches whose
    padding normalizes (OkHttp dot-segment resolution) into leading `//` on
    some paths, e.g. `http://127.0.0.1:19002//passwordless/start`. Collapsing
    here (rather than relying on Werkzeug merge_slashes) avoids 308 redirects,
    which POST bodies from the app must never bounce through.
    """

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        collapsed = re.sub(r"/{2,}", "/", path)
        if collapsed != path:
            environ["PATH_INFO"] = collapsed
        return self.app(environ, start_response)

_SENSITIVE = {"access_token", "authorization", "device_push_token", "id_token", "otp", "refresh_token", "token"}


def _redact(value, key=None):
    if key and key.lower() in _SENSITIVE:
        return "<redacted>"
    if isinstance(value, dict):
        return {k: _redact(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def _snapshot(state):
    with state._lock:
        requests = copy.deepcopy(list(state.request_log))
        interactions = copy.deepcopy(state.interactions)
        qa = copy.deepcopy(state.qa_pings)
        return {
            "server": {"started_at": state.server_started_at, "server_time": time.time(), "uptime_seconds": round(time.time() - state.server_started_at, 3)},
            "summary": {"requests": len(requests), "request_errors": sum(int(r.get("status", 0)) >= 400 for r in requests), "interactions": len(interactions), "qa_pings": len(qa), "voters": len(state.VOTERS), "push_tokens": len(state.push_tokens)},
            "breakdowns": {"interaction_types": dict(Counter(i.get("_mock_type", "unknown") for i in interactions)), "status_codes": dict(Counter(str(r.get("status")) for r in requests))},
            "users": _redact(copy.deepcopy(list(state.USERS_BY_EMAIL.values()))),
            "orgs": copy.deepcopy(list(state.ORGS.values())), "projects": copy.deepcopy(list(state.PROJECTS.values())),
            "interactions": interactions, "qa_pings": qa, "push_tokens": _redact(copy.deepcopy(state.push_tokens)),
            "otps": copy.deepcopy(state.otps),
            "notifications": copy.deepcopy(state.notifications), "contact_matches": copy.deepcopy(state.contact_matches),
            "requests": requests,
        }


def create_app():
    app = Flask(__name__)
    from . import auth0, interactions, orgs, projects, push, ros, voters
    for blueprint in (auth0.bp, orgs.bp, projects.bp, voters.bp, interactions.bp, push.bp, ros.bp):
        app.register_blueprint(blueprint)

    @app.before_request
    def log_request():
        g.mock_request_id = uuid.uuid4().hex[:12]
        g.mock_started = time.monotonic()
        g.mock_payload = _redact(request.get_json(silent=True)) if request.is_json else None
        print(f"[numinar-mock] {request.method} {request.path} auth={'yes' if request.headers.get('Authorization') else 'no'} org={request.headers.get('x-org-id', '-')}", flush=True)

    @app.before_request
    def dashboard_auth():
        if not request.path.startswith("/__mock"):
            return None
        auth = request.authorization
        if auth and auth.type == "basic" and auth.username == config.DASH_USER and auth.password == config.DASH_PASS:
            return None
        return Response("authentication required", 401, {"WWW-Authenticate": 'Basic realm="numinar-mock"'})

    @app.after_request
    def record_request(response):
        from . import state
        response.headers["X-Mock-Request-Id"] = getattr(g, "mock_request_id", "")
        if request.path.startswith("/__mock") or request.path in ("/", "/favicon.ico"):
            response.headers["Cache-Control"] = "no-store"
            return response
        entry = {
            "id": getattr(g, "mock_request_id", None), "received_at": state.iso_now(),
            "method": request.method, "path": request.path,
            "query": request.args.to_dict(flat=False), "status": response.status_code,
            "duration_ms": round((time.monotonic() - getattr(g, "mock_started", time.monotonic())) * 1000, 2),
            "authenticated": bool(request.headers.get("Authorization")),
            "headers": _redact({k.lower(): v for k, v in request.headers.items() if k.lower() in {"content-type", "numinar-origin", "platform", "x-org-id", "sentry-sid", "authorization"}}),
            "request": getattr(g, "mock_payload", None),
            "response": _redact(response.get_json(silent=True)) if response.is_json else None,
        }
        state.request_log.append(entry)
        state.capture("requests", entry)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and response.status_code < 500:
            state.persist_runtime_state()
        return response

    @app.get("/")
    def root(): return redirect("/__mock/")

    @app.get("/favicon.ico")
    def favicon(): return "", 204

    @app.get("/__mock/")
    def dashboard(): return send_from_directory(os.path.dirname(__file__), "dashboard.html")

    @app.get("/__mock/state")
    def dashboard_state():
        from . import state
        return jsonify(_snapshot(state))

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify({"detail": "Not Found"}), 404

    app.wsgi_app = _SlashCollapseMiddleware(app.wsgi_app)
    return app
