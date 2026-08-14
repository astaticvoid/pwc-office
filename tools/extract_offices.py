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
import copy
import json
import os
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF
from corrections_lib import replace_occurrences
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
# Page bounds detected by detect_office_bounds.py from the PDF content.
# Regenerate with: python3 tools/detect_office_bounds.py --write
def _load_offices():
    bounds_path = ROOT / "tools" / "office_bounds.json"
    if not bounds_path.exists():
        sys.exit(f"Bounds file not found: {bounds_path}\nRun: python3 tools/detect_office_bounds.py --write")
    bounds = json.loads(bounds_path.read_text())
    return [(k, v["start"], v["end"]) for k, v in bounds.items()]

OFFICES = _load_offices()

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
    (re.compile(r'^(?:the )?evening hymn\b',              re.IGNORECASE), "phos_hilaron"),
    (re.compile(r'^the Responsory$',                    re.IGNORECASE), "responsory"),
    (re.compile(r'^the Canticle$',                      re.IGNORECASE), "canticle"),
    (re.compile(r'Affirmation of faith',                re.IGNORECASE), "affirmation"),
    # Ordinary-time: free-prayer space + day-specific topic prompts before the Litany
    (re.compile(r'^intercessions and thanksgivings$',   re.IGNORECASE), "intercessions"),
    (re.compile(r'^the Litany$',                        re.IGNORECASE), "litany"),
    # Lord's Prayer: keep litany section active so intro + prayer text flow in and are
    # later split out by _split_lords_prayer. Anchored like every other entry (#93),
    # so a heading-styled line that merely BEGINS with these words — e.g. a printed
    # "…continues with the Lord's Prayer." transition rubric — could never be
    # consumed as structure. Note the class is ASCII-only: the PDF prints a U+2019
    # apostrophe, so this entry is currently inert and the heading arrives via the
    # UNKNOWN-HDR path instead (conservation watches for that changing).
    (re.compile(r"^the Lord['']?s Prayer$",             re.IGNORECASE), _CONTINUE),
    (re.compile(r'^the dismissal$',                     re.IGNORECASE), "dismissal"),
    # The psalm/lesson content comes from the lectionary, not the form, so these
    # sections keep only the fixed rubrics printed around them — filtered to
    # label + rubric segments at flush time, before _merge (#84).
    (re.compile(r'^the Reading$',                       re.IGNORECASE), "reading_rubrics"),
    (re.compile(r'^the Psalm$',                         re.IGNORECASE), "psalm_rubrics"),
]

# Every section that reaches the renderer, in the order a form presents them.
# This is the canonical list — `_SUB_HDR_MAP` above is NOT, and using it as one is
# a repeated source of wrong measurements.
SECTION_ORDER = (
    "opening_responses", "thanksgiving_for_light", "phos_hilaron",
    "invitatory", "psalm_rubrics", "reading_rubrics", "responsory", "canticle", "affirmation",
    "intercessions", "litany", "seasonal_collects", "lords_prayer_intro",
    "dismissal",
)

# Sections no heading ever names. They are carved out of the litany block after
# section assignment, by _split_litany_collects and _split_lords_prayer, so any
# analysis that walks typed lines and assigns sections via _heading_to_key
# reports ZERO for these rather than failing — which has silently produced wrong
# answers more than once (a slack sweep that missed 334 breaks, an audit that
# reported "no breaks sampled"). Walk SECTION_ORDER, or a built form, instead.
SPLIT_SECTIONS = frozenset({"seasonal_collects", "lords_prayer_intro"})


def sections_of(form: dict):
    """Yield (section_key, segments) for a built form, in canonical order.

    The accessor analyses should use: it cannot miss a split-out section the way
    heading-derived assignment does.
    """
    for key in SECTION_ORDER:
        segs = form.get(key)
        if segs:
            yield key, segs


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
# C0 controls PyMuPDF emits for glyphs with no Unicode mapping.
_CONTROL_CHARS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')

def _is_noise(typ: str, text: str) -> bool:
    if typ == "footer":
        return True
    if _PAGE_NUM.match(text):
        return True
    if _RUNNING_HDR.match(text):
        return True
    return False


# ── Segment merging ───────────────────────────────────────────────────────────

