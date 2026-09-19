# Master endpoint inventory — `com.patriotgrassroots.validnation` v1.0.0 (114)

Audit date: 2026-09-19. Checklist: `patriot_grassroots/endpoints.txt` (265 paths).
Ground truth for method+path: the generated API client `client/sdk.gen.ts`
(hey-api openapi-ts; 322 exported operations) in the recovered frontend source
`/tmp/vn_src/` — all paths cited below are relative to `/tmp/vn_src/` unless
they start with `patriot_grassroots/`.

**Caveat (shapes):** `client/types.gen.ts` (the hey-api type definitions, ~all
`*Data`/`*Response` types) was NOT recovered from the source maps — it is a
build-time generated file with no runtime code, so source maps do not contain
it. Type *names* are known from `sdk.gen.ts:4`; exact field lists are confirmed
only where app code constructs or consumes the payload (mobile-critical
endpoints are fully confirmed this way). Everything else is marked
UNCONFIRMED. The live `https://api.validnation.ai/openapi.json` returns
`401 {"detail":"Not authenticated"}` unauthenticated (verified 2026-09-19), so
the OpenAPI schema could not be used.

**Canvasser-facing UI definition** (for DECLARED-UNUSED verdicts): pages whose
`roles` meta includes `canvasser`/`subcontractor_canvasser`
(`middleware/02.permission.global.ts`), the two `platform: 'mobile'` shift
pages (`pages/shift/index.vue:82-84`, `pages/shift/[id].vue:113-115`), the
mobile composables/stores/plugins (`composables/mobile/`, `stores/mobile/`,
`plugins/notifications.ts`, `plugins/stateChangeListeners.ts`,
`plugins/mobileInit.ts`), plus shared components they mount (sidebar,
notification list, entity labels, chats). Admin/manager pages exist in the
same shipped bundle but are role-gated; a canvasser JWT can never reach them.

---

## 1. Transports — every server-bound message uses one of these

| # | Transport | Used for | Key behavior |
|---|---|---|---|
| T1 | hey-api client (`client/client.gen.ts:15`) configured in `app.vue:40-73` on top of `$fetch` (ofetch; on native, CapacitorHttp patches global fetch) | All web-UI API calls (admin + canvasser pages) | `auth` hook = `authPreRequest` (proactive refresh if exp within 30 s, `composables/auth/httpInterceptors.ts:54-71`); `onResponse` 401 → refresh + single replay → sign-out cascade (`httpInterceptors.ts:106-137`); GET responses cached offline via `createCachingFetch` (`utils/offlineCache.ts:319`) |
| T2 | `doNativeRequest()` (`utils/mobile/doNativeRequest.ts:41-128`) on `CapacitorHttp.request` | All `mutations/mobile/*` (work_shift, sensors, device events/info, FCM token, unlink, versions, restricted_areas, selector/project) | `Authorization: Bearer` header attached (`:62`); `Content-Type: application/json` on non-GET; 15 s connect+read timeouts; 401 → refresh + one retry → foreground sign-out (`:102-128`); GET cache fallback on connectivity errors (`:90-99`); no CapacitorHttp CORS limits |
| T3 | Native multipart upload inside `audio-manager-plugin` (OkHttp, `patriot_grassroots/java/sources/validnation/ai/audiomanager/AudioManager.java`) | `/api/canvasser_voice/receive`, `/cached_receive`, `/wake_word_audio`, `/wake_word_audio_cached` | `Authorization` header + `multipart/form-data` bodies built natively; on failure the plugin writes the WAV to disk and JS indexes it in SQLite for later retry (audio-voice.md §2) |
| T4 | Hand-rolled `CapacitorHttp`/`XMLHttpRequest` multipart | `POST /api/upload/` (chat attachments) — `mutations/uploadFile.ts:19-36,64-119` | single `file` part; progress events on web |
| T5 | Supabase JS client (`plugins/supabase.ts:53-236`) | Chats: PostgREST `/rest/v1/`, RPC `/rest/v1/rpc/*`, Realtime websocket, Storage `attachments` bucket | Host `https://tfnnpqpvdjisoizvciyr.supabase.co`, schema `private`, app JWT as `Authorization` (`:74-78`); 401 → refresh+retry (`:104-118`); 5 s manual timeout race (`:80-92`); GET/RPC offline cache (`:96-156`) |
| T6 | Websocket `wss://api.validnation.ai/api/ws/voice_verification/{id}` | Signatory voice verification only (audio-voice.md §4) | one-time token from `GET /api/auth/ws_token` as query param (§WS below) |
| T7 | Firebase (FCM + Remote Config + Analytics) | push, remote tuning config | Remote Config min fetch interval 600 s, timeout 10 s (`composables/mobile/config/useMobileRemoteConfig.ts:8-11`) |
| T8 | Sentry tunnel `POST /api/sentry` | crash/error envelopes | `sentry.client.config.ts:12`; filtered to 400/403/404/5xx events (`:15-27`) |

Cross-cutting: `Authorization: Bearer <jwt>` goes ONLY to
`api.validnation.ai` and to the Supabase project (its own host)
— auth-session.md §7. JWT access token maxAge 900 s, refresh token 15 days
(`config/auth.ts:11-24`). Proactive refresh fires 60 s before `exp`
(`plugins/auth.ts:35-39`, `config/AuthRefreshHandler.ts:88-105`) — **resolves
[H]** DESIGN-VALIDNATION.md §2 line 54 ("80 % TTL" guess): stock is exp−60 s,
i.e. at 840 s of 900 s.

Offline behavior summary: GETs fall back to a CacheStorage API cache
(24 h TTL, 50 MB, `config/cache.ts:2-6`); a 4-hourly prefetch warms
`/api/account/`, `/api/selector/project`, `/api/earnings/balance/`,
`/api/earnings/account/`, `/api/projects/` (+short_info/details per project),
chat list + unread count (`utils/prefetchOfflineData.ts:14-57`,
`plugins/offlinePrefetch.ts:16-26`, `PREFETCH_INTERVAL` = 4 h
`config/cache.ts:17`). Mobile writes (sensors, events, shift pause/resume/
finalize, wake-word) queue into the SQLite `payloads` outbox and drain FIFO —
see shift-lifecycle.md §11 and sensors-telemetry.md §6. Audio has its own
WAV-file cache (`utils/mobile/uploadAudioNative.ts`).

---

## 2. Master table

Columns: Method/Path (ground truth `client/sdk.gen.ts`); Req type (name only —
fields UNCONFIRMED unless §6 or an owner file documents them); Trigger (in the
canvasser build); Owner audit file; Status/caller evidence.

Status vocabulary:
- `LIVE via mobile wrapper/native upload` — sent by the app, but through T2/T3
  wrappers that build the request by hand, not through the SDK function.
- `LIVE via config/auth.ts` — sent via `doMobileRequest`/`doWebRequest` with
  paths from `config/auth.ts:6-11`, not via the SDK function.
- a caller path (`file:line`) — SDK function called there.
- `DEAD — no caller in frontend` — declared in the API client but nothing in
  the shipped frontend ever calls it → **DECLARED-UNUSED** (any UI).
- callers only in admin/manager-gated pages → **DECLARED-UNUSED from the
  canvasser-facing UI** (noted in the group heading).

(The `Owner` column names the audit file that documents the endpoint in full;
`earnings-account-misc.md` rows are documented in §6 below.)

### Root / meta

| Method | Path | SDK fn `client/sdk.gen.ts` | Req type | Trigger (canvasser build) | Owner | Status / caller evidence |
|---|---|---|---|---|---|---|
| GET | `/` | `root` :24 | `RootData` | — (never sent) | earnings-account-misc.md | DEAD — no caller in frontend |
| GET | `/docs` | `getDocumentation` :5761 | `GetDocumentationData` | — (never sent) | earnings-account-misc.md | DEAD — no caller in frontend |
| GET | `/health` | `health` :5777 | `HealthData` | — (never sent) | earnings-account-misc.md | DEAD — no caller in frontend |
| GET | `/openapi.json` | `getOpenapi` :5787 | `GetOpenapiData` | — (never sent) | earnings-account-misc.md | DEAD — no caller in frontend |

### Auth & session

| Method | Path | SDK fn `client/sdk.gen.ts` | Req type | Trigger (canvasser build) | Owner | Status / caller evidence |
|---|---|---|---|---|---|---|
| POST | `/api/auth/logout` | `logout` :386 | `LogoutData` | user: sign out (auth-session.md §4) | auth-session.md | LIVE via config/auth.ts (not the SDK fn) |
| GET | `/api/auth/profile` | `getAuthProfile` :407 | `GetAuthProfileData` | post-login + app start + after each refresh (auth-session.md §3) | auth-session.md | LIVE via config/auth.ts (not the SDK fn) |
| POST | `/api/auth/refresh` | `refreshAuthToken` :424 | `RefreshAuthTokenData` | proactive timer at exp-60 s; 401-retry; route middleware; visibility (auth-session.md §2,§8) | auth-session.md | LIVE via config/auth.ts (not the SDK fn) |
| POST | `/api/auth/token` | `createAuthToken` :439 | `CreateAuthTokenData` | user: login submit (auth-session.md §1) | auth-session.md | LIVE via config/auth.ts (not the SDK fn) |
| GET | `/api/auth/ws_token` | `createAuthOneTimeToken` :455 | `CreateAuthOneTimeTokenData` | voice-verification WS connect (audio-voice.md §4) | auth-session.md | ./composables/useVoiceVerification.ts:1 |

### Sign-up

| Method | Path | SDK fn `client/sdk.gen.ts` | Req type | Trigger (canvasser build) | Owner | Status / caller evidence |
|---|---|---|---|---|---|---|
| POST | `/api/signup/` | `signUpNewAccount` :3780 | `SignUpNewAccountData` | user: sign up (`mutations/signUp/index.ts:7`) | earnings-account-misc.md | ./mutations/signUp/index.ts:1 |
| PUT | `/api/signup/email/` | `signUpChangeEmail` :3795 | `SignUpChangeEmailData` | user: change email mid-signup (`mutations/signUp/changeEmail.ts:9`) | earnings-account-misc.md | ./mutations/signUp/changeEmail.ts:1 |
| POST | `/api/signup/email/confirm` | `signUpConfirmEmail` :3810 | `SignUpConfirmEmailData` | user: confirm email code (`mutations/signUp/confirmEmail.ts:7`) | earnings-account-misc.md | ./mutations/signUp/confirmEmail.ts:1 |
| POST | `/api/signup/email/info` | `getSignUpEmailInfo` :3825 | `GetSignUpEmailInfoData` | signup flow (`queries/signUp/infoEmail.ts:12`) | earnings-account-misc.md | ./queries/signUp/infoEmail.ts:1 |
| POST | `/api/signup/email/resend` | `signUpResendConfirmationEmail` :3840 | `SignUpResendConfirmationEmailData` | user: resend code (`mutations/signUp/resendEmail.ts:7`) | earnings-account-misc.md | ./mutations/signUp/resendEmail.ts:1 |

### Account

| Method | Path | SDK fn `client/sdk.gen.ts` | Req type | Trigger (canvasser build) | Owner | Status / caller evidence |
|---|---|---|---|---|---|---|
| GET | `/api/account/` | `getAccountDetails` :35 | `GetAccountDetailsData` | account pages mount (`queries/account.ts:2-13`) + offline prefetch (4 h, `utils/prefetchOfflineData.ts:20`) | earnings-account-misc.md | ./queries/account.ts:1 |
| PUT | `/api/account/password/edit` | `editAccountPassword` :52 | `EditAccountPasswordData` | user: change password (`mutations/account/editUserPassword.ts:12`) | earnings-account-misc.md | ./mutations/account/editUserPassword.ts:1 |
| POST | `/api/account/password/reset` | `accountPasswordReset` :73 | `AccountPasswordResetData` | user: forgot-password (`mutations/resetPassword.ts:8`) | earnings-account-misc.md | ./mutations/resetPassword.ts:1 |
| POST | `/api/account/password/set` | `accountPasswordSet` :88 | `AccountPasswordSetData` | user: set password from invite/reset (`mutations/setPassword.ts:8`) | earnings-account-misc.md | ./mutations/setPassword.ts:1 |
| GET | `/api/account/referral_code` | `getReferralCode` :103 | `GetReferralCodeData` | — (never sent) | earnings-account-misc.md | DEAD — no caller in frontend |
| PATCH | `/api/account/settings/edit` | `editAccountSettings` :120 | `EditAccountSettingsData` | user: edit account settings (`mutations/account/editUserSettings.ts:12`) | earnings-account-misc.md | ./mutations/account/editUserSettings.ts:1 |
| POST | `/api/account/voice_sample/` | `createVoiceSample` :141 | `CreateVoiceSampleData` | user: record+save voice sample (audio-voice.md §1) | audio-voice.md | ./mutations/createSample.ts:1 |
| PATCH | `/api/account/{user_id}/delete` | `deleteAccount` :162 | `DeleteAccountData` | user: delete account (`mutations/users/deleteUser.ts:10`) | earnings-account-misc.md | ./mutations/users/deleteUser.ts:1 |

### Canvasser application

| Method | Path | SDK fn `client/sdk.gen.ts` | Req type | Trigger (canvasser build) | Owner | Status / caller evidence |
|---|---|---|---|---|---|---|
| POST | `/api/canvasser_application/documents` | `postCanvasserDocuments` :472 | `PostCanvasserDocumentsData` | canvasser: edit-application documents save (`pages/account/canvasser/edit/documents/index.vue:96`) | earnings-account-misc.md | ./pages/account/canvasser/edit/documents/index.vue:58 |
| POST | `/api/canvasser_application/general_info` | `postCanvasserGeneralInfo` :493 | `PostCanvasserGeneralInfoData` | canvasser: application general-info save (`mutations/account/setCanvasserApplication.ts:8`) | earnings-account-misc.md | ./mutations/account/setCanvasserApplication.ts:1 |
| PUT | `/api/canvasser_application/{user_id}/general_info` | `editCanvasserGeneralInfo` :514 | `EditCanvasserGeneralInfoData` | web UI (see caller) | earnings-account-misc.md | ./pages/users/[id]/edit/general-info.vue:37 |

### Applications & assignments

| Method | Path | SDK fn `client/sdk.gen.ts` | Req type | Trigger (canvasser build) | Owner | Status / caller evidence |
|---|---|---|---|---|---|---|
| GET | `/api/applications/` | `getUpcomingProjects` :179 | `GetUpcomingProjectsData` | canvasser: upcoming-projects list mount (`queries/applications/upcomingProjects.ts:33`) | earnings-account-misc.md | ./queries/applications/upcomingProjects.ts:6 |
| POST | `/api/applications/applicants/` | `getUserApplications` :196 | `GetUserApplicationsData` | web UI (see caller) | earnings-account-misc.md | ./components/applications/details/ApplicationsDetailsTable.vue:30 |
| GET | `/api/applications/applied` | `getAppliedProjectsForCanvasser` :217 | `GetAppliedProjectsForCanvasserData` | canvasser: "My applications" page mount (`pages/applications/my.vue:65`) | earnings-account-misc.md | ./pages/applications/my.vue:23 |
| POST | `/api/applications/approve` | `projectApplicationApprove` :234 | `ProjectApplicationApproveData` | web UI (see caller) | earnings-account-misc.md | ./mutations/applications/approveCanvasser.ts:1 |
| PUT | `/api/applications/create` | `applyToProject` :255 | `ApplyToProjectData` | canvasser: Apply button (`mutations/applications/applyToProject.ts:9`) | earnings-account-misc.md | ./mutations/applications/applyToProject.ts:1 |
| POST | `/api/applications/reject` | `projectApplicationReject` :276 | `ProjectApplicationRejectData` | web UI (see caller) | earnings-account-misc.md | ./mutations/applications/rejectCanvasser.ts:1 |
| GET | `/api/applications/{project_id}` | `getUpcomingProjectDetails` :297 | `GetUpcomingProjectDetailsData` | canvasser: application details page (`queries/applications/details.ts:14`) | earnings-account-misc.md | ./queries/applications/details.ts:1 |
| GET | `/api/assignments/{project_id}/{user_id}` | `getAssignmentDetails` :314 | `GetAssignmentDetailsData` | web UI (see caller) | earnings-account-misc.md | ./pages/assignments/[project_id]/[user_id].vue:57 |
| POST | `/api/assignments/{project_id}/{user_id}/contracts/resend` | `resendAssignmentContract` :331 | `ResendAssignmentContractData` | — (never sent) | earnings-account-misc.md | DEAD — no caller in frontend |
| PUT | `/api/assignments/{project_id}/{user_id}/info` | `updateAssignmentInfo` :348 | `UpdateAssignmentInfoData` | web UI (see caller) | earnings-account-misc.md | ./mutations/assignments/updateInfo.ts:1 |
| GET | `/api/assignments/{project_id}/{user_id}/status-history` | `getAssignmentStatusHistory` :369 | `GetAssignmentStatusHistoryData` | web UI (see caller) | earnings-account-misc.md | ./components/assignments/details/AssignmentsDetailsStatusHistory.vue:59 |

