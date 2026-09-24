"""Minimal WebSocket acceptor for the ROS realtime channel.

[O] The stock app opens `ws://<ros>/websocket/?token=<jwt>&...` as soon as a
user+org are loaded and gates its offline-buffer drain on the socket being up
(push-realtime-endpoints.md §3). The wire protocol we must honor is tiny:

- client sends a literal text frame "ping" every 30 s (no reply expected —
  the client JSON-parses any non-"ping" frame, so never send "pong" text);
- client sends {"action":"sendmessage","data":"..."} envelopes after
  offline-drain uploads (no reply expected);
- server MAY push {"data": "<stringified json>"} envelopes (the "canvassed"
  side-channel) — the mock simply never does;
- a 101 handshake that stays open is all `websocketUp` needs.

Werkzeug's dev server has no WS support, so the upgrade is intercepted in a
WSGIRequestHandler subclass before WSGI dispatch and the frame loop runs on
the raw socket. Dependency-free.
"""

import base64
import hashlib
import struct

_WS_GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _read_exact(conn, count):
    buf = b""
    while len(buf) < count:
        chunk = conn.recv(count - len(buf))
        if not chunk:
            raise ConnectionError("websocket closed")
        buf += chunk
    return buf


def _send_frame(conn, opcode, payload=b""):
    header = bytes([0x80 | opcode])
    length = len(payload)
    if length < 126:
        header += bytes([length])
    elif length < 65536:
        header += bytes([126]) + struct.pack(">H", length)
    else:
        header += bytes([127]) + struct.pack(">Q", length)
    conn.sendall(header + payload)


def _handle_websocket(handler):
    """Complete the upgrade on the handler's raw socket and hold the loop."""
    conn = handler.connection
    key = handler.headers.get("Sec-WebSocket-Key", "")
    accept = base64.b64encode(hashlib.sha1(key.encode() + _WS_GUID).digest()).decode()
    conn.sendall(
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {accept}\r\n\r\n".encode()
    )
    handler.close_connection = True
    from . import state
    query = {}
    if "?" in handler.path:
        from urllib.parse import parse_qsl
        query = dict(parse_qsl(handler.path.split("?", 1)[1]))
    print(f"[numinar-mock] websocket open org={query.get('org_id', '-')}", flush=True)
    state.capture("websocket", {"event": "open", "path": handler.path,
                                "org_id": query.get("org_id"), "email": query.get("email")})
    try:
        while True:
            head = _read_exact(conn, 2)
            opcode = head[0] & 0x0F
            masked = head[1] & 0x80
            length = head[1] & 0x7F
            if length == 126:
                length = struct.unpack(">H", _read_exact(conn, 2))[0]
            elif length == 127:
                length = struct.unpack(">Q", _read_exact(conn, 8))[0]
            mask = _read_exact(conn, 4) if masked else b""
            payload = _read_exact(conn, length) if length else b""
            if masked:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            if opcode == 0x8:  # close
                _send_frame(conn, 0x8)
                break
            if opcode == 0x9:  # protocol-level ping -> pong
                _send_frame(conn, 0xA, payload)
            # text/binary frames ("ping", sendmessage envelopes): accepted,
            # deliberately unanswered (client JSON-parses any non-"ping").
    except (ConnectionError, OSError):
        pass
    finally:
        state.capture("websocket", {"event": "close", "org_id": query.get("org_id")})
        print("[numinar-mock] websocket closed", flush=True)


class WebSocketInterceptHandlerMixin:
    """WSGIRequestHandler mixin: divert /websocket upgrades before WSGI."""

    def run_wsgi(self):
        path = self.path.split("?", 1)[0].rstrip("/")
        if self.headers.get("Upgrade", "").lower() == "websocket" and path == "/websocket":
            try:
                _handle_websocket(self)
            except Exception as exc:  # never take the server thread down
                print(f"[numinar-mock] websocket error: {exc}", flush=True)
            return
        super().run_wsgi()
