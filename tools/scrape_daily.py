#!/usr/bin/env python3
"""
scrape_daily.py — scrape per-day lectionary data from lectionary.anglican.ca.

The ACC website exposes a per-day portal at:
  https://lectionary.anglican.ca/?date=YYYY-MM-DD&submit=show%20new%20date

This goes back further than the annual CSVs (which only cover the current year).
Use this to populate historical data, then run convert_lectionary.py for the
current-year CSV data (which has manual corrections and observances not
available in the HTML).

HTML-scraped data is lower fidelity than CSV data — no observances, no notes,
rank is inferred. Run convert_lectionary.py after this to overwrite the months
it covers with higher-quality CSV data.

Raw HTML responses are cached in tools/.daily_cache/YYYY-MM-DD.html so the
parser can be improved without re-fetching.

Run from repo root:
  python3 tools/scrape_daily.py [options]

  --find-start          Binary-search for earliest available date; print it
  --start YYYY-MM-DD    First date to scrape (default: auto binary-search)
  --end YYYY-MM-DD      Last date to scrape (default: yesterday)
  --delay N             Seconds between HTTP requests (default: 1.0)
  --no-cache            Ignore HTML cache; always fetch from server
  --re-parse            Re-parse all cached HTML without fetching (parser fix)
  --skip-existing       Skip dates already present in data/lectionary/
  --audit               Structural quality report on data/lectionary/ JSON files
"""

import argparse
import html as html_module
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from html.parser import HTMLParser
from pathlib import Path


PORTAL_URL = "https://lectionary.anglican.ca/"
ROOT = Path(__file__).parent.parent
CACHE_DIR = Path(__file__).parent / ".daily_cache"
DATA_DIR = ROOT / "data" / "lectionary"
LOG_FILE = CACHE_DIR / "scrape.log"

WEEKDAY_NAMES = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday"}


# ── HTML fetching ─────────────────────────────────────────────────────────────

def _scrape_log(date_str: str, status: str, detail: str = "") -> None:
    """Append one line to the scrape error log."""
    import datetime as _dt
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ts = _dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    line = f"{ts}  {date_str}  {status}"
    if detail:
        line += f"  {detail}"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _request_html(d: date) -> tuple[str | None, str]:
    """
    HTTP GET for one day.
    Returns (html, 'ok'), (None, 'not_found'), or (None, '<error_code>').
    Never raises — all errors are captured in the status string.
    """
    url = f"{PORTAL_URL}?date={d}&submit=show%20new%20date"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "pwc-office-scraper/1.0 (+https://github.com/astaticvoid/pwc-office)")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
            return html, "ok"
    except urllib.error.HTTPError as e:
        if e.code in (404, 403):
            return None, "not_found"
        return None, f"http_{e.code}"
    except urllib.error.URLError as e:
        reason = str(e.reason) if hasattr(e, "reason") else str(e)
        if "timed out" in reason.lower():
            return None, "timeout"
        return None, f"network_error"


def fetch_day_html(d: date, *, delay: float = 1.0, no_cache: bool = False) -> str | None:
    """
    Return raw HTML for a day (from cache or network).
    Returns None for any failure; logs all non-200 responses and parse failures
    to tools/.daily_cache/scrape.log.
    On HTTP 429 backs off and retries up to 3 times before giving up.
    """
    cache_path = CACHE_DIR / f"{d}.html"

    if not no_cache and cache_path.exists():
        return cache_path.read_text(encoding="utf-8")

    time.sleep(delay)

    html_text: str | None = None
    for attempt in range(3):
        html_text, status = _request_html(d)
        if status == "ok":
            break
        if status == "http_429":
            wait = 60 * (2 ** attempt)  # 60s, 120s, 240s
            print(f"  {d}: throttled (429) — waiting {wait}s…", flush=True)
            _scrape_log(str(d), "http_429", f"attempt {attempt + 1}, sleeping {wait}s")
            time.sleep(wait)
        elif status == "not_found":
            # Legitimate empty date — not an error worth logging
            return None
        else:
            # Unexpected error — log it and retry once after a short wait
            _scrape_log(str(d), status)
            print(f"  {d}: {status} — retrying…", flush=True)
            time.sleep(5)
    else:
        _scrape_log(str(d), "gave_up", "3 retries exhausted")
        print(f"  {d}: gave up after 3 retries", flush=True)
        return None

    if html_text is None:
        return None
    if "Couldn't find data" in html_text or "acc_lectionary" not in html_text:
        # Server returned 200 but the page has no lectionary data
        _scrape_log(str(d), "no_data", "200 but no lectionary content")
        return None

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(html_text, encoding="utf-8")
    return html_text


