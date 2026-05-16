#!/usr/bin/env python3
"""
Convert sources/bas_short_2026.csv → data/lectionary_2026.yaml

CSV columns (0-indexed):
  0: date (YYYY-MM-DD)
  1: name (primary name, rank marker, primary colour, secondary observances)
  2: eucharist
  3: morning office
  4: evening office
  5: extra (supplementary notes; 72 entries)

Run from the repo root:
  python3 tools/convert_lectionary.py
"""

import csv
import html
import json
import re
import sys
from pathlib import Path


# ── Manual corrections ─────────────────────────────────────────────────────────
# Entries where parse_name_meta produces the wrong name or rank.

# Manual corrections for lesson citations where the CSV source has errors:
# missing semicolon separators, typos, contextual continuations, etc.
# Key: (date, office) — "morning" or "evening".
# Value: the corrected lessons list (same format as parse_office_column output).
LESSON_FIXES: dict[tuple[str, str], list] = {
    # CSV has "Zeph 3:14-20 Tit 1:1-16" — missing semicolon separator
    ("2025-12-19", "morning"): ["Zeph 3:14-20", "Tit 1:1-16"],
    # CSV has "Jer 24:-10" — typo, missing "1-"
    ("2026-03-23", "evening"): [{"citation": "Jer 24:1-10", "optional": True}, "Mk 9:30-41"],
    # CSV has "Mt (1:1-17), 3:1-6" — optional prefix merged into citation
    ("2026-04-20", "evening"): [{"citation": "Dan 4:19-27", "optional": True}, "Mt 1:1-17, 3:1-6"],
    # CSV has "32-35" without book/chapter prefix — continuation of Job 9
    ("2026-08-28", "morning"): ["Job 9:1-15", "Job 9:32-35", "Acts 10:34-48"],
    # CSV has "108:1-6, (7-13)" without "Ps" prefix
    ("2026-11-21", "morning"): ["Ps 108:1-6, (7-13)", "Mal 3:13—4:6", "Jas 5:13-20"],
}

NAME_FIXES = {
    # parse_name_meta strips the trailing "- Com" as a rank marker, losing the
    # rank indicator that belongs to John of the Cross in this combined feast.
    "2026-10-15": (
        "Teresa of Avila, Spiritual Teacher and Reformer, 1582"
        " - Com and John of the Cross, Priest, Spiritual Teacher, 1591 - Com"
    ),
}

# Days where a co-occurring Commemoration raises the rank from feria.
# Colour does not change — a Com uses the season colour.
RANK_FIXES = {
    "2026-02-27": "commemoration",
    "2026-05-12": "commemoration",
    "2026-05-27": "commemoration",
    "2026-05-30": "commemoration",
    "2026-09-19": "commemoration",
}


# ── Observances ────────────────────────────────────────────────────────────────
# Secondary liturgical labels not encoded in the primary name/rank fields.
# Derived from the secondary markers in the CSV name column.

