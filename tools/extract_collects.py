"""
extract_collects.py — extract BAS collects by book page number.

Reads sources/BAS.pdf directly and uses a transient pdftotext extraction
for pages that pdfplumber garbles due to font encoding issues.
Writes data/collects.json.

Each collect entry includes:
  name    — liturgical name extracted from BAS heading
  section — BAS section ("Sundays and Holy Days", "Saints' Days…", "Common Propers")
  season  — liturgical season ("Advent", "Lent", "Easter", etc.) or "" for holy days/commons
  proper  — Proper number (int) for post-Epiphany/Pentecost Sundays, or absent
  date    — fixed calendar date ("14 May") for feasts on fixed dates, or absent
  text    — literal-block collect prayer text

Usage: python3 tools/extract_collects.py [--accept]

  --accept  Update tools/manifest.json with current output hashes.
"""

import argparse
import re
import sys
from pathlib import Path

import pdfplumber

from extract_lib import check_manifest, pdf_as_txt, write_json

ROOT = Path(__file__).parent.parent

# ── Page range ────────────────────────────────────────────────────────────────
FIRST_PAGE = 262   # book page where Proper of the Church Year begins
LAST_PAGE  = 447   # last page of Common Propers

# ── Occasional Prayers page range ─────────────────────────────────────────────
# BAS pp.675-683: "Occasional Prayers and Thanksgivings" section.
# p.675 is a TOC; pp.676-683 contain the numbered prayers (1-33).
OCCASIONAL_FIRST_PAGE = 676
OCCASIONAL_LAST_PAGE  = 683

# Map from BAS page reference → prayer number within the section.
# The lectionary cites these as "Coll N, PAGE" (e.g. "8, 677 (The King)").
# Multiple prayers appear on a single page, so we use explicit mappings rather
# than a per-page heuristic.
_OCC_PAGE_ALIASES = {
    "677": "8",   # prayer 8 "For the Queen/Sovereign" appears on BAS p.677
    "680": "17",  # prayer 17 "For Industry and Commerce" begins BAS p.680
}

# Matches numbered prayer headers: "8 For the Queen", "32 A General Intercession"
_OCC_HEADER = re.compile(r'^(\d+) ([A-Z][^\n]+)', re.MULTILINE)

# ── Pages where pdfplumber garbles text; always use pdftotext fallback ────────
# These pages have font-encoding issues that pdfplumber cannot recover from.
# pdftotext produces clean text for them, so we bypass the garbling check.
_TXT_FALLBACK_PAGES = {356, 358, 392, 396}

# ── Terminator patterns ───────────────────────────────────────────────────────
_TERMINATORS = re.compile(
    r'\n(?:Readings|Prayer over the Gifts|Preface of|Prayer after Communion'
    r'|Sentence|In the absence)\b'
)

# Liturgical exchange lines that appear between "Collect of the Day" and text.
_EXCHANGE = re.compile(
    r'^(?:Celebrant[^\n]*|People[^\n]*|Let ?us pray\.?'
    r'|The Lord be with you\.?|And also with you\.?)\n',
    re.MULTILINE,
)

# ── Collect-body finder ───────────────────────────────────────────────────────

def _find_collect_body(text: str) -> str:
    """
    Return the text immediately following a collect header, or "" if none.

    Handles three header styles:
      1. Bare "Collect" on its own line
      2. "Collect of the Day" followed by optional liturgical exchange
      3. "collect is said." in prose (Palm Sunday procession)

    When multiple headers appear, the last one wins.
    """
    best = -1
    body_start = -1

    for m in re.finditer(r'(?:^|\n)(Collect)\n', text):
        pos = m.start(1)
        end = m.end()
        if pos > best:
            best = pos
            body_start = end

    for m in re.finditer(r'Collect of the Day\.?\n', text):
        pos = m.start()
        if pos > best:
            best = pos
            rest = text[m.end():]
            skip = _EXCHANGE.match(rest)
            while skip:
                rest = rest[skip.end():]
                skip = _EXCHANGE.match(rest)
            body_start = len(text) - len(rest)

    for m in re.finditer(r'collect is said\.\n', text):
        pos = m.start()
        if pos > best:
            best = pos
            body_start = m.end()

    if body_start == -1:
        return ""
    return text[body_start:]


