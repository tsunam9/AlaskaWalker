# Audit — Earnings, Account, Applications, Assignments, Chats, Reports, Canvasser Application, Recruitment, Supabase

App: `com.patriotgrassroots.validnation` v1.0.0 (114), white-label of ValidNation.
Sources: complete recovered frontend at `/tmp/vn_src/` (cited as `path:line` relative to it),
generated API client `client/sdk.gen.ts` (ground truth for method+path+content-type),
decompiled Java in `patriot_grassroots/java/`.

**Caveat on response shapes:** `client/types.gen.ts` (the hey-api generated type file) is
type-only and therefore absent from the shipped source maps — it is NOT recoverable.
Response field lists below are reconstructed from the exact fields the UI code reads
(cited per field group). Fields the server may send but the app never reads cannot be
confirmed and are marked UNCONFIRMED where relevant.

## 0. Transport & auth (applies to every `/api/*` message below)

- Base URL: `useRuntimeConfig().public.apiBaseURL` = `https://api.validnation.ai`
  (wired at `app.vue:40-46`).
- All SDK calls go through the hey-api client with `security: [{scheme:'bearer', type:'http'}]`
  (per-endpoint, e.g. `client/sdk.gen.ts:37-42`). The `auth` callback returns the raw JWT
  (`composables/auth/httpInterceptors.ts:50-67`); the client sends header
  `Authorization: Bearer <jwt>` (`client/core/auth.gen.ts:33-35`).
- Pre-request: if a refresh is in flight it is awaited; else if the JWT expires within
  30 s the client proactively calls `POST /api/auth/refresh`
  (`composables/auth/httpInterceptors.ts:29-31, 50-67`).
- On 401: `authOnResponse` refreshes once and retries the original request with the new
  token; on refresh-401 it signs out with redirect to login (`app.vue:47-63`).
- HTTP stack: `$fetch` wrapped in `createCachingFetch` (`app.vue:41`); on device this is
  CapacitorHttp (native HTTP), per ANALYSIS.md.
