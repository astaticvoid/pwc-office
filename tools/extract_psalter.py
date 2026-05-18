#!/usr/bin/env python3
"""
Extract the Liturgical Psalter from pray-without-ceasing.txt → data/psalter.yaml

Structure of the source text (PDF-to-text artefacts):
  • Page headers appear in two forms, sometimes mid-line:
      "NNN    Liturgical PsalterXXX"     (page number prefix)
      "  Liturgical Psalter     NNNXXX"  (page number suffix)
    Where XXX is empty, a psalm heading, a verse, or a continuation.
  • Psalm headings: "Psalm N  Latin title"
  • Section headings within psalms:
      "Part I  Latin title" / "Part II  ..."  (multi-part psalms)
      Hebrew letter names  (Psalm 119 only)
  • Verses: "N  verse text *"  then continuation lines
  • Continuation lines may or may not start with whitespace.
  • Book markers ("BooK i", "BooK ii" …) are structural noise.

Run from repo root:
    python3 tools/extract_psalter.py
"""

import json
import re
import subprocess
import sys
from pathlib import Path


def _ensure_txt(pdf_path: Path, txt_path: Path) -> None:
    """Generate txt_path from pdf_path if it doesn't already exist.

    Tries pdftotext (poppler) first for best encoding fidelity; falls back to
    pdfplumber if pdftotext is not installed.
    """
    if txt_path.exists():
        return
    print(f"Generating {txt_path.name} from {pdf_path.name}...", file=sys.stderr)
    try:
        subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), str(txt_path)],
            check=True, capture_output=True,
        )
        return
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    try:
        import pdfplumber
    except ImportError:
        print("ERROR: pdftotext not found and pdfplumber not installed — cannot generate txt",
              file=sys.stderr)
        sys.exit(1)
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text(layout=True) or "")
    txt_path.write_text("\n\f\n".join(pages), encoding="utf-8")

# ── Patterns ───────────────────────────────────────────────────────────────────

# Matches either page-header form and captures whatever follows it.
# The trailing-number form uses \d{3} (not greedy \d+) because psalter pages are
# always 3 digits (231-364) and content may follow immediately after the page
# number with no separator (e.g. "Liturgical Psalter     24318  They confronted…").
RE_PAGE = re.compile(
    r'(?:\d+\s+Liturgical Psalter|Liturgical Psalter\s+\d{3})(.*)'
)

# "Psalm N  Latin title" — the title part may be empty (e.g., Psalm 119)
RE_PSALM_HEAD = re.compile(r'^Psalm\s+(\d+)\s*(.*)')

# "N verse text" — one or more spaces after the verse number
RE_VERSE = re.compile(r'^(\d+)\s+(.*)')

# Section headings within psalms (Part I/II/III/IV, or Hebrew letter names)
_HEBREW = (
    r'Aleph|Beth|Gimel|Daleth|He|Vau|Waw|Zayin|Cheth|Teth|Yodh|'
    r'Kaph|Lamedh|Mem|Nun|Samekh|Ayin|Pe|Sadhe|Tzadhe|Qoph|Resh|Shin|Tau|Taw'
)
RE_SECTION = re.compile(rf'^(?:Part\s+[IVX]+|{_HEBREW})\s*(.*)')

# Book markers to skip
RE_BOOK = re.compile(r'^BooK\s+[ivxIVX]+', re.I)


# Typographic → ASCII quote normalisation applied to every source line.
# The PDF-to-text output uses curly quotes; YAML double-quoted scalars need
# straight quotes to avoid prematurely terminating the YAML string value.
_QUOTE_MAP = str.maketrans({
    "“": '"',   # LEFT DOUBLE QUOTATION MARK
    "”": '"',   # RIGHT DOUBLE QUOTATION MARK
    "‘": "'",   # LEFT SINGLE QUOTATION MARK
    "’": "'",   # RIGHT SINGLE QUOTATION MARK
})


def normalise_quotes(s: str) -> str:
    s = s.translate(_QUOTE_MAP)
    # Fix PDF indentation artifact: a line that starts with an opening quote
    # followed by spaces before the text, e.g. '"  The mercy' → '"The mercy'.
    # Only match at line-start (^) so we don't strip the space after closing
    # quotes mid-line, e.g. 'yoke," they say' must stay intact.
    s = re.sub(r'^"( +)(?=\S)', '"', s, flags=re.MULTILINE)
    return s


