"""Interaction write path and canvassing QA telemetry."""

import copy

from flask import Blueprint, g, jsonify, request

from . import state
from .common import detail, require_auth

bp = Blueprint("interactions", __name__)

CANVASS_DISPOSITIONS = {"canvassed", "Not Home", "Refused", "Wrong Address", "Inaccessible Address", "Dropped Literature", "Other"}
CALL_DISPOSITIONS = {"answered", "call-back", "do-not-call", "no-answer", "voicemail", "wrong-number", "hung-up"}


def has_keys(item, keys): return all(key in item for key in keys)


def classify(item):
    """[R] interactions-surveys.md §1.1 guard order; first match wins."""
    if has_keys(item, ("project_id", "voter_id", "household_id", "latitude", "longitude")): return "canvass"
    if has_keys(item, ("project_id", "voter_id", "call_length")): return "call"
    if "voter_id" in item and item.get("survey_type") == "relational": return "relational"
    if has_keys(item, ("voter_id", "tag_id", "value")): return "tag"
    return "notes"


def validate(item, kind):
    if not isinstance(item, dict): return "Each interaction must be an object"
    if kind == "canvass":
        if item.get("disposition") not in CANVASS_DISPOSITIONS: return "Invalid canvass disposition"
        for key in ("user_latitude", "user_longitude"):
            if key in item and item[key] is not None and not isinstance(item[key], str):
                return f"{key} must be a string or null"
    elif kind == "call":
        if item.get("disposition") not in CALL_DISPOSITIONS: return "Invalid call disposition"
        if not isinstance(item.get("call_length"), (int, float)): return "call_length must be numeric"
    elif kind == "relational":
        if not has_keys(item, ("survey_id", "responses", "project_id", "created_at")): return "Incomplete relational survey interaction"
    elif kind == "tag":
        if not str(item.get("tag_id", "")) or item.get("value") is None or not item.get("org_id"): return "Incomplete tag interaction"
    else:
        if not has_keys(item, ("project_id", "voter_id", "value", "created_at", "id")): return "Incomplete notes interaction"
    responses = item.get("responses")
    if responses is not None and not isinstance(responses, list): return "responses must be an array"
    return None


def accept(item, forced_kind=None):
    kind = forced_kind or classify(item)
    error = validate(item, kind)
    if error: return kind, error, False
    inserted = state.add_interaction(item, kind)
    state.capture("interactions", {"type": kind, "duplicate": not inserted, "interaction": copy.deepcopy(item)})
    return kind, None, inserted


@bp.post("/api/v1/interactions/batch")
@require_auth()
def batch():
    items = request.get_json(silent=True)
    if not isinstance(items, list) or not items: return detail("Request body must be a non-empty array")
    results = []
    # Validate first so malformed mixed batches never partially land.
    for index, item in enumerate(items):
        if not isinstance(item, dict): return detail(f"Interaction {index}: Each interaction must be an object")
        kind = classify(item)
        error = validate(item, kind)
        if error: return detail(f"Interaction {index}: {error}")
        results.append((item, kind))
    inserted, duplicates, types = 0, 0, []
    for item, kind in results:
        _kind, _error, was_inserted = accept(item, kind)
        types.append(kind)
        inserted += int(was_inserted); duplicates += int(not was_inserted)
    return jsonify({"accepted": len(items), "inserted": inserted, "duplicates": duplicates, "types": types})


@bp.post("/api/v1/interactions/call")
@require_auth()
def direct_call():
    item = request.get_json(silent=True) or {}
    if not has_keys(item, ("project_id", "voter_id", "disposition", "call_length")): return detail("Incomplete call interaction")
    if item.get("disposition") not in CALL_DISPOSITIONS: return detail("Invalid call disposition")
    item.setdefault("user_id", g.current_user["id"]); item.setdefault("created_at", state.iso_now())
    _kind, error, _inserted = accept(item, "call")
    return detail(error) if error else jsonify({"accepted": True})


@bp.post("/api/v1/interactions/relational-text")
@require_auth()
def relational_text():
    item = request.get_json(silent=True) or {}
    required = ("user_id", "voter_id", "project_id", "outreach_type", "abev_status", "created_at", "device_id", "is_using_emulator")
    if not has_keys(item, required) or item.get("outreach_type") != "text": return detail("Incomplete relational-text interaction")
    state.add_interaction(item, "relational-text")
    state.capture("interactions", {"type": "relational-text", "interaction": item})
    return jsonify({"accepted": True})


@bp.post("/api/v1/canvassing-qa/tracking")
@require_auth()
def qa_tracking():
    data = request.get_json(silent=True) or {}
    allowed = {"project_id", "latitude", "longitude", "device_id", "device_geolocation_enabled", "device_geolocation_permission_status", "is_using_emulator"}
    if not isinstance(data, dict): return detail("Request body must be an object")
    row = {key: copy.deepcopy(value) for key, value in data.items() if key in allowed}
    row["received_at"] = state.iso_now()
    state.qa_pings.append(row)
    state.capture("qa_tracking", row)
    return jsonify({"accepted": True})