OBSERVANCES: dict[str, list[str]] = {
    "2025-12-05": ["fast_day"],
    "2025-12-06": ["eve_of:Advent II"],
    "2025-12-12": ["fast_day"],
    "2025-12-13": ["eve_of:Advent III"],
    "2025-12-19": ["fast_day"],
    "2025-12-20": ["eve_of:Advent IV"],
    "2025-12-24": ["eve_of:Christmas"],
    "2025-12-26": ["octave_of_christmas"],
    "2025-12-27": ["eve_of:Christmas I", "octave_of_christmas"],
    "2025-12-28": ["octave_of_christmas"],
    "2025-12-29": ["octave_of_christmas"],
    "2025-12-30": ["octave_of_christmas"],
    "2025-12-31": ["eve_of:the Naming of Jesus", "octave_of_christmas"],
    "2026-01-01": ["octave_of_christmas"],
    "2026-01-03": ["eve_of:the Epiphany", "eve_of:Christmas II"],
    "2026-01-05": ["eve_of:the Epiphany"],
    "2026-01-10": ["eve_of:the Baptism of the Lord"],
    "2026-01-16": ["fast_day"],
    "2026-01-18": ["week_of_prayer_for_christian_unity"],
    "2026-01-19": ["week_of_prayer_for_christian_unity"],
    "2026-01-20": ["week_of_prayer_for_christian_unity"],
    "2026-01-21": ["week_of_prayer_for_christian_unity"],
    "2026-01-22": ["week_of_prayer_for_christian_unity"],
    "2026-01-23": ["fast_day", "week_of_prayer_for_christian_unity"],
    "2026-01-24": ["week_of_prayer_for_christian_unity"],
    "2026-01-25": ["week_of_prayer_for_christian_unity"],
    "2026-01-30": ["fast_day"],
    "2026-02-01": ["eve_of:the Presentation of the Lord"],
    "2026-02-06": ["fast_day"],
    "2026-02-13": ["fast_day"],
    "2026-02-18": ["fast_day"],
    "2026-02-19": ["fast_day"],
    "2026-02-20": ["fast_day"],
    "2026-02-21": ["fast_day", "eve_of:Lent I"],
    "2026-02-22": ["freedom_sunday"],
    "2026-02-23": ["fast_day"],
    "2026-02-24": ["fast_day"],
    "2026-02-25": ["fast_day"],
    "2026-02-26": ["fast_day"],
    "2026-02-27": ["fast_day"],
    "2026-02-28": ["fast_day", "eve_of:Lent II"],
    "2026-03-02": ["fast_day"],
    "2026-03-03": ["fast_day"],
    "2026-03-04": ["fast_day"],
    "2026-03-05": ["fast_day"],
    "2026-03-06": ["fast_day", "world_day_of_prayer"],
    "2026-03-07": ["fast_day", "eve_of:Lent III"],
    "2026-03-09": ["fast_day"],
    "2026-03-10": ["fast_day"],
    "2026-03-11": ["fast_day"],
    "2026-03-12": ["fast_day"],
    "2026-03-13": ["fast_day"],
    "2026-03-14": ["fast_day", "eve_of:Lent IV"],
    "2026-03-16": ["fast_day"],
    "2026-03-17": ["fast_day"],
    "2026-03-18": ["fast_day"],
    "2026-03-19": ["fast_day"],
    "2026-03-20": ["fast_day"],
    "2026-03-21": ["fast_day", "eve_of:Lent V"],
    "2026-03-23": ["fast_day"],
    "2026-03-24": ["fast_day", "eve_of:the Annunciation"],
    "2026-03-26": ["fast_day"],
    "2026-03-27": ["fast_day"],
    "2026-03-28": ["fast_day", "eve_of:the Sunday of the Passion: Palm Sunday"],
    "2026-03-30": ["fast_day"],
    "2026-03-31": ["fast_day"],
    "2026-04-01": ["fast_day"],
    "2026-04-02": ["fast_day"],
    "2026-04-03": ["fast_day"],
    "2026-04-04": ["fast_day", "easter_eve"],
    "2026-04-06": ["octave_of_easter"],
    "2026-04-07": ["octave_of_easter"],
    "2026-04-08": ["octave_of_easter"],
    "2026-04-09": ["octave_of_easter"],
    "2026-04-10": ["octave_of_easter"],
    "2026-04-11": ["eve_of:Easter II", "octave_of_easter"],
    "2026-04-12": ["octave_of_easter"],
    "2026-04-18": ["eve_of:Easter III"],
    "2026-04-25": ["eve_of:Easter IV"],
    "2026-04-26": ["vocations_sunday"],
    "2026-05-02": ["eve_of:Easter V"],
    "2026-05-09": ["eve_of:Easter VI"],
    "2026-05-13": ["eve_of:the Ascension"],
    "2026-05-16": [
        "eve_of:the Seventh Sunday of Easter",
        "eve_of:Ascension Sunday",
        "ascension_sunday_option",
    ],
    "2026-05-17": ["jerusalem_holy_land_sunday", "ascension_sunday_option"],
    "2026-05-18": ["journee_nationale_des_patriotes", "victoria_day"],
    "2026-05-23": ["eve_of:Pentecost"],
    "2026-05-29": ["fast_day"],
    "2026-05-30": ["eve_of:Trinity Sunday"],
    "2026-06-04": ["corpus_christi_option"],
    "2026-06-05": ["fast_day"],
    "2026-06-06": ["eve_of:Corpus Christi"],
    "2026-06-07": ["corpus_christi_option"],
    "2026-06-12": ["fast_day"],
    "2026-06-19": ["fast_day"],
    "2026-06-20": [
        "eve_of:National Indigenous Day of Prayer",
        "national_indigenous_day_of_prayer",
    ],
    "2026-06-21": ["national_indigenous_day_of_prayer"],
    "2026-06-23": ["eve_of:the Birth of Saint John the Baptist"],
    "2026-06-26": ["fast_day"],
    "2026-06-28": ["eve_of:Saint Peter and Saint Paul"],
    "2026-07-01": ["canada_day"],
    "2026-07-03": ["fast_day"],
    "2026-07-10": ["fast_day"],
    "2026-07-17": ["fast_day"],
    "2026-07-24": ["fast_day"],
    "2026-07-31": ["fast_day"],
    "2026-08-05": ["eve_of:the Transfiguration of the Lord"],
    "2026-08-07": ["fast_day"],
    "2026-08-14": ["fast_day", "eve_of:Saint Mary the Virgin"],
    "2026-08-21": ["fast_day"],
    "2026-08-28": ["fast_day"],
    "2026-09-01": ["season_of_creation"],
    "2026-09-02": ["season_of_creation"],
    "2026-09-03": ["season_of_creation"],
    "2026-09-04": ["fast_day", "season_of_creation"],
    "2026-09-05": ["season_of_creation"],
    "2026-09-06": ["season_of_creation"],
    "2026-09-07": ["season_of_creation", "labour_day"],
    "2026-09-08": ["season_of_creation"],
    "2026-09-09": ["season_of_creation"],
    "2026-09-10": ["season_of_creation"],
    "2026-09-11": ["fast_day", "season_of_creation"],
    "2026-09-12": ["season_of_creation"],
    "2026-09-13": ["eve_of:Holy Cross", "season_of_creation"],
    "2026-09-14": ["season_of_creation"],
    "2026-09-15": ["season_of_creation"],
    "2026-09-16": ["season_of_creation"],
    "2026-09-17": ["season_of_creation"],
    "2026-09-18": ["fast_day", "season_of_creation"],
    "2026-09-19": ["season_of_creation"],
    "2026-09-20": ["season_of_creation"],
    "2026-09-21": ["season_of_creation"],
    "2026-09-22": ["season_of_creation"],
    "2026-09-23": ["season_of_creation"],
    "2026-09-24": ["season_of_creation"],
    "2026-09-25": ["fast_day", "season_of_creation"],
    "2026-09-26": ["season_of_creation"],
    "2026-09-27": ["season_of_creation"],
    "2026-09-28": ["eve_of:Saint Michael and All Angels", "season_of_creation"],
    "2026-09-29": ["season_of_creation"],
    "2026-09-30": ["season_of_creation"],
    "2026-10-01": ["season_of_creation"],
    "2026-10-02": ["fast_day", "season_of_creation"],
    "2026-10-03": ["season_of_creation"],
    "2026-10-04": ["season_of_creation"],
    "2026-10-09": ["fast_day"],
    "2026-10-10": ["eve_of:Harvest Thanksgiving", "harvest_thanksgiving"],
    "2026-10-11": ["harvest_thanksgiving"],
    "2026-10-12": ["thanksgiving_day"],
    "2026-10-16": ["fast_day"],
    "2026-10-23": ["fast_day"],
    "2026-10-24": ["eve_of:Dedication Sunday", "dedication_sunday"],
    "2026-10-25": ["dedication_sunday"],
    "2026-10-30": ["fast_day"],
    "2026-11-06": ["fast_day"],
    "2026-11-07": ["eve_of:Remembrance Sunday", "remembrance_sunday"],
    "2026-11-08": ["remembrance_sunday"],
    "2026-11-13": ["fast_day"],
    "2026-11-20": ["fast_day"],
    "2026-11-21": ["eve_of:the Reign of Christ"],
    "2026-11-27": ["fast_day"],
    "2026-11-28": ["eve_of:Advent I"],
    "2026-12-04": ["fast_day"],
    "2026-12-05": ["eve_of:Advent II"],
    "2026-12-11": ["fast_day"],
    "2026-12-12": ["eve_of:Advent III"],
    "2026-12-18": ["fast_day"],
    "2026-12-19": ["eve_of:Advent IV"],
    "2026-12-24": ["eve_of:Christmas"],
    "2026-12-26": ["eve_of:Christmas I", "octave_of_christmas"],
    "2026-12-27": ["octave_of_christmas"],
    "2026-12-28": ["octave_of_christmas"],
    "2026-12-29": ["octave_of_christmas"],
    "2026-12-30": ["octave_of_christmas"],
    "2026-12-31": ["eve_of:the Naming of Jesus", "octave_of_christmas"],
}


