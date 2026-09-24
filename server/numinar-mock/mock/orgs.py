"""Profile and organization bootstrap endpoints."""

from flask import Blueprint, g, jsonify, request

from . import state
from .common import current_org_id, detail, require_auth

bp = Blueprint("orgs", __name__)


@bp.route("/api/v1/mobile_204", methods=["HEAD", "GET"])
def mobile_204():
    return "", 204


@bp.get("/api/v1/me")
@require_auth()
def get_me():
    return jsonify(state.public_user(g.current_user))


@bp.put("/api/v1/me")
@require_auth()
def update_me():
    data = request.get_json(silent=True) or {}
    if "has_registered" in data:
        g.current_user["has_registered"] = bool(data["has_registered"])
    return jsonify(state.public_user(g.current_user))


@bp.get("/api/v1/my-orgs-mobile")
@require_auth()
def my_orgs():
    ids = set(g.current_user.get("org_ids") or [])
    ids.update(state.memberships.get(g.current_user["id"], []))
    return jsonify([org for oid, org in state.ORGS.items() if oid in ids])


@bp.get("/api/v2/orgs/<org_id>")
@require_auth()
def org_detail(org_id):
    org = state.ORGS.get(org_id)
    return jsonify(org) if org else detail("Organization not found", 404)


@bp.get("/api/v1/public-orgs")
@require_auth()
def public_orgs():
    return jsonify(list(state.ORGS.values()))


@bp.post("/api/v1/orgs/<org_id>/join")
@require_auth()
def join_org(org_id):
    if org_id not in state.ORGS:
        return detail("Organization not found", 404)
    memberships = state.memberships.setdefault(g.current_user["id"], [])
    if org_id not in memberships:
        memberships.append(org_id)
    if org_id not in g.current_user.setdefault("org_ids", []):
        g.current_user["org_ids"].append(org_id)
    return jsonify({"joined": True, "organization": state.ORGS[org_id]})


@bp.put("/api/v1/orgs/<org_id>/invite-status")
@require_auth()
def invite_status(org_id):
    if org_id not in state.ORGS:
        return detail("Organization not found", 404)
    value = (request.get_json(silent=True) or {}).get("invite_status")
    if value not in {"accepted", "declined", "accept", "decline"}:
        return detail("invite_status is required")
    if value in {"accepted", "accept"}:
        memberships = state.memberships.setdefault(g.current_user["id"], [])
        if org_id not in memberships: memberships.append(org_id)
    return jsonify({"org_id": org_id, "invite_status": value})


@bp.post("/api/v1/verification-email")
@require_auth(verify_email=False)
def verification_email():
    return jsonify({"sent": True, "email": g.current_user["email"]})