- GET responses for offline: `pinned()` prefetch at
  `utils/prefetchOfflineData.ts:15-56` covers `GET /api/account/`,
  `GET /api/earnings/balance/`, `GET /api/earnings/account/` (canvassers only), project
  list/details, and Supabase chat list + unread count. Mutations in this document have
  NO offline queue — failure surfaces a toast (`showToastError`) and nothing is retried
  automatically (see each mutation's `onError`).
- Query library is pinia-colada; `staleTime` values below control refetch-on-mount
  behavior. No polling anywhere in this scope except the Branch-activation poll (§1.5).

---

## 1. Earnings (worker-facing surface)

Roles: earnings pages allow `admin, manager, canvasser` (`pages/earnings/index.vue:78-81`);
balance page is canvasser-only (`pages/earnings/balance.vue:61-63`). In the Patriot
Grassroots mobile build the signed-in role is canvasser, so the canvasser shapes are the
operative ones; manager/admin variants are documented because the same endpoints serve them.

### 1.1 `GET /api/earnings/totals-by-rate-type/` — 30-day bonus/increased-rate totals — resolves [H]

SDK: `getEarningTotalsByRateType`, GET, bearer, no body (`client/sdk.gen.ts:1055-1070`).
Server doc string: "Get the canvasser's total Bonus and Increased Rate earnings over the
past 30 days."

- Trigger: earnings list page mount, canvasser only; query key
  `['earnings-totals-by-rate-type']`, `staleTime: 60_000` → refetch at most ~1/min while
  the page is used (`queries/earnings/totalsByRateType.ts:6-11`,
  `pages/earnings/index.vue:123-127`).
- Response shape CONSUMED (resolves DESIGN-VALIDNATION.md §8 [H] "response shapes [H]"):
  ```json
  {
    "bonus":          { "total": <number|string>, "count": <number> },
    "increased_rate": { "total": <number|string>, "count": <number> }
  }
  ```
  `total` is coerced with `Number(... ?? 0)` (so it may arrive as a string);
  `count` read directly (`components/earnings/EarningsRateTypeSummary.vue:42-46`).
  Cards render only when `count > 0`; load failure shows a non-blocking inline error and
  the earnings list below is unaffected (`EarningsRateTypeSummary.vue:7-9`).
- Offline/failure: error → inline "Couldn't load your bonus summary" note; no retry
  button, no queue.

### 1.2 `GET /api/earnings/` — earnings list

SDK: `getEarningList`, GET, bearer (`client/sdk.gen.ts:962-977`).

- Trigger: earnings page mount + any filter/sort/page change (URL query driven);
  key `['earnings-list', JSON.stringify(params)]` (`pages/earnings/index.vue:87-117`).
- Query params (all optional unless noted; `page`,`size` from `parsePagination`):
  `page, size, sort_by (default 'created_at'; also 'final_total' |
  'review_deadline_timestamp' — `constants/earnings/earningsSortBy.ts`),
  `sort_type ('asc'|'desc', default 'desc')`, `search_query`,
  `statuses[] ∈ EarningPaymentStatus`, `rate_types[] ∈ EarningRateType`,
  `sources[] ∈ EarningSource ('manual'|'system' — `constants/earnings/source.ts`),
  `canvasser_ids[], project_ids[], created_date_from, created_date_to,
  final_total_min, final_total_max (numbers), timezone` (IANA name from
  `Intl.DateTimeFormat`) (`pages/earnings/index.vue:87-108`).
- Response CONSUMED: `{ items: EarningListItem[], total_count: number }`
  (`pages/earnings/index.vue:36-50,119`).
  - Canvasser item fields read: `id, created_at, project{name}|null, status, final_total,
    rate_type` (`components/earnings/list/EarningsListCanvasserTable.vue:13-42`).
  - Admin/manager item adds: `canvasser` (user object passed to `username()`),
    `source`, `review_deadline_timestamp` — presence of `review_deadline_timestamp` is
    the runtime discriminator for admin/manager items
    (`utils/typeCheckers/earnings.ts:16-20`,
    `components/earnings/list/EarningsListAdminManagerTable.vue:17-53`).
- Enums (client-side, exhaustive per constants):
  `EarningPaymentStatus = pending | under_review | ready_for_payment |
  transaction_processing | completed | manually_completed | rejected | failed`
  (`constants/earnings/paymentStatus.ts`);
  `EarningRateType = regular_rate | bonus | increased_rate | reimbursement`
  (`constants/earnings/rateType.ts`).

### 1.3 `GET /api/earnings/{earning_id}` — earning detail

SDK: `getEarningDetails`, GET, bearer (`client/sdk.gen.ts:1157-1172`).

- Trigger: navigation to `/earnings/{id}`; key `['earnings-id', id]`, `staleTime: 0`
  (refetch every mount), invalidated after approve/reject/pay mutations
  (`queries/earnings/earningDetails.ts:9-18`).
- Response CONSUMED (canvasser variant `EarningDetailsForCanvasser`):
  `status, payroll_at (ISO date|null — drives "Upcoming payment" banner only when status
  is pending|ready_for_payment), rate_type, final_total, work_shift_date|null,
  created_at, project_id|null, referral_id|null, paid_signatures_amount|null,
  work_shift{id, …}|null, assignment_type|null, description (markdown)|null`
  (`pages/earnings/[id].vue:6-8,121-126`,
  `components/earnings/EarningsCanvasserDetails.vue:5-61`).
- Admin/manager variant additionally CONSUMED: `canvasser` (its presence is the
  discriminator — `utils/typeCheckers/earnings.ts:34-38`), `report_id`,
  `review_deadline_timestamp`, `approved_details{user_id, timestamp, comment}`,
  `cancelled_details{user_id, timestamp, comment}`,
  `manually_completed_details{user_id, timestamp, comment}`, `total`, `adjustment`,
  `description` (`pages/earnings/[id].vue:27-86`,
  `components/earnings/EarningsAdminManagerDetails.vue:333-399`).
- "Approve-state fields" (design-doc question): approval state is conveyed by
  `status` + the three nullable `*_details` blocks above; there is no separate boolean.

### 1.4 `GET /api/earnings/{earning_id}/short_info`

SDK: `getEarningShortInfo`, GET (`client/sdk.gen.ts:1254-1269`). Trigger: hover/inline
cross-reference labels (`components/common/labeled-entity/InlineEntityEarning.vue`,
`LabeledEntityEarning.vue`). Response fields consumed: display label fields only
(UNCONFIRMED beyond that — the components render a name/amount line).

### 1.5 `GET /api/earnings/account/` — Branch payout onboarding status — resolves [H]

SDK: `getPaymentAccountDetails`, GET, bearer (`client/sdk.gen.ts:1000-1015`).

- Trigger: balance page + transactions page mount, canvasser only; key `['earnings']`,
  `staleTime: 500` (`queries/earnings/details.ts:6-15`,
  `pages/earnings/balance.vue:67`, `pages/earnings/transactions/index.vue:98`).
- **Polling cadence**: while the user has clicked "Open Branch" and the app is waiting
  for activation, `useTimeoutPoll(..., 10000)` refetches every **10 s** until
  `status` flips `registered → activated`
  (`components/earnings/EarningsProcessingBranchRegistration.vue:18-23`,
  state machine in `pages/earnings/balance.vue:65-84`). This is the only poll in scope.
- Response CONSUMED (resolves [H] — Branch onboarding status shape):
  ```json
  { "status": "not_registered" | "registered" | "activated" | "deactivated",
    "onboarding_link": "<url string|null>" }
  ```
  (`pages/earnings/balance.vue:14-48`; enum `PaymentAccountStatus` keyed exhaustively in
  `constants/earnings/branchData.ts`). Other fields UNCONFIRMED.
- Semantics: `not_registered` → warning "Earnings are not available…";
  `registered` → "Open Branch" card (`onboarding_link` opened in external browser via
  `<a target="_blank">`, click emits `openBranchCallback` which arms the 10 s poll —
  `components/earnings/EarningsBranchInfoCard.vue:24-28`,
  `pages/earnings/balance.vue:21-29`); `activated` → payout UI + optional success dialog
  (`pages/earnings/balance.vue:75-84`); `deactivated` → warning + balance shown
  read-only, withdraw disabled (`balance.vue:36-48`,
  `components/earnings/EarningsCurrentBalance.vue:40-48`).
- This is the entire client-side Branch integration: no Branch SDK, no API key; Branch
  itself is configured server-side (plus a server webhook `BranchWebhookHandler` in the
  SDK, `client/sdk.gen.ts` import line 4 — server-to-server, not called by the app).

### 1.6 `GET /api/earnings/balance/` — current balance

SDK: `getEarningBalance`, GET, bearer (`client/sdk.gen.ts:1038-1053`).

- Trigger: balance page mount only (`enabled: route.name === 'earnings-balance'`),
  `staleTime: 0` (`queries/earnings/balance.ts:9-14`). Also prefetched for offline via
  `pinned()` (`utils/prefetchOfflineData.ts:25`).
- Response CONSUMED:
  ```json
  { "ready_for_payment": <number>, "pending": <number>,
    "next_payment_date": "<ISO date>", "same_day_payout_enabled": <boolean> }
  ```
  (`components/earnings/EarningsCurrentBalance.vue:20-34,43-44`;
  `queries/earnings/balance.ts:18`). Amounts rendered via `formatAmount` (dollars).
- Withdraw button enabled iff `same_day_payout_enabled && ready_for_payment > 0 &&
  !deactivated` (`EarningsCurrentBalance.vue:40-48`).

### 1.7 `POST /api/earnings/withdraw` — same-day payout

SDK: `createDisbursement`, POST, bearer, **no body** (`client/sdk.gen.ts:1140-1155`).

- Trigger: user taps "Withdraw {amount}" → confirmation dialog → Confirm
  (`components/earnings/EarningsCurrentBalance.vue:105-113`).
- Response: not field-read; success just zeroes `ready_for_payment` in the local
  `['balance']` cache and toasts (`mutations/earnings/withdraw.ts:10-19`).
- Failure: toast only; no queue/retry.

### 1.8 Transactions (payout history)

- `GET /api/earnings/transactions/` — SDK `getTransactionList`
  (`client/sdk.gen.ts:1072-1087`). Trigger: transactions page mount/filter change
  (`pages/earnings/transactions/index.vue:100-128`). Query params: `page, size,
  sort_by (default 'timestamp_created'), sort_type, search_query,
  statuses[] ∈ TransactionStatus, canvasser_ids[], created_date_from, created_date_to,
  amount_min, amount_max, timezone` (`index.vue:100-118`).
  `TransactionStatus = PENDING | SCHEDULED | COMPLETED | FAILED | CANCELED | SKIPPED |
  REVERSED | UNKNOWN` (uppercase — `constants/earnings/transactionStatus.ts`).
  Response CONSUMED: `{items[], total_count}`; canvasser item: `id, timestamp_created,
  status|null, amount` — **`amount` is integer cents** (divided by 100 for display,
  `components/transactions/TransactionsCanvasserList.vue:19-29`); admin item adds
  `canvasser` (`components/transactions/TransactionsAdminManagerList.vue:16-32`).
- `GET /api/earnings/transactions/{transaction_id}` — `getTransactionDetails`
  (`client/sdk.gen.ts:1089-1104`). Trigger: transaction detail page mount,
  `staleTime: 0` (`queries/earnings/transactions/details.ts:8-16`).
  Response CONSUMED: `status, amount (cents), created_at`; admin/manager variant adds
  `type` (displayed lowercased), `canvasser{id}`, `reason_code`, `error_label`,
  `error_message` (shown when `status === 'FAILED' || !status`)
  (`pages/earnings/transactions/[id].vue:7-53`; discriminator
  `isTransactionDetailsForAdminManager`).
- `GET /api/earnings/transactions/{transaction_id}/earnings` — `getTransactionEarnings`
  (`client/sdk.gen.ts:1106-1121`). Trigger: same detail page ("Breakdown" section),
  `staleTime: 0` (`queries/earnings/transactions/breakdown.ts:9-19`). Response CONSUMED:
  `{items[]}` where items are the same earning-list-item shapes as §1.2
  (`pages/earnings/transactions/[id].vue:67-72,104-114`).
- `GET /api/earnings/transactions/{transaction_id}/short_info` — SDK exists
  (`client/sdk.gen.ts:1123-1138`); no consumer found outside labeled-entity components
  (grep, /tmp/vn_src). UNCONFIRMED fields.

### 1.9 Manager/admin-only earning mutations (worker never triggers; documented for completeness)

- `PATCH /api/earnings/{earning_id}/approve` — body
  `{adjustment: number|null (−1000..1000, never reduces final total ≤ 0),
   note: string|null, description: string (1..5000 chars)}`
  (`client/sdk.gen.ts:1174-1193`,
  `components/earnings/EarningsAdminManagerDetails.vue:361-424`,
  `mutations/earnings/approve.ts:6-11`). Trigger: "Approve & Save" dialog.
- `PATCH /api/earnings/{earning_id}/reject` — body `{note: string|null,
  description: string}` (`client/sdk.gen.ts:1233-1252`,
  `EarningsAdminManagerDetails.vue:425-431`, `mutations/earnings/reject.ts:8-14`).
- `PATCH /api/earnings/{earning_id}/manually_completed` — body `{note: string|null,
  description: string}` ("pay manually", e.g. paid in cash)
  (`client/sdk.gen.ts:1195-1214`, `EarningsAdminManagerDetails.vue:435-447`,
  `mutations/earnings/payManually.ts:6-14`).
- `POST /api/earnings/{earning_id}/pay` — no body; instant Branch disbursement of one
  ready earning (`client/sdk.gen.ts:1216-1231`, `mutations/earnings/payNow.ts:6-11`).
  Response CONSUMED: `{status: TransactionStatus, error_message: string|null}` — HTTP is
  200 even on failure; success iff `status ∈ {COMPLETED, PENDING}`
  (`constants/earnings/transactionsStatuses.ts`, `payNow.ts:16-20`).
- `POST /api/earnings/` — manager creates manual earning; body type
  `EarningCreateRequest` (fields UNCONFIRMED — constructed in
  `components/earnings/create/EarningsCreateForm.vue`, not fully traced; response
  consumes `id` for redirect, `mutations/earnings/create.ts:12-19`).
- `PATCH /api/earnings/account/{user_id}` — admin toggles payout settings on a user;
  body is exactly one of `{weekly_payroll_enabled: boolean}` or
  `{same_day_payout_enabled: boolean}` per call (toggle handler sends a single key)
  (`client/sdk.gen.ts:1017-1036`,
  `components/users/details/UserDetailsCanvasserInfo.vue:306-319`,
  `mutations/users/updatePaymentInfo.ts:8-16`). Server coupling: turning weekly payroll
  off forces `same_day_payout_enabled=false` (mirrored in cache logic,
  `updatePaymentInfo.ts:35-50`).

---

## 2. `/api/account/*`

### 2.1 `GET /api/account/` — account details

SDK: `getAccountDetails`, GET, bearer (`client/sdk.gen.ts:31-46`). Query
`useAccount`, key `['account']`, `staleTime: 0` (`queries/account.ts:3-12`).

- Triggers: account page mount; invalidated + refetched after every onboarding step
  (voice sample, general info, documents, profile) via `useRefreshAccountAndRedirect`
  (`composables/useRefreshAccountAndRedirect.ts:1-12`); also prefetched for offline
  (`utils/prefetchOfflineData.ts:20`).
- Response CONSUMED: `profile` (object passed to profile card),
  `general_info{city, state}|null`, `created_at`, `subcontractor_company_id|null`,
  `voice_sample_recorded` (boolean|null — drives the voice-sample checkmark),
  `referral_program{referral_code}` (`pages/account/index.vue:4-13`,
  `pages/account/canvasser/index.vue:13-14`,
  `pages/account/referral-program/index.vue:3,68`).

### 2.2 `PATCH /api/account/settings/edit`

SDK: `editAccountSettings`, PATCH, JSON (`client/sdk.gen.ts:116-135`).

- Trigger: "Save New Timezone" on Edit Settings page (`pages/account/edit-settings/index.vue:59-61`).
- Body: `{time_zone: <IANA string, nonempty>}` (zod-validated,
  `pages/account/edit-settings/index.vue:47-51`).
- On success: full session refresh (`useAuth().getSession()`) + navigate to account
  (`mutations/account/editUserSettings.ts:16-21`).

### 2.3 Password endpoints

- `PUT /api/account/password/edit` — change password while logged in. Body
  `{old_password: string, new_password: string}` (`client/sdk.gen.ts:48-67`,
  `pages/account/edit-password/index.vue:72-81`, `mutations/account/editUserPassword.ts:11-15`).
  `new_password` must match `passwordRegex` (≥8 chars, upper+lower, digit, one of
  `#?!@$%^&*-`, no spaces — `constants/regularExpressions.ts`, used at
  `pages/account/edit-password/index.vue:55-63` area).
- `POST /api/account/password/reset` — request reset email, UNAUTHENTICATED (no
  `security` block — `client/sdk.gen.ts:69-82`). Body `{email: string}`
  (`pages/password/restore.vue:93-99`, `mutations/resetPassword.ts:7-11`).
- `POST /api/account/password/set` — complete reset from email link, UNAUTHENTICATED
  (`client/sdk.gen.ts:84-97`). Body `{otp_code: string, user_id: string,
  password: string}` where `otp_code`/`user_id` come from the email link's query params
  (`pages/password/reset.vue:100-116`, `mutations/setPassword.ts:7-11`).

### 2.4 `PATCH /api/account/{user_id}/delete` — account deletion

SDK: `deleteAccount`, PATCH, no body (`client/sdk.gen.ts:158-173`).

- Triggers: self-delete from account page, or admin deleting a user from the user page
  (`mutations/users/deleteUser.ts:8-26`).
- On success deleting self: local sign-out; deleting another user: cache patch
  `status: 'deleted'` (`deleteUser.ts:11-27, 40-43`).

### 2.5 `POST /api/account/voice_sample/` — voice enrollment (cross-ref) — resolves [H]

SDK: `createVoiceSample`, POST, **`Content-Type: application/json`** — NOT multipart
(`client/sdk.gen.ts:137-156`). This resolves DESIGN-VALIDNATION.md §voice_sample [H]
("multipart; exact field names [H] … likely audio/webm [H]"): **both guesses were
wrong**.

- Body (exact):
  ```json
  {
    "audio_data": "<base64 — raw PCM samples captured via AudioWorklet, NOT an encoded container>",
    "audio_config": {
      "sample_rate": <int, default 48000 from track settings>,
      "channels": <int, default 1>,
      "bits_per_sample": <int, default 16 from track capabilities>,
      "encoding": "linear16"
    }
  }
  ```
  (`mutations/createSample.ts:7-11`, `composables/useSampleRecorder.ts:105-121`,
  `utils/createAudioConfig.ts:1-12`, base64 via `utils/arrayBufferToBase64.ts`).
  Note: RecordRTC is started in parallel only to give the user a playable preview blob
  (webm duration-fixed); the **uploaded** payload is the PCM worklet chunks concatenated
  and base64'd (`useSampleRecorder.ts:74-86, 110-115`).
- Trigger: user records on the voice-sample page and taps save; client enforces
  > 30 s minimum (`useSampleRecorder.ts:22-25, 71-72`).
- On success: toast + `useRefreshAccountAndRedirect` → `GET /api/account/` refetch,
  redirect to `account-canvasser` (`mutations/createSample.ts:12-15`).
- Server-mandated: `voice_sample_recorded` flag on `GET /api/account/` (§2.1).

### 2.6 `GET /api/account/referral_code`

SDK exists (`client/sdk.gen.ts:99-114`) but the referral page reads the code from
`GET /api/account/` (`referral_program.referral_code`,
`pages/account/referral-program/index.vue:3`). No live caller of `getReferralCode`
found (grep). Dead client code as shipped.

---

## 3. `/api/applications/*` (worker side) + manager actions

Pages `applications/upcoming`, `applications/index`, `applications/[id]` allow
`admin, manager, canvasser`; `applications/my` is canvasser-only
(`pages/applications/my.vue:34-37`).

- `GET /api/applications/` — upcoming (open) projects list. Query: `page (def 1),
  size (def 10), sort_by (def 'start_date'), sort_type (def 'desc'), from_date, name,
  project_type (def 'all'), type` (`queries/applications/upcomingProjects.ts:13-39`,
  `client/sdk.gen.ts:175-190`). Trigger: upcoming page mount/filter change. Response
  CONSUMED: `{items[], total}`.
- `GET /api/applications/applied` — worker's own applications. Query: `page, size,
  sort_by, sort_type, from_date, name, application_statuses[], type`
  (`pages/applications/my.vue:41-70`, `client/sdk.gen.ts:213-228`). Response CONSUMED:
  `{items[], total_count}`.
- `GET /api/applications/{project_id}` — upcoming project details
  (`client/sdk.gen.ts:293-308`, `queries/applications/details.ts:8-17`). Response
  CONSUMED includes `id, start_date, end_date, pricing, goal, application_status`
  (set to `'applied'` in cache after applying —
  `mutations/applications/applyToProject.ts:15-26`,
  `components/applications/details/ApplicationsDetailsData.vue:95-115`).
- `PUT /api/applications/create` — **worker applies to a project**. Body exactly
  `{project_id: string, user_id: string}` (`client/sdk.gen.ts:251-270`,
  `components/applications/details/ApplicationsDetailsData.vue:124-132`). Trigger:
  "Apply" button on project details. On success: cache-patch `application_status:
  'applied'`; failure: toast, no retry.
- Manager-side (worker never calls):
  - `POST /api/applications/applicants/` — paginated applicant list; body
    `{page, size, project_id, sort_by (def 'name'), sort_type (def 'asc'),
    search_query, statuses[], onboarding_state}`
    (`client/sdk.gen.ts:192-211`,
    `components/applications/details/ApplicationsDetailsTable.vue:50-77`).
  - `POST /api/applications/approve` — body `{user_id, project_id,
    price_per_signature: number|null (signature projects),
    price_per_hour: number|null (canvassing projects),
    canvassing_application_user_email: string|null,
    assignment_type: string|null, increased_price_per_hour: number|null,
    position: string|null}` (`client/sdk.gen.ts:230-249`,
    `components/applications/details/ApplicationsDetailsApplyDialog.vue:81-92`).
  - `POST /api/applications/reject` — body `{user_id, project_id, rejection_reason:
    string}` (preset reason or free text when "Other")
    (`client/sdk.gen.ts:272-291`,
    `components/applications/details/ApplicationsDetailsRejectDialog.vue:126-134`).

## 4. `/api/assignments/*`

All assignment UI pages are `admin, manager` only
(`pages/assignments/[project_id]/[user_id].vue:61-62`) — the worker app receives
assignment effects indirectly (project appears in its active list, contract issued).
Documented because the same backend serves the reimplementation's project-assignment
state:

- `GET /api/assignments/{project_id}/{user_id}` — assignment detail
  (`client/sdk.gen.ts:310-325`; consumer `pages/assignments/[project_id]/[user_id].vue:57,77`).
- `PUT /api/assignments/{project_id}/{user_id}/info` — body type `AssignmentInfoBody`;
  per SDK doc: "Update editable assignment fields (pay rates, assignment type,
  canvassing app username). If the pay rate changes, any pending/active contract is
  terminated and a new one is issued." (`client/sdk.gen.ts:343-363`,
  `mutations/assignments/updateInfo.ts:13-18`). Exact field list UNCONFIRMED
  (type-only import; built by `buildAssignmentInfoSchema`, same fields as the
  application-approve body in §3 — rates, assignment_type, position,
  canvassing app email — but not independently verified).
- `GET /api/assignments/{project_id}/{user_id}/status-history` — query
  `{page (def 1), size (def 20)}` (`client/sdk.gen.ts:365-380`,
  `components/assignments/details/AssignmentsDetailsStatusHistory.vue:72-87`).
  Response item CONSUMED: `source` (+ status-change fields rendered as history rows).
- `POST /api/assignments/{project_id}/{user_id}/contracts/resend` — re-trigger contract
  signing (`client/sdk.gen.ts:327-342`).
- Assignment **status** changes go to a different path:
  `PUT /api/users/{user_id}/projects/{project_id}/update`, body `{assignment_status:
  AssignmentStatus}` (`client/sdk.gen.ts:4904-4923`,
  `mutations/assignments/updateAssignmentStatus.ts:18-23`).

---

## 5. `/api/broadcast` — NOT a ValidNation endpoint

`/api/broadcast` appears in `endpoints.txt:23` but has **no SDK entry and no caller in
the frontend source** (grep over /tmp/vn_src). The string in the bundle comes from the
vendored Supabase `realtime-js` library: it is the realtime HTTP-broadcast fallback path
computed from the websocket URL (`tree/assets/public/_nuxt/BYbP5qv3.js`, `gL` function:
`…t.pathname="/api/broadcast"…` — i.e. it targets
`https://tfnnpqpvdjisoizvciyr.supabase.co/api/broadcast`, the Supabase project, not
api.validnation.ai). All "broadcast" traffic in the app is Supabase Realtime broadcast
events over the Supabase websocket (§7). Nothing to reimplement against
api.validnation.ai here.

---

## 6. `/api/reports/*` (fraud reports) — admin/manager only

Pages: reports list is admin-only (`pages/reports/index.vue:102`), details admin+manager
(`pages/reports/[id].vue:162`). Worker impact is indirect: a fraud report puts the
worker's earning into `under_review` with `report_id` + `review_deadline_timestamp`
(§1.3).

- `GET /api/reports/` — list (`client/sdk.gen.ts:3243-3258`,
  `pages/reports/index.vue:141`).
- `GET /api/reports/{report_id}` — details (`client/sdk.gen.ts:3260-3275`,
  `pages/reports/[id].vue:180`).
- `PATCH /api/reports/{report_id}/confirm` — no body; confirms fraud (keeps earning
  rejected/under review) (`client/sdk.gen.ts:3277-3292`,
  `mutations/reports/confirm.ts:5-9`).
- `PATCH /api/reports/{report_id}/discard` — no body (`client/sdk.gen.ts:3294-3309`,
  `mutations/reports/discard.ts:5-9`).
- `GET /api/reports/{report_id}/view_data?simplified=<bool>` — the rendered fraud-report
  view artifact; query `{simplified: boolean}` (`client/sdk.gen.ts:3311-3326`,
  `queries/reports/viewData.ts:8-18`, `staleTime: 60_000`).

---

## 7. Chats — 100% Supabase, ZERO api.validnation.ai calls

The entire chat feature bypasses the ValidNation API. There is no `/api/chats*`
endpoint in the SDK at all (grep confirms). All chat reads/writes are PostgREST RPC /
table operations against `https://tfnnpqpvdjisoizvciyr.supabase.co`, plus Supabase
Realtime broadcast for live updates, plus Supabase Storage for attachments.

### 7.1 Supabase client setup

- Client: `createClient(config.supabase.url, config.supabase.key)` with
  `db: { schema: 'private' }`, `auth: {persistSession:false, autoRefreshToken:false,
  detectSessionInUrl:false}` (`plugins/supabase.ts:63-162`). URL+anon key ship in
  plaintext runtime config (see ANALYSIS.md §Backends).
- **Auth: the app's own ValidNation JWT is sent as `Authorization: Bearer <jwt>` on
  every Supabase request** (the anon key goes in the `apikey` header per supabase-js
  defaults) (`plugins/supabase.ts:72-78`). On 401 the wrapper refreshes the ValidNation
  token and retries once (`plugins/supabase.ts:104-118`). Realtime websocket auth is set
  via `supabase.realtime.setAuth(<raw JWT>)` on login/token change
  (`plugins/supabase.ts:164, 215-223`). → the Supabase project validates the same JWT
  (custom JWT secret), which is why the app can bypass its own API: row-level security
  in the `private` schema enforces per-user access server-side.
- Resilience: 5 s manual timeout raced against fetch (CapacitorHttp ignores
  AbortSignal) (`plugins/supabase.ts:80-92`); GET `/rest/v1/*` and RPC responses are
  cached offline and served with `X-Offline-Cache: true` on network failure
  (`plugins/supabase.ts:94-156`); chat list + unread count are also prefetch-pinned
  (`utils/prefetchOfflineData.ts:47-50`).
- **Why the app bypasses its own API** (evidence-based summary): chat data lives in a
  Supabase Postgres (`private` schema) with RPC functions; the ValidNation JWT is
  accepted directly by Supabase, so no backend proxy is needed. This is an
  architectural fact confirmed by the client setup above, not conjecture.

### 7.2 PostgREST RPC calls (POST `https://tfnnpqpvdjisoizvciyr.supabase.co/rest/v1/rpc/<fn>`)

All bodies are `{"input": {...}}` unless noted; schema `private` (default from client
config, explicit `.schema('private')` in some).

| RPC | Input fields | Trigger |
|---|---|---|
| `get_user_chats_cursor` | `{archived: bool, before_cursor: null, after_cursor: null, chat_limit: int (def 18)}` | chats page mount / archived toggle (`pages/chats.vue:58-113`, `composables/supabase/useChatList.ts:7-9`) |
| `get_user_chats_cursor_at` | `{archived, at_cursor: int, chat_limit}` | open a specific chat deep-link (`pages/chats.vue:83-88`, `useChatList.ts:13-15`) |
| `get_messages_with_details` | `get_messages_with_details_input` (cursor pagination; exact fields UNCONFIRMED — type-only) | chat [id] page mount/scroll (`composables/supabase/useChatMessages.ts:8-10`) |
| `get_messages_at_with_details` | same family | jump to message (`useChatMessages.ts:12-14`) |
| `send_message` | `{chat_id: string, body: string|null (trimmed), reply_to_message_id: int|null, forwarded_from_user_id: string|null, attachment_group_id: string|null, dedup_key: string}` | user sends message (`composables/supabase/useSendMessage.ts:9-20`, mutation wrapper `mutations/chats/sendMessage.ts:4-14`). `dedup_key` = client-generated idempotency key |
| `mark_message_read` | `{chat_id, message_id}` | viewing a message (`composables/supabase/useMarkMessageAsRead.ts:6-15`) |
| `edit_message` | `edit_message` Args type (UNCONFIRMED fields; called from edit flow) | edit own message (`composables/supabase/useEditMessage.ts:6-8`) |
| `delete_message` | `delete_message` Args type (UNCONFIRMED) | delete own message (`composables/supabase/useDeleteMessage.ts:6-8`) |
| `mute_chat` | `{chat_id}` | mute toggle (`composables/supabase/useMuteChat.ts:6-14`) |
| `new_dm` | `new_dm` Args (UNCONFIRMED) | start DM from contacts (`composables/supabase/useCreateDm.ts:6-8`) |
| `get_chat_details` | `{input}` | chat header info (`composables/supabase/useChatInfo.ts:6-8`) |
| `get_chat_info` | `{input}` | channel details (`composables/supabase/useGetChannelDetails.ts:6-8`) |
| `get_chat_id` | `{input}` | resolve chat id (`composables/supabase/useGetChatId.ts:6-8`) |
| `get_chat_participants_with_details` | `{input}` | participants list (`composables/supabase/useGetChatParticipants.ts:6-8`) |
| `get_user_info` | `{input}` | user details in chat (`composables/supabase/useGetUserDetails.ts:6-8`) |
| `get_unread_chat_count` | none | unread badge; also prefetched offline (`composables/supabase/useGetUnreadChatsCount.ts:3-5`, `utils/prefetchOfflineData.ts:50`) |

Response shapes: typed via `Database['private']['Functions'][fn]['Returns']` in
`~/types/schema` — that file is type-only and NOT recoverable from source maps;
individual response fields are therefore UNCONFIRMED except where UI code reads them
(e.g. chat item fields `id, cursor, last_read_message_id, last_message_id,
muted_until, archived_at` — `pages/chats.vue:340-365,105-106`; chat info `title,
cursor` — `pages/chats.vue:81,425-427`).

### 7.3 Direct table queries (PostgREST GET/POST `/rest/v1/<table>`)

- `profiles`: `GET` select all where `id != me AND is_deactivated = false` (contact
  picker — `composables/supabase/useUsers.ts:4-12`); `GET` by id
  (`composables/supabase/useUserProfile.ts:7-9`). Row fields typed as
  `Database['private']['Tables']['profiles']['Row']` (UNCONFIRMED beyond
  `id`, `is_deactivated`).
- `attachments`: `INSERT` rows `{sender_id, channel_id, group_id, bucket, path, name,
  mime, size, width, height, duration_ms, meta}` after files are uploaded to Storage
  (`composables/supabase/uploadAttachments.ts:13-28`).

### 7.4 Supabase Storage (bucket `attachments`)

- `POST /storage/v1/object/attachments/<path>` — file upload, `upsert:false`
  (`composables/supabase/uploadFile.ts:3-9`).
- move (rename) (`composables/supabase/updateFilePath.ts:3-5`).
- `createSignedUrl(path, expiresIn=60s)` for viewing/downloading attachments
  (`composables/supabase/createPublicLinkForAttachment.ts:9-12`).

### 7.5 Realtime (websocket `wss://tfnnpqpvdjisoizvciyr.supabase.co/realtime/v1/websocket`)

Private broadcast channels (`config: {private: true, broadcast: {ack: true}}`),
authenticated with the ValidNation JWT (`plugins/supabase.ts:164`):

- `chat-list:{userId}` — registered on chats layout mount; events:
  `chat_list_new_message, chat_list_new_chat, chat_list_delete_chat,
  chat_list_update_chat, chat_list_archive_chat, chat_list_read_message,
  chat_list_edit_message, chat_list_delete_message, chat_list_mute_chat,
  chat_list_unmute_chat`; payload `{record: ChatItem}` (`pages/chats.vue:369-416`).
- `chat:{chatId}` — registered on chat page mount; events: `new_message,
  edit_message, delete_message, edit_chat_details, edit_participant`
  (`pages/chats/[id].vue:372-403`).
- Both: on `system` event containing "Token has expired" → refresh JWT and reconnect
  (`pages/chats.vue:409-414`, `plugins/supabase.ts:205-223`). Channels are de-registered
  on unmount and the socket is disconnected when no channels remain
  (`pages/chats.vue:419-423`, `plugins/supabase.ts:200-203`).

---

## 8. `/api/canvasser_application/*` + W-9/Checkr (document flows; OUT of reimplementation scope)

Worker-facing onboarding forms; all write endpoints JSON, bearer.

- `POST /api/canvasser_application/general_info` — create canvasser info. Body type
  `CanvasserGeneralInfoForm`; form fields (zod): `date_of_birth (ISO date string),
  address, city, state, zip_code, military_service, equipment_confirmation (bool),
  referral_source, referral_source_other (only when referral_source === 'Other')`
  (`client/sdk.gen.ts:489-508` — doc string confirms field set;
  `components/account/profile/GeneralInfoForm.vue:3-112,231-237`,
  `mutations/account/setCanvasserApplication.ts:6-13`). Trigger: onboarding form
  submit (page `account/canvasser/edit/application`, canvasser role). On success:
  account refetch + redirect.
- `PUT /api/canvasser_application/{user_id}/general_info` — admin edit of the same
  fields; "Records who/when. Does not re-run the vetting pipeline."
  (`client/sdk.gen.ts:510-529`, `mutations/account/editGeneralInfo.ts:12-18`).
- `POST /api/canvasser_application/documents` — "Add SSN and ID photos". Body sent:
  `{id_photo_urls: string[] (≥1)}` — URLs obtained from the generic file-upload
  endpoint first (`POST /api/files` style upload, `mutations/uploadFile.ts:20-40`,
  multipart via CapacitorHttp); the `consent` checkbox is client-side only and NOT sent
  (`pages/account/canvasser/edit/documents/index.vue:71-115`). Note: despite the SDK
  doc string, no `ssn` field is sent by this page — SSN capture happens in the W-9
  (SignWell) flow server-side (contract detail exposes `parsed_ssn` to admins,
  `pages/contracts/[id]/index.vue:40`).
- W-9: manager triggers `POST /api/contracts/w9/send` with body `{canvasser_id:
  string}` (`client/sdk.gen.ts:838-857`, `mutations/users/sendOrResendW9Form.ts:7-11`);
  signing happens off-app via SignWell email link; worker/admin view status via
  `GET /api/contracts/v2/` (query: pagination + `statuses[], types[], project_ids[],
  canvasser_ids[], signed_by_admin, signed_by_canvasser, created_date_from/to,
  search_query, sort_by/sort_type` — `pages/contracts/index.vue:127-152`, page allows
  canvasser role) and `GET /api/contracts/v2/{contract_id}`
  (`pages/contracts/[id]/index.vue:154`; consumed: `type ('w9'|assignment),
  parsed_ssn, signed-by flags, status`). Webhook `SignWellWebhookHandler` is
  server-side only.
- Checkr: manager triggers `POST /api/users/{user_id}/checkr/request` (no body; 409 if
  already running) (`client/sdk.gen.ts:4722-4737`,
  `mutations/users/requestCheckrBackgroundCheck.ts:6-8`). Results arrive via
  server-side `CheckrWebhookHandler`.
- `DELETE /api/users/{user_id}/canvasser_application/{section}/` — admin resets one
  onboarding section; `section ∈ CanvasserSection` (used values include `profile`,
  `general_info` — `mutations/users/removeCanvasserInfo.ts:8-30`).

---

## 9. Recruitment — admin/manager only, NOT worker-facing

All recruitment pages require `admin` or `manager` (`pages/recruitment.vue:19`,
`pages/recruitment/index.vue:7`). The canvasser role never calls these; they are listed
so the reimplementation can ignore them. All JSON + bearer; methods/paths from
`client/sdk.gen.ts`:

- `GET|POST /api/recruitment/campaigns/` (list/create; create body `CampaignCreateRequest`,
  response `id` — `sdk.gen.ts:2968-3000`, `mutations/recruitment/createCampaign.ts:7-12`)
- `GET /api/recruitment/campaigns/by_project/{project_id}` (404 if none — `sdk.gen.ts:3002-3017`)
- `GET|PATCH /api/recruitment/campaigns/{campaign_id}` (`sdk.gen.ts:3019-3055`,
  `mutations/recruitment/updateCampaign.ts:7-11`)
- `PATCH /api/recruitment/campaigns/{campaign_id}/pause|/resume` (no body — `sdk.gen.ts:3057-3090`,
  `mutations/recruitment/pauseCampaign.ts:7-10`)
- `GET /api/recruitment/campaigns/{campaign_id}/stats` (`sdk.gen.ts:3091-3106`)
- `GET /api/recruitment/messages/` + `GET /api/recruitment/messages/{message_id}`
  (`sdk.gen.ts:3108-3161`)
- `POST /api/recruitment/messages/send_batch` — body `{emails: string[],
  idempotency_key: string, ignore_quiet_hours?: boolean, channel_strategy?:
  RecruitmentChannelStrategy}` (null strategy omitted → server default); returns 200
  with per-contact skip reasons even if all skipped (`sdk.gen.ts:3125-3144`,
  `mutations/recruitment/messages/sendBatch.ts:5-25`)
- Project-scoped variants: `GET /api/projects/{project_id}/recruitment/eligible_contacts`
  (query params type UNCONFIRMED — `queries/recruitment/projectEligibleContacts.ts:8-18`,
  `sdk.gen.ts:2618`) and `POST /api/projects/{project_id}/recruitment/send_batch`
  (body `ProjectRecruitmentSendBatchRequest` + same channel_strategy null-omission —
  `mutations/recruitment/projectSendBatch.ts:13-21`, `sdk.gen.ts:2635`)
- Prompt-editor (Gemini) preview endpoints: `GET
  /api/recruitment/settings/prompt/editor-metadata`, `POST
  …/preview/build-context|/generate|/render` (`sdk.gen.ts:3163-3241`,
  `mutations/recruitment/buildContextPreview.ts:8-11`). Response for `/generate`:
  email → subject+content, SMS → body + char/segment count (SDK doc string).

---

## 10. Resolved [H] items (DESIGN-VALIDNATION.md cross-reference)

1. **Voice sample** (doc lines 67-68): `POST /api/account/voice_sample/` is **JSON, not
   multipart**; fields `{audio_data: base64 PCM, audio_config: {sample_rate, channels,
   bits_per_sample, encoding:'linear16'}}` — see §2.5. The "[H] likely audio/webm"
   hypothesis is refuted (webm is preview-only).
2. **Earnings response shapes** (doc §8, line 177): totals-by-rate-type, Branch account
   status, balance, earning list/detail, transactions shapes resolved — see §1.1, §1.5,
   §1.6, §1.2/1.3, §1.8.
3. **`/api/broadcast`**: not a ValidNation endpoint; Supabase realtime-js artifact — §5.

## 11. Not confirmable in code (UNCONFIRMED)

- Full response field sets for every endpoint above (only consumed fields are proven);
  `client/types.gen.ts` and `~/types/schema` (Supabase Database types) are type-only
  and absent from the source maps.
- `AssignmentInfoBody` exact fields (§4), `EarningCreateRequest` fields (§1.9),
  `CanvasserSection` full enum (§8), RPC input/output composite types for chat (§7.2).
- Whether `/api/earnings/` etc. send additional envelope fields (e.g. `links`) — no
  consumer, cannot confirm.
