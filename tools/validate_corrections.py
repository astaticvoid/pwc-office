#!/usr/bin/env python3
"""
validate_corrections.py — verify that corrections in data/corrections.json
still match the current data files.

Each correction has a target locator and an 'old' value that must exist in the
current data. Stale corrections (old value not found) exit non-zero.

Usage: python3 tools/validate_corrections.py [--strict]
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"
CORRECTIONS = DATA / "corrections.json"


def get_at_path(obj, path: list):
    """Navigate a JSON object by path segments (string keys or int indices)."""
    for key in path:
        if isinstance(obj, list):
            obj = obj[int(key)]
        elif isinstance(obj, dict):
            obj = obj[key]
        else:
            raise KeyError(f"Cannot index {type(obj).__name__} with {key!r}")
    return obj


def find_text_in_segments(segments, target_text):
    """Recursively search segments for exact text match, trying both nbsp and regular space."""
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        if seg.get("type") == "alternatives":
            for group in seg.get("groups", []):
                if find_text_in_segments(group.get("segments", []), target_text):
                    return True
        elif seg.get("type") in ("response", "label", "leader"):
            t = seg.get("text", "")
            if t == target_text:
                return True
            if "\xa0" in t and target_text.replace(" ", "\xa0", 1) == t:
                return True
            if "\xa0" in target_text and t.replace("\xa0", " ") == target_text:
                return True
    return False


def validate_office_text(corrections: list, data: dict) -> list[str]:
    errors = []
    for c in corrections:
        cid = c["id"]
        office = data.get(c["office"])
        if office is None:
            errors.append(f"{cid}: office '{c['office']}' not found")
            continue
        field = office.get(c["field"])
        if field is None:
            errors.append(f"{cid}: field '{c['field']}' not in {c['office']}")
            continue
        old = c.get("old", "")
        if isinstance(field, str):
            if field != old and old not in field:
                errors.append(f"{cid}: old value mismatch in {c['office']}.{c['field']}")
        elif isinstance(field, list):
            if not find_text_in_segments(field, old):
                errors.append(f"{cid}: old value not found in {c['office']}.{c['field']} segments")
    return errors


def validate_lectionary_citation(corrections: list) -> list[str]:
    errors = []
    for c in corrections:
        cid = c["id"]
        month = c["date"][:7]
        path = DATA / "lectionary" / f"{month}.json"
        if not path.exists():
            errors.append(f"{cid}: month file {month}.json not found")
            continue
        month_data = json.loads(path.read_text())
        day = month_data.get(c["date"])
        if day is None:
            errors.append(f"{cid}: date {c['date']} not found")
            continue
        office = day.get(c["office"], {})
        lessons = office.get("lessons", [])
        if c.get("index", 0) >= len(lessons):
            errors.append(f"{cid}: lesson index {c.get('index')} out of range")
            continue
        lesson = lessons[c["index"]]
        actual = lesson.get("citation", lesson) if isinstance(lesson, dict) else lesson
        if actual != c.get("old"):
            errors.append(f"{cid}: old value mismatch: {actual!r} != {c['old']!r}")
    return errors


def load_lectionary():
    lec = {}
    for f in sorted((DATA / "lectionary").glob("*.json")):
        lec.update(json.loads(f.read_text()))
    return lec


def validate_lectionary_field(corrections: list, field_name: str) -> list[str]:
    """Generic validator for lectionary date-level fields (names, ranks, colours)."""
    errors = []
    lectionary = load_lectionary()
    for c in corrections:
        cid = c["id"]
        day = lectionary.get(c["date"])
        if day is None:
            errors.append(f"{cid}: date {c['date']} not found")
            continue
        actual = day.get(field_name, "")
        if actual != c.get("old"):
            errors.append(f"{cid}: {field_name} mismatch: {actual!r} != {c['old']!r}")
    return errors


def validate_lectionary_notes(corrections: list) -> list[str]:
    errors = []
    lectionary = load_lectionary()
    for c in corrections:
        cid = c["id"]
        day = lectionary.get(c["date"])
        if day is None:
            errors.append(f"{cid}: date {c['date']} not found")
            continue
        notes = day.get("notes") or []
        action = c.get("action", "")
        if action == "clear":
            if notes:
                errors.append(f"{cid}: notes not empty (expected clear)")
        elif action == "set_type":
            if not notes:
                errors.append(f"{cid}: no notes to set type on")
                continue
            for n in notes:
                if isinstance(n, dict):
                    actual_type = n.get("type", "")
                    if actual_type != c.get("old"):
                        errors.append(f"{cid}: note type mismatch: {actual_type!r} != {c['old']!r}")
                    break
    return errors


def validate_psalter(corrections: list) -> list[str]:
    errors = []
    psalter = json.loads((DATA / "psalter.json").read_text())
    for c in corrections:
        cid = c["id"]
        pnum = str(c["psalm"])
        psalm = psalter.get(pnum)
        if psalm is None:
            errors.append(f"{cid}: psalm {pnum} not found")
            continue
        ptext = psalm.get("text", "")
        action = c.get("action", "")
        if action == "replace":
            old = c.get("old", "")
            if old not in ptext:
                # Try nbsp variant
                if old.replace(" ", "\xa0") not in ptext:
                    errors.append(f"{cid}: old text not found in psalm {pnum}")
        elif action in ("insert_before", "insert_after"):
            marker = c.get("marker", "")
            if marker and marker not in ptext:
                errors.append(f"{cid}: marker not found in psalm {pnum}")
        elif action == "fix_v12":
            if "12 lest God be angry" not in ptext:
                errors.append(f"{cid}: v12 still missing from psalm {pnum}")
    return errors


def validate_fats(corrections: list) -> list[str]:
    errors = []
    fats = json.loads((DATA / "fats" / "saints.json").read_text())
    for c in corrections:
        cid = c["id"]
        action = c.get("action", "")
        if action == "rename_key":
            skey = c.get("saint_key")
            if skey is None:
                errors.append(f"{cid}: missing saint_key")
                continue
            if skey not in fats:
                errors.append(f"{cid}: saint key {skey!r} not found (already renamed?)")
        elif action is None and "field" in c:
            # Text fix within a saint field
            saint = fats.get(c.get("saint") or c.get("saint_key", ""))
            if saint is None:
                errors.append(f"{cid}: saint not found")
                continue
            field = c.get("field")
            val = saint.get(field, "")
            if c.get("old") not in val:
                errors.append(f"{cid}: old text not found in saint.{field}")
        else:
            # Unknown action — skip
            pass
    return errors


def main():
    if not CORRECTIONS.exists():
        print("No corrections.json found — nothing to validate.")
        return

    corrections = json.loads(CORRECTIONS.read_text())
    errors = []

    if corrections.get("office_text"):
        offices = json.loads((DATA / "offices.json").read_text())
        errors.extend(validate_office_text(corrections["office_text"], offices))

    if corrections.get("lectionary_citations"):
        errors.extend(validate_lectionary_citation(corrections["lectionary_citations"]))

    if corrections.get("lectionary_names"):
        errors.extend(validate_lectionary_field(corrections["lectionary_names"], "name"))

    if corrections.get("lectionary_ranks"):
        errors.extend(validate_lectionary_field(corrections["lectionary_ranks"], "rank"))

    if corrections.get("lectionary_colours"):
        errors.extend(validate_lectionary_field(corrections["lectionary_colours"], "colour"))

    if corrections.get("lectionary_notes"):
        errors.extend(validate_lectionary_notes(corrections["lectionary_notes"]))

    if corrections.get("psalter"):
        errors.extend(validate_psalter(corrections["psalter"]))

    if corrections.get("fats"):
        errors.extend(validate_fats(corrections["fats"]))

    if errors:
        print(f"{len(errors)} stale/invalid correction(s):", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        sys.exit(1)

    print("All corrections validated.")


if __name__ == "__main__":
    main()
