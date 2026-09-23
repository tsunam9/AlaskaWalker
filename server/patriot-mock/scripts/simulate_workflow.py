#!/usr/bin/env python3
"""Full stock-workflow simulation against the patriot mock.

Replays the request sequence the stock app performs in a normal canvasser
shift, in stock order, with stock wire shapes (per patriot_grassroots/audit/*):

  cold start   versions check -> login (multipart) -> profile -> device link
               -> FCM token -> offline prefetch batch
  shift start  status_v2 pre-check -> selector/project -> generate
               -> update_info -> app_state event -> tracking loop
  tracking     uploader ticks: device_state_sync + data_upload events, then
               gps/wifi/ble/motionActivity batch_uploads with stock envelopes
  breaks       pause -> resume (button_pressed_time, outbox order)
  clock-out    finalize_v2 (array, data_complete:true after drain)
  post-shift   recent shifts, earning_progress, earnings views
  logout       device unlink -> logout (refresh revoked)

Exits non-zero if any step fails. Usage:
  python3 scripts/simulate_workflow.py [base_url]   (default http://127.0.0.1:8790)
"""

import json
import sys
import time
import urllib.error
import urllib.request
import uuid

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8790"
EMAIL = "canvasser@alaska.test"
PASSWORD = "alaska-test-1"
DEVICE_ID = "sim-device-" + uuid.uuid4().hex[:8]
PROJECT_ID = "3f8a2c1e-7b4d-4e2a-9c5f-1a2b3c4d5e6f"  # no_recording canvassing

failures = []


def iso(ts=None):
    t = ts if ts is not None else time.time()
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + "Z"


def req(method, path, token=None, json_body=None, form=None, raw=None,
        content_type=None):
    url = BASE + path
    headers = {}
    data = None
    if form is not None:
        boundary = "----SimBoundary" + uuid.uuid4().hex[:12]
        parts = []
        for k, v in form.items():
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; "
                         f'name="{k}"\r\n\r\n{v}\r\n')
        parts.append(f"--{boundary}--\r\n")
        data = "".join(parts).encode()
        content_type = f"multipart/form-data; boundary={boundary}"
    elif json_body is not None:
        data = json.dumps(json_body).encode()
        content_type = "application/json"
    elif raw is not None:
        data = raw
    if content_type:
        headers["Content-Type"] = content_type
    if token:
        headers["Authorization"] = "Bearer " + token
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except urllib.error.URLError as e:
        return -1, str(e)


def check(name, result, expect=200, keep=None):
    status, body = result
    ok = status == expect
    print(f"{'PASS' if ok else 'FAIL'} {name}: {status} {body[:160]!r}")
    if not ok:
        failures.append((name, status, body[:200]))
    if keep is not None:
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            failures.append((name + " (json parse)", status, body[:200]))
    return None


def state_payload():
    # getDeviceStatePayload shape, snake_cased (deviceInfoUtils.ts:12-33)
    return {
        "permissions": {"wifi": True, "ble": True, "gps": True, "motion": True},
        "battery": {"battery_level": 87, "is_charging": False},
        "config": {
            "location_distance_filter": 0, "location_buffer_size": 60,
            "location_flush_interval_ms": 30000, "location_android_priority": 0,
            "location_desired_accuracy": 2, "location_pauses_automatically": True,
            "location_activity_type": 3, "ble_scan_duration_ms": 10000,
            "ble_scan_interval_ms": 30000, "ble_scan_allow_duplicates": True,
            "wifi_scan_interval_ms": 30000, "physical_sensor_buffer_size": 200,
            "physical_classifier_buffer_size": 5,
            "motion_activity_interval_ms": 10000,
            "physical_sensor_window_ms": 1000, "uploader_batch_size": 100,
            "uploader_period_ms": 60000, "vad_enabled": True,
            "vad_max_buffer_size": 50, "vad_max_segment_seconds": 120,
            "vad_model_threshold": 0.5, "vad_gate_wake_word": True,
            "vad_wake_word_hangover_ms": 1500, "geofence_fetch_radius_km": 50,
            "geofence_refresh_distance_km": 10,
            "geofence_warning_distance_km": 1,
            "geofence_restriction_queue_size": 4, "audio_cache_ttl_days": 7,
            "audio_upload_batch_size": 5,
        },
    }


