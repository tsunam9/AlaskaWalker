"""Canvasser-facing reads used by the stock mobile workflow.

Fields are limited to those consumed by the recovered frontend. Where the
real backend calculation is unrecoverable, fixture behavior is marked [H].
"""

import datetime
import io
import uuid

from flask import Blueprint, jsonify, request, send_file

from . import state
from .auth import detail, require_auth

bp = Blueprint("reads", __name__)

# Runtime-only local object storage.  The stock client expects the generic
# upload endpoint to return both URLs immediately, then sends public_url in
# the subsequent application/document request.
_uploads = {}


def _query_list(name):
    """Accept both OpenAPI array encodings seen in recovered/manual calls."""
    values = request.args.getlist(name) + request.args.getlist(f"{name}[]")
    return [str(value) for value in values if value not in (None, "")]


def _page(items, default_size=10):
    try:
        page = max(1, int(request.args.get("page", 1)))
        size = max(1, min(100, int(request.args.get("size", default_size))))
    except (TypeError, ValueError):
        page, size = 1, default_size
    start = (page - 1) * size
    return items[start:start + size]


def _project_item(project):
    return {
        "id": project["id"],
        "name": project["name"],
        "status": project["status"],
        "project_type": project["project_type"],
        "type": project["project_type"],
        "start_date": project.get("start_date"),
        "end_date": project.get("end_date"),
        "audio_recording_config": project.get("audio_recording_config"),
        "allowed_break_minutes_per_hour": project.get("allowed_break_minutes_per_hour"),
    }


def _project_details(project):
    result = _project_item(project)
    result.update({
        "hourly_rate": project.get("hourly_rate"),
        "zip_list": list(project.get("zip_list", [])),
        "description": f"Field campaign for {project['name']}.",
        "short_description": "Alaska field campaign",
        "client": "Alaska Campaign",
        "chat_id": None,
        "voter_database": {"name": None, "status": None},
        "ballot_template": None,
        "statistics": None,
        # Presence of this key is the stock UI's canvasser response
        # discriminator; null means no pending contract alert.
        "contract": None,
    })
    return result


def _earning_item(earning):
    project = state.PROJECTS.get(earning.get("project_id"))
    return {
        "id": earning["id"],
        "created_at": earning["created_at"],
        "project": ({"id": project["id"], "name": project["name"]}
                    if project else None),
        "status": earning.get("status", "pending"),
        "final_total": earning.get("amount", 0),
        "rate_type": earning.get("rate_type", "regular_rate"),
    }


def _shift_item(shift):
    project = state.PROJECTS.get(shift.get("project_id"), {})
    return {
        "id": shift["work_shift_id"],
        "start_time": shift.get("start_time"),
        "end_time": shift.get("end_time"),
        "status": shift.get("status"),
        "net_hours": round(state.net_seconds(shift) / 3600.0, 4),
        "project": {
            "id": project.get("id", shift.get("project_id")),
            "name": project.get("name", "Unknown project"),
        },
    }


@bp.get("/api/account/")
@require_auth
def account_details():
    user = request.mock_user
    user_id = str(user["id"])
    return jsonify({
        "profile": state.public_user(user),
        "general_info": {"city": "Anchorage", "state": "AK"},
        "created_at": "2026-09-01T00:00:00Z",
        "subcontractor_company_id": None,
        "voice_sample_recorded": user_id in state.voice_samples,
        "referral_program": {"referral_code": "ALASKA1001"},
    })


@bp.get("/api/selector/project")
@require_auth
def selector_projects():
    requested_users = _query_list("assigned_user_ids")
    allowed_user = str(request.mock_user["id"])
    if requested_users and allowed_user not in requested_users:
        return jsonify({"items": []})
    projects = state.projects_for_user(request.mock_user["id"])
    statuses = set(_query_list("statuses"))
    project_type = request.args.get("type")
    if statuses:
        projects = [p for p in projects if p.get("status") in statuses]
    if project_type:
        projects = [p for p in projects if p.get("project_type") == project_type]
    return jsonify({"items": [_project_item(p) for p in projects]})


