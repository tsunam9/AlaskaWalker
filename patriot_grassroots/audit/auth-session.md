# Audit: Auth & Session — `com.patriotgrassroots.validnation` v1.0.0 (114)

Scope: every server-bound message in the auth/session domain — login, refresh,
profile, logout, websocket one-time token — plus token storage, bearer
attachment, refresh scheduling, 401/retry policy, and CapacitorHttp native
behavior. Primary evidence: recovered frontend source in `/tmp/vn_src/`
(cited relative to that root, e.g. `composables/auth/useAuth.ts:89`);
native evidence in `patriot_grassroots/java/sources/...` and
`patriot_grassroots/tree/assets/...`.

Caveat: the generated `client/types.gen.ts` (hey-api type definitions) was NOT
recovered from the source maps, so exact TS type names (`CreateAuthTokenResponse`,
`GetProfileResponse`, `SessionData`, `BannerAlerts`, …) are known but their full
field lists are not. Everything below is grounded in fields the code actually
reads/writes; fields the server may send but the app never touches are marked
UNCONFIRMED.

Backends (plaintext runtime config, `tree/assets/public/index.html`):
`apiBaseURL: "https://api.validnation.ai"`, `wsBaseURL: "wss://api.validnation.ai/api/ws"`,
Supabase `https://tfnnpqpvdjisoizvciyr.supabase.co` with publishable key
`sb_publishable_xeO1bd3QP8IbXsKvFBW27g_OLjQU62U`.

---

## 1. POST /api/auth/token — login

SDK ground truth: `client/sdk.gen.ts:436-449` (`createAuthToken`), serializer
`urlSearchParamsBodySerializer`, header `Content-Type: application/x-www-form-urlencoded`,
NO `security` block (unauthenticated). Docstring: "Get a JWT access token by
username and password".

Actual shipped mobile path does NOT use the SDK function. `signIn()`
(`composables/auth/useAuth.ts:67-114`) posts via `doWebRequest()` (ofetch
`$fetch`) with config endpoint `POST /api/auth/token` (`config/auth.ts:7`) and
`body: credentials`. The login page builds the body as multipart FormData
(`pages/login.vue:98-100`):

```
body = new FormData()
body.append('username', values.email)      // validated z.string().email()
body.append('password', values.password)   // trimmed non-empty string
```

Confirms DESIGN-VALIDNATION.md line 45 ([R]): OAuth2-style form fields
`username`/`password`, NOT JSON. On the wire in the Android app this goes out
as `multipart/form-data` (the CapacitorHttp fetch patch strips a boundary-less
`Content-Type` so the native layer sets one: `tree/assets/native-bridge.js:473-479`);
FastAPI's OAuth2 form parser accepts it. The generated client would instead send
`application/x-www-form-urlencoded` — both encodings carry the same two fields.

Trigger: user taps "Log In" on `/login` (`pages/login.vue:92-118`). Guarded by
`isSigningIn` ref (no double-submit). No retry on failure; error toast
"Authorization error" (`pages/login.vue:113-115`).

Response fields consumed (`useAuth.ts:89-90`):
- `access_token` → `setToken()`
- `refresh_token` → `setRefreshToken()`

Any other fields (e.g. `token_type`, `expires_in`) are ignored → UNCONFIRMED.

Post-login side effects: `getSession()` (profile fetch, §3), then
`ensureDeviceLinked()` + `requestAndRegisterPushNotifications()` on native
(`pages/login.vue:108`, `120-124`), offline prefetch, navigate to
`callbackUrl` (`getSafeRedirectUrl(route)`).

Failure/offline: `doWebRequest` (`utils/authRequestHandlers.ts:37-60`) — on
network-connectivity error sets the offline flag and returns `undefined`;
signIn then logs "signIn returned non-object value" and shows
"Failed to sign in." Non-200 responses throw `createError` with
`data.detail || error.message` as the message shown in the toast.

## 2. POST /api/auth/refresh — **resolves [H]** (DESIGN-VALIDNATION.md line 47)

SDK: `client/sdk.gen.ts:420-433` (`refreshAuthToken`),
`Content-Type: application/json`, NO `security` block (no bearer attached).

Exact request (single implementation, `composables/auth/useAuth.ts:228-240`):

```
POST {apiBase}/api/auth/refresh
Content-Type: application/json          (added by doMobileRequest, authRequestHandlers.ts:11)
Authorization: (none)

{ "refresh_token": "<raw refresh JWT or null>" }
```

