# Design: Numinar domain — canvassing

The canvassing half of `alaska_walker`. Reimplements the voter-contact slice
of Numinar (`com.numinar.numinar` v10.0.0) as native Java, and plays the walk
server's `pulsar` role: session liveness, walk-list upload, and doorknock
submission off the server's latch queue.

Evidence labels: **[R]** recovered from stock app (string/code level),
**[O]** observed live, **[H]** hypothesis. Numinar's Hermes v96 bundle is not
decompilable with current tooling — endpoint *names* are [R], but request/
response *shapes* are [H] until step-1 capture (hbcdump build or runtime
capture with a test account). The mock backend (§4) defines the harness
contract meanwhile. Source material: `../numinar/ANALYSIS.md`.

The same wire-parity rules as the ValidNation domain apply
(`DESIGN-VALIDNATION.md` §1): no invented fields, no harness metadata toward
Numinar hosts, server-side receipt verification.

---

## 1. Auth — mock first, Auth0 later

| Mode | Contract | Evidence |
|---|---|---|
| Mock (default for harness) | `POST /api/v1/session` (mock-defined) → opaque token; walk.json carries `mockBackend` + credentials | mock contract |
| Real (later milestone) | Auth0 `auth.numinar.com`, scope `openid profile email offline_access`, PKCE redirect `com.numinar.numinar.auth0://...` — **client_id/audience inlined away, require runtime capture** | [R] flow, [H] params |

Token handling: refresh-capable store in encrypted prefs; 401 → one refresh
→ terminal signed-out. Liveness toward the walk server (`POST /<person>/api/
client/login` + `/heartbeat` 5 s) is driven by this domain's session state —
the same way Pulsar Clean did it.

## 2. Data bootstrap

| Contract | Purpose | Evidence |
|---|---|---|
| `GET /v1/my-orgs-mobile` | orgs the user belongs to | [R] path |
| `GET /v2/mobile-app/projects/` | projects (canvassing assignments) | [R] path |
| `GET /v1/voters/` + `/v1/nearby-voters` | voter/household records with geo | [R] paths, [H] shapes |
| `GET /v1/projects/sse/updates` | SSE change notifications (optional; polling fallback) | [R] path |

Stock is offline-first (expo-sqlite + `/v1/interactions/batch` retry queue
[R]); ours mirrors that with a SQLite store keyed by project, and one
bounded serial fetch per restart (single-flight; no duplicate concurrent
fetches).

## 3. WalklistAdapter — the synthesis layer (the new piece)

The walk server's route pipeline consumes
`{lists: [{wid, name, formId, addresses: [{aid, lat, lng, knocked}]}]}`;
Numinar has no such object. Adapter rules:

1. Scope: one walk list per selected project; `wid` = stable project-scoped
   id (string; type preserved exactly).
2. Addresses: project voters grouped by household location
   (stock does `groupHouseholdsByLocation` [R]) → one address per
   household; `aid` = stable household id; `lat/lng` = household location;
   `knocked` = true when every voter in the household has a completed
   interaction for this project.
3. Upload: one batch `POST /<person>/api/walklist` on every process restart
   (202-idempotent; server stores, never routes on upload); re-upload on
   project data refresh. Uploading never triggers compute — that stays an
   operator action.
4. Route adoption: poll `/api/status`; adopt only a server-selected
   `walklist_id` that is still assigned locally; switch active list without
   inventing a parallel route state machine.

## 4. Doorknock loop (latch → interaction)

```
walk server latches PendingSubmission (gated on ValidNation shift)
  → WalkCanvasser reads pendingSubmissions (status poll), cursor-filtered
  → match stop_id/house → household (aid) → voter set
  → POST /v1/interactions/batch  [{household/voter ids, interaction type,
    disposition, survey answers?, timestamp, gps}]   [R path, H shape]
  → on accepted: advance exactly-once cursor (persisted, keyed by route
    identity), update local knocked state
  → on failure: surface, keep pending; retry only where idempotent
```

- Disposition mapping: walk-server trace dispositions → Numinar interaction
  types (e.g. `not_home` → no-contact result, `resolved` → survey
  completion). The mapping table is mock-defined first, real-mapped after
  capture. [H]
- Surveys: `/v1/relational-survey/` + tags (`/v1/tags`) attached to the
  interaction where the trace carries them. [R paths]
- The clock gate is upstream (server-side); the app additionally refuses to
  submit while the walk is not running — same fail-closed posture as
  Pulsar Clean.
- Exactly-once: cursor survives process death; a restart replays nothing
  older than the cursor. Server-side duplicate protection is assumed absent
  until observed.

## 5. Mock backend contract (`server/numinar-mock/`)

Flask, mirrors `campaign_project/server/harness/backend.py` (routes +
matching debugger port). Implements only what this domain calls:

```
POST /api/v1/session            login → token
GET  /v1/my-orgs-mobile         one org
GET  /v2/mobile-app/projects/   one+ projects with voter sets
GET  /v1/voters/                households with geo + per-voter data
POST /v1/interactions/batch     accepts + records (debugger shows them)
GET  /v1/relational-survey/     survey definitions
POST /v1/push/tokens/           accepted, ignored
```

The mock is the harness's definition of the Numinar contract until step-1
capture lets us diff it against reality; every mock shape carries the
evidence label and gets reconciled then.

## 6. Realtime / push

Deferred: SSE (`/v1/projects/sse/updates`) and FCM token registration are
nice-to-have; polling at stock-plausible cadence covers the harness. Twilio
voice, relational texting, contact matching, leaderboards, paid-relational,
Intercom/Mixpanel/Adjust, Mapbox native SDK: **not implemented** (the unified
map stays the offline Leaflet WebView from `walker_unified`).

## 7. Persistence

SQLite: households/voters per project, interaction outbox (FIFO, drain on
reconnect [R: stock offline semantics]), knocked-state cache, cursor store.
Encrypted prefs: session tokens. All keyed so that sign-out wipes canvassing
data but keeps walk config.

## 8. UI surfaces

- **Canvass screen**: Leaflet map (route, houses by state, me-dot),
  progress, next-house; bottom sheet with submission queue (each pending
  interaction as a row: address, disposition, state chip, age) — a stuck
  item must be visible, not a counter.
- **Lists screen**: projects as selectable lists with household/knocked
  counts, Download/Select, pull-to-refresh.
- **Settings → Accounts**: Numinar session card (identity, mock/real badge,
  sign-out), matching the ValidNation account card.

## 9. Acceptance gates (this domain)

1. Mock login → projects → households render; restart produces exactly one
   walklist upload batch (server log assertion).
2. Full harness walk: route computed from synthesized list; every latched
   house produces exactly one mock interaction; cursor prevents duplicates
   across a process restart mid-route.
3. `X-Walk-Client` version gate passes; readiness + liveness posts keep the
   walk unpaused for a full route.
4. Step-1 capture complete: mock contract diffed against real Numinar
   shapes; discrepancies fixed with evidence labels updated.
