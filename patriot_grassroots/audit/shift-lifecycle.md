# Audit: Shift lifecycle & device events — `com.patriotgrassroots.validnation` v1.0.0 (114)

Scope: `work_shift/generate|pause|resume|finalize_v2|status_v2`, cross-device conflict,
`device/update_info`, `device/event/send|batch_send` (full event-type catalog),
`notifications/token`, wake-word event, and the process-death/restart (app-exit-reason) flow.

Sources: `/tmp/vn_src/` (complete original frontend source from shipped source maps; cites
like `composables/mobile/shift/useMobileShift.ts:138`), `patriot_grassroots/java/sources/...`
(decompiled native plugins), `client/sdk.gen.ts` (generated API client). Caveats:
`client/types.gen.ts` and `native_plugins/*/src/definitions.ts` are type-only files that were
NOT recovered from the source maps (types are erased at compile time), so exact TypeScript
type *names* are unrecoverable; every field below is confirmed from the code that constructs
or consumes the payload. Anything not confirmable is marked **UNCONFIRMED**.

Resolves DESIGN-VALIDNATION.md [H]/[R]-pending items as noted inline ("resolves [H]").

---

## 0. Transport shared by every message below

All mobile calls go through `doNativeRequest` (`utils/mobile/doNativeRequest.ts:41-128`)
on top of `CapacitorHttp` (native HTTP, bypasses webview CORS):

- URL = `useRuntimeConfig().public.apiBaseURL` + path → `https://api.validnation.ai/...`
  (`doNativeRequest.ts:53,58`).
- Headers (`doNativeRequest.ts:59-63`): `Content-Type: application/json` on non-GET;
  `Authorization: Bearer <jwt>` — `token` computed as `` `Bearer ${rawToken}` ``
  (`composables/auth/useAuthState.ts:106-109`). No other custom headers.
- Timeouts: `connectTimeout: 15000`, `readTimeout: 15000` (`doNativeRequest.ts:64-65`).
- Non-200 → throws `createError({statusCode, message: data.detail || data.message || ...})`
  (`doNativeRequest.ts:85-89`).
- 401 → one token refresh + single retry (`doNativeRequest.ts:102-112`); if the retried
  request still 401/403s and the app is foregrounded → "Session expired" toast + sign-out
  (`doNativeRequest.ts:116-124`); in background it just throws (data stays queued).
- Network-connectivity failure → `setOfflineFlag()`; GETs fall back to a cached response if
  one exists, successful GETs populate that cache (`doNativeRequest.ts:76-99`).
- Requests short-circuit with a synthetic 401 when the session is unrecoverable (logged out)
  (`doNativeRequest.ts:48-50`).

---

## 1. `POST /api/mobile/work_shift/generate` — clock-in (resolves [H]: exact body)

Wrapper: `mutations/mobile/generateWorkShiftId.ts:5-14` (endpoint also in
`client/sdk.gen.ts:1551`). Constructed in `registerWorkShift`,
`composables/mobile/shift/useMobileShift.ts:134-148`.

**Trigger (user action):** worker taps Start on the shift page (`pages/shift/index.vue:100`
→ `useTrackingController.start()`, `useTrackingController.ts:230-286`). Sequence before this
POST: permission gate (`ensurePermissions`, `useTrackingController.ts:150-158`), project
loaded, audio-session check, then `requestNewWorkShiftSession` (§6) which ends in
`registerWorkShift`.

**Full request body** (`useMobileShift.ts:138-144`):

```json
{
  "device_id": "<capacitor-udid string; stores/mobile/deviceInfo.ts:55>",
  "project_id": "<server project uuid selected by worker>",
  "start_time": "<local ISO-8601, new Date().toISOString()>",
  "state_payload": { "...": "see below" },
  "time_zone": "<IANA tz, e.g. America/Anchorage — Intl.DateTimeFormat().resolvedOptions().timeZone, stores/mobile/deviceInfo.ts:49>"
}
```

**`state_payload`** — built by `getDeviceStatePayload()`
(`utils/mobile/deviceInfoUtils.ts:12-33`) and deep-snake-cased
(`utils/toSnakeCase.ts:21-29`). Confirms DESIGN §4 `state_payload` hypothesis — resolves [H]:

