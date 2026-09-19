# Audit: Audio & Voice — server-bound messages

App: `com.patriotgrassroots.validnation` v1.0.0 (114). Base `https://api.validnation.ai`;
WS base `wss://api.validnation.ai/api/ws` (`tree/assets/public/index.html` runtime config:
`apiBaseURL:"https://api.validnation.ai"`, `wsBaseURL:"wss://api.validnation.ai/api/ws"`).
Auth on every call: `Authorization: Bearer <jwt>` — `token.value` already includes the
`Bearer ` prefix (`composables/auth/useAuthState.ts:108`).

Evidence roots: `/tmp/vn_src/` (recovered frontend source, cited as `path:line`) and
`patriot_grassroots/java/sources/validnation/ai/audiomanager/` (decompiled native plugin,
cited as `java/.../File.java:line`). The plugin's TS `definitions.ts` was a type-only file
and was not recoverable from source maps; plugin call/response shapes below are taken from
the Java implementations (ground truth for the wire).

---

## 1. Voice-sample enrollment — `POST /api/account/voice_sample/`

**Resolves [H] (DESIGN-VALIDNATION.md §3, lines 67–68): NOT multipart, NOT `audio/webm`.**
The generated client sends **`Content-Type: application/json`** (`client/sdk.gen.ts:149–154`)
with a JSON body; the RecordRTC webm blob is used *only* for local playback preview
(`composables/useSampleRecorder.ts:74–81`) and is never uploaded.

- Method/path: `POST /api/account/voice_sample/` (`client/sdk.gen.ts:141–155`).
- Body (`mutations/createSample.ts:7–11`):
  ```json
  {
    "audio_data": "<base64>",
    "audio_config": {
      "sample_rate": 48000,
      "channels": 1,
      "bits_per_sample": 16,
      "encoding": "linear16"
    }
  }
  ```
  - `audio_data` = base64 of the concatenation of raw **Int16 little-endian PCM** buffers.
    The capture path is an `AudioWorkletNode` loaded from `/audio-processor.js`, which
    converts each Float32 input frame to Int16 (`inputChannel[i] * 32767`, clamped) and
    posts the `Int16Array` buffer (`tree/assets/public/audio-processor.js`; wired in
    `composables/useSampleRecorder.ts:37–51`; chunks combined and base64-encoded in
    `useSampleRecorder.ts:110–115`).
  - `audio_config` from `utils/createAudioConfig.ts:6–11`: `sample_rate` =
    `track.getSettings().sampleRate || 48000`; `channels` = `channelCount || 1`;
    `bits_per_sample` = `capabilities.sampleSize?.max || 16`; `encoding` hardcoded
    `'linear16'`. Note: sample rate is device-dependent (typically 48000 in a WebView;
    *not* resampled to 16 kHz).
- Trigger: user action on the "Verification Sample" page
  (`pages/account/canvasser/edit/voice-sample/index.vue`), reached from:
  - the account-problem banner when server profile returns `alerts.banner_alert ===
    "record_voice_sample"` — banner text/route mapping at
    `constants/accountProblems.ts:29–35`, rendered by
    `components/accountProblemNotifier/AccountProblemNotifier.vue:21–23` from
    `useUserRole().accountProblems`;
  - the canvasser account page, which displays the server-driven
    `accountInfo.voice_sample_recorded` hiring checkmark
    (`pages/account/canvasser/index.vue:13–14`).
- The read-aloud prompt is brand text hardcoded in the page
  (`pages/account/canvasser/edit/voice-sample/index.vue:89–99`).
- Client-side gate: recording must be **> 30 s** (`useSampleRecorder.ts:22–25`; code
  comment "todo replace 30 with value received from server" — value is hardcoded).
  Stop is allowed earlier but shows "Verification sample is too short"
  (`useSampleRecorder.ts:71–72`) and Save is disabled.
- Response consumed: none of the body — on success only a toast + `getSession()` refresh,
  `['account']` query invalidation, redirect to `account-canvasser`
  (`mutations/createSample.ts:12–15`, `composables/useRefreshAccountAndRedirect.ts:7–11`).
  The server flips `voice_sample_recorded` and clears `banner_alert` (server-side; the
  client just re-reads the account).
- Transport: generated client with `composable: '$fetch'` (webview fetch, not the native
  OkHttp path used for shift audio). Offline/failure: error toast, **no retry, no offline
  queue** (`useSampleRecorder.ts:116–120`).
