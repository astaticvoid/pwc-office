"""
add_collect_names.py — enrich data/collects.json with feast names from BAS PDF.

Reads sources/BAS.pdf to extract the liturgical name (feast/Sunday heading) for
each collect page, then rewrites data/collects.json with a name field added to
each entry.

The existing text values are preserved exactly — only the name field is added.

Usage: python3 tools/add_collect_names.py
"""

import json
import re
import sys
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).parent.parent

# Pages in the BAS collect range (book page numbers).
COLLECT_RANGE = (262, 448)

# Non-heading lines: these patterns at the START of a line disqualify it from
# being a feast heading even if it appears before "Sentence".
_NOT_HEADING = re.compile(
    r'^(?:'
    r'Prayer over|Preface of|Prayer after|Preface$|'
    r'Sentence$|Readings?$|Refrain|'
    r'Celebrant|People|Reader|Deacon|Cantor|Leader|'
    r'[ABC] \w|'                            # Year-letter readings lines
    r'Sundays and Holy Days$|'
    r"Saints' Days and Other Holy Days$|"
    r"Common Propers for Saints' Days$|"
    r'Holy Week$|'
    r'The Celebration|The Ministry|The Procession|'
    r'If |When |After |In the absence|'
    r'These |Several |Concerning |Notes |'
    r'All shall |All remain|The service|'
    r'This liturgy|This Sunday|This festival|'
    r'The readings|The propers|'
    r'Calendar\.|'                          # rubric calendar note
    r'To be used|Tobeused|'                # garbled/normal votive rubric
    r'With the Liturgy'
    r')'
)


def _feast_name_before_marker(text: str) -> str:
    """
    Return the feast heading that appears immediately before the first
    occurrence of a 'Sentence' or 'Collect of the Day' section marker on
    this page, or "" if none found.
    """
    # Find the earliest section marker.
    m = re.search(r'\nSentence\n|\nCollect of the Day\.?\n', text)
    if not m:
        return ""

    before = text[: m.start()]
    lines = [l.strip() for l in before.splitlines() if l.strip()]

    # Walk backwards past generic section-header lines.
    for line in reversed(lines):
        if not line:
            continue
        if re.search(r'\b\d{3}\b', line):      # running header with page number
            continue
        if _NOT_HEADING.match(line):
            continue
        if len(line) > 80:                  # too long for a feast heading
            continue
        if line[0].islower():               # prose continuation
            continue
        if line[0].isdigit():               # date fragment e.g. "31 May"
            continue
        if line.endswith(('.', ',')):       # sentence fragments, not titles
            continue
        if re.search(r'\b(?:instead of|or to the|or those of|assigned for|may be read)\b', line):
            continue                         # rubric connectors mid-line
        if re.search(r'\w\. [A-Z]', line):  # internal sentence break: "Day. When…"
            continue
        return line

    return ""


def _special_service_heading(text: str) -> str:
    """
    Some services (Ash Wednesday, Maundy Thursday, Good Friday, etc.) open
    with the feast name followed by liturgical description rather than Sentence.
    Detect those.
    """
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    if not lines:
        return ""
    first = lines[0]
    if re.search(r'\b\d{3}\b', first):      # running header, skip
        if len(lines) > 1:
            first = lines[1]
        else:
            return ""

    # Second line must look like introductory rubric prose (starts lowercase
    # or with known rubric words).
    if len(lines) < 2:
        return ""
    second = lines[1]
    if re.match(r'^(?:This liturgy|On this day|The glory|When the congregation|'
                r'The Celebration|With the Liturgy)', second):
        if (first and not _NOT_HEADING.match(first)
                and not re.search(r'\b\d{3}\b', first)
                and len(first) < 80):
            return first
    return ""


def build_name_map(pdf) -> dict[int, str]:
    """
    Scan all pages in the collect range and return a mapping of
    book_page → feast_name, carrying the most recent name forward to pages
    that don't start a new feast.
    """
    name_map: dict[int, str] = {}
    current_name = ""

    start, end = COLLECT_RANGE
    for idx in range(start - 1, end):
        book_page = idx + 1
        text = pdf.pages[idx].extract_text() or ""

        # Try to detect a new feast heading on this page.
        candidate = _feast_name_before_marker(text)
        if not candidate:
            candidate = _special_service_heading(text)

        if candidate:
            current_name = candidate

        name_map[book_page] = current_name

    return name_map


def run():
    pdf_path = ROOT / "sources" / "BAS.pdf"
    if not pdf_path.exists():
        print(f"ERROR: {pdf_path} not found", file=sys.stderr)
        sys.exit(1)

    json_path = ROOT / "data" / "collects.json"
    if not json_path.exists():
        print(f"ERROR: {json_path} not found — run extract_collects.py first",
              file=sys.stderr)
        sys.exit(1)

    with open(json_path, encoding="utf-8") as f:
        raw = json.load(f)

    print("Building feast-name map from BAS PDF…")
    with pdfplumber.open(pdf_path) as pdf:
        name_map = build_name_map(pdf)

    # Merge: update name from BAS PDF scan, preserve all other fields.
    enriched: dict[str, dict] = {}
    for key in sorted(raw, key=lambda k: int(k)):
        entry = dict(raw[key])
        page = int(key)
        name = name_map.get(page, "")
        if name:
            entry["name"] = name
        enriched[key] = entry
        print(f"  p.{key:>3}  {name!r}")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)

    print(f"\nWrote {len(enriched)} enriched collects → {json_path}")

    # Spot-check a few names.
    checks = [
        ("268", "First Sunday of Advent"),
        ("269", "Second Sunday of Advent"),
        ("272", "Fourth Sunday of Advent"),
        ("280", "The Epiphany"),
        ("281", "Ash Wednesday"),
        ("299", "The Sunday of the Passion"),
        ("344", "Seventh Sunday of Easter"),
    ]
    print("\nName spot checks:")
    ok = True
    for key, want_fragment in checks:
        got = enriched.get(key, {}).get("name", "")
        found = want_fragment in got
        print(f"  p.{key} name contains {want_fragment!r}: {'✓' if found else '✗'}  (got {got!r})")
        if not found:
            ok = False
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    run()
