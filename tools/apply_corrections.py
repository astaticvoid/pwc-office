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

from corrections_lib import check_office_text_across, replace_occurrences, resolve_offices

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"
# Intermediate pipeline artifacts. Deliberately outside data/, which is the
# published tree — anything under it is copied into dist/ by the data symlink.
BUILD = ROOT / ".build"
CORRECTIONS = DATA / "corrections.json"

_misses: list[str] = []


def _stage_input(path: Path) -> Path:
    """Return `path`, or fail with the remediation rather than a traceback.

    Every input here is written by an earlier stage of `make extract`. If one is
    absent the pipeline did not run, and that is worth saying in the same terms
    check_data_integrity.py uses — not a bare FileNotFoundError from whichever
    stage happened to be first.
    """
    missing = not path.exists()
    if not missing and path.is_dir():
        # For the one directory input, "the pipeline did not run" is an empty
        # directory, not an absent one — convert_lectionary.py creates
        # .build/lectionary/ and can then prune every month out of it. That
        # matters more here than anywhere else: _seed_lectionary mirrors the
        # source exactly, so an empty source does not mean "nothing to copy",
        # it means "delete all 14 published months", and it did so at exit 0.
        missing = not any(path.glob("*.json"))
    if missing:
        print(
            f"ERROR: {path.relative_to(ROOT)} is missing or empty — it is written\n"
            f"       by an earlier stage of the pipeline. Run `make extract`.",
            file=sys.stderr,
        )
        sys.exit(1)
    return path


def _apply_replace(in_path: Path, out_path: Path, corrections: list, locate,
                   describe, on_applied=None):
    """Generic 'find old substring, replace with new' applier for a list of
    corrections against one JSON file. `locate(data, c)` returns the mutable
    container to correct plus its field name (container, field), or None if
    not found. `describe(c)` returns a short id string for logging.
    `on_applied(container, c)`, if given, runs after a successful replace —
    e.g. to stamp provenance metadata alongside the corrected field.

    Reads `in_path` and writes `out_path`, always — the output is a separate
    artifact that downstream stages read by name, so skipping the write when
    nothing applied would leave them consuming a stale copy (#49). That is why
    an empty `corrections` list is not an early return: this function derives
    the published file, and correcting it is the incidental part."""
    data = json.loads(_stage_input(in_path).read_text())
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
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    if applied:
        print(f"  Applied {applied} correction(s) → {out_path}")


def _seed_lectionary() -> None:
    """Mirror .build/lectionary/ into data/lectionary/ before corrections run.

    The five date-keyed appliers (lessons, names, ranks, colours, notes) each
    walk the months they have corrections for, so they have to accumulate: if
    every one re-read the pristine build artifact, the last would discard the
    others' work. Three months carry two correction types and regressed exactly
    that way when this was first written.

    So the published copy is seeded once here and corrected in place after. The
    build artifact is still never written, and months that lost their corrections
    or dropped out of the source cannot linger, because the mirror is exact.
    """
    src, dst = _stage_input(BUILD / "lectionary"), DATA / "lectionary"
    dst.mkdir(parents=True, exist_ok=True)
    wanted = {p.name for p in src.glob("*.json")}
    for stale in dst.glob("*.json"):
        if stale.name not in wanted:
            stale.unlink()
    for month in sorted(src.glob("*.json")):
        (dst / month.name).write_text(month.read_text())


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
        out_path = path
        if not path.exists():
            for c in month_corrections:
                _misses.append(f"{c['id']}: month file {month}.json not found")
            continue
        data = json.loads(path.read_text())
        for c in month_corrections:
            day = data.get(c["date"])
            if day is None:
                _misses.append(f"{c['id']}: date {c['date']} not found")
                continue
            if mutate(day, c):
                applied += 1
                print(f"  {c['id']}: {describe(c) if describe else c['date']}")
            else:
                _misses.append(f"{c['id']}: {describe(c) if describe else c['date']} — old value mismatch")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    if applied:
        print(f"  Applied {applied} correction(s)")


