# Numinar audit — Push, Realtime & Full Endpoint Sweep

App: `com.numinar.numinar` v10.0.0 (Hermes bytecode v96, decompiled).
Primary source: `/tmp/numinar_decompiled_rust.js` (line citations `L<n>` refer to it).
Cross-checked against `/tmp/numinar_decompiled_p1.js` (register-level) where noted.
Date: 2026-09-19.

> **Correction to `numinar/ANALYSIS.md`:** the "main `/v1/...` API" is **not**
> hosted on `mobile.numinar.com`. The only occurrence of `mobile.numinar.com`
> in the bundle is a deep-link rewrite (`numinar://` →
> `https://mobile.numinar.com/`, L337400). All `/v1/`, `/v2/`, `/v3/` API
> traffic goes to `https://fast-api.numinar.com/api` (`usingFastApi: true`)
> or `https://rust-server.numinar.com` (`usingROS`/`ros: true`). Host
> constants: L202360–202395.

---

## 0. Shared transport layer (module 1398, `useFetchService`, L225026–225140)

Every application API call goes through one axios wrapper:

- Base URL: `usingROS ? ROS_URL : FAST_API_URL` (L225060), i.e.
  `https://rust-server.numinar.com` or `https://fast-api.numinar.com/api`.
- Headers on every request (L225064):
  - `Content-Type: application/json`
  - `numinar-origin: mobile`
  - `platform: android`
  - `x-org-id: <current org id>`
  - `sentry-sid: <Sentry session id>` (may be undefined)
  - `Authorization: Bearer <Auth0 access token>` — added when `requiresAuth`
    (default true) and a token exists; `bearerOverride` supported.
- Default timeout **61000 ms** (overridable per request, L225049).
- axios-retry: **1 retry**, only when the error message contains `"timeout"`,
  `shouldResetTimeout: true` (L225016–225023).
- 401 handling (L225084–225120): if `detail === "You need to verify your
  email to access this resource"` → rethrow. Otherwise one
  `refreshAccessToken()`; on success the request is retried once with
  `bearerOverride`; on refresh failure → logout + toast "Session Expired /
  Please log in again."
- `makeApiRequest` (L225129+) is the same call plus Redux `onStart/onSuccess/
  onError` action dispatch.

The SSE hook uses the same header convention but **not** the axios wrapper
(see §2). The WebSocket carries the token in the query string (§3).

---

## 1. Push notifications (FCM via Expo + Twilio + Intercom)

### 1.1 Token registration — `POST /v1/push/tokens`

- **Hook:** `useSaveExpoToken`, module 2633, L332045–332059. Request literal
  at **L332051**: `{ method: "POST", url: "/v1/push/tokens",
  usingFastApi: true, orgId, data }` →
  `POST https://fast-api.numinar.com/api/v1/push/tokens`.
- **Body** (constructed at the two call sites L393042–393045 and
  L393098–393102, identical):
  ```json
  {
    "expo_push_token": "<ExponentPushToken[...]>",
    "is_android": true,
    "device_push_token": "<native FCM token>"
  }
  ```
  - `expo_push_token` — from `expo-notifications`
    `getExpoPushTokenAsync({ projectId })` where `projectId` is the EAS
    project id (`690023b7-7c29-48ba-a024-2757d50beed2`) read from
    `expoConfig.extra.eas.projectId` / `easConfig.projectId`
    (`registerForPushNotificationsAsync`, module 2629, L331974–332024). That
    call itself contacts `https://exp.host/--/api/v2/...` (L222531, L222922)
    — an Expo-hosted round trip, not Numinar.
  - `is_android: true` is **hardcoded** in this build.
  - `device_push_token` — `Notifications.getDevicePushTokenAsync()` `.data`
    (raw FCM registration token).
- **Trigger:** a `useEffect` in the authenticated root component (L393020+)
  fires once all of: user profile loaded, `deviceUuid` available, `orgId`
  selected, and notification permission state set. It first runs
  `registerForPushNotificationsAsync()` (which itself requests the
  `POST_NOTIFICATIONS` runtime permission via
  `getPermissionsAsync`/`requestPermissionsAsync`, L331977–331983), stores
  the Expo token in a module-level singleton (`setExpoNotificationToken`,
  module 1371 L202480–202485), then fetches the FCM token and POSTs the body
  above. The same registration is repeated from the
  `getLastNotificationResponseAsync()` cold-start branch (L393098+).
  Errors are swallowed with `console.error`.
