# Numinar decompiled-bundle audit index — `com.numinar.numinar` v10.0.0

Six audit files produced from the full JavaScript decompilation of the app's
Hermes v96 bundle (see "How this was produced" below). All line citations
(`L<n>`) refer to `/tmp/numinar_decompiled_rust.js` (400,709 lines); `p1:L<n>`
refers to the register-level cross-check `/tmp/numinar_decompiled_p1.js`.
Everything in these files is code-confirmed unless tagged **UNCONFIRMED**.
Where they conflict with `../ANALYSIS.md` or `../../docs/DESIGN-NUMINAR.md`,
these files are the ground truth.

## Files

- **[auth-session.md](auth-session.md)** — the complete Auth0 integration.
  Recovers the configuration constants (`AUTH0_DOMAIN auth.numinar.com`,
  `AUTH0_CLIENT_ID 329jKTvPKBUjOSnY9sYnf0m7Z0gkzTTm`, `AUTH0_AUDIENCE
  https://api.numinar.com`, L202372–202374), all four login flows (including
  the hand-rolled email magic-code path: `POST /passwordless/start` +
  `POST /oauth/token` passwordless/otp grant), the refresh-token exchange,
  token storage (AsyncStorage **plaintext** keys `access_token`/`id_token`/
  `refresh_token` — no expo-secure-store anywhere), the shared fetch envelope
  (headers, 61 s timeout, 1 timeout retry, single 401→refresh→retry), the dead
  `usingFastApi` flag, session bootstrap, the WebSocket session (JWT in the
  query string), and sign-out (local-only; refresh token never revoked).

- **[canvassing-core.md](canvassing-core.md)** — org/project/voter bootstrap
  and the canvassing data model. Confirms the project list is
  `GET /v3/projects` (not `/v2/mobile-app/projects/`), the voter download is
  `GET /v2/mobile-app/projects/{id}/voters` with the exact param set
  `{ignore_contacted, include_past_contacts, limit:10000, include_tags,
  compress:true}` returning gzipped column-oriented JSON (`voters_compressed`),
  `GET /v1/nearby-voters` takes only `{latitude, longitude}`, and there is **no**
  plain `GET /v1/voters/` list call. Also documents voter search, per-voter
  sub-resources, the household-grouping logic (`house_hold_id` spelling,
  location bucketing, street extraction), the full voter object schema, and
  the AsyncStorage offline-cache layout (no expo-sqlite in the JS bundle).

- **[interactions-surveys.md](interactions-surveys.md)** — the write path.
  Full confirmed schemas for `POST /v1/interactions/batch` across all five
  interaction subtypes (canvass, call, relational-survey, tag, notes), the
  type-guard classification order, the canvass disposition enum
  (`canvassed|Not Home|Refused|Wrong Address|Inaccessible Address|Dropped
  Literature|Other`), the anti-fraud telemetry embedded in canvass
  interactions (`user_latitude`/`user_longitude` as strings, `device_id`,
  `is_using_emulator`, geolocation permission status), the AsyncStorage
  `offline_buffer` queue (dedupe key `url_voter_id_project_id_tag_id`, drain
  in batches of 10), the 15 s `/v1/canvassing-qa/tracking` beacon, relational
  survey/tag read endpoints, and the WS "canvassed" side-channel.

- **[push-realtime-endpoints.md](push-realtime-endpoints.md)** — push
  notifications, SSE, WebSocket, Twilio calling, and a complete endpoint
  sweep. Documents `POST /v1/push/tokens` (`{expo_push_token, is_android,
  device_push_token}`) and the logout-time DELETE, the notification inbox
  routes, both SSE streams and the `useSSE` hook (flat 3 s reconnect, no
  backoff), the WebSocket protocol (30 s `"ping"` keepalive, 1001/5 s
  reconnect policy, double-encoded `canvassed` messages), the Twilio
  server-side dialing flow (`GET /api/v3/auth_token` + `POST
  /api/v3/amd_call`), leaderboards, paid-relational payouts, contact matching
  (entire address book uploaded to `POST /v1/contact-matches`), and an
  exhaustive first-party endpoint inventory with per-endpoint line cites.

- **[security-antifraud.md](security-antifraud.md)** — anti-tamper and
  privacy posture. Establishes that Numinar has essentially **no** anti-fraud:
  no root/jailbreak gate, no mock-GPS detection, no debugger/Frida checks, no
  tamper/signature self-check, no Play Integrity/SafetyNet, no certificate
  pinning, and unsigned expo-updates OTA. Emulator detection exists but is
  telemetry-only (`is_using_emulator` on uploads, never gates). Also documents
  the Sentry configuration (100% session-replay sample rate with text/image/
  vector masking **disabled**, live DSN `o463956.ingest.sentry.io/5469707`),
  Mixpanel events carrying voter PII, Adjust (the only real anti-fraud
  component, protecting Adjust's own pipeline), and Intercom HMAC login.

- **[telemetry-sensors.md](telemetry-sensors.md)** — location and sensor
  collection. Details the `/v1/canvassing-qa/tracking` beacon (every 15 s
  while logged in with an org, foreground-only; one-shot high-accuracy GPS fix
  per ping; full field provenance), all one-shot GPS call sites, GPS inside
  canvass interactions, and the negative results: no background location, no
  geofencing, no WiFi scans, no BLE scans, no motion/battery collection, mic
  only for Twilio VoIP. (WiFi/BLE/motion/battery surveillance is a
  ValidNation-domain feature set, not Numinar.)

## How this was produced

On 2026-09-19 the app's `index.android.bundle` (Hermes bytecode **v96**) was
fully decompiled with **hermes-decomp** (Rust,
<https://github.com/SymbioticSec/hermes-decomp>, built at
`/tmp/hermes-decomp`), invalidating the earlier claim in `../ANALYSIS.md` that
v96 was not decompilable with current tooling. Outputs:

- `/tmp/numinar_decompiled_rust.js` — primary decompilation, 400,709 lines
  (all `L<n>` citations).
- `/tmp/numinar_decompiled_p1.js` — register-level decompilation used as a
  cross-check (`p1:L<n>` citations).
- `/tmp/numinar_extract/assets/index.android.bundle.hdcache` — hermes-decomp
  analysis cache (speeds up re-runs).

To reproduce:

```bash
# 1. Extract the bundle from the stock base APK
unzip -o numinar/stock/base.apk assets/index.android.bundle -d /tmp/numinar_extract

# 2. Decompile (primary readable JS)
/tmp/hermes-decomp/target/release/hermes-decomp decompile \
    /tmp/numinar_extract/assets/index.android.bundle \
    -o /tmp/numinar_decompiled_rust.js

# 3. Register-level cross-check (optional, used for p1: cites)
/tmp/hermes-decomp/target/release/hermes-decomp decompile \
    /tmp/numinar_extract/assets/index.android.bundle \
    -o /tmp/numinar_decompiled_p1.js --p1
```

(Exact flag spelling per `hermes-decomp --help`; the cache file lets re-runs
skip re-analysis.) The six audit files were then written by manual analysis of
the decompiled JS, sweeping for endpoint literals, request builders, and
storage keys, with ambiguous decompiler output cross-checked between the two
decompilations and against the JADX output under `numinar/java/sources/`.
