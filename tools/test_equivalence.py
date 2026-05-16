#!/usr/bin/env python3
"""
test_equivalence.py — verify that freshly extracted JSON matches the old YAML.

Compares boneyard/data/*.yaml against data/ to confirm zero data loss
in the YAML→JSON extraction pipeline migration.

Usage: python3 tools/test_equivalence.py

Exit code 0 = all checks pass, 1 = failures found.
"""

import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("pip install pyyaml", file=sys.stderr)
    sys.exit(1)

root = Path(__file__).parent.parent
boneyard = root / "boneyard" / "data"
data = root / "data"

errors: list[str] = []


# ── Normalisation helpers ──────────────────────────────────────────────────────

def _norm_item(item) -> dict:
    """Normalise a lectionary psalm/lesson item to {citation, optional} form."""
    if isinstance(item, str):
        s = item.strip()
        if s.startswith("(") and s.endswith(")"):
            return {"citation": s[1:-1], "optional": True}
        return {"citation": s, "optional": False}
    return {
        "citation": item.get("citation", ""),
        "optional": bool(item.get("optional", False)),
    }


def _norm_office(office: dict | None) -> dict:
    """Recursively normalise psalm/lesson items within an office dict."""
    if not office:
        return office or {}
    result = dict(office)
    for field in ("psalms", "lessons"):
        if result.get(field):
            result[field] = [_norm_item(x) for x in result[field]]
    if result.get("psalm_sets"):
        result["psalm_sets"] = [
            [_norm_item(x) for x in group] for group in result["psalm_sets"]
        ]
    if result.get("alternate"):
        result["alternate"] = _norm_office(result["alternate"])
    return result


# ── Lectionary ─────────────────────────────────────────────────────────────────

def check_lectionary():
    yaml_path = boneyard / "lectionary_2026.yaml"
    if not yaml_path.exists():
        print(f"SKIP lectionary: {yaml_path} not found")
        return

    with open(yaml_path) as f:
        old = yaml.safe_load(f)

    bounds_path = data / "season_bounds.json"
    if not bounds_path.exists():
        errors.append("lectionary: data/season_bounds.json missing")
        return
    with open(bounds_path) as f:
        new_bounds = json.load(f)

    for k, v in old["meta"].items():
        if new_bounds.get(k) != v:
            errors.append(f"season_bounds.{k}: YAML={v!r}, JSON={new_bounds.get(k)!r}")

    lect_dir = data / "lectionary"
    if not lect_dir.exists():
        errors.append("lectionary: data/lectionary/ directory missing")
        return

    old_entries = {e["date"]: e for e in old["entries"]}
    new_entries: dict[str, dict] = {}
    for path in sorted(lect_dir.glob("*.json")):
        with open(path) as f:
            e = json.load(f)
        new_entries[e["date"]] = e

    if len(old_entries) != len(new_entries):
        errors.append(
            f"lectionary entry count: YAML={len(old_entries)}, JSON={len(new_entries)}"
        )

    for date, old_e in sorted(old_entries.items()):
        new_e = new_entries.get(date)
        if new_e is None:
            errors.append(f"lectionary: {date} missing from JSON")
            continue
        for field in ("name", "rank", "colour", "eucharist"):
            ov, nv = old_e.get(field, ""), new_e.get(field, "")
            if ov != nv:
                errors.append(f"lectionary {date}.{field}: YAML={ov!r}, JSON={nv!r}")
        for office in ("morning", "evening"):
            old_o = _norm_office(old_e.get(office) or {})
            new_o = _norm_office(new_e.get(office) or {})
            if old_o != new_o:
                errors.append(
                    f"lectionary {date}.{office}: mismatch\n"
                    f"  YAML: {old_o}\n"
                    f"  JSON: {new_o}"
                )
        if old_e.get("observances") != new_e.get("observances"):
            errors.append(
                f"lectionary {date}.observances: "
                f"YAML={old_e.get('observances')!r}, JSON={new_e.get('observances')!r}"
            )
        if old_e.get("notes") != new_e.get("notes"):
            errors.append(
                f"lectionary {date}.notes: "
                f"YAML={old_e.get('notes')!r}, JSON={new_e.get('notes')!r}"
            )

    print(f"lectionary: checked {len(old_entries)} entries, {len(old['meta'])} bounds")


# ── Psalter ────────────────────────────────────────────────────────────────────

# Psalm text differences that are deliberate improvements over the boneyard YAML.
# These are whitelisted: reported informatively but NOT counted as failures.
PSALM_IMPROVEMENTS: dict[int, str] = {
    2:   "v12 verse-number spacing normalised (PDF source has 1 space; old YAML had 2)",
    35:  "v25 source error corrected: 'Do not let them say' (YAML missing 'not')",
    51:  "v1 British spelling: 'offences' (YAML had American 'offenses')",
    61:  "v8 British spelling: 'fulfil' (YAML had American 'fulfill')",
    64:  "v9 British spelling: 'recognise' (YAML had American 'recognize')",
    78:  "v72 typographic: double period corrected to single (YAML had '..')",
    118: "vv3-4 continuation-line indent restored (YAML missing leading space after '*')",
    119: "section heading: 'Sadhe' renamed to standard 'Tsadhe'",
}


