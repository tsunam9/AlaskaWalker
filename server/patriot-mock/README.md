# Patriot Grassroots / ValidNation mock backend

A Flask re-implementation of `https://api.validnation.ai` for the Alaska
campaign. Two consumers:

1. **The repointed stock app** — the endgame fidelity test: rebuild
   `com.patriotgrassroots.validnation` with its API origin pointed at this
   mock (same technique as `patriot_grassroots/instrumentation/`, which
   already repoints origins to a device-local port). If the stock app runs
   its normal workflow against the mock without errors, the mock is
   behaviorally indistinguishable from the real backend for that surface.
2. **`alaska_walker/`** — the reimplementation develops against the mock
   before any real-backend canary (plan step 9).

Fidelity rule: the audit files in `patriot_grassroots/audit/` are ground
truth (line-cited against the recovered stock frontend). Anything the real
server does that is not recoverable from client code is marked **[H]** in
the code and chosen to keep the stock client's state machine coherent —
a wrong guess here produces poisoned test data, so every [H] is a
candidate for correction from a real traffic capture
(`patriot_grassroots/instrumentation/`).

## Run

```bash
python3 patriot_mock.py          # 0.0.0.0:19001
```

Env: `PM_HOST`, `PM_PORT`, `PM_ACCESS_TTL_S` (900), `PM_REFRESH_TTL_S` (15 d),
`PM_WS_TOKEN_TTL_S`. The default listener is reachable on all computer
interfaces at TCP port 19001. **Router port-forward convention: TCP 19001 →
this patriot mock, TCP 19002 → the (not yet implemented) numinar mock.** Apps
on cellular reach the mock at the router's public IP (currently
`50.39.218.242`, the default `api_base` in `alaska_walker`). Flask does not
use UDP.

Fixtures: `users.json` (one canvasser), `projects.json` (two assigned
projects: a `no_recording` canvassing project and a
`full_recording_with_restricted_area` signature project).

Dashboard: open `http://127.0.0.1:19001/__mock/` for a live browser view of
requests/responses, shifts, devices, sensor readings, events, audio metadata,
earnings, notifications, and fixtures. It refreshes every two seconds and
redacts credentials and raw voice-sample bytes. `GET /__mock/state` provides
the same complete state as JSON (and retains the original summary fields).
The `/__mock` namespace never exists on the real backend, so no stock traffic
can collide with it.

Shift and device state is persisted to the gitignored `runtime-state.json` so
restarting the mock does not strand the stock app's durable upload outbox.

## Architecture

```
patriot_mock.py     entrypoint (python3 patriot_mock.py)
mock/
  __init__.py       create_app, request logging, /__mock/state, 404 handler
  config.py         secret + TTLs (env-overridable)
  state.py          shared in-memory server state + fixtures + shift/earning math
  auth.py           /api/auth/* (token, refresh, profile, logout, ws_token)
  shifts.py         /api/mobile/work_shift/* state machine
  device.py         update_info, event/send|batch_send, unlink, FCM token,
                    /api/settings/versions
  sensors.py        /api/mobile/sensor/batch_upload, restricted_areas
  audio.py          voice_sample, canvasser_voice/*, verifications/voice/*
  reads.py          canvasser read surface: account, applications, earnings,
                    contracts, notifications, selector/project, projects,
                    work_shift reads, docs, wake_word_events, labels, upload,
                    export, verifications/voter
scripts/            per-domain curl tests + simulate_workflow.py
```

## Wire invariants (all domains)

- Success is strictly HTTP 200 (the stock client treats any other 2xx as
  an error).
- Errors are FastAPI-style `{"detail": "..."}` — the client displays
  `data.detail || data.message`.
- `Authorization: Bearer <jwt>` everywhere except `/api/auth/token`,
  `/api/auth/refresh`, `/api/settings/versions`, and the public
  shared-profile page. The access JWT carries `exp` and a `user` claim
  (`{id,email,first_name,last_name,role}`) — the client decodes it as a
  profile fallback.
- Refresh tokens are not rotated (the client ignores a rotated one) and are
  revoked on logout.
- Device events are rejected 403 until the device is linked via
  `update_info` (the stock client's `ensureDeviceLinked` exists because the
  real backend does this).
- `finalize_v2` takes a JSON **array** and accepts the cross-device
  interrupt shape (`data_complete: null`, no `state_payload`).
- Duplicate sensor `record_id`s are accepted (the client re-sends rows
  verbatim after a failed upload).

## Coverage

The mock implements the canvasser-facing surface enumerated in
`patriot_grassroots/audit/endpoint-inventory.md` §2/§6 — everything the
stock app calls in a normal canvasser workflow (login, onboarding banners,
project select, shift start/tracking/breaks/finish, sensor upload, device
telemetry, earnings, notifications, contracts, applications, voice
verification REST, misc labels/prefetch). Admin/manager-gated endpoints and
DEAD declarations (Appendix A of the inventory) intentionally 404.

Not implemented (deliberate): the voice-verification **websocket**
(`/api/ws/voice_verification/{id}` — Flask dev server can't WS), Supabase
(chats live on a different host, `*.supabase.co`), FCM/Sentry/Google
third-party traffic.

## Tests

Run against a **fresh** state file (the suites assume an empty fixture —
e.g. an earlier run's submitted application makes `applications/create`
correctly return 400 on rerun):

```bash
PM_PORT=8899 PM_STATE_PATH=$(mktemp -u) python3 patriot_mock.py &
scripts/test_audio.sh              # audio/voice domain (26 checks)
scripts/test_reads.sh              # canvasser read surface (77 checks)
scripts/simulate_workflow.py http://127.0.0.1:8899   # full stock-workflow sim
```