- **Response handling:** `mutateAsync(...)` result unused; no query
  invalidation on this mutation.

### 1.2 Token deletion — `DELETE /v1/push/tokens/{token}`

- **Hook:** `useDeletePushNotificationToken`, L332060–332085; request literal
  **L332067**: `DELETE /v1/push/tokens/${arg0}`, `usingFastApi: true`, org
  header. `arg0` is the **Expo** push token.
- **Trigger:** logout. `HomeSideMenu` → `handleLogout` (L391185–391200):
  reads the cached Expo token from the module-1371 singleton, calls the
  DELETE, then clears project state and signs out. Failure is caught and
  only logged ("Error deleting push notification token on logout").
- On success invalidates `["push-notifications"]` (L332077).

### 1.3 Notification inbox — `/v1/push/notifications*`

All in module 2633, `usingFastApi: true`, standard headers, query key
`["push-notifications"]`:

| Method & path | Line | Body / params | Trigger |
|---|---|---|---|
| `GET /v1/push/notifications` | L332094 | — | Inbox screen query (`useNotifications`) |
| `POST /v1/push/notifications/read` | L332139 | `{ expo_push_token: <token or "">, message_ids: [<notification ids>] }` (built L341112–341117) | Opening/viewing a message group (`useMarkNotificationRowsAsRead.markOrgNotificationsRead`) — only unread rows' ids are sent |
| `POST /v1/push/notifications/read-all` | L332115 | none | Mark-all-read UI action |
| `DELETE /v1/push/notifications` | L332163 | none | Delete-all UI action |
| `DELETE /v1/push/notifications/bulk` | L332187 | `data` = caller-supplied id list (exact field name UNCONFIRMED — passed through opaquely) | Bulk-delete UI action |

Each mutation invalidates `["push-notifications"]` on success.

### 1.4 Incoming push handling (client-side, no server call)

`addNotificationReceivedListener` (L393048–393069) and the response listener
(L393071–393088) branch on `notification.request.content.data`:

- `captureAnnouncement(...)`: if the push is an Intercom "announcement"
  (`data.intercom_push_type === "push_only"`, module 2634 L332430–332470), it
  is written to **AsyncStorage only** (`"announcements"` key, module 2635
  L332222–332380) and the announcements query is invalidated. Announcements
  never hit a Numinar endpoint — `useAnnouncements` reads local storage
  (L332495–332512).
- `data.type === "BADGE_SYNC"` → refetch `["push-notifications"]`.
- `data.twi_message_type === "twilio.voice.call"` → handed to the Twilio
  Voice native module (`voice_handleEvent`, L336933–336944; call at L393057).
  The notification handler is also configured to **suppress banner/sound/
  badge** for `twilio.voice.call` pushes (L394464, L394508).
- Anything else → refetch `["push-notifications"]`.

Native side (from the APK tree): three FCM services — app notifications,
Twilio Voice, Intercom (see `numinar/tree/` manifest). Foreground-only.

---

## 2. SSE (Server-Sent Events)

### 2.1 The `useSSE` hook (module 2678, L338718–338963)

Implementation: a bundled XHR-based EventSource polyfill (modules
2679/2680, L338262–338716) that sends `Accept: text/event-stream` (L338378)
and auto-detects line endings.

Connection setup (L338790–338850):

- URL: `<base>/<path>[?<params>]` where base is `ROS_URL` when
  `useRos: true`, else `FAST_API_URL` (L338813–338818). Leading `/` on the
  path is stripped.
- Headers (L338820–338827):
  - `x-org-id: <orgId or "">`
  - `Authorization: Bearer <accessToken from redux auth slice>`
- Throws `"No access token available"` if no token (L338902).
- Event name defaults to `"update"`; `reconnectInterval` default **3000 ms**
  (L338742–338750).
- **Message handling:** `JSON.parse(event.data)`; parse failures logged
  ("Failed to parse SSE message:") and dropped (L338852–338864). Parsed
  object goes to the caller's `onMessage`.
- **Reconnect/backoff:** on `error`: sets error state, fires `onError` /
  `onDisconnect`, closes the connection, and — cross-checked in p1
  (L974907–974945, `_closure2_slot6 > 0`) — schedules exactly one reconnect
  via `setTimeout(reconnect, reconnectInterval)`; **flat interval, no
  exponential backoff, no retry cap**.
- **Lifecycle:** closes on `AppState` → `background`, reconnects on
  `active` (L338940–338959); reconnects when network `connectionState`
  flips back on (L338927–338936); closes on unmount and cancels the pending
  reconnect timer (L338912–338925).