# ── Note types ─────────────────────────────────────────────────────────────────
# The CSV extra column contains one block of text per day. The type is
# determined here rather than by content heuristics to avoid ambiguity.

NOTE_TYPES: dict[str, str] = {
    "2025-12-14": "pastoral",
    "2025-12-17": "o_antiphon",
    "2025-12-18": "o_antiphon",
    "2025-12-19": "o_antiphon",
    "2025-12-20": "o_antiphon",
    "2025-12-21": "o_antiphon",
    "2025-12-22": "o_antiphon",
    "2025-12-23": "o_antiphon",
    "2025-12-26": "pastoral",
    "2025-12-27": "precedence_rule",
    "2025-12-29": "pastoral",
    "2026-01-06": "office_note",
    "2026-01-11": "pastoral",
    "2026-01-18": "week_of_prayer",
    "2026-01-19": "week_of_prayer",
    "2026-01-20": "week_of_prayer",
    "2026-01-21": "week_of_prayer",
    "2026-01-22": "week_of_prayer",
    "2026-01-23": "week_of_prayer",
    "2026-01-24": "week_of_prayer",
    "2026-01-25": "week_of_prayer",
    "2026-02-01": "precedence_rule",
    "2026-02-08": "pastoral",
    "2026-02-17": "pastoral",
    "2026-02-22": "pastoral",
    "2026-02-25": "ember_crossref",
    "2026-02-28": "ember_crossref",
    "2026-03-06": "pastoral",
    "2026-03-15": "pastoral",
    "2026-04-01": "pastoral",
    "2026-04-05": "reconciliation_propers",
    "2026-04-25": "precedence_rule",
    "2026-05-11": "rogation_crossref",
    "2026-05-12": "rogation_crossref",
    "2026-05-13": "rogation_crossref",
    "2026-05-17": "pastoral",
    "2026-05-18": "civil_day",
    "2026-05-27": "ember_crossref",
    "2026-05-29": "ember_crossref",
    "2026-05-30": "ember_crossref",
    "2026-05-31": "precedence_rule",
    "2026-06-03": "office_note",
    "2026-06-07": "office_note",
    "2026-06-28": "precedence_rule",
    "2026-07-01": "civil_day",
    "2026-07-25": "precedence_rule",
    "2026-08-06": "reconciliation_propers",
    "2026-08-14": "pastoral",
    "2026-08-15": "precedence_rule",
    "2026-08-29": "precedence_rule",
    "2026-09-07": "civil_day",
    "2026-09-08": "pastoral",
    "2026-09-13": "precedence_rule",
    "2026-09-16": "ember_crossref",
    "2026-09-18": "ember_crossref",
    "2026-09-19": "ember_crossref",
    "2026-09-28": "pastoral",
    "2026-10-04": "pastoral",
    "2026-10-30": "pastoral",
    "2026-11-11": "civil_day",
    "2026-12-13": "pastoral",
    "2026-12-16": "ember_crossref",
    "2026-12-17": "o_antiphon",
    "2026-12-18": "o_antiphon",
    "2026-12-19": "o_antiphon",
    "2026-12-20": "o_antiphon",
    "2026-12-21": "o_antiphon",
    "2026-12-22": "o_antiphon",
    "2026-12-23": "o_antiphon",
    "2026-12-26": "pastoral",
    "2026-12-28": "pastoral",
    "2026-12-29": "pastoral",
}


