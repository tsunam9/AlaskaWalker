"""Shared in-memory state for the patriot mock.

One module-level store, loaded from users.json + projects.json at import.
Thread-safe enough for the Flask dev server (a single lock around writes).

Everything here is the mock's *server-side* truth: shifts, device links,
sensor records, device events, earnings, notifications. Server-side
computations (break budgets, earning amounts) are [H] — payroll review
criteria are known (net hours vs break budgets, gps_quality, phone_behaviour)
but the real backend's exact arithmetic is not recoverable from client code.
"""

import json
import os
import threading
import time
import uuid
from collections import deque

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNTIME_STATE_PATH = os.environ.get(
    "PM_STATE_PATH", os.path.join(HERE, "runtime-state.json"))

_lock = threading.RLock()
server_started_at = time.time()


def _load(name):
    with open(os.path.join(HERE, name)) as fh:
        return json.load(fh)


# --- fixtures ---------------------------------------------------------------

_users_list = _load("users.json")["users"]
USERS_BY_EMAIL = {u["email"]: u for u in _users_list}
USERS_BY_ID = {str(u["id"]): u for u in _users_list}

PROJECTS = {p["id"]: p for p in _load("projects.json")["projects"]}

# --- mutable server state ----------------------------------------------------

# refresh-token revocation (logout) — auth-session.md §4 docstring
revoked_jti = set()

# device_id -> {"user_id", "linked": bool, "info": dict|None, "fcm_token": str|None}
devices = {}

# work_shift_id -> shift dict (see new_shift)
shifts = {}

# append-only sinks
sensor_records = []   # validated batch envelopes (tolerates duplicate record_id)
device_events = []    # event envelopes from event/send + batch_send
audio_uploads = []    # metadata of canvasser_voice/* uploads
wake_word_events = []

# Dashboard-only diagnostics. This never participates in a stock-app response.
# Bound the history so a long-running shift cannot grow the mock without limit.
request_log = deque(maxlen=2000)

# earnings domain (reads blueprint owns the response shaping)
earnings = []         # earning dicts created on finalize
transactions = []
notifications = []    # seeded below
voice_samples = {}    # user_id -> {"uploaded_at", "audio_config", "seconds"}
verifications = {}    # conversation_id -> voice-verification dict
orphaned_finalizations = []  # recovered stale shift_end rows after a mock restart

_next_ids = {"earning": 5000, "transaction": 9000, "notification": 1}


def persist_runtime_state():
    """Persist continuity-critical state so restarting the mock does not make
    the stock client's durable outbox impossible to drain — and does not
    "un-remember" completed onboarding (voice samples), payroll, or
    notification read state."""
    with _lock:
        payload = {
            "devices": devices,
            "shifts": shifts,
            "orphaned_finalizations": orphaned_finalizations,
            "voice_samples": voice_samples,
            "verifications": verifications,
            "earnings": earnings,
            "transactions": transactions,
            "notifications": notifications,
        }
        temp_path = RUNTIME_STATE_PATH + ".tmp"
        with open(temp_path, "w") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
        os.replace(temp_path, RUNTIME_STATE_PATH)


def _load_runtime_state():
    try:
        with open(RUNTIME_STATE_PATH) as handle:
            payload = json.load(handle)
    except FileNotFoundError:
        return
    except (OSError, ValueError) as exc:
        print(f"[patriot-mock] ignoring invalid runtime state: {exc}", flush=True)
        return
    devices.update(payload.get("devices") or {})
    shifts.update(payload.get("shifts") or {})
    orphaned_finalizations.extend(payload.get("orphaned_finalizations") or [])
    voice_samples.update(payload.get("voice_samples") or {})
    verifications.update(payload.get("verifications") or {})
    earnings.extend(payload.get("earnings") or [])
    transactions.extend(payload.get("transactions") or [])
    saved_notifications = payload.get("notifications") or []
    if saved_notifications:
        notifications.clear()
        notifications.extend(saved_notifications)


def next_id(kind):
    with _lock:
        _next_ids[kind] = _next_ids.get(kind, 1) + 1
        return _next_ids[kind]


# --- durable capture ------------------------------------------------------------
#
# Append-only JSONL record of everything the (repointed stock) app sends, for
# later comparison against simulated walk-harness data. One file per stream in
# captures/: sensors.jsonl, device_events.jsonl, shift_events.jsonl,
# audio.jsonl. Every line is {"captured_at": <server ISO>, ...payload}.
# Unlike the in-memory sinks, these survive restarts and are never truncated.

CAPTURE_DIR = os.environ.get("PM_CAPTURE_DIR", os.path.join(HERE, "captures"))
CAPTURE_ENABLED = os.environ.get("PM_CAPTURE", "1") == "1"


def capture(kind, obj):
    if not CAPTURE_ENABLED:
        return
    os.makedirs(CAPTURE_DIR, exist_ok=True)
    line = {"captured_at": iso_now()}
    line.update(obj)
    with _lock:
        with open(os.path.join(CAPTURE_DIR, kind + ".jsonl"), "a") as fh:
            fh.write(json.dumps(line) + "\n")


def now_ms():
    return int(time.time() * 1000)


def iso_now():
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z"


# --- users / projects ---------------------------------------------------------

def public_user(u):
    # Exactly the claim set the client reads (useUserRole.ts:9-27).
    return {
        "id": u["id"],
        "email": u["email"],
        "first_name": u["first_name"],
        "last_name": u["last_name"],
        "role": u["role"],
    }


