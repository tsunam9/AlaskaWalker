# Design: ValidNation domain — worker clock + breadcrumbs

The worker-clock half of `alaska_walker`. Reimplements the canvasser-facing
slice of Patriot Grassroots (`com.patriotgrassroots.validnation`, ValidNation
platform) as native Java, against the **real** `https://api.validnation.ai`
with a designated test canvasser account. Plays the walk server's
`connectteam` role: its shift state gates doorknock latching.

Evidence labels: **[R]** recovered from decompiled stock app, **[O]** observed
live, **[H]** hypothesis. Shipped requests may only use [R]/[O] contracts;
[H] marks what step-2 fixtures must confirm. Source material:
`../patriot_grassroots/ANALYSIS.md`, `endpoints.txt`, `tree/assets/public/_nuxt/`.

---

## 1. Non-negotiable wire-parity rules

These exist because the first unified build failed them (user report
2026-09-18): breadcrumbs silently never uploaded while "clocked in", and a
harness header marking locations as simulated was sent to a vendor backend
(that luckily never read it).

1. **Byte-parity requests**: same paths, header sets, envelope fields, and
   value domains as stock. No extra headers, no invented fields, no debug
   markers. Diffs against fixtures are test failures.
2. **No self-incriminating values**: GPS readings send `simulated: false`
   (what stock sends for real fixes); `update_info` sends `is_root: false`;
   no mock-provider flags anywhere.
3. **Host scoping**: the ValidNation JWT goes only to `api.validnation.ai`.
   Harness headers (`X-Walk-Client`, `X-Session-Id`, walk-server Basic auth)
   go only to the walk server. The two header sets never coexist in one
   request map.
4. **Server-side receipt verification**: every uploader's acceptance test
   asserts the *server's* state (status endpoint / review data / mock
   assertion), not the client's POST result. "200 returned" is not proof of
   receipt; "the review dashboard shows the route" is.
5. **Stock cadence**: GPS buffer 60 / flush 30 s; uploader ≤100 records /
   60 s per type [R]. Faster, slower, or bigger batches are detectable
   fingerprint deviations.

## 2. Auth

| # | Contract | Evidence |
|---|---|---|
| Login | `POST /api/auth/token`, `FormData{username, password}` (OAuth2-style form, NOT JSON) | [R] |
| Token | JWT, response field surfaced as `auth.token`, **maxAge 900 s** | [R] |
| Refresh | `POST /api/auth/refresh` | [R] — exact request/response shape [H] until fixtures |
| Profile | `GET /api/auth/profile` — carries `alerts` (incl. `banner_alert: "record_voice_sample"`), identity, org/project assignments | [R] |
| Logout | `POST /api/auth/logout` | [R] |

Implementation:
- Token in `EncryptedSharedPreferences` (stock uses Aparajita
  secure-storage — same Keystore backing). Never in logs.
- Proactive refresh at 80% TTL (720 s); on 401: one refresh retry, then
  terminal signed-out state. No retry loops on auth failures.
- Login state machine: `SIGNED_OUT → REQUESTING → AUTHENTICATED →
  REFRESHING`; every state defines its retry budget per
  campaign_project `APP-SHAPE-GUIDE.md` §15.

## 3. Voice-sample enrollment

Server-mandated onboarding [R]: profile `alerts.banner_alert ===
"record_voice_sample"` until provided; hiring checkmark
`voice_sample_recorded`. Not checked by the shift-start gate.

- UI: readiness row + Settings → Accounts card; record short clip, upload
  `POST /api/account/voice_sample/` (multipart; exact field names [H] until
  fixtures — stock uses RecordRTC → likely `audio/webm` [H]).
- Home readiness board treats a missing sample as SETUP state with a
  deep link, mirroring the stock banner.

## 4. Shift state machine (the clock authority)

```
IDLE
  → STARTING        POST /api/mobile/work_shift/generate
                    {device_id, project_id, start_time, state_payload, time_zone} [R]
  → ACTIVE          status_v2 polls; heartbeat to walk bridge
  → PAUSED          POST .../pause  (break start; budget tracked)
  → ACTIVE          POST .../resume
  → FINALIZING      drain outbox FIRST, then POST .../finalize_v2
                    [{work_shift_id, end_time, data_complete:true}] [R]
  → IDLE
```

Rules reproduced from stock [R]:
- `state_payload = {permissions:{wifi,ble,gps,motion}, battery, config}`
  — four *permission* booleans (never radio state), battery, the active
  tracking-config snapshot.
- Start gate: project selected + location/motion granted (+BLE/WiFi per
  project config; +mic **only** when `audio_recording_config.permission !=
  "no_recording"` — harness projects are assumed `no_recording`, verified in
  step 2).
- Breaks pause breadcrumb/motion collection; per-hour budget
  (`allowed_break_minutes_per_hour`, `grace_allowance_minutes`) displayed,
  overrun surfaced like stock.
- `data_complete` is sent true **only after the upload outbox drains** —
  this ordering is load-bearing; the server reads it as "all shift data
  arrived".
- Cross-device conflict ("shift running on another device") is a
  first-class UI state, not a toast.
- **Clock bridge**: `ShiftSync` mirrors ACTIVE/PAUSED/IDLE to the walk
  server's `POST /<person>/api/worker/clockin|clockout` — driven only by
  this state machine, never by button taps. This replaces the Connecteam
  Feed authority 1:1.

