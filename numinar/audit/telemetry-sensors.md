# Audit: Location telemetry & sensors — `com.numinar.numinar` v10.0.0

Scope: GPS breadcrumbs, `/v1/canvassing-qa/tracking`, location acquisition, geofencing,
WiFi/Bluetooth/audio/motion/battery/device-info collection.

Sources: `/tmp/numinar_decompiled_rust.js` ("rust", line cites `L…`) and
`/tmp/numinar_decompiled_p1.js` ("p1", register-level, cites `p1:L…`), cross-checked
against `numinar/tree/apktool/AndroidManifest.xml`. Everything below is code-confirmed
unless marked **UNCONFIRMED**.

---

## 1. `POST /v1/canvassing-qa/tracking` — canvasser GPS QA ping (primary finding)

### 1.1 Wire format

- **Method/path**: `POST /v1/canvassing-qa/tracking` (rust L230691; p1:L651198).
- **Full URL**: `https://fast-api.numinar.com/api/v1/canvassing-qa/tracking`
  (`FAST_API_URL = "https://fast-api.numinar.com/api"`, L202375/L202390; URL assembled as
  `(usingROS ? ROS_URL : FAST_API_URL) + url`, L225060; request sets `usingFastApi: true`).
- **Request descriptor**: `{ method: "POST", url: "/v1/canvassing-qa/tracking",
  usingFastApi: true, data: <payload>, orgId: <orgId>, timeout: 10000 }` (L230691).
- **Headers** (built in `useFetchService`, module 1398, L225049–225078):
  - `Content-Type: application/json`
  - `numinar-origin: mobile`
  - `platform: android`
  - `x-org-id: <orgId>` (request-level `orgId` overrides the org-context value)
  - `sentry-sid: <Sentry session id>` (from `Sentry.getCurrentScope().getSession().sid`,
    omitted when no session)
  - `Authorization: Bearer <Auth0 access token>` (added unless `requiresAuth: false`;
    this request requires auth)
- **Timeout**: 10,000 ms (per-request; default would be 61,000 ms, L225049).
- **Retry**: the shared axios instance is wrapped with axios-retry
  `{ retries: 1, retryCondition: message includes "timeout", shouldResetTimeout: true }`
  (L225017–225024). A `401` response triggers one Auth0 token refresh + replay, then a
  "Session Expired" toast and throw (L225075–225100).
- **Response handling**: none — the resolved value is discarded (`await arg1(request)`,
  L230693). On failure the error is logged (`"Error inserting canvassing QA tracking
  data"`) and rethrown to the caller (L230694–230697).

### 1.2 Payload — every field

Constructed in module 1563 `insertCanvassQATracking` (L230656–230720; p1:L650990–651240
confirms identical structure, incl. `data = r5`, `orgId = r4` at p1:L651198–651202):

```json
{
  "project_id": "<currentProject.id | absent>",
  "latitude":  <number | absent>,
  "longitude": <number | absent>,
  "device_id": "<uuid v4 | absent>",
  "device_geolocation_enabled": <boolean | absent>,
  "device_geolocation_permission_status": "<granted|limited|blocked|denied|unavailable | absent>",
  "is_using_emulator": <boolean>          // initialized false
}
```

Field provenance (each in its own try/catch, so partial payloads are possible and
`undefined` values are dropped by JSON serialization):

| Field | Source | Cite |
|---|---|---|
| `project_id` | `projects.currentProject.id`; `undefined` when no project selected (ping still fires) | L230673; caller L230960–230966; p1:L544576–544595 |
| `latitude`/`longitude` | fresh one-shot GPS fix (see §2); set only if truthy | L230675–230683; p1:L651038–651075 |
| `device_id` | `getDeviceUuid()`: uuid v4 generated once, persisted in AsyncStorage key `"deviceUuid"`; fallback = websocket id on storage error | L226092–226110, export L226278 |
| `device_geolocation_enabled` | react-native-device-info `isLocationEnabled()` (OS location toggle); `false` on error | module 1564, L230575–230586 |
| `device_geolocation_permission_status` | react-native-permissions `check()`: FINE granted → `"granted"`; else COARSE granted → `"limited"`; else `blocked`/`denied`/`unavailable` | L230600–230632 |
| `is_using_emulator` | react-native-device-info `isEmulator()`; default `false` | L230587–230598 |

