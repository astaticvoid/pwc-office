"""
extract_lib.py — shared utilities for PDF extraction tools.

Imported by: extract_psalter.py, extract_collects.py, extract_offices.py,
             and any future BAS office-form extractor.
"""

import json
import subprocess
import sys
from pathlib import Path


# ── PDF → text ────────────────────────────────────────────────────────────────

def ensure_txt(pdf_path: Path, txt_path: Path, prefer_pdftotext: bool = True) -> None:
    """Generate txt_path from pdf_path if it does not already exist.

    Tries pdftotext (poppler) first for best encoding fidelity.  Falls back to
    pdfplumber if pdftotext is not installed.  When prefer_pdftotext=False the
    fallback warning is omitted (use when pdfplumber quality is acceptable).
    """
    if txt_path.exists():
        return
    print(f"Generating {txt_path.name} from {pdf_path.name}…", file=sys.stderr)
    try:
        subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), str(txt_path)],
            check=True, capture_output=True,
        )
        return
    except (FileNotFoundError, subprocess.CalledProcessError):
        if prefer_pdftotext:
            print(
                "WARNING: pdftotext not found — falling back to pdfplumber "
                "(some pages may have garbled text)",
                file=sys.stderr,
            )
    try:
        import pdfplumber  # noqa: PLC0415
    except ImportError:
        print(
            "ERROR: neither pdftotext nor pdfplumber is available — cannot generate txt",
            file=sys.stderr,
        )
        sys.exit(1)
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text(layout=True) or "")
    txt_path.write_text("\n\f\n".join(pages), encoding="utf-8")


# ── JSON output ───────────────────────────────────────────────────────────────

def write_json(data: object, path: Path) -> None:
    """Write data to path as indented JSON with a trailing newline."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


# ── Typography ────────────────────────────────────────────────────────────────

_QUOTE_MAP = str.maketrans({
    "“": '"',   # LEFT DOUBLE QUOTATION MARK
    "”": '"',   # RIGHT DOUBLE QUOTATION MARK
    "‘": "'",   # LEFT SINGLE QUOTATION MARK
    "’": "'",   # RIGHT SINGLE QUOTATION MARK
})


def normalise_quotes(s: str) -> str:
    """Replace curly/smart quotes with straight ASCII equivalents.

    Also fixes a PDF indentation artifact where an opening quote is followed
    by extra spaces before the verse text (e.g. '"  The mercy' → '"The mercy').
    """
    import re  # noqa: PLC0415
    s = s.translate(_QUOTE_MAP)
    s = re.sub(r'^"( +)(?=\S)', '"', s, flags=re.MULTILINE)
    return s
