"""Shared validation rules. Imported by scripts/validate.py (batch) and the Lambda write path (per request)."""
import json
import re
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


def load_record_validator(schema_path: Path = SCHEMA_PATH) -> Draft202012Validator:
    return Draft202012Validator(json.loads(schema_path.read_text()))


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


def validate_record(record: dict, validator: Draft202012Validator) -> list[Finding]:
    """Per-record rules: schema first, then business rules only if the schema passes.
    Safe to call from the write Lambda."""
    schema_findings = check_schema(record, validator)
    if schema_findings:
        return schema_findings
    return check_armor(record)


def check_duplicate_stats(records: list[dict]) -> list[Finding]:
    """Batch-only: needs the full dataset. Do not call from the write Lambda."""
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


def check_weapons_against_source(records: list[dict], source: dict) -> list[Finding]:
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
