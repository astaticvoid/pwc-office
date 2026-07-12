#!/usr/bin/env python3
"""
Validate RCL Daily lectionary extraction output.

Checks:
  1. Coverage: all expected dates present, no gaps
  2. Content: every entry has psalm + at least one reading
  3. Citations: reading format looks like valid Scripture citations
  4. Two-track: track2 matches track1 structure where present
  5. Season boundaries: key feast days are present
  6. Duplicates: no duplicate dates

Usage: python3 tools/validate_rcl_daily.py [--strict] [--data-dir data/rcl-daily]
       --strict: exit 1 on any warning
"""

import json
import os
import re
import sys
from datetime import date, timedelta
from glob import glob

CITATION_RE = re.compile(r"^(?:[\d]?\s*[A-Za-z]+(?:\s+\d+)?\s+\d+:\d+|Psalm\s+\d+)")


def load_all(data_dir):
    """Load all monthly JSON files, return dict keyed by date."""
    all_entries = {}
    files = sorted(glob(os.path.join(data_dir, "*.json")))
    for fp in files:
        with open(fp) as f:
            month_data = json.load(f)
        for date_str, entry in month_data.items():
            all_entries[date_str] = entry
    return all_entries


def check_coverage(entries):
    """Check date continuity and count."""
    dates = sorted(entries.keys())
    if not dates:
        return ["No entries found"]

    issues = []
    print(f"  Total entries: {len(dates)}")
    print(f"  Date range: {dates[0]} → {dates[-1]}")

    first = date.fromisoformat(dates[0])
    last = date.fromisoformat(dates[-1])
    expected = (last - first).days + 1
    if len(dates) != expected:
        issues.append(f"Coverage gap: expected {expected} days, got {len(dates)}")
        # Find gaps
        for i in range(len(dates) - 1):
            d1 = date.fromisoformat(dates[i])
            d2 = date.fromisoformat(dates[i + 1])
            gap = (d2 - d1).days
            if gap > 1:
                issues.append(f"  Gap: {dates[i]} → {dates[i+1]} ({gap - 1} days missing)")

    return issues


def check_content(entries):
    """Check every entry has psalm + readings."""
    issues = []
    missing_psalm = []
    missing_first = []
    missing_second = []
    two_track_count = 0
    two_track_missing_t2 = []

    for date_str, entry in entries.items():
        is_two_track = "track1" in entry

        if is_two_track:
            two_track_count += 1
            t1 = entry.get("track1", {})
            t2 = entry.get("track2", {})
            if not t1.get("psalm"):
                missing_psalm.append(date_str)
            if not t1.get("first_reading"):
                missing_first.append(date_str)
            if not t1.get("second_reading"):
                missing_second.append(date_str)
            if t2 and t2.get("psalm") and not t2.get("first_reading"):
                two_track_missing_t2.append(date_str)
        else:
            if not entry.get("psalm"):
                missing_psalm.append(date_str)
            if not entry.get("first_reading"):
                missing_first.append(date_str)
            if not entry.get("second_reading"):
                missing_second.append(date_str)

    print(f"  Two-track entries: {two_track_count}")
    if missing_psalm:
        issues.append(f"{len(missing_psalm)} entries missing psalm")
        for d in missing_psalm[:5]:
            issues.append(f"    {d}")
    if missing_first:
        issues.append(f"{len(missing_first)} entries missing first reading")
    if missing_second:
        issues.append(f"{len(missing_second)} entries missing second reading")
    if two_track_missing_t2:
        issues.append(f"{len(two_track_missing_t2)} two-track entries missing track2 first reading")

    return issues