def update_info_body():
    return {
        "model": "Pixel 7", "device_id": DEVICE_ID, "name": "pixel",
        "is_complete_sensors": True, "is_root": False, "os_version": "15",
        "permission_gps": True, "permission_ble": True,
        "permission_wifi": True, "permission_motion": True,
        "push_permission_granted": True, "push_notifications_enabled": True,
        "platform": "android", "software_version": "v1.0.0 (114)",
        "timezone": "America/Anchorage",
    }


def gps_record(shift_id, base_ms):
    fixes = []
    for i in range(3):  # small stand-in for the 60-fix buffer
        fixes.append({
            "latitude": 61.2181 + i * 1e-5, "longitude": -149.9003 - i * 1e-5,
            "accuracy": 4.8, "timestamp": base_ms + i * 1000,
            "altitude": 31.0, "altitude_accuracy": 8.0, "speed": 1.3,
            "bearing": 92.0, "simulated": False, "connection_type": "wifi",
        })
    return {
        "record_id": uuid.uuid4().hex, "work_shift_id": shift_id,
        "device_id": DEVICE_ID, "sensor_type": "gps",
        "started_at": base_ms, "ended_at": base_ms + 2000,
        "sensor_readings": fixes,
    }


def wifi_record(shift_id, ts=None):
    t = iso(ts)
    return {
        "record_id": uuid.uuid4().hex, "work_shift_id": shift_id,
        "device_id": DEVICE_ID, "sensor_type": "wifi",
        "started_at": t, "ended_at": t,
        "sensor_readings": [{
            "bssid": "aa:bb:cc:dd:ee:ff", "ssid": "GCI-Home", "level": -55,
            "isCurrentWifi": True,
            "capabilities": ["WPA2-PSK-CCMP", "RSN-PSK-CCMP", "ESS"],
        }],
    }


def ble_record(shift_id, ts=None):
    t = iso(ts)
    return {
        "record_id": uuid.uuid4().hex, "work_shift_id": shift_id,
        "device_id": DEVICE_ID, "sensor_type": "ble",
        "started_at": t, "ended_at": t,
        "sensor_readings": [{
            "device": {"deviceId": "5A:3C:91:00:11:22", "name": "Tile"},
            "localName": "Tile", "rssi": -71, "txPower": 127,
            "manufacturerData": {"76": "02015a"}, "uuids": [],
            "rawAdvertisement": "020106",
        }],
    }


def motion_record(shift_id, base_ms):
    return {
        "record_id": uuid.uuid4().hex, "work_shift_id": shift_id,
        "device_id": DEVICE_ID, "sensor_type": "motionActivity",
        "started_at": base_ms, "ended_at": base_ms + 10000,
        "sensor_readings": [{
            "activity": "walking", "confidence": 100, "timestamp": base_ms,
            "accelerometer_std": 0.42,
        }],
    }


def device_event(event_type, payload):
    return {
        "device_id": DEVICE_ID, "created_at": iso(),
        "event_type": event_type, "payload": payload,
    }


