# Numinar security & anti-fraud audit — `com.numinar.numinar` v10.0.0

Sources: decompiled Hermes bundle `/tmp/numinar_decompiled_rust.js` (line cites
`L…`), cross-checked against register-level decompilation
`/tmp/numinar_decompiled_p1.js`, JADX output under `numinar/java/sources/`,
manifest `numinar/tree/apktool/AndroidManifest.xml`, and APK assets/libs in
`numinar/tree/` and `numinar/stock/`.

Everything below is code-confirmed unless tagged **UNCONFIRMED**.

---

## 1. Headline summary

- **No root/jailbreak, mock-GPS, debugger, Frida, tamper/signature, or Play
  Integrity checks exist anywhere in the app.** The only "device trust"
  signals are *telemetry*: an emulator flag and location-permission status are
  attached to canvassing submissions and to a dedicated 15-second QA ping.
  Nothing blocks, refuses, or degrades behavior on a rooted/emulated device.
- **The strongest surveillance finding is `/v1/canvassing-qa/tracking`**: while
  logged in, the app POSTs precise GPS + device id + emulator flag + location
  permission status to `fast-api.numinar.com` every **15 seconds**.
- **Sentry session replay is enabled at 100% sample rate with text/image
  masking disabled** — effectively full screen recording of every session,
  shipped to a Sentry project.
- **Adjust (attribution) SDK is initialized with its native request-signing
  library (`libsigner.so`) present** — the only genuine anti-fraud mechanism in
  the binary, and it protects *Adjust's* backend, not Numinar's.
- **No certificate pinning, no network security config.** OTA (expo-updates)
  pulls JS bundles from EAS with no code-signing verification — TLS is the only
  integrity control for executed code updates.

## 2. Environment / anti-tamper detection

### 2.1 Root / jailbreak detection — ABSENT

- Only hit in the bundle is the **expo-device library wrapper**
  `isRootedExperimentalAsync` (L331802–331808, exported L331949–331950).
  Grep for callers finds none — it is dead library code. Cross-checked in the
  p1 decompilation (p1 L951840, L952312): same, definition only.
- No matches anywhere for `jailbreak`, `RootBeer`, `magisk`, `supersu`,
  `superuser`, `jail-monkey` (bundle grep, case-insensitive).
- No root-detection native packages in `numinar/java/sources/` (no
  `scottyab`, `rootbeer`, etc.).

### 2.2 Emulator detection — PRESENT, telemetry-only

- App-level helper `getIsUsingEmulator` (module 1562 area, L230589–230597)
  wraps `react-native-device-info`'s `isEmulator()` (wrapper defs
  L226902/229989–229990; full API surface listed at L229914) and returns
  `false` on error.
- The flag is attached to three outbound flows:
  1. `POST /v1/canvassing-qa/tracking` (§3.1) — L230673 field default
     `is_using_emulator: false`, set at L230689.
  2. `POST /v1/interactions/relational-text` — mutation sets
     `data.is_using_emulator` at L339108 (failure logs "Unable to determine if
     device is using an emulator" and the interaction is **still sent**;
     L339111–339115).
  3. Canvass interactions (single, L383414; bulk household, L383541) — same
     pattern, attached to the interaction object before mutation; failure is
     logged and submission proceeds.
- There is **no behavioral gate**: emulator use changes nothing client-side;
  the server gets the flag for QA/fraud scoring. `useIsEmulator` hooks exist
  only as react-native-device-info library exports (L228843–229906, exported
  L230076).

### 2.3 Mock / fake GPS detection — ABSENT

- Zero matches in the bundle for `isMock`, `MockLocation`,
  `isFromMockProvider`, `mocked`, `mockProvider`, `fake gps` (the only `mock`
  hits are RN animation internals and a jest package name — L60934–61062,
  L214587). Cross-checked in p1: 4 `mock` hits, all animation/test related.
- Native side: `isMock`/`isFromMockProvider` appears only in AndroidX
  `LocationCompat` (compat shim) and Mapbox `LocationServiceUtils` — library
  code, never invoked by app code.
- The app therefore has **no defense against GPS spoofing**; QA relies on
  server-side analysis of the 15 s tracking pings (§3.1) and the
  user-vs-voter address coordinates embedded in each interaction (§3.2).

