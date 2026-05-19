#!/usr/bin/env python3
"""
scrape_lectionary.py — discover and download ACC lectionary CSVs.

The Anglican Church of Canada publishes one CSV per liturgical year at:
  https://lectionary.anglican.ca/wp-content/uploads/bas_short_YYYY.csv

This tool probes available years, downloads missing or updated CSVs with
conditional HTTP requests (ETag / Last-Modified), and optionally runs
convert_lectionary.py to regenerate the JSON data files.

Run from repo root:
  python3 tools/scrape_lectionary.py [options]

  --probe           HEAD-probe all years, print availability table; no downloads
  --years 2024-2027 Restrict to this year range (default: current-5 to current+2)
  --force           Re-download even if ETag says unchanged
  --delay N         Seconds between HTTP requests (default: 1.0)
  --diff            Show row-level diff vs previous version after download
  --no-convert      Skip running convert_lectionary.py after download
  --accept          Pass --accept through to convert_lectionary.py

Default (no flags): probe + download changed/missing + convert.
"""

import argparse
import csv
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path


BASE_URL = "https://lectionary.anglican.ca/wp-content/uploads"
CACHE_FILE = Path(__file__).parent / ".scrape_cache.json"
ROOT = Path(__file__).parent.parent
SOURCES_DIR = ROOT / "sources"


# ── ETag cache ────────────────────────────────────────────────────────────────

