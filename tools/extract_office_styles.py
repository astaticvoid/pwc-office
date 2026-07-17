#!/usr/bin/env python3
"""
extract_office_styles.py — PyMuPDF (fitz) style classification for office forms.

Reads sources/pray-without-ceasing.pdf and office_bounds.json, then for each
office form extracts span-level typed runs from PyMuPDF's get_text("dict") API.

Each span is classified as leader, response, rubric, heading, or footer using
native bitmask flags (bold/italic/serif) and sRGB color values.

Output: writable to stdout or a JSON file for consumption by align_extraction.py.

Usage:
    python3 tools/extract_office_styles.py [--office advent-mp] [--json out.json]
"""

import argparse
import json
import sys
from pathlib import Path

import fitz  # PyMuPDF

ROOT = Path(__file__).parent.parent
PDF = ROOT / "sources" / "pray-without-ceasing.pdf"
BOUNDS = ROOT / "tools" / "office_bounds.json"

# Colors observed in the PWC PDF (sRGB ints)
# 0x231F20 = near-black body text
# 0xBC303A = rubric red
_RED = 0xBC303A


def span_type(span: dict) -> str:
    """Classify a PyMuPDF span dict as leader/response/rubric/heading/footer."""
    flags = span["flags"]
    size = span["size"]
    color = span["color"]

    # Rubric: red text, regardless of weight
    if color == _RED:
        return "rubric"

    # Heading: bold + large font (title-level)
    if (flags & 16) and size >= 11:
        return "heading"

    # Response: bold, body-font size
    if flags & 16:
        return "response"

    # Footer: italic + small font + near page edge
    if (flags & 2) and size < 10:
        return "footer"

    return "leader"


def extract_office(pdf_doc: fitz.Document, form_key: str,
                   start_page: int, end_page: int) -> list[list[dict]]:
    """Return per-page lists of typed segments for one office form."""
    pages_output = []
    # MuPDF pages are 0-indexed
    for i in range(start_page - 1, end_page):
        page = pdf_doc[i]
        d = page.get_text("dict", flags=fitz.TEXTFLAGS_DICT)
        segments = []
        for block in d["blocks"]:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    text = span["text"].strip()
                    if not text:
                        continue
                    stype = span_type(span)
                    segments.append({
                        "type": stype,
                        "text": text,
                        "x0": span["bbox"][0],
                        "y0": span["bbox"][1],
                        "x1": span["bbox"][2],
                        "y1": span["bbox"][3],
                    })
        pages_output.append(segments)
    return pages_output


def main():
    ap = argparse.ArgumentParser(description="Extract styled text runs via PyMuPDF")
    ap.add_argument("--office", help="Single office form key (default: all)")
    ap.add_argument("--json", type=Path, help="Write JSON output to file")
    args = ap.parse_args()

    if not PDF.exists():
        sys.exit(f"PDF not found: {PDF}\nRun: make fetch-sources")
    if not BOUNDS.exists():
        sys.exit(f"Bounds file not found: {BOUNDS}\nRun: python3 tools/detect_office_bounds.py --write")

    bounds = json.loads(BOUNDS.read_text())

    if args.office:
        if args.office not in bounds:
            sys.exit(f"Unknown form: {args.office}")
        todo = {args.office: bounds[args.office]}
    else:
        todo = bounds

    doc = fitz.open(PDF)
    output = {}

    for form_key, b in todo.items():
        pages = extract_office(doc, form_key, b["start"], b["end"])
        output[form_key] = pages

    doc.close()

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"Wrote {args.json}")
    else:
        # Print summary
        for form_key, pages in sorted(output.items()):
            total = sum(len(segs) for segs in pages)
            types = {}
            for segs in pages:
                for s in segs:
                    types[s["type"]] = types.get(s["type"], 0) + 1
            type_str = " ".join(f"{t}:{c}" for t, c in sorted(types.items()))
            print(f"  {form_key:<30} {len(pages)} pages, {total} spans  [{type_str}]")


if __name__ == "__main__":
    main()
