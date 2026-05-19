#!/usr/bin/env python3
"""
validate_lectionary.py — diff CSV-converted data against HTML-scraped data.

For each date in the overlap window, reads (or fetches) the HTML from
lectionary.anglican.ca and compares the parsed output against the JSON
produced by convert_lectionary.py.

Known systematic differences that are suppressed:
  - observances: absent in HTML (handcrafted dict in convert_lectionary.py)
  - notes content: different sources (HTML subtitle vs. CSV extra column)
  - book abbreviations: HTML uses full names ("Isaiah"), CSV uses short ("Is")

Run from repo root:
  python3 tools/validate_lectionary.py [--start YYYY-MM-DD] [--end YYYY-MM-DD]
                                        [--delay N] [--no-fetch]

  --start YYYY-MM-DD  First date (default: earliest CSV-covered date)
  --end YYYY-MM-DD    Last date (default: yesterday)
  --delay N           Seconds between HTTP requests when fetching (default: 1.0)
  --no-fetch          Only compare dates already cached; skip network requests
  --show-all          Print OK lines too, not just diffs
"""

import argparse
import json
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data" / "lectionary"
sys.path.insert(0, str(Path(__file__).parent))

from scrape_daily import CACHE_DIR, fetch_day_html, parse_day_html


# ── Normalisation ─────────────────────────────────────────────────────────────

def _norm_dash(s: str) -> str:
    return s.replace('—', '-').replace('–', '-').replace('–', '-').replace('—', '-')


def _citation_key(citation: str) -> str:
    """
    Strip the book-name prefix so "Is 1:1-9" and "Isaiah 1:1-9" both yield "1:1-9".
    Also normalises dashes and whitespace.
    """
    s = _norm_dash(citation).strip()
    # Strip everything before the first chapter:verse digit pattern
    m = re.search(r'\d+:\d+', s)
    if m:
        return s[m.start():].strip()
    # Bare psalm number or non-chapter citation — just normalise whitespace
    return ' '.join(s.split())


def _psalm_nums(psalms: list) -> list[str]:
    nums = []
    for p in psalms:
        if isinstance(p, str):
            nums.append(p)
        elif isinstance(p, dict):
            nums.append(p.get('citation', ''))
    return nums


def _collect_page(collect: str) -> str:
    """Primary page reference only: "430 or FAS 359" → "430"."""
    if not collect:
        return ''
    return collect.split()[0].rstrip('.')


def _lesson_key(lesson) -> tuple[str, bool]:
    """(normalised citation, is_optional)"""
    if isinstance(lesson, dict):
        return _citation_key(lesson.get('citation', '')), lesson.get('optional', False)
    return _citation_key(lesson), False


# ── Field-level comparison ────────────────────────────────────────────────────

def _cmp_office(csv_off: dict, html_off: dict, label: str) -> list[str]:
    issues = []

    if 'psalm_sets' in csv_off:
        # Multiple alternative psalm sets — check HTML psalms match at least one set.
        html_ps = _psalm_nums(html_off.get('psalms', []))
        matched = any(
            _psalm_nums(s) == html_ps for s in csv_off['psalm_sets']
        )
        if not matched and html_ps:
            all_csv = [_psalm_nums(s) for s in csv_off['psalm_sets']]
            issues.append(f"  {label} psalms (sets): html={html_ps}  csv_sets={all_csv}")
    else:
        csv_ps = _psalm_nums(csv_off.get('psalms', []))
        html_ps = _psalm_nums(html_off.get('psalms', []))
        if csv_ps != html_ps:
            issues.append(f"  {label} psalms:    csv={csv_ps}  html={html_ps}")

    csv_yn = csv_off.get('year_note', '')
    html_yn = html_off.get('year_note', '')
    if csv_yn != html_yn:
        issues.append(f"  {label} year_note: csv={csv_yn!r}  html={html_yn!r}")

    csv_les = [_lesson_key(l) for l in csv_off.get('lessons', [])]
    html_les = [_lesson_key(l) for l in html_off.get('lessons', [])]

    if len(csv_les) != len(html_les):
        issues.append(f"  {label} lesson count: csv={len(csv_les)}  html={len(html_les)}")
        issues.append(f"    csv : {[c for c, _ in csv_les]}")
        issues.append(f"    html: {[h for h, _ in html_les]}")
    else:
        for i, ((ck, co), (hk, ho)) in enumerate(zip(csv_les, html_les)):
            if ck != hk:
                raw_c = csv_off.get('lessons', [])[i]
                raw_h = html_off.get('lessons', [])[i]
                issues.append(f"  {label} lesson[{i}] citation:")
                issues.append(f"    csv : {raw_c!r}  (key: {ck!r})")
                issues.append(f"    html: {raw_h!r}  (key: {hk!r})")
            if co != ho:
                issues.append(f"  {label} lesson[{i}] optional: csv={co}  html={ho}")

    csv_coll = _collect_page(csv_off.get('collect', ''))
    html_coll = _collect_page(html_off.get('collect', ''))
    if csv_coll != html_coll:
        issues.append(
            f"  {label} collect:   csv={csv_off.get('collect')!r}  html={html_off.get('collect')!r}"
        )

    return issues