```json
{
  "permissions": {
    "wifi":   "<bool — permission grant only, NOT radio state; deviceInfoUtils.ts:19-24>",
    "ble":    "<bool>",
    "gps":    "<bool — perms.granted.value.location>",
    "motion": "<bool>"
  },
  "battery": {
    "battery_level": "<int 0-100; Math.round((level ?? -0.01)*100) → -1 when unavailable; deviceInfoUtils.ts:6-10>",
    "is_charging": "<bool>"
  },
  "config": { "...": "full active tracking-config snapshot, snake_cased ({...config}, deviceInfoUtils.ts:28)" }
}
```

`config` is the entire `AppConfig` object (`types/database/config.ts:1-40`), snake_cased —
30 keys, values possibly overridden by Firebase Remote Config: `location_distance_filter`,
`location_buffer_size` (60), `location_flush_interval_ms` (30000), `location_android_priority`,
`location_desired_accuracy`, `location_pauses_automatically`, `location_activity_type`,
`ble_scan_duration_ms`, `ble_scan_interval_ms`, `ble_scan_allow_duplicates`,
`wifi_scan_interval_ms`, `physical_sensor_buffer_size`, `physical_classifier_buffer_size`,
`motion_activity_interval_ms`, `physical_sensor_window_ms`, `uploader_batch_size` (100),
`uploader_period_ms` (60000 — see §11, unused), `vad_enabled`, `vad_max_buffer_size`,
`vad_max_segment_seconds`, `vad_model_threshold`, `vad_gate_wake_word`,
`vad_wake_word_hangover_ms`, `geofence_fetch_radius_km`, `geofence_refresh_distance_km`,
`geofence_warning_distance_km`, `geofence_restriction_queue_size`, `audio_cache_ttl_days`,
`audio_upload_batch_size`.

**Response fields consumed:** `work_shift_id` (becomes the session id, persisted to
Preferences key `current_work_shift_id`) and `start_time` — the *server-canonical* start
time re-initializes the local timer (`useMobileShift.ts:146-147`). Any other response
fields: **UNCONFIRMED** (types.gen.ts missing).

**Offline/failure:** no offline path — shift start hard-requires network; a throw aborts
`start()`, stops any started modules and runs `cancelWorkShiftSession()`
(`useTrackingController.ts:263-285`).

**After generate succeeds** (still in start flow): remote-config refresh
(`useTrackingController.ts:168-172`), `POST /api/mobile/device/update_info` (§7,
`useTrackingController.ts:180-182`), background-fetch armed (15-min minimum interval,
`composables/mobile/backgroundFetch.ts:3-27`), tracking modules start, clean-shutdown flag
re-armed to "unclean-assumed" (`useTrackingController.ts:198-200`).

---

## 2. `GET /api/mobile/work_shift/status_v2` — state sync (no fixed poll cadence)

Wrapper: `mutations/mobile/getWorkShiftStatus.ts:5-13` (GET, **no query params, no body**;
endpoint `client/sdk.gen.ts:1614`). Errors are swallowed → returns `null`.

**Response fields consumed** (only these four; anything else **UNCONFIRMED**):
`device_id`, `work_shift_id` (`useMobileShift.ts:102-106`), `project_id`
(`useMobileShift.ts:220,237-254`), `start_time` (`useMobileShiftTimer.ts:143-144`).

**Call sites / cadence** — there is NO periodic status_v2 loop; it fires on:
1. Shift start, pre-generate conflict check (`useMobileShift.ts:158`).
2. Session restore (app launch, start-error recovery) (`useMobileShift.ts:215`).
3. `checkAndStopIfClosed()` (`useTrackingController.ts:552-567`) — invoked (a) every
   **5 minutes** by the app-level `useTimeoutPoll(..., 5*60*1000)` (`app.vue:78-100`), and
   (b) on every **app resume** (`plugins/stateChangeListeners.ts:48-56`). If the server no
   longer reports a shift for this device (`shiftExists === false`), the local shift is
   gracefully stopped (`stop()` → §5 finish path) — this is how a manager-side or
   other-device finalization propagates.
4. Timer fallback for a lost local start time (`useMobileShiftTimer.ts:135-148`).