@bp.get("/api/projects/")
@require_auth
def projects_list():
    projects = state.projects_for_user(request.mock_user["id"])
    statuses = set(_query_list("statuses"))
    if statuses:
        projects = [p for p in projects if p.get("status") in statuses]
    search = (request.args.get("search_query") or "").casefold()
    if search:
        projects = [p for p in projects if search in p.get("name", "").casefold()]
    reverse = request.args.get("sort_type", "desc") != "asc"
    projects.sort(key=lambda p: p.get("start_date") or "", reverse=reverse)
    total = len(projects)
    return jsonify({"items": [_project_item(p) for p in _page(projects)],
                    "total_count": total})


@bp.get("/api/projects/<project_id>")
@require_auth
def project_details(project_id):
    project = state.PROJECTS.get(project_id)
    if project is None:
        return detail(404, "Project not found")
    assigned = {str(uid) for uid in project.get("assigned_user_ids", [])}
    if str(request.mock_user["id"]) not in assigned:
        return detail(404, "Project not found")
    return jsonify(_project_details(project))


@bp.get("/api/projects/<project_id>/short_info")
@require_auth
def project_short_info(project_id):
    project = state.PROJECTS.get(project_id)
    if project is None:
        return detail(404, "Project not found")
    return jsonify({
        "id": project["id"],
        "name": project["name"],
        "type": project["project_type"],
        "status": project["status"],
        "short_description": "Alaska field campaign",
    })


@bp.get("/api/projects/<project_id>/voter_database")
@require_auth
def project_voter_database(project_id):
    project = state.PROJECTS.get(project_id)
    if project is None:
        return detail(404, "Project not found")
    assigned = {str(uid) for uid in project.get("assigned_user_ids", [])}
    if str(request.mock_user["id"]) not in assigned:
        return detail(404, "Project not found")
    # [H] No voter file is installed in the local fixture.  These are the
    # fields consumed by the recovered stock voter-database screens; a null
    # status intentionally renders their normal "No voter database" state.
    return jsonify({
        "status": None,
        "database_name": None,
        "created_at": None,
        "file_name": None,
        "file_url": None,
        "error_message": None,
        "stats": None,
        "table_data": None,
        "table_columns": None,
        "import_progress": None,
        "indexing_progress": None,
        "geocoding_progress": None,
    })


@bp.get("/api/earnings/account/")
@require_auth
def payment_account():
    # [H] Activated local fixture, with no third-party onboarding destination.
    return jsonify({"status": "activated", "onboarding_link": None})


@bp.get("/api/earnings/balance/")
@require_auth
def earning_balance():
    user_id = str(request.mock_user["id"])
    own = [e for e in state.earnings if e.get("user_id") == user_id]
    pending = round(sum(float(e.get("amount", 0)) for e in own
                        if e.get("status") == "pending"), 2)
    ready = round(sum(float(e.get("amount", 0)) for e in own
                      if e.get("status") == "ready_for_payment"), 2)
    next_payment = (datetime.datetime.now(datetime.timezone.utc)
                    + datetime.timedelta(days=7))
    return jsonify({
        "ready_for_payment": ready,
        "pending": pending,
        "next_payment_date": next_payment.isoformat().replace("+00:00", "Z"),
        "same_day_payout_enabled": False,
    })


@bp.get("/api/earnings/")
@require_auth
def earnings_list():
    user_id = str(request.mock_user["id"])
    earnings = [e for e in state.earnings if e.get("user_id") == user_id]
    earnings.sort(key=lambda e: e.get("created_at") or "", reverse=True)
    return jsonify({"items": [_earning_item(e) for e in _page(earnings)],
                    "total_count": len(earnings)})


@bp.get("/api/earnings/totals-by-rate-type/")
@require_auth
def earning_totals_by_rate_type():
    user_id = str(request.mock_user["id"])
    own = [e for e in state.earnings if e.get("user_id") == user_id]

    def total(kind):
        selected = [e for e in own if e.get("rate_type") == kind]
        return {"total": round(sum(float(e.get("amount", 0)) for e in selected), 2),
                "count": len(selected)}

    return jsonify({"regular_rate": total("regular_rate"),
                    "bonus": total("bonus"),
                    "increased_rate": total("increased_rate")})


