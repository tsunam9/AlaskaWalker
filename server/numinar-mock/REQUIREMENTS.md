# Numinar mock backend — implementation requirements

Contract for implementing `server/numinar-mock/`: a Flask re-implementation of
the Numinar backend (`fast-api.numinar.com/api`, `rust-server.numinar.com`,
`auth.numinar.com`) for the Alaska campaign. Mirrors the proven
`server/patriot-mock/` architecture, conventions, and test methodology — read
that package and its README first; this document only describes what differs
and what the Numinar surface requires.

## 1. Mission & consumers

1. **Repointed stock app fidelity test** — rebuild `com.numinar.numinar`
   v10.0.0 with its origins pointed at this mock (see §10). If the stock app
   runs its normal workflow (login → org → project → voters → canvass → QA
   beacon) with zero client-visible errors, the mock is behaviorally
   indistinguishable for that surface.
2. **`alaska_walker/` development** — the reimplemented canvassing domain
   develops against the mock before any real-backend canary (plan step 6/9).

Port: **0.0.0.0:19002** (router port-forward convention: 19001 patriot,
19002 numinar). One Flask process plays **all three origins** — the
repointed app points every host at the mock.

## 2. Ground truth (read fully before writing code)

`numinar/audit/` — six line-cited audit files, produced from the full
hermes-decomp decompilation of the Hermes v96 bundle. **These are ground
truth**; where they conflict with `numinar/ANALYSIS.md` or
`docs/DESIGN-NUMINAR.md`, the audits win:

- `auth-session.md` — Auth0 flows, token shapes, refresh, headers envelope
- `canvassing-core.md` — orgs, projects, voter download, household model,
  voter schema (§10)
- `interactions-surveys.md` — `/v1/interactions/batch` all five subtypes,
  offline queue semantics, QA beacon, tags, relational surveys
- `push-realtime-endpoints.md` — push tokens, notification inbox, SSE,
  Twilio, leaderboards, payouts, contact matching, full endpoint sweep (§9)
- `telemetry-sensors.md` — QA tracking beacon field provenance
- `security-antifraud.md` — anti-fraud posture (essentially none)

When an audit says a shape is UNCONFIRMED or you need a field the audit
doesn't name, consult the cited lines in `/tmp/numinar_decompiled_rust.js`
(400k-line decompile; `L<n>` cites) or `/tmp/numinar_decompiled_p1.js`.

Evidence labels in code comments: **[R]** code-confirmed (cite audit §/line),
**[H]** hypothesis — chosen to keep the stock client's state machine
coherent; every [H] is a candidate for correction by the repointed-app run.

## 3. Wire invariants (all endpoints)

From `auth-session.md` §5 / `canvassing-core.md` §1:

- Every request carries headers: `Content-Type: application/json`,
  `numinar-origin: mobile`, `platform: android`, `x-org-id: <org id>`,
  optionally `sentry-sid`, and `Authorization: Bearer <Auth0 access token>`
  unless the request is `requiresAuth: false` (`HEAD /v1/mobile_204`,
  Auth0 endpoints). The mock must accept and log these; org scoping is
  driven by `x-org-id`.
- **Success = HTTP 200** with the expected body shape. Errors: fast-api
  convention `{"detail": "..."}`; Auth0 endpoints use Auth0 error shape
  `{"error": ..., "error_description": ...}` (client reads
  `error_description ?? error`, auth-session §2.1).
- **401 contract**: any 401 triggers one refresh + one identical retry
  client-side — EXCEPT 401s whose body is exactly
  `{"detail": "You need to verify your email to access this resource"}`,
  which bypass refresh and drive the VerifyEmail gate. Use this only for
  a fixture user with `email_verified: false`.
- Timeouts are client-side (61 s default, 5–10 s on specific calls); the
  mock just answers promptly.
