#!/usr/bin/env python3
"""
Extract biographical notices and propers from For All The Saints (FATS) PDF.

Output: data/fats/saints.json  (gitignored — copyrighted ACC content)

Run:
    python3 tools/extract_fats.py
"""

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent
PDF_PATH = ROOT / 'sources' / 'For-All-The-Saints.pdf'
OUT_DIR = ROOT / 'data' / 'fats'
OUT_FILE = OUT_DIR / 'saints.json'

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

# Names split by a date line in the PDF: truncated_name → full_name
NAME_FIXES = {
    'The Annunciation of the Lord to the Blessed Virgin':
        'The Annunciation of the Lord to the Blessed Virgin Mary',
    'The Visit of the Blessed Virgin Mary to':
        'The Visit of the Blessed Virgin Mary to Elizabeth',
    'Founders, Benefactors and Missionaries':
        'Founders, Benefactors and Missionaries of the Anglican Church of Canada',
}

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
    non_blank = [l for l in page.split('\n') if l.strip()]
    return any(is_date_like(l) for l in non_blank[:n])


def is_bio_page(page: str) -> bool:
    return bool(page) and has_date_near_top(page) and not is_propers_page(page)


def _find_first_date_idx(lines: list[str]) -> int | None:
    """Return index of first date-like line, or None."""
    for i, line in enumerate(lines):
        if is_date_like(line):
            return i
    return None


def _extract_name(lines: list[str], first_date_idx: int) -> str:
    """
    Extract saint name from lines before the first date line.

    Stops at:
    - A blank line that follows at least one name line (name paragraph ended)
    - A date-like line (handles cases like 'Saint Stephen\\n3 August...' with no blank)
    - A rank line containing '—'

    Skips "Either X or Y may be commemorated..." note lines.
    """
    name_lines: list[str] = []
    for l in lines[:first_date_idx]:
        s = l.strip()
        if not s:
            if name_lines:
                break  # blank line after name = done
            continue
        # Skip/reset on note lines
        if re.match(r'^Either\b', s, re.IGNORECASE) or 'may be commemorated' in s.lower():
            name_lines = []
            continue
        # Stop at date-like content (e.g., "3 August (or 26 December)")
        if is_date_like(s):
            break
        # Stop at rank line (contains em-dash description)
        if '—' in s:
            break
        name_lines.append(s)
    return ' '.join(name_lines).strip()


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


def parse_bio(page: str) -> dict | None:
    """Parse a bio page. Returns dict with name, date, rank, bio or None."""
    lines = page.split('\n')

    first_date_idx = _find_first_date_idx(lines)
    if first_date_idx is None:
        return None

    raw_name = _extract_name(lines, first_date_idx)
    name = NAME_FIXES.get(raw_name, raw_name)
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
        # (has em-dash but does not END with it, so the rank word follows on same line)
        if '—' in line and not line.rstrip().endswith('—'):
            if not rank:
                m = re.search(r'—\s*(.+)$', line)
                if m:
                    rank = RANK_SUFFIX_MAP.get(m.group(1).strip().lower())
            bio_start = i + 1
            break

        # Partial rank line ending with "—" (wraps to next line) or misc descriptor
        rank_lines.append(line)

    bio_text = _extract_bio_body(lines[bio_start:])
    if not bio_text:
        return None

    return {'name': name, 'date': date, 'rank': rank, 'bio': bio_text}


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
    return text.strip()


def parse_propers(page: str) -> dict:
    """Parse a propers page. Returns dict with sentence, collect, psalm, readings."""
    # Sentence: between "Sentence" heading and "Collect" heading
    m = re.search(r'Sentence\s*\n\s*\n(.+?)(?=\n\s*Collect)', page, re.DOTALL)
    sentence = ' '.join(m.group(1).split()) if m else ''

    # Collect: between "Collect" heading and "Readings" heading
    m = re.search(r'Collect\s*\n\s*\n(.+?)(?=\n\s*Readings)', page, re.DOTALL)
    collect = m.group(1).strip() if m else ''

    # Readings section: up to "Prayer over the Gifts"
    m = re.search(r'Readings\s*\n(.+?)(?=\n\s*Prayer over the Gifts)', page, re.DOTALL)
    readings_text = m.group(1).strip() if m else ''

    psalm = ''
    readings: list[str] = []
    for line in readings_text.split('\n'):
        line = line.strip()
        if not line:
            continue
        if line.startswith('Psalm'):
            psalm = line[len('Psalm'):].strip()
        elif re.match(r'^Refrain\b', line, re.IGNORECASE):
            continue
        elif re.match(r'^Or\b', line, re.IGNORECASE):
            continue
        else:
            readings.append(line)

    return {'sentence': sentence, 'collect': collect, 'psalm': psalm, 'readings': readings}


def extract_fats(pdf_path: Path) -> dict:
    result = subprocess.run(
        ['pdftotext', str(pdf_path), '-'],
        capture_output=True, text=True, check=True,
    )
    raw_pages = result.stdout.split('\x0c')
    pages = [strip_garbage_header(p) for p in raw_pages]

    # Main section: PDF pages 37–385 (0-indexed 36–384)
    # Appendix:     PDF pages 388–392 (0-indexed 387–391)
    page_indices = list(range(36, 385)) + list(range(387, 392))

    saints: dict = {}
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
        saints[name] = {
            'date':     bio_info['date'],
            'rank':     bio_info['rank'],
            'bio':      bio_info['bio'],
            'sentence': propers_info['sentence'],
            'collect':  propers_info['collect'],
            'psalm':    propers_info['psalm'],
            'readings': propers_info['readings'],
        }

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
