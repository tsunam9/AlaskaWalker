# Patriot Grassroots analysis — `com.patriotgrassroots.validnation` v1.0.0 (114)

White-label build of the **ValidNation** field-workforce platform, branded
"Patriot Grassroots". **Capacitor hybrid** (Nuxt/Vue web build readable in
`tree/assets/public/_nuxt/*.js` with source maps), 4 dexes, minSdk 23,
targetSdk 36. Stock APKs in `stock/`, frozen baseline in `BASELINE.md`,
full endpoint dump in `endpoints.txt`. **2026-09-19: the complete original
frontend source tree (2,518 files) was recovered from the shipped source
maps** (`tree/assets/public/_nuxt/*.js.map`); six line-cited audit files in
`patriot_grassroots/audit/` (index: `audit/README.md`) are ground truth
where they correct this file — corrections applied inline below.

**Role in this project: the worker time-clock (Connecteam equivalent).**

## Feature surface

Time-clock core confirmed, embedded in a much larger workforce-monitoring
platform:

- **Shifts**: `POST /api/mobile/work_shift/generate` (clock-in,
  `{device_id, project_id, start_time, state_payload, time_zone}`),
  `/pause` + `/resume` (breaks, with `allowed_break_minutes_per_hour`
  budgets), `/finalize_v2` (clock-out), `/status_v2` (state sync).
  Cross-device conflict detection ("running on another device").
- **GPS breadcrumbs**: buffered sensor records posted to
  `POST /api/mobile/sensor/batch_upload`; sensor types `gps, wifi, ble,
  accelerometer, gyroscope, magnetometer, motionActivity`. GPS record shape:
  `{latitude, longitude, accuracy, altitude, altitude_accuracy, timestamp,
  speed, bearing, simulated, connection_type}` — note the honest `simulated`
  flag (mock-location detection exists; confirmed 2026-09-19 as verbatim
  Android `Location.isFromMockProvider()`, `audit/sensors-telemetry.md`
  §3.1).
- **Geofencing**: per-project restricted-area polygons
  (`/api/projects/{id}/restricted_areas`, 50 km fetch radius, 1 km warning).
- **Device telemetry**: `/api/mobile/device/event/send|batch_send`
  (`app_state`, `data_upload`, `device_state_sync`, `app_termination`,
  `restored_after_termination`, `tracker_state_divergence`,
  `pause_stop_failed`, `audio_cache_cleanup`, `live_update_*` — corrected
  2026-09-19 per `audit/shift-lifecycle.md` §7: `shift_end`,
  `shift_break_event` and `wake_word_event` are outbox routing labels that
  map to `finalize_v2`, `pause`/`resume` and
  `/api/canvasser_voice/wake_word_event` respectively; they never go to
  `device/event/*`), `/api/mobile/device/update_info`,
  `/api/mobile/notifications/token` (FCM).
