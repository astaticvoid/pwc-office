#!/usr/bin/env python3
"""
extract_midday.py — extract Prayers at Mid-day (BAS pp. 56-59) as a standalone office.

Reads sources/BAS.pdf at span level and writes .build/midday.1-extract.json,
a single keyed form {"_midday": {...}} in the offices.json field schema.
apply_corrections.py merges that key into data/offices.json, so the office is
the third office alongside the 30 MP/EP forms, reached through the office
selector rather than a season key.

The BAS typesets this office with a convention distinct from the PWC book:

  - rubrics AND speaker labels are red (0xED2124); a speaker label is one of
    the four short words "Officiant" / "People" / "All" / "Reader" and is
    consumed as structure (the following line's weight already carries who
    speaks: regular = leader, bold = response), exactly as the PWC extraction
    consumes its speaker labels. A rubric is any other red line.
  - scripture citations ("Galatians 5.22, 23a, 25") are black italic; they
    extract as `rubric` segments, the same treatment the Penitential Office's
    sentence citations get (#165).
  - the office title "Prayers at Mid-day" is black bold title-size; "Psalm 19"
    and "The Lord's Prayer" are black bold heading-size; "Psalm Prayer" is a
    black bold small-caps heading (9pt, smaller than the 10.1pt body); black
    bold body-size is a response; black regular is leader text.

The office is one fixed form: no per-day appointment, no seasonal variant.
Its printed choices — three readings ("One of the following… Or the
following:"), three collects ("one of the following collects"), and two Lord's
Prayer forms ("Or") — extract as alternatives groups with the standard roman
I/II/III labels, the shape every other alternatives block in the app uses.

Page bounds are detected from the PDF content, not hardcoded: the title span
marks the start page, and the office runs through the last page whose running
header reads "Mid-day Prayer".
"""

import json
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF

ROOT = Path(__file__).parent.parent
PDF = ROOT / "sources" / "BAS.pdf"
BUILD = ROOT / ".build"
OUT = BUILD / "midday.1-extract.json"

# BAS sRGB colours (the PWC book uses 0xBC303A red / 0x231F20 black).
_BLACK = 0x030404
_RED = 0xED2124

_SPEAKERS = {"Officiant", "People", "All", "Reader"}

_TITLE = "Prayers at Mid-day"
_LORDS_PRAYER = "The Lord\u2019s Prayer"
_PSALM_HEAD_RE = re.compile(r"^Psalm (\d+)$")
_VERSE_RANGE_RE = re.compile(r"^[\d\s\u2013\u2014-]+$")
_PSALMODY_RUBRIC_RE = re.compile(r"^The following portion of Psalm")
_READING_RUBRIC_RE = re.compile(r"^One of the following, or some other suitable")
_COLLECT_RUBRIC_RE = re.compile(r"^The officiant then says one of the following collects")
_OR_FOLLOWING_RE = re.compile(r"^Or the following:?$")
_BARE_NUM_RE = re.compile(r"^\d{1,3}$")

# Field-opening rubrics whose exact text may be re-typeset with trailing
# words; matched by prefix in both _starts_field and assemble so the two
# sites cannot drift apart.
_FIELD_BOUNDARY_PREFIXES = ("A period of silence may follow.", "Then may be said,")

_ROMAN = ("I", "II", "III", "IV")


def _span_type(span: dict) -> str:
    """Classify one BAS span into the extractor's vocabulary."""
    flags, size, color = span["flags"], span["size"], span["color"]
    if color == _RED:
        return "rubric"
    if color == _BLACK and (flags & 2) and not (flags & 16):
        return "citation"
    if flags & 16 and size >= 18:
        return "title"
    if flags & 16 and size >= 11:
        return "heading"
    if flags & 16 and size < 10:
        return "smallheading"
    if flags & 16:
        return "response"
    return "leader"