Native transport: `CapacitorHttp.request` via `doMobileRequest`
(`utils/authRequestHandlers.ts:5-35`) with `connectTimeout: 5000`,
`readTimeout: 5000` ms. Web: `$fetch` with same JSON body.

Response fields consumed (`useAuth.ts:241-246`):
- `access_token` → `setToken()`; `lastRefreshedAt = new Date()`
- **The refresh token is NOT rotated client-side** — `setRefreshToken` is never
  called in `_doRefresh`. If the server returns a new `refresh_token` it is
  silently ignored (field presence UNCONFIRMED, ignored either way).

After a successful refresh, `getSession()` is fired (profile refetch,
`useAuth.ts:252-256`); its failure is swallowed ("token preserved").

Concurrency: all refreshes funnel through `singleFlightRefresh`
(`composables/auth/refreshSingleFlight.ts:54-62`) — concurrent callers share one
in-flight POST; returns `undefined` immediately while a sign-out is in progress.

Failure behavior: non-200 → throw with `data.detail || data.message`. Network
error → offline flag set, `undefined` returned, token left unchanged
(`useAuth.ts:241-244`). 401 handling of refresh itself lives in the callers (§6).

## 3. GET /api/auth/profile — session/profile fetch

SDK: `client/sdk.gen.ts:403-418` (`getAuthProfile`), GET, bearer security.
Config endpoint: `config/auth.ts:9`. Implementation: `getSession()`
(`useAuth.ts:178-226`).

Request:

```
GET {apiBase}/api/auth/profile
Authorization: Bearer <access JWT>
```

Native: `doMobileRequest` (5 s connect/read timeouts). Success is strictly
`status === 200` — any other 2xx is treated as error
(`utils/authRequestHandlers.ts:22-27`).

Triggers:
- App start: if an access token exists in storage → `getSession()`; if only a
  refresh token exists → `refresh()` (which then calls getSession)
  (`plugins/auth.ts:17-32`).
- After every successful login (`useAuth.ts:94-96`) and every successful
  refresh (`useAuth.ts:252-256`).
- `useRefreshAccountAndRedirect()` after account-editing flows
  (`composables/useRefreshAccountAndRedirect.ts:7-11`).
- NO periodic poll of profile exists.

Response fields consumed (type `GetProfileResponse` ≈ `SessionData`; full shape
UNCONFIRMED, consumed fields confirmed):
- `token.user` — object with `id`, `email`, `first_name`, `last_name`, `role`
  (`composables/useUserRole.ts:9-10`, `composables/useSentryContext.ts:9-14`,
  `utils/manualCaptureErrorToSentry.ts:5-11`). `role` compared against
  `'canvasser' | 'subcontractor_canvasser' | 'manager' | 'admin'`
  (`useUserRole.ts:12-19`). Note the profile embeds a token-shaped object
  mirroring the JWT payload; when profile data is absent the app decodes the
  access JWT itself for the same `user` claim (`useUserRole.ts:7-9`, type
  `AuthTokenData` — full claim list UNCONFIRMED).
- `alerts` — object; `alerts.banner_alert` drives the destructive banner in
  `components/accountProblemNotifier/AccountProblemNotifier.vue:19-23` via
  `useUserRole.ts:20` (`accountProblems`). Known `banner_alert` values (type
  `BannerAlerts`, `constants/accountProblems.ts:4-50`):
  `create_application`, `provide_documents`, `fill_w9_form`,
  `record_voice_sample`, `provide_payment_info`, `provide_profile_info`.
  Unknown values fall back to a generic title (`accountProblems.ts:57-62`).
- `settings.time_zone` — fallback timezone (`useUserRole.ts:21-25`).
- `profile_picture_url` — avatar (`useUserRole.ts:30`); per a comment it is an
  ephemeral presigned URL re-issued on every refetch
  (`components/account/profile/ProfileEditForm.vue:151`).

Org/project assignments: NOT read from this endpoint anywhere in the recovered
source. Project lists come from separate `/api/projects...` queries. The DESIGN
claim that profile carries org/project assignments is UNCONFIRMED — no consumer
found (grep for `assigned_project`, `organization`, `.token.projects` across
`/tmp/vn_src` returns nothing outside unrelated admin endpoints).

Consumed response stored as `data.value` (global session state,
`composables/auth/useAuthState.ts:115`).

Failure: 401 → `data = null`, `clearToken()` (access only; refresh token kept —
`useAuth.ts:207-210`). Any other error (network, 5xx) → session and token
preserved, error logged (`useAuth.ts:211-214`).