# ── Text helpers ───────────────────────────────────────────────────────────────

def clean(s: str) -> str:
    """Strip HTML tags/entities and normalise whitespace."""
    s = s.replace("<br>", "\n").replace("<BR>", "\n")
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    return s.strip()


def clean_inline(s: str) -> str:
    """Strip HTML, decode entities, and collapse to a single line."""
    s = re.sub(r"<br\s*/?>", " ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    return " ".join(s.split())


def first_line(s: str) -> str:
    for line in s.split("\n"):
        if line.strip():
            return line.strip()
    return s


# ── Name / rank / colour ───────────────────────────────────────────────────────

RANK_SUFFIXES = {
    " - PF": "principal_feast",
    " - HD": "holy_day",
    " - Mem": "memorial",
    " - Com": "commemoration",
}


def parse_name_meta(raw: str):
    desc = first_line(clean(raw))
    colour = ""
    if (i := desc.rfind("(")) >= 0:
        if (j := desc.rfind(")")) > i:
            colour = desc[i + 1 : j].strip()
            desc = desc[:i].strip()
    if (i := desc.find("[")) >= 0:
        desc = desc[:i].strip()
    rank = "feria"
    for suffix, r in RANK_SUFFIXES.items():
        if desc.endswith(suffix):
            rank = r
            desc = desc[: -len(suffix)].strip()
            break
    return desc.strip(), rank, colour


# ── Season boundaries ──────────────────────────────────────────────────────────

def detect_bounds(rows) -> dict:
    bounds = {}
    advent_count = 0
    for row in rows:
        if len(row) < 2:
            continue
        date_str = row[0].strip()
        if not re.match(r"\d{4}-\d{2}-\d{2}", date_str):
            continue
        desc = first_line(clean(row[1])).lower()
        if "first sunday of advent" in desc:
            advent_count += 1
            if advent_count == 1:
                bounds["advent_i"] = date_str
            elif advent_count == 2:
                bounds["advent_ii"] = date_str
        elif "christmas" not in bounds and "birth of the lord" in desc:
            bounds["christmas"] = date_str
        elif "christmas_ii" not in bounds and "birth of the lord" in desc and "christmas" in bounds:
            bounds["christmas_ii"] = date_str
        elif "epiphany" not in bounds and "baptism of the lord" in desc:
            bounds["epiphany"] = date_str
        elif "ash_wednesday" not in bounds and "ash wednesday" in desc:
            bounds["ash_wednesday"] = date_str
        elif "palm_sunday" not in bounds and "palm sunday" in desc:
            bounds["palm_sunday"] = date_str
        elif "easter" not in bounds and (
            "easter day" in desc or "sunday of the resurrection" in desc
        ):
            bounds["easter"] = date_str
        elif "pentecost" not in bounds and "day of pentecost" in desc:
            bounds["pentecost"] = date_str
        elif "all_saints" not in bounds and "all saints" in desc:
            bounds["all_saints"] = date_str
    return bounds


# ── Psalm parsing ──────────────────────────────────────────────────────────────

def _psalm_token(token: str):
    t = token.strip()
    if not t:
        return None
    if (t.startswith("(") and t.endswith(")")) or (
        t.startswith("[") and t.endswith("]")
    ):
        return {"citation": t[1:-1], "optional": True}
    return t


def _psalm_group(s: str) -> list:
    s = s.strip()
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1]
        return [
            {"citation": t.strip(), "optional": True}
            for t in inner.split(",")
            if t.strip()
        ]
    result = []
    for tok in s.split(", "):
        p = _psalm_token(tok)
        if p is not None:
            result.append(p)
    return result


