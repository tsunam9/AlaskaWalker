# Alaska unified app plan — one APK playing Patriot Grassroots + Numinar roles

Prepared 2026-09-18, from static analysis of the two pulled store apps
(`patriot_grassroots/ANALYSIS.md`, `numinar/ANALYSIS.md`) and the proven
merge of `~/src/campaign_project/walker_unified` (`docs/MERGED-APP-PLAN.md`,
`server/ARCHITECTURE.md`).

**Verdict: the same unified-app architecture works, with one real gap.**
The walk server requires two *signal streams*, not two apps — a canvassing
client and a worker clock. Numinar supplies the canvassing domain; Patriot
Grassroots (ValidNation) supplies a real, API-backed shift clock that maps
onto the Connecteam role **more directly than Connecteam itself did**
(first-class `work_shift/generate` + `finalize_v2` instead of an inferred
punch feed). The gap: Numinar has **no walk-list/turf concept** — its
canvassing is household-based — so the walk-list upload the server routes
from must be synthesized. See §3.

---

## 1. Role mapping onto the walk-server contract

The server (`server/pulsar-route/`) is unchanged in behavior. Per person:

| Server expectation | Walker Unified (current) | Alaska unified app |
|---|---|---|
| `POST /api/worker/ready` ×2 roles (`client: "pulsar"`, `client: "connectteam"`), 30 s lease | one process posts both | same — one process, both roles |
| Pulsar liveness: `POST /api/client/login` + `/heartbeat` 5 s | Pulsar session | Numinar session (Auth0 or mock) |
| Worker clock: `POST /api/worker/clockin\|clockout` 5 s re-assert | Connecteam Feed (real service) | **ValidNation shift state** (real `api.validnation.ai`) — generate/finalize mirrored to the bridge |
| Feed poll `GET /<person>/api/location` 500 ms | one WalkFix poller | same WalkFix, ported as-is |
| `X-Walk-Client` version gate | `walker-unified/unified-1.1` | new string, e.g. `alaska-walker/unified-1.0`, added to `CURRENT_WALK_CLIENTS` |
| Doorknock latch consumption (exactly-once cursor) | submits Pulsar doorknock | submits **Numinar canvass interaction** (`/v1/interactions/batch`) |

The clock gate keeps its meaning: **doorknock latching is gated on the
ValidNation shift**, the app a human actually starts a shift on. The safety
model is identical — one process death stops both heartbeats and the walk
pauses within 15 s.

## 2. The two domains (and what gets left behind)

### Numinar domain (canvassing role)

Reimplement this slice only:

- Auth0 login (`auth.numinar.com`, scope `openid profile email
  offline_access`) **or** mock-backend session (see §4 decision).
- Org/project bootstrap: `/v1/my-orgs-mobile`, `/v2/mobile-app/projects/`.
- Voter/household fetch: `/v1/voters/`, `/v1/nearby-voters`.
- Walk-list synthesis → `POST /<person>/api/walklist` (§3).
- Doorknock submission: `POST /v1/interactions/batch` with disposition
  mapping; surveys: `/v1/relational-survey/`; tags.
- Optional breadcrumb analog: `/v1/canvassing-qa/tracking`.

**Left behind**: Twilio Voice calling, relational texting (Bandwidth/SMS
intent), contact matching, leaderboards, paid-relational payouts, Intercom,
Mixpanel/Adjust, Mapbox native SDK (the unified app keeps the proven
offline Leaflet WebView map from `walker_unified`).

### Patriot Grassroots / ValidNation domain (worker-clock role)

Reimplement this slice only:

- Auth: `POST /api/auth/token` (FormData username/password → JWT, **900 s
  expiry**) + `/api/auth/refresh`; token in encrypted prefs.
- Shift state machine: `generate` (in) → `pause`/`resume` (breaks, with
  per-hour budget) → `finalize_v2` (out); `status_v2` sync; cross-device
  conflict surfaced.
- Breadcrumbs: WalkFix-derived GPS fixes → `/api/mobile/sensor/batch_upload`
  records (`sensor_type: gps`, honest `simulated` flag — see risks §7).
- Device registration/events: `/api/mobile/device/update_info`,
  `/event/batch_send` (shift events), FCM token post.
- Restricted-area geofences: `/api/projects/{id}/restricted_areas`
  (drives a warning UI; the audio-recording behavior it gates in the stock
  app is not reimplemented).

**Left behind**: all audio (VAD, wake-word, voice biometrics, coaching),
payroll/Branch/W-9/Checkr, recruitment, manager review queues, Supabase
direct queries, live-update OTA, Capacitor itself (native Java app, like
`walker_unified`).