### Mobile — work shift

| Method | Path | SDK fn `client/sdk.gen.ts` | Req type | Trigger (canvasser build) | Owner | Status / caller evidence |
|---|---|---|---|---|---|---|
| POST | `/api/mobile/work_shift/finalize_v2` | `finalizeWorkShiftV2` :1522 | `FinalizeWorkShiftV2Data` | clock-out, after outbox drain (shift-lifecycle.md §4) | shift-lifecycle.md | LIVE via mobile wrapper/native upload (not the SDK fn) |
| POST | `/api/mobile/work_shift/generate` | `generateWorkShiftId` :1543 | `GenerateWorkShiftIdData` | shift start / cross-device interrupt (shift-lifecycle.md §1) | shift-lifecycle.md | ./composables/mobile/shift/useMobileShift.ts:11 |
| POST | `/api/mobile/work_shift/pause` | `pauseWorkShift` :1564 | `PauseWorkShiftData` | break start, via outbox FIFO (shift-lifecycle.md §3) | shift-lifecycle.md | ./utils/mobile/uploadShiftBreakEventBatch.ts:1 |
| POST | `/api/mobile/work_shift/resume` | `resumeWorkShift` :1585 | `ResumeWorkShiftData` | break end, via outbox FIFO (shift-lifecycle.md §3) | shift-lifecycle.md | ./utils/mobile/uploadShiftBreakEventBatch.ts:2 |
| GET | `/api/mobile/work_shift/status_v2` | `checkWorkShiftStatusV2` :1606 | `CheckWorkShiftStatusV2Data` | shift start pre-check, app.vue 5-min poll, resume/restore, foreground resume (shift-lifecycle.md §2) | shift-lifecycle.md | LIVE via mobile wrapper/native upload (not the SDK fn) |

### Mobile — device, events, push token

| Method | Path | SDK fn `client/sdk.gen.ts` | Req type | Trigger (canvasser build) | Owner | Status / caller evidence |
|---|---|---|---|---|---|---|
| POST | `/api/mobile/device/action/data_sync` | `attemptDataSync` :1292 | `AttemptDataSyncData` | — (never sent) | earnings-account-misc.md | DEAD — no caller in frontend |
| POST | `/api/mobile/device/action/live_update` | `attemptLiveUpdate` :1313 | `AttemptLiveUpdateData` | — (never sent) | earnings-account-misc.md | DEAD — no caller in frontend |
| POST | `/api/mobile/device/event/batch_send` | `mobileDeviceEventBatchSend` :1334 | `MobileDeviceEventBatchSendData` | outbox drain of queued mobile events (shift-lifecycle.md §7,§11) | shift-lifecycle.md | LIVE via mobile wrapper/native upload (not the SDK fn) |
| POST | `/api/mobile/device/event/send` | `mobileDeviceEventSend` :1355 | `MobileDeviceEventSendData` | mobile events: app_state, device_state_sync, app_termination, restored_after_termination, live_update_*, audio_cache_cleanup, tracker_state_divergence, pause_stop_failed, data_upload (shift-lifecycle.md §7) | shift-lifecycle.md | LIVE via mobile wrapper/native upload (not the SDK fn) |
| POST | `/api/mobile/device/send_event` | `sendMobileDeviceEvents` :1377 | `SendMobileDeviceEventsData` | — (never sent) | earnings-account-misc.md | DEAD — no caller in frontend |
| POST | `/api/mobile/device/unlink` | `unlinkMobileDeviceFromCurrentUser` :1399 | `UnlinkMobileDeviceFromCurrentUserData` | logout, native only (`utils/mobile/unlinkDeviceFromUser.ts:9-33`) | shift-lifecycle.md | LIVE via mobile wrapper/native upload (not the SDK fn) |
| POST | `/api/mobile/device/update_info` | `deviceInfoUpdate` :1420 | `DeviceInfoUpdateData` | app.vue 5-min poll, shift start, push toggle, ensure-linked single-flight (shift-lifecycle.md §6) | shift-lifecycle.md | LIVE via mobile wrapper/native upload (not the SDK fn) |
| DELETE | `/api/mobile/notifications/token` | `unregisterFcmToken` :1441 | `UnregisterFcmTokenData` | push registration/token refresh (POST), user opt-out (DELETE) (shift-lifecycle.md §9) | shift-lifecycle.md | LIVE via mobile wrapper/native upload (not the SDK fn) |
| POST | `/api/mobile/notifications/token` | `syncFcmToken` :1458 | `SyncFcmTokenData` | push registration/token refresh (POST), user opt-out (DELETE) (shift-lifecycle.md §9) | shift-lifecycle.md | LIVE via mobile wrapper/native upload (not the SDK fn) |

### Mobile — sensors

| Method | Path | SDK fn `client/sdk.gen.ts` | Req type | Trigger (canvasser build) | Owner | Status / caller evidence |
|---|---|---|---|---|---|---|
| POST | `/api/mobile/sensor/` | `uploadSensorData` :1480 | `UploadSensorDataData` | — (never sent) | sensors-telemetry.md | DEAD — no caller in frontend |
| POST | `/api/mobile/sensor/batch_upload` | `batchUploadSensorData` :1501 | `BatchUploadSensorDataData` | uploader tick: background-fetch 15 min, push, pause/resume/finish, foreground-resume 15-min throttle, manual sync (sensors-telemetry.md §1,§5) | sensors-telemetry.md | LIVE via mobile wrapper/native upload (not the SDK fn) |

### Mobile — version / live-update

| Method | Path | SDK fn `client/sdk.gen.ts` | Req type | Trigger (canvasser build) | Owner | Status / caller evidence |
|---|---|---|---|---|---|---|
| POST | `/api/settings/versions` | `getVersionsInfo` :3765 | `GetVersionsInfoData` | app cold start (silent), resume (prompt, 3 h throttle), push live-update (`composables/mobile/updates/useMobileLiveUpdates.ts:56-139`) | earnings-account-misc.md | LIVE via mobile wrapper/native upload (not the SDK fn) |

### Audio & voice upload

| Method | Path | SDK fn `client/sdk.gen.ts` | Req type | Trigger (canvasser build) | Owner | Status / caller evidence |
|---|---|---|---|---|---|---|
| POST | `/api/canvasser_voice/cached_receive` | `receiveCachedCanvasserVoices` :535 | `ReceiveCachedCanvasserVoicesData` | uploader tail: cached audio retry (audio-voice.md §2) | audio-voice.md | LIVE via mobile wrapper/native upload (not the SDK fn) |
| POST | `/api/canvasser_voice/receive` | `receiveCanvasserVoice` :557 | `ReceiveCanvasserVoiceData` | VAD segment-pool auto-flush (~120 s audio) + stop-flow flush (audio-voice.md §2) | audio-voice.md | LIVE via mobile wrapper/native upload (not the SDK fn) |
| POST | `/api/canvasser_voice/wake_word_audio` | `receiveWakeWordAudioClip` :579 | `ReceiveWakeWordAudioClipData` | wake-word clip upload (audio-voice.md §3) | audio-voice.md | LIVE via mobile wrapper/native upload (not the SDK fn) |
| POST | `/api/canvasser_voice/wake_word_audio_cached` | `receiveCachedWakeWordAudioClips` :601 | `ReceiveCachedWakeWordAudioClipsData` | cached wake-word clip retry (audio-voice.md §3) | audio-voice.md | LIVE via mobile wrapper/native upload (not the SDK fn) |
| POST | `/api/canvasser_voice/wake_word_event` | `wakeWordDetectionEvent` :623 | `WakeWordDetectionEventData` | wake-word detection (shift-lifecycle.md §8) | shift-lifecycle.md | LIVE via mobile wrapper/native upload (not the SDK fn) |

### Earnings

| Method | Path | SDK fn `client/sdk.gen.ts` | Req type | Trigger (canvasser build) | Owner | Status / caller evidence |
|---|---|---|---|---|---|---|
| GET | `/api/earnings/` | `getEarningList` :966 | `GetEarningListData` | earnings list page (`pages/earnings/index.vue:116`) | earnings-account-misc.md | ./pages/earnings/index.vue:61 |
| POST | `/api/earnings/` | `createEarning` :983 | `CreateEarningData` | earnings list page (`pages/earnings/index.vue:116`) | earnings-account-misc.md | ./mutations/earnings/create.ts:1 |
| GET | `/api/earnings/account/` | `getPaymentAccountDetails` :1004 | `GetPaymentAccountDetailsData` | earnings/balance pages + prefetch (`queries/earnings/details.ts:12`) | earnings-account-misc.md | ./queries/earnings/details.ts:1 |
| PATCH | `/api/earnings/account/{user_id}` | `editPaymentUserSettings` :1021 | `EditPaymentUserSettingsData` | user: edit payment info (`mutations/users/updatePaymentInfo.ts:12`) | earnings-account-misc.md | ./mutations/users/updatePaymentInfo.ts:1 |
| GET | `/api/earnings/balance/` | `getEarningBalance` :1042 | `GetEarningBalanceData` | balance page + prefetch (`queries/earnings/balance.ts:11`) | earnings-account-misc.md | ./queries/earnings/balance.ts:1 |
| GET | `/api/earnings/totals-by-rate-type/` | `getEarningTotalsByRateType` :1059 | `GetEarningTotalsByRateTypeData` | earnings pages (`queries/earnings/totalsByRateType.ts:8`, staleTime 60 s) | earnings-account-misc.md | ./queries/earnings/totalsByRateType.ts:1 |
| GET | `/api/earnings/transactions/` | `getTransactionList` :1076 | `GetTransactionListData` | transactions list page (`pages/earnings/transactions/index.vue:127`) | earnings-account-misc.md | ./pages/earnings/transactions/index.vue:73 |
| GET | `/api/earnings/transactions/{transaction_id}` | `getTransactionDetails` :1093 | `GetTransactionDetailsData` | transaction details page (`queries/earnings/transactions/details.ts:13`) | earnings-account-misc.md | ./queries/earnings/transactions/details.ts:1 |
| GET | `/api/earnings/transactions/{transaction_id}/earnings` | `getTransactionEarnings` :1110 | `GetTransactionEarningsData` | transaction details page (`queries/earnings/transactions/breakdown.ts:16`) | earnings-account-misc.md | ./queries/earnings/transactions/breakdown.ts:1 |
| GET | `/api/earnings/transactions/{transaction_id}/short_info` | `getTransactionShortInfo` :1127 | `GetTransactionShortInfoData` | — (never sent) | earnings-account-misc.md | DEAD — no caller in frontend |
| POST | `/api/earnings/withdraw` | `createDisbursement` :1144 | `CreateDisbursementData` | user: Withdraw button (`mutations/earnings/withdraw.ts:7`) | earnings-account-misc.md | ./mutations/earnings/withdraw.ts:1 |
| GET | `/api/earnings/{earning_id}` | `getEarningDetails` :1161 | `GetEarningDetailsData` | earning details page (`queries/earnings/earningDetails.ts:15`) | earnings-account-misc.md | ./queries/earnings/earningDetails.ts:1 |
| PATCH | `/api/earnings/{earning_id}/approve` | `approveEarning` :1178 | `ApproveEarningData` | web UI (see caller) | earnings-account-misc.md | ./mutations/earnings/approve.ts:1 |
| PATCH | `/api/earnings/{earning_id}/manually_completed` | `markEarningManuallyCompleted` :1199 | `MarkEarningManuallyCompletedData` | web UI (see caller) | earnings-account-misc.md | ./mutations/earnings/payManually.ts:1 |
| POST | `/api/earnings/{earning_id}/pay` | `payEarningNow` :1220 | `PayEarningNowData` | web UI (see caller) | earnings-account-misc.md | ./mutations/earnings/payNow.ts:1 |
| PATCH | `/api/earnings/{earning_id}/reject` | `rejectEarning` :1237 | `RejectEarningData` | web UI (see caller) | earnings-account-misc.md | ./mutations/earnings/reject.ts:1 |
| GET | `/api/earnings/{earning_id}/short_info` | `getEarningShortInfo` :1258 | `GetEarningShortInfoData` | inline entity labels (`components/common/labeled-entity/LabeledEntityEarning.vue:37`) | earnings-account-misc.md | ./components/common/labeled-entity/InlineEntityEarning.vue:13 |

### Notifications (in-app)

| Method | Path | SDK fn `client/sdk.gen.ts` | Req type | Trigger (canvasser build) | Owner | Status / caller evidence |
|---|---|---|---|---|---|---|
| GET | `/api/notifications/list` | `notificationsList` :1623 | `NotificationsListData` | notifications page (`pages/notifications/index.vue:77`) | earnings-account-misc.md | ./pages/notifications/index.vue:44 |
| POST | `/api/notifications/mark_all_as_read` | `markAllAsRead` :1640 | `MarkAllAsReadData` | user: Read All (`components/notification/list/NotificationListActions.vue:20`) | earnings-account-misc.md | ./components/notification/list/NotificationListActions.vue:8 |
| POST | `/api/notifications/mark_as_read/{notification_id}` | `markAsRead` :1657 | `MarkAsReadData` | user: mark read (`components/notification/NotificationListItem.vue:73`) | earnings-account-misc.md | ./components/notification/NotificationListItem.vue:39 |
| GET | `/api/notifications/unread-count` | `getUnreadNotificationsCount` :1674 | `GetUnreadNotificationsCountData` | poll 60 s foreground (`components/sidebar/AppSidebar.vue:93-99`) | earnings-account-misc.md | ./components/sidebar/AppSidebar.vue:56 |

### Verification — voice & voters

| Method | Path | SDK fn `client/sdk.gen.ts` | Req type | Trigger (canvasser build) | Owner | Status / caller evidence |
|---|---|---|---|---|---|---|
| GET | `/api/verifications/voice/` | `getVoiceVerificationList` :5285 | `GetVoiceVerificationListData` | — (never sent) | audio-voice.md | DEAD — no caller in frontend |
| PUT | `/api/verifications/voice/` | `createVoiceVerification` :5302 | `CreateVoiceVerificationData` | canvasser: start voice verification, body `{project_id}` (`stores/verification/voice.ts:19-26`) | audio-voice.md | ./stores/verification/voice.ts:2 |
| GET | `/api/verifications/voice/{conversation_id}` | `getVoiceVerification` :5323 | `GetVoiceVerificationData` | voice verification page mount (`queries/verification/voice-details.ts:9`) | audio-voice.md | ./stores/verification/voice.ts:3 |
| POST | `/api/verifications/voice/{conversation_id}/submit` | `submitVoiceVerification` :5340 | `SubmitVoiceVerificationData` | canvasser: submit signatories (`mutations/verification/voice.ts:11`) | audio-voice.md | ./mutations/verification/voice.ts:1 |
| PUT | `/api/verifications/voter/` | `createVerificationVoters` :5361 | `CreateVerificationVotersData` | canvasser: create signatory voters (`mutations/verification/voter.ts:8`) | earnings-account-misc.md | ./pages/verification/signatory/create.vue:58 |

