# Network communication — Patriot Grassroots ⇄ ValidNation servers

**App:** `com.patriotgrassroots.validnation` v1.0.0 (114) — white-label of the
ValidNation platform (Capacitor/Nuxt hybrid). **Backend:**
`https://api.validnation.ai` (plus the Supabase project
`tfnnpqpvdjisoizvciyr.supabase.co`, which is part of the official pipeline for
chats; §11). Compiled 2026-09-19 from the audit files, which are ground truth.

This document catalogs every message the app sends to or receives from the
official servers — purpose, trigger, and the purpose of each exchanged data
point, at field level wherever the recovered code proves the fields.

**Source-of-truth files** (all under `patriot_grassroots/`):

- `audit/README.md` — audit index, methodology, recovery caveats.
- `audit/endpoint-inventory.md` — master table (322 SDK operations),
  transports T1–T8, websocket + push inventories, endpoints.txt reconciliation.
- `audit/auth-session.md` — auth/session wire behavior.
- `audit/shift-lifecycle.md` — shift state machine, device events, outbox.
- `audit/sensors-telemetry.md` — sensor batch upload, reading schemas,
  geofencing, uploader cadence.
- `audit/audio-voice.md` — voice sample, VAD audio, wake word, signatory
  voice verification.
- `audit/earnings-account-misc.md` — earnings, account, applications,
  contracts, chats/Supabase, recruitment.
- `endpoints.txt` — 265 raw extracted API paths (completeness checklist, §13).
- `ANALYSIS.md`, `../docs/DESIGN-VALIDNATION.md` — secondary; where they
  conflict with the audits, the audits win (conflicts collected in §14).

**Evidence labels:** **[R]** recovered from decompiled/recovered stock code;
**[O]** observed live; **[H]** hypothesis. Fields the audits mark UNCONFIRMED
are labeled UNCONFIRMED here — most full response schemas are unrecoverable
because `client/types.gen.ts` (hey-api generated types) was erased at compile
time and `/openapi.json` requires auth (`audit/endpoint-inventory.md` header).
`/tmp/vn_src/` citations in the audits are relative to the ephemeral recovered
source tree; regenerate it per `audit/README.md` "How this was produced".

---

## 1. Transport layer (every message uses one of these) [R]

`audit/endpoint-inventory.md` §1. Base URLs come from the plaintext runtime
config in `tree/assets/public/index.html`: `apiBaseURL:
https://api.validnation.ai`, `wsBaseURL: wss://api.validnation.ai/api/ws`,
Supabase `https://tfnnpqpvdjisoizvciyr.supabase.co` (+ publishable key
`sb_publishable_xeO1bd3QP8IbXsKvFBW27g_OLjQU62U`).

| # | Transport | Used for | Key behavior |
|---|---|---|---|
| T1 | hey-api generated client on `$fetch` (on device: CapacitorHttp patches global fetch) | all web-UI API calls | proactive refresh if `exp` within 30 s; 401 → refresh → single replay → sign-out; GETs offline-cached (24 h TTL, 50 MB) |
| T2 | `doNativeRequest()` on `CapacitorHttp.request` | all `mutations/mobile/*` (work_shift, sensors, device events/info, FCM token, unlink, versions, restricted_areas, selector/project) | `Authorization: Bearer` attached; JSON content-type on non-GET; 15 s timeouts; 401 → refresh + one retry → foreground sign-out; GET cache fallback on connectivity errors |
| T3 | Native OkHttp multipart inside `audio-manager-plugin` | `/api/canvasser_voice/receive`, `/cached_receive`, `/wake_word_audio`, `/wake_word_audio_cached` | `Authorization` header; failure → WAV cached to disk + SQLite row for retry |
| T4 | Hand-rolled CapacitorHttp/XMLHttpRequest multipart | `POST /api/upload/` (chat attachments) | single `file` part |
| T5 | Supabase JS client | chats: PostgREST `/rest/v1/`, RPC, Realtime WS, Storage | ValidNation JWT as bearer + anon `apikey`; 401 → refresh+retry; 5 s timeout race |
| T6 | WebSocket `wss://api.validnation.ai/api/ws/voice_verification/{id}` | signatory voice verification only | one-time token from `GET /api/auth/ws_token` as query param |
| T7 | Firebase (FCM + Remote Config + Analytics) | push delivery, remote tuning | Remote Config min fetch 600 s, timeout 10 s |
| T8 | Sentry tunnel `POST /api/sentry` | crash/error envelopes via the API host | filtered to 400/403/404/5xx events |

Cross-cutting [R]:

- `Authorization: Bearer <ValidNation JWT>` goes **only** to
  `api.validnation.ai` and to the Supabase project host
  (`audit/auth-session.md` §7). FCM/Sentry/Maps are keyed, not bearer.
- No certificate pinning; no Play Integrity; user CAs untrusted at
  targetSdk 36 (`audit/auth-session.md` §10, `ANALYSIS.md`).
- `CapacitorHttp.enabled: true`; the native layer adds no auth/tracking
  headers of its own; FormData bodies get a native-generated boundary
  (`audit/auth-session.md` §10).
- Offline: GETs fall back to a CacheStorage cache; a 4-hourly prefetch warms
  `/api/account/`, `/api/selector/project`, `/api/earnings/balance/`,
  `/api/earnings/account/`, `/api/projects/` (+short_info/details), chat
  list + unread count (`audit/endpoint-inventory.md` §1). Mobile writes queue
  into the SQLite `payloads` outbox (§4.7, §5.6) and drain FIFO-ish (§5.6);
  audio has a separate WAV-file cache (§6.2).

---

## 2. Authentication & session

All [R]; owner: `audit/auth-session.md`. Token storage [R]: keys
`auth.token` / `auth.refresh-token` in `@aparajita/capacitor-secure-storage`
(per-key AES-GCM key in AndroidKeyStore, ciphertext in SharedPreferences
`WSSecureStorageSharedPreferences`); web fallback = cookies, access maxAge
900 s, refresh 15 d (`config/auth.ts:11-24`). The real JWT lifetime is read
from the token's `exp` claim; server-side TTL is UNCONFIRMED.

### 2.1 `POST /api/auth/token` — login [R]

Direction: upload (credentials) / download (tokens). Trigger: user taps "Log
In" (`pages/login.vue:92-118`). Unauthenticated (no bearer). Sent as
`multipart/form-data` on the wire (CapacitorHttp native boundary), same two
OAuth2-style fields the generated client would url-encode:

| Field | Purpose |
|---|---|
| `username` | account email (zod-validated email) |
| `password` | account password (trimmed) |

Response fields consumed: `access_token` → stored as the bearer JWT;
`refresh_token` → stored for refresh. Any other fields (`token_type`,
`expires_in`, …) ignored → UNCONFIRMED (`useAuth.ts:89-90`). Post-login side
effects: profile fetch (§2.3), device link + FCM registration (§4.5, §4.6),
offline prefetch. No retry on failure.

### 2.2 `POST /api/auth/refresh` — token refresh [R]

Direction: upload (refresh token) / download (new access token). JSON body
`{"refresh_token": "<raw refresh JWT or null>"}`; **no Authorization header**
(`useAuth.ts:228-240`). Triggers [R]: proactive timer at JWT **exp − 60 s**
(single-flight; re-armed on every token change); `visibilitychange`→visible;
route middleware on expired access token; 30 s pre-request expiry buffer in
the T1 stack; after a 401 on any path. Response: only `access_token` is
consumed — **no client-side refresh-token rotation** (a returned
`refresh_token` is silently ignored). A successful refresh always fires a
profile refetch (§2.3).

### 2.3 `GET /api/auth/profile` — session/profile fetch [R]

Direction: download. Bearer. Success is strictly HTTP 200. Triggers: app start
(with stored token), after every login and every refresh, after account-edit
flows. **No periodic poll.** Response fields consumed:

| Field | Purpose |
|---|---|
| `token.user{id,email,first_name,last_name,role}` | identity + role gating (`canvasser`/`subcontractor_canvasser`/`manager`/`admin`); Sentry user context |
| `alerts.banner_alert` | drives the account-problem banner; known values `create_application`, `provide_documents`, `fill_w9_form`, `record_voice_sample`, `provide_payment_info`, `provide_profile_info` |
| `settings.time_zone` | fallback timezone |
| `profile_picture_url` | avatar; ephemeral presigned URL re-issued per refetch |

Org/project assignments are **not** read from this response anywhere
(UNCONFIRMED whether present). Failure: 401 clears the access token only
(refresh kept); other errors preserve the session.