### 1.3 Trigger / cadence

- Sent by `NetworkManagerComp` (module 1351, L230801–231093), which is mounted once at
  the App root next to the router (`<NetworkManagerComp.default />`, L394601).
- A `setInterval(..., 15000)` — **every 15 seconds** — runs the "online-check task"
  (rust L230982–231020; p1:L544657–544660 confirms `setInterval(task, 15000)`).
- Gates (all must be truthy): user profile loaded (`useUser().data`), Auth0 user present
  (`auth.auth0User`), and `orgId` set (rust L230987–230992; p1:L544556–544570:
  closure slots 8, 7, 1). **No project is required** — `project_id` is just `undefined`.
- The interval lives as long as the component is mounted. RN JS timers do not run while
  the app is backgrounded on Android, so in practice this is a **foreground-only**
  breadcrumb stream (no background execution facility exists — see §7).
- On success: if `connectionState` was false it is set true. On error: logged as
  `"Online-check task error:"`; `connectionState` is set `false` unless the error message
  contains `"credential"` (p1:L544610–544630; rust L231003–231017).
- The same 15 s task also issues `HEAD /v1/mobile_204`
  (`requiresAuth: false, timeout: 10000`, L230834) as a connectivity probe. The two
  decompilations disagree on exact control flow: rust shows the HEAD request running
  unconditionally after the QA send; p1 shows it running only when a QA-send gate is
  unmet (p1:L544566–544580 vs. success path L544596–544609). **UNCONFIRMED** which is
  exact; either way the QA ping itself doubles as the connectivity proof.

There is **no batching** for this endpoint: one POST per 15 s tick, one GPS fix per POST.

---

## 2. Location acquisition (client side)

- The app **does not use expo-location** (no module/strings; only a Google-places library
  warning mentioning it, L243149). All app-level GPS goes through
  **react-native-get-location** (`RNGetLocation`, module 1580) via wrapper module 1579
  (L230508–230560).
- Wrapper behavior (L230525–230548): merges caller options over defaults
  `{ enableHighAccuracy: false, timeout: 60000 }`, then **requests the runtime permission
  first** — FINE when `enableHighAccuracy`, else COARSE, with the supplied rationale —
  throwing `LocationError("UNAUTHORIZED")` if denied (module 1581, L230474–230499).
- `getLocationAsync()` (module 1564, L230631–230651) — used by the QA ping and the
  canvass submissions — calls `getCurrentPosition` with
  `{ enableHighAccuracy: true, timeout: 30000,
     rationale: { title: "Location permission",
                  message: "Numinar needs permission to request your location.",
                  buttonPositive: "Ok" } }`.
  On any error it logs `"Unable to determine valid current location"` and returns `{}`
  (ping then goes out without coordinates). **No `watchPosition`, no subscription, no
  continuous tracking anywhere** (zero hits for `watchPosition`/`requestLocationUpdates`).
- Only four modules import the location wrapper: the QA helper (1564), `MapScreen`
  (L387471), `EmptyMap` (L387089), `HomeScreen` (L340788).

### One-shot GPS call sites (all `enableHighAccuracy: true, timeout: 30000`)

| Screen | When | What happens to the fix | Cite |
|---|---|---|---|
| `MapScreen` (canvass map) | once on mount | stored in state → map camera + `useNearbyVoters` (§3) | L387763–387776 |
| `EmptyMap` | once on mount | sets local map region only (latDelta 0.0922/lngDelta 0.0421); nothing transmitted | L387111–387149 |
| `HomeScreen` | once, after first screen transition | result **discarded** (only `.catch`) — permission warm-up | L340863–340876 |