## 4. POST /api/auth/logout

SDK: `client/sdk.gen.ts:382-401` (`logout`), POST,
`Content-Type: application/json`, bearer security. Docstring: "Logout the user
by removing the refresh token".

Exact request (`useAuth.ts:137-162`):

```
POST {apiBase}/api/auth/logout
Authorization: Bearer <access JWT>      (captured before tokens are cleared)
Content-Type: application/json

{ "refresh_token": "<raw refresh JWT or null>" }
```

Trigger: user logout (`composables/useLogout.ts:8-18`) or forced sign-out from
401 cascades (§6). UI-level guards: blocked while offline
(`useAuth.ts:117-120`, toast only) and blocked while a shift is tracking or
shift data is unsynced (`useLogout.ts:6-15`).

Full sequence in `signOut()` (`useAuth.ts:116-176`):
1. `setSigningOut(true)` — blocks new refreshes; `drainPendingRefresh()` lets an
   in-flight refresh settle.
2. `unlinkIfNative()` (`utils/mobile/unlinkDeviceFromUser.ts:7-29`): deletes the
   FCM token, then `POST /api/mobile/device/unlink` `{device_id}` (device-audit
   scope), resets cached device link.
3. `useMobile()?.stop()` — stops tracking/audio.
4. **Tokens and session cleared BEFORE the API call** (`useAuth.ts:146-148`) to
   prevent refresh races; the `Authorization` header was snapshotted earlier.
5. POST logout. Response body unused (type `AuthLogoutResponse`; fields
   UNCONFIRMED). Errors swallowed (logged only) — local logout is unconditional.
6. `setSigningOut(false)`, redirect `/login`, `cacheClear()`.

Offline behavior: no-op with offline toast when `servingOffline`; the 401-driven
paths clear tokens locally WITHOUT calling this endpoint when the backend
already rejected the token (`config/AuthRefreshHandler.ts:174-180`).

## 5. GET /api/auth/ws_token — websocket one-time token

SDK: `client/sdk.gen.ts:451-466` (`createAuthOneTimeToken`), GET, bearer
security. Docstring: "Get a JWT access token by username and password for
websocket only". No request body/params.

Sole caller: `composables/useVoiceVerification.ts:135-149`. Fetched each time a
signatory voice-verification websocket session is started (and again on each
reconnect, because the `reconnectAttempts` watcher re-runs
`onStartVerification`, lines 46-48, 85-133). Response field consumed:
`access_token` (line 136); other fields UNCONFIRMED/ignored.

Usage: query param on the WS upgrade, NOT an HTTP header:

```
wss://api.validnation.ai/api/ws/voice_verification/{verification_id}
  ?token={access_token}
  &sample_rate={audio_config.sample_rate}      // device-reported, fallback 48000 (line 119)
  &bits_per_sample={audio_config.bits_per_sample}
  &channels={audio_config.channels}
  &encoding={audio_config.encoding}
```

(`useVoiceVerification.ts:137-148`; audio config from `utils/createAudioConfig.ts`.)
The websocket itself is a plain browser `WebSocket` (`composables/useSocket.ts:17`) —
no auth headers possible, hence the one-time token. Reconnect policy: max 3
attempts, fixed 5 s delay with a visible countdown (`useSocket.ts:8,42-66`).

This is the ONLY use of `/api/auth/ws_token` in the app — it is not used for
any general-purpose `/api/ws` channel (none exists client-side).

## 6. Token storage (`@aparajita/capacitor-secure-storage`)

Web: cookies `auth.token` (maxAge 900 s) and `auth.refresh-token`
(maxAge 1,296,000 s = 15 d), SameSite=Lax, NOT Secure, NOT HttpOnly
(`config/auth.ts:12-25`, `useAuthState.ts:30-46`). The 900 s figure from
ANALYSIS.md/DESIGN is this cookie maxAge — on native it is unused; native
scheduling reads the JWT `exp` claim directly (§7). The actual server-side JWT
lifetime is UNCONFIRMED from code (client trusts `exp`).

Native: `SecureStorage.set/remove/get` under the same keys `'auth.token'` /
`'auth.refresh-token'` (`composables/auth/useAuthState.ts:56-104`), mirrored in
memory in `useState` refs. Writes are fire-and-forget (no await). Hydration
happens once, before any auth logic, in the auth plugin
(`plugins/auth.ts:6-9`); hydration failure clears both tokens
(`useAuthState.ts:99-103`). `KeychainAccess.afterFirstUnlock`
(`useAuthState.ts:7`) is an iOS-only parameter, ignored on Android.

