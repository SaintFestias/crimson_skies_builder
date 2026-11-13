#!/usr/bin/env python3
"""Batch validation of normalized aircraft records. Rules live in src/validators.py.

Usage:
  python scripts/validate.py data/aircraft.json
  python scripts/validate.py data/aircraft.json --source data/import/aircraft_of_north_america.json
  python scripts/validate.py data/aircraft.json --strict   # warnings also fail

Exit codes: 0 clean, 1 errors (or any finding with --strict).
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from validators import (  # noqa: E402
    Finding, load_record_validator, validate_record,
    check_duplicate_stats, check_weapons_against_source,
)


def load_records(path: Path) -> list[dict]:
    data = json.loads(path.read_text())
    return data["aircraft"] if isinstance(data, dict) else data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("records", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    records = load_records(args.records)
    validator = load_record_validator()
    findings: list[Finding] = []

    for rid, n in Counter(r.get("id") for r in records).items():
        if n > 1:
            findings.append(Finding("error", str(rid), "duplicate-id", f"appears {n} times"))

    valid = []
    for r in records:
        f = validate_record(r, validator)
        findings.extend(f)
        if not any(x.level == "error" for x in f):
            valid.append(r)

    findings.extend(check_duplicate_stats(valid))
    if args.source:
        findings.extend(check_weapons_against_source(valid, json.loads(args.source.read_text())))

    for f in findings:
        print(f"[{f.level.upper()}] {f.record} ({f.rule}): {f.message}")

    errors = [f for f in findings if f.level == "error"]
    warnings = [f for f in findings if f.level == "warning"]
    print(f"\n{len(records)} records, {len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors or (args.strict and warnings) else 0


if __name__ == "__main__":
    sys.exit(main())