- Manager side: user details expose `canvasser_voice_sample` and a `voice_sample` removal
  action (`components/users/details/UserDetailsCanvasserInfo.vue:104,231`) — confirms the
  sample is stored server-side per worker and can be invalidated (which presumably re-arms
  the banner/checkmark; server behavior UNCONFIRMED).

---

## 2. Continuous shift audio (VAD pipeline)

### 2.1 When recording runs

- The `microphone` tracking module is included only when the shift project requires audio:
  `project.audio_recording_config.permission != null && !== 'no_recording'`
  (`composables/mobile/useMobilePermissions.ts:18,25`; module wiring
  `composables/mobile/useMobileModules.ts:23–30`).
- Recorder store: `stores/mobile/vadRecorder.ts` → `createAudioRecorder(shiftId, deviceId)`
  (`composables/mobile/audio/useMobileAudioManager.ts:46`).
- `start()` (`useMobileAudioManager.ts:88–134`):
  - no-ops when `VadEnabled` is false, non-native, or already running;
  - **skips silently** (console.warn) when `audio_recording_config.permission` is `null`
    (unresolved) or `'no_recording'` (`useMobileAudioManager.ts:91–100`) — zero audio is
    the normal server-visible state for `no_recording` projects;
  - wires restriction zones **only** for `'full_recording_with_restricted_area'`
    (`useMobileAudioManager.ts:102–105`);
  - calls native `AudioManager.setPermissionMode({mode})` — native accepts exactly
    `full_recording` / `full_recording_with_restricted_area` / `no_recording`
    (`java/.../AudioManager.java:524–538`; constants `:59–61`);
  - audio-session pre-flight: 5 attempts × 1 s (`useMobileAudioManager.ts:26–44`); note the
    Android implementation of `checkAudioSessionAvailable` **always returns
    `{available: true}`** (`java/.../AudioManager.java:244–249`) — the busy-gate is iOS-only
    in practice (UNCONFIRMED for iOS, no iOS sources in scope);
  - `AudioManager.startVad({bufferSeconds: config.VadMaxSegmentSeconds, threshold:
    config.VadModelThreshold, includeProbabilities: false, gateWakeWord:
    config.VadGateWakeWord, wakeWordHangoverMs: config.VadWakeWordHangoverMs})`
    (`useMobileAudioManager.ts:115–121`). Defaults (`types/database/config.ts:24–31`,
    remotely tunable via Firebase Remote Config): `VadEnabled=true`,
    `VadMaxSegmentSeconds=3`, `VadModelThreshold=0.8`, `VadMaxBufferSize=120`,
    `VadGateWakeWord=true`, `VadWakeWordHangoverMs=800`.
  - then warms the native location repo from the `recent_locations` SQLite history
    (`useMobileAudioManager.ts:136–146`).
- Native capture (`java/.../RecordingService.java`, `AudioProcessor.java`): foreground
  service, notification channel `vad_record_channel`, ongoing notification "Listening for
  voice" (`RecordingService.java:58–182`); `AudioRecord` source **6 = VOICE_RECOGNITION**,
  **16 000 Hz, mono, PCM16** (`AudioProcessor.java:432`); Silero VAD ONNX in 256-sample
  (16 ms) hops (`AudioProcessor.java:49`); a `vadVoice` chunk is emitted when accumulated
  *voiced* audio ≥ `bufferSeconds` (3 s), at voice offset, and on flush/stop
  (`AudioProcessor.java:188–216, 312–329, 369–380`).

### 2.2 GPS per segment (native)

- JS forwards every GPS fix to the native ring while the recorder is alive:
  `AudioManager.updateLocation(loc)` per location update
  (`composables/mobile/trackers/useMobileLocationTracking.ts:141–146`). Native keeps the
  last **300** fixes (`java/.../LocationRepo.java:91–97`).
- Per voice segment, native picks the fix **nearest to the segment midpoint** within
  `NEAREST_MAX_DELTA_MS`, falling back to `latestFresh()` (age ≤ `LATEST_MAX_AGE_MS` and
  accuracy ≤ 500 m) (`java/.../AudioManager.java:451–454`;
  `LocationRepo.java:55–89`). Both thresholds default to Sentry's
  `TransactionOptions.DEFAULT_DEADLINE_TIMEOUT_AUTO_TRANSACTION` constant (30 000 ms in
  the bundled sentry-java; exact value UNCONFIRMED from decompilation — it's a third-party
  constant, `LocationRepo.java:38–40`).
