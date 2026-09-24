"""Minimal ROS/Twilio/Bandwidth and SSE compatibility surface."""

import json
import time

from flask import Blueprint, Response, jsonify, request, stream_with_context

from . import state
from .common import require_auth

bp = Blueprint("ros", __name__)


@bp.get("/api/v3/auth_token")
@require_auth()
def auth_token():
    # [H] The native Twilio SDK expects an opaque string token.
    return jsonify("mock-twilio-access-token")


@bp.get("/api/v3/twilio_numbers")
@require_auth()
def twilio_numbers(): return jsonify([{"phone_number": "+19075550100", "number": "+19075550100", "number_type": "calling"}])


@bp.post("/api/v3/amd_call")
@require_auth()
def amd_call():
    row = {**(request.get_json(silent=True) or {}), "received_at": state.iso_now()}
    state.ros_calls.append(row)
    return jsonify({"accepted": True, "state": row.get("state")})


@bp.get("/api/v3/outreach/status/<project_id>")
@require_auth()
def outreach_status(project_id):
    count = sum(str(i.get("project_id")) == project_id for i in state.interactions)
    return jsonify({"project_id": project_id, "calling": count, "completed": count, "texting_counts": {"sent": 0}})


@bp.get("/api/v3/project/<project_id>/queue")
@require_auth()
def call_queue(project_id): return jsonify({"queue": []})


@bp.get("/api/v3/project/loading_status/<project_id>")
@require_auth()
def loading_status(project_id): return jsonify({"project_id": project_id, "status": "ready"})


@bp.get("/api/v3/bandwidth/numbers")
@require_auth()
def bandwidth_numbers(): return jsonify({"bw_nums": [{"number": "+19075550102", "phone_number": "+19075550102", "status": "10DLC-VERIFIED"}]})


@bp.post("/api/v3/bandwidth/batch-texts")
@require_auth()
def batch_texts():
    data = request.get_json(silent=True) or {}
    return jsonify({"accepted": len(data.get("texts") or []), "status": "queued"})


def sse(event_name, payload):
    def events():
        yield f"event: {event_name}\ndata: {json.dumps(payload)}\n\n"
        while True:
            time.sleep(15)
            yield ": keepalive\n\n"
    return Response(stream_with_context(events()), mimetype="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@bp.get("/api/v1/projects/sse/updates")
@require_auth()
def project_updates(): return sse("update", {"status": "ready"})


@bp.get("/api/v3/events/source/outreach/<project_id>")
@require_auth()
def outreach_events(project_id): return sse("outreach_status", {"project_id": project_id, "status": "ready", "completed": 0})


@bp.get("/api/v3/events/source/calls/<project_id>")
@require_auth()
def call_events(project_id): return sse("call_update", {"type": "completed", "voter_id": "", "voter_phone_number": "", "voter_first_name": "", "voter_last_name": "", "call_status": "idle", "twilio_call_status": "idle", "registered_party_roll_up": ""})