def detect_pages(doc) -> tuple[int, int]:
    """Find the office's start/end pages from content, not page numbers.

    The start is the page carrying the "Prayers at Mid-day" title (a black
    bold span >= 18pt). The office then runs through the last page whose
    running header reads "Mid-day Prayer".
    """
    start = None
    end = None
    for i in range(doc.page_count):
        page = doc[i]
        if start is None:
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    if any(
                        s["flags"] & 16 and s["size"] >= 18 and s["text"].strip() == _TITLE
                        for s in line["spans"]
                    ):
                        start = i + 1
                        break
                if start is not None:
                    break
        if start is not None:
            # Bound to the contiguous run: the office ends at the first page
            # whose running header stops, so a later cross-reference to
            # "Mid-day Prayer" elsewhere in the book cannot extend the range.
            if "Mid-day Prayer" in page.get_text():
                end = i + 1
            else:
                break
    if start is None:
        sys.exit(f"ERROR: '{_TITLE}' title not found in {PDF.name}")
    if end is None:
        sys.exit(f"ERROR: no 'Mid-day Prayer' running header after page {start}")
    return start, end


def _coalesce_line(line) -> list[tuple[str, str]]:
    """One PDF line -> [(type, text), ...], same-type spans joined with a space.

    The running header (page number + "Mid-day Prayer") sits in the footer
    band and is dropped here; the office body starts around y=33.
    """
    entries: list[tuple[str, str]] = []
    for span in line["spans"]:
        text = span["text"].strip()
        if not text:
            continue
        if span["bbox"][1] > 480:  # footer band: running header + page number
            continue
        typ = _span_type(span)
        if typ == "rubric" and text in _SPEAKERS:
            continue  # speaker label — structural, not spoken text
        if entries and entries[-1][0] == typ:
            entries[-1] = (typ, entries[-1][1] + " " + text)
        else:
            entries.append((typ, text))
    return entries


def _page_lines(doc, start: int, end: int) -> list[list[tuple[str, str]]]:
    """Every body line of the office, one coalesced entry list per line."""
    out: list[list[tuple[str, str]]] = []
    for i in range(start - 1, end):
        d = doc[i].get_text("dict", flags=fitz.TEXTFLAGS_DICT)
        for block in d["blocks"]:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                entries = _coalesce_line(line)
                if not entries:
                    continue
                if len(entries) == 1 and entries[0][0] in ("leader", "response") \
                        and _BARE_NUM_RE.match(entries[0][1].strip()):
                    continue  # stray page number outside the footer band
                out.append(entries)
    return out


def _starts_field(typ: str, text: str) -> bool:
    """True when this item opens a new field, so a same-type merge must stop here."""
    if typ != "rubric":
        return False
    return bool(
        _PSALMODY_RUBRIC_RE.match(text)
        or _READING_RUBRIC_RE.match(text)
        or _COLLECT_RUBRIC_RE.match(text)
    ) or text.startswith(_FIELD_BOUNDARY_PREFIXES)


def _merge_lines(lines: list[list[tuple[str, str]]]) -> list[tuple[str, str]]:
    """Flatten the office's lines into merged (type, text) items.

    Consecutive same-type entries merge with a newline, matching the PWC
    extraction's own line join, except that a field-opening rubric never
    merges with the rubric before it. The "Psalm 19" heading folds its "1-6"
    verse range into a single `label` citation.
    """
    items: list[tuple[str, str]] = []
    for entries in lines:
        for typ, text in entries:
            text = text.strip()
            if not text or typ == "title":
                continue
            if (
                typ == "response"
                and items
                and items[-1][0] == "heading"
                and _VERSE_RANGE_RE.match(text)
            ):
                # "Psalm 19" + "1-6" -> label "Psalm 19:1-6"
                items[-1] = ("label", f"{items[-1][1]}:{text.replace(' ', '')}")
                continue
            if items and items[-1][0] == typ and not _starts_field(typ, text):
                items[-1] = (typ, items[-1][1] + "\n" + text)
            else:
                items.append((typ, text))
    return items


def _seg(typ: str, text: str) -> dict:
    text = re.sub(r"\s+([,.!?])", r"\1", text)
    text = text.replace("\u00a0", " ")
    return {"type": typ, "text": text.strip()}