What it syncs: active-on-another-device detection, unfinished-shift adoption, project
recovery (`recoverWorkShiftProjectIfNeeded` re-fetches the project via
`findSelectorProjectByIdViaList` and rewrites local storage if the server's `project_id`
differs, `useMobileShift.ts:237-254`), and remote-stop detection.

---

## 3. `POST /api/mobile/work_shift/pause` and `/resume` — breaks (outbox-routed)

Wrappers: `mutations/mobile/pauseWorkShift.ts:5-12`, `resumeWorkShift.ts:5-12`
(endpoints `client/sdk.gen.ts:1572,1593`; sdk doc comments describe server-side span
bookkeeping keyed on `button_pressed_time`).

**Trigger (user action):** break / end-break buttons (`pages/shift/[id].vue:197-199` →
`useTrackingController.pause()/resume()`, `useTrackingController.ts:288-401`).

These do NOT POST directly. Each button press enqueues an outbox row of type
`shift_break_event` (`useMobileShift.ts:260-288`):

```json
{ "type": "pause" | "resume", "work_shift_id": "<id>", "button_pressed_time": "<ISO-8601>" }
```

then kicks `syncAndUploadWorkShiftData()` fire-and-forget (remote-config refresh + uploader
tick). The uploader (`utils/mobile/uploadShiftBreakEventBatch.ts:17-41`) drains these rows
**in row-ID order** (causality), strips `type`/`_rowId`, and POSTs the remainder:
- `type:'pause'` → `POST /api/mobile/work_shift/pause`, body
  `{ "work_shift_id": "...", "button_pressed_time": "..." }`
- `type:'resume'` → `POST /api/mobile/work_shift/resume`, same body.

**Response:** nothing consumed.
**Failure policy:** HTTP 400/404 → the offending row is *dropped* (event no longer
applicable) and draining continues (`uploadShiftBreakEventBatch.ts:26-34`); any other error
aborts the batch, row stays, retried next tick. Local pause bookkeeping rolls back if the
pause flow fails partway (`useTrackingController.ts:88-114,299-318`); on pause failure a
`pause_stop_failed` device event is emitted (§8).

---

## 4. `POST /api/mobile/work_shift/finalize_v2` — clock-out (array body; outbox drain FIRST)

Wrapper: `mutations/mobile/uploadShiftEnd.ts:9-18` (endpoint `client/sdk.gen.ts:1530`).
**Body is a JSON array** of `MobileWorkShiftFinalizeRequest` — resolves [H].

**Triggers:**
- Worker taps End shift (`pages/shift/[id].vue:172-181` → `useTrackingController.stop()`,
  `useTrackingController.ts:523-550` → `finishWorkShiftSession`, `useMobileShift.ts:290-314`).
- Remote stop detected by `checkAndStopIfClosed` (§2) or `work_shift_end` silent push
  (`plugins/notifications.ts:163-166`).
- Cross-device interrupt (§6) — direct call, bypasses the outbox.
- Aborted start (`cancelWorkShiftSession`, `useMobileShift.ts:316-335`).

**Enqueue shape** (normal finish/cancel, `useMobileShift.ts:298-304,321-326`):

```json
{
  "work_shift_id": "<id>",
  "end_time": "<ISO-8601>",
  "state_payload": { "...": "same shape as generate §1 — fresh permissions/battery/config snapshot" }
}
```

**Drain-before-finalize ordering (resolves [H] — confirmed, and stronger than the design
doc states):**
1. `finishWorkShiftSession` enqueues the `shift_end` row, then runs
   `uploader.tick({ showProgress: true, limitIterations: false })` — an *unlimited* drain
   (`useMobileShift.ts:306-310`; unlimited ticks never ride on a capped in-flight tick,
   `useUploader.ts:211-224`).
2. Inside a tick, `shift_end` is drained strictly **after** every other payload type
   (`useUploader.ts:178-193`).
3. Per-shift deferral: `uploadShiftEndBatch` (`useUploader.ts:43-74`) checks the outbox for
   any remaining non-`shift_end` rows with the same `work_shift_id`
   (`json_extract(payload,'$.work_shift_id')`, `utils/useDb.ts:218-233`). Only when none
   remain is the row uploaded with **`data_complete: true`** and deleted; otherwise it is
   deferred (`data_complete` initialized `false` on the outgoing object,
   `useUploader.ts:44,57-66`).
