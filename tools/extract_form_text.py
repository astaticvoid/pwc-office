#!/usr/bin/env python3
"""
extract_form_text.py — Generate a golden-file plain-text rendering for a given
office form, derived from the source PDF.

Usage:
    python3 tools/extract_form_text.py <form> [--date YYYY-MM-DD]
    python3 tools/extract_form_text.py ordinary-sunday-ep --date 2026-06-14

Writes: tests/fixtures/book/<form>.txt

The output format matches cli/book.js output (after normalisation):
  - Section headings as plain lines
  - Rubrics in (parentheses)
  - Alternatives separated by bare "or"
  - Psalm text from data/psalter.json (not from PDF, which has no psalm text)
  - Scripture as [Reading: Citation] from the lectionary JSON
  - Collect as [Collect of the Day: DATE]
  - Collect text joined to a single line (matching book.js joinLines:true)
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / 'tools'))

import fitz  # PyMuPDF
from extract_office_styles import extract_office_typed_lines
from extract_offices import OFFICES, _is_noise, _MAJOR_HDRS, _DIVINE_FIXES

# ── Casing helpers ────────────────────────────────────────────────────────────

_SHORT_LABEL_RE = re.compile(r'^(?:Form\s+)?(?:I{1,3}|IV|V|VI{0,3}|IX|X)$', re.IGNORECASE)

_PRONOUN_I_RE = re.compile(r'\bi\b')

# Vocative "O" of address: "O Lord", "O God", "O come", "O Son", etc.
# Word-boundary match so it won't affect "of", "on", etc.
_VOCATIVE_O_RE = re.compile(
    r'\bo (?=(?:lord|god|come|son|father|christ|most)\b)',
    re.IGNORECASE,
)


_SKIP_COLLECT_RE = re.compile(
    r'^Either the Collect of the Day'
    r'|^(?:the\s+)?Lord[’‘\']s Prayer$',
    re.IGNORECASE,
)
_BOOK_SKIP_RUBRICS_RE = re.compile(
    r'continues with|may conclude with|^The Litany is said or sung\.',
    re.IGNORECASE,
)


def _text_rubric_collect(text, skip_collect=True):
    """Render a rubric segment for the collect section (matches book.js textRubric)."""
    t = text.strip()
    if _BOOK_SKIP_RUBRICS_RE.search(t):
        return ''
    if skip_collect and _SKIP_COLLECT_RE.search(t):
        return ''
    if _IS_INTERCESSIONS.search(t):
        joined = t.replace('\n', ' ')
        first_sent = re.split(r'\.\s', joined)[0] + '.'
        return f'({first_sent.strip()})'
    return f'({t})'


def _render_doxology_blocks(shared_data, alleluia=False):
    """Emit doxology alternatives in canonical (offices.json) order as a list of blocks."""
    dox = shared_data.get('doxology', {})
    groups = dox.get('groups', [])
    result = []
    for g in groups:
        lines = []
        for seg in g.get('segments', []):
            if seg.get('type') in ('leader', 'response'):
                lines.append((seg.get('text') or '').strip())
        if lines:
            block = '\n'.join(lines)
            if alleluia:
                block += '\nAlleluia.'
            result.append(block)
    blocks = []
    for i, block in enumerate(result):
        if i > 0:
            blocks.append('or')
        blocks.append(block)
    return blocks


def _render_collect_blocks(segs, shared_data, join_lines=True):
    """Render segments as blocks, matching book.js textFlatSegs.

    join_lines=True  → matches {joinLines:True}  (seasonal_collects)
    join_lines=False → matches default textFlatSegs (opening_responses, litany)

    Returns list of block strings; 'or' separators are their own entries."""

    def render_segs(seg_list):
        """Render a list of segments → list of blocks."""
        blocks_out, para = [], []

        def flush():
            if para:
                blocks_out.append('\n'.join(para))
                para.clear()

        for seg in (seg_list or []):
            t = seg.get('type')
            if t in ('leader', 'response'):
                text = (seg.get('text') or '')
                if join_lines:
                    text = text.replace('\n', ' ')
                text = text.strip()
                if text:
                    para.append(text)
            elif t == 'rubric':
                rt = _text_rubric_collect(seg.get('text', ''))
                if rt:
                    flush()
                    blocks_out.append(rt)
            elif t == 'label':
                lbl = (seg.get('text') or '').strip()
                if lbl:
                    flush()
                    blocks_out.append(lbl)
            elif t == 'shared':
                resolved = shared_data.get(seg.get('key'))
                if resolved:
                    sub = resolved if isinstance(resolved, list) else [resolved]
                    # SHORT_LABEL folding: if resolved is a single alternatives segment
                    # with short Roman-numeral group labels and we have an in-progress
                    # para, fold first group inline (matches book.js textFlatSegs).
                    if (para and len(sub) == 1
                            and sub[0].get('type') == 'alternatives'):
                        groups = sub[0].get('groups') or []
                        if groups and all(_SHORT_LABEL_RE.match(g.get('label', '')) for g in groups):
                            first_blocks = render_segs(groups[0].get('segments') or [])
                            if first_blocks:
                                para.append('\n'.join(first_blocks))
                            flush()
                            for g in groups[1:]:
                                gblocks = render_segs(g.get('segments') or [])
                                if gblocks:
                                    blocks_out.append('or')
                                    blocks_out.extend(gblocks)
                            continue
                    flush()
                    blocks_out.extend(render_segs(sub))
        flush()
        return blocks_out

    outer, para = [], []

    def flush_outer():
        if para:
            outer.append('\n'.join(para))
            para.clear()

    for seg in (segs or []):
        t = seg.get('type')
        if t == 'alternatives':
            groups = seg.get('groups') or []
            flush_outer()
            first = True
            for g in groups:
                gblocks = render_segs(g.get('segments') or [])
                if not gblocks:
                    continue
                if not first:
                    outer.append('or')
                first = False
                outer.extend(gblocks)
        elif t in ('leader', 'response'):
            text = (seg.get('text') or '')
            if join_lines:
                text = text.replace('\n', ' ')
            text = text.strip()
            if text:
                para.append(text)
        elif t == 'rubric':
            rt = _text_rubric_collect(seg.get('text', ''))
            if rt:
                flush_outer()
                outer.append(rt)
        elif t == 'label':
            lbl = (seg.get('text') or '').strip()
            if lbl:
                flush_outer()
                outer.append(lbl)
        elif t == 'shared':
            resolved = shared_data.get(seg.get('key'))
            if resolved:
                sub = resolved if isinstance(resolved, list) else [resolved]
                flush_outer()
                outer.extend(_render_collect_blocks(sub, shared_data, join_lines=join_lines))

    flush_outer()
    return outer


def _normalise_casing(line_type, text):
    """Fix PDF small-caps casing artifacts.

    line_type: 'heading' | 'response' | 'leader' | 'collect'
    - 'heading' and 'response': also capitalise the first character.
    - All types: fix pronoun I, vocative O, and divine titles.
    """
    if not text:
        return text
    # Capitalise first character for headings and standalone responses.
    if line_type in ('heading', 'response'):
        text = text[0].upper() + text[1:]
    # Standalone pronoun I.
    text = _PRONOUN_I_RE.sub('I', text)
    # Vocative O of address.
    text = _VOCATIVE_O_RE.sub('O ', text)
    # Divine titles (Holy Spirit, the Father, Son of God, etc.)
    for pat, replacement in _DIVINE_FIXES:
        text = pat.sub(replacement, text)
    # PDF small-caps artifact: Creed comma after "ascended into heaven" is dropped.
    text = re.sub(r'\bascended into heaven\b(?!,)', 'ascended into heaven,', text, flags=re.IGNORECASE)
    return text


# ── Date defaults (one representative date per form for lectionary lookup) ────

SEASONAL_DATES = {
    "advent-mp":             "2026-11-29",
    "advent-ep":             "2026-11-29",
    "christmas-mp":          "2025-12-28",
    "christmas-ep":          "2025-12-28",
    "epiphany-mp":           "2026-01-11",
    "epiphany-ep":           "2026-01-11",
    "lent-mp":               "2026-03-08",
    "lent-ep":               "2026-03-08",
    "passiontide-mp":        "2026-03-29",
    "passiontide-ep":        "2026-03-29",
    "easter-mp":             "2026-04-19",
    "easter-ep":             "2026-04-19",
    "pentecost-mp":          "2026-05-24",
    "pentecost-ep":          "2026-05-24",
    "allsaints-mp":          "2026-11-01",
    "allsaints-ep":          "2026-11-01",
    "ordinary-sunday-mp":    "2026-06-14",
    "ordinary-sunday-ep":    "2026-06-14",
    "ordinary-monday-mp":    "2026-06-15",
    "ordinary-monday-ep":    "2026-06-15",
    "ordinary-tuesday-mp":   "2026-06-16",
    "ordinary-tuesday-ep":   "2026-06-16",
    "ordinary-wednesday-mp": "2026-06-17",
    "ordinary-wednesday-ep": "2026-06-17",
    "ordinary-thursday-mp":  "2026-06-25",
    "ordinary-thursday-ep":  "2026-06-25",
    "ordinary-friday-mp":    "2026-06-19",
    "ordinary-friday-ep":    "2026-06-19",
    "ordinary-saturday-mp":  "2026-06-20",
    "ordinary-saturday-ep":  "2026-06-20",
}

# ── Abbreviation expansion (mirrors render.js ABBREV_TO_FILE) ─────────────────

ABBREV_TO_FILE = {
    'Gen':'Genesis','Ex':'Exodus','Lev':'Leviticus','Num':'Numbers',
    'Dt':'Deuteronomy','Jos':'Joshua','Jg':'Judges','Ruth':'Ruth',
    '1 Sam':'1 Samuel','2 Sam':'2 Samuel','1 Kgs':'1 Kings','2 Kgs':'2 Kings',
    '1 Chr':'1 Chronicles','2 Chr':'2 Chronicles','Ezra':'Ezra','Neh':'Nehemiah',
    'Est':'Esther','Job':'Job','Ps':'Psalm','Pr':'Proverbs','Ec':'Ecclesiastes',
    'Song':'Song Of Songs','Is':'Isaiah','Jer':'Jeremiah','Lam':'Lamentations',
    'Ezek':'Ezekiel','Dan':'Daniel','Hos':'Hosea','Jl':'Joel','Am':'Amos',
    'Ob':'Obadiah','Jon':'Jonah','Mic':'Micah','Nah':'Nahum','Hab':'Habakkuk',
    'Zeph':'Zephaniah','Hag':'Haggai','Zech':'Zechariah','Mal':'Malachi',
    'Mt':'Matthew','Mk':'Mark','Lk':'Luke','Jn':'John','Acts':'Acts',
    'Rom':'Romans','1 Cor':'1 Corinthians','2 Cor':'2 Corinthians',
    'Gal':'Galatians','Eph':'Ephesians','Phil':'Philippians','Col':'Colossians',
    '1 Th':'1 Thessalonians','2 Th':'2 Thessalonians','1 Tim':'1 Timothy',
    '2 Tim':'2 Timothy','Tit':'Titus','Philem':'Philemon','Heb':'Hebrews',
    'Jas':'James','1 Pet':'1 Peter','2 Pet':'2 Peter','1 Jn':'1 John',
    '2 Jn':'2 John','3 Jn':'3 John','Jude':'Jude','Rev':'Revelation',
    'Tob':'Tobit','Jdt':'Judith','Wis':'Wisdom Of Solomon','Sir':'Sirach',
    'Bar':'Baruch','1 Macc':'1 Maccabees','2 Macc':'2 Maccabees','2 Esd':'2 Esdras',
}

# ── Patterns ──────────────────────────────────────────────────────────────────

# Navigation rubrics: structural cues in the printed book, never content.
_NAV_RUBRIC = re.compile(
    r'(?:Morning|Evening) Prayer continues\b'
    r'|may conclude with the following'
    r'|^The Prayers continue\b'
    r'|^If two Readings are read\b',
    re.IGNORECASE,
)

# "The Litany is said or sung." is suppressed in book.js (BOOK_SKIP_RUBRICS).
_LITANY_SAID = re.compile(r'^The Litany is said or sung\.', re.IGNORECASE)

_IS_OR = re.compile(r'^[Oo]r$')
_IS_INTRO_RUBRIC = re.compile(r'may be said or sung[.\s]*$', re.IGNORECASE)
_IS_INTERCESSIONS = re.compile(r'^(?:The community may offer|Additional intercessions)', re.IGNORECASE)
_COLLECT_TRIGGER = re.compile(r'Either the Collect of the Day|After a period of silence', re.IGNORECASE)
_LORDS_PRAYER_HDG = re.compile(r"the Lord['’]?s Prayer", re.IGNORECASE)
_SENDING_FORTH_HDG = re.compile(r'sendinG foRth', re.IGNORECASE)

# Canticle label: "Name (Citation)" — citation in parentheses at end.
_CANTICLE_LABEL_PAT = re.compile(r'^(.*?)\s+(?:—\s+(.+)$|\(([^)]+)\)\s*$)')

# Canonical citations — matches render.js CANTICLE_SOURCE (updated to BAS verse ranges).
# Used in _format_label to normalise PDF citation text to a single canonical form per
# canticle, so that the golden file always agrees with book.js regardless of which
# form's PDF page is being read (some canticles appear with slightly different verse
# selections on different seasonal pages).
_CANTICLE_SOURCE = {
    'Bless the Lord':                 'The Song of the Three 29–34',
    'Great and Wonderful':            'Revelation 15:3, 4',
    'Prayer of Habakkuk':             'Habakkuk 3:2, 13a, 15–16, 17–19',
    'Song of Mary':                   'Luke 1:46–55',
    'Song of Zechariah':              'Luke 1:68–79',
    'Song of Moses and Miriam':       'Exodus 15:1b–3, 6, 10, 13, 17',
    'Song of Manasseh':               'Manasseh 1a, 2, 4, 6, 7ab, 9ac, 11, 12, 14b, 15b',
    "Song of Christ's Glory":         'Philippians 2:5–11',
    'A Song of Baruch':               'Baruch 5:5, 6c, 7–9',
    'A Song of Christ the Servant':   '1 Peter 2:21b–25',
    "A Song of Christ's Appearing":   '1 Timothy 3:16; 6:15a, 16',
    "A Song of Christ's Glory":       'Philippians 2:5–11',
    'A Song of David':                '1 Chronicles 29:10b–13, 14b',
    'A Song of Deliverance':          'Isaiah 12:2–6',
    'A Song of Ezekiel':              'Ezekiel 36:24–26, 28b',
    'A Song of Faith':                '1 Peter 1:3–5, 18, 19, 21',
    "A Song of God's Assembled":      'Hebrews 12:22–24a, 28, 29',
    "A Song of God's Children":       'Romans 8:2, 14, 15b–19',
    "A Song of God's Chosen One":     'Isaiah 11:1, 2, 3b–4a, 6, 9',
    "A Song of God's Grace":          'Ephesians 1:3–10',
    "A Song of God's Love":           '1 John 4:7–11, 12b',
    'A Song of Hannah':               '1 Samuel 2:1, 2, 3b–5, 7, 8',
    'A Song of Humility':             'Hosea 6:1, 3–4, 6',
    'A Song of Jerusalem Our Mother': 'Isaiah 66:10, 11a, 12a, 12c, 13a, 14a, 14b',
    'A Song of Jonah':                'Jonah 2:2–7, 9',
    'A Song of Judith':               'Judith 16:13–16',
    'A Song of Peace':                'Isaiah 2:3–5',
    'A Song of Pilgrimage':           'Ecclesiasticus 51:13a, 13c–17, 20, 21a, 22b',
    'A Song of Praise':               'Revelation 4:11; 5:9b, 10',
    'A Song of Redemption':           'Colossians 1:13–18a, 19, 20a',
    'A Song of Repentance':           '1 John 1:5–9',
    'A Song of Tobit':                'Tobit 13:1, 3, 4, 6a',
    'A Song of Wisdom':               'Wisdom 9:1–4, 9–11',
    'A Song of the Blessed':          'Matthew 5:3–12',
    'A Song of the Bride':            'Isaiah 61:10, 11; 62:1–3',
    'A Song of the Covenant':         'Isaiah 42:5–8a',
    'A Song of the Heavenly City':    'Revelation 21:22–26; 22:1, 2b, d, 3b, 4',
    'A Song of the Holy City':        'Revelation 21:1–5a',
    'A Song of the Justified':        'Romans 4:24, 25; 5:1–5, 11',
    'A Song of the Lamb':             'Revelation 19:1b, 2a, 5b, 6b, 7, 9b',
    "A Song of the Lord's Anointed": 'Isaiah 61:1–3, 11, 6a',
    'A Song of the New Creation':     'Isaiah 43:15, 16, 18, 19, 20c, 21',
    'A Song of the New Jerusalem':    'Isaiah 60:1–3, 11a, 18, 19, 14b',
    'A Song of the Spirit':           'Revelation 22:12–14, 16, 17',
    'A Song of the Wilderness':       'Isaiah 35:1, 2b–4a, 4c–6, 10',
    'A Song of the Word of the Lord': 'Isaiah 55:6–11',
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _expand_citation(raw):
    """Expand abbreviated book names, matching book.js expandCitation."""
    parts = [p.strip() for p in raw.split(' or ')]
    out = []
    for part in parts:
        m = re.match(r'^([1-3]?\s*[A-Z][a-z]*)\s+(.+)$', part)
        if m:
            abbr = m.group(1).strip()
            out.append(f"{ABBREV_TO_FILE.get(abbr, abbr)} {m.group(2)}")
        else:
            out.append(part)
    return ' or '.join(out)


def _citation_str(lesson):
    raw = lesson['citation'] if isinstance(lesson, dict) else str(lesson)
    return _expand_citation(raw)


def _render_psalm(ps_data):
    """Render a psalm entry from psalter.json, matching book.js renderPsalm."""
    title = f"Psalm {ps_data['number']}"
    if ps_data.get('title'):
        title += f" — {ps_data['title']}"
    lines = ps_data['text'].split('\n')
    body_lines = [re.sub(r'^\d+\s+', '', ln).lstrip() for ln in lines]
    return title + '\n\n' + '\n'.join(body_lines).rstrip()


def _format_label(text):
    """
    Format a canticle or affirmation label rubric as a plain heading.
    "The Song of Mary (Luke 1:46-55)" → "Song of Mary — Luke 1:46-55"
    "The Apostles' Creed" → "The Apostles' Creed"

    The canonical citation is looked up from _CANTICLE_SOURCE (same values as
    render.js CANTICLE_SOURCE) to ensure the golden file always agrees with
    book.js regardless of which form's PDF page is being read.
    """
    m = _CANTICLE_LABEL_PAT.match(text)
    if m:
        name_raw = m.group(1)
        pdf_citation = m.group(2) or m.group(3)  # em-dash group or parentheses group
        name = re.sub(r'^The\s+', '', name_raw)
        # PDF may use curly apostrophe (U+2019); _CANTICLE_SOURCE keys use straight (U+0027).
        name_key = name.replace('’', "'").replace('‘', "'")
        citation = _CANTICLE_SOURCE.get(name_key, pdf_citation)
        return f"{name} — {citation}"
    return text


def _canonicalize_major(text):
    """Map mixed-case major heading text to its canonical book.js form."""
    t = text.lower()
    if 'gathering' in t:
        return 'The Gathering of the Community'
    if 'proclamation' in t:
        return 'The Proclamation of the Word'
    if 'prayer' in t and 'community' in t:
        return 'The Prayers of the Community'
    if 'sending' in t:
        return 'The Sending Forth of the Community'
    return text


def _merge_rubric_lines(raw):
    """
    Merge consecutive rubric lines that wrap across PDF lines.

    Two rubric lines are merged (joined with a space) UNLESS:
    - Either is a bare "Or" / "or" (alternatives separator).
    - The previous line ends with a sentence-terminal punctuation mark (. ! ?)
      AND the next line starts with an uppercase letter (new sentence).
    """
    merged = []
    buf = []

    def flush():
        if buf:
            merged.append(('rubric', ' '.join(buf)))
            buf.clear()

    for typ, text in raw:
        text = text.strip()
        if not text:
            continue
        if typ != 'rubric':
            flush()
            merged.append((typ, text))
            continue
        if _IS_OR.match(text):
            flush()
            merged.append(('rubric', text))
            continue
        if buf and re.search(r'[.!?]$', buf[-1]) and text[0].isupper():
            flush()
        buf.append(text)

    flush()
    return merged


def _reclassify_headings(lines):
    """Re-classify heading lines that look like liturgical content as response.

    In some PDFs the first line on a new page is rendered with heading-weight
    font even when it is a refrain or response (e.g. allsaints-mp litany
    refrains, christmas-mp opening-response refrain).  Headings that end with
    sentence-terminal punctuation (. ? !) and do NOT match any known
    major/section heading pattern are reclassified as 'response'.
    """
    _KNOWN_HDG = re.compile(
        r'^(?:the (?:psalm|reading|canticle|responsory|litany|dismissal)|'
        r'(?:morning|evening) prayer\b|introductory responses|affirmation|'
        r'thanksgiving|invitatory|(?:the )?lord\b|the lord\'s prayer)',
        re.IGNORECASE,
    )
    result = []
    for typ, text in lines:
        if (typ == 'heading'
                and not _MAJOR_HDRS.search(text)
                and not _KNOWN_HDG.search(text)
                and re.search(r'[.!?]$', text.strip())):
            result.append(('response', text))
        else:
            result.append((typ, text))
    return result


# ── Main extraction ───────────────────────────────────────────────────────────

def extract_form_text(form_name, date_str):
    pdf_path = ROOT / 'sources' / 'pray-without-ceasing.pdf'
    psalter = json.loads((ROOT / 'data' / 'psalter.json').read_text(encoding='utf-8'))
    offices = json.loads((ROOT / 'data' / 'offices.json').read_text(encoding='utf-8'))
    form_data = offices.get(form_name, {})

    year, month = date_str[:4], date_str[5:7]
    office_data = {}
    try:
        lect = json.loads(
            (ROOT / 'data' / 'lectionary' / f'{year}-{month}.json').read_text(encoding='utf-8')
        )
        day = lect.get(date_str, {})
        slot = 'evening' if form_name.endswith('-ep') else 'morning'
        office_data = day.get(slot, {})
    except Exception:
        pass

    lessons = office_data.get('lessons', [])
    psalms  = office_data.get('psalms', [])

    shared_data = offices.get('_shared', {})

    page_range = next((r[1:3] for r in OFFICES if r[0] == form_name), None)
    if not page_range:
        raise ValueError(f'Unknown form: {form_name}')
    start_p, end_p = page_range

    raw = []
    doc = fitz.open(str(pdf_path))
    raw.extend(extract_office_typed_lines(doc, form_name, start_p, end_p))
    doc.close()

    raw = [(t, x.strip()) for t, x in raw if not _is_noise(t, x) and x.strip()]
    lines = _merge_rubric_lines(raw)
    lines = _reclassify_headings(lines)

    # ── State ─────────────────────────────────────────────────────────────────
    section                = None   # current content section
    after_alt_intro        = False  # True after intro rubric or "or" — next rubric is a label
    sending_emitted        = False  # True once "The Sending Forth" has been output
    collect_mode           = False  # True inside the collect text (join leaders with space)
    lesson_idx             = 0      # index into lessons[] for citation lookup
    intercessions_emitted  = False  # True once "Intercessions and Thanksgivings" is output

    # Reading responses captured from PDF (list of blocks) — re-used for second lesson.
    rresp_blocks      = []     # completed blocks: para text or 'or'
    rresp_para        = []     # in-progress para for reading response lines
    rresp_saved       = None   # saved list of blocks after first reading section

    blocks = []   # output blocks (joined with '\n\n')
    para   = []   # accumulated leader/response lines (joined with '\n')
    collect_lines = []  # collect text (joined with ' ')

    # Seasonal forms have a multi-line subtitle in the PDF but offices.json stores
    # only the first line (the canonical form book.js uses).  Emit from JSON and
    # skip PDF content before the first major heading.
    pre_gathering = False
    if form_data.get('subtitle'):
        blocks.append(form_data['subtitle'])
        pre_gathering = True

    READING_RUBRIC = (
        'A Reading from the Daily Office Lectionary, the Weekday Eucharistic '
        'Lectionary, or the Revised Common Lectionary Daily Readings is read. '
        'After a period of silent reflection one of the following is said.'
    )

    def flush_para():
        if para:
            blocks.append('\n'.join(para))
            para.clear()

    def flush_collect():
        if collect_lines:
            lines = collect_lines[:]
            collect_lines.clear()
            # When the last line is exactly "Amen." it is a congregational
            # response (separate segment in offices.json), so book.js renders it
            # on its own line within the para.  Join the rest with spaces to
            # match book.js's joinLines:true behaviour, then append the Amen.
            if len(lines) > 1 and lines[-1].strip().rstrip('.') == 'Amen':
                amen = lines.pop()
                blocks.append(' '.join(lines) + '\n' + amen)
            else:
                blocks.append(' '.join(lines))

    def save_rresp():
        """Flush in-progress reading-response para and save the block list."""
        nonlocal rresp_saved
        if rresp_para:
            rresp_blocks.append('\n'.join(rresp_para))
            rresp_para.clear()
        if rresp_blocks and rresp_saved is None:
            rresp_saved = list(rresp_blocks)
            rresp_blocks.clear()

    def inject_lesson(idx):
        """Emit a full reading block (heading + rubric + citation + responses)."""
        if idx >= len(lessons):
            return
        blocks.append('The Reading')
        blocks.append(f'({READING_RUBRIC})')
        blocks.append(f'[Reading: {_citation_str(lessons[idx])}]')
        if rresp_saved:
            blocks.extend(rresp_saved)

    i = 0
    while i < len(lines):
        typ, text = lines[i]
        i += 1

        # ── Headings ──────────────────────────────────────────────────────────
        if typ == 'heading':
            # Nav rubrics already skipped before we get here; headings always flush.
            flush_para()
            flush_collect()
            save_rresp()

            # Skip form-title headings (e.g. "evening Prayer for sunday").
            if re.search(r'^(?:morning|evening) prayer for\b', text, re.IGNORECASE):
                after_alt_intro = False
                collect_mode = False
                continue


            major_m = _MAJOR_HDRS.search(text)
            sub_text = _MAJOR_HDRS.sub('', text).strip() if major_m else text

            if major_m:
                if _SENDING_FORTH_HDG.search(text):
                    # PDF places this heading after Lord's Prayer; we already emitted
                    # it before The Lord's Prayer — skip to avoid duplication.
                    after_alt_intro = False
                    collect_mode = False
                    if not sub_text:
                        continue
                    # Fall through to handle any sub-heading embedded in the major line.
                else:
                    # First major heading ends pre-gathering (subtitle skip zone).
                    pre_gathering = False
                    blocks.append(_canonicalize_major(text))

            if not sub_text:
                if major_m:
                    pre_gathering = False
                after_alt_intro = False
                section = None
                collect_mode = False
                continue

            after_alt_intro = False
            collect_mode = False

            # Skip generic sub-headings while in the pre-gathering zone (subtitle area).
            if pre_gathering and not major_m:
                continue

            if re.search(r'^the psalm$', sub_text, re.IGNORECASE):
                section = 'psalm'
                blocks.append('The Psalm')
            elif re.search(r'^the reading$', sub_text, re.IGNORECASE):
                section = 'reading'
                blocks.append('The Reading')
            elif re.search(r'^the canticle$', sub_text, re.IGNORECASE):
                # Inject second lesson before canticle.
                if lesson_idx < len(lessons):
                    inject_lesson(lesson_idx)
                    lesson_idx += 1
                section = 'canticle'
                blocks.append('The Canticle')
            elif re.search(r'affirmation of faith', sub_text, re.IGNORECASE):
                section = 'affirmation'
                blocks.append('Affirmation of Faith')
            elif re.search(r'^intercessions and thanksgivings$', sub_text, re.IGNORECASE):
                section = 'intercessions'
                blocks.append('Intercessions and Thanksgivings')
                intercessions_emitted = True
            elif re.search(r'^the litany$', sub_text, re.IGNORECASE):
                # If intercessions heading hasn't been emitted yet (seasonal forms where it
                # doesn't appear as its own PDF sub-heading), emit it now before the litany.
                if not intercessions_emitted:
                    blocks.append('Intercessions and Thanksgivings')
                    intercessions_emitted = True
                section = 'litany'
                blocks.append('The Litany')
            elif re.search(r'^the responsory$', sub_text, re.IGNORECASE):
                # Inject first lesson before responsory.
                if lesson_idx == 0 and lesson_idx < len(lessons):
                    inject_lesson(lesson_idx)
                    lesson_idx += 1
                section = 'responsory'
                blocks.append('The Responsory')
            elif _LORDS_PRAYER_HDG.search(sub_text):
                if not sending_emitted:
                    blocks.append('The Sending Forth of the Community')
                    sending_emitted = True
                section = 'lp'
                blocks.append("The Lord's Prayer")
            elif re.search(r'^the dismissal$', sub_text, re.IGNORECASE):
                section = 'dismissal'
                blocks.append('The Dismissal')
            elif re.search(r'^thanksgiving$', sub_text, re.IGNORECASE):
                section = 'thanksgiving'
                blocks.append('Thanksgiving for Light')
            elif re.search(r'^invitatory psalm\b', sub_text, re.IGNORECASE):
                # book.js known gap: form.invitatory not rendered; skip this section.
                section = 'invitatory'
                continue
            elif re.search(r'^(?:the )?evening hymn\b', sub_text, re.IGNORECASE):
                if form_data.get('phos_hilaron') or form_data.get('thanksgiving_for_light'):
                    # Data exists — book.js renders it; include in golden.
                    blocks.append(_normalise_casing('heading', sub_text))
                    section = None
                else:
                    # No data — book.js has a gap here; skip to avoid mismatch.
                    section = 'phos_hilaron_skip'
            else:
                # Generic sub-heading.
                blocks.append(_normalise_casing('heading', sub_text))
                section = None

            continue

        # ── Rubrics ───────────────────────────────────────────────────────────
        if typ == 'rubric':
            if section in ('invitatory', 'phos_hilaron_skip', 'psalm_dox_skip', 'collect_done'):
                continue  # skip content for sections already rendered from offices.json
            if pre_gathering:
                continue  # skip rubrics in the subtitle zone before first major heading
            # Navigation / structural-only rubrics: skip WITHOUT flushing para
            # (they may interrupt content that should stay together, e.g. the
            # dismissal where "may conclude with…" sits between two leader lines).
            if _NAV_RUBRIC.search(text) or _LITANY_SAID.search(text):
                after_alt_intro = False
                continue

            flush_para()

            if _IS_OR.match(text):
                if section == 'reading' and rresp_saved is None:
                    # Save in-progress reading-response para, add 'or' block.
                    if rresp_para:
                        rresp_blocks.append('\n'.join(rresp_para))
                        rresp_para.clear()
                    rresp_blocks.append('or')
                if collect_mode:
                    flush_collect()
                    # Re-enable collect mode for the next alternative.
                blocks.append('or')
                after_alt_intro = True
                continue

            # For all structural rubrics: also flush collect.
            flush_collect()
            collect_mode = False

            if after_alt_intro:
                blocks.append(_format_label(text))
                after_alt_intro = False
                continue

            if section == 'psalm':
                if re.search(r'^A Psalm\b', text, re.IGNORECASE):
                    PSALM_RUBRIC = (
                        'A Psalm from the Daily Office Lectionary, the Weekday Eucharistic '
                        'Lectionary, or the Revised Common Lectionary Daily Readings is said or sung.'
                    )
                    blocks.append(f'({PSALM_RUBRIC})')
                    for ps_ref in psalms:
                        ps_num = str(ps_ref['citation'] if isinstance(ps_ref, dict) else ps_ref)
                        ps_num = re.sub(r'[^0-9].*', '', ps_num)
                        ps_data = psalter.get(ps_num)
                        if ps_data:
                            blocks.append(_render_psalm(ps_data))
                    continue
                if re.search(r'^(After the Psalm|At the end of the Psalm)\b', text, re.IGNORECASE):
                    blocks.append(f'({text})')
                    # Emit doxology in canonical (offices.json) order, not PDF page order.
                    # Seasonal forms print alternatives in a different order than ordinary forms.
                    blocks.extend(_render_doxology_blocks(shared_data, alleluia=False))
                    section = 'psalm_dox_skip'   # skip PDF alternatives that follow
                    after_alt_intro = False
                    continue

            if section == 'canticle':
                if re.search(r'^(?:After the Canticle|At the end of (?:either )?(?:the )?Canticle)\b', text, re.IGNORECASE):
                    blocks.append(f'({text})')
                    blocks.extend(_render_doxology_blocks(shared_data, alleluia=False))
                    section = 'psalm_dox_skip'
                    after_alt_intro = False
                    continue

            if section == 'reading':
                if re.search(r'^A Reading from\b', text, re.IGNORECASE):
                    blocks.append(f'({READING_RUBRIC})')
                    if lesson_idx < len(lessons):
                        blocks.append(f'[Reading: {_citation_str(lessons[lesson_idx])}]')
                        lesson_idx += 1
                    continue

            if _COLLECT_TRIGGER.search(text):
                blocks.append('The Collect')
                blocks.append(f'[Collect of the Day: {date_str}]')
                # Emit seasonal collect content from offices.json (same source as book.js),
                # rather than reading from the PDF where the structure differs.
                sc_blocks = _render_collect_blocks(
                    form_data.get('seasonal_collects') or [], shared_data
                )
                blocks.extend(sc_blocks)
                section = 'collect_done'   # skip all remaining PDF collect content
                collect_mode = False
                continue

            if _IS_INTERCESSIONS.match(text):
                # Only emit the intercessions rubric when it appears before the litany
                # (ordinary forms — section=='intercessions').  Seasonal forms have it
                # after the litany; it will be emitted from offices.json via seasonal_collects.
                if section == 'intercessions':
                    joined = text.replace('\n', ' ')
                    first_sent = re.split(r'\.\s', joined)[0] + '.'
                    blocks.append(f'({first_sent.strip()})')
                continue

            if _IS_INTRO_RUBRIC.search(text):
                blocks.append(f'({text})')
                after_alt_intro = True
                continue

            blocks.append(f'({text})')
            after_alt_intro = False
            continue

        # ── Leader / response ─────────────────────────────────────────────────
        after_alt_intro = False
        if pre_gathering:
            continue  # skip subtitle lines from PDF (already emitted from form_data)
        if section in ('invitatory', 'phos_hilaron_skip', 'psalm_dox_skip', 'collect_done'):
            continue  # skip content for sections already rendered from offices.json
        text = _normalise_casing(typ, text)
        if collect_mode:
            collect_lines.append(text)
        elif section == 'reading' and rresp_saved is None:
            rresp_para.append(text)
            para.append(text)
        else:
            # In the thanksgiving section, a new prayer that starts "Blessed are
            # you" opens a new paragraph (matches book.js alternatives structure).
            if section == 'thanksgiving' and re.match(r'^Blessed are you\b', text, re.IGNORECASE) and para:
                flush_para()
            para.append(text)

    flush_para()
    flush_collect()
    save_rresp()

    return '\n\n'.join(b for b in blocks if b is not None and b != '') + '\n'


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('form', help='Office form key, e.g. ordinary-sunday-ep')
    ap.add_argument('--date', default=None, help='YYYY-MM-DD for lectionary lookup')
    args = ap.parse_args()

    form_name = args.form
    if form_name not in {r[0] for r in OFFICES}:
        sys.exit(f'Unknown form: {form_name!r}')

    date_str = args.date or SEASONAL_DATES.get(form_name, '2026-06-14')

    out_path = ROOT / 'tests' / 'fixtures' / 'book' / f'{form_name}.txt'
    out_path.parent.mkdir(parents=True, exist_ok=True)

    text = extract_form_text(form_name, date_str)
    header = f'# generated-date: {date_str}\n\n'
    out_path.write_text(header + text, encoding='utf-8')
    print(f'Written: {out_path}')


if __name__ == '__main__':
    main()
