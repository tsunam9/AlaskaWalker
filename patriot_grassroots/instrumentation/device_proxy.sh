#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-status}"
DEVICE_PORT="${DEVICE_PORT:-18080}"
HOST_CAPTURE_PORT="${HOST_CAPTURE_PORT:-18081}"

case "$ACTION" in
  app-only)
    # The instrumented Patriot build has every recovered origin rewritten to this
    # device loopback port. Bridge it to a distinct host port so unrelated phone
    # apps and desktop processes using localhost:18080 cannot enter the capture.
    adb shell settings put global http_proxy :0
    adb reverse "tcp:$DEVICE_PORT" "tcp:$HOST_CAPTURE_PORT"
    printf 'Patriot-only route enabled: device %s -> host recorder %s.\n' \
      "$DEVICE_PORT" "$HOST_CAPTURE_PORT"
    ;;
  enable)
    adb reverse "tcp:$DEVICE_PORT" "tcp:$HOST_CAPTURE_PORT"
    adb shell settings put global http_proxy "127.0.0.1:$DEVICE_PORT"
    printf 'Device-wide HTTP(S) proxy enabled: device %s -> host recorder %s.\n' \
      "$DEVICE_PORT" "$HOST_CAPTURE_PORT"
    ;;
  disable)
    adb shell settings put global http_proxy :0
    adb reverse --remove "tcp:$DEVICE_PORT" 2>/dev/null || true
    printf 'Device proxy disabled.\n'
    ;;
  status)
    adb devices -l
    printf 'http_proxy=%s\n' "$(adb shell settings get global http_proxy 2>/dev/null || true)"
    adb reverse --list 2>/dev/null || true
    ;;
  *)
    printf 'Usage: %s {app-only|enable|disable|status}\n' "$0" >&2
    exit 2
    ;;
esac
