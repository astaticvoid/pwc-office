#!/usr/bin/env python3
"""
Convert sources/bas_short_*.csv → data/lectionary/YYYY-MM.json

Reads all bas_short_YYYY.csv files found in sources/ (or those given via
--csv), merges rows by date (later file wins on overlap), and writes one
JSON file per YYYY-MM. Place bas_short_YYYY.csv files in sources/ before
running this tool. When ACC provides a new year's CSV, add it there.

CSV columns (0-indexed):
  0: date (YYYY-MM-DD)
  1: name (primary name, rank marker, primary colour, secondary observances)
  2: eucharist
  3: morning office
  4: evening office
  5: extra (supplementary notes)

Run from the repo root:
  python3 tools/convert_lectionary.py [--csv PATH ...] [--accept]

  --csv PATH  One or more CSV files (default: sources/bas_short_*.csv)
  --accept    Update tools/manifest.json with current output hashes.
"""

import argparse
import csv
import datetime
import difflib
import html
import json
import re
import sys
from pathlib import Path

from extract_lib import check_manifest

# One-off corrections for lesson citations, names, ranks, colours, and notes
# where the CSV source has errors (missing separators, typos, mis-parsed
# markers) used to be hardcoded dicts here (LESSON_FIXES, NAME_FIXES,
# RANK_FIXES, COLOUR_FIXES, CLEAR_NOTES). They now live in
# data/corrections.json ("lectionary_lessons"/"lectionary_names"/
# "lectionary_ranks"/"lectionary_colours"/"lectionary_notes"), applied by
# apply_corrections.py after this script runs — the same mechanism used for
# office text, psalter, and FATS corrections. This extractor only parses the
# CSV; it no longer patches its own output. See issue #13 and ADR 0005.
# (NOTE_TYPES below is not migrated: it is substantive project-authored
# classification data, not a correction of a wrong value — there's no "old"
# the CSV got wrong to record provenance against. OBSERVANCES was the same
# until ADR 0017 replaced its hand-transcribed per-date dict with real
# extraction from the CSV name column, below.)


# ── Observances ────────────────────────────────────────────────────────────────
# Secondary liturgical labels not encoded in the primary name/rank fields.
# ADR 0017: these used to be a hand-transcribed per-date dict (175 entries);
# they are now extracted from the CSV name column by the classifier in the
# "Observance classification" section below. The tables here are the ~30
# general rules the per-date facts collapse into.

# phrase → tag substring map, matched against lowercased lines. "Eve of …"
# lines are classified by RE_EVE_OF before this table is consulted — some
# phrases here ("ascension sunday", "harvest thanksgiving", …) also appear
# inside eve lines and must not steal them.
OBSERVANCE_PHRASES: dict[str, str] = {
    "day of discipline and self-denial": "fast_day",
    "within the octave of christmas": "octave_of_christmas",
    "within the octave of easter": "octave_of_easter",
    "week of prayer for christian unity": "week_of_prayer_for_christian_unity",
    "season of creation": "season_of_creation",
    "freedom sunday": "freedom_sunday",
    "world day of prayer": "world_day_of_prayer",
    "vocations sunday": "vocations_sunday",
    "jerusalem and the holy land sunday": "jerusalem_holy_land_sunday",
    "journée nationale des patriotes": "journee_nationale_des_patriotes",
    "victoria day": "victoria_day",
    "easter eve": "easter_eve",
    "corpus christi": "corpus_christi_option",
    "ascension sunday": "ascension_sunday_option",
    "national indigenous day of prayer": "national_indigenous_day_of_prayer",
    "canada day": "canada_day",
    "labour day": "labour_day",
    "harvest thanksgiving": "harvest_thanksgiving",
    "thanksgiving day": "thanksgiving_day",
    "dedication sunday": "dedication_sunday",
    "remembrance sunday": "remembrance_sunday",
    # The three civil markers the original dict left out. They are structurally
    # identical to the four tagged above (Victoria/Canada/Labour/Thanksgiving
    # Day) — same shape, same source; their absence was transcription, not
    # decision. Completing the vocabulary against the CSV (ADR 0017).
    "remembrance day": "remembrance_day",
    "new year's day": "new_year_day",
    "accession day": "accession_day",
}

# Feast names whose English liturgical usage prefixes the definite article to
# the eve target ("eve_of:the Epiphany", never "eve_of:Epiphany"). The CSV's
# own capitalization is not a trustworthy signal for this (it capitalizes
# "the" in "Eve of the Epiphany" and omits it in "Eve of Advent II"), so the
# convention is encoded here — deliberately independent of the outgoing
# per-date dict, so the replacement does not quietly depend on the thing it
# replaces (ADR 0017).
EVE_THE_ARTICLE = frozenset({
    "naming of jesus",
    "epiphany",
    "baptism of the lord",
    "presentation of the lord",
    "annunciation",
    "sunday of the passion: palm sunday",
    "ascension",
    "seventh sunday of easter",
    "birth of saint john the baptist",
    "transfiguration of the lord",
    "reign of christ",
})

