# Audit: Interactions, Surveys & Tags — Numinar v10.0.0

Source: `/tmp/numinar_decompiled_rust.js` (line cites as `L<n>`). All claims are
code-confirmed unless marked **UNCONFIRMED**. This replaces the [H] hypotheses
in `docs/DESIGN-NUMINAR.md` §4 for the interactions/surveys/tags slice.

---

## 0. Transport layer (applies to every request below)

Fetch service: module 1398, `useFetchService` (L224969–225168).

- **Base URL selection** (L225043–225060): `base = usingROS ? ROS_URL : FAST_API_URL`.
  The `usingFastApi: true` flag carried on request objects is **not consulted** in
  this version — everything without `usingROS` goes to
  `https://fast-api.numinar.com/api` (constants at L202363–202400:
  `FAST_API_URL = https://fast-api.numinar.com/api`,
  `ROS_URL = https://rust-server.numinar.com`,
  `ROS_WS_URL = wss://rust-server.numinar.com/websocket`).
  So all `/v1/...` URLs below are `https://fast-api.numinar.com/api/v1/...`.
  (Contradicts `numinar/ANALYSIS.md`, which attributes `/v1/interactions/batch`
  to `mobile.numinar.com`; `mobile.numinar.com` does not appear in the bundle.)
- **Headers** (L225067–225076):
  - `Content-Type: application/json`
  - `numinar-origin: mobile`
  - `platform: android`
  - `x-org-id: <orgId>` (from `useCurrentOrgContext`; value may be `undefined`
    if no org selected — header is set unconditionally)
  - `sentry-sid: <Sentry session sid>` (undefined if no session)
  - `Authorization: Bearer <Auth0 access token>` — added when
    `requiresAuth !== false` (default true) and a token exists; `bearerOverride`
    can substitute a fresh token on the 401-retry path.
- **Default timeout** 61000 ms (L225054–225057); several calls below override to
  5000 or 10000 ms.
- **Retry**: axios-retry on the shared instance — `retries: 1`, only when the
  error message contains `"timeout"`, `shouldResetTimeout: true` (L225018–225026).
  No retry on 4xx/5xx or network-down.
- **401 handling** (L225082–225120): on 401, unless
  `response.data.detail === "You need to verify your email to access this resource"`,
  the app calls Auth0 `refreshAccessToken` once and retries the identical request
  with `bearerOverride`; if refresh fails → sign-out + toast
  "Session Expired / Please log in again."
- Axios; JSON bodies. Response bodies for all interaction POSTs are **unused** by
  the client (no parsing of the response payload anywhere in these flows).

---

## 1. POST /v1/interactions/batch — the single write path for all interaction types

Four construction sites, all identical shape:
`{ method: "POST", url: "/v1/interactions/batch", usingFastApi: true, data, orgId, timeout? }`.

| Site | Caller | Body | Timeout |
|---|---|---|---|
| L226387 | `useInsertInteraction` (module 1558) | `[ <one interaction object> ]` (always a 1-element array, L226388–226389) | 5000 ms |
| L226487 | `useBatchUpdate` (module 1558) | array (wraps non-array into 1-element, L226483–226486) | default 61000 ms |
| L359600 | `useInsertNotesInteraction` (module 2772) | `[ <notes object> ]` | 5000 ms |
| L383274 | `useBulkInsertCanvassInteraction` (module 3310) | array of canvass objects (one per voter) | 5000 ms |

### 1.1 Type guards — how the app classifies an interaction object

Evaluated in this exact order in `useInsertInteraction` (L226421–226436, duplicated
at L226442–226458); first match wins and becomes the offline-queue `url` label:

1. **`isCreateCanvassInteraction`** (module 1560, L226302–226317) → label
   `insertCanvassInteraction`. Requires keys: `project_id`, `voter_id`,
   `household_id`, `latitude`, `longitude`.