def parse_psalm_field(raw: str) -> dict:
    s = raw.strip()
    if not s.startswith("Ps "):
        return {}
    s = s[3:]

    if " or " in s:
        parts = s.split(" or ", 1)
        groups = [_psalm_group(p) for p in parts]
        return {"psalm_sets": groups}

    return {"psalms": _psalm_group(s)}


# ── Lesson parsing ─────────────────────────────────────────────────────────────

_RE_BOOK_COLON = re.compile(r'^([A-Z][a-z]*):\s*(?=\d)')
_RE_CHAPTER_DOT = re.compile(r'^([A-Z][a-z]* \d+)\.(\d+)')


def _clean_citation(s: str) -> str:
    """Fix CSV source errors in a citation string."""
    # "Mt: 22:23-33" or "Ezek:7:10-15" → "Mt 22:23-33" / "Ezek 7:10-15"
    s = _RE_BOOK_COLON.sub(r'\1 ', s)
    # "Gal 4.21-31" → "Gal 4:21-31" (period used as chapter separator)
    s = _RE_CHAPTER_DOT.sub(r'\1:\2', s)
    return s


def parse_lesson(raw: str):
    r = raw.strip()
    if not r:
        return None
    if r.startswith("(") and r.endswith(")"):
        return {"citation": _clean_citation(r[1:-1].strip()), "optional": True}
    return _clean_citation(r)


