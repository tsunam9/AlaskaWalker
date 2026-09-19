# Numinar canvassing core — endpoint & data-flow audit

Source: `/tmp/numinar_decompiled_rust.js` (machine decompile of Hermes v96 bundle,
`com.numinar.numinar` v10.0.0), cross-checked against `/tmp/numinar_decompiled_p1.js`
(register-level). Line refs `L<n>` = rust decompile; `p1:L<n>` = p1 decompile.
Everything below is code-confirmed unless marked **UNCONFIRMED**.

## 0. Corrections to prior hypotheses

- **There is NO plain `GET /v1/voters/` list call in v10.0.0.** The only
  `/v1/voters/...` URLs are per-voter sub-resources (`/notes`, `/interactions`,
  L359640, L360750). The voter list for a project comes from
  `GET /v2/mobile-app/projects/{id}/voters` (L226164). No pagination/offset, no
  bounding-box, no org query param anywhere in the voter fetch (swept for
  `bbox|bounding|radius|sw_lat|ne_lat|min_lat|max_lat|offset` — only React Native
  layout and a geojson library match).
- **`GET /v2/mobile-app/projects/` is only used with the `/voters` suffix.** The
  project *list* is `GET /v3/projects` (L339387); single project is
  `GET /v3/projects/{id}` (L226218).
- **No expo-sqlite usage in the JS bundle.** Offline persistence is
  `@react-native-async-storage/async-storage` (module_1359), whose native backing
  is `AsyncSQLiteDBStorage` (L199477–199501) — hence the sqlite-looking artifacts
  in the APK. Voter data is stored gzip-compressed in one AsyncStorage value.

## 1. Transport layer (module 1398, `useFetchService`, L224969–225200)

Every request below goes through `backendFetch`/`makeApiRequest`:

- Base URL: `FAST_API_URL = "https://fast-api.numinar.com/api"` unless
  `usingROS`, then `ROS_URL = "https://rust-server.numinar.com"`
  (constants module 1392, L202357–202395; selection at L225068).
- Default method `get`, default timeout **61000 ms** (L225055–225060).
- Headers on every request (L225072–225085):
  - `Content-Type: application/json`
  - `numinar-origin: mobile`
  - `platform: android`
  - `x-org-id: <current org id>` (from OrgContext; empty string allowed)
  - `sentry-sid: <Sentry session sid>` (if a Sentry session exists)
  - `Authorization: Bearer <Auth0 access token>` unless `requiresAuth:false`
    or a `bearerOverride` is supplied (L225078–225084).
- Retry: axios-retry, `retries: 1`, only when the error message contains
  `timeout`, `shouldResetTimeout: true` (L225014–225023).
- 401 handling (L225095–225150): if response `data.detail === "You need to
  verify your email to access this resource"` → rethrow; else attempt
  `refreshAccessToken()` once and retry the identical request with the new
  bearer; if refresh fails → toast "Session Expired / Please log in again." and
  throw. Non-401 errors rethrow.
- React Query global default: `new QueryClient({ defaultOptions: { queries:
  { refetchOnWindowFocus: false } } })` (L394548). Unless stated, queries use
  default staleTime 0 and refetch on mount.

## 2. Org bootstrap

### GET /v1/my-orgs-mobile  (L231404–231452)
- Request: no params, no body; `usingFastApi: true`. Full URL
  `https://fast-api.numinar.com/api/v1/my-orgs-mobile`. Method defaults to GET.
- Trigger: React Query `queryKey: ["organizations"]` (L231439), mounted by
  HomeScreen (`useOrganizations()`, L340823) and org-switch screens. When
  offline (`network.connectionState` false) or on request failure, falls back
  to AsyncStorage key `orgs` (`getOrgsFromOffline`, L225745–225772; legacy
  entries shaped `{org: {...}}` are unwrapped and re-stored).
- Response consumed: array of orgs; sorted client-side by `name`
  (localeCompare, L231419–231422); the sorted array is written to AsyncStorage
  `orgs` (L231424–231425). Org fields read elsewhere: `id`, `name`, `slug`
  (L392907), `signed_url` (L340998), `selected_state` (L340893, L382448),
  `data_source` (`!== "l2"` gates party fields, L382187), `has_relational_enabled`
  (L231515–231530).
