# AGENTS.md — Alaska_Campaign

Guidance for AI coding agents working in this repository. Read this first.

## What this repository is

This is **not a buildable software project** — there is no `pyproject.toml`,
`package.json`, `Cargo.toml`, Gradle build, or test suite here. It is a
**reverse-engineering evidence + design repository** for the Alaska campaign:
two stock Android apps pulled from a phone, fully reverse-engineered to
citation grade, plus the plan and domain designs for a unified
walk-harness app (`alaska_walker/`) that has **not been built yet**.

Goal (per `README.md` and `docs/UNIFIED-APP-PLAN.md`): one native Java
Android app that plays two roles against the walk server in the sibling
project `~/src/campaign_project` (`server/pulsar-route/`, port 8765):

- **Canvassing role** (Pulsar equivalent) — reimplemented from Numinar.
- **Worker time-clock role** (Connecteam equivalent) — reimplemented from
  Patriot Grassroots (a white-label of the ValidNation platform,
  `api.validnation.ai`).

Status as of 2026-09-19: **static recovery complete; plan steps 1–2 (static
halves) done.** Updated 2026-09-21: first build artifacts exist —
`server/patriot-mock/` (ValidNation mock backend covering the full
canvasser-facing surface per `patriot_grassroots/audit/`; test suites
`scripts/test_audio.sh` 26/26, `scripts/test_reads.sh` 77/77,
`scripts/simulate_workflow.py` all green) and the `alaska_walker/` scaffold
(logs into the mock: token → profile → proactive refresh verified
on-device). Per user direction the Patriot side is mocked first and
GraphHopper is deferred. A repointed stock Patriot Grassroots build
(`patriot_grassroots/instrumentation/build_instrumented.sh` with
`BUILD_VARIANT=repointed TARGET_HTTP_ORIGIN=...`) runs against the mock as
the behavioral fidelity test. Next work: steps 3–6 of
`docs/UNIFIED-APP-PLAN.md` (grow `alaska_walker/` against the mock).

Updated 2026-09-23: `server/numinar-mock/` exists (port 19002, all four
acceptance suites green) and `numinar/instrumentation/build_repointed.sh`
builds the repointed stock Numinar APK set (Hermes v96 patched via
hermes-decomp patch-string/asm; expo-updates disabled; Sentry/Mixpanel/
Adjust neutered). The mock includes the minimal WebSocket acceptor required
to open the stock client's `websocketUp`-gated offline drain.

## Repository layout

```
README.md                     status + next actions (start here)
docs/
  UNIFIED-APP-PLAN.md         master plan: role mapping, constraints,
                              10-step execution sequence with gates, risks
  DESIGN-VALIDNATION.md       worker-clock domain design (wire contracts)
  DESIGN-NUMINAR.md           canvassing domain design (adapter, latch loop)
patriot_grassroots/           ValidNation white-label (Capacitor/Nuxt hybrid)
  stock/                      base + split APKs pulled from the phone
  BASELINE.md                 frozen install path, cert, SHA-256 evidence
  ANALYSIS.md                 feature/auth/API/location findings
  endpoints.txt               265 extracted API paths
  audit/                      six line-cited audit files — GROUND TRUTH
  tree/                       extracted web build + apktool output
numinar/                      canvassing app (Expo/React Native, Hermes v96)
  stock/  BASELINE.md  ANALYSIS.md  tree/  (same roles as above)
  audit/                      six line-cited audit files — GROUND TRUTH
  instrumentation/            build_repointed.sh — repointed stock build
                              targeting the mock (Hermes v96 bytecode patch)
server/patriot-mock/          ValidNation mock backend (Flask+PyJWT,
                              0.0.0.0:19001, env PM_HOST/PM_PORT); full
                              canvasser surface; dashboard at /__mock/;
                              runtime-state.json persistence; tests in
                              scripts/; run: python3 patriot_mock.py
server/numinar-mock/          Numinar mock backend (same pattern, port
                              19002, one Flask process plays all three
                              Numinar origins); slash-collapse middleware
                              absorbs repoint URL padding; run:
                              python3 numinar_mock.py
alaska_walker/                unified app scaffold (native Java, AGP 8.10,
                              gradle 8.11.1 wrapper); build: ./build.sh
```

Gitignored local artifacts (not committed, may be absent on disk):
`.venv-re/` (Python RE env with hbctool), `*/java/` (jadx decompilations),
`*/tree/apktool/` (apktool output), `*.keystore`/`*.jks`. Note the README
references `patriot_grassroots/java/` and `numinar/java/` — these are
regenerable local outputs, not tracked content.

## Technology stack

### Subject apps (analysis targets, do not modify)

