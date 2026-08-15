#!/usr/bin/env python3
"""
Extract biographical notices and propers from For All The Saints (FATS) PDF.

Output: data/fats/saints.json  (gitignored — copyrighted ACC content)

Run:
    python3 tools/extract_fats.py
"""

import json
import re
from pathlib import Path

import fitz

ROOT = Path(__file__).parent.parent
PDF_PATH = ROOT / 'sources' / 'For-All-The-Saints.pdf'
OUT_DIR = ROOT / 'data' / 'fats'
# Stage 1: apply_corrections.py reads this and writes data/fats/saints.json.
OUT_FILE = ROOT / '.build' / 'fats-saints.1-extract.json'

MONTHS = (
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
)

# Strict date: "12 January" or "January 12" with nothing else
DATE_RE = re.compile(
    r'^(\d{1,2})\s+(' + '|'.join(MONTHS) + r')$'
    r'|^(' + '|'.join(MONTHS) + r')\s+(\d{1,2})$',
    re.IGNORECASE,
)

# Broader: also matches "3 August (or 26 December)", "January 11 (or December 28)"
# Used to detect the first date in a bio header (which may have extra text)
DATE_LIKE_RE = re.compile(
    r'^(\d{1,2})\s+(' + '|'.join(MONTHS) + r')'
    r'|^(' + '|'.join(MONTHS) + r')\s+(\d{1,2})',
    re.IGNORECASE,
)

# Rank words that appear alone on a line (abbreviations in Appendix, full words in main section)
STANDALONE_RANKS = {
    'Com': 'commemoration', 'Mem': 'memorial', 'HD': 'holy_day',
    'Commemoration': 'commemoration', 'Memorial': 'memorial',
    'Holy Day': 'holy_day', 'Principal Feast': 'principal_feast',
}

# Rank words found after "—" in a description line
RANK_SUFFIX_MAP = {
    'commemoration': 'commemoration',
    'memorial': 'memorial',
    'holy day': 'holy_day',
    'principal feast': 'principal_feast',
}

# Adjacent duplicate word from PDF line-wrap artifacts (e.g. "who who inhabited").
# NAME_FIXES (names split by a date line) and _TEXT_FIXES (merged hyphenated
# tokens: 'midVictorian', 'NinetyFive') used to live here too, targeting the
# same class of PDF artifact by exact string match. Both confirmed dead —
# zero live effect on the current dataset (disable+diff, 2026-07-26) — the
# source no longer produces the truncations/merges they were written to
# catch. Removed; see issue #13. If a real one-off editorial correction is
# needed for a saint's field, it belongs in data/corrections.json ("fats"),
# applied by apply_corrections.py after extraction, not hardcoded here.
_DUP_WORD_RE = re.compile(r'\b(\w{3,})\s+\1\b', re.IGNORECASE)


def _clean_text(text: str) -> str:
    """Fix duplicate adjacent words from PDF line-wrap artifacts."""
    return _DUP_WORD_RE.sub(r'\1', text)


# Hard line-wrap hyphenation: the justified PDF layout breaks words like
# "doctrine" across a line as "doc-\ntrine". Rejoin without the hyphen by
# default. Two cases keep it instead:
#   - the continuation starts with a capital, e.g. "mid-\nVictorian" ->
#     "mid-Victorian" — a capitalized continuation is a whole word in its
#     own right, never a mid-word fragment, so it's always a real compound.
#   - a small set of lowercase pairs are genuine compounds too (e.g.
#     "hard-\npressed" -> "hard-pressed", not "hardpressed").
# Found by diffing every wrap pair in the current PDF against an English
# wordlist (dwyl/english-words) and reviewing the non-matches in context;
# the source PDF is static, so this exception list won't grow on rerun.
_HYPHEN_WRAP_RE = re.compile(r'([A-Za-z]+)-\n([A-Za-z]+)')
_HYPHEN_KEEP = {
    ('Church', 'wide'), ('English', 'speaking'), ('Greek', 'speaking'),
    ('brother', 'in'), ('eleven', 'year'), ('fifty', 'nine'),
    ('hard', 'pressed'), ('nuclear', 'disarmament'), ('thirteenth', 'century'),
}