### Verification — ballots & signatures

| Method | Path | SDK fn `client/sdk.gen.ts` | Req type | Trigger (canvasser build) | Owner | Status / caller evidence |
|---|---|---|---|---|---|---|
| GET | `/api/verifications/ballot/` | `getBallotVerification` :4984 | `GetBallotVerificationData` | web UI (see caller) | earnings-account-misc.md | ./queries/verification/ballot.ts:1 |
| POST | `/api/verifications/ballot/` | `addNewBallot` :5001 | `AddNewBallotData` | web UI (see caller) | earnings-account-misc.md | ./pages/verification/ballots/import/index.vue:145 |
| PUT | `/api/verifications/ballot/` | `submitBallotVerification` :5022 | `SubmitBallotVerificationData` | web UI (see caller) | earnings-account-misc.md | ./mutations/verification/submitBallots.ts:1 |
| GET | `/api/verifications/ballot/list` | `getBallotVerificationList` :5043 | `GetBallotVerificationListData` | ballots list page (`pages/verification/ballots/index.vue:122`) | earnings-account-misc.md | ./pages/verification/ballots/index.vue:79 |
| POST | `/api/verifications/ballot/pages/` | `addNewBallotPage` :5060 | `AddNewBallotPageData` | ballot page add (`mutations/verification/addPage.ts:7`) | earnings-account-misc.md | ./mutations/verification/addPage.ts:1 |
| GET | `/api/verifications/ballot/pages/{ballot_page_id}` | `getBallotVerificationPageDetails` :5081 | `GetBallotVerificationPageDetailsData` | web UI (see caller) | earnings-account-misc.md | ./queries/verification/ballots/pageDetails.ts:1 |
| DELETE | `/api/verifications/ballot/pages/{page_id}` | `removeBallotPage` :5098 | `RemoveBallotPageData` | web UI (see caller) | earnings-account-misc.md | ./components/verification/ballots/VerificationBallotsImagePreview.vue:29 |
| PUT | `/api/verifications/ballot/upload-batch` | `uploadBallotBatch` :5115 | `UploadBallotBatchData` | ballot batch upload (`pages/verification/ballots/import/index.vue:199`) | earnings-account-misc.md | ./pages/verification/ballots/import/index.vue:108 |
| DELETE | `/api/verifications/ballot/{ballot_id}` | `removeBallot` :5136 | `RemoveBallotData` | web UI (see caller) | earnings-account-misc.md | ./mutations/verification/removeBallot.ts:1 |
| GET | `/api/verifications/ballot/{ballot_id}` | `getBallotVerificationDetails` :5153 | `GetBallotVerificationDetailsData` | web UI (see caller) | earnings-account-misc.md | ./queries/verification/ballots/details.ts:1 |
| PUT | `/api/verifications/ballot/{ballot_id}/upload-files` | `uploadBallotFiles` :5170 | `UploadBallotFilesData` | ballot photo upload (`components/verification/ballots/VerificationBallotsListItem.vue:141`) | earnings-account-misc.md | ./pages/verification/ballots/import/index.vue:110 |
| GET | `/api/verifications/signature/submitted/` | `getSubmittedSignaturesList` :5191 | `GetSubmittedSignaturesListData` | web UI (see caller) | earnings-account-misc.md | ./pages/projects/[id]/signatures.vue:78 |
| POST | `/api/verifications/signature/submitted/export/` | `createExportSubmittedSignaturesJob` :5208 | `CreateExportSubmittedSignaturesJobData` | web UI (see caller) | earnings-account-misc.md | ./mutations/project/exportSignatures.ts:1 |
| GET | `/api/verifications/signature/submitted/{submitted_signature_id}` | `getSubmittedSignatureDetails` :5229 | `GetSubmittedSignatureDetailsData` | web UI (see caller) | earnings-account-misc.md | ./pages/verification/ballots/signatures/submitted/[id].vue:101 |
| POST | `/api/verifications/signature/valid/export/` | `createExportValidSignaturesJob` :5246 | `CreateExportValidSignaturesJobData` | — (never sent) | earnings-account-misc.md | DEAD — no caller in frontend |
| GET | `/api/verifications/signature/valid/{valid_signature_id}` | `getValidSignatureDetails` :5267 | `GetValidSignatureDetailsData` | web UI (see caller) | earnings-account-misc.md | ./pages/verification/ballots/signatures/valid/[id].vue:57 |

### Wake-word events (emergencies UI)

| Method | Path | SDK fn `client/sdk.gen.ts` | Req type | Trigger (canvasser build) | Owner | Status / caller evidence |
|---|---|---|---|---|---|---|
| GET | `/api/wake_word_events/` | `getWakeWordEventList` :5382 | `GetWakeWordEventListData` | emergencies list page (`pages/emergencies/index.vue:115`) | earnings-account-misc.md | ./pages/emergencies/index.vue:69 |
| GET | `/api/wake_word_events/{wake_word_event_id}` | `getWakeWordEventDetails` :5399 | `GetWakeWordEventDetailsData` | emergency details page (`pages/emergencies/[id].vue:87`) | earnings-account-misc.md | ./pages/emergencies/[id].vue:65 |

### Work shift (non-mobile API)

| Method | Path | SDK fn `client/sdk.gen.ts` | Req type | Trigger (canvasser build) | Owner | Status / caller evidence |
|---|---|---|---|---|---|---|
| GET | `/api/work_shift/` | `getWorkShiftList` :5508 | `GetWorkShiftListData` | canvasser: shift page recent-shifts (page=1,size=5; `pages/shift/index.vue:113-128`) + admin workshifts pages | earnings-account-misc.md | ./pages/shift/index.vue:91 |
| POST | `/api/work_shift/export/` | `createExportWorkShiftsJob` :5525 | `CreateExportWorkShiftsJobData` | web UI (see caller) | earnings-account-misc.md | ./mutations/workshifts/exportWorkShiftsList.ts:1 |
| GET | `/api/work_shift/{work_shift_id}` | `getWorkShiftDetails` :5546 | `GetWorkShiftDetailsData` | web UI (see caller) | earnings-account-misc.md | ./pages/workshifts/[id].vue:211 |
| GET | `/api/work_shift/{work_shift_id}/canvassing_app_stats` | `getCanvassingAppStatsForAWorkShift` :5563 | `GetCanvassingAppStatsForAWorkShiftData` | — (never sent) | earnings-account-misc.md | DEAD — no caller in frontend |
| GET | `/api/work_shift/{work_shift_id}/conversations` | `getWorkShiftConversations` :5580 | `GetWorkShiftConversationsData` | shift conversations query (`queries/workshifts/conversations.ts:7`) | earnings-account-misc.md | ./queries/workshifts/conversations.ts:1 |
| GET | `/api/work_shift/{work_shift_id}/earning_progress` | `getWorkShiftEarningProgress` :5597 | `GetWorkShiftEarningProgressData` | canvasser: active shift page, refetch on mount, no polling (`queries/workshifts/earningProgress.ts:2-15`) | earnings-account-misc.md | ./queries/workshifts/earningProgress.ts:1 |
| POST | `/api/work_shift/{work_shift_id}/export/` | `createWorkShiftDataExportJob` :5614 | `CreateWorkShiftDataExportJobData` | web UI (see caller) | earnings-account-misc.md | ./mutations/workshifts/exportWorkShiftData.ts:2 |
| GET | `/api/work_shift/{work_shift_id}/interactions` | `getWorkShiftUnifiedInteractionsMapData` :5635 | `GetWorkShiftUnifiedInteractionsMapDataData` | — (never sent) | earnings-account-misc.md | DEAD — no caller in frontend |
| POST | `/api/work_shift/{work_shift_id}/interactions/exclusions` | `excludeOrRestoreWorkShiftInteractions` :5652 | `ExcludeOrRestoreWorkShiftInteractionsData` | web UI (see caller) | earnings-account-misc.md | ./mutations/workshifts/excludeInteractions.ts:1 |
| POST | `/api/work_shift/{work_shift_id}/recalculate/` | `recalculateWorkShiftHoursAndEarnings` :5673 | `RecalculateWorkShiftHoursAndEarningsData` | web UI (see caller) | earnings-account-misc.md | ./pages/workshifts/[id].vue:212 |
| PATCH | `/api/work_shift/{work_shift_id}/review` | `reviewWorkShift` :5690 | `ReviewWorkShiftData` | web UI (see caller) | earnings-account-misc.md | ./pages/workshifts/[id].vue:233 |
| GET | `/api/work_shift/{work_shift_id}/review_data` | `getWorkShiftReviewData` :5711 | `GetWorkShiftReviewDataData` | web UI (see caller) | earnings-account-misc.md | ./queries/workshifts/reviewData.ts:1 |
| GET | `/api/work_shift/{work_shift_id}/route_with_interactions` | `getWorkShiftRouteWithInteractions` :5728 | `GetWorkShiftRouteWithInteractionsData` | web UI (see caller) | earnings-account-misc.md | ./queries/workshifts/routeWithInteractions.ts:1 |
| GET | `/api/work_shift/{work_shift_id}/short_info` | `getWorkShiftShortInfo` :5745 | `GetWorkShiftShortInfoData` | entity labels (`components/common/labeled-entity/LabeledEntityWorkShift.vue:38`) | earnings-account-misc.md | ./components/common/labeled-entity/LabeledEntityWorkShift.vue:26 |

### Contracts

| Method | Path | SDK fn `client/sdk.gen.ts` | Req type | Trigger (canvasser build) | Owner | Status / caller evidence |
|---|---|---|---|---|---|---|
| GET | `/api/contracts/` | `getContractList` :749 | `GetContractListData` | — (never sent) | earnings-account-misc.md | DEAD — no caller in frontend |
| POST | `/api/contracts/sync` | `syncContractsTemplates` :766 | `SyncContractsTemplatesData` | web UI (see caller) | earnings-account-misc.md | ./components/project/edit/configuration/ProjectEditConfigurationContractTemplatesCard.vue:125 |
| POST | `/api/contracts/terminate` | `terminateContract` :787 | `TerminateContractData` | web UI (see caller) | earnings-account-misc.md | ./mutations/contract/terminateContract.ts:1 |
| GET | `/api/contracts/v2/` | `getContractListV2` :808 | `GetContractListV2Data` | contracts list page mount (`pages/contracts/index.vue:152`) | earnings-account-misc.md | ./pages/contracts/index.vue:99 |
| GET | `/api/contracts/v2/{contract_id}` | `getContractDetailsV2` :825 | `GetContractDetailsV2Data` | contract details page mount (`pages/contracts/[id]/index.vue:154`) | earnings-account-misc.md | ./pages/contracts/[id]/index.vue:133 |
| POST | `/api/contracts/w9/send` | `sendOrResendW9Form` :842 | `SendOrResendW9FormData` | web UI (see caller) | earnings-account-misc.md | ./mutations/users/sendOrResendW9Form.ts:1 |
| GET | `/api/contracts/{contract_id}` | `getContractDetails` :864 | `GetContractDetailsData` | — (never sent) | earnings-account-misc.md | DEAD — no caller in frontend |
| GET | `/api/contracts/{contract_id}/short_info` | `getContractShortInfo` :881 | `GetContractShortInfoData` | entity label (`components/common/labeled-entity/LabeledEntityContract.vue:35`) | earnings-account-misc.md | ./components/common/labeled-entity/LabeledEntityContract.vue:22 |

### Profile & sharing

| Method | Path | SDK fn `client/sdk.gen.ts` | Req type | Trigger (canvasser build) | Owner | Status / caller evidence |
|---|---|---|---|---|---|---|
| POST | `/api/profile/` | `setProfile` :1691 | `SetProfileData` | user: set profile (`mutations/account/setProfile.ts:10`) | earnings-account-misc.md | ./mutations/account/setProfile.ts:1 |
| POST | `/api/profile/generate-bio` | `generateBioFromAnswers` :1712 | `GenerateBioFromAnswersData` | user: generate bio (`mutations/account/generateBio.ts:13`) | earnings-account-misc.md | ./mutations/account/generateBio.ts:1 |
| GET | `/api/profile/shared/{shareable_code}` | `getSharedDetails` :1733 | `GetSharedDetailsData` | public shared-profile page (`pages/share/profile/[code].vue:41`) | earnings-account-misc.md | ./pages/share/profile/[code].vue:24 |
| PUT | `/api/profile/shared/{user_id}/disable` | `disableShareableLink` :1744 | `DisableShareableLinkData` | user: share dialog toggle (`mutations/profile/shareable_link/toggle.ts:14-15`) | earnings-account-misc.md | ./mutations/profile/shareable_link/toggle.ts:1 |
| PUT | `/api/profile/shared/{user_id}/enable` | `enableShareableLink` :1761 | `EnableShareableLinkData` | user: share dialog toggle (`mutations/profile/shareable_link/toggle.ts:14-15`) | earnings-account-misc.md | ./mutations/profile/shareable_link/toggle.ts:1 |
| POST | `/api/profile/shared/{user_id}/generate` | `generateShareableLink` :1778 | `GenerateShareableLinkData` | user: regenerate link (`mutations/profile/shareable_link/regenerate.ts:19`) | earnings-account-misc.md | ./mutations/profile/shareable_link/regenerate.ts:2 |
| GET | `/api/profile/{user_id}` | `getProfileDetails` :1795 | `GetProfileDetailsData` | web UI (see caller) | earnings-account-misc.md | ./queries/users/profile.ts:1 |
| PUT | `/api/profile/{user_id}` | `editUserProfile` :1812 | `EditUserProfileData` | web UI (see caller) | earnings-account-misc.md | ./mutations/account/editProfile.ts:2 |
| GET | `/api/profile/{user_id}/shared_link` | `getShareableLinkCode` :1833 | `GetShareableLinkCodeData` | share dialog open (`components/users/details/ProfileShareDialog.vue:127`) | earnings-account-misc.md | ./components/users/details/ProfileShareDialog.vue:103 |

### Projects (admin)