4. Note: `data_complete` covers the SQLite `payloads` outbox only. Cached *audio* uploads
   (`/api/canvasser_voice/cached_receive`) run as the tick's tail, AFTER the shift_end drain
   (`useUploader.ts:195-197`) — a `data_complete:true` finalize can still be followed by
   cached-audio uploads.

**Final wire body:** `[{ "work_shift_id", "end_time", "state_payload", "data_complete": true|false }]`
— an array because one tick can finalize several shifts. Failure → nothing deleted, retried
next tick (`useUploader.ts:68-71`); finish logs "will retry on the next sync"
(`useMobileShift.ts:308-309`). **Response:** nothing consumed.

---

## 5. Cross-device conflict handling (resolves [H]: first-class UI state confirmed)

Detection: `transformToStatusForCurrentDevice` compares `status_v2.device_id` against the
local UDID (`useMobileShift.ts:93-110`).

- **At start** (`requestNewWorkShiftSession`, `useMobileShift.ts:150-183`): local
  `current_work_shift_id` set → `WorkShiftRunningError` (recovered via restore). Server
  shift on *this* device → adopt id + throw `WorkShiftRunningError`. Server shift on
  *another* device → modal Dialog "The work shift is running on another device..."
  (`useMobileShift.ts:112-119`); on confirm it **directly** POSTs
  `finalize_v2` with `[{ "work_shift_id", "end_time": <now ISO>, "data_complete": null }]`
  — no `state_payload`, literal `data_complete: null` (`useMobileShift.ts:122-124`) — then
  proceeds to `generate`. On cancel → start aborted.
- **Mid-shift:** 5-min/resume `status_v2` check stops the local shift when the server no
  longer lists it (§2.3).

---

## 6. `POST /api/mobile/device/update_info` — device registration/telemetry (resolves [H])

Wrapper: `mutations/mobile/uploadDeviceInfo.ts:5-14` (endpoint `client/sdk.gen.ts:1428`).
Builder: `utils/mobile/updateDeviceInfo.ts:30-48`. Full body:

```json
{
  "model": "<Device.getInfo().model>",
  "device_id": "<UDID>",
  "name": "<device name>",
  "is_complete_sensors": "<bool — accelerometer && gyroscope && magnetometer && rotationVector, stores/mobile/deviceInfo.ts:53-54>",
  "is_root": "<bool — @capacitor-community/device-security-detect isJailBreakOrRooted; deviceInfo.ts:50>",
  "os_version": "<e.g. 15>",
  "permission_gps":    "<bool>", "permission_ble": "<bool>",
  "permission_wifi":   "<bool>", "permission_motion": "<bool>",
  "push_permission_granted": "<bool — FCM OS permission>",
  "push_notifications_enabled": "<bool — in-app opt-out inverted>",
  "platform": "<android|ios|web>",
  "software_version": "<'v<web_version> (<native build>)', deviceInfo.ts:67>",
  "timezone": "<IANA tz — note: 'timezone' here vs 'time_zone' in generate>"
}
```

**Triggers:** (a) every 5 min via the app-level poll (`app.vue:87-89`); (b) once at every
fresh shift start, before modules start (`useTrackingController.ts:180-182`); (c) lazily,
single-flight, before the first device event of a session (`ensureDeviceLinked`,
`utils/mobile/ensureDeviceLinked.ts:25-33` — the backend 403s events from an unlinked
device). **Response:** nothing consumed. On logout the link is torn down via
`POST /api/mobile/device/unlink {device_id}` (`mutations/mobile/unlinkUserFromDevice.ts:9-16`;
called from `utils/mobile/unlinkDeviceFromUser.ts:7-29`).

---

## 7. `POST /api/mobile/device/event/send` and `/batch_send` — event catalog

Wrappers: `mutations/mobile/sendDeviceEvent.ts:12-32` (endpoints
`client/sdk.gen.ts:1363,1342`; sdk doc: "Send mobile device event(s) to clickhouse").

**Envelope** (every event, built by `composePayload`, `utils/mobile/mobileEvents.ts:9-28`;
payload keys deep-snake-cased):

```json
{
  "device_id": "<UDID>",
  "created_at": "<ISO-8601>",
  "event_type": "<see catalog>",
  "payload": { "...": "per event, snake_cased" } | null
}
```

