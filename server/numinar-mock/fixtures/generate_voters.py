#!/usr/bin/env python3
"""Generate deterministic synthetic voters on the Anchorage shift walklist."""

import argparse
import json
import re
from pathlib import Path

FIRST = ["Avery", "Jordan", "Morgan", "Riley", "Casey", "Taylor", "Quinn", "Skyler", "Rowan", "Parker", "Harper", "Cameron"]
LAST = ["Williams", "Johnson", "Smith", "Nelson", "Brown", "Davis", "Miller", "Wilson", "Anderson", "Thomas", "Moore", "Martin"]

HERE = Path(__file__).resolve().parent
WALKLIST_PATH = HERE / "walklists" / "anchorage-shift-100.json"
WALKSERVER_UPLOAD_PATH = HERE / "walklists" / "anchorage-shift-100-upload.json"
PROJECT_ID = "project_canvass_001"
WALKLIST_NAME = "Anchorage Shift Test - 100 Doors"
VOTER_PREFIX = "shift26_voter_"
HOUSEHOLD_PREFIX = "shift26_household_"


def load_walklist(path=WALKLIST_PATH):
    with Path(path).open(encoding="utf-8") as handle:
        walklist = json.load(handle)
    houses = walklist.get("houses") or []
    if not houses:
        raise ValueError(f"walklist has no houses: {path}")
    return walklist


def address_fields(address):
    """Split the OSM display address into Numinar's address columns."""
    parts = [part.strip() for part in str(address).split(",") if part.strip()]
    line_1 = parts[0]
    tail = " ".join(parts[1:])
    zip_match = re.search(r"\b(\d{5})(?:-\d{4})?\b", tail)
    return line_1, "Anchorage", zip_match.group(1) if zip_match else "99503"


def household_slots(voter_count, household_count):
    """Keep voters adjacent while distributing them across every house."""
    base, extra = divmod(voter_count, household_count)
    slots = []
    for household in range(household_count):
        slots.extend([household] * (base + (1 if household < extra else 0)))
    return slots


def generate(count=240, walklist_path=WALKLIST_PATH):
    walklist = load_walklist(walklist_path)
    houses = walklist["houses"]
    if count < len(houses):
        raise ValueError(
            f"count must be at least the {len(houses)} walklist households"
        )

    # The names and demographics are synthetic. Only the public OSM addresses
    # and coordinates are real, so the stock client gets a realistic map without
    # introducing voter PII into the repository.
    rows = []
    slots = household_slots(count, len(houses))
    for i, household in enumerate(slots):
        house = houses[household]
        line_1, city, zip_5 = address_fields(house["address"])
        coordinate = house["locationHint"]
        party = ["Republican", "Democrat", "Nonpartisan", "Undeclared"][i % 4]
        voter_id = f"{VOTER_PREFIX}{i + 1:04d}"
        row = {
            "id": voter_id,
            "house_hold_id": f"{HOUSEHOLD_PREFIX}{household + 1:04d}",
            "first_name": FIRST[i % len(FIRST)],
            "middle_name": "A" if i % 3 == 0 else "",
            "last_name": LAST[household % len(LAST)],
            "name_suffix": "",
            "rnc_reg_id": f"AKRNC{i + 100000}",
            "jurisdiction_voter_id": f"AKJ{i + 200000}",
            "state_voter_id": f"AKS{i + 300000}",
            "data_source_id": f"AKD{i + 400000}",
            "registration_address_1": line_1,
            "registration_address_2": "",
            "registration_address_city": city,
            "registration_address_state": "AK",
            "registration_address_zip_5": zip_5,
            "registration_address_latitude": round(float(coordinate["latitude"]), 7),
            "registration_address_longitude": round(float(coordinate["longitude"]), 7),
            "registered_party_roll_up": party,
            "official_party": party,
            "rnc_calc_party": party,
            "voter_status": "A" if i % 17 else "I",
            "permanent_absentee": "Y" if i % 9 == 0 else "N",
            "voter_frequency_general": i % 5,
            "voter_frequency_primary": (i + 2) % 5,
            "abev_election_ballot_status": 2 if i % 13 == 0 else 5,
            "abev_elections": [{"id": "election_2026", "name": "2026 General", "ballot_status": 2 if i % 13 == 0 else 5}],
            "age": 18 + i % 68,
            "sex": "F" if i % 2 else "M",
            "ethnicity_modeled_ethnic_group_name": "Unknown",
            "cell_phone_area_code": "907",
            "cell_phone_number": f"907555{1000 + i:04d}",
            "email": f"voter{i + 1}@example.test",
            "is_in_list": True,
            "has_interaction": False,
        }
        for year in range(8, 25):
            row[f"vh_{year:02d}_g"] = 1 if (i + year) % 3 else 0
            row[f"vh_{year:02d}_p"] = 3 if (i + year) % 4 == 0 else 0
            row[f"vh_{year:02d}_pp"] = 3 if (i + year) % 5 == 0 else 0
        rows.append(row)
    return rows


def generate_walkserver_upload(count=240, walklist_path=WALKLIST_PATH):
    """Build the exact payload accepted by pulsar-route POST /api/walklist."""
    walklist = load_walklist(walklist_path)
    voters = generate(count, walklist_path)
    voters_by_household = {}
    for voter in voters:
        voters_by_household.setdefault(voter["house_hold_id"], []).append(voter)

    addresses = []
    for index, house in enumerate(walklist["houses"], 1):
        household_id = f"{HOUSEHOLD_PREFIX}{index:04d}"
        coordinate = house["locationHint"]
        addresses.append({
            "aid": household_id,
            "street": address_fields(house["address"])[0],
            "city": "Anchorage",
            "lat": round(float(coordinate["latitude"]), 7),
            "lng": round(float(coordinate["longitude"]), 7),
            "leg": index,
            "knocked": False,
            "has_voter": True,
            "voters": [
                {
                    "first_name": voter["first_name"],
                    "age": voter["age"],
                    "gender": voter["sex"],
                }
                for voter in voters_by_household[household_id]
            ],
        })

    return {
        "lists": [{
            "wid": PROJECT_ID,
            "name": WALKLIST_NAME,
            "form_id": "survey_canvass_001",
            "created_at": walklist["generatedAt"],
            "updated_at": walklist["generatedAt"],
            "addresses": addresses,
        }]
    }


def write_json(path, value):
    with Path(path).open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2)
        handle.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-walkserver-upload", action="store_true")
    args = parser.parse_args()
    if args.write_walkserver_upload:
        write_json(WALKSERVER_UPLOAD_PATH, generate_walkserver_upload())
        print(WALKSERVER_UPLOAD_PATH)
    else:
        path = HERE / "voters.json"
        write_json(path, {"voters": generate()})
        print(path)
