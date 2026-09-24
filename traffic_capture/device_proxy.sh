#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-status}"
DEVICE_PORT="${DEVICE_PORT:-18084}"
HOST_CAPTURE_PORT="${HOST_CAPTURE_PORT:-18083}"

case "$ACTION" in
  enable)
    adb reverse "tcp:$DEVICE_PORT" "tcp:$HOST_CAPTURE_PORT"
    adb shell settings put global http_proxy "127.0.0.1:$DEVICE_PORT"
    printf 'Device-wide proxy enabled: device %s -> host capture %s.\n' \
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
    printf 'Usage: %s {enable|disable|status}\n' "$0" >&2
    exit 2
    ;;
esac