- Org selection: if the user has exactly one org it is auto-selected
  (`setOrgId(memo1[0].id)` + `setLastOrgSelected`, L392954–392960); otherwise a
  stored/last org is chosen. `x-org-id` on all later calls comes from this.

### GET /v2/orgs/{orgId}  (L231455–231512)
- Trigger: `queryKey: ["organization", orgId]`, `staleTime: Infinity` (L231507),
  enabled only when `orgId` set. Used for org detail (relational flag, data
  source, selected_state).
- Offline: cached under AsyncStorage `org` (L231479–231480); fallback
  `getOrgFromOffline` reads from the `orgs` array (L225773–225795).

## 3. Project list and project selection

### GET /v3/projects  (module `useProjects`, L339362–339445)
- Request: `{ method: "GET", url: "/v3/projects", usingFastApi: true, orgId }`
  (L339387). No params. Headers per §1 (org scoping via `x-org-id`).
- Trigger: `queryKey: [orgId, "projects"]`, `initialData: []`,
  `networkMode: "always"` (L339437–339439). Mounted by HomeScreen, gated on
  `enabled` = org loaded AND (offline OR relational-survey query settled)
  (L340833–340840). Refetch triggers: pull-to-refresh on the home project list
  (HomeScreen `handleRefresh`, L340965–340974) and standard React Query remount.
- Response handling (L339388–339434):
  - If offline/failure → `getProjectsFromOffline()` (AsyncStorage `projects`,
    L225817–225833) and dispatch `setProjects`.
  - If `data.conditional_survey` is truthy, a synthetic project is prepended:
    `{ id: RELATIONAL_NEIGHBORS, name: "Contact Your Neighbors",
    outreach_type: "relational", is_active: true, status: "in-progress",
    created_at: <now-1ms ISO>, description: "See voters near you and remind
    them to vote" }` (L339392–339407).
  - Only `is_active` projects are kept for offline caching; when online they are
    written via `storeOfflineProjects` (AsyncStorage `projects`, L339424–339427,
    L225834–225847).
  - `dispatch(setProjects(data))`.
- Fields consumed per project (rendering/filtering, HomeProjectList
  L339900–339945): `id`, `name`, `outreach_type` (`canvass|call|relational`),
  `status` (`in-progress|todo` shown; relational always shown), `is_active`,
  `created_at`, `description`, `county_name`, `geofence_name`, `precinct_name`,
  `precinct_id` (search filter), `abev_election_id`, `dynamic_survey.id`,
  `survey` (+`survey.questions`), `text` / `specific_number` (after-canvass
  text, L384813–384830), `conditional_survey`.

### Project press flow (p1:L973500–973740; rust call site L340970)
On tap of a project row:
1. Mixpanel track one of `Opened Nearby Voters` / `Opened Call Project` /
   `Opened Relational Project` / `Opened Canvassing Project` with `{project_id}`.
2. If `project.id === RELATIONAL_NEIGHBORS`: dispatch `_clearVoters` (if a
   current project exists), `_resetCurrentProject`,
   `setNearbyCanvassingActive(true)`, `setContactTextingActive(false)`,
   navigate `Map` (with `{screen: "MapScreen"}` if a project was active). **No
   network call here** — the nearby-voters query (§5) takes over on MapScreen.
3. Else if different from current project: dispatch `_clearVoters`,
   `setCurrentProject(project)`, then `fetchOfflineProject({projectId, orgId,
   allProjects, dispatch, region, isOnline, makeApiRequest})` (L226209–226248),
   `_resetVoterInfo`, `setNearbyCanvassingActive(false)`,
   `setContactTextingActive(false)`; navigate: canvass → `Map`/`MapScreen`,
   call → `Voters`, relational → `Voters`/`ContactsListScreen`.
4. Same project re-tap: navigate only.

### GET /v3/projects/{id}  (inside `fetchOfflineProject`, L226218)
- Trigger: project selection (above) and home pull-to-refresh while a project
  is active (L340965–340973). `onStart: currentProjectApiRequest`,
  `onError: currentProjectApiFail`.
- Offline/failure fallback: `getCachedProject()` (AsyncStorage `cachedProject`,
  L225922–225943). If nothing → toast "Unable to retrieve project from offline
  storage" + throw (L226225–226231).