# "Eve of X" lines whose X is deliberately not an observance. "Eve of Sunday"
# sits on most Saturdays — a plain eve, not a secondary fact.
EVE_EXCLUDED_TARGETS = frozenset({"sunday"})

# Eve lines that also carry a same-date bare tag alongside the eve. The CSV
# wording alone cannot decide this: two structurally identical "[if also
# celebrated on Sunday]" eve lines get different treatment in the source data
# (Eve of Corpus Christi carries no companion; Eve of Ascension Sunday does).
# Explicit, commented, hand-maintained judgment calls (ADR 0017 point 5),
# keyed on the article-stripped, lowercased eve target.
EVE_COMPANION_TAGS: dict[str, str] = {
    "ascension sunday": "ascension_sunday_option",
    "national indigenous day of prayer": "national_indigenous_day_of_prayer",
    "harvest thanksgiving": "harvest_thanksgiving",
    "dedication sunday": "dedication_sunday",
    "remembrance sunday": "remembrance_sunday",
}

# The complete expected "Eve of X" target vocabulary (article-stripped,
# lowercased). A target outside this set means ACC rephrased an eve marker —
# the classifier warns rather than silently dropping it (ADR 0017 negative
# consequence; the same drift guard detect_bounds() applies to season
# boundaries).
KNOWN_EVE_TARGETS = (
    EVE_THE_ARTICLE
    | EVE_EXCLUDED_TARGETS
    | frozenset({
        "advent i", "advent ii", "advent iii", "advent iv",
        "christmas", "christmas i", "christmas ii",
        "lent i", "lent ii", "lent iii", "lent iv", "lent v",
        "easter ii", "easter iii", "easter iv", "easter v", "easter vi",
        "pentecost", "trinity sunday", "corpus christi", "ascension sunday",
        "national indigenous day of prayer",
        "saint peter and saint paul", "saint mary the virgin",
        "saint michael and all angels", "holy cross",
        "harvest thanksgiving", "dedication sunday", "remembrance sunday",
        "all saints' day",
    })
)

# Wording-drift guard for the phrase table (ADR 0017 negative consequence):
# an unmatched line within this SequenceMatcher ratio of a known phrase is
# warned about rather than silently dropped. Calibrated so no legitimate
# non-observance line in the current CSV reaches it (see
# tools/tests/test_convert_lectionary.py).
OBSERVANCE_FUZZY_RATIO = 0.72



# ── Note types ─────────────────────────────────────────────────────────────────
# The CSV extra column contains one block of text per day. The type is
# determined here rather than by content heuristics to avoid ambiguity.
#
# A string types the whole cell as one note. A list splits the cell on its <br>
# runs and types each segment in order — some cells carry two or three notes of
# different kinds, and typing the cell as a whole let one kind decide the fate
# of another (2026-06-28's sourcing note was suppressed because it shared a
# cell with a precedence rule). The list length must equal the segment count;
# parse_extra fails loudly when ACC re-splits a cell, since a silent
# off-by-one would retype every note after the change.
#
# `source_note` is the calendar compiler's own apparatus — where a day's
# propers came from, which of two lectionary options was taken, how two
# sources package the same commemoration. It explains a decision already
# applied to the data; the reader is not being asked to do anything with it.
# It is not `pastoral`, which is a custom addressed to whoever is praying
# (rose vestments, pancakes, blessing the animals).