def _dehyphenate(text: str) -> str:
    """Rejoin words split by hard line-wrap hyphenation (see _HYPHEN_KEEP)."""
    def repl(m: re.Match) -> str:
        a, b = m.group(1), m.group(2)
        return f'{a}-{b}' if b[0].isupper() or (a, b) in _HYPHEN_KEEP else a + b
    return _HYPHEN_WRAP_RE.sub(repl, text)


# Printer artifact patterns in appendix pages
PRINTER_LINE_RE = re.compile(
    r'\.prn$'
    r'|^D:\\[A-Za-z\\]+'
    r'|^\w+day,\s+\w+\s+\d+,\s+\d{4}'  # "Friday, September 28, 2007"
)


def is_date_line(s: str) -> bool:
    """Strict: exact date match with nothing else on the line."""
    return bool(DATE_RE.match(s.strip()))


def is_date_like(s: str) -> bool:
    """Broader: line starts with a date (may have extra text like '(or 26 December)')."""
    return bool(DATE_LIKE_RE.match(s.strip()))


def normalize_date(s: str) -> str:
    """'12 January' or 'January 12' → 'January 12'.

    Also strips trailing artifacts like '(or 26 December)' and '— Memorial'.
    """
    s = s.strip()
    s = re.sub(r'\s*\(.*\)\s*$', '', s)  # strip "(or ...)"
    s = re.sub(r'\s*—.*$', '', s).strip()  # strip "— Rank" suffix
    parts = s.split()
    if len(parts) == 2 and parts[0].isdigit():
        month = parts[1].capitalize()
        if month in MONTHS:
            return f'{month} {parts[0]}'
    return s  # already "Month D" or unrecognised


def _page_text_without_margin_artifacts(page) -> str:
    """Extract page text excluding production artifacts outside the page.

    The FATS PDF contains stray 3pt fragments (drop-cap remnants of the
    running month header) positioned off-page in the left margin (bbox x0
    < 0). ``get_text()`` includes them, corrupting the first line of 119
    bios — 'mber' for Martin of Tours, 'y' for January saints. They are
    exactly the spans whose bbox starts left of the page edge, so those
    lines are dropped by exact text match. Empirically validated 2026-08
    against the current PDF: 119 pages carry off-page spans, exactly one
    artifact line dropped per page, and no legitimate line's text equals
    an artifact text (no over-drops).
    """
    text = page.get_text() or ""
    artifacts = {
        span["text"].strip()
        for block in page.get_text("dict")["blocks"]
        for line in block.get("lines", [])
        for span in line["spans"]
        if span["bbox"][0] < 0 and span["text"].strip()
    }
    if not artifacts:
        return text
    return "\n".join(
        line for line in text.split("\n") if line.strip() not in artifacts
    )


def strip_garbage_header(page: str) -> str:
    """Strip 'Color profile: Disabled / Composite Default screen' prefix lines."""
    lines = page.split('\n')
    i = 0
    while i < min(4, len(lines)):
        line = lines[i]
        if line.startswith('Color profile:') or line.startswith('Composite Default screen'):
            i += 1
        else:
            break
    return '\n'.join(lines[i:]).strip()


def is_propers_page(page: str) -> bool:
    """True if page has a standalone 'Collect' section heading."""
    return bool(re.search(r'^Collect\s*$', page, re.MULTILINE)) and 'Readings' in page


def has_date_near_top(page: str, n: int = 8) -> bool:
    non_blank = [line for line in page.split('\n') if line.strip()]
    return any(is_date_like(line) for line in non_blank[:n])


def is_bio_page(page: str) -> bool:
    return bool(page) and has_date_near_top(page) and not is_propers_page(page)


def _find_first_date_idx(lines: list[str]) -> int | None:
    """Return index of first date-like line, or None."""
    for i, line in enumerate(lines):
        if is_date_like(line):
            return i
    return None