def main():
    print(f"== cold start / login ({BASE}) ==")
    check("versions (pre-login)", req("POST", "/api/settings/versions",
          json_body={"platform": "android", "native_version": "1.0.0",
                     "native_build_number": 114, "frontend_version": "1.0.0",
                     "current_bundle_id": None}))
    login = check("login", req("POST", "/api/auth/token",
                  form={"username": EMAIL, "password": PASSWORD}), keep=True)
    if not login:
        return 1
    at, rt = login["access_token"], login["refresh_token"]
    check("profile", req("GET", "/api/auth/profile", at), keep=True)
    check("update_info (link)", req("POST", "/api/mobile/device/update_info",
          at, update_info_body()))
    check("fcm token", req("POST", "/api/mobile/notifications/token", at,
          {"device_id": DEVICE_ID, "token": "sim-fcm-" + uuid.uuid4().hex[:8]}))

    print("== offline prefetch batch ==")
    uid = login and json.loads(req("GET", "/api/auth/profile", at)[1])["token"]["user"]["id"]
    for name, path in [
            ("prefetch account", "/api/account/"),
            ("prefetch selector/project",
             f"/api/selector/project?assigned_user_ids[]={uid}"),
            ("prefetch balance", "/api/earnings/balance/"),
            ("prefetch earnings account", "/api/earnings/account/"),
            ("prefetch projects", "/api/projects/"),
            ("prefetch project details", f"/api/projects/{PROJECT_ID}"),
            ("prefetch project short_info", f"/api/projects/{PROJECT_ID}/short_info"),
            ("unread count", "/api/notifications/unread-count")]:
        check(name, req("GET", path, at))

    print("== shift start ==")
    check("status_v2 pre-check", req("GET", "/api/mobile/work_shift/status_v2", at))
    check("selector/project", req("GET",
          f"/api/selector/project?assigned_user_ids[]={uid}&statuses[]=active", at))
    gen = check("generate", req("POST", "/api/mobile/work_shift/generate", at, {
        "device_id": DEVICE_ID, "project_id": PROJECT_ID,
        "start_time": iso(), "state_payload": state_payload(),
        "time_zone": "America/Anchorage",
    }), keep=True)
    if not gen:
        return 1
    sid = gen["work_shift_id"]
    check("update_info (shift start)", req("POST",
          "/api/mobile/device/update_info", at, update_info_body()))
    check("event app_state", req("POST", "/api/mobile/device/event/send", at,
          device_event("app_state", {"state": "foreground"})))

    print("== tracking loop (3 uploader ticks) ==")
    base_ms = int(time.time() * 1000)
    for tick in range(3):
        t_ms = base_ms + tick * 30_000
        check(f"tick{tick} device_state_sync", req("POST",
              "/api/mobile/device/event/send", at,
              device_event("device_state_sync",
                           {**state_payload(), "resource_snapshot": None})))
        check(f"tick{tick} data_upload", req("POST",
              "/api/mobile/device/event/send", at,
              device_event("data_upload",
                           {"timestamp": t_ms, "data": {"max_id": tick * 4}})))
        check(f"tick{tick} gps", req("POST",
              "/api/mobile/sensor/batch_upload", at,
              {"records": [gps_record(sid, t_ms)]}))
        check(f"tick{tick} wifi", req("POST",
              "/api/mobile/sensor/batch_upload", at,
              {"records": [wifi_record(sid)]}))
        check(f"tick{tick} ble", req("POST",
              "/api/mobile/sensor/batch_upload", at,
              {"records": [ble_record(sid)]}))
        check(f"tick{tick} motionActivity", req("POST",
              "/api/mobile/sensor/batch_upload", at,
              {"records": [motion_record(sid, t_ms)]}))
    check("status_v2 poll", req("GET", "/api/mobile/work_shift/status_v2", at))
    check("recent shifts", req("GET",
          "/api/work_shift/?page=1&size=5&sort_by=start_time&sort_type=desc"
          "&timezone=America/Anchorage", at))
    check("earning_progress", req("GET",
          f"/api/work_shift/{sid}/earning_progress", at), keep=True)

    print("== break ==")
    check("pause", req("POST", "/api/mobile/work_shift/pause", at,
          {"work_shift_id": sid, "button_pressed_time": iso()}))
    time.sleep(1)
    check("resume", req("POST", "/api/mobile/work_shift/resume", at,
          {"work_shift_id": sid, "button_pressed_time": iso()}))

    print("== clock-out ==")
    check("finalize_v2", req("POST", "/api/mobile/work_shift/finalize_v2", at,
          [{"work_shift_id": sid, "end_time": iso(),
            "state_payload": state_payload(), "data_complete": True}]))
    check("status_v2 after finalize", req("GET",
          "/api/mobile/work_shift/status_v2", at), keep=True)

    print("== post-shift views ==")
    check("recent shifts", req("GET",
          "/api/work_shift/?page=1&size=5&sort_by=start_time&sort_type=desc"
          "&timezone=America/Anchorage", at))
    check("earnings list", req("GET", "/api/earnings/", at))
    check("balance", req("GET", "/api/earnings/balance/", at), keep=True)
    check("totals-by-rate-type", req("GET",
          "/api/earnings/totals-by-rate-type/", at))
    check("notifications list", req("GET",
          "/api/notifications/list?page=1&size=10&sort_type=desc", at))

    print("== logout ==")
    check("device unlink", req("POST", "/api/mobile/device/unlink", at,
          {"device_id": DEVICE_ID}))
    check("logout", req("POST", "/api/auth/logout", at,
          {"refresh_token": rt}))
    check("refresh after logout (expect 401)",
          req("POST", "/api/auth/refresh", json_body={"refresh_token": rt}),
          expect=401)

    print()
    if failures:
        print(f"{len(failures)} FAILURES:")
        for name, status, body in failures:
            print(f"  {name}: {status} {body!r}")
        return 1
    print("ALL STEPS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
