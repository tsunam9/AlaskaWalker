"""Deterministic, local-only fixtures for exercising the instrumented app.

This is intentionally not a proxy.  Every handled response is synthesized in this
process and no code in this module opens sockets or resolves hostnames.
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mitmproxy import http


AUDIT_EMAIL = "audit@local.test"
AUDIT_PASSWORD = "LocalAudit!2026"
AUDIT_USER_ID = "00000000-0000-4000-8000-000000000001"
AUDIT_PROJECT_ID = "00000000-0000-4000-8000-000000000101"


def _b64url(value: dict[str, Any]) -> str:
    raw = json.dumps(value, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _token(kind: str, lifetime: int) -> str:
    now = int(time.time())
    payload = {
        "sub": AUDIT_USER_ID,
        "iat": now,
        "exp": now + lifetime,
        "type": kind,
        "user": {
            "id": AUDIT_USER_ID,
            "email": AUDIT_EMAIL,
            "first_name": "Local",
            "last_name": "Auditor",
            "role": "canvasser",
        },
    }
    return f"{_b64url({'alg': 'none', 'typ': 'JWT'})}.{_b64url(payload)}.local-audit"


def _json(status: int, value: Any) -> http.Response:
    return http.Response.make(
        status,
        json.dumps(value, separators=(",", ":")).encode(),
        {
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Methods": "GET,HEAD,POST,PUT,PATCH,DELETE,OPTIONS",
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "no-store",
            "Content-Type": "application/json",
            "X-Audit-Backend": "local",
        },
    )


def _text(value: bytes | str) -> str:
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else value


def _form(request: http.Request) -> dict[str, str]:
    result: dict[str, str] = {}
    try:
        for key, value in request.multipart_form.items(multi=True):
            result[_text(key)] = _text(value)
    except Exception:
        pass
    try:
        for key, value in request.urlencoded_form.items(multi=True):
            result[_text(key)] = _text(value)
    except Exception:
        pass
    if result:
        return result

    # Capacitor's multipart encoder is simple enough for this fallback, which also
    # makes malformed-form tests observable without accepting arbitrary credentials.
    body = request.raw_content or b""
    for name in ("username", "password"):
        match = re.search(
            rb'name="' + name.encode() + rb'"[^\r\n]*\r\n\r\n(.*?)\r\n--',
            body,
            re.DOTALL,
        )
        if match:
            result[name] = match.group(1).decode("utf-8", "replace")
    return result


def _json_body(request: http.Request) -> Any:
    try:
        return json.loads((request.raw_content or b"").decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


class LocalAuditBackend:
    """Small stateful backend for the currently testable canvasser workflow."""

    def __init__(self) -> None:
        self.shift_id: str | None = None
        self.shift_started_at: str | None = None
        self.shift_device_id: str | None = None
        self.shift_project_id: str | None = None
        configured_state = os.environ.get("PATRIOT_LOCAL_STATE")
        self.state_path = (
            Path(configured_state).expanduser().resolve()
            if configured_state
            else Path(__file__).resolve().parent / "build" / "local_backend_state.json"
        )
        self._load_state()

    def _load_state(self) -> None:
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return
        self.shift_id = state.get("shift_id") if isinstance(state.get("shift_id"), str) else None
        self.shift_started_at = (
            state.get("shift_started_at") if isinstance(state.get("shift_started_at"), str) else None
        )
        self.shift_device_id = (
            state.get("shift_device_id") if isinstance(state.get("shift_device_id"), str) else None
        )
        self.shift_project_id = (
            state.get("shift_project_id") if isinstance(state.get("shift_project_id"), str) else None
        )

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "shift_id": self.shift_id,
                    "shift_started_at": self.shift_started_at,
                    "shift_device_id": self.shift_device_id,
                    "shift_project_id": self.shift_project_id,
                },
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        temporary.replace(self.state_path)

    def _clear_shift(self) -> None:
        self.shift_id = None
        self.shift_started_at = None
        self.shift_device_id = None
        self.shift_project_id = None
        self._save_state()

    @staticmethod
    def _profile() -> dict[str, Any]:
        return {
            "token": {
                "user": {
                    "id": AUDIT_USER_ID,
                    "email": AUDIT_EMAIL,
                    "first_name": "Local",
                    "last_name": "Auditor",
                    "role": "canvasser",
                }
            },
            "alerts": {"banner_alert": None},
            "settings": {"time_zone": "America/Los_Angeles"},
            "profile_picture_url": None,
        }

    @staticmethod
    def _project() -> dict[str, Any]:
        return {
            "id": AUDIT_PROJECT_ID,
            "name": "Local Security Audit",
            "short_description": "Local-only Patriot protocol testing",
            "description": "A local fixture for exercising the unmodified Patriot user interface.",
            "status": "active",
            "type": "canvassing",
            "start_date": "2026-09-01",
            "end_date": "2026-12-31",
            "client": "Local Audit Client",
            "chat_id": None,
            "voter_database": {"name": None, "status": None},
            "contract": None,
            "time_zone": "America/Los_Angeles",
            "audio_recording_config": {"permission": "no_recording"},
        }

    def response_for(self, request: http.Request) -> http.Response:
        method = request.method.upper()
        path = request.path.split("?", 1)[0]

        if method == "OPTIONS":
            return _json(204, {})
        if path in {"/health", "/generate_204"} and method in {"GET", "HEAD"}:
            return http.Response.make(204, b"", {"X-Audit-Backend": "local"})

        if path == "/api/auth/token" and method == "POST":
            form = _form(request)
            if form.get("username") != AUDIT_EMAIL or form.get("password") != AUDIT_PASSWORD:
                return _json(401, {"detail": "Invalid local audit credentials"})
            return _json(
                200,
                {
                    "access_token": _token("access", 24 * 60 * 60),
                    "refresh_token": _token("refresh", 15 * 24 * 60 * 60),
                    "token_type": "bearer",
                },
            )
        if path == "/api/auth/refresh" and method == "POST":
            return _json(200, {"access_token": _token("access", 24 * 60 * 60)})
        if path == "/api/auth/profile" and method == "GET":
            return _json(200, self._profile())
        if path == "/api/auth/ws_token" and method == "GET":
            return _json(200, {"access_token": "local-websocket-token"})
        if path == "/api/auth/logout" and method == "POST":
            self._clear_shift()
            return _json(200, {})

        if path == "/api/selector/project" and method == "GET":
            return _json(200, {"items": [self._project()], "total": 1, "page": 1, "size": 50, "pages": 1})
        if path == "/api/projects/" and method == "GET":
            return _json(200, {"items": [self._project()], "total": 1, "page": 1, "size": 50, "pages": 1})
        if path.startswith(f"/api/projects/{AUDIT_PROJECT_ID}") and path.endswith("/restricted_areas"):
            return _json(200, {"type": "FeatureCollection", "features": [], "permission": "no_recording"})
        if path in {f"/api/projects/{AUDIT_PROJECT_ID}", f"/api/projects/{AUDIT_PROJECT_ID}/short_info"}:
            return _json(200, self._project())

        if path == "/api/mobile/work_shift/status_v2" and method == "GET":
            return _json(
                200,
                {
                    "device_id": self.shift_device_id,
                    "work_shift_id": self.shift_id,
                    "project_id": self.shift_project_id,
                    "start_time": self.shift_started_at,
                },
            )
        if path == "/api/mobile/work_shift/generate" and method == "POST":
            payload = _json_body(request)
            self.shift_id = str(uuid.uuid4())
            self.shift_started_at = datetime.now(timezone.utc).isoformat()
            self.shift_device_id = payload.get("device_id") if isinstance(payload, dict) else None
            self.shift_project_id = (
                payload.get("project_id") if isinstance(payload, dict) else AUDIT_PROJECT_ID
            )
            if not isinstance(self.shift_project_id, str):
                self.shift_project_id = AUDIT_PROJECT_ID
            self._save_state()
            return _json(200, {"work_shift_id": self.shift_id, "start_time": self.shift_started_at})
        if path == "/api/mobile/work_shift/finalize_v2" and method == "POST":
            self._clear_shift()
            return _json(200, {})
        if path in {"/api/mobile/work_shift/pause", "/api/mobile/work_shift/resume"} and method == "POST":
            return _json(200, {})
        if path == "/api/work_shift/" and method == "GET":
            return _json(200, {"items": [], "total": 0, "page": 1, "size": 5, "pages": 0})

        if path == "/api/earnings/balance/" and method == "GET":
            return _json(
                200,
                {
                    "ready_for_payment": 0,
                    "pending": 0,
                    "next_payment_date": None,
                    "same_day_payout_enabled": False,
                },
            )
        if path == "/api/earnings/account/" and method == "GET":
            return _json(200, {"status": "not_registered", "onboarding_link": None})
        if path == "/api/earnings/totals-by-rate-type/" and method == "GET":
            return _json(200, {"bonus": {"total": 0, "count": 0}, "increased_rate": {"total": 0, "count": 0}})

        if path.startswith("/rest/v1/rpc/get_unread_chat_count"):
            return _json(200, 0)
        if path.startswith("/rest/v1/"):
            return _json(200, [])

        if path.startswith("/api/mobile/") or path in {"/api/sentry", "/api/upload/"}:
            return _json(200, {})
        if method == "GET":
            return _json(200, {"items": [], "total": 0, "page": 1, "size": 50, "pages": 0})
        return _json(200, {})