@bp.get("/api/work_shift/")
@require_auth
def work_shift_list():
    user_id = str(request.mock_user["id"])
    shifts = [s for s in state.shifts.values() if s.get("user_id") == user_id]
    reverse = request.args.get("sort_type", "desc") != "asc"
    shifts.sort(key=lambda s: s.get("start_time") or "", reverse=reverse)
    return jsonify({"items": [_shift_item(s) for s in _page(shifts, default_size=5)],
                    "total_count": len(shifts)})


@bp.get("/api/work_shift/<work_shift_id>")
@require_auth
def work_shift_details(work_shift_id):
    shift = state.get_shift(work_shift_id)
    if shift is None or shift.get("user_id") != str(request.mock_user["id"]):
        return detail(404, "Work shift not found")
    project = state.PROJECTS.get(shift.get("project_id"), {})
    net_hours = state.net_seconds(shift) / 3600.0
    rate = float(project.get("hourly_rate", 0))
    result = _shift_item(shift)
    result.update({
        "project_id": shift.get("project_id"),
        # This field is the recovered stock UI discriminator for a regular
        # canvasser self-view (as opposed to subcontractor/admin shapes).
        "normal_pay_rate": rate,
        "increased_pay_rate": None,
        "increased_pay_rate_threshold_in_hours": None,
        "current_earned": round(net_hours * rate, 2),
        "last_interaction_timestamp": None,
    })
    return jsonify(result)


@bp.get("/api/work_shift/<work_shift_id>/earning_progress")
@require_auth
def work_shift_earning_progress(work_shift_id):
    shift = state.get_shift(work_shift_id)
    if (shift is None or shift.get("user_id") != str(request.mock_user["id"])
            or shift.get("status") == "finalized"):
        return detail(404, "Work shift not found")
    project = state.PROJECTS.get(shift.get("project_id"), {})
    net_hours = state.net_seconds(shift) / 3600.0
    rate = float(project.get("hourly_rate", 0))
    paid_break_left = max(
        0.0,
        (state.paid_break_budget_seconds(shift)
         - state.break_seconds(shift, state.iso_now())) / 3600.0,
    )
    return jsonify({
        "net_hours": round(net_hours, 4),
        "current_earned": round(net_hours * rate, 2),
        "current_pay_rate": rate,
        "increased_pay_rate": None,
        "increased_pay_rate_threshold_in_hours": None,
        "paid_break_hours_left": round(paid_break_left, 4),
        "last_interaction_timestamp": None,
    })


@bp.get("/api/notifications/unread-count")
@require_auth
def notifications_unread_count():
    return jsonify({"count": sum(1 for n in state.notifications
                                  if n.get("read_at") is None)})


@bp.get("/api/notifications/list")
@require_auth
def notifications_list():
    items = list(state.notifications)
    if request.args.get("only_unread", "false").lower() == "true":
        items = [n for n in items if n.get("read_at") is None]
    reverse = request.args.get("sort_type", "desc") != "asc"
    items.sort(key=lambda n: n.get("sent_at") or "", reverse=reverse)
    return jsonify({"notifications": _page(items), "total_count": len(items)})


@bp.post("/api/notifications/mark_as_read/<int:notification_id>")
@require_auth
def notification_mark_read(notification_id):
    item = next((n for n in state.notifications if n.get("id") == notification_id), None)
    if item is None:
        return detail(404, "Notification not found")
    item["read_at"] = state.iso_now()
    return jsonify({})


@bp.post("/api/notifications/mark_all_as_read")
@require_auth
def notifications_mark_all_read():
    timestamp = state.iso_now()
    for item in state.notifications:
        if item.get("read_at") is None:
            item["read_at"] = timestamp
    return jsonify({})


@bp.get("/api/docs/")
@require_auth
def docs_list():
    # The navigation queries this on every mount to decide whether to show
    # contextual help. No local help fixtures are installed yet.
    return jsonify({"pages": []})


@bp.post("/api/upload/")
@require_auth
def upload_file():
    uploaded = request.files.get("file")
    if uploaded is None:
        return detail(400, "File is required")
    upload_id = uuid.uuid4().hex
    _uploads[upload_id] = {
        "data": uploaded.read(),
        "content_type": uploaded.mimetype or "application/octet-stream",
        "name": uploaded.filename or "upload",
    }
    public_url = f"{request.host_url.rstrip('/')}/__mock/uploads/{upload_id}"
    return jsonify({"private_url": public_url, "public_url": public_url})


