#!/usr/bin/env python3
"""
check_casing.py — casing oracle for data/offices.json against pdftotext.

Why this exists (BUG-25 / BUG-18):
  pdfplumber (the extraction pipeline) decodes the PDF's small-caps response
  font as *lowercase*; `pdftotext` (poppler) decodes the same glyphs with the
  correct case. So pdftotext output is a free ground-truth oracle for casing.
  This tool would have caught all 22 BUG-25 "Holy One" errors — and BUG-18's
  over-correction — automatically.

What it does:
  For every leader / response / label segment in offices.json (resolving
  `_shared` refs and recursing into `alternatives` groups), locate the text in
  the pdftotext output (case-insensitively) and compare the two slices
  character-by-character.

  Two kinds of difference, kept apart because only one is a defect:
    * INTERNAL — a casing difference at any position other than the segment's
      first letter. This is the real signal: divine titles ("holy one" vs
      "Holy One" — BUG-25), proper nouns ("israel" vs "Israel"). Strict mode
      gates on these.
    * FIRST-LETTER — the opening character differs and nothing else. The app
      deliberately capitalises response openings (`_fix_casing`), while the PDF
      keeps grammatical continuations lowercase after a colon. This is an
      editorial choice (the BUG-18 territory), not a decoding error, so it is
      an informational count only — never gates.

  Segments not found at all (synthesized like reading_response, or reworded by
  patches) are counted as informational "unmatched" — never errors.

Exits 0 always (advisory).  Pass --strict to exit 1 on any INTERNAL mismatch
outside the allowlist.  Pass --show-first-letter to list the first-letter
differences too.

Usage:
    python3 tools/check_casing.py [--strict]
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
PDF = ROOT / "sources" / "pray-without-ceasing.pdf"
OFFICES = ROOT / "data" / "offices.json"

# Segment types that carry spoken/sung text whose casing the PDF fixes.
_CASED_TYPES = {"leader", "response", "label"}

# Responses that are INTENTIONALLY lowercase in the data (BUG-18 EP): they are
# grammatical continuations of the preceding leader line, verified lowercase in
# the PDF (pdftotext). Listed here so a future decoding quirk that flips them
# doesn't read as a regression. See BUGS.md BUG-18 / BUG-25, CORRECTNESS.md.
KNOWN_INTENTIONAL = {
    "to declare the mystery of Christ.",
    "behold and tend the vine you have planted.",
    "in the strength of your name.",
    "as we have put our hope in you.",
}

_WS = re.compile(r"\s+")
_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})


def _norm(text: str) -> str:
    """Collapse whitespace and straighten quotes so data and PDF align."""
    return _WS.sub(" ", text.translate(_QUOTES)).strip()


def pdf_text() -> tuple[str, str]:
    """Return (normalised original-case PDF text, casefolded copy)."""
    if not PDF.exists():
        print(f"ERROR: source PDF not found: {PDF}\n"
              f"  Run `make fetch-sources` first.", file=sys.stderr)
        sys.exit(2)
    raw = subprocess.run(
        ["pdftotext", str(PDF), "-"],
        capture_output=True, text=True, check=True,
    ).stdout
    norm = _norm(raw)
    return norm, norm.casefold()


def iter_segments(offices: dict):
    """Yield (office_key, section_key, text) for every cased segment.

    Resolves whole-field and inline `_shared` refs and recurses into
    `alternatives` groups.
    """
    shared = offices.get("_shared", {})

    def resolve(node):
        if isinstance(node, dict) and node.get("type") == "shared":
            return shared.get(node.get("key"), [])
        return node

    def walk(segs, office_key, section_key):
        segs = resolve(segs)
        if not isinstance(segs, list):
            return
        for seg in segs:
            if not isinstance(seg, dict):
                continue
            if seg.get("type") == "shared":
                walk(resolve(seg), office_key, section_key)
            elif seg.get("type") == "alternatives":
                for group in seg.get("groups", []):
                    walk(group.get("segments", []), office_key, section_key)
            elif seg.get("type") in _CASED_TYPES:
                text = seg.get("text") or ""
                if text.strip():
                    yield_targets.append((office_key, section_key, text))

    for office_key, form in offices.items():
        if office_key.startswith("_") or not isinstance(form, dict):
            continue
        for section_key, section in form.items():
            if section_key in ("title", "subtitle"):
                continue
            yield_targets.clear()
            walk(section, office_key, section_key)
            yield from yield_targets


# module-level scratch used by the nested walker above
yield_targets: list = []


def _classify(seg: str, pdf_slice: str) -> str:
    """Return 'match', 'first_letter', or 'internal' for two equal-length,
    case-insensitively-identical strings."""
    diffs = [i for i in range(len(seg)) if seg[i] != pdf_slice[i]]
    if not diffs:
        return "match"
    first_alpha = next((i for i, c in enumerate(seg) if c.isalpha()), None)
    if any(i != first_alpha for i in diffs):
        return "internal"
    return "first_letter"


def main():
    ap = argparse.ArgumentParser(description="Casing oracle vs pdftotext.")
    ap.add_argument("--strict", action="store_true",
                    help="Exit 1 on any INTERNAL mismatch outside the allowlist.")
    ap.add_argument("--show-first-letter", action="store_true",
                    help="Also list the first-letter (editorial) differences.")
    args = ap.parse_args()

    offices = json.loads(OFFICES.read_bytes())
    pdf_norm, pdf_low = pdf_text()

    internal: list[tuple[str, str, str, str]] = []
    first_letter: list[tuple[str, str, str, str]] = []
    allowlisted = 0
    unmatched = 0
    checked = 0

    for office_key, section_key, text in iter_segments(offices):
        seg = _norm(text)
        if not seg:
            continue
        checked += 1
        idx = pdf_low.find(seg.casefold())
        if idx < 0:
            unmatched += 1
            continue
        pdf_slice = pdf_norm[idx: idx + len(seg)]
        kind = _classify(seg, pdf_slice)
        if kind == "match":
            continue
        if seg in KNOWN_INTENTIONAL:
            allowlisted += 1
            continue
        (internal if kind == "internal" else first_letter).append(
            (office_key, section_key, seg, pdf_slice)
        )

    if internal:
        print("CASING MISMATCHES (internal — likely errors):\n")
        for office_key, section_key, data_text, pdf_slice in internal:
            print(f"{office_key}/{section_key}:")
            print(f'  data: "{data_text}"')
            print(f'  pdf:  "{pdf_slice}"')
        print()

    if args.show_first_letter and first_letter:
        print("First-letter differences (editorial — app capitalises response "
              "openings; informational):\n")
        for office_key, section_key, data_text, pdf_slice in first_letter:
            print(f"{office_key}/{section_key}: "
                  f'"{data_text[:1]}…" vs pdf "{pdf_slice[:1]}…"')
        print()

    print(
        f"checked {checked} segments — {len(internal)} internal mismatch(es); "
        f"{len(first_letter)} first-letter, {allowlisted} allowlisted, "
        f"{unmatched} unmatched (all informational)."
    )
    if not internal:
        print("No casing errors found.")

    if internal and args.strict:
        sys.exit(1)


if __name__ == "__main__":
    main()
