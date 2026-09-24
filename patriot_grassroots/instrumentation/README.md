# Patriot full-traffic capture

For the separate real-backend, stock-derived build with app-internal recording and a
private delayed VPS upload queue, see
[`../../traffic_capture/README.md`](../../traffic_capture/README.md) and run
`./build_stock_capture.sh`. It needs no root, device proxy, user CA, or external
capture process. That build disables Firebase auto-start/components and makes the
native Sentry plugin follow its existing missing-DSN/skip-init branch. The tooling
below remains the isolated, mock-repointed/sink-only audit variant.

This directory produces a separately signed, instrumented Patriot build and routes
its proxy-aware traffic into a local, sink-only recorder. The frozen APKs in
`../stock/` and the evidence tree in `../tree/` are never edited.

## What is captured

The recorder stores unredacted request/response headers and bodies, multipart
boundaries and WAV payloads, WebSocket frames, and any TCP/UDP/DNS flows presented to
mitmproxy. Each body is stored verbatim in `captures/<run>/bodies/`; `events.jsonl`
records ordering, direction, metadata, SHA-256, and base64. This covers transports
T1–T6 and T8 in `../NETWORK-COMMUNICATION.md` when they honor Android's proxy.
Every non-local HTTP request receives a locally generated `451`; DNS is refused and
raw TCP/UDP flows are killed. The recorder never forwards to the requested server.

FCM delivery and some Google Play Services traffic (T7) execute in Google-owned
processes and may bypass an app/system HTTP proxy or use certificate pinning. Verify
that channel with an emulator packet capture; absence from `events.jsonl` is not proof
that no packets were sent. To recover the usable inbound format despite that boundary,
the build also instruments Patriot's three Firebase callbacks and records their exact
delivered objects as `instrumented_inbound_event` entries.

## Build and run

```bash
./build_instrumented.sh
./run_capture.sh
```

The first command downloads the pinned Apktool release, patches only an ignored work
copy to trust user CAs, disables the PairIP license entry point (the local signature
cannot satisfy the store-bound check), rebuilds the base, and signs the base plus all
split APKs with one local key. It cannot update the vendor-signed installation.

The rebuilt audit APK already points its recovered runtime origins at device
localhost port `18080`. For normal use, enable only the USB reverse. It bridges that
private device port to the recorder's host-loopback port `18081`, keeping unrelated
phone apps, desktop processes using port `18080`, and LAN clients out of the capture:

```bash
./device_proxy.sh app-only
# exercise the app with designated test accounts
./device_proxy.sh disable
```

`./device_proxy.sh enable` is a device-wide diagnostic mode and should only be used
when an intentionally mixed capture is desired. It makes every proxy-aware phone app
visible to the recorder.

For device-wide routing, including non-proxy-aware TCP/UDP and DNS, run
`CAPTURE_MODE=wireguard LISTEN_HOST=192.168.1.10 LISTEN_PORT=51820 ./run_capture.sh`
(replace the example address with this machine's device-reachable LAN IP) and import
the generated `build/wireguard.conf` into the Android WireGuard client instead of
running `device_proxy.sh`. The HTTP-proxy method is simpler for the app-owned T1–T6/T8
paths; WireGuard is the completeness check for SDK and unexpected destinations.

Always disable the proxy before disconnecting USB. Android 14+ may require CA
installation through Settings. For a strict no-upstream run on a physical device,
leave the USB reverse and recorder active and disable both Wi-Fi and mobile data. This
also prevents proxy-bypassing SDK traffic, but Android will report the app as offline.

## Data handling

Captures contain bearer tokens, credentials, location, audio, and personal data.
They are gitignored and created mode `0700`/`0600`. Do not commit, share, or use real
participant accounts. Responses are local sink responses, not genuine vendor data.
