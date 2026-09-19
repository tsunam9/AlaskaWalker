# Audit: Auth & Session — Numinar `com.numinar.numinar` v10.0.0

Scope: complete Auth0 flow, token request/response shapes, token storage,
Authorization/org headers, host selection (`usingFastApi`), 401/refresh-retry,
post-login bootstrap, sign-out. All line numbers (L…) refer to the primary
decompilation `/tmp/numinar_decompiled_rust.js` unless noted; `p1:` refers to
the register-level cross-check `/tmp/numinar_decompiled_p1.js`.

This file **replaces** the [H] hypotheses in `docs/DESIGN-NUMINAR.md` §1 and
corrects `numinar/ANALYSIS.md` where noted.

---

## 1. Configuration constants (module 1392, L202360–202395)

| Constant | Value | Line |
|---|---|---|
| `AUTH0_DOMAIN` | `auth.numinar.com` | L202372, export L202387 |
| `AUTH0_CLIENT_ID` | `329jKTvPKBUjOSnY9sYnf0m7Z0gkzTTm` | L202373, export L202388 |
| `AUTH0_AUDIENCE` | `https://api.numinar.com` | L202374, export L202389 |
| `FAST_API_URL` | `https://fast-api.numinar.com/api` | L202375, export L202390 |
| `ROS_WS_URL` | `wss://rust-server.numinar.com/websocket` | L202376, export L202391 |
| `ROS_URL` | `https://rust-server.numinar.com` | L202377, export L202392 |
| `VERSION` | `Version 10.0.0` | L202384 |

**Correction to ANALYSIS.md:** `AUTH0_CLIENT_ID`/`AUTH0_AUDIENCE` are *not*
"inlined away / not statically recoverable" — they are plain string
assignments in module 1392 (L202372–202374). Also, `mobile.numinar.com` is
**never** an API host in the JS bundle; its only occurrence is a deep-link
rewrite (`numinar://` → `https://mobile.numinar.com/`, L337400). All REST
traffic goes to `fast-api.numinar.com/api` or `rust-server.numinar.com` (§6).

react-native-auth0 SDK version: **5.11.0** (L212590).

---

## 2. Auth0 login flows (app module 1556 `useAuth0Login`, L224694–224967)

The app implements **four** sign-in paths. Three go through the SDK's native
Web Auth; the email magic-code path is hand-rolled with raw `fetch` against
Auth0. All request the scope `openid profile email offline_access` (refresh
tokens) and audience `https://api.numinar.com`.

### 2.1 Email magic code — step 1: `POST /passwordless/start` (L224752–224786)

- **Trigger:** user submits their email on the magic-code screen
  (`sendMagicCode`, consumed at L391801).
- **Method/URL:** `POST https://auth.numinar.com/passwordless/start` (URL built
  L224768).
- **Headers:** `Content-Type: application/json` (L224762). No auth header.
- **Body** (L224765–224767):
  ```json
  {
    "client_id": "329jKTvPKBUjOSnY9sYnf0m7Z0gkzTTm",
    "connection": "email",
    "email": "<user email>",
    "send": "code",
    "authParams": {
      "scope": "openid profile email offline_access",
      "audience": "https://api.numinar.com",
      "redirect_uri": "numinar://auth"
    }
  }
  ```
- **Response handling:** `response.ok` → sets `isMagicCodeSent = true`
  (L224772). Non-OK → reads Auth0 error body (`error_description` ?? `error`,
  helper `readAuth0Error` L224711–224728) and throws
  `Error(<desc> ?? "Failed to send magic code.")`.

### 2.2 Email magic code — step 2: `POST /oauth/token` (OTP grant) (L224790–224838)

- **Trigger:** user submits the 6-digit code (`authenticateOTP(otp, username)`,
  consumed at L391967–392000).
- **Method/URL:** `POST https://auth.numinar.com/oauth/token` (L224805).
- **Headers:** `Content-Type: application/json`.
- **Body** (L224804):
  ```json
  {
    "grant_type": "http://auth0.com/oauth/grant-type/passwordless/otp",
    "client_id": "329jKTvPKBUjOSnY9sYnf0m7Z0gkzTTm",
    "username": "<user email>",
    "otp": "<code>",
    "realm": "email",
    "audience": "https://api.numinar.com",
    "scope": "openid profile email offline_access"
  }
  ```