`send` takes the envelope directly; `batch_send` takes
`{ "device_id": "...", "events": [<envelope>, ...] }` (up to `UploaderBatchSize`=100 per
batch, `useUploader.ts:84,103`). **Responses:** nothing consumed.

**Routing** (`mobileEvents.ts:43-72`): online+authed → `ensureDeviceLinked()` then direct
`send`; on failure/offline/logged-out → enqueue as `mobile_event` outbox rows, drained by
the uploader via `batch_send` (`useUploader.ts:76-85,108`). Caveat: `addPayload` **drops**
rows when no shift is active (`utils/useDb.ts:44-48`), so an event that fails direct-send
outside a shift is lost.

**Event-type catalog** (all confirmed call sites; the `MobileEventType` TS enum itself is
UNCONFIRMED — types.gen.ts missing):

| `event_type` | Trigger | Wire payload (after snake-casing) |
|---|---|---|
| `app_state` | Every app foreground/background toggle (`plugins/stateChangeListeners.ts:58-63`) | `{state: 'foreground'\|'background'}` |
| `data_upload` | Start of every uploader tick, before drains (`useUploader.ts:176`) | `{timestamp: <epoch ms>, data: {max_id: <int outbox high-water mark>}}` |
| `device_state_sync` | Start of every uploader tick (`useUploader.ts:135-146,171`) | full `state_payload` (§1: permissions/battery/config) **plus** `resource_snapshot` (§9) |
| `app_termination` | Once per process launch, before shift restore (§9) | `{platform, reason, was_graceful_marker, was_clean_shutdown, work_shift_id, was_paused, last_resource_snapshot}` |
| `restored_after_termination` | Shift restored after process death (§9) | `{was_paused, work_shift_id, project_id, permissions:{...}, battery:{...}}` (config stripped, `useTrackingController.ts:486-488`) |
| `tracker_state_divergence` | Watchdog finds live modules/native GPS watchers while JS believes tracking stopped — checked on foreground, after background fetch, after paused-restore (`useTrackingController.ts:68-86,576-597`, `stateChangeListeners.ts:69-71`) | `{alive_modules: string[], native_watcher_count: int}` — resolves [H] re `aliveModules` (wire key is snake_case) |
| `pause_stop_failed` | Pause failed: modules wouldn't stop (`{stage:'module_stop', failed: string[]}`) or pause bookkeeping threw (`{stage:'record_pause', error: string}`) (`useTrackingController.ts:88-114,323`) | as shown |
| `audio_cache_cleanup` | App resume; only when the audio cache had items or errored (`utils/mobile/uploadAudioNative.ts:19-33`) | `{audio_paths: string[]}` or `{error, audio_paths, indices}` |
| `live_update_downloaded` / `live_update_applied` | OTA bundle lifecycle (`composables/mobile/updates/useMobileLiveUpdates.ts:192,220`) | `{bundle_id: string}` |

**Correction to ANALYSIS.md/DESIGN §7:** `shift_end`, `shift_break_event` and
`wake_word_event` are NOT sent to these endpoints — they are outbox routing labels
(`types/mobile/trackingSensors.ts:11-23`) that map to `finalize_v2` (§4), `pause`/`resume`
(§3) and `/api/canvasser_voice/wake_word_event` (§8) respectively. `device_state_sync` is
not fixed-period; it rides uploader ticks (§11 drivers).

---

## 8. `POST /api/canvasser_voice/wake_word_event` — wake word (NOT a device event)

Wrapper: `mutations/mobile/sendWakeWordEvent.ts:5-12` (endpoint `client/sdk.gen.ts:631`).
Constructed in `composables/mobile/audio/useWakeWordHandler.ts:14-21` when the native
AudioManager fires `wakeWordDetection` (`AudioManager.java:114-158`):

```json
{
  "id": "<uuid v4, generated in JS>",
  "work_shift_id": "<id>",
  "device_id": "<UDID>",
  "timestamp_ms": "<int, detection time>",
  "gps_point": {
    "latitude": 0.0, "longitude": 0.0,
    "accuracy": 0.0, "altitude": 0.0, "altitude_accuracy": 0.0,
    "timestamp": "<ISO — converted from ms, useWakeWordHandler.ts:12>"
  } | null
}
```

