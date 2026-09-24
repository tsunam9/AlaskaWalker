"""Passively record allowlisted HTTP(S) and WebSocket traffic.

This addon never creates a response, changes a request, adds a header, or blocks an
upstream. Captures are intentionally exact and therefore contain credentials, PII,
GPS coordinates, and possibly audio. Runtime output belongs only in the gitignored
capture directory.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from mitmproxy import ctx, http


DEFAULT_HOSTS = (
    # Patriot / ValidNation first-party traffic.
    "api.validnation.ai",
    "tfnnpqpvdjisoizvciyr.supabase.co",
    # Numinar first-party traffic.
    "fast-api.numinar.com",
    "rust-server.numinar.com",
    "auth.numinar.com",
    # Recovered stock telemetry/update endpoints. Some SDKs may bypass the proxy.
    "firebaseinstallations.googleapis.com",
    "firebaseremoteconfig.googleapis.com",
    "fcmregistrations.googleapis.com",
    "o447951.ingest.sentry.io",
    "o463956.ingest.sentry.io",
    "api.mixpanel.com",
    "app.adjust.com",
    "gdpr.adjust.com",
    "u.expo.dev",
    "exp.host",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _latin1(value: bytes) -> str:
    return value.decode("latin-1")


def _headers(fields: Iterable[tuple[bytes, bytes]]) -> list[list[str]]:
    # Preserve order, casing, and duplicate fields. Never redact the local evidence.
    return [[_latin1(name), _latin1(value)] for name, value in fields]


class ForwardCapture:
    def __init__(self) -> None:
        self.root: Path | None = None
        self.events: Path | None = None
        self.hosts: frozenset[str] = frozenset(DEFAULT_HOSTS)
        self.lock = threading.Lock()
        self.sequence = 0
        self.captured_flows: set[str] = set()

    def load(self, loader: Any) -> None:
        loader.add_option(
            "capture_root",
            str,
            "",
            "Parent directory in which to create the sensitive capture run",
        )
        loader.add_option(
            "capture_hosts",
            str,
            ",".join(DEFAULT_HOSTS),
            "Comma-separated host allowlist; '*' records all proxy traffic",
        )
        loader.add_option(
            "capture_label",
            str,
            "stock-real-backend",
            "Non-secret label written into run metadata",
        )

    def running(self) -> None:
        configured = ctx.options.capture_root or os.environ.get(
            "CAPTURE_ROOT", "traffic_capture/captures"
        )
        parsed_hosts = {
            host.strip().lower().rstrip(".")
            for host in ctx.options.capture_hosts.split(",")
            if host.strip()
        }
        if not parsed_hosts:
            raise RuntimeError("capture_hosts must contain at least one exact hostname")
        self.hosts = frozenset(parsed_hosts)

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.root = Path(configured).expanduser().resolve() / stamp
        (self.root / "bodies").mkdir(parents=True, mode=0o700)
        os.chmod(self.root, 0o700)
        os.chmod(self.root / "bodies", 0o700)
        self.events = self.root / "events.jsonl"
        self.events.touch(mode=0o600)
        os.chmod(self.events, 0o600)
        metadata = {
            "format": 1,
            "started_at": _now(),
            "label": ctx.options.capture_label,
            "hosts": sorted(self.hosts),
            "forwarding": True,
            "redacted": False,
        }
        metadata_path = self.root / "metadata.json"
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.chmod(metadata_path, 0o600)
        ctx.log.warn(f"Sensitive, unredacted capture directory: {self.root}")

    def _selected(self, flow: http.HTTPFlow) -> bool:
        return "*" in self.hosts or flow.request.host.lower().rstrip(".") in self.hosts

    def done(self) -> None:
        if self.root is None:
            return
        metadata_path = self.root / "metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["ended_at"] = _now()
        metadata["event_count"] = self.sequence
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.chmod(metadata_path, 0o600)

    def _write_body(self, flow_id: str, direction: str, body: bytes | None) -> dict[str, Any]:
        assert self.root is not None
        payload = body or b""
        relative = Path("bodies") / f"{flow_id}.{direction}.bin"
        target = self.root / relative
        target.write_bytes(payload)
        os.chmod(target, 0o600)
        return {
            "path": str(relative),
            "length": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }

    def _event(self, kind: str, flow_id: str, **data: Any) -> None:
        assert self.events is not None
        with self.lock:
            self.sequence += 1
            record = {
                "sequence": self.sequence,
                "captured_at": _now(),
                "kind": kind,
                "flow_id": flow_id,
                **data,
            }
            with self.events.open("a", encoding="utf-8") as handle:
                json.dump(record, handle, ensure_ascii=False, separators=(",", ":"))
                handle.write("\n")

    def request(self, flow: http.HTTPFlow) -> None:
        if not self._selected(flow):
            return
        self.captured_flows.add(flow.id)
        request = flow.request
        self._event(
            "http_request",
            flow.id,
            method=request.method,
            scheme=request.scheme,
            authority=request.host_header,
            host=request.host,
            port=request.port,
            path=request.path,
            pretty_url=request.pretty_url,
            http_version=request.http_version,
            headers=_headers(request.headers.fields),
            body=self._write_body(flow.id, "request", request.raw_content),
        )
        # Deliberately do not assign flow.response or mutate the request.

    def response(self, flow: http.HTTPFlow) -> None:
        if flow.id not in self.captured_flows or flow.response is None:
            return
        response = flow.response
        self._event(
            "http_response",
            flow.id,
            status_code=response.status_code,
            reason=response.reason,
            http_version=response.http_version,
            headers=_headers(response.headers.fields),
            body=self._write_body(flow.id, "response", response.raw_content),
        )

    def error(self, flow: http.HTTPFlow) -> None:
        if flow.id in self.captured_flows:
            self._event("http_error", flow.id, error=str(flow.error))

    def websocket_message(self, flow: http.HTTPFlow) -> None:
        if flow.id not in self.captured_flows:
            return
        if flow.websocket is None or not flow.websocket.messages:
            return
        message = flow.websocket.messages[-1]
        direction = "client_to_server" if message.from_client else "server_to_client"
        self._event(
            "websocket_message",
            flow.id,
            direction=direction,
            message_type="text" if message.is_text else "binary",
            content=self._write_body(
                flow.id,
                f"websocket-{len(flow.websocket.messages):06d}",
                message.content,
            ),
        )


addons = [ForwardCapture()]
