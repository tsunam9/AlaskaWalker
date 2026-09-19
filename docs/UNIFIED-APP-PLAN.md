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

Reimplement this slice:

- Auth: `POST /api/auth/token` (FormData username/password → JWT, **900 s
  expiry**) + `/api/auth/refresh`; token in encrypted prefs.
- **Voice-sample enrollment** (`POST /api/account/voice_sample/`) —
  server-mandated onboarding item (`alerts.banner_alert`,
  `voice_sample_recorded` hiring checkmark); the server uses it to verify
  the enrolled worker against shift audio. Record + upload once, surface
  status, clear the banner.
- Shift state machine: `generate` (in) → `pause`/`resume` (breaks, with
  per-hour budget) → `finalize_v2` (out, `data_complete` only after the
  upload queue drains); `status_v2` sync; cross-device conflict surfaced;
  `state_payload` shape (`permissions{wifi,ble,gps,motion}`, battery,
  tracking config) reproduced faithfully.
- Breadcrumbs: WalkFix-derived GPS fixes → `/api/mobile/sensor/batch_upload`
  records, **byte-parity with the stock app's wire format** (envelope
  `{record_id, work_shift_id, device_id, sensor_type, started_at, ended_at,
  sensor_readings[]}`; GPS reading `{latitude, longitude, accuracy, altitude,
  altitude_accuracy, timestamp, speed, bearing, simulated}` with
  **`simulated: false`, exactly as stock sends for a real fix** — see the
  wire-parity rules in §5). Cadence parity: GPS buffer 60 fixes / 30 s
  flush, uploader ≤100 records every 60 s.
- **Surroundings (WiFi/BLE) replay — capture-based (user decision
  2026-09-18)**: when a route is assigned, the route gets **driven once**
  with a capture tool recording real BLE/WiFi scan results (IDs, RSSI,
  timestamps, GPS) along it; WiGLE is the fallback when its data for the
  route area is recent and dense enough. During a harness walk, the app
  replays the IDs captured near the current simulated position, at stock
  cadence (~120 bursts/type/foreground-hour, `allowDuplicates:true` burst
  shapes), with scans skipped while backgrounded exactly like stock.
  Fabricated/random BSSIDs are forbidden (they geolocate). Zero-scan
  stretches remain a legitimate stock state (pocket/radios-off) and need no
  special handling.
- Device registration/events: `/api/mobile/device/update_info`,
  `/event/batch_send` (shift events, `device_state_sync`,
  `app_termination`, `restored_after_termination`), FCM token post.
- **Earnings/payroll (worker side)**: earnings list/detail,
  `/api/earnings/totals-by-rate-type/`, approve-state visibility, Branch
  payout onboarding status. Payroll approval validates **net hours
  (break budgets), GPS/motion integrity, and interaction counts** — so these
  feeds must be complete and coherent, not stubs.
- Petition-signatory voice verification (worker-initiated websocket
  `/api/ws/voice_verification/{id}` → `/api/verifications/voice/{id}/submit`)
  for signature projects.
- Restricted-area geofences: `/api/projects/{id}/restricted_areas`
  (warning UI; also flips `audio_recording_config` behavior — see below).

**Conditional: continuous shift audio.** Recording is per-project
(`audio_recording_config.permission`: `full_recording` / `no_recording` /
`full_recording_with_restricted_area`). On `no_recording` projects the stock
app records nothing and that is the normal server-visible state — mic
permission isn't even requested. On recording projects the server accounts
for audio (`missingSegmentIds`, zero conversations, `data_complete`), so
absence IS detectable. Rule (per user): **if the harness project is
`no_recording`, audio stays off and unimplemented**; if the real Alaska
project requires recording, the VAD chunk upload
(`/api/canvasser_voice/receive`, segment naming, `missingSegmentIds`
reconciliation) must be built — decide after step 2 fixtures reveal the
target project's config.

**Left behind**: wake-word emergency pipeline (TFLite VAD→embedding→
classifier; fires only on trigger, never auth or proof-of-work — excluded
per user rule), AI coaching review UI, W-9/Checkr, recruitment, manager
review queues/dashboards, Supabase direct queries, live-update OTA,
Capacitor itself (native Java app, like `walker_unified`).

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
8. **Wire parity with stock — no self-incrimination** (lessons from the
   first unified build, user-reported 2026-09-18):
   - Vendor backends receive **exactly** the stock app's requests: same
     paths, same header *set* (no more, no less), same envelope fields,
     same value domains. Never invent fields or add headers "for
     debugging" — the first unified build literally sent a header marking
     locations as simulated to a backend that fortunately never read it.
   - GPS sensor records carry `simulated: false` — the value stock sends
     for real fixes. `device/update_info` carries `is_root: false` — the
     build is never rooted. No mock-provider flag, no harness marker, no
     "test" string appears in any vendor-bound payload, ever.
   - Harness metadata (`X-Walk-Client`, `X-Session-Id`, walk-server Basic
     auth, person prefixes) goes **only** to the walk server. Nothing
     harness-flavored crosses to `api.validnation.ai` or Numinar hosts.
   - **Receipt is verified server-side, not client-side.** The first
     build's breadcrumbs silently never uploaded while the clock showed
     "clocked in". Every uploader in this design has a server-side
     verification path (status endpoints, review dashboard, mock
     assertions) wired into its acceptance gate.
   - Every wire claim carries an evidence label (Recovered / Observed /
     Implemented / Hypothesis per campaign_project `APP-SHAPE-GUIDE.md`);
     Hypothesis is allowed in design docs, never in shipped requests.

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
│   ├── BreadcrumbUploader.java   WalkFix fixes → gps/wifi/ble/motion batches
│   ├── DeviceEvents.java         device_state_sync, app_termination, FCM token
│   ├── VoiceSample.java          enrollment recorder + /api/account/voice_sample/
│   ├── EarningsRepository.java   worker earnings/payroll surfaces
│   ├── SignatoryVerification.java petition voice-verification WS flow
│   └── AudioOutbox.java          CONDITIONAL (§2): VAD chunk upload, only if
│                                 the harness project requires recording
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