(gps_point fields from `AudioManager.java:131-139`; null when no fresh fix.)
**Policy:** written to the outbox first, then direct-send; success deletes the row,
failure leaves it for the uploader (which drops rows on 400/404, retries otherwise —
`useUploader.ts:87-100`). A raw audio clip is uploaded separately, joined by `id`
(`useWakeWordHandler.ts:33-48`). **Response:** nothing consumed.

---

## 9. `POST /api/mobile/notifications/token` (+ DELETE) — FCM

Wrapper: `mutations/mobile/uploadPushNotificationsToken.ts:5-13` (endpoints
`client/sdk.gen.ts:1449,1466`). Body: `{ "device_id": "<UDID>", "token": "<FCM token>" }`.

**Triggers:** (a) the 5-min app poll re-registers whenever `isRegistered` is false
(`app.vue:91-97` → `requestAndRegisterPushNotifications`, `plugins/notifications.ts:48-95` —
requires OS permission granted and no in-app opt-out); (b) FCM `tokenReceived` listener
(token refresh) (`plugins/notifications.ts:123-152`). **Response:** sets `isRegistered`;
nothing else consumed.

**Opt-out:** `DELETE /api/mobile/notifications/token?device_id=...`
(`mutations/mobile/unregisterPushNotificationsToken.ts:5-14`, called from
`composables/mobile/useMobilePushNotifications.ts:81-104`) followed by local FCM token
deletion.

---

## 10. Process death & restart (app-exit-reason flow; resolves DESIGN gate 5)

**During life:** the native plugin snapshots resource pressure to SharedPreferences
(`AppExitReasonPrefs/last_resource_snapshot`) on `onStop`, `onDestroy`, and
`onTrimMemory(level >= 15)` (`AppExitReason.java:196-230`). Snapshot shape
(`AppExitReason.java:39-83`; snake_cased on the wire):
`{sampled_at: <epoch ms>, battery: {low_power_mode: bool, level: int 0-100|-1, is_charging: bool},
memory: {trim_level_max: int, available_bytes, total_bytes, threshold_bytes, low_memory: bool},
thermal: {state: int|-1}}`. The JS side also fetches this snapshot on every uploader tick
and attaches it to `device_state_sync` (`useUploader.ts:135-146`).

**Clean/unclean marker:** Preferences key `session_clean_shutdown` — cleared at shift start
("unclean-assumed"), set on graceful stop/pause (`useMobileShift.ts:41-43,79-85`;
`useTrackingController.ts:198-200,319,537`).

**On next launch** — ordering enforced by `middleware/05.mobileInit.global.ts:23-33`:
`initialize()` → `reportLastExitReason()` (MUST precede restore; once per process, gated by
both a JS flag and the native `claimLaunchReport` one-shot, `AppExitReason.java:123-129`) →
`restoreAfterTermination()`.

1. **`app_termination` event** (`useTrackingController.ts:409-467`): reads
   `ActivityManager.getHistoricalProcessExitReasons` (API 30+; `supported:false` below),
   retrying once after 600 ms if empty, `max: 1` (only the most recent record)
   (`AppExitReason.java:131-171`). Wire payload:
   `{platform:'android', reason: {reason: <mapped string>, raw_code: int, description,
   timestamp: epoch ms|null, importance: int, pid: int}|null, was_graceful_marker: null
   (iOS-only, always null on Android), was_clean_shutdown: bool|null (null when no shift was
   active), work_shift_id: string|null, was_paused: bool, last_resource_snapshot: <above>|null}`.
   Reason mapping (`AppExitReason.java:85-116`): 1 `exit_self`, 2 `signaled`, 3 `low_memory`,
   4 `crash`, 5 `crash_native`, 6 `anr`, 7 `initialization_failure`, 8 `permission_change`,
   9 `excessive_resource`, 10 `user_requested`, 11 `user_stopped`, 12 `dependency_died`,
   13 `other`, else `unknown`.
2. **Restore** (`useTrackingController.ts:469-521`): syncs/uploads first (skipped when
   offline), re-checks `status_v2`, recovers the project if needed, emits
   **`restored_after_termination`** (§7), then: if the shift was paused → re-arm
   clean-shutdown, re-show break notification, stay stopped; else → restart tracking modules
   and resume tracking. The `session_clean_shutdown` flag is consumed (reset) after
   reporting (`useTrackingController.ts:463-466`).