# ── Line cleaner ───────────────────────────────────────────────────────────────

def strip_page_header(line: str) -> str | None:
    """
    Remove page-header artefact from a line.
    Returns the residual content (may be empty string), or None if the line
    contained ONLY a page header with no psalm/verse content.
    Leaves non-header lines unchanged.
    """
    m = RE_PAGE.match(line.strip())
    if m:
        return m.group(1)  # residual (may be "")
    return line


# ── Psalter extractor ──────────────────────────────────────────────────────────

def extract_psalms(path: Path) -> list[dict]:
    """
    Read the source text and return a list of psalm dicts:
        {number: int, title: str, text: str}
    where `text` is clean multi-line psalm content with:
      • verse numbers preserved ("N  verse text")
      • section headings preserved as-is ("Aleph", "Part I", …)
      • no page-header artefacts
      • no Book-division markers
    """
    raw_lines = path.read_text(encoding="utf-8").splitlines()

    # ── Find the start of the Psalter ─────────────────────────────────────────
    # Look for "BooK i" after the evening prayer section.
    psalter_start = None
    for i, line in enumerate(raw_lines):
        cleaned = strip_page_header(line)
        if cleaned is not None and RE_BOOK.match(cleaned.strip()):
            # The FIRST "Book I" in the file is the Psalter section.
            # (Earlier "BooK" never appears outside the Psalter.)
            if psalter_start is None:
                psalter_start = i
                break

    if psalter_start is None:
        sys.exit("Could not locate the Psalter section.")

    # ── Parse lines ───────────────────────────────────────────────────────────
    psalms: list[dict] = []
    cur_num: int | None = None
    cur_title: str = ""
    cur_lines: list[str] = []

    def psalm_book(n: int) -> int:
        if n <= 41:  return 1
        if n <= 72:  return 2
        if n <= 89:  return 3
        if n <= 106: return 4
        return 5

    def flush():
        if cur_num is not None:
            psalms.append({
                "number": cur_num,
                "book": psalm_book(cur_num),
                "title": cur_title,
                "text": "\n".join(cur_lines).strip(),
            })

    for raw in raw_lines[psalter_start:]:
        raw = normalise_quotes(raw)
        # Stop at the Acknowledgements section that follows Psalm 150.
        if "Acknowledgements" in raw:
            break
        line = strip_page_header(raw)
        if line is None:
            continue
        line = line.rstrip()
        stripped = line.strip()

        # Skip empty lines and Book markers.
        if not stripped or RE_BOOK.match(stripped):
            continue

        # ── Psalm heading ──────────────────────────────────────────────────
        m = RE_PSALM_HEAD.match(stripped)
        if m:
            flush()
            cur_num = int(m.group(1))
            cur_title = m.group(2).strip()
            cur_lines = []
            continue

        # Nothing to accumulate before the first psalm.
        if cur_num is None:
            continue

        # ── Section heading (Part I/II, Hebrew letters) ────────────────────
        if RE_SECTION.match(stripped):
            cur_lines.append(stripped)
            continue

        # ── Numbered verse ─────────────────────────────────────────────────
        mv = RE_VERSE.match(stripped)
        if mv:
            cur_lines.append(stripped)
            continue

        # ── Continuation line ──────────────────────────────────────────────
        # Indent with a single space to distinguish from verse-start lines,
        # preserving the original chant-score layout.
        cur_lines.append(" " + stripped)

    flush()  # save the last psalm

    return psalms


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    root = Path(__file__).parent.parent
    src = root / "sources" / "pray-without-ceasing.txt"

    _ensure_txt(root / "sources" / "pray-without-ceasing.pdf", src)
    psalms = extract_psalms(src)

    found = {p["number"] for p in psalms}
    missing = [n for n in range(1, 151) if n not in found]
    if missing:
        print(f"WARNING: missing psalms: {missing}", file=sys.stderr)

    psalter = {str(p["number"]): p for p in psalms}
    psalter_path = root / "data" / "psalter.json"
    psalter_path.parent.mkdir(parents=True, exist_ok=True)
    with open(psalter_path, "w", encoding="utf-8") as f:
        json.dump(psalter, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(psalms)} psalms to {psalter_path}")
    if missing:
        print(f"  Missing: {missing}")



if __name__ == "__main__":
    main()
