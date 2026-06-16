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

import pdfplumber
from extract_offices import OFFICES, _page_styled_lines, _is_noise, _MAJOR_HDRS

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
    "ordinary-thursday-mp":  "2026-06-18",
    "ordinary-thursday-ep":  "2026-06-18",
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
_CANTICLE_LABEL_PAT = re.compile(r'^(.*?)\s+\(([^)]+)\)\s*$')


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
    """
    m = _CANTICLE_LABEL_PAT.match(text)
    if m:
        name_raw = m.group(1)
        citation = m.group(2)
        name = re.sub(r'^The\s+', '', name_raw)
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


# ── Main extraction ───────────────────────────────────────────────────────────

def extract_form_text(form_name, date_str):
    pdf_path = ROOT / 'sources' / 'pray-without-ceasing.pdf'
    psalter = json.loads((ROOT / 'data' / 'psalter.json').read_text(encoding='utf-8'))

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

    page_range = next((r[1:3] for r in OFFICES if r[0] == form_name), None)
    if not page_range:
        raise ValueError(f'Unknown form: {form_name}')
    start_p, end_p = page_range

    raw = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for pg in range(start_p - 1, end_p):
            raw.extend(_page_styled_lines(pdf.pages[pg], form_name))

    raw = [(t, x.strip()) for t, x in raw if not _is_noise(t, x) and x.strip()]
    lines = _merge_rubric_lines(raw)

    # ── State ─────────────────────────────────────────────────────────────────
    section           = None   # current content section
    after_alt_intro   = False  # True after intro rubric or "or" — next rubric is a label
    sending_emitted   = False  # True once "The Sending Forth" has been output
    collect_mode      = False  # True inside the collect text (join leaders with space)
    lesson_idx        = 0      # index into lessons[] for citation lookup

    # Reading responses captured from PDF (list of blocks) — re-used for second lesson.
    rresp_blocks      = []     # completed blocks: para text or 'or'
    rresp_para        = []     # in-progress para for reading response lines
    rresp_saved       = None   # saved list of blocks after first reading section

    blocks = []   # output blocks (joined with '\n\n')
    para   = []   # accumulated leader/response lines (joined with '\n')
    collect_lines = []  # collect text (joined with ' ')

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
            blocks.append(' '.join(collect_lines))
            collect_lines.clear()

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
                    blocks.append(_canonicalize_major(text))

            if not sub_text:
                after_alt_intro = False
                section = None
                collect_mode = False
                continue

            after_alt_intro = False
            collect_mode = False

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
            elif re.search(r'^the litany$', sub_text, re.IGNORECASE):
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
            elif re.search(r'^invitatory psalm$', sub_text, re.IGNORECASE):
                section = 'invitatory'
                blocks.append('Invitatory Psalm')
            else:
                # Generic sub-heading (e.g. "the evening hymn: ...").
                blocks.append(sub_text)
                section = None

            continue

        # ── Rubrics ───────────────────────────────────────────────────────────
        if typ == 'rubric':
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
                if re.search(r'^A Psalm from\b', text, re.IGNORECASE):
                    blocks.append(f'({text})')
                    for ps_ref in psalms:
                        ps_num = str(ps_ref['citation'] if isinstance(ps_ref, dict) else ps_ref)
                        ps_num = re.sub(r'[^0-9].*', '', ps_num)
                        ps_data = psalter.get(ps_num)
                        if ps_data:
                            blocks.append(_render_psalm(ps_data))
                    continue
                if re.search(r'^After the Psalm\b', text, re.IGNORECASE):
                    blocks.append(f'({text})')
                    after_alt_intro = True
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
                collect_mode = True
                section = 'collect'
                continue

            if _IS_INTERCESSIONS.match(text):
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
        if collect_mode:
            collect_lines.append(text)
        elif section == 'reading' and rresp_saved is None:
            rresp_para.append(text)
            para.append(text)
        else:
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
    out_path.write_text(text, encoding='utf-8')
    print(f'Written: {out_path}')


if __name__ == '__main__':
    main()