def load_cache() -> dict:
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict) -> None:
    CACHE_FILE.write_text(
        json.dumps(dict(sorted(cache.items())), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _csv_url(year: int) -> str:
    return f"{BASE_URL}/bas_short_{year}.csv"


def probe_year(year: int) -> bool:
    """HEAD request — True if the CSV exists (HTTP 200)."""
    req = urllib.request.Request(_csv_url(year), method="HEAD")
    req.add_header("User-Agent", "pwc-office-scraper/1.0 (+https://github.com/astaticvoid/pwc-office)")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as e:
        if e.code in (404, 403):
            return False
        raise
    except urllib.error.URLError:
        return False


def fetch_year(
    year: int,
    *,
    cache: dict,
    force: bool = False,
    delay: float = 1.0,
) -> str:
    """
    Download bas_short_{year}.csv to sources/ if missing or changed.

    Returns one of: "downloaded", "unchanged", "skipped" (not available).
    Updates cache in place on successful download.
    """
    dest = SOURCES_DIR / f"bas_short_{year}.csv"
    url = _csv_url(year)
    cached = cache.get(str(year), {})

    req = urllib.request.Request(url)
    req.add_header("User-Agent", "pwc-office-scraper/1.0 (+https://github.com/astaticvoid/pwc-office)")

    if not force and dest.exists():
        if cached.get("etag"):
            req.add_header("If-None-Match", cached["etag"])
        elif cached.get("last_modified"):
            req.add_header("If-Modified-Since", cached["last_modified"])

    time.sleep(delay)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            etag = resp.headers.get("ETag", "")
            last_modified = resp.headers.get("Last-Modified", "")

        SOURCES_DIR.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

        cache[str(year)] = {}
        if etag:
            cache[str(year)]["etag"] = etag
        if last_modified:
            cache[str(year)]["last_modified"] = last_modified

        return "downloaded"

    except urllib.error.HTTPError as e:
        if e.code == 304:
            return "unchanged"
        if e.code in (404, 403):
            return "skipped"
        raise


# ── Row-level diff ────────────────────────────────────────────────────────────

def _load_csv_rows(path: Path) -> dict[str, list[str]]:
    """Return rows keyed by date string."""
    rows = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if row and len(row) >= 1:
                rows[row[0].strip()] = row
    return rows


def diff_csv(old: Path, new: Path) -> list[dict]:
    """
    Row-level diff between two CSVs. Returns list of change dicts:
      {"date": "YYYY-MM-DD", "col": 0, "old": "...", "new": "..."}
    Empty list = identical.
    """
    old_rows = _load_csv_rows(old)
    new_rows = _load_csv_rows(new)
    COLS = ["date", "name", "eucharist", "morning", "evening", "extra"]
    changes = []

    all_dates = sorted(set(old_rows) | set(new_rows))
    for date_str in all_dates:
        if date_str not in old_rows:
            changes.append({"date": date_str, "col": -1, "old": None, "new": "NEW ROW"})
            continue
        if date_str not in new_rows:
            changes.append({"date": date_str, "col": -1, "old": "DELETED", "new": None})
            continue
        old_r, new_r = old_rows[date_str], new_rows[date_str]
        max_cols = max(len(old_r), len(new_r))
        for i in range(max_cols):
            ov = old_r[i] if i < len(old_r) else ""
            nv = new_r[i] if i < len(new_r) else ""
            if ov != nv:
                changes.append({
                    "date": date_str,
                    "col": i,
                    "col_name": COLS[i] if i < len(COLS) else f"col{i}",
                    "old": ov,
                    "new": nv,
                })
    return changes


def print_diff(changes: list[dict], year: int) -> None:
    if not changes:
        print(f"  {year}: no changes vs. previous version")
        return
    print(f"  {year}: {len(changes)} field change(s):")
    for c in changes[:20]:
        if c["col"] == -1:
            print(f"    {c['date']}: {c['old'] or c['new']}")
        else:
            old_short = (c["old"] or "")[:80].replace("\n", "\\n")
            new_short = (c["new"] or "")[:80].replace("\n", "\\n")
            print(f"    {c['date']} [{c['col_name']}]")
            print(f"      - {old_short}")
            print(f"      + {new_short}")
    if len(changes) > 20:
        print(f"    … and {len(changes) - 20} more. Run with --diff to see all.")


# ── Main ──────────────────────────────────────────────────────────────────────

def parse_year_range(s: str) -> range:
    """Parse "2024-2027" or "2026" into a range of years (inclusive)."""
    if "-" in s:
        parts = s.split("-", 1)
        return range(int(parts[0]), int(parts[1]) + 1)
    return range(int(s), int(s) + 1)


def main():
    current_year = date.today().year
    default_start = current_year - 5
    default_end = current_year + 2

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", action="store_true",
                    help="HEAD-probe all years and print availability table; no downloads")
    ap.add_argument("--years", default=f"{default_start}-{default_end}", metavar="RANGE",
                    help=f"Year range to probe/fetch (default: {default_start}-{default_end})")
    ap.add_argument("--force", action="store_true",
                    help="Re-download even if ETag says unchanged")
    ap.add_argument("--delay", type=float, default=1.0, metavar="N",
                    help="Seconds between HTTP requests (default: 1.0)")
    ap.add_argument("--diff", action="store_true",
                    help="Show row-level diff vs previous version after download")
    ap.add_argument("--no-convert", action="store_true",
                    help="Skip running convert_lectionary.py after download")
    ap.add_argument("--accept", action="store_true",
                    help="Pass --accept to convert_lectionary.py (accept new manifest hashes)")
    args = ap.parse_args()

    years = parse_year_range(args.years)

    # ── Probe ─────────────────────────────────────────────────────────────────
    print(f"Probing {len(years)} year(s)…")
    available = []
    for year in years:
        ok = probe_year(year)
        status = "available" if ok else "not found"
        print(f"  {year}: {status}")
        if ok:
            available.append(year)
        time.sleep(args.delay)

    if not available:
        print("No years available. Nothing to do.")
        return

    if args.probe:
        return

    # ── Download ──────────────────────────────────────────────────────────────
    cache = load_cache()
    downloaded = []
    for year in available:
        dest = SOURCES_DIR / f"bas_short_{year}.csv"
        old_content = dest.read_bytes() if dest.exists() else None

        result = fetch_year(year, cache=cache, force=args.force, delay=args.delay)
        print(f"  {year}: {result}")

        if result == "downloaded" and args.diff and old_content is not None:
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
                tmp.write(old_content)
                tmp_path = Path(tmp.name)
            try:
                changes = diff_csv(tmp_path, dest)
                print_diff(changes, year)
            finally:
                tmp_path.unlink(missing_ok=True)

        if result == "downloaded":
            downloaded.append(year)

    save_cache(cache)

    if not downloaded and not args.force:
        print("All CSVs already up to date.")
    else:
        print(f"Downloaded: {downloaded or 'none (all unchanged)'}")

    if args.no_convert:
        return

    # ── Convert ───────────────────────────────────────────────────────────────
    print("\nRunning convert_lectionary.py…")
    cmd = [sys.executable, str(Path(__file__).parent / "convert_lectionary.py")]
    if args.accept:
        cmd.append("--accept")
    subprocess.run(cmd, check=True, cwd=str(ROOT))


if __name__ == "__main__":
    main()