- Only one live connection per hook instance (`closure_1_16` ref closed
  before reopen).

### 2.2 `GET /v1/projects/sse/updates` (fast-api)

- **Call site:** `useProjectLoadingSSE`, **L339355**:
  `useSSE("/v1/projects/sse/updates", { enabled, onMessage })` →
  `GET https://fast-api.numinar.com/api/v1/projects/sse/updates`, default
  event name `update`.
- **Purpose:** project data-prep progress. Paired with a REST seed:
  `GET /api/v3/project/loading_status/<projectId>` (ROS, **L339336**),
  response `.data.status`.
- **Message shape:** `onMessage(status)` writes `status.status` into query
  cache `["project_loading_status", projectId]` (L339350–339353). Status
  value domain (module 2677, L338160–338168): `not_started`, `in_queue`,
  `in_progress`, `ready`, `failed`. Inner field names beyond `status`:
  UNCONFIRMED.
- **Trigger/cadence:** enabled whenever a call/canvass screen mounts with a
  current project (`useProjectLoadingSSEStatus`, L339458–339465; consumed at
  L382808). Also re-fetches the seed query on every app-foreground
  (L339318–339332).

### 2.3 `GET /api/v3/events/source/outreach/{projectId}` (rust-server)

- **Call site:** `useOutreachStatusSSE`, **L381100**; `useRos: true`,
  `eventName: "outreach_status"` (L381101–381109) →
  `GET https://rust-server.numinar.com/api/v3/events/source/outreach/<projectId>`.
- **Seed:** `GET /api/v3/outreach/status/<projectId>` (ROS, L381089),
  flattened by `flattenOutreachStatus` (strips the `texting_counts` key,
  L381058–381064).
- **Message shape:** merged into `["outreach_status", projectId]` cache.
  Exact fields UNCONFIRMED (decompilation of the merge is lossy); the
  surrounding UI reads texting/calling aggregate counts.
- **Trigger:** call screen mount with current project
  (`useSseOutreachStatus(projectId)`, L382628).

### 2.4 `GET /api/v3/events/source/calls/{projectId}` (rust-server)

- **Call site:** `useCallingSSE`, **L381150**; `useRos: true`,
  `eventName: "call_update"` (L381139–381154) →
  `GET https://rust-server.numinar.com/api/v3/events/source/calls/<projectId>`.
- **Seed:** `GET /api/v3/project/<projectId>/queue` (ROS, L381139),
  response used as `{ queue: [...] }`.
- **Message shape** (fully recovered from the reducer L381160–381235):
  ```json
  {
    "type": "placing" | "established" | "detected" | "completed",
    "voter_id": "<id>",
    "voter_phone_number": "<string, may be ''>",
    "voter_first_name": "<string>", "voter_last_name": "<string>",
    "call_status": "<string>", "twilio_call_status": "<string>",
    "registered_party_roll_up": "<string>"
  }
  ```
  Effects: `placing` inserts/updates the voter in the on-device call queue;
  `established`/`detected` update `calling_status`/`twilio_call_status`;
  `completed` removes the voter from the queue.
- **Trigger:** call screen (`useSseCallStatus(projectId)`, L382638).

---

## 3. WebSocket — `wss://rust-server.numinar.com/websocket`

### 3.1 Connection establishment

- **`createWs`** (module 1371, L202420–202488). URL built at **L202441**:
  ```
  wss://rust-server.numinar.com/websocket
      ?token=<Auth0 access token>
      &first_name=<urlencoded, '' if missing>
      &last_name=<urlencoded, '' if missing>
      &email=<urlencoded>
      &org_name=<urlencoded org.name>
      &org_id=<org.id>
      &platform=mobile
  ```
  i.e. the JWT and PII (name, email, org) travel **in the query string**.
- A per-app-lifetime `websocketId` (uuid v4, module 1372) is generated at
  module load (L202410) and exposed via `getWebsocketId()`; it is sent as
  `device_id` in Twilio/amd_call payloads and canvassed WS messages.
- **Keepalive:** literal text frame `"ping"` every **30000 ms**
  (`setInterval`, L202451–202461). Incoming `"ping"` frames are ignored
  (L338100).
- **Component:** `Websocket` (module 2671, L338041–338257) mounted in the
  authenticated tree. Connects only when: network online, user + org loaded,
  `reopenWebsocket` flag true, access token present. If the stored JWT is
  expired (checked by decoding `exp`, L338236–338250) it is refreshed via
  Auth0 first.