# Litany line breaks are decided per break from page geometry, not per section.
# The litany is the one genuinely mixed section: seasonal forms set it as verse
# (the Advent litany is the O Antiphons, lines ending 90-215pt short of the
# margin) while ordinary-time forms end with prose collects that really do wrap
# ("...you create us by your power and redeem us by your / love"). Measured
# across all 168 litany breaks, the end-of-line gap is bimodal: 67 breaks under
# 30pt, 83 over 70pt, and 18 between. See #39.
# A break is forced iff the next line's first word could not have fitted on it.
# `slack` measures exactly that, so it decides directly and no gap band is needed.
# Only near zero is the answer genuinely uncertain: the measure is known to about
# a point, so anything inside this dead band is adjudicated by hand instead.
# Verified across all 149 litany breaks — every deliberate one has at least
# 26.8pt of slack and the single true wrap has -22.8pt, so nothing real sits
# near the band.
_SLACK_DECIDES = 3.0
# Prose needs a much higher bar than verse. The book's prose is not composed
# greedily: a word that would have fitted is pushed to the next line to even out
# the paragraph, so a wrap can show several points of POSITIVE slack and the
# "would it have fitted?" test alone reads it as chosen. Measured over every
# break in the prose sections, that shuffling reaches 26.6pt, while the one
# genuinely structural break — the Christmas dismissal couplet — leaves 256.4pt.
# 60 sits clear of the first and nowhere near the second.
#
# Verse is unaffected: a chosen verse break leaves 26.8pt at minimum and usually
# far more, so `slack < 0` settles it there without a threshold.
_PROSE_STRUCTURAL_SLACK = 60.0
# Used only where slack cannot be measured, i.e. the next line is on another page.
_LITANY_VERSE_MIN_GAP = 70.0
# Body leading is ~12.5pt and a paragraph or stanza boundary is 16.5pt or more;
# 15 sits between them, the same split spans_to_typed_lines already uses for
# creed stanza breaks.
#
# The real headroom is narrower than those figures suggest. The tightest true
# boundary in the corpus is 16.5pt (ordinary-sunday-ep) and the widest gap that
# is NOT a boundary is 14.5pt (also ordinary-sunday-ep, between "To you of right
# belongs all praise of holy songs," and "O Son of God, life-giver;" — splitting
# there would sever a subject from its verb). So the discriminating window is
# 14.5 <-> 16.5, and this threshold sits 0.5pt off a false positive. Correct on
# the current PDF and verified across all seven hymns, but re-check it if the
# book is ever re-cut.
_PARAGRAPH_LEAD = 15.0
_LITANY_PARAGRAPH_LEAD = _PARAGRAPH_LEAD


def _insert_stanza_breaks(segs: list) -> list:
    """Insert a blank line at each stanza boundary the page actually shows.

    Hymn stanza breaks are vertical whitespace, and spans_to_typed_lines only
    emits a synthetic blank for `response` lines, so for a `leader` hymn the
    structure is lost by the time the segment is built. This restores it from
    the leading recorded per break, rather than assuming a stanza length.

    Replaces _fix_phos_hilaron, which inserted a break every 4th line. That held
    for six of the seven evening hymns but not for "O gladsome Light", which is
    in 3-line stanzas: it printed 4/4/1 and split a sentence across the break
    ("we see the evening light, / <break> / our hymn of praise outpouring").
    """
    for seg in segs:
        if seg.get("type") == "alternatives":
            for g in seg.get("groups", []):
                _insert_stanza_breaks(g.get("segments", []))
            continue
        if seg.get("type") != "leader" or not seg.get("text"):
            continue
        lines = seg["text"].split("\n")
        leads = seg.get("break_leads", [])
        if len(leads) != len(lines) - 1:
            continue  # alignment lost; leave the text alone

        # A break whose leading is None sits at a page boundary, where leading
        # cannot be measured. Resolve those from the stanza length the rest of
        # this hymn actually shows: take the measurable boundaries first, and if
        # they agree on one length, apply it. If they disagree, leave the break
        # out rather than guess — that is what the old every-4 rule did wrong.
        unknown = {i for i, lead in enumerate(leads) if lead is None}
        measured = [i for i, lead in enumerate(leads) if lead is not None and lead > _PARAGRAPH_LEAD]
        lengths, prev = [], -1
        for i in measured:
            # Skip any span containing an unknown break: its length is inflated by
            # the very boundary being resolved, which would defeat the inference.
            if not any(prev < u < i for u in unknown):
                lengths.append(i - prev)
            prev = i
        uniform = lengths[0] if lengths and len(set(lengths)) == 1 else None

        out, since_break = [lines[0]], 1
        for i, nxt in enumerate(lines[1:]):
            if leads[i] is None:
                stanza_break = uniform is not None and since_break == uniform
            else:
                stanza_break = leads[i] > _PARAGRAPH_LEAD
            if stanza_break:
                out.append("")
                since_break = 0
            out.append(nxt)
            since_break += 1
        seg["text"] = "\n".join(out)
    return segs

# Breaks that geometry cannot settle, adjudicated by hand against the PDF.
#
# `slack` answers the question directly, so this list only catches breaks inside
# the dead band where the measure's own precision (about a point) is the limit.
# It went from 24 entries to 2 when the margin stopped being measured per page;
# the other 22 were never ambiguous, only mis-measured. Keyed by the text of the
# line the break follows.
#
# Both entries below are couplets whose first line happens to run nearly the full
# measure, so the next word does not quite fit and the geometry reads as forced.
# Their surrounding petitions are unambiguous couplets set to the same pattern
# with a repeating response, and a wrap landing exactly on the couplet boundary
# is not credible against that.
#
# tools/tests/test_special_cases.py pins the size of these lists: if extraction
# starts needing more hand-adjudicated breaks, the geometry has stopped working
# and the build fails until someone looks.
_LITANY_VALLEY_JOIN: frozenset[str] = frozenset()
_LITANY_VALLEY_KEEP: frozenset[str] = frozenset({
    "May candidates for baptism and confirmation live by every word",
    "Guide us into new and just ways of sharing the goods of the earth,",
})