def _restore_title_space(name: str) -> str:
    """Restore a space dropped before a title merged into the preceding word.

    The FATS PDF drops the space between a short function word and a following
    capitalized title in bold heading lines: the name line arrives as a single
    span "The Confession ofSaint Peter the Apostle". "Saint" is always a
    standalone title in this corpus, so reinserting the space before it is safe;
    a generic lower→upper insertion would split "McDonald" and is avoided.
    """
    return re.sub(r'([a-z])Saint\b', r'\1 Saint', name)


def _extract_name(lines: list[str], first_date_idx: int) -> str:
    """
    Extract saint name from lines before the first date line.

    Stops at:
    - A blank line that follows at least one name line (name paragraph ended)
    - A date-like line (handles cases like 'Saint Stephen\n3 August...' with no blank)
    - A rank line containing '—'

    Skips "Either X or Y may be commemorated..." note lines, including when the
    note wraps to a second line ("...may be commemo-\nrated on this day."); the
    continuation is not part of the name.
    """
    name_lines: list[str] = []
    in_note = False
    for line in lines[:first_date_idx]:
        s = line.strip()
        if not s:
            if name_lines:
                break  # blank line after name = done
            continue
        if in_note:
            # Continuation of a wrapped note — not the name.
            name_lines = []
            if s.endswith('.'):
                in_note = False
            continue
        # Skip/reset on note lines
        if re.match(r'^Either\b', s, re.IGNORECASE) or 'may be commemorated' in s.lower():
            name_lines = []
            in_note = not s.endswith('.')  # may wrap to a second line
            continue
        # Stop at date-like content (e.g., "3 August (or 26 December)")
        if is_date_like(s):
            break
        # Stop at rank line (contains em-dash description)
        if '—' in s:
            break
        name_lines.append(s)
    return _restore_title_space(' '.join(name_lines).strip())


def _parse_rank_from_first_date_line(line: str) -> str | None:
    """Handle 'Date — Rank' on a single line, e.g. '8 December — Memorial'."""
    m = re.search(r'—\s*(.+)$', line)
    if m:
        return RANK_SUFFIX_MAP.get(m.group(1).strip().lower())
    return None


def _parse_rank_from_lines(rank_lines: list[str]) -> str | None:
    """Parse rank from accumulated lines between first and second date."""
    rank_text = ' '.join(rank_lines).strip()
    if not rank_text:
        return None
    m = re.search(r'—\s*(.+)$', rank_text)
    if m:
        return RANK_SUFFIX_MAP.get(m.group(1).strip().lower())
    return RANK_SUFFIX_MAP.get(rank_text.lower())


def _description_from_header(lines: list[str]) -> str:
    """The saint's description from the header lines between date and bio.

    The header carries "Description, Year — Rank" (e.g. "First Archbishop of
    Canterbury, 605 — Memorial"), possibly wrapped across lines. The
    description is everything before the em-dash that introduces the rank; a
    header with no em-dash (a bare rank word, or no header at all) yields "".
    Only consulted when a name collides, where the description is the key's
    disambiguator and reproduces the lectionary's "Name, Description" form.
    """
    text = " ".join(lines).strip()
    if "—" not in text:
        return ""
    return text.split("—", 1)[0].strip()