| Method | Path | SDK fn `client/sdk.gen.ts` | Req type | Trigger (canvasser build) | Owner | Status / caller evidence |
|---|---|---|---|---|---|---|
| GET | `/api/projects/` | `getProjectList` :1850 | `GetProjectListData` | projects list page (admin) + prefetch (`utils/prefetchOfflineData.ts:32`) | earnings-account-misc.md | ./queries/recruitment/promptEditorProjectSearch.ts:1 |
| POST | `/api/projects/` | `createProject` :1867 | `CreateProjectData` | projects list page (admin) + prefetch (`utils/prefetchOfflineData.ts:32`) | earnings-account-misc.md | ./mutations/project/create.ts:1 |
| GET | `/api/projects/voter_db_column_mapping/` | `getVoterDatabaseColumnsMapping` :1888 | `GetVoterDatabaseColumnsMappingData` | web UI (see caller) | earnings-account-misc.md | ./queries/project/edit/csvColumnMapping.ts:1 |
| GET | `/api/projects/{project_id}` | `getProjectDetails` :1905 | `GetProjectDetailsData` | project details page + prefetch (`utils/prefetchOfflineData.ts:41`) | earnings-account-misc.md | ./queries/project/details.ts:1 |
| GET | `/api/projects/{project_id}/ballot_template` | `getProjectBallotTemplate` :1922 | `GetProjectBallotTemplateData` | web UI (see caller) | earnings-account-misc.md | ./queries/project/edit/ballotTemplate.ts:1 |
| PATCH | `/api/projects/{project_id}/ballot_template` | `editProjectBallotTemplate` :1939 | `EditProjectBallotTemplateData` | web UI (see caller) | earnings-account-misc.md | ./mutations/project/edit/editBallotTemplate.ts:1 |
| PATCH | `/api/projects/{project_id}/ballot_template_pdf` | `editProjectBallotTemplatePdf` :1960 | `EditProjectBallotTemplatePdfData` | web UI (see caller) | earnings-account-misc.md | ./mutations/project/edit/uploadBallotTemplatePdf.ts:1 |
| GET | `/api/projects/{project_id}/canvassing-app-users` | `getProjectCanvassingAppUsers` :1981 | `GetProjectCanvassingAppUsersData` | web UI (see caller) | earnings-account-misc.md | ./components/project/edit/configuration/ProjectEditConfigurationFormCanvassing/CanvassingAppUsersModal.vue:257 |
| POST | `/api/projects/{project_id}/canvassing-app-users/import` | `startCanvassingAppUsersImport` :1998 | `StartCanvassingAppUsersImportData` | web UI (see caller) | earnings-account-misc.md | ./components/project/edit/configuration/ProjectEditConfigurationFormCanvassing/CanvassingAppUsersModal.vue:258 |
| GET | `/api/projects/{project_id}/canvassing-app-users/import/latest` | `getLatestCanvassingAppUsersImport` :2019 | `GetLatestCanvassingAppUsersImportData` | web UI (see caller) | earnings-account-misc.md | ./components/project/edit/configuration/ProjectEditConfigurationFormCanvassing/CanvassingAppUsersModal.vue:256 |
| GET | `/api/projects/{project_id}/canvassing-app-users/import/{import_id}` | `getCanvassingAppUsersImportStatus` :2036 | `GetCanvassingAppUsersImportStatusData` | — (never sent) | earnings-account-misc.md | DEAD — no caller in frontend |
| GET | `/api/projects/{project_id}/checklist` | `getProjectChecklist` :2053 | `GetProjectChecklistData` | — (never sent) | earnings-account-misc.md | DEAD — no caller in frontend |
| POST | `/api/projects/{project_id}/checklist` | `addChecklistItem` :2070 | `AddChecklistItemData` | web UI (see caller) | earnings-account-misc.md | ./mutations/project/checklist/applyTemplate.ts:1 |
| DELETE | `/api/projects/{project_id}/checklist/{item_id}` | `deleteChecklistItem` :2091 | `DeleteChecklistItemData` | web UI (see caller) | earnings-account-misc.md | ./mutations/project/checklist/remove.ts:1 |
| PATCH | `/api/projects/{project_id}/checklist/{item_id}` | `updateChecklistItem` :2108 | `UpdateChecklistItemData` | web UI (see caller) | earnings-account-misc.md | ./mutations/project/checklist/update.ts:2 |
| GET | `/api/projects/{project_id}/coaching_config` | `getCoachingConfigForProject` :2129 | `GetCoachingConfigForProjectData` | web UI (see caller) | earnings-account-misc.md | ./pages/projects/[id]/edit/coaching.vue:141 |
| PATCH | `/api/projects/{project_id}/coaching_config` | `editProjectCoachingConfig` :2146 | `EditProjectCoachingConfigData` | web UI (see caller) | earnings-account-misc.md | ./pages/projects/[id]/edit/coaching.vue:180 |
| GET | `/api/projects/{project_id}/daily_review` | `getProjectDailyReview` :2167 | `GetProjectDailyReviewData` | web UI (see caller) | earnings-account-misc.md | ./queries/project/dailyReview.ts:2 |
| GET | `/api/projects/{project_id}/daily_review/pending_dates` | `getProjectDailyReviewPendingDates` :2184 | `GetProjectDailyReviewPendingDatesData` | web UI (see caller) | earnings-account-misc.md | ./queries/project/dailyReview.ts:3 |
| GET | `/api/projects/{project_id}/dashboard/canvassing/activity` | `getCanvassingProjectActivityDashboard` :2201 | `GetCanvassingProjectActivityDashboardData` | web UI (see caller) | earnings-account-misc.md | ./components/project/dashboard/canvassing/CanvassingProjectActivityDashboard.vue:19 |
| GET | `/api/projects/{project_id}/dashboard/canvassing/overview` | `getCanvassingProjectOverviewDashboard` :2218 | `GetCanvassingProjectOverviewDashboardData` | web UI (see caller) | earnings-account-misc.md | ./components/project/dashboard/CanvassingProjectDashboard.vue:56 |
| GET | `/api/projects/{project_id}/dashboard/canvassing/responses` | `getCanvassingProjectResponsesDashboard` :2235 | `GetCanvassingProjectResponsesDashboardData` | web UI (see caller) | earnings-account-misc.md | ./components/project/dashboard/canvassing/CanvassingProjectResponsesDashboard.vue:19 |
| GET | `/api/projects/{project_id}/dashboard/canvassing/team` | `getCanvassingProjectTeamDashboard` :2252 | `GetCanvassingProjectTeamDashboardData` | web UI (see caller) | earnings-account-misc.md | ./components/project/dashboard/canvassing/CanvassingProjectTeamDashboard.vue:128 |
| GET | `/api/projects/{project_id}/dashboard/canvassing/team/{user_id}` | `getCanvassingProjectTeamMember` :2269 | `GetCanvassingProjectTeamMemberData` | web UI (see caller) | earnings-account-misc.md | ./components/project/dashboard/canvassing/CanvassingProjectTeamDashboard.vue:129 |
| POST | `/api/projects/{project_id}/dashboard/map/v2/{map_type}` | `getDashboardMap` :2286 | `GetDashboardMapData` | web UI (see caller) | earnings-account-misc.md | ./components/common/dashboard/charts-v2/map-v2/ProjectHexagonMapChartV2.vue:13 |
| POST | `/api/projects/{project_id}/dashboard/map/{question_hash}` | `getQuestionDashboardMap` :2308 | `GetQuestionDashboardMapData` | web UI (see caller) | earnings-account-misc.md | ./components/common/dashboard/charts/map/ProjectHexagonMapChart.vue:13 |
| GET | `/api/projects/{project_id}/dashboard/signature` | `getSignatureProjectDashboard` :2329 | `GetSignatureProjectDashboardData` | web UI (see caller) | earnings-account-misc.md | ./components/project/dashboard/SignatureProjectDashboard.vue:30 |
| GET | `/api/projects/{project_id}/edit/tabs_status` | `getProjectEditTabsStatus` :2346 | `GetProjectEditTabsStatusData` | web UI (see caller) | earnings-account-misc.md | ./pages/projects/[id].vue:30 |
| GET | `/api/projects/{project_id}/general_info` | `getProjectGeneralInformation` :2363 | `GetProjectGeneralInformationData` | web UI (see caller) | earnings-account-misc.md | ./queries/project/edit/generalInfo.ts:1 |
| PATCH | `/api/projects/{project_id}/general_info` | `editProjectGeneralInformation` :2380 | `EditProjectGeneralInformationData` | web UI (see caller) | earnings-account-misc.md | ./mutations/project/edit/generalInfo.ts:1 |
| GET | `/api/projects/{project_id}/kickoff_notes` | `getProjectKickoffNotes` :2401 | `GetProjectKickoffNotesData` | web UI (see caller) | earnings-account-misc.md | ./queries/project/kickoffNotes.ts:1 |
| PATCH | `/api/projects/{project_id}/kickoff_notes` | `patchProjectKickoffNotes` :2418 | `PatchProjectKickoffNotesData` | web UI (see caller) | earnings-account-misc.md | ./mutations/project/kickoff/patch.ts:2 |
| GET | `/api/projects/{project_id}/kpi_config` | `getKpiConfigForProject` :2439 | `GetKpiConfigForProjectData` | web UI (see caller) | earnings-account-misc.md | ./pages/projects/[id]/edit/kpi-rules.vue:58 |
| PATCH | `/api/projects/{project_id}/kpi_config` | `editProjectKpiConfig` :2456 | `EditProjectKpiConfigData` | web UI (see caller) | earnings-account-misc.md | ./pages/projects/[id]/edit/kpi-rules.vue:87 |
| DELETE | `/api/projects/{project_id}/note` | `deleteProjectNote` :2477 | `DeleteProjectNoteData` | web UI (see caller) | earnings-account-misc.md | ./mutations/project/notes/remove.ts:1 |
| GET | `/api/projects/{project_id}/note` | `getProjectNote` :2494 | `GetProjectNoteData` | — (never sent) | earnings-account-misc.md | DEAD — no caller in frontend |
| POST | `/api/projects/{project_id}/note` | `upsertProjectNote` :2511 | `UpsertProjectNoteData` | web UI (see caller) | earnings-account-misc.md | ./mutations/project/notes/upsert.ts:1 |
| GET | `/api/projects/{project_id}/project_config` | `getProjectConfig` :2532 | `GetProjectConfigData` | web UI (see caller) | earnings-account-misc.md | ./queries/project/edit/configuration.ts:1 |
| PATCH | `/api/projects/{project_id}/project_config` | `editProjectConfig` :2549 | `EditProjectConfigData` | web UI (see caller) | earnings-account-misc.md | ./mutations/project/edit/configuration.ts:1 |
| GET | `/api/projects/{project_id}/public_link/` | `getProjectPublicLink` :2571 | `GetProjectPublicLinkData` | — (never sent) | earnings-account-misc.md | DEAD — no caller in frontend |
| PATCH | `/api/projects/{project_id}/public_link/` | `togglePublicSharing` :2589 | `TogglePublicSharingData` | — (never sent) | earnings-account-misc.md | DEAD — no caller in frontend |
| GET | `/api/projects/{project_id}/recruitment/eligible_contacts` | `getEligibleContactsForProjectRecruitment` :2610 | `GetEligibleContactsForProjectRecruitmentData` | web UI (see caller) | earnings-account-misc.md | ./queries/recruitment/projectEligibleContacts.ts:1 |
| POST | `/api/projects/{project_id}/recruitment/send_batch` | `sendBatchProjectScopedRecruitmentMessages` :2627 | `SendBatchProjectScopedRecruitmentMessagesData` | web UI (see caller) | earnings-account-misc.md | ./mutations/recruitment/projectSendBatch.ts:2 |
| POST | `/api/projects/{project_id}/restricted_areas` | `getRestrictedAreasForAudioRecording` :2648 | `GetRestrictedAreasForAudioRecordingData` | shift audio-restriction zones: fetch on start + every 10 km moved; 50 km radius (sensors-telemetry.md §11) | sensors-telemetry.md | LIVE via mobile wrapper/native upload (not the SDK fn) |
| GET | `/api/projects/{project_id}/short_info` | `getProjectShortInfo` :2669 | `GetProjectShortInfoData` | many pages + prefetch (`utils/prefetchOfflineData.ts:40`) | earnings-account-misc.md | ./utils/prefetchOfflineData.ts:8 |
| GET | `/api/projects/{project_id}/tabs_status` | `getProjectTabsStatus` :2686 | `GetProjectTabsStatusData` | web UI (see caller) | earnings-account-misc.md | ./pages/projects/[id].vue:30 |
| POST | `/api/projects/{project_id}/users/canvassers` | `getProjectCanvasserList` :2703 | `GetProjectCanvasserListData` | web UI (see caller) | earnings-account-misc.md | ./pages/projects/[id]/assignments.vue:148 |
| GET | `/api/projects/{project_id}/voter_database` | `getProjectVoterDatabaseConfiguration` :2724 | `GetProjectVoterDatabaseConfigurationData` | web UI (see caller) | earnings-account-misc.md | ./queries/project/edit/voterDatabase.ts:1 |
| PATCH | `/api/projects/{project_id}/voter_database` | `editProjectVoterDatabase` :2741 | `EditProjectVoterDatabaseData` | web UI (see caller) | earnings-account-misc.md | ./mutations/project/edit/uploadVoterDatabase.ts:1 |
| GET | `/api/projects/{project_id}/zip_list` | `getListOfZipCodes` :2762 | `GetListOfZipCodesData` | web UI (see caller) | earnings-account-misc.md | ./components/project/edit/configuration/ProjectEditConfigurationFormCanvassing/SectionVoice.vue:68 |
| GET | `/api/projects/{project_id}/{link_type}/public_link/` | `getProjectPublicLinkV2` :2779 | `GetProjectPublicLinkV2Data` | web UI (see caller) | earnings-account-misc.md | ./components/common/PublicLinkDialog.vue:70 |
| PATCH | `/api/projects/{project_id}/{link_type}/public_link/` | `togglePublicSharingV2` :2796 | `TogglePublicSharingV2Data` | web UI (see caller) | earnings-account-misc.md | ./mutations/project/public_link/toggle.ts:1 |

### Public / share / redirect

| Method | Path | SDK fn `client/sdk.gen.ts` | Req type | Trigger (canvasser build) | Owner | Status / caller evidence |
|---|---|---|---|---|---|---|
| GET | `/api/public/projects/dashboard/{public_hash}/` | `getProjectPublicDashboard` :2817 | `GetProjectPublicDashboardData` | web UI (see caller) | earnings-account-misc.md | ./pages/share/project/dashboard/[hash]/index.vue:73 |
| GET | `/api/public/projects/dashboard/{public_hash}/canvassing/activity` | `getPublicCanvassingProjectActivityDashboard` :2828 | `GetPublicCanvassingProjectActivityDashboardData` | web UI (see caller) | earnings-account-misc.md | ./components/project/dashboard/canvassing/CanvassingProjectActivityDashboard.vue:19 |
| GET | `/api/public/projects/dashboard/{public_hash}/canvassing/overview` | `getPublicCanvassingProjectOverviewDashboard` :2839 | `GetPublicCanvassingProjectOverviewDashboardData` | web UI (see caller) | earnings-account-misc.md | ./components/project/dashboard/canvassing/CanvassingProjectOverviewDashboard.vue:18 |
| GET | `/api/public/projects/dashboard/{public_hash}/canvassing/responses` | `getPublicCanvassingProjectResponsesDashboard` :2850 | `GetPublicCanvassingProjectResponsesDashboardData` | web UI (see caller) | earnings-account-misc.md | ./components/project/dashboard/canvassing/CanvassingProjectResponsesDashboard.vue:19 |
| GET | `/api/public/projects/dashboard/{public_hash}/canvassing/team` | `getPublicCanvassingProjectTeamDashboard` :2861 | `GetPublicCanvassingProjectTeamDashboardData` | web UI (see caller) | earnings-account-misc.md | ./components/project/dashboard/canvassing/CanvassingProjectTeamDashboard.vue:130 |
| GET | `/api/public/projects/dashboard/{public_hash}/canvassing/team/{user_id}` | `getPublicCanvassingProjectTeamMember` :2872 | `GetPublicCanvassingProjectTeamMemberData` | web UI (see caller) | earnings-account-misc.md | ./components/project/dashboard/canvassing/CanvassingProjectTeamDashboard.vue:131 |
| POST | `/api/public/projects/dashboard/{public_hash}/map/v2/{map_type}` | `getPublicDashboardMap` :2883 | `GetPublicDashboardMapData` | web UI (see caller) | earnings-account-misc.md | ./components/common/dashboard/charts-v2/map-v2/PublicProjectHexagonMapChartV2.vue:13 |
| POST | `/api/public/projects/dashboard/{public_hash}/map/{question_hash}` | `getPublicQuestionDashboardMap` :2898 | `GetPublicQuestionDashboardMapData` | web UI (see caller) | earnings-account-misc.md | ./components/common/dashboard/charts/map/PublicProjectHexagonMapChart.vue:13 |
| GET | `/api/public/projects/dashboard/{public_hash}/metadata` | `getProjectPublicDashboardMetadata` :2912 | `GetProjectPublicDashboardMetadataData` | web UI (see caller) | earnings-account-misc.md | ./queries/project/publicDashboardMetadata.ts:1 |
| GET | `/api/public/projects/details/{public_hash}` | `getPublicProjectDetails` :2923 | `GetPublicProjectDetailsData` | public share page (`pages/share/project/[hash].vue:66`) | earnings-account-misc.md | ./pages/share/project/[hash].vue:46 |
| GET | `/api/public/sms_redirect/{code}` | `resolveSmsShortLink` :2934 | `ResolveSmsShortLinkData` | SMS short-link page (`pages/r/[code].vue:26`) | earnings-account-misc.md | ./pages/r/[code].vue:6 |
| GET | `/api/public/subcontractor_company/details/{sign_up_code}` | `getSubcontractorCompanyPublicInfoBySignUpCode` :2945 | `GetSubcontractorCompanyPublicInfoBySignUpCodeData` | company sign-up page (`pages/sign-up/company/[code].vue:223`) | earnings-account-misc.md | ./pages/sign-up/company/[code].vue:195 |
| GET | `/api/public/upcoming_projects/{project_public_link_hash}` | `getPublicUpcomingProjectDetails` :2957 | `GetPublicUpcomingProjectDetailsData` | — (never sent) | earnings-account-misc.md | DEAD — no caller in frontend |