@bp.get("/__mock/uploads/<upload_id>")
def uploaded_file(upload_id):
    uploaded = _uploads.get(upload_id)
    if uploaded is None:
        return detail(404, "File not found")
    return send_file(
        io.BytesIO(uploaded["data"]),
        mimetype=uploaded["content_type"],
        download_name=uploaded["name"],
    )


@bp.post("/api/canvasser_application/documents")
@require_auth
def canvasser_documents():
    body = request.get_json(silent=True) or {}
    urls = body.get("id_photo_urls")
    if not isinstance(urls, list) or not urls or not all(isinstance(url, str) for url in urls):
        return detail(400, "At least one ID photo is required")
    request.mock_user["id_photo_urls"] = list(urls)
    return jsonify({"id_photo_urls": list(urls)})


@bp.post("/rest/v1/rpc/get_unread_chat_count")
@require_auth
def supabase_unread_chat_count():
    # Supabase is repointed to this same isolated origin. PostgREST returns the
    # scalar function result as JSON; zero keeps the stock unread badge quiet.
    return jsonify(0)


@bp.post("/rest/v1/rpc/get_user_chats_cursor")
@require_auth
def supabase_chat_cursor_list():
    # Empty local chat inbox used by startup/offline prefetch.
    return jsonify([])


# --- earnings: details, transactions, withdraw --------------------------------

def _find_own_earning(user, earning_id):
    for e in state.earnings:
        if str(e.get("id")) == str(earning_id) \
                and e.get("user_id") == str(user["id"]):
            return e
    return None


@bp.get("/api/earnings/<earning_id>")
@require_auth
def earning_details(earning_id):
    e = _find_own_earning(request.mock_user, earning_id)
    if e is None:
        return detail(404, "Earning not found")
    result = _earning_item(e)
    # [H] detail-only fields; schema UNCONFIRMED (types.gen.ts missing).
    result.update({
        "work_shift_id": e.get("work_shift_id"),
        "hours": e.get("hours"),
        "rate": e.get("rate"),
    })
    return jsonify(result)


@bp.get("/api/earnings/<earning_id>/short_info")
@require_auth
def earning_short_info(earning_id):
    e = _find_own_earning(request.mock_user, earning_id)
    if e is None:
        return detail(404, "Earning not found")
    return jsonify({"id": e["id"], "final_total": e.get("amount", 0),
                    "status": e.get("status", "pending")})


@bp.get("/api/earnings/transactions/")
@require_auth
def transactions_list():
    user_id = str(request.mock_user["id"])
    txs = [t for t in state.transactions if t.get("user_id") == user_id]
    txs.sort(key=lambda t: t.get("created_at") or "", reverse=True)
    return jsonify({"items": _page(txs), "total_count": len(txs)})


@bp.get("/api/earnings/transactions/<transaction_id>")
@require_auth
def transaction_details(transaction_id):
    t = next((x for x in state.transactions
              if str(x.get("id")) == str(transaction_id)
              and x.get("user_id") == str(request.mock_user["id"])), None)
    if t is None:
        return detail(404, "Transaction not found")
    return jsonify(t)


@bp.get("/api/earnings/transactions/<transaction_id>/earnings")
@require_auth
def transaction_earnings(transaction_id):
    t = next((x for x in state.transactions
              if str(x.get("id")) == str(transaction_id)
              and x.get("user_id") == str(request.mock_user["id"])), None)
    if t is None:
        return detail(404, "Transaction not found")
    items = [_earning_item(_find_own_earning(request.mock_user, eid))
             for eid in t.get("earning_ids", [])]
    return jsonify({"items": [i for i in items if i],
                    "total_count": len(items)})


@bp.post("/api/earnings/withdraw")
@require_auth
def earnings_withdraw():
    # No body (mutations/earnings/withdraw.ts:5-9); on success the client
    # zeroes ready_for_payment locally.
    user_id = str(request.mock_user["id"])
    moved = [e for e in state.earnings
             if e.get("user_id") == user_id
             and e.get("status") == "ready_for_payment"]
    if not moved:
        # [H] real backend rejects with no payable balance; detail text
        # unrecoverable.
        return detail(400, "No funds available for withdrawal")
    for e in moved:
        e["status"] = "paid"
    state.transactions.append({
        "id": state.next_id("transaction"),
        "user_id": user_id,
        "amount": round(sum(float(e.get("amount", 0)) for e in moved), 2),
        "earning_ids": [e["id"] for e in moved],
        "status": "processing",
        "created_at": state.iso_now(),
    })
    return jsonify({})