### 2.4 `POST /api/auth/logout` — sign out [R]

Direction: upload. Bearer (snapshot taken before tokens are cleared) + JSON
body `{"refresh_token": ...}`. Trigger: user logout or 401-cascade forced
sign-out; blocked while offline and while a shift is tracking/unsynced.
Sequence: block new refreshes → delete FCM token + `POST
/api/mobile/device/unlink {device_id}` (§4.6) → stop tracking/audio → clear
tokens locally → POST logout (response unused; errors swallowed — local
logout is unconditional). When the backend already rejected the token, the
POST is skipped entirely.

### 2.5 `GET /api/auth/ws_token` — websocket one-time token [R]

Direction: download. Bearer. No body/params. Sole consumer: the signatory
voice-verification websocket (§6.4). Response: `access_token` (one-time)
consumed; rest UNCONFIRMED. Used as a **query param** on the WS upgrade, not a
header. Refetched on every WS (re)connect; WS reconnect budget 3 × 5 s.

### 2.6 401 handling & retry budgets [R]

All three stacks share "refresh once, replay once, then sign out"
(`audit/auth-session.md` §9). T2 nuance: in background a failed replay just
throws (queued data survives; possible shift-data loss acknowledged in code).
Login and ws_token have no retry.

---

## 3. Shift lifecycle (`/api/mobile/work_shift/*`)

All [R]; owner: `audit/shift-lifecycle.md`. Transport T2 (bearer, JSON, 15 s
timeouts). The shared **`state_payload`** object (built by
`utils/mobile/deviceInfoUtils.ts:12-33`, deep-snake-cased) appears in
`generate` and `finalize_v2`:

| Field | Purpose |
|---|---|
| `permissions.{wifi,ble,gps,motion}` | OS **permission-grant** booleans only — never radio on/off state |
| `battery.{battery_level,is_charging}` | 0–100 (−1 when unavailable); charging state |
| `config` | full 30-key active tracking-config snapshot (Remote-Config-overridable): `location_distance_filter`, `location_buffer_size`(60), `location_flush_interval_ms`(30000), `location_android_priority`, `location_desired_accuracy`, `location_pauses_automatically`, `location_activity_type`, `ble_scan_duration_ms`, `ble_scan_interval_ms`, `ble_scan_allow_duplicates`, `wifi_scan_interval_ms`, `physical_sensor_buffer_size`, `physical_classifier_buffer_size`, `motion_activity_interval_ms`, `physical_sensor_window_ms`, `uploader_batch_size`(100), `uploader_period_ms`(60000, dead config), `vad_enabled`, `vad_max_buffer_size`, `vad_max_segment_seconds`, `vad_model_threshold`, `vad_gate_wake_word`, `vad_wake_word_hangover_ms`, `geofence_fetch_radius_km`, `geofence_refresh_distance_km`, `geofence_warning_distance_km`, `geofence_restriction_queue_size`, `audio_cache_ttl_days`, `audio_upload_batch_size` |

### 3.1 `POST /api/mobile/work_shift/generate` — clock-in [R]

Direction: upload (shift creation) / download (shift id). Trigger: worker taps
Start on the shift page, after the permission gate + project selection +
audio-session check. Body (`useMobileShift.ts:138-144`):

| Field | Purpose |
|---|---|
| `device_id` | device UUID (capacitor-udid); server-side per-device shift authority |
| `project_id` | server project UUID the worker selected |
| `start_time` | local ISO-8601 request time |
| `state_payload` | device capability/permission/config snapshot (above) |
| `time_zone` | IANA tz of the device (note spelling vs `timezone` in update_info) |

Response consumed: `work_shift_id` (becomes the session id, persisted) and
`start_time` — the **server-canonical** start time re-initializes the local
timer. Other fields UNCONFIRMED. Hard-requires network: no offline path.

### 3.2 `GET /api/mobile/work_shift/status_v2` — state sync [R]

Direction: download. Bearer; no query params, no body. **No fixed poll loop**
— fires on: shift start (pre-generate conflict check), session restore, the
app-level 5-min `useTimeoutPoll` → `checkAndStopIfClosed()`, every app resume,
and as a lost-timer fallback. Response fields consumed (only these four; rest
UNCONFIRMED):

| Field | Purpose |
|---|---|
| `device_id` | cross-device conflict detection (compare vs local UDID) |
| `work_shift_id` | unfinished-shift adoption; remote-stop detection (`shiftExists === false` → graceful local stop) |
| `project_id` | project recovery — if it differs from local storage the project is re-fetched and local state rewritten |
| `start_time` | timer fallback |

### 3.3 `POST /api/mobile/work_shift/pause` and `POST /api/mobile/work_shift/resume` — breaks [R]

Direction: upload. Trigger: break / end-break buttons. **Not direct calls**:
each button press enqueues an outbox row
`{type: "pause"|"resume", work_shift_id, button_pressed_time: ISO-8601}`, then
kicks an uploader tick. The uploader drains rows in row-ID order, strips
`type`/`_rowId`, and POSTs to `pause` or `resume` with body:

| Field | Purpose |
|---|---|
| `work_shift_id` | which shift the break belongs to |
| `button_pressed_time` | when the worker actually tapped (ISO-8601); server does span bookkeeping keyed on it |

Response: nothing consumed. HTTP 400/404 → row dropped (event no longer
applicable); other errors → row stays, retried next tick. Pause failure
emits a `pause_stop_failed` device event (§4.4).

### 3.4 `POST /api/mobile/work_shift/finalize_v2` — clock-out [R]

Direction: upload. **Body is a JSON array** (one tick can finalize several
shifts). Triggers: End-shift button; remote stop via §3.2 or `work_shift_end`
silent push; cross-device interrupt (direct call, bypasses outbox); aborted
start. Normal-path item:

| Field | Purpose |
|---|---|
| `work_shift_id` | shift being closed |
| `end_time` | ISO-8601 end time |
| `state_payload` | fresh permissions/battery/config snapshot at clock-out |
| `data_complete` | `true` **only** when no other outbox rows for this `work_shift_id` remain — the server reads it as "all shift data arrived" |

Drain-before-finalize ordering (load-bearing): the `shift_end` row is enqueued
first, then an unlimited uploader tick runs; inside a tick `shift_end` drains
strictly last and is deferred per-shift until no other rows for that shift
remain. `data_complete` covers only the SQLite `payloads` outbox — cached
**audio** uploads run after (a `data_complete:true` finalize can still be
followed by `/cached_receive`). The cross-device interrupt path sends
`[{work_shift_id, end_time, data_complete: null}]` — no `state_payload`,
literal null. Response: nothing consumed; failure → nothing deleted, retried
next tick.

### 3.5 Cross-device conflict [R]

At start: server shift on this device → adopt; on another device → modal; on
confirm, direct `finalize_v2` with `data_complete: null` (above), then
`generate`. Mid-shift: the 5-min/resume `status_v2` check stops the local
shift when the server no longer lists it for this device.

---

## 4. Device registration, device events, push token

All [R]; owner: `audit/shift-lifecycle.md` §6–§10. Transport T2.

### 4.1 `POST /api/mobile/device/update_info` — device registration/telemetry

Direction: upload. Triggers: app-level 5-min poll; once per shift start before
modules start; lazily single-flight before the first device event of a session
(the backend 403s events from an unlinked device). Full body
(`utils/mobile/updateDeviceInfo.ts:30-48`):

| Field | Purpose |
|---|---|
| `model`, `name` | device hardware identity (Device.getInfo) |
| `device_id` | device UUID — the link key between device and user account |
| `is_complete_sensors` | bool: accelerometer && gyroscope && magnetometer && rotationVector present |
| `is_root` | root/jailbreak detection (`device-security-detect`); the only anti-fraud bit on this endpoint |
| `os_version` | e.g. `"15"` |
| `permission_gps` / `permission_ble` / `permission_wifi` / `permission_motion` | OS permission-grant booleans |
| `push_permission_granted` | FCM OS-level permission |
| `push_notifications_enabled` | in-app push opt-out, inverted |
| `platform` | `android`/`ios`/`web` |
| `software_version` | `"v<web_version> (<native build>)"` |
| `timezone` | IANA tz |

Response: nothing consumed.

### 4.2 `POST /api/mobile/device/event/send` and `POST /api/mobile/device/event/batch_send` — device event catalog