### Conversations & coaching

| Method | Path | SDK fn `client/sdk.gen.ts` | Req type | Trigger (canvasser build) | Owner | Status / caller evidence |
|---|---|---|---|---|---|---|
| GET | `/api/coaching_feedback/` | `getCoachingFeedbackList` :697 | `GetCoachingFeedbackListData` | web UI (see caller) | earnings-account-misc.md | ./pages/coaching-feedbacks/index.vue:90 |
| GET | `/api/coaching_feedback/{feedback_id}` | `getCoachingFeedbackDetails` :714 | `GetCoachingFeedbackDetailsData` | web UI (see caller) | earnings-account-misc.md | ./pages/workshifts/[id].vue:210 |
| GET | `/api/coaching_feedback/{feedback_id}/short_info` | `getCoachingFeedbackShortInfo` :731 | `GetCoachingFeedbackShortInfoData` | entity label (`components/common/labeled-entity/LabeledEntityCoachingFeedback.vue:40`) | earnings-account-misc.md | ./components/common/labeled-entity/LabeledEntityCoachingFeedback.vue:28 |
| GET | `/api/conversations/` | `getConversationList` :898 | `GetConversationListData` | web UI (see caller) | earnings-account-misc.md | ./pages/conversations/index.vue:89 |
| GET | `/api/conversations/{conversation_id}` | `getConversationDetails` :915 | `GetConversationDetailsData` | web UI (see caller) | earnings-account-misc.md | ./pages/conversations/[id].vue:18 |

### Docs (in-app help)

| Method | Path | SDK fn `client/sdk.gen.ts` | Req type | Trigger (canvasser build) | Owner | Status / caller evidence |
|---|---|---|---|---|---|---|
| GET | `/api/docs/` | `getDocsList` :932 | `GetDocsListData` | docs page + nav (`pages/docs/index.vue:28`) | earnings-account-misc.md | ./pages/docs/index.vue:18 |
| GET | `/api/docs/{doc_path}` | `getDocPage` :949 | `GetDocPageData` | doc page mount (`pages/docs/[...slug].vue:51`) | earnings-account-misc.md | ./pages/docs/[...slug].vue:32 |

### Canvassing-interaction imports

| Method | Path | SDK fn `client/sdk.gen.ts` | Req type | Trigger (canvasser build) | Owner | Status / caller evidence |
|---|---|---|---|---|---|---|
| GET | `/api/canvassing-interaction-imports/` | `listCanvassingInteractionImports` :643 | `ListCanvassingInteractionImportsData` | web UI (see caller) | earnings-account-misc.md | ./pages/canvassing-interaction-imports/index.vue:27 |
| POST | `/api/canvassing-interaction-imports/upload` | `uploadCanvassingInteractionCsv` :660 | `UploadCanvassingInteractionCsvData` | web UI (see caller) | earnings-account-misc.md | ./components/canvassing-interaction-imports/UploadModal.vue:61 |
| GET | `/api/canvassing-interaction-imports/{import_id}` | `getCanvassingInteractionImportDetails` :680 | `GetCanvassingInteractionImportDetailsData` | web UI (see caller) | earnings-account-misc.md | ./pages/canvassing-interaction-imports/[importId].vue:25 |

### Recruitment

| Method | Path | SDK fn `client/sdk.gen.ts` | Req type | Trigger (canvasser build) | Owner | Status / caller evidence |
|---|---|---|---|---|---|---|
| GET | `/api/recruitment/campaigns/` | `getCampaignList` :2968 | `GetCampaignListData` | web UI (see caller) | earnings-account-misc.md | ./pages/recruitment/campaigns/index.vue:74 |
| POST | `/api/recruitment/campaigns/` | `createCampaign` :2985 | `CreateCampaignData` | web UI (see caller) | earnings-account-misc.md | ./pages/recruitment/campaigns/create/index.vue:55 |
| GET | `/api/recruitment/campaigns/by_project/{project_id}` | `getRecruitmentCampaignByProjectId` :3006 | `GetRecruitmentCampaignByProjectIdData` | web UI (see caller) | earnings-account-misc.md | ./pages/projects/[id]/recruitment.vue:224 |
| GET | `/api/recruitment/campaigns/{campaign_id}` | `getCampaignDetails` :3023 | `GetCampaignDetailsData` | web UI (see caller) | earnings-account-misc.md | ./pages/recruitment/campaigns/[id].vue:65 |
| PATCH | `/api/recruitment/campaigns/{campaign_id}` | `updateCampaign` :3040 | `UpdateCampaignData` | web UI (see caller) | earnings-account-misc.md | ./pages/recruitment/campaigns/[id]/edit.vue:25 |
| PATCH | `/api/recruitment/campaigns/{campaign_id}/pause` | `pauseCampaign` :3061 | `PauseCampaignData` | web UI (see caller) | earnings-account-misc.md | ./pages/recruitment/campaigns/[id].vue:67 |
| PATCH | `/api/recruitment/campaigns/{campaign_id}/resume` | `resumeCampaign` :3078 | `ResumeCampaignData` | web UI (see caller) | earnings-account-misc.md | ./pages/recruitment/campaigns/[id].vue:68 |
| GET | `/api/recruitment/campaigns/{campaign_id}/stats` | `getCampaignStats` :3095 | `GetCampaignStatsData` | web UI (see caller) | earnings-account-misc.md | ./pages/recruitment/campaigns/[id]/stats.vue:21 |
| GET | `/api/recruitment/messages/` | `getRecruitmentMessageList` :3112 | `GetRecruitmentMessageListData` | web UI (see caller) | earnings-account-misc.md | ./pages/recruitment/messages/index.vue:89 |
| POST | `/api/recruitment/messages/send_batch` | `sendBatchRecruitmentMessages` :3129 | `SendBatchRecruitmentMessagesData` | web UI (see caller) | earnings-account-misc.md | ./mutations/recruitment/messages/sendBatch.ts:2 |
| GET | `/api/recruitment/messages/{message_id}` | `getRecruitmentMessageDetails` :3150 | `GetRecruitmentMessageDetailsData` | web UI (see caller) | earnings-account-misc.md | ./pages/recruitment/messages/[id].vue:183 |
| GET | `/api/recruitment/settings/prompt/editor-metadata` | `getEditorMetadata` :3167 | `GetEditorMetadataData` | web UI (see caller) | earnings-account-misc.md | ./pages/system/settings/recruitment/prompt.vue:540 |
| POST | `/api/recruitment/settings/prompt/preview/build-context` | `buildContextPreview` :3184 | `BuildContextPreviewData` | web UI (see caller) | earnings-account-misc.md | ./pages/system/settings/recruitment/prompt.vue:574 |
| POST | `/api/recruitment/settings/prompt/preview/generate` | `generatePreview` :3205 | `GeneratePreviewData` | web UI (see caller) | earnings-account-misc.md | ./composables/recruitment/usePromptPreview.ts:3 |
| POST | `/api/recruitment/settings/prompt/preview/render` | `renderPromptPreview` :3226 | `RenderPromptPreviewData` | web UI (see caller) | earnings-account-misc.md | ./composables/recruitment/usePromptPreview.ts:3 |

### Reports

| Method | Path | SDK fn `client/sdk.gen.ts` | Req type | Trigger (canvasser build) | Owner | Status / caller evidence |
|---|---|---|---|---|---|---|
| GET | `/api/reports/` | `getReportList` :3247 | `GetReportListData` | web UI (see caller) | earnings-account-misc.md | ./pages/reports/index.vue:88 |
| GET | `/api/reports/{report_id}` | `getReportDetails` :3264 | `GetReportDetailsData` | web UI (see caller) | earnings-account-misc.md | ./pages/reports/[id].vue:152 |
| PATCH | `/api/reports/{report_id}/confirm` | `confirmReport` :3281 | `ConfirmReportData` | web UI (see caller) | earnings-account-misc.md | ./mutations/reports/confirm.ts:1 |
| PATCH | `/api/reports/{report_id}/discard` | `discardReport` :3298 | `DiscardReportData` | web UI (see caller) | earnings-account-misc.md | ./mutations/reports/discard.ts:1 |
| GET | `/api/reports/{report_id}/view_data` | `getCanvassingFraudReportViewData` :3315 | `GetCanvassingFraudReportViewDataData` | web UI (see caller) | earnings-account-misc.md | ./queries/reports/viewData.ts:1 |

### Selectors

| Method | Path | SDK fn `client/sdk.gen.ts` | Req type | Trigger (canvasser build) | Owner | Status / caller evidence |
|---|---|---|---|---|---|---|
| GET | `/api/selector/canvassing/apps` | `getCanvassingAppList` :3332 | `GetCanvassingAppListData` | web UI (see caller) | earnings-account-misc.md | ./queries/selectors/canvassingApps.ts:1 |
| GET | `/api/selector/canvassing/canvassers` | `getCanvassingAppCanvassersList` :3349 | `GetCanvassingAppCanvassersListData` | web UI (see caller) | earnings-account-misc.md | ./components/assignments/AssignmentInfoForm.vue:127 |
| POST | `/api/selector/canvassing/canvassers` | `createCanvassingAppCanvasser` :3366 | `CreateCanvassingAppCanvasserData` | web UI (see caller) | earnings-account-misc.md | ./mutations/assignments/createCanvassingAppCanvasser.ts:1 |
| GET | `/api/selector/canvassing/prefixes` | `getSelectorI360PrefixList` :3387 | `GetSelectorI360PrefixListData` | web UI (see caller) | earnings-account-misc.md | ./queries/selectors/canvassingPrefixes.ts:2 |
| GET | `/api/selector/canvassing/surveys` | `getSelectorSurveyList` :3404 | `GetSelectorSurveyListData` | web UI (see caller) | earnings-account-misc.md | ./components/project/edit/configuration/ProjectEditConfigurationFormCanvassing/SectionApp.vue:218 |
| POST | `/api/selector/canvassing/surveys` | `createSelectorSurvey` :3421 | `CreateSelectorSurveyData` | web UI (see caller) | earnings-account-misc.md | ./mutations/project/createCanvassingAppProject.ts:1 |
| GET | `/api/selector/client` | `getSelectorClientList` :3442 | `GetSelectorClientListData` | web UI (see caller) | earnings-account-misc.md | ./queries/selectors/clients.ts:1 |
| GET | `/api/selector/contract_adjustment/templates` | `getContractTemplates` :3459 | `GetContractTemplatesData` | web UI (see caller) | earnings-account-misc.md | ./queries/selectors/contractTemplates.ts:1 |
| GET | `/api/selector/fips/counties` | `getSelectorFipsCounties` :3476 | `GetSelectorFipsCountiesData` | web UI (see caller) | earnings-account-misc.md | ./queries/selectors/fipsCounties.ts:1 |
| GET | `/api/selector/project` | `getSelectorProjectList` :3493 | `GetSelectorProjectListData` | canvasser: shift-start project selector + project recovery (`queries/selectors/projects.ts:11`; `mutations/mobile/findSelectorProjectByIdViaList.ts`) | earnings-account-misc.md | ./queries/selectors/projects.ts:1 |
| GET | `/api/selector/recruitment/campaigns` | `getSelectorRecruitmentCampaigns` :3510 | `GetSelectorRecruitmentCampaignsData` | web UI (see caller) | earnings-account-misc.md | ./pages/recruitment/messages/index.vue:90 |
| GET | `/api/selector/staffing_contacts/additional_languages` | `getSelectorStaffingContactAdditionalLanguages` :3527 | `GetSelectorStaffingContactAdditionalLanguagesData` | web UI (see caller) | earnings-account-misc.md | ./components/staffing-contacts/list/StaffingContactsListFilters.vue:196 |
| GET | `/api/selector/staffing_contacts/cities` | `getSelectorStaffingContactCities` :3544 | `GetSelectorStaffingContactCitiesData` | web UI (see caller) | earnings-account-misc.md | ./components/staffing-contacts/list/StaffingContactsListFilters.vue:193 |
| GET | `/api/selector/staffing_contacts/grades` | `getSelectorStaffingContactGrades` :3561 | `GetSelectorStaffingContactGradesData` | web UI (see caller) | earnings-account-misc.md | ./components/staffing-contacts/list/StaffingContactsListFilters.vue:198 |
| GET | `/api/selector/staffing_contacts/leaderships` | `getSelectorStaffingContactLeaderships` :3578 | `GetSelectorStaffingContactLeadershipsData` | web UI (see caller) | earnings-account-misc.md | ./components/staffing-contacts/list/StaffingContactsListFilters.vue:199 |
| GET | `/api/selector/staffing_contacts/levels` | `getSelectorStaffingContactLevels` :3595 | `GetSelectorStaffingContactLevelsData` | web UI (see caller) | earnings-account-misc.md | ./components/staffing-contacts/list/StaffingContactsListFilters.vue:200 |
| GET | `/api/selector/staffing_contacts/military_statuses` | `getSelectorStaffingContactMilitaryStatuses` :3612 | `GetSelectorStaffingContactMilitaryStatusesData` | web UI (see caller) | earnings-account-misc.md | ./components/staffing-contacts/list/StaffingContactsListFilters.vue:195 |
| GET | `/api/selector/staffing_contacts/projects` | `getSelectorStaffingContactProjects` :3629 | `GetSelectorStaffingContactProjectsData` | web UI (see caller) | earnings-account-misc.md | ./components/staffing-contacts/list/StaffingContactsListFilters.vue:191 |
| GET | `/api/selector/staffing_contacts/relationships` | `getSelectorStaffingContactRelationships` :3646 | `GetSelectorStaffingContactRelationshipsData` | web UI (see caller) | earnings-account-misc.md | ./components/staffing-contacts/list/StaffingContactsListFilters.vue:197 |
| GET | `/api/selector/staffing_contacts/remotes` | `getSelectorStaffingContactRemotes` :3663 | `GetSelectorStaffingContactRemotesData` | web UI (see caller) | earnings-account-misc.md | ./components/staffing-contacts/list/StaffingContactsListFilters.vue:194 |
| GET | `/api/selector/staffing_contacts/states` | `getSelectorStaffingContactStates` :3680 | `GetSelectorStaffingContactStatesData` | web UI (see caller) | earnings-account-misc.md | ./components/staffing-contacts/list/StaffingContactsListFilters.vue:192 |
| GET | `/api/selector/subcontractor_company` | `getSelectorSubcontractorCompanyList` :3697 | `GetSelectorSubcontractorCompanyListData` | web UI (see caller) | earnings-account-misc.md | ./components/common/filters/FilterBySubcontractorCompany.vue:39 |
| GET | `/api/selector/timezone` | `getSelectorTimezoneList` :3714 | `GetSelectorTimezoneListData` | web UI (see caller) | earnings-account-misc.md | ./queries/selectors/timezones.ts:1 |
| GET | `/api/selector/users` | `getSelectorUserList` :3731 | `GetSelectorUserListData` | web UI (see caller) | earnings-account-misc.md | ./pages/earnings/create.vue:22 |
| GET | `/api/selector/{project_id}/regions` | `getSelectorProjectRegions` :3748 | `GetSelectorProjectRegionsData` | web UI (see caller) | earnings-account-misc.md | ./components/common/filters/FilterByProjectRegion.vue:34 |

