"""
extract_offices.py — extract Daily Office forms from Pray Without Ceasing PDF.

Reads sources/pray-without-ceasing.pdf using character-level extraction
to preserve semantic style information. Each text run is classified as:
  leader   — regular black text (officiant/leader says this)
  response — bold black text (congregation responds)
  rubric   — red italic text (liturgical instructions, canticle titles, alternatives)
  heading  — bold heading text (section boundaries, consumed during processing)
  footer   — small italic running headers/footers (stripped)

Writes data/offices.json with each section as a list of typed segments.

Usage: python3 tools/extract_offices.py
"""

import re
import sys
import collections
from pathlib import Path

import json
import pdfplumber

ROOT = Path(__file__).parent.parent

# ── Office table ──────────────────────────────────────────────────────────────
# (key, start_book_page, end_book_page_inclusive)
OFFICES = [
    # Seasonal
    ("advent-mp",        14, 21),
    ("advent-ep",        22, 28),
    ("christmas-mp",     29, 35),
    ("christmas-ep",     36, 42),
    ("epiphany-mp",      43, 49),
    ("epiphany-ep",      50, 56),
    ("lent-mp",          57, 64),
    ("lent-ep",          65, 71),
    ("passiontide-mp",   72, 78),
    ("passiontide-ep",   79, 85),
    ("easter-mp",        86, 92),
    ("easter-ep",        93, 99),
    ("pentecost-mp",    100, 106),
    ("pentecost-ep",    107, 113),
    ("allsaints-mp",    114, 120),
    ("allsaints-ep",    121, 128),
    # Ordinary Time (by weekday)
    ("ordinary-sunday-mp",    132, 138),
    ("ordinary-sunday-ep",    139, 145),
    ("ordinary-monday-mp",    146, 152),
    ("ordinary-monday-ep",    153, 159),
    ("ordinary-tuesday-mp",   160, 166),
    ("ordinary-tuesday-ep",   167, 173),
    ("ordinary-wednesday-mp", 174, 181),
    ("ordinary-wednesday-ep", 182, 188),
    ("ordinary-thursday-mp",  189, 195),
    ("ordinary-thursday-ep",  196, 202),
    ("ordinary-friday-mp",    203, 209),
    ("ordinary-friday-ep",    210, 216),
    ("ordinary-saturday-mp",  217, 223),
    ("ordinary-saturday-ep",  224, 230),
]

# ── Style classifier ──────────────────────────────────────────────────────────

# Red rubric color observed in the PDF: approx (0.736, 0.189, 0.227).
_RED_R_MIN = 0.5
_RED_G_MAX = 0.4

def _char_type(c: dict) -> str:
    fn  = c.get("fontname", "")
    sz  = round(c.get("size", 0), 1)
    col = c.get("non_stroking_color") or (0, 0, 0)
    is_red = (
        isinstance(col, tuple)
        and len(col) >= 3
        and col[0] > _RED_R_MIN
        and col[1] < _RED_G_MAX
    )
    if is_red:                      return "rubric"
    if "Bold" in fn and sz >= 11:   return "heading"
    if "Bold" in fn:                return "response"
    if "Italic" in fn and sz < 10:  return "footer"
    return "leader"


# ── Line extraction from page.chars ──────────────────────────────────────────

def _page_styled_lines(page) -> list[tuple[str, str]]:
    """
    Return (type, text) for each line on the page, in reading order.
    Characters are grouped by y-coordinate into lines, then classified
    by the dominant style among that line's characters.
    """
    chars = page.chars or []
    if not chars:
        return []

    # Sort top-to-bottom, left-to-right.
    chars = sorted(chars, key=lambda c: (round(c.get("top", 0)), c.get("x0", 0)))

    # Group into lines by y-coordinate proximity (tolerance: 3pt).
    line_buckets: list[list[dict]] = []
    cur_y: float | None = None
    cur_bucket: list[dict] = []
    for ch in chars:
        y = round(ch.get("top", 0))
        if cur_y is None or abs(y - cur_y) > 3:
            if cur_bucket:
                line_buckets.append(cur_bucket)
            cur_bucket = [ch]
            cur_y = y
        else:
            cur_bucket.append(ch)
    if cur_bucket:
        line_buckets.append(cur_bucket)

    result: list[tuple[str, str]] = []
    for bucket in line_buckets:
        sorted_b = sorted(bucket, key=lambda c: c.get("x0", 0))

        # Reconstruct text with word spacing from x-coordinate gaps.
        text = ""
        prev_x1: float | None = None
        for ch in sorted_b:
            x0 = ch.get("x0", 0)
            x1 = ch.get("x1", x0 + 1)
            if prev_x1 is not None and x0 - prev_x1 > 1.5:
                text += " "
            text += ch.get("text", "")
            prev_x1 = x1
        text = text.strip()
        if not text:
            continue

        # Classify by majority vote.
        type_counts = collections.Counter(_char_type(c) for c in bucket)
        dominant = type_counts.most_common(1)[0][0]
        result.append((dominant, text))

    return result


