#!/usr/bin/env python3
"""Worklist for taking a new lectionary year's CSV into the pipeline.

Most of the converter derives itself from the CSV (ADR 0017). What does not
is keyed by date or by vocabulary, and none of it carries from one year to
the next. This tool reads a CSV without extracting anything and reports every
decision the converter cannot make for itself, so the work is visible before
`make extract` refuses it.

  python3 tools/intake_year.py [--csv PATH ...]      # default: sources/bas_short_*.csv
  make intake-year

Report-only: exit status is 0 even when findings exist. `make extract` is the
gate — this is the worklist for clearing it. See
docs/runbooks/lectionary-year-intake.md.
"""
import argparse
import csv
import datetime
import difflib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from convert_lectionary import (  # noqa: E402
    EVE_COMPANION_TAGS,
    EVE_EXCLUDED_TARGETS,
    EVE_THE_ARTICLE,
    KNOWN_EVE_TARGETS,
    OBSERVANCE_FUZZY_RATIO,
    OBSERVANCE_PHRASES,
    RE_EVE_OF,
    _type_hint,
    clean,
    detect_bounds,
    unlabelled_alternates,
    unmatched_eve_offices,
    untyped_note_dates,
)

RE_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def head(n: int, title: str) -> None:
    print("\n" + "=" * 72)
    print(f"{n}. {title}")
    print("=" * 72)