Native implementation (decompiled,
`java/sources/com/aparajita/capacitor/securestorage/SecureStorage.java:29-73`):
per-key AES key in `AndroidKeyStore`, cipher `AES/GCM/NoPadding`, ciphertext +
IV (Base64, separated by \x10) stored in plain SharedPreferences file
`WSSecureStorageSharedPreferences`. I.e. Keystore-backed encryption, not
`EncryptedSharedPreferences`. Design note: DESIGN-VALIDNATION.md line 52-53
(EncryptedSharedPreferences) is equivalent in strength.

## 7. Bearer attachment — which headers, which hosts

Three request stacks, all attaching the SAME ValidNation JWT:

1. **hey-api generated client** (all `sdk.gen` endpoints, incl. profile,
   logout, ws_token when called via SDK): `client.setConfig` in `app.vue:40-73`.
   `auth` callback = `authPreRequest` (`composables/auth/httpInterceptors.ts:50-69`)
   returns the raw JWT (no prefix); the generated core wraps it as
   `Authorization: Bearer <jwt>` (`client/core/auth.gen.ts:33-35`). Only
   endpoints with a `security: [{scheme:'bearer'}]` block get the header —
   `/api/auth/token` and `/api/auth/refresh` have none (`sdk.gen.ts:424-433,439-449`).
   baseURL = `apiBaseURL` → host `api.validnation.ai` only.
2. **Native mobile requests** (`doNativeRequest`, `utils/mobile/doNativeRequest.ts:55-67`;
   and `doMobileRequest` for auth endpoints): header `Authorization: Bearer <jwt>`
   added when a token exists; `Content-Type: application/json` on non-GET.
   Timeouts 15 s (doNativeRequest) / 5 s (doMobileRequest). Same host.
3. **Supabase** (`plugins/supabase.ts:65-164`): custom `global.fetch` sets
   `Authorization: Bearer <validnation JWT>` on every request to
   `tfnnpqpvdjisoizvciyr.supabase.co` (PostgREST `db.schema: 'private'` +
   Realtime). supabase-js additionally sends its `apikey: sb_publishable_...`
   header automatically. So Supabase calls carry BOTH the publishable anon key
   and the app's own JWT as bearer — the RLS backend must validate the
   ValidNation JWT. Realtime socket auth via `supabase.realtime.setAuth(rawToken)`
   on init and on every token change (`supabase.ts:164,215-223`).

FCM/Sentry/Maps are keyed, not bearer — out of scope.

## 8. Refresh scheduling — proactive, exact cadence

**Resolves DESIGN-VALIDNATION.md line 54 ("80% TTL (720 s)") — that was the
rewrite plan, not stock behavior.** Stock refreshes **60 s before JWT `exp`**
(≈93% of a 900 s TTL):

- Proactive timer: `CustomRefreshHandler` (`config/AuthRefreshHandler.ts:82-103`)
  armed with `proactiveLeadTimeMs: 60_000` (`plugins/auth.ts:35-39`). Delay =
  `exp*1000 − now − 60000`, clamped ≥0; computed from the JWT itself
  (`config/authRefreshSchedule.ts:24-35`, `utils/authTokenExpiry.ts:25-34`).
  Re-armed by a watcher on every token change (login/refresh/logout)
  (`AuthRefreshHandler.ts:51-58`). Not scheduled when access or refresh token
  missing, access JWT unparseable, or refresh JWT already expired.
  Failure: logged, not re-armed — the other paths take over.
- `visibilitychange` → visible: ALWAYS calls `refresh()` when a valid refresh
  token exists (`AuthRefreshHandler.ts:124-194`). If the refresh token is
  missing/expired, tracking is stopped, tokens cleared, and (on protected
  pages) redirect to `/login?redirect_url=...`. 401 from this refresh → local
  cleanup only, no logout POST. Window-`focus` handler exists but is commented
  out (`AuthRefreshHandler.ts:48,64`).
- Route middleware: on every navigation to an auth-gated page, if access token
  expired but refresh token present → `refresh()` before proceeding
  (`middleware/01.auth.global.ts:49-63`).
- Pre-request expiry check: before any hey-api request, if `exp` is within a
  30 s clock-skew buffer (`PRE_REQUEST_EXPIRY_BUFFER_MS = 30_000`,
  `httpInterceptors.ts:34,58-67`), refresh first; if a refresh is already in
  flight, await it instead of racing.