def projects_for_user(user_id):
    """Projects assigned to the user (fixture field assigned_user_ids) with
    status active — the shift-start selector filters statuses=['active']
    (pages/shift/index.vue:130-133)."""
    uid = str(user_id)
    return [p for p in PROJECTS.values()
            if uid in [str(x) for x in p.get("assigned_user_ids", [])]]


# --- devices -------------------------------------------------------------------

def link_device(user_id, device_id, info=None):
    with _lock:
        d = devices.setdefault(device_id, {"fcm_token": None})
        d["user_id"] = str(user_id)
        d["linked"] = True
        if info is not None:
            d["info"] = info


def unlink_device(device_id):
    with _lock:
        d = devices.get(device_id)
        if d is not None:
            d["linked"] = False
            d["fcm_token"] = None


def device_is_linked(device_id, user_id):
    d = devices.get(device_id)
    return bool(d and d.get("linked") and str(d.get("user_id")) == str(user_id))


def linked_device_for_user(user_id):
    """The user's currently linked device — status_v2 reports device_id even
    with no active shift so the client's shiftExists check
    (useMobileShift.ts:102-106) resolves false rather than undefined."""
    with _lock:
        for did, d in devices.items():
            if d.get("linked") and str(d.get("user_id")) == str(user_id):
                return did
    return None


# --- shifts --------------------------------------------------------------------

def new_shift(user_id, device_id, project_id, start_time, state_payload, time_zone):
    with _lock:
        sid = uuid.uuid4().hex
        server_start = iso_now()
        shifts[sid] = {
            "work_shift_id": sid,
            "user_id": str(user_id),
            "device_id": device_id,
            "project_id": project_id,
            "start_time": server_start,      # server-canonical (client re-inits
                                             # its timer from the response)
            "client_start_time": start_time,
            "time_zone": time_zone,
            "end_time": None,
            "status": "active",              # active | paused | finalized
            "breaks": [],                    # {"pause": iso, "resume": iso|None}
            "generate_state_payload": state_payload,
            "finalize_state_payload": None,
            "data_complete": None,
        }
        return shifts[sid]


def active_shift_for_user(user_id):
    with _lock:
        for s in shifts.values():
            if s["user_id"] == str(user_id) and s["status"] in ("active", "paused"):
                return s
    return None


def get_shift(sid):
    return shifts.get(sid)


def break_seconds(s, upto_iso=None):
    """Total recorded break time. [H] server-side bookkeeping — the SDK docs
    mention span bookkeeping keyed on button_pressed_time."""
    total = 0.0
    for b in s["breaks"]:
        if not b.get("pause"):
            continue
        end = b.get("resume") or upto_iso
        if not end:
            continue
        total += max(0.0, _iso_to_epoch(end) - _iso_to_epoch(b["pause"]))
    return total


def paid_break_budget_seconds(s):
    """[H] allowed_break_minutes_per_hour × gross hours."""
    p = PROJECTS.get(s["project_id"], {})
    per_hour = float(p.get("allowed_break_minutes_per_hour", 0))
    gross_h = gross_seconds(s) / 3600.0
    return per_hour * 60.0 * gross_h


def gross_seconds(s):
    end = s["end_time"] or iso_now()
    return max(0.0, _iso_to_epoch(end) - _iso_to_epoch(s["start_time"]))


def net_seconds(s):
    unpaid = max(0.0, break_seconds(s, s["end_time"]) - paid_break_budget_seconds(s))
    return max(0.0, gross_seconds(s) - unpaid)


def finalize_shift(s, end_time, state_payload, data_complete):
    with _lock:
        s["status"] = "finalized"
        s["end_time"] = end_time or iso_now()
        s["finalize_state_payload"] = state_payload
        s["data_complete"] = data_complete
        for b in s["breaks"]:
            if b.get("resume") is None:
                b["resume"] = s["end_time"]
    _create_earning_for_shift(s)


def _create_earning_for_shift(s):
    """[H] earning generation. Known: payroll review validates net hours vs
    break budgets, gps/motion integrity, interaction counts (ANALYSIS.md).
    Exact earning schema is UNCONFIRMED (types.gen.ts missing)."""
    p = PROJECTS.get(s["project_id"], {})
    rate = float(p.get("hourly_rate", 0))
    hours = net_seconds(s) / 3600.0
    earnings.append({
        "id": next_id("earning"),
        "user_id": s["user_id"],
        "work_shift_id": s["work_shift_id"],
        "project_id": s["project_id"],
        "rate_type": "regular_rate",
        "rate": rate,
        "hours": round(hours, 4),
        "amount": round(hours * rate, 2),
        "status": "pending",
        "created_at": iso_now(),
    })


def _iso_to_epoch(iso):
    if iso is None:
        return time.time()
    iso = str(iso).replace("Z", "+00:00")
    import datetime
    try:
        return datetime.datetime.fromisoformat(iso).timestamp()
    except ValueError:
        # tolerate epoch-ms numbers sent as strings/numbers
        try:
            return float(iso) / 1000.0
        except (TypeError, ValueError):
            return time.time()


# Restore shift/device continuity before serving requests. Sensor and request
# history intentionally begins fresh with each process; the dashboard labels
# server uptime so that boundary is visible.
_load_runtime_state()


# --- seed notifications ---------------------------------------------------------

# Fresh-install fixture only; a restored notification list wins.
if not notifications:
    notifications.append({
        "id": next_id("notification"),
        "type_": "work_shift_start_reminder",
        "message": "Don't forget to start your shift.",
        "read_at": None,
        "sent_at": iso_now(),
        "relative_url": "/shift",
    })