- **Scope note (revised 2026-09-18, second pass)**: voice-sample enrollment
  and worker-side earnings/payroll are **in scope** for the reimplementation
  (see `docs/UNIFIED-APP-PLAN.md` §2). Key facts:
  - Voice sample (`POST /api/account/voice_sample/`) is server-mandated
    onboarding (`alerts.banner_alert: "record_voice_sample"` + hiring
    checkmark `voice_sample_recorded`), consumed server-side to verify the
    worker's voice against shift audio. Wire format confirmed 2026-09-19
    (`audit/audio-voice.md` §1): **JSON, not multipart** —
    `{audio_data: base64 raw Int16-LE PCM, audio_config:{sample_rate
    (device-dependent, ~48000), channels, bits_per_sample,
    encoding:"linear16"}}`; >30 s client-side minimum; the RecordRTC webm
    blob is local preview only and never uploaded. The shift-start screen
    does NOT check for it client-side; shift start gates on: assigned
    project + location/motion/BLE/WiFi permissions (+ mic ONLY when the
    project's `audio_recording_config.permission != "no_recording"`).
  - Continuous shift audio is per-project (`full_recording` /
    `no_recording` / `full_recording_with_restricted_area`; admin UI labels
    them "Full Note-taking" / "No Note-taking" / "Note-taking With
    Restricted Areas"). On `no_recording` projects, zero audio is the
    normal server-visible state. Restricted-area mode = record everywhere
    except admin-configured restricted ZIP polygons
    (`/api/projects/{id}/restricted_areas`); enforced client-side per VAD
    segment — segments whose GPS fix lands in a zone are deleted on-device
    (`releaseSegments`) and never uploaded, and in this mode segments with
    NO valid GPS fix are dropped too (`AudioManager.java:455` fail-closed).
    On recording projects the server accounts for audio: zero conversations,
    `data_complete` at `finalize_v2`, `alive_modules` (snake_case on the
    wire) in `tracker_state_divergence` events. Corrected 2026-09-19 per
    `audit/audio-voice.md` §2.5: `missingSegmentIds` in `/receive` plugin
    responses is a CLIENT-side report (segments evicted from the 50 MB
    native store), not server reconciliation — the `/receive` response body
    is never parsed.
  - The `/api/ws/voice_verification/{id}` websocket is the petition
    SIGNATORY verification feature (voters' voices, worker-initiated),
    NOT a worker spot-check. No server-initiated voice challenge exists.
  - Payroll review scores: net hours vs break budgets, `gps_quality`
    (`coverage_pct`, `simulated` mock-GPS, `speed_mismatch_pct`),
    `phone_behaviour`, `surroundings` (BLE/WiFi uniqueness), engagement
    (interaction counts). No audio-presence metric client-side, but
    managers see conversation lists — a recording-project shift with no
    conversations looks anomalous.
  - **Sensor/scanning deep-dive (2026-09-18)**: batch envelope =
    `{record_id(uuid), work_shift_id, device_id, sensor_type, started_at,
    ended_at, sensor_readings[]}`; readings have no per-item time/GPS.
    WiFi reading: `{bssid, ssid, level, isCurrentWifi, capabilities[]}`;
    BLE reading: `{device{deviceId,name,uuids}, rssi, txPower,
    manufacturerData, rawAdvertisement...}` (`allowDuplicates:true`, no
    client dedup). Cadence: ~120 bursts/type/foreground-hour; scans are
    SKIPPED while backgrounded (pocket = GPS-only); radio-off silently
    produces zero records. Radio on/off state itself is still reported
    nowhere and `state_payload.permissions` remain permission booleans only
    — but network *connection type* IS uploaded: every GPS reading carries
    `connection_type` (`wifi|cellular|none|unknown`, corrected 2026-09-19
    per `audit/sensors-telemetry.md` §3.1). Dashboard
    `surroundings` card soft-flags >1h shifts with <5 BLE and <5 WiFi
    uniques. Anti-fraud: only `is_root` in `update_info`; no Play
    Integrity, no cert pinning (but user CAs untrusted on targetSdk 36 →
    MITM needs root; Pairip blocks repackaging). Real-footprint capture:
    rooted device + test account + cut network after shift start →
    unencrypted SQLite `payloads` outbox accumulates byte-exact upload
    bodies → `adb pull` the db.
  - Wake-word emergency pipeline: fires only when triggered; not auth, not
    proof-of-work → excluded from reimplementation.

## Auth

Email+password → `POST /api/auth/token` (FormData `username`/`password`,
OAuth2-style) → JWT `auth.token`, **maxAge 900 s**; `POST /api/auth/refresh`;
`GET /api/auth/profile`; `POST /api/auth/logout`. Token in
`@aparajita/capacitor-secure-storage`. Bearer on all `/api` calls.
No OAuth/OTP/biometric login. Refresh confirmed 2026-09-19
(`audit/auth-session.md` §2, §8): JSON body `{refresh_token}` with NO
Authorization header; response consumes `access_token` only (no client-side
refresh-token rotation); proactive refresh fires at JWT **exp−60 s**
(single-flight), plus a 30 s pre-request expiry buffer and
visibility/route-middleware triggers; 401 → refresh → replay once →
sign-out.

## Backends / config (plaintext in `index.html` runtime config)

| Item | Value |
|---|---|
| API | `https://api.validnation.ai` |
| WS | `wss://api.validnation.ai/api/ws` (+ `/api/auth/ws_token`) |
| Supabase | `tfnnpqpvdjisoizvciyr.supabase.co` (PostgREST, app's own bearer) |
| Firebase project | `validnationai`, sender `575341455775` |
| Sentry | `o4505907064864768.ingest.us.sentry.io/4509870541242368` |
| Google Maps key | `AIzaSyChKq8NXkaIkEwJWpuV0hXx5tdRVDZsdyc` |

## Location / tracking stack

`@capacitor-community/background-geolocation` (equimaps, FGS type location)
+ `@transistorsoft/capacitor-background-fetch`. Permissions include
`ACCESS_BACKGROUND_LOCATION`, `ACTIVITY_RECOGNITION`, `RECEIVE_BOOT_COMPLETED`.
Remotely tunable config (Firebase Remote Config): buffer 60 fixes, flush
30 s, uploader batch 100 records/request, geofence radii. Uploader cadence
corrected 2026-09-19 (`audit/sensors-telemetry.md` §5): `UploaderPeriodMs`
(60 s) is dead config — the uploader is **event-driven**: 15-min background
fetch (OS floor), foreground resume (15-min throttle), silent push
`work_shift_upload_data`/`work_shift_end`, shift lifecycle events, manual
sync. Breaks pause tracking.
Offline outbox: SQLite `payloads` table (queued events, deleted on success),
`recent_locations`, `cached_audio*`; SecureStorage = token.

## Push / realtime

FCM via `@capacitor-firebase/messaging` (+ Remote Config), local
notifications, websocket `/api/ws` — the ONLY ValidNation websocket is
`/api/ws/voice_verification/{id}` (signatory voice verification stream;
confirmed 2026-09-19, `audit/endpoint-inventory.md` §3). Push taxonomy
corrected 2026-09-19 (`audit/endpoint-inventory.md` §4): silent/data
`action` values are exactly `work_shift_upload_data`, `work_shift_end`,
`download_and_apply_live_update` (and none); the previously listed
`silent_upload_work_shift_data` / `silent_force_live_update` names do not
exist — `silent_*` strings are in-app notification `type_` values (27-type
display/routing taxonomy). Visible pushes: shift reminders, contracts,
chats, wake-word emergencies.

## Capacitor

29 plugins in `tree/assets/capacitor.plugins.json`; custom native plugins:
`audio-manager-plugin` (ValidNation), `motion-activity-plugin`,
`permissions-manager-plugin`, `capacitor-udid`, `app-exit-reason-plugin`,
`@capgo/camera-preview` (CameraX), `@capawesome/capacitor-live-update` (OTA).
`CapacitorHttp` enabled (API calls via native HTTP).

## Signing

Play App Signing cert (`CN=Android, O=Google Inc.`) — we cannot sign as the
vendor; any rebuild needs its own applicationId and cannot in-place upgrade
the store install.