def _clean(text: str) -> str:
    """Strip PDF running-header lines anywhere in text (e.g. '270 Advent', '308 Good Friday')."""
    return re.sub(r'\n[^\n]*\b\d{3}\b[^\n]*', '', text.strip()).strip()


def extract_collect(text: str, overflow: str = "") -> str:
    """
    Find the last collect on a page and return its body text.
    Uses overflow (next page) if the collect appears to run past the page break.
    """
    body = _find_collect_body(text)
    if not body:
        return ""

    m = _TERMINATORS.search(body)
    if m:
        return _clean(body[: m.start()])

    combined = body + "\n" + overflow
    m = _TERMINATORS.search(combined)
    if m:
        return _clean(combined[: m.start()])

    return _clean(body)


# ── Garbling detection ────────────────────────────────────────────────────────

def is_garbled(text: str) -> bool:
    """Return True if text has words concatenated without spaces (font-encoding bug)."""
    return bool(re.search(r'[a-z]{14,}', text))


# ── BAS.txt fallback ──────────────────────────────────────────────────────────

def _load_bas_txt(path: Path) -> str:
    # pdftotext uses \x0c as page separators; normalise to \n so collect
    # patterns like r'(?:^|\n)(Collect)\n' match across page breaks.
    return path.read_text(encoding="utf-8", errors="replace").replace("\x0c", "\n")


def _find_first_collect_body(text: str) -> str:
    """Return text after the FIRST collect header found."""
    best = len(text)
    body_start = -1

    for m in re.finditer(r'(?:^|\n)(Collect)\n', text):
        pos = m.start(1)
        if pos < best:
            best = pos
            body_start = m.end()

    for m in re.finditer(r'Collect of the Day\.?\n', text):
        pos = m.start()
        if pos < best:
            best = pos
            rest = text[m.end():]
            skip = _EXCHANGE.match(rest)
            while skip:
                rest = rest[skip.end():]
                skip = _EXCHANGE.match(rest)
            body_start = len(text) - len(rest)

    for m in re.finditer(r'collect is said\.\n', text):
        pos = m.start()
        if pos < best:
            best = pos
            body_start = m.end()

    if body_start == -1:
        return ""
    return text[body_start:]


def extract_collect_from_txt(bas_txt: str, feast_name: str) -> str:
    """
    Extract a collect from BAS.txt by anchoring on the feast heading.
    Uses the FIRST collect found after the anchor (not last) to avoid
    spilling into the next feast's window.
    Returns "" if the feast name cannot be found.
    """
    if not bas_txt or not feast_name:
        return ""

    # Use first 20 chars of the feast name for search robustness.
    anchor = re.escape(feast_name[:20].rstrip())
    m = re.search(anchor, bas_txt, re.IGNORECASE)
    if not m:
        # Try first word only as a fallback.
        first_word = feast_name.split()[0] if feast_name.split() else ""
        if first_word and len(first_word) > 4:
            m = re.search(re.escape(first_word), bas_txt, re.IGNORECASE)
        if not m:
            return ""

    window = bas_txt[m.start(): min(m.start() + 3000, len(bas_txt))]
    body = _find_first_collect_body(window)
    if not body:
        return ""
    mt = _TERMINATORS.search(body)
    if mt:
        return _clean(body[: mt.start()])
    return _clean(body)


# ── Feast-name extraction (from BAS page headings) ────────────────────────────

_NOT_HEADING = re.compile(
    r'^(?:'
    r'Prayer over|Preface of|Prayer after|Preface$|'
    r'Sentence$|Readings?$|Refrain|'
    r'Celebrant|People|Reader|Deacon|Cantor|Leader|'
    r'[ABC] \w|'
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
    r'Calendar\.|'
    r'To be used|Tobeused|'
    r'With the Liturgy'
    r')'
)


