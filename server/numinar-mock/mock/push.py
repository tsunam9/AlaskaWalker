"""Push inbox, contact matching, and relational payment endpoints."""

import copy
import uuid

from flask import Blueprint, g, jsonify, request

from . import state
from .common import detail, require_auth

bp = Blueprint("push", __name__)


@bp.post("/api/v1/push/tokens")
@require_auth()
def save_push_token():
    data = request.get_json(silent=True) or {}
    required = {"expo_push_token", "is_android", "device_push_token"}
    if not required.issubset(data): return detail("Incomplete push token")
    token = str(data["expo_push_token"])
    state.push_tokens[token] = {**copy.deepcopy(data), "user_id": g.current_user["id"], "updated_at": state.iso_now()}
    return jsonify({"saved": True})


@bp.delete("/api/v1/push/tokens/<path:token>")
@require_auth()
def delete_push_token(token):
    state.push_tokens.pop(token, None)
    return jsonify({"deleted": True})


@bp.get("/api/v1/push/notifications")
@require_auth()
def get_notifications(): return jsonify(state.notifications)


@bp.post("/api/v1/push/notifications/read")
@require_auth()
def read_notifications():
    ids = {str(value) for value in (request.get_json(silent=True) or {}).get("message_ids", [])}
    for item in state.notifications:
        if str(item.get("id")) in ids: item["read_at"] = state.iso_now()
    return jsonify({"updated": len(ids)})


@bp.post("/api/v1/push/notifications/read-all")
@require_auth()
def read_all():
    now = state.iso_now()
    for item in state.notifications: item["read_at"] = item.get("read_at") or now
    return jsonify({"updated": len(state.notifications)})


@bp.delete("/api/v1/push/notifications")
@require_auth()
def delete_all():
    count = len(state.notifications); state.notifications.clear()
    return jsonify({"deleted": count})


@bp.delete("/api/v1/push/notifications/bulk")
@require_auth()
def delete_bulk():
    data = request.get_json(silent=True)
    ids = data if isinstance(data, list) else (data or {}).get("message_ids", (data or {}).get("ids", []))
    ids = {str(value) for value in ids}
    before = len(state.notifications)
    state.notifications[:] = [item for item in state.notifications if str(item.get("id")) not in ids]
    return jsonify({"deleted": before - len(state.notifications)})


@bp.get("/api/v1/contact-matches")
@require_auth()
def contact_match_status(): return jsonify(state.contact_matches)


@bp.post("/api/v1/contact-matches")
@require_auth()
def create_contact_match():
    contacts = (request.get_json(silent=True) or {}).get("contact_data")
    if not isinstance(contacts, list): return detail("contact_data must be an array")
    match = {"id": "match_" + uuid.uuid4().hex[:12], "status": "completed", "match_state": "AK", "created_at": state.iso_now(), "contact_count": len(contacts)}
    state.contact_matches.append(match)
    state.voter_contacts.clear()
    for index, contact in enumerate(contacts[:len(state.VOTERS)]):
        voter = copy.deepcopy(list(state.VOTERS.values())[index])
        display = contact.get("displayName") or contact.get("givenName") or voter["first_name"]
        voter["contact_names"] = [display]; state.voter_contacts.append(voter)
    return jsonify(match)


@bp.get("/api/v1/voter-contacts")
@bp.get("/api/v1/voter-contacts/<project_id>")
@require_auth()
def contacts(project_id=None): return jsonify(state.voter_contacts)


@bp.get("/api/v2/me/relational-payment")
@require_auth()
def payment():
    relational = sum(i.get("_mock_type") in {"relational", "relational-text"} for i in state.interactions)
    return jsonify({"relational_paid_potential": round(relational * 2.5, 2), "relational_paid_pending_contacts": relational, "relational_paid_out_contacts": 0, "relational_paid_potential_contacts": relational})


@bp.post("/api/v2/me/relational-payment")
@require_auth()
def request_payment():
    timezone = (request.get_json(silent=True) or {}).get("timezone")
    if not timezone: return detail("timezone is required")
    row = {"id": "payout_" + uuid.uuid4().hex[:12], "user_id": g.current_user["id"], "timezone": timezone, "status": "submitted", "created_at": state.iso_now()}
    state.payout_requests.append(row)
    return jsonify(row)