# ── Section key mapping ───────────────────────────────────────────────────────

# The mixed-case major-section strings in the PWOC PDF. These appear concatenated
# with the sub-section header on the same styled run, e.g.:
#   "the GAtheRinG of the CoMMunitYintroductory Responses"
# We split them out and discard the major-section label (it is structural, not
# content — the renderer knows the order).
_MAJOR_HDRS = re.compile(
    r'the (?:GAtheRinG of the CoMMunitY'
    r'|PRoCLAMAtion of the WoRd'
    r'|PRAYeRs of the CoMMunitY'
    r'|sendinG foRth of the CoMMunitY)',
    re.IGNORECASE,
)

# Map heading text → YAML key. None = structural (discarded).
_SUB_HDR_MAP: list[tuple[re.Pattern, str | None]] = [
    (re.compile(r'introductory Responses', re.IGNORECASE),  "opening_responses"),
    (re.compile(r'invitatory Psalm',        re.IGNORECASE),  "invitatory"),
    (re.compile(r'^the Responsory$',        re.IGNORECASE),  "responsory"),
    (re.compile(r'^the Canticle$',          re.IGNORECASE),  "canticle"),
    (re.compile(r'Affirmation of faith',    re.IGNORECASE),  "affirmation"),
    (re.compile(r'^the Litany$',            re.IGNORECASE),  "litany"),
    (re.compile(r"the Lord'?s Prayer",      re.IGNORECASE),  "lords_prayer"),
    (re.compile(r'^the dismissal$',         re.IGNORECASE),  "dismissal"),
    (re.compile(r'^the Reading$',           re.IGNORECASE),  None),
    (re.compile(r'^the Psalm$',             re.IGNORECASE),  None),
]

def _heading_to_key(text: str) -> str | None | bool:
    """
    Return the YAML key for a heading line, None if discarded, or False if
    not a recognised section header.
    """
    # Strip leading major-section prefix if concatenated.
    text = _MAJOR_HDRS.sub("", text).strip()
    if not text:
        return None  # pure major-section line, discard

    for pat, key in _SUB_HDR_MAP:
        if pat.search(text):
            return key
    return False  # unrecognised heading — keep as content? (shouldn't happen)


# ── Running-header / page-number stripping ────────────────────────────────────

_RUNNING_HDR = re.compile(
    r'^(?:Morning|Evening) Prayer\b.*\d|^\d+\s+(?:Morning|Evening) Prayer\b'
)
_PAGE_NUM = re.compile(r'^\d{1,3}$')

def _is_noise(typ: str, text: str) -> bool:
    if typ == "footer":
        return True
    if _PAGE_NUM.match(text):
        return True
    if _RUNNING_HDR.match(text):
        return True
    return False


# ── Segment merging ───────────────────────────────────────────────────────────

# Response segments starting with these words are grammatical continuations of
# the preceding leader line and should remain lowercase.
_CONTINUATION_STARTS = {'who', 'which', 'that', 'and', 'or', 'but', 'nor', 'yet'}