def parse_bio(page: str) -> dict | None:
    """Parse a bio page. Returns dict with name, date, rank, bio or None."""
    lines = page.split('\n')

    first_date_idx = _find_first_date_idx(lines)
    if first_date_idx is None:
        return None

    name = _extract_name(lines, first_date_idx)
    if not name:
        return None

    first_date_line = lines[first_date_idx].strip()
    date = normalize_date(first_date_line)

    # Initial rank from "Date — Rank" pattern on the date line itself
    rank = _parse_rank_from_first_date_line(first_date_line)

    # Scan lines after first date to find rank and bio start
    rank_lines: list[str] = []
    bio_start = first_date_idx + 1

    for i in range(first_date_idx + 1, min(first_date_idx + 15, len(lines))):
        line = lines[i].strip()
        if not line:
            continue

        # Standalone rank word (abbreviation or full word alone on a line)
        if line in STANDALONE_RANKS:
            if not rank:
                rank = STANDALONE_RANKS[line]
            bio_start = i + 1
            break

        # Second strict date → bio starts after it
        if is_date_line(line):
            bio_start = i + 1
            if not rank:
                rank = _parse_rank_from_lines(rank_lines)
            break

        # Complete rank on one line: "Reformer, 1415 — Commemoration"
        # (has em-dash but does NOT end with it, so the rank word follows on same line).
        # Only a real rank suffix ends the header — prose em-dashes like Canada
        # Day's "citizens — all these" must not truncate the bio.
        if '—' in line and not line.rstrip().endswith('—'):
            m = re.search(r'—\s*(.+)$', line)
            if m:
                suffix = m.group(1).strip().lower()
                if suffix in RANK_SUFFIX_MAP:
                    if not rank:
                        rank = RANK_SUFFIX_MAP[suffix]
                    bio_start = i + 1
                    break
            rank_lines.append(line)
            continue

        # Partial rank line ending with "—" (wraps to next line) or misc descriptor
        rank_lines.append(line)

    header_lines = [ln.strip() for ln in lines[first_date_idx + 1:bio_start]
                    if ln.strip()]
    description = _description_from_header(header_lines)

    bio_text = _extract_bio_body(lines[bio_start:])
    if not bio_text:
        return None

    return {'name': name, 'date': date, 'rank': rank, 'bio': bio_text,
            'description': description}


def _extract_bio_body(lines: list[str]) -> str:
    """Clean and join bio body lines, stripping pagination artifacts."""
    result = []
    for line in lines:
        s = line.strip()
        if not s:
            result.append('')
        elif is_date_line(s):
            continue  # running header from book pagination
        elif re.match(r'^\d+$', s):
            continue  # book or PDF page number
        elif PRINTER_LINE_RE.search(s):
            continue  # FAS printer artefact
        else:
            result.append(s)
    text = '\n'.join(result)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return _clean_text(_dehyphenate(text.strip()))


# ── Readings block ────────────────────────────────────────────────────────────
#
# The propers page prints one readings set as: first reading, psalm, a "Refrain"
# heading with the refrain beneath it, an optional pointer to an alternative
# refrain, then the remaining readings. Only the citations belong in `readings`;
# the refrain is text the book prints and gets its own field (#112).

# The main section heads the refrain "Refrain"; the appendix also prints
# "Refrain:" and "Refrain Common Refrain 7: …", so the colon is optional and
# anything after the heading is the refrain itself.
_REFRAIN_HEAD_RE = re.compile(r'^Refrain\b:?\s*(.*)$', re.IGNORECASE)

# "Or v. 9 or Alleluia!", "Or CR 4" — a pointer to an alternative refrain, by
# psalm verse or common-refrain number. "Or Isaiah 52.7–10" opens with the same
# word and is an alternative *reading*, so the pointer forms are matched
# exactly; those two are the only shapes the corpus prints.
_REFRAIN_ALT_RE = re.compile(r'^Or\s+(?:v\.?\s*\d|CR\s*\d)', re.IGNORECASE)

# The same pointer where it starts on the refrain's own line rather than the
# next one ("Happy are they who have given to the poor. Or v. 9 or").
_REFRAIN_TAIL_RE = re.compile(r'\s+Or\s+(?:v\.?\s*\d|CR\s*\d).*$', re.IGNORECASE)

# A pointer that runs past the end of its line, completed by the line below
# ("… Or v. 9 or" / "Alleluia!"). Twice in the corpus, both completed by
# "Alleluia!".
_DANGLING_OR_RE = re.compile(r'\bor\s*$', re.IGNORECASE)

# A refrain runs to the first line carrying a number. Everything that can follow
# it cites something and so carries one — a psalm, a canticle, a reading, a
# pointer to another refrain — and no refrain the book prints does, wrapped ones
# ("…happy are they who" / "trust in him.") included.
_HAS_NUMBER_RE = re.compile(r'\d')