@bp.patch("/api/earnings/account/<user_id>")
@require_auth
def edit_payment_account(user_id):
    if str(request.mock_user["id"]) != str(user_id):
        return detail(404, "Payment account not found")
    return jsonify({"status": "activated", "onboarding_link": None})


# --- contracts (read-only v2) ----------------------------------------------------

# [H] canvassers normally hold a signed assignment contract + W-9; the fixture
# starts empty (a brand-new account is a legitimate state). Shapes are
# UNCONFIRMED beyond list consumption.
_contracts = []


@bp.get("/api/contracts/v2/")
@require_auth
def contracts_list_v2():
    own = [c for c in _contracts
           if c.get("user_id") == str(request.mock_user["id"])]
    return jsonify({"items": _page(own), "total_count": len(own)})


@bp.get("/api/contracts/v2/<contract_id>")
@require_auth
def contract_details_v2(contract_id):
    c = next((x for x in _contracts if str(x.get("id")) == str(contract_id)
              and x.get("user_id") == str(request.mock_user["id"])), None)
    if c is None:
        return detail(404, "Contract not found")
    return jsonify(c)


@bp.get("/api/contracts/<contract_id>/short_info")
@require_auth
def contract_short_info(contract_id):
    c = next((x for x in _contracts if str(x.get("id")) == str(contract_id)
              and x.get("user_id") == str(request.mock_user["id"])), None)
    if c is None:
        return detail(404, "Contract not found")
    return jsonify({"id": c["id"], "name": c.get("name"),
                    "status": c.get("status")})


# --- work_shift extras ------------------------------------------------------------

@bp.get("/api/work_shift/<work_shift_id>/conversations")
@require_auth
def work_shift_conversations(work_shift_id):
    shift = state.get_shift(work_shift_id)
    if shift is None or shift.get("user_id") != str(request.mock_user["id"]):
        return detail(404, "Work shift not found")
    # The mock never produces conversations; on a no_recording project zero
    # conversations is the normal server-visible state.
    return jsonify({"items": [], "total_count": 0})


@bp.get("/api/work_shift/<work_shift_id>/short_info")
@require_auth
def work_shift_short_info(work_shift_id):
    shift = state.get_shift(work_shift_id)
    if shift is None or shift.get("user_id") != str(request.mock_user["id"]):
        return detail(404, "Work shift not found")
    return jsonify({
        "id": shift["work_shift_id"],
        "start_time": shift.get("start_time"),
        "end_time": shift.get("end_time"),
        "status": shift.get("status"),
    })


# --- applications -------------------------------------------------------------------

_applications = {}  # user_id -> list of {"project_id", "status", "applied_at"}


@bp.get("/api/applications/")
@require_auth
def applications_upcoming():
    projects = state.projects_for_user(request.mock_user["id"])
    applied = {a["project_id"]
               for a in _applications.get(str(request.mock_user["id"]), [])}
    items = [_project_item(p) for p in projects if p["id"] not in applied]
    items.sort(key=lambda p: p.get("start_date") or "",
               reverse=request.args.get("sort_type", "desc") != "asc")
    return jsonify({"items": _page(items), "total_count": len(items)})


@bp.get("/api/applications/applied")
@require_auth
def applications_applied():
    mine = _applications.get(str(request.mock_user["id"]), [])
    items = []
    for a in mine:
        p = state.PROJECTS.get(a["project_id"])
        if p is None:
            continue
        item = _project_item(p)
        item["application_status"] = a["status"]
        item["applied_at"] = a["applied_at"]
        items.append(item)
    return jsonify({"items": _page(items), "total_count": len(items)})


@bp.get("/api/applications/<project_id>")
@require_auth
def application_details(project_id):
    project = state.PROJECTS.get(project_id)
    if project is None:
        return detail(404, "Project not found")
    result = _project_details(project)
    mine = _applications.get(str(request.mock_user["id"]), [])
    a = next((x for x in mine if x["project_id"] == project_id), None)
    result["application_status"] = a["status"] if a else None
    return jsonify(result)