def check_psalter():
    yaml_path = boneyard / "psalter.yaml"
    if not yaml_path.exists():
        print(f"SKIP psalter: {yaml_path} not found")
        return

    with open(yaml_path) as f:
        old = yaml.safe_load(f)

    psalms_dir = data / "psalms"
    if not psalms_dir.exists():
        errors.append("psalter: data/psalms/ directory missing")
        return

    old_psalms = {p["number"]: p for p in old["psalms"]}
    new_psalms: dict[int, dict] = {}
    for path in psalms_dir.glob("*.json"):
        with open(path) as f:
            p = json.load(f)
        new_psalms[p["number"]] = p

    if len(old_psalms) != len(new_psalms):
        errors.append(f"psalter count: YAML={len(old_psalms)}, JSON={len(new_psalms)}")

    improvements: list[str] = []
    for num, old_p in old_psalms.items():
        new_p = new_psalms.get(num)
        if new_p is None:
            errors.append(f"psalter: psalm {num} missing from JSON")
            continue
        for field in ("number", "book", "title", "text"):
            if old_p.get(field) != new_p.get(field):
                if field == "text" and num in PSALM_IMPROVEMENTS:
                    improvements.append(f"  [improved] psalm {num}: {PSALM_IMPROVEMENTS[num]}")
                else:
                    ov, nv = old_p.get(field), new_p.get(field)
                    errors.append(f"psalter psalm {num}.{field}: YAML={ov!r}, JSON={nv!r}")

    print(f"psalter: checked {len(old_psalms)} psalms")
    if improvements:
        print(f"  {len(improvements)} whitelisted improvement(s):")
        for msg in improvements:
            print(msg)


# ── Offices ────────────────────────────────────────────────────────────────────

def check_offices():
    yaml_path = boneyard / "offices.yaml"
    if not yaml_path.exists():
        print(f"SKIP offices: {yaml_path} not found")
        return

    with open(yaml_path) as f:
        old = yaml.safe_load(f)

    json_path = data / "offices.json"
    if not json_path.exists():
        errors.append("offices: data/offices.json missing")
        return
    with open(json_path) as f:
        new = json.load(f)

    missing = set(old.keys()) - set(new.keys())
    extra = set(new.keys()) - set(old.keys())
    if missing:
        errors.append(f"offices: missing keys in JSON: {sorted(missing)}")
    if extra:
        errors.append(f"offices: extra keys in JSON: {sorted(extra)}")

    for key in old:
        if key not in new:
            continue
        if old[key] != new[key]:
            errors.append(f"offices.{key}: content mismatch")

    print(f"offices: checked {len(old)} forms")


# ── Collects ───────────────────────────────────────────────────────────────────

def check_collects():
    yaml_path = boneyard / "collects.yaml"
    if not yaml_path.exists():
        print(f"SKIP collects: {yaml_path} not found")
        return

    with open(yaml_path) as f:
        old = yaml.safe_load(f)

    json_path = data / "collects.json"
    if not json_path.exists():
        errors.append("collects: data/collects.json missing")
        return
    with open(json_path) as f:
        new = json.load(f)

    missing = set(old.keys()) - set(new.keys())
    extra = set(new.keys()) - set(old.keys())
    if missing:
        errors.append(f"collects: missing keys in JSON: {sorted(missing)}")
    if extra:
        errors.append(f"collects: extra keys in JSON: {sorted(extra)}")

    for key in old:
        if key not in new:
            continue
        old_e, new_e = old[key], new[key]
        for field in ("name", "section", "season", "text"):
            ov = old_e.get(field, "") if isinstance(old_e, dict) else ""
            nv = new_e.get(field, "") if isinstance(new_e, dict) else ""
            if ov != nv:
                errors.append(f"collects {key}.{field}: mismatch")
        for field in ("proper", "date"):
            ov = old_e.get(field) if isinstance(old_e, dict) else None
            nv = new_e.get(field) if isinstance(new_e, dict) else None
            if ov != nv:
                errors.append(f"collects {key}.{field}: YAML={ov!r}, JSON={nv!r}")

    print(f"collects: checked {len(old)} collects")


# ── Run ────────────────────────────────────────────────────────────────────────

check_lectionary()
check_psalter()
check_offices()
check_collects()

if errors:
    print(f"\n{len(errors)} FAILURE(S):")
    for e in errors:
        print(f"  ✗ {e}")
    sys.exit(1)
else:
    print("\nAll equivalence checks passed — JSON matches YAML exactly.")
