# Numinar analysis — `com.numinar.numinar` v10.0.0 (100000)

Expo/React Native app (RN 0.83.10, New Arch, Hermes **bytecode v96**). 7 dexes,
minSdk 25, targetSdk 36. Stock APKs in `stock/`, frozen baseline in
`BASELINE.md`. **The full JS bundle was recovered 2026-09-19** via
hermes-decomp (see "Hermes v96 recovery" below); line-cited audit findings
live in `audit/` (`L<n>` cites refer to `/tmp/numinar_decompiled_rust.js`).

**Role in this project: the canvassing app (Pulsar equivalent).**

## Feature surface

Relational-organizing + household canvassing + outreach. **No time clock.**

- **Canvassing (household-based, no turf/walklist concept)**:
  `CanvassVoterListScreen`, `OfflineBulkCanvassHouseholdListScreen`,
  `groupHouseholdsByLocation`, `VotersInHouseholdHaveVoted`,
  `markHouseholdUnavailable`, `insertCanvassInteraction` /
  `BulkInsertCanvassInteraction`, voter history (absentee/early-vote fields),
  `/v1/canvassing-qa/tracking` (canvasser GPS QA pings).
- **Surveys**: `/v1/relational-survey/`, `useSubmitRelationalSurvey`, tags
  (`/v1/tags`, `/v2/voter_tags/`).
- **Relational organizing** (core concept): READ_CONTACTS →
  `/v1/contact-matches`, `/v1/voter-contacts/`, relational texting
  (native SMS intent + server batch via Bandwidth), leaderboards
  (`/v1/mobile/leaderboard`), paid-relational payouts
  (`fast-api.numinar.com/api/v2/me/relational-payment`).
- **Calling**: Twilio Voice VoIP (`/api/v3/auth_token`,
  `/api/v3/twilio_numbers`, `/api/v3/amd_call`), voter outreach calls,
  not a predictive dialer.
- **Out of scope for us**: Twilio calling, relational texting, Intercom,
  Mixpanel/Adjust analytics, paid-relational payouts, contact matching.

## Backends (multiple hosts)

| Host | Surface |
|---|---|
| `auth.numinar.com` | Auth0 tenant (custom domain) |
| `fast-api.numinar.com` | **all** REST API traffic under `/api` — `/v1/...`, `/v2/...`, `/v3/...` (voters, interactions, projects, push, SSE) |
| `rust-server.numinar.com` | `/api/v3/...` (Twilio tokens, Bandwidth texting, outreach) + `/websocket` |
| `mobile.numinar.com` | **not an API host** — only a deep-link rewrite target (`numinar://` → `https://mobile.numinar.com/`, decompiled L337400) |

## Auth

**Auth0** via react-native-auth0 (SDK 5.11.0), Web Auth Custom Tabs
(redirect `com.numinar.numinar.auth0://auth.numinar.com/.../callback`).
Scope `openid profile email offline_access` (refresh tokens).
`AUTH0_CLIENT_ID`/`AUTH0_AUDIENCE` **are statically recoverable** as plain
string constants (decompiled L202372–202374): client_id
`329jKTvPKBUjOSnY9sYnf0m7Z0gkzTTm`, domain `auth.numinar.com`, audience
`https://api.numinar.com` (audience is JWT-only; no fetch targets it).
Four login paths, incl. a hand-rolled email magic-code flow
(`POST /passwordless/start` + `POST /oauth/token` passwordless/otp grant,
`audit/auth-session.md` §2.1–2.2). Tokens are stored in **AsyncStorage
plaintext** keys `access_token`/`id_token`/`refresh_token` (L221577–221586) —
there is no expo-secure-store anywhere in the bundle; the Keystore-backed
Auth0 `CredentialsManager` is only written by the SDK web-auth flows and read
once for legacy migration. JWT claims namespaced
`https://numinar.com/roles`, `.../email_verified`. Logout is local-only — the
refresh token is never revoked server-side (`audit/auth-session.md` §10).

