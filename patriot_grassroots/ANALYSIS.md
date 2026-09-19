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
- **Out of scope for us**: continuous shift audio recording + on-device VAD
  (Silero) + wake-word emergency (`validnation.ai.audiomanager`,
  TFLite pipeline), voice-biometric verification over websocket, AI coaching,
  earnings/payroll/Branch payouts, W-9/Checkr, recruitment campaigns,
  manager review queues. ~80% of the app is surveillance/HR we do not
  reimplement.

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