@bp.put("/api/applications/create")
@require_auth
def application_create():
    body = request.get_json(silent=True) or {}
    project_id = body.get("project_id")
    project = state.PROJECTS.get(project_id)
    if project is None:
        return detail(404, "Project not found")
    mine = _applications.setdefault(str(request.mock_user["id"]), [])
    if any(a["project_id"] == project_id for a in mine):
        return detail(400, "Already applied")
    mine.append({"project_id": project_id, "status": "applied",
                 "applied_at": state.iso_now()})
    return jsonify({})


@bp.post("/api/canvasser_application/general_info")
@require_auth
def canvasser_general_info():
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not body:
        return detail(400, "general info body is required")
    request.mock_user["canvasser_general_info"] = body
    return jsonify({})


# --- account & profile management --------------------------------------------------

@bp.patch("/api/account/settings/edit")
@require_auth
def account_settings_edit():
    body = request.get_json(silent=True) or {}
    user = request.mock_user
    if "time_zone" in body:
        user["time_zone"] = body["time_zone"]
    return jsonify({"time_zone": user.get("time_zone", "America/Anchorage")})


@bp.put("/api/account/password/edit")
@require_auth
def account_password_edit():
    body = request.get_json(silent=True) or {}
    old = body.get("old_password") or body.get("current_password")
    new = body.get("new_password")
    user = request.mock_user
    if not new:
        return detail(400, "new_password is required")
    # [H] field names UNCONFIRMED; old-password check mirrors any sane backend.
    if old is not None and user["password"] != old:
        return detail(400, "Current password is incorrect")
    user["password"] = new
    return jsonify({})


@bp.post("/api/account/password/reset")
def account_password_reset():
    # Unauthenticated forgot-password. [H] always-200 (no account enumeration).
    return jsonify({})


@bp.post("/api/account/password/set")
def account_password_set():
    # Invite/reset-token flow; the mock has no token issuance for it. [H]
    return detail(400, "Invalid or expired token")


@bp.patch("/api/account/<user_id>/delete")
@require_auth
def account_delete(user_id):
    if str(request.mock_user["id"]) != str(user_id):
        return detail(404, "User not found")
    request.mock_user["deleted"] = True
    return jsonify({})


@bp.post("/api/profile/")
@require_auth
def profile_set():
    body = request.get_json(silent=True) or {}
    user = request.mock_user
    for k in ("first_name", "last_name"):
        if k in body and isinstance(body[k], str) and body[k]:
            user[k] = body[k]
    user["profile"] = {**user.get("profile", {}), **body}
    return jsonify({})


@bp.post("/api/profile/generate-bio")
@require_auth
def profile_generate_bio():
    return jsonify({"bio": ""})  # [H] AI feature; mock returns empty


@bp.get("/api/profile/<user_id>")
@require_auth
def profile_details(user_id):
    user = state.USERS_BY_ID.get(str(user_id))
    if user is None:
        return detail(404, "User not found")
    result = state.public_user(user)
    result.update(user.get("profile", {}))
    return jsonify(result)


@bp.put("/api/profile/<user_id>")
@require_auth
def profile_edit(user_id):
    if str(request.mock_user["id"]) != str(user_id):
        return detail(404, "User not found")
    return profile_set()


_share_codes = {}  # code -> user_id


@bp.get("/api/profile/<user_id>/shared_link")
@require_auth
def profile_shared_link_get(user_id):
    for code, uid in _share_codes.items():
        if uid == str(user_id):
            return jsonify({"shareable_code": code, "enabled": True})
    return jsonify({"shareable_code": None, "enabled": False})


@bp.post("/api/profile/shared/<user_id>/generate")
@require_auth
def profile_shared_link_generate(user_id):
    if str(request.mock_user["id"]) != str(user_id):
        return detail(404, "User not found")
    code = uuid.uuid4().hex[:12]
    _share_codes[code] = str(user_id)
    return jsonify({"shareable_code": code, "enabled": True})


@bp.put("/api/profile/shared/<user_id>/enable")
@require_auth
def profile_shared_link_enable(user_id):
    return jsonify({"enabled": True})