Direction: upload ("send mobile device event(s) to clickhouse" per SDK doc).
Routing: online+authed → `ensureDeviceLinked()` → direct `send`; on
failure/offline/logged-out → enqueue as `mobile_event` outbox rows drained via
`batch_send` (`{device_id, events: [...]}`, ≤100/batch). **Caveat:** outbox
inserts are silently dropped when no shift is active — a failed direct-send
outside a shift is lost. Envelope (payload keys deep-snake-cased):

| Field | Purpose |
|---|---|
| `device_id` | device UUID |
| `created_at` | ISO-8601 event time |
| `event_type` | catalog below |
| `payload` | per-event object, or null |

Event-type catalog (complete for this build; full server enum UNCONFIRMED):

| `event_type` | Trigger | Payload (purpose) |
|---|---|---|
| `app_state` | every foreground/background toggle | `{state: 'foreground'|'background'}` — app visibility timeline |
| `data_upload` | start of every uploader tick | `{timestamp: epoch ms, data: {max_id: int}}` — tick marker + outbox high-water mark |
| `device_state_sync` | start of every uploader tick (rides ticks, not fixed-period) | full `state_payload` **plus** `resource_snapshot` (§4.4) |
| `app_termination` | once per process launch, before shift restore | `{platform, reason{reason,raw_code,description,timestamp,importance,pid}|null, was_graceful_marker (null on Android), was_clean_shutdown, work_shift_id, was_paused, last_resource_snapshot}` — why the process last died (Android `getHistoricalProcessExitReasons` mapped: exit_self/signaled/low_memory/crash/crash_native/anr/initialization_failure/permission_change/excessive_resource/user_requested/user_stopped/dependency_died/other/unknown) |
| `restored_after_termination` | shift restored after process death | `{was_paused, work_shift_id, project_id, permissions{...}, battery{...}}` (config stripped) |
| `tracker_state_divergence` | watchdog: native modules alive while JS believes tracking stopped | `{alive_modules: string[], native_watcher_count: int}` — snake_case on the wire |
| `pause_stop_failed` | pause flow failed | `{stage:'module_stop', failed: string[]}` or `{stage:'record_pause', error: string}` |
| `audio_cache_cleanup` | app resume, when the audio cache had items/errored | `{audio_paths: string[]}` or `{error, audio_paths, indices}` |
| `live_update_downloaded` / `live_update_applied` | OTA bundle lifecycle | `{bundle_id: string}` |

**Correction (audits win):** `shift_end`, `shift_break_event`,
`wake_word_event` are **outbox routing labels**, not event types — they map to
`finalize_v2`, `pause`/`resume`, and `/api/canvasser_voice/wake_word_event`
and never reach `device/event/*` (`audit/shift-lifecycle.md` §7; corrects
older ANALYSIS.md text).

### 4.3 `POST /api/canvasser_voice/wake_word_event` — wake-word event (JSON)

Direction: upload. Trigger: native `grace_emergency.tflite` detection
(threshold 0.99) while VAD hears voice. Body (`useWakeWordHandler.ts:14-21`):

| Field | Purpose |
|---|---|
| `id` | client-generated UUIDv4 — join key to the audio clip upload (§6.3) |
| `work_shift_id`, `device_id` | shift/device attribution |
| `timestamp_ms` | detection time, epoch ms |
| `gps_point{latitude,longitude,accuracy,altitude,altitude_accuracy,timestamp(ISO)}` | last fresh fix, or null |

Policy: outbox first, then direct send; success deletes the row; 400/404 drops
the row permanently (Sentry-reported), other errors retry. Response unused.

### 4.4 Process death & restart [R]

Native snapshots resource pressure to SharedPreferences on onStop/onDestroy/
onTrimMemory(≥15): `{sampled_at, battery{low_power_mode,level,is_charging},
memory{trim_level_max,available_bytes,total_bytes,threshold_bytes,low_memory},
thermal{state}}` — this `last_resource_snapshot`/`resource_snapshot` rides
`app_termination` and `device_state_sync`. On next launch, ordering is
enforced: `app_termination` report (once per process) →
`restored_after_termination` → resume or stay stopped. A
`session_clean_shutdown` Preferences flag distinguishes graceful stops.

### 4.5 `POST /api/mobile/notifications/token` (+ `DELETE`) — FCM token

Direction: upload. Body `{device_id, token}` — registers the FCM push token
for this device. Triggers: the 5-min app poll re-registers whenever
unregistered (requires OS permission + no in-app opt-out); FCM
`tokenReceived` (token refresh). Opt-out: `DELETE
/api/mobile/notifications/token?device_id=...` then local FCM token deletion.
Response: only `isRegistered` bookkeeping consumed.

### 4.6 `POST /api/mobile/device/unlink` — logout teardown

Direction: upload. Body `{device_id}` — unlinks the device from the user
account. Trigger: logout, native only, after FCM token deletion
(`utils/mobile/unlinkDeviceFromUser.ts:7-29`).

### 4.7 Offline outbox mechanics (shapes what actually reaches the server) [R]

SQLite `{environment}-internal-data`, **unencrypted**,
`payloads(id, user_id, data_type, payload)` + index on `data_type`
(`audit/shift-lifecycle.md` §11). `data_type` → endpoint routing: the 7 sensor
types → `sensor/batch_upload`; `shift_break_event` → pause/resume; `shift_end`
→ finalize_v2; `mobile_event` → event/batch_send; `wake_word_event` →
wake_word endpoint. Rows are deleted only after their upload succeeds;
failures resend verbatim, so the server must tolerate duplicate `record_id`s.
Drain SQL has **no `ORDER BY`** — strict FIFO is UNCONFIRMED (rowid order in
practice). Inserts are silently dropped when logged out / no active shift.

---

## 5. Location / sensor telemetry

All [R]; owner: `audit/sensors-telemetry.md`. Sensor records are never posted
directly from trackers — every byte goes through the outbox (§4.7).

### 5.1 `POST /api/mobile/sensor/batch_upload` — the sensor upload

Direction: upload. Trigger: uploader ticks (drivers in §5.5). Body
`{"records": [<envelope>, ...]}`; up to `uploader_batch_size` = 100 records
per request, all of the **same** `sensor_type`. Success = **HTTP 200
exactly**; response body never read (schema UNCONFIRMED). Any failure → rows
kept, retried verbatim next tick (no poison-record drop for sensor types; the
server must tolerate duplicate `record_id`s). Sibling `POST
/api/mobile/sensor/` is declared `@deprecated` and **never called** (DEAD).

Record envelope (all sensor types):

| Field | Purpose |
|---|---|
| `record_id` | UUIDv4 per batch; generated at first enqueue (idempotency anchor for duplicate tolerance) |
| `work_shift_id` | current shift UUID — records exist only while a shift is active |
| `device_id` | device UUID |
| `sensor_type` | `gps`/`wifi`/`ble`/`accelerometer`/`gyroscope`/`magnetometer`/`motionActivity` |
| `started_at` / `ended_at` | batch time bounds — **epoch-ms numbers** for gps/IMU/motionActivity, **ISO-8601 strings** for wifi/ble |
| `sensor_readings` | schema per sensor type (§5.2) |

### 5.2 Reading schemas per sensor type [R]

**`gps`** (`useMobileLocationTracking.ts:21-32,63-74`):

| Field | Purpose |
|---|---|
| `latitude`, `longitude` | degrees |
| `accuracy` | horizontal accuracy, meters |
| `timestamp` | epoch ms — `Location.getTime()`, fallback `Date.now()` |
| `altitude`, `altitude_accuracy` | meters, nullable |
| `speed`, `bearing` | m/s and degrees; only present when the fix has them |
| `simulated` | verbatim Android `Location.isFromMockProvider()` (`BackgroundGeolocation.java:89`) — mock-location honesty bit |
| `connection_type` | `wifi`/`cellular`/`none`/`unknown` — sampled from `@capacitor/network` per reading (this corrects the older "radio state sent nowhere" claim) |

**`wifi`** (one record per scan burst; readings = raw `WifiEntry[]`):
`bssid` (AP MAC), `ssid` (empty SSID serialized as `"[HIDDEN_SSID]"`),
`level` (RSSI dBm), `isCurrentWifi` (bssid == connected BSSID),
`capabilities[]` (ScanResult.capabilities split). Burst every
`wifi_scan_interval_ms` = 30 s; skipped while backgrounded.

