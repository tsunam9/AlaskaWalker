# Sensors & telemetry — `com.patriotgrassroots.validnation` v1.0.0 (114)

Audit date: 2026-09-19. Sources: recovered frontend source `/tmp/vn_src/` (paths
below are relative to it), decompiled Java `patriot_grassroots/java/sources/`
(paths relative to project root). Every claim cites file:line; unverifiable
items are marked **UNCONFIRMED**.

Pipeline in one paragraph: while a shift is tracking, per-sensor modules buffer
readings and write **batch records** into a SQLite `payloads` outbox table. A
single uploader drains the outbox by type and posts arrays of records to
`POST /api/mobile/sensor/batch_upload`, deleting rows only after HTTP 200.
Sensor records are never posted directly from the trackers — every sensor byte
goes through the outbox.

---

## 1. `POST /api/mobile/sensor/batch_upload` — the sensor upload

Client definition: `client/sdk.gen.ts:1497-1516` ("Batch Upload Sensor Data",
bearer security). The app does **not** use the generated client for this call;
it builds the request by hand in `mutations/mobile/uploadSensors.ts:5-13`:

- **Method/path**: `POST {apiBase}/api/mobile/sensor/batch_upload`
  (`apiBase` = `https://api.validnation.ai`, runtime config).
- **Headers**: `Content-Type: application/json` (uploadSensors.ts:9),
  `Authorization: Bearer <jwt>` added by `doNativeRequest`
  (`utils/mobile/doNativeRequest.ts:59-63`; Bearer prefix composed at
  `composables/auth/useAuthState.ts:108`). Transport is `CapacitorHttp`
  (native HTTP), `connectTimeout: 15000`, `readTimeout: 15000`
  (doNativeRequest.ts:64-65).
- **Body**: `{"records": [<record>, ...]}` — note the wrapper key `records`
  (uploadSensors.ts:10). Each `<record>` is one batch envelope (§2). Up to
  `UploaderBatchSize` (default 100, `types/database/config.ts:21`) records per
  request, all of the **same** `sensor_type` (the outbox is drained per type,
  `composables/mobile/useUploader.ts:102-110`).
- **Trigger**: uploader tick (§5). Records are pulled from the outbox by
  `getAllByType(type, UploaderBatchSize, maxId)` (useUploader.ts:103,
  `utils/useDb.ts:202-216`).
- **Response consumed**: **none**. `doNativeRequest` returns the body only on
  HTTP **200 exactly** (doNativeRequest.ts:78-83); any other status throws
  (lines 85-89). `flushType` only awaits the promise and deletes rows on
  success (useUploader.ts:110-112). Response body schema is **UNCONFIRMED**
  (never read; the generated type file `client/types.gen.ts` was not present
  in the recovered source, only its imports in sdk.gen.ts:4).
- **Failure/offline behavior**: any throw (non-200, timeout, no connectivity)
  → rows are **kept** in the outbox and retried at the next tick
  (useUploader.ts:114-118). There is no retry counter and no poison-record
  drop for sensor types (only `wake_word_event` rows are dropped on 400/404,
  useUploader.ts:91-98). Non-network errors are reported to Sentry
  (useUploader.ts:116). On HTTP 401 the layer refreshes the JWT once and
  retries the request once (doNativeRequest.ts:102-128).
- **Auth edge case**: if the session is unrecoverable the request short-
  circuits with a synthetic 401 before any network I/O (doNativeRequest.ts:48-50),
  and the whole tick is skipped while logged out (useUploader.ts:159-162).
- Deprecated sibling: `POST /api/mobile/sensor/` ("Upload Sensor Data",
  `@deprecated`, sdk.gen.ts:1475-1495) exists in the API but is **never
  called** by the app.

## 2. Batch record envelope (all sensor types)

Constructed identically in all four trackers
(`composables/mobile/trackers/useMobileLocationTracking.ts:90-98`,
`useMobileWifiScan.ts:34-42`, `useMobileBleScan.ts:60-68`,
`useMobileMotionTracking.ts:105-113`):

```json
{
  "record_id": "<uuid v4>",           // per batch; generated at first enqueue
  "work_shift_id": "<uuid>",          // current shift, from module ctor arg
  "device_id": "<udid>",              // capacitor-udid, stores/mobile/deviceInfo.ts:55
  "sensor_type": "gps|wifi|ble|accelerometer|gyroscope|magnetometer|motionActivity",
  "started_at": <see below>,
  "ended_at": <see below>,
  "sensor_readings": [ ... ]          // schema per sensor_type, §3
}
```

