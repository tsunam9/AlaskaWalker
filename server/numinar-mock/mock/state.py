"""Thread-safe shared state, fixture loading, persistence, and captures."""

import copy
import json
import os
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone

from fixtures.generate_voters import generate

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(HERE, "fixtures")
RUNTIME_STATE_PATH = os.environ.get("PM_STATE_PATH", os.path.join(HERE, "runtime-state.json"))
CAPTURE_DIR = os.environ.get("PM_CAPTURE_DIR", os.path.join(HERE, "captures"))
CAPTURE_ENABLED = os.environ.get("PM_CAPTURE", "1") == "1"

_lock = threading.RLock()
server_started_at = time.time()
request_log = deque(maxlen=2000)


def _load(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as handle:
        return json.load(handle)


USERS_BY_EMAIL = {u["email"].lower(): u for u in _load("users.json")["users"]}
USERS_BY_ID = {str(u["id"]): u for u in USERS_BY_EMAIL.values()}
USERS_BY_SUB = {u["sub"]: u for u in USERS_BY_EMAIL.values()}
ORGS = {str(o["id"]): o for o in _load("orgs.json")["orgs"]}
PROJECTS = {str(p["id"]): p for p in _load("projects.json")["projects"]}
VOTERS = {str(v["id"]): v for v in generate(240)}

interactions = []
interaction_ids = set()
notes = {}
voter_tags = {}
qa_pings = []
push_tokens = {}
notifications = [{
    "id": "notification_001", "title": "Welcome to the field",
    "body": "Your mock canvassing workspace is ready.", "message": "Your mock canvassing workspace is ready.",
    "created_at": "2026-09-20T12:00:00Z", "read_at": None,
}]
otps = {}
refresh_tokens = {}
auth_codes = {}
memberships = {}
contact_matches = []
voter_contacts = []
payout_requests = []
ros_calls = []


def iso_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def public_user(user):
    return {k: copy.deepcopy(v) for k, v in user.items() if k not in {"roles", "org_ids"}}


def ensure_user(email):
    """Return the fixture user for email, auto-provisioning unknowns.

    [O-equivalent] Real Auth0 passwordless/Universal-Login accepts any email
    and creates the account on first verification, so the mock does the same
    instead of 400ing unknown addresses. New users land in the fixture org so
    the bootstrap chain has something to select.
    """
    key = str(email).strip().lower()
    with _lock:
        user = USERS_BY_EMAIL.get(key)
        if user is None:
            local = key.split("@", 1)[0].replace(".", " ").replace("_", " ").title() or "Mock Walker"
            first, _, last = local.partition(" ")
            user = {
                "id": "usr_" + uuid.uuid4().hex[:12],
                "sub": "auth0|" + uuid.uuid4().hex,
                "email": key,
                "first_name": first or "Mock",
                "last_name": last or "Walker",
                "name": local,
                "email_verified": True,
                "has_registered": False,
                "roles": ["canvasser"],
                "hmac": "mock-intercom-hmac",
                "org_ids": ["org_alaska_001"],
            }
            USERS_BY_EMAIL[key] = user
            USERS_BY_ID[str(user["id"])] = user
            USERS_BY_SUB[user["sub"]] = user
        return user


def capture(kind, obj):
    if not CAPTURE_ENABLED:
        return
    os.makedirs(CAPTURE_DIR, exist_ok=True)
    row = {"captured_at": iso_now(), **copy.deepcopy(obj)}
    with _lock, open(os.path.join(CAPTURE_DIR, f"{kind}.jsonl"), "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, separators=(",", ":")) + "\n")


def persist_runtime_state():
    with _lock:
        payload = {
            "users": list(USERS_BY_EMAIL.values()), "voters": list(VOTERS.values()),
            "orgs": list(ORGS.values()), "projects": list(PROJECTS.values()),
            "interactions": interactions, "notes": notes, "voter_tags": voter_tags,
            "qa_pings": qa_pings, "push_tokens": push_tokens,
            "notifications": notifications, "otps": otps,
            "refresh_tokens": refresh_tokens, "memberships": memberships,
            "contact_matches": contact_matches, "voter_contacts": voter_contacts,
            "payout_requests": payout_requests, "ros_calls": ros_calls,
            "auth_codes": auth_codes,
        }
        temp = RUNTIME_STATE_PATH + ".tmp"
        os.makedirs(os.path.dirname(os.path.abspath(RUNTIME_STATE_PATH)), exist_ok=True)
        with open(temp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
        os.replace(temp, RUNTIME_STATE_PATH)


def _restore():
    try:
        with open(RUNTIME_STATE_PATH, encoding="utf-8") as handle:
            payload = json.load(handle)
    except FileNotFoundError:
        return
    except (OSError, ValueError) as exc:
        print(f"[numinar-mock] ignoring invalid runtime state: {exc}", flush=True)
        return
    with _lock:
        for user in payload.get("users") or []:
            email = user.get("email", "").lower()
            target = USERS_BY_EMAIL.get(email)
            if target:
                target.update(user)
            elif email:
                # Auto-provisioned users from a previous run must survive restart.
                USERS_BY_EMAIL[email] = user
                USERS_BY_ID[str(user.get("id"))] = user
                USERS_BY_SUB[user.get("sub")] = user
        restored_orgs = payload.get("orgs") or []
        if restored_orgs:
            fixture_by_id = {str(o["id"]): o for o in ORGS.values()}
            merged = []
            for o in restored_orgs:
                base = fixture_by_id.get(str(o.get("id")), {})
                merged.append({**base, **o})  # fixture supplies newly added keys
            ORGS.clear(); ORGS.update({str(o["id"]): o for o in merged})
        restored_projects = payload.get("projects") or []
        if restored_projects:
            # Runtime persistence must not freeze an obsolete wire fixture.
            # The stock client treats survey/dynamic_survey as a strict shape;
            # only the two fields accepted by PUT /v1/projects/{id} are mutable.
            restored_by_id = {str(p["id"]): p for p in restored_projects}
            for project_id, project in PROJECTS.items():
                restored = restored_by_id.get(project_id, {})
                for key in ("text", "specific_number"):
                    if key in restored:
                        project[key] = restored[key]
        restored_voters = payload.get("voters") or []
        if restored_voters:
            # Fixture identity/address data is authoritative so a newly generated
            # shift list takes effect after restart. Runtime state only owns the
            # one voter field the mock mutates; retaining whole old rows would
            # silently pin the previous synthetic map forever.
            restored_by_id = {str(v["id"]): v for v in restored_voters}
            for voter_id, voter in VOTERS.items():
                restored = restored_by_id.get(voter_id, {})
                if "has_interaction" in restored:
                    voter["has_interaction"] = restored["has_interaction"]
        interactions.extend(payload.get("interactions") or [])
        interaction_ids.update(str(x["id"]) for x in interactions if x.get("id") is not None)
        notes.update(payload.get("notes") or {})
        voter_tags.update(payload.get("voter_tags") or {})
        qa_pings.extend(payload.get("qa_pings") or [])
        push_tokens.update(payload.get("push_tokens") or {})
        if payload.get("notifications") is not None:
            notifications.clear(); notifications.extend(payload["notifications"])
        otps.update(payload.get("otps") or {})
        refresh_tokens.update(payload.get("refresh_tokens") or {})
        memberships.update(payload.get("memberships") or {})
        contact_matches.extend(payload.get("contact_matches") or [])
        voter_contacts.extend(payload.get("voter_contacts") or [])
        payout_requests.extend(payload.get("payout_requests") or [])
        ros_calls.extend(payload.get("ros_calls") or [])
        auth_codes.update(payload.get("auth_codes") or {})


def mark_voter(voter_id):
    voter = VOTERS.get(str(voter_id))
    if voter is not None:
        voter["has_interaction"] = True


def add_interaction(item, kind):
    item = copy.deepcopy(item)
    item_id = str(item.get("id")) if item.get("id") is not None else None
    with _lock:
        if item_id and item_id in interaction_ids:
            return False
        item.setdefault("id", str(uuid.uuid4()))
        item["_mock_type"] = kind
        item["_received_at"] = iso_now()
        interactions.append(item)
        interaction_ids.add(str(item["id"]))
        voter_id = str(item.get("voter_id", ""))
        mark_voter(voter_id)
        if kind == "notes":
            notes.setdefault(voter_id, []).append({"id": item["id"], "value": item.get("value", ""), "created_at": item.get("created_at")})
        elif kind == "tag":
            voter_tags.setdefault(voter_id, {})[str(item.get("tag_id"))] = {
                "tag_id": item.get("tag_id"), "tag_value": item.get("value"),
                "value": item.get("value"), "updated_at": item.get("updated_at") or item.get("created_at"),
            }
        if item.get("notes"):
            notes.setdefault(voter_id, []).append({"id": item.get("notes_interaction_id") or str(uuid.uuid4()), "value": item["notes"], "created_at": item.get("created_at")})
        for response in item.get("responses") or []:
            tag_id = response.get("tag_id")
            if tag_id:
                voter_tags.setdefault(voter_id, {})[str(tag_id)] = {
                    "tag_id": tag_id, "tag_value": response.get("response"),
                    "value": response.get("response"), "question_id": response.get("question_id"),
                }
    return True


_restore()