### 2.4 App tamper / signature integrity — ABSENT

- No signature-digest verification, no installer check at app level.
  `getInstallerPackageName` / `getInstallReferrer` exist only as
  react-native-device-info / expo-application library wrappers (L228133–228195,
  L229945–229946; L222071–222180).
- `MainApplication.onCreate()` (numinar/java/sources/com/numinar/numinar/
  MainApplication.java:85–103) performs no integrity work: Sentry app-start
  metrics, RN load, Twilio voice proxy, **Intercom init**, an Intercom survey
  insets callback, and a CursorWindow 20 MB reflection hack. No Play Integrity,
  no SafetyNet, no attestation calls.
- No matches for `PlayIntegrity`, `SafetyNet`, `DeviceCheck`, `AppAttest`,
  `attestation` in bundle or Java sources.

### 2.5 Debugger / Frida detection — ABSENT

- No matches for `isDebuggerConnected`, `isDebugging`, `frida`. The only
  related hit is RN core's `global.__REMOTEDEV__` check (L250588), which is
  framework plumbing, not anti-debug.

## 3. Canvasser QA / fraud telemetry (server-bound)

### 3.1 `POST /v1/canvassing-qa/tracking` — 15-second GPS beacon

- **Construction**: module 1563 `insertCanvassQATracking` (L230658–230720).
  Request object at L230691:
  `{ method: "POST", url: "/v1/canvassing-qa/tracking", usingFastApi: true, data: _location, orgId, timeout: 10000 }`.
  With the fetch service (§9) this resolves to
  `POST https://fast-api.numinar.com/api/v1/canvassing-qa/tracking`.
- **Body** (L230673, defaults; each filled best-effort — failure of any probe
  is logged and the POST still goes out with the field undefined):
  | field | source |
  |---|---|
  | `project_id` | current project id; `undefined` if none selected (L230711 arg, caller L230996) |
  | `latitude` / `longitude` | one-shot GPS fix, high accuracy, 30 s timeout (L230633–230649, `getCurrentPosition`) |
  | `device_id` | `getDeviceUuid()` — random UUID v4 generated once, persisted in AsyncStorage key `deviceUuid` (L226094–226107); fallback: websocket id |
  | `device_geolocation_enabled` | `react-native-device-info` `isLocationEnabled()` (L230574–230583) |
  | `device_geolocation_permission_status` | `"granted" | "limited" | "blocked" | "denied" | "unavailable"` from FINE/COARSE checks (L230600–230627) |
  | `is_using_emulator` | boolean (L230689) |
- **Headers** (fetch service, L225067–225075): `Content-Type: application/json`,
  `numinar-origin: mobile`, `platform: android`, `x-org-id: <orgId>`,
  `sentry-sid: <sentry session id>`, `Authorization: Bearer <Auth0 access token>`.
- **Trigger / cadence**: a `setInterval(…, 15000)` in the online-sync effect
  (L230988–231024). Fires every 15 s whenever `useUser` data is loaded, an
  Auth0 user is present, and an org id is set — i.e. essentially the whole
  time a logged-in session is open, project selected or not. The same 15 s
  tick also issues `HEAD https://fast-api.numinar.com/api/v1/mobile_204`
  (requiresAuth false, 10 s timeout; defined L230834, invoked L231010) as a
  connectivity probe.
- **Response handling**: none beyond error logging — errors are caught,
  logged ("Error inserting canvassing QA tracking data", L230694), and a
  network-type failure flips redux `connectionState` false (L231004–231015).
  No client-side retry queue; the next 15 s tick is the retry.

### 3.2 Anti-fraud fields embedded in interactions

Every canvass interaction object (single L383351–383378, bulk L383479–383504)
carries both the voter's registered-address coordinates
(`latitude`/`longitude` from `registration_address_*`) **and** the canvasser's
live GPS (`user_latitude`/`user_longitude`, one-shot fix, stringified,
L383399–383406 / L383526–383533), plus `device_id`, `is_using_emulator`,
`device_geolocation_enabled`, `device_geolocation_permission_status`.
`POST /v1/interactions/relational-text` carries `device_id` +
`is_using_emulator` (L339105–339112). These are the fields a server would use
to flag spoofed doorknocks; exact `/v1/interactions/batch` envelope is covered
in the interactions audit — the anti-fraud-relevant additions are confirmed
here.