---

## 3. `GET /v1/nearby-voters` — device GPS sent as query params

- Hook `useNearbyVoters(latitude, longitude)` (module 3348, L387420–387454):
  `GET /v1/nearby-voters` with `params = { latitude, longitude }`, `usingFastApi: true`,
  same headers as §1.1 (`x-org-id` etc.), default 61 s timeout.
- react-query: `queryKey: ["nearby-voters"]`, `staleTime: 600000` (10 min), `enabled`
  only when lat & lng are non-null **and** `canvass.nearbyCanvassingActive` is true
  (L387541–387548).
- Coordinates come from the one-shot mount-time fix in `MapScreen` (§2). `refetch()` is
  triggered when the project id or nearby-mode flag changes while a fix exists
  (L387553–387560).

---

## 4. GPS inside canvass interactions (`/v1/interactions/batch` items)

The interaction pipeline is another audit scope, but the **location fields** are in
scope. Both submit paths capture a fresh fix via `getLocationAsync()` at submission
time (module 3310):

- `useCanvass` (single, L383314–383450) and `useBulkCanvass` (bulk, L383455–383560)
  build interaction objects with:
  - `latitude` / `longitude` = **voter's registration address** (from the voter record,
    not GPS) — L383355, L383500
  - `user_latitude` / `user_longitude` = **canvasser's live GPS as decimal strings**
    (`.toString()`), initialized `null` — L383358–383359 → L383406–383409;
    L383507–383508 → L383530–383533
  - `device_id` (same AsyncStorage uuid), `is_using_emulator`,
    `device_geolocation_enabled`, `device_geolocation_permission_status` —
    L383412–383417, L383536–383541
  - plus `created_at` (ISO timestamp), disposition, ids, etc.
- These items go to `POST /v1/interactions/batch` (offline-buffered; L226387/L226487)
  — wire details left to the interactions audit.
- Relational-text interactions (`POST /v1/interactions/relational-text`) add only
  `device_id` + `is_using_emulator`, **no GPS** (L339096–339120).
- Call/notes/tag/survey interaction payloads: no `user_latitude`/`user_longitude`
  occurrences outside the two canvass paths (grep L383358–383533 only).

---

## 5. WebSocket (rust-server) — no location

- Connect: `wss://rust-server.numinar.com/websocket?token=<auth0 token>&first_name=…&
  last_name=…&email=…&org_name=…&org_id=<id>&platform=mobile` (L202428–202445).
- Keepalive: literal `"ping"` every 30 s (L202453).
- Only application messages sent: `{ action: "sendmessage", data: JSON.stringify({
  type: "canvassed", device_id: <websocketId>, voter_id, org_id, project_id, user_id }) }`
  on canvass submit / offline-sync replay (L230887–230896, L383426–383430). **No
  coordinates ever sent over the socket.**

---

## 6. Geofencing

- **None.** No geofencing API exists in the bundle (no expo-location task manager, no
  `startGeofencingAsync`, no native geofence service in the manifest).
- `geofence_name` (L339720–339779, L339942) is only a **project metadata string**
  displayed in project UI ("name • county • geofence_name • precinct") — not a client
  geofence.

---

## 7. Background location

- **Not possible / not implemented**: manifest declares `ACCESS_FINE_LOCATION` and
  `ACCESS_COARSE_LOCATION` only — **no `ACCESS_BACKGROUND_LOCATION`**, no location-type
  foreground service (only `android:foregroundServiceType="microphone"` on Twilio's
  `VoiceService`), and no background-task API usage in JS. All location use is
  foreground one-shot fixes plus the 15 s JS interval (§1.3).

---

## 8. Other sensors — negative findings (swept, code-confirmed absent)

