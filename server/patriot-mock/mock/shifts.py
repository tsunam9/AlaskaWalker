"""Work-shift lifecycle — /api/mobile/work_shift/*.

State machine and wire shapes per audit/shift-lifecycle.md (verified against
/tmp/vn_src 2026-09-20):

  generate     {device_id, project_id, start_time, state_payload, time_zone}
               -> 200 {work_shift_id, start_time} (only fields consumed,
               useMobileShift.ts:146-147)
  status_v2    GET, no params -> 200 {device_id, work_shift_id, project_id,
               start_time} (only fields consumed, useMobileShift.ts:102-106)
  pause/resume {work_shift_id, button_pressed_time} -> 200; the client DROPS
               the outbox row on 400/404 (uploadShiftBreakEventBatch.ts:26-34)
  finalize_v2  JSON ARRAY [{work_shift_id, end_time, state_payload?,
               data_complete: true|false|null}] -> 200; nothing consumed

Server-behavior hypotheses ([H], not recoverable from client code) are marked
inline; each was chosen to keep the stock client's state machine coherent.
"""

from flask import Blueprint, jsonify, request

from . import state
from .auth import detail, require_auth

bp = Blueprint("shifts", __name__)


@bp.post("/api/mobile/work_shift/generate")
@require_auth
def generate():
    body = request.get_json(silent=True) or {}
    device_id = body.get("device_id")
    project_id = body.get("project_id")
    if not device_id or not project_id:
        return detail(400, "device_id and project_id are required")
    project = state.PROJECTS.get(project_id)
    if project is None:
        return detail(404, "Project not found")
    user = request.mock_user
    existing = state.active_shift_for_user(user["id"])
    if existing is not None:
        # [H] the stock client never sends this (it pre-checks status_v2 and
        # interrupts via finalize_v2 first). 409 surfaces client bugs loudly
        # in the mock log instead of silently double-shifting.
        return detail(409, "User already has an active work shift")
    state.link_device(user["id"], device_id)
    s = state.new_shift(user["id"], device_id, project_id,
                        body.get("start_time"), body.get("state_payload"),
                        body.get("time_zone"))
    state.capture("shift_events", {
        "event": "generate", "user_id": str(user["id"]),
        "work_shift_id": s["work_shift_id"], "device_id": device_id,
        "project_id": project_id, "start_time": s["start_time"],
        "client_start_time": body.get("start_time"),
        "time_zone": body.get("time_zone"),
    })
    return jsonify({
        "work_shift_id": s["work_shift_id"],
        "start_time": s["start_time"],
    })


@bp.get("/api/mobile/work_shift/status_v2")
@require_auth
def status_v2():
    user = request.mock_user
    s = state.active_shift_for_user(user["id"])
    if s is not None:
        return jsonify({
            "device_id": s["device_id"],
            "work_shift_id": s["work_shift_id"],
            "project_id": s["project_id"],
            "start_time": s["start_time"],
        })
    # No active shift. The client's closed-shift detection needs
    # device_id == local device with a falsy work_shift_id
    # (useMobileShift.ts:102-106, checkAndStopIfClosed). [H] on the exact
    # null-field shape — consumed fields force device_id present +
    # work_shift_id null.
    return jsonify({
        "device_id": state.linked_device_for_user(user["id"]),
        "work_shift_id": None,
        "project_id": None,
        "start_time": None,
    })


def _break_event(required_status, target_status):
    body = request.get_json(silent=True) or {}
    sid = body.get("work_shift_id")
    pressed = body.get("button_pressed_time")
    s = state.get_shift(sid)
    if s is None or s["user_id"] != str(request.mock_user["id"]):
        # Client drops the row on 400/404 — a stale/foreign shift is exactly
        # the "event no longer applicable" case that code path exists for.
        return detail(404, "Work shift not found")
    if s["status"] == "finalized":
        return detail(400, "Work shift already finalized")
    if s["status"] != required_status:
        return detail(400, f"Work shift is not {required_status}")
    if target_status == "paused":
        s["breaks"].append({"pause": pressed, "resume": None})
        s["status"] = "paused"
    else:
        if s["breaks"] and s["breaks"][-1]["resume"] is None:
            s["breaks"][-1]["resume"] = pressed
        s["status"] = "active"
    state.capture("shift_events", {
        "event": target_status, "user_id": str(request.mock_user["id"]),
        "work_shift_id": sid, "button_pressed_time": pressed,
    })
    return jsonify({})  # nothing consumed


@bp.post("/api/mobile/work_shift/pause")
@require_auth
def pause():
    return _break_event("active", "paused")


@bp.post("/api/mobile/work_shift/resume")
@require_auth
def resume():
    return _break_event("paused", "active")


@bp.post("/api/mobile/work_shift/finalize_v2")
@require_auth
def finalize_v2():
    body = request.get_json(silent=True)
    if not isinstance(body, list):
        return detail(400, "Expected a JSON array")
    results = []
    for item in body:
        if not isinstance(item, dict):
            return detail(400, "Expected an array of objects")
        sid = item.get("work_shift_id")
        if not sid:
            return detail(400, "work_shift_id is required")
        s = state.get_shift(sid)
        if s is None:
            # The phone's shift_end outbox survives process/app restarts. The
            # mock now persists shifts too, but acknowledge rows created before
            # persistence existed so one stale ID cannot poison every Sync Now.
            user_id = str(request.mock_user["id"])
            already_recorded = any(
                orphan.get("work_shift_id") == sid
                and orphan.get("user_id") == user_id
                for orphan in state.orphaned_finalizations
            )
            if not already_recorded:
                state.orphaned_finalizations.append({
                    "work_shift_id": sid,
                    "user_id": user_id,
                    "received_at": state.iso_now(),
                    "end_time": item.get("end_time"),
                    "data_complete": item.get("data_complete"),
                    "reason": "shift_missing_after_mock_restart",
                })
            results.append(sid)
            continue
        if s["user_id"] != str(request.mock_user["id"]):
            return detail(404, "Work shift not found")
        if s["status"] == "finalized":
            # Idempotent acknowledgement handles a lost HTTP response without
            # leaving the stock client's durable shift_end row stuck forever.
            results.append(sid)
            continue
        # Cross-device interrupt sends data_complete:null and NO
        # state_payload (useMobileShift.ts:122-124) — accepted verbatim.
        state.finalize_shift(s, item.get("end_time"),
                             item.get("state_payload"),
                             item.get("data_complete"))
        state.capture("shift_events", {
            "event": "finalize", "user_id": str(request.mock_user["id"]),
            "work_shift_id": sid, "end_time": item.get("end_time"),
            "data_complete": item.get("data_complete"),
        })
        results.append(sid)
    return jsonify({})  # nothing consumed (useUploader.ts:68-71)