- Response: `dispatch(setCurrentProject(data))`; if
  `data.outreach_type !== "relational"` → immediately `fetchOfflineVoters` with
  `isSwitchingProjects: true` (L226238–226241).

## 4. Voter list fetch — GET /v2/mobile-app/projects/{id}/voters

(`fetchOfflineVoters`, module 1358, L226137–226206; cross-checked p1:L567900–568100)

- Request (L226147–226170):
  - URL `/v2/mobile-app/projects/{project.id}/voters`, method `get`,
    `usingFastApi: true`.
  - Query params (exact set, nothing else):
    - `ignore_contacted: project.outreach_type === "call"`
    - `include_past_contacts: project.outreach_type === "canvass"`
    - `limit: 10000`
    - `include_tags: !!project?.dynamic_survey?.id`
    - `compress: true`
  - `onStart: initialPageRequested`, `onError: votersFailed`.
  - Single page: no offset/cursor is ever sent; the whole list is bounded by
    `limit=10000`. No bounding-box params; geo filtering is client-side.
- Triggers:
  1. Project selection / switch (via `fetchOfflineProject`, §3).
  2. Home pull-to-refresh (same path).
  3. **After every successful offline-interaction sync**: NetworkManagerComp
     calls its `callback1` = `fetchOfflineVoters({project, orgId,
     isSwitchingProjects: false, ..., existingVotersWithInteractions})`
     (L230837–230842, invoked at L230939 before `commitOfflineBufferAfterSync`).
  4. When `isOnline` is false, the network call is skipped entirely and the
     offline copy is used (L226198–226203).
- Response handling:
  - Reads `data.voters_compressed` (string, default `""`, L226172–226176) →
    `decompressVoters` (L200160–200179): gzip **inflate** → JSON in
    **column-oriented** form `{field: [values...]}` → rebuilt into row objects
    via `Object.fromEntries`. The raw compressed string (not the rows) is what
    gets cached offline.
  - If `isSwitchingProjects` and `outreach_type === "canvass"`: the compressed
    string is stored (`storeOfflineVoters`, AsyncStorage key `voters`,
    L225872–225890) and the project JSON is stored via `setCachedProject`
    (keys `cachedProject`, `cachedProjectId`, canvass projects only,
    L225904–225921); on success dispatch `_setCachedProjectId(project.id)`.
    Then `dispatch(_backendStats({}))` and, if `project.survey`,
    `dispatch(_setSurveyAndQuestions(project.survey))` (L226186–226194).
  - Finally `dispatch(setVoters(processVoters(voters, region,
    existingVotersWithInteractions)))` (L226195–226196).
  - On fetch error: toast-less fallback to `getVotersFromOffline(project, ...)`
    (L226198): requires `cachedProjectId === project.id`, otherwise toast
    "Unable to retrieve voters from database" and return `[]`; decompresses
    AsyncStorage `voters` (L225848–225871).

## 5. Nearby voters — GET /v1/nearby-voters

(hook `useNearbyVoters`, module 3348, L387405–387460; consumer MapScreen)

- Request (L387431–387433): `{ method: "GET", url: "/v1/nearby-voters",
  usingFastApi: true, orgId }`, query params **exactly** `{ latitude, longitude }`
  — **no radius parameter is sent** (any radius is server-side; UNCONFIRMED).
- Query config: `queryKey: ["nearby-voters"]`, `staleTime: 600000` (10 min,
  L387447), `enabled` = `nearbyCanvassingActive && <device location available>`
  (MapScreen L387539–387549; location from one-shot `getCurrentPosition`,
  high accuracy, L387762–387775).
- Trigger chain: user opens the synthetic "Contact Your Neighbors" project →
  `setNearbyCanvassingActive(true)` (§3) → MapScreen obtains GPS fix → query
  fires. An effect refetches when the flag/project changes and a location
  exists (L387558–387563).
- Response: array of voter objects (same schema as §4); when present and the
  flag is active it is run through `processVoters` and dispatched as
  `setVoters`, replacing the project voter set in redux (L387746–387753).

## 6. Voter search — GET /v1/mobile-voter-search

(L386330–386455)

- Trigger: "Search" button on the voter search form; requires ≥1 non-empty
  field; navigates to `SearchResultsScreen` and dispatches `searchStarted`.