- **Response handling (L224808–224821):** on OK, parses JSON and dispatches
  `authStore.setCredentials` with fields mapped from the Auth0 token response:
  `access_token → accessToken`, `refresh_token → refreshToken`,
  `id_token → idToken`, `scope → scope`, `token_type → tokenType`, plus a
  computed `expiresAt = floor(Date.now()/1000) + Number(expires_in ?? 0)`.
  (The redux slice only persists the three tokens; see §4.) Non-OK → throws
  `Error(<auth0 error> ?? "Invalid or expired code.")`.
- The react-native-auth0 SDK has the same grant built in
  (`passwordless/otp`, realm `email`/`sms`, L213074–213108) but the app does
  **not** use the SDK for this — it posts directly with `fetch`.
  Other SDK grants present but unused by app code: `password-realm` (L212979),
  `mfa-otp` (L213124–213133), `mfa-oob` (L213149–213158),
  `mfa-recovery-code` (L213174–213183).

### 2.3 Google sign-in — SDK Web Auth (L224841–224860)

- **Trigger:** "Continue with Google" button on `LoginScreen` (`handleGoogleLogin`,
  L391615–391617).
- Calls `useAuth0().authorize({ connection: "google-oauth2", scope: "openid
  profile email offline_access", audience: AUTH0_AUDIENCE,
  additionalParameters: { prompt: "login select_account" } })` (L224846–224848).
- This goes to the SDK native bridge `A0Auth0.webAuth` (L211680–211710), which
  opens a Custom Tab on `https://auth.numinar.com/authorize?...` with PKCE
  (code challenge/verifier generated **in native code**, not visible in the JS
  bundle — the exact authorize query string is therefore UNCONFIRMED beyond
  the parameters the JS passes). The SDK's `authorizeUrl` builder
  (L212886–212896) shows the parameters are sent as query params with
  `client_id` + `redirect_uri` added.
- **Redirect:** scheme `com.numinar.numinar.auth0`, host `auth.numinar.com`,
  path `/android/com.numinar.numinar/callback`
  (`numinar/tree/apktool/AndroidManifest.xml:173–179`,
  `com.auth0.android.provider.RedirectActivity`). The SDK also has a
  `numinar://auth` redirect registered in the passwordless flow (§2.1).
- **Response handling:** SDK exchanges the code at `POST /oauth/token`
  (`grant_type=authorization_code`, `code_verifier`, `redirect_uri`,
  L212927–212935), returns `Credentials`; the provider wrapper saves them into
  the Auth0 `CredentialsManager` (Keystore-backed, L214040–214060) **and** the
  app dispatches `authStore.setCredentials(credentials)` (L224853).

### 2.4 Email + password login — SDK Web Auth, Universal Login (L224905–224935)

- **Trigger:** "Continue with Email" (password) button on `LoginScreen`
  (`loginWithUsernamePassword`).
- `authorize({ scope, audience, additionalParameters: { prompt: "login" } })`
  (L224917–224920) — i.e. Universal Login in a Custom Tab; no `connection`
  hint. Result handled identically to §2.3; throws `Error("No credentials")`
  if the SDK returns nothing.

### 2.5 Sign-up — SDK Web Auth (L224937–224966)

- `authorize({ scope, audience, additionalParameters: { prompt: "login",
  screen_hint: "signup" } })` (L224949). Same handling as §2.3.

### 2.6 Token response shape (all flows)

Auth0 returns the standard token set; the app consumes: `access_token`
(JWT, audience `https://api.numinar.com`), `refresh_token` (rotation enabled —
a new refresh token may be returned, see §3), `id_token` (JWT, decoded for the
user profile), `scope`, `token_type` (`Bearer`), `expires_in` (seconds).
Custom namespaced claims observed in code: `https://numinar.com/roles`
(array; `[0] === "admin"` gates admin UI, L352506) and
`https://numinar.com/email_verified` (boolean; gates the VerifyEmail screen,
constant at L393486, checked at L392505–392512 via `jwtDecode(accessToken)`).

---

## 3. Refresh-token exchange (module 1556 `refreshAccessToken`, L224863–224902)

- **Trigger:** (a) any API call that returns 401 (§7); (b) the WebSocket
  component when the stored access token is expired (`isTokenExpired`,
  L338218–338230 → `refreshAccessToken()` at L338080–338086); (c) app-start
  bootstrap when a stored refresh token exists (§8.2).
