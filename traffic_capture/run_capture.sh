#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
CAPTURE_DIR="${CAPTURE_DIR:-$SCRIPT_DIR/captures}"
LISTEN_HOST="${LISTEN_HOST:-127.0.0.1}"
LISTEN_PORT="${LISTEN_PORT:-18083}"
CAPTURE_HOSTS="${CAPTURE_HOSTS:-api.validnation.ai,tfnnpqpvdjisoizvciyr.supabase.co,fast-api.numinar.com,rust-server.numinar.com,auth.numinar.com,firebaseinstallations.googleapis.com,firebaseremoteconfig.googleapis.com,fcmregistrations.googleapis.com,o447951.ingest.sentry.io,o463956.ingest.sentry.io,api.mixpanel.com,app.adjust.com,gdpr.adjust.com,u.expo.dev,exp.host}"
CAPTURE_LABEL="${CAPTURE_LABEL:-stock-real-backend}"

if [[ ! -x "$VENV_DIR/bin/mitmdump" ]]; then
  python3 -m venv "$VENV_DIR"
  "$VENV_DIR/bin/python" -m pip install --disable-pip-version-check \
    -r "$SCRIPT_DIR/requirements.txt"
fi

umask 077
mkdir -p "$CAPTURE_DIR"
printf 'Starting pass-through capture proxy on %s:%s\n' "$LISTEN_HOST" "$LISTEN_PORT"
printf 'Sensitive capture root: %s\n' "$CAPTURE_DIR"
printf 'Exact host allowlist: %s\n' "$CAPTURE_HOSTS"
exec "$VENV_DIR/bin/mitmdump" \
  --mode "regular@$LISTEN_HOST:$LISTEN_PORT" \
  --set "capture_root=$CAPTURE_DIR" \
  --set "capture_hosts=$CAPTURE_HOSTS" \
  --set "capture_label=$CAPTURE_LABEL" \
  --set connection_strategy=lazy \
  --set block_global=false \
  --set websocket=true \
  -s "$SCRIPT_DIR/capture_addon.py"