- GPS point shape attached to a segment (`AudioManager.java:460–466`):
  `{timestamp (ms epoch), latitude, longitude, accuracy, altitude, altitude_accuracy}`
  (missing accuracy/altitude → 0.0).

### 2.3 `vadVoice` event shape (native → JS)

`AudioManager.java:444–490` notifies:
```
{
  chunkId: "{sessionStartMs}_{firstSegStartMs}_{lastSegEndMs}",
  sessionStartMs: number, sampleRate: 16000, channels: 1, seconds: number,
  vad_model_name: "silero",
  segments: [
    { segmentId: "{sessionStartMs}_{startMsAbs}_{endMsAbs}",
      byteLength: number,
      gps_point: {timestamp, latitude, longitude, accuracy, altitude, altitude_accuracy} }
  ]
}
```
Segments are stored PCM16-LE in an in-memory `SegmentStore` capped at **50 000 000 bytes**,
oldest-first eviction (`AudioManager.java:64`, `SegmentStore.java:85–99`).

**Fail-closed no-GPS drop:** if no usable fix exists and mode is
`full_recording_with_restricted_area`, the segment is **dropped on-device** (counted in
`droppedMissingGpsCount`, never reaches JS) (`AudioManager.java:455–458`). In
`full_recording` mode a no-fix segment is kept with a **zeroed gps_point**
(`{timestamp:0, latitude:0, longitude:0, ...}`) — the `else` branch runs with
`fixNearestTo == LocationRepo.ZERO`.

### 2.4 Restricted-area enforcement (client-side)

- Zones: `POST /api/projects/{project_id}/restricted_areas`, JSON body
  `{lat, lon, radius_km}` (`mutations/mobile/fetchRestrictedAreas.ts`; radius default
  `GeofenceFetchRadiusKm = 50`, `types/database/config.ts:33`). Response consumed:
  `features[]` (GeoJSON Polygon/MultiPolygon; `properties.zipCode`/`zip_code` used as zone
  id, synthetic `unknown-{i}` fallback) and `permission`
  (`composables/mobile/audio/useAudioRestrictionZones.ts:32–46,124–139`).
- Refetch when the fix is > `GeofenceRefreshDistanceKm = 10` km from the fetch center;
  30 s error backoff (`useAudioRestrictionZones.ts:25,76–98`).
- Per VAD segment (`composables/mobile/audio/useVadVoiceHandler.ts:15–51`):
  chunks deduped by `chunkId`; zones ensured loaded from the chunk's first GPS fix;
  `updateStatus(gpsPoint)` pushes `{isRestricted, hasCoverage, timestamp, point}` onto a
  queue of size `GeofenceRestrictionQueueSize = 4` (`types/database/config.ts:36`).
  If `!isRecentlyAllowed()` → `AudioManager.releaseSegments({segmentIds:[id]})` → native
  deletes the bytes (`AudioManager.java:505–522`); the segment is **never uploaded**.
- `isRecentlyAllowed()` is fail-closed (`useAudioRestrictionZones.ts:237–255`): false when
  zones were never successfully fetched, when the queue has < 4 entries, or when any
  recent entry lacks coverage (drifted outside the 50 km prefetch radius) or is restricted.
  Full-recording projects always return true; `no_recording` false.

### 2.5 `POST /api/canvasser_voice/receive` (online segment upload)

Upload trigger (JS pool, `composables/mobile/audio/useAudioSegmentPool.ts`):
- **auto-flush** when pooled bytes ≥ `BYTES_PER_SECOND (32 000) × VadMaxBufferSize (120)`
  = 3 840 000 bytes ≈ 120 s of PCM16 (`useMobileAudioManager.ts:16–17,64–66`;
  `useAudioSegmentPool.ts:62–73`) — i.e. roughly one request per ~2 min of accumulated
  voice;
- **flush on recorder stop** (shift pause/end) (`useMobileAudioManager.ts:148–185`);
- **uploader tick tail**: `recorderStore.sendFullBuffer()` (= pool.flush) on every uploader
  tick (`composables/mobile/useUploader.ts:195–196`); ticks run on background fetch
  (`minimumFetchInterval: 15` min, `composables/mobile/backgroundFetch.ts:5`), on shift
  sync/end (`useMobileShift.ts:307,327,340,346`), and after resume/restore flows.
  (`UploaderPeriodMs=60_000` exists in config but is referenced nowhere else — UNCONFIRMED
  dead config.)