2. **`isCreateCallInteraction`** (module 1559, L226288–226297) →
   `insertCallInteraction`. Requires: `project_id`, `voter_id`, `call_length`.
3. **`isCreateRelationalSurveyInteraction`** (module 1561, L226322–226331) →
   `insertRelationalSurveyInteraction`. Requires: `voter_id` **and**
   `survey_type === "relational"`.
4. **`isCreateTagInteraction`** (module 1562, L226336–226345) →
   `insertTagInteraction` if true (requires `voter_id`, `tag_id`, `value`),
   otherwise the fallback label is **`insertNotesInteraction`** (no guard —
   notes is the default bucket).

Note the order matters: a canvass object also satisfies the call guard's subset,
but canvass is checked first. A notes object (`project_id`, `voter_id`, `value`,
`created_at`, `id`) fails all four guards → `insertNotesInteraction`.

### 1.2 Canvass interaction object (single) — `useCanvass.submitCanvass`, module 3310, L383315–383462

Built at the moment the canvasser taps submit in `CanvassSurveyTab` (module 3326,
L385402+): survey-completed path passes disposition `"canvassed"` (L385604, 385623);
household-unavailable path passes the selected reason string (L385640–385644).

```jsonc
{
  "id":            "<uuid v4>",                        // L383351
  "user_id":       "<current user id>",                // L383351 (arg5.id)
  "project_id":    "<project id | undefined>",         // L383353–383356
  "voter_id":      "<voter.id>",                       // L383357
  "latitude":      voter.registration_address_latitude,   // L383357 — ADDRESS geo
  "longitude":     voter.registration_address_longitude,  // L383357
  "user_latitude": "<device GPS lat as STRING | null>",   // L383358, 383405–383407
  "user_longitude":"<device GPS lng as STRING | null>",   // L383359, 383408–383410
  "disposition":   "canvassed" | "Not Home" | "Refused" | "Wrong Address"
                   | "Inaccessible Address" | "Dropped Literature" | "Other",  // L383360
  "household_id":  voter.house_hold_id,                // L383361 (sic: house_hold_id)
  "notes":         "<free text>",                      // only if notes non-empty, L383380–383381
  "notes_interaction_id": "<uuid v4>",                 // only with notes, L383382
  "survey_type":   "canvass",                          // L383363
  "survey_id":     "<survey id | undefined>",          // L383365–383368
  "survey_interaction_id": "<uuid v4>",                // only if survey_id set, L383370–383377
  "responses":     [ { "question_id": "<question.id>",
                       "tag_id":     "<question.tag_id | \"\">",
                       "response":   "<answer value>",
                       "tag_interaction_id": "<uuid v4>" } ],  // only for answered
                     // questions whose definition has tag_id; L383333–383347, 383399–383401
  "created_at":    "<new Date().toISOString()>",       // L383379
  "device_id":     "<uuid from AsyncStorage deviceUuid>",  // L383412
  "is_using_emulator": <bool>,                         // L383414
  "device_geolocation_enabled": <bool>,                // L383416
  "device_geolocation_permission_status": "granted"|"limited"|"blocked"|"denied"|"unavailable" // L383417
}
```

- `latitude/longitude` are the **voter's registered-address coordinates**; the
  canvasser's own GPS goes in `user_latitude/user_longitude` (strings, via
  `toString()`), or stay `null` if GPS fails.
- Device telemetry fields are best-effort: each is in its own try/catch that only
  logs on failure (L383440–383455). GPS via `getCurrentPosition
  {enableHighAccuracy: true, timeout: 30000}` (module 1564, L230635–230650).
- Disposition enumeration (UI picker, module 3328 site L384541 and L385148):
  labels → values: `"Not Home"→"Not Home"`, `"Refused Survey"→"Refused"`,
  `"Voter not at Address"→"Wrong Address"`, `"Inaccessible Address"`,
  `"Dropped Literature"`, `"Other"`; plus `"canvassed"` for the completed-survey
  path (L385604). No other values are emitted.