- **Access tokens are JWTs decoded by the client** and must carry:
  - standard `exp`, `aud` = `https://api.numinar.com` (audience constant)
  - `https://numinar.com/roles` (array; `"admin"` in [0] gates admin UI —
    keep the fixture user non-admin)
  - `https://numinar.com/email_verified` (boolean; gates VerifyEmail screen)
  The access token uses HS256 with a mock-only secret (the JS client only
  decodes its claims). **Corrected 2026-09-23 from the repointed-stock Web
  Auth run:** Auth0.Android independently validates `id_token`; the mock must
  sign it with RS256, advertise the matching `kid` at
  `GET /.well-known/jwks.json`, preserve the request `nonce`, and use the
  SDK's exact repointed domain URL as `iss` (including same-length slash
  padding).
- Refresh: `POST /oauth/token` with `grant_type: "refresh_token"`. The
  client tolerates rotation **or** no rotation (keeps old token if the
  response omits one) — simplest correct behavior: return a new
  `access_token` and omit `refresh_token`.

## 4. Endpoint requirements — Phase 1 (core workflow; the fidelity gate)

### Auth0 origin (auth.numinar.com)

| Endpoint | Requirements |
|---|---|
| `POST /passwordless/start` | Body `{client_id, connection:"email", email, send:"code", authParams:{scope, audience, redirect_uri}}` (auth-session §2.1). Issue a mock 6-digit OTP; store it; return 200 (`response.ok` is all the client checks). Print the OTP to the mock log/dashboard (it is the "email"). |
| `POST /oauth/token` | Three grant shapes: (a) `http://auth0.com/oauth/grant-type/passwordless/otp` — validate `{username, otp, realm:"email"}` against the issued OTP; wrong → 4xx Auth0 error shape; (b) `refresh_token` grant (§3 above); (c) `authorization_code` — exchange a code issued by the mock `/authorize` page and carry its nonce into the ID token (corrected [O] 2026-09-23 after the repointed-stock browser flow). Success returns `{access_token, refresh_token, id_token, scope, token_type:"Bearer", expires_in}` (all consumed, auth-session §2.6). |
| `GET /.well-known/jwks.json` | Publish the persistent mock RSA public key as an Auth0-compatible RS256 JWKS; `kid` must match the ID-token header. |
| `GET /userinfo` | Bearer → user profile object consumed by `setAuth0User` (auth-session §8.2). Failure → client falls back to id_token decode, so any object with name/email/sub fields works; return the fixture profile. |

### fast-api origin — bootstrap

| Endpoint | Requirements |
|---|---|
| `HEAD /v1/mobile_204` | Connectivity probe, `requiresAuth:false`, every 15 s. Return 204 with empty body. |
| `GET /v1/me` | User profile; cached client-side under AsyncStorage `me`. Consumed fields per canvassing-core §13 / auth-session §8.3. |
| `PUT /v1/me` | First-run registration `{has_registered: true}`; accept + persist. |
| `GET /v1/my-orgs-mobile` | Array of orgs (client sorts by name). Org fields read: `id, name, slug, signed_url, selected_state, data_source, has_relational_enabled` (canvassing-core §2). One fixture org suffices. |
| `GET /v2/orgs/{orgId}` | Org detail; staleTime Infinity. |
| `GET /v1/public-orgs` | Org-join browser; fixture list. |
| `POST /v1/orgs/{orgId}/join` | Accept; membership recorded. |
| `PUT /v1/orgs/{orgId}/invite-status` | `{invite_status}` accept/decline. |
| `POST /v1/verification-email` | Empty body; accept (user-driven resend). |
| `POST /v1/push/tokens` | `{expo_push_token, is_android, device_push_token}`; store; tolerate duplicates (client may double-call). |
| `DELETE /v1/push/tokens/{token}` | Logout-time deletion. |

### fast-api origin — projects & voters