# ── HTML parsing ──────────────────────────────────────────────────────────────

class _ElementExtractor(HTMLParser):
    """Collect text of the first element matching a given id attribute."""

    # Void elements never emit a closing tag — don't adjust depth for them.
    _VOID = frozenset({
        'area', 'base', 'br', 'col', 'embed', 'hr', 'img',
        'input', 'link', 'meta', 'param', 'source', 'track', 'wbr',
    })

    def __init__(self, target_id: str):
        super().__init__()
        self._target = target_id
        self._depth = 0
        self._collecting = False
        self._parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if attrs_dict.get("id") == self._target:
            self._collecting = True
            self._depth = 1
        elif self._collecting and tag not in self._VOID:
            self._depth += 1

    def handle_startendtag(self, tag, attrs):
        # Self-closing or void element (e.g. <br />) — treat as data boundary only.
        if self._collecting:
            self._parts.append(" ")

    def handle_endtag(self, tag):
        if self._collecting:
            self._depth -= 1
            if self._depth == 0:
                self._collecting = False

    def handle_data(self, data):
        if self._collecting:
            self._parts.append(data)

    def handle_entityref(self, name):
        if self._collecting:
            self._parts.append(html_module.unescape(f"&{name};"))

    def handle_charref(self, name):
        if self._collecting:
            self._parts.append(html_module.unescape(f"&#{name};"))

    @property
    def text(self) -> str:
        return " ".join(" ".join(self._parts).split()).strip()


def _extract(html_text: str, elem_id: str) -> str:
    p = _ElementExtractor(elem_id)
    p.feed(html_text)
    return p.text


# ── Office text parsing ───────────────────────────────────────────────────────

# Matches "Psalm/Psalms" or bare abbreviation "Ps" followed by whitespace.
_RE_PSALM_PREFIX = re.compile(r'^(?:Psalms?|Ps)\b\.?\s*', re.IGNORECASE)
# Matches "(Year N)" year-cycle note at the start of a segment.
_RE_YEAR_NOTE = re.compile(r'^\(Year\s+(\d+)\)\s*', re.IGNORECASE)
# Collects: "Collect 430 or FAS 359", "Coll 268", "Coll 430 or FAS 359"
_RE_COLLECT = re.compile(r'^(?:Collect|Coll\.?)\s+(.+)', re.IGNORECASE)


def _parse_psalm_token(tok: str):
    """Parse a single psalm token like "97", "[100]", "(95)"."""
    tok = tok.strip()
    optional = False
    if (tok.startswith("[") and tok.endswith("]")) or (tok.startswith("(") and tok.endswith(")")):
        tok = tok[1:-1].strip()
        optional = True
    tok = _RE_PSALM_PREFIX.sub('', tok).strip()
    if not tok:
        return None
    return {"citation": tok, "optional": True} if optional else tok


def _parse_psalms(psalm_text: str) -> list:
    """Parse "97, 99, [100]" or "Psalm 97, 99, [100]" → structured list."""
    psalm_text = _RE_PSALM_PREFIX.sub('', psalm_text.strip())
    results = []
    for tok in re.split(r',\s*', psalm_text):
        p = _parse_psalm_token(tok.strip())
        if p is not None:
            results.append(p)
    return results


def _parse_lesson(text: str):
    """Return lesson string or dict-with-optional for parenthesized entries."""
    text = text.strip()
    if text.startswith("(") and text.endswith(")"):
        inner = text[1:-1].strip()
        return {"citation": inner, "optional": True}
    return text