def _reflow_by_geometry(segs: list, office_key: str = "", section: str = "",
                        prose: bool = False,
                        types: tuple[str, ...] = ("leader",)) -> list:
    """Join only those breaks the typesetter was forced into.

    Replaces the unconditional joins that _reflow_leader_prose used to apply to
    litany (#39) and seasonal_collects (#42), which flattened every petition in
    all 30 forms and left the collects correct only by accident.

    `types` names the segment types to reflow. It defaults to leader lines
    because that is what the litany/collect/dismissal material is made of;
    sections whose prose lives in rubric segments (psalm_rubrics,
    reading_rubrics — #84) pass those types explicitly. Widening the default
    would silently re-wrap rubrics in every other section.
    """
    for seg in segs:
        if seg.get("type") == "alternatives":
            for g in seg.get("groups", []):
                _reflow_by_geometry(g.get("segments", []), office_key, section, prose, types)
            continue
        if seg.get("type") not in types or not seg.get("text"):
            continue
        lines = seg["text"].split("\n")
        gaps = seg.get("break_gaps", [])
        slacks = seg.get("break_slacks", [])
        leads = seg.get("break_leads", [])
        if len(gaps) != len(lines) - 1 or len(leads) != len(gaps) or len(slacks) != len(gaps):
            # Alignment lost — a later pass rewrote the text. Fall back to the
            # historical behaviour rather than guessing at which break is which.
            _dbg(f"  LITANY gap misalignment ({len(gaps)} gaps, {len(lines)} lines)"
                 f" — joining unconditionally", office=office_key)
            seg["text"] = re.sub(r"\s*\n\s*", " ", seg["text"]).strip()
            continue
        out = lines[0]
        for i, nxt in enumerate(lines[1:]):
            gap, slack = gaps[i], slacks[i]
            line = lines[i].strip()
            para = False
            if (leads[i] or 0) > _LITANY_PARAGRAPH_LEAD:
                # Extra leading below the line — a paragraph or stanza boundary.
                # The typesetter cannot open up space by wrapping, so this is
                # decisive regardless of how full the line ran. Carry the
                # division through as a blank line rather than flattening it to
                # an ordinary break: in every litany this is the bidding
                # ("Let us pray, saying, ...") standing apart from the first
                # petition (#40).
                join, para = False, True
            elif prose:
                # Only an unmistakably short line is structural here; see
                # _PROSE_STRUCTURAL_SLACK. Everything else is a wrap.
                join = not (slack is not None and slack >= _PROSE_STRUCTURAL_SLACK)
            elif slack is not None and abs(slack) >= _SLACK_DECIDES:
                # The decisive question: would the next line's first word have
                # fitted here? If yes the break was chosen; if not it was forced.
                join = slack < 0
            elif slack is None and gap >= _LITANY_VERSE_MIN_GAP:
                # Next line is on another page, so the word cannot be measured;
                # only a break with room to spare can still be called deliberate.
                join = False
            elif line in _LITANY_VALLEY_JOIN:
                join = True
            elif line in _LITANY_VALLEY_KEEP:
                join = False
            else:
                # Geometry could not decide. Fall back to the section's own mode:
                # joining a prose wrap restores flowing text, while keeping a
                # verse break preserves lineation. Each errs the harmless way for
                # the material it governs.
                join = False
                where = ("unmeasurable (page break)" if slack is None
                         else f"slack={slack:.1f}pt")
                print(f"  WARNING [{office_key}/{section}] unadjudicated break, {where}, "
                      f"gap={gap:.1f}pt, kept: {line[:60]!r}", file=sys.stderr)
            sep = " " if join else ("\n\n" if para else "\n")
            out += sep + nxt.strip()
        seg["text"] = re.sub(r"[ \t]+", " ", out).strip()
    return segs