| Endpoint | Requirements |
|---|---|
| `GET /v3/projects` | Project array for the org. Fields consumed (canvassing-core §3): `id, name, outreach_type (canvass\|call\|relational), status, is_active, created_at, description, county_name, geofence_name, precinct_name, precinct_id, abev_election_id, dynamic_survey.id, survey (+survey.questions), text, specific_number, conditional_survey`. At least one `canvass` project with a real `survey.questions[]` (so the canvass survey flow works), one `call`, and set `conditional_survey` truthy so the synthetic "Contact Your Neighbors" project appears. |
| `GET /v3/projects/{id}` | Single project (refetched on select). Same shape. |
| `GET /v2/mobile-app/projects/{id}/voters` | **The critical one.** Query params exactly `{ignore_contacted, include_past_contacts, limit:10000, include_tags, compress:true}` (canvassing-core §4). Response: `{"voters_compressed": "<gzip-deflated base64? — verify encoding against decompressVoters L200160–200179>"}` containing **column-oriented** JSON `{field: [values...]}`. Read the actual decompress/compress functions (canvassing-core §4, §11) and match the encoding byte-for-byte — this is the easiest place to silently poison the app. Voter objects need the full §10 schema (id, house_hold_id — note the spelling, names, registration_address_* incl. lat/lng, registered_party_roll_up, official_party, rnc_calc_party, voter_status, permanent_absentee, voter_frequency_*, vh_* history, abev fields, age, sex, cell_phone_number, is_in_list, has_interaction). Generate ~200–500 Alaska-plausible voters with realistic household clustering (shared house_hold_id + identical address lat/lng per household). |
| `GET /v1/nearby-voters` | Params exactly `{latitude, longitude}`; return an array of voter objects near the point (any reasonable radius — server-side choice, mark [H]). |
| `GET /v1/mobile-voter-search` | Params = search form fields + `{limit:100, offset:0}`; substring/case-insensitive matching over the voter fixture is fine. |
| `GET /v1/voters/{id}/notes` | Notes text for the voter (from stored note interactions). |
| `GET /v1/voters/{id}/interactions` | Voter activity feed from stored interactions. |
| `GET /v2/voter_tags/{voterId}` | `{tags: {<n>: {tag_id, tag_value, ...}}}` from stored tag interactions. |
| `GET /v1/projects/{pid}/voters/{vid}` | Single voter (call flow). |
| `GET /v1/voter-filter-categories` | `{political: [{internal_name, filters...}]}`; must include whatever `registered_party_roll_up` values the fixture uses. staleTime Infinity. |
| `GET /v1/projects/{id}/counts` | Call-screen counts [H shape]. |
| `GET /v1/tags` | Org tag definitions for the picker. |
| `GET /v1/relational-survey` and `/v1/relational-survey/{projectId}` | Survey definitions; consumed shape: `questions[]` with `id, tag_id` + jump logic; `tags` map (interactions-surveys §4). |
| `GET /v1/relational-text` and `/{projectId}` | Text templates. |
| `GET /v1/user-outreach-stats` | Achievements screen; params `{cycle?}` [H shape — derive from stored interactions]. |

### fast-api origin — the write path (highest fidelity priority)

| Endpoint | Requirements |
|---|---|
| `POST /v1/interactions/batch` | JSON array of interaction objects in ANY of the five confirmed shapes (interactions-surveys §1.1–1.7): canvass (with `user_latitude`/`user_longitude` **strings**, `device_id`, `is_using_emulator`, geolocation flags, `household_id`, disposition enum `canvassed\|Not Home\|Refused\|Wrong Address\|Inaccessible Address\|Dropped Literature\|Other`), call (`call_length` + CallDisposition enum), relational-survey (`survey_type:"relational"`), tag (`tag_id, value, org_id` in body), notes (fallback bucket — `{project_id, voter_id, value, created_at, id}`). Classify with the audit's guard order (canvass → call → relational → tag → notes). Validate accordingly; store each; flip `has_interaction` on the voter; keep responses[]/notes as sub-records. Response body is **never parsed** — return minimal 200. Must accept 1-element arrays and 10-element offline-drain batches; must tolerate client-uuid duplicates (the drain has no per-item ack). |
| `POST /v1/interactions/call` | `{project_id, voter_id, disposition, call_length}` — call-end disposition, no queue. |
| `POST /v1/interactions/relational-text` | `{user_id, voter_id, project_id, outreach_type:"text", abev_status, created_at, device_id, is_using_emulator}`. |
| `POST /v1/canvassing-qa/tracking` | The 15 s beacon: `{project_id?, latitude?, longitude?, device_id?, device_geolocation_enabled?, device_geolocation_permission_status?, is_using_emulator}` — every field optional (best-effort client). Store for telemetry capture; response unused. |