- After `mutate`, a **WebSocket** message is sent (only when online and a project
  is selected, L383420–383438) — see §6.
- Mixpanel events: `"Canvass Survey Submitted"` (L385613) and
  `"Edited Voter Notes"` when notes present (L383384–383396).

### 1.3 Bulk canvass interaction — `useBulkCanvass.submitCanvass` (module 3310, L383463–383566) + `useBulkInsertCanvassInteraction` (L383255–383314)

- Per-household bulk path builds one object per voter with the same fields,
  except: no `id`, no `survey_interaction_id`, and `responses` entries **omit
  `tag_interaction_id`** (L383481–383491). `voter_id` is initialized `""` then
  filled per voter (L383504; the per-voter mapping loop is partially garbled in
  decompilation, L383542–383544 — the exact per-voter field copy is **partially
  UNCONFIRMED**, but the array POSTed contains one canvass object per voter).
- `useBulkInsertCanvassInteraction` POSTs the whole array in one request
  (L383274), timeout 5000 ms. On success: invalidate `["user-outreach-stats"]`,
  toast `"<n> Interaction(s) have been submitted!"`, per-voter
  `setVoterInteraction`, `setStoredVotersAsCanvassed([ids])` (L383289–383293).
- On failure/offline: each object is wrapped `{url:"insertCanvassInteraction",
  data}` and queued via `addToOfflineBulkCanvass` (L383271, 383301, 383306).

### 1.4 Call interaction object — `useCall`, module 3285, L381252–381333

Built when a call survey is submitted from `CallSurveyTab` (module 3286,
L381369–381383, `onSurveySubmit` → `useCall`).

```jsonc
{
  "id":            "<uuid v4>",
  "user_id":       "<current user id>",
  "project_id":    "<project id>",        // required here (arg4.id, L381288)
  "voter_id":      "<voter.id>",
  "disposition":   "<CallDisposition value>",  // see enum below
  "call_length":   <number>,              // seconds; from CallScreen timer state
  "notes":         "<free text>",         // only if present (+ notes_interaction_id uuid)
  "survey_type":   "call",
  "survey_id":     "<survey id | undefined>",
  "survey_interaction_id": "<uuid v4 | undefined>",
  "responses":     [ { question_id, tag_id, response, tag_interaction_id } ],  // same rule as canvass
  "created_at":    "<ISO>"
}
```

- **No GPS and no device-telemetry fields** on call interactions (contrast with
  canvass). The type guard only demands `project_id`, `voter_id`, `call_length`.
- `CallDisposition` enum (module 1559, L226285):
  `Answered:"answered"`, `CallBack:"call-back"`, `DoNotCall:"do-not-call"`,
  `NoAnswer:"no-answer"`, `Voicemail:"voicemail"`,
  `WrongNumber:"wrong-number"`, `HungUp:"hung-up"`.
- Submitted through `useInsertInteraction` → 1-element `/v1/interactions/batch`.

### 1.5 Relational-survey interaction object — `useSubmitRelationalSurvey`, module 2675, L339202–339288

Built on save in the relational-survey screen (hook wired at L360249).

```jsonc
{
  "id":            "<uuid v4>",                 // L339240
  "user_id":       "<current user id>",         // L339240
  "voter_id":      "<voter id as STRING>" | "", // arg0.toString(), "" if null; L339242–339248
  "survey_type":   "relational",                // L339249 — this is what guard #3 keys on
  "survey_id":     "<survey id>",               // L339250
  "responses":     [ { question_id, tag_id, response, tag_interaction_id } ],  // L339222–339236
  "created_at":    "<ISO>",                     // L339252–339254
  "project_id":    "<project id>",              // L339255
  "notes":         "<free text>",               // only if present
  "notes_interaction_id": "<uuid v4>"           // only with notes, L339258
}
```