- **Method/URL:** `POST https://auth.numinar.com/oauth/token` (L224878) —
  raw `fetch`, not the SDK.
- **Headers:** `Content-Type: application/json`.
- **Body** (L224877):
  ```json
  { "grant_type": "refresh_token",
    "client_id": "329jKTvPKBUjOSnY9sYnf0m7Z0gkzTTm",
    "refresh_token": "<stored refresh token>" }
  ```
  The refresh token is read from a ref mirroring `auth.auth.refreshToken`
  (L224746–224748).
- **Single-flight:** an in-flight refresh promise is cached module-locally and
  returned to concurrent callers; cleared to null on completion/failure
  (L224874–224899; confirmed at register level p1:649700–649860,
  `_closure1_slot8`).
- **Response handling:**
  - OK + `access_token` present → dispatch `setTokensAfterRefresh({
    accessToken, refreshToken })` and **return the new access token**
    (L224884–224890). If Auth0 omits `refresh_token` the old one is kept
    (bootstrap variant, L392787–392800; p1:661770–661819).
  - OK but no `access_token` → throw `Error("No new access token returned.")`.
  - Non-OK → throw `Error(<auth0 error> ?? "Unable to refresh session.")`.
  - Network/throw → logs `Auth0 token refresh failed:` and **returns null**
    (p1:649810+ catch path).

No leeway/expiry margin is applied when refreshing; the bootstrap expiry check
compares `exp * 1000` to `Date.now()` directly (L392760–392775).

---

## 4. Token storage (modules 1488/1489, AsyncStorage — NOT SecureStore)

**There is no expo-secure-store usage anywhere in the bundle** (no
`SecureStore`/`secure-store` references). Tokens live in two places:

1. **AsyncStorage** (`@react-native-async-storage/async-storage`, module 1359
   wrapping module 1360, L199878–199894) under plain-text keys
   (module 1489, L221577–221586):
   - `"access_token"` (`AUTH_ACCESS_TOKEN`)
   - `"id_token"` (`AUTH_ID_TOKEN`)
   - `"refresh_token"` (`AUTH_REFRESH_TOKEN`)
   - `"auth_session_migrated"` (`AUTH_SESSION_MIGRATED`, set to `"true"`)
   Writes happen in the auth slice (module 1488, L221591–221675) via
   `persist()` (fire-and-forget `AsyncStorage.setItem`, errors only logged,
   L221602–221608). `setCredentials` persists all three tokens + the migration
   flag (L221615–221622); `setTokensAfterRefresh` persists access token and,
   if present, the rotated refresh token (L221652–221660). AsyncStorage on
   Android is an **unencrypted SQLite database** in the app sandbox — the
   refresh token is recoverable from any process with file access (root,
   backup abuse — though `allowBackup=false` per ANALYSIS.md).
2. **Auth0 `CredentialsManager`** (react-native-auth0 native,
   Keystore-backed): written by the SDK provider only for the Web-Auth flows
   (Google/password/signup, L214040–214060). The OTP flow never writes here.
   It is read once at startup for **legacy session migration** (§8.2).

Redux slice `auth` (module 1488): `{ auth0User, idToken, accessToken,
refreshToken }` in memory (L221636–221675). **No redux-persist** — the string
appears nowhere in the bundle; persistence is entirely the manual AsyncStorage
writes above (corrects ANALYSIS.md "redux-persist").

---

## 5. Fetch service — headers & envelope (module 1398 `useFetchService`, L224969–225167)

HTTP client: axios instance (`axios.create()`, module 1400, instantiated
L225016) wrapped with axios-retry (module 1402): `retries: 1`,
`retryCondition: error.message includes "timeout"`,
`shouldResetTimeout: true` (L225019–225025). Default per-request timeout
**61 000 ms**, overridable per request (L225053–225058).

`backendFetch(request)` builds (L225036–225080):

- **URL:** `(usingROS ? ROS_URL : FAST_API_URL) + url` (L225060). See §6.
- **Method:** `request.method ?? "get"` (L225038–225042).
- **Headers** (L225067–225074):
  | Header | Value |
  |---|---|
  | `Content-Type` | `application/json` |
  | `numinar-origin` | `mobile` |
  | `platform` | `android` |
  | `x-org-id` | `request.orgId ?? <orgId from OrgContext>` (fallback confirmed p1:580250–580330) |
  | `sentry-sid` | `Sentry.getCurrentScope().getSession()?.sid` (undefined if no session) |
  | `Authorization` | `Bearer <token>` — only when `requiresAuth !== false` **and** a token exists. Token = `request.bearerOverride ?? auth.auth.accessToken` from redux (L225028–225031, L225068–225074). |