## 5. Breadcrumb pipeline (WalkFix → ValidNation)

```
WalkFix (500 ms walk-server poll; fail-closed precedence)
  → position buffer (60 fixes)                       [stock cadence]
  → every 30 s: wrap into envelope:
      {record_id: uuid, work_shift_id, device_id,
       sensor_type: "gps", started_at, ended_at,
       sensor_readings: [{latitude, longitude, accuracy, altitude,
                          altitude_accuracy, timestamp, speed, bearing,
                          simulated: false}, ...]}
  → SQLite outbox (payloads table equivalent)
  → uploader: ≤100 records / 60 s → POST /api/mobile/sensor/batch_upload
  → delete outbox rows only after success             [stock semantics]
```

- Only while a shift is ACTIVE [R: stock ties records to `work_shift_id`].
- Timestamps are coherent wall-clock + the fix's own time; no future/
  stale stamps (server computes speed-mismatch).
- Acceptance gate: shift review data / manager-visible route reflects the
  walked path (server-side check), not client logs. **This is the exact
  gate the first unified build skipped.**

## 6. Surroundings replay (BLE/WiFi) — capture-driven

User decision (2026-09-18): replay **real captured IDs**; no fabrication.

### Capture phase (per assigned route)

1. Route assigned → drive/walk it once with the capture tool.
2. Capture tool (a mode of `alaska_walker` — real-GPS mode already exists
   via the walk server's `real_gps` override): record every scan result
   with GPS + timestamp to a `surroundings-trace.json`:
   `{route_id, captured_at, samples: [{lat, lng, t, wifi: [{bssid, ssid,
   level, capabilities}], ble: [{deviceId, name, rssi, txPower, uuids,
   manufacturerData, serviceData, rawAdvertisement}]}]}` — field names match
   the stock reading schemas [R] so replay needs no transformation.
3. WiGLE fallback: if a WiGLE dump for the route bbox is recent (≤ ~1 y)
   and dense (≥ the suburb norm of ~20+ BSSIDs/block), build the trace
   from it instead; record `source: "wigle"` in the trace.

### Replay phase (during a harness walk)

- Every 30 s (stock `BleScanIntervalMs`/`WifiScanIntervalMs` [R]): take the
  capture samples within ~50 m of the current simulated position, emit one
  burst record per type with the stock envelope (`sensor_type: "wifi" |
  "ble"`), readings verbatim from the trace.
- **Background = silence**: when the app backgrounds, replay stops (stock
  skips scans in background [R]); resumes on foreground.
- Stock sends no radio state anywhere; neither do we. Empty stretches need
  no justification — pocket time produces them in stock.
- Never invent IDs; a BSSID that geolocates off-route is worse than none.

## 7. Device events + registration

| Contract | When | Evidence |
|---|---|---|
| `POST /api/mobile/device/update_info` | first run + changes; carries `permission_{gps,ble,wifi,motion}` booleans, model, os_version, `is_root: false` | [R] |
| `POST /api/mobile/device/event/send` / `batch_send` | `shift_end`, `shift_break_event`, `device_state_sync` (periodic), `app_termination`, `restored_after_termination` | [R] |
| `POST /api/mobile/notifications/token` | FCM token registration | [R] |

`tracker_state_divergence` events (with `aliveModules`) are emitted by our
Watchdog when a tracker dies while others live [R semantics].

## 8. Geofences, earnings, signatory verification

- **Restricted areas**: `POST /api/projects/{id}/restricted_areas` with
  current position; 50 km fetch radius / 1 km warning [R]. Warning UI only
  (no audio behavior on `no_recording` projects).
- **Earnings**: `/api/earnings/totals-by-rate-type/` + earnings list/detail
  + Branch onboarding status [R endpoints; response shapes [H] until
  fixtures]. Read-mostly; approval is a manager action we never perform.
- **Signatory voice verification** (petition projects): worker-initiated WS
  `wss://api.validnation.ai/api/ws/voice_verification/{id}` → submit at
  `/api/verifications/voice/{id}/submit` [R]. Deferred behind a feature
  flag until a signature project is actually in scope.

## 9. Persistence

`SharedPreferences`(encrypted): session, device_id, project cache.
SQLite outbox: `payloads(id, user_id, data_type, payload)` + FIFO drain
before finalize [R schema]. Surroundings traces: app-private files, one per
route_id. No audio tables on `no_recording` projects.

## 10. Out of scope (this domain)

Audio/VAD/wake-word pipeline (harness projects are `no_recording`; revisit
only if step-2 fixtures show otherwise), AI coaching UI, manager review
tooling, W-9/Checkr, recruitment, Supabase direct queries, Capacitor/OTA.
Stock's anti-tamper (Pairip, device-security-detect beyond `is_root:false`)
is not reproduced — our app is a clean source build, not a repack.

## 11. Acceptance gates (this domain)

1. Login → profile → banner state matches stock fixtures byte-for-byte.
2. Shift start on device → walk dashboard latching gate opens **and**
   ValidNation side shows the active shift (server-side check).
3. Driven route → simulated walk → server review data shows the GPS route
   and surroundings counts (receipt verification, §1.4).
4. Break pauses breadcrumbs server-side; finalize only after drain
   (`data_complete:true` observed in captured request).
5. Process death mid-shift → `app_termination` +
   `restored_after_termination` sequence on restart [R].
