#!/usr/bin/env python3
"""Bundle one completed capture and upload it to the dedicated logger service.

The logger protocol is intentionally small while its final VPS address is unknown:
an authenticated POST whose body is a tar.gz archive. Nothing is uploaded unless
both a destination and a dedicated logger token are explicitly supplied.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import ssl
import tarfile
import tempfile
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", type=Path, help="completed capture run directory")
    parser.add_argument(
        "--url",
        default=os.environ.get("LOGGER_UPLOAD_URL"),
        help="dedicated logger HTTPS endpoint (or LOGGER_UPLOAD_URL)",
    )
    parser.add_argument(
        "--token-env",
        default="LOGGER_UPLOAD_TOKEN",
        help="environment variable containing the dedicated logger bearer token",
    )
    parser.add_argument(
        "--allow-http-localhost",
        action="store_true",
        help="permit plain HTTP only for a logger on localhost/127.0.0.1",
    )
    parser.add_argument("--force", action="store_true", help="upload again after a receipt exists")
    return parser


def _validate_url(raw: str | None, allow_http_localhost: bool) -> str:
    if not raw:
        raise SystemExit("logger URL is unset; pass --url or set LOGGER_UPLOAD_URL")
    parsed = urllib.parse.urlparse(raw)
    if parsed.username or parsed.password or parsed.fragment:
        raise SystemExit("logger URL must not contain credentials or a fragment")
    if parsed.scheme == "https" and parsed.hostname:
        return raw
    local = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if parsed.scheme == "http" and local and allow_http_localhost:
        return raw
    raise SystemExit("logger URL must use HTTPS (plain HTTP is allowed only for localhost testing)")


def _post_archive(url: str, token: str, archive: Path, digest: str, run: str) -> tuple[int, str]:
    parsed = urllib.parse.urlsplit(url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if parsed.scheme == "https":
        connection: http.client.HTTPConnection = http.client.HTTPSConnection(
            parsed.hostname,
            port,
            timeout=120,
            context=ssl.create_default_context(),
        )
    else:
        connection = http.client.HTTPConnection(parsed.hostname, port, timeout=120)
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/vnd.alaska-campaign.capture+tar+gzip",
        "Content-Length": str(archive.stat().st_size),
        "X-Capture-Run": run,
        "X-Capture-SHA256": digest,
    }
    try:
        with archive.open("rb") as payload:
            # http.client streams file-like request bodies instead of holding the
            # potentially large audio/traffic archive in memory.
            connection.request("POST", path, body=payload, headers=headers)
            response = connection.getresponse()
            body = response.read(4096).decode("utf-8", errors="replace")
            return response.status, body
    finally:
        connection.close()


def _archive(capture: Path, target: Path) -> None:
    with tarfile.open(target, "w:gz", format=tarfile.PAX_FORMAT) as bundle:
        for source in sorted(capture.rglob("*")):
            if source.name == "upload-receipt.json" or not source.is_file():
                continue
            bundle.add(source, arcname=f"{capture.name}/{source.relative_to(capture)}", recursive=False)
    os.chmod(target, 0o600)


def main() -> int:
    args = _parser().parse_args()
    capture = args.capture.expanduser().resolve()
    if not (capture / "events.jsonl").is_file() or not (capture / "metadata.json").is_file():
        raise SystemExit(f"not a capture run: {capture}")
    metadata = json.loads((capture / "metadata.json").read_text(encoding="utf-8"))
    if "ended_at" not in metadata:
        raise SystemExit("capture is not finalized; stop the recorder before uploading")
    receipt_path = capture / "upload-receipt.json"
    if receipt_path.exists() and not args.force:
        raise SystemExit(f"capture already has an upload receipt: {receipt_path}")

    url = _validate_url(args.url, args.allow_http_localhost)
    token = os.environ.get(args.token_env)
    if not token:
        raise SystemExit(f"dedicated logger token is unset: {args.token_env}")

    descriptor, archive_name = tempfile.mkstemp(prefix="capture-", suffix=".tar.gz")
    os.close(descriptor)
    archive = Path(archive_name)
    try:
        _archive(capture, archive)
        with archive.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        archive_bytes = archive.stat().st_size
        status, response_body = _post_archive(url, token, archive, digest, capture.name)
        if not 200 <= status < 300:
            raise SystemExit(f"logger rejected upload with HTTP {status}: {response_body}")
        receipt = {
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "url": url,
            "archive_sha256": digest,
            "archive_bytes": archive_bytes,
            "http_status": status,
            "response": response_body,
        }
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        os.chmod(receipt_path, 0o600)
        print(f"uploaded {capture.name}: {archive_bytes} bytes, sha256={digest}")
        return 0
    finally:
        archive.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