## 5. Phase 2 (secondary screens — implement after Phase 1 passes)

Notification inbox: `GET /v1/push/notifications`,
`POST /v1/push/notifications/read`, `POST .../read-all`,
`DELETE /v1/push/notifications`, `DELETE /v1/push/notifications/bulk`
(shapes in push-realtime-endpoints §1.3). Contact matching:
`GET /v1/contact-matches` (5 s status poll), `POST /v1/contact-matches`
(`{contact_data[]}` full address book), `GET /v1/voter-contacts[/{projectId}]`.
Payouts: `GET /v2/me/relational-payment`, `POST /v2/me/relational-payment`
`{timezone}`. Leaderboard: `GET /v1/mobile/leaderboard` params
`{cycle?, start_datetime?, end_datetime?}`.

## 6. Phase 3 (stub/ack so unsupported screens don't crash)

ROS origin (rust-server.numinar.com): `GET /api/v3/auth_token`,
`GET /api/v3/twilio_numbers`, `POST /api/v3/amd_call`,
`GET /api/v3/outreach/status/{projectId}`, `GET /api/v3/project/{projectId}/queue`,
`GET /api/v3/project/loading_status/{projectId}`,
`GET /api/v3/bandwidth/numbers`, `POST /api/v3/bandwidth/batch-texts`.
Return plausible minimal seed shapes (read push-realtime-endpoints §2–§8
for consumed fields). SSE streams (`GET /v1/projects/sse/updates` fast-api,
`GET /api/v3/events/source/outreach/{id}`, `.../calls/{id}` ROS): Flask can
serve SSE with a generator — emit an initial status event then keep the
stream; reconnect interval 3 s client-side.

**Corrected 2026-09-23 after repointed-stock observation:** the ROS WebSocket
(`wss://rust-server.numinar.com/websocket`) needs a minimal acceptor because
`websocketUp` gates the offline drain client-side. Remaining explicit
non-goals are Twilio call media, Bandwidth SMS delivery,
and third-party telemetry SDK hosts (Sentry/Intercom/Mixpanel/Adjust —
traffic goes to those vendors, not Numinar). Mapbox and Google Maps are the
explicit map-rendering exception recorded in §8.1.

## 7. State & semantics

- Single in-memory store + `runtime-state.json` persistence (same pattern
  as patriot-mock: orgs, users, projects, voters, interactions, tags,
  notes, QA pings, push tokens, OTPs). Persist enough that a mock restart
  mid-session doesn't strand the client (interactions, voter
  has_interaction flags, auth sessions/refresh tokens).
- **has_interaction flips server-side** on accepted interactions and is
  reflected in subsequent voter fetches (`has_interaction` field,
  canvassing-core §10).
- The offline drain replays interactions that may have partially landed —
  never 4xx on a duplicate client `id`; accept and dedupe [H server
  semantics].
- OTPs are single-use with a generous TTL; refresh tokens long-lived
  (Auth0-like); no server-side logout semantics (stock never revokes —
  auth-session §10; match that: logout is local-only).

## 8. Anti-fraud posture (match the real thing: essentially none)

Per `security-antifraud.md`: no root/mock-GPS detection, no emulator gate,
no cert pinning. The mock must **accept** `is_using_emulator`,
geolocation-permission fields, and device uuids verbatim and store them as
telemetry — never gate or reject on them. The `numinar-origin: mobile` /
`platform: android` headers are observed, not enforced.

### 8.1 Vendor egress isolation (added 2026-09-23 per user direction;
map exception added 2026-09-23 per subsequent user direction)

The repointed stock build must **never send a request to a real third-party
vendor backend carrying Numinar-identifying material** — API keys, DSNs,
SDK app tokens, EAS/Firebase project IDs, or account-linked device
fingerprints. If the vendor can attribute the traffic to Numinar, the
traffic must not happen at all, **except for the stock Mapbox and Google Maps
credentials explicitly restored by user direction so the map can render**.
Outside that narrow map exception, this rule overrides app functionality.