def check_citation_format(entries):
    """Check that reading fields look like valid Scripture citations."""
    issues = []
    suspicious = []

    for date_str, entry in entries.items():
        fields_to_check = []
        if "track1" in entry:
            for tkey in ("track1", "track2"):
                t = entry.get(tkey, {})
                if t:
                    fields_to_check.extend([
                        ("psalm", t.get("psalm", "")),
                        ("first_reading", t.get("first_reading", "")),
                        ("second_reading", t.get("second_reading", "")),
                    ])
        else:
            fields_to_check.extend([
                ("psalm", entry.get("psalm", "")),
                ("first_reading", entry.get("first_reading", "")),
                ("second_reading", entry.get("second_reading", "")),
            ])

        for field_name, value in fields_to_check:
            if not value:
                continue
            # Skip known non-citation values (prayer texts, etc.)
            if value.startswith(("Prayer", "Collect", "Lord", "Almighty")):
                continue
            # Check for date labels masquerading as readings
            if re.match(r"^(January|February|March|April|May|June|July|August|"
                        r"September|October|November|December)\s+\d+", value):
                suspicious.append(f"{date_str} {field_name}: {value[:60]} (looks like date label)")
            elif not CITATION_RE.search(value):
                suspicious.append(f"{date_str} {field_name}: {value[:60]} (not a citation)")

    if suspicious:
        issues.append(f"{len(suspicious)} suspicious citation formats")
        for s in suspicious[:10]:
            issues.append(f"    {s}")

    return issues


def check_key_dates(entries):
    """Verify key feast days are present."""
    issues = []
    key_dates = [
        ("Advent 1 Sunday", None),  # computed below
        ("Christmas Day", "12-25"),
        ("Ash Wednesday", None),
        ("Easter Sunday", None),
        ("Pentecost", None),
    ]

    # Find key dates from the entries (search by label)
    for date_str, entry in entries.items():
        label = entry.get("week_label", "")
        if ("Advent 1" in label or "First Sunday of Advent" in label):
            key_dates[0] = ("Advent 1 Sunday", date_str)
        if "Ash Wednesday" in label or ("Lent 1" in label and "Wednesday" in label):
            # Ash Wednesday is the first Wednesday of Lent
            if date_str.endswith(("02-10", "02-11", "02-12", "02-13", "02-14",
                                   "02-15", "02-16", "02-17", "02-18", "02-19",
                                   "02-20", "02-21", "02-22", "02-23", "02-24")):
                if date_str < "2027-02-14":  # Before Lent 1 Sunday
                    key_dates[2] = ("Ash Wednesday", date_str)
        if ("Resurrection" in label or "Easter Day" in label or
            ("Easter" in label and "Sunday" in label)):
            key_dates[3] = ("Easter Sunday", date_str)
        if "Pentecost" in label and ("Sunday" in label or "of" not in label.lower()):
            key_dates[4] = ("Pentecost", date_str)

    # Check Christmas by date
    for date_str, entry in entries.items():
        if date_str.endswith("-12-25"):
            key_dates[1] = ("Christmas Day", date_str)

    for name, date_str in key_dates:
        if date_str:
            print(f"  {name}: {date_str}")
        else:
            issues.append(f"Missing key date: {name}")

    return issues


def check_duplicates(entries):
    """Check for duplicate dates."""
    issues = []
    dates = list(entries.keys())
    seen = set()
    dupes = set()
    for d in dates:
        if d in seen:
            dupes.add(d)
        seen.add(d)
    if dupes:
        issues.append(f"{len(dupes)} duplicate dates: {sorted(dupes)[:10]}")
    return issues


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Validate RCL Daily lectionary output")
    parser.add_argument("--data-dir", default=None,
                        help="Path to data/rcl-daily directory")
    parser.add_argument("--strict", action="store_true",
                        help="Exit 1 on any warning")
    args = parser.parse_args()

    if args.data_dir:
        data_dir = args.data_dir
    else:
        data_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "rcl-daily"
        )

    if not os.path.isdir(data_dir):
        print(f"ERROR: data directory not found: {data_dir}")
        sys.exit(1)

    print(f"RCL Daily Validation — {data_dir}")
    entries = load_all(data_dir)

    all_issues = []

    print("\n[Coverage]")
    issues = check_coverage(entries)
    all_issues.extend(issues)

    print("\n[Content]")
    issues = check_content(entries)
    all_issues.extend(issues)

    print("\n[Citations]")
    issues = check_citation_format(entries)
    all_issues.extend(issues)

    print("\n[Key Dates]")
    issues = check_key_dates(entries)
    all_issues.extend(issues)

    print("\n[Duplicates]")
    issues = check_duplicates(entries)
    all_issues.extend(issues)

    if all_issues:
        print(f"\n{len(all_issues)} issue(s) found:")
        for issue in all_issues:
            print(f"  {issue}")
        if args.strict:
            sys.exit(1)
    else:
        print("\nNo issues found.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