- **Body:** `request.data` as-is (JSON-serialized by axios). **Query params:**
  `request.params`.
- `makeApiRequest` (L225128–225165) is a redux-thunk wrapper around
  `backendFetch` that dispatches `onStart`/`onSuccess`/`onError` action types
  and shows a toast `"Server Error:" + message` on failure (L225153–225158).

---

## 6. Host selection — the `usingFastApi` flag is DEAD

Every API request in the bundle sets `usingFastApi: true` (e.g. L226387,
L230752, L231418), but the request builder **never reads it** — it only reads
`usingROS` (L225043–225047; confirmed at register level p1:580278–580330:
`usingROS ? ROS_URL : FAST_API_URL`, no reference to `usingFastApi`). The flag
is passed through `makeApiRequest` (L225137) and ignored. Effective routing:

| Flag | Base URL | Used for |
|---|---|---|
| default (`usingROS` unset/false) | `https://fast-api.numinar.com/api` | everything: `/v1/me`, `/v1/my-orgs-mobile`, `/v1/interactions/batch`, `/v1/push/tokens`, `/v3/projects`, `/v2/...` etc. |
| `usingROS: true` (passed as `ros:` via makeApiRequest) | `https://rust-server.numinar.com` | `/api/v3/...` Twilio/Bandwidth/outreach (L339336, L381089, L381139, L383749, L383772) |

`https://api.numinar.com` (AUTH0_AUDIENCE) appears **only** as the JWT
audience — no fetch targets it. `https://mobile.numinar.com` appears only in
a deep-link rewrite (L337400). So the effective API prefix for e.g. the batch
upload is `POST https://fast-api.numinar.com/api/v1/interactions/batch`.

The WebSocket uses a third transport (§9): `wss://rust-server.numinar.com/websocket`.

---

## 7. 401 handling & refresh-retry (module 1398, L225084–225120)

On a rejected request where `axios.isAxiosError` and `response.status === 401`:

1. If `response.data.detail === "You need to verify your email to access this
   resource"` → rethrow immediately; **no refresh attempted** (L225096–225099).
   (This drives the VerifyEmail gate; resend via §8.4.)
2. Else if a refresh token exists (`ref.current`):
   a. `await refreshAccessToken()` (§3).
   b. **Success (token returned):** retry the original request **exactly once**
      with `bearerOverride = <new access token>` (L225102–225106). The retry
      bypasses the redux value so the fresh token is used immediately.
   c. **Refresh failed (null) but a refresh token still exists:** `await
      useLogOut()` (full sign-out, §10) + toast
      `{ type: "error", text1: "Session Expired", text2: "Please log in
      again.", topOffset: 48 }`, then rethrow (L225107–225110).
   d. No refresh token → rethrow.
3. Non-401 errors rethrow unchanged (and axios-retry may have already retried
   once on timeout, L225019–225025).

This matches the design doc's "401 → one refresh → terminal signed-out"
contract exactly.

---

## 8. Session bootstrap after login / on app start (module 1589 `AppRouter`, L392405–393520)

### 8.1 Startup token restore — `initializeAppToken` (L392750–392845)

Runs once on mount (guarded by an `isLoading`-style flag; deps include
`getCredentials`, L392750). Order of operations:

1. Read `access_token` and `refresh_token` from AsyncStorage (L392756–392758).
2. If access token: `jwtDecode` it; if `exp` is in the future, dispatch
   `setTokensAfterRefresh({ accessToken, refreshToken })` to rehydrate redux
   (L392760–392780). Decode errors are only logged.
3. If refresh token: POST the refresh grant (§3 body, L392787–392795). On OK
   with `access_token`, dispatch `setTokensAfterRefresh` (keeping the old
   refresh token if the response omits one, L392796–392802;
   p1:661770–661819). **On network error:** if a stored access token exists,
   dispatch it anyway (offline-tolerant start, L392815–392822) and continue.