- `sensor_type` values are the exact strings in `types/mobile/trackingSensors.ts:1-9`.
- **`started_at`/`ended_at` types differ by sensor** (important for fixtures):
  - `gps`: epoch **milliseconds, number** — first/last reading's `timestamp`
    (useMobileLocationTracking.ts:95-96).
  - `accelerometer`/`gyroscope`/`magnetometer`: epoch **milliseconds, number** —
    `t_start`/`t_end` of first/last reading (useMobileMotionTracking.ts:110-111).
  - `motionActivity`: epoch **milliseconds, number** — `timestamp` of first/last
    event (same lines; `eventStartTs` falls back to `timestamp`, lines 39-46).
  - `wifi` and `ble`: **ISO-8601 strings** (`new Date().toISOString()`) bracketing
    the scan burst (useMobileWifiScan.ts:23,27; useMobileBleScan.ts:44,53).
- One DB row = one record; the whole envelope is JSON-serialized into the
  `payloads.payload` column (`utils/useDb.ts:53-59`).

## 3. Reading schemas per `sensor_type`

### 3.1 `gps`

`LocationReading` interface, `composables/mobile/trackers/useMobileLocationTracking.ts:21-32`;
fields populated at lines 63-74:

```json
{
  "latitude": 0.0,               // degrees
  "longitude": 0.0,              // degrees
  "accuracy": 0.0,               // meters
  "timestamp": 0,                // epoch ms; Android Location.getTime(), fallback Date.now()
  "altitude": 0.0,               // meters | null
  "altitude_accuracy": 0.0,      // meters | null (verticalAccuracyMeters)
  "speed": 0.0,                  // m/s | null (only if Location.hasSpeed())
  "bearing": 0.0,                // degrees | null (only if Location.hasBearing())
  "simulated": false,            // see below
  "connection_type": "wifi"      // "wifi"|"cellular"|"none"|"unknown" — @capacitor/network ConnectionType
}
```

- **`simulated` source (resolves the open question)**: it is **not** computed by
  app code. The `@capacitor-community/background-geolocation` plugin sets it
  natively to Android `Location.isFromMockProvider()` —
  `patriot_grassroots/java/sources/com/equimaps/capacitor_background_geolocation/BackgroundGeolocation.java:89`
  (`jSObject.put("simulated", location.isFromMockProvider())`), passed through
  verbatim at useMobileLocationTracking.ts:72. Note: API 31+ deprecated
  `isFromMockProvider()` in favor of `Location.isMock()`; the shipped plugin
  uses the legacy call, which the OS still aliases.