@bp.put("/api/profile/shared/<user_id>/disable")
@require_auth
def profile_shared_link_disable(user_id):
    for code, uid in list(_share_codes.items()):
        if uid == str(user_id):
            del _share_codes[code]
    return jsonify({"enabled": False})


@bp.get("/api/profile/shared/<shareable_code>")
def profile_shared_public(shareable_code):
    uid = _share_codes.get(shareable_code)
    user = state.USERS_BY_ID.get(uid) if uid else None
    if user is None:
        return detail(404, "Profile not found")
    p = state.public_user(user)
    return jsonify({"first_name": p["first_name"], "last_name": p["last_name"],
                    "profile_picture_url": None})


# --- labels, docs, emergencies, verifications, export ---------------------------------

@bp.get("/api/users/<user_id>/short_info")
@require_auth
def user_short_info(user_id):
    user = state.USERS_BY_ID.get(str(user_id))
    if user is None:
        return detail(404, "User not found")
    p = state.public_user(user)
    return jsonify({**p, "profile_picture_url": None})


@bp.get("/api/subcontractor_company/<company_id>/short_info")
@require_auth
def subcontractor_company_short_info(company_id):
    # No subcontractor companies exist in the fixture.
    return detail(404, "Subcontractor company not found")


@bp.get("/api/coaching_feedback/<feedback_id>/short_info")
@require_auth
def coaching_feedback_short_info(feedback_id):
    # No coaching feedback exists in the fixture.
    return detail(404, "Coaching feedback not found")


@bp.get("/api/docs/<path:doc_path>")
@require_auth
def docs_page(doc_path):
    return detail(404, "Doc not found")  # matches an empty docs fixture


@bp.get("/api/wake_word_events/")
@require_auth
def wake_word_events_list():
    items = [{
        "id": e["id"],
        "work_shift_id": e.get("work_shift_id"),
        "device_id": e.get("device_id"),
        "timestamp_ms": e.get("timestamp_ms"),
        "gps_point": e.get("gps_point"),
    } for e in state.wake_word_events
        if e.get("user_id") == str(request.mock_user["id"])]
    items.sort(key=lambda e: e.get("timestamp_ms") or 0, reverse=True)
    return jsonify({"items": _page(items), "total_count": len(items)})


@bp.get("/api/wake_word_events/<event_id>")
@require_auth
def wake_word_event_details(event_id):
    e = next((x for x in state.wake_word_events
              if x.get("id") == event_id
              and x.get("user_id") == str(request.mock_user["id"])), None)
    if e is None:
        return detail(404, "Wake word event not found")
    return jsonify({k: e.get(k) for k in ("id", "work_shift_id", "device_id",
                                          "timestamp_ms", "gps_point")})


@bp.put("/api/verifications/voter/")
@require_auth
def verifications_voter_create():
    body = request.get_json(silent=True) or {}
    project_id = body.get("project_id")
    infos = body.get("infos")
    if not project_id or not isinstance(infos, list):
        return detail(400, "project_id and infos are required")
    if project_id not in state.PROJECTS:
        return detail(404, "Project not found")
    created = []
    for info in infos:
        if not isinstance(info, dict):
            return detail(400, "infos entries must be objects")
        created.append({"id": state.next_id("notification"), **info})
    return jsonify({"items": created})  # [H] response schema UNCONFIRMED


@bp.get("/api/export/<export_job_id>")
@require_auth
def export_job(export_job_id):
    # [H] no export jobs exist; report a completed job shape so pollers stop.
    return jsonify({"id": export_job_id, "status": "completed",
                    "file_url": None})


# --- mock-only payroll control (NOT a vendor endpoint) ------------------------------

@bp.post("/__mock/earnings/<earning_id>/approve")
def mock_earning_approve(earning_id):
    """Harness control: move an earning pending -> ready_for_payment so the
    withdraw flow can be exercised. Lives under /__mock, which never exists
    on the real backend."""
    e = next((x for x in state.earnings
              if str(x.get("id")) == str(earning_id)), None)
    if e is None:
        return detail(404, "Earning not found")
    e["status"] = "ready_for_payment"
    return jsonify({"id": e["id"], "status": e["status"]})
