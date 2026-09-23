"""Sensor batch upload + restricted-area geofences.

  POST /api/mobile/sensor/batch_upload  {"records": [<envelope>]}, all of one
      sensor_type (sensors-telemetry §1). Envelope: {record_id, work_shift_id,
      device_id, sensor_type, started_at, ended_at, sensor_readings[]}.
      gps/IMU/motionActivity started_at/ended_at are epoch-ms numbers;
      wifi/ble are ISO strings (§2). Server must tolerate duplicate
      record_ids — rows are re-sent verbatim after a failed upload (§6).
  POST /api/projects/{id}/restricted_areas  {lat, lon, radius_km} ->
      {features: [...], permission: <AudioRecordingPermission>} (§11).
"""

from flask import Blueprint, jsonify, request

from . import state
from .auth import detail, require_auth

bp = Blueprint("sensors", __name__)

SENSOR_TYPES = {
    "gps", "wifi", "ble", "accelerometer", "gyroscope", "magnetometer",
    "motionActivity",
}


@bp.post("/api/mobile/sensor/batch_upload")
@require_auth
def batch_upload():
    body = request.get_json(silent=True) or {}
    records = body.get("records")
    if not isinstance(records, list):
        return detail(400, "records must be an array")
    user = request.mock_user
    for rec in records:
        if not isinstance(rec, dict):
            return detail(400, "records must be objects")
        st = rec.get("sensor_type")
        if st not in SENSOR_TYPES:
            return detail(400, f"unknown sensor_type: {st!r}")
        if not rec.get("record_id") or not rec.get("device_id"):
            return detail(400, "record_id and device_id are required")
        if not isinstance(rec.get("sensor_readings"), list):
            return detail(400, "sensor_readings must be an array")
        stored = {
            "user_id": str(user["id"]),
            "received_at": state.iso_now(),
            **{k: rec.get(k) for k in (
                "record_id", "work_shift_id", "device_id", "sensor_type",
                "started_at", "ended_at", "sensor_readings")},
        }
        state.sensor_records.append(stored)
        state.capture("sensors", stored)
    # Response body is never read by the client; only HTTP 200 matters
    # (sensors-telemetry §1).
    return jsonify({})


@bp.post("/api/projects/<project_id>/restricted_areas")
@require_auth
def restricted_areas(project_id):
    project = state.PROJECTS.get(project_id)
    if project is None:
        return detail(404, "Project not found")
    permission = (project.get("audio_recording_config") or {}).get(
        "permission", "no_recording")
    # Consumed: response.features (GeoJSON Features; zipCode/zip_code props)
    # and response.permission (useAudioRestrictionZones.ts:124-137). The
    # project's restricted zones come from its fixture (empty = no zones).
    return jsonify({
        "features": project.get("restricted_area_features", []),
        "permission": permission,
    })
