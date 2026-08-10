#!/usr/bin/env python3
"""Audit the observances the ADR 0017 classifier pulls from the CSV.

For every date x name-column line: what did the classifier do with it?
Plus temporal/structural checks. Report-only (like review_form.cjs) — run by
hand after a re-extraction or when ACC ships a new CSV year:

  python3 tools/audit_observances.py

Exit status is 0 even when findings exist; findings print to stdout.
"""
import csv
import datetime
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from convert_lectionary import (  # noqa: E402
    KNOWN_EVE_TARGETS,
    OBSERVANCE_PHRASES,
    _classify_observance_line,
    clean,
)

CSV_GLOB = sorted((ROOT / "sources").glob("bas_short_*.csv"))
if not CSV_GLOB:
    sys.exit("No bas_short_*.csv found in sources/ — run make fetch-sources first.")

ROWS = {}
for path in CSV_GLOB:
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.reader(f, quoting=csv.QUOTE_MINIMAL):
            if len(row) >= 2 and re.match(r"\d{4}-\d{2}-\d{2}", row[0].strip()):
                ROWS[row[0].strip()] = row[1]

DATA = {}
for p in (ROOT / "data" / "lectionary").glob("*.json"):
    with open(p, encoding="utf-8") as f:
        DATA.update(json.load(f))

OBS = {d: e.get("observances") for d, e in DATA.items() if e.get("observances")}
with open(ROOT / "data" / "season_bounds.json", encoding="utf-8") as f:
    BOUNDS = json.load(f)


def bucket(line: str) -> str:
    low = line.lower()
    if re.match(r"^(and / or|or both together)$", low):
        return "separator text"
    if re.search(r" - (com|mem|hd|pf)\b", low) or "," in line or re.search(r"\d", line):
        return "commemoration / alternate"
    if "feria" in low or "ember day" in low or "rogation day" in low:
        return "feria / ember / rogation"
    if low.startswith("eve of sunday"):
        return "eve-of-Sunday (excluded by design)"
    return "OTHER - untagged marker, human decision"


print("=" * 72)
print("1. LINE-LEVEL ACCOUNTING (every name-column line classified)")
print("=" * 72)
unmatched = {}
matched = lines_total = 0
for d, raw in ROWS.items():
    for line in clean(raw).split("\n"):
        line = line.strip()
        if not line:
            continue
        lines_total += 1
        if _classify_observance_line(line) is not None:
            matched += 1
        else:
            unmatched.setdefault(bucket(line), []).append((d, line))
print(f"dates in CSV: {len(ROWS)} | name-column lines: {lines_total} | "
      f"lines emitting a tag: {matched} | unmatched: {lines_total - matched}")
for b, items in sorted(unmatched.items()):
    print(f"\n  {b}: {len(items)}")
    for d, line in sorted(items):
        print(f"    {d}  {line!r}")

print()
print("=" * 72)
print("2. EVE -> FEAST RESOLUTION (day after each eve is ranked or an observance)")
print("=" * 72)
eve_days = [(d, t) for d, tags in OBS.items() for t in tags if t.startswith("eve_of:")]
bad_eve = []
for d, t in sorted(eve_days):
    nxt = (datetime.date.fromisoformat(d) + datetime.timedelta(days=1)).isoformat()
    e = DATA.get(nxt)
    rank = e.get("rank") if e else None
    is_observance_day = bool(e and e.get("observances"))
    if e is None:
        bad_eve.append((d, t, "window edge (next day not in data)"))
    elif rank not in ("holy_day", "principal_feast") and not is_observance_day:
        bad_eve.append((d, t, f"{nxt} rank={rank}, no observances"))
print(f"eve tags: {len(eve_days)} | unresolved: {len(bad_eve)}")
for d, t, why in bad_eve:
    print(f"    {d} {t}: {why}")

print()
print("=" * 72)
print("3. fast_day CHECK (Friday, or Ash Wednesday..Easter weekday, or exception)")
print("=" * 72)
fast = [d for d, tags in OBS.items() if "fast_day" in tags]
ash = datetime.date.fromisoformat(BOUNDS["ash_wednesday"])
easter = datetime.date.fromisoformat(BOUNDS["easter"])
lent = set()
day = ash
while day < easter:
    if day.weekday() != 6:  # Sundays excluded by the source's own tagging
        lent.add(day.isoformat())
    day += datetime.timedelta(days=1)
weird = [d for d in fast
         if datetime.date.fromisoformat(d).weekday() != 4 and d not in lent]
print(f"fast_day dates: {len(fast)} | outside the convention: {len(weird)}")
for d in weird:
    print(f"    {d} ({datetime.date.fromisoformat(d).strftime('%A')})")

print()
print("=" * 72)
print("4. TEMPORAL RANGE CHECKS")
print("=" * 72)
WINDOWS = {
    "octave_of_christmas": [(datetime.date(2025, 12, 26), datetime.date(2026, 1, 1)),
                            (datetime.date(2026, 12, 26), datetime.date(2027, 1, 1))],
    "octave_of_easter": [(easter + datetime.timedelta(days=1), easter + datetime.timedelta(days=7))],
    "week_of_prayer_for_christian_unity": [(datetime.date(2026, 1, 18), datetime.date(2026, 1, 25))],
    "season_of_creation": [(datetime.date(2026, 9, 1), datetime.date(2026, 10, 4))],
    "easter_eve": [(easter - datetime.timedelta(days=1), easter - datetime.timedelta(days=1))],
}
for tag, windows in WINDOWS.items():
    ds = [d for d, tags in OBS.items() if tag in tags]
    out = [d for d in ds if not any(lo <= datetime.date.fromisoformat(d) <= hi
                                    for lo, hi in windows)]
    print(f"  {tag}: {len(ds)} dates, {min(ds)}..{max(ds)} "
          f"| out of window: {out or 'none'}")

print()
print("=" * 72)
print("5. VOCABULARY HYGIENE")
print("=" * 72)


def norm(tag: str) -> str:
    if tag.startswith("eve_of:"):
        tag = tag[7:]
    tag = re.sub(r"^the\s+", "", tag, flags=re.I).strip().lower()
    return tag.replace("\u2019", "'")


known = {norm(t) for t in set(OBSERVANCE_PHRASES.values())}
known |= {norm("eve_of:" + t) for t in KNOWN_EVE_TARGETS}
unknown = sorted({t for t in set(t for tags in OBS.values() for t in tags)
                  if norm(t) not in known})
dups = [(d, t) for d, tags in OBS.items() for t in set(tags) if tags.count(t) > 1]
print(f"distinct tags in data: {len({t for tags in OBS.values() for t in tags})} "
      f"| unknown/typo tags: {unknown or 'none'} | duplicate tags in a date: {dups or 'none'}")

print()
print("=" * 72)
print("6. CIVIL-DAY CONSISTENCY (civil markers should all be tagged)")
print("=" * 72)
civil_kw = ["remembrance day", "victoria day", "canada day", "labour day",
            "thanksgiving day", "new year", "accession day"]
untagged = []
for kw in civil_kw:
    for d, raw in ROWS.items():
        if kw in raw.lower() and d not in OBS:
            untagged.append((d, kw))
print(f"untagged civil-marker lines: {untagged or 'none'}")
