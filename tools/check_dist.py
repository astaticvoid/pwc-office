#!/usr/bin/env python3
"""
check_dist.py — verify dist/ is complete before deploying.

Checks:
  - Required web files present
  - Every .woff2 fonts.css references is present and distinct, with both OFL
    licence files
  - Data files the app fetches at runtime are all present
  - All lectionary entries reference valid psalm files and form keys
  - All collect IDs referenced in the lectionary exist in collects.json
  - At least one translation present (KJV or NRSVUE)

Usage: python3 tools/check_dist.py   (or via `make check-dist`)
Exit 0 = ready to deploy, 1 = failures found.
"""

import datetime
import hashlib
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

for f in ("index.html", "app.js", "office.css", "sw.js"):
    require(dist / f)

# Sanity-check that app.js references the data path it expects.
app_js = dist / "app.js"
if app_js.exists():
    src = app_js.read_text()
    if "const DATA = 'data'" not in src:
        errors.append("app.js: DATA path constant missing or changed")

# Verify the build stamped the SW cache version (placeholder must be replaced).
sw_js = dist / "sw.js"
if sw_js.exists() and "pwc-v1" in sw_js.read_text():
    errors.append("sw.js: cache version is still 'pwc-v1' — build stamp was not applied")

# ── Fonts and their licences ───────────────────────────────────────────────────

# Both bundled families are OFL 1.1, which requires the licence to travel with
# the font files. dist/ is what reaches the bucket and the native binaries, so
# the licences dropping out of a build is a distribution problem, not a repo one.

fonts_dir = dist / "assets" / "fonts"
fonts_css = fonts_dir / "fonts.css"

present_fonts = sorted(f.name for f in fonts_dir.glob("*.woff2")) if fonts_dir.is_dir() else []

if require(fonts_css):
    # Quotes around a url() are optional in CSS, so a quote-only pattern would
    # skip an unquoted face silently — unchecked, unhashed, and not counted.
    # The set is reconciled against what is on disk below rather than trusted.
    referenced = sorted(set(re.findall(
        r"""url\(\s*['"]?([^'")\s]+\.woff2)['"]?\s*\)""", fonts_css.read_text())))
    if not referenced:
        errors.append("assets/fonts/fonts.css: no .woff2 sources found")
    for name in referenced:
        require(fonts_dir / name, "(referenced by fonts.css)")
    print(f"fonts:       {len(referenced)} woff2 referenced by fonts.css")

    # A font on disk that nothing references is either dead bytes being shipped
    # or a face this parse failed to see. Both want looking at, and the second
    # would otherwise hide a face from every check below.
    for name in present_fonts:
        if name not in referenced:
            errors.append(f"assets/fonts/{name}: present but not referenced by fonts.css "
                          "(dead weight in dist/, or a url() this check failed to parse)")

    # Every face but the small-caps one is a variable font, so a single file
    # covers a family+style at every weight. Two identical files under two names
    # means someone split a range back into one @font-face per weight: the same
    # bytes then download once per weight under distinct cache keys. That was #108.
    by_digest: dict[str, list[str]] = {}
    for name in referenced:
        f = fonts_dir / name
        if f.exists():
            by_digest.setdefault(hashlib.sha256(f.read_bytes()).hexdigest(), []).append(name)
    for digest, names in sorted(by_digest.items()):
        if len(names) > 1:
            errors.append(
                f"assets/fonts/: {', '.join(names)} are byte-identical ({digest[:12]}) — "
                "collapse them to one file with a ranged font-weight descriptor")

# Which licences are required is derived from the font filenames, not restated:
# a third family added without its OFL text should fail here rather than pass
# because nobody remembered to extend a list. `EBGaramond-*.woff2` wants
# `OFL-EBGaramond.txt`.
required_licences = sorted({f"OFL-{name.split('-')[0]}.txt" for name in present_fonts})
if present_fonts and not required_licences:
    errors.append("assets/fonts/: could not derive licence filenames from the font filenames")

for licence in required_licences:
    if require(fonts_dir / licence, "(OFL 1.1 requires the licence to ship with the fonts)"):
        if "SIL OPEN FONT LICENSE Version 1.1" not in (fonts_dir / licence).read_text():
            errors.append(f"assets/fonts/{licence}: does not contain the OFL 1.1 text")

# ── Static data files ──────────────────────────────────────────────────────────

for f in ("data/offices.json", "data/collects.json", "data/season_bounds.json", "data/psalter.json"):
    require(dist / f)

lect_dir = dist / "data" / "lectionary"

if not lect_dir.is_dir():
    errors.append("missing: data/lectionary/")
else:
    monthly_files = list(lect_dir.glob("????-??.json"))
    if not monthly_files:
        errors.append("data/lectionary/: no monthly files (expected YYYY-MM.json)")

# ── Load core data ─────────────────────────────────────────────────────────────

offices_path  = dist / "data" / "offices.json"
collects_path = dist / "data" / "collects.json"
psalter_path  = dist / "data" / "psalter.json"

offices  = json.loads(offices_path.read_text())  if offices_path.exists()  else {}
collects = json.loads(collects_path.read_text()) if collects_path.exists() else {}
psalter  = json.loads(psalter_path.read_text())  if psalter_path.exists()  else {}

# ── Lectionary cross-references ────────────────────────────────────────────────

# Monthly files only (YYYY-MM.json); individual day files are no longer used.
lect_month_files = sorted(lect_dir.glob("????-??.json")) if lect_dir.is_dir() else []

# Flatten all day entries for cross-reference checks.
lect_entries: list[dict] = []
for mf in lect_month_files:
    month_data = json.loads(mf.read_text())
    lect_entries.extend(month_data.values())

if not lect_entries:
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

for entry in lect_entries:
    date    = entry.get("date", "")
    d       = datetime.date.fromisoformat(date)
    weekday = (d.weekday() + 1) % 7  # Mon=0 → Sun=0
    season  = season_of(date)
    rank    = entry.get("rank", "")

    for office_type, office_key in (("mp", "morning"), ("ep", "evening")):
        office = entry.get(office_key) or {}
        for obs in [office, office.get("alternate") or {}]:
            if not obs:
                continue
            # Psalm numbers present in psalter.json
            for p in obs.get("psalms", []):
                cit = p["citation"] if isinstance(p, dict) else p
                for num in psalm_nums_from_citation(cit):
                    if str(num) not in psalter:
                        errors.append(f"{date} {office_type}: psalm {num} missing from psalter.json (from '{cit}')")
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

if lect_entries:
    print(f"lectionary:  {len(lect_entries)} entries checked"
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

print("web files:   index.html, app.js, office.css")
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