### 3.3 WebSocket "canvassed" message

On each canvass submission the app also sends over
`wss://rust-server.numinar.com/websocket` (L383426–383434):
`{"action":"sendmessage","data":"<JSON string>"}` where the inner JSON is
`{type:"canvassed", device_id:<websocket id>, voter_id, org_id, project_id, user_id}`.
Sent only when online and a project is selected; failures swallowed.

## 4. Device fingerprinting

- **`deviceUuid`**: app-generated random UUID v4 (uuid module 1372), stored in
  AsyncStorage under `deviceUuid` (L226094–226107). Used as `device_id` in the
  QA beacon, interactions, and set on the Sentry user (§5).
- **react-native-device-info** is bundled with its full API (L229914):
  androidId, serial, IMEI-class ids, install referrer, app-set id, carrier,
  IP/MAC, hardware/build fingerprints, etc. **App-level code only calls
  `isEmulator()` and `isLocationEnabled()`** — no other getters are invoked by
  Numinar code (all other references are internal library wrappers).
- **expo-device** is bundled (`DeviceModule` in
  numinar/java/sources/expo/modules/ExpoModulesPackageList.java); only the
  un-called `isRootedExperimentalAsync` wrapper surfaces in the bundle.
- **Sentry user context** (§5) and **Mixpanel people properties** (§6) add
  identity-level fingerprinting: email, name, app version, role, org.
- No advertising-id usage found in JS; the manifest grants
  `com.google.android.gms.permission.AD_ID` (required by Adjust/Firebase
  libraries; whether Adjust reads the GPS adid depends on play-services-ads
  presence — **UNCONFIRMED** at runtime, no direct JS/Java call found).

## 5. Sentry — crash reporting + 100% unmasked session replay

- **Init**: guarded by `USING_SENTRY = true` (L202392, defined L202377 `c8 = true`),
  executed at module load of the root App module (L394522–394544):
  ```js
  Sentry.init({
    beforeSend: (event) => { event.extra = event.extra || {}; return event; },  // L394523-394534 — no PII scrubbing
    replaysSessionSampleRate: 1,        // 100% of sessions recorded
    replaysOnErrorSampleRate: 1,        // 100% of error sessions
    dsn: "https://95e84220d4cb4014badfe47db424924d@o463956.ingest.sentry.io/5469707",  // L394539
    integrations: [mobileReplayIntegration({ maskAllText: false, maskAllImages: false, maskAllVectors: false })]  // L394541
  })
  ```
  SDK `@sentry/react-native` 7.11.0 (L157320–157326).
- **What leaves the device**:
  - Crash/exception envelopes to `https://o463956.ingest.sentry.io/api/5469707/envelope/`
    (native `libsentry.so` / `libsentry-android.so` in
    split_config.arm64_v8a.apk; JS transport via fetch).
  - **Mobile Session Replay for every session with text, images, and vectors
    UNMASKED** — in a canvassing app whose screens display voter names,
    addresses, and survey answers, replay uploads are the highest-sensitivity
    outbound channel in the app.
  - Native integrations compiled in per manifest meta-data
    `io.sentry.gradle-plugin-integrations` =
    `AppStartInstrumentation,DatabaseInstrumentation,FileIOInstrumentation,LogcatInstrumentation`
    (AndroidManifest.xml L247) — **logcat output is captured into Sentry
    events**. Sentry native auto-init is disabled (`io.sentry.auto-init=false`,
    manifest L114) so config comes from the JS init above.
  - **Previous-session exit reasons**: `reportRecentExitReasons` (L393574–393671)
    runs right after init (L394544). It reads up to 5
    `ApplicationExitInfo` records via the custom native `ExitReasons` module
    (numinar/java/sources/com/numinar/numinar/ExitReasonsModule.java:82–85),
    adds a Sentry breadcrumb `{category:"app.exit", level:"info", message:"<reason>: <description>", data}` per record, and if any of
    `low_memory|crash|crash_native|anr|signaled` occurred while the app was
    foreground (importance ≤ 125), calls `Sentry.captureMessage("Previous
    session ended abnormally: <reason>", {level:"warning", tags:{exit_reason}, extra:{exitReasons}})`
    (L393640–393648). Dedup via AsyncStorage `@exit_reasons_last_reported_timestamp`.
  - **User identity**: on login, `Sentry.setUser({id, email, name:"<first> <last>",
    displayedVersion:"Version 10.0.0", deviceUuid})` (L392972–392981).
  - **expo-updates context** on every event: an integration attaches
    `{is_enabled, is_embedded_launch, is_emergency_launch, is_using_embedded_assets,
    update_id, channel, runtime_version, check_automatically, emergency_launch_reason,
    launch_duration, …}` from expo-updates (L159184–159216).
  - **Correlation header outbound to Numinar**: every API request carries
    `sentry-sid: <Sentry session id>` (L225063–225067), letting the backend
    join API traffic to Sentry sessions.
