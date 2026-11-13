#!/usr/bin/env python3
"""Convert flat source aircraft JSON (Air Action Weekly 1937) to schema_version 1 records.

Usage:
  python scripts/import_source.py data/import/aircraft_of_north_america.json data/aircraft.json
Then:
  python scripts/validate.py data/aircraft.json --source data/import/aircraft_of_north_america.json
"""
import json
import re
import sys
from pathlib import Path

ENGINE_COUNT = re.compile(r"\(x(\d+)\)")
WEAPON_TYPE = {"machine gun": "machine_gun", "cannon": "cannon"}


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def inches(text):
    m = re.search(r"(\d+)\s*ft\.?(?:,?\s*(\d+)\s*in\.?)?", text)
    if not m:
        raise ValueError(f"cannot parse dimension: {text!r}")
    return int(m.group(1)) * 12 + int(m.group(2) or 0)


def engines(src):
    m = ENGINE_COUNT.search(src["engine"])
    count = int(m.group(1)) if m else 1
    name = ENGINE_COUNT.sub("", src["engine"]).strip()
    if src["engine_hp"] % count:
        raise ValueError(f"{src['name']}: engine_hp {src['engine_hp']} not divisible by {count}")
    return [{"name": name, "count": count, "hp_each": src["engine_hp"] // count}]


def weapons(src):
    groups = []
    for g in src["weapons"]:
        for _ in range(g["count"]):
            groups.append({"name": g["name"], "caliber": g["caliber"], "type": WEAPON_TYPE[g["type"]]})

    out = []
    for lo in src["game_stats"]["weapon_loadout"]:
        idx = next((i for i, g in enumerate(groups) if g["caliber"] == lo["caliber"]), None)
        if idx is not None:
            g = groups.pop(idx)
            out.append({**g, "arc": lo["arc"], "mass_lbs": lo["mass_lbs"]})
        elif lo["caliber"] is None:
            out.append({"name": "Rear turret mount", "caliber": None, "type": "turret_mount",
                        "arc": lo["arc"], "mass_lbs": lo["mass_lbs"]})
        else:
            raise ValueError(f"{src['name']}: loadout caliber {lo['caliber']} has no weapon group")
    if groups:
        raise ValueError(f"{src['name']}: weapon groups not in loadout: {groups}")
    return out


def stat(src, key):
    return {"value": src["game_stats"][key], "mass_lbs": src["game_stats"][f"{key}_mass_lbs"]}


def convert(src, document):
    p, d, g = src["performance"], src["dimensions"], src["game_stats"]
    return {
        "id": slugify(src["name"]),
        "schema_version": 1,
        "name": src["name"],
        "class": src["class"],
        "propulsion": src["propulsion"],
        "manufacturer": {"name": src["manufacturer"], "location": src["manufacturer_location"]},
        "engines": engines(src),
        "dimensions": {
            "wingspan_in": inches(d["wing_span"]),
            "length_in": inches(d["length"]),
            "height_in": inches(d["height"]),
            "length_excludes_prop": "excluding prop" in d["length"],
        },
        "performance": {
            "loaded_weight_lbs": p["loaded_weight_lbs"],
            "service_ceiling_ft": p["service_ceiling_ft"],
            "range_miles": p["range_miles"],
            "max_speed_mph": p["max_speed_mph"],
            "max_accel_ft_s": p["max_accel_ft_per_sec"],
            "max_decel_ft_s": p["max_decel_ft_per_sec"],
        },
        "weapons": weapons(src),
        "armor": {
            "locations": g["armor"],
            "total_points": g["armor_points_total"],
            "mass_lbs": g["armor_points_mass_lbs"],
        },
        "game_stats": {
            "base_target_number": stat(src, "base_target_number"),
            "maximum_speed": stat(src, "maximum_speed"),
            "maximum_gs": stat(src, "maximum_gs"),
            "acceleration_rate": stat(src, "acceleration_rate"),
        },
        "source": {"document": document, "edition": None},
        "visibility": "default",
        "owner_id": None,
        "version": 1,
    }


def main():
    src_path, out_path = Path(sys.argv[1]), Path(sys.argv[2])
    data = json.loads(src_path.read_text())
    records = [convert(a, data["source"]) for a in data["aircraft"]]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"aircraft": records}, indent=2) + "\n")
    print(f"wrote {len(records)} records to {out_path}")


if __name__ == "__main__":
    main()