# Divine titles and proper nouns that small-caps encoding renders lowercase in the PDF.
# Order matters: multi-word phrases must come before their components.
_DIVINE_FIXES: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\bholy spirit\b',       re.IGNORECASE), 'Holy Spirit'),
    (re.compile(r'\bholy ghost\b',        re.IGNORECASE), 'Holy Ghost'),
    (re.compile(r"\bgod's only son\b",    re.IGNORECASE), "God's only Son"),
    (re.compile(r'\bgod the father\b',    re.IGNORECASE), 'God the Father'),
    (re.compile(r'\bgod the son\b',       re.IGNORECASE), 'God the Son'),
    (re.compile(r'\bson of god\b',        re.IGNORECASE), 'Son of God'),
    (re.compile(r'\bthe father\b',        re.IGNORECASE), 'the Father'),
    (re.compile(r'\bthe son\b',           re.IGNORECASE), 'the Son'),
    (re.compile(r'\bthe creator\b',       re.IGNORECASE), 'the Creator'),
    (re.compile(r"\bgod's\b",             re.IGNORECASE), "God's"),
    # Standalone (not preceded by "the") — apply after the above.
    (re.compile(r'\bfather\b'),  'Father'),
    (re.compile(r'\bcreator\b'), 'Creator'),
    # Proper nouns rendered lowercase by small-caps.
    (re.compile(r'\bisrael\b'),  'Israel'),
    (re.compile(r'\bpilate\b'),  'Pilate'),
    # Vocative interjection "O" after comma (e.g. "Where, O death", "Hear, O Israel").
    (re.compile(r', o (?=\w)'),  ', O '),
]

def _fix_casing(seg: dict) -> dict:
    """
    Fix PDF small-caps artifacts in response segments:
      1. Capitalize first character unless the segment is a grammatical
         continuation (starts with a conjunction or relative pronoun).
      2. Capitalize the first letter of each new sentence within the segment
         (letter following .  !  ? and a newline).
      3. Fix standalone lowercase "i" → "I" (first-person pronoun).
      4. Restore capitalization of divine titles (small-caps encodes them lowercase).
    """
    if seg["type"] != "response" or not seg["text"]:
        return seg
    seg = dict(seg)
    text = seg["text"]

    # Normalize typographic apostrophes so pattern matching is consistent.
    text = text.replace('’', "'").replace('‘', "'")

    first_word = re.split(r'\W', text)[0].lower()
    if first_word not in _CONTINUATION_STARTS:
        text = text[0].upper() + text[1:]

    text = re.sub(r'([.!?]\n)([a-z])',
                  lambda m: m.group(1) + m.group(2).upper(), text)
    text = re.sub(r'\bi\b', 'I', text)

    for pat, replacement in _DIVINE_FIXES:
        text = pat.sub(replacement, text)

    seg["text"] = text
    return seg


def _merge(segs: list[dict]) -> list[dict]:
    """Merge consecutive segments of the same type into one, fixing casing."""
    if not segs:
        return []
    merged = [dict(segs[0])]
    for seg in segs[1:]:
        if seg["type"] == merged[-1]["type"]:
            merged[-1]["text"] += "\n" + seg["text"]
        else:
            merged.append(dict(seg))
    return [_fix_casing(s) for s in merged if s["text"].strip()]


# ── Post-process: split seasonal collects from litany ─────────────────────────

_AFTER_SILENCE     = re.compile(r'After a period of silence', re.IGNORECASE)
_LP_CONTINUES      = re.compile(r'(?:Morning|Evening) Prayer continues with the Lord', re.IGNORECASE)
_CONTINUES_RUBRIC  = re.compile(r'(?:Morning|Evening) Prayer continues', re.IGNORECASE)