def eve_key(target: str) -> str:
    key = re.sub(r"^the\s+", "", target, flags=re.I).strip().lower()
    return key.replace("’", "'")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", nargs="*", metavar="PATH",
                    help="CSV files to read (default: sources/bas_short_*.csv)")
    args = ap.parse_args()

    paths = ([Path(p) for p in args.csv] if args.csv
             else sorted(ROOT.glob("sources/bas_short_*.csv")))
    if not paths:
        sys.exit("No bas_short_*.csv found in sources/ — run make fetch-sources first.")

    rows_by_date: dict[str, list] = {}
    for path in paths:
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.reader(f, quoting=csv.QUOTE_MINIMAL):
                if len(row) >= 5 and RE_DATE.match(row[0].strip()):
                    rows_by_date[row[0].strip()] = row
    rows = sorted(rows_by_date.values(), key=lambda r: r[0])
    dates = sorted(rows_by_date)
    print(f"Lectionary intake — {len(paths)} file(s), {len(dates)} dates")
    print(f"  {', '.join(p.name for p in paths)}")

    # ── 1. Coverage ────────────────────────────────────────────────────────────
    head(1, "COVERAGE (the span the CSV actually provides)")
    if dates:
        first = datetime.date.fromisoformat(dates[0])
        last = datetime.date.fromisoformat(dates[-1])
        print(f"  {dates[0]} .. {dates[-1]}  ({(last - first).days + 1} calendar days)")
        have = {datetime.date.fromisoformat(d) for d in dates}
        gaps = [first + datetime.timedelta(days=i)
                for i in range((last - first).days + 1)
                if first + datetime.timedelta(days=i) not in have]
        if gaps:
            print(f"  MISSING {len(gaps)} date(s) inside the span — the app has no "
                  f"office for these:")
            for g in gaps[:20]:
                print(f"    {g.isoformat()}")
            if len(gaps) > 20:
                print(f"    … and {len(gaps) - 20} more")
        else:
            print("  No gaps.")

    # ── 2. Note types ──────────────────────────────────────────────────────────
    head(2, "NOTE TYPES (hand-classified per date; `make extract` gates on this)")
    untyped = untyped_note_dates(rows_by_date)
    if not untyped:
        print("  Every note-bearing date is typed.")
    else:
        print(f"  {len(untyped)} date(s) need a NOTE_TYPES entry in "
              f"tools/convert_lectionary.py.")
        print("  `source_note` = the compiler's apparatus (where propers came")
        print("  from, which option was taken). `pastoral` = a custom addressed")
        print("  to whoever is praying. The rest of the vocabulary is in the table.\n")
        for date_str, segs in untyped:
            print(f'    "{date_str}": {_type_hint(segs)},')
            for i, s in enumerate(segs):
                print(f"        # [{i}] {s[:110]}")

    # ── 3. Eve ────────────────────────────────────────────────────────────────
    head(3, "EVE (name-column targets, office labels)")
    eve_lines: dict[str, list[str]] = {}
    for row in rows:
        for line in clean(row[1]).split("\n"):
            line = line.strip()
            if m := RE_EVE_OF.match(line):
                eve_lines.setdefault(eve_key(m.group(1)), []).append(
                    f"{row[0].strip()}  {line}")

    unknown = {k: v for k, v in eve_lines.items() if k not in KNOWN_EVE_TARGETS}
    if unknown:
        print(f"  {len(unknown)} name-column eve target(s) outside KNOWN_EVE_TARGETS.")
        print("  The converter warns and drops these — advisory, not blocking — but")
        print("  each is a rewording to add to the vocabulary, and to EVE_THE_ARTICLE")
        print('  if liturgical usage prefixes "the" ("Eve of the Epiphany", never')
        print('  "Eve of Epiphany"):')
        for k, examples in sorted(unknown.items()):
            print(f"    {k!r}")
            for ex in examples[:3]:
                print(f"        {ex}")
    else:
        print("  All name-column eve targets are in the known vocabulary.")

    # Absence from EVE_COMPANION_TAGS already encodes "decided: no companion"
    # for every target in the known vocabulary, so only a target new to the
    # vocabulary carries an open question.
    bracketed = {k: v for k, v in eve_lines.items()
                 if any("[" in ex for ex in v)
                 and k not in KNOWN_EVE_TARGETS
                 and k not in EVE_COMPANION_TAGS
                 and k not in EVE_EXCLUDED_TARGETS}
    if bracketed:
        print(f"\n  {len(bracketed)} new conditional eve(s) needing an")
        print("  EVE_COMPANION_TAGS decision. ADR 0017 point 5: the CSV wording")
        print("  cannot decide whether a conditional eve also carries a same-date")
        print("  bare tag — Corpus Christi does not, Ascension Sunday does:")
        for k, examples in sorted(bracketed.items()):
            print(f"    {k!r}")
            for ex in examples[:2]:
                print(f"        {ex}")

    articled = sorted(k for k in eve_lines if k in EVE_THE_ARTICLE)
    print(f"\n  {len(eve_lines)} distinct eve target(s); "
          f"{len(articled)} take the definite article.")

    unmatched = unmatched_eve_offices(rows_by_date)
    if unmatched:
        print(f"\n  {len(unmatched)} eve office(s) matched no name-column line —")
        print("  blocking: fail-open would put the day's colour on an office")
        print("  praying the eve's propers (#128). Extend eve_identity's matching")
        print("  or add a correction:")
        for d, office_key, label, lines in unmatched:
            print(f"    {d} {office_key} label={label!r}")
            for ln in lines[:3]:
                print(f"        name line: {ln}")
    else:
        print("\n  No unmatched eve offices.")

    unlabelled = unlabelled_alternates(rows_by_date)
    if unlabelled:
        print(f"\n  {len(unlabelled)} office alternate(s) carry no label —")
        print("  blocking: the toggle would offer the choice as \"Alternate\" and")
        print("  the observance would keep the day's colour and rank (#131).")
        print("  Widen RE_BRANCH_LABEL; no correction category reaches an")
        print("  alternate's label, so an unnamed one needs a new one added:")
        for d, office_key, branch in unlabelled:
            print(f"    {d} {office_key}")
            print(f"        branch: {branch[:100]}")
    else:
        print("\n  No unlabelled office alternates.")

    # ── 4. Observance phrases ──────────────────────────────────────────────────
    head(4, "OBSERVANCE PHRASES (drift in wording the classifier matches on)")
    near = []
    for row in rows:
        for line in clean(row[1]).split("\n"):
            line = line.strip()
            if not line or RE_EVE_OF.match(line):
                continue
            low = line.lower().replace("’", "'")
            if any(p in low for p in OBSERVANCE_PHRASES):
                continue
            best_ratio, best = 0.0, None
            for phrase in OBSERVANCE_PHRASES:
                r = difflib.SequenceMatcher(None, low, phrase).ratio()
                if r > best_ratio:
                    best_ratio, best = r, phrase
            if best_ratio >= OBSERVANCE_FUZZY_RATIO:
                near.append((row[0].strip(), line, best, best_ratio))
    if near:
        print(f"  {len(near)} line(s) match no phrase but are close to one — ACC")
        print("  may have rephrased a marker. Each is either a rewording to add to")
        print("  OBSERVANCE_PHRASES or a coincidence to ignore:")
        for date_str, line, phrase, ratio in near:
            print(f"    {date_str}  {line!r}")
            print(f"        {ratio:.0%} similar to {phrase!r}")
    else:
        print("  No near-miss wordings.")

    # ── 5. Season bounds ───────────────────────────────────────────────────────
    head(5, "SEASON BOUNDS (detected from the name column)")
    bounds = detect_bounds(rows)
    required = ["advent_i", "christmas", "epiphany", "ash_wednesday",
                "easter", "pentecost", "trinity_sunday", "all_saints"]
    missing = [b for b in required if b not in bounds]
    for name, date_str in sorted(bounds.items(), key=lambda kv: kv[1]):
        print(f"    {date_str}  {name}")
    if missing:
        print(f"\n  MISSING required bound(s): {', '.join(missing)}")
        print("  detect_bounds reads CANONICAL_BOUNDS_PHRASES against the name")
        print("  column; a missing bound means the phrase moved.")

    # ── 6. Corrections ─────────────────────────────────────────────────────────
    head(6, "CORRECTIONS (per-date, do not carry to a new year)")
    corr_path = ROOT / "data" / "corrections.json"
    with open(corr_path, encoding="utf-8") as f:
        corrections = json.load(f)
    for category, entries in sorted(corrections.items()):
        if not category.startswith("lectionary") or not entries:
            continue
        in_csv = [e for e in entries
                  if (m := RE_DATE.search(json.dumps(e))) and m.group(0) in rows_by_date]
        print(f"    {category}: {len(entries)} entry(ies), "
              f"{len(in_csv)} on a date this CSV covers")
    print("\n  Corrections are found by inspection, not derived. A new year's")
    print("  errors surface through `make validate` and `make check-text`, and")
    print("  each fix goes in data/corrections.json with its `old` value (ADR 0005).")

    print("\n" + "=" * 72)
    blocking = len(untyped) + len(unmatched) + len(missing)
    if blocking:
        print(f"{blocking} item(s) block extraction. Work them, then re-run.")
    else:
        print("Nothing blocks extraction. Run `make extract`.")
    print("=" * 72)


if __name__ == "__main__":
    main()
