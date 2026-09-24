# Alaska_Campaign

A walk-harness client pair for the Alaska campaign: one unified Android app
playing the **Patriot Grassroots** (worker time-clock) and **Numinar**
(canvassing) roles against the same walk server used by
`~/src/campaign_project` (`server/pulsar-route/`, :8765).

```
Alaska_Campaign/
  patriot_grassroots/      pulled stock app + analysis (worker-clock role)
    stock/                 base + split APKs off the phone
    BASELINE.md            frozen install/cert/hash evidence
    ANALYSIS.md            feature/auth/API/location findings
    endpoints.txt          265 extracted API paths
    audit/                 full endpoint/shape/trigger audit (2026-09-19,
                           from source-map-recovered original sources)
    tree/                  extracted web build (readable Nuxt JS) + apktool
    java/                  jadx decompilation
  numinar/                 pulled stock app + analysis (canvassing role)
    stock/  BASELINE.md  ANALYSIS.md  tree/  java/
    audit/                 full endpoint/shape/trigger audit (2026-09-19,
                           from hermes-decomp decompilation of the v96 bundle)
  docs/
    UNIFIED-APP-PLAN.md    the plan: roles, architecture, milestones, risks
    DESIGN-VALIDNATION.md  worker-clock domain design (wire contracts, gates)
    DESIGN-NUMINAR.md      canvassing domain design (adapter, latch loop)
  .venv-re/                reverse-engineering python env (hbctool)
```

Status: **static recovery complete; mocks being built**. Both stock apps are
fully reverse-engineered to citation grade (all endpoint shapes, triggers,
cadences, and anti-fraud behavior confirmed in code — see the two `audit/`
directories); every former hypothesis in the design docs is resolved. Plan
steps 1–2 (static halves) are done.

Updated 2026-09-21: `server/patriot-mock/` (ValidNation mock, all test
suites green) and the `alaska_walker/` scaffold exist; a repointed stock
Patriot build (`patriot_grassroots/instrumentation/`) runs against it.
Updated 2026-09-23: `server/numinar-mock/` exists (Numinar mock,
0.0.0.0:19002; `test_auth0.sh` / `test_core.sh` / `test_interactions.sh` /
`simulate_workflow.py` all pass) and `numinar/instrumentation/` builds a
repointed stock Numinar APK set (Hermes v96 string-table + instruction
patches) that targets the mock via `adb reverse tcp:19002`.

Next actions are steps 3–6 in `docs/UNIFIED-APP-PLAN.md` (grow
`alaska_walker/` against the mocks; GraphHopper deferred). Runtime-only
leftovers: the target project's `audio_recording_config.permission` value
and the step-9 live canaries, both needing a ValidNation test account.

Sibling project reference: `~/src/campaign_project/` (walk server, mock
backend pattern, `walker_unified` app this plan mirrors).