- No GPS/device fields, no `household_id`, no `disposition`.
- Sent via `useInsertInteraction` with `isRelationalSurvey: true` (L339279); on
  success additionally patches the `["voter-contacts", project_id]` query cache
  setting `has_interaction: true` for that voter (L226400–226416).

### 1.6 Notes interaction object — `VoterNotesTab` (module 3341, L386775–386861) + `useInsertNotesInteraction` (module 2772, L359583–359629)

```jsonc
{
  "project_id": "<project id>",      // L386830 (decompiler shows both project_id
                                     // and voter_id sourced from the same var;
                                     // project context is currentProject — see note)
  "voter_id":   "<voter id>",        // L386831
  "value":      "<notes text>",      // L386832
  "created_at": "<ISO>",             // L386833
  "id":         "<uuid v4>"          // added in the mutation itself, L359597
}
```

(The decompiled call site at L386826–386831 shows `project_id` and `voter_id`
both assigned from a variable named `user`/`id`; the `project_id` source is
likely the current project but is **UNCONFIRMED** at field level due to
decompiler variable reuse. Cross-check against `/tmp/numinar_decompiled_p1.js`
if this matters.)

- Success: toast "Note has been submitted!", invalidate `["voter-notes",
  voter_id]` (L359609–359612). Mixpanel `"Edited Voter Notes"` (L386835–386843).
- Notes read-back: **GET `/v1/voters/{voter_id}/notes`** (module 2772,
  `useGetVoterNotes`, L359630–359655), query key `["voter-notes", id]`,
  `initialData: ""`.

### 1.7 Tag interaction object — `useSubmitTag`, module 3295, L381575–381607

```jsonc
{
  "id":         "<uuid v4>",
  "created_at": "<ISO>",
  "updated_at": "<ISO>",             // same timestamp as created_at, L381585–381588
  "org_id":     "<current org id>",  // NOTE: inside the body, in addition to the x-org-id header
  "voter_id":   "<voter.id>",
  "tag_id":     "<tag id>",
  "value":      "<tag value (trimmed free text or choice)>",
  "user_id":    "<user id | undefined>",
  "project_id":            undefined,  // present as keys but undefined at both
  "question_id":           undefined,  // observed call sites (AddTagModal L381685,
  "survey_id":             undefined,  // tag-edit L381793) — they are survey-context
  "survey_interaction_id": undefined   // plumbing, only set when a survey supplies them
}
```

- Submitted via `useInsertInteraction` → batch. Trigger: user adds/edits a tag on
  the voter profile (`AddTagModal`, module 3294) or edits a tag inline in a
  survey (L381793). Mixpanel `"Edited Voter Tag"` (L382088–382099).
- Tag questions answered inside a canvass/call/relational survey are **not**
  separate tag interactions — they ride inside `responses[]` on the parent
  interaction (each with its own `tag_interaction_id`).

### 1.8 Success/failure handling of the batch POST (single-insert path, L226385–226462)

Online (`network.connectionState` true) → try POST. On success:
invalidate `["user-outreach-stats"]`, toast "Interaction has been submitted!"
(1 s), dispatch `setVoterInteraction(voter_id)`, `setStoredVotersAsCanvassed(
voter_id)` (marks the voter canvassed in offline voter storage, L226398–226399).
On throw → error toast "Failed to record data / There's no internet connection",
dispatch `setConnectionState(false)`, and queue offline with the classified label.
If already offline → skip the POST entirely and queue directly (L226441–226461).
`useBatchUpdate` additionally invalidates `["user-outreach-stats"]` on success
(L226495–226503).

---

## 2. Offline queue (AsyncStorage, module 1358, L225309–226281)

### 2.1 Storage schema (AsyncStorage keys)