- App start: refresh if only refresh token survives (`plugins/auth.ts:21-22`).

## 9. 401 handling & retry budgets

Three parallel mechanisms, all "refresh once, replay once, then sign out":

1. **hey-api/`$fetch` path** — `authOnResponse` (`httpInterceptors.ts:110-132`,
   wired `app.vue:49-69`): 401 → (skip if user-sign-out in progress) →
   `refresh()` → replay original request once with the new bearer. Second 401
   (online, not signing out) → toast "Session expired. Please log in again.",
   `queryCache.cancelQueries()`, `signOut({callbackUrl: /login?redirect_url=...})`.
   Module-level `_signingOut` flag prevents cascading multi-sign-outs.
2. **Native `doNativeRequest` path** (`utils/mobile/doNativeRequest.ts:102-128`):
   requests are short-circuited pre-flight when the session is unrecoverable
   (no access AND no refresh token — `utils/authSessionGuard.ts:14-18`).
   401 → `refresh()` → retry once. If the retried/refresh attempt fails with
   401 or 403: sign-out ONLY if the app is foregrounded
   (`App.getState().isActive`, lines 116-124); in background the request fails
   silently (code comment acknowledges possible shift-data loss).
3. **Supabase path** (`plugins/supabase.ts:104-118,17-51`): 401 →
   `checkAccessToken()` (refresh if refresh-token exists) → replay once with
   new bearer. Refresh 401 or missing refresh token → `handleSessionExpired()`
   → toast + cancelQueries + signOut (skipped while offline).

Login and ws_token have no retry. WebSocket reconnect budget: 3 × 5 s (§5).

## 10. CapacitorHttp native behavior

`CapacitorHttp.enabled: true` (`tree/assets/capacitor.config.json`); direct
calls use `CapacitorHttp.request` and all WebView `fetch` calls are monkey-
patched to the native bridge (`tree/assets/native-bridge.js:470-529`):

- Non-GET methods → native `CapacitorHttp` plugin (HttpURLConnection, not
  OkHttp — `java/sources/com/getcapacitor/plugin/util/HttpRequestHandler.java:389-390`).
- GET/HEAD/OPTIONS/TRACE → routed through a local proxy URL
  (`CapacitorWebFetch`, native-bridge.js:484-507) — still native HTTP under the
  hood, plus the `x-cap-user-agent` workaround: a JS-supplied `User-Agent` is
  copied to `x-cap-user-agent` so the WebView doesn't strip it
  (native-bridge.js:493-499), and the native layer copies it back to
  `User-Agent` (`HttpRequestHandler.java:381-385`).
- Native layer adds NO auth or tracking headers of its own. It would set
  `User-Agent` from `overrideUserAgent` config, but this build defines none →
  the put is a null no-op (`HttpRequestHandler.java:386-388`,
  `CapConfig.java:478-480`, vs `capacitor.config.json`).
- FormData bodies with boundary-less `Content-Type` have the header deleted
  JS-side so the native layer generates the multipart boundary
  (native-bridge.js:473-479).
- No certificate pinning anywhere (only the unrelated OkHttp
  `CertificatePinner` class from another dependency); TLS validation is the
  platform default (`HttpRequestHandler.java:391` domain-exclusion check is
  stock Capacitor).

## 11. Resolved / still-open items

Resolved [H] / hypotheses:
- **POST /api/auth/refresh exact shape [H]** → JSON `{refresh_token}`, no auth
  header, response `access_token` only consumed, no client-side refresh-token
  rotation (§2).
- Login form encoding → FormData `username`/`password` confirmed (§1).
- Logout body → JSON `{refresh_token}` + Bearer, tokens cleared locally first (§4).
- Proactive refresh cadence → 60 s before JWT `exp` (not "80% TTL") (§8).
- Supabase bearer → same ValidNation JWT, plus publishable `apikey` (§7).

Still UNCONFIRMED (not recoverable from code):
- Full server response shapes for token/refresh/logout/ws_token (extra fields
  ignored by the client).
- Actual JWT `exp` lifetime issued by the server (client-side cookie config
  says 900 s; scheduling trusts the token's `exp`).
- Refresh-token server-side lifetime (cookie config says 15 d).
- Whether profile response contains org/project assignment data the app
  ignores (no consumer found).
- `AuthTokenData` JWT claim list beyond `user{id,email,first_name,last_name,role}`.