## 3. The walk-list synthesis gap (the one genuinely new piece)

The server's route pipeline needs
`{lists:[{wid, name, formId, addresses:[{aid, lat, lng, knocked}]}]}`.
Pulsar served that shape natively; Numinar does not. The adapter:

1. Pick a Numinar project → fetch its voter/household set
   (`/v1/voters/` or mock equivalent).
2. Group by location (`groupHouseholdsByLocation` logic) → one address per
   household location, `aid` = stable household id, `knocked` from prior
   interaction state.
3. Upload as one walk list per project (wid = project-scoped id).

Consequence: route quality depends on household geocoding quality; the
server's Overpass/GraphHopper pipeline is unchanged. The mock backend
(§4) serves this shape directly, which is what most harness runs will use.

## 4. Backends: mock + real split (same trust model as today)

Following the current project's precedent (mock the canvassing backend, hit
the real clock service with a designated test account):

| Backend | Strategy | Notes |
|---|---|---|
| Walk server :8765 | **same server, shared instance** | one-line `CURRENT_WALK_CLIENTS` addition |
| Numinar canvassing | **mock** (`server/numinar-mock/`, Flask, mirrors `harness/backend.py`): login, projects, voters, interactions/batch, surveys | doorknocks never hit the live campaign DB during walks; debugger on its own port |
| ValidNation clock | **real** `api.validnation.ai`, designated test canvasser account | mirrors Connecteam precedent; clock-ins are real records — canary first |
| Auth0 (Numinar) | mock issues opaque session tokens; real Auth0 login is a later milestone (needs client ID/audience via runtime capture) | keeps harness runs credential-free |
| Pusher | not needed (neither app uses it) | door-blocking/lobby features not ported |

## 5. Hard constraints (carried over, plus Alaska specifics)

1. **Location precedence, fail-closed**: `real_gps:true` → device GPS; fresh
   simulated fix → walk feed; otherwise **no location**. One WalkFix poller
   serves breadcrumb upload, canvassing position, and UI.
2. **Host-scoped credentials**: walk-server Basic only to the walk origin;
   ValidNation JWT only to `api.validnation.ai`; Numinar token only to
   Numinar hosts (or mock). No shared header map.
3. **Clock authority**: the walk-server clock bridge is driven only by the
   ValidNation shift state machine, never by button state.