| Key | Contents |
|---|---|
| `offline_buffer` | JSON array of `{url: <label>, data: <interaction object>}` — the outbox (L225395, 225628) |
| `offline_buffer_temp` | crash-safe copy made before a sync drain (L225480, 225548) |
| `offline_interaction_count` | decimal string, count already uploaded in current sync (L225497, 225556) |
| `offline_lock` | `"true"` while a queue mutation is in flight (L225422–225456) |
| `deviceUuid` | device id sent in interactions (L226093–226098) |
| `me`, `orgs`, `voters`, `substitute_number`, `lastEnv`, `async_test_key` | other offline cache (L225562–225582, 225755+, 226068) |

Queue item labels: `insertCanvassInteraction`, `insertCallInteraction`,
`insertRelationalSurveyInteraction`, `insertTagInteraction`,
`insertNotesInteraction` (§1.1).

### 2.2 Enqueue — `addToOffline` (L225602–225676) / `addToOfflineBulkCanvass` (L225677–225751)

1. Acquire `offline_lock` with retry: up to 10 attempts, backing off
   `(attempt+1) * 100 ms` (defaults num=10, num2=100, L225406–225461). On lock
   failure → toast "Unable to Store Offline Interaction - Too Many Retries",
   item **dropped**.
2. Read `offline_buffer` (default `[]`), push item(s), **dedupe**, write back.
3. **Dedupe** (`dedupeOfflineBuffer`, L225584–225601): key =
   `url + "_" + data.voter_id + "_" + data.project_id + "_" + (data.tag_id ?? "")`.
   Later duplicates overwrite earlier ones in place. Consequences:
   - repeated canvass/call/notes for the same voter+project collapse to the
     **latest** only;
   - tag interactions survive per distinct `tag_id`;
   - ordering is otherwise insertion order (FIFO).
4. Update Redux `offlineInteractionsCount`; toast "Interaction Saved! /
   \<n\> interactions pending upload" for canvass items; dispatch
   `setVoterInteraction` + `setStoredVotersAsCanvassed` so UI shows the voter as
   done even before upload.

### 2.3 Drain — `NetworkManagerComp` (module 1351, L230817–231093)

Trigger conditions (any of):
- Redux `websocketUp && connectionState` both true and not already syncing
  (effect, L231030–231051);
- App returns from background to `active` while online (L231053–231086);
- Periodic: every **15000 ms** interval (L230987–231020) runs the online check
  (below) and, on success, the sync after a **1500 ms** delay
  (callback4, L230966–230977).

Drain procedure (callback3, L230851–230964):
1. Reentrancy guard `isSyncing`.
2. `prepareOfflineBufferForSync` (L225471–225493): copy `offline_buffer` →
   `offline_buffer_temp`, delete `offline_buffer` (new submissions during sync
   start a fresh buffer), return deduped snapshot.
3. If empty, done. Else `setSyncState(true)`, `setSyncProgress(0)`.
4. **Batches of 10** (L230870): each item's `data` (label discarded — all five
   types are merged into one array) → `useBatchUpdate.mutateAsync({data})` →
   **POST /v1/interactions/batch** (array, default 61 s timeout, L226487).
   For each `insertCanvassInteraction` item a WS "canvassed" message is also
   sent (L230884–230897). Progress Redux updated per batch;
   `setOfflineInteractionsCount(remaining)`.
5. On total success: toast "Connection Restored! / Successfully uploaded \<n\>
   interactions" (only if the app had been offline), refresh offline voters,
   `commitOfflineBufferAfterSync` (deletes `offline_buffer_temp` and
   `offline_interaction_count`, L225513–225521).
6. On any batch failure: toast "Unable to Upload Offline Interactions … will
   retry uploading once connection is restored", **rollback** (callback2,
   L230844–230849): write remaining items to `offline_buffer_temp`, then
   `rollbackOfflineBuffer` (L225522–225545) merges temp back **behind** any
   newly queued items → failed items keep their relative order but newer
   submissions stay ahead… (actually `[...temp, ...buffer]`; temp = un-sent
   remainder, so unsent old items precede new ones). `setConnectionState(false)`.
7. App-state `inactive` mid-sync also triggers rollback (L231077–231081).