# A refrain wraps onto the next line only where it has not finished, which the
# book marks the ordinary way: no terminal punctuation. Without that floor a
# refrain swallows whatever digit-free line follows it — the "Optional Readings"
# heading, an A/B/C set marker — because citing nothing is all it takes to look
# like a continuation.
_UNFINISHED_RE = re.compile(r'[^.!?]$')

# FATS cites in the For All The Saints convention: a dot between chapter and
# verse, and an en dash for a range. The rest of the data uses the BAS
# lectionary's — a colon, an ASCII hyphen within a chapter, an em dash across
# chapters — which is what web/render.js parses. Normalising at extraction puts
# FATS on the same footing and keeps a source convention out of the renderer
# (#112). convert_lectionary.py's _clean_citation makes the same move for the
# CSV's own dot form; each stays with its extractor because the conventions
# differ, the CSV having neither en dash nor cross-chapter dot form.
_CHAPTER_DOT_RE = re.compile(r'(\d)\.(\d)')
# Which dash a range carries is not something to read meaning from: the book
# prints "Psalm 119.89-96" with an ASCII hyphen, alone among its citations. So
# both dashes are read as a range, and it is the second reference naming a
# chapter that makes it a cross-chapter one. The verse the range starts from may
# carry a part-verse letter ("6.8–7.2a" has one on the far side, "15.51c–16.2"
# on this one); the chapter it runs to never does.
_CROSS_CHAPTER_DASH_RE = re.compile(r'(?<=[\da-c])[–-](?=\d+:)')


def _normalize_citation(s: str) -> str:
    """A FATS citation punctuated the way the rest of the data punctuates one."""
    s = _CHAPTER_DOT_RE.sub(r'\1:\2', s)
    # "Acts 6:8–7:2a" crosses chapters where "51c–60" does not, and the second
    # ref naming a chapter is what tells them apart. parseRanges reads the em
    # dash as the cross-chapter marker and the hyphen as a verse range.
    s = _CROSS_CHAPTER_DASH_RE.sub('—', s)
    return s.replace('–', '-')


# ── Sentence and Collect blocks ───────────────────────────────────────────────
#
# Every section on a propers page prints its heading alone on a line with the
# body starting on the next one, so the separator between the two is a single
# newline. PyMuPDF's text layer for this PDF emits no blank line anywhere — not
# on any of the 176 propers pages — so a pattern that expects one under the
# heading matches nothing (#113). The headings are matched as whole lines, the
# way `is_propers_page` matches the "Collect" one.
_SENTENCE_RE = re.compile(r'^Sentence[ \t]*\n(.+?)^Collect[ \t]*$', re.M | re.S)
_COLLECT_RE = re.compile(r'^Collect[ \t]*\n(.+?)^Readings[ \t]*$', re.M | re.S)


def _sentence_and_ref(block: str) -> tuple[str, str]:
    """The Sentence block split into the sentence and the line attributing it.

    The book prints the attribution on its own line under the sentence, which
    wraps above it but never onto it: the last line of the block is the
    attribution on all 176 propers pages. Usually it is a citation ("Hebrews
    1.1–2"), so it ships punctuated as the rest of the data is (#112); four
    sentences are attributed to a writer or a work instead ("Lancelot Andrewes,
    1620", "The Venerable Bede"), which is why the field holds a reference
    rather than a citation and why the fats conservation chain does not walk it
    as prose — the same reason `psalm` and `readings` are not walked.
    """
    lines = [ln.strip() for ln in _dehyphenate(block).split('\n') if ln.strip()]
    if len(lines) < 2:
        # No page prints a sentence with nothing under it; attributing the only
        # line to itself would be worse than shipping it as the sentence.
        return (_clean_text(' '.join(lines)), '')
    return (_clean_text(' '.join(' '.join(lines[:-1]).split())),
            _normalize_citation(lines[-1]))