- Second hardcoded DSN `https://o447951.ingest.sentry.io/api/4509632503087104/envelope/?…&sentry_client=sentry.javascript.browser%2F1.33.7`
  appears inside the SDK's `diagnoseSdkConnectivity()` utility (L150578) — a
  connectivity self-test that POSTs `{}` to that envelope endpoint when (and
  only when) that function is invoked; **no app-level caller found**, so it is
  dormant library code. Note this differs from the DSN in ANALYSIS.md — the
  live app DSN is the o463956 one above.
- Mixpanel errors from Intercom init are reported via `Sentry.captureException`
  on `initIntercom` failure (OrgInvitesScreen effect, L330355–330359).

## 6. Mixpanel — product analytics

- **Init**: lazily on first use (and at App mount, L394583 `initMixpanel()`).
  Module 1455 `MixpanelSingleton` (L221504–221575):
  `new Mixpanel(MIXPANEL_TOKEN, /*trackAutomaticEvents*/ false, /*useNative*/ true)`,
  then `.init()` and `registerSuperProperties({ usingMobile: true })`
  (L221518–221530). Token `a0a85ec57b490e5801b70f516709000d` (L202400).
  Constructor signature confirmed at L220465–220510. Native module
  `MixpanelReactNative` present (L220454), so queueing/flush runs in the
  com.mixpanel.android SDK.
- **Endpoint**: `https://api.mixpanel.com` (L214621; passed explicitly at
  L220623 and L220992). Batching/flush cadence is native-SDK default
  (events queued, flushed periodically/on background); **exact flush interval
  not overridden in code — UNCONFIRMED beyond SDK defaults**.
- **Identity**: on login, `identify(user.id)` (L392983) and
  `people.set({$name, $email, displayedVersion:"Version 10.0.0", $avatar:<profile_url?>, role})`
  (L392984–392995). On logout, `mixpanel.reset()` (useLogOut, L224663).