def main():
    # A missing manifest means there is nothing to correct, not nothing to do:
    # every stage below derives a published file from a build artifact, and
    # returning here would leave all four of them underived. Once the last
    # correction is migrated into an extractor — which AGENTS.md actively asks
    # for — deleting this file would otherwise publish nothing while reporting
    # success.
    have_manifest = CORRECTIONS.exists()
    corrections = json.loads(CORRECTIONS.read_text()) if have_manifest else {}
    if not have_manifest:
        print("No corrections.json — deriving published files with no corrections applied.")

    # Check every stage input before the first write. Validating lazily, in
    # derivation order, means a missing lectionary artifact exits only after the
    # three JSON files have been rewritten, leaving data/ half-re-derived against
    # a stale manifest — and check-integrity then reports that as "modified
    # outside the extraction pipeline", which is the wrong remediation entirely.
    # Built here rather than at module scope so tests that repoint BUILD are
    # honoured.
    for stage_input in (
        BUILD / "offices.2-normalized.json",
        BUILD / "psalter.1-extract.json",
        BUILD / "fats-saints.1-extract.json",
        BUILD / "lectionary",
    ):
        _stage_input(stage_input)

    # Office text corrections — substring replace within the field's segments
    # when 'old' is a string, whole-field replace otherwise. See corrections_lib.
    # Stage 3, the last of the offices chain: reads the normalized artifact and
    # writes the file everything else consumes. Because the input is a separate
    # artifact, re-running this is idempotent — it re-derives from normalized
    # output rather than correcting already-corrected text (#48).
    #
    # Deliberately not guarded on a non-empty office_text list. This stage
    # *derives* the published file; correcting it is the incidental part. Behind
    # such a guard the write below was unconditional in name only, and with no
    # office_text corrections data/offices.json was never rebuilt at all — an
    # extractor change then left the published file stale through a full
    # `make extract` that reported success, and check-integrity passed because
    # the manifest was rehashed from the same stale file.
    out_path = DATA / "offices.json"
    data = json.loads(_stage_input(BUILD / "offices.2-normalized.json").read_text())
    applied = 0
    for c in corrections.get("office_text", []):
        targets = [(k, o) for k, o in resolve_offices(data, c) if c["field"] in o]
        if not targets:
            _misses.append(f"{c['id']}: {c['office']}.{c['field']} not found")
            continue
        # Same check the validator ran, so nothing applies on a state it would
        # have rejected — including the occurrence count, which is what stops a
        # substring correction applying to fewer (or more) segments than its
        # author counted. Checked across the whole set before any of it is
        # written, so a wildcard cannot half-apply.
        problem = check_office_text_across(c, [o[c["field"]] for _, o in targets])
        if problem:
            _misses.append(f"{c['id']}: {c['office']}.{c['field']} — {problem}")
            continue
        if isinstance(c["old"], str):
            n = 0
            for _, office in targets:
                field = office[c["field"]]
                if isinstance(field, str):
                    # A plain-string field (every office `title`) — replaced on
                    # the office dict, since a str cannot be corrected in place.
                    n += field.count(c["old"])
                    office[c["field"]] = field.replace(c["old"], c["new"])
                else:
                    n += replace_occurrences(field, c["old"], c["new"])
            where = f"{c['office']}.{c['field']}"
            spread = f" across {len(targets)} offices" if len(targets) > 1 else ""
            print(f"  {c['id']}: {where} ({n}×{spread})")
        else:
            targets[0][1][c["field"]] = c["new"]
            print(f"  {c['id']}: {c['office']}.{c['field']}")
        applied += 1
    # This is the artifact the app, the manifest and the integrity check read,
    # so it must exist and must be derived from the normalized input even when
    # no correction applies.
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

    _apply_replace(
        BUILD / "psalter.1-extract.json", DATA / "psalter.json",
        corrections.get("psalter", []),
        locate=lambda data, c: (
            (data[pnum], "text") if (pnum := str(c["psalm"])) in data else None
        ),
        describe=lambda c: f"Psalm {c['psalm']}",
        on_applied=_stamp_source_correction,
    )

    # FATS (saint biography) corrections — substring replace within one field.
    _apply_replace(
        BUILD / "fats-saints.1-extract.json", DATA / "fats" / "saints.json",
        corrections.get("fats", []),
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

    # Seed the published months from the build artifact before any date-keyed
    # applier runs. They accumulate against data/lectionary/, so this is the one
    # point where the pristine input is copied across.
    _seed_lectionary()

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