### Staffing contacts

| Method | Path | SDK fn `client/sdk.gen.ts` | Req type | Trigger (canvasser build) | Owner | Status / caller evidence |
|---|---|---|---|---|---|---|
| GET | `/api/staffing_contacts/` | `getStaffingContactList` :3855 | `GetStaffingContactListData` | web UI (see caller) | earnings-account-misc.md | ./queries/recruitment/promptEditorContactSearch.ts:1 |
| POST | `/api/staffing_contacts/refer` | `referContact` :3872 | `ReferContactData` | web UI (see caller) | earnings-account-misc.md | ./components/common/ReferralForm.vue:70 |
| POST | `/api/staffing_contacts/reset_counters_batch` | `batchResetStaffingContactCounters` :3893 | `BatchResetStaffingContactCountersData` | web UI (see caller) | earnings-account-misc.md | ./mutations/staffing-contacts/resetCountersBatch.ts:1 |
| PATCH | `/api/staffing_contacts/upload_file` | `uploadStaffingContactFile` :3914 | `UploadStaffingContactFileData` | web UI (see caller) | earnings-account-misc.md | ./pages/staffing-resources/import/index.vue:20 |
| GET | `/api/staffing_contacts/{email}` | `getStaffingContactDetails` :3935 | `GetStaffingContactDetailsData` | web UI (see caller) | earnings-account-misc.md | ./pages/staffing-resources/[email].vue:61 |
| POST | `/api/staffing_contacts/{email}/clear_sms_suppression` | `clearStaffingContactSmsSuppression` :3952 | `ClearStaffingContactSmsSuppressionData` | web UI (see caller) | earnings-account-misc.md | ./mutations/staffing-contacts/clearSmsSuppression.ts:1 |
| POST | `/api/staffing_contacts/{email}/clear_suppression` | `clearStaffingContactSuppression` :3969 | `ClearStaffingContactSuppressionData` | web UI (see caller) | earnings-account-misc.md | ./mutations/staffing-contacts/clearSuppression.ts:1 |
| GET | `/api/staffing_contacts/{email}/interactions` | `getStaffingContactInteractionList` :3986 | `GetStaffingContactInteractionListData` | web UI (see caller) | earnings-account-misc.md | ./pages/staffing-resources/[email].vue:62 |
| PUT | `/api/staffing_contacts/{email}/note/` | `editStaffingContactNote` :4003 | `EditStaffingContactNoteData` | web UI (see caller) | earnings-account-misc.md | ./mutations/staffing-contacts/notes/edit.ts:2 |
| DELETE | `/api/staffing_contacts/{email}/note/remove` | `removeStaffingContactNote` :4024 | `RemoveStaffingContactNoteData` | web UI (see caller) | earnings-account-misc.md | ./mutations/staffing-contacts/notes/remove.ts:1 |
| POST | `/api/staffing_contacts/{email}/reset_counters` | `resetStaffingContactCounters` :4041 | `ResetStaffingContactCountersData` | web UI (see caller) | earnings-account-misc.md | ./mutations/staffing-contacts/resetCounters.ts:1 |
| POST | `/api/staffing_contacts/{email}/resume_recruitment` | `resumeStaffingContactRecruitment` :4062 | `ResumeStaffingContactRecruitmentData` | web UI (see caller) | earnings-account-misc.md | ./mutations/staffing-contacts/resumeRecruitment.ts:1 |
| POST | `/api/staffing_contacts/{email}/set_email_unsubscribe` | `setStaffingContactEmailUnsubscribe` :4079 | `SetStaffingContactEmailUnsubscribeData` | web UI (see caller) | earnings-account-misc.md | ./mutations/staffing-contacts/setEmailUnsubscribe.ts:1 |
| POST | `/api/staffing_contacts/{email}/set_sms_suppression` | `setStaffingContactSmsSuppression` :4096 | `SetStaffingContactSmsSuppressionData` | web UI (see caller) | earnings-account-misc.md | ./mutations/staffing-contacts/setSmsSuppression.ts:1 |
| POST | `/api/staffing_contacts/{email}/stop_recruitment` | `stopStaffingContactRecruitment` :4113 | `StopStaffingContactRecruitmentData` | web UI (see caller) | earnings-account-misc.md | ./mutations/staffing-contacts/stopRecruitment.ts:1 |
| GET | `/api/staffing_contacts/{file_import_id}/check_file_import_status` | `getLastStaffingContactFileProcessingStatus` :4130 | `GetLastStaffingContactFileProcessingStatusData` | web UI (see caller) | earnings-account-misc.md | ./pages/staffing-resources/import/[id].vue:181 |

### Subcontractor companies

| Method | Path | SDK fn `client/sdk.gen.ts` | Req type | Trigger (canvasser build) | Owner | Status / caller evidence |
|---|---|---|---|---|---|---|
| GET | `/api/subcontractor_company/` | `getSubcontractorCompanyList` :4147 | `GetSubcontractorCompanyListData` | web UI (see caller) | earnings-account-misc.md | ./pages/subcontractor-companies/index.vue:67 |
| POST | `/api/subcontractor_company/` | `createSubcontractorCompany` :4164 | `CreateSubcontractorCompanyData` | web UI (see caller) | earnings-account-misc.md | ./pages/subcontractor-companies/create.vue:30 |
| GET | `/api/subcontractor_company/{subcontractor_company_id}` | `getSubcontractorCompanyDetails` :4185 | `GetSubcontractorCompanyDetailsData` | web UI (see caller) | earnings-account-misc.md | ./pages/subcontractor-companies/[id].vue:29 |
| GET | `/api/subcontractor_company/{subcontractor_company_id}/edit` | `getSubcontractorCompanyEditableFields` :4202 | `GetSubcontractorCompanyEditableFieldsData` | web UI (see caller) | earnings-account-misc.md | ./pages/subcontractor-companies/[id]/edit.vue:20 |
| PATCH | `/api/subcontractor_company/{subcontractor_company_id}/edit` | `updateSubcontractorCompany` :4219 | `UpdateSubcontractorCompanyData` | web UI (see caller) | earnings-account-misc.md | ./pages/subcontractor-companies/[id]/edit.vue:50 |
| DELETE | `/api/subcontractor_company/{subcontractor_company_id}/note` | `deleteSubcontractorCompanyNote` :4240 | `DeleteSubcontractorCompanyNoteData` | web UI (see caller) | earnings-account-misc.md | ./mutations/subcontractor-company/notes/remove.ts:2 |
| POST | `/api/subcontractor_company/{subcontractor_company_id}/note` | `upsertSubcontractorCompanyNote` :4257 | `UpsertSubcontractorCompanyNoteData` | web UI (see caller) | earnings-account-misc.md | ./mutations/subcontractor-company/notes/upsert.ts:2 |
| GET | `/api/subcontractor_company/{subcontractor_company_id}/short_info` | `getSubcontractorCompanyShortInfo` :4278 | `GetSubcontractorCompanyShortInfoData` | entity label (`components/common/labeled-entity/LabeledEntitySubcontractorCompany.vue:24`) | earnings-account-misc.md | ./components/common/labeled-entity/LabeledEntitySubcontractorCompany.vue:14 |
| POST | `/api/subcontractor_company/{subcontractor_company_id}/sign_up_code/regenerate` | `regenerateSubcontractorCompanySignUpCode` :4295 | `RegenerateSubcontractorCompanySignUpCodeData` | web UI (see caller) | earnings-account-misc.md | ./mutations/subcontractor-company/signUpCode/regenerate.ts:2 |
| PATCH | `/api/subcontractor_company/{subcontractor_company_id}/sign_up_url_enabled` | `toggleSubcontractorCompanySignUpUrl` :4312 | `ToggleSubcontractorCompanySignUpUrlData` | web UI (see caller) | earnings-account-misc.md | ./mutations/subcontractor-company/signUpUrl/toggle.ts:2 |
| PATCH | `/api/subcontractor_company/{subcontractor_company_id}/status` | `changeSubcontractorCompanyStatus` :4333 | `ChangeSubcontractorCompanyStatusData` | web UI (see caller) | earnings-account-misc.md | ./mutations/subcontractor-company/status/change.ts:2 |
| GET | `/api/subcontractor_company/{subcontractor_company_id}/subcanvassers/` | `getSubcontractorCompanySubcanvasserList` :4354 | `GetSubcontractorCompanySubcanvasserListData` | web UI (see caller) | earnings-account-misc.md | ./pages/subcontractor-companies/[id]/subcanvassers.vue:55 |

### System & system settings

| Method | Path | SDK fn `client/sdk.gen.ts` | Req type | Trigger (canvasser build) | Owner | Status / caller evidence |
|---|---|---|---|---|---|---|
| GET | `/api/system/dashboard/{tab}` | `systemDashboard` :4371 | `SystemDashboardData` | web UI (see caller) | earnings-account-misc.md | ./composables/useSystemDashboard.ts:7 |
| GET | `/api/system_settings/` | `getAllSystemSettings` :4388 | `GetAllSystemSettingsData` | web UI (see caller) | earnings-account-misc.md | ./pages/system/settings/recruitment.vue:12 |
| PUT | `/api/system_settings/general_recruitment` | `updateGeneralRecruitmentSettings` :4405 | `UpdateGeneralRecruitmentSettingsData` | web UI (see caller) | earnings-account-misc.md | ./mutations/system/updateSettingsGeneral.ts:1 |
| PUT | `/api/system_settings/project_recruitment` | `updateProjectRecruitmentSettings` :4426 | `UpdateProjectRecruitmentSettingsData` | web UI (see caller) | earnings-account-misc.md | ./mutations/system/updateSettingsProjectRecruitment.ts:1 |
| PUT | `/api/system_settings/prompt` | `updatePromptSettings` :4447 | `UpdatePromptSettingsData` | web UI (see caller) | earnings-account-misc.md | ./mutations/system/updateSettingsPrompt.ts:1 |
| PUT | `/api/system_settings/recruitment_analytics` | `updateRecruitmentAnalyticsSettings` :4468 | `UpdateRecruitmentAnalyticsSettingsData` | web UI (see caller) | earnings-account-misc.md | ./mutations/system/updateSettingsAnalytics.ts:1 |
| PUT | `/api/system_settings/throttling` | `updateThrottlingSettings` :4489 | `UpdateThrottlingSettingsData` | web UI (see caller) | earnings-account-misc.md | ./mutations/system/updateSettingsThrottling.ts:1 |
| PUT | `/api/system_settings/urgency_presets` | `updateUrgencyPresetsSettings` :4510 | `UpdateUrgencyPresetsSettingsData` | web UI (see caller) | earnings-account-misc.md | ./mutations/system/updateSettingsUrgency.ts:1 |

### Users (admin)

| Method | Path | SDK fn `client/sdk.gen.ts` | Req type | Trigger (canvasser build) | Owner | Status / caller evidence |
|---|---|---|---|---|---|---|
| POST | `/api/users/` | `getUserList` :4553 | `GetUserListData` | web UI (see caller) | earnings-account-misc.md | ./queries/recruitment/promptEditorReferrerSearch.ts:1 |
| POST | `/api/users/export/` | `createExportUsersJob` :4574 | `CreateExportUsersJobData` | web UI (see caller) | earnings-account-misc.md | ./mutations/users/exportUsersList.ts:1 |
| GET | `/api/users/export/{export_job_id}` | `getExportUsersJob` :4595 | `GetExportUsersJobData` | — (never sent) | earnings-account-misc.md | DEAD — no caller in frontend |
| POST | `/api/users/hiring/checkmark` | `editUserHiringCheckmark` :4612 | `EditUserHiringCheckmarkData` | web UI (see caller) | earnings-account-misc.md | ./mutations/users/hiring/edit.ts:2 |
| POST | `/api/users/hiring/dashboard` | `getUsersHiringDashboard` :4633 | `GetUsersHiringDashboardData` | web UI (see caller) | earnings-account-misc.md | ./queries/users/hiring-dashboard.ts:1 |
| GET | `/api/users/{user_id}` | `getUserDetails` :4654 | `GetUserDetailsData` | web UI (see caller) | earnings-account-misc.md | ./pages/users/[id].vue:22 |
| PUT | `/api/users/{user_id}` | `updateUserField` :4671 | `UpdateUserFieldData` | web UI (see caller) | earnings-account-misc.md | ./mutations/users/updateUser.ts:1 |
| PATCH | `/api/users/{user_id}/block` | `blockUser` :4692 | `BlockUserData` | web UI (see caller) | earnings-account-misc.md | ./mutations/users/blockUser.ts:1 |
| DELETE | `/api/users/{user_id}/canvasser_application/{section}/` | `resetCanvasserApplicationSection` :4709 | `ResetCanvasserApplicationSectionData` | web UI (see caller) | earnings-account-misc.md | ./mutations/users/removeCanvasserInfo.ts:1 |
| POST | `/api/users/{user_id}/checkr/request` | `requestCheckrBackgroundCheck` :4726 | `RequestCheckrBackgroundCheckData` | web UI (see caller) | earnings-account-misc.md | ./mutations/users/requestCheckrBackgroundCheck.ts:1 |
| GET | `/api/users/{user_id}/dashboard/` | `getCanvasserDashboard` :4743 | `GetCanvasserDashboardData` | web UI (see caller) | earnings-account-misc.md | ./pages/users/[id]/dashboard.vue:33 |
| GET | `/api/users/{user_id}/devices/` | `getUserDevices` :4760 | `GetUserDevicesData` | — (never sent) | earnings-account-misc.md | DEAD — no caller in frontend |
| PUT | `/api/users/{user_id}/note/` | `editUserNote` :4777 | `EditUserNoteData` | web UI (see caller) | earnings-account-misc.md | ./mutations/users/notes/edit.ts:1 |
| DELETE | `/api/users/{user_id}/note/remove` | `removeUserNote` :4798 | `RemoveUserNoteData` | web UI (see caller) | earnings-account-misc.md | ./mutations/users/notes/remove.ts:1 |
| GET | `/api/users/{user_id}/projects/` | `getUserProjects` :4815 | `GetUserProjectsData` | web UI (see caller) | earnings-account-misc.md | ./pages/users/[id]/assignments.vue:29 |
| PUT | `/api/users/{user_id}/projects/` | `assignUserToProject` :4832 | `AssignUserToProjectData` | web UI (see caller) | earnings-account-misc.md | ./mutations/users/assignUserToProject.ts:1 |
| DELETE | `/api/users/{user_id}/projects/{project_id}` | `unassignUserFromProject` :4853 | `UnassignUserFromProjectData` | web UI (see caller) | earnings-account-misc.md | ./mutations/users/unassignUserFromProject.ts:1 |
| DELETE | `/api/users/{user_id}/projects/{project_id}/note/` | `removeProjectAssignmentNote` :4870 | `RemoveProjectAssignmentNoteData` | web UI (see caller) | earnings-account-misc.md | ./mutations/assignments/removeNote.ts:1 |
| PUT | `/api/users/{user_id}/projects/{project_id}/note/` | `editProjectAssignmentNote` :4887 | `EditProjectAssignmentNoteData` | web UI (see caller) | earnings-account-misc.md | ./mutations/assignments/updateNote.ts:1 |
| PUT | `/api/users/{user_id}/projects/{project_id}/update` | `updateUserToProjectAssignmentStatus` :4908 | `UpdateUserToProjectAssignmentStatusData` | web UI (see caller) | earnings-account-misc.md | ./mutations/assignments/updateAssignmentStatus.ts:2 |
| PUT | `/api/users/{user_id}/registered_party/` | `editUserRegisteredParty` :4929 | `EditUserRegisteredPartyData` | web UI (see caller) | earnings-account-misc.md | ./mutations/users/editRegisteredParty.ts:1 |
| GET | `/api/users/{user_id}/short_info` | `getUserShortInfo` :4950 | `GetUserShortInfoData` | entity labels, assignments, dashboards (`components/common/labeled-entity/LabeledEntityUser.vue:33`) | earnings-account-misc.md | ./pages/assignments/[project_id]/[user_id].vue:57 |
| PATCH | `/api/users/{user_id}/unblock` | `unblockUser` :4967 | `UnblockUserData` | web UI (see caller) | earnings-account-misc.md | ./mutations/users/unblockUser.ts:1 |