def _feast_name_from_page(text: str) -> str:
    """
    Return the feast/Sunday heading that appears immediately before the first
    Sentence or Collect-of-the-Day marker on this page, or "" if none found.
    """
    m = re.search(r'\nSentence\n|\nCollect of the Day\.?\n', text)
    if not m:
        return ""

    before = text[: m.start()]
    lines = [l.strip() for l in before.splitlines() if l.strip()]

    for line in reversed(lines):
        if not line:
            continue
        if re.search(r'\b\d{3}\b', line):
            continue
        if _NOT_HEADING.match(line):
            continue
        if len(line) > 80:
            continue
        if line[0].islower():
            continue
        if line[0].isdigit():
            continue
        if line.endswith(('.', ',')):
            continue
        if re.search(r'\b(?:instead of|or to the|or those of|assigned for|may be read)\b', line):
            continue
        if re.search(r'\w\. [A-Z]', line):
            continue
        return line.rstrip(':').rstrip()

    return ""


def _special_service_heading(text: str) -> str:
    """Detect feast names on special-service pages (no Sentence in standard position)."""
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    if not lines:
        return ""
    first = lines[0]
    if re.search(r'\b\d{3}\b', first):
        first = lines[1] if len(lines) > 1 else ""
    if not first:
        return ""

    if len(lines) < 2:
        return ""
    second = lines[1]
    if re.match(
        r'^(?:This liturgy|On this day|The glory|When the congregation|The Celebration|With the Liturgy)',
        second,
    ):
        if first and not _NOT_HEADING.match(first) and not re.search(r'\b\d{3}\b', first) and len(first) < 80:
            return first
    return ""


# ── Metadata derivation ───────────────────────────────────────────────────────

def section_from_page(page: int) -> str:
    if page <= 395:
        return "Sundays and Holy Days"
    if page <= 397:
        return "Special Observances"
    if page <= 431:
        return "Saints' Days and Other Holy Days"
    if page <= 447:
        return "Common Propers"
    return "Occasional Prayers"


def season_from_name(name: str) -> str:
    n = name.lower()
    if "advent" in n:
        return "Advent"
    if any(w in n for w in ("christmas", "naming of jesus", "first sunday after christmas",
                             "second sunday after christmas", "first sunday of christmas",
                             "second sunday of christmas")):
        return "Christmas"
    if any(w in n for w in ("epiphany", "after epiphany", "baptism of the lord",
                             "sunday before the epiphany")):
        return "Epiphany"
    if any(w in n for w in ("ash wednesday", "lent", "lenten")):
        return "Lent"
    if any(w in n for w in ("holy week", "monday in holy", "tuesday in holy",
                             "wednesday in holy", "maundy thursday",
                             "good friday", "holy saturday", "passion")):
        return "Passiontide"
    if any(w in n for w in ("easter vigil", "easter", "ascension")):
        return "Easter"
    if "last sunday after pentecost" in n:
        return "OrdinaryTime"
    if any(w in n for w in ("pentecost", "trinity sunday")):
        return "Pentecost"
    if any(w in n for w in ("sunday between", "proper ", "last sunday after pentecost",
                             "ember", "rogation", "harvest")):
        return "OrdinaryTime"
    return ""  # Holy Days and Common Propers have no specific season.


def proper_from_name(name: str) -> int | None:
    m = re.search(r'\bProper (\d+)\b', name)
    return int(m.group(1)) if m else None


_MONTHS = (r'January|February|March|April|May|June|July|August'
           r'|September|October|November|December')

def date_from_name(name: str) -> str:
    # Exclude dates that are the upper bound of a "between X and Y Month" range.
    m = re.search(rf'(?<! and )\b(\d{{1,2}} (?:{_MONTHS}))\b', name)
    return m.group(1) if m else ""