**`ble`** (one record per burst; `requestLEScan({allowDuplicates:true})`, no
client dedup): `device{deviceId (MAC), name?, uuids?}`, `localName?`, `rssi`,
`txPower`, `manufacturerData{<decimal mfr id>: <hex>}`,
`serviceData{<service UUID>: <hex>}`, `uuids[]`, `rawAdvertisement` (full
ScanRecord hex or null). Burst every `ble_scan_interval_ms` = 30 s, window
`ble_scan_duration_ms` = 10 s; skipped while backgrounded.

**`accelerometer`/`gyroscope`/`magnetometer`** (fallback IMU mode, only when
the OS activity classifier is unavailable): windowed magnitude aggregates per
1 s window — `{t_start, t_end, n (sample count), sum, sum_sq, max}` of
`sqrt(x²+y²+z²)`. Flush at 200 readings or module stop; no wall-clock timer.

**`motionActivity`** (normal path): `{activity:
automotive|cycling|walking|stationary|running|unknown, confidence (0–100; −1
on periodic ticks), timestamp (epoch ms), accelerometer_std?}` — emitted every
`motion_activity_interval_ms` = 10 s plus immediately on change.

### 5.3 Buffer sizes & flush cadence [R]

gps: 60 fixes **or** 30 s timer **or** module stop. wifi/ble: 1 burst = 1
record, every 30 s. IMU: 200 readings. motionActivity: 5 events. All constants
are Firebase-Remote-Config-overridable (`DefaultAppConfig` keys; §7).

### 5.4 Foreground/background behavior [R]

GPS keeps running in background (foreground-service notification "Activity is
being recorded"). wifi/BLE scans are skipped while backgrounded (pocket =
GPS-only). Motion/IMU: no JS gate; OS delivery while backgrounded UNCONFIRMED.
Radio on/off state itself is reported nowhere (only gps `connection_type`).

### 5.5 Uploader cadence — event-driven, not periodic [R]

**Correction:** `UploaderPeriodMs` (60 s) is dead config — no consumer exists.
Actual tick triggers: (1) background-fetch `minimumFetchInterval: 15` min (OS
floor, `stopOnTerminate: true`); (2) app foregrounding, throttled to once per
15 min while tracking; (3) silent pushes `work_shift_upload_data` /
`work_shift_end` (§10); (4) shift lifecycle (pause/resume/restore/finish/
cancel); (5) manual "sync now". Per tick: `device_state_sync` event →
`data_upload` event → drain all non-`shift_end` types in parallel (≤50
iterations × 100 records/type when capped; finish/manual ticks unlimited) →
`shift_end` last with per-shift deferral → audio tail.

### 5.6 `POST /api/projects/{project_id}/restricted_areas` — geofencing [R]

Direction: upload (position) / download (zones). Body `{lat, lon, radius_km}`
— radius = `geofence_fetch_radius_km` (default 50). Called only for
`full_recording_with_restricted_area` projects: on the first GPS-tagged VAD
chunk and on every GPS fix via the restriction banner; refetch when >10 km
(`geofence_refresh_distance_km`) from the last fetch center; 30 s error
backoff; single-flight. Response consumed: `features[]` (GeoJSON restricted
polygons; `properties.zipCode`/`zip_code` as zone id) and `permission`
(audio-recording permission string). Decision logic is client-side: 1 km
warning (`geofence_warning_distance_km`, banner only) and a fail-closed
recording gate (queue of 4 consecutive covered+unrestricted fixes required;
disallowed segments deleted on-device via `releaseSegments`, never uploaded).

---

## 6. Audio / voice

All [R]; owner: `audit/audio-voice.md`. Base `https://api.validnation.ai`.

### 6.1 `POST /api/account/voice_sample/` — worker voice enrollment

Direction: upload. Server-mandated onboarding: profile `alerts.banner_alert
=== "record_voice_sample"` until provided; hiring checkmark
`voice_sample_recorded` on `/api/account/`. **JSON, not multipart, not webm**
(the webm blob is local preview only):

| Field | Purpose |
|---|---|
| `audio_data` | base64 of concatenated raw **Int16-LE PCM** (AudioWorklet, no container) |
| `audio_config.sample_rate` | device-reported (`track.getSettings().sampleRate`, typically 48000; NOT resampled) |
| `audio_config.channels` | default 1 |
| `audio_config.bits_per_sample` | default 16 |
| `audio_config.encoding` | hardcoded `"linear16"` |

Client enforces >30 s minimum. Transport: webview fetch (not the native OkHttp
path). Response body unused; failure = toast, no retry, no offline queue.

### 6.2 Continuous shift audio (VAD pipeline) — `POST /api/canvasser_voice/receive` and `/cached_receive`

Active only when the project's `audio_recording_config.permission` is
`full_recording` or `full_recording_with_restricted_area`; on `no_recording`
projects zero audio is the normal server-visible state. Native capture:
`AudioRecord` VOICE_RECOGNITION, 16 kHz mono PCM16, Silero VAD, ~3 s voiced
chunks; each chunk carries a GPS point (nearest fix to segment midpoint; in
restricted-area mode no-fix segments are dropped on-device).

Upload triggers: JS pool auto-flush at ~120 s of accumulated PCM (3.84 MB),
flush on recorder stop, and the uploader-tick tail. Request is built
**natively** (OkHttp multipart, bearer) — `POST /api/canvasser_voice/receive`:

| Part | Purpose |
|---|---|
| `audio` | file `voice_chunk.wav`, `audio/wav` — WAV (PCM16/16 kHz/mono) wrapping all included segments |
| `work_shift_id` | shift attribution |
| `vad_model_name` | `"silero"` |
| `device_id` | device UUID |
| `sample_rate` | `"16000"` |
| `wallclock_start` / `wallclock_end` | UTC `yyyy-MM-dd'T'HH:mm:ss.SSS'Z'` span bounds; chunks tile a contiguous wall-clock span via persisted `lastUploadEndMs` |
| `segments` | JSON string: per-segment `{start_ms, end_ms, gps_point{timestamp,latitude,longitude,accuracy,altitude,altitude_accuracy}}` |
| `span_upload_id` | fresh UUIDv4 per request (span dedup/continuity anchor) |

Response body is **never parsed** for `/receive`. `missingSegmentIds` in the
plugin result is a **client-side** 50 MB-store eviction report, not server
reconciliation. On success native deletes the segments; non-2xx keeps them
(re-queued); network failure writes `AudioChunks/{start}-{end}.wav` to disk +
a `cached_audio` SQLite row; 401 → JS refresh + one retry.

**`POST /api/canvasser_voice/cached_receive`** (offline backlog, uploader-tick
tail, batches of `audio_upload_batch_size` = 64 rows): multipart with per-chunk
`audio` = `voice_chunk_{i}.wav`, per-row `work_shift_id`/`wallclock_start`/
`wallclock_end`/`span_upload_id`, one `device_id` (from the first row), and
`segments` = JSON array **whose elements are themselves JSON strings** of the
per-chunk segment arrays (reimplementation must reproduce this nesting).
Response consumed: `succeeded_filenames` — listed files/rows are deleted.
Cached audio TTL 4 days (`audio_cache_ttl_days`), swept on every app resume.

### 6.3 Wake-word emergency uploads

Detection: `grace_emergency.tflite` @ 0.99, VAD-gated, 30 s debounce; clip =
raw ring-buffer slice [t−3 s, t+1 s], clip id `wakeword_{startMs}_{endMs}`.
The JSON event (§4.3) goes first; the clip follows.

- **`POST /api/canvasser_voice/wake_word_audio`** (multipart): `audio` =
  `wake_word_clip.wav`; `event_id` (join key = §4.3 `id`); `work_shift_id`;
  `device_id`; `clip_start_ms`; `clip_end_ms`. Failure/any non-2xx → cached to
  disk + `cached_wake_word_clips` row. Response ignored.
- **`POST /api/canvasser_voice/wake_word_audio_cached`** (multipart batch,
  uploader-tick tail, grouped per `device_id`): `audio` =
  `wake_word_clip_{i}.wav` × N; `device_id`; `clips` = JSON string
  `[{event_id, work_shift_id, clip_start_ms, clip_end_ms}, …]`. Response
  consumed: `succeeded_indices` — those clips' files/rows are deleted. Same
  4-day TTL.

### 6.4 Signatory voice verification (petition voters — worker-initiated) [R]