- **Custom events** (name — properties — trigger):
  - `Logged In` — none — first user-data load after login (L393002, dedup via `lastUserId`)
  - `Signed Up` — none — registration success (L244968)
  - `Switched Org` — org object — org switch (L245344)
  - `App Sent to Background` — {} — AppState change (L231073)
  - `Looked Up Voter` — voter search context — voter search (L386408, L386456)
  - `Surveyed Voter` — `{outreach_type:"relational", voter_id, project_id}` (L360089–360095);
    canvass variant L381033, L385363
  - `Canvass Survey Submitted` — `{org_id:[user.id]}` (L385613, L385632 — note odd property: user's own id in an org_id array)
  - `Marked Voter Unavailable` — `{reason, project_id, voter_id}` (L385653, L385674)
  - `Edited Voter Notes` — `{org_id:[…], voterId, notes:<full note text>, project, voterName:"<first> <last>"}` — **free-text voter notes and voter name go to Mixpanel** (L383379–383395; also L339272, L381318, L386843)
  - `Edited Voter Tag` — tag info (L382099)
  - `Sent Relational Text` — text context (L360303)
  - `Submitted Relational Text Survey` — survey context (L360570)
  - `Opened Notifications from Home` / `Opened Notification Details` (L340942, L340956, L341318)
  - `Viewed Leaderboard` (L389520)
  - `Opened Address in Maps` — address context (L384483, L384495, L387310)
- Voter PII flows to a third-party US analytics processor, keyed by the
  canvasser's identity — a data-governance finding, though not a fraud
  mechanism.

## 7. Adjust — attribution/deep links (the only real anti-fraud component)

- **Init**: inside the `useHandleDeepLinks` effect (app startup),
  L337442–337466:
  ```js
  const adjustConfig = new AdjustConfig(ADJUST_APP_TOKEN, ADJUST_APP_ENV);
  adjustConfig.setLogLevel(AdjustConfig.LogLevelVerbose);        // verbose logging in production
  adjustConfig.setDeferredDeeplinkCallback(cb);                  // resolves deferred deep links
  adjustConfig.enableLinkMe();
  Adjust.initSdk(adjustConfig);
  ```
  Token `idif65k6cl4w`, env `EnvironmentProduction` (L202394–202395).
- **Backend**: `https://app.adjust.com` (numinar/java/sources/com/adjust/sdk/
  Constants.java:15–16) — session, attribution, event, sdk_click traffic;
  `https://gdpr.adjust.com` for GDPR erasure. Adjust sends install/session
  packages with device metadata; attribution results and deferred deep links
  come back into the JS callbacks.
- **Request signing (anti-fraud)**: `libsigner.so` ships in
  split_config.arm64_v8a.apk and is loaded by
  numinar/java/sources/com/adjust/sdk/sig/NativeLibHelper.java:10
  (`System.loadLibrary("signer")`). This is **Adjust Signature V3**: the
  native library signs outgoing Adjust requests so Adjust's servers can reject
  spoofed installs. It protects Adjust's pipeline only; no equivalent exists
  for Numinar's own API.
- **Install referrer**: manifest receiver
  `com.adjust.sdk.AdjustReferrerReceiver` for
  `com.android.vending.INSTALL_REFERRER`, declared with
  `android:permission="android.permission.INSTALL_PACKAGES"`
  (AndroidManifest.xml L121) plus a `SystemLifecycleContentProvider` (L246).
- **Deep-link flow**: `Adjust.processAndResolveDeeplink` rewrites
  `numinar://…` links to `https://mobile.numinar.com/…` and handles
  `/notifications` and org-join links (`?join_org=` or `/join/<code>`,
  L337381–337435). Also listens on `Linking` url events and the initial URL
  (L337452–337468).
- No app-level `AdjustEvent` revenue/event tracking found — only the class
  definition (L201921).

## 8. Intercom — support messenger

- **Native init at process start**:
  numinar/java/sources/com/numinar/numinar/MainApplication.java:88 —
  `IntercomModule.initialize(this, "android_sdk-4b0b73f2a4c08b8f04e03d7c07227fbcfcd25730", "zskx6pd1")`
  (API key + app id hardcoded). Manifest carries Intercom activities,
  `IntercomFcmMessengerService` (L133), `IntercomInitializeContentProvider`
  (L150), and `IntercomFileProvider` (L151).
- **Login/identity**: module 1490 `initIntercom` (L224560–224595), called from
  OrgInvitesScreen when user data loads (L330353–330359):
  1. `Intercom.logout()` (clear prior identity)
  2. `setUserHash(user.hmac)` — **Intercom identity-verification HMAC is
     server-issued in the `/v1/me` profile** (L224577)
  3. `loginUserWithUserAttributes({userId: user.id, email: user.email})` (L224578)
  4. `updateUser({userId, username: email, email, name: "<first> <last>",
     companies: [{id, name}]})` — org name/id attached when provided (L224562–224579)
  5. `sendTokenToIntercom(expoPushToken)` — registers push token with Intercom (L224581)
- **Push**: MainNotificationService (numinar/java/sources/com/numinar/numinar/
  MainNotificationService.java:85–95) routes Intercom pushes via
  `IntercomModule.isIntercomPush` / `handleRemotePushMessage`; unread counts
  drive a local "N unread messages" badge notification (L394489–394503).
- `logoutIntercom()` on sign-out (useLogOut, L224666). No app-level
  `Intercom.logEvent` calls (wrapper only, L221797–221805).
- Intercom traffic goes to Intercom's own hosts (`*.intercom.io` /
  api.intercom.io) from the native SDK — endpoints are inside the closed-source
  AAR, not in JS: **UNCONFIRMED at wire level**.

## 9. Shared API envelope (all Numinar-host calls above)