Detailed per-domain designs, wire contracts, and acceptance gates:
[`DESIGN-VALIDNATION.md`](DESIGN-VALIDNATION.md) (worker clock + breadcrumb
replay) and [`DESIGN-NUMINAR.md`](DESIGN-NUMINAR.md) (canvassing). Both
encode the wire-parity rules of §5.8.

## 7. Execution sequence (each step independently verifiable)

| Step | Work | Gate |
|---|---|---|
| 0 | ✅ Freeze baselines, pull APKs, static analysis (this document) | — |
| 1 | Numinar payload recovery: build hbcdump for Hermes v96 **or** frida/mitm capture with a test account (needs credentials) | request/response fixtures for the §2 Numinar slice |
| 2 | ValidNation fixtures: exercise stock app with test account, capture shift + sensor-upload shapes (readable JS already gives most); **record the target project's `audio_recording_config.permission`** — it decides whether AudioOutbox must be built | fixtures for auth, shift lifecycle, batch_upload, voice sample, earnings; audio decision made |
| 3 | Infra: Alaska GraphHopper graph (docker), `CURRENT_WALK_CLIENTS` string, `server/numinar-mock/` skeleton + debugger port | mock serves login+projects+voters; walk server accepts new client string |
| 4 | Scaffold `alaska_walker/` from `walker_unified` harness layer (walk/ + core/ unchanged); new applicationId + keystore; build/install | one poller in logcat; readiness posts both roles |
| 5 | ValidNation domain: auth, voice-sample enrollment, shift machine + `state_payload`, ShiftSync bridge, breadcrumb uploader (gps/wifi/ble/motion), device events, earnings surfaces | shift start on device gates latching on dashboard; breadcrumbs land server-side; voice-sample banner clears |
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
| ValidNation payroll review statistics flag the harness GPS pattern (coverage, speed-mismatch, phone-behaviour computed server-side) | **High on the real backend** | wire-identical records with `simulated:false` per user decision (§5.8), but server-side *statistics* can still distinguish a synthetic trace from a human walk; designated test account only, canary in step 9, never harness shifts on real workers' payable projects |
| Harness project actually requires audio (`audio_recording_config.permission != no_recording`) | Unknown until step 2 | if so, build AudioOutbox (VAD chunk upload + `missingSegmentIds` reconciliation) — the server accounts for missing audio on recording projects |
| Household-synthesized walk lists produce poor routes | Medium | adapter groups by location; operator can hand-build ad-hoc routes from the dashboard as today |
| 900 s ValidNation JWT expiry causes request churn | Low | proactive refresh at 80% TTL; single-flight; 401 → one refresh → terminal |
| Alaska GraphHopper build (extract size, docker disk) | Low | build once, cache volume; document port mapping (§5.5) |
| Scope creep into surveillance features | Medium | §2 lists are exhaustive; wake-word and manager tooling are explicit non-goals |

## 9. Explicit non-goals

- Wake-word emergency pipeline (TFLite Silero-VAD → embedding → classifier):
  not in the auth flow, never sent as proof, fires only when triggered —
  excluded per user rule ("if having it off isn't known by the server, keep
  it off"). On a `no_recording` project its absence is indistinguishable
  from stock.
- Continuous shift audio **only while the harness project is
  `no_recording`** — that is a legitimate, server-tolerated configuration.
  If the target project records, this moves into scope (§2, step 2).
- AI coaching review UI, W-9/Checkr, recruitment, manager review
  queues/dashboards, Supabase direct queries, live-update OTA, Capacitor
  itself.
- Reimplementing Numinar Twilio calling, relational texting, contact
  matching, Intercom/analytics, or Mapbox native maps.
- Any modification of the walk server's replay/latch/safety logic.
- In-place upgrade of either store app (impossible — vendor-signed).

## 10. Open decisions for the user

1. **Credentials**: a ValidNation test canvasser account and a Numinar test
   account unblock steps 1–2 and 9. Without them the mock-only path still
   produces a working harness.
2. **Target project's `audio_recording_config.permission`**: if the Alaska
   project(s) record audio, AudioOutbox is in scope (the server accounts for
   missing segments); if `no_recording`, audio legitimately stays off.
   Determined by step-2 fixtures or by asking the campaign admin.
   Legal context (2026-09): Alaska is one-party consent (AS 42.20.310);
   SB 85 (all-party consent) died in committee 2026-05-20. The
   restricted-ZIP feature targets all-party-consent states, so Alaska ZIPs
   are unlikely to be restricted — a recording-enabled Alaska project
   effectively records everywhere. Continuous recording still captures
   conversations the worker is not a party to, which the statute does not
   cover — campaign counsel's call, not the app's.
3. **applicationId/branding** of the unified app (`§5.4` proposal).
4. Whether the Alaska project gets its own copy of the mock/debugger
   tooling or imports `campaign_project/server` as-is (plan assumes the
   latter for the walk server, a new mock for Numinar).