- Request: `{ url: "/v1/mobile-voter-search", method: "get", usingFastApi: true }`
  with params = all form fields plus `limit: 100, offset: 0` (L386394–386396).
  Field names (L386330–386336 and Location section): `first_name`,
  `middle_name`, `last_name`, `phone` (digits only, `/\D/g` stripped), `email`,
  `address`, `city`, `state`, `zip_code`, `jurisdiction_voter_id`,
  `state_voter_id`, `numinar_id`, `data_source_id`.
- `onSuccess: _gotSearchedVoters`, `onError: searchFailed`. Mixpanel
  `Looked Up Voter` with `{org_id: [orgId], fields_used: <keys>}` (L386408–386413).

## 7. Per-voter sub-resources

- `GET /v1/voters/{voterId}/notes` — `queryKey: ["voter-notes", id]`,
  `initialData: ""` (L359630–359655). Shown on VoterProfileTab "Voter Notes"
  (L382226–382228); invalidated after a note interaction uploads (L359610–359612).
- `GET /v1/voters/{voterId}/interactions` — activity feed,
  `queryKey: ["voter-interactions", id]`, `initialData: []` (L360738–360763).
- `GET /v2/voter_tags/{voterId}` — `queryKey: ["tags", id]` (L359513–359541).
- `GET /v1/projects/{projectId}/voters/{voterId}` — call-flow voter load
  (`loadVoterInfo`, L382770, L382796); `onSuccess: _getVoterInfo` (twilio slice).
- `GET /v1/voter-filter-categories` — filter/party label metadata,
  `queryKey: ["filterCategories"]`, `staleTime: Infinity`, enabled only online
  (L381400–381430). Response field consumed: `data.political[].internal_name`
  (looks up `registered_party_roll_up`) with nested `filters`.

## 8. Connectivity + telemetry calls that drive refetch

- `HEAD /v1/mobile_204` — online check; `requiresAuth: false`, `timeout: 10000`
  (L230836). Run by NetworkManagerComp (module 1351):
  - on a **15 s interval** (L230966–231030) — every tick also fires the QA
    tracking POST below when: user loaded AND `websocketUp` AND `orgId` AND a
    current project is set (L230988–230996);
  - on reconnect (`websocketUp && connectionState && !isSyncing`), which then
    schedules the offline-buffer sync after a 1500 ms delay (L230945–230958,
    L231034–231070);
  - on AppState return to `active` under the same conditions (L231071–231100).
- `POST /v1/canvassing-qa/tracking` (module 1563, L230656–230720) — canvasser
  GPS QA ping. Body (L230668–230691):
  ```
  { project_id,
    latitude, longitude,                      // one-shot GPS, high accuracy, 30 s timeout
    device_id,                                // AsyncStorage "deviceUuid" (uuid v4, persisted)
    device_geolocation_enabled,               // bool, LocationManager
    device_geolocation_permission_status,     // "granted"|"limited"|"blocked"|"denied"|"unavailable"
    is_using_emulator }                       // bool
  ```
  `timeout: 10000`. Cadence: piggybacked on the 15 s interval above (i.e. up to
  every 15 s while a project is open and the websocket is up). Each sub-check
  failure is caught individually and the field left undefined.
- WebSocket side-channel: after each successful offline sync, for every
  `insertCanvassInteraction` uploaded, a WS message
  `{"action":"sendmessage","data":"{\"type\":\"canvassed\",\"device_id\":...,\"voter_id\":...,\"org_id\":...,\"project_id\":...,\"user_id\":...}"}`
  is sent on the ROS websocket (L230875–230890). (The
  `POST /v1/interactions/batch` upload itself, in chunks of 10, is documented in
  the interactions audit — L230855–230925.)
- SSE `GET {FAST_API_URL}/v1/projects/sse/updates` (useSSE, L338722–338860;
  subscription L339345–339357): EventSource with headers
  `{x-org-id, Authorization: Bearer}`, default event name `update`, default
  reconnect interval 3000 ms. Messages update
  `["project_loading_status", projectId]` query data (`status.status` field).
  Companion REST poll: `GET {ROS_URL}/api/v3/project/loading_status/{id}`
  (`usingROS: true`, L339330–339342). Purpose: "project data still loading"
  spinner while the server prepares a project.

## 9. Household grouping logic (module 1394, L202496–202830; verified p1:L578686–578760)