Module 1398 `useFetchService` (L225017–225128). Base URL selection:
`usingROS ? ROS_URL : FAST_API_URL` — so every `usingFastApi: true` `/v1/…`
call goes to **`https://fast-api.numinar.com/api`** (L225061; constants
L202373–202376). Headers (L225067): `Content-Type: application/json`,
`numinar-origin: mobile`, `platform: android`, `x-org-id: <orgId>`,
`sentry-sid: <sid>`, plus `Authorization: Bearer <Auth0 token>` unless
`requiresAuth:false`. Default timeout 61 s (overridden per call).
Retry policy: axios-retry with `retries: 1`, only when the error message
includes "timeout", `shouldResetTimeout: true` (L225019–225025). On 401: one
`refreshAccessToken()` then a single replayed request with `bearerOverride`;
on refresh failure → logout + "Session Expired" toast (L225090–225119).

## 10. expo-updates OTA

- **Config** (AndroidManifest.xml L74–79): `ENABLED=true`,
  `CHECK_ON_LAUNCH=ALWAYS`, `LAUNCH_WAIT_MS=0` (check in background, apply next
  launch), `EXPO_UPDATE_URL=https://u.expo.dev/690023b7-7c29-48ba-a024-2757d50beed2`,
  runtime version `10.0.0` (res/values/strings.xml:212),
  request header `{"expo-channel-name":"production"}`.
  Same values in embedded `assets/app.config` (sdkVersion 55.0.0,
  `checkAutomatically:"ON_LOAD"`).
- **Code signing NOT configured**: no `expo.modules.updates.CODE_SIGNING_*`
  meta-data anywhere in the manifest. The verification path in
  numinar/java/sources/expo/modules/updates/loader/FileDownloader.java:606–620
  only validates a manifest signature when
  `configuration.getCodeSigningConfiguration() != null`; here it is null, so
  manifests are accepted unsigned (`isVerified=false`). `assets/expo-root.pem`
  (Expo Root Certificate, valid 2022–2042) is bundled as part of the standard
  expo-updates asset set, but with no code-signing metadata it is not used to
  gate updates. **Integrity of OTA JS therefore rests solely on TLS to
  u.expo.dev + EAS project ACLs.** No JS-level `checkForUpdateAsync` /
  `fetchUpdateAsync` / `reloadAsync` calls — updates are purely automatic on
  launch.
- expo-updates native lib `libexpo-updates.so` present; `UpdatesModule`
  registered (ExpoModulesPackageList.java).

## 11. Transport security / cert pinning

- **No SSL/certificate pinning**: no `android:networkSecurityConfig` attribute
  on `<application>` (only `usesCleartextTraffic="false"`,
  `allowBackup="false"`, `extractNativeLibs="false"` — AndroidManifest.xml
  application tag). `res/xml/` contains no network-security-config file.
  okhttp3 `CertificatePinner` exists as library code but no pins are built by
  app code (no non-okhttp `CertificatePinner(` constructions).
- Consequence: standard system-trust TLS everywhere — MITM with a user-installed
  CA is feasible for dynamic analysis; combined with §10, OTA content is
  TLS-only-protected.

## 12. Dormant / leftover analytics

- `assets/appcenter-config.json` with `app_secret
  54ca053f-781f-4fd1-a14d-6897e9cb9129` — **no AppCenter SDK classes exist** in
  the dex (only an R.java string reference). Leftover asset; no traffic.

## 13. Negative results (explicitly swept, not found)

| Check | Result | Evidence |
|---|---|---|
| Root/jailbreak gate | absent | §2.1 |
| Mock-GPS detection | absent | §2.3 |
| Signature/tamper self-check | absent | §2.4 |
| Play Integrity / SafetyNet / App Attest / DeviceCheck | absent | grep bundle+Java, §2.4 |
| Debugger/Frida detection | absent | §2.5 |
| Cert pinning | absent | §11 |
| OTA manifest signature verification | not configured | §10 |
| Behavior gated on emulator/root | none — telemetry only | §2.2 |

## 14. Out-of-scope notes (pointers for other audits)

- Twilio Voice SDK (`libtwilio_voice_android_so.so`, VoiceService) and the
  WebSocket/SSE channels carry their own telemetry — covered by the
  calling/realtime audits.
- `/v1/interactions/batch` envelope shape (L226387, L226487, L359600, L383274)
  is the interactions audit's scope; §3.2 here confirms the anti-fraud fields
  injected into those payloads.