def parse_propers(page: str) -> dict:
    """Parse a propers page. Returns dict with sentence, sentence_ref, collect,
    psalm, refrain, readings."""
    m = _SENTENCE_RE.search(page)
    sentence, sentence_ref = _sentence_and_ref(m.group(1)) if m else ('', '')

    # The collect is verse-set — one clause to a line — and `.collect-text`
    # renders it `white-space: pre-wrap`, so the line breaks are kept.
    m = _COLLECT_RE.search(page)
    collect = _clean_text('\n'.join(
        ln.strip() for ln in _dehyphenate(m.group(1)).split('\n') if ln.strip()
    )) if m else ''

    # Readings section: up to "Prayer over the Gifts"
    m = re.search(r'Readings\s*\n(.+?)(?=\n\s*Prayer over the Gifts)', page, re.DOTALL)
    readings_text = m.group(1).strip() if m else ''

    psalm = ''
    readings: list[str] = []
    refrain_lines: list[str] = []
    in_refrain = False   # inside the refrain the heading above introduced
    alt_wraps = False    # the previous line's pointer runs onto this one

    for line in readings_text.split('\n'):
        line = line.strip()
        if not line:
            continue

        if alt_wraps:
            alt_wraps = False
            continue

        head = _REFRAIN_HEAD_RE.match(line)
        if head:
            # The appendix prints the refrain on the heading line itself
            # ("Refrain Common Refrain 7: Behold, I come to do your will, O
            # God."); the main section puts it on the line below.
            inline = head.group(1).strip()
            refrain_lines = [inline] if inline else []
            in_refrain = not inline
            continue

        if in_refrain:
            body = _REFRAIN_TAIL_RE.sub('', line).strip()
            tailed = body != line
            # The line straight after the heading is the refrain whatever it
            # looks like. A later one continues it only while the refrain is
            # unfinished and the line cites nothing — "As above" finishes
            # without terminal punctuation, and the pointer under it carries the
            # number that stops it being read as the rest of a sentence.
            if (not refrain_lines
                    or (_UNFINISHED_RE.search(refrain_lines[-1])
                        and not _HAS_NUMBER_RE.search(body))):
                if body:
                    refrain_lines.append(body)
                in_refrain = not tailed
                alt_wraps = tailed and bool(_DANGLING_OR_RE.search(line))
                continue
            in_refrain = False

        if _REFRAIN_ALT_RE.match(line):
            alt_wraps = bool(_DANGLING_OR_RE.search(line))
            continue
        if line.startswith('Psalm'):
            psalm = _normalize_citation(line[len('Psalm'):].strip())
        elif _HAS_NUMBER_RE.search(line):
            readings.append(_normalize_citation(line))
        # What is left names no chapter or verse and so cites nothing: the
        # "Optional Readings" heading, and the A/B/C letters marking All Saints'
        # three sets. The sets are flattened into one list either way — a bare
        # letter in a list of citations records neither the grouping nor a
        # reading.

    # A page printing several sets (All Saints A/B/C, Christmas) collapses to
    # one psalm and one refrain, both from the last set, so the two still name
    # the same psalm as each other.
    return {'sentence': sentence, 'sentence_ref': sentence_ref,
            'collect': collect, 'psalm': psalm,
            'refrain': ' '.join(refrain_lines), 'readings': readings}


def _fats_keys(entries: list[tuple[str, str, str]]) -> list[str]:
    """Unique key per saint, disambiguating name collisions with the description.

    FATS prints distinct saints under the same heading (the two Augustines, 26
    May and 28 August), so a bare name is not a unique key. A non-colliding
    name keys on itself; a colliding one keys on "name, description" (the
    description line the book prints, which the lectionary reproduces exactly),
    or "name (date)" when the book prints no description. `entries` is (name,
    description, date) in extraction order; the returned keys align one-to-one.
    """
    counts: dict[str, int] = {}
    for name, _desc, _date in entries:
        counts[name] = counts.get(name, 0) + 1
    keys = []
    for name, description, date in entries:
        if counts[name] == 1:
            keys.append(name)
        elif description:
            keys.append(f"{name}, {description}")
        else:
            keys.append(f"{name} ({date})")
    return keys