`processVoters(voters, region, existingVotersWithInteractions)` (L202585–202608):
1. For each voter: if `house_hold_id === null` → set `house_hold_id = voter.id`
   (L202604). **The server field is spelled `house_hold_id`.**
2. `households` = `groupVotersByHousehold` → object keyed by `house_hold_id`,
   values = voter arrays; kept as `Object.values(...)` (array of arrays)
   (L202519–202533).
3. `householdsByLocation` = `groupHouseholdsByLocation(households)` → key =
   `"${household[0].registration_address_latitude},${household[0].registration_address_longitude}"`
   (exact float string, L202504–202507), values = arrays of households; redux
   stores `Object.values(...)` (L202612). So a map "location" = identical
   lat,lng of the first voter of each household.
4. `votersWithInteraction` = `{[voter.id]: true}` for every voter with
   `has_interaction` truthy, merged over the previous map
   (`existingVotersWithInteractions`) (p1:L578720–578745).
5. `streets` = unique street names: `extractStreetName` lowercases
   `registration_address_1`, strips house number and unit designators (list of
   66 tokens incl. apt/ste/unit/fl, module 1395, L202489–202494) →
   `"unknown street"` fallback (L202547–202564).
6. `region` = `averageGeolocation(households, region)`: NOT an average — the
   min/max lat/lng bounding box center with deltas = span; single household →
   that point with `latitudeDelta = longitudeDelta = 0.5`; empty → previous
   region (L202562–202584).
7. Result `{voters, households, householdsByLocation, votersWithInteraction,
  streets, region}` → `setVoters` reducer stores all pieces plus
  `voterCount = voters.length` (L200270–200283).

Derived household helpers:
- `getHouseholdName` — most common lowercase `last_name` in the household,
  ties broken by localeCompare, TitleCase + `" Household"` (L202629–202659).
- `voterHasVoted` — `abev_election_ballot_status ∈ {2, 3, 82, 83, 92, 93}`
  (L202620–202628).
- `allVotersInHouseholdHaveVoted` — only voters with `is_in_list` are counted;
  requires project `abev_election_id` set, else false (L202660–202667).
- `householdIsCompleted` — any member id present in `votersWithInteraction`
  (i.e. **one** canvassed voter completes the household) OR all in-list members
  voted (L202668–202675). Map markers use `allHouseholdsHaveVoted` for the
  "voted" pin state (L387581–387591).
- `addressSort` — street number asc, then street remainder, then numeric part
  of `registration_address_2` (apt) (L202732–202790).
- `getAbevValueLabel(filter_value, rnc_reg_id)` — label map for ballot status:
  null `rnc_reg_id` → "Hasn't Registered"; "-1" → "Not Applicable";
  4/84/94 → "Unknown"; 5/85/95 → "Hasn't Voted"; 1/81/91/2/3/82/83/92/93 →
  "Voted"; 6/86/96 → "Fix address"; 0/80/90 → "Unknown" (L202673–202731;
  nesting partially garbled in decompile — the leaf labels and the voted set
  are confirmed, the exact 0/80/90 branch is **UNCONFIRMED** in detail).

## 10. Voter object schema (every field the code reads or writes)

Server→client fields (read in UI/logic):
- Identity: `id` (number/string key everywhere), `house_hold_id` (nullable;
  client writes `id` into it when null), `first_name`, `last_name`
  (`middle_name`, `name_suffix` only appear in the search form, UNCONFIRMED as
  response fields), `rnc_reg_id` (registration id, L202674).
- Address/geo: `registration_address_1`, `registration_address_2`,
  `registration_address_city`, `registration_address_state`,
  `registration_address_zip_5`, `registration_address_latitude`,
  `registration_address_longitude` (all L202506, L382171–382235,
  L387363–387365); fallback plain `state` when
  `registration_address_state` empty (L382177).
- Political: `registered_party_roll_up` (party chip; label maps in module 1366
  L200126–200144 and `/v1/voter-filter-categories`), `official_party`,
  `rnc_calc_party` (both hidden when org `data_source === "l2"`,
  L382187–382205).
