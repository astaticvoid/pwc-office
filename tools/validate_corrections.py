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

from corrections_lib import ALL_OFFICES, check_office_text_across, resolve_offices

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"
# Intermediate pipeline artifacts. Deliberately outside data/, which is the
# published tree — anything under it is copied into dist/ by the data symlink.
BUILD = ROOT / ".build"
CORRECTIONS = DATA / "corrections.json"

# ADR 0005 declared three values and said the full schema lived in a JSON Schema
# file "checked into the repository alongside the manifest". That file was never
# written, and the field grew to six values unremarked. It stopped being merely
# untidy when ADR 0012 made `source` load-bearing: the QA rules decide which
# corrections may vouch for a deliberate line break by testing for the
# `pwc-errata-` prefix, so a typo here silently withdraws an exemption and the
# break it covered gets reported as a column wrap. An unchecked string cannot
# decide what a validator enforces.
PERMITTED_SOURCES = {
    "editorial":               "a project editorial decision, with no upstream error behind it",
    "acc-csv-error":           "an error in the ACC lectionary CSV",
    "pwc-pdf-error":           "an error in the printed Pray Without Ceasing PDF",
    "pdf-extraction-artifact": "an artifact of extraction rather than a defect in the source",
    "pwc-errata-ordinary":     "the errata for Ordinary Time (docs/errata/ordinary-time.md)",
    "pwc-errata-seasonal":     "the errata for the seasonal offices (docs/errata/seasonal.md)",
    "upstream-review":         "a correction from upstream review of the app, with no errata document behind it (ADR 0015)",
}

# The prefix ADR 0012's exemption keys on. Adding a source that starts with it
# grants the power to vouch for a line break, so it is named here rather than
# left implicit in two other files.
VOUCHING_PREFIX = "pwc-errata-"


def adr_numbers() -> set[str]:
    """The ADR numbers that exist as files in docs/adr/ (e.g. "0019").

    Excludes 0000-template.md: the template is not an ADR, so citing it must
    not resolve.
    """
    adr_dir = ROOT / "docs" / "adr"
    if not adr_dir.is_dir():
        return set()
    return {p.name[:4] for p in adr_dir.glob("[0-9][0-9][0-9][0-9]-*.md")
            if p.name[:4] != "0000"}


def validate_provenance(corrections: dict) -> list[str]:
    """Every correction carries a known `source`, a unique `id`, and a warrant.

    ADR 0022: the manifest is the only authorized divergence from the source
    text, so every entry must name what authorizes it — a `reason` always, and
    an `adr` when an ADR settled it (`upstream-review`, the source whose whole
    point is a review ruling, is required to). An `adr` that cannot be
    followed to a real ADR file is not a citation.
    """
    errors = []
    seen: dict = {}
    known_adrs = adr_numbers()
    for category, entries in corrections.items():
        if not isinstance(entries, list):
            continue          # "version" and any future scalar metadata
        for i, entry in enumerate(entries):
            where = f"{category}[{i}]"
            cid = entry.get("id")
            if not cid:
                errors.append(f"{where}: no 'id'")
            elif cid in seen:
                errors.append(f"{where}: duplicate id {cid!r}, already used by {seen[cid]}")
            else:
                seen[cid] = where

            source = entry.get("source")
            if source not in PERMITTED_SOURCES:
                known = ", ".join(sorted(PERMITTED_SOURCES))
                errors.append(
                    f"{where} ({cid or 'no id'}): unknown source {source!r}. "
                    f"Permitted: {known}. Add it to PERMITTED_SOURCES in "
                    f"validate_corrections.py if it is genuinely new — note that "
                    f"a source starting with {VOUCHING_PREFIX!r} may vouch for a "
                    f"deliberate line break (ADR 0012).")

            reason = entry.get("reason")
            if not reason or not str(reason).strip():
                errors.append(
                    f"{where} ({cid or 'no id'}): no 'reason' — every entry "
                    f"names the warrant for its divergence (ADR 0022)")

            adr = entry.get("adr")
            adr_tokens = str(adr or "").split()
            if source == "upstream-review" and not adr_tokens:
                errors.append(
                    f"{where} ({cid or 'no id'}): 'upstream-review' entries "
                    f"must name the ADR that settled them ('adr') (ADR 0022)")
            if adr_tokens and adr_tokens[0] not in known_adrs:
                errors.append(
                    f"{where} ({cid or 'no id'}): adr {adr!r} does not name a "
                    f"real ADR in docs/adr/ (ADR 0022)")
    return errors


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
    """Check every office_text correction against the pre-correction offices.

    The match itself is decided by corrections_lib, which is also what
    apply_corrections.py uses — so anything that validates here applies there.
    """
    errors = []
    for c in corrections:
        cid = c["id"]
        targets = resolve_offices(data, c)
        if not targets:
            # A wildcard resolves through the field, so an empty result means
            # no office carries it — naming the office would point at the one
            # key that is certainly right.
            errors.append(
                f"{cid}: no office has field '{c['field']}'"
                if c["office"] == ALL_OFFICES
                else f"{cid}: office '{c['office']}' not found")
            continue
        fields = []
        for key, office in targets:
            field = office.get(c["field"])
            if field is None:
                # Only reachable for a named office; the wildcard skips offices
                # without the field rather than resolving them.
                errors.append(f"{cid}: field '{c['field']}' not in {key}")
                break
            fields.append(field)
        else:
            problem = check_office_text_across(c, fields)
            if problem:
                errors.append(f"{cid}: {c['office']}.{c['field']} — {problem}")
    return errors


