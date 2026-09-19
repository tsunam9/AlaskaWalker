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
    tree/                  extracted web build (readable Nuxt JS) + apktool
    java/                  jadx decompilation
  numinar/                 pulled stock app + analysis (canvassing role)
    stock/  BASELINE.md  ANALYSIS.md  tree/  java/
  docs/
    UNIFIED-APP-PLAN.md    the plan: roles, architecture, milestones, risks
    DESIGN-VALIDNATION.md  worker-clock domain design (wire contracts, gates)
    DESIGN-NUMINAR.md      canvassing domain design (adapter, latch loop)
  .venv-re/                reverse-engineering python env (hbctool)
```

Status: **planning**. Stock apps analyzed; nothing built yet.
Next actions are steps 1–3 in `docs/UNIFIED-APP-PLAN.md` (Numinar payload
recovery, ValidNation fixtures, Alaska GraphHopper graph + mock backend).

Sibling project reference: `~/src/campaign_project/` (walk server, mock
backend pattern, `walker_unified` app this plan mirrors).
