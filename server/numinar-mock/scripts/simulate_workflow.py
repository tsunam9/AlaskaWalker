#!/usr/bin/env python3
"""Simulate the recovered stock login-to-offline-drain workflow."""

import base64
import gzip
import json
import sys
import time
import urllib.parse

from test_api import Client, check, interaction_samples


def decompress_voters(encoded):
    columns = json.loads(gzip.decompress(base64.b64decode(encoded)).decode("utf-8"))
    keys = list(columns)
    return [{key: columns[key][index] for key in keys} for index in range(len(columns[keys[0]]))]


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:19002"
    client = Client(base)
    tokens = client.otp_login(); check(tokens["token_type"] == "Bearer", "passwordless login")
    status, userinfo, _ = client.request("GET", "/userinfo"); check(status == 200 and userinfo["sub"], "Auth0 userinfo")
    status, me, _ = client.request("GET", "/api/v1/me"); check(status == 200, "profile bootstrap")
    status, orgs, _ = client.request("GET", "/api/v1/my-orgs-mobile"); check(status == 200 and orgs, "organization bootstrap")
    client.org = orgs[0]["id"]
    status, org, _ = client.request("GET", "/api/v2/orgs/" + client.org); check(status == 200 and org["id"] == client.org, "organization select")
    status, projects, _ = client.request("GET", "/api/v3/projects"); check(status == 200, "project list")
    project = next(item for item in projects if item["outreach_type"] == "canvass")
    status, project, _ = client.request("GET", "/api/v3/projects/" + project["id"]); check(status == 200, "project select")
    params = urllib.parse.urlencode({"ignore_contacted": "false", "include_past_contacts": "true", "limit": 10000, "include_tags": "true", "compress": "true"})
    voter_path = f"/api/v2/mobile-app/projects/{project['id']}/voters?{params}"
    status, payload, _ = client.request("GET", voter_path); voters = decompress_voters(payload["voters_compressed"])
    check(status == 200 and voters, "compressed voter download")
    for tick in range(2):
        status, _, _ = client.request("POST", "/api/v1/canvassing-qa/tracking", {"project_id": project["id"], "latitude": 61.171 + tick * .0001, "longitude": -149.913, "device_id": "workflow-device", "device_geolocation_enabled": True, "device_geolocation_permission_status": "granted", "is_using_emulator": False})
        check(status == 200, f"QA beacon {tick + 1}")
    online = interaction_samples("workflow-online")[0]
    online["voter_id"] = voters[20]["id"]; online["household_id"] = voters[20]["house_hold_id"]
    status, result, _ = client.request("POST", "/api/v1/interactions/batch", [online]); check(status == 200 and result["inserted"] == 1, "online canvass submit")
    drain = []
    for index in range(10):
        voter = voters[30 + index]
        drain.append({"id": f"workflow-drain-{index}-{time.time_ns()}", "user_id": me["id"], "project_id": project["id"], "voter_id": voter["id"], "household_id": voter["house_hold_id"], "latitude": voter["registration_address_latitude"], "longitude": voter["registration_address_longitude"], "user_latitude": "61.171", "user_longitude": "-149.913", "disposition": "Not Home" if index % 2 else "canvassed", "survey_type": "canvass", "created_at": state_time(), "device_id": "workflow-device", "is_using_emulator": False, "device_geolocation_enabled": True, "device_geolocation_permission_status": "granted"})
    status, result, _ = client.request("POST", "/api/v1/interactions/batch", drain); check(status == 200 and result["accepted"] == 10, "offline drain batch of 10")
    status, refreshed, _ = client.request("GET", voter_path); refreshed_voters = decompress_voters(refreshed["voters_compressed"])
    touched = {online["voter_id"], *(item["voter_id"] for item in drain)}
    check(status == 200 and all(v["has_interaction"] for v in refreshed_voters if v["id"] in touched), "voter refresh reflects has_interaction")
    print("PASS: full stock workflow simulation")


def state_time():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


if __name__ == "__main__": main()