def extract_fats(pdf_path: Path) -> dict:
    with fitz.open(pdf_path) as pdf:
        raw_pages = [_page_text_without_margin_artifacts(page) for page in pdf]
    pages = [strip_garbage_header(p) for p in raw_pages]

    # Main section: PDF pages 37–385 (0-indexed 36–384)
    # Appendix:     PDF pages 388–392 (0-indexed 387–391)
    page_indices = list(range(36, 385)) + list(range(387, 392))

    entries: list[tuple[str, str, dict]] = []
    i = 0
    while i < len(page_indices):
        pi = page_indices[i]
        page = pages[pi]

        if not is_bio_page(page):
            i += 1
            continue

        bio_info = parse_bio(page)
        if not bio_info:
            i += 1
            continue

        i += 1

        # Collect continuation pages (e.g., Christmas Day bio spans 2 PDF pages)
        while i < len(page_indices):
            npi = page_indices[i]
            np_ = pages[npi]
            if is_propers_page(np_) or is_bio_page(np_) or not np_:
                break
            extra = _extract_bio_body(np_.split('\n'))
            if extra:
                bio_info['bio'] = (bio_info['bio'] + '\n\n' + extra).strip()
            i += 1

        # Need a propers page
        if i >= len(page_indices) or not is_propers_page(pages[page_indices[i]]):
            continue

        propers_info = parse_propers(pages[page_indices[i]])
        i += 1

        # Skip additional propers variants (e.g., Christmas "At Midnight" / "During the Day")
        while (i < len(page_indices)
               and is_propers_page(pages[page_indices[i]])
               and not is_bio_page(pages[page_indices[i]])):
            i += 1

        name = bio_info['name']
        entries.append((name, bio_info['description'], {
            'date':     bio_info['date'],
            'rank':     bio_info['rank'],
            'bio':      bio_info['bio'],
            'sentence': propers_info['sentence'],
            'sentence_ref': propers_info['sentence_ref'],
            'collect':  propers_info['collect'],
            'psalm':    propers_info['psalm'],
            'refrain':  propers_info['refrain'],
            'readings': propers_info['readings'],
        }))

    saints: dict = {}
    keys = _fats_keys([(n, d, data['date']) for n, d, data in entries])
    for key, (_name, _desc, data) in zip(keys, entries):
        saints[key] = data
    return saints


def main() -> int:
    if not PDF_PATH.exists():
        print(f'ERROR: {PDF_PATH} not found. Run: make fetch-sources')
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    saints = extract_fats(PDF_PATH)

    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(saints, f, ensure_ascii=False, indent=2)

    print(f'Extracted {len(saints)} saints → {OUT_FILE}')

    spot_checks = [
        'John Horden',
        'Canada Day',
        'The Naming of Jesus',
        'The Epiphany of the Lord',
        'The Holy Innocents',
        'Basil the Great and Gregory of Nazianzus',
        'Florence Li Tim-Oi',
        'Mother Emily Ayckbowm',
        'The Birth of the Lord',
        'Thomas Becket',
        'Hannah Grier Coome',
        'Charles Henry Brent',
        'Saint Stephen',
        'The Conception of the Blessed Virgin Mary',
    ]
    for name in spot_checks:
        if name in saints:
            s = saints[name]
            bio_words = len(s['bio'].split())
            collect_words = len(s['collect'].split())
            print(f'  ✓ {name}: {s["date"]}, rank={s["rank"]}, '
                  f'bio={bio_words}w, collect={collect_words}w, psalm={s["psalm"]}')
        else:
            print(f'  ✗ {name}: NOT FOUND')

    no_rank = [n for n, s in saints.items() if s['rank'] is None]
    print(f'\nSaints with no rank ({len(no_rank)}):')
    for n in no_rank:
        print(f'  {n}: {saints[n]["date"]}')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
