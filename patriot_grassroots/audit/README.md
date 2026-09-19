# Patriot Grassroots reverse-engineering audit — index

App: `com.patriotgrassroots.validnation` v1.0.0 (114), white-label of the
ValidNation platform (Capacitor/Nuxt hybrid). Audit date: 2026-09-19.
This directory holds six line-cited audit files produced from the complete
original frontend source tree recovered from the app's shipped source maps
(see "How this was produced" below), plus the decompiled native Java in
`patriot_grassroots/java/`. Where these files disagree with
`patriot_grassroots/ANALYSIS.md` or `docs/DESIGN-VALIDNATION.md`, these files
are ground truth.

## The audit files

- **auth-session.md** — every auth/session message: login
  (`POST /api/auth/token`, FormData `username`/`password`), refresh, profile,
  logout, the websocket one-time token, plus token storage
  (SecureStorage/AES-GCM AndroidKeyStore), bearer attachment (which headers on
  which hosts, incl. Supabase carrying the same ValidNation JWT), refresh
  scheduling and 401/retry budgets. Resolves the refresh-shape [H]:
  `POST /api/auth/refresh` is JSON `{refresh_token}` with NO Authorization
  header; only `access_token` is consumed; proactive refresh fires 60 s before
  JWT `exp` (not "80% TTL"), single-flight; 401 → refresh → replay once →
  sign-out.

- **shift-lifecycle.md** — the shift state machine on the wire:
  `work_shift/generate|pause|resume|finalize_v2|status_v2`, cross-device
  conflict, `device/update_info`, `device/event/send|batch_send` (full
  event-type catalog), `notifications/token`, and the process-death/restart
  flow. Key results: full `state_payload` shape (permission booleans, battery,
  30-key config snapshot); finalize_v2 takes an array with per-item
  `state_payload` and per-shift drain-before-finalize ordering (`shift_end`
  rows upload last, `data_complete:true` only when no other rows for that
  shift remain; interrupt path sends `data_complete:null`); pause/resume are
  outbox `shift_break_event` rows, not direct POSTs; `shift_end` /
  `shift_break_event` / `wake_word_event` are outbox routing labels that never
  reach `device/event/*`.

- **sensors-telemetry.md** — the sensor pipeline: `sensor/batch_upload` body
  `{"records":[...]}` (success = HTTP 200 exactly, delete-after-success,
  duplicate `record_id` tolerance), per-sensor reading schemas (GPS incl.
  `simulated` = verbatim `Location.isFromMockProvider()` and `connection_type`
  per reading; WiFi/BLE/IMU/motionActivity), buffer sizes and flush cadences,
  the SQLite `payloads` outbox, and the restricted-areas geofence logic
  (50 km fetch / 10 km re-center / 1 km warning / queue-of-4 fail-closed).
  Corrects the cadence claim: `UploaderPeriodMs` (60 s) is dead config — the
  uploader is event-driven (15-min background fetch, 15-min foreground
  throttle, silent push, lifecycle events, manual sync); 100 = records per
  request.

- **audio-voice.md** — voice-sample enrollment, the VAD shift-audio pipeline,
  the wake-word emergency pipeline, and signatory voice verification.
  Resolves/refutes the voice-sample [H]: `POST /api/account/voice_sample/` is
  JSON (`audio_data` = base64 raw Int16-LE PCM + `audio_config{sample_rate,
  channels, bits_per_sample, encoding:"linear16"}`), NOT multipart, NOT webm,
  >30 s minimum; webm is preview-only. Also: Silero VAD 16 kHz PCM16 ~3 s
  chunks to `/api/canvasser_voice/receive` (native OkHttp multipart);
  `missingSegmentIds` is a client-side 50 MB-store eviction report, not server
  reconciliation; wake word = `grace_emergency.tflite` @ 0.99, JSON event +
  multipart [t−3s, t+1s] clip; voice_verification is the ONLY ValidNation
  websocket.

- **earnings-account-misc.md** — earnings/payroll, account, applications,
  assignments, reports, onboarding (canvasser application/W-9/Checkr),
  recruitment, and chats. Resolves the earnings [H]: totals-by-rate-type =
  `{bonus:{total,count}, increased_rate:{total,count}}`; Branch status =
  `{status, onboarding_link}`; balance = `{ready_for_payment, pending,
  next_payment_date, same_day_payout_enabled}`; amounts integer cents;
  withdraw is a body-less POST; only poll is 10 s while awaiting Branch
  activation. Chats are 100% Supabase (~16 PostgREST RPCs, `private` schema,
  Realtime broadcast, Storage bucket) authed with the app's own ValidNation
  JWT — `/api/broadcast` is the Supabase realtime-js path, NOT a ValidNation
  endpoint.

- **endpoint-inventory.md** — the master table: all 322 SDK operations from
  the generated client (`client/sdk.gen.ts`), grouped by domain, each with
  method/path ground truth, canvasser-build trigger, owner audit file, and
  caller evidence. Also: the eight transports (T1–T8), websocket inventory
  (voice_verification is the only ValidNation WS), the FCM push inventory
  (silent actions are exactly `work_shift_upload_data` / `work_shift_end` /
  `download_and_apply_live_update` — the `silent_*` names in older docs are
  in-app notification `type_` values), `endpoints.txt` reconciliation, and
  Appendix A: the DECLARED-UNUSED list (34 operations with no caller anywhere;
  ~180 more admin/manager-role-gated).

## How this was produced

On 2026-09-19 the app's shipped source maps
(`patriot_grassroots/tree/assets/public/_nuxt/*.js.map`) were exploded to
recover the **complete original frontend source tree**: 2,518 files at
`/tmp/vn_src/` — including the generated API client ground truth
(`client/sdk.gen.ts`, `client/client.gen.ts`, `client/core/`), plus
`queries/`, `mutations/`, `composables/`, `stores/mobile/`,
`native_plugins/`, `types/`, `pages/`, `plugins/`, `utils/`.

Reproduction: each `.js.map` under
`patriot_grassroots/tree/assets/public/_nuxt/` contains `sources[]` +
`sourcesContent[]` (webpack/Vite convention). A small Python script iterates
the maps, and for every `sources[i]` writes `sourcesContent[i]` to the
original relative path under `/tmp/vn_src/` (normalizing `webpack://...` /
`../` prefixes). No deobfuscation is needed — the contents are the original
TypeScript/Vue sources verbatim. Native evidence comes from the decompiled
Java in `patriot_grassroots/java/sources/...`; wire shapes for the audio
endpoints are taken from the shipped dex (native OkHttp multipart), which is
exact.

**`/tmp/vn_src` is ephemeral** — it is not in the repo and does not survive a
reboot. The durable source is the set of `.js.map` files under
`patriot_grassroots/tree/assets/public/_nuxt/`; re-run the extraction script
to regenerate the tree before verifying any `path:line` citation in these
files (citations are relative to the `/tmp/vn_src/` root).

Known recovery gap (kept UNCONFIRMED throughout): `client/types.gen.ts` (the
hey-api generated type definitions) and other type-only files were erased at
compile time and are absent from the source maps. Full server response
schemas are therefore proven only for fields the app actually constructs or
consumes; everything else is marked UNCONFIRMED in the audit files. The live
`/openapi.json` requires authentication and could not be used.
