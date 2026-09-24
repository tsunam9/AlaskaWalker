# Numinar repointed build

Produces a separately signed build of the stock Numinar app
(`com.numinar.numinar` v10.0.0) whose three backend origins are retargeted to
the local mock in `../../server/numinar-mock/`. The frozen APKs in `../stock/`
are never edited. This is the gate-5 fidelity harness from
`../../server/numinar-mock/REQUIREMENTS.md` §10: if the stock workflow
(login → org → project → voters → canvass → QA beacon) runs clean against the
mock, the mock is behaviorally indistinguishable for that surface.

Unlike Patriot (HTML runtime config), Numinar's origins are string constants
inside a Hermes **v96** bytecode bundle, so the repoint patches bytecode:

- `hermes-decomp patch-string` (same-length) rewrites the string table:
  - `https://fast-api.numinar.com/api` → `http://127.0.0.1:19002/api/./.`
  - `https://rust-server.numinar.com` → `http://127.0.0.1:19002/././././`
  - `wss://rust-server.numinar.com/websocket` → `ws://127.0.0.1:19002/websocket/././././`
  - `auth.numinar.com` → `127.0.0.1:19002/`
  - `https://api.mixpanel.com` / `https://browser.sentry-cdn.com` → mock (404s, captured)
  - both Sentry DSN/envelope URLs → `.invalid` TLD (zero egress)
  - `ADJUST_APP_TOKEN` zeroed
  URL padding uses `/.` segments (OkHttp dot-segment resolution removes them)
  plus a trailing `/` (the mock's slash-collapse WSGI middleware absorbs the
  resulting `//`). **Keep-list:** `https://api.numinar.com` (JWT audience),
  `https://numinar.com/roles`, `https://numinar.com/email_verified` (claim
  names), `mobile.numinar.com` (deep-link shim), `www.numinar.com/privacy`.
- `hermes-decomp asm` patches seven functions at instruction level:
  - f19929/21886/21890/21897/22568/22574 — the bundle's only six
    `"https://" + AUTH0_DOMAIN` builders (auth-session.md §2); scheme
    downgraded to `http://`. The shared `https://` string entry stays intact
    for unrelated `startsWith()` validators.
  - f33115 — `Adjust.initSdk(config)` call removed (Adjust never starts).
- Vendor egress isolation (REQUIREMENTS §8.1): Adjust token zeroed, Sentry
  DSNs → `.invalid`, Mixpanel host/token killed, exp.host push endpoints →
  `.invalid`, and Firebase/Intercom/Twilio-FCM autostart disabled. Mapbox and
  Google Maps are the explicit 2026-09-23 user-authorized exception: their
  stock keys remain in the repointed app so maps render. Accepted remaining
  degradations: no push delivery, no call media, no telemetry.
- Smali: `Auth0$Companion.getDomainUrl` prepends `http://` instead of
  `https://`, so the native Universal Login (webAuth "Log in with password"
  / Google buttons) also reaches the mock; the mock serves a stand-in login
  page at `/authorize` that accepts any credentials and redirects back with
  an authorization code (mock `/oauth/token` maps it to that user).
- Manifest: `networkSecurityConfig` allows cleartext (base-config, since
  domain-config does not reliably match raw IP literals);
  `expo.modules.updates.ENABLED` → false (otherwise the ALWAYS
  check-on-launch could fetch the vendor OTA bundle over our patch); Adjust,
  Sentry-native, Intercom, Firebase, Twilio-FCM, and datatransport
  autostart components are disabled.

## Build and run

```bash
./build_repointed.sh                 # env: TARGET_HOST TARGET_PORT HERMES_DECOMP
adb install-multiple build-repointed/out/{base,split_config.arm64_v8a,split_config.en,split_config.xxhdpi}.apk
adb reverse tcp:19002 tcp:19002      # bridge device localhost to the mock
```

Remove the vendor-signed app first (signatures differ). Start the mock
(`python3 ../../server/numinar-mock/numinar_mock.py`) before launching; the
magic-code OTP appears in the mock log and the `/__mock/` dashboard.

The mock now has the minimal WebSocket acceptor required for `websocketUp` and
offline-buffer drain. The Auth0 web-authorize flow is covered end-to-end:
`/authorize` canonicalizes only the slash-padded repoint callback path to the
stock Android intent-filter path, then `/oauth/token` exchanges the returned
authorization code. Map tiles load from Google/Mapbox using the explicitly
authorized stock map credentials.

Captures land in `../../server/numinar-mock/captures/` (requests.jsonl covers
every hit, including neutered-SDK 404s).