def _split_litany_collects(segs: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Split the litany section into (litany_segs, seasonal_collect_segs).
    The split point is the rubric 'After a period of silence…'.
    """
    for i, seg in enumerate(segs):
        if seg["type"] == "rubric" and _AFTER_SILENCE.search(seg["text"]):
            # Drop 'Morning Prayer continues…' rubric at end of collects.
            collect_segs = [
                s for s in segs[i:]
                if not (s["type"] == "rubric" and _LP_CONTINUES.search(s["text"]))
            ]
            return segs[:i], collect_segs
    return segs, []


# ── Lords-prayer intro extraction ─────────────────────────────────────────────

_OUR_FATHER = re.compile(r'^our father\b', re.IGNORECASE)

def _split_lords_prayer(segs: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Split lords_prayer section into (intro_segs, prayer_body_segs).
    The prayer body starts at 'Our Father…'.
    """
    for i, seg in enumerate(segs):
        if _OUR_FATHER.match(seg["text"].strip()):
            return segs[:i], segs[i:]
    return [], segs


# ── Main extraction ───────────────────────────────────────────────────────────

def extract_office(pdf, start: int, end: int) -> dict:
    # Collect all styled lines across the page range.
    all_lines: list[tuple[str, str]] = []
    for book_pg in range(start, end + 1):
        idx = book_pg - 1
        if idx < len(pdf.pages):
            all_lines.extend(_page_styled_lines(pdf.pages[idx]))

    # Pull title (first heading line) and subtitle (first leader line before any section).
    title = ""
    subtitle = ""
    header_done = False
    filtered_lines: list[tuple[str, str]] = []

    for typ, text in all_lines:
        if _is_noise(typ, text):
            continue
        if not header_done:
            if not title and typ == "heading":
                title = text
                continue
            if title and not subtitle and typ == "leader":
                subtitle = text
                header_done = True
                continue
            if title and typ == "heading":
                header_done = True
        filtered_lines.append((typ, text))

    # Walk lines and split into sections by heading markers.
    sections: dict[str, list[dict]] = {}
    current_key: str | None = None
    current_segs: list[dict] = []

    def _flush():
        nonlocal current_segs
        if current_key is not None and current_segs:
            sections[current_key] = _merge(current_segs)
        current_segs = []

    for typ, text in filtered_lines:
        if typ == "heading":
            key = _heading_to_key(text)
            if key is False:
                # Unknown heading — treat as content in current section.
                if current_key is not None:
                    current_segs.append({"type": "rubric", "text": text})
                continue
            _flush()
            current_key = key  # may be None (major section label → ignored)
            continue

        if current_key is not None:
            current_segs.append({"type": typ, "text": text})

    _flush()

    # Post-process: split seasonal collects and Lord's Prayer out of litany block.
    if "litany" in sections:
        sections["litany"], sc = _split_litany_collects(sections["litany"])
        if sc:
            pre_lp, lp_segs = _split_lords_prayer(sc)
            lp_found = bool(lp_segs) and _OUR_FATHER.match(lp_segs[0]["text"].strip())
            if lp_found:
                # pre_lp[-1] is the LP intro ("Rejoicing in God's new creation…")
                sections["seasonal_collects"] = pre_lp[:-1] if len(pre_lp) > 1 else pre_lp
                lp_body = [
                    s for s in lp_segs
                    if not (s["type"] == "rubric" and _CONTINUES_RUBRIC.search(s["text"]))
                ]
                sections["lords_prayer_intro"] = (pre_lp[-1:] if pre_lp else []) + lp_body
            else:
                sections["seasonal_collects"] = sc

    # Build result.
    result: dict = {"title": title}
    if subtitle:
        result["subtitle"] = subtitle

    # Preserve canonical section order.
    for key in ("opening_responses", "invitatory", "responsory", "canticle",
                "affirmation", "litany", "seasonal_collects", "lords_prayer_intro",
                "dismissal"):
        if key in sections and sections[key]:
            result[key] = sections[key]

    return result


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    pdf_path = ROOT / "sources" / "pray-without-ceasing.pdf"
    if not pdf_path.exists():
        print(f"ERROR: {pdf_path} not found", file=sys.stderr)
        sys.exit(1)

    out_path = ROOT / "data" / "offices.json"

    offices: dict[str, dict] = {}
    with pdfplumber.open(pdf_path) as pdf:
        for key, start, end in OFFICES:
            offices[key] = extract_office(pdf, start, end)
            sections = [k for k in offices[key] if k not in ("title", "subtitle")]
            print(f"  {key}: {sections}")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(offices, f, ensure_ascii=False, indent=2)
    print(f"\nWrote {len(offices)} offices → {out_path}")

    # Spot checks.
    checks = [
        ("easter-mp",   "opening_responses", "rubric",   "Or"),
        ("easter-mp",   "opening_responses", "leader",   "Alleluia! Christ is risen."),
        ("easter-mp",   "opening_responses", "response", "The Lord is risen indeed"),
        ("easter-mp",   "responsory",        "rubric",   "The Responsory is said or sung"),
        ("easter-mp",   "canticle",          "rubric",   "Song of Zechariah"),
        ("easter-mp",   "seasonal_collects", "leader",   "Living God"),
        ("advent-mp",   "opening_responses", "leader",   "Creator of the stars"),
        ("lent-mp",     "canticle",          "rubric",   "A Song of"),
        ("ordinary-sunday-mp", "opening_responses", "leader", "proclaim your praise"),
    ]
    print("\nSpot checks:")
    ok = True
    for key, section, seg_type, fragment in checks:
        segs = offices.get(key, {}).get(section, [])
        found = any(
            s.get("type") == seg_type and fragment in s.get("text", "")
            for s in segs
        )
        mark = "✓" if found else "✗"
        print(f"  {key}.{section}[type={seg_type!r}] contains {fragment!r}: {mark}")
        if not found:
            ok = False
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    run()
