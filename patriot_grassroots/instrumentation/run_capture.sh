#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
CAPTURE_DIR="${CAPTURE_DIR:-$SCRIPT_DIR/captures}"
LISTEN_HOST="${LISTEN_HOST:-127.0.0.1}"
LISTEN_PORT="${LISTEN_PORT:-${HOST_CAPTURE_PORT:-18081}}"
CAPTURE_MODE="${CAPTURE_MODE:-regular}"

if [[ ! -x "$VENV_DIR/bin/mitmdump" ]]; then
  python3 -m venv "$VENV_DIR"
  "$VENV_DIR/bin/python" -m pip install --disable-pip-version-check -r "$SCRIPT_DIR/requirements.txt"
fi

umask 077
mkdir -p "$CAPTURE_DIR"
printf 'Starting unredacted recorder on %s:%s\n' "$LISTEN_HOST" "$LISTEN_PORT"
printf 'Capture root: %s\n' "$CAPTURE_DIR"
MODE_ARGS=(--mode "regular@$LISTEN_HOST:$LISTEN_PORT")
if [[ "$CAPTURE_MODE" == "wireguard" ]]; then
  mkdir -p "$SCRIPT_DIR/build"
  MODE_ARGS=(--mode "wireguard:$SCRIPT_DIR/build/wireguard.conf@$LISTEN_HOST:$LISTEN_PORT")
elif [[ "$CAPTURE_MODE" != "regular" ]]; then
  printf 'CAPTURE_MODE must be regular or wireguard.\n' >&2
  exit 2
fi
exec "$VENV_DIR/bin/mitmdump" \
  "${MODE_ARGS[@]}" \
  --set "capture_root=$CAPTURE_DIR" \
  --set connection_strategy=lazy \
  --set upstream_cert=false \
  --set anticache=true \
  --set block_global=false \
  --set websocket=true \
  -s "$SCRIPT_DIR/capture_addon.py"
