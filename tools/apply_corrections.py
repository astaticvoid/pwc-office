#!/usr/bin/env python3
"""
apply_corrections.py — apply corrections from data/corrections.json to data files.

Always run validate_corrections.py first — it catches stale corrections
(the 'old' value no longer present) before this script would otherwise
silently skip them. This script also refuses to skip silently itself: any
correction whose 'old' value isn't found is collected as a miss and fails
the run, so a stale/misapplied correction can never pass unnoticed.

Usage: python3 tools/apply_corrections.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"
CORRECTIONS = DATA / "corrections.json"

_misses: list[str] = []


def _apply_replace(path: Path, corrections: list, locate, describe, on_applied=None):
    """Generic 'find old substring, replace with new' applier for a list of
    corrections against one JSON file. `locate(data, c)` returns the mutable
    container to correct plus its field name (container, field), or None if
    not found. `describe(c)` returns a short id string for logging.
    `on_applied(container, c)`, if given, runs after a successful replace —
    e.g. to stamp provenance metadata alongside the corrected field."""
    if not corrections:
        return
    data = json.loads(path.read_text())
    applied = 0
    for c in corrections:
        located = locate(data, c)
        if located is None:
            _misses.append(f"{c['id']}: target not found")
            continue
        container, field = located
        current = container.get(field, "")
        if c["old"] not in current:
            _misses.append(f"{c['id']}: old value not found in {describe(c)}")
            continue
        container[field] = current.replace(c["old"], c["new"], 1)
        if on_applied:
            on_applied(container, c)
        applied += 1
        print(f"  {c['id']}: {describe(c)}")
    if applied:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        print(f"  Applied {applied} correction(s) → {path}")


def _apply_by_date(corrections: list, mutate, describe=None):
    """Generic date-keyed applier across monthly data/lectionary/*.json files.
    `mutate(day, c)` mutates one day's dict in place and returns True if
    applied, False if stale/not-found (misses are recorded by the caller's
    mutate function for a specific message, or here generically if it just
    returns False)."""
    if not corrections:
        return
    applied = 0
    by_month: dict[str, list] = {}
    for c in corrections:
        by_month.setdefault(c["date"][:7], []).append(c)
    for month, month_corrections in by_month.items():
        path = DATA / "lectionary" / f"{month}.json"
        if not path.exists():
            for c in month_corrections:
                _misses.append(f"{c['id']}: month file {month}.json not found")
            continue
        data = json.loads(path.read_text())
        changed = False
        for c in month_corrections:
            day = data.get(c["date"])
            if day is None:
                _misses.append(f"{c['id']}: date {c['date']} not found")
                continue
            if mutate(day, c):
                applied += 1
                changed = True
                print(f"  {c['id']}: {describe(c) if describe else c['date']}")
            else:
                _misses.append(f"{c['id']}: {describe(c) if describe else c['date']} — old value mismatch")
        if changed:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    if applied:
        print(f"  Applied {applied} correction(s)")


def main():
    if not CORRECTIONS.exists():
        print("No corrections.json found — nothing to apply.")
        return

    corrections = json.loads(CORRECTIONS.read_text())

    # Office text corrections — whole-field replace (old == entire field value).
    if corrections.get("office_text"):
        # Stage 3, the last of the offices chain: reads the normalized artifact
        # and writes the file everything else consumes. Because the input is a
        # separate artifact, re-running this is idempotent — it re-derives from
        # normalized output rather than correcting already-corrected text (#48).
        path = DATA / "build" / "offices.2-normalized.json"
        out_path = DATA / "offices.json"
        data = json.loads(path.read_text())
        applied = 0
        for c in corrections["office_text"]:
            office = data.get(c["office"])
            if office and office.get(c["field"]) == c.get("old"):
                office[c["field"]] = c["new"]
                applied += 1
                print(f"  {c['id']}: {c['office']}.{c['field']}")
            else:
                _misses.append(f"{c['id']}: {c['office']}.{c['field']} mismatch")
        # Written unconditionally: this is the artifact the app, the manifest and
        # the integrity check read, so it must exist and must be derived from the
        # normalized input even when no correction applies.
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        if applied:
            print(f"  Applied {applied} office text corrections → {out_path}")

    # Psalter corrections — substring replace within one psalm's text, tagged
    # with source_corrections provenance for entries that carry a reason.
    def _stamp_source_correction(psalm, c):
        if "reason" not in c:
            return
        entry = {"original": c["old"], "corrected": c["new"], "reason": c["reason"]}
        if "verse" in c:
            entry = {"verse": c["verse"], **entry}
        psalm.setdefault("source_corrections", []).append(entry)

    if corrections.get("psalter"):
        _apply_replace(
            DATA / "psalter.json", corrections["psalter"],
            locate=lambda data, c: (
                (data[pnum], "text") if (pnum := str(c["psalm"])) in data else None
            ),
            describe=lambda c: f"Psalm {c['psalm']}",
            on_applied=_stamp_source_correction,
        )

    # FATS (saint biography) corrections — substring replace within one field.
    if corrections.get("fats"):
        path = DATA / "fats" / "saints.json"
        if path.exists():
            _apply_replace(
                path, corrections["fats"],
                locate=lambda data, c: (
                    (data[skey], c["field"])
                    if (skey := c.get("saint") or c.get("saint_key")) in data and c.get("field")
                    else None
                ),
                describe=lambda c: f"{c.get('saint') or c.get('saint_key')}.{c.get('field')}",
            )

    # Lectionary citation corrections — one indexed lesson within a day's office.
    def _mutate_citation(day, c):
        office = day.get(c["office"], {})
        lessons = office.get("lessons", [])
        idx = c.get("index", 0)
        if idx >= len(lessons):
            return False
        lesson = lessons[idx]
        actual = lesson.get("citation", lesson) if isinstance(lesson, dict) else lesson
        if actual != c.get("old"):
            return False
        if isinstance(lesson, dict):
            lesson["citation"] = c["new"]
        else:
            lessons[idx] = c["new"]
        return True

    _apply_by_date(
        corrections.get("lectionary_citations", []), _mutate_citation,
        describe=lambda c: f"{c['date']}/{c['office']}",
    )

    # Lectionary lesson-list corrections — whole lessons list for a day's office
    # (CSV row-level errors: missing separators, merged optional markers, etc.).
    def _mutate_lessons(day, c):
        office = day.get(c["office"], {})
        if office.get("lessons") != c.get("old"):
            return False
        office["lessons"] = c["new"]
        return True

    _apply_by_date(
        corrections.get("lectionary_lessons", []), _mutate_lessons,
        describe=lambda c: f"{c['date']}/{c['office']}",
    )

    # Lectionary day-level field corrections (name / rank / colour) —
    # whole-value replace, same shape as office_text but keyed by date.
    for category, field in (
        ("lectionary_names", "name"),
        ("lectionary_ranks", "rank"),
        ("lectionary_colours", "colour"),
    ):
        def _mutate_field(day, c, field=field):
            if day.get(field, "") != c.get("old"):
                return False
            day[field] = c["new"]
            return True

        _apply_by_date(
            corrections.get(category, []), _mutate_field,
            describe=lambda c, field=field: f"{c['date']}.{field}",
        )

    # Lectionary notes corrections — currently only 'clear' (drop a garbled,
    # unparseable note). Checked for staleness the same way as everything
    # else: there must be something present to clear.
    def _mutate_notes(day, c):
        if c.get("action") != "clear" or not day.get("notes"):
            return False
        day.pop("notes", None)
        return True

    _apply_by_date(
        corrections.get("lectionary_notes", []), _mutate_notes,
        describe=lambda c: f"{c['date']}.notes",
    )

    if _misses:
        print(f"\n{len(_misses)} correction(s) failed to apply:", file=sys.stderr)
        for m in _misses:
            print(f"  {m}", file=sys.stderr)
        sys.exit(1)

    print("Done.")


if __name__ == "__main__":
    main()