def assemble(lines: list[list[tuple[str, str]]]) -> dict:
    """Assemble the merged span items into the {_midday: {...}} form."""
    midday: dict = {"title": _TITLE}
    fields: list[tuple[str, list]] = []
    cur: tuple[str, list] = ("opening", [])
    fields.append(cur)

    groups: list[dict] | None = None
    group: list | None = None

    def begin_field(name: str):
        nonlocal cur, groups, group
        close_alternatives()
        cur = (name, [])
        fields.append(cur)
        groups = None
        group = None

    def start_group():
        nonlocal group
        group = []

    def close_group():
        nonlocal group
        if group and groups is not None:
            groups.append({"label": _ROMAN[len(groups)], "segments": group})
        group = None

    def close_alternatives():
        nonlocal groups, group
        close_group()
        if groups:
            cur[1].append({"type": "alternatives", "groups": groups})
        groups = None
        group = None

    def emit(typ: str, text: str):
        seg = _seg(typ, text)
        if group is not None:
            group.append(seg)
        else:
            cur[1].append(seg)

    for typ, text in _merge_lines(lines):
        store_typ = "rubric" if typ == "citation" else typ

        # ── Section boundaries (structural headings) ──────────────────────
        if typ == "smallheading" and text == "Psalm Prayer":
            begin_field("psalm_prayer")
            continue
        if typ == "heading" and text == _LORDS_PRAYER:
            begin_field("lords_prayer")
            groups, group = [], None
            start_group()
            continue
        if typ == "label":  # folded "Psalm 19:1-6" citation
            emit("label", text)
            continue
        if typ in ("heading", "smallheading"):
            # "The Lord's Prayer" and "Psalm Prayer" are consumed above; the
            # "Psalm 19" head folds to a label in _merge_lines. Anything else
            # means the PDF no longer matches this extractor's model.
            sys.exit(f"ERROR: unhandled {typ} in mid-day office: {text!r}")

        # ── Rubric-driven boundaries and alternative separators ───────────
        if typ == "rubric":
            if _PSALMODY_RUBRIC_RE.match(text):
                begin_field("psalm")
                emit("rubric", text)
                continue
            if _READING_RUBRIC_RE.match(text):
                begin_field("reading")
                emit("rubric", text)
                groups, group = [], None
                start_group()
                continue
            if _COLLECT_RUBRIC_RE.match(text):
                begin_field("collects")
                emit("rubric", text)
                groups, group = [], None
                start_group()
                continue
            if _OR_FOLLOWING_RE.match(text) or text.strip().lower() == "or":
                if groups is not None:
                    close_group()
                    start_group()
                else:
                    # Outside an alternatives context an "Or" is a plain
                    # rubric; never open a phantom group whose segments would
                    # be silently discarded.
                    emit("rubric", text)
                continue
            if text.startswith(_FIELD_BOUNDARY_PREFIXES[0]):
                begin_field("prayers")
                emit("rubric", text)
            elif text.startswith(_FIELD_BOUNDARY_PREFIXES[1]):
                begin_field("dismissal")
                emit("rubric", text)
            else:
                emit("rubric", text)
            continue

        # ── Collect alternatives close on their "Amen." response ───────────
        if typ == "response" and text.strip() == "Amen." and cur[0] == "collects":
            emit("response", text)
            close_group()
            start_group()
            continue

        emit(store_typ, text)

    close_alternatives()

    for name, segs in fields:
        if segs:
            midday[name] = segs
    return midday


def main() -> int:
    if not PDF.exists():
        sys.exit(f"ERROR: {PDF} not found. Run: make fetch-sources")
    doc = fitz.open(PDF)
    try:
        start, end = detect_pages(doc)
        lines = _page_lines(doc, start, end)
        midday = assemble(lines)
    finally:
        doc.close()

    BUILD.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"_midday": midday}, ensure_ascii=False, indent=2) + "\n")
    n = sum(len(v) for v in midday.values() if isinstance(v, list))
    print(f"Wrote {OUT} (pp. {start}-{end}, {n} top-level segments)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
