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

import argparse
import json
import os
import re
import sys
import collections
from pathlib import Path

import pdfplumber

from extract_lib import check_manifest

# Set DEBUG=1 to emit a full extraction trace to stderr.
# Usage: DEBUG=1 python3 tools/extract_offices.py 2> audit.log
_DEBUG = os.environ.get("DEBUG", "0") == "1"
_OFFICE_FILTER = os.environ.get("DEBUG_OFFICE", "")  # e.g. "easter-ep" to trace one office

def _dbg(*parts, office="", section=""):
    if not _DEBUG:
        return
    if _OFFICE_FILTER and office and _OFFICE_FILTER not in office:
        return
    prefix = f"[{office}]" if office else ""
    if section:
        prefix += f"[{section}]"
    print(prefix, *parts, file=sys.stderr)

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

def _page_styled_lines(page, office="") -> list[tuple[str, str]]:
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
        # Log minority disagreements so we can audit misclassified lines.
        if _DEBUG and len(type_counts) > 1:
            votes = ", ".join(f"{t}×{n}" for t, n in type_counts.most_common())
            _dbg(f"  RAW [{dominant}] {repr(text[:60])}  (votes: {votes})", office=office)
        elif _DEBUG:
            _dbg(f"  RAW [{dominant}] {repr(text[:60])}", office=office)

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

# Sentinel: heading is structural but the current section stays active (don't flush).
# Used for the Lord's Prayer heading so the intro + prayer text accumulate into litany
# and are later split out by _split_lords_prayer.
_CONTINUE = object()

# Map heading text → section key (str), None (flush section, no new section),
# _CONTINUE (discard heading, keep current section), or False (unknown, treated as content).
_SUB_HDR_MAP: list[tuple] = [
    (re.compile(r'introductory Responses',              re.IGNORECASE), "opening_responses"),
    (re.compile(r'invitatory Psalm',                    re.IGNORECASE), "invitatory"),
    # Seasonal EP: Service of Light elements (Gathering section)
    (re.compile(r'^thanksgiving$',                      re.IGNORECASE), "thanksgiving_for_light"),
    # Ordinary-time EP: evening hymn heading carries the hymn title as rubric text
    (re.compile(r'^the evening hymn\b',                 re.IGNORECASE), "phos_hilaron"),
    (re.compile(r'^the Responsory$',                    re.IGNORECASE), "responsory"),
    (re.compile(r'^the Canticle$',                      re.IGNORECASE), "canticle"),
    (re.compile(r'Affirmation of faith',                re.IGNORECASE), "affirmation"),
    # Ordinary-time: free-prayer space + day-specific topic prompts before the Litany
    (re.compile(r'^intercessions and thanksgivings$',   re.IGNORECASE), "intercessions"),
    (re.compile(r'^the Litany$',                        re.IGNORECASE), "litany"),
    # Lord's Prayer: keep litany section active so intro + prayer text flow in and are
    # later split out by _split_lords_prayer.
    (re.compile(r"the Lord['']?s Prayer",               re.IGNORECASE), _CONTINUE),
    (re.compile(r'^the dismissal$',                     re.IGNORECASE), "dismissal"),
    (re.compile(r'^the Reading$',                       re.IGNORECASE), None),
    (re.compile(r'^the Psalm$',                         re.IGNORECASE), None),
]