Request is built **natively** (`AudioManager.uploadVadChunk`,
`java/.../AudioManager.java:856–1007`) as `multipart/form-data` via OkHttp, header
`Authorization: Bearer <jwt>`:

| Part | Value |
|---|---|
| `audio` | file `voice_chunk.wav`, `Content-Type: audio/wav` — WAV (PCM, mono, 16 000 Hz, 16-bit LE) wrapping the concatenation of all requested segments still in the store (`AudioEncoders.java:58–78`) |
| `work_shift_id` | shift UUID from JS |
| `vad_model_name` | `"silero"` |
| `device_id` | device UUID from JS |
| `sample_rate` | `"16000"` |
| `wallclock_start` | UTC `yyyy-MM-dd'T'HH:mm:ss.SSS'Z'`; = min segment start, overridden by `sessionStartMs`, then by previous upload's `lastUploadEndMs` (persisted in SharedPreferences) — chunks tile a contiguous wall-clock span (`AudioManager.java:928–957`) |
| `wallclock_end` | max segment end, clamped ≥ start+1 ms |
| `segments` | JSON string: `[{start_ms, end_ms, gps_point:{timestamp, latitude, longitude, accuracy, altitude, altitude_accuracy}}, …]` for the segments actually included (`SegmentStore.java:55–72`) |
| `span_upload_id` | fresh UUIDv4 per request (`AudioManager.java:959–960`) |

Client call site: `utils/mobile/uploadAudioNative.ts:15,36–47` (URL from generated type
`ReceiveCanvasserVoiceData['url']` = `/api/canvasser_voice/receive`;
`client/sdk.gen.ts:557–573`).

**Response handling — important correction to prior analysis:**
- The server response body is **not parsed** for `/receive`; native only reports
  `{success, status, body}` (`AudioManager.java:987–1002`).
- `missingSegmentIds` in the plugin response is a **client-side** list: segment IDs the JS
  asked to upload that had already been **evicted from the 50 MB native store**
  (`AudioManager.java:873–874,1000`; `SegmentStore.java:74–83`). It is NOT server
  reconciliation data. JS logs/Sentry-reports these as lost audio
  (`uploadAudioNative.ts:164–185`). No server-provided "missing segments" list is consumed
  anywhere in this flow.
- On HTTP success: native deletes the uploaded segments from the store and persists
  `lastUploadEndMs` (`AudioManager.java:991–995`).
- On non-2xx: native **keeps** segments; JS returns `retryable: true` and the pool
  re-queues them (`AudioManager.java:996–1001`; `uploadAudioNative.ts:242–246`;
  `useAudioSegmentPool.ts:46–59`).
- On 401: JS refreshes the access token and retries once
  (`uploadAudioNative.ts:210–240`).
