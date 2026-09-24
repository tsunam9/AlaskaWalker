# Real-backend stock traffic capture

This is a separate pass-through capture plane for the real Patriot and Numinar
backends. It never talks to `server/patriot-mock/` or `server/numinar-mock/` and
never synthesizes a response. Every vendor request and response header is captured
unredacted as an ordered list, preserving original casing and duplicate fields; the
proxy does not inject any additional header into the vendor request. The complete
header records are included in the delayed VPS archive. The future VPS logger address
is intentionally unset.

## Fidelity boundary

There are two supported device choices:

1. **Actually stock:** install/use the vendor-signed Play builds and install the
   mitmproxy CA as a system trust anchor on a controlled device. This is the only
   choice that preserves the vendor signature, installer provenance, and PairIP.
2. **Stock-derived capture builds:** use the new `build_stock_capture.sh` scripts.
   They preserve the real origins and normal application behavior but trust a
   user-installed CA. Both are locally re-signed; Patriot also needs a PairIP bypass.
   Per the test configuration, Firebase and Sentry initialization are disabled in
   both builds. Numinar Adjust remains enabled and otherwise stock.

The second choice is still not telemetry-invisible. Disabling Firebase and Sentry
creates an observable absence of their normal traffic. Numinar's retained Adjust SDK
still records installer/install data and may observe the local signature/install
provenance.

The public SHA-256 certificate fingerprints in each `BASELINE.md` identify the stock
signers but cannot be used to reproduce their signatures. Exact signing and Play
installer identity require either the untouched Play installation or cooperation from
the app owner to publish the capture build through a Google Play test track using the
real app-signing key. Falsifying Adjust installer or certificate data would not make
a locally signed APK stock-equivalent and is intentionally not part of this capture
harness.

Numinar's build patches only its `USING_SENTRY` getter to return false, which follows
the app's existing no-Sentry branch. It verifies that the stock Adjust token,
`Adjust.initSdk` bytecode, manifest receiver/provider, and native `libsigner.so`
survive unchanged. Patriot's stock browser DSN is already empty; the build blanks its
two native DSNs, causing the recovered native plugin to take its existing “Missing
DSN … skipping Sentry init” return path. Both builds disable the native Firebase,
Sentry, and associated DataTransport components and Firebase auto-init metadata;
Numinar's app, Expo, Intercom, and Twilio FCM receiver services are disabled with the
Firebase path. Push notification delivery is therefore intentionally unavailable in
these test builds.

## Capture a test run

Create and install mitmproxy's CA on the dedicated test device, then run:

```bash
./run_capture.sh
./device_proxy.sh enable
# Run the authorized real-backend test shift.
./device_proxy.sh disable
```

The Android proxy setting is device-wide, although the recorder persists only exact
allowlisted first-party and recovered SDK/update hosts. On a dedicated device,
`CAPTURE_HOSTS='*' ./run_capture.sh` records every proxy-visible host. Always disable
the proxy before disconnecting USB. FCM,
Google Play Services, native map traffic, pinned connections, and proxy-bypassing
transports may be absent; absence from a capture is not evidence of no traffic.

The proxy preserves HTTP methods, headers, and bodies, but it necessarily terminates
TLS. A remote service can observe mitmproxy's upstream TLS fingerprint and possibly a
different egress address even when the application payload is unchanged.

Runs are written under `captures/<timestamp>/` with mode `0700`; files use `0600`.
They are unredacted and contain credentials, tokens, voter PII, GPS, and potentially
audio. They are gitignored. Use only authorized test accounts and a controlled host.

## Delayed upload to the separate VPS logger

Nothing uploads by default. Once the logger URL, port, and token are supplied:

```bash
export LOGGER_UPLOAD_URL=https://logger.example.test:PORT/api/captures
export LOGGER_UPLOAD_TOKEN='dedicated-logger-token'
./upload_capture.py captures/20260923-120000
```

The current provisional protocol is an authenticated HTTPS `POST` containing a
`tar.gz`, with `X-Capture-Run` and `X-Capture-SHA256` headers. It can be adjusted to
the VPS logger's final contract without rebuilding either Android app. The dedicated
logger credential is used only by this host-side uploader and is never put into a
Numinar, ValidNation, mock-backend, or walk-server request.