def parse_office_text(text: str) -> dict:
    """
    Parse the inline office text from #lectionary_MP or #lectionary_EP.

    Input examples:
      "Morning Prayer: (Year 2) Ps 146, 147; Am 1:1-5, 13—2:8; 1 Th 5:1-11; Coll 268"
      "Morning Prayer: Psalm 97, 99, [100]; Ezekiel 7:10-15, 23b-27; Collect 344"
      "Evening Prayer: Psalm 94, [95]; (1 Samuel 16:1-13a); Luke 10:1-17; Collect 344"
      "Morning Prayer: Saint Stephen: Ps 28, 30; 2 Chr 24:17-22; Acts 6:1-7; Coll 417 or FAS 229 Or Feria: Ps 145; ..."

    Returns: {psalms, year_note, lessons, collect} — omits empty fields.
    """
    text = re.sub(r'^(?:Morning Prayer|Evening Prayer|Evensong)\s*:\s*', '', text, flags=re.IGNORECASE)

    # Drop alternative readings ("Or FeastName: ...") — keep only the primary option.
    # The HTML uses uppercase "Or" for alternatives; lowercase "or" appears in collect
    # references like "Coll 280 or FAS 43", so the case distinction is reliable.
    text = re.split(r'\s+Or\s+(?=[A-Z])', text, maxsplit=1)[0]

    psalms: list = []
    lessons: list = []
    collect: str = ""
    year_note: str = ""

    for segment in text.split(";"):
        segment = segment.strip()
        if not segment:
            continue

        # Extract leading (Year N) note — may appear before "Ps" or "Psalm"
        m_year = _RE_YEAR_NOTE.match(segment)
        if m_year:
            year_note = m_year.group(1)
            segment = segment[m_year.end():].strip()

        # Strip feast-label prefix: "Saint John: Ps 97" or "Eve of Baptism: Ps 104"
        # Matches any "Label: Ps/Psalm" pattern (never a scripture ref, which has digits after the colon).
        m_feast_ps = re.match(r'^[^;:]+:\s*((?:Psalms?|Ps)\b.+)$', segment, re.IGNORECASE)
        if m_feast_ps:
            segment = m_feast_ps.group(1)

        # Strip parenthetical-label prefix: "(First Evensong of Christmas) Ps 89:1-29"
        # Older pages sometimes label the office in parens before the psalm reference.
        m_paren_ps = re.match(r'^\([^)]+\)\s+((?:Psalms?|Ps)\b.+)$', segment, re.IGNORECASE)
        if m_paren_ps:
            segment = m_paren_ps.group(1)

        # Collect reference — capture full string ("430 or FAS 359", "268")
        m_collect = _RE_COLLECT.match(segment)
        if m_collect:
            collect = m_collect.group(1).strip()
            continue

        # Psalm block: starts with "Psalm/Ps" prefix
        if _RE_PSALM_PREFIX.match(segment):
            parsed = _parse_psalms(segment)
            if parsed:
                psalms.extend(parsed)
            continue

        # Optional reading in balanced parens and no "Year" prefix (already stripped)
        if segment.startswith("(") and segment.endswith(")"):
            inner = segment[1:-1].strip()
            lessons.append({"citation": inner, "optional": True})
            continue

        # Bare psalm number (no "Psalm" prefix): digits only, no letters.
        # Excludes numbered-book refs like "3 Jn 1-15" that start with a digit.
        if (re.match(r'^\d', segment) and ":" not in segment
                and "," not in segment and not re.search(r'[a-zA-Z]', segment)):
            p = _parse_psalm_token(segment)
            if p is not None:
                psalms.append(p)
            continue

        # Everything else is a lesson citation (may contain ":" for chapter:verse)
        if segment:
            lessons.append(segment)

    result: dict = {}
    if psalms:
        result["psalms"] = psalms
    if year_note:
        result["year_note"] = year_note
    if lessons:
        result["lessons"] = lessons
    if collect:
        result["collect"] = collect
    return result