No max-retry count or dead-letter: failed items stay in the buffer and are
retried on the next trigger, indefinitely.

### 2.4 Online check — HEAD /v1/mobile_204 (L230834)

`{ method: "HEAD", url: "/v1/mobile_204", usingFastApi: true, requiresAuth:
false, timeout: 10000 }` — i.e. `HEAD https://fast-api.numinar.com/api/v1/mobile_204`,
**no Authorization header**. Run every 15 s and before each sync; success sets
`connectionState true`, failure sets it false (L230986–231015).
Redux: `connectionState` default true; setting it false also flips
`websocketUp` to false (network slice, L199290–199341).

---

## 3. Canvassing QA tracking — POST /v1/canvassing-qa/tracking

Module 1563 (`insertCanvassQATracking`, L230656–230720), invoked from the 15 s
interval in `NetworkManagerComp` when: user loaded, Auth0 user present, org
selected, and a **project is currently selected** (L230986–231000).

```jsonc
// POST https://fast-api.numinar.com/api/v1/canvassing-qa/tracking, timeout 10000
{
  "project_id": "<current project id>",
  "latitude":   <number | undefined>,   // device GPS, raw numbers (not strings)
  "longitude":  <number | undefined>,
  "device_id":  "<deviceUuid>",
  "device_geolocation_enabled": <bool>,
  "device_geolocation_permission_status": "granted"|"limited"|"blocked"|"denied"|"unavailable",
  "is_using_emulator": <bool>
}
```

- Cadence: every 15 s while the app is foreground (the interval is a React
  effect; cleared on unmount). Fire-and-forget: errors only logged
  (L230693–230697), no offline queuing.
- This is the continuous canvasser-location beacon; it is separate from the
  per-interaction GPS.

---

## 4. Relational surveys — read side

Module 2675 (L339049–339097):

- **GET `/v1/relational-survey`** — `useRelationalSurvey`, query key
  `["relational-survey"]`, org header. List of org-level surveys.
- **GET `/v1/relational-survey/{project_id}`** — `useRelationalSurveyForProject`,
  enabled only when the project's `survey_id ?? ds_id` is truthy (L360227–360240).
- Question/answer shape inferred from consumption: `data.questions[]` with
  `id`, `tag_id`, and jump-logic; tag values come back as `data.tags` (map of
  `{tag_id, tag_value}`) — see the mapping at L360014–360035 and the
  voter-tags display object `{tag_id, tag_name, tag_value, tag_type:
  "multi-choice", question_text, response_set}` at L382076. Full GET response
  schema is **UNCONFIRMED** beyond these consumed fields.
- Submit: covered in §1.5 (goes to `/v1/interactions/batch`, **not** to a
  survey endpoint).
- Related but distinct: `useRelationalText`/`ForProject` GET
  `/v1/relational-text[/​{project_id}]` (L339009, 339034), and
  **POST `/v1/interactions/relational-text`** (L339109) with body
  `{user_id, voter_id, project_id, outreach_type: "text", abev_status,
  created_at, device_id, is_using_emulator}` (L360277–360281, 339106–339108) —
  relational-texting interactions, a separate endpoint from `/batch`.

---

## 5. Tags — read side

- **GET `/v1/tags`** — `useAllTags` (module 2771, L359541–359567), query key
  `["allTags"]`; org's tag definitions for the AddTagModal picker.
- **GET `/v2/voter_tags/{voter_id}`** — `useVoterTags` (module 2771,
  L359516–359540), query key `["tags", voter_id]`; per-voter existing tag
  values, consumed as `{tags: {<n>: {tag_id, tag_value, ...}}}` (L382038–382040,
  382064–382079).
- Tag writes: only via interactions batch (§1.7). No PUT/DELETE tag endpoints
  exist in the bundle.

---

## 6. WebSocket side-channel — "canvassed" notifications

