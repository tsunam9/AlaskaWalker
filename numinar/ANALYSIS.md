# Numinar analysis — `com.numinar.numinar` v10.0.0 (100000)

Expo/React Native app (RN 0.83.10, New Arch, Hermes **bytecode v96** — too new
for hbctool; analysis is from string table + Java glue). 7 dexes, minSdk 25,
targetSdk 36. Stock APKs in `stock/`, frozen baseline in `BASELINE.md`.

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
| `mobile.numinar.com` | main `/v1/...` API (voters, interactions, projects, push, SSE) |
| `rust-server.numinar.com` | `/api/v3/...` (Twilio tokens, Bandwidth texting) + `/websocket` |
| `fast-api.numinar.com` | `/api/v2/users/`, relational payment |

## Auth

**Auth0** via react-native-auth0, Web Auth Custom Tabs
(redirect `com.numinar.numinar.auth0://auth.numinar.com/.../callback`).
Scope `openid profile email offline_access` (refresh tokens).
`AUTH0_CLIENT_ID`/`AUTH0_AUDIENCE` values are inlined away — **not statically
recoverable**; need runtime capture (frida) or an account. Tokens in Auth0
`SecureCredentialsManager` (Keystore-backed). JWT claims namespaced
`https://numinar.com/roles`, `.../email_verified`.

## Key endpoints (canvassing slice)

`/v1/voters/`, `/v1/nearby-voters`, `/v1/mobile-voter-search`,
`/v1/interactions/batch` (offline sync upload!), `/v1/interactions/callback`,
`/v1/canvassing-qa/tracking`, `/v1/relational-survey/`, `/v1/tags`,
`/v1/my-orgs-mobile`, `/v2/mobile-app/projects/`, `/v1/projects/sse/updates`
(SSE), `/v1/push/tokens/`.

## Location / storage / push

- Mapbox maps (RNMBX), embedded **secret** `sk.eyJ1IjoibnVtaW5hciIs...` token
  shipped client-side; stock styles only. Location foreground-only
  (FINE/COARSE; no background permission, no FGS location).
- Offline: expo-sqlite (schema not recoverable from strings) + AsyncStorage +
  redux-persist; offline interactions queue with retry; 20 MB CursorWindow.
- FCM (3 services: app notifications, Twilio Voice, Intercom) + Expo push
  (`/v1/push/tokens/`) + WebSocket + SSE. No Pusher.
- Sentry `o447951.ingest.sentry.io/4509632503087104`, Intercom `zskx6pd1`,
  EAS project `690023b7-7c29-48ba-a024-2757d50beed2`, channel `production`.
- `usesCleartextTraffic=false`, `allowBackup=false`.

## Signing

Vendor/Play-signed; rebuilds need their own applicationId.

## Hermes v96 recovery options

hbctool rejects v96. To recover exact payload shapes:
1. Build `hbcdump` from facebook/hermes at the v96 tag (heavy but offline), or
2. Runtime capture with frida on a logged-in test account (needs credentials),
   or
3. MITM proxy capture of the real app's canvassing flows (needs account +
   possible cert-pinning bypass via frida).