4. **Legacy migration:** if `auth_session_migrated` is unset, call Auth0
   `getCredentials()` (SDK CredentialsManager / Keystore); if it yields both
   `accessToken` and `idToken`, dispatch `setCredentials` to copy them into
   AsyncStorage (which also sets the migration flag) (L392826–392838;
   register-level confirmation p1:661470–661560). Failure logged as
   `legacy session migration failed:` and ignored.
5. Any top-level error logged as `existing token error:`; the loading flag is
   always cleared.

### 8.2 Profile fetch — `GET /userinfo` (L392697–392745)

- **Trigger:** whenever `auth.auth.accessToken` changes (effect deps
  `[accessToken, dispatch]`).
- **Method/URL:** `GET https://auth.numinar.com/userinfo` (L392706).
- **Headers:** `Authorization: Bearer <accessToken>` (L392708). AbortController
  cancels on cleanup.
- **Response handling:** JSON dispatched as `setAuth0User(json)` (L392712).
  **On failure:** fall back to reading `id_token` from AsyncStorage and
  `jwtDecode` it into `setAuth0User` (L392720–392735); errors logged.

### 8.3 Post-login bootstrap calls (all to fast-api via `backendFetch`, §5 headers)

| Call | Trigger | Caching/notes | Lines |
|---|---|---|---|
| `GET /v1/me` | react-query `useUser`, enabled when `auth0User` set; also refetched by NetworkManagerComp | `staleTime: Infinity`; result cached to AsyncStorage key `"me"`; offline fallback reads cache | L230731–230780, L392515 |
| `GET /v1/my-orgs-mobile` | `useOrganizations`, enabled once `/v1/me` loaded | results sorted by name, cached to AsyncStorage `"orgs"`; offline fallback | L231402–231448 |
| `GET /v2/orgs/{orgId}` | `useOrganization`, enabled when org context set | cached to AsyncStorage `"org"`; drives Mixpanel group props | L231455–231500, L392560–392660 |
| `GET /v1/public-orgs` | `usePublicOrgs` (org-join flow) | react-query | L231287 |
| `POST /v1/push/tokens` body `{ expo_push_token, is_android: true, device_push_token }` | after user+org loaded and nav ready (`registerForPushNotificationsAsync` → Expo token + FCM device token) | mutation; duplicates possible (called in two `.then` branches, L393037, L393098) | L332045–332060, L393020–393100 |
| org selection | if exactly 1 usable org → `setOrgId` + persist `last_org_selected`; else restore last selection | `last_org_selected` in AsyncStorage (L245283–245296, L393487–393500) | L392940–392965 |
| `POST /v1/orgs/{orgId}/join` | deep-link org join during bootstrap (`useJoinPublicOrg`) | mutation | L231309 |

On org switch (`useSwitchOrg`, L245300–245350): react-query caches cleared
(except `user`/`organizations`/`orgs`), redux slices cleared (`_clearVoters`,
`_clearProjects`, `_clearSearch`, `_clearSurveys`, `_clearContacts`,
`_clearCall`, `_clearCanvass`), `last_org_selected` updated, Mixpanel
`Switched Org` tracked.

### 8.4 Email verification

- The `email_verified` gate decodes the **access token** claim
  `https://numinar.com/email_verified` (L392505–392512, constant L393486).
- Resend: `POST /v1/verification-email` (empty body, standard headers)
  — user-tapped with a client-side countdown (L337594–337610,
  countdown L337620+).
- 401s carrying the verify-email `detail` string bypass refresh (§7).

---

## 9. WebSocket session (module 1371 `createWs` L202420–202470; module 2671 `Websocket` L338044–338230)

- **URL:** `wss://rust-server.numinar.com/websocket?token=<accessToken>
  &first_name=<enc>&last_name=<enc>&email=<enc>&org_name=<enc>&org_id=<id>
  &platform=mobile` (L202442). **The access token is sent as a query
  parameter** (visible in logs/proxies).
- **Trigger:** effect in `Websocket` component when user, org, connection and
  `reopenWebsocket` state align (L338070–338090). Before connecting, if
  `isTokenExpired(accessToken)` (jwtDecode `exp` check, L338218–338230) it
  calls `refreshAccessToken()` (§3) and uses the fresh token.
- **Keepalive:** client sends literal `"ping"` every **30 000 ms**
  (`setInterval`, L202450–202460).
