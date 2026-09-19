# Design: Numinar domain — canvassing

The canvassing half of `alaska_walker`. Reimplements the voter-contact slice
of Numinar (`com.numinar.numinar` v10.0.0) as native Java, and plays the walk
server's `pulsar` role: session liveness, walk-list upload, and doorknock
submission off the server's latch queue.

Evidence labels: **[R]** recovered from stock app (string/code level),
**[O]** observed live, **[H]** hypothesis. Numinar's Hermes v96 bundle was
**fully decompiled 2026-09-19** via hermes-decomp — endpoint names *and*
request/response shapes are now [R], confirmed with line cites in
`../numinar/audit/` (index: `../numinar/audit/README.md`). Step-1 capture is
now only needed to verify runtime/server behavior with a test account, not
shapes. The mock backend (§5) can be built to real parity immediately.
Source material: `../numinar/ANALYSIS.md`, `../numinar/audit/`.

The same wire-parity rules as the ValidNation domain apply
(`DESIGN-VALIDNATION.md` §1): no invented fields, no harness metadata toward
Numinar hosts, server-side receipt verification.

---

## 1. Auth — mock first, Auth0 later

| Mode | Contract | Evidence |
|---|---|---|
| Mock (default for harness) | `POST /api/v1/session` (mock-defined) → opaque token; walk.json carries `mockBackend` + credentials | mock contract |
| Real (later milestone) | Auth0 `auth.numinar.com`, scope `openid profile email offline_access`, PKCE redirect `com.numinar.numinar.auth0://...`; client_id `329jKTvPKBUjOSnY9sYnf0m7Z0gkzTTm`, audience `https://api.numinar.com` (decompiled L202372–202374) | [R] flow, [R] params (`../numinar/audit/auth-session.md` §1–2) |

Token handling: refresh-capable store in encrypted prefs; 401 → one refresh
→ terminal signed-out. (Our store stays encrypted — note stock does **not**:
it keeps `access_token`/`id_token`/`refresh_token` in plaintext AsyncStorage,
no expo-secure-store anywhere, L221577–221586.) Liveness toward the walk
server (`POST /<person>/api/client/login` + `/heartbeat` 5 s) is driven by
this domain's session state — the same way Pulsar Clean did it.

## 2. Data bootstrap

| Contract | Purpose | Evidence |
|---|---|---|
| `GET /v1/my-orgs-mobile` | orgs the user belongs to | [R] (`../numinar/audit/canvassing-core.md` §2) |
| `GET /v3/projects` | projects (canvassing assignments) | [R] (`canvassing-core.md` §3) |
| `GET /v2/mobile-app/projects/{id}/voters` — params `{ignore_contacted, include_past_contacts, limit:10000, include_tags, compress:true}` → gzipped column-oriented `voters_compressed` | voter/household records with geo (single page, no offset/bbox) | [R] (`canvassing-core.md` §4) |
| `GET /v1/nearby-voters` — params only `{latitude, longitude}` | nearby voters for relational-neighbors mode | [R] (`canvassing-core.md` §5) |
| `GET /v1/projects/sse/updates` | SSE change notifications (optional; polling fallback) | [R] (`../numinar/audit/push-realtime-endpoints.md` §2.2) |

Stock is offline-first (AsyncStorage `offline_buffer` + `/v1/interactions/
batch` retry queue [R]; no expo-sqlite in the JS bundle); ours mirrors that
with a SQLite store keyed by project, and one bounded serial fetch per
restart (single-flight; no duplicate concurrent fetches).

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
    disposition, survey answers?, timestamp, gps}]   [R path, R shape]
  → on accepted: advance exactly-once cursor (persisted, keyed by route
    identity), update local knocked state
  → on failure: surface, keep pending; retry only where idempotent
```

- Interaction schema [R]: full confirmed canvass object and disposition enum
  (`canvassed|Not Home|Refused|Wrong Address|Inaccessible Address|Dropped
  Literature|Other`) in `../numinar/audit/interactions-surveys.md` §1.2.
  Confirmed extra telemetry on canvass interactions — `user_latitude`/
  `user_longitude` (canvasser GPS, **strings**), `device_id`,
  `is_using_emulator`, `device_geolocation_enabled`,
  `device_geolocation_permission_status` — are wire-parity obligations for
  our client now, as is the 15 s `POST /v1/canvassing-qa/tracking` GPS beacon
  (`interactions-surveys.md` §3): the server sees canvasser liveness/location
  through it, so its absence is detectable.
- Disposition mapping: walk-server trace dispositions → Numinar interaction
  types (e.g. `not_home` → `Not Home`, `resolved` → survey completion).
  The mapping table is mock-defined first, then checked against the real
  enum above. [H mapping, R enum]
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
GET  /v3/projects               one+ projects
GET  /v2/mobile-app/projects/{id}/voters
                                households with geo + per-voter data
                                (gzip-compressed column JSON in
                                voters_compressed, matching stock's
                                compress:true request)
POST /v1/interactions/batch     accepts + records (debugger shows them)
GET  /v1/relational-survey/     survey definitions
POST /v1/canvassing-qa/tracking accepts + records the 15 s GPS QA beacon
POST /v1/push/tokens            accepted, ignored
```

Shapes are now [R]-verified against `../numinar/audit/`, so the mock can be
built to real parity immediately; step-1 runtime capture only confirms
server behavior (status codes, error envelopes), and any discrepancy found
then gets reconciled with evidence labels updated.

## 6. Realtime / push

Deferred: SSE (`/v1/projects/sse/updates`; stock reconnects on a flat 3 s
interval, no backoff, no cap [R]) and FCM token registration are
nice-to-have; polling at stock-plausible cadence covers the harness. Twilio
voice, relational texting, contact matching, leaderboards, paid-relational,
Intercom/Mixpanel/Adjust, Mapbox native SDK: **not implemented** (the unified
map stays the offline Leaflet WebView from `walker_unified`).

## 7. Persistence

SQLite: households/voters per project, interaction outbox (FIFO, drain on
reconnect — mirroring stock's AsyncStorage `offline_buffer` semantics:
dedupe key `url_voter_id_project_id_tag_id`, drain in batches of 10 [R]),
knocked-state cache, cursor store. Encrypted prefs: session tokens (note:
stock itself uses plaintext AsyncStorage for tokens; we keep encrypted
prefs). All keyed so that sign-out wipes canvassing data but keeps walk
config.

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
4. Step-1 shape capture is **done statically** (hermes-decomp 2026-09-19;
   fixtures in `../numinar/audit/`); what remains is a runtime canary
   against the real API with a test account — sanitized live responses
   match the audit fixtures, Auth0 login works with the recovered
   client_id/audience.