NOTE_TYPES: dict[str, str | list[str]] = {
    "2025-12-14": "pastoral",
    "2025-12-17": "o_antiphon",
    "2025-12-18": "o_antiphon",
    "2025-12-19": "o_antiphon",
    "2025-12-20": "o_antiphon",
    "2025-12-21": "o_antiphon",
    "2025-12-22": "o_antiphon",
    "2025-12-23": "o_antiphon",
    "2025-12-26": ["source_note", "source_note"],
    "2025-12-27": "precedence_rule",
    "2025-12-29": ["source_note", "source_note"],
    "2026-01-06": ["source_note", "office_note"],
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
    "2026-06-28": ["precedence_rule", "source_note"],
    "2026-07-01": "civil_day",
    "2026-07-25": "precedence_rule",
    "2026-08-06": "reconciliation_propers",
    "2026-08-14": "source_note",
    "2026-08-15": "precedence_rule",
    "2026-08-29": "precedence_rule",
    "2026-09-07": "civil_day",
    "2026-09-08": "pastoral",
    "2026-09-13": "precedence_rule",
    "2026-09-16": "ember_crossref",
    "2026-09-18": "ember_crossref",
    "2026-09-19": "ember_crossref",
    "2026-09-28": "source_note",
    "2026-10-04": "pastoral",
    "2026-10-30": "source_note",
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
    "2026-12-26": ["source_note", "source_note", "precedence_rule"],
    "2026-12-28": "source_note",
    "2026-12-29": ["source_note", "source_note"],
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


# ── Observance classification ─────────────────────────────────────────────────
# ADR 0017: observances are extracted from the CSV name column, reading every
# line of it — most markers are lines after the first <br>, but at least one
# (National Indigenous Day of Prayer) appears as the entire primary line.

RE_EVE_OF = re.compile(
    r"^Eve of\s+(.+?)\s*(?:\([^)]*\))?\s*(?:\[[^]]*\])?\s*$",
    re.IGNORECASE,
)

# An office label naming an eve ("Eve of Saint Mary"). Looser than RE_EVE_OF,
# which anchors a whole name-column line; this one only has to recognise the
# label the office column prefixes its propers with.
RE_EVE_LABEL = re.compile(r"^Eve of\s+\S", re.IGNORECASE)


def _classify_observance_line(line: str) -> list[str] | None:
    """Classify one cleaned name-column line into observance tags.

    Returns a list of tags (usually one), or None when the line is not an
    observance — alternate commemorations ("Florence Nightingale, … - Com"),
    separator text ("And / or"), and plain eves ("Eve of Sunday") are all
    deliberately ignored (ADR 0017 point 3).
    """
    if m := RE_EVE_OF.match(line):
        target = m.group(1).strip()
        key = re.sub(r"^the\s+", "", target, flags=re.I).strip().lower()
        key = key.replace("\u2019", "'")  # CSV uses U+2019; vocabulary is ASCII
        if key not in KNOWN_EVE_TARGETS:
            print(
                f"WARNING: observances: unrecognized 'Eve of {target}' line in "
                f"the CSV name column; expected one of the known eve targets — "
                f"check whether ACC changed the wording",
                file=sys.stderr,
            )
            return None
        if key in EVE_EXCLUDED_TARGETS:
            return None
        bare = re.sub(r"^the\s+", "", target, flags=re.I).strip()
        tag = "eve_of:" + ("the " if key in EVE_THE_ARTICLE else "") + bare
        tags = [tag]
        if companion := EVE_COMPANION_TAGS.get(key):
            tags.append(companion)
        return tags
    lowered = line.lower()
    # CSV typography uses U+2019 ("New Year's Day"); the phrase vocabulary is
    # ASCII, so normalize before matching.
    lowered = lowered.replace("\u2019", "'")
    # Longest phrase first: if ACC ever adds a phrase containing an existing
    # one (e.g. "National Day of Thanksgiving" inside "thanksgiving day"),
    # the more specific match wins rather than whichever dict order happens
    # to come first.
    for phrase, tag in sorted(
        OBSERVANCE_PHRASES.items(), key=lambda kv: len(kv[0]), reverse=True
    ):
        if phrase in lowered:
            return [tag]
    _warn_phrase_drift(line, lowered)
    return None


def _warn_phrase_drift(line: str, lowered: str) -> None:
    """Warn when an unmatched line is close to a known phrase.

    Unmatched lines are deliberately ignored (commemorations, separators), so
    ACC rephrasing a marker would otherwise fail silently — the same
    silent-drift risk detect_bounds() guards against for season boundaries.
    A line within OBSERVANCE_FUZZY_RATIO of a known phrase is warned about;
    anything more distant is treated as a new or non-observance line.
    """
    best_ratio, best_phrase = 0.0, None
    for phrase in OBSERVANCE_PHRASES:
        ratio = difflib.SequenceMatcher(None, lowered, phrase).ratio()
        if ratio > best_ratio:
            best_ratio, best_phrase = ratio, phrase
    if best_ratio >= OBSERVANCE_FUZZY_RATIO:
        print(
            f"WARNING: observances: CSV name-column line {line!r} matches no "
            f"phrase but is {best_ratio:.0%} similar to {best_phrase!r} — "
            f"check whether ACC changed the wording",
            file=sys.stderr,
        )


def parse_observances(raw: str) -> list[str] | None:
    """Extract secondary-observance tags from the CSV name column (ADR 0017).

    Classifies every line of the cleaned field, in line order; returns None
    when no line is an observance.
    """
    tags: list[str] = []
    for line in clean(raw).split("\n"):
        line = line.strip()
        if not line:
            continue
        if found := _classify_observance_line(line):
            tags.extend(found)
    return tags or None


def alternate_identity(label: str, lines: list[str]) -> dict | None:
    """Match an office alternate's label against name-column lines (ADR 0018).

    Returns the alternate observance's identity — {colour, optional, rank} —
    when a line matches, else None (the caller keeps the day's identity).
    Matching is case-insensitive containment in either direction after
    stripping "the" (the label's article form — "Eve of the Ascension" —
    need not match the CSV's bare form); see line_identity for the rank.
    """
    target = re.sub(r"\bthe\s+", "", label, flags=re.I).strip().lower()
    target = target.replace("\u2019", "'")  # CSV typography vs ASCII labels
    if not target:
        return None
    for line in lines:
        low = re.sub(r"\bthe\s+", "", line, flags=re.I).strip().lower()
        low = low.replace("\u2019", "'")
        if not low or not (target in low or low in target):
            continue
        return line_identity(line, low)
    return None


def line_identity(line: str, low: str) -> dict:
    """Read one name-column line's identity \u2014 {colour, optional, rank}.

    ``low`` is the caller's article-stripped lowercase form of ``line``.
    """
    identity: dict = {}
    if m := re.search(r"\(([^)]*)\)", line):
        identity["colour"] = m.group(1).strip()
    identity["optional"] = bool(re.search(r"\[[^]]*\]", line))
    # ADR 0018 ranked eve lines `feria` alongside actual ferias for want of a
    # better token. `eve` is that token (#128): an eve alternate and an eve in
    # the primary slot are the same kind of office, and 2026-01-03 puts one of
    # each on the two sides of a single toggle.
    if low.startswith("eve "):
        identity["rank"] = "eve"
    elif re.search(r"\bferia\b", low):
        identity["rank"] = "feria"
    return identity


def eve_identity(label: str, lines: list[str]) -> dict | None:
    """Identity for an eve's office, from the name column (#128).

    ADR 0018's containment match locates the line. It fails where ACC writes
    the eve's full title in the name column and an abbreviated one in the
    office column \u2014 "Eve of the Birth of Saint John the Baptist" against "Eve
    of Saint John the Baptist" \u2014 so a day naming exactly one eve falls back to
    that line: with one candidate there is nothing for the label to be
    ambiguous about. A day naming two (2026-01-03 keeps both the Epiphany's
    eve and Christmas II's) keeps containment, which separates them correctly.

    Adds `title` \u2014 the eve named as the name column names it, minus the
    colour and bracket decorations. The office column's own label is an
    abbreviation ("Eve of Saint Mary" for "Eve of Saint Mary the Virgin");
    it stays where the source put it, above the readings, while the header
    announces the day in full.
    """
    target = re.sub(r"\bthe\s+", "", label, flags=re.I).strip().lower()
    target = target.replace("\u2019", "'")
    line = None
    for candidate in lines:
        low = re.sub(r"\bthe\s+", "", candidate, flags=re.I).strip().lower()
        low = low.replace("\u2019", "'")
        if low and (target in low or low in target):
            line = candidate
            break
    if line is None:
        eve_lines = [ln for ln in lines if RE_EVE_OF.match(ln)]
        if len(eve_lines) != 1:
            return None
        line = eve_lines[0]

    low = re.sub(r"\bthe\s+", "", line, flags=re.I).strip().lower()
    identity = line_identity(line, low.replace("\u2019", "'"))
    # line_identity ranks the line `eve` only when it reads as one; the
    # containment match can land on a line that does not (2026-01-03's
    # "Eve of Christmas II" against "Christmas Feria"). Nothing to take from
    # such a line \u2014 the caller keeps the day's identity.
    if identity.get("rank") != "eve":
        return None
    if m := RE_EVE_OF.match(line):
        identity["title"] = "Eve of " + m.group(1).strip()
    # `optional` is the alternate toggle's concern; an eve in the primary slot
    # has no toggle, and one in the alternate slot keeps it via ADR 0018.
    identity.pop("optional", None)
    return identity



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

    # Sundays never carry an explicit rank marker in the CSV but are holy days.
    if rank == "feria" and "sunday" in desc.lower():
        rank = "holy_day"

    return desc.strip(), rank, colour


# ── Season boundaries ──────────────────────────────────────────────────────────

# Expected lowercase substrings in CSV name field for each season boundary.
# If ACC changes wording, detect_bounds() will warn rather than silently accept.
CANONICAL_BOUNDS_PHRASES = {
    "advent_i":       ["first sunday of advent"],
    "christmas":      ["birth of the lord"],
    "epiphany":       ["baptism of the lord"],
    "presentation":   ["presentation of the lord", "presentation of our lord"],
    "ash_wednesday":  ["ash wednesday"],
    "passiontide":    ["fifth sunday in lent"],
    "palm_sunday":    ["palm sunday"],
    "easter":         ["easter day", "sunday of the resurrection"],
    "ascension":      ["ascension of the lord"],
    "pentecost":      ["day of pentecost"],
    "trinity_sunday": ["trinity sunday"],
    "all_saints":     ["all saints"],
}


def _bounds_title_forms(desc):
    """The candidate titles in a CSV description, with its decorations removed.

    The source writes a feast as an article, one or two titles, then a rank code
    and a colour: "the sunday of the resurrection: easter day - pf (white or
    gold)". CANONICAL_BOUNDS_PHRASES holds the bare titles, so matching the raw
    description could only ever succeed as a loose substring — every correct
    match reported itself as fuzzy, and six such warnings printed on every
    extraction. A warning that always fires trains people to ignore the ones
    that mean something, so the decorations are stripped and a real match is
    allowed to be exact.
    """
    text = re.sub(r"\s*[-–]\s*(pf|hd|fd)\b.*$", "", desc)   # rank code and after
    text = re.sub(r"\s*\([^)]*\)\s*$", "", text)            # trailing colour
    text = re.sub(r"\s*\[[^]]*\]", "", text)                # proper number
    text = text.strip()
    forms = {text}
    if text.startswith("the "):
        forms.add(text[4:])
    for form in list(forms):                                # "title a: title b"
        for part in form.split(":"):
            part = part.strip()
            if part:
                forms.add(part)
                if part.startswith("the "):
                    forms.add(part[4:])
    return forms


def _bounds_match(desc, phrases):
    """Check exact (== or startswith) then fuzzy (in). Returns ('exact'|'fuzzy'|None, phrase|None)."""
    forms = _bounds_title_forms(desc)
    for phrase in phrases:
        for form in forms:
            if form == phrase or form.startswith(phrase):
                return 'exact', phrase
    for phrase in phrases:
        if phrase in desc:
            return 'fuzzy', phrase
    return None, None


def detect_bounds(rows) -> dict:
    bounds = {}
    advent_count = 0
    christmas_count = 0
    for row in rows:
        if len(row) < 2:
            continue
        date_str = row[0].strip()
        if not re.match(r"\d{4}-\d{2}-\d{2}", date_str):
            continue
        desc = first_line(clean(row[1])).lower()

        # advent_i / advent_ii: same phrase appears twice in a multi-year CSV
        phrases = CANONICAL_BOUNDS_PHRASES["advent_i"]
        match_type, _ = _bounds_match(desc, phrases)
        if match_type:
            if match_type == 'fuzzy':
                print(f"WARNING: detect_bounds: 'advent_i' matched via fuzzy substring; "
                      f"expected one of {phrases!r}, got {desc!r}", file=sys.stderr)
            advent_count += 1
            if advent_count == 1:
                bounds["advent_i"] = date_str
            elif advent_count == 2:
                bounds["advent_ii"] = date_str
            continue

        # christmas / christmas_ii: same phrase appears twice in a multi-year CSV
        phrases = CANONICAL_BOUNDS_PHRASES["christmas"]
        match_type, _ = _bounds_match(desc, phrases)
        if match_type:
            if match_type == 'fuzzy':
                print(f"WARNING: detect_bounds: 'christmas' matched via fuzzy substring; "
                      f"expected one of {phrases!r}, got {desc!r}", file=sys.stderr)
            christmas_count += 1
            if christmas_count == 1:
                bounds["christmas"] = date_str
            elif christmas_count == 2:
                bounds["christmas_ii"] = date_str
            continue

        # All remaining single-occurrence bounds
        for key, phrases in CANONICAL_BOUNDS_PHRASES.items():
            if key in ("advent_i", "christmas"):
                continue
            if key in bounds:
                continue
            match_type, _ = _bounds_match(desc, phrases)
            if match_type == 'exact':
                bounds[key] = date_str
                break
            elif match_type == 'fuzzy':
                print(f"WARNING: detect_bounds: '{key}' matched via fuzzy substring; "
                      f"expected one of {phrases!r}, got {desc!r}", file=sys.stderr)
                bounds[key] = date_str
                break

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
    last_psalm_num: str | None = None
    for tok in s.split(", "):
        p = _psalm_token(tok)
        if p is None:
            continue
        is_optional = isinstance(p, dict)
        c = p["citation"] if is_optional else p
        if ":" in c:
            # Normal "139:1-17" style — record psalm number for continuations.
            last_psalm_num = c.split(":")[0]
        elif "-" in c and last_psalm_num:
            # Bare verse range like "(18-23)" following "139:1-17".
            # The parenthesised suffix continues the same psalm, not a new one.
            new_c = f"{last_psalm_num}:{c}"
            p = {"citation": new_c, "optional": True} if is_optional else new_c
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
# CSV shorthand "Coll above" / "Coll below" points at the Collect of the Day in
# the propers — it is not a lesson (BUG-26). Case-sensitive by design.
RE_COLL_REF = re.compile(r"^Coll (above|below)\b")
# "O Antiphon" leaks from the CSV into the lessons array on Dec 17–23 (BUG-33);
# the antiphon is already delivered as a typed o_antiphon note. Not a lesson.
RE_O_ANTIPHON = re.compile(r"^O Antiphon$")
# "Preface of a Saint" / "Preface of a Martyr" etc. — Eucharistic rubrics that
# occasionally leak into the lessons array via the Br/Or alternative separator.
RE_PREFACE = re.compile(r"(?i)^Preface of")

# Collect of the Day inside a eucharist propers blob (BUG-27). The blob runs
# "… Collect of the Day: <text> Amen <next heading>: …".
RE_COLLECT_OF_DAY = re.compile(
    r"Collect of the Day:\s*(.*?)\s*"
    r"(?=Prayer over the Gifts:|Prayer after Communion:|Sentence:|$)",
    re.DOTALL,
)


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
            citation = lesson if isinstance(lesson, str) else lesson.get("citation", "")
            if RE_COLL_REF.match(citation) or RE_O_ANTIPHON.match(citation) or RE_PREFACE.match(citation):
                continue
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

RE_BR_RUN = re.compile(r"(?:<br\s*/?>\s*)+", re.I)


def note_segments(raw: str) -> list[str]:
    """The extra column's <br>-separated segments, cleaned, blanks dropped."""
    return [s for s in (clean_inline(p) for p in RE_BR_RUN.split(raw)) if s]


def _type_hint(segments: list[str]) -> str:
    """A copy-pasteable NOTE_TYPES value shape for an untyped cell.

    The type itself is a judgment call the reporter will not make; only the
    str-or-list shape follows from the segment count.
    """
    if len(segments) == 1:
        return '"???"'
    return "[" + ", ".join('"???"' for _ in segments) + "]"


def untyped_note_dates(rows_by_date: dict[str, list]) -> list[tuple[str, list[str]]]:
    """Note-bearing dates with no NOTE_TYPES entry, with their segments.

    NOTE_TYPES is keyed by date, so no classification carries from one
    lectionary year to the next: 2027's sourcing notes are new keys. The
    lookup defaults, and a default is how the DOL notes spent a year typed
    `pastoral` — the reader was told, in the voice of a custom to observe,
    which of two lectionary options the compiler had taken (#127).

    So a new year's notes are triaged or they are not extracted. Callers
    report this rather than guessing; tools/intake_year.py reads it too.
    """
    untyped = []
    for date_str, row in sorted(rows_by_date.items()):
        raw = row[5].strip() if len(row) > 5 else ""
        if raw and date_str not in NOTE_TYPES:
            untyped.append((date_str, note_segments(raw)))
    return untyped


def unmatched_eve_offices(
    rows_by_date: dict[str, list],
) -> list[tuple[str, str, str, list[str]]]:
    """Eve offices whose label matches no name-column line (#128).

    Fail-open would put the day's colour on an office praying the eve's
    propers — green on the Eve of Saint Mary — so these block extraction.
    Computed from the raw rows so main()'s gate and tools/intake_year.py
    share one reader and cannot drift apart; the enrichment pass that
    follows re-derives the same name lines from each entry.
    """
    unmatched = []
    for date_str, row in sorted(rows_by_date.items()):
        if len(row) < 5:
            continue
        name_lines = [ln.strip() for ln in clean(row[1]).split("\n") if ln.strip()]
        if not name_lines:
            continue
        for office_key, idx in (("morning", 3), ("evening", 4)):
            if len(row) <= idx:
                continue
            office = parse_office_column(row[idx])
            label = (office or {}).get("label") or ""
            if not RE_EVE_LABEL.match(label):
                continue
            if not eve_identity(label, name_lines):
                unmatched.append((date_str, office_key, label, name_lines))
    return unmatched


def parse_extra(raw: str, date_str: str) -> list[dict] | None:
    """
    Parse the extra column into a notes list.
    Type is looked up from NOTE_TYPES; text is the HTML-cleaned content.

    A str type makes the whole cell one note. A list type splits the cell on
    its <br> runs and pairs each segment with the type at the same index, so
    a cell carrying two kinds of note (a precedence rule and the sourcing it
    was fused with) yields one note per kind.
    """
    note_type = NOTE_TYPES.get(date_str, "pastoral")

    if isinstance(note_type, list):
        segments = [s for s in (clean_inline(p) for p in RE_BR_RUN.split(raw)) if s]
        if len(segments) != len(note_type):
            sys.exit(
                f"{date_str}: NOTE_TYPES lists {len(note_type)} types but the "
                f"extra column splits into {len(segments)} segments. ACC "
                f"re-split the cell — retype it in NOTE_TYPES rather than "
                f"letting the pairing shift silently.\n"
                + "\n".join(f"  [{i}] {s[:90]}" for i, s in enumerate(segments))
            )
        return [{"type": t, "text": s} for t, s in zip(note_type, segments)]

    text = clean_inline(raw)
    if not text:
        return None
    # Some Advent Ember Days that coincide with O Antiphon days have the Ember Day
    # cross-reference appended to the antiphon text in the CSV. Strip the suffix —
    # it is redundant since the day name already says "Advent Ember Day".
    if note_type == "o_antiphon":
        text = re.sub(r'\s*Ember Day:.*', '', text, flags=re.DOTALL).strip()
        if not text:
            return None
    return [{"type": note_type, "text": text}]


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", nargs="*", metavar="PATH",
                    help="CSV files to process (default: sources/bas_short_*.csv)")
    ap.add_argument("--accept", action="store_true",
                    help="Update tools/manifest.json with current output hashes")
    ap.add_argument("--window", type=int, default=None, metavar="N",
                    help="Keep only monthly files within N months of today (default: keep all)")
    args = ap.parse_args()

    root = Path(__file__).parent.parent
    # Stage 1: apply_corrections.py reads these and writes data/lectionary/.
    lect_dir = root / ".build" / "lectionary"
    bounds_path = root / "data" / "season_bounds.json"

    if args.csv:
        csv_paths = [Path(p) for p in args.csv]
    else:
        csv_paths = sorted(root.glob("sources/bas_short_*.csv"))
    if not csv_paths:
        sys.exit("No CSV files found. Add a bas_short_YYYY.csv file to sources/ and re-run.")

    # Merge rows from all CSVs by date; sort by year so later files win on overlap.
    rows_by_date: dict[str, list] = {}
    for csv_path in csv_paths:
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in csv.reader(f, quoting=csv.QUOTE_MINIMAL):
                if len(row) >= 5 and re.match(r"\d{4}-\d{2}-\d{2}", row[0].strip()):
                    rows_by_date[row[0].strip()] = row
    rows = sorted(rows_by_date.values(), key=lambda r: r[0])
    print(f"Loaded {len(rows)} unique dates from {len(csv_paths)} CSV file(s)")

    # Intake gate. Everything a new lectionary year needs decided by hand is
    # collected here and reported at once, so the worklist arrives whole
    # rather than one exit at a time. See docs/runbooks/lectionary-year-intake.md.
    intake: list[str] = []
    if untyped := untyped_note_dates(rows_by_date):
        intake.append(
            f"{len(untyped)} date(s) carry a note with no NOTE_TYPES entry. "
            f"Classify each, then add it to the table in this file. A list "
            f"types a cell's <br> segments in order; a string types the whole "
            f"cell. `source_note` is the compiler's apparatus, `pastoral` is a "
            f"custom addressed to whoever is praying — the distinction the "
            f"default silently collapsed (#127).\n"
            + "\n".join(
                f'    "{d}": {_type_hint(segs)},'
                + "".join(f"\n        # [{i}] {s[:96]}" for i, s in enumerate(segs))
                for d, segs in untyped
            )
        )

    bounds = detect_bounds(rows)
    _REQUIRED_BOUNDS = [
        'advent_i', 'christmas', 'epiphany', 'ash_wednesday',
        'easter', 'pentecost', 'trinity_sunday', 'all_saints',
    ]
    missing = [k for k in _REQUIRED_BOUNDS if k not in bounds]
    if missing:
        sys.exit(
            f"ERROR: detect_bounds() missing required keys: {', '.join(missing)}\n"
            "Check CSV name strings and update detect_bounds() if ACC wording changed."
        )
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

        # Field order: date, name, rank, colour, observances, eucharist,
        #              morning, evening, notes.
        entry: dict = {
            "date": date_str,
            "name": name,
            "rank": rank,
        }
        if colour:
            entry["colour"] = colour

        obs = parse_observances(row[1])
        if obs:
            entry["observances"] = obs

        # ADR 0018: keep the cleaned name-column lines for the
        # alternate-identity enrichment pass below (popped there, like
        # _coll_ref).
        entry["_name_lines"] = [
            line.strip() for line in clean(row[1]).split("\n") if line.strip()
        ]

        eucharist = parse_eucharist(row[2]) if len(row) > 2 else ""
        if eucharist:
            entry["eucharist"] = eucharist

        mp = parse_office_column(row[3])
        ep = parse_office_column(row[4])

        # Remember when this row's offices referenced the propers Collect
        # ("Coll above/below" — stripped from lessons by RE_COLL_REF); a second
        # pass below surfaces the collect itself as collect_inline (BUG-27).
        raw_offices = " ".join(row[3:5])
        if m := re.search(r"\bColl (above|below)\b", raw_offices):
            entry["_coll_ref"] = m.group(1)

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

    # Second pass (BUG-27): days whose offices said "Coll above/below" get the
    # Collect of the Day extracted from the propers blob as collect_inline.
    # "below" on an eve means the collect lives on the following day's blob.
    by_date = {e["date"]: e for e in entries}
    for entry in entries:
        ref = entry.pop("_coll_ref", None)
        if not ref:
            continue
        source = entry
        if ref == "below":
            next_key = (
                datetime.date.fromisoformat(entry["date"])
                + datetime.timedelta(days=1)
            ).isoformat()
            nxt = by_date.get(next_key)
            if nxt and RE_COLLECT_OF_DAY.search(nxt.get("eucharist", "")):
                source = nxt
            else:
                print(
                    f"  note: {entry['date']} 'Coll below' did not resolve to "
                    f"next day's propers; using same-day blob",
                    file=sys.stderr,
                )
        m = RE_COLLECT_OF_DAY.search(source.get("eucharist", ""))
        if not m or not m.group(1).strip():
            print(
                f"  note: {entry['date']} has 'Coll {ref}' but no "
                f"'Collect of the Day:' text found — collect_inline skipped",
                file=sys.stderr,
            )
            continue
        text = m.group(1).strip()
        if text.endswith("Amen"):
            text += "."
        entry["collect_inline"] = {"name": source["name"], "text": text}

    # Third pass (ADR 0018): give each office alternate the alternate
    # observance's identity — colour, optionality, rank — matched from the
    # name column's lines, so the app's Primary/Alternate toggle can present
    # the selected observance's own identity rather than the primary's.
    # The eve gate (#128) is computed up front from the raw rows so the
    # report tool and this gate share one reader (unmatched_eve_offices).
    unmatched_eves = unmatched_eve_offices(rows_by_date)
    if unmatched_eves:
        intake.append(
            f"{len(unmatched_eves)} eve office(s) matched no name-column line, "
            f"so the eve has no colour of its own and the header would show "
            f"the day's (#128). Either the office label and the name line have "
            f"drifted apart — extend eve_identity's matching — or ACC omitted "
            f"the eve from the name column, which is a correction.\n"
            + "\n".join(
                f"    {d} {office} label={label!r}\n"
                + "".join(f"        name line: {ln}\n" for ln in lines)
                for d, office, label, lines in unmatched_eves
            )
        )

    for entry in entries:
        name_lines = entry.pop("_name_lines", None)
        if not name_lines:
            continue
        for office_key in ("morning", "evening"):
            office = entry.get(office_key, {})
            if alt := office.get("alternate"):
                identity = alternate_identity(alt.get("label") or "", name_lines)
                if identity:
                    alt.update(identity)
            # An eve does not alternate with the day's own propers, it replaces
            # them — so an eve in the primary slot has no toggle to carry its
            # identity and kept presenting the day's instead (#128). Enriched
            # whether or not an alternate exists: on 2026-01-03 both slots are
            # eves, the Epiphany's and Christmas II's.
            label = office.get("label") or ""
            if not RE_EVE_LABEL.match(label):
                continue
            if identity := eve_identity(label, name_lines):
                office.update(identity)

    if intake:
        sys.exit(
            "\nLectionary intake — this CSV needs decisions that cannot be "
            "derived from it.\nSee docs/runbooks/lectionary-year-intake.md.\n\n"
            + "\n\n".join(f"── {p}" for p in intake)
            + "\n\nNothing was written. Resolve the above and re-run.\n"
        )

    # Group entries by YYYY-MM and write one file per month.
    months: dict[str, dict] = {}
    for entry in entries:
        month_key = entry["date"][:7]  # "YYYY-MM"
        months.setdefault(month_key, {})[entry["date"]] = entry

    # Apply rolling window: keep only months within N months of today.
    if args.window is not None:
        today = datetime.date.today()
        window_start = today - datetime.timedelta(days=args.window * 31)
        window_end = today + datetime.timedelta(days=args.window * 31)
        window_start_key = window_start.strftime("%Y-%m")
        window_end_key = window_end.strftime("%Y-%m")
        months = {k: v for k, v in months.items()
                  if window_start_key <= k <= window_end_key}
        # Remove existing files the current source no longer accounts for:
        # outside the window, or inside it but no longer produced by the CSV.
        # Pruning by window alone stranded months from a previous lectionary
        # year — they sat inside the date window, nothing regenerated them, and
        # they failed validation with entries the current parser rejects. CI
        # never saw it because a fresh checkout starts with an empty directory.
        if lect_dir.exists():
            for existing in sorted(lect_dir.glob("*.json")):
                mk = existing.stem  # "YYYY-MM"
                if mk < window_start_key or mk > window_end_key:
                    existing.unlink()
                    print(f"  removed {existing.name} (outside window)")
                elif mk not in months:
                    existing.unlink()
                    print(f"  removed {existing.name} (not in current source)")

    lect_dir.mkdir(parents=True, exist_ok=True)
    with open(bounds_path, "w", encoding="utf-8") as f:
        json.dump(bounds, f, ensure_ascii=False, indent=2)
    output_paths = [bounds_path]
    for month_key, month_entries in sorted(months.items()):
        path = lect_dir / f"{month_key}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(month_entries, f, ensure_ascii=False, indent=2)
            f.write('\n')
        output_paths.append(path)

    print(f"Wrote {len(entries)} entries across {len(months)} monthly files to {lect_dir}/")
    print(f"Wrote season bounds to {bounds_path}")
    print(f"Skipped {skipped} non-date rows")
    print(f"Season bounds: {bounds}")

    # ── Verification ──────────────────────────────────────────────────────────
    # One-off CSV-error corrections (name/rank/colour/lessons/notes) are no
    # longer applied or stale-checked here — that's data/corrections.json +
    # validate_corrections.py/apply_corrections.py now, which run later in
    # `make extract` and do the same staleness check generically for every
    # correction category, not just this file's.
    with_eucharist = sum(1 for e in entries if e.get("eucharist"))
    with_obs = sum(1 for e in entries if e.get("observances"))
    with_notes = sum(1 for e in entries if e.get("notes"))
    print(f"  eucharist populated: {with_eucharist}/{len(entries)}")
    print(f"  observances:         {with_obs} days (extracted from CSV name column)")
    print(f"  notes:               {with_notes}/{len(NOTE_TYPES)} from correction dict")

    check_manifest(output_paths, root, accept=args.accept)


if __name__ == "__main__":
    main()