- **Reconnect policy** (L338155–338230):
  - `onclose` → clear ping interval, dispatch `websocketOnClose(<CloseEvent
    JSON>)`. If `code === 1001` ("ROS killed us") → `setWebsocketReopen(true)`
    → immediate reconnect on next effect run. Otherwise
    `androidClosedWS()`.
  - Separate effect (L338212–338230): when `androidClosedWS` is set and
    network is up, `setTimeout(5000)` → `setWebsocketReopen(true)`. So:
    immediate reconnect on server-initiated 1001, **5 s** delayed reconnect
    otherwise. No backoff growth, no attempt cap.

### 3.2 Inbound messages

`ws.onmessage` (L338094–338152): frames other than `"ping"` are parsed as
`JSON.parse(JSON.parse(arg0.data).data)` — i.e. envelope
`{ "data": "<stringified JSON>" }` (matches the outbound envelope below).
Parsed object fields:

- `user_id` — if present and equal to the current user's id, a `device_id`
  check follows (self-echo detection; the decompiled branch body is lossy,
  exact action UNCONFIRMED).
- `org_id` — compared against current org id.
- `type === "canvassed"` with `project_id`, `voter_id`: if `project_id`
  matches the current project → Redux `setVoterInteraction(voter_id)` +
  `setStoredVotersAsCanvassed(voter_id)` (marks the voter canvassed locally,
  including offline cache); if it matches the cached project id → only the
  offline-cache update; if no `project_id` → unconditional update.
  Purpose: **live multi-canvasser dedup** — another canvasser's doorknock
  greys out the voter on this device in real time.

### 3.3 Outbound messages

The only `ws.send(...)` besides `"ping"` is in the offline-sync pump
(`NetworkManagerComp`, **L230885–230906**). For every buffered
`insertCanvassInteraction` uploaded to `/v1/interactions/batch`, the app also
sends:

```json
{
  "action": "sendmessage",
  "data": "{\"type\":\"canvassed\",\"device_id\":\"<websocketId uuid>\",\"voter_id\":\"<id>\",\"org_id\":\"<id>\",\"project_id\":\"<id>\",\"user_id\":\"<id>\"}"
}
```

(`data` is a **string**, not an object — double-encoded JSON.) Trigger:
only during offline-queue drain while the socket is open. There is no
outbound message on the online (non-queued) canvass path — UNCONFIRMED
whether the server broadcasts those some other way.

---

## 4. Twilio voice (voter outreach calling)

SDK: `@twilio/voice-react-native-sdk` (module 2637; `new Voice()` memoized
per call screen, L380243–380246). The app **receives** the call as VoIP: the
server dials the voter and bridges back to the app (CallInvite flow); this
is outreach calling, not a predictive dialer.

| # | Request | Line | Details |
|---|---|---|---|
| 1 | `GET /api/v3/auth_token` (ROS) | **L380539** | Params (**L380541–380542**): `{ user_id, org_id, device_id: getWebsocketId(), platform: "fcm" }`. Returns a Twilio access token → Redux `_getTwimlAppToken` (L225197–225199). Trigger: `initBeforeCall()` when the user taps to start calling and no active call. Errors → `twilioFailed`. |
| 2 | `voice.register(<token>)` | L380588 | Registers the device with Twilio for incoming VoIP; then `_resetTwimlAppToken()`. |
| 3 | `POST /api/v3/amd_call` (ROS) | **L380413** | Body (**L380415–380417**): `{ org_id, user_id, project_id, state: "start"\|"stop", voter_id: "", testnumber, sim_calls: <project.simultaneous_calls, default 6>, substitute_number, device_id: getWebsocketId() }`. Trigger: `postCall("start", validTestNumber)` after register; `postCall("stop","")` on screen-blur/disconnect (L380395, L380519). "amd" = answering-machine detection; server places the actual voter call. |
| 4 | `GET /api/v3/twilio_numbers` (ROS) | **L382665** | No params/body. Trigger: call screen mount **and every 120000 ms** while the screen is focused (`setInterval`, L382705–382717). Response → `_phoneNumbers`; the UI checks `number_type === "calling"` (L382653–382655). |
| 5 | `GET /v1/projects/{projectId}/counts` (fast-api) | **L380373** | Trigger: `useEffect` on current-project change in the call screen; response → `_getVoterCount`. |
| 6 | `POST /v1/interactions/call` (fast-api) | **L381243** | Body: `{ project_id, voter_id, disposition, call_length }`. Trigger: disposition modal submit after a call (`useUpdateCallInteraction`; call site L382854–382860). |
| 7 | Incoming FCM `twilio.voice.call` | L393056 | → `Voice.handleFirebaseMessage(data)` → native `voice_handleEvent`. Then `CallInvite` event wiring with Accepted/Rejected/Cancelled handlers and a 500 ms timer (L380472–380489). |