- **Patriot Grassroots** (`com.patriotgrassroots.validnation` v1.0.0 (114)):
  Capacitor hybrid wrapping a Nuxt/Vue web build. The complete original
  frontend source (2,518 files) was recovered from shipped source maps
  (`tree/assets/public/_nuxt/*.js.map` → `sourcesContent[]`).
- **Numinar** (`com.numinar.numinar` v10.0.0 (100000)): Expo/React Native
  0.83.10, Hermes **bytecode v96**. The JS bundle was fully decompiled with
  hermes-decomp (400k-line output; `L<n>` line cites in `numinar/audit/`
  refer to `/tmp/numinar_decompiled_rust.js`, a /tmp artifact that may need
  regeneration — see "How this was produced" in `numinar/audit/README.md`).

### RE tooling used (reproduction recipes live in the audit READMEs)

apktool, jadx, hermes-decomp, hbctool (in `.venv-re/`), adb pull, apksigner,
plus small Python scripts for source-map explosion.

### Future build target

`alaska_walker/` will be a **native Java/Gradle Android app** modeled on
`walker_unified/` in `~/src/campaign_project` (harness layer `walk/` +
`core/` ported as-is). No code exists yet; `docs/UNIFIED-APP-PLAN.md` §6
has the target package layout.

## Build and test commands

None in this repo — there is nothing to compile or run. Verification here
means:

1. **Documentation verification**: audit files under `*/audit/` are the
   ground truth; where they conflict with `ANALYSIS.md` or `docs/DESIGN-*.md`,
   the audits win.
2. **Plan gates**: each step in `docs/UNIFIED-APP-PLAN.md` §7 has an
   explicit acceptance gate (e.g. "mock serves login+projects+voters").
3. **Runtime canaries** (step 9): real-backend checks with designated test
   accounts — blocked on credentials the user must supply.

## Project conventions (important — read before editing docs)

- **Evidence labels**: wire/behavior claims carry **[R]** (recovered from
  decompiled stock code), **[O]** (observed live), or **[H]** (hypothesis).
  Shipped requests may only use [R]/[O] contracts; [H] marks what fixtures
  must confirm. Hypotheses are allowed in design docs, never in shipped
  requests.
- **Audit supremacy**: `patriot_grassroots/audit/` and `numinar/audit/` are
  ground truth with line citations. When new findings correct older docs,
  corrections are applied **inline with a date stamp** (e.g. "corrected
  2026-09-19 per `audit/sensors-telemetry.md` §5") rather than silently
  rewriting history.
- **Wire parity / no self-incrimination** (`UNIFIED-APP-PLAN.md` §5.8 —
  hard rules for any future code):
  - Vendor backends receive exactly the stock app's requests: same paths,
    same header set (no more, no less), same envelope fields, same value
    domains. Never invent fields or add debug headers.
  - GPS sensor records carry `simulated: false`; `device/update_info`
    carries `is_root: false`. No mock-provider flag, harness marker, or
    "test" string in any vendor-bound payload, ever.
  - Harness metadata (`X-Walk-Client`, `X-Session-Id`, walk-server Basic
    auth) goes **only** to the walk server.
  - Receipt is verified server-side, not client-side; every uploader needs
    a server-side verification path wired into its acceptance gate.
- **Frozen baselines**: each app's `BASELINE.md` records install path,
  signing cert digests, and SHA-256 of pulled APKs. Do not overwrite stock
  artifacts; rollback strategy depends on the stock apps staying untouched.

## Security considerations

- **Host-scoped credentials**: walk-server Basic auth only to the walk
  origin; ValidNation JWT only to `api.validnation.ai`; Numinar token only
  to Numinar hosts (or mock). No shared header map.
- Keystores (`*.keystore`, `*.jks`) are gitignored; never commit signing
  material or credentials. Test-account credentials for ValidNation/Numinar
  are an open dependency (§10 of the plan) and belong to the user.
- Both store apps are vendor-signed — no in-place upgrade path; the unified
  app needs a new applicationId and its own keystore.
- Sensitive scope decisions are recorded in the plan: wake-word pipeline and
  manager tooling are explicit non-goals; continuous shift audio is
  conditional on the target project's `audio_recording_config.permission`
  (still unknown, runtime-only). Do not expand scope beyond the §2 lists
  without a user decision.

## Key open dependencies (do not guess around these)

1. ValidNation and Numinar test accounts (unblock step-2 runtime fixtures
   and step-9 canaries).
2. The target project's `audio_recording_config.permission` value (decides
   whether `AudioOutbox` must be built).
3. applicationId/branding choice for the unified app.
4. Sibling project `~/src/campaign_project` (walk server, mock-backend
   pattern, `walker_unified` reference app) lives outside this repo.