# ── Occasional Prayers extraction ─────────────────────────────────────────────

def _extract_occasional_prayers(pdf, collects: dict) -> None:
    """
    Parse BAS pp.676-683 (Occasional Prayers section) and add selected entries
    to the collects dict under their BAS page-reference keys.

    The section contains 33 numbered prayers.  Multiple prayers appear on each
    page, so a simple per-page heuristic cannot reliably assign the right prayer
    to a given page key.  Instead, all prayers are extracted and then stored
    under the explicit page aliases in _OCC_PAGE_ALIASES.
    """
    total = len(pdf.pages)
    all_text = ""
    for idx in range(OCCASIONAL_FIRST_PAGE - 1, min(OCCASIONAL_LAST_PAGE, total)):
        page_text = pdf.pages[idx].extract_text() or ""
        all_text += page_text + "\n"

    headers = list(_OCC_HEADER.finditer(all_text))

    entries: dict[str, dict] = {}
    for i, m in enumerate(headers):
        num = m.group(1)
        if not (1 <= int(num) <= 33):
            continue  # Skip page-footer numbers (676-683) that match the pattern
        name = m.group(2).strip()
        body_start = m.end()
        # Advance to the next valid prayer header to bound this prayer's text.
        next_valid = next(
            (h for h in headers[i + 1:] if 1 <= int(h.group(1)) <= 33),
            None,
        )
        body_end = next_valid.start() if next_valid else len(all_text)
        text = _clean(all_text[body_start:body_end])
        if text:
            entries[num] = {
                "name": name,
                "section": "Occasional Prayers",
                "text": text,
            }

    for page, num in _OCC_PAGE_ALIASES.items():
        if num in entries:
            collects[page] = entries[num]
            print(f"  occ p.{page}  prayer #{num} {entries[num]['name']!r}")
        else:
            print(f"  WARNING: occ prayer #{num} not found (needed for p.{page})")


# ── Main extraction loop ──────────────────────────────────────────────────────

