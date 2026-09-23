"""Device registration, events, FCM token, version check.

  POST   /api/mobile/device/update_info     16-field body (shift-lifecycle §6);
         links device<->user. The backend 403s events from unlinked devices
         (ensureDeviceLinked.ts:25-33).
  POST   /api/mobile/device/event/send      envelope {device_id, created_at,
         event_type, payload} (mobileEvents.ts:9-28)
  POST   /api/mobile/device/event/batch_send {device_id, events:[envelope]}
  POST   /api/mobile/device/unlink          {device_id}
  POST   /api/mobile/notifications/token    {device_id, token}
  DELETE /api/mobile/notifications/token?device_id=
  POST   /api/settings/versions             version/live-update check,
         unauthenticated-allowed (mutations/mobile/getUpdateInfo.ts:13)
"""

from flask import Blueprint, jsonify, request

from . import state
from .auth import detail, require_auth

bp = Blueprint("device", __name__)

UPDATE_INFO_FIELDS = {
    "model", "device_id", "name", "is_complete_sensors", "is_root",
    "os_version", "permission_gps", "permission_ble", "permission_wifi",
    "permission_motion", "push_permission_granted",
    "push_notifications_enabled", "platform", "software_version", "timezone",
}


@bp.post("/api/mobile/device/update_info")
@require_auth
def update_info():
    body = request.get_json(silent=True) or {}
    device_id = body.get("device_id")
    if not device_id:
        return detail(400, "device_id is required")
    state.link_device(request.mock_user["id"], device_id, info=body)
    return jsonify({})  # nothing consumed


@bp.post("/api/mobile/device/unlink")
@require_auth
def unlink():
    body = request.get_json(silent=True) or {}
    device_id = body.get("device_id")
    if not device_id:
        return detail(400, "device_id is required")
    state.unlink_device(device_id)
    return jsonify({})


def _accept_events(user, device_id, envelopes):
    if not device_id:
        return detail(400, "device_id is required")
    # The backend rejects events from a device that has not been linked via
    # update_info (ensureDeviceLinked.ts:25-33 — single-flight update_info
    # before the first event of a session). [R]-grade behavior per the code
    # comment; exact status 403 per that comment.
    if not state.device_is_linked(device_id, user["id"]):
        return detail(403, "Device is not linked to the current user")
    for env in envelopes:
        entry = {
            "user_id": str(user["id"]),
            "device_id": device_id,
            "received_at": state.iso_now(),
            "created_at": env.get("created_at"),
            "event_type": env.get("event_type"),
            "payload": env.get("payload"),
        }
        state.device_events.append(entry)
        state.capture("device_events", entry)
    return None


@bp.post("/api/mobile/device/event/send")
@require_auth
def event_send():
    body = request.get_json(silent=True) or {}
    err = _accept_events(request.mock_user, body.get("device_id"), [body])
    return err or jsonify({})


@bp.post("/api/mobile/device/event/batch_send")
@require_auth
def event_batch_send():
    body = request.get_json(silent=True) or {}
    events = body.get("events")
    if not isinstance(events, list):
        return detail(400, "events must be an array")
    err = _accept_events(request.mock_user, body.get("device_id"), events)
    return err or jsonify({})


@bp.post("/api/mobile/notifications/token")
@require_auth
def fcm_token_register():
    body = request.get_json(silent=True) or {}
    device_id = body.get("device_id")
    token = body.get("token")
    if not device_id or not token:
        return detail(400, "device_id and token are required")
    d = state.devices.setdefault(device_id, {"linked": False})
    d["fcm_token"] = token
    return jsonify({})


@bp.delete("/api/mobile/notifications/token")
@require_auth
def fcm_token_unregister():
    device_id = request.args.get("device_id")
    if not device_id:
        return detail(400, "device_id is required")
    d = state.devices.get(device_id)
    if d is not None:
        d["fcm_token"] = None
    return jsonify({})


@bp.post("/api/settings/versions")
def versions():
    # allows unauthorized (requiresAuth:false, mutations/mobile/getUpdateInfo.ts:13)
    # Consumed (useMobileLiveUpdates.ts:68-94): force_native_update,
    # force_live_update, live_update_bundle_id, bundle_url, checksum,
    # has_native_update. Mock: never any update.
    return jsonify({
        "force_native_update": False,
        "force_live_update": False,
        "live_update_bundle_id": None,
        "bundle_url": None,
        "checksum": None,
        "has_native_update": False,
    })