_FERIA_WORDS = {"feria"} | WEEKDAY_NAMES

_COLOUR_WORDS = frozenset({
    'white', 'red', 'violet', 'blue', 'green', 'gold', 'purple', 'rose', 'black',
})


def _looks_like_colour(s: str) -> bool:
    """True if s contains at least one recognised liturgical colour word."""
    return any(w in _COLOUR_WORDS for w in re.split(r'[\s/]+', s.lower()))

# Dash-style rank marker: " - PF", " - HD", " - Memorial", etc. (post-Advent 2019 format).
# Anchored to word boundary so " - Comment" doesn't match " - Com".
_RANK_MARKER_RE = re.compile(
    r'\s+-\s+(?P<rk>PF|Principal\s+Feast|HD|Holy\s+Day|Mem(?:orial)?|Com(?:memoration)?)\b',
    re.IGNORECASE,
)

# Paren-style rank marker: "(PF)", "(HD)", "(Mem)", "(Com)" (pre-Advent 2019 format).
_RANK_PAREN_RE = re.compile(
    r'\((?P<rk>PF|Principal\s+Feast|HD|Holy\s+Day|Mem(?:orial)?|Com(?:memoration)?)\)',
    re.IGNORECASE,
)


def _rank_from_marker(rk: str) -> str:
    r = re.sub(r'\s+', '', rk).lower()
    if r in ('pf', 'principalfeast'):
        return 'principal_feast'
    if r in ('hd', 'holyday'):
        return 'holy_day'
    if r.startswith('mem'):
        return 'memorial'
    return 'commemoration'


def _parse_title(raw: str) -> tuple[str, str, str]:
    """
    Parse ACC title text → (name, rank, colour).

    Handles abbreviated and full rank markers, co-occurring feasts (takes the
    first/primary only), [annotation] stripping, and colour extraction.

    Examples:
      "Easter Feria (White)"
      "Saint Andrew the Apostle - Holy Day (Red)"          # 2021 full form
      "Saint Andrew the Apostle - HD (Red) [transferred…]" # 2025+ abbreviated
      "Clement of Alexandria - Com (Violet or Blue) Day of discipline…"
      "The Holy Innocents - HD (Red) [transferred…] Bourgeoys - Com (Green)…"
      "Advent Feria (Violet or Blue) Day of discipline and self-denial"
    """
    s = raw.strip()

    # Find the FIRST rank marker — everything before it is the primary name.
    m_rank = _RANK_MARKER_RE.search(s)

    if m_rank:
        # Post-Advent-2019 dash format: "Name - PF (White or Gold)"
        # But the dash marker may belong to a *secondary* feast when the primary
        # has its own colour paren: "Rogation Day (Violet or White) Nightingale - Com (White)".
        # Detect this by checking for a colour paren before the rank marker.
        primary_part = s[:m_rank.start()]
        m_pre_col = re.search(r'\(([^)]+)\)', primary_part)
        if m_pre_col and _looks_like_colour(m_pre_col.group(1)):
            # Multi-feast title: primary feast has its own colour paren before
            # the secondary feast's rank marker.
            # e.g. "Rogation Day (Violet or White) Nightingale - Com (White)"
            # Parens that are NOT colours (e.g. "(Konwatsijayenni)" in a name)
            # are excluded by the _looks_like_colour guard.
            name = primary_part[:m_pre_col.start()].strip()
            colour = m_pre_col.group(1).strip()
            rank = ''  # inferred from name below
        else:
            # Single feast: rank marker belongs to this entry.
            name = primary_part.strip()
            rank = _rank_from_marker(m_rank.group('rk'))
            rest = s[m_rank.end():]
            # Colour: first (...) anywhere after the rank marker; use search to skip
            # optional [annotation] brackets like "[Proper 1]" that precede the colour.
            m_col = re.search(r'\(([^)]+)\)', rest)
            colour = m_col.group(1).strip() if m_col else ''
    else:
        m_rank_p = _RANK_PAREN_RE.search(s)
        if m_rank_p:
            # Pre-Advent-2019 paren format: "Name (PF) (White or Gold)"
            name = s[:m_rank_p.start()].strip()
            rank = _rank_from_marker(m_rank_p.group('rk'))
            rest = s[m_rank_p.end():]
            m_col = re.search(r'\(([^)]+)\)', rest)
            colour = m_col.group(1).strip() if m_col else ''
        else:
            # No rank marker — colour is the first (...) group; name is before it.
            m_col = re.search(r'\(([^)]+)\)', s)
            if m_col:
                colour = m_col.group(1).strip()
                name = s[:m_col.start()].strip()
            else:
                colour = ''
                name = s
            rank = ''

    # Strip [annotation] brackets from name (e.g. "[transferred from Nov 30]").
    name = re.sub(r'\s*\[.*?\]', '', name).strip()

    # Fallback rank inference from name text when no marker was found.
    if not rank:
        lower = name.lower()
        if 'feria' in lower or any(lower.startswith(w) for w in WEEKDAY_NAMES):
            rank = 'feria'
        elif 'sunday' in lower:
            rank = 'holy_day'
        else:
            rank = 'holy_day'

    return name, rank, colour