## Key endpoints (canvassing slice)

All on `fast-api.numinar.com/api` (full inventory with line cites:
`audit/push-realtime-endpoints.md` §9.1):
`/v3/projects` (project list — **not** `/v2/mobile-app/projects/`),
`/v2/mobile-app/projects/{id}/voters` (voter download; params
`{ignore_contacted, include_past_contacts, limit:10000, include_tags,
compress:true}` → gzipped column-oriented `voters_compressed`; **no plain
`GET /v1/voters/` list call exists**), `/v1/nearby-voters` (params only
`{latitude, longitude}`), `/v1/mobile-voter-search`,
`/v1/interactions/batch` (offline sync upload, chunks of 10),
`/v1/canvassing-qa/tracking` (15 s GPS QA beacon), `/v1/relational-survey/`,
`/v1/tags`, `/v1/my-orgs-mobile`, `/v1/projects/sse/updates` (SSE),
`/v1/push/tokens`. (`/v1/interactions/callback`, previously listed here, does
**not** appear anywhere in the decompiled bundle — stale.)

## Location / storage / push

- Mapbox maps (RNMBX), embedded **secret** `sk.eyJ1IjoibnVtaW5hciIs...` token
  shipped client-side (L202388); stock styles only. Location foreground-only
  (FINE/COARSE; no background permission, no FGS location, one-shot fixes
  only — `audit/telemetry-sensors.md`).
- Offline: **AsyncStorage only** — no expo-sqlite in the JS bundle (the
  sqlite-looking artifacts are AsyncStorage's `AsyncSQLiteDBStorage` backing,
  L199477–199501) and no redux-persist (manual AsyncStorage writes).
  Offline interaction queue = AsyncStorage `offline_buffer` JSON array,
  dedupe key `url_voter_id_project_id_tag_id`, drained in batches of 10
  (`audit/interactions-surveys.md` §2). 20 MB CursorWindow.
- FCM (3 services: app notifications, Twilio Voice, Intercom) + Expo push
  (`/v1/push/tokens`) + WebSocket + SSE. No Pusher.
- Sentry live DSN `o463956.ingest.sentry.io/5469707` (L394539) with **100%
  session replay, masking disabled** (the `o447951.../4509632503087104`
  string is dormant SDK self-test code, not the app DSN —
  `audit/security-antifraud.md` §5). Intercom `zskx6pd1`,
  EAS project `690023b7-7c29-48ba-a024-2757d50beed2`, channel `production`.
- `usesCleartextTraffic=false`, `allowBackup=false`. No cert pinning; OTA
  (expo-updates) is unsigned. No root/mock-GPS/debugger/Play-Integrity
  checks anywhere (`audit/security-antifraud.md`).

## Signing

Vendor/Play-signed; rebuilds need their own applicationId.

## Hermes v96 recovery — DONE (2026-09-19)

The v96 bundle was fully decompiled with **hermes-decomp** (Rust,
<https://github.com/SymbioticSec/hermes-decomp>, built at
`/tmp/hermes-decomp`) — hbctool's v96 rejection no longer matters:

- Bundle: `/tmp/numinar_extract/assets/index.android.bundle` (unzipped from
  `stock/base.apk`); analysis cache `…/index.android.bundle.hdcache`.
- Primary output: `/tmp/numinar_decompiled_rust.js` (400,709 lines, readable
  JS; all `L<n>` cites in `audit/`).
- Register-level cross-check: `/tmp/numinar_decompiled_p1.js` (`p1:` cites).
- Reproduce: `hermes-decomp decompile <bundle> -o <out.js>` — see
  `audit/README.md` for the exact commands.

Six audit files with line-cited findings live in `audit/` (index:
`audit/README.md`): auth-session, canvassing-core, interactions-surveys,
push-realtime-endpoints, security-antifraud, telemetry-sensors. Exact payload
shapes are now statically confirmed; remaining runtime work is a canary
against the real API with a test account (server behavior, not shapes).