Call-survey results go through `useCall` → the normal interaction pipeline
(`/v1/interactions/batch`, interactions-surveys scope), with
`survey_type: "call"`, `call_length`, `disposition`, `notes`,
`notes_interaction_id`, optional tag responses (L381275–381335).

Mic permission is requested on call-screen mount (`requestMicPermission`,
L380352); audio device enumeration/selection is local-only
(`voice_getAudioDevices`, L380424–380440).

---

## 5. Leaderboards

- **`GET /v1/mobile/leaderboard`** (fast-api), request literal **L389369**;
  hook `useLeaderboard` (module 3359, L389337–389405).
- **Params** (confirmed in p1 L1131704–1131745): `{ cycle?, start_datetime?,
  end_datetime? }` — all optional; derived by `datePresetToQueryParams`
  (module 3355) from the user's date-preset/cycle-year selection
  (L389509). Axios serializes them as query string.
- **Trigger:** Leaderboard screen query, `enabled` = cycle state hydrated
  **and** org flag `has_mobile_leaderboard_enabled` (checked on the org
  object, L231552; UI strings L388174, L352562). Query key
  `[orgId, "mobile-leaderboard", cycle, start_datetime, end_datetime]`;
  pull-to-refresh refetch; offline shows a dedicated empty state.
- Response rows feed `useLeaderboardRows` (local transform).

---

## 6. Paid-relational payout flow

Gated by org flag (`usePaidRelationalEnabled`, L340523–340526).

- **`GET /v2/me/relational-payment`** (fast-api), **L339163**
  (`useGetRelationalPaymentDetails`, query key `["relational-payment"]`,
  `refetchOnWindowFocus: true`). Response fields read by the UI (module
  2693, L340426–340455): `relational_paid_potential` (dollars),
  `relational_paid_pending_contacts`, `relational_paid_out_contacts`,
  `relational_paid_potential_contacts`.
- **`POST /v2/me/relational-payment`** (fast-api), **L339185**
  (`useCreateRelationalPayment`). Body (**L340462–340465**):
  ```json
  { "timezone": "<Intl.DateTimeFormat().resolvedOptions().timeZone>" }
  ```
  Trigger: user taps "Redeem $N" in `RedeemPaymentDialog` (shown from the
  Achievements screen, L340529+). Success toast "Successfully submitted
  payout request / Please check your email for further instructions";
  invalidates `["relational-payment"]`. Payout itself is handled
  server-side via email; no payment credentials touch the app.
- The `["relational-payment"]` query is also invalidated after each
  relational-text interaction (L339129) — billable-contact accounting.

---

## 7. Contact matching (relational organizing upload)

Flow (`ContactsListScreen`, module 2715, L353306–353620):

1. **Permission:** `PermissionsAndroid.request(READ_CONTACTS)` with the
   rationale text (L353459–353466): *"You are consenting to our retention
   and use of your contacts for voter matching, outreach, and sharing. See
   our privacy policy for more information."*
2. **Collection:** on user tap of "match contacts"
   (`MatchContactsPrompt.onMatch`, L353540–353560), the app calls
   `react-native-contacts` **`getAll()`** (module 2716, L352666–352672) —
   the **entire device address book** (all fields that library returns:
   names, phone numbers, emails, postal addresses, etc. — full record shape
   is library-defined; no client-side minimization is visible).
3. **Upload — `POST /v1/contact-matches`** (fast-api), request literal
   **L352984**. Body: `{ contact_data: [<full contact records>] }`
   (`mutate({ contact_data })`, L353544/L353555). This is the largest PII
   egress in the app: the whole address book leaves the device.
4. **Polling — `GET /v1/contact-matches`** (fast-api), **L352963**; query
   key `["contact-matches"]` with `refetchInterval: 5000` ms
   (L353341–353347). Client filters by `match_state === org.selected_state`
   and sorts by `created_at`; when the newest request reaches
   `status === "completed"` polling effectively stops via `enabled` logic
   (status domain, module 2719 L353631 area: `received`, `processing`,
   `completed`, `error`). UI warns matching takes "30 – 60 seconds".
