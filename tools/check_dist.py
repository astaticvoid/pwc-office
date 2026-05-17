#!/usr/bin/env python3
"""
check_dist.py — verify dist/ is complete before deploying.

Checks:
  - Required web files present
  - Data files the app fetches at runtime are all present
  - All lectionary entries reference valid psalm files and form keys
  - All collect IDs referenced in the lectionary exist in collects.json
  - At least one translation present (KJV or NRSVUE)

Usage: python3 tools/check_dist.py   (or via `make check-dist`)
Exit 0 = ready to deploy, 1 = failures found.
"""

import json
import re
import sys
from pathlib import Path

dist = Path(__file__).parent.parent / "dist"
errors: list[str] = []
warnings: list[str] = []


def require(path: Path, label: str = "") -> bool:
    if not path.exists():
        errors.append(f"missing: {path.relative_to(dist)} {label}".strip())
        return False
    return True


# ── Web shell ──────────────────────────────────────────────────────────────────

for f in ("index.html", "app.js", "office.css"):
    require(dist / f)

# Sanity-check that app.js references the data path it expects.
app_js = dist / "app.js"
if app_js.exists():
    src = app_js.read_text()
    if "const DATA = 'data'" not in src:
        errors.append("app.js: DATA path constant missing or changed")

# ── Static data files ──────────────────────────────────────────────────────────

for f in ("data/offices.json", "data/collects.json", "data/season_bounds.json"):
    require(dist / f)

lect_dir   = dist / "data" / "lectionary"
psalms_dir = dist / "data" / "psalms"

if not lect_dir.is_dir():
    errors.append("missing: data/lectionary/")
if not psalms_dir.is_dir():
    errors.append("missing: data/psalms/")

# ── Load core data ─────────────────────────────────────────────────────────────

offices_path  = dist / "data" / "offices.json"
collects_path = dist / "data" / "collects.json"

offices  = json.loads(offices_path.read_text())  if offices_path.exists()  else {}
collects = json.loads(collects_path.read_text()) if collects_path.exists() else {}

# ── Lectionary cross-references ────────────────────────────────────────────────

lect_files = sorted(lect_dir.glob("*.json")) if lect_dir.is_dir() else []

if not lect_files:
    errors.append("data/lectionary/ is empty")

SEASON_ORDER = [
    "christmas_ii", "advent_ii", "all_saints", "pentecost",
    "easter", "palm_sunday", "ash_wednesday", "epiphany", "christmas", "advent_i",
]
WEEKDAYS = ["sunday","monday","tuesday","wednesday","thursday","friday","saturday"]

def form_key(season: str, office: str, weekday: int, rank: str) -> str:
    s = season.lower()
    if s == "pentecost" and rank != "principal_feast":
        s = "ordinarytime"
    if s == "ordinarytime":
        s = f"ordinary-{WEEKDAYS[weekday]}"
    return f"{s}-{office}"

def first_digits(ref: str):
    m = re.search(r"\d+", str(ref))
    return m.group() if m else None

import datetime

bounds_path = dist / "data" / "season_bounds.json"
bounds = json.loads(bounds_path.read_text()) if bounds_path.exists() else {}

def season_of(date_str: str) -> str:
    d = datetime.date.fromisoformat(date_str)
    for key, season in [
        ("christmas_ii", "Christmas"), ("advent_ii", "Advent"),
        ("all_saints", "AllSaints"), ("pentecost", "Pentecost"),
        ("easter", "Easter"), ("palm_sunday", "Passiontide"),
        ("ash_wednesday", "Lent"), ("epiphany", "Epiphany"),
        ("christmas", "Christmas"), ("advent_i", "Advent"),
    ]:
        if key in bounds and d >= datetime.date.fromisoformat(bounds[key]):
            return season
    return "OrdinaryTime"

def psalm_nums_from_citation(cit: str) -> list:
    """Return individual psalm numbers from a citation like '8-14', '87:1-7', '95 (Invitatory)'."""
    cit = re.sub(r'\([^)]*\)', '', cit).strip()  # strip parentheticals
    if ':' in cit:
        cit = cit.split(':')[0].strip()           # drop verse range
    if '-' in cit:
        parts = cit.split('-')
        try:
            start, end = int(parts[0].strip()), int(parts[-1].strip())
            if start <= end:
                return list(range(start, end + 1))
            else:
                return [start, end]               # reversed = data error, flag both
        except ValueError:
            pass
    try:
        return [int(cit)]
    except ValueError:
        return []


psalm_errors, collect_errors, form_errors = 0, 0, 0

for path in lect_files:
    entry = json.loads(path.read_text())
    date  = entry.get("date", path.stem)
    d     = datetime.date.fromisoformat(date)
    weekday = d.weekday()  # Mon=0; convert to Sun=0
    weekday = (weekday + 1) % 7
    season  = season_of(date)
    rank    = entry.get("rank", "")

    for office_type, office_key in (("mp", "morning"), ("ep", "evening")):
        office = entry.get(office_key) or {}
        for obs in [office, office.get("alternate") or {}]:
            if not obs:
                continue
            # Psalm files
            psalms = obs.get("psalms", [])
            for p in psalms:
                cit = p["citation"] if isinstance(p, dict) else p
                for num in psalm_nums_from_citation(cit):
                    if not (psalms_dir / f"{num}.json").exists():
                        errors.append(f"{date} {office_type}: psalm {num}.json missing (from '{cit}')")
                        psalm_errors += 1

            # Collect IDs — missing collect degrades gracefully (shows page num only)
            ref = obs.get("collect")
            if ref:
                page = first_digits(str(ref))
                if page and page not in collects:
                    warnings.append(f"{date} {office_type}: collect '{ref}' (p.{page}) not extracted — will show page number only")
                    collect_errors += 1

        # Office form key
        key = form_key(season, office_type, weekday, rank)
        if offices and key not in offices:
            errors.append(f"{date} {office_type}: form key '{key}' not in offices.json")
            form_errors += 1

if lect_files:
    print(f"lectionary:  {len(lect_files)} entries checked"
          f" ({psalm_errors} psalm errors, {collect_errors} collect errors, {form_errors} form errors)")

# ── Translations ───────────────────────────────────────────────────────────────

trans_dir = dist / "data" / "translations"
found_translations = []
if trans_dir.is_dir():
    found_translations = [t.name for t in trans_dir.iterdir() if t.is_dir()]

if not found_translations:
    errors.append("data/translations/: no translations found (need at least KJV)")
else:
    if "kjv" not in found_translations:
        warnings.append("KJV translation missing — scripture fallback will fail")
    print(f"translations: {', '.join(sorted(found_translations))}")

# ── Report ─────────────────────────────────────────────────────────────────────

print(f"web files:   index.html, app.js, office.css")
print(f"offices:     {len(offices)} forms")
print(f"collects:    {len(collects)} entries")

if warnings:
    for w in warnings:
        print(f"  ⚠ {w}")

if errors:
    print(f"\n{len(errors)} ERROR(S) — dist/ is not ready to deploy:")
    for e in errors:
        print(f"  ✗ {e}")
    sys.exit(1)
else:
    print("\ndist/ is ready to deploy.")