def parse_day_html(d: date, html_text: str) -> dict | None:
    """Parse one day's HTML into our lectionary JSON schema."""
    title_raw = _extract(html_text, "lectionary_title")
    if not title_raw:
        return None

    name, rank, colour = _parse_title(title_raw)

    entry: dict = {"date": str(d), "name": name, "rank": rank}
    if colour:
        entry["colour"] = colour

    mp_text = _extract(html_text, "lectionary_MP")
    ep_text = _extract(html_text, "lectionary_EP")
    he_text = _extract(html_text, "lectionary_HE")
    subtitle_text = _extract(html_text, "lectionary_subtitle")

    if mp_text:
        mp = parse_office_text(mp_text)
        if mp:
            entry["morning"] = mp

    if ep_text:
        ep = parse_office_text(ep_text)
        if ep:
            entry["evening"] = ep

    if he_text:
        he_clean = re.sub(r'^Holy Eucharist\s*:\s*', '', he_text, flags=re.IGNORECASE).strip()
        if he_clean:
            entry["eucharist"] = he_clean

    if subtitle_text:
        entry["notes"] = [{"type": "pastoral", "text": subtitle_text}]

    return entry


# ── Binary search for earliest available date ─────────────────────────────────

def find_start_date(*, delay: float = 1.0) -> date:
    """Binary-search for the earliest date with available data."""
    # Known bounds: 2015-01-06 returns 404; 2021-01-01 confirmed available.
    lo = date(2015, 1, 1)  # known absent
    hi = date(2021, 6, 1)  # known present

    print(f"Binary-searching for start date between {lo} and {hi}…")
    while (hi - lo).days > 1:
        mid = lo + timedelta(days=(hi - lo).days // 2)
        html_text = fetch_day_html(mid, delay=delay, no_cache=False)
        available = html_text is not None
        print(f"  {mid}: {'available' if available else 'not found'}")
        if available:
            hi = mid
        else:
            lo = mid

    return hi


# ── JSON output ───────────────────────────────────────────────────────────────

def _load_month(month_key: str) -> dict:
    path = DATA_DIR / f"{month_key}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _write_month(month_key: str, entries: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / f"{month_key}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(entries.items())), f, ensure_ascii=False, indent=2)
        f.write("\n")


# ── Quality audit ────────────────────────────────────────────────────────────

# Spot-check dates: (month-day, expected name fragment, expected colour)
_SPOT_CHECKS = [
    ("12-25", "Christmas",  "White"),
    ("01-06", "Epiphany",   "White"),
]

# Easter dates by year (Western Easter algorithm gives varying dates)
_EASTER = {
    2016: "03-27", 2017: "04-16", 2018: "04-01", 2019: "04-21",
    2020: "04-12", 2021: "04-04", 2022: "04-17", 2023: "04-09",
    2024: "03-31", 2025: "04-20", 2026: "04-05",
}