5. **Results — `GET /v1/voter-contacts/{projectId}`** (fast-api),
   **L353031** (enabled once the latest match is completed), plus
   `GET /v1/voter-contacts` (**L353006**) for the unscoped list. Rows carry
   `contact_names[]`, `has_interaction`, voter linkage; sorted locally by
   contact name.

---

## 8. Relational texting (adjacent, in scope via contact matching)

- **Server-side send — `POST /api/v3/bandwidth/batch-texts`** (ROS),
  **L383772** (`useSendText`, module 3312). Body (built L385500–385535 and
  L384879–384910):
  ```json
  {
    "texts": [{
      "voter_id": "<id>",
      "voter_number": "<substitute number, else cell_phone_area_code + cell_phone_number>",
      "text_payload": "<text_body>",
      "media_urls": "<media_url>",
      "first_name": "<voter first name>"
    }],
    "project_id": "<id or ''>",
    "from_number": "<project.specific_number, omitted if unset>",
    "user_id": "<id>"
  }
  ```
  Trigger: "Send text(s)" in the follow-up text modal (canvass flow,
  L385500) or household batch text (L384879). Success toast; no retry.
- **`GET /api/v3/bandwidth/numbers`** (ROS), **L383749**
  (`useBandwidthNumbers`, `staleTime: Infinity`). Response `bw_nums[]` with
  `status` checked against `TextingNumberStatusType` (module 3313:
  `TWILIO_APPROVED`, `VERIFIED`, `10DLC-VERIFIED`, …). Trigger: canvass
  survey screen when the project has follow-up texts.
- **Native SMS path:** `NativeTexting` TurboModule (module 2725,
  L353631–353639) — `sendText(cell_phone_number, text_body, …)` sends SMS
  **from the user's own SIM** (L360432–360445). On result `"sent"` the app
  records the interaction:
- **`POST /v1/interactions/relational-text`** (fast-api), **L339109**
  (`useCreateRelationalTextInteraction`). Body (built L360261–360272, fields
  added in hook L339098–339112):
  ```json
  {
    "user_id": "<id>", "voter_id": "<id>", "project_id": "<id>",
    "outreach_type": "text",
    "abev_status": "<voter absentee/early-vote status>",
    "created_at": "<ISO8601>",
    "device_id": "<device uuid>",
    "is_using_emulator": <bool>
  }
  ```
  Success updates `["voter-contacts", projectId]` cache
  (`has_interaction: true`) and invalidates `["relational-payment"]`,
  `["user-outreach-stats"]`.
- Relational text/survey templates: `GET /v1/relational-text` (L339009),
  `GET /v1/relational-text/{projectId}` (L339034),
  `GET /v1/relational-survey` (L339059),
  `GET /v1/relational-survey/{projectId}` (L339084) — all fast-api GETs.

---

## 9. Complete endpoint inventory (sweep results)

Method: exhaustive grep for `url:` literals and every quoted string
containing `/v1/`, `/v2/`, `/v3/`, `/api/` across the 400,709-line bundle
(69 raw hits; third-party SDK internals separated below). **Host** column:
FA = `https://fast-api.numinar.com/api`, ROS = `https://rust-server.numinar.com`.
**Owner**: HERE = documented in this file; CC = canvassing-core.md;
IS = interactions-surveys.md; AS = auth-session.md (cross-references per
assignment; those files are owned by other auditors).

### 9.1 Numinar first-party endpoints