The petition **signatory** feature (voters' voices), not a worker spot-check;
no server-initiated voice challenge exists. The **only** ValidNation
websocket.

1. `PUT /api/verifications/voice/`, body `{"project_id"}` → response `id`
   (conversation id) consumed. Shown only when
   `project.voice_verification_enabled`.
2. `GET /api/verifications/voice/{conversation_id}` on page mount — consumed:
   `status` (`new`/`in_progress` → stream; `ready_for_submit` → render
   `extracted_signatories`).
3. `GET /api/auth/ws_token` (§2.5) → WS
   `wss://api.validnation.ai/api/ws/voice_verification/{id}?token=&sample_rate=&bits_per_sample=&channels=&encoding=`.
   Query params carry the one-time token plus the audio config
   (device-dependent, e.g. 48000/16/1/linear16).
4. WS messages, client→server: `{type:'start'}` (after server `initialized`);
   `{type:'stream_audio', audio_data: <base64 PCM>}` every 250 ms (bytes are
   the same Int16-LE worklet output; sent verbatim);
   `{type:'stop'}` (user stop / server `force_stop`); `{type:'cancel'}`
   (user cancel / route leave).
   Server→client: `initialized`; `signatory_info` (`{infos: [...]}` with
   per-signer `id, first_name, middle_name, last_name, state, city, county,
   address_1, address_2, zip_code, validation_result, signed_date,
   other_data` — extracted signer identity for the worker to confirm);
   `ready_for_submission`; `force_stop`; `error{detail}`. Reconnect: 3 × 5 s;
   online-only, no offline queue.
5. `POST /api/verifications/voice/{conversation_id}/submit`, body
   `{signatories: [{first_name, last_name, middle_name, state, city, county,
   address_1, address_2, zip_code, signed_date}]}` — the worker-confirmed
   signer identities (client strips server `id`/`other_data`/
   `validation_result`; `signed_date` defaults to today). Success: toast +
   query invalidation; failure: toast only.

Related: `GET /api/verifications/voice/` exists but is DEAD (no caller);
`PUT /api/verifications/voter/` `{project_id, infos: SignatoryVoiceForm[]}` is
the manual (non-voice) signatory-entry path.

---

## 7. Remote configuration (server → app tuning) [R]

Firebase Remote Config (project `validnationai`) is part of the official
pipeline: `fetchAndActivate()` on every shift start (awaited) and resume;
min fetch interval 600 s, timeout 10 s. Only keys with `source === Remote`
override `DefaultAppConfig`; the synced config is persisted to the SQLite
`settings` row and is exactly the 30-key set echoed back to the server inside
`state_payload.config` (§3) — buffer sizes, scan intervals, VAD thresholds,
geofence radii, uploader batch size, audio cache TTL/ batch. This is how the
backend remotely retunes collection density.

`POST /api/settings/versions` — version / live-update check [R]: body
`{platform, native_version, native_build_number, frontend_version,
current_bundle_id}`; **unauthenticated-allowed**. Triggers: cold start
(silent), resume prompt (3 h dialog throttle), push action
`download_and_apply_live_update`. Response consumed: `force_native_update`,
`force_live_update`, `live_update_bundle_id`, `bundle_url`, `checksum`,
`has_native_update`. The OTA bundle itself downloads from the server-supplied
`bundle_url` via `@capawesome/capacitor-live-update` (host UNCONFIRMED);
applied bundles are reported back via `live_update_downloaded`/
`live_update_applied` device events + a fresh `update_info` (§4.1, §4.2).

---

## 8. Earnings & payroll (worker-facing reads + one write)

All [R]; owner: `audit/earnings-account-misc.md` §1. T1 transport, bearer, JSON.

### 8.1 Downloads

- **`GET /api/earnings/totals-by-rate-type/`** — 30-day bonus/increased-rate
  totals; earnings list page, staleTime 60 s. Consumed:
  `{bonus:{total,count}, increased_rate:{total,count}}`; `total` coerced with
  `Number(... ?? 0)` (may arrive as string); cards render only when
  `count > 0`.
- **`GET /api/earnings/`** — earnings list; query params `page, size,
  sort_by ('created_at'|'final_total'|'review_deadline_timestamp'), sort_type,
  search_query, statuses[], rate_types[], sources[], canvasser_ids[],
  project_ids[], created_date_from/to, final_total_min/max, timezone`.
  Consumed: `{items[], total_count}`; canvasser item fields `id, created_at,
  project{name}|null, status, final_total, rate_type`. Enums (client-side):
  status = `pending|under_review|ready_for_payment|transaction_processing|
  completed|manually_completed|rejected|failed`; rate_type =
  `regular_rate|bonus|increased_rate|reimbursement`.
- **`GET /api/earnings/{earning_id}`** — detail page, refetch every mount.
  Consumed (canvasser variant): `status, payroll_at|null, rate_type,
  final_total, work_shift_date|null, created_at, project_id|null,
  referral_id|null, paid_signatures_amount|null, work_shift{id,…}|null,
  assignment_type|null, description|null`. Approval state is conveyed by
  `status` + the admin-variant `*_details` blocks; no separate boolean.
- **`GET /api/earnings/{earning_id}/short_info`** — inline entity labels;
  display label fields only (UNCONFIRMED beyond that).
- **`GET /api/earnings/account/`** — Branch payout-onboarding status; balance
  + transactions pages, staleTime 500 ms; **the only poll in scope**: 10 s
  while awaiting Branch activation after "Open Branch". Consumed:
  `{status: not_registered|registered|activated|deactivated, onboarding_link}`.
  No Branch SDK client-side; Branch config is server-side.
- **`GET /api/earnings/balance/`** — balance page only (+ offline prefetch).
  Consumed: `{ready_for_payment, pending, next_payment_date,
  same_day_payout_enabled}`.
- **`GET /api/earnings/transactions/`** — payout history; query `page, size,
  sort_by (default 'timestamp_created'), sort_type, search_query, statuses[],
  canvasser_ids[], created_date_from/to, amount_min/max, timezone`;
  `TransactionStatus` = uppercase `PENDING|SCHEDULED|COMPLETED|FAILED|
  CANCELED|SKIPPED|REVERSED|UNKNOWN`. Consumed: `{items[], total_count}`;
  item `id, timestamp_created, status|null, amount` — **`amount` is integer
  cents**.
- **`GET /api/earnings/transactions/{transaction_id}`** — consumed: `status,
  amount (cents), created_at` (+ admin variant `type, canvasser{id},
  reason_code, error_label, error_message`).
- **`GET /api/earnings/transactions/{transaction_id}/earnings`** — breakdown:
  `{items[]}` of earning-list items.
- `GET /api/earnings/transactions/{transaction_id}/short_info` — DEAD
  (no caller).

### 8.2 `POST /api/earnings/withdraw` — same-day payout [R]

Direction: upload; **body-less POST**. Trigger: Withdraw button + confirm.
Response not field-read; success zeroes `ready_for_payment` in the local
cache. Button enabled iff `same_day_payout_enabled && ready_for_payment > 0 &&
!deactivated`.

### 8.3 Manager/admin-only earning mutations (worker never triggers)

Documented for completeness: `PATCH .../approve` `{adjustment (±1000),
note, description (1–5000)}`; `PATCH .../reject` / `PATCH
.../manually_completed` `{note, description}`; `POST .../pay` (no body;
response `{status, error_message}`, HTTP 200 even on failure — success iff
`status ∈ {COMPLETED, PENDING}`); `POST /api/earnings/` (manager creates
manual earning; fields UNCONFIRMED); `PATCH /api/earnings/account/{user_id}`
(single-key toggle `{weekly_payroll_enabled}` or `{same_day_payout_enabled}`).

---

## 9. Account, onboarding, profile

All [R]; owner: `audit/earnings-account-misc.md` §2, §8 and
`audit/endpoint-inventory.md` §6.1–6.2.

### 9.1 Sign-up (unauthenticated, onboarding only)

`POST /api/signup/` (create account), `POST /api/signup/email/confirm`
(submit code), `POST /api/signup/email/info` (poll email info), `POST
/api/signup/email/resend` (resend code), `PUT /api/signup/email/` (change
email mid-flow), `GET /api/public/subcontractor_company/details/{sign_up_code}`
(company sign-up landing). Exact bodies UNCONFIRMED (types.gen.ts missing);
failure = toast, no retry.

### 9.2 Account

- **`GET /api/account/`** — download. Account pages (staleTime 0), refetched
  after every onboarding step, 4-hourly prefetch. Consumed: `profile` (object),
  `general_info{city,state}|null`, `created_at`,
  `subcontractor_company_id|null`, `voice_sample_recorded` (voice-sample
  checkmark), `referral_program{referral_code}`.
- `PUT /api/account/password/edit` — upload `{old_password, new_password}`
  (new password: ≥8 chars, upper+lower, digit, one of `#?!@$%^&*-`, no
  spaces).
- `POST /api/account/password/reset` — **unauthenticated** `{email}` —
  request reset email.
- `POST /api/account/password/set` — **unauthenticated** `{otp_code, user_id,
  password}` from the email link's query params — complete reset.
- `PATCH /api/account/settings/edit` — upload `{time_zone: <IANA>}` (Save New
  Timezone); success triggers a full session refresh.
- `PATCH /api/account/{user_id}/delete` — no body; self-delete → local
  sign-out.
- `GET /api/account/referral_code` — DEAD (the referral page reads
  `referral_program.referral_code` from `/api/account/` instead).

### 9.3 Canvasser application & documents (onboarding writes)

- `POST /api/canvasser_application/general_info` — `{date_of_birth (ISO),
  address, city, state, zip_code, military_service, equipment_confirmation
  (bool), referral_source, referral_source_other?}`.
- `POST /api/canvasser_application/documents` — `{id_photo_urls: string[]
  (≥1)}`; URLs come from a prior file upload. **No `ssn` field is sent**
  despite the SDK doc string — SSN capture happens in the SignWell W-9 flow
  server-side; the `consent` checkbox is client-side only.
- `PUT /api/canvasser_application/{user_id}/general_info` — admin edit of the
  same fields (does not re-run vetting).

### 9.4 Contracts (worker side is read-only display)

`GET /api/contracts/v2/` (list; pagination + `statuses[], types[],
project_ids[], canvasser_ids[], signed_by_admin, signed_by_canvasser,
created_date_from/to, search_query, sort_by/sort_type`) and `GET
/api/contracts/v2/{contract_id}` (consumed: `type ('w9'|assignment),
parsed_ssn, signed-by flags, status`). Signing happens off-app via SignWell
email link; `POST /api/contracts/w9/send` `{canvasser_id}` and the SignWell
webhook are manager/server-side. v1 `GET /api/contracts/`,
`/api/contracts/{id}` are DEAD (superseded by v2).

### 9.5 Profile & sharing

`POST /api/profile/`, `POST /api/profile/generate-bio`, `PUT
/api/profile/{user_id}` — profile create/edit/AI bio (bodies UNCONFIRMED).
Shareable link: `GET /api/profile/{user_id}/shared_link` (dialog open), `POST
/api/profile/shared/{user_id}/generate` (regenerate), `PUT
.../enable`/`.../disable` (toggle). `GET
/api/profile/shared/{shareable_code}` — public, unauthenticated
shared-profile view.

---

## 10. Push notifications (server → app) and in-app notifications

### 10.1 FCM silent/data actions [R]

`audit/endpoint-inventory.md` §4. Android payload key `action` has **exactly
four values**; this is how the server drives the app between sessions:

| `action` | Client behavior |
|---|---|
| `none` | no-op; shows body toast if present |
| `work_shift_upload_data` | uploader tick → drains outbox (sensors/events/shift_end/audio) |
| `work_shift_end` | full local clock-out (`useMobile().stop()` — enqueues shift_end, drains), then tick |
| `download_and_apply_live_update` | download/apply OTA bundle (`bundle_id`, `bundle_url` from payload) → `live_update_*` events + `update_info` → webview reload |

The `silent_upload_work_shift_data` / `silent_force_live_update` names in
older docs are **in-app notification `type_` values**, not push actions
(correction per audit §4.1). In-app notification `type_` taxonomy (27 values,
display/routing only): `work_shift_start_reminder`,
`work_shift_deadline_exceeded`, `reset_password`,
`reset_password_confirmation`, `confirm_email`, `complete_branch_onboarding`,
`grace_message`, `recruitment_inbound_message`, `chat_message`,
`invalid_assignment_contract_template`, `deleted_assignment_contract_template`,
`invalid_w9_contract_template`, `deleted_w9_contract_template`,
`staffing_contact_invite`, `silent_force_live_update`,
`silent_upload_work_shift_data`,
`admin_assignment_contract_signing_request`,
`canvasser_assignment_contract_signing_request`,
`assignment_contract_sign_failed`, `w9_form_signing_request`,
`admin_assignment_contract_resign_request`, `w9_form_resign_request`,
`wake_word_event`, `project_finished`, `checkr_report_review_required`.
Tap routing: `data.redirectUrl` — `validnation:` scheme → internal route,
else external browser.

### 10.2 In-app notification endpoints [R]

- `GET /api/notifications/list` — notifications page; query `{page=1,
  size=10, sort_type='desc', only_unread}`. Consumed:
  `notifications[]{id, type_, message, read_at, sent_at, relative_url}`,
  `total_count`.
- `GET /api/notifications/unread-count` — sidebar badge, `useTimeoutPoll`
  **60 s**, skipped while backgrounded. Consumed: `{count}`.
- `POST /api/notifications/mark_as_read/{id}`,
  `POST /api/notifications/mark_all_as_read` — user actions.

---

## 11. Chats — 100% Supabase (official pipeline, different host) [R]

The entire chat feature bypasses `api.validnation.ai` — there is **no**
`/api/chats*` endpoint in the SDK. All chat traffic targets the official
ValidNation Supabase project `https://tfnnpqpvdjisoizvciyr.supabase.co`,
schema `private`, authenticated with the **app's own ValidNation JWT** as
`Authorization: Bearer` (plus the publishable anon key in `apikey`); the
Supabase backend validates the ValidNation JWT (RLS). Owner:
`audit/earnings-account-misc.md` §7. Documented separately because it is
third-party-hosted but part of the official data path.

**PostgREST RPC calls** (`POST /rest/v1/rpc/<fn>`, body `{"input": {...}}`):

| RPC | Input fields | Purpose / trigger |
|---|---|---|
| `get_user_chats_cursor` | `{archived, before_cursor, after_cursor, chat_limit (def 18)}` | chat list, cursor pagination |
| `get_user_chats_cursor_at` | `{archived, at_cursor, chat_limit}` | deep-link into a specific chat |
| `get_messages_with_details` / `get_messages_at_with_details` | cursor pagination; exact fields UNCONFIRMED | message history / jump to message |
| `send_message` | `{chat_id, body, reply_to_message_id, forwarded_from_user_id, attachment_group_id, dedup_key}` | send; `dedup_key` is a client idempotency key |
| `mark_message_read` | `{chat_id, message_id}` | read receipts |
| `edit_message` / `delete_message` | UNCONFIRMED fields | edit/delete own message |
| `mute_chat` | `{chat_id}` | mute toggle |
| `new_dm` | UNCONFIRMED | start DM from contacts |
| `get_chat_details` / `get_chat_info` / `get_chat_id` / `get_chat_participants_with_details` / `get_user_info` | `{input}` wrappers | chat header / channel details / id resolution / participants / user info |
| `get_unread_chat_count` | none | unread badge; also 15 s foreground poll + offline prefetch |

Consumed response fields (rest UNCONFIRMED — `~/types/schema` type-only):
chat item `id, cursor, last_read_message_id, last_message_id, muted_until,
archived_at`; chat info `title, cursor`.

**Direct table queries**: `profiles` (GET all where `id != me AND
is_deactivated = false` — contact picker; GET by id), `attachments` (INSERT
`{sender_id, channel_id, group_id, bucket, path, name, mime, size, width,
height, duration_ms, meta}` after Storage upload).

**Storage bucket `attachments`**: `POST /storage/v1/object/attachments/<path>`
(upload, `upsert:false`), `move` (rename), `createSignedUrl(path, 60 s)` for
viewing.

**Realtime websocket** `wss://tfnnpqpvdjisoizvciyr.supabase.co/realtime/v1/
websocket`, auth via `realtime.setAuth(<ValidNation JWT>)`: private broadcast
channels `chat-list:{userId}` (events `chat_list_new_message`,
`chat_list_new_chat`, `chat_list_delete_chat`, `chat_list_update_chat`,
`chat_list_archive_chat`, `chat_list_read_message`, `chat_list_edit_message`,
`chat_list_delete_message`, `chat_list_mute_chat`, `chat_list_unmute_chat`)
and `chat:{chatId}` (events `new_message`, `edit_message`, `delete_message`,
`edit_chat_details`, `edit_participant`), payloads `{record}`. A `system`
"Token has expired" event triggers a ValidNation `POST /api/auth/refresh` and
reconnect. The `/api/broadcast` path in `endpoints.txt` is this library's
broadcast-endpoint construction targeting the Supabase host — **not** a
ValidNation REST endpoint.

---

## 12. Other canvasser-facing reads/writes (misc)

All [R]; owner: `audit/endpoint-inventory.md` §6, `audit/earnings-account-misc.md`.

### 12.1 Project selection & shift reads

- **`GET /api/selector/project`** — shift-start project selector + project
  recovery after restore; query `assigned_user_ids[]=<uid>`, `statuses=active`;
  also 4-hourly prefetch. Purpose: which projects this worker may clock into.
- **`GET /api/work_shift/`** — recent shifts on the shift home page; fixed
  query `{page:1, size:5, sort_by:'start_time', sort_type:'desc', timezone}`.
- **`GET /api/work_shift/{id}/earning_progress`** — active-shift page; refetch
  on mount, **no polling** (staleTime Infinity). Consumed: `net_hours`,
  `last_interaction_timestamp`, `paid_break_hours_left` — live pay/break
  budget display.
- `GET /api/work_shift/{id}/conversations` — shift conversation list (managers
  see these; a recording-project shift with none looks anomalous).
- `GET /api/work_shift/{id}/short_info` — entity label.

### 12.2 Applications (worker side)

- `GET /api/applications/` — upcoming open projects; query `{page, size,
  sort_by='start_date', sort_type='desc', from_date?, name?,
  project_type='all', type?}`; consumed `{items[], total}`.
- `GET /api/applications/applied` — worker's own applications; consumed
  `{items[], total_count}`.
- `GET /api/applications/{project_id}` — upcoming-project details; consumed
  `id, start_date, end_date, pricing, goal, application_status`.
- **`PUT /api/applications/create`** — worker applies; body exactly
  `{project_id, user_id}`; success cache-patches `application_status:
  'applied'`.
- Manager-side (`/applicants/`, `/approve`, `/reject`): never fired from the
  canvasser role; bodies documented in `audit/earnings-account-misc.md` §3.

### 12.3 Verification — voters & ballots (petition projects)

- `PUT /api/verifications/voter/` `{project_id, infos: SignatoryVoiceForm[]}`
  — manual signatory creation (§6.4 non-voice path).
- Ballots: `GET /api/verifications/ballot/` (drafts), `GET .../ballot/list`,
  `POST /api/verifications/ballot/` (add), `PUT /api/verifications/ballot/`
  (submit), `GET/DELETE /api/verifications/ballot/{ballot_id}`, `PUT
  .../ballot/{ballot_id}/upload-files` (photo upload), `PUT
  .../ballot/upload-batch`, `POST/GET/DELETE .../ballot/pages[/{id}]`.
  Multipart field names for ballot uploads: UNCONFIRMED (SDK-generated).
- Signature review (`/signature/submitted*`, `/valid/*`, exports) is
  manager-facing; `POST /api/verifications/signature/valid/export/` is DEAD.

### 12.4 Emergencies UI

- `GET /api/wake_word_events/` — emergencies list page.
- `GET /api/wake_word_events/{wake_word_event_id}` — emergency details page.

### 12.5 Misc

- `POST /api/upload/` — chat attachment upload (T4 hand-rolled multipart,
  single `file` part); also referenced by ballot import.
- `GET /api/docs/`, `GET /api/docs/{doc_path}` — in-app help content.
- `GET /api/export/{export_job_id}` — export-job status polling (job creation
  endpoints are admin-only).
- `GET /api/projects/`, `GET /api/projects/{id}`, `GET
  /api/projects/{id}/short_info` — prefetch + shared components.
- `GET /api/users/{user_id}/short_info`, `GET
  /api/subcontractor_company/{id}/short_info`, `GET
  /api/coaching_feedback/{id}/short_info` — inline entity labels.

---

## 13. Completeness & coverage notes

**Checklist reconciliation.** `endpoints.txt` (265 paths) is fully reconciled
in `audit/endpoint-inventory.md` §5: 4 paths are not ValidNation REST
endpoints (`/api/sentry` = Sentry tunnel; `/api/broadcast` + `/rest/v1/` +
`/rest/v1/rpc/` = Supabase artifacts, §11), and 30 SDK paths are absent from
endpoints.txt (mostly DEAD declarations + webhooks/docs/health; only
`/api/upload/` is actually sent). Every live endpoint in endpoints.txt is
covered above.

**Endpoints without field-level detail.** `client/types.gen.ts` (all
`*Data`/`*Response` types) and `~/types/schema` (Supabase types) are type-only
and were not recoverable from the source maps. Therefore:

- Full response schemas are confirmed only for fields the app constructs or
  consumes. All mobile-critical requests (auth, shift, sensor, device, audio)
  are fully field-confirmed; the following response areas remain
  **UNCONFIRMED** beyond consumed fields: `/api/account/` extras, signup
  bodies, application/assignment responses, profile/sharing, contracts v2,
  notifications item extras, ballots, wake_word_events, selector/project,
  work_shift non-mobile reads, docs, export.
- Explicitly UNCONFIRMED request shapes: `EarningCreateRequest` (POST
  /api/earnings/, manager), `AssignmentInfoBody`, ballot-upload multipart
  fields, several Supabase RPC input/output composites.
- DEAD declarations (declared in the SDK, zero call sites anywhere) and
  admin/manager-gated endpoints (~180) never fire from the canvasser-facing
  UI. They are inventoried in Appendix A below with their status; per-path
  caller evidence lives in `audit/endpoint-inventory.md` §2 + Appendix A.

**Third-party services.** Only these non-`api.validnation.ai` destinations are
documented by the audits as part of the official pipeline: the Supabase
project (chats, §11), Firebase (FCM push, Remote Config tuning, §7/§10), and
the Sentry tunnel `POST /api/sentry` (crash envelopes relayed via the API
host). Google Maps key usage is static-asset/map-tile loading and is excluded
per scope. Web/asset loading of the Nuxt frontend from CDNs is excluded per
scope.

---

## 14. Known conflicts between sources (audits win)

| Topic | ANALYSIS.md / DESIGN-VALIDNATION.md said | Audit ground truth |
|---|---|---|
| Refresh cadence | "80% TTL" guess (DESIGN §2) | exp − 60 s proactive, single-flight, 30 s pre-request buffer (`audit/auth-session.md` §8) |
| Refresh shape | [H] | JSON `{refresh_token}`, no Authorization header; `access_token` only consumed; no client-side rotation (`audit/auth-session.md` §2) |
| Voice-sample format | "multipart / likely audio/webm" [H] (DESIGN §3) | JSON `{audio_data: base64 Int16-LE PCM, audio_config{...linear16}}`; webm is preview-only (`audit/audio-voice.md` §1) |
| Uploader cadence | "uploader batch 100/60 s" (ANALYSIS.md:111) | event-driven; `UploaderPeriodMs` is dead config; 100 = records/request (`audit/sensors-telemetry.md` §5) |
| Push action names | `silent_upload_work_shift_data`, `silent_force_live_update` (ANALYSIS.md:120) | real actions: `work_shift_upload_data`, `work_shift_end`, `download_and_apply_live_update`, `none`; the `silent_*` strings are notification `type_` values (`audit/endpoint-inventory.md` §4) |
| Device event surface | `shift_end`/`shift_break_event`/`wake_word_event` listed as `device/event/*` types | those are outbox routing labels → finalize_v2 / pause-resume / wake_word_event endpoint (`audit/shift-lifecycle.md` §7) |
| Radio state reporting | "radio state is sent NOWHERE" (ANALYSIS.md:74) | qualified: network `connection_type` rides every GPS reading; wifi/BLE radio on/off still reported nowhere (`audit/sensors-telemetry.md` §3.1) |
| Websockets | "websocket /api/ws (voice verification stream; likely more)" | voice_verification is the ONLY ValidNation WS; other realtime = FCM + Supabase (`audit/endpoint-inventory.md` §3) |
| Profile content | profile carries org/project assignments (DESIGN §2) | no consumer found → UNCONFIRMED (`audit/auth-session.md` §3) |
| `missingSegmentIds` | implied server reconciliation | client-side 50 MB-store eviction report; `/receive` body never parsed (`audit/audio-voice.md` §2.5) |
| `/api/broadcast` | listed as an API path (endpoints.txt) | Supabase realtime-js artifact targeting the Supabase host (`audit/earnings-account-misc.md` §5) |
| Geofence numbers | [H] uncertainty (DESIGN §8) | 50 km fetch / 10 km re-center / 1 km warning / queue of 4 — all Remote-Config defaults (`audit/sensors-telemetry.md` §11) |
| Earnings shapes | [H] (DESIGN §8) | totals-by-rate-type, Branch status, balance, cents amounts, body-less withdraw all resolved (`audit/earnings-account-misc.md` §1) |
| Outbox FIFO | "FIFO" (DESIGN §9) | drain SQL has no `ORDER BY` — strict FIFO UNCONFIRMED, rowid order in practice (`audit/sensors-telemetry.md` §6) |

---

## Appendix A. Declared-but-not-canvasser-sent endpoints (no field detail)

These paths exist in the generated client / `endpoints.txt` but never fire from
the canvasser-facing (mobile worker) UI — they are either **DEAD** (zero call
sites anywhere in the shipped frontend) or reachable only from
admin/manager-role-gated pages (`audit/endpoint-inventory.md` §2 master table,
Appendix A; page `roles` meta). Method+path are [R] from `client/sdk.gen.ts`;
request/response fields are UNCONFIRMED except where §8.3 and
`audit/earnings-account-misc.md` §3/§4/§8/§9 document manager bodies.

| Group | Paths | Status |
|---|---|---|
| Root/meta | `GET /`, `GET /docs`, `GET /health`, `GET /openapi.json` | DEAD |
| Mobile device leftovers | `POST /api/mobile/device/action/data_sync`, `POST /api/mobile/device/action/live_update`, `POST /api/mobile/device/send_event`, `POST /api/mobile/sensor/` | DEAD (likely predecessors of the push-action/batch endpoints) |
| Manager application review | `POST /api/applications/applicants/`, `POST /api/applications/approve`, `POST /api/applications/reject` | admin/manager pages (bodies: `audit/earnings-account-misc.md` §3) |
| Assignments | `GET /api/assignments/{p}/{u}`, `PUT .../info`, `GET .../status-history`, `POST .../contracts/resend` (DEAD) | admin/manager pages |
| Contracts | `GET /api/contracts/`, `GET /api/contracts/{contract_id}` (v1, superseded), `POST /api/contracts/sync`, `POST /api/contracts/terminate`, `POST /api/contracts/w9/send` | DEAD / admin-manager; worker side is read-only v2 (§9.4) |
| Manager payroll actions | `POST /api/earnings/`, `PATCH /api/earnings/{id}/approve`, `PATCH .../manually_completed`, `POST .../pay`, `PATCH .../reject`, `PATCH /api/earnings/account/{user_id}`, `GET /api/earnings/transactions/{t}/short_info` (DEAD) | admin/manager (bodies §8.3) |
| Projects (admin config) | `POST /api/projects/`; per-project: `ballot_template` (GET/PATCH), `ballot_template_pdf`, `canvassing-app-users` (+`import`, `import/latest`; `import/{import_id}` DEAD), `checklist` (GET DEAD; POST/DELETE/PATCH), `coaching_config`, `daily_review` (+`pending_dates`), `dashboard/canvassing/{activity,overview,responses,team,team/{user_id}}`, `dashboard/map/{question_hash}`, `dashboard/map/v2/{map_type}`, `dashboard/signature`, `edit/tabs_status`, `general_info`, `kickoff_notes`, `kpi_config`, `note` (GET DEAD; POST/DELETE), `project_config`, `public_link/` (GET/PATCH DEAD; v2 used), `{link_type}/public_link/`, `recruitment/eligible_contacts`, `recruitment/send_batch`, `tabs_status`, `users/canvassers`, `voter_database`, `zip_list`, `/api/projects/voter_db_column_mapping/` | admin/manager pages; canvasser-reachable project reads (`/api/projects/`, `/{id}`, `/short_info`, `/restricted_areas`) are covered in §5.6/§12.5 |
| Public web pages | `/api/public/projects/dashboard/{public_hash}[...]` (10 dashboard/metadata paths), `/api/public/projects/details/{public_hash}`, `/api/public/sms_redirect/{code}`, `/api/public/upcoming_projects/{hash}` (DEAD) | unauthenticated share/redirect web pages; not part of the worker app flow (`/api/public/subcontractor_company/details/{code}` is covered §9.1) |
| Recruitment | `/api/recruitment/campaigns/` (GET/POST), `by_project/{project_id}`, `{campaign_id}` (GET/PATCH, `pause`, `resume`, `stats`), `/api/recruitment/messages/` (+`{message_id}`, `send_batch`), `/api/recruitment/settings/prompt/editor-metadata`, `preview/build-context`, `preview/generate`, `preview/render` | admin/manager pages |
| Fraud reports | `GET /api/reports/`, `GET .../{report_id}`, `PATCH .../confirm`, `PATCH .../discard`, `GET .../view_data` | admin/manager pages; worker impact is indirect (`under_review` earning state, §8.1) |
| Selectors (admin dropdowns) | `/api/selector/canvassing/{apps,canvassers,prefixes,surveys}`, `/api/selector/{client,contract_adjustment/templates,fips/counties,recruitment/campaigns,subcontractor_company,timezone,users}`, `/api/selector/staffing_contacts/{additional_languages,cities,grades,leaderships,levels,military_statuses,projects,relationships,remotes,states}`, `/api/selector/{project_id}/regions` | admin/manager pages; canvasser-live `/api/selector/project` is covered §12.1 |
| Staffing contacts | `/api/staffing_contacts/` + `refer`, `reset_counters_batch`, `upload_file`, `{email}` (+ `clear_sms_suppression`, `clear_suppression`, `interactions`, `note/`, `note/remove`, `reset_counters`, `resume_recruitment`, `set_email_unsubscribe`, `set_sms_suppression`, `stop_recruitment`), `{file_import_id}/check_file_import_status` | admin/manager pages |
| Subcontractor companies | `/api/subcontractor_company/` (GET/POST), `{id}` (+ `edit` GET/PATCH, `note` POST/DELETE, `sign_up_code/regenerate`, `sign_up_url_enabled`, `status`, `subcanvassers/`) | admin pages (`/{id}/short_info` label is shared, §12.5) |
| System | `GET /api/system/dashboard/{tab}`, `GET /api/system_settings/`, `PUT /api/system_settings/{general_recruitment,project_recruitment,prompt,recruitment_analytics,throttling,urgency_presets}` | admin pages |
| Users (admin) | `POST /api/users/`, `POST /api/users/export/`, `GET /api/users/export/{job}` (DEAD), `POST /api/users/hiring/checkmark`, `POST /api/users/hiring/dashboard`, `GET/PUT /api/users/{user_id}`, `PATCH .../block`, `PATCH .../unblock`, `DELETE .../canvasser_application/{section}/`, `POST .../checkr/request`, `GET .../dashboard/`, `GET .../devices/` (DEAD), `PUT .../note/`, `DELETE .../note/remove`, `GET/PUT .../projects/`, `DELETE .../projects/{project_id}`, `DELETE/PUT .../projects/{project_id}/note/`, `PUT .../projects/{project_id}/update`, `PUT .../registered_party/` | admin/manager pages (`/{user_id}/short_info` label is shared, §12.5) |
| Signature review | `/api/verifications/signature/submitted/` (+`{id}`, `export/`), `/api/verifications/signature/valid/{id}`, `POST /api/verifications/signature/valid/export/` (DEAD) | manager pages |
| Work-shift review | `POST /api/work_shift/export/`, `GET /api/work_shift/{id}`, `GET .../canvassing_app_stats` (DEAD), `POST .../export/`, `GET .../interactions` (DEAD), `POST .../interactions/exclusions`, `POST .../recalculate/`, `PATCH .../review`, `GET .../review_data`, `GET .../route_with_interactions` | admin/manager pages; canvasser shift reads covered §12.1 |
| Conversations & coaching | `GET /api/conversations/`, `GET .../{conversation_id}`, `GET /api/coaching_feedback/`, `GET .../{feedback_id}` | admin/manager pages (`/short_info` label is shared, §12.5) |
| Canvassing-interaction imports | `GET /api/canvassing-interaction-imports/`, `POST .../upload`, `GET .../{import_id}` | admin pages |
| Misc DEAD | `GET /api/account/referral_code` (referral code read from `/api/account/` instead), `GET /api/verifications/voice/` | DEAD |
| Server-side webhooks | `POST /api/webhooks/{branch,checkr,sign_well,twilio/inbound,twilio/status-callback,mailersend/bulk-email,mailersend/inbound,mailersend/single-email}` | server-to-server handlers that appear in the generated client; never client-called |