---

## 11. Offline outbox & uploader mechanics

Schema (DB v2+, `utils/dbManager.ts:63-70`; DB name `<environment>-internal-data`):
`payloads(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, data_type TEXT NOT
NULL, payload TEXT NOT NULL)` + index on `data_type` — resolves [H] (DESIGN §9 schema).
Rows are written by `addPayload` (`utils/useDb.ts:35-60`) which **silently drops** data when
the DB isn't initialized, no user is logged in, or **no shift is active**
(`useDb.ts:40-52`).

Outbox `data_type` values (`types/mobile/trackingSensors.ts:1-23`): the 7 sensor types
(`gps, wifi, ble, accelerometer, gyroscope, magnetometer, motionActivity`) →
`/api/mobile/sensor/batch_upload`; `shift_break_event` → pause/resume; `shift_end` →
finalize_v2; `mobile_event` → event/batch_send; `wake_word_event` → wake_word endpoint.

Tick (`useUploader.ts:148-207`): skip when logged out; skip + set offline flag when
`Network.getStatus()` is disconnected; then `device_state_sync` event → `data_upload`
event → drain all non-shift_end types in parallel (batches of `UploaderBatchSize`=100, up
to 50 iterations/type when capped) → drain `shift_end` (per-shift deferral, §4) → audio
tail. Rows are deleted only after their upload succeeds.

**Tick drivers (no fixed-period foreground timer):** background-fetch with
`minimumFetchInterval: 15` minutes, `stopOnTerminate: true`
(`composables/mobile/backgroundFetch.ts:3-27`, armed at shift start
`useTrackingController.ts:184-190`); app foregrounding, throttled to once per 15 min while
tracking (`plugins/stateChangeListeners.ts:13,73-81`); pause/resume
(`useMobileShift.ts:269,284`); finish/cancel (`useMobileShift.ts:307,327`); manual
sync-now (`pages/shift/[id].vue:216`); silent push `work_shift_upload_data` and
`work_shift_end` (`plugins/notifications.ts:154-169`). Note: `UploaderPeriodMs: 60000`
exists in the config (`types/database/config.ts:22`) but has **no consumer** in the
recovered sources and appears only once — in the defaults object — in the shipped bundle
(`tree/assets/public/_nuxt/BYbP5qv3.js`); treat the "60 s uploader" in ANALYSIS.md as dead
config.

Unsynced-shift detection for UI badging: distinct `work_shift_id`s in the outbox excluding
the current shift (`utils/useDb.ts:314-330`, surfaced via `setUnsyncedShiftIds`).

---

## 12. [H] resolutions summary

- Generate body incl. full `state_payload` (permissions{bwifi,ble,gps,motion} = permission
  booleans only, battery{battery_level,is_charging}, 30-key config snapshot) + `time_zone` —
  **resolved** (§1).
- "Drain outbox FIRST, then finalize_v2 with data_complete:true" — **resolved**, stronger:
  per-shift deferral inside the uploader + `shift_end` always drained last; interrupt path
  sends `data_complete: null` (§4, §5).
- update_info exact field set incl. `is_root` and `permission_*` — **resolved** (§6).
- Device event surface — **resolved with corrections**: `shift_end`/`shift_break_event`/
  `wake_word_event` never hit `device/event/*`; wire key for divergence is `alive_modules`
  (§7).
- Outbox schema `payloads(id, user_id, data_type, payload)` — **resolved** (§11).
- Gate 5: `app_termination` → `restored_after_termination` sequence — **resolved**, with
  exact ordering guard and once-per-process semantics (§10).

## 13. Open / UNCONFIRMED items

- Exact response schemas for all endpoints above (types.gen.ts unrecovered); only consumed
  fields are confirmed: generate→`{work_shift_id,start_time}`, status_v2→`{device_id,
  work_shift_id, project_id, start_time}`.
- The full server-side `MobileEventType` enum (call-site catalog in §7 is complete for this
  build but the server may accept more).
- Whether the 5-min `useTimeoutPoll` fires immediately on mount (VueUse default) — affects
  only first-update_info timing, not cadence.
