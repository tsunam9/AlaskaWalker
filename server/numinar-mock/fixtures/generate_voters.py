#!/usr/bin/env python3
"""Generate deterministic, Alaska-plausible voter fixtures."""

import json
import os
import random

FIRST = ["Avery", "Jordan", "Morgan", "Riley", "Casey", "Taylor", "Quinn", "Skyler", "Rowan", "Parker", "Harper", "Cameron"]
LAST = ["Williams", "Johnson", "Smith", "Nelson", "Brown", "Davis", "Miller", "Wilson", "Anderson", "Thomas", "Moore", "Martin"]
STREETS = ["Northern Lights Blvd", "Muldoon Rd", "Lake Otis Pkwy", "Boniface Pkwy", "Tudor Rd", "Minnesota Dr", "Debarr Rd", "Rabbit Creek Rd"]


def generate(count=240):
    rng = random.Random(20260922)
    rows = []
    for i in range(count):
        household = i // 2
        street_index = household % len(STREETS)
        number = 100 + household * 3
        lat = round(61.171 + (household % 20) * 0.0021, 6)
        lng = round(-149.913 + (household // 20) * 0.0057, 6)
        party = ["Republican", "Democrat", "Nonpartisan", "Undeclared"][i % 4]
        voter_id = f"voter_{i + 1:04d}"
        row = {
            "id": voter_id,
            "house_hold_id": f"household_{household + 1:04d}",
            "first_name": FIRST[i % len(FIRST)],
            "middle_name": "A" if i % 3 == 0 else "",
            "last_name": LAST[household % len(LAST)],
            "name_suffix": "",
            "rnc_reg_id": f"AKRNC{i + 100000}",
            "jurisdiction_voter_id": f"AKJ{i + 200000}",
            "state_voter_id": f"AKS{i + 300000}",
            "data_source_id": f"AKD{i + 400000}",
            "registration_address_1": f"{number} {STREETS[street_index]}",
            "registration_address_2": f"Apt {i % 8 + 1}" if i % 11 == 0 else "",
            "registration_address_city": "Anchorage",
            "registration_address_state": "AK",
            "registration_address_zip_5": f"995{(i % 20) + 1:02d}",
            "registration_address_latitude": lat,
            "registration_address_longitude": lng,
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


if __name__ == "__main__":
    path = os.path.join(os.path.dirname(__file__), "voters.json")
    with open(path, "w") as handle:
        json.dump({"voters": generate()}, handle, indent=2)
    print(path)