def _entry_issues(entry: dict) -> list[str]:
    """Return a list of structural problems with a parsed entry."""
    problems = []
    for office in ("morning", "evening"):
        off = entry.get(office)
        if not off:
            problems.append(f"no {office} office")
            continue
        has_psalms = bool(off.get("psalms") or off.get("psalm_sets"))
        if not has_psalms:
            problems.append(f"{office}: no psalms")
        if not off.get("lessons"):
            problems.append(f"{office}: no lessons")
    return problems


def audit_quality(start: date | None = None, end: date | None = None) -> None:
    """Print a structural quality report over data/lectionary/ JSON files."""
    json_files = sorted(DATA_DIR.glob("????-??.json")) if DATA_DIR.exists() else []
    if not json_files:
        print("No lectionary JSON files found.")
        return

    total = ok = warn = 0
    year_stats: dict[str, dict] = {}

    for jf in json_files:
        month_data = json.loads(jf.read_text(encoding="utf-8"))
        for date_str, entry in sorted(month_data.items()):
            d = date.fromisoformat(date_str)
            if start and d < start:
                continue
            if end and d > end:
                continue
            total += 1
            yr = date_str[:4]
            stats = year_stats.setdefault(yr, {"ok": 0, "warn": 0, "issues": []})
            problems = _entry_issues(entry)
            if problems:
                warn += 1
                stats["warn"] += 1
                stats["issues"].append((date_str, entry.get("name", "?"), problems))
            else:
                ok += 1
                stats["ok"] += 1

    print(f"\nAudit: {total} entries — {ok} ok, {warn} with issues")
    print()

    for yr, stats in sorted(year_stats.items()):
        total_yr = stats["ok"] + stats["warn"]
        flag = " !" if stats["warn"] else ""
        print(f"  {yr}: {total_yr} days, {stats['warn']} issues{flag}")
        for date_str, name, problems in stats["issues"]:
            print(f"    {date_str} {name}: {', '.join(problems)}")

        # Spot-checks
        for md, frag, colour in _SPOT_CHECKS:
            ds = f"{yr}-{md}"
            entry = None
            jf = DATA_DIR / f"{yr}-{md[:2]}.json"
            if jf.exists():
                entry = json.loads(jf.read_text()).get(ds)
            if entry:
                name_ok = frag.lower() in entry.get("name", "").lower()
                col_ok  = colour.lower() in entry.get("colour", "").lower()
                status  = "✓" if (name_ok and col_ok) else "MISMATCH"
                print(f"    spot {ds}: {entry['name']!r} ({entry.get('colour','?')}) {status}")

        easter_md = _EASTER.get(int(yr))
        if easter_md:
            ds = f"{yr}-{easter_md}"
            jf = DATA_DIR / f"{yr}-{easter_md[:2]}.json"
            entry = json.loads(jf.read_text()).get(ds) if jf.exists() else None
            if entry:
                name_ok = "easter" in entry.get("name", "").lower()
                col_ok  = "white" in entry.get("colour", "").lower()
                status  = "✓" if (name_ok and col_ok) else "MISMATCH"
                print(f"    spot {ds}: {entry['name']!r} ({entry.get('colour','?')}) {status}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--find-start", action="store_true",
                    help="Binary-search for earliest available date, then exit")
    ap.add_argument("--start", metavar="YYYY-MM-DD",
                    help="First date to scrape (default: auto binary-search)")
    ap.add_argument("--end", metavar="YYYY-MM-DD",
                    help="Last date to scrape (default: yesterday)")
    ap.add_argument("--delay", type=float, default=1.0, metavar="N",
                    help="Seconds between HTTP requests (default: 1.0)")
    ap.add_argument("--no-cache", action="store_true",
                    help="Ignore HTML cache; always fetch from server")
    ap.add_argument("--re-parse", action="store_true",
                    help="Re-parse cached HTML files without fetching")
    ap.add_argument("--skip-existing", action="store_true",
                    help="Skip dates already present in data/lectionary/")
    ap.add_argument("--audit", action="store_true",
                    help="Structural quality report on data/lectionary/ JSON files")
    args = ap.parse_args()

    if args.audit:
        start = date.fromisoformat(args.start) if args.start else None
        end_d = date.fromisoformat(args.end) if args.end else None
        audit_quality(start, end_d)
        return

    if args.find_start:
        start = find_start_date(delay=args.delay)
        print(f"Earliest available date: {start}")
        return

    # Determine date range
    end_date = date.fromisoformat(args.end) if args.end else date.today() - timedelta(days=1)

    if args.re_parse:
        # Parse all cached HTML files without any HTTP requests
        html_files = sorted(CACHE_DIR.glob("????-??-??.html")) if CACHE_DIR.exists() else []
        if not html_files:
            sys.exit("No cached HTML files found. Run without --re-parse first.")
        print(f"Re-parsing {len(html_files)} cached HTML file(s)…")
        month_data: dict[str, dict] = {}
        for html_path in html_files:
            d = date.fromisoformat(html_path.stem)
            if args.start and d < date.fromisoformat(args.start):
                continue
            if d > end_date:
                continue
            html_text = html_path.read_text(encoding="utf-8")
            entry = parse_day_html(d, html_text)
            if entry:
                mk = str(d)[:7]
                month_data.setdefault(mk, _load_month(mk))[str(d)] = entry
        for mk, entries in sorted(month_data.items()):
            _write_month(mk, entries)
            print(f"  wrote {mk}.json ({len(entries)} entries)")
        return

    # Determine start date
    if args.start:
        start_date = date.fromisoformat(args.start)
    else:
        start_date = find_start_date(delay=args.delay)
        print(f"Start date: {start_date}")

    if start_date > end_date:
        sys.exit(f"Start {start_date} is after end {end_date}.")

    total_days = (end_date - start_date).days + 1
    print(f"Scraping {total_days} day(s): {start_date} → {end_date}")
    print(f"Estimated time at {args.delay}s/request: {total_days * args.delay / 60:.1f} min")

    # Load existing month data to merge into
    month_data: dict[str, dict] = {}

    scraped = skipped = errors = 0
    d = start_date
    while d <= end_date:
        date_str = str(d)
        month_key = date_str[:7]

        if month_key not in month_data:
            month_data[month_key] = _load_month(month_key)

        if args.skip_existing and date_str in month_data[month_key]:
            d += timedelta(days=1)
            skipped += 1
            continue

        cached = (CACHE_DIR / f"{d}.html").exists() and not args.no_cache
        html_text = fetch_day_html(d, delay=args.delay if not cached else 0.0,
                                   no_cache=args.no_cache)

        if html_text is None:
            print(f"  {d}: no data")
            errors += 1
        else:
            entry = parse_day_html(d, html_text)
            if entry:
                month_data[month_key][date_str] = entry
                src = "cache" if cached else "fetched"
                problems = _entry_issues(entry)
                if problems:
                    _scrape_log(date_str, "parse_warn", "; ".join(problems))
                    print(f"  {d}: {entry['name'][:45]} [{src}] WARN: {', '.join(problems)}")
                else:
                    print(f"  {d}: {entry['name'][:50]} [{src}]")
                scraped += 1
            else:
                _scrape_log(date_str, "parse_failed", "no title extracted")
                print(f"  {d}: parse failed")
                errors += 1

        d += timedelta(days=1)

        # Flush month to disk when we move to the next month
        next_day = d
        if str(next_day)[:7] != month_key or d > end_date:
            if month_key in month_data:
                _write_month(month_key, month_data[month_key])
                print(f"  → wrote {month_key}.json ({len(month_data[month_key])} entries)")

    print(f"\nDone: {scraped} scraped, {skipped} skipped, {errors} errors")
    if errors:
        print(f"  Error log: {LOG_FILE}")
    print("Run 'python3 tools/convert_lectionary.py' to overlay high-quality CSV data.")


if __name__ == "__main__":
    main()