- On network failure (IOException): native writes the WAV to
  `files/AudioChunks/{wallclock_start}-{wallclock_end}.wav`, drops the segments from the
  store, and resolves with `{cachedPath, segments, wallclockStart, wallclockEnd,
  spanUploadId, missingSegmentIds, error}` (`AudioManager.java:962–984`); JS then inserts a
  `cached_audio` SQLite row (`saveAudio(metadata, filename)`), retrying the DB write 3× and
  deleting the orphan file + Sentry-reporting if it can't (`uploadAudioNative.ts:109–159,
  200–204`).
- On recorder stop with a retryable flush failure still pending, JS force-caches the
  remainder via `AudioManager.forceCacheRemaining` (same on-disk format; `AudioManager
  .java:290–409`, `uploadAudioNative.ts:259–290`) so `AudioManager.stop()` wiping the store
  doesn't lose audio (`useMobileAudioManager.ts:151–175`).

### 2.6 `POST /api/canvasser_voice/cached_receive` (offline backlog)

- Trigger: uploader-tick tail → `uploadAllCachedAudioIfExists()` →
  `uploadCachedAudioIfExists()` (`utils/mobile/uploadAllCachedAudio.ts`;
  `utils/mobile/uploadAudioNative.ts:75–107`), batched by `AudioUploadBatchSize = 64`
  cached rows (`types/database/config.ts:39`).
- Native request (`AudioManager.uploadCachedChunks`, `AudioManager.java:606–743`),
  `multipart/form-data`, `Authorization: Bearer <jwt>`:
  - per cached chunk *i* (index among files that still exist on disk):
    - `audio`: file **`voice_chunk_{i}.wav`**, `audio/wav` (file content = the cached WAV
      from §2.5's failure path);
    - `work_shift_id`, `wallclock_start`, `wallclock_end`: per-row values;
    - `vad_model_name`: `"silero"`;
    - `span_upload_id`: per-row UUID, only when the row has one (`AudioManager.java:654–656`);
  - once per request: `device_id` (taken from the **first** row,
    `AudioManager.java:635,666`);
  - `segments`: `JSON.stringify` of the whole JS array of per-row `segments` JSON strings —
    i.e. the wire value is a JSON array whose elements are themselves JSON strings of the
    per-chunk segment-metadata arrays (`AudioManager.java:636,667`; rows built in
    `uploadAudioNative.ts:53–73,91–100`). Reimplementation must reproduce this nesting.
- Response consumed: **`succeeded_filenames`** (JSON array in the body). For each listed
  `voice_chunk_{i}.wav`, native deletes the cached file and reports the row index as
  `succeededIndices`; JS deletes those SQLite rows (`AudioManager.java:695–719`;
  `utils/mobile/offlineAudioCache.ts:87–103`). Unlisted rows stay for the next tick.
- On failure: TTL cleanup runs, then remaining groups are skipped (`stopOnFailure`)
  (`uploadAudioNative.ts:103–106`).
- TTL: cached audio older than `AudioCacheTTLDays = 4` days is deleted (file + row) by
  `checkAudioCacheTTL`, which runs on **every app resume**
  (`plugins/stateChangeListeners.ts:54`) and after cached-upload failures
  (`utils/mobile/offlineAudioCache.ts:16–52`; an `audio_cache_cleanup` mobile event is sent
  when anything was scanned, `uploadAudioNative.ts:20–34`).

---

## 3. Wake-word pipeline (emergency)

- Native detector: `WakeWordEngine` with bundled TFLite models `melspectrogram.tflite`,
  `embedding_model.tflite`, classifier **`grace_emergency.tflite`**, score threshold 0.99
  (`java/.../WakeWordTypes.java:21–23`; engine constructed unconditionally at VAD start,
  `RecordingService.java:129`). The spoken phrase is not recoverable from code —
  **UNCONFIRMED** (model asset name suggests a "Grace" emergency word; the app also has a
  user-facing emergencies feature, `pages/emergencies/[id].vue`).
- Gating: the wake-word engine only runs while VAD sees voice (+ `VadWakeWordHangoverMs =
  800` ms hangover) when `VadGateWakeWord = true` (`AudioProcessor.java:265–288`);
  30 s debounce between detections (`AudioProcessor.java:15,340–344`).
- On detection, 1 100 ms later native slices the raw ring buffer **[t−3 000 ms, t+1 000 ms]**
  into the segment store as clip id `wakeword_{clipStartMs}_{clipEndMs}` and notifies
  `wakeWordDetection` with `{timestampMs, gps_point? (latestFresh only), clipId,
  clipStartMs, clipEndMs}` (`AudioManager.java:114–159`; ring = 480 000 samples = 30 s,
  `AudioProcessor.java:14`). The SDK doc comment confirms the [t−3s, t+1s] clip and a 5 MB
  default server cap (`client/sdk.gen.ts:575–578`).

### 3.1 `POST /api/canvasser_voice/wake_word_event` (JSON)

- Triggered per detection by `composables/mobile/audio/useWakeWordHandler.ts:10–31`.
- Body (`WakeWordEventRequest`):
  ```json
  {
    "id": "<uuidv4, client-generated>",
    "work_shift_id": "<shift uuid>",
    "device_id": "<device uuid>",
    "timestamp_ms": <detection epoch ms>,
    "gps_point": { "latitude": …, "longitude": …, "accuracy": …, "altitude": …,
                   "altitude_accuracy": …, "timestamp": "<ISO8601 string>" } | null
  }
  ```
  (`useWakeWordHandler.ts:12–21` — note gps `timestamp` is converted to an ISO string here,
  unlike the ms-epoch form used in VAD segment metadata.)
- Transport: `doNativeRequest` (CapacitorHttp), JSON
  (`mutations/mobile/sendWakeWordEvent.ts`). Endpoint from
  `client/sdk.gen.ts:623–638`.
- Offline: the payload is first written to the SQLite `payloads` outbox
  (`MESSAGE_TYPES.wake_word_event`) and deleted on success; the uploader replays failed
  rows individually and **permanently drops** a row on HTTP 400/404 (Sentry-reported),
  retrying others (`useWakeWordHandler.ts:23–31`; `useUploader.ts:87–100`).

### 3.2 `POST /api/canvasser_voice/wake_word_audio` (multipart)

- Sent immediately after the event (same handler, `useWakeWordHandler.ts:35–48` →
  `utils/mobile/uploadWakeWordClipNative.ts:27–61` → native
  `AudioManager.uploadWakeWordClip`, `AudioManager.java:1009–1086`).
- Parts: `audio` = file `wake_word_clip.wav` (`audio/wav`, PCM16/16 kHz/mono of the 4 s
  slice), `event_id` (the same client UUID as §3.1 — join key), `work_shift_id`,
  `device_id`, `clip_start_ms`, `clip_end_ms` (`AudioManager.java:1029`).
- If the clip was evicted from the store: resolves `{error:"CLIP_EVICTED", …}`, nothing
  sent (`AudioManager.java:1074–1082`).
- On network failure **or any non-2xx** (e.g. event row not yet landed → 404): native
  caches `AudioChunks/{clipId}.wav` and resolves `cachedPath`; JS records it in the
  `cached_wake_word_clips` table (`AudioManager.java:1030–1062`;
  `uploadWakeWordClipNative.ts:48–60`).
- Success response body ignored (`AudioManager.java:1064–1069`).

### 3.3 `POST /api/canvasser_voice/wake_word_audio_cached` (multipart batch)

- Trigger: uploader-tick tail (`uploadAllCachedAudioIfExists` →
  `uploadCachedWakeWordClipsIfExists`, `uploadWakeWordClipNative.ts:63–114`), grouped per
  `device_id`; TTL sweep runs first.
- Parts: `audio` = `wake_word_clip_{i}.wav` × N; `device_id`; `clips` = JSON string
  `[{event_id, work_shift_id, clip_start_ms, clip_end_ms}, …]` (note snake_case remap from
  the TS camelCase, `AudioManager.java:764–789`).
- Response consumed: **`succeeded_indices`** — those clips' files and DB rows are deleted
  (`AudioManager.java:813–839`; `offlineAudioCache.ts:93–103`). Failed groups stay cached.
- TTL: same 4-day expiry as VAD cache (`uploadWakeWordClipNative.ts:15–25`).

---

## 4. Signatory voice verification (petition voters — worker-initiated)

This is the petition **signatory** feature (voters' voices), not a worker spot-check; no
server-initiated voice challenge exists. Flow:

1. Worker opens "Signatory Verification", picks a project; the "Start Signatory
   Verification" button is shown only when `project.voice_verification_enabled`
   (`pages/verification/signatory/index.vue:16–24`).
2. `createVerification(project_id)`: requests mic permission, then
   **`PUT /api/verifications/voice/`**, JSON body `{"project_id": "<uuid>"}`; consumes
   `response.id` (the conversation id) (`stores/verification/voice.ts:19–28`;
   `client/sdk.gen.ts:5302–5317`).
3. On the `verification-voice-id` page, `useVoiceVerification(conversationId)` runs on
   mount (`components/verification/voice/VerificationVoiceForm.vue:167–169`;
   `composables/useVoiceVerification.ts`):
   - `GET /api/verifications/voice/{conversation_id}` (bearer) drives the branch:
     `status` `new`/`in_progress` → start streaming; `ready_for_submit` → render
     `extracted_signatories` (`queries/verification/voice-details.ts`;
     `useVoiceVerification.ts:90–103`).
   - `GET /api/auth/ws_token` (bearer) → one-time `access_token` for the socket
     (`client/sdk.gen.ts:451–466`; `useVoiceVerification.ts:136`).
   - **WebSocket connect**: `wss://api.validnation.ai/api/ws/voice_verification/{id}`
     with query params `token`, `sample_rate`, `bits_per_sample`, `channels`, `encoding`
     (from `createAudioConfig` — e.g. `48000/16/1/linear16`, device-dependent sample rate)
     (`useVoiceVerification.ts:135–149`).
   - Wait for server message `{"type":"initialized"}`, then client sends
     **`{"type":"start"}`** and begins streaming (`useVoiceVerification.ts:128–133`).
   - **Audio messages**: every **250 ms** (`setInterval(sendBase64EncodedAudio, 250)`)
     the client sends
     ```json
     {"type":"stream_audio", "audio_data":"<base64>"}
     ```
     (`useVoiceVerification.ts:162–182`). The bytes are the same worklet's **Int16 LE PCM**
     (`/audio-processor.js`); the `new Float32Array(data)` wrapper reinterprets but does
     not alter the bytes (`combinedBuffer.buffer` is sent verbatim).
   - Client control messages: `{"type":"stop"}` (Stop button, or on server `force_stop`),
     `{"type":"cancel"}` (Cancel button / route leave)
     (`useVoiceVerification.ts:189–212`; `VerificationVoiceForm.vue:134–137,171–174`).
   - Server→client messages consumed: `initialized`, `signatory_info`
     (`{infos: SignatoryInfoResult[]}` — extracted signer fields), `ready_for_submission`,
     `force_stop`, `error` (`{detail}`) (`useVoiceVerification.ts:56–79`).
     `SignatoryInfoResult` fields (from store usage): `id, first_name, middle_name,
     last_name, state, city, county, address_1, address_2, zip_code, validation_result,
     signed_date, other_data` (`stores/verification/voice.ts:50–66`).
   - Reconnect: on socket close, up to **3 attempts**, 5 s apart; each attempt re-runs the
     full start sequence (new WS + `start`) (`composables/useSocket.ts:8,42–66`;
     `useVoiceVerification.ts:46–48`). After 3 failures: toast, navigate back to
     `verification` (`useVoiceVerification.ts:104–106`). No offline queue — this feature
     is online-only by design.