4. **Identity**: both store apps are vendor/Play-signed — **no in-place
   upgrade path exists**. The unified app gets a new applicationId
   (proposal `ai.validnation.walker.dev` or `com.alaskacampaign.walker`)
   and its own keystore. The stock apps stay installed as reference. No
   SMS-retriever hash or package-bound license constraints exist in either
   app (a real simplification vs. Connecteam's Transistorsoft license).
5. **Alaska geography**: the existing GraphHopper graphs cover west Portland
   and Texas only. Alaska routes need a new graph (Geofabrik `us/alaska`
   extract, new `compose.alaska.yaml`, new port, distinct compose project
   name — `ARCHITECTURE.md` §9 documents the collision trap).
6. **Version gate discipline**: bump `versionName` + append to
   `CURRENT_WALK_CLIENTS` in the same commit; old strings stay during
   transition.
7. **One `walk.json` per person**, union schema, external file over asset —
   same as `walker_unified`.

## 6. Target app

`alaska_walker/` — native Java/Gradle app modeled directly on
`walker_unified/` (same proven harness layer):

```
alaska_walker/app/src/main/java/<ns>/
├── WalkerApplication.java        boot: config → WalkFix → shift sync → canvasser
├── MainActivity.java             5 destinations: Home · Shift · Canvass · Health · Settings
├── walk/                         PORTED AS-IS from walker_unified
│   ├── WalkFix.java              the one 500 ms feed poller + clock bridge
│   ├── WalkClient.java           walk-server HTTP boundary
│   ├── WalkService.java          one FGS (dataSync|location), live notification
│   ├── WalkLifecycle.java
│   └── WalklistGeofence.java
├── core/RuntimeConfig.java + Http.java   walk.json union loader, shared helper
├── validnation/                  worker-clock domain
│   ├── VnApiClient.java          /api/auth/*, work_shift/*, sensor/batch_upload
│   ├── VnSessionStore.java       JWT + refresh (900 s expiry handling)
│   ├── ShiftRepository.java      shift state machine + break budgets
│   ├── ShiftSync.java            mirrors shift state → walk-server clock bridge
│   └── BreadcrumbUploader.java   WalkFix fixes → sensor/batch_upload batches
└── numinar/                      canvassing domain
    ├── NmApiClient.java          projects, voters, interactions/batch, surveys
    ├── NmSessionStore.java       session (mock token now; Auth0 later)
    ├── WalklistAdapter.java      project households → server walk-list shape (§3)
    ├── WalkUpload.java           restart batch upload (202-idempotent)
    ├── WalkCanvasser.java        latch consumption → interaction submission,
    │                             exactly-once cursor keyed by route identity
    └── MapTab.java               Leaflet WebView (from walker_unified)
```

UI: the same five-destination information architecture as `walker_unified`
(readiness board / shift clock / map-first canvass / diagnostics / settings),
re-skinned. The Shift screen talks ValidNation instead of Connecteam;
Canvass talks Numinar instead of Pulsar.

## 7. Execution sequence (each step independently verifiable)

| Step | Work | Gate |
|---|---|---|
| 0 | ✅ Freeze baselines, pull APKs, static analysis (this document) | — |
| 1 | Numinar payload recovery: build hbcdump for Hermes v96 **or** frida/mitm capture with a test account (needs credentials) | request/response fixtures for the §2 Numinar slice |
| 2 | ValidNation fixtures: exercise stock app with test account, capture shift + sensor-upload shapes (readable JS already gives most) | fixtures for auth, shift lifecycle, batch_upload |
| 3 | Infra: Alaska GraphHopper graph (docker), `CURRENT_WALK_CLIENTS` string, `server/numinar-mock/` skeleton + debugger port | mock serves login+projects+voters; walk server accepts new client string |
| 4 | Scaffold `alaska_walker/` from `walker_unified` harness layer (walk/ + core/ unchanged); new applicationId + keystore; build/install | one poller in logcat; readiness posts both roles |
| 5 | ValidNation domain: auth, shift machine, ShiftSync bridge, breadcrumb uploader | shift start on device gates latching on dashboard; breadcrumbs land server-side |
| 6 | Numinar domain against mock: session, projects→walklist adapter, upload, latch→interaction submission, surveys | full mock walk end-to-end: route computed, doors knocked exactly once |
| 7 | UI pass: five destinations, readiness board, Health diagnostics | every datum reachable; config editor validates |
| 8 | `multiclient-test`-style Alaska configs (one union `walk.json` per phone, person prefix) | two phones run separate people concurrently |
| 9 | Real-backend canaries: ValidNation shift + breadcrumbs (real, test account); Numinar read-only against real API | sanitized live shapes match fixtures |
| 10 | Device acceptance per campaign_project `APP-SHAPE-GUIDE.md` §9.3 + docs + completion matrix | full sequence observed on one phone |

Rollback at every step: the stock apps are untouched on the phone; nothing
in `campaign_project` is modified except the one server string (step 3),
which is additive.

## 8. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Numinar Hermes v96 blocks static recovery of exact payloads | Certain | step 1: hbcdump build or frida capture; mock-defined shapes cover harness runs meanwhile |
| Auth0 client ID/audience not statically recoverable | Certain (inlined) | runtime capture with test account; mock auth until then |
| ValidNation rejects/flags simulated GPS (`simulated:true`, root/tamper detection in stock app) | Medium | honest flag + test-account canary (step 9) before any walk depends on it; worst case, breadcrumbs stay mock-only while the clock (the load-bearing part) still works |
| Household-synthesized walk lists produce poor routes | Medium | adapter groups by location; operator can hand-build ad-hoc routes from the dashboard as today |
| 900 s ValidNation JWT expiry causes request churn | Low | proactive refresh at 80% TTL; single-flight; 401 → one refresh → terminal |
| Alaska GraphHopper build (extract size, docker disk) | Low | build once, cache volume; document port mapping (§5.5) |
| Scope creep into surveillance features | Medium | §2 lists are exhaustive; audio/Twilio/payroll are explicit non-goals |

## 9. Explicit non-goals

- Reimplementing ValidNation audio recording, wake-word, voice biometrics,
  AI coaching, payroll, recruitment, or manager tooling.
- Reimplementing Numinar Twilio calling, relational texting, contact
  matching, Intercom/analytics, or Mapbox native maps.
- Any modification of the walk server's replay/latch/safety logic.
- In-place upgrade of either store app (impossible — vendor-signed).

## 10. Open decisions for the user

1. **Credentials**: a ValidNation test canvasser account and a Numinar test
   account unblock steps 1–2 and 9. Without them the mock-only path still
   produces a working harness.
2. **applicationId/branding** of the unified app (`§5.4` proposal).
3. Whether the Alaska project gets its own copy of the mock/debugger
   tooling or imports `campaign_project/server` as-is (plan assumes the
   latter for the walk server, a new mock for Numinar).
