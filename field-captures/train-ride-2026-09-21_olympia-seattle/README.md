# Field capture: train ride, 2026-09-21/22 (Olympia area → Seattle)

Snapshot of the patriot-mock live capture stream
(`server/patriot-mock/captures/`, gitignored) taken 2026-09-22 ~10:05 PDT.
Format and comparison checklist: `server/patriot-mock/CAPTURES.md`.

Provenance: stock Patriot Grassroots app (repointed build, stock logic
unmodified) on a Samsung SM-S921U, ~16 h shift across a train ride plus a
second short shift the next morning. Phone foregrounded only intermittently —
long background stretches show stock-legitimate behavior (GPS/motion
collection continues, WiFi/BLE scans skipped, uploads buffered then drained
on wake/finalize).

Contents:

- `sensors.jsonl` — 77 batch envelopes (gps/wifi/ble/motionActivity)
- `device_events.jsonl` — 45 device events
- `shift_events.jsonl` — generate/finalize lifecycle

Key stats: 667 GPS fixes, ~86 km path, avg 26 km/h, max 131 km/h, median
accuracy 9.9 m, all cellular, `simulated:false` throughout; motionActivity
automotive-dominant; 190 unique WiFi BSSIDs, 1,077 unique BLE devices.

**Privacy: real movement data with timestamps and radio IDs, committed
deliberately (public repo) by the data owner on 2026-09-22.**