| Method | Path | Host | Line | Trigger | Owner |
|---|---|---|---|---|---|
| GET | `/v1/me` | FA | L230752 | bootstrap profile (offline-cached) | AS |
| PUT | `/v1/me` | FA | L230782 | first-run registration (`has_registered: true`) | AS |
| HEAD | `/v1/mobile_204` | FA | L230834 | connectivity check, `requiresAuth:false`, timeout 10 s, **every 15 s** (L230971) | HERE §9.4 |
| GET | `/v1/my-orgs-mobile` | FA | L231418 | org list bootstrap | AS |
| GET | `/v2/orgs/{orgId}` | FA | L231469 | org detail bootstrap | AS |
| GET | `/v1/public-orgs` | FA | L231287 | public org browser | AS |
| POST | `/v1/orgs/{orgId}/join` | FA | L231309 | join public org | AS |
| PUT | `/v1/orgs/{orgId}/invite-status` | FA | L231332 | accept/decline invite, body `{invite_status}` | AS |
| POST | `/v1/verification-email` | FA | L337601 | resend verification email | AS |
| GET | `/v3/projects` | FA | L339387 | project list (relational augmentation, offline cache) | CC |
| GET | `/v3/projects/{projectId}` | FA | L226218 | project refresh on select | CC |
| GET | `/v2/mobile-app/projects/{id}/voters` | FA | L226164 | voter download; params `{include_tags, compress:true}` → `voters_compressed` | CC |
| PUT | `/v1/projects/{projectId}` | FA | L225247 | project settings update | CC |
| GET | `/v1/projects/{id}/counts` | FA | L380373 | call screen project change | HERE §4 |
| GET | `/v1/projects/sse/updates` | FA | L339355 | SSE project loading status | HERE §2.2 |
| GET | `/v1/projects/{pid}/voters/{vid}` | FA | L382770, L382796 | call screen voter info load | CC |
| GET | `/v1/voters/{id}/notes` | FA | L359640 | voter detail | CC |
| GET | `/v1/voters/{id}/interactions` | FA | L360750 | voter activity feed | CC |
| GET | `/v1/nearby-voters` | FA | L387431 | params `{latitude, longitude}`; relational-neighbors map | CC |
| GET | `/v1/mobile-voter-search` | FA | L386393, L386441 | voter search; params = form fields + `{limit:100, offset:0}` | CC |
| GET | `/v1/voter-filter-categories` | FA | L381415 | search filter metadata (`staleTime: Infinity`) | CC |
| POST | `/v1/interactions/batch` | FA | L226387, L226487, L359600, L383274 | interaction upload incl. offline drain (10-item chunks) | IS |
| POST | `/v1/interactions/call` | FA | L381243 | call disposition | HERE §4 |
| POST | `/v1/interactions/relational-text` | FA | L339109 | native-SMS follow-up record | HERE §8 |
| GET | `/v1/relational-text` · `/{projectId}` | FA | L339009, L339034 | text templates | HERE §8 |
| GET | `/v1/relational-survey` · `/{projectId}` | FA | L339059, L339084 | survey definitions | IS |
| GET | `/v1/tags` | FA | L359551 | all org tags | IS |
| GET | `/v2/voter_tags/{voterId}` | FA | L359526 | per-voter tags | IS |
| POST | `/v1/canvassing-qa/tracking` | FA | L230691 | GPS QA ping, every 15 s tick w/ user+org+project; body = `{latitude, longitude, device_id, device_geolocation_enabled, device_geolocation_permission_status, is_using_emulator}`, timeout 10 s (L230660–230711) | CC |
| GET | `/v1/user-outreach-stats` | FA | L340021 | Achievements screen; params `{cycle?}` | HERE §9.4 |
| GET | `/v1/mobile/leaderboard` | FA | L389369 | leaderboard; params `{cycle?, start_datetime?, end_datetime?}` | HERE §5 |
| POST | `/v1/push/tokens` | FA | L332051 | push registration | HERE §1.1 |
| DELETE | `/v1/push/tokens/{token}` | FA | L332067 | logout | HERE §1.2 |
| GET | `/v1/push/notifications` | FA | L332094 | inbox | HERE §1.3 |
| POST | `/v1/push/notifications/read` | FA | L332139 | `{expo_push_token, message_ids[]}` | HERE §1.3 |
| POST | `/v1/push/notifications/read-all` | FA | L332115 | mark all read | HERE §1.3 |
| DELETE | `/v1/push/notifications` | FA | L332163 | delete all | HERE §1.3 |
| DELETE | `/v1/push/notifications/bulk` | FA | L332187 | bulk delete | HERE §1.3 |
| GET | `/v1/contact-matches` | FA | L352963 | match-status poll, 5 s | HERE §7 |
| POST | `/v1/contact-matches` | FA | L352984 | full address-book upload `{contact_data[]}` | HERE §7 |
| GET | `/v1/voter-contacts` · `/{projectId}` | FA | L353006, L353031 | matched contacts | HERE §7 |
| GET | `/v2/me/relational-payment` | FA | L339163 | payout details | HERE §6 |
| POST | `/v2/me/relational-payment` | FA | L339185 | payout request `{timezone}` | HERE §6 |
| GET | `/api/v3/auth_token` | ROS | L380539 | Twilio token, params `{user_id, org_id, device_id, platform:"fcm"}` | HERE §4 |
| GET | `/api/v3/twilio_numbers` | ROS | L382665 | mount + 120 s poll on call screen | HERE §4 |
| POST | `/api/v3/amd_call` | ROS | L380413 | start/stop server-side dialing | HERE §4 |
| GET | `/api/v3/outreach/status/{projectId}` | ROS | L381089 | outreach status seed | HERE §2.3 |
| GET | `/api/v3/project/{projectId}/queue` | ROS | L381139 | call queue seed | HERE §2.4 |
| GET | `/api/v3/project/loading_status/{projectId}` | ROS | L339336 | loading status seed | HERE §2.2 |
| GET | `/api/v3/events/source/outreach/{projectId}` | ROS | L381100 | SSE `outreach_status` | HERE §2.3 |
| GET | `/api/v3/events/source/calls/{projectId}` | ROS | L381150 | SSE `call_update` | HERE §2.4 |
| GET | `/api/v3/bandwidth/numbers` | ROS | L383749 | texting numbers | HERE §8 |
| POST | `/api/v3/bandwidth/batch-texts` | ROS | L383772 | server-side SMS batch | HERE §8 |
| WSS | `/websocket?token=…&first_name=…&last_name=…&email=…&org_name=…&org_id=…&platform=mobile` | ROS | L202441 | realtime canvass dedup | HERE §3 |

