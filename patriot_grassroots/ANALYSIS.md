# Patriot Grassroots analysis — `com.patriotgrassroots.validnation` v1.0.0 (114)

White-label build of the **ValidNation** field-workforce platform, branded
"Patriot Grassroots". **Capacitor hybrid** (Nuxt/Vue web build readable in
`tree/assets/public/_nuxt/*.js` with source maps), 4 dexes, minSdk 23,
targetSdk 36. Stock APKs in `stock/`, frozen baseline in `BASELINE.md`,
full endpoint dump in `endpoints.txt`.

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
  speed, bearing, simulated}` — note the honest `simulated` flag
  (mock-location detection exists).
- **Geofencing**: per-project restricted-area polygons
  (`/api/projects/{id}/restricted_areas`, 50 km fetch radius, 1 km warning).
- **Device telemetry**: `/api/mobile/device/event/send|batch_send`
  (`shift_end`, `shift_break_event`, `wake_word_event`,
  `restored_after_termination`, ...), `/api/mobile/device/update_info`,
  `/api/mobile/notifications/token` (FCM).
- **Scope note (revised 2026-09-18, second pass)**: voice-sample enrollment
  and worker-side earnings/payroll are **in scope** for the reimplementation
  (see `docs/UNIFIED-APP-PLAN.md` §2). Key facts:
  - Voice sample (`POST /api/account/voice_sample/`) is server-mandated
    onboarding (`alerts.banner_alert: "record_voice_sample"` + hiring
    checkmark `voice_sample_recorded`), consumed server-side to verify the
    worker's voice against shift audio. The shift-start screen does NOT
    check for it client-side; shift start gates on: assigned project +
    location/motion/BLE/WiFi permissions (+ mic ONLY when the project's
    `audio_recording_config.permission != "no_recording"`).
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
    On recording projects the server accounts for audio: `missingSegmentIds`
    in `/api/canvasser_voice/receive` responses, zero conversations,
    `data_complete` at `finalize_v2`, `aliveModules` in
    `tracker_state_divergence` events.
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
    produces zero records and radio state is sent NOWHERE
    (`state_payload.permissions` are permission booleans only). Dashboard
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
No OAuth/OTP/biometric login.

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
30 s, uploader batch 100/60 s, geofence radii. Breaks pause tracking.
Offline outbox: SQLite `payloads` table (queued events, deleted on success),
`recent_locations`, `cached_audio*`; SecureStorage = token.

## Push / realtime

FCM via `@capacitor-firebase/messaging` (+ Remote Config), local
notifications, websocket `/api/ws` (voice verification stream; likely more).
Push taxonomy: shift reminders, contracts, chats, wake-word emergencies,
`silent_upload_work_shift_data`, `silent_force_live_update`.

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