def validate_lectionary_citation(corrections: list) -> list[str]:
    errors = []
    for c in corrections:
        cid = c["id"]
        month = c["date"][:7]
        path = BUILD / "lectionary" / f"{month}.json"
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
    for f in sorted((BUILD / "lectionary").glob("*.json")):
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
    """Only 'clear' is a live action (removes a garbled/unparseable note).
    ('set_type' existed here previously but was never used by any real
    correction — removed 2026-07-26, see issue #13.)

    Checks PRE-application state, like every other validator here: a
    'clear' correction is stale once notes are already gone (either
    because it was applied, or the upstream CSV stopped producing the
    garbled note), so it must find notes still present to be actionable —
    not already-empty, which is what this checked before (backwards: that
    tested apply_corrections' output, not whether there was anything left
    to correct, so it could never actually catch staleness)."""
    errors = []
    lectionary = load_lectionary()
    for c in corrections:
        cid = c["id"]
        day = lectionary.get(c["date"])
        if day is None:
            errors.append(f"{cid}: date {c['date']} not found")
            continue
        if not day.get("notes"):
            errors.append(f"{cid}: notes already empty — nothing to clear (stale?)")
    return errors


def validate_lectionary_psalms(corrections: list) -> list[str]:
    """One indexed psalms[] entry within a day's office, whole-entry replace."""
    errors = []
    lectionary = load_lectionary()
    for c in corrections:
        cid = c["id"]
        day = lectionary.get(c["date"])
        if day is None:
            errors.append(f"{cid}: date {c['date']} not found")
            continue
        office = day.get(c["office"], {})
        psalms = office.get("psalms", [])
        idx = c.get("index", 0)
        if idx >= len(psalms):
            errors.append(f"{cid}: psalm index {idx} out of range")
            continue
        actual = psalms[idx]
        if actual != c.get("old"):
            errors.append(f"{cid}: psalm[{idx}] mismatch for {c['date']}/{c['office']}: {actual!r} != {c['old']!r}")
    return errors


def validate_lectionary_lessons(corrections: list) -> list[str]:
    """Whole-lessons-list replace for one date+office, keyed by (date, office)."""
    errors = []
    lectionary = load_lectionary()
    for c in corrections:
        cid = c["id"]
        day = lectionary.get(c["date"])
        if day is None:
            errors.append(f"{cid}: date {c['date']} not found")
            continue
        office = day.get(c["office"], {})
        actual = office.get("lessons")
        if actual != c.get("old"):
            errors.append(f"{cid}: lessons mismatch for {c['date']}/{c['office']}: {actual!r} != {c['old']!r}")
    return errors


def validate_psalter(corrections: list) -> list[str]:
    """Every psalter correction is a plain text replace within one psalm's
    text, keyed by psalm number. (insert_before/insert_after/fix_v12 action
    variants existed here previously but were never used by any real
    correction — removed 2026-07-26, see issue #13.)"""
    errors = []
    psalter = json.loads((BUILD / "psalter.1-extract.json").read_text())
    for c in corrections:
        cid = c["id"]
        pnum = str(c["psalm"])
        psalm = psalter.get(pnum)
        if psalm is None:
            errors.append(f"{cid}: psalm {pnum} not found")
            continue
        ptext = psalm.get("text", "")
        old = c.get("old", "")
        if old not in ptext and old.replace(" ", "\xa0") not in ptext:
            errors.append(f"{cid}: old text not found in psalm {pnum}")
    return errors


def validate_fats(corrections: list) -> list[str]:
    """Every FATS correction is a plain text replace within one saint's
    field. (A "rename_key" action variant existed here previously but was
    never used by any real correction — removed 2026-07-26, see issue #13.)"""
    errors = []
    fats = json.loads((BUILD / "fats-saints.1-extract.json").read_text())
    for c in corrections:
        cid = c["id"]
        saint = fats.get(c.get("saint") or c.get("saint_key", ""))
        if saint is None:
            errors.append(f"{cid}: saint not found")
            continue
        field = c.get("field")
        val = saint.get(field, "")
        if c.get("old") not in val:
            errors.append(f"{cid}: old text not found in saint.{field}")
    return errors


def main():
    if not CORRECTIONS.exists():
        print("No corrections.json found — nothing to validate.")
        return

    corrections = json.loads(CORRECTIONS.read_text())
    errors = validate_provenance(corrections)

    if corrections.get("office_text"):
        # The pre-correction artifact, named explicitly. This check is about
        # whether a correction still matches the text it was written against, so
        # it must never see corrected output — which naming its own input
        # guarantees whenever this runs, rather than an order to remember (#48).
        offices = json.loads((BUILD / "offices.2-normalized.json").read_text())
        errors.extend(validate_office_text(corrections["office_text"], offices))

    if corrections.get("lectionary_citations"):
        errors.extend(validate_lectionary_citation(corrections["lectionary_citations"]))

    if corrections.get("lectionary_psalms"):
        errors.extend(validate_lectionary_psalms(corrections["lectionary_psalms"]))

    if corrections.get("lectionary_lessons"):
        errors.extend(validate_lectionary_lessons(corrections["lectionary_lessons"]))

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
