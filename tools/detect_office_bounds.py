#!/usr/bin/env python3
"""
detect_office_bounds.py — find office form page boundaries by scanning
pdftotext output for form title patterns.

Two-phase detection:
  1. Seasonal forms: matched by unique title regex (16 forms)
  2. Ordinary Time forms: detected by generic weekday pattern in pages after
     the last seasonal form (14 forms = 7 weekdays × MP+EP)

Output: tools/office_bounds.json

Usage:
    python3 tools/detect_office_bounds.py --write     # regenerate bounds file
    python3 tools/detect_office_bounds.py --strict    # fail if detection differs from committed file
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
PDF = ROOT / "sources" / "pray-without-ceasing.pdf"
OUT = ROOT / "tools" / "office_bounds.json"

# ── Seasonal — unique titles ────────────────────────────────────────────────

SEASONAL_PATTERNS = [
    ("advent-mp",        re.compile(r"Morning Prayer for Advent\b")),
    ("advent-ep",        re.compile(r"Evening Prayer for Advent\b")),
    ("christmas-mp",     re.compile(r"Morning Prayer for Christmas\b")),
    ("christmas-ep",     re.compile(r"Evening Prayer for Christmas\b")),
    ("epiphany-mp",      re.compile(r"Morning Prayer for Epiphany\b")),
    ("epiphany-ep",      re.compile(r"Evening Prayer for Epiphany\b")),
    ("lent-mp",          re.compile(r"Morning Prayer for Lent\b")),
    ("lent-ep",          re.compile(r"Evening Prayer for Lent\b")),
    ("passiontide-mp",   re.compile(r"Morning Prayer for Passiontide\b")),
    ("passiontide-ep",   re.compile(r"Evening Prayer for Passiontide\b")),
    ("easter-mp",        re.compile(r"Morning Prayer for Easter\b")),
    ("easter-ep",        re.compile(r"Evening Prayer for Easter\b")),
    ("pentecost-mp",     re.compile(r"Morning Prayer for Pentecost\b")),
    ("pentecost-ep",     re.compile(r"Evening Prayer for Pentecost\b")),
    ("allsaints-mp",     re.compile(r"Morning Prayer for All Saints\b")),
    ("allsaints-ep",     re.compile(r"Evening Prayer for All Saints\b")),
]

# ── Ordinary Time — generic titles, detected by position ────────────────────

ORDINARY_FORM_KEYS = [
    "ordinary-sunday-mp",    "ordinary-sunday-ep",
    "ordinary-monday-mp",    "ordinary-monday-ep",
    "ordinary-tuesday-mp",   "ordinary-tuesday-ep",
    "ordinary-wednesday-mp", "ordinary-wednesday-ep",
    "ordinary-thursday-mp",  "ordinary-thursday-ep",
    "ordinary-friday-mp",    "ordinary-friday-ep",
    "ordinary-saturday-mp",  "ordinary-saturday-ep",
]

# Generic pattern for an Ordinary Time form title (weekday name, no season label)
ORDINARY_TITLE = re.compile(
    r"^(Morning|Evening) Prayer for (Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday)\b",
    re.IGNORECASE,
)

OFFICE_SECTION_END = 230  # page after last office form (Psalter begins ~231)

EXPECTED_SEASONAL = len(SEASONAL_PATTERNS)   # 16
EXPECTED_ORDINARY = len(ORDINARY_FORM_KEYS)  # 14


def detect(pdf_path: Path) -> dict[str, tuple[int, int]]:
    result = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"],
        capture_output=True, text=True, check=True,
    )
    text = result.stdout
    pages = text.split("\f")

    # ── Phase 1: detect seasonal forms by unique title ──────────────────────
    # Skip running-header lines (page number + form title, e.g. "64 Morning Prayer for Lent")
    RUNNING_HDR = re.compile(r'^\d+\s+(Morning|Evening) Prayer\b')

    seasonal: list[tuple[str, int]] = []
    for page_idx, page_text in enumerate(pages):
        book_page = page_idx + 1
        # Skip front matter (TOC, preface) — first office form starts at page 14.
        # Skip back matter (index after Psalter, ~page 236+).
        if book_page < 14 or book_page > 240:
            continue
        # Check the top of the page; strip running headers first.
        first_lines = []
        for line in page_text.split('\n')[:8]:
            line = line.strip()
            if RUNNING_HDR.match(line):
                continue
            first_lines.append(line)
        first_chars = '\n'.join(first_lines)
        for form_key, pattern in SEASONAL_PATTERNS:
            if pattern.search(first_chars):
                seasonal.append((form_key, book_page))
                break

    if len(seasonal) != EXPECTED_SEASONAL:
        found_keys = {k for k, _ in seasonal}
        missing = [k for k, _ in SEASONAL_PATTERNS if k not in found_keys]
        print(f"ERROR: found {len(seasonal)} seasonal forms, expected {EXPECTED_SEASONAL}",
              file=sys.stderr)
        if missing:
            print(f"Missing seasonal: {missing}", file=sys.stderr)
        sys.exit(1)

    # ── Phase 2: detect Ordinary Time forms (generic titles, after last seasonal) ──
    last_seasonal_page = max(p for _, p in seasonal)
    ordinary: list[tuple[str, int]] = []
    seen = set()

    for page_idx, page_text in enumerate(pages):
        book_page = page_idx + 1
        if book_page <= last_seasonal_page:
            continue
        if book_page < 14 or book_page > 240:
            continue
        # Check top of page; strip running headers
        first_lines = []
        for line in page_text.split('\n')[:8]:
            line = line.strip()
            if RUNNING_HDR.match(line):
                continue
            first_lines.append(line)
        first_chars = '\n'.join(first_lines)
        m = ORDINARY_TITLE.search(first_chars)
        if m:
            office_type = "mp" if m.group(1).lower() == "morning" else "ep"
            weekday = m.group(2).lower()
            candidate = f"ordinary-{weekday}-{office_type}"
            if candidate in seen:
                # Duplicate weekday+type — shouldn't happen in Ordinary Time block
                print(f"WARNING: duplicate {candidate} at page {book_page}, skipping",
                      file=sys.stderr)
                continue
            if candidate in ORDINARY_FORM_KEYS:
                seen.add(candidate)
                ordinary.append((candidate, book_page))

    if len(ordinary) != EXPECTED_ORDINARY:
        found_keys = {k for k, _ in ordinary}
        missing = [k for k in ORDINARY_FORM_KEYS if k not in found_keys]
        print(f"ERROR: found {len(ordinary)} Ordinary Time forms, expected {EXPECTED_ORDINARY}",
              file=sys.stderr)
        if missing:
            print(f"Missing ordinary: {missing}", file=sys.stderr)
        sys.exit(1)

    # ── Assemble all forms in reading order ─────────────────────────────────
    all_forms = sorted(seasonal + ordinary, key=lambda x: x[1])

    bounds: dict[str, tuple[int, int]] = {}
    seasonal_keys = {k for k, _ in SEASONAL_PATTERNS}
    for i, (form_key, start) in enumerate(all_forms):
        next_start = all_forms[i + 1][1] if i + 1 < len(all_forms) else OFFICE_SECTION_END + 1
        end = next_start - 1

        # When crossing from seasonal to ordinary section, check for the section
        # divider page ("Morning and Evening Prayer for Ordinary Time") between
        # the last seasonal form and the first ordinary form.
        if form_key in seasonal_keys:
            next_key = all_forms[i + 1][0] if i + 1 < len(all_forms) else ""
            if next_key and next_key not in seasonal_keys:
                for p in range(start + 1, next_start):
                    page_text = pages[p - 1]
                    if "Morning and Evening Prayer" in page_text and "Ordinary Time" in page_text:
                        end = p - 1
                        break

        bounds[form_key] = (start, end)

    return bounds


def main():
    ap = argparse.ArgumentParser(description="Detect office form page bounds from PDF content")
    ap.add_argument("--write", action="store_true", help="Write office_bounds.json")
    ap.add_argument("--strict", action="store_true",
                    help="Fail if detection differs from committed file")
    args = ap.parse_args()

    if not PDF.exists():
        sys.exit(f"PDF not found: {PDF}\nRun: make fetch-sources")

    bounds = detect(PDF)

    if args.write:
        output = {k: {"start": s, "end": e} for k, (s, e) in bounds.items()}
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"Wrote {len(output)} forms to {OUT}")

    if args.strict:
        if not OUT.exists():
            sys.exit(f"No committed bounds file at {OUT}\nRun with --write first")
        committed = json.loads(OUT.read_text())
        committed_bounds = {k: (v["start"], v["end"]) for k, v in committed.items()}
        if committed_bounds != bounds:
            print("ERROR: detected bounds differ from committed file", file=sys.stderr)
            for k in bounds:
                if k not in committed_bounds:
                    print(f"  NEW: {k} = {bounds[k]}", file=sys.stderr)
                elif bounds[k] != committed_bounds[k]:
                    print(f"  CHANGED: {k}: committed={committed_bounds[k]}, detected={bounds[k]}",
                          file=sys.stderr)
            for k in committed_bounds:
                if k not in bounds:
                    print(f"  MISSING: {k} (was {committed_bounds[k]})", file=sys.stderr)
            sys.exit(1)
        print(f"All {len(bounds)} forms match committed bounds.")

    if not args.write and not args.strict:
        for k, (s, e) in sorted(bounds.items()):
            print(f"  {k:<30} pp. {s:3d}–{e:3d}")


if __name__ == "__main__":
    main()
