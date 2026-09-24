# App-internal real-backend traffic recording

The stock-derived Patriot and Numinar test builds continue to use their real vendor
origins. Recording happens inside each APK: no rooted device, Android proxy, VPN,
user CA, USB reverse, or external capture process is required.

Each app duplicates network observations into its own app-private
`files/network-capture/` NDJSON queue. When a dedicated logger URL is configured,
the queue is uploaded by a separate native `HttpURLConnection`; the uploader does
not add logger headers to vendor requests and is outside the instrumented vendor
transport, so it cannot record itself recursively. With no URL configured, records
remain queued locally.

These files are unredacted. They can contain credentials, bearer tokens, voter PII,
GPS, and audio. Use only authorized accounts and send them only to the dedicated
logger over a trusted connection.

## What is recorded

- Numinar installs an OkHttp network interceptor in React Native's shared client.
  It records the final OkHttp request/response header lists and bodies, plus
  RealWebSocket text/binary messages.
- Patriot injects a document-start-accessible JavaScript bridge into its Capacitor
  WebView and wraps `fetch`, `XMLHttpRequest`, and `WebSocket`. It records headers
  exposed to WebView JavaScript, bodies, responses, errors, and WebSocket messages.
  Chromium-managed transport headers that Web APIs do not expose are outside this
  recorder's visibility.

Capture is observational: neither recorder mutates the vendor URL, request, response,
or header set. The logger upload uses these dedicated headers only on the logger
connection:

- `Content-Type: application/x-ndjson`
- `X-Capture-App: numinar|patriot`
- `X-Capture-Install: <random app-install UUID>`
- `X-Capture-Batch: <queue filename>`
- `Authorization: Bearer <token>` when configured

The logger must return a 2xx status before the app deletes a batch. Failed batches
remain private on the device and are retried after later app traffic.

## Build

The future VPS endpoint is intentionally unset in the default build:

```bash
cd ../numinar/instrumentation
./build_stock_capture.sh

cd ../../patriot_grassroots/instrumentation
./build_stock_capture.sh
```

Once the dedicated logger address and token are known, rebuild both APKs with the
same configuration:

```bash
export LOGGER_UPLOAD_URL='https://LOGGER_HOST:PORT/api/captures'
export LOGGER_UPLOAD_TOKEN='dedicated-logger-token'
./build_stock_capture.sh
```

`LOGGER_UPLOAD_URL` accepts only an empty value or an `http://`/`https://` URL. HTTPS
is preferred because the records are sensitive. When Numinar is built with an
`http://` logger URL, its builder explicitly enables Android cleartext traffic for
that build; this does not repoint or downgrade its HTTPS vendor origins. The token is
embedded in the local test APK but is never printed in `BUILD-MANIFEST.txt`.

## Fidelity boundary

Both APKs are locally signed and therefore are stock-derived, not vendor-identical.
Patriot also requires a PairIP startup bypass because a local signer cannot satisfy
the Play-bound check. Per the test configuration, Firebase and Sentry initialization
are disabled in both builds. Numinar Adjust remains enabled with its stock token,
initialization function, components, and native signer library.

The certificate fingerprints in each `BASELINE.md` identify the vendor signers but
cannot reproduce those signatures. Numinar Adjust may observe the local signature
or install provenance, and disabling Firebase/Sentry creates an observable absence
of their normal traffic.