`wss://rust-server.numinar.com/websocket?token=<access_token>&first_name=…&last_name=…&email=…&org_name=…&org_id=<id>&platform=mobile`
(module 1371 `createWs`, L202420–202467; 30 s `"ping"` keepalive, L202449–202459).

Immediately after a **successful online canvass submit**, and again per canvass
item during offline drain, the app sends (L383423–383430, L230884–230897):

```jsonc
{ "action": "sendmessage",
  "data": "{\"type\":\"canvassed\",\"device_id\":\"<websocketId (uuid v4, L202417)>\",
            \"voter_id\":\"...\",\"org_id\":\"...\",\"project_id\":\"...\",\"user_id\":\"...\"}" }
```

Best-effort: wrapped in try/catch, failure only logged (L383434–383437).

---

## 7. Other interaction-read endpoints

- **GET `/v1/voters/{voter_id}/interactions`** — `useGetVoterActivityFeedInteractions`
  (module 2778, L360739–360767), query key `["voter-interactions", id]`,
  `initialData: []`; powers the voter activity feed.
- **POST `/v1/interactions/call`** — `useUpdateCallInteraction` (module 3285,
  L381238–381251): `{project_id, voter_id, disposition, call_length}`.
  Triggered from the calling screen's `DispositionModal` submit (L382806–382822)
  — i.e. when a call ends **without** a survey, the disposition is posted here
  directly (separate from `/batch`, no offline queue, no GPS/device fields).
  Disposition values are the `CallDisposition` enum (§1.4).
- `GET /v1/interactions/callback` (listed in `numinar/ANALYSIS.md`) does **not**
  appear anywhere in the decompiled bundle — **UNCONFIRMED / likely stale**.

---

## 8. Client-side data collection summary (this scope)

| What | Where it goes | Cadence/trigger |
|---|---|---|
| Voter address lat/lng + canvasser GPS (strings) + device id + emulator flag + location-enabled + location-permission status | `/v1/interactions/batch` (canvass objects) | per canvass submit |
| Device GPS (numbers) + same device telemetry | `/v1/canvassing-qa/tracking` | every 15 s while a project is selected |
| Call duration + disposition | `/v1/interactions/batch` or `/v1/interactions/call` | per call end |
| Survey answers keyed to question/tag ids with per-answer uuids | `/v1/interactions/batch` `responses[]` | per survey submit |
| Free-text notes | `/v1/interactions/batch` (notes object, or `notes` on parent interaction) | per save |
| voter_id/org_id/project_id/user_id | WS `canvassed` message | per successful canvass |
| Location permission request | `react-native-permissions` ACCESS_FINE/COARSE check, GPS request with rationale dialog "Numinar needs permission to request your location." (L230638) | per submit |

Everything above is foreground-only (no background location; drain triggers are
WS-state, AppState, and the 15 s in-app interval).

## 9. Notable audit observations

1. **Dedupe data loss**: the offline queue collapses repeat interactions for the
   same `(url, voter_id, project_id, tag_id)` to the latest one (L225584–225601).
   Two door-knocks at the same voter while offline upload only the second.
2. **No idempotency key beyond client uuids**: each interaction carries a
   client-generated `id` (uuid v4); retry after ambiguous failure can produce
   server-side duplicates if the first request actually landed, since the 10-item
   drain batch has no per-item acknowledgment handling — the whole batch is
   rolled back on any error (L230948–230956).
3. **Org context is client-supplied** (`x-org-id` header + `org_id` in tag
   bodies) with no visible server-binding check on the client.
4. `usingFastApi` is dead config; **all** v1/v2 API traffic in this scope goes to
   `fast-api.numinar.com`, not `mobile.numinar.com` as previously recorded.
5. `voter_id` in the relational-survey interaction is coerced to string
   (`arg0.toString()`, L339243); elsewhere it is the raw voter id.
6. Device UUID is self-minted (AsyncStorage `deviceUuid`, random uuid v4,
   L226090–226110) — trivially resettable, not a hardware identifier.