def _merge(segs: list[dict]) -> list[dict]:
    """Merge consecutive segments of the same type into one.

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
            if sep == "\n":
                # Record the geometry of the break, so _reflow_by_geometry can judge
                # each one individually later: the end-of-line gap of the line
                # the break follows, and the leading opened up below it. Both
                # lists stay index-aligned with the "\n"s in prev["text"].
                prev.setdefault("break_gaps", []).append(prev.get("gap", 0.0))
                prev.setdefault("break_slacks", []).append(prev.get("slack"))
                prev.setdefault("break_leads", []).append(seg.get("lead", 0.0))
            prev["text"] += sep + seg["text"]
            # The segment now ends where `seg` ends.
            prev["gap"] = seg.get("gap", 0.0)
            prev["slack"] = seg.get("slack")
        else:
            merged.append(dict(seg))
    return [s for s in merged if s["text"].strip()]


# ── Post-process: split seasonal collects from litany ─────────────────────────

_AFTER_SILENCE     = re.compile(r'After a period of silence', re.IGNORECASE)
_EITHER_COLLECT    = re.compile(r'Either the Collect of the Day', re.IGNORECASE)

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
            # Keep every segment, including the section-closing hand-off rubric
            # ("{office} Prayer continues with the Lord's Prayer."): it is printed
            # text (ADR 0013) and closes seasonal_collects. The main pipeline
            # re-homes it there after _split_lords_prayer (#93). The old version
            # discarded it here, which is how it left the data (issue #93).
            collect_segs = segs[i:]
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
# with adjacent segments. All variants are kept as PWC text (#93).
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

        # "{office} Prayer continues with …" rubrics are PWC liturgical
        # transitions and are kept — including the Lord's Prayer hand-off,
        # which is printed text that closes the collects section (#93). It was
        # discarded here until #93, which is what ate it out of the data.

        # Canticle intro: '"Name A," "Name B," … may be said or sung.\nName A (citation)'
        if typ == 'rubric' and _CANTICLE_INTRO.match(text):
            lines = text.strip().split('\n')
            # The intro spans multiple PDF lines — join with space for a single rubric.
            intro_part = ' '.join(line.strip() for line in lines[:-1] if line.strip())
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
            intro_part = ' '.join(line.strip() for line in lines[:-1] if line.strip())
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
            _dbg("    SKIP: fewer than 3 groups", office=office, section="opening_responses")
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
            _dbg("    SKIP: group[1] doesn't end with response", office=office, section="opening_responses")
            result.append(seg)
            continue

        # Find the last leader in group[1]; its final line should be the first blessing option.
        leaders = [(i, s) for i, s in enumerate(g1_segs) if s['type'] == 'leader']
        if not leaders:
            _dbg("    SKIP: group[1] has no leader segments", office=office, section="opening_responses")
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

# ── Reading/Psalm rubric sections (#84) ───────────────────────────────────────

# The Reading and Psalm pages print fixed rubrics around content that comes
# from the lectionary. Those rubrics belong in the data (ADR 0019 item 7 needs
# the Responsory transition; ADR 0013's rubric rule can only check rubrics that
# exist in the data), while the lectionary content itself must stay out. The
# filtering happens in _flush (before _merge); the reading responses on the
# page are leader/response lines and drop with the rest of the content, so
# `reading_response` continues to come from _add_reading_responses until the
# extracted rubrics are proven and that synthesizer is retired.


# ── Section-closing office transitions ───────────────────────────────────────

_OFFICE_TRANSITION = re.compile(r'^(?:Morning|Evening) Prayer continues with\b',
                                re.IGNORECASE)


def _hoist_office_transition(segs: list, office_key: str = "", section: str = "") -> list:
    """Lift a section-closing "{office} Prayer continues with …" rubric out of
    the alternatives block that swallowed it.

    The rubric is printed after the last alternative, not inside it, and its
    wording names both the office and the section that follows — four distinct
    variants across the 30 forms for the affirmation alone. _group_alternatives
    cannot tell it from a group's own trailing rubric and sweeps it into the
    final group, where _dedup_shared then buries it: that pass keys the
    doxology and affirmation blocks by shape, not by equality, and keeps
    whichever office it meets first, so every form would inherit one office's
    copy and all 15 Evening Prayer forms would read "Morning Prayer continues
    with the Litany." (#84 — the running-header fix is what recovered these
    rubrics into the blocks in the first place).
    """
    if not segs or segs[-1].get("type") != "alternatives":
        return segs
    groups = segs[-1].get("groups", [])
    inner = groups[-1].get("segments", []) if groups else []
    # The trailer can be a RUN of rubrics: the transition itself plus any rubric
    # the book prints after it — e.g. the ordinary-time collects' last group ends
    # "…continues with the Lord's Prayer." / "The Lord's Prayer" (#93). Nothing
    # printed after a section-closing transition belongs inside the alternative,
    # but a rubric printed BEFORE the transition is still the group's content,
    # so only the tail from the first transition onward is hoisted.
    trailer: list[dict] = []
    while inner and inner[-1].get("type") == "rubric":
        trailer.insert(0, inner.pop())
    start = next(
        (i for i, t in enumerate(trailer)
         if _OFFICE_TRANSITION.match(t.get("text", "").strip())),
        None,
    )
    if start is None:
        inner.extend(trailer)  # no transition: the run is the group's own content
        return segs
    inner.extend(trailer[:start])
    trailer = trailer[start:]
    _dbg(f"  HOIST [{section}] {trailer[0]['text'][:60]!r} out of last group",
         office=office_key)
    if not inner:
        # The run was the group's only content, so the group is now an empty
        # alternative. renderAlternatives builds a tab per group without
        # checking, so leaving it would put a live tab over a blank panel. No
        # group empties on the current corpus — every one carries its creed or
        # canticle text — but the group is only ever this thin because
        # _group_alternatives mistook the trailer for content in the first place.
        groups.pop()
        _dbg(f"  HOIST [{section}] dropped the group it emptied", office=office_key)
        if not groups:
            return segs[:-1] + trailer
    return segs + trailer


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

# Ordinary-time morning prayer keeps "Alleluia." after the opening doxology
# (dropped in Lent/seasonal forms elsewhere), printed once per "or" option in
# the PDF but said only once, after whichever option is chosen. If baked into
# each group's response text it would get hoisted (or lost) along with the
# doxology's dedup to _shared, which is used everywhere doxology appears
# (after every Psalm/Canticle too) — so it's stripped here and re-attached by
# the caller as one standalone trailing segment on the forms that had it.
def _split_doxology_alleluia(alt_block: dict) -> tuple[dict, bool]:
    groups = alt_block.get('groups', [])
    has_alleluia = groups and all(
        g.get('segments')
        and g['segments'][-1]['type'] == 'response'
        and g['segments'][-1]['text'].endswith('\nAlleluia.')
        for g in groups
    )
    if not has_alleluia:
        return alt_block, False
    new_groups = []
    for g in groups:
        segs = list(g['segments'])
        last = dict(segs[-1])
        last['text'] = last['text'][: -len('\nAlleluia.')]
        segs[-1] = last
        new_groups.append({**g, 'segments': segs})
    return {**alt_block, 'groups': new_groups}, True

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



def _normalize_whitespace(offices: dict) -> dict:
    """Fix common PyMuPDF whitespace artifacts across all forms."""
    import copy
    offices = copy.deepcopy(offices)

    # Span-join artifacts, not book typography: PyMuPDF leaves a space before
    # some punctuation and splits a trailing "Amen ." off its block. Every
    # section wants these fixed, so the replacements are unconditional and no
    # section needs an exemption — there is no line-join step here to opt out
    # of, extraction decides each break from the page geometry instead (#39).
    # "Amen ." is the bulk of it, 84 of the 86 occurrences, and it is
    # load-bearing rather than cosmetic: render.js's Amen match and
    # validate_office.cjs's tier-1 Amen rule both require "Amen." exactly.
    def _fix(text):
        text = text.replace(" ,", ",")
        text = text.replace(" !", "!")
        text = text.replace(" ?", "?")
        text = text.replace("Amen .", "Amen.")
        text = text.replace(" \n", "\n")
        return text

    def _walk(segs):
        for seg in segs:
            if seg.get("type") == "alternatives":
                for g in seg.get("groups", []):
                    _walk(g.get("segments", []))
            elif "text" in seg:
                seg["text"] = _fix(seg["text"])

    for office_key, form in offices.items():
        if office_key.startswith("_") and office_key != "_shared":
            continue
        for segs in form.values():
            if isinstance(segs, list):
                _walk(segs)
    return offices


def _add_reading_responses(offices: dict) -> dict:
    """
    Add reading_response to each office. The three alternatives are the same
    across all offices. The third option's leader is "Holy Word, Holy Wisdom."
    in every form, confirmed by upstream review of the app (ADR 0015): the
    seasonal/ordinary distinction previously encoded here reproduced the
    printed book's error, which the errata corrects (Ordinary p. 132,
    "PWC has the wrong order"). This is not captured by PDF extraction — it
    comes from PWC rubrics.
    """
    def _make() -> dict:
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
                    {"type": "leader",   "text": "Holy Word, Holy Wisdom."},
                    {"type": "response", "text": "Thanks be to God."},
                ]},
            ],
        }

    result = {}
    for office_key, office in offices.items():
        if office_key.startswith('_'):
            result[office_key] = office
            continue
        result[office_key] = {**office, 'reading_response': _make()}
    return result


def _blocks_equal(a: dict, b: dict) -> bool:
    """Structural equality for alternatives blocks (the normalize_offices model)."""
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def _block_content_sig(block: dict) -> str:
    """Content-only signature for a shared alternatives block.

    Collapses every run of whitespace to a single space so that line-break and
    paragraph differences — legitimate per-page geometry (ADR 0012) — do not
    create spurious variants, while a genuine word change does.
    """
    text = " ".join(
        seg.get("text", "")
        for group in block.get("groups", [])
        for seg in group.get("segments", [])
    )
    return " ".join(text.split())


def _load_shared_corrections() -> dict:
    """office_text corrections targeting _shared.<key>, grouped by key.

    Loaded read-only from the committed manifest so _dedup_shared can tell a
    known, already-corrected divergence apart from a new one (#103). stage-1
    never patches, so ADR 0005 is unaffected; an absent manifest just means no
    divergence is pre-reconciled and every warning fires as before.
    """
    path = ROOT / "data" / "corrections.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    by_key: dict = {}
    for entry in data.get("office_text", []):
        if (entry.get("office") == "_shared"
                and isinstance(entry.get("old"), str)
                and isinstance(entry.get("new"), str)):
            by_key.setdefault(entry.get("field"), []).append(entry)
    return by_key


def _dedup_shared(offices: dict) -> dict:
    """
    Scan every alternatives block across all offices.
    Doxologies and affirmations are identical across offices; extract each to
    _shared and replace inline occurrences with {type: "shared", key: "..."}.

    The first block met is kept as canonical. Every later block is compared
    against it and a mismatch is reported rather than silently discarded —
    _dedup_shared used to keep the first form's copy without looking at the
    others, so one defective printing (advent-mp's creed missing a comma, #101)
    was adopted and the 29 correct ones overwritten without a word. With the
    disagreement visible, a known divergence is resolved by a
    data/corrections.json entry against _shared.<key>; anything new surfaces
    as this warning and must be audited before it can ship.

    A divergence the manifest already corrects does not warn (#103): an
    office_text entry against _shared.<key> reconciles the block if applying
    its old→new to the stored first copy reproduces the differing block, so
    the constant re-warning for a known, corrected divergence (the creed
    comma, #101) stops burying the next real one. Removing the correction
    re-arms the warning; an unrelated new divergence on the same key still
    fires.
    """
    shared: dict = {}
    shared_origin: dict = {}  # key -> (office, section) where the canonical was kept
    warned: set = set()       # (key, divergent-block json) signatures already reported
    shared_corrections = _load_shared_corrections()

    def _store_shared(key: str, block: dict, office_key: str, section_key: str) -> None:
        if key not in shared:
            shared[key] = block
            shared_origin[key] = (office_key, section_key)
            return
        if _blocks_equal(shared[key], block):
            return
        # A committed office_text correction against _shared.<key> may already
        # reconcile this divergence — applying its old→new to the stored first
        # copy should reproduce the differing block. If so, the manifest owns
        # the difference (it normalizes the shipped text in apply_corrections),
        # so this is not a new defect and the warning would be noise.
        for entry in shared_corrections.get(key, []):
            trial = copy.deepcopy(shared[key])
            replace_occurrences(trial, entry["old"], entry["new"])
            if _block_content_sig(trial) == _block_content_sig(block):
                return
        # Dedupe per distinct *content* variant, not per key and not per raw
        # structure: two printings differing only in line breaks (legitimate
        # per-page geometry, ADR 0012) are the same content, but a second,
        # genuinely different defective printing is still reported rather than
        # silently overwritten (the #101 silent-overwrite class).
        sig = (key, _block_content_sig(block))
        if sig in warned:
            return
        warned.add(sig)
        origin_office, origin_section = shared_origin.get(key, ("—", "—"))
        print(f"  WARNING: shared.{key} differs across forms — kept the first form's "
              f"copy ({origin_office}/{origin_section}), {office_key}/{section_key} "
              f"disagrees; if authorised, add an office_text correction against "
              f"_shared.{key}")

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
                seg, has_alleluia = _split_doxology_alleluia(seg)
                _store_shared('doxology', _canonical_doxology(seg), office_key, section_key)
                # The canticle doxology intro rubric ("At the end of the Canticle…" /
                # "After the Canticle…") is now emitted natively by _group_alternatives
                # as a plain rubric segment immediately before this alternatives block,
                # so no re-insertion is needed here.
                out.append({'type': 'shared', 'key': 'doxology'})
                if has_alleluia:
                    out.append({'type': 'response', 'text': 'Alleluia.'})
            elif _is_affirmation(seg):
                _store_shared('affirmation', seg, office_key, section_key)
                out.append({'type': 'shared', 'key': 'affirmation'})
            elif _is_berakah_blessings(seg):
                _store_shared('berakah_blessings', seg, office_key, section_key)
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
    Restore the article _alt_label strips from the one alternatives-group label
    the book prints as 'The Apostles' Creed' ('Apostles' -> 'The Apostles' Creed').
    Kept as code rather than a data/corrections.json entry because it is this
    pipeline's own label-stripping needing to be undone, not a source-text
    divergence — and the corrections categories address offices and fields, not
    a group label nested inside a shared alternatives block.

    The creed comma is a separate matter and no longer lives here: _dedup_shared
    keeps the first form's copy of _shared.affirmation, and advent-mp is the one
    printing of 30 that omits the comma, so the shared block inherited the
    defective form. That divergence is a real one and is handled by an
    office_text correction against _shared.affirmation in data/corrections.json
    (#101).
    """
    import copy
    offices = copy.deepcopy(offices)
    affirmation = offices.get('_shared', {}).get('affirmation', {})

    for group in affirmation.get('groups', []):
        if group.get('label', '').startswith('Apostles'):
            group['label'] = 'The Apostles’ Creed'
    return offices


# ── Main extraction ───────────────────────────────────────────────────────────

def extract_office(typed_lines: list, office_key: str = "") -> dict:
    title = ""
    subtitle = ""
    header_done = False
    filtered_lines: list = []

    for typ, text, gap, slack, lead in typed_lines:
        if _is_noise(typ, text):
            _dbg(f"  NOISE [{typ}] {repr(text[:60])}", office=office_key)
            continue
        if not header_done:
            if not title and typ == "heading":
                # The Advent title carries an unmapped glyph after it, which
                # PyMuPDF hands back as U+0003 and which would ship into the
                # UI as a stray control character.
                title = _CONTROL_CHARS.sub("", text).strip()
                _dbg(f"  TITLE {repr(title[:60])}", office=office_key)
                continue
            if title and typ == "leader":
                # The date-range subtitle is set as a centred block, two lines
                # on eight of the seasonal forms ("From Ash Wednesday until the
                # / Sunday before Palm/Passion Sunday"). Taking only the first
                # line left those eight ending mid-clause, so collect leader
                # lines until the first section heading closes the header.
                subtitle = f"{subtitle} {text}".strip() if subtitle else text
                _dbg(f"  SUBTITLE {repr(subtitle[:60])}", office=office_key)
                continue
            if title and typ == "heading":
                header_done = True
        filtered_lines.append((typ, text, gap, slack, lead))

    _dbg(f"\n=== SECTION ASSIGNMENT: {office_key} ===", office=office_key)

    # Walk lines and split into sections by heading markers.
    sections: dict[str, list[dict]] = {}
    current_key: str | None = None
    current_segs: list[dict] = []

    def _flush():
        nonlocal current_segs
        if current_key is not None and current_segs:
            # The Reading/Psalm pages mix fixed rubrics with lectionary content
            # (#84). Drop the content BEFORE _merge: merging joins same-type
            # neighbours, and rubric lines there alternate with leader/response
            # lines ("...is read." / "The word of the Lord." / "Thanks be to
            # God."), so merged text would glue rubric to content beyond any
            # later filter's reach.
            segs = current_segs
            if current_key in ("psalm_rubrics", "reading_rubrics"):
                kept = [s for s in segs if s["type"] in ("label", "rubric")]
                for s in segs:
                    if s["type"] not in ("label", "rubric"):
                        _dbg(f"  DROP [{current_key}] {s['type']} {repr(s['text'][:60])}",
                             office=office_key)
                # Neutralize the orphaned "or" separators the dropped content
                # leaves behind: _merge absorbs a bare Or/or into the following
                # rubric ("Or\nName"), which would corrupt these fixed rubrics,
                # and _group_alternatives would then build empty alternatives
                # groups from them. They separated lectionary content options
                # (doxologies, reading responses); with the content gone they
                # carry no meaning.
                kept = [s for s in kept
                        if not (s["type"] == "rubric"
                                and re.fullmatch(r'or\.?', s["text"].strip(), re.IGNORECASE))]
                segs = kept
            _dbg(f"  FLUSH {current_key!r}: {len(segs)} segs", office=office_key)
            if segs:
                sections[current_key] = _merge(segs)
        current_segs = []

    for typ, text, gap, slack, lead in filtered_lines:
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
                    current_segs.append({"type": content_type, "text": text, "gap": gap, "slack": slack, "lead": lead})
                continue
            if key is _CONTINUE:
                # Structural heading that keeps the current section active (e.g. Lord's Prayer
                # heading — the intro + prayer text must flow into litany for post-processing).
                _dbg(f"  CONTINUE-HDR {raw_disp} (stays in {current_key!r})", office=office_key)
                continue
            _dbg(f"  HEADING {raw_disp} → section {key!r}", office=office_key)
            _flush()
            current_key = key  # may be None (major section label → ignored)
            # Preserve the phos_hilaron/invitatory heading text as a "label" segment
            # so renderers can emit it as a titled section rather than bare content
            # (invitatory headings carry the psalm citation, e.g. "Invitatory Psalm:
            # Psalm 95:1–7" — see issue #1). The psalm_rubrics/reading_rubrics
            # headings are fixed ("The Psalm" / "The Reading") but equally title the
            # section their rubrics belong to (#84).
            if key in ("phos_hilaron", "invitatory", "psalm_rubrics", "reading_rubrics") and text:
                current_segs.append({"type": "label", "text": text, "gap": gap, "slack": slack, "lead": lead})
            continue

        if current_key is not None:
            _dbg(f"  [{current_key}] {typ} {repr(text[:60])}", office=office_key)
            current_segs.append({"type": typ, "text": text, "gap": gap, "slack": slack, "lead": lead})
        else:
            _dbg(f"  [NO-SECTION] {typ} {repr(text[:60])}", office=office_key)

    _flush()

    # Re-home the "{office} Prayer continues with the Reading." transition: it
    # is printed at the foot of the Psalm block but introduces the Reading, so
    # it renders with the reading rubrics, not the psalm rubrics (#84).
    if sections.get("psalm_rubrics") and sections.get("reading_rubrics"):
        pr = sections["psalm_rubrics"]
        moved = [s for s in pr
                 if s["type"] == "rubric"
                 and re.match(r'^(?:Morning|Evening) Prayer continues with the Reading\.',
                              s["text"].strip(), re.IGNORECASE)]
        if moved:
            sections["psalm_rubrics"] = [s for s in pr if s not in moved]
            rr = sections["reading_rubrics"]
            insert_at = 1 if rr and rr[0]["type"] == "label" else 0
            sections["reading_rubrics"] = rr[:insert_at] + moved + rr[insert_at:]

    # Post-process: split seasonal collects and Lord's Prayer out of litany block.
    if "litany" in sections:
        sections["litany"], sc = _split_litany_collects(sections["litany"])
        if sc:
            pre_lp, lp_segs = _split_lords_prayer(sc)
            lp_found = bool(lp_segs) and _OUR_FATHER.match(lp_segs[0]["text"].strip())
            if lp_found:
                # pre_lp[-1] is the LP intro ("Rejoicing in God's new creation…").
                # The Lord's Prayer hand-off rubric sits before it in pre_lp and
                # stays with the collects it closes (#93) — the old pipeline
                # discarded it in _split_litany_collects. The Dismissal hand-off
                # closes the prayer itself and stays as the last segment of
                # lords_prayer_intro (#93) — the old pipeline filtered every
                # "continues with…" rubric out of lp_body, which is the mechanism
                # issue #93 could not trace. Both were silent drops of printed
                # text; ADR 0013 renders what the page prints.
                sections["seasonal_collects"] = pre_lp[:-1] if len(pre_lp) > 1 else pre_lp
                sections["lords_prayer_intro"] = (pre_lp[-1:] if pre_lp else []) + lp_segs
            else:
                sections["seasonal_collects"] = sc

    # Apply alternatives grouping to all sections. psalm_rubrics/reading_rubrics
    # are exempt: their alternatives (doxologies, reading responses) dropped
    # with the lectionary content, and the rubrics that introduced them would
    # otherwise be misread as group-introducers, producing empty groups (#84).
    _NO_ALT_SECTIONS = {"litany", "lords_prayer_intro", "psalm_rubrics", "reading_rubrics"}
    for key in list(sections.keys()):
        if key not in _NO_ALT_SECTIONS:
            sections[key] = _group_alternatives(sections[key], office=office_key, section=key)
            sections[key] = _hoist_office_transition(sections[key], office_key, key)

    # BUG-29: seasonal collect leaders are prose; the PDF's column-width hard
    # wraps are typographic, not semantic. Join them. Rubric segments (bullet
    # lists) and response segments keep their lineation.
    if "seasonal_collects" in sections:
        _reflow_by_geometry(sections["seasonal_collects"], office_key,
                            "seasonal_collects", prose=True)

    # Litany is mixed verse and prose, so each break is judged on its own
    # geometry rather than section-wide (#39).
    if "litany" in sections:
        _reflow_by_geometry(sections["litany"], office_key, "litany")

    # Prose sections: wraps joined, structural breaks kept (#41).
    for key in ("dismissal", "intercessions"):
        if key in sections:
            _reflow_by_geometry(sections[key], office_key, key, prose=True)

    # The Reading/Psalm rubrics are page prose too — the PDF column-wraps them
    # mid-sentence (#84) — but the whole section survives _flush as label and
    # rubric segments, with not one leader among them, so the default type
    # filter would skip every segment and leave the forced wraps in the data.
    for key in ("psalm_rubrics", "reading_rubrics"):
        if key in sections:
            _reflow_by_geometry(sections[key], office_key, key, prose=True,
                                types=("rubric",))

    # Hymn stanza breaks come from the page's own leading, not an assumed
    # stanza length. Must run here, while break_leads is still attached.
    if "phos_hilaron" in sections:
        _insert_stanza_breaks(sections["phos_hilaron"])

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

    # Drop the geometry carried through merging. It must not reach the output,
    # and must not survive into _dedup_shared: gaps differ per form, so leaving
    # them on would stop identical blocks from comparing equal.
    def _strip_internal(segs: list) -> None:
        for seg in segs:
            seg.pop("gap", None)
            seg.pop("break_gaps", None)
            seg.pop("break_slacks", None)
            seg.pop("slack", None)
            seg.pop("break_leads", None)
            seg.pop("lead", None)
            for g in seg.get("groups", []):
                _strip_internal(g.get("segments", []))

    for segs in sections.values():
        _strip_internal(segs)

    # Build result.
    result: dict = {"title": title}
    if subtitle:
        result["subtitle"] = subtitle

    # Preserve canonical section order.
    for key in SECTION_ORDER:
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

    # Stage 1 of the offices chain. Each stage writes its own artifact and never
    # mutates a predecessor's, so an intermediate can never be mistaken for the
    # finished file — running this script alone used to leave a complete-looking
    # data/offices.json whose _shared was missing three blocks (#48).
    out_path = ROOT / ".build" / "offices.1-extract.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    from extract_office_styles import (  # noqa: PLC0415
        document_metrics,
        extract_office_typed_lines,
    )

    offices: dict[str, dict] = {}
    doc = fitz.open(pdf_path)
    # Measure the book once: line geometry is judged against the text block, not
    # against each page's widest line (#39).
    office_pages = sorted({p for _, st, en in OFFICES for p in range(st - 1, en)})
    metrics = document_metrics(doc, office_pages)
    print(f"Text measure: {{{', '.join(f'{k}: {v:.1f}pt' for k, v in sorted(metrics[0].items()))}}}, "
          f"space advance {metrics[1]:.2f}pt")
    for key, start, end in OFFICES:
        _dbg(f"\n{'='*60}\nEXTRACTING: {key} (pages {start}–{end})\n{'='*60}", office=key)
        typed_lines = extract_office_typed_lines(doc, key, start, end, metrics=metrics)
        offices[key] = extract_office(typed_lines, office_key=key)
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
    doc.close()

    offices = _dedup_shared(offices)
    offices = _normalize_whitespace(offices)
    offices = _fix_shared_affirmation(offices)
    offices = _add_reading_responses(offices)
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