### 9.2 Third-party endpoints (inside bundled SDKs — not Numinar-owned)

| Endpoint | Line | SDK | Notes |
|---|---|---|---|
| `https://auth.numinar.com/v2/logout`, `/oauth/token`, `/api/v2/users/{id}` (GET/PATCH) | L212916, L212928, L213451–L213476 | react-native-auth0 | AS scope |
| `https://exp.host/--/api/v2/push/updateDeviceToken`, `…/api/v2/` | L222531, L222922 | expo-notifications | token mint path |
| Google Places `/v1/places…`, `/place/autocomplete/json`, `/place/details/json` | L243515, L243925 | google-places-autocomplete | address search (uses `GOOGLE_MAPS_APIKEY` L202382) |
| `https://api.mixpanel.com` (8 refs) | — | mixpanel-react-native | analytics, token `a0a85ec57b…` L202389 |
| `https://o447951.ingest.sentry.io/…/api/<proj>/envelope/` | L110694 | @sentry/react-native | crash reporting DSN 4509632503087104 |
| Intercom (FCM push only, no direct HTTP in JS) | — | @intercom | app id `zskx6pd1` |
| Adjust | — | react-native-adjust | token `idif65k6cl4w` L202379 |
| Mapbox | — | @rnmapbox/maps | **secret** `sk.…` token L202383 |

### 9.3 Client-side periodic behavior summary (what leaves the device)

| Behavior | Cadence | Egress |
|---|---|---|
| Connectivity check `HEAD /v1/mobile_204` | 15 s interval (L230971) | unauthenticated HEAD |
| Canvassing QA tracking | same 15 s tick, gated on user+org | GPS coords + device_id + permission status + emulator flag → FA |
| WS keepalive `"ping"` | 30 s (L202458) | text frame |
| Twilio numbers poll | 120 s on call screen (L382709) | GET twilio_numbers |
| Contact-match status poll | 5 s while matching (L353347) | GET contact-matches |
| Offline interaction drain | on reconnect/foreground; chunks of 10 (L230866–230925) | POST interactions/batch + WS `canvassed` per item |
| SSE reconnects | flat 3 s after error, no cap | reconnect GETs |

### 9.4 Endpoints owned by no other audit area (flagged, documented here)

`/v1/mobile_204` (§9.1/§9.3), `/v1/user-outreach-stats` (§9.1 — response
fields read: `canvass_interaction_count` et al., L340529+; full domain
UNCONFIRMED), `/v1/projects/{id}/counts` (§4), all `/v1/push/*` (§1),
all contact-matching (§7), all payment (§6), leaderboard (§5), all
`/api/v3/*` ROS endpoints + websocket (§2–§4, §8).

### 9.5 UNCONFIRMED items (not statically recoverable)

- Exact JSON field names inside SSE `outreach_status` and
  `update` (project loading) payloads beyond the keys shown in §2.
- The self-echo branch of the WS `onmessage` handler (`device_id` check body).
- `DELETE /v1/push/notifications/bulk` body field name (opaque passthrough).
- Full response schemas for leaderboard, outreach-stats, counts,
  contact-matches (only client-read fields are confirmed).
- Whether online (non-offline-queued) canvass interactions trigger a WS
  broadcast by the server (the app only sends WS `canvassed` during offline
  drain; other devices still receive `canvassed` events, so the server must
  fan out from the REST path too — mechanism not visible client-side).
