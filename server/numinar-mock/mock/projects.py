"""Project, survey, tag, statistics, and leaderboard read surfaces."""

import copy

from flask import Blueprint, jsonify, request

from . import state
from .common import current_org_id, detail, require_auth

bp = Blueprint("projects", __name__)

TAGS = [
    {"id": "tag_support", "tag_id": "tag_support", "name": "Candidate support", "tag_name": "Candidate support", "tag_type": "multi-choice", "response_set": ["Yes", "No", "Undecided"]},
    {"id": "tag_issue", "tag_id": "tag_issue", "name": "Priority issue", "tag_name": "Priority issue", "tag_type": "multi-choice", "response_set": ["Cost of living", "Energy", "Public safety"]},
    {"id": "tag_comment", "tag_id": "tag_comment", "name": "Canvasser comment", "tag_name": "Canvasser comment", "tag_type": "text", "response_set": []},
]


def org_projects():
    org_id = current_org_id()
    return [copy.deepcopy(p) for p in state.PROJECTS.values() if p.get("org_id") == org_id]


@bp.get("/api/v3/projects")
@require_auth()
def projects(): return jsonify(org_projects())


@bp.get("/api/v3/projects/<project_id>")
@require_auth()
def project(project_id):
    item = state.PROJECTS.get(project_id)
    return jsonify(item) if item else detail("Project not found", 404)


@bp.put("/api/v1/projects/<project_id>")
@require_auth()
def update_project(project_id):
    item = state.PROJECTS.get(project_id)
    if not item: return detail("Project not found", 404)
    # [R] Endpoint exists; exact editable field set is not consumed by stock.
    allowed = {"text", "specific_number"}
    item.update({k: v for k, v in (request.get_json(silent=True) or {}).items() if k in allowed})
    return jsonify(item)


@bp.get("/api/v1/projects/<project_id>/counts")
@require_auth()
def project_counts(project_id):
    if project_id not in state.PROJECTS: return detail("Project not found", 404)
    touched = {str(i.get("voter_id")) for i in state.interactions if str(i.get("project_id")) == project_id}
    total = len(state.VOTERS)
    # [H] Full server response is unrecoverable; expose redundant names used by plausible UIs.
    return jsonify({"total": total, "total_voters": total, "contacted": len(touched), "remaining": max(0, total - len(touched))})


@bp.get("/api/v1/tags")
@require_auth()
def tags(): return jsonify(TAGS)


def relational_survey(project_id=None):
    return {
        "id": "survey_relational_001", "project_id": project_id,
        "name": "Relational Survey",
        "questions": [
            {"id": "rel_support", "tag_id": "tag_support", "question_text": "Do they support our candidate?", "response_set": ["Yes", "No", "Undecided"], "jump_logic": []},
            {"id": "rel_issue", "tag_id": "tag_issue", "question_text": "What matters most?", "response_set": ["Cost of living", "Energy", "Public safety"], "jump_logic": []},
        ],
        "tags": {tag["tag_id"]: tag for tag in TAGS},
    }


@bp.get("/api/v1/relational-survey")
@require_auth()
def relational_surveys(): return jsonify([relational_survey()])


@bp.get("/api/v1/relational-survey/<project_id>")
@require_auth()
def relational_survey_for_project(project_id): return jsonify(relational_survey(project_id))


def text_template(project_id=None):
    return {"id": "rel_text_001", "project_id": project_id, "name": "Voting reminder", "text": "Hi {{first_name}}, remember to vote in the upcoming election."}


@bp.get("/api/v1/relational-text")
@require_auth()
def relational_texts(): return jsonify([text_template()])


@bp.get("/api/v1/relational-text/<project_id>")
@require_auth()
def relational_text_for_project(project_id): return jsonify(text_template(project_id))


@bp.get("/api/v1/voter-filter-categories")
@require_auth()
def filter_categories():
    values = ["Republican", "Democrat", "Nonpartisan", "Undeclared"]
    return jsonify({"political": [{"internal_name": "registered_party_roll_up", "name": "Party", "filters": [{"label": value, "value": value} for value in values]}]})


def stats_for(user_id):
    rows = [i for i in state.interactions if str(i.get("user_id", user_id)) == str(user_id)]
    counts = {kind: sum(i.get("_mock_type") == kind for i in rows) for kind in ("canvass", "call", "relational", "tag", "notes")}
    return {"canvass_interaction_count": counts["canvass"], "call_interaction_count": counts["call"], "relational_interaction_count": counts["relational"], "interaction_count": len(rows), **counts}


@bp.get("/api/v1/user-outreach-stats")
@require_auth()
def outreach_stats():
    from flask import g
    return jsonify(stats_for(g.current_user["id"]))


@bp.get("/api/v1/mobile/leaderboard")
@require_auth()
def leaderboard():
    rows = []
    for rank, user in enumerate(state.USERS_BY_EMAIL.values(), 1):
        stats = stats_for(user["id"])
        rows.append({"rank": rank, "user_id": user["id"], "first_name": user["first_name"], "last_name": user["last_name"], "interaction_count": stats["interaction_count"], "canvass_interaction_count": stats["canvass_interaction_count"]})
    rows.sort(key=lambda x: x["interaction_count"], reverse=True)
    for rank, row in enumerate(rows, 1): row["rank"] = rank
    return jsonify(rows)