def compare_day(csv_entry: dict, html_entry: dict) -> list[str]:
    issues = []

    if csv_entry.get('name') != html_entry.get('name'):
        issues.append(f"  name:   csv={csv_entry.get('name')!r}")
        issues.append(f"          html={html_entry.get('name')!r}")

    if csv_entry.get('colour') != html_entry.get('colour'):
        issues.append(
            f"  colour: csv={csv_entry.get('colour')!r}  html={html_entry.get('colour')!r}"
        )

    csv_rank = csv_entry.get('rank', '')
    html_rank = html_entry.get('rank', '')
    if csv_rank != html_rank:
        # Suppress the known CSV bug: Sundays default to "feria"
        if not (csv_rank == 'feria' and html_rank == 'holy_day'):
            issues.append(f"  rank:   csv={csv_rank!r}  html={html_rank!r}")

    for office in ('morning', 'evening'):
        csv_off = csv_entry.get(office) or {}
        html_off = html_entry.get(office) or {}
        issues.extend(_cmp_office(csv_off, html_off, office))

    return issues


# ── Main ──────────────────────────────────────────────────────────────────────

def _load_csv_entry(d: date) -> dict | None:
    month_key = str(d)[:7]
    path = DATA_DIR / f"{month_key}.json"
    if not path.exists():
        return None
    month = json.loads(path.read_text(encoding='utf-8'))
    return month.get(str(d))


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument('--start', metavar='YYYY-MM-DD',
                    help='First date (default: 2025-11-30, earliest CSV date)')
    ap.add_argument('--end', metavar='YYYY-MM-DD',
                    help='Last date (default: yesterday)')
    ap.add_argument('--delay', type=float, default=1.0, metavar='N',
                    help='Seconds between HTTP fetches (default: 1.0)')
    ap.add_argument('--no-fetch', action='store_true',
                    help='Only compare cached dates; skip network requests')
    ap.add_argument('--show-all', action='store_true',
                    help='Print OK lines too, not just diffs')
    args = ap.parse_args()

    start = date.fromisoformat(args.start) if args.start else date(2025, 11, 30)
    end = date.fromisoformat(args.end) if args.end else date.today() - timedelta(days=1)

    total = (end - start).days + 1
    print(f"Validating {total} date(s): {start} → {end}")
    if not args.no_fetch:
        cached = sum(1 for d in (start + timedelta(n) for n in range(total))
                     if (CACHE_DIR / f"{d}.html").exists())
        to_fetch = total - cached
        if to_fetch:
            print(f"  {cached} cached, {to_fetch} to fetch (~{to_fetch * args.delay / 60:.1f} min)")

    total_ok = total_diff = total_missing_html = total_missing_csv = 0
    all_issues: list[tuple[str, list[str]]] = []

    d = start
    while d <= end:
        date_str = str(d)
        is_cached = (CACHE_DIR / f"{d}.html").exists()

        if args.no_fetch and not is_cached:
            d += timedelta(days=1)
            continue

        delay = args.delay if not is_cached else 0.0
        html_text = fetch_day_html(d, delay=delay, no_cache=False)

        if html_text is None:
            print(f"  {date_str}: no HTML data")
            total_missing_html += 1
            d += timedelta(days=1)
            continue

        html_entry = parse_day_html(d, html_text)
        csv_entry = _load_csv_entry(d)

        if csv_entry is None:
            if args.show_all:
                print(f"  {date_str}: no CSV entry")
            total_missing_csv += 1
            d += timedelta(days=1)
            continue

        issues = compare_day(csv_entry, html_entry)

        if issues:
            total_diff += 1
            all_issues.append((date_str, issues))
            print(f"  {date_str}: DIFF ({html_entry.get('name', '?')})")
            for line in issues:
                print(line)
        else:
            total_ok += 1
            if args.show_all:
                print(f"  {date_str}: ok  ({csv_entry.get('name', '?')})")

        d += timedelta(days=1)

    print()
    print(f"Results: {total_ok} ok, {total_diff} diff, "
          f"{total_missing_html} no-html, {total_missing_csv} no-csv")

    if all_issues:
        sys.exit(1)


if __name__ == '__main__':
    main()