- Turnout/history: `voter_status` (`A|I|C|D` → Active/Inactive/Canceled/
  Deceased, L200145–200153), `permanent_absentee` (`"Y"` → Yes, L382212),
  `voter_frequency_general`, `voter_frequency_primary` (rendered `x/4`,
  L382202–382203), vote-history columns `vh_08_g … vh_24_g`, `vh_YY_p`,
  `vh_YY_pp` (full key list module 2780, L360786–360789; codes: 0 "Did not
  Vote", 1 "Voted", 2 "Absentee", 3 "Republican", 4 "Absentee (R)",
  5 "Democrat", 6 "Absentee (D)", 7 "Voted Early", 8 "Early Vote (R)",
  9 "Early Vote (D)", 100 "Independent", 101 "Absentee (I)",
  102 "Voted Early (I)", "Y" "Voted" — L360795–360810; the canvass list shows
  24G/23G/22G/22P/21G/21P/20G/20P/19G/19P/18G, L383985–383988).
- ABEV: `abev_election_ballot_status` (numeric, voted set above),
  `abev_elections` (array with `name`, matched to filter labels,
  L361038–361062).
- Demographic: `age`, `sex` (`M/F` → Male/Female else Other, L200073–200079),
  `ethnicity_modeled_ethnic_group_name` (L382222).
- Contact: `cell_phone_number` (gates follow-up text, L384831–384836),
  `email` (search form).
- List state: `is_in_list` (target-list membership; drives "In Target List" vs
  other sections, L384703–384740), `has_interaction` (server-set; **client also
  writes it**: after an interaction is queued, `setStoredVotersAsCanvassed`
  mutates the cached copy setting `has_interaction = true`, L225985–226040).
- Related resources (not embedded): notes, interactions, tags via §7.

A "household object" is just a JS array of voter objects; address/location are
always read from `household[0]` (e.g. L387363, L202506). There is no separate
household record from the server.

## 11. Offline cache layout (AsyncStorage; module 1358 + 1366)

| Key | Content |
|---|---|
| `voters` | gzip-compressed column-oriented voter JSON for the cached canvass project (L225848–225890) |
| `cachedProject` / `cachedProjectId` | project JSON / id, canvass projects only (L225904–225921) |
| `projects` | active projects array (L225817–225847) |
| `orgs` / `org` | org list / current org (L231424, L231479) |
| `me` | `/v1/me` user profile (L230749–230755) |
| `offline_buffer` / `offline_buffer_temp` / `offline_interaction_count` | interaction outbox + sync staging (L225404–225545); dedupe key `url_voter_id_project_id_tag_id` (L225573–225588) |
| `offline_lock` / `offline_voter_write_lock` | mutexes, 10 retries with linear backoff `(attempt+1)*100ms` (L225430–225470, L225945–225983) |
| `deviceUuid` | uuid v4, generated once (L226041–226060) |
| `substitute_number`, `lastEnv`, `async_test_key` | misc (L225546–225570, L226111–226135, L225374–225398) |

`compressVoters` is the inverse of §4 (rows → column object → JSON → gzip
deflate, L200180–200193).

## 12. Refetch cadence summary

- Organizations/projects: React Query defaults (refetch on mount) + home
  pull-to-refresh (refetch org + projects + `fetchOfflineProject` for current
  project, L340965–340974). `refetchOnWindowFocus` globally false (L394548).
- Voters: fetched only on project select/switch, home pull-to-refresh, and
  after each offline sync drain. No timer-based voter polling.
- Nearby voters: `staleTime` 10 min; refetch when nearby mode/project changes
  with a fresh GPS fix.
- Project loading status: SSE push + REST poll while project data loads.
- Org detail: `staleTime: Infinity`; filter categories: `staleTime: Infinity`,
  online only.

## 13. Not confirmable / out of scope notes

- Server-side default radius for `/v1/nearby-voters`: UNCONFIRMED (client sends
  only lat/lng).
- Exact response JSON shapes (field nullability/types beyond usage above):
  UNCONFIRMED statically; the bundle only reveals fields the client touches.
- `/v1/interactions/batch` request body, `insertCanvassInteraction` payload,
  bulk-canvass flow (`markHouseholdUnavailable` → `useBulkCanvass`,
  L385022–385037): interactions audit scope; referenced here only for the sync
  triggers they cause.
- `GET /v1/me` (L230757) and `PUT /v1/me` (`has_registered: true`, L230782)
  are fetched with the same offline-cache pattern; included for completeness.
