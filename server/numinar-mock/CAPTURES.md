# Numinar mock captures

With `PM_CAPTURE=1` (default), the mock writes append-only JSONL under
`captures/`. Set `PM_CAPTURE_DIR` to relocate it.

| File | Contents |
|---|---|
| `requests.jsonl` | Redacted request/response metadata for all non-dashboard traffic |
| `interactions.jsonl` | Accepted interaction payloads, their ordered type classification, and duplicate status |
| `qa_tracking.jsonl` | Every `/v1/canvassing-qa/tracking` beacon with server receipt time |

The directory is gitignored because stock-app captures can include voter PII,
GPS positions, device identifiers, and tokens. Authorization and token-shaped
fields are redacted from request captures. Use the domain streams to compare
stock-app and `alaska_walker` request shapes and cadence.
