#!/usr/bin/env python3
"""
apply_corrections.py — apply corrections from data/corrections.json to data files.

Always run validate_corrections.py first.

Usage: python3 tools/apply_corrections.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"
CORRECTIONS = DATA / "corrections.json"


def set_at_path(obj, path: list, value):
    for key in path[:-1]:
        if isinstance(obj, list):
            obj = obj[int(key)]
        else:
            obj = obj[key]
    last = path[-1]
    if isinstance(obj, list):
        obj[int(last)] = value
    else:
        obj[last] = value


def main():
    if not CORRECTIONS.exists():
        print("No corrections.json found — nothing to apply.")
        return

    corrections = json.loads(CORRECTIONS.read_text())

    # Office text corrections
    if "office_text" in corrections:
        path = DATA / "offices.json"
        data = json.loads(path.read_text())
        applied = 0
        for c in corrections["office_text"]:
            office = data.get(c["office"])
            if office and office.get(c["field"]) == c.get("old"):
                office[c["field"]] = c["new"]
                applied += 1
                print(f"  {c['id']}: {c['office']}.{c['field']}")
        if applied:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
            print(f"  Applied {applied} office text corrections → {path}")

    # Lectionary citation corrections
    if "lectionary_citations" in corrections:
        applied = 0
        for c in corrections["lectionary_citations"]:
            month = c["date"][:7]
            path = DATA / "lectionary" / f"{month}.json"
            if not path.exists():
                continue
            data = json.loads(path.read_text())
            day = data.get(c["date"])
            if day:
                office = day.get(c["office"], {})
                lessons = office.get("lessons", [])
                idx = c.get("index", 0)
                if idx < len(lessons):
                    lesson = lessons[idx]
                    actual = lesson.get("citation", lesson) if isinstance(lesson, dict) else lesson
                    if actual == c.get("old"):
                        if isinstance(lesson, dict):
                            lesson["citation"] = c["new"]
                        else:
                            lessons[idx] = c["new"]
                        applied += 1
                        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
                        print(f"  {c['id']}: {c['date']}/{c['office']}")
        if applied:
            print(f"  Applied {applied} lectionary corrections")

    print("Done.")


if __name__ == "__main__":
    main()