- Incoming non-`"ping"` messages are double-JSON-parsed (`JSON.parse(
  JSON.parse(msg.data).data)`) and drive `canvassed` invalidations
  (L338092–338130). Outgoing canvass events are also sent over this socket
  (`action: "sendmessage"`, `type: "canvassed"`, L230880–230900).

---

## 10. Sign-out (`useLogOut`, module 1405, L224654–224692)

- **Trigger:** user action (settings) **or** the 401/refresh-failure path (§7).
- **No server round-trip for logout.** The SDK's `webAuth.clearSession`
  (which would hit `GET /v2/logout`, builder at L212908–212916, native bridge
  L211713–211745, provider wrapper L214095–214120) is **never called by app
  code** — the Auth0 browser session cookie survives sign-out.
  `revokeRefreshToken` (`POST /oauth/revoke`, L213223–213228) is likewise
  never called — **the refresh token is not revoked server-side on logout.**
- What is wiped, in order (L224676–224690):
  1. `dispatch(auth.logout())` → redux auth slice reset +
     `AsyncStorage.removeItem` for `access_token`, `id_token`,
     `refresh_token` (L221625–221635). (`auth_session_migrated` is **not**
     removed.)
  2. Org context `setOrgId("")`.
  3. Mixpanel `reset()`.
  4. `logoutIntercom()` (twice — called once fire-and-forget and once more,
     L224683–224686).
  5. `setActiveAnnouncementUser(null)` (native `AnnouncementStore`).
  6. `clearCredentials()` — Auth0 CredentialsManager/Keystore wipe
     (errors only logged: `"Failed to clear Auth0 keychain:"`).
  7. `AsyncStorage.multiRemove(["lastUserId", "me", "orgs", "org"])`
     (L224689). Note: `last_org_selected` and the push-token rows are **not**
     removed here.
  8. react-query `queryClient.clear()`.
- The offline SQLite interaction queue and canvass DB are not wiped by this
  function (no DB calls in module 1405) — residual voter data may persist on
  device across accounts. UNCONFIRMED whether another code path purges SQLite
  on account switch.

---

## 11. Liveness / connectivity checks (client-side behaviors)

| Check | What | Cadence/trigger | Lines |
|---|---|---|---|
| Online check | `HEAD /v1/mobile_204`, `requiresAuth: false` (no Authorization header), timeout 10 s | every **15 s** while NetworkManagerComp mounted; also re-run 1.5 s after a successful offline-sync flush | L230834, L230976–231010, L230963–230971 |
| Canvasser QA ping | `POST /v1/canvassing-qa/tracking`, body = current GPS location object, timeout 10 s | same 15 s interval, only when user + orgId present | L230691, L230984–230990 |
| Offline interaction flush | `POST /v1/interactions/batch` in chunks of 10 | on reconnect (websocketUp && online && !isSyncing) | L230851–230960 |
| WS keepalive | `"ping"` over WebSocket | every 30 s | L202450–202460 |

---

## 12. Security-relevant observations (audit notes)

1. **Refresh token in unencrypted AsyncStorage** (§4) — no SecureStore/
   Keystore for the app's primary token copy.
2. **No server-side logout / token revocation** (§10) — stolen refresh tokens
   remain valid after "sign out"; Auth0 SSO session persists in the browser.
3. **Access token in WebSocket query string** (§9) — logged by any TLS-
   terminating intermediary.
4. `expiresAt` computed at OTP login (L224815–224818) is **never persisted or
   enforced**; freshness decisions rely solely on JWT `exp` decode and 401s.
5. 401 refresh-retry is unbounded across requests (each 401 triggers one
   refresh + one retry) but the refresh itself is single-flighted (§3, §7).
6. Auth0 client_id is public (native app, no client secret) — standard for
   public clients, but note the passwordless OTP grant can be exercised by
   anyone with the client_id (§2.1–2.2).

## UNCONFIRMED items

- Exact `/authorize` query string for Web-Auth flows (PKCE parameters are
  generated in native `A0Auth0` code, not in the JS bundle) — §2.3.
- Whether the Auth0 tenant has refresh-token **rotation** enforced: the code
  tolerates both (keeps old token if none returned, §3), so tenant behavior
  is not determinable statically.
- Whether any code path purges the expo-sqlite canvass/voter DB on logout —
  none found in `useLogOut` (§10).
- `response.data.detail` verify-email string is a fast-api convention; other
  401 body shapes are not special-cased.