# ── Collect parsing ────────────────────────────────────────────────────────────

RE_COLL_NORM = re.compile(r"(?i)\bColl\s+")


def parse_collect(raw: str) -> str:
    return RE_COLL_NORM.sub("", raw.strip()).strip()


# ── Office parsing ─────────────────────────────────────────────────────────────

RE_MULTI = re.compile(r"(?i)two of the following (\w+) readings:\s*")
RE_IS_COLL = re.compile(r"(?i)^Coll\s+\d")


def parse_single_office(text: str) -> dict:
    text = text.strip()
    if not text:
        return {}

    office = {}

    if (i := text.find(": Ps ")) >= 0 and i < 120:
        office["label"] = text[:i].strip()
        text = text[i + 2 :].strip()

    if m := RE_MULTI.search(text):
        office["lessons_pick"] = 2
        text = RE_MULTI.sub("", text)

    psalms_found = False
    lessons = []

    for field in text.split(";"):
        field = field.strip()
        if not field:
            continue

        if RE_IS_COLL.match(field):
            office["collect"] = parse_collect(field)
            continue

        psalm_text = field
        year_note = None
        if m := re.match(r"^\(Year (\d+)\)\s*", field):
            year_note = m.group(1)
            psalm_text = field[m.end():]
        if psalm_text.startswith("Ps ") and not psalms_found:
            psalms_found = True
            parsed = parse_psalm_field(psalm_text)
            if year_note:
                parsed["year_note"] = year_note
            office.update(parsed)
            continue

        lesson = parse_lesson(field)
        if lesson is not None:
            lessons.append(lesson)

    if lessons:
        office["lessons"] = lessons

    if lessons and isinstance(lessons[0], str) and re.search(
        r"(?i)common of|as proper", lessons[0]
    ):
        office["note"] = lessons[0]
        remaining = lessons[1:]
        if remaining:
            office["lessons"] = remaining
        else:
            office.pop("lessons", None)

    return office


RE_OR_SPLIT = re.compile(r"\nOr\s*\n")


def parse_office_column(raw: str) -> dict:
    if not raw:
        return {}
    text = clean(raw)
    parts = RE_OR_SPLIT.split(text)
    primary = parse_single_office(parts[0].strip())
    if len(parts) > 1:
        alt = parse_single_office(parts[1].strip())
        if alt:
            primary["alternate"] = alt
    return primary


