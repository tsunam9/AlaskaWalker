"""Voter fixture download, search, nearby, and per-voter reads."""

import base64
import copy
import gzip
import json
import math

from flask import Blueprint, jsonify, request

from . import state
from .common import detail, require_auth

bp = Blueprint("voters", __name__)


def rows_to_columns(rows):
    if not rows: return {}
    keys = list(rows[0])
    return {key: [row.get(key) for row in rows] for key in keys}


def compress_voters(rows):
    # [R] canvassing-core §4/§11 + native GzipModule.java: JSON -> gzip ->
    # Android Base64.NO_WRAP. gzip.compress emits the same RFC 1952 format.
    raw = json.dumps(rows_to_columns(rows), separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return base64.b64encode(gzip.compress(raw)).decode("ascii")


def all_voters(): return [copy.deepcopy(v) for v in state.VOTERS.values()]


@bp.get("/api/v2/mobile-app/projects/<project_id>/voters")
@require_auth()
def project_voters(project_id):
    if project_id not in state.PROJECTS: return detail("Project not found", 404)
    rows = all_voters()
    if request.args.get("ignore_contacted", "false").lower() == "true":
        rows = [v for v in rows if not v.get("has_interaction")]
    limit = min(int(request.args.get("limit", 10000)), 10000)
    return jsonify({"voters_compressed": compress_voters(rows[:limit])})


def distance_km(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 6371 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@bp.get("/api/v1/nearby-voters")
@require_auth()
def nearby_voters():
    try:
        lat, lng = float(request.args["latitude"]), float(request.args["longitude"])
    except (KeyError, ValueError): return detail("latitude and longitude are required")
    # [H] Server radius is not recoverable; 25 km keeps the Alaska fixture coherent.
    rows = [v for v in all_voters() if distance_km(lat, lng, float(v["registration_address_latitude"]), float(v["registration_address_longitude"])) <= 25]
    return jsonify(rows)


@bp.get("/api/v1/mobile-voter-search")
@require_auth()
def search_voters():
    aliases = {"phone": "cell_phone_number", "address": "registration_address_1", "city": "registration_address_city", "state": "registration_address_state", "zip_code": "registration_address_zip_5", "numinar_id": "id"}
    ignored = {"limit", "offset"}
    terms = [(aliases.get(k, k), str(v).strip().lower()) for k, v in request.args.items() if k not in ignored and str(v).strip()]
    rows = [v for v in all_voters() if all(term in str(v.get(field, "")).lower() for field, term in terms)]
    offset, limit = int(request.args.get("offset", 0)), min(int(request.args.get("limit", 100)), 100)
    return jsonify(rows[offset:offset + limit])


@bp.get("/api/v1/voters/<voter_id>/notes")
@require_auth()
def voter_notes(voter_id):
    items = state.notes.get(voter_id, [])
    return jsonify("\n".join(str(item.get("value", "")) for item in items))


@bp.get("/api/v1/voters/<voter_id>/interactions")
@require_auth()
def voter_interactions(voter_id):
    return jsonify([i for i in state.interactions if str(i.get("voter_id")) == voter_id])


@bp.get("/api/v2/voter_tags/<voter_id>")
@require_auth()
def tags(voter_id):
    values = list((state.voter_tags.get(voter_id) or {}).values())
    return jsonify({"tags": {str(index): item for index, item in enumerate(values)}})


@bp.get("/api/v1/projects/<project_id>/voters/<voter_id>")
@require_auth()
def project_voter(project_id, voter_id):
    if project_id not in state.PROJECTS: return detail("Project not found", 404)
    voter = state.VOTERS.get(voter_id)
    return jsonify(voter) if voter else detail("Voter not found", 404)