### Upload

| Method | Path | SDK fn `client/sdk.gen.ts` | Req type | Trigger (canvasser build) | Owner | Status / caller evidence |
|---|---|---|---|---|---|---|
| POST | `/api/upload/` | `uploadFile` :4531 | `UploadFileData` | chat attachment upload (`components/chats/ChatsInputs.vue:169`; `mutations/uploadFile.ts`) | earnings-account-misc.md | ./mutations/chats/uploadFile.ts:1 |

### Export

| Method | Path | SDK fn `client/sdk.gen.ts` | Req type | Trigger (canvasser build) | Owner | Status / caller evidence |
|---|---|---|---|---|---|---|
| GET | `/api/export/{export_job_id}` | `getExportJob` :1275 | `GetExportJobData` | export job polling (`queries/exports.ts:14`) | earnings-account-misc.md | ./queries/exports.ts:1 |

### Webhooks (server-side handlers)

| Method | Path | SDK fn `client/sdk.gen.ts` | Req type | Trigger (canvasser build) | Owner | Status / caller evidence |
|---|---|---|---|---|---|---|
| POST | `/api/webhooks/branch` | `branchWebhookHandler` :5416 | `BranchWebhookHandlerData` | — (never sent) | earnings-account-misc.md | DEAD — no caller in frontend |
| POST | `/api/webhooks/checkr` | `checkrWebhookHandler` :5427 | `CheckrWebhookHandlerData` | — (never sent) | earnings-account-misc.md | DEAD — no caller in frontend |
| POST | `/api/webhooks/mailersend/bulk-email` | `mailerSendWebhookHandlerForBulkEmail` :5442 | `MailerSendWebhookHandlerForBulkEmailData` | — (never sent) | earnings-account-misc.md | DEAD — no caller in frontend |
| POST | `/api/webhooks/mailersend/inbound` | `mailerSendInboundEmailHandler` :5453 | `MailerSendInboundEmailHandlerData` | — (never sent) | earnings-account-misc.md | DEAD — no caller in frontend |
| POST | `/api/webhooks/mailersend/single-email` | `mailerSendWebhookHandlerForSingleEmail` :5464 | `MailerSendWebhookHandlerForSingleEmailData` | — (never sent) | earnings-account-misc.md | DEAD — no caller in frontend |
| POST | `/api/webhooks/sign_well` | `signWellWebhookHandler` :5475 | `SignWellWebhookHandlerData` | — (never sent) | earnings-account-misc.md | DEAD — no caller in frontend |
| POST | `/api/webhooks/twilio/inbound` | `twilioInboundMessageHandler` :5486 | `TwilioInboundMessageHandlerData` | — (never sent) | earnings-account-misc.md | DEAD — no caller in frontend |
| POST | `/api/webhooks/twilio/status-callback` | `twilioStatusCallbackHandler` :5497 | `TwilioStatusCallbackHandlerData` | — (never sent) | earnings-account-misc.md | DEAD — no caller in frontend |

**Group-level DECLARED-UNUSED notes** (evidence = caller column above +
page `roles` meta): all rows under "Canvassing-interaction imports",
"Recruitment", "Reports", "Staffing contacts", "Subcontractor companies"
(except the `short_info` label), "System & system settings", "Users (admin)",
"Selectors" (except `/api/selector/project`, which the canvasser shift flow
uses), "Projects (admin)" (except list/details/short_info used by prefetch and
`/restricted_areas`), "Verification — ballots & signatures" `/signature/*`
rows, "Work shift (non-mobile)" review/recalculate/export/exclusions rows, and
"Conversations & coaching" list/details rows are called only from pages gated
`roles: ['admin'|'manager'...]` (e.g. `pages/conversations/index.vue:94`
`roles: ['admin']`) or admin components → they never fire from the
canvasser-facing UI.

---

## 3. Websocket inventory

### 3.1 `wss://api.validnation.ai/api/ws/voice_verification/{id}` — the only ValidNation WS in the frontend

A repo-wide search for `new WebSocket` / `wsBaseURL` finds exactly two files:
`composables/useSocket.ts:17` (generic wrapper) and
`composables/useVoiceVerification.ts:137` (sole caller). **No other
ValidNation websocket message types exist in this build** — the ANALYSIS.md
line "websocket /api/ws (voice verification stream; likely more)" is resolved:
voice verification only, everything else realtime is FCM push or Supabase
Realtime.

- Connect: `GET /api/auth/ws_token` → `{access_token}` (one-time), then WS URL
  with query `token, sample_rate, bits_per_sample, channels, encoding`
  (`composables/useVoiceVerification.ts:135-149`). Audio config from
  `utils/createAudioConfig.ts`: `sample_rate` (device, default 48000),
  `channels` (default 1), `bits_per_sample` (default 16),
  `encoding: 'linear16'`.
- Client→server message types (`useVoiceVerification.ts:13-17,81-83,130,180,193,210`;
  TS types in unrecovered `~/types/api`, field names as sent):
  - `{type:'start'}` — after server `initialized` (`:128-130`)
  - `{type:'stream_audio', audio_data:<base64 Float32 PCM>}` — every 250 ms
    while streaming (`:163,171-182`)
  - `{type:'stop'}` — user stop / server `force_stop` (`:209-212`)
  - `{type:'cancel'}` — user cancel / route leave (`:189-195`)
- Server→client message types (`useVoiceVerification.ts:50-79`):
  - `initialized`; `signatory_info` (`{infos: SignatoryInfoResult[]}` → store,
    fields: `id, first_name, middle_name, last_name, state, city, county,
    address_1, address_2, zip_code, validation_result, signed_date,
    other_data` — `stores/verification/voice.ts:47-62`);
  - `force_stop`; `ready_for_submission`; `error` (`{detail}`).
- Reconnect: max 3 attempts, 5 s delay, re-runs `onStartVerification`
  (`composables/useSocket.ts:42-66`, `useVoiceVerification.ts:46-48`).
- Lifecycle: opened when the canvasser opens a voice-verification page
  (conversation created via `PUT /api/verifications/voice/ {project_id}` →
  `stores/verification/voice.ts:19-26`), closed on submit/cancel/route-leave.
  Submit is a separate REST call `POST /api/verifications/voice/{id}/submit`
  `{signatories:[...]}` (`components/verification/voice/VerificationVoiceForm.vue:141-160`).

### 3.2 Supabase Realtime websocket (different host)

`wss://tfnnpqpvdjisoizvciyr.supabase.co/realtime/v1/websocket` (supabase-js;
the `/api/broadcast` path in endpoints.txt is this library's broadcast
endpoint construction, confirmed in bundle `tree/assets/public/_nuxt/BYbP5qv3.js`
— `t.pathname="/api/broadcast"` string). Auth via `realtime.setAuth(<ValidNation JWT>)`
(`plugins/supabase.ts:164,215-223`). Channels/messages (chat page,
`pages/chats/[id].vue:375-397`):
- channel `chat:{chatId}` (`config: {private: true, broadcast: {ack: true}}`)
- broadcast events received: `new_message`, `edit_message`, `delete_message`,
  `edit_chat_details`, `edit_participant` (payload `{record}`)
- `system` events watched for "Token has expired" → `$realtimeManager.refresh()`
  → ValidNation `POST /api/auth/refresh` (`plugins/supabase.ts:17-39`).

---

## 4. Push-notification inventory (FCM)

Registration/handler: `plugins/notifications.ts:116-235`
(`@capacitor-firebase/messaging`). Token sync: `POST
/api/mobile/notifications/token {device_id, token}` on registration +
`tokenReceived` (`:48-95,123-152`); opt-out: `DELETE .../token?device_id=`
(`composables/mobile/useMobilePushNotifications.ts:81-104`).

### 4.1 Silent/data actions — `notification.data.action` (Android payload key `action`)

Enum: `types/mobile/pushNotificationActions.ts` — **exactly four values**;
dispatch in `plugins/notifications.ts:154-169`:

| action | Client behavior |
|---|---|
| `none` | no-op parse; still shows body toast if present (`:197-205`) |
| `work_shift_upload_data` | upload-only: falls through to `useUploader().tick()` → drains outbox (sensors/events/shift_end/audio) (`:161-162,167-168`) |
| `work_shift_end` | `useMobile().stop()` — full local clock-out (enqueues shift_end, drains), then uploader tick (`:163-166`) |
| `download_and_apply_live_update` | `prepareNextBundleIfNeeded(payload.bundle_id, payload.bundle_url)` → `applyNewBundle()` → posts `live_update_downloaded`/`live_update_applied` device events + `POST /api/mobile/device/update_info`, reloads webview (`:155-160`; `composables/mobile/updates/useMobileLiveUpdates.ts:186-238`) |

iOS payload variant: `data.aps.custom_data`/`data.aps` with `action` key
(`plugins/notifications.ts:177-184`). **Resolves the ANALYSIS.md naming
question**: `silent_upload_work_shift_data` and `silent_force_live_update`
are **in-app notification-list `type_` values** (taxonomy in bundle
`tree/assets/public/_nuxt/Bwx73IuD.js`, mirrored below), NOT the silent-push
`action` keys — the action keys are the four above.

### 4.2 In-app notification `type_` taxonomy (display + routing only)

Consumed by the notifications list (`GET /api/notifications/list`) — mapping
table recovered from bundle `Bwx73IuD.js` (component NotificationListItem):
`work_shift_start_reminder` (→ /shift), `work_shift_deadline_exceeded`
(→ /shift), `reset_password`, `reset_password_confirmation`,
`confirm_email`, `complete_branch_onboarding` (→ /account), `grace_message`
(→ Grace chat), `recruitment_inbound_message`, `chat_message` (→ /chats),
`invalid_assignment_contract_template`, `deleted_assignment_contract_template`,
`invalid_w9_contract_template`, `deleted_w9_contract_template`,
`staffing_contact_invite`, `silent_force_live_update`,
`silent_upload_work_shift_data`, `admin_assignment_contract_signing_request`,
`canvasser_assignment_contract_signing_request`,
`assignment_contract_sign_failed`, `w9_form_signing_request`,
`admin_assignment_contract_resign_request`, `w9_form_resign_request`,
`wake_word_event`, `project_finished`, `checkr_report_review_required`;
unknown types fall back to a default rendering.

### 4.3 Tap behavior

`notificationActionPerformed` → `data.redirectUrl`: `validnation:` scheme →
internal router push; otherwise `AppLauncher.openUrl`
(`plugins/notifications.ts:207-234`).

---

## 5. endpoints.txt reconciliation

In `endpoints.txt` but **not** in `client/sdk.gen.ts` (4):

| Path | What it is |
|---|---|
| `/api/sentry` | Sentry tunnel (`sentry.client.config.ts:12`) — POSTs Sentry envelopes through the API host |
| `/api/broadcast` | Supabase Realtime broadcast path (supabase-js library constant, bundle `BYbP5qv3.js`) — not a ValidNation REST endpoint |
| `/rest/v1/`, `/rest/v1/rpc/` | Supabase PostgREST root markers (chats; §6.10) |

In `sdk.gen.ts` but **not** in endpoints.txt (30): `/`,
`/api/account/referral_code`, `/api/assignments/{p}/{u}/contracts/resend`,
`/api/contracts/`, `/api/contracts/{contract_id}`,
`/api/earnings/transactions/{t}/short_info`,
`/api/mobile/device/action/data_sync`, `/api/mobile/device/action/live_update`,
`/api/mobile/device/send_event`, `/api/mobile/sensor/`,
`/api/projects/{p}/canvassing-app-users/import/{import_id}`,
`/api/projects/{p}/public_link/`,
`/api/public/upcoming_projects/{hash}`, `/api/upload/`,
`/api/users/export/{export_job_id}`, `/api/users/{user_id}/devices/`,
`/api/verifications/signature/valid/export/`, 8× `/api/webhooks/*`,
`/api/work_shift/{id}/canvassing_app_stats`, `/api/work_shift/{id}/interactions`,
`/docs`, `/health`, `/openapi.json`. Of these, only `/api/upload/` is actually
sent by the app (chat attachments, `mutations/uploadFile.ts`); the rest are
DEAD declarations or server-only surface (webhooks/docs/health).

---

## 6. Endpoints not owned by another audit file — full documentation

Owner check: auth-session.md covers `/api/auth/*`; shift-lifecycle.md covers
`/api/mobile/work_shift/*`, `/api/mobile/device/update_info|event/*|unlink`,
`/api/mobile/notifications/token`, `/api/canvasser_voice/wake_word_event`;
sensors-telemetry.md covers `/api/mobile/sensor/*`,
`/api/projects/{id}/restricted_areas`; audio-voice.md covers
`/api/account/voice_sample/`, `/api/canvasser_voice/receive|cached_receive|
wake_word_audio|wake_word_audio_cached`, `/api/verifications/voice/*` + the WS.
Everything else in scope for the canvasser build is documented here. All are
T1 transport (`Authorization: Bearer`, JSON), share the 401 → refresh →
single-replay → sign-out policy (auth-session.md §9), and GETs are
offline-cacheable. Request/response FIELDS are UNCONFIRMED unless stated
(types.gen.ts not recovered); query params below are the ones the code sets.

### 6.1 Sign-up (unauthenticated)

- `POST /api/signup/` — create account (`mutations/signUp/index.ts:7`).
- `POST /api/signup/email/confirm` — submit email code (`mutations/signUp/confirmEmail.ts:7`).
- `POST /api/signup/email/info` — poll email info (`queries/signUp/infoEmail.ts:12`).
- `POST /api/signup/email/resend` — resend code (`mutations/signUp/resendEmail.ts:7`).
- `PUT /api/signup/email/` — change email mid-flow (`mutations/signUp/changeEmail.ts:9`).
- `GET /api/public/subcontractor_company/details/{sign_up_code}` — company
  sign-up landing (`pages/sign-up/company/[code].vue:223`).
Trigger: user-driven during onboarding only. Failure: toast; no retry.

### 6.2 Account & profile

- `GET /api/account/` — account pages (`queries/account.ts:2-13`, staleTime 0)
  + 4-hourly prefetch (`utils/prefetchOfflineData.ts:20`). Response consumed:
  `AccountDetailsResponse` incl. referral/share info and hiring state (fields
  UNCONFIRMED beyond what pages read).
- `PUT /api/account/password/edit` — `{...}` change password (`mutations/account/editUserPassword.ts:12`).
- `POST /api/account/password/reset` — forgot password (`mutations/resetPassword.ts:8`).
- `POST /api/account/password/set` — set password via token flow (`mutations/setPassword.ts:8`).
- `PATCH /api/account/settings/edit` — account settings (`mutations/account/editUserSettings.ts:12`).
- `PATCH /api/account/{user_id}/delete` — delete account (`mutations/users/deleteUser.ts:10`).
- `POST /api/profile/`, `POST /api/profile/generate-bio`,
  `PUT /api/profile/{user_id}` — profile create/edit/AI bio
  (`mutations/account/setProfile.ts:10`, `generateBio.ts:13`, `editProfile.ts:17`).
- Shareable link (referral-program page `pages/account/referral-program/index.vue`):
  `GET /api/profile/{user_id}/shared_link` on dialog open
  (`components/users/details/ProfileShareDialog.vue:127`),
  `POST /api/profile/shared/{user_id}/generate` regenerate
  (`mutations/profile/shareable_link/regenerate.ts:19`),
  `PUT .../enable` / `.../disable` toggle
  (`mutations/profile/shareable_link/toggle.ts:14-15`).
  NOTE: `GET /api/account/referral_code` is DECLARED-UNUSED — the referral
  page reads the code from `/api/account/` details instead (no caller).
