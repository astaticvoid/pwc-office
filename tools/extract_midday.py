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

# A column wrap that split a word across the line end: rejoin without the
# hyphen by default (a wrap-split single word like "doctrine" would print as
# "doc-"/"trine" — no such split occurs in the current PDF, but the rule
# generalizes), but keep it when the continuation is capitalized
# ("mid-"/"Victorian") or the pair is a genuine compound — "self-"/"control"
# is "self-control" in this office, not "selfcontrol". Same rule as
# extract_fats.py's _dehyphenate; found by reviewing every wrap pair in the
# current PDF.
_HYPHEN_KEEP = {("self", "control")}


def _dehyphenate(prev: str, next_: str) -> str:
    """Rejoin a hyphenated wrap, keeping the hyphen where it belongs.

    `prev` is the accumulated item text (it may already span several lines),
    so the word pair is the trailing hyphenated word of `prev` and the
    leading word of `next_`. A genuine compound keeps its hyphen
    ("self-control"); a wrap-split single word drops it ("doctrine").
    """
    a = re.search(r"([A-Za-z]+)-$", prev)
    b = re.match(r"([A-Za-z]+)", next_)
    if a and b:
        keep = b.group(1)[0].isupper() or (a.group(1), b.group(1)) in _HYPHEN_KEEP
        sep = "-" if keep else ""
        return prev[:-1] + sep + next_
    return prev[:-1] + next_


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


def _coalesce_line(line) -> tuple[list[tuple[str, str]], float]:
    """One PDF line -> ([(type, text), ...], x1), same-type spans joined with a space.

    The running header (page number + "Mid-day Prayer") sits in the footer
    band and is dropped here; the office body starts around y=33. `x1` is the
    line's right edge, used by _merge_lines to tell a column wrap from a
    deliberate break.
    """
    entries: list[tuple[str, str]] = []
    x1 = 0.0
    for span in line["spans"]:
        text = span["text"].strip()
        if not text:
            continue
        if span["bbox"][1] > 480:  # footer band: running header + page number
            continue
        typ = _span_type(span)
        if typ == "rubric" and text in _SPEAKERS:
            continue  # speaker label — structural, not spoken text
        x1 = max(x1, span["bbox"][2])
        if entries and entries[-1][0] == typ:
            entries[-1] = (typ, entries[-1][1] + " " + text)
        else:
            entries.append((typ, text))
    return entries, x1


def _page_lines(doc, start: int, end: int) -> list[tuple[list[tuple[str, str]], float]]:
    """Every body line of the office: (coalesced entries, x1) per line."""
    out: list[tuple[list[tuple[str, str]], float]] = []
    for i in range(start - 1, end):
        d = doc[i].get_text("dict", flags=fitz.TEXTFLAGS_DICT)
        for block in d["blocks"]:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                entries, x1 = _coalesce_line(line)
                if not entries:
                    continue
                if len(entries) == 1 and entries[0][0] in ("leader", "response") \
                        and _BARE_NUM_RE.match(entries[0][1].strip()):
                    continue  # stray page number outside the footer band
                out.append((entries, x1))
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


def _merge_lines(lines: list[tuple[list[tuple[str, str]], float]]) -> list[tuple[str, str]]:
    """Flatten the office's lines into merged (type, text) items.

    Consecutive same-type entries merge; the join is decided from the page,
    the way extract_offices.py's own line join is (#39): a line that ran out
    of horizontal room is a column wrap and joins its follower with a space,
    a line that ended deliberately keeps a newline. A wrap that split a word
    across lines ("self-"/"control") is dehyphenated on the join. A
    field-opening rubric never merges with the rubric before it. The "Psalm
    19" heading folds its "1-6" verse range into a single `label` citation.
    """
    # The right text margin, measured from the office's own lines: the widest
    # body line ends there. A prose line that ends within ~53.7pt of it ran
    # out of room and is a column wrap — the follower continues the sentence
    # and joins with a space. A line that ends well short ended deliberately
    # (verse, paragraph end) and keeps a newline. Measured over all four
    # pages: the tightest wrap ("here. It is all God's work. It was God who",
    # reading II) ends 52.7pt short; the tightest deliberate break (the psalm
    # line "it comes forth like a bridegroom out of his chamber;") ends
    # 54.8pt short. 53.7 sits 1.0-1.1pt off each side — the PWC extractor's
    # own break threshold sits 0.5pt off a false positive (#39), so this is
    # the safer of the two. Re-check if the book is ever re-cut.
    #
    # Responses are exempt: the Gloria, the Lord's Prayer and the Kyrie are
    # verse in this office, so they keep their line breaks even when one runs
    # close to the margin — "as we forgive those who trespass against us."
    # ends 39.4pt short, which geometry alone would read as a wrap. (Some
    # response breaks are geometric wraps by the 53.7pt measure — the Gloria's
    # first two lines end 31.2/26.9pt short — but keeping them is the
    # presentation the book chose, so responses never join.) Only rubric and
    # leader prose are judged by geometry.
    margin = max((x1 for _, x1 in lines), default=0.0)
    wrap = 53.7

    items: list[tuple[str, str]] = []
    prev_x1: float | None = None
    for entries, x1 in lines:
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
                prev = items[-1][1]
                if (
                    typ != "response"
                    and prev_x1 is not None
                    and margin - prev_x1 < wrap
                ):
                    # Column wrap: the follower continues the sentence.
                    if prev.endswith("-") and not prev.endswith("--"):
                        # Word split across the line end ("self-"/"control").
                        items[-1] = (typ, _dehyphenate(prev, text))
                    else:
                        items[-1] = (typ, prev + " " + text)
                else:
                    items[-1] = (typ, prev + "\n" + text)
            else:
                items.append((typ, text))
        prev_x1 = x1
    return items


def _seg(typ: str, text: str) -> dict:
    text = re.sub(r"\s+([,.!?])", r"\1", text)
    text = text.replace("\u00a0", " ")
    return {"type": typ, "text": text.strip()}


def assemble(lines: list[tuple[list[tuple[str, str]], float]]) -> dict:
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