| Sensor | Finding | Evidence |
|---|---|---|
| **WiFi scan results (SSID/BSSID)** | Not collected. No scan APIs, no ssid/bssid strings in app code. Manifest has only `ACCESS_WIFI_STATE` (library boilerplate); no `NEARBY_WIFI_DEVICES` | grep `SSID|BSSID|getScanResults` → no app hits; manifest |
| **Bluetooth / BLE scans** | Not collected. Only react-native-device-info's headphone-connection helpers exist (no app callers). Manifest: legacy `BLUETOOTH` (maxSdk 30) + `BLUETOOTH_CONNECT` (Twilio audio routing); **no `BLUETOOTH_SCAN`** | L226888, L229726; manifest |
| **Audio / voice recording** | `RECORD_AUDIO` requested **only** for Twilio VoIP calls: `CallControlsModal.requestMicPermission`, rationale `"Numinar needs access to your microphone to make calls"` (L380220). expo-audio's `useAudioRecorder` is present as **dead library export** — zero app callers (L379436–379453). The `startRecording` hits at L144997+ are Sentry **Session Replay** internals, not audio. Mic FGS = `com.twiliovoicereactnative.VoiceService` (manifest) | L380216–380235; manifest |
| **Motion / accelerometer / gyroscope / pedometer** | Not collected. Zero expo-sensors/DeviceMotion/Pedometer modules; no `ACTIVITY_RECOGNITION` permission. The Mapbox `LocationPuck` (`puckBearing: "heading"`, L387934) and `UserLocation` puck (L387164) use the compass **inside the native Mapbox SDK** for rendering only | grep sweeps; manifest |
| **Battery level / power state** | Not collected. `useBatteryLevel`/`getBatteryLevel` etc. exist only inside the react-native-device-info library wrapper; no app-code callers | L226822–226856, L229914 |
| **Device model / OS / hardware ids** | App code itself only uses DeviceInfo's `isLocationEnabled`, `isEmulator` (§1.2). `getModel`/`getSystemVersion`/etc. have **no app callers**. Third-party SDKs (Sentry `o447951.ingest.sentry.io/4509632503087104`, Intercom, Mixpanel, Adjust) attach standard device context automatically — payloads are SDK-controlled, **UNCONFIRMED** in detail; they go to those vendors, not Numinar. Numinar's own API receives only the `platform: android` header | L229914; L225055 |

---

## 9. Mapbox (third party)

- Secret access token `sk.eyJ1IjoibnVtaW5hciIs…` shipped in the bundle (L202388) and set
  at App mount (`Mapbox.setAccessToken(MAPBOX_ACCESS_TOKEN)`, L394574).
- `Mapbox.setTelemetryEnabled` is exported by the RNMBX wrapper (L168198) but **never
  called** → Mapbox native telemetry remains at SDK default (enabled). Mapbox telemetry
  (which can include location events) goes to Mapbox, not Numinar; exact behavior is
  native-SDK-level — **UNCONFIRMED**.

---

## 10. Summary of what leaves the device (location/sensor data)

| Destination | What | Cadence/trigger |
|---|---|---|
| `fast-api.numinar.com/api/v1/canvassing-qa/tracking` | GPS lat/lng, project_id, persistent device uuid, location-enabled flag, location-permission status, emulator flag | every 15 s while logged in w/ org (foreground) |
| `fast-api.numinar.com/api/v1/interactions/batch` | GPS as `user_latitude`/`user_longitude` + same device/geo flags, per canvass interaction | on doorknock submit (offline-queued) |
| `fast-api.numinar.com/api/v1/nearby-voters` | GPS lat/lng as query params | when nearby-canvassing mode active, ≤1/10 min |
| `wss://rust-server.numinar.com/websocket` | identity in URL query (name/email/org), canvassed pings (no GPS) | connect + 30 s ping |
| Mapbox / Sentry / Intercom / Mixpanel / Adjust | native SDK telemetry incl. device context (Mapbox may include location) | SDK-controlled, UNCONFIRMED |