- `GET /api/profile/shared/{shareable_code}` — public, unauthenticated
  shared-profile view (`pages/share/profile/[code].vue:41`).

### 6.3 Earnings (canvasser-facing; **resolves [H]** DESIGN-VALIDNATION.md §8 line 177 — triggers + consumed fields below; full response schemas still UNCONFIRMED)

- `GET /api/earnings/` — earnings list page; query from route
  (page/size/filters; `pages/earnings/index.vue:60-117`). Consumed:
  `items[]` (`EarningListItemForCanvasser`).
- `GET /api/earnings/balance/` — balance page + prefetch
  (`queries/earnings/balance.ts:3-20`); consumed `pending`,
  `ready_for_payment` (`balance.ts:15`, `mutations/earnings/withdraw.ts:12-18`).
- `GET /api/earnings/totals-by-rate-type/` — earnings pages, staleTime 60 s
  (`queries/earnings/totalsByRateType.ts:4-20`).
- `GET /api/earnings/account/` — Branch/payment-account status (onboarding
  banner source), staleTime 500 ms (`queries/earnings/details.ts:3-21`) + prefetch.
- `PATCH /api/earnings/account/{user_id}` — edit payment settings
  (`mutations/users/updatePaymentInfo.ts:12`).
- `GET /api/earnings/{earning_id}` — earning details (`queries/earnings/earningDetails.ts:15`).
- `GET /api/earnings/{earning_id}/short_info` — inline labels
  (`components/common/labeled-entity/LabeledEntityEarning.vue:37`).
- `GET /api/earnings/transactions/`, `GET .../transactions/{id}`,
  `GET .../transactions/{id}/earnings` — transactions pages
  (`pages/earnings/transactions/index.vue:127`,
  `queries/earnings/transactions/details.ts:13`, `breakdown.ts:16`).
- `POST /api/earnings/withdraw` — Withdraw button, **no body**
  (`mutations/earnings/withdraw.ts:5-9`); on success zeroes
  `ready_for_payment` locally.
- DECLARED-UNUSED for canvassers (manager payroll actions):
  `POST /api/earnings/` create, `/approve`, `/manually_completed`, `/pay`,
  `/reject` (`mutations/earnings/*`, admin/manager pages).

### 6.4 Applications & assignments

- `GET /api/applications/` — upcoming projects; query
  `{page,size,sort_by='start_date',sort_type='desc',from_date?,name?,project_type='all',type?}`
  (`queries/applications/upcomingProjects.ts:10-40`).
- `GET /api/applications/{project_id}` — details (`queries/applications/details.ts:14`).
- `GET /api/applications/applied` — my applications (`pages/applications/my.vue:65`).
- `PUT /api/applications/create` — apply (`mutations/applications/applyToProject.ts:9`).
- `POST /api/canvasser_application/general_info`,
  `POST /api/canvasser_application/documents` — application form saves
  (`mutations/account/setCanvasserApplication.ts:8`,
  `pages/account/canvasser/edit/documents/index.vue:96`).
- DECLARED-UNUSED for canvassers: `POST /api/applications/applicants/`
  (admin table `ApplicationsDetailsTable.vue:72`), `/approve`, `/reject`,
  `/api/assignments/*` (admin assignment pages; `updateAssignmentInfo` also
  used from assignment card, manager context).

### 6.5 Contracts (canvasser sees read-only v2)

- `GET /api/contracts/v2/` — contracts list (`pages/contracts/index.vue:145-156`).
- `GET /api/contracts/v2/{contract_id}` — details (`pages/contracts/[id]/index.vue:154`).
- `GET /api/contracts/{contract_id}/short_info` — labels (`LabeledEntityContract.vue:35`).
- Signing happens off-platform (SignWell webhook flow); the app only displays.
- DECLARED-UNUSED: v1 `GET /api/contracts/`, `GET /api/contracts/{id}` (no
  caller — v2 superseded), `POST /api/contracts/sync`, `/terminate`
  (admin-only callers), `POST /api/contracts/w9/send`
  (`mutations/users/sendOrResendW9Form.ts:9`, manager user-details context).

### 6.6 Notifications (in-app)

- `GET /api/notifications/list` — notifications page; query
  `{page=1,size=10,sort_type='desc',only_unread}` (`pages/notifications/index.vue:44-82`).
  Consumed: `notifications[]{id,type_,message,read_at,sent_at,relative_url}`,
  `total_count`.
- `GET /api/notifications/unread-count` — sidebar badge, `useTimeoutPoll`
  **60 s**, skipped when mobile app backgrounded
  (`components/sidebar/AppSidebar.vue:87-99`). Consumed: `{count}`.
- `POST /api/notifications/mark_as_read/{id}`,
  `POST /api/notifications/mark_all_as_read` — user actions
  (`components/notification/NotificationListItem.vue:73`,
  `list/NotificationListActions.vue:20`).

### 6.7 Verification — voters & ballots (canvasser petition features)

- `PUT /api/verifications/voter/` `{project_id, infos: SignatoryVoiceForm[]}`
  — create signatory voters (`pages/verification/signatory/create.vue:68-76`,
  `mutations/verification/voter.ts:5-24`).
- Ballots: `GET /api/verifications/ballot/` drafts
  (`queries/verification/ballot.ts:21`), `GET .../ballot/list`
  (`pages/verification/ballots/index.vue:122`),
  `POST /api/verifications/ballot/` add (`mutations/verification/addBallot.ts:7`),
  `PUT /api/verifications/ballot/` submit (`mutations/verification/submitBallots.ts:7`),
  `GET/DELETE /api/verifications/ballot/{ballot_id}`
  (`queries/verification/ballots/details.ts:10`,
  `mutations/verification/removeBallot.ts`),
  `PUT /api/verifications/ballot/{ballot_id}/upload-files` photo upload
  (`components/verification/ballots/VerificationBallotsListItem.vue:141`),
  `PUT /api/verifications/ballot/upload-batch`
  (`pages/verification/ballots/import/index.vue:199`),
  `POST /api/verifications/ballot/pages/`, `GET/DELETE .../pages/{id}`
  (`mutations/verification/addPage.ts:7`,
  `queries/verification/ballots/pageDetails.ts:11`,
  `components/verification/ballots/VerificationBallotsImagePreview.vue:47`).
  Multipart details for ballot file uploads: UNCONFIRMED (SDK-generated).
- Signature review pages (`/submitted/`, `/valid/{id}`, exports) are
  manager-facing → DECLARED-UNUSED for canvassers;
  `POST /api/verifications/signature/valid/export/` has no caller at all
  (DEAD).

### 6.8 Emergencies (wake-word event viewers)

- `GET /api/wake_word_events/` — list page (`pages/emergencies/index.vue:115`).
- `GET /api/wake_word_events/{wake_word_event_id}` — details
  (`pages/emergencies/[id].vue:87`).

### 6.9 Misc reads used by the canvasser build

- `GET /api/selector/project?assigned_user_ids[]=<uid>` — shift-start project
  list (`queries/selectors/projects.ts:11`, statuses `active` filter set in
  `pages/shift/index.vue:130-133`) and shift-restore project recovery
  (`mutations/mobile/findSelectorProjectByIdViaList.ts:6-24`, T2 transport);
  also prefetched with `statuses=['active']` (`utils/prefetchOfflineData.ts:21`).
- `GET /api/work_shift/` — recent shifts on the shift home page, fixed query
  `{page:1,size:5,sort_by:'start_time',sort_type:'desc',timezone}`
  (`pages/shift/index.vue:113-128`); admin workshifts pages use the same
  endpoint with richer filters.
- `GET /api/work_shift/{id}/earning_progress` — active-shift page; refetch on
  every mount, **no interval polling** (staleTime Infinity,
  `queries/workshifts/earningProgress.ts:2-15`). Consumed: `net_hours`,
  `last_interaction_timestamp`, `paid_break_hours_left`
  (`pages/shift/[id].vue:35-47`).
- `GET /api/work_shift/{id}/conversations` — (`queries/workshifts/conversations.ts:7`).
- `GET /api/work_shift/{id}/short_info` — labels (`LabeledEntityWorkShift.vue:38`).
- `GET /api/projects/`, `/api/projects/{id}`, `/api/projects/{id}/short_info`
  — prefetch + shared components (`utils/prefetchOfflineData.ts:32-44`).
- `GET /api/users/{user_id}/short_info` — labels (`LabeledEntityUser.vue:33`).
- `GET /api/subcontractor_company/{id}/short_info`,
  `GET /api/coaching_feedback/{id}/short_info` — labels.
- `GET /api/docs/`, `GET /api/docs/{doc_path}` — in-app help
  (`pages/docs/index.vue:28`, `pages/docs/[...slug].vue:51`).
- `GET /api/export/{export_job_id}` — export-job status polling
  (`queries/exports.ts:14`); job creation endpoints are admin-only.
- `POST /api/settings/versions` — version/live-update check, body
  `{platform, native_version, native_build_number, frontend_version,
  current_bundle_id}` (`composables/mobile/updates/useVersionCheck.ts:8-24`),
  **unauthenticated-allowed** (`requiresAuth:false`,
  `mutations/mobile/getUpdateInfo.ts:13`). Consumed: `force_native_update`,
  `force_live_update`, `live_update_bundle_id`, `bundle_url`, `checksum`,
  `has_native_update` (`useMobileLiveUpdates.ts:68-94`). Triggers: cold start
  silent (`plugins/stateChangeListeners.ts:35-37`), every resume prompt-mode
  with 3 h dialog throttle (`:48-50`, `useMobileLiveUpdates.ts:13,201-205`),
  and push action `download_and_apply_live_update`. OTA bundle download goes
  to `bundle_url` via `@capawesome/capacitor-live-update` (host UNCONFIRMED —
  server-supplied URL).
- `POST /api/mobile/device/unlink` `{device_id}` — native logout
  (`utils/mobile/unlinkDeviceFromUser.ts:9-33`, called from
  `composables/auth/useAuth.ts:130`).
- `POST /api/upload/` — chat attachments, single multipart `file` part
  (`mutations/uploadFile.ts:19-119`); also `uploadFile` SDK fn referenced by
  ballot import (TODO comment `mutations/uploadFile.ts:38`).

### 6.10 Chats via Supabase (not api.validnation.ai)

RPC calls (`POST /rest/v1/rpc/<fn>`, schema `private`,
`plugins/supabase.ts:159-161`): `get_user_chats_cursor`,
`get_user_chats_cursor_at`, `get_chat_id`, `get_chat_details`,
`get_chat_info`, `get_chat_participants_with_details`,
`get_messages_with_details`, `get_messages_at_with_details`,
`get_unread_chat_count`, `get_user_info`, `send_message` `{input:{chat_id,
body, reply_to_message_id, forwarded_from_user_id, attachment_group_id,
dedup_key}}` (`composables/supabase/useSendMessage.ts:7-21`),
`edit_message`, `delete_message`, `mark_message_read`, `mute_chat`,
`new_dm` (one file per fn under `composables/supabase/`).
PostgREST tables: `attachments`, `profiles` (`composables/supabase/`).
Storage bucket `attachments`: upload / `createSignedUrl(60 s)` / `move`
(`composables/supabase/uploadFile.ts:5`, `createPublicLinkForAttachment.ts:10`,
`updateFilePath.ts:4`). Unread-chat-count poll: **15 s** foreground
(`components/sidebar/AppSidebar.vue:73-79`).

---

## 7. [H] resolutions (DESIGN-VALIDNATION.md)

| [H] item | Resolution |
|---|---|
| §2 line 47 — refresh request/response shape | `{refresh_token}` JSON body → `{access_token}` (+ getSession after); `composables/auth/useAuth.ts:228-257`. Full detail in auth-session.md §2 ("resolves [H]" there) |
| §2 line 54 — proactive refresh timing | exp − 60 s (not 80 % TTL); `plugins/auth.ts:38`, `config/authRefreshSchedule.ts:26-37` |
| §3 lines 67-68 — voice-sample field names/format | JSON `{audio_data: base64 PCM, audio_config:{sample_rate, channels, bits_per_sample, encoding:'linear16'}}`, NOT multipart/webm; `mutations/createSample.ts:7-11`, `composables/useSampleRecorder.ts:105-119`, `utils/createAudioConfig.ts`. Full detail audio-voice.md §1 |
| §8 line 177 — earnings endpoints/shapes | endpoints + triggers + consumed fields confirmed (§6.3); full response schemas remain UNCONFIRMED (types.gen.ts missing, `/openapi.json` 401) |
| ANALYSIS.md p.119 — "websocket /api/ws (voice verification stream; likely more)" | No more: voice verification is the only WS consumer (§3.1) |
| ANALYSIS.md p.120 — push taxonomy `silent_upload_work_shift_data`, `silent_force_live_update` | Those are in-app notification `type_` values; silent push `action` keys are `work_shift_upload_data`, `work_shift_end`, `download_and_apply_live_update`, `none` (§4.1) |

## 8. UNCONFIRMED items (not guessable from recovered code)

1. All request/response field lists carried only by the unrecovered
   `client/types.gen.ts` (affects most non-mobile endpoints). Type names are
   cited per row in §2 as anchors for a future authenticated
   `/openapi.json` pull.
2. `~/types/api` module (voice-verification WS message types,
   `SignatoryInfoResult`) — not recovered; §3.1 fields are from usage sites.
3. `restricted_areas` response `features[]` entry schema beyond
   `features`/`permission` (`composables/mobile/audio/useAudioRestrictionZones.ts:124-137`)
   — detail in sensors-telemetry.md §11.
4. OTA `bundle_url` host (server-supplied, §6.9).
5. Server behavior of `/api/mobile/device/action/data_sync|live_update`,
   `/api/mobile/device/send_event`, `/api/mobile/sensor/` (singular) —
   declared in the client, never called (DEAD); likely predecessors of the
   push-action/batch endpoints.
6. Ballot file-upload multipart field names (SDK-generated,
   `uploadBallotFiles`/`uploadBallotBatch`).

---

## Appendix A. Dead declarations (DECLARED-UNUSED, no caller anywhere)

`GET /` (`root`), `GET /api/account/referral_code`,
`POST /api/assignments/{p}/{u}/contracts/resend`,
`GET /api/contracts/`, `GET /api/contracts/{contract_id}` (v1),
`GET /api/earnings/transactions/{t}/short_info`,
`POST /api/mobile/device/action/data_sync`,
`POST /api/mobile/device/action/live_update`,
`POST /api/mobile/device/send_event`, `POST /api/mobile/sensor/`,
`GET /api/projects/{p}/canvassing-app-users/import/{import_id}`,
`GET /api/projects/{p}/checklist`, `GET /api/projects/{p}/note`,
`GET/PATCH /api/projects/{p}/public_link/` (v1; V2 used),
`GET /api/public/upcoming_projects/{hash}`,
`GET /api/users/export/{export_job_id}`, `GET /api/users/{user_id}/devices/`,
`POST /api/verifications/signature/valid/export/`,
`GET /api/verifications/voice/`,
`GET /api/work_shift/{id}/canvassing_app_stats`,
`GET /api/work_shift/{id}/interactions` (superseded by
`/route_with_interactions`), 8× `/api/webhooks/*` (server-side handlers that
appear in the generated client), `GET /docs`, `GET /health`,
`GET /openapi.json`. Evidence: zero call sites of the corresponding SDK
function in the full recovered tree (usage scan of all `.ts`/`.vue` outside
`client/`), and not referenced by any `mutations/mobile/` wrapper or
`config/auth.ts`.

Note: `sdk.gen.ts` functions for the auth four (`createAuthToken`,
`refreshAuthToken`, `getAuthProfile`, `logout`) and all mobile wrapper
endpoints also have zero direct call sites, but they ARE live — called
through `config/auth.ts` paths (auth) or hand-built T2/T3 requests (mobile).
They are not in the dead list.