# ── Eucharist parsing ──────────────────────────────────────────────────────────

def parse_eucharist(raw: str) -> str:
    """Clean HTML from the eucharist column; return as a plain inline string."""
    return clean_inline(raw)


# ── Extra / notes parsing ──────────────────────────────────────────────────────

def parse_extra(raw: str, date_str: str) -> list[dict] | None:
    """
    Parse the extra column into a notes list.
    Each day has at most one note. Type is looked up from NOTE_TYPES;
    text is the HTML-cleaned content of the column.
    """
    text = clean_inline(raw)
    if not text:
        return None
    note_type = NOTE_TYPES.get(date_str, "pastoral")
    return [{"type": note_type, "text": text}]


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    root = Path(__file__).parent.parent
    csv_path = root / "sources" / "bas_short_2026.csv"
    lect_dir = root / "data" / "lectionary"
    bounds_path = root / "data" / "season_bounds.json"

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f, quoting=csv.QUOTE_MINIMAL)
        rows = list(reader)

    bounds = detect_bounds(rows)
    entries = []
    skipped = 0

    for row in rows:
        if len(row) < 5:
            skipped += 1
            continue
        date_str = row[0].strip()
        if not re.match(r"\d{4}-\d{2}-\d{2}", date_str):
            skipped += 1
            continue

        name, rank, colour = parse_name_meta(row[1])

        # Apply manual corrections.
        name = NAME_FIXES.get(date_str, name)
        rank = RANK_FIXES.get(date_str, rank)

        # Field order: date, name, rank, colour, observances, eucharist,
        #              morning, evening, notes.
        entry: dict = {
            "date": date_str,
            "name": name,
            "rank": rank,
        }
        if colour:
            entry["colour"] = colour

        obs = OBSERVANCES.get(date_str)
        if obs:
            entry["observances"] = obs

        eucharist = parse_eucharist(row[2]) if len(row) > 2 else ""
        if eucharist:
            entry["eucharist"] = eucharist

        mp = parse_office_column(row[3])
        ep = parse_office_column(row[4])

        # Apply manual lesson corrections for known CSV errors.
        for office_key, office_data in (("morning", mp), ("evening", ep)):
            fix = LESSON_FIXES.get((date_str, office_key))
            if fix is not None:
                office_data["lessons"] = fix

        if mp:
            entry["morning"] = mp
        if ep:
            entry["evening"] = ep

        extra_raw = row[5].strip() if len(row) > 5 else ""
        if extra_raw:
            notes = parse_extra(extra_raw, date_str)
            if notes:
                entry["notes"] = notes

        entries.append(entry)

    lect_dir.mkdir(parents=True, exist_ok=True)
    with open(bounds_path, "w", encoding="utf-8") as f:
        json.dump(bounds, f, ensure_ascii=False, indent=2)
    for entry in entries:
        path = lect_dir / f"{entry['date']}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(entries)} entries to {lect_dir}/")
    print(f"Wrote season bounds to {bounds_path}")
    print(f"Skipped {skipped} non-date rows")
    print(f"Season bounds: {bounds}")

    # ── Verification ──────────────────────────────────────────────────────────
    with_eucharist = sum(1 for e in entries if e.get("eucharist"))
    with_obs = sum(1 for e in entries if e.get("observances"))
    with_notes = sum(1 for e in entries if e.get("notes"))
    rank_fixed = sum(1 for e in entries if e["date"] in RANK_FIXES)
    name_fixed = sum(1 for e in entries if e["date"] in NAME_FIXES)
    print(f"  eucharist populated: {with_eucharist}/397")
    print(f"  observances:         {with_obs} entries (expected 175)")
    print(f"  notes:               {with_notes} entries (expected 72)")
    print(f"  rank fixes applied:  {rank_fixed}/5")
    print(f"  name fixes applied:  {name_fixed}/1")


if __name__ == "__main__":
    main()
