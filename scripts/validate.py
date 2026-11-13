#!/usr/bin/env python3
"""Validate normalized aircraft records.

Checks, in order:
  1. JSON Schema (draft 2020-12) against schemas/aircraft.v1.json
  2. Duplicate ids
  3. Armor location sum equals total_points (null counts as 0)
  4. Armor mass equals total_points x 3
  5. Identical dimensions and performance across records (possible copy error)
  6. Optional: weapons match the source file's weapon_loadout

Usage:
  pip install jsonschema
  python scripts/validate.py data/aircraft.json
  python scripts/validate.py data/aircraft.json --source data/import/aircraft_of_north_america.json
  python scripts/validate.py data/aircraft.json --strict   # warnings also fail

Exit codes: 0 clean, 1 errors (or any finding with --strict).
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "schemas" / "aircraft_v1.json"
MASS_PER_ARMOR_POINT = 3


@dataclass
class Finding:
    level: str   # "error" or "warning"
    record: str
    rule: str
    message: str


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def check_schema(record: dict, validator: Draft202012Validator) -> list[Finding]:
    rid = record.get("id", "<no id>")
    findings = []
    for err in sorted(validator.iter_errors(record), key=lambda e: list(e.absolute_path)):
        path = "/".join(str(p) for p in err.absolute_path) or "(root)"
        findings.append(Finding("error", rid, "json-schema", f"{path}: {err.message}"))
    return findings


def check_armor(record: dict) -> list[Finding]:
    rid = record["id"]
    armor = record["armor"]
    findings = []

    summed = sum(v or 0 for v in armor["locations"].values())
    if summed != armor["total_points"]:
        findings.append(Finding(
            "error", rid, "armor-sum",
            f"locations sum to {summed}, total_points is {armor['total_points']}",
        ))

    expected_mass = armor["total_points"] * MASS_PER_ARMOR_POINT
    if armor["mass_lbs"] != expected_mass:
        findings.append(Finding(
            "error", rid, "armor-mass",
            f"mass_lbs is {armor['mass_lbs']}, expected {expected_mass} "
            f"({armor['total_points']} points x {MASS_PER_ARMOR_POINT}). "
            "Confirm against the source before accepting.",
        ))
    return findings


def check_duplicate_stats(records: list[dict]) -> list[Finding]:
    groups = defaultdict(list)
    for r in records:
        key = json.dumps({"d": r["dimensions"], "p": r["performance"]}, sort_keys=True)
        groups[key].append(r["id"])

    findings = []
    for ids in groups.values():
        if len(ids) > 1:
            for rid in ids:
                others = ", ".join(i for i in ids if i != rid)
                findings.append(Finding(
                    "warning", rid, "duplicate-stats",
                    f"dimensions and performance identical to {others}. Possible copy error.",
                ))
    return findings


def check_weapons_against_source(records: list[dict], source_path: Path) -> list[Finding]:
    source = json.loads(source_path.read_text())
    source_by_id = {slugify(a["name"]): a for a in source["aircraft"]}

    findings = []
    for r in records:
        src = source_by_id.get(r["id"])
        if src is None:
            findings.append(Finding(
                "warning", r["id"], "source-match",
                "no matching source entry, weapon check skipped",
            ))
            continue

        expected = Counter(
            (w["caliber"], w["arc"], w["mass_lbs"])
            for w in src["game_stats"]["weapon_loadout"]
        )
        actual = Counter((w["caliber"], w["arc"], w["mass_lbs"]) for w in r["weapons"])
        if expected != actual:
            missing = list((expected - actual).elements())
            extra = list((actual - expected).elements())
            findings.append(Finding(
                "error", r["id"], "weapons-vs-source",
                f"weapons differ from source loadout. Missing: {missing or 'none'}. "
                f"Extra: {extra or 'none'}.",
            ))
    return findings


def load_records(path: Path) -> list[dict]:
    data = json.loads(path.read_text())
    return data["aircraft"] if isinstance(data, dict) else data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("records", type=Path, help="normalized aircraft JSON (array or {'aircraft': [...]})")
    parser.add_argument("--source", type=Path, help="original source JSON for the weapon cross-check")
    parser.add_argument("--strict", action="store_true", help="treat warnings as failures")
    args = parser.parse_args()

    records = load_records(args.records)
    validator = Draft202012Validator(json.loads(SCHEMA_PATH.read_text()))

    findings: list[Finding] = []

    id_counts = Counter(r.get("id") for r in records)
    for rid, n in id_counts.items():
        if n > 1:
            findings.append(Finding("error", str(rid), "duplicate-id", f"appears {n} times"))

    valid = []
    for r in records:
        schema_findings = check_schema(r, validator)
        if schema_findings:
            findings.extend(schema_findings)
        else:
            valid.append(r)
            findings.extend(check_armor(r))

    findings.extend(check_duplicate_stats(valid))

    if args.source:
        findings.extend(check_weapons_against_source(valid, args.source))

    for f in findings:
        print(f"[{f.level.upper()}] {f.record} ({f.rule}): {f.message}")

    errors = [f for f in findings if f.level == "error"]
    warnings = [f for f in findings if f.level == "warning"]
    print(f"\n{len(records)} records, {len(errors)} errors, {len(warnings)} warnings")

    if errors or (args.strict and warnings):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