- **`connection_type`**: sampled from `@capacitor/network` at tracker start and
  kept current via a `networkStatusChange` listener
  (useMobileLocationTracking.ts:161-165). It is a per-reading field and IS
  uploaded — this contradicts `patriot_grassroots/ANALYSIS.md:74` ("radio state
  is sent NOWHERE"): network *connection type* rides along with every GPS fix.
- The same fix is also forwarded live to the native audio manager
  (`AudioManager.updateLocation`, useMobileLocationTracking.ts:142-146) — this
  is the GPS used for restricted-area audio decisions, separate from upload.

### 3.2 `wifi`

One record per scan burst; `sensor_readings` is the raw `WifiEntry[]` returned
by `@codext/capacitor-wifi` `Wifi.scanWifi()` (useMobileWifiScan.ts:25-41).
Entry shape, native source of truth
`patriot_grassroots/java/sources/com/lindsor/capacitor/wifi/WifiEntry.java:17-39`:

```json
{
  "bssid": "aa:bb:cc:dd:ee:ff",   // ScanResult.BSSID
  "ssid": "MyAP",                 // empty SSID serialized as "[HIDDEN_SSID]" (WifiEntry.java:10,22-26)
  "level": -55,                   // RSSI dBm, ScanResult.level (default -1)
  "isCurrentWifi": false,         // bssid == connected WifiInfo.BSSID (Wifi.java:244-255)
  "capabilities": ["WPA2-PSK-CCMP", "RSN-PSK-CCMP", "ESS"]
                                  // ScanResult.capabilities string split on "][",
                                  // brackets stripped (Wifi.java:69-87)
}
```

Scan mechanics: `WifiManager.startScan()` then broadcast
`SCAN_RESULTS_AVAILABLE_ACTION`; on either fresh or stale results it returns
`getScanResults()` (Wifi.java:261-283). Deprecated-throttled `startScan` on
modern Android means bursts can return cached results.

### 3.3 `ble`

One record per scan burst; `sensor_readings` is the raw `ScanResult[]` from
`@capacitor-community/bluetooth-le` `BleClient.requestLEScan({allowDuplicates:
true})` (useMobileBleScan.ts:23-31, 60-68). Entry shape, native source of truth
`patriot_grassroots/java/sources/com/capacitorjs/community/plugins/bluetoothle/BluetoothLe.java:357-414`:

```json
{
  "device": {                     // BluetoothLe.java:126-143
    "deviceId": "AA:BB:CC:DD:EE:FF",  // BluetoothDevice.getAddress()
    "name": "...",                    // optional, only if device.getName() != null
    "uuids": ["..."]                  // optional, only if device.getUuids() non-empty
  },
  "localName": "...",             // optional, only if device name != null (line 364-366)
  "rssi": -70,                    // dBm
  "txPower": 127,                 // ScanResult.getTxPower() on API≥26, else constant 127 (lines 368-372)
  "manufacturerData": { "76": "02015..." },  // key = decimal manufacturer id, value = lowercase hex string
  "serviceData": { "0000feaa-...": "00..." },// key = service UUID, value = hex string
  "uuids": ["..."],               // advertised service UUIDs (may be [])
  "rawAdvertisement": "0201..."   // full ScanRecord bytes as hex string, or null
}
```

Byte arrays are lowercase hex via `ConversionKt.bytesToString`
(`.../bluetoothle/ConversionKt.java`, `bytesToString` → `toHexString`).
`allowDuplicates: true` means the same advertiser appears many times per burst;
there is no client-side dedup (devices pushed per callback,
useMobileBleScan.ts:28-30).

### 3.4 `accelerometer` / `gyroscope` / `magnetometer` (fallback IMU mode)

Used only when the OS activity classifier is unavailable
(`isMotionActivityAvailable()` = Play Services present AND SDK ≥ 29 —
`.../motionactivity/MotionActivityPlugin.java:471-477`; mode selection at
useMobileMotionTracking.ts:181-195). Readings are **windowed aggregates of the
vector magnitude** — one reading per `windowMs` (default 1000 ms,
`PhysicalSensorWindowMs`, config.ts:19), emitted natively per sensor:

```json
{
  "t_start": 0,     // epoch ms, first sample in window
  "t_end": 0,       // epoch ms, window close (System.currentTimeMillis)
  "n": 25,          // sample count in window
  "sum": 0.0,       // Σ magnitude
  "sum_sq": 0.0,    // Σ magnitude²
  "max": 0.0        // max magnitude in window
}
```

Native: `MotionActivityPlugin.java:224-272` (emit functions), aggregator at
lines 133-180. Magnitude = `sqrt(x²+y²+z²)` of the raw sensor event
(accelerometer type 1 including gravity; gyroscope type 4 rad/s; magnetometer
type 2 µT) — lines 501-533. Sampling rate `SENSOR_DELAY_NORMAL` (field
`sensorUpdateInterval = 3`, line 69). Windows with `n == 0` emit nothing
(lines 227-229 etc.). Windows where the sensor is missing cause the whole
module start for that sensor to reject silently (useMobileMotionTracking.ts:199-204).

### 3.5 `motionActivity` (classifier mode, the normal path)

Emitted natively every `intervalMs` (default 10 000 ms,
`MotionActivityIntervalMs`, config.ts:18) plus immediately on activity change
(`MotionActivityPlugin.java:275-290`, receiver at 81-131, timer at 359-373):

```json
{
  "activity": "walking",   // "automotive"|"cycling"|"walking"|"stationary"|"running"|"unknown"
  "confidence": 100,       // 0-100; -1 on periodic ticks (only change-triggered
                           // ticks carry the real value) — line 287
  "timestamp": 0,          // epoch ms, emit time
  "accelerometer_std": 0.0 // optional; std-dev of (|accel| − 9.80665) drained
                           // since last emit (lines 199-221, 343-346)
}
```

Activity mapping from `DetectedActivity.getType()`: 0 IN_VEHICLE→`automotive`,
1 ON_BICYCLE→`cycling`, 2 ON_FOOT→`walking`, 3 STILL→`stationary`,
7 WALKING→`walking` (default string already "walking"), 8 RUNNING→`running`,
else `unknown` (lines 323-339). Type 4 (TILTING) and 5 are deprioritized by
`pickMostLikely` (lines 307-321); on start the cached type is seeded to 4 so
the first real update always registers as a "change" (line 631).

## 4. Buffer sizes & flush cadence (per sensor, into the outbox)

All constants from `types/database/config.ts:1-40` (`DefaultAppConfig`), all
overridable by Firebase Remote Config (§8):

| Sensor | Buffer | Flush trigger |
|---|---|---|
| gps | `LocationBufferSize` = 60 fixes (config.ts:3; enforced useMobileLocationTracking.ts:75-79) | size, **or** wall-clock timer `LocationFlushIntervalMs` = 30 000 ms (config.ts:4; timer at lines 167-169), **or** module stop (lines 181-182) |
| wifi | none (1 burst = 1 record) | one record written per burst; burst every `WifiScanIntervalMs` = 30 000 ms (config.ts:14; useMobileWifiScan.ts:55-70) |
| ble | none (1 burst = 1 record) | one record per burst; burst every `BleScanIntervalMs` = 30 000 ms, scan window `BleScanDurationMs` = 10 000 ms (config.ts:10-11; useMobileBleScan.ts:41-104) |
| accelerometer / gyroscope / magnetometer | `PhysicalSensorBufferSize` = 200 readings (config.ts:16; useMobileMotionTracking.ts:64-79, 130-134) | size only + module stop (lines 207-211). **No wall-clock timer** — a quiet sensor can sit in RAM indefinitely |
| motionActivity | `PhysicalClassifierBufferSize` = 5 events (config.ts:17; lines 51-57) | size only + module stop |

At defaults: ≈120 wifi bursts + ≈120 ble bursts per foreground hour; gps at
`distanceFilter: 0` flushes every 60 fixes or 30 s, whichever first. Concurrent
wifi/BLE bursts are coalesced (`activeBurst` guard, useMobileWifiScan.ts:63-66,
useMobileBleScan.ts:100-103).

## 5. Uploader cadence — correction to ANALYSIS.md

`UploaderBatchSize` = 100 records per request **is real**
(config.ts:21; useUploader.ts:103). But **`UploaderPeriodMs` = 60 000
(config.ts:22) is never read anywhere** — grep across the full recovered source
finds it only in the config file itself (it is still fetched from Remote Config
like every key, useMobileRemoteConfig.ts:25-60). There is **no foreground
60-second uploader interval**. The claim "uploader batch 100/60 s" in
`patriot_grassroots/ANALYSIS.md:111` is wrong on the cadence. Actual
`uploader.tick()` triggers:

1. **Background fetch** — `@transistorsoft/capacitor-background-fetch`,
   `minimumFetchInterval: 15` minutes, `NETWORK_TYPE_ANY`, `stopOnTerminate:
   true`, `enableHeadless: false` (`composables/mobile/backgroundFetch.ts:4-10`);
   wired while tracking at `useTrackingController.ts:184-190`. OS-scheduled, so
   15 min is a floor, not a period.
2. **App foregrounding** — `appStateChange` listener: if tracking and ≥ 15 min
   (`SYNC_THROTTLE_MS`) since last sync → tick (`plugins/stateChangeListeners.ts:13,73-81`).
3. **Silent push** — FCM data message with `action == "work_shift_upload_data"`
   → tick (`plugins/notifications.ts:154-168`, action constant
   `types/mobile/pushNotificationActions.ts:3`). `action == "work_shift_end"`
   stops the shift first, then ticks. (ANALYSIS.md:120's
   `silent_upload_work_shift_data` / `silent_force_live_update` names are wrong;
   the real action strings are `work_shift_upload_data`,
   `work_shift_end`, `download_and_apply_live_update`.)
4. **Shift lifecycle** — after pause (`useMobileShift.ts:269`), after resume
   (line 284), on shift restore (line 199), on finish
   (line 307, unlimited drain with progress), on cancel (line 327).
5. **Manual "sync now"** on shift pages (`pages/shift/index.vue:167`,
   `pages/shift/[id].vue:216`, unlimited drain).

Per tick (`useUploader.ts:148-207`): skip if unauthenticated; skip if
`Network.getStatus()` reports offline (sets offline flag); then send
`device_state_sync` event (line 171) and a `data_upload` event carrying
`{timestamp, data:{maxId}}` (line 176) — both are
`POST /api/mobile/device/event/send` mobile events
(`mutations/mobile/sendDeviceEvent.ts:12-20`; enqueued to the same outbox if
offline, `utils/mobile/mobileEvents.ts:51-68`); then drain every sensor type
plus all message types **except `shift_end`** in parallel; `shift_end` drains
last and only when no other payloads for that shift remain (so
`data_complete: true` is set correctly, useUploader.ts:43-74, 187-193); finally
flushes VAD audio. A limited tick loops ≤ 50 iterations × 100 records per type
(`drainType`, useUploader.ts:121-133); finish/manual ticks are unlimited
(`tick` single-flight logic, lines 211-224).

## 6. SQLite outbox (`payloads` table)

- DB `{environment}-internal-data`, version 5, **no encryption**
  (`utils/dbManager.ts:5,9,139` — `createConnection(..., 'no-encryption', ...)`).
- Schema (migration v2, dbManager.ts:60-69):
  ```sql
  CREATE TABLE payloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    data_type TEXT NOT NULL,     -- sensor_type or message type string
    payload TEXT NOT NULL        -- JSON of the batch envelope (§2)
  );
  CREATE INDEX idx_payloads_type ON payloads(data_type);
  ```
- **Insert**: `addPayload(dataType, payload)` — `utils/useDb.ts:35-60`. Gated:
  silently skipped if DB not initialized, if there is **no current work-shift
  id**, or if no user id (lines 40-52) — collection that outlives the shift is
  dropped, not queued.
- **Drain**: `getAllByType(type, limit, maxId)` — `SELECT id, payload ...
  WHERE data_type=? AND user_id=? AND id<=maxId LIMIT ?`
  (useDb.ts:202-216). **No `ORDER BY` clause** — FIFO holds in practice via
  rowid order but is not guaranteed by the SQL; mark the strict-FIFO claim
  **UNCONFIRMED**. `maxId` snapshot (`getMaxPayloadId`, useDb.ts:184-191) bounds
  each tick to rows present at tick start, so rows inserted mid-tick wait for
  the next tick.
- **Delete-on-success**: `deletePayloadsByIds(rows.map(_rowId))` runs only
  after the upload promise resolves (useUploader.ts:110-112; delete SQL at
  useDb.ts:235-240). On failure rows stay and are re-sent verbatim → the server
  must tolerate duplicate `record_id`s.
- Related tables in the same DB (dbManager.ts:78-113): `settings` (single row
  id=1 holding the synced AppConfig JSON, useDb.ts:18-27,242-260),
  `cached_audio`, `cached_wake_word_clips`, `recent_locations` (ring buffer of
  last 20 fixes, useDb.ts:13,262-298 — not server-bound itself).

## 7. Foreground vs background behavior

- `isAppForeground` is a global ref set from `App.getState()` at plugin start
  and on every `appStateChange` (`plugins/stateChangeListeners.ts:45-46,58-59`;
  setter `composables/mobile/useMobileRuntimeState.ts:38-40`).
- **WiFi**: interval tick checks `isAppForeground` and **skips the scan while
  backgrounded** (useMobileWifiScan.ts:58-62). Confirmed.
- **BLE**: same guard (useMobileBleScan.ts:95-99). Confirmed.
- **GPS**: keeps running in background — the plugin is configured with a
  foreground-service notification (`backgroundMessage: 'Activity is being
  recorded'`, `backgroundTitle: 'Workshift in progress'`,
  useMobileLocationTracking.ts:116-117). No foreground gate anywhere in the
  location tracker.
- **Motion/IMU**: no JS-side foreground gate (useMobileMotionTracking.ts has no
  `isAppForeground` reference). Native listeners and the emit timer keep firing
  while the process lives. Whether Android actually delivers sensor events to
  this app while backgrounded (background sensor restrictions, API 29+) is
  **UNCONFIRMED** from the sources; the activity-recognition broadcast
  (`ActivityRecognitionClient`) is delivered regardless.
- Net effect confirmed: pocket/backgrounded shift = GPS (+ possibly motion)
  only; radio-off wifi/BLE bursts produce zero records and the radio state
  itself is not reported (except gps `connection_type`, §3.1).

## 8. Config source (incl. Firebase Remote Config keys)

Chain: `DefaultAppConfig` → SQLite `settings` row → Firebase Remote Config
(`useMobileConfig.ts:18-23`: local DB first, then `fetchAndSync`; changes
persisted back to DB at lines 29-34). Remote Config via
`@capacitor-firebase/remote-config`, project `validnationai`:
`fetchAndActivate()` then per-key `getBoolean`/`getNumber`, **only keys whose
`source === Remote` override defaults** (`useMobileRemoteConfig.ts:21-60`);
fetch settings `fetchTimeoutInSeconds: 10`, `minimumFetchIntervalInSeconds:
600` (lines 8-11). Refreshed on every shift start (awaited) and resume
(fire-and-forget) — `useTrackingController.ts:166-172`.

The Remote Config **keys are exactly the `DefaultAppConfig` property names**
(config.ts:1-40, iterated via `AppConfigKeys`). Sensor-relevant keys:
`LocationDistanceFilter` (0), `LocationBufferSize` (60),
`LocationFlushIntervalMs` (30000), `LocationAndroidPriority` (0),
`LocationDesiredAccuracy` (2), `LocationPausesAutomatically` (true),
`LocationActivityType` (3), `BleScanDurationMs` (10000), `BleScanIntervalMs`
(30000), `BleScanAllowDuplicates` (true), `WifiScanIntervalMs` (30000),
`PhysicalSensorBufferSize` (200), `PhysicalClassifierBufferSize` (5),
`MotionActivityIntervalMs` (10000), `PhysicalSensorWindowMs` (1000),
`UploaderBatchSize` (100), `UploaderPeriodMs` (60000 — fetched but unused, §5),
`GeofenceFetchRadiusKm` (50), `GeofenceRefreshDistanceKm` (10),
`GeofenceWarningDistanceKm` (1), `GeofenceRestrictionQueueSize` (4).

## 9. Background-geolocation configuration

`BackgroundGeolocation.addWatcher` options, `useMobileLocationTracking.ts:114-127`:

```ts
{
  backgroundMessage: 'Activity is being recorded',   // hardcoded
  backgroundTitle: 'Workshift in progress',          // hardcoded
  requestPermissions: false,                          // hardcoded
  stale: false,                                       // hardcoded
  distanceFilter: config.LocationDistanceFilter,      // 0 → every fix
  androidPriority: config.LocationAndroidPriority,    // 0 = high accuracy
  desiredAccuracy: config.LocationDesiredAccuracy,    // iOS-only
  pausesLocationUpdatesAutomatically: config.LocationPausesAutomatically, // iOS-only
  activityType: config.LocationActivityType,          // iOS-only
}
```

Values come from `getAppConfig()` (§8). Every accepted fix triggers
`onLocationUpdate` → enqueue into the GPS buffer and forward to the audio
manager (lines 131-147).

## 10. Break (pause) behavior — collection fully stopped

`pause()` → `executePause` (`useTrackingController.ts:88-114`): **all modules
are stopped first** (`moduleManager.stop()` — GPS watcher removed, wifi/BLE
intervals cleared and in-flight burst awaited, motion listeners removed with
final buffer flush, audio stopped — `useMobileModules.ts:35-63`); only then is
the pause recorded (`pauseWorkShiftSession`, which enqueues a
`shift_break_event` `{type:'pause', work_shift_id, button_pressed_time}` and
fire-and-forget syncs — `useMobileShift.ts:260-271`). If any module fails to
stop, the pause is aborted and modules restarted (lines 90-96). Confirmed: no
sensor collection of any kind during breaks; buffered-but-unflushed readings
are flushed to the outbox as part of module stop. Resume restarts modules
**before** committing the resume server-side (useTrackingController.ts:350-368).

## 11. `POST /api/projects/{project_id}/restricted_areas` (geofencing)

- **Client**: `mutations/mobile/fetchRestrictedAreas.ts:9-22` — POST with JSON
  body; path template from generated client
  `GetRestrictedAreasForAudioRecordingData['url']`.
- **Body**: `{ "lat": <number>, "lon": <number>, "radius_km": <number> }`
  (`useAudioRestrictionZones.ts:124-131`), radius = `GeofenceFetchRadiusKm`
  (default 50).
- **Response consumed**: `response.features` (GeoJSON Features; properties read
  as `zipCode` or `zip_code`, fallback synthetic id — lines 32-46) and
  `response.permission` (an `AudioRecordingPermission` string — line 137).
  Nothing else is read.
- **When called** (all paths funnel through `ensureZonesLoaded`,
  lines 194-207, which is gated by `shouldRefreshZones`, lines 76-98):
  1. On the **first VAD voice chunk that carries a GPS point** in a shift whose
     project is `full_recording_with_restricted_area`
     (`useVadVoiceHandler.ts:21-24`; restriction checking only activated for
     that permission at `useMobileAudioManager.ts:104`).
  2. From the restriction banner on **every GPS fix** while such a shift is
     active (`components/mobile/AudioRestrictionBanner.vue:46-50`).
  - Refetch rules: never for `full_recording`/`no_recording` projects
    (lines 79-83); not before `nextRetryAfter` (30 s error backoff,
    lines 25,85,145); refetch when the current fix is > `GeofenceRefreshDistanceKm`
    (default 10 km) from the last fetch center (lines 91-97); always when never
    fetched. Single-flight per project (`inFlightFetches`, lines 197-205).
- **Decision logic (client-side, no further server traffic)**: point-in-polygon
  via turf (`isPointRestricted`/`checkRestriction`, lines 152-186);
  **warning** = within `GeofenceWarningDistanceKm` (default 1 km) of a zone and
  not inside it (`isApproachingRestriction`, lines 188-192, drives the banner
  "Note-taking paused in this area", AudioRestrictionBanner.vue:56-59);
  **recording gate** = `isRecentlyAllowed()` (lines 237-255): fail-closed —
  false until a successful fetch AND a full queue of
  `GeofenceRestrictionQueueSize` (4) consecutive GPS-tagged statuses that all
  (a) lie within the cached 50 km fetch circle (`hasCoverageFor`, lines 100-109)
  and (b) are outside every zone. Disallowed segments are deleted natively via
  `AudioManager.releaseSegments` and never uploaded
  (`useVadVoiceHandler.ts:36-39`). This resolves the [H]-grade uncertainty in
  `docs/DESIGN-VALIDNATION.md:174-175` about the 50 km/1 km numbers: both are
  Remote-Config-tunable defaults (config.ts:33-35), and the "50 km" is a fetch
  radius around the worker's current position, re-centered every 10 km of drift.

## 12. What this audit resolves / corrects

- **Resolves** the GPS `simulated` flag question: verbatim pass-through of
  Android `Location.isFromMockProvider()` (BackgroundGeolocation.java:89).
- **Corrects ANALYSIS.md:111**: uploader is event-driven (background fetch ≥
  15 min, foreground ≥ 15 min throttle, silent push, lifecycle, manual);
  `UploaderPeriodMs` is dead config. 100 = records per request, not per minute.
- **Corrects ANALYSIS.md:120**: push action strings are
  `work_shift_upload_data` / `work_shift_end` / `download_and_apply_live_update`.
- **Corrects/qualifies ANALYSIS.md:74**: network *connection type* IS uploaded,
  as `connection_type` on every GPS reading. Wifi/BLE radio on/off state is
  still reported nowhere.
- **New**: GPS/IMU/motionActivity `started_at`/`ended_at` are epoch-ms numbers;
  wifi/ble are ISO strings — fixtures must match per type.
- **New**: IMU readings are 1 s windowed magnitude aggregates
  `{t_start,t_end,n,sum,sum_sq,max}`, not raw samples; motionActivity
  confidence is `-1` on periodic ticks.
- **New**: outbox drain SQL has no `ORDER BY` — strict FIFO **UNCONFIRMED**
  (rowid order in practice).
- **Resolves** DESIGN-VALIDNATION.md:174 geofence numbers: 50 km fetch /
  10 km re-center / 1 km warning / queue of 4, all Remote-Config defaults.
- **UNCONFIRMED**: batch_upload response body schema (never consumed; only
  HTTP-200-vs-other matters); motion-sensor delivery while backgrounded
  (no JS gate, OS behavior unknown); generated client types
  (`client/types.gen.ts` absent from the recovered tree).
