# Mock telemetry captures

Append-only JSONL streams of everything the (repointed, stock-logic) Patriot
Grassroots app sends to the mock. Written by `state.capture()`; enabled by
default, `PM_CAPTURE=0` disables, `PM_CAPTURE_DIR` relocates. **Gitignored —
contains real GPS/WiFi/BLE data.**

Files (one JSON object per line, each with `captured_at` = server receipt
time, ISO-8601 UTC):

| file | one line is | written by |
|---|---|---|
| `sensors.jsonl` | one batch envelope `{user_id, record_id, work_shift_id, device_id, sensor_type, started_at, ended_at, sensor_readings[]}` (gps/IMU/motionActivity times are epoch-ms; wifi/ble are ISO) | `POST /api/mobile/sensor/batch_upload` |
| `device_events.jsonl` | one event `{user_id, device_id, created_at, event_type, payload}` | `event/send`, `event/batch_send` |
| `shift_events.jsonl` | `{event: generate\|paused\|active\|finalize, work_shift_id, ...}` | work_shift lifecycle |
| `audio.jsonl` | one audio-upload metadata entry (WAV bytes are not stored) | `canvasser_voice/*` |

## Comparing against simulated walk data

The point of this capture: a later agent checks that harness-generated
walking telemetry "looks like" this real telemetry. Compare at least:

- **GPS**: fixes per record (60-fix buffer / 30 s flush), speed
  distribution, accuracy field values, `connection_type` mix,
  `simulated` always false, track continuity (no teleportation).
- **WiFi/BLE**: bursts per hour (~120/type/foreground-hour at defaults),
  unique-BSSID/device counts per distance moved, RSSI ranges, burst size
  distribution. Zero-scan stretches are legitimate (backgrounded/pocket).
- **motionActivity**: activity distribution for the locomotion type
  (walking shift should be walking-dominant; this capture's train ride is
  automotive-dominant), confidence=-1 on periodic ticks.
- **Cadence**: upload inter-arrival times (~30 s flush while active),
  per-tick `device_state_sync` + `data_upload` events before sensor drains.

Note what this capture is NOT: the phone was mostly stationary/on a train
with the screen in various states. Use it as a reference for shapes,
cadences, and value domains — the walk harness must match walking-motion
statistics from a real walked route capture (to be collected separately or
from this file's stationary/walking segments).