Applied in `numinar/instrumentation/build_repointed.sh`:

- **Adjust**: `initSdk` call removed + app token zeroed + manifest
  components disabled (device fingerprinting under Numinar's Adjust account).
- **Sentry**: both DSN/envelope URLs → `.invalid` TLD; native providers
  disabled (DSN identifies Numinar's project; payloads carry voter PII and
  session replay).
- **Mixpanel**: host → `.invalid`/mock; token entry repurposed (events carry
  voter PII under Numinar's project token).
- **Mapbox (explicit exception, corrected 2026-09-23):** preserve the stock
  `sk.` account token so map tiles can render.
- **Google Maps (explicit exception, corrected 2026-09-23):** preserve the
  stock `com.google.android.geo.API_KEY` manifest value so maps can render.
- **Expo/EAS**: `exp.host` push-token endpoint → `.invalid`; expo-updates
  disabled (update check carries Numinar's EAS project ID, and an OTA would
  overwrite the patch).
- **Firebase/FCM, Intercom, Twilio FCM**: autostart components disabled
  (registration would carry Numinar's Firebase project and user PII).

**Permitted APK modifications are only:** (a) connection viability — origin
host/scheme rewrites to the mock, cleartext network config, the auth-callback
intent-filter addition, OTA disable; (b) vendor egress isolation as above;
(c) local re-signing. No functional, UI, or logic changes to the app itself.
Traffic to the mock itself (including neutered-SDK 404s) is fine — it is
captured, not leaked.

## 9. Ops & repo conventions (same as patriot-mock)

- Package layout mirroring `server/patriot-mock/`: `numinar_mock.py`
  entrypoint, `mock/` package (`__init__` app factory, `config.py`,
  `state.py`, domain blueprints: `auth0.py`, `orgs.py`, `projects.py`,
  `voters.py`, `interactions.py`, `push.py`, `ros.py`), `fixtures/`
  (org/user/projects/voters JSON or generator script), `scripts/` tests.
- Dashboard at `/__mock/` (reuse the patriot dashboard approach) with the
  same Basic auth convention (`PM_DASH_USER`/`PM_DASH_PASS`, default
  admin/testpass123); `/api`+Auth0 paths stay Bearer-only.
- Durable telemetry capture to `numinar-mock/captures/` JSONL (same family
  as patriot: interactions, QA tracking pings, requests) for later
  comparison against harness walks — see `server/patriot-mock/CAPTURES.md`.
- Env: `PM_HOST`, `PM_PORT` (19002), `PM_STATE_PATH`, `PM_CAPTURE`,
  `PM_DASH_USER/PASS`.
- .gitignore: captures, runtime-state.json, `__pycache__`.

## 10. Acceptance gates (each must pass before the next)

1. `scripts/test_auth0.sh` — OTP flow end-to-end (start → log shows code →
   token), refresh grant, userinfo, verify-email 401 semantics.
2. `scripts/test_core.sh` — bootstrap chain (me → orgs → org → projects →
   project → voters) with the voters_compressed round-trip verified by
   re-inflating with the audit's decompress algorithm; nearby-voters;
   search; per-voter sub-resources.
3. `scripts/test_interactions.sh` — all five interaction types accepted,
   guard-order classification correct, has_interaction flips, 10-item
   mixed drain batch, duplicate tolerance, QA beacon stored.
4. `scripts/simulate_workflow.py` — full stock sequence:
   passwordless → userinfo → me → orgs → org select → projects → project
   select → voters download → QA beacon cadence → canvass submit →
   offline drain of 10 → voter re-fetch shows has_interaction.
5. **Repointed stock app run** — the real gate. Note: repointing Numinar
   is harder than Patriot (origins are string constants inside a Hermes
   v96 bytecode bundle, not an HTML runtime config). Options: hbctool/HASM
   string-table rebuild (`.venv-re/` has hbctool), patching at the native
   level, or network-layer redirection (DNS/hosts on a rooted device or
   emulator — security-antifraud.md confirms no pinning, so plain HTTP
   proxy + hosts rewrite works). That build task is tracked separately;
   this mock must be ready for it.
