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
import re
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


def spans_to_typed_lines(page_spans: list[dict]) -> list[tuple[str, str, float, float]]:
    """Group spans on a page into typed lines by y-position proximity.

    Returns [(type, text, gap), ...] where `gap` is the unused space in points
    between the end of the line and the page's right margin. A column wrap can
    only occur on a line that ran out of horizontal room, so a large gap is
    positive evidence that the following break was chosen by the typesetter
    rather than forced. Consumed by _reflow_litany in extract_offices.py; see
    #39 for the measurements behind the thresholds.
    """
    if not page_spans:
        return []
    sorted_spans = sorted(page_spans, key=lambda s: (round(s["y0"]), s["x0"]))
    lines: list[list[dict]] = []
    cur_line: list[dict] = []
    cur_y: float | None = None
    for s in sorted_spans:
        y = round(s["y0"])
        if cur_y is not None and abs(y - cur_y) > 2:
            if cur_line:
                lines.append(cur_line)
            cur_line = [s]
            cur_y = y
        else:
            cur_line.append(s)
            if cur_y is None:
                cur_y = y
    if cur_line:
        lines.append(cur_line)
    # Pass 1: classify each line and note its geometry, so the page's right
    # margin is known before any line is emitted. Running headers ("34 Morning
    # Prayer for Christmas") are dropped downstream by _is_noise, but they run
    # wider than the text block and would inflate the margin, so they are
    # excluded from it here.
    prepared: list[dict] = []
    for line_spans in lines:
        line_spans.sort(key=lambda s: s["x0"])
        body = [s for s in line_spans if s["type"] != "footer"]
        if not body:
            continue
        types: dict[str, int] = {}
        for s in body:
            types[s["type"]] = types.get(s["type"], 0) + 1
        text = " ".join(s["text"] for s in line_spans).strip()
        if not text or re.match(r"^\d{1,3}$", text) or re.match(r"^(Morning|Evening) Prayer", text):
            continue
        prepared.append({
            "dominant": max(types, key=types.get),
            "text": text,
            "body": body,
            "y0": min(s["y0"] for s in body),
            "is_running_hdr": bool(re.match(r"^\d+\s+(Morning|Evening) Prayer", text)),
        })

    # Leading above each line. Body leading in this book is ~12.5pt; a paragraph
    # or stanza boundary opens it to ~21pt. A column wrap never carries extra
    # leading, so this distinguishes a chosen break from a forced one even when
    # the line happens to run the full measure. First line of a page has no
    # predecessor, so it reports normal leading and the horizontal gap decides.
    for i, p in enumerate(prepared):
        p["lead"] = (p["y0"] - prepared[i - 1]["y0"]) if i else 0.0

    margin = max(
        (max(s["x1"] for s in p["body"]) for p in prepared
         if p["dominant"] in ("leader", "response") and not p["is_running_hdr"]),
        default=0.0,
    )

    result: list[tuple[str, str, float, float]] = []
    # Verse second-halves are typeset with a physical ~18pt indent relative to
    # the first half (e.g. psalm/canticle/invitatory poetic line-pairs), and a
    # second half can itself run onto multiple indented lines. Track the
    # left-most 'leader' x0 seen since the last reset as the margin baseline —
    # not just the previous line's x0, which would only catch the first line
    # of a multi-line indented run — and mark any line indented past it with a
    # leading space, the same continuation marker already used in
    # data/psalter.json, for renderers to pick up. Reset on any non-leader
    # line (heading/rubric/response) so unrelated indented blocks (e.g. the
    # Confession, which is uniformly indented, not jump-indented) aren't misread.
    baseline_x0: float | None = None
    # The Affirmation of Faith's response text (Apostles' Creed, Hear O
    # Israel) is typeset with extra vertical space between its credal
    # stanzas — ~18-22pt between consecutive "response" lines vs. ~12.5pt
    # for an ordinary line within a stanza. Checked against every "response"
    # line-pair gap >13pt across all 31 office forms (2026-07-27): every one
    # is a real stanza boundary in the Affirmation, with zero false
    # positives — narrow enough that no other response-typed content
    # (there is none with this gap) can be mismarked. Insert a blank line so
    # the stanza break survives extraction; reset the baseline whenever the
    # dominant type isn't "response" so unrelated content can't misread a
    # leftover previous-line y-position.
    prev_response_y0: float | None = None
    for p in prepared:
        dominant, text, body = p["dominant"], p["text"], p["body"]
        gap = margin - max(s["x1"] for s in body)
        lead = p["lead"]
        if dominant == "leader":
            x0 = min(s["x0"] for s in body)
            if baseline_x0 is None or x0 < baseline_x0 - 2:
                baseline_x0 = x0
            elif x0 > baseline_x0 + 8:
                text = " " + text
        else:
            baseline_x0 = None
        if dominant == "response":
            y0 = min(s["y0"] for s in body)
            if prev_response_y0 is not None and y0 - prev_response_y0 > 15:
                # Synthetic stanza break — not a typeset line, so it has no
                # geometry. Give it an unbounded gap: it is deliberate by
                # construction and must never be treated as a column wrap.
                result.append(("response", "", float("inf"), 0.0))
            prev_response_y0 = y0
        else:
            prev_response_y0 = None
        result.append((dominant, text, gap, lead))
    return result


def extract_office_typed_lines(pdf_doc: fitz.Document, form_key: str,
                                start_page: int, end_page: int) -> list[tuple[str, str, float, float]]:
    """Return typed lines for an entire office form (all pages concatenated).

    Each line carries its end-of-line gap; the margin is per page, so gaps stay
    comparable across a form even where page geometry differs slightly.
    """
    all_lines: list[tuple[str, str, float, float]] = []
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
                    segments.append({
                        "type": span_type(span),
                        "text": text,
                        "x0": span["bbox"][0],
                        "y0": span["bbox"][1],
                        "x1": span["bbox"][2],
                        "y1": span["bbox"][3],
                    })
        all_lines.extend(spans_to_typed_lines(segments))
    return all_lines


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
