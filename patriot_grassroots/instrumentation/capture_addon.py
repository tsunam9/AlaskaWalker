"""Persist unredacted HTTP, WebSocket, TCP, UDP, and DNS messages from mitmproxy.

The output intentionally contains credentials and personal data. It is written under a
gitignored directory with restrictive permissions and must never be committed.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from mitmproxy import ctx, dns, http, tcp, udp

from local_backend import LocalAuditBackend


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: bytes) -> str:
    return value.decode("latin-1")


def _headers(fields: Iterable[tuple[bytes, bytes]]) -> list[list[str]]:
    # A list preserves order, original casing, and duplicate header fields.
    return [[_text(name), _text(value)] for name, value in fields]


class ExactCapture:
    def __init__(self) -> None:
        self.root: Path | None = None
        self.events: Path | None = None
        self.lock = threading.Lock()
        self.sequence = 0
        self.backend = LocalAuditBackend()

    def load(self, loader: Any) -> None:
        loader.add_option(
            "capture_root",
            str,
            "",
            "Directory in which to create the unredacted capture run",
        )

    def running(self) -> None:
        configured = ctx.options.capture_root or os.environ.get("CAPTURE_ROOT", "captures")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.root = Path(configured).expanduser().resolve() / stamp
        (self.root / "bodies").mkdir(parents=True, mode=0o700)
        os.chmod(self.root, 0o700)
        self.events = self.root / "events.jsonl"
        self.events.touch(mode=0o600)
        os.chmod(self.events, 0o600)
        ctx.log.info(f"Unredacted capture directory: {self.root}")

    def _write_body(self, flow_id: str, direction: str, body: bytes | None) -> dict[str, Any]:
        payload = body or b""
        assert self.root is not None
        relative = Path("bodies") / f"{flow_id}.{direction}.bin"
        target = self.root / relative
        target.write_bytes(payload)
        os.chmod(target, 0o600)
        return {
            "path": str(relative),
            "length": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "base64": base64.b64encode(payload).decode("ascii"),
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
        if request.path == "/__patriot_capture_event" and request.host in {
            "127.0.0.1",
            "localhost",
        }:
            self._event(
                "instrumented_inbound_event",
                flow.id,
                body=self._write_body(flow.id, "inbound-event", request.raw_content),
            )
            flow.response = http.Response.make(
                204,
                b"",
                {
                    "Access-Control-Allow-Origin": "*",
                    "Cache-Control": "no-store",
                },
            )
            return

        if request.host in {"127.0.0.1", "localhost"}:
            flow.response = self.backend.response_for(request)
            self._event(
                "local_backend_response",
                flow.id,
                method=request.method,
                path=request.path,
                status_code=flow.response.status_code,
            )
            return

        # Audit isolation rule: record the fully decoded request but never create
        # an upstream connection to its requested destination.
        self._event("upstream_blocked", flow.id, destination=request.pretty_url)
        flow.response = http.Response.make(
            451,
            b'{"detail":"Blocked by local security-audit sink"}',
            {
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "no-store",
                "Content-Type": "application/json",
                "X-Audit-Sink": "blocked",
            },
        )

    def response(self, flow: http.HTTPFlow) -> None:
        response = flow.response
        if response is None:
            return
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
        self._event("http_error", flow.id, error=str(flow.error))

    def websocket_message(self, flow: http.HTTPFlow) -> None:
        if flow.websocket is None or not flow.websocket.messages:
            return
        message = flow.websocket.messages[-1]
        direction = "client_to_server" if message.from_client else "server_to_client"
        self._event(
            "websocket_message",
            flow.id,
            direction=direction,
            message_type="text" if message.is_text else "binary",
            content=self._write_body(flow.id, f"websocket-{len(flow.websocket.messages):06d}", message.content),
        )

    def tcp_message(self, flow: tcp.TCPFlow) -> None:
        message = flow.messages[-1]
        direction = "client_to_server" if message.from_client else "server_to_client"
        self._event(
            "tcp_message",
            flow.id,
            direction=direction,
            content=self._write_body(flow.id, f"tcp-{len(flow.messages):06d}", message.content),
        )

    def tcp_start(self, flow: tcp.TCPFlow) -> None:
        self._event("tcp_upstream_blocked", flow.id)
        flow.kill()

    def udp_message(self, flow: udp.UDPFlow) -> None:
        message = flow.messages[-1]
        direction = "client_to_server" if message.from_client else "server_to_client"
        self._event(
            "udp_message",
            flow.id,
            direction=direction,
            content=self._write_body(flow.id, f"udp-{len(flow.messages):06d}", message.content),
        )

    def udp_start(self, flow: udp.UDPFlow) -> None:
        self._event("udp_upstream_blocked", flow.id)
        flow.kill()

    def dns_request(self, flow: dns.DNSFlow) -> None:
        self._event(
            "dns_request",
            flow.id,
            questions=[str(question) for question in flow.request.questions],
        )
        flow.response = flow.request.fail(5)  # REFUSED; no upstream resolver.

    def dns_response(self, flow: dns.DNSFlow) -> None:
        answers = [] if flow.response is None else [str(answer) for answer in flow.response.answers]
        self._event("dns_response", flow.id, answers=answers)


addons = [ExactCapture()]