def run():
    ap = argparse.ArgumentParser()
    ap.add_argument("--accept", action="store_true",
                    help="Update tools/manifest.json with current output hashes")
    args = ap.parse_args()

    pdf_path = ROOT / "sources" / "BAS.pdf"
    if not pdf_path.exists():
        print(f"ERROR: {pdf_path} not found", file=sys.stderr)
        sys.exit(1)

    out_path = ROOT / "data" / "collects.json"

    with pdf_as_txt(pdf_path) as bas_txt_path:
        bas_txt = _load_bas_txt(bas_txt_path)

    collects: dict[str, dict] = {}
    failures: list[int] = []
    txt_fallbacks: list[int] = []

    current_name = ""

    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)

        for idx in range(FIRST_PAGE - 1, min(LAST_PAGE, total)):
            book_page = idx + 1
            text = pdf.pages[idx].extract_text() or ""
            overflow_pdf = (pdf.pages[idx + 1].extract_text() or "") if idx + 1 < total else ""

            # ── Update current feast name ─────────────────────────────────
            candidate = _feast_name_from_page(text)
            if not candidate:
                candidate = _special_service_heading(text)
            if candidate:
                current_name = candidate

            # ── Extract collect text ──────────────────────────────────────
            collect_text = ""

            if is_garbled(text) or book_page in _TXT_FALLBACK_PAGES:
                # Fall back to BAS.txt for clean text.
                collect_text = extract_collect_from_txt(bas_txt, current_name)
                if collect_text:
                    txt_fallbacks.append(book_page)
                else:
                    # Last resort: still try PDF text (may be garbled).
                    collect_text = extract_collect(text, overflow_pdf)
            else:
                collect_text = extract_collect(text, overflow_pdf)

            if collect_text:
                proper = proper_from_name(current_name)
                date   = date_from_name(current_name)
                entry: dict = {
                    "name":    current_name,
                    "section": section_from_page(book_page),
                    "season":  season_from_name(current_name),
                    "text":    collect_text,
                }
                if proper is not None:
                    entry["proper"] = proper
                if date:
                    entry["date"] = date
                collects[str(book_page)] = entry
                print(f"  p.{book_page:3d}  {current_name!r}")
            elif re.search(r'\bCollect\b', text):
                failures.append(book_page)

        # ── Occasional Prayers section (pp.676-683) ───────────────────────────
        print("\nExtracting Occasional Prayers (pp.676-683)...")
        _extract_occasional_prayers(pdf, collects)

    # ── Supplemental collects outside the main extraction range ──────────────
    # These are from Occasional Services / other BAS sections not covered by
    # the page scan above. Add manually after verifying against the PDF.
    collects["668"] = {
        "name": "Anniversary of a Parish / Feast of Dedication",
        "section": "Occasional Services",
        # BAS pp. 668–669: collect for the Feast of Dedication of a Church.
        "text": (
            "Almighty God,\n"
            "watchful and caring,\n"
            "our source and our end,\n"
            "all that we are and all that we have are yours.\n"
            "Accept us now,\n"
            "as we give thanks to you for this place\n"
            "where we have come to praise your name,\n"
            "to ask your forgiveness,\n"
            "to know your healing power,\n"
            "to hear your word,\n"
            "and to be nourished by the body and blood of your Son.\n"
            "Be present always to guide and to judge,\n"
            "to illumine and to bless your people.\n"
            "This we pray in the name of Jesus Christ our Lord. Amen."
        ),
    }

    # BUG-29: collect texts are single prose prayers; the PDF's column-width
    # hard wraps are typographic, not semantic. Join internal line breaks so the
    # app wraps them naturally instead of mid-clause.
    for entry in collects.values():
        if entry.get("text"):
            entry["text"] = re.sub(r"\s*\n\s*", " ", entry["text"]).strip()

    write_json(collects, out_path)
    print(f"\nWrote {len(collects)} collects → {out_path}")
    if txt_fallbacks:
        print(f"txt fallback used for: {txt_fallbacks}")
    if failures:
        print(f"WARNING: pages mentioning Collect but not extracted: {failures}")

    # ── Spot checks ───────────────────────────────────────────────────────────
    checks = [
        ("268", "text",   "armour of light"),
        ("268", "name",   "First Sunday of Advent"),
        ("268", "season", "Advent"),
        ("280", "text",   "led wise men"),           # was garbled — txt fallback
        ("280", "name",   "The Epiphany"),
        ("281", "name",   "Ash Wednesday"),
        ("281", "season", "Lent"),
        ("308", "text",   "look graciously"),
        ("343", "name",   "Ascension of the Lord"),
        ("343", "season", "Easter"),
        ("360", "proper", 10),                        # "Proper 10"
        ("407", "date",   "14 May"),
        ("432", "section","Common Propers"),
        # p.392: txt fallback catches garbling; patches 007/008/010 fix remaining 3 pages
        ("392", "text",   "to be the light of the world"),
        # Occasional Prayers (pp.676-683)
        ("677", "name",   "For the Queen"),
        ("677", "text",   "fountain of all goodness"),
        ("677", "section","Occasional Prayers"),
        ("680", "name",   "For Industry and Commerce"),
        ("680", "text",   "dignified our labour"),
        ("680", "section","Occasional Prayers"),
    ]
    print("\nSpot checks:")
    ok = True
    for key, field, want in checks:
        entry = collects.get(key, {})
        got = entry.get(field, "")
        if isinstance(want, int):
            found = (got == want)
        else:
            found = (want in str(got))
        mark = "✓" if found else "✗"
        print(f"  p.{key} .{field} contains {want!r}: {mark}  (got {got!r})")
        if not found:
            ok = False
    if not ok:
        sys.exit(1)

    check_manifest([out_path], ROOT, accept=args.accept)


if __name__ == "__main__":
    run()