4. Submit (Submit button, enabled when server sent `ready_for_submission` and every row
   passes the client zod schema):
   **`POST /api/verifications/voice/{conversation_id}/submit`**, JSON body
   ```json
   {"signatories":[{
     "first_name":"…","last_name":"…","middle_name":null,
     "state":null,"city":null,"county":null,
     "address_1":"…","address_2":null,"zip_code":null,
     "signed_date":"yyyy-MM-dd"
   }]}
   ```
   (`components/verification/voice/VerificationVoiceForm.vue:141–158` — client strips
   `id`, `other_data`, `validation_result` and defaults `signed_date` to today;
   `mutations/verification/voice.ts:5–24`; `client/sdk.gen.ts:5340–5355`).
   Success: toast "Signatories created successfully", invalidates the
   `['voice-verification', conversationId]` query. Failure: toast only, no retry.
5. Related list endpoint (not part of the capture flow): `GET /api/verifications/voice/`
   (`client/sdk.gen.ts:5285–5296`). A non-voice manual path exists too:
   `PUT /api/verifications/voters` ("Submit Signatories" form,
   `pages/verification/signatory/create.vue`) — out of audio scope.

---

## 5. Cross-cutting facts

- All four `canvasser_voice` binary endpoints are **not** called through the generated JS
  client at runtime; the JS only borrows the URL constants from generated types
  (`uploadAudioNative.ts:15–16`; `uploadWakeWordClipNative.ts:12–13`). The actual
  multipart is OkHttp in the native plugin, so the shapes in §2.5/§2.6/§3.2/§3.3 are from
  the shipped dex (exact).
- Auth refresh on audio paths: only `/receive` has an explicit 401→refresh→retry
  (`uploadAudioNative.ts:210–240`); cached-upload and wake-word paths treat 401 as a
  generic failure (rows stay cached for the next tick; VAD segments are re-queued or
  force-cached).
- `data_complete` at shift end is gated on the `payloads` outbox draining, not on audio:
  the shift-end payload is only marked complete when no other payloads for that shift
  remain; cached audio rows do **not** block it (`useUploader.ts:43–74`). UNCONFIRMED:
  whether the server additionally reconciles audio spans (e.g. via `wallclock_start/end`
  continuity or `span_upload_id`) — no client code consumes such feedback.
- Constants worth mirroring in a reimplementation (`types/database/config.ts`, all remotely
  tunable): VAD threshold 0.8, segment cap 3 s, JS pool 120 s (3.84 MB), native store
  50 MB, cached-audio batch 64, cache TTL 4 days, geofence 50 km fetch / 10 km refresh /
  1 km warning / queue 4.