# Heading lines that are actually repeated congregational refrains (antiphon pattern).
# Some PDF occurrences are rendered at heading font size/weight; reclassify as response.
_RESPONSE_HDRS: list[re.Pattern] = [
    re.compile(r'^Let heaven and earth shout their praise', re.IGNORECASE),
    re.compile(r'^God of all the faithful, we thank you',  re.IGNORECASE),
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
    (re.compile(r"\bgod[’']s only son\b", re.IGNORECASE), "God’s only Son"),
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
    if not seg["text"]:
        return seg
    seg = dict(seg)
    text = seg["text"]

    # Normalize space before punctuation (PDF extraction artifact).
    text = re.sub(r' ([!?])', r'\1', text)

    if seg["type"] != "response":
        seg["text"] = text
        return seg

    # Normalize typographic apostrophes so pattern matching is consistent.
    text = text.replace('‘', "'").replace('’', "'")

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
    """Merge consecutive segments of the same type into one, fixing casing.

    Structural rubrics must not be merged in ways that destroy their semantics:
    - Bare 'Or' / 'or' absorb the immediately following name-line rubric to form
      'Or\\nName' — this is intentional and required for _OR_NAMED detection.
    - All other structural rubrics (already-complete Or\\nName, block seps, canticle
      intros, continues) do not merge with anything.
    """
    if not segs:
        return []
    merged = [dict(segs[0])]
    for seg in segs[1:]:
        prev = merged[-1]
        prev_is_bare_or = (
            prev["type"] == "rubric"
            and (_OR_UPPER.match(prev["text"]) or _OR_LOWER.match(prev["text"]))
        )
        # A truncated "continues with…" rubric (no trailing period) may absorb the
        # immediately following non-structural rubric to complete the sentence.
        prev_is_truncated_continues = (
            prev["type"] == "rubric"
            and _CONTINUES_ALT.search(prev["text"])
            and not prev["text"].rstrip().endswith(".")
        )
        can_merge = (
            seg["type"] == prev["type"]
            and not (
                seg["type"] == "rubric" and (
                    # Incoming structural rubric always starts a new segment.
                    _is_structural_rubric(seg["text"])
                    # Structural prev merges only when it's a bare Or/or (needs its name)
                    # or a truncated continues rubric waiting for its continuation.
                    or (_is_structural_rubric(prev["text"]) and not prev_is_bare_or
                        and not prev_is_truncated_continues)
                )
            )
        )
        if can_merge:
            # Truncated continues rubric: join with space (mid-sentence continuation).
            sep = " " if prev_is_truncated_continues else "\n"
            prev["text"] += sep + seg["text"]
        else:
            merged.append(dict(seg))
    return [_fix_casing(s) for s in merged if s["text"].strip()]


# ── Post-process: split seasonal collects from litany ─────────────────────────

_AFTER_SILENCE     = re.compile(r'After a period of silence', re.IGNORECASE)
_EITHER_COLLECT    = re.compile(r'Either the Collect of the Day', re.IGNORECASE)
_LP_CONTINUES      = re.compile(r'(?:Morning|Evening) Prayer continues with the Lord', re.IGNORECASE)
_CONTINUES_RUBRIC  = re.compile(r'(?:Morning|Evening) Prayer continues', re.IGNORECASE)

def _split_litany_collects(segs: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Split the litany section into (litany_segs, seasonal_collect_segs).
    Seasonal forms use 'After a period of silence…'; ordinary-time forms use
    'Either the Collect of the Day…'.
    """
    for i, seg in enumerate(segs):
        if seg["type"] == "rubric" and (
            _AFTER_SILENCE.search(seg["text"]) or _EITHER_COLLECT.search(seg["text"])
        ):
            # Drop 'Morning Prayer continues…' rubric at end of collects.
            collect_segs = [
                s for s in segs[i:]
                if not (s["type"] == "rubric" and _LP_CONTINUES.search(s["text"]))
            ]
            return segs[:i], collect_segs
    return segs, []


# ── Post-process: group alternatives (Or / or rubrics) ───────────────────────

_OR_NAMED       = re.compile(r'^Or\n(.+)', re.DOTALL)
_OR_UPPER       = re.compile(r'^Or$')
_OR_LOWER       = re.compile(r'^or$')
_BLESSED_BE     = re.compile(r'^Blessed be (?:God|the holy)\b', re.IGNORECASE)
# Canticle intro: starts with curly/straight open-quote, contains “said or sung.”, newline, then first option label.
# Handles all line-break variants (“may be\nsaid”, “may\nbe said”, “may be said”).
_CANTICLE_INTRO = re.compile(r'^[“”].+?said or sung\.\n(.+)', re.DOTALL)
_GENERAL_INTRO  = re.compile(r'one of the following .+ may be said or sung\.\n(.+)', re.IGNORECASE | re.DOTALL)
# Matches pure block separator rubrics (no embedded label).
# Canticle doxology intros ("At the end of the Canticle…" / "After the Canticle…") also
# match this pattern, but are now emitted as plain rubric segments rather than discarded
# — see the BLOCK-SEP branch in _group_alternatives.
_BLOCK_SEP_ONLY = re.compile(r'of the following may be said or sung\.?\s*$', re.IGNORECASE)
# Identifies the two canticle doxology intro phrasings so _group_alternatives can
# preserve them in the output instead of silently discarding them.
_CANTICLE_DOXOLOGY_INTRO = re.compile(
    r'^(?:At the end of the Canticle|After the Canticle)\b', re.IGNORECASE
)
# Used as a structural separator to prevent "continues with…" rubrics from merging
# with adjacent segments. The Lord's Prayer variant is discarded; others are kept as PWC text.
_CONTINUES_ALT  = re.compile(r'(?:Morning|Evening) Prayer continues', re.IGNORECASE)

def _is_structural_rubric(text: str) -> bool:
    """True for rubrics with structural meaning that must not be merged with neighbours."""
    return bool(
        _OR_NAMED.match(text) or _OR_UPPER.match(text) or _OR_LOWER.match(text)
        or _CANTICLE_INTRO.match(text) or _BLOCK_SEP_ONLY.search(text)
        or _CONTINUES_ALT.search(text)
    )

_ROMAN = ['I', 'II', 'III', 'IV', 'V']


def _alt_label(text: str) -> str:
    """Extract short display label from 'Name (citation)' or 'Name' string."""
    name = re.sub(r'\s*\([^)]*\)\s*$', '', text).strip()
    # Strip "The " and "An " articles that don't belong in canonical short names,
    # but preserve "A " so canticle names like "A Song of the Lamb" keep their article.
    name = re.sub(r'^(?:The |An )', '', name).strip()
    return name or text.strip()


def _group_alternatives(segs: list[dict], office="", section="") -> list[dict]:
    """
    Replace Or/or separator rubrics with {type: "alternatives", groups: [...]} nodes.
    Two kinds of alternatives block:
      - Named: canticle intro rubric → Or\\nName rubrics → named groups
      - Unnamed: block-sep rubric or bare or/Or rubrics → Roman-numeral groups
    """
    result: list[dict] = []
    pending: list[dict] = []   # flat segments not yet committed to result
    groups: list | None = None # None = flat mode; list = inside alternatives block
    unnamed_n = [0]            # mutable counter for Roman numerals

    def _flush_groups():
        nonlocal groups
        if groups:
            result.append({'type': 'alternatives', 'groups': groups})
        groups = None
        unnamed_n[0] = 0

    def _flush_pending():
        result.extend(pending)
        pending.clear()

    def _new_group(label: str | None = None):
        if label is None:
            label = _ROMAN[unnamed_n[0]]
            unnamed_n[0] += 1
        groups.append({'label': label, 'segments': []})

    def _push(seg: dict):
        if groups is not None:
            if not groups:          # pure block-sep started, no group yet
                _new_group()
            groups[-1]['segments'].append(seg)
        else:
            pending.append(seg)

    _dbg(f"\n  --- _group_alternatives: {office}[{section}] ({len(segs)} segs) ---",
         office=office, section=section)

    for seg in segs:
        text = seg.get('text', '')
        typ  = seg.get('type', '')
        cur_grp = f"grp[{len(groups)}]" if groups is not None else "pending"

        # Discard only the Lord's Prayer navigation rubric ("…continues with the Lord's Prayer").
        # Other "continues with…" rubrics are PWC liturgical transitions and are kept.
        if typ == 'rubric' and _LP_CONTINUES.search(text):
            _dbg(f"    DISCARD lp-continues-rubric: {repr(text[:60])}", office=office, section=section)
            continue

        # Canticle intro: '"Name A," "Name B," … may be said or sung.\nName A (citation)'
        if typ == 'rubric' and _CANTICLE_INTRO.match(text):
            lines = text.strip().split('\n')
            # The intro spans multiple PDF lines — join with space for a single rubric.
            intro_part = ' '.join(l.strip() for l in lines[:-1] if l.strip())
            last_line = lines[-1]
            _dbg(f"    CANTICLE-INTRO → flush, start named group {repr(_alt_label(last_line))}: {repr(text[:60])}", office=office, section=section)
            _flush_groups()
            _flush_pending()
            if intro_part:
                result.append({'type': 'rubric', 'text': intro_part})
            groups = []
            unnamed_n[0] = 0
            _new_group(_alt_label(last_line))
            continue

        # General intro with embedded first label:
        # 'One of the following Affirmations … may be said or sung.\nLabel'
        if typ == 'rubric' and _GENERAL_INTRO.search(text) and not _BLOCK_SEP_ONLY.search(text):
            lines = text.strip().split('\n')
            # Join intro lines with space; they're PDF line-break artefacts.
            intro_part = ' '.join(l.strip() for l in lines[:-1] if l.strip())
            last_line = lines[-1]
            _dbg(f"    GENERAL-INTRO → flush, start named group {repr(_alt_label(last_line))}: {repr(text[:60])}", office=office, section=section)
            _flush_groups()
            _flush_pending()
            if intro_part:
                result.append({'type': 'rubric', 'text': intro_part})
            groups = []
            unnamed_n[0] = 0
            _new_group(_alt_label(last_line))
            continue

        # Pure block separator (no embedded label):
        if typ == 'rubric' and _BLOCK_SEP_ONLY.search(text):
            _dbg(f"    BLOCK-SEP → flush, start unnamed groups: {repr(text[:60])}", office=office, section=section)
            _flush_groups()
            _flush_pending()
            # Block-sep rubrics carry liturgical text (e.g. "One of the following may be
            # said or sung." before the opening doxology; "After the Canticle…" before the
            # post-canticle doxology). Emit all of them as plain rubric segments so they
            # appear in the rendered output before the alternatives block they introduce.
            result.append(seg)
            groups = []
            unnamed_n[0] = 0
            continue

        # Or\nName (citation) — named alternative
        if typ == 'rubric' and _OR_NAMED.match(text):
            m = _OR_NAMED.match(text)
            label = _alt_label(m.group(1).strip().split('\n')[0])
            _dbg(f"    OR-NAMED → new group {repr(label)}: {repr(text[:60])}", office=office, section=section)
            if groups is None:
                _flush_pending()
                groups = []
                unnamed_n[0] = 0
            _new_group(label)
            continue

        # Or (uppercase, unnamed) or or (lowercase, unnamed)
        if typ == 'rubric' and (_OR_UPPER.match(text) or _OR_LOWER.match(text)):
            next_roman = _ROMAN[unnamed_n[0]] if unnamed_n[0] < len(_ROMAN) else f"?{unnamed_n[0]}"
            _dbg(f"    OR-BARE → new group {next_roman} (groups={'None' if groups is None else len(groups)}): {repr(text[:60])}", office=office, section=section)
            if groups is None:
                _flush_groups()
                groups = []
                unnamed_n[0] = 0
                if pending:
                    groups.append({'label': _ROMAN[0], 'segments': list(pending)})
                    pending.clear()
                    unnamed_n[0] = 1
            _new_group()
            continue

        _dbg(f"    CONTENT [{cur_grp}] {typ} {repr(text[:60])}", office=office, section=section)
        _push(seg)

    _flush_groups()
    _flush_pending()
    _dbg(f"  --- result: {len(result)} top-level segs ---", office=office, section=section)
    return result


# ── Post-process: fold Berakah blessing conclusions into nested alternatives ───

def _fold_berakah_blessings(segs: list[dict], office="") -> list[dict]:
    """
    Seasonal opening_responses have an alternatives block where the last N groups
    are short "Blessed be…" doxological conclusions that belong NESTED inside
    the preceding Berakah prayer group, not as separate top-level alternatives.

    Before: alternatives {I: Form A, II: Berakah…"Blessed be God, F,S,HS.", III: "Blessed be God: Source…", IV: "Blessed be the holy Trinity…"}
    After:  alternatives {I: Form A, II: Berakah body + nested {I,II,III: three blessing conclusions}}
    """
    result: list[dict] = []
    for seg in segs:
        if seg.get('type') != 'alternatives':
            result.append(seg)
            continue
        groups = seg['groups']
        labels = [g['label'] for g in groups]
        _dbg(f"  BERAKAH-FOLD? groups={labels}", office=office, section="opening_responses")
        if len(groups) < 3:
            _dbg(f"    SKIP: fewer than 3 groups", office=office, section="opening_responses")
            result.append(seg)
            continue

        # Check whether groups[2:] are all short "Blessed be…" leader+response pairs.
        tail = groups[2:]
        tail_ok = all(
            len(g['segments']) == 2
            and g['segments'][0]['type'] == 'leader'
            and _BLESSED_BE.match(g['segments'][0]['text'])
            and g['segments'][1]['type'] == 'response'
            for g in tail
        )
        if not tail_ok:
            bad = [g['label'] for g in tail if not (
                len(g['segments']) == 2
                and g['segments'][0]['type'] == 'leader'
                and _BLESSED_BE.match(g['segments'][0]['text'])
                and g['segments'][1]['type'] == 'response'
            )]
            _dbg(f"    SKIP: tail groups not all short 'Blessed be' pairs — failing: {bad}", office=office, section="opening_responses")
            result.append(seg)
            continue

        # Confirm group[1] ends with a response (the "Blessed be God for ever." close).
        g1_segs = list(groups[1]['segments'])
        if not g1_segs or g1_segs[-1]['type'] != 'response':
            _dbg(f"    SKIP: group[1] doesn't end with response", office=office, section="opening_responses")
            result.append(seg)
            continue

        # Find the last leader in group[1]; its final line should be the first blessing option.
        leaders = [(i, s) for i, s in enumerate(g1_segs) if s['type'] == 'leader']
        if not leaders:
            _dbg(f"    SKIP: group[1] has no leader segments", office=office, section="opening_responses")
            result.append(seg)
            continue
        last_i, last_leader = leaders[-1]
        lines = last_leader['text'].rsplit('\n', 1)
        if len(lines) < 2 or not _BLESSED_BE.match(lines[1].strip()):
            _dbg(f"    SKIP: group[1] last leader doesn't end with 'Blessed be' line: {repr(lines[-1][:60])}", office=office, section="opening_responses")
            result.append(seg)
            continue
        _dbg(f"    FOLDING: nesting groups {[g['label'] for g in tail]} into group[1]", office=office, section="opening_responses")

        berakah_body   = lines[0]
        blessing_one   = lines[1].strip()
        blessing_resp  = g1_segs[-1]['text']   # "Blessed be God for ever."

        # Build trimmed group[1] segments: Berakah body only (no trailing blessing line/response).
        trimmed = list(g1_segs[:-1])           # drop final response
        trimmed[last_i] = {**last_leader, 'text': berakah_body}

        # Build the nested 3-way alternatives for the blessing conclusion.
        nested_groups = [{'label': _ROMAN[0], 'segments': [
            {'type': 'leader',   'text': blessing_one},
            {'type': 'response', 'text': blessing_resp},
        ]}]
        for j, tg in enumerate(tail, 1):
            nested_groups.append({'label': _ROMAN[j], 'segments': list(tg['segments'])})

        new_g1 = {'label': groups[1]['label'],
                  'segments': trimmed + [{'type': 'alternatives', 'groups': nested_groups}]}
        result.append({'type': 'alternatives', 'groups': [groups[0], new_g1]})

    return result


# ── Thanksgiving exchange/body split ─────────────────────────────────────────

def _split_thanksgiving(segs: list[dict]) -> list[dict]:
    """
    After _fold_berakah_blessings the thanksgiving section is:
      alternatives { I: [exchange-A], II: [exchange-B, Berakah-body, berakah_blessings] }

    The Berakah body and blessing conclusions are common to both exchange forms;
    only the opening call-and-response differs. Restructure to:
      [alternatives { I: [exchange-A], II: [exchange-B] },
       Berakah-body segs...,
       shared:berakah_blessings]
    so the common text renders after the exchange toggle regardless of which is chosen.
    """
    if len(segs) != 1 or segs[0].get("type") != "alternatives":
        return segs
    groups = segs[0].get("groups", [])
    if len(groups) != 2:
        return segs
    g0_segs = groups[0].get("segments", [])  # exchange form I only
    g1_segs = groups[1].get("segments", [])  # exchange form II + common Berakah
    n = len(g0_segs)
    if len(g1_segs) <= n:
        return segs
    exchange_alt = {
        "type": "alternatives",
        "groups": [
            {"label": groups[0]["label"], "segments": g0_segs},
            {"label": groups[1]["label"], "segments": g1_segs[:n]},
        ],
    }
    return [exchange_alt] + g1_segs[n:]


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


# ── Shared-block deduplication ───────────────────────────────────────────────

# Canonical doxology ordering (Source → Trinity → Father). All offices normalize to this.
_DOXOLOGY_CANONICAL_ORDER = [
    'Glory to God, Source of all being, eternal Word, and Holy Spirit:',
    'Glory to the holy and undivided Trinity, one God:',
    'Glory to the Father, and to the Son, and to the Holy Spirit:',
]

def _is_berakah_blessings(alt_block: dict) -> bool:
    """Three-option block of short 'Blessed be…' doxological conclusions."""
    groups = alt_block.get('groups', [])
    return (
        len(groups) == 3
        and all(
            len(g.get('segments', [])) == 2
            and g['segments'][0]['type'] == 'leader'
            and g['segments'][0]['text'].startswith('Blessed be')
            for g in groups
        )
    )

def _is_doxology(alt_block: dict) -> bool:
    groups = alt_block.get('groups', [])
    return (
        len(groups) == 3
        and all(
            g.get('segments') and g['segments'][0]['text'].startswith('Glory')
            for g in groups
        )
    )

def _is_affirmation(alt_block: dict) -> bool:
    groups = alt_block.get('groups', [])
    return (
        len(groups) == 2
        and groups[0].get('label', '').startswith("Apostles")
    )

def _canonical_doxology(alt_block: dict) -> dict:
    """Reorder a 3-group doxology to the canonical Source→Trinity→Father sequence."""
    groups = alt_block['groups']
    by_first_line = {g['segments'][0]['text']: g for g in groups if g.get('segments')}
    ordered = []
    for leader_text in _DOXOLOGY_CANONICAL_ORDER:
        grp = by_first_line.get(leader_text)
        if grp:
            ordered.append({**grp, 'label': _ROMAN[len(ordered)]})
    if len(ordered) == 3:
        return {'type': 'alternatives', 'groups': ordered}
    return alt_block  # fallback: leave as-is if we can't normalise


# ── Post-extraction text patches ─────────────────────────────────────────────
# Some PDF responses are genuinely lowercase in the source (not small-caps
# artefacts). _fix_casing capitalises them because they aren't in
# _CONTINUATION_STARTS. Patch them back here rather than widening
# _CONTINUATION_STARTS (which would affect every response).
#
# Format: (office_key, section_key, old_text, new_text)
_TEXT_PATCHES: list[tuple[str, str, str, str]] = [
    # BUG-18: Wednesday litany responses are lowercase in the PDF.
    # MP: eight identical responses
    ("ordinary-wednesday-mp", "litany",
     "Holy one, accomplish your purposes in us.",
     "holy one, accomplish your purposes in us."),
    # EP: four distinct responses that start with a capital after _fix_casing
    ("ordinary-wednesday-ep", "litany",
     "To declare the mystery of Christ.",
     "to declare the mystery of Christ."),
    ("ordinary-wednesday-ep", "litany",
     "Behold and tend the vine you have planted.",
     "behold and tend the vine you have planted."),
    ("ordinary-wednesday-ep", "litany",
     "In the strength of your name.",
     "in the strength of your name."),
    ("ordinary-wednesday-ep", "litany",
     "As we have put our hope in you.",
     "as we have put our hope in you."),
      # Fix 'The Evening Hymn:' capitalisation and per-hymn title casing (PDF artifacts)
    ("ordinary-sunday-ep", "phos_hilaron",
     'the evening hymn: “o Gladsome Light, o Grace”',
     'The Evening Hymn: “O Gladsome Light, O Grace”'),
    ("ordinary-monday-ep", "phos_hilaron",
     'the evening hymn: “o Gracious Light, Lord Jesus Christ”',
     'The Evening Hymn: “O Gracious Light, Lord Jesus Christ”'),
    ("ordinary-tuesday-ep", "phos_hilaron",
     'the evening hymn: “Light of the World, in Grace and Beauty”',
     'The Evening Hymn: “Light of the World, in Grace and Beauty”'),
    ("ordinary-wednesday-ep", "phos_hilaron",
     'the evening hymn: “o Light, Whose splendour thrills”',
     'The Evening Hymn: “O Light, Whose Splendour Thrills”'),
    ("ordinary-thursday-ep", "phos_hilaron",
     'the evening hymn: ”Christ, Mighty saviour”',
     'The Evening Hymn: “Christ, Mighty Saviour”'),
    ("ordinary-saturday-ep", "phos_hilaron",
     'the evening hymn: “now from the Altar of My heart”',
     'The Evening Hymn: “Now from the Altar of My Heart”'),
]

def _apply_text_patches(offices: dict) -> dict:
    """Apply _TEXT_PATCHES to correct responses the extractor mis-capitalised."""
    import copy
    offices = copy.deepcopy(offices)
    for office_key, section_key, old, new in _TEXT_PATCHES:
        section = offices.get(office_key, {}).get(section_key)
        if not isinstance(section, list):
            continue
        for seg in section:
            if seg.get("type") in ("response", "label") and seg.get("text") == old:
                seg["text"] = new
    return offices


def _add_reading_responses(offices: dict) -> dict:
    """
    Add reading_response to each office. The three alternatives are the same
    across all offices except the third option, whose leader text differs:
      - seasonal offices:  "Holy Word, Holy Wisdom."
      - ordinary offices:  "Holy wisdom, holy word."
    This is not captured by PDF extraction — it comes from PWC rubrics.
    """
    def _make(third_leader: str) -> dict:
        return {
            "type": "alternatives",
            "groups": [
                {"label": "I", "segments": [
                    {"type": "leader",   "text": "The word of the Lord."},
                    {"type": "response", "text": "Thanks be to God."},
                ]},
                {"label": "II", "segments": [
                    {"type": "leader",   "text": "Hear what the Spirit is saying to the Church."},
                    {"type": "response", "text": "Thanks be to God."},
                ]},
                {"label": "III", "segments": [
                    {"type": "leader",   "text": third_leader},
                    {"type": "response", "text": "Thanks be to God."},
                ]},
            ],
        }

    result = {}
    for office_key, office in offices.items():
        if office_key.startswith('_'):
            result[office_key] = office
            continue
        third = ("Holy wisdom, holy word." if office_key.startswith('ordinary-')
                 else "Holy Word, Holy Wisdom.")
        result[office_key] = {**office, 'reading_response': _make(third)}
    return result


def _dedup_shared(offices: dict) -> dict:
    """
    Scan every alternatives block across all offices.
    Doxologies and affirmations are identical across offices; extract each to
    _shared and replace inline occurrences with {type: "shared", key: "..."}.
    """
    shared: dict = {}

    def _walk(segs: list, office_key: str = "", section_key: str = "") -> list:
        out = []
        for seg in segs:
            if seg.get('type') != 'alternatives':
                out.append(seg)
                continue
            # Recursively walk into each group's segments first so nested
            # alternatives (e.g. berakah_blessings inside opening_responses group II)
            # are deduped before we inspect the parent block.
            new_groups = [
                {**g, 'segments': _walk(g.get('segments', []), office_key, section_key)}
                for g in seg.get('groups', [])
            ]
            seg = {**seg, 'groups': new_groups}

            if _is_doxology(seg):
                if 'doxology' not in shared:
                    shared['doxology'] = _canonical_doxology(seg)
                # The canticle doxology intro rubric ("At the end of the Canticle…" /
                # "After the Canticle…") is now emitted natively by _group_alternatives
                # as a plain rubric segment immediately before this alternatives block,
                # so no re-insertion is needed here.
                out.append({'type': 'shared', 'key': 'doxology'})
            elif _is_affirmation(seg):
                if 'affirmation' not in shared:
                    shared['affirmation'] = seg
                out.append({'type': 'shared', 'key': 'affirmation'})
            elif _is_berakah_blessings(seg):
                if 'berakah_blessings' not in shared:
                    shared['berakah_blessings'] = seg
                out.append({'type': 'shared', 'key': 'berakah_blessings'})
            else:
                out.append(seg)
        return out

    result = {}
    for office_key, office in offices.items():
        new_office = {}
        for section_key, segs in office.items():
            if isinstance(segs, list):
                new_office[section_key] = _walk(segs, office_key, section_key)
            else:
                new_office[section_key] = segs
        result[office_key] = new_office

    if shared:
        return {'_shared': shared, **result}
    return result


def _fix_shared_affirmation(offices: dict) -> dict:
    """
    Correct two known issues in _shared.affirmation that can't be caught by
    the per-office text-patch mechanism (shared blocks are deduplicated before
    _apply_text_patches runs, so the segment no longer lives in any office section):

    1. The Apostles' Creed group label is stripped of its article by _alt_label.
       Restore 'The Apostles' Creed'.
    2. 'he ascended into heaven' is missing a comma (BAS p.189).
       Add the comma so the line reads 'he ascended into heaven,'.
    """
    import copy
    offices = copy.deepcopy(offices)
    affirmation = offices.get('_shared', {}).get('affirmation', {})
    for group in affirmation.get('groups', []):
        if group.get('label', '').startswith('Apostles'):
            group['label'] = 'The Apostles’ Creed'
        for seg in group.get('segments', []):
            if seg.get('type') == 'response' and 'he ascended into heaven\n' in seg['text']:
                seg['text'] = seg['text'].replace(
                    'he ascended into heaven\n',
                    'he ascended into heaven,\n',
                )
    return offices


# ── Main extraction ───────────────────────────────────────────────────────────

def extract_office(pdf, start: int, end: int, office_key: str = "") -> dict:
    # Collect all styled lines across the page range.
    all_lines: list[tuple[str, str]] = []
    for book_pg in range(start, end + 1):
        idx = book_pg - 1
        if idx < len(pdf.pages):
            all_lines.extend(_page_styled_lines(pdf.pages[idx], office=office_key))

    # Pull title (first heading line) and subtitle (first leader line before any section).
    title = ""
    subtitle = ""
    header_done = False
    filtered_lines: list[tuple[str, str]] = []

    for typ, text in all_lines:
        if _is_noise(typ, text):
            _dbg(f"  NOISE [{typ}] {repr(text[:60])}", office=office_key)
            continue
        if not header_done:
            if not title and typ == "heading":
                title = text
                _dbg(f"  TITLE {repr(text[:60])}", office=office_key)
                continue
            if title and not subtitle and typ == "leader":
                subtitle = text
                header_done = True
                _dbg(f"  SUBTITLE {repr(text[:60])}", office=office_key)
                continue
            if title and typ == "heading":
                header_done = True
        filtered_lines.append((typ, text))

    _dbg(f"\n=== SECTION ASSIGNMENT: {office_key} ===", office=office_key)

    # Walk lines and split into sections by heading markers.
    sections: dict[str, list[dict]] = {}
    current_key: str | None = None
    current_segs: list[dict] = []

    def _flush():
        nonlocal current_segs
        if current_key is not None and current_segs:
            _dbg(f"  FLUSH {current_key!r}: {len(current_segs)} segs", office=office_key)
            sections[current_key] = _merge(current_segs)
        current_segs = []

    for typ, text in filtered_lines:
        if typ == "heading":
            key = _heading_to_key(text)
            raw_disp = repr(text[:60])
            if key is False:
                # Check if this is a known antiphon refrain rendered in heading style.
                content_type = "rubric"
                for pat in _RESPONSE_HDRS:
                    if pat.match(text):
                        content_type = "response"
                        break
                _dbg(f"  UNKNOWN-HDR → content in {current_key!r} as {content_type}: {raw_disp}", office=office_key)
                if current_key is not None:
                    current_segs.append({"type": content_type, "text": text})
                continue
            if key is _CONTINUE:
                # Structural heading that keeps the current section active (e.g. Lord's Prayer
                # heading — the intro + prayer text must flow into litany for post-processing).
                _dbg(f"  CONTINUE-HDR {raw_disp} (stays in {current_key!r})", office=office_key)
                continue
            _dbg(f"  HEADING {raw_disp} → section {key!r}", office=office_key)
            _flush()
            current_key = key  # may be None (major section label → ignored)
            # Preserve the phos_hilaron heading text as a "label" segment so
            # renderers can emit it as a titled section rather than bare hymn text.
            if key == "phos_hilaron" and text:
                current_segs.append({"type": "label", "text": text})
            continue

        if current_key is not None:
            _dbg(f"  [{current_key}] {typ} {repr(text[:60])}", office=office_key)
            current_segs.append({"type": typ, "text": text})
        else:
            _dbg(f"  [NO-SECTION] {typ} {repr(text[:60])}", office=office_key)

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

    # Apply alternatives grouping to all sections.
    _NO_ALT_SECTIONS = {"litany", "lords_prayer_intro"}
    for key in list(sections.keys()):
        if key not in _NO_ALT_SECTIONS:
            sections[key] = _group_alternatives(sections[key], office=office_key, section=key)

    # Fold Berakah prayer blessing conclusions into nested alternatives inside
    # group II of seasonal opening_responses (not applicable to ordinary-time).
    if "opening_responses" in sections:
        sections["opening_responses"] = _fold_berakah_blessings(
            sections["opening_responses"], office=office_key
        )
    if "thanksgiving_for_light" in sections:
        sections["thanksgiving_for_light"] = _fold_berakah_blessings(
            sections["thanksgiving_for_light"], office=office_key
        )
        sections["thanksgiving_for_light"] = _split_thanksgiving(
            sections["thanksgiving_for_light"]
        )

    # Build result.
    result: dict = {"title": title}
    if subtitle:
        result["subtitle"] = subtitle

    # Preserve canonical section order.
    for key in ("opening_responses", "thanksgiving_for_light", "phos_hilaron",
                "invitatory", "responsory", "canticle", "affirmation",
                "intercessions", "litany", "seasonal_collects", "lords_prayer_intro",
                "dismissal"):
        if key in sections and sections[key]:
            result[key] = sections[key]

    return result


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    ap = argparse.ArgumentParser()
    ap.add_argument("--accept", action="store_true",
                    help="Update tools/manifest.json with current output hashes")
    args = ap.parse_args()

    pdf_path = ROOT / "sources" / "pray-without-ceasing.pdf"
    if not pdf_path.exists():
        print(f"ERROR: {pdf_path} not found", file=sys.stderr)
        sys.exit(1)

    out_path = ROOT / "data" / "offices.json"

    offices: dict[str, dict] = {}
    with pdfplumber.open(pdf_path) as pdf:
        for key, start, end in OFFICES:
            _dbg(f"\n{'='*60}\nEXTRACTING: {key} (pages {start}–{end})\n{'='*60}", office=key)
            offices[key] = extract_office(pdf, start, end, office_key=key)
            sections = [k for k in offices[key] if k not in ("title", "subtitle")]
            print(f"  {key}: {sections}")
            # Log final section group counts for quick audit.
            for sk, sv in offices[key].items():
                if sk in ("title", "subtitle") or not isinstance(sv, list):
                    continue
                for seg in sv:
                    if seg.get('type') == 'alternatives':
                        glabels = [g['label'] for g in seg.get('groups', [])]
                        _dbg(f"  RESULT {sk}: alternatives {glabels}", office=key)

    offices = _dedup_shared(offices)
    offices = _fix_shared_affirmation(offices)
    offices = _add_reading_responses(offices)
    offices = _apply_text_patches(offices)
    n_shared = len(offices.get('_shared', {}))
    print(f"\nShared blocks extracted: {list(offices.get('_shared', {}).keys())}")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(offices, f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(offices) - (1 if '_shared' in offices else 0)} offices + {n_shared} shared → {out_path}")

    # Spot checks.
    shared_blocks = offices.get('_shared', {})

    def _resolve(seg):
        """Expand {type: shared} sentinels for search purposes."""
        if seg.get('type') == 'shared':
            return shared_blocks.get(seg['key'], seg)
        return seg

    def _find(segs, seg_type, fragment):
        for s in segs:
            s = _resolve(s)
            if s.get("type") == seg_type and fragment in s.get("text", ""):
                return True
            for g in s.get("groups", []):
                if _find(g.get("segments", []), seg_type, fragment):
                    return True
        return False

    def _has_alt_group(segs, label_fragment):
        for s in segs:
            s = _resolve(s)
            if s.get("type") == "alternatives":
                for g in s.get("groups", []):
                    if label_fragment in g.get("label", ""):
                        return True
        return False

    content_checks = [
        ("easter-mp",   "opening_responses", "leader",   "Alleluia! Christ is risen."),
        ("easter-mp",   "opening_responses", "response", "The Lord is risen indeed"),
        ("easter-mp",   "responsory",        "rubric",   "The Responsory is said or sung"),
        ("easter-mp",   "seasonal_collects", "leader",   "Living God"),
        ("advent-mp",   "opening_responses", "leader",   "Creator of the stars"),
        ("ordinary-sunday-mp", "opening_responses", "leader", "proclaim your praise"),
    ]
    alt_checks = [
        ("easter-mp",   "canticle",          "Song of Moses"),
        ("easter-ep",   "canticle",          "Song of Mary"),
        ("advent-mp",   "canticle",          "Song of Zechariah"),
        ("advent-ep",   "canticle",          "Song of Mary"),
        ("lent-mp",     "canticle",          "Song of Manasseh"),
        ("advent-mp",   "affirmation",       "Apostles"),
        ("advent-mp",   "affirmation",       "Hear, O Israel"),
    ]
    print("\nSpot checks:")
    ok = True
    for key, section, seg_type, fragment in content_checks:
        segs = offices.get(key, {}).get(section, [])
        found = _find(segs, seg_type, fragment)
        mark = "✓" if found else "✗"
        short = repr(fragment[:30])
        print(f"  {key}.{section} contains {short}: {mark}")
        if not found:
            ok = False
    for key, section, label_frag in alt_checks:
        segs = offices.get(key, {}).get(section, [])
        found = _has_alt_group(segs, label_frag)
        mark = "✓" if found else "✗"
        print(f"  {key}.{section} alternatives group {label_frag!r}: {mark}")
        if not found:
            ok = False
    if not ok:
        sys.exit(1)

    check_manifest([out_path], ROOT, accept=args.accept)


if __name__ == "__main__":
    run()
