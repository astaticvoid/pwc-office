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


def validate_office_text(corrections: list, data: dict) -> list[str]:
    errors = []
    for c in corrections:
        office = data.get(c["office"])
        if office is None:
            errors.append(f"{c['id']}: office '{c['office']}' not found")
            continue
        field = office.get(c["field"])
        if field is None:
            errors.append(f"{c['id']}: field '{c['field']}' not in office")
            continue
        # field is a string (title, subtitle) — check if old matches
        if field != c.get("old"):
            errors.append(f"{c['id']}: old value mismatch in {c['office']}.{c['field']}")
    return errors


def validate_lectionary_citation(corrections: list) -> list[str]:
    errors = []
    for c in corrections:
        month = c["date"][:7]
        path = DATA / "lectionary" / f"{month}.json"
        if not path.exists():
            errors.append(f"{c['id']}: month file {month}.json not found")
            continue
        month_data = json.loads(path.read_text())
        day = month_data.get(c["date"])
        if day is None:
            errors.append(f"{c['id']}: date {c['date']} not found")
            continue
        office = day.get(c["office"], {})
        lessons = office.get("lessons", [])
        if c.get("index", 0) >= len(lessons):
            errors.append(f"{c['id']}: lesson index {c.get('index')} out of range")
            continue
        lesson = lessons[c["index"]]
        actual = lesson.get("citation", lesson) if isinstance(lesson, dict) else lesson
        if actual != c.get("old"):
            errors.append(f"{c['id']}: old value mismatch: {actual!r} != {c['old']!r}")
    return errors


def main():
    if not CORRECTIONS.exists():
        print("No corrections.json found — nothing to validate.")
        return

    corrections = json.loads(CORRECTIONS.read_text())
    errors = []

    # Office text corrections
    if "office_text" in corrections:
        offices = json.loads((DATA / "offices.json").read_text())
        errors.extend(validate_office_text(corrections["office_text"], offices))

    # Lectionary citation corrections
    if "lectionary_citations" in corrections:
        errors.extend(validate_lectionary_citation(corrections["lectionary_citations"]))

    if errors:
        print(f"{len(errors)} stale/invalid correction(s):", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        sys.exit(1)

    print(f"All corrections validated.")


if __name__ == "__main__":
    main()
