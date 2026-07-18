#!/usr/bin/env python3
"""
Extract RCL Daily Readings from RTF source files → data/rcl-daily/YYYY-MM.json

The Revised Common Lectionary Daily Readings (Consultation on Common Texts, 2005)
provide a psalm and two readings for each weekday of the church year, organized
in a Thursday–Wednesday cycle around each Sunday.

Input:  sources/rcl/rcl_year_b.rtf (Years A and C also available)
Output: data/rcl-daily/YYYY-MM.json

Usage:
    python3 tools/extract_rcl_daily.py [--year YEAR] [--season-bounds PATH] [--rtf PATH]

The extractor:
  1. Converts RTF to plain text via textutil
  2. Parses the Year B template into a linear sequence of day entries
  3. Computes church-year season bounds (Easter-based) for the target year
  4. Maps template days to calendar dates
  5. Outputs monthly JSON files to data/rcl-daily/
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import date, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(PROJECT_ROOT, "data", "rcl-daily")
SOURCES_DIR = os.path.join(PROJECT_ROOT, "sources", "rcl")

WEEKDAY_ABBR = {"Th": 3, "F": 4, "Sa": 5, "Su": 6, "M": 0, "T": 1, "Tu": 1, "W": 2}
WEEKDAY_NAMES = {3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday",
                 0: "Monday", 1: "Tuesday", 2: "Wednesday"}
WEEKDAY_ORDER = [3, 4, 5, 6, 0, 1, 2]  # Th, F, Sa, Su, M, Tu, W


def easter_date(year):
    """Compute Western Easter Sunday date for a given year (Anonymous Gregorian algorithm)."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def advent_sunday(year):
    """First Sunday of Advent: the Sunday between Nov 27 and Dec 3 (inclusive)."""
    nov27 = date(year, 11, 27)
    days_to_sun = (6 - nov27.weekday()) % 7
    return nov27 + timedelta(days=days_to_sun)


def compute_season_bounds(year):
    """Compute all season boundary dates for a church year starting Advent of `year`."""
    advent1 = advent_sunday(year)
    christmas = date(year, 12, 25)
    epiphany = date(year + 1, 1, 6)
    # Baptism of the Lord: Sunday after Jan 6 (or Jan 6 itself if Sunday, then next Sunday)
    # In practice: first Sunday after Epiphany (Jan 6) that is not Epiphany itself
    epiphany_wd = epiphany.weekday()  # Mon=0 ... Sun=6
    if epiphany_wd == 6:
        baptism = epiphany + timedelta(days=7)
    else:
        baptism = epiphany + timedelta(days=6 - epiphany_wd)

    easter = easter_date(year + 1)
    ash_wednesday = easter - timedelta(days=46)
    pentecost = easter + timedelta(days=49)
    trinity = easter + timedelta(days=56)
    # Christ the King: Sunday before Advent 1 of the NEXT church year
    advent1_next = advent_sunday(year + 1)
    christ_the_king = advent1_next - timedelta(days=7)
    ascension = easter + timedelta(days=39)  # 40th day counting from Easter

    # Palm Sunday: Sunday before Easter
    palm_sunday = easter - timedelta(days=7)
    # Holy Week: Monday before Easter through Saturday
    holy_week_mon = easter - timedelta(days=6)

    # Compute Lent Sundays (1-5) from ash_wednesday
    # Ash Wednesday is Lent 1 week already started. Lent 1 Sunday = Ash Wed + 4
    lent1_sunday = ash_wednesday + timedelta(days=4)

    # Advent Sundays: Advent 1 through 4
    advent1_sunday = advent1
    advent2_sunday = advent1 + timedelta(days=7)
    advent3_sunday = advent1 + timedelta(days=14)
    advent4_sunday = advent1 + timedelta(days=21)

    # Epiphany Sundays: after Baptism
    # Epiphany 2 Sunday = Baptism + 7
    epiphany2_sunday = baptism + timedelta(days=7)
    epiphany3_sunday = baptism + timedelta(days=14)
    epiphany4_sunday = baptism + timedelta(days=21)
    epiphany5_sunday = baptism + timedelta(days=28)
    epiphany6_sunday = baptism + timedelta(days=35)
    epiphany7_sunday = baptism + timedelta(days=42)
    epiphany8_sunday = baptism + timedelta(days=49)
    epiphany9_sunday = baptism + timedelta(days=56)

    # Easter Sundays
    easter1_sunday = easter
    easter2_sunday = easter + timedelta(days=7)
    easter3_sunday = easter + timedelta(days=14)
    easter4_sunday = easter + timedelta(days=21)
    easter5_sunday = easter + timedelta(days=28)
    easter6_sunday = easter + timedelta(days=35)
    easter7_sunday = easter + timedelta(days=42)

    return {
        "advent_1": advent1_sunday,
        "advent_2": advent2_sunday,
        "advent_3": advent3_sunday,
        "advent_4": advent4_sunday,
        "christmas": christmas,
        "epiphany": epiphany,
        "baptism": baptism,
        "epiphany_2": epiphany2_sunday,
        "epiphany_3": epiphany3_sunday,
        "epiphany_4": epiphany4_sunday,
        "epiphany_5": epiphany5_sunday,
        "epiphany_6": epiphany6_sunday,
        "epiphany_7": epiphany7_sunday,
        "epiphany_8": epiphany8_sunday,
        "epiphany_9": epiphany9_sunday,
        "ash_wednesday": ash_wednesday,
        "lent_1": lent1_sunday,
        "lent_2": lent1_sunday + timedelta(days=7),
        "lent_3": lent1_sunday + timedelta(days=14),
        "lent_4": lent1_sunday + timedelta(days=21),
        "lent_5": lent1_sunday + timedelta(days=28),
        "palm_sunday": palm_sunday,
        "holy_week_mon": holy_week_mon,
        "easter": easter,
        "easter_2": easter2_sunday,
        "easter_3": easter3_sunday,
        "easter_4": easter4_sunday,
        "easter_5": easter5_sunday,
        "easter_6": easter6_sunday,
        "easter_7": easter7_sunday,
        "ascension": ascension,
        "pentecost": pentecost,
        "trinity": trinity,
        "christ_the_king": christ_the_king,
        "advent_1_next": advent1_next,
    }


def rtf_to_text(rtf_path):
    """Convert RTF to plain text using striprtf (cross-platform)."""
    from striprtf.striprtf import rtf_to_text as _parse
    with open(rtf_path, 'r') as f:
        return _parse(f.read())


def parse_rtf_template(text):
    """Parse the RTF plain text into a structured Year B template.

    Tab structure: lines with leading tabs. `content = stripped.lstrip("\\t")` gives
    the first real field at index 0 after splitting content on "\\t".

    Single-track 1-tab:   content="Th\\tPsalm X"     → [Th, Psalm X]
    Single-track 2-tab:   content="Reading 1"          → [Reading 1]
    Two-track   1-tab:    content="Th\\tP1\\t\\t\\t\\tP2" → [Th, P1, "", "", "P2"]
    Two-track   2-tab:    content="R1\\t\\t\\t\\tR2"     → [R1, "", "", "R2"]

    For two-track: track 1 fields are at content-split index 0/1; track 2 at index 4/5.
    """
    lines = text.split("\n")
    blocks = []
    current_season = None
    current_week = None

    day_tag = None
    day_label = None
    day_season = None
    day_week = None
    day_is_two_track = False
    day_readings_t1 = []
    day_readings_t2 = []
    day_alternative_of = None
    day_is_special = False

    def flush_day():
        nonlocal day_tag, day_label, day_season, day_week, day_is_two_track
        nonlocal day_readings_t1, day_readings_t2, day_alternative_of, day_is_special

        if day_tag and (day_readings_t1 or day_readings_t2):
            entry = {
                "season": day_season,
                "week": day_week,
                "day_tag": day_tag,
                "label": day_label,
                "alternative_of": day_alternative_of,
                "is_special": day_is_special,
            }
            if day_is_two_track:
                entry["two_track"] = True
                entry["track1"] = list(day_readings_t1)
                entry["track2"] = list(day_readings_t2)
            else:
                entry["two_track"] = False
                entry["track1"] = list(day_readings_t1)
                entry["track2"] = []
            blocks.append(entry)

        day_tag = None
        day_label = None
        day_season = None
        day_week = None
        day_is_two_track = False
        day_readings_t1 = []
        day_readings_t2 = []
        day_alternative_of = None
        day_is_special = False

    re_advent = re.compile(r"^Advent (\d)$")
    re_lent = re.compile(r"^Lent (\d)$")
    re_easter_season = re.compile(r"^Easter (\d)$")
    re_epiphany = re.compile(r"^Epiphany (\d+)(?: .*)?$")
    re_epiphany1 = re.compile(r"^Baptism of the Lord")
    re_transfig_alt = re.compile(r"^OR Transfiguration$")
    re_weekday = re.compile(r"^(Th|F|Sa|Su|M|T|Tu|W)$")
    re_fixed_date = re.compile(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d+)$")
    re_sunday_name = re.compile(
        r"^(First|Second|Third|Fourth|Fifth|Sixth|Seventh|Eighth|Ninth|Tenth) Sunday"
    )
    re_stray_reading = re.compile(r"^[A-Za-z]+\s+\d+:")

    def _is_season_header(content):
        """Check if a 0-tab line is a recognized season/section header."""
        if content == "Days around Christmas":
            return "Christmas", None
        if content == "Days around Epiphany":
            return "Epiphany", None
        if content == "Trinity":
            return "Trinity", 1
        if content == "Pentecost":
            return "Pentecost", 1
        if content == "Three Days—Easter":
            return "HolyWeek", None
        if re_advent.match(content):
            return "Advent", int(re_advent.match(content).group(1))
        if re_lent.match(content):
            return "Lent", int(re_lent.match(content).group(1))
        if re_easter_season.match(content):
            return "Easter", int(re_easter_season.match(content).group(1))
        if re_epiphany1.match(content):
            return "Epiphany", 1
        if re_epiphany.match(content):
            return "Epiphany", int(re_epiphany.match(content).group(1))
        if re_transfig_alt.match(content):
            return "TransfigurationAlt", None
        if content.startswith("Sunday,") or content.startswith("Reign of Christ"):
            return "Ordinary", None
        if re_sunday_name.match(content):
            return current_season or "Christmas", None
        if any(x in content for x in ("Holy Week", "Passion", "Palm")):
            return "HolyWeek", None
        if "Good Friday" in content or "Holy Saturday" in content:
            return "HolyWeek", None
        if "Resurrection" in content or "Easter Day" in content:
            return "Easter", 1
        if "Ascension" in content:
            return "Easter", 7
        if "Nativity" in content:
            return "Christmas", None
        return None, None

    for line in lines:
        stripped = line.strip("\n")
        content = stripped.lstrip("\t")
        if not content:
            continue

        fields = content.split("\t")
        tab_count = len(stripped) - len(content)

        # 0-tab: season/week headers (or stray reading lines)
        if tab_count == 0:
            new_season, new_week = _is_season_header(content)
            if new_season is not None:
                flush_day()
                current_season, current_week = new_season, new_week
            elif re_stray_reading.search(content):
                # Stray reading line at 0-tab (RTF formatting artifact).
                # Treat as a reading line — do NOT flush current day.
                if day_tag:
                    if day_is_two_track:
                        non_empty = [i for i, f in enumerate(fields) if f.strip()]
                        t1 = fields[0].strip()
                        t2_idx = non_empty[-1] if non_empty and non_empty[-1] > 0 else None
                        t2 = fields[t2_idx].strip() if t2_idx is not None else ""
                        if t1 and not re_sunday_name.match(t1):
                            day_readings_t1.append(t1)
                        if t2 and not re_sunday_name.match(t2):
                            day_readings_t2.append(t2)
                    else:
                        if not re_sunday_name.match(fields[0].strip()):
                            day_readings_t1.append(fields[0].strip())
            else:
                # Unknown 0-tab content (Easter Vigil numbers, copyright, etc.)
                # Flush current day but don't change season
                flush_day()
            continue

        # tab_count >= 1: day entries or reading lines
        # Detect two-track: look at fields count; two-track has 5+ fields (Th, P1, _, _, P2)
        # But also check for the "Complementary" header (tab_count==2)
        is_two_track = False
        is_two_track_header = False
        if tab_count == 2 and fields[0].strip() == "Complementary":
            is_two_track_header = True
            continue  # skip the header line

        if len(fields) >= 5:
            # Check if fields suggest two-track: fields[2] and [3] are empty, [4] has content
            if (not fields[2].strip() and not fields[3].strip() and fields[4].strip()):
                is_two_track = True
            elif tab_count == 1 and fields[0].strip() in ("Th", "F", "Sa", "Su", "M", "T", "Tu", "W"):
                # Could be two-track with fields that are all non-empty
                is_two_track = True

        if tab_count == 1:
            # Day entry line
            # Check for (a.m.) sub-entry — appends to previous day
            if fields[0].strip() == "(a.m.)" and day_tag:
                # (a.m.) readings append to current day entry
                f1 = fields[1].strip() if len(fields) > 1 else ""
                if f1 and not is_citation(f1):
                    day_label = (day_label or "") + " (a.m.)"
                if f1 and is_citation(f1):
                    day_readings_t1.append(f1)
                day_is_special = True
                continue

            if day_tag:
                flush_day()

            if is_two_track:
                # For two-track, find track2 at the LAST non-empty field
                non_empty_indices = [i for i, f in enumerate(fields) if f.strip()]
                t2_idx = non_empty_indices[-1] if len(non_empty_indices) >= 2 else None

                day_tag_raw = fields[0].strip()
                t1_val = fields[1].strip() if len(fields) > 1 else ""
                t2_val = fields[t2_idx].strip() if t2_idx is not None and t2_idx > 1 else ""

                day_season = current_season
                day_week = current_week
                day_is_two_track = True

                t1_is_label = _is_date_range_label(t1_val) if t1_val else False
                t2_is_label = _is_date_range_label(t2_val) if t2_val else False

                if re_weekday.match(day_tag_raw):
                    day_tag = day_tag_raw
                    if t1_is_label:
                        day_label = t1_val
                        t1_val = ""
                    else:
                        day_label = None
                    if t1_val:
                        day_readings_t1 = [t1_val]
                    if t2_val and not t2_is_label:
                        day_readings_t2 = [t2_val]
                    elif t2_val and t2_is_label:
                        day_label = day_label or t2_val
                elif re_fixed_date.match(day_tag_raw):
                    day_tag = day_tag_raw
                    day_label = None
                    if t1_val:
                        day_readings_t1 = [t1_val]
                    if t2_val:
                        day_readings_t2 = [t2_val]
                else:
                    day_tag = "Su"
                    day_label = day_tag_raw
                    if t1_val and not t1_is_label:
                        day_readings_t1 = [t1_val]
                    if t2_val and not t2_is_label:
                        day_readings_t2 = [t2_val]
            else:
                day_tag_raw = fields[0].strip()
                f1 = fields[1].strip() if len(fields) > 1 else ""

                # Detect Easter Day entries and flip season
                if "Resurrection" in f1 or "Easter Day" in f1 or "Easter Evening" in f1:
                    current_season = "Easter"
                    current_week = 1

                day_season = current_season
                day_week = current_week
                day_is_two_track = False

                if re_weekday.match(day_tag_raw):
                    # "Th", "F", etc.
                    day_tag = day_tag_raw
                    if f1 and not re_weekday.match(f1):
                        # f1 is a psalm or label
                        if re.match(r"^(Psalm|\d|Ps )", f1, re.IGNORECASE) or is_citation(f1):
                            day_readings_t1 = [f1]
                            day_label = None
                        else:
                            day_label = f1
                            day_readings_t1 = []
                    else:
                        day_label = None
                        day_readings_t1 = []

                elif re_fixed_date.match(day_tag_raw):
                    # "Dec 22", "Jan 6", etc.
                    day_tag = day_tag_raw
                    if f1:
                        if re.match(r"^(Psalm|Ps |\d)", f1) or is_citation(f1):
                            day_readings_t1 = [f1]
                            day_label = None
                        elif f1.startswith("(a.m.)"):
                            day_tag = f1  # "(a.m.)" sub-entry
                            day_label = "(a.m.)"
                            day_is_special = True
                        else:
                            day_label = f1
                    day_readings_t1 = day_readings_t1 or []

                elif "Nativity" in day_tag_raw or "New Year" in day_tag_raw or "Holy Name" in day_tag_raw:
                    day_tag = day_tag_raw
                    day_label = day_tag_raw
                    day_is_special = True
                    if f1:
                        day_readings_t1 = [f1]

                elif "Epiphany of" in day_tag_raw:
                    day_tag = day_tag_raw
                    day_label = "Epiphany of the Lord"
                    day_is_special = True
                    if f1:
                        day_readings_t1 = [f1]

                elif "(a.m.)" in day_tag_raw:
                    day_tag = "(a.m.)"
                    day_label = "(a.m.)"
                    day_is_special = True
                    if f1:
                        day_readings_t1 = [f1]

                elif re_sunday_name.match(day_tag_raw) or "Sunday" in day_tag_raw:
                    day_tag = "Su"
                    day_label = day_tag_raw
                    if f1:
                        day_readings_t1 = [f1]

                elif "Monday" in day_tag_raw and "Holy Week" in day_tag_raw:
                    day_tag = day_tag_raw
                    day_label = day_tag_raw
                elif "Tuesday" in day_tag_raw and "Holy Week" in day_tag_raw:
                    day_tag = day_tag_raw
                    day_label = day_tag_raw
                elif "Wednesday" in day_tag_raw and "Holy Week" in day_tag_raw:
                    day_tag = day_tag_raw
                    day_label = day_tag_raw
                elif "Good Friday" in day_tag_raw:
                    day_tag = day_tag_raw
                    day_label = day_tag_raw
                elif "Holy Saturday" in day_tag_raw:
                    day_tag = day_tag_raw
                    day_label = day_tag_raw
                elif "Resurrection" in day_tag_raw:
                    day_tag = day_tag_raw
                    day_label = day_tag_raw
                elif "Easter Evening" in day_tag_raw:
                    day_tag = day_tag_raw
                    day_label = day_tag_raw
                elif "Ascension" in day_tag_raw:
                    day_tag = day_tag_raw
                    day_label = day_tag_raw
                else:
                    # Catch-all: treat as a label
                    day_tag = day_tag_raw
                    day_label = day_tag_raw

        elif tab_count >= 2:
            # Reading line — but check for embedded Sunday labels first
            first_field = fields[0].strip()
            is_sunday_label = False
            if re_sunday_name.match(first_field) or (
                "Sunday" in first_field and (
                    "December" in first_field or "January" in first_field or
                    "February" in first_field or "after" in first_field
                )
            ):
                is_sunday_label = True

            if is_sunday_label:
                # This is a Sunday label line masquerading as a reading line.
                # Flush current day and start a new Sunday entry.
                if day_tag:
                    flush_day()
                day_tag = "Su"
                day_label = first_field
                day_season = current_season
                day_week = current_week
                day_is_two_track = False
                day_is_special = False
                day_readings_t1 = []
                day_readings_t2 = []
                continue

            if not day_tag:
                continue

            if day_is_two_track:
                non_empty = [i for i, f in enumerate(fields) if f.strip()]
                t1 = fields[0].strip()
                t2_idx = non_empty[-1] if non_empty and non_empty[-1] > 0 else None
                t2 = fields[t2_idx].strip() if t2_idx is not None else ""
                if t1:
                    day_readings_t1.append(t1)
                if t2:
                    day_readings_t2.append(t2)
            else:
                reading = first_field
                if reading:
                    day_readings_t1.append(reading)

    flush_day()
    return blocks


def is_citation(text):
    """Check if text looks like a Scripture citation (book chapter:verse)."""
    return bool(re.match(r"^(?:Psalm|\d+\s*)?[A-Za-z]+\s+\d+:\d+", text.strip()))


def _is_date_range_label(text):
    """Check if text looks like a date range label (e.g. 'May 24-28', 'May 29--June 4')."""
    t = text.strip()
    months = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    # Single month: "Month Day-Day" or "Month Day—Day"
    single = rf"^{months}\s+\d+\s*[—–\-]+\s*\d+$"
    # Two months: "Month Day--Month Day" or "Month Day—Month Day"  
    two = rf"^{months}\s+\d+\s*[—–\-]+\s*{months}\s+\d+$"
    return bool(re.match(single, t) or re.match(two, t))


def normalize_citation(cite):
    """Normalize a Scripture citation for comparison."""
    c = cite.strip()
    c = re.sub(r"\s+", " ", c)
    c = re.sub(r"[—–]", "-", c)
    return c


def _resolve_date(block, bounds, prev_date=None):
    """Resolve a template block to a calendar date. Returns date or None."""
    season = block.get("season")
    week = block.get("week")
    tag = block.get("day_tag", "")
    label = block.get("label", "")
    advent_year = bounds["advent_1"].year

    day_offset = {"Th": -3, "F": -2, "Sa": -1, "Su": 0, "M": 1, "Tu": 2, "T": 2, "W": 3}

    season_sundays = {
        ("Advent", 1): bounds["advent_1"],
        ("Advent", 2): bounds["advent_2"],
        ("Advent", 3): bounds["advent_3"],
        ("Advent", 4): bounds["advent_4"],
        ("Lent", 1): bounds["lent_1"],
        ("Lent", 2): bounds["lent_2"],
        ("Lent", 3): bounds["lent_3"],
        ("Lent", 4): bounds["lent_4"],
        ("Lent", 5): bounds["lent_5"],
        ("Lent", 6): bounds.get("palm_sunday"),
        ("Easter", 1): bounds["easter"],
        ("Easter", 2): bounds["easter_2"],
        ("Easter", 3): bounds["easter_3"],
        ("Easter", 4): bounds["easter_4"],
        ("Easter", 5): bounds["easter_5"],
        ("Easter", 6): bounds["easter_6"],
        ("Easter", 7): bounds["easter_7"],
        ("Pentecost", 1): bounds["pentecost"],
        ("Trinity", 1): bounds["trinity"],
        ("Epiphany", 1): bounds["baptism"],
        ("Epiphany", 2): bounds["epiphany_2"],
        ("Epiphany", 3): bounds["epiphany_3"],
        ("Epiphany", 4): bounds["epiphany_4"],
        ("Epiphany", 5): bounds["epiphany_5"],
        ("Epiphany", 6): bounds["epiphany_6"],
        ("Epiphany", 7): bounds["epiphany_7"],
        ("Epiphany", 8): bounds["epiphany_8"],
        ("Epiphany", 9): bounds["epiphany_9"],
    }

    # --- Pass 1: weekday-tagged seasons with numbered weeks ---
    key = (season, week) if week else None
    if key and key in season_sundays and tag in day_offset:
        # Special case: Ash Wednesday
        if "Ash Wednesday" in (label or "") or "Ash Wed" in (tag or ""):
            return bounds.get("ash_wednesday")
        return season_sundays[key] + timedelta(days=day_offset[tag])

    # --- Pass 2: Easter week 7 special cases (Ascension) ---
    if season == "Easter" and week == 7:
        if "Ascension" in (tag or "") or "Ascension" in (label or ""):
            return bounds["ascension"]
        key = (season, week)
        if key in season_sundays and tag in day_offset:
            return season_sundays[key] + timedelta(days=day_offset[tag])

    # --- Pass 3: Holy Week / Easter Triduum ---
    if season == "HolyWeek":
        easter = bounds["easter"]
        tag_label = (tag or "") + " " + (label or "")
        tag_only = (tag or "")
        label_only = (label or "")

        if "Monday" in tag_label and "Holy Week" in tag_label:
            return easter - timedelta(days=6)
        if "Tuesday" in tag_label and "Holy Week" in tag_label:
            return easter - timedelta(days=5)
        if "Wednesday" in tag_label and "Holy Week" in tag_label:
            return easter - timedelta(days=4)
        if "Holy Thursday" in tag_label or "Maundy Thursday" in tag_label:
            return easter - timedelta(days=3)
        if "Good Friday" in tag_label or tag_only == "Good Friday":
            return easter - timedelta(days=2)
        if "Holy Saturday" in tag_label and ("Vigil" not in tag_label or "other than the Vigil" in tag_label):
            return easter - timedelta(days=1)
        if "Easter Vigil" in tag_label or ("Vigil" in tag_label and "Resurrection" in tag_label):
            return easter - timedelta(days=1)
        if "Resurrection" in tag_label and "Easter Day" in tag_label:
            return easter
        if "Easter Evening" in tag_label:
            return easter
        # M, Tu, W after Easter Sunday should be Easter week 1
        # But these get season=Easter, week=1 from the parser, not HolyWeek
        return None

    # --- Pass 4: Holy Week entries under Lent 6 (Mon-Wed of Holy Week) ---
    if season == "Lent" and week == 6:
        easter = bounds["easter"]
        tag_label = (tag or "") + " " + (label or "")

        # The Th/F/Sa before Palm Sunday are -7/-6/-5 from Palm Sunday
        # Palm Sunday = bounds["palm_sunday"]
        palm = bounds.get("palm_sunday", easter - timedelta(days=7))
        if tag in day_offset and not any(x in tag_label for x in ("Holy Week", "Monday", "Tuesday", "Wednesday")):
            return palm + timedelta(days=day_offset[tag])

        # Mon-Wed of Holy Week
        if "Monday" in tag_label and "Holy Week" in tag_label:
            return easter - timedelta(days=6)
        if "Tuesday" in tag_label and "Holy Week" in tag_label:
            return easter - timedelta(days=5)
        if "Wednesday" in tag_label and "Holy Week" in tag_label:
            return easter - timedelta(days=4)

        # Palms / Passion Sunday sub-entries
        if tag in ("Palms", "Passion"):
            return palm

        return None

    # --- Pass 4: Christmas fixed-date entries ---
    if season == "Christmas":
        return _resolve_christmas_date(tag, label, block.get("is_special"), bounds, prev_date)

    # --- Pass 5: Epiphany fixed-date entries ---
    if season == "Epiphany" and week is None:
        return _resolve_epiphany_fixed_date(tag, label, bounds)

    # --- Anything else ---
    return None


def _resolve_christmas_date(tag, label, is_special, bounds, prev_date):
    advent_year = bounds["advent_1"].year
    m = re.match(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d+)$", tag)
    if m:
        month_abbr = m.group(1)
        day_num = int(m.group(2))
        month_map = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
                     "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}
        month = month_map[month_abbr]
        yr = advent_year if month >= 11 else advent_year + 1
        return date(yr, month, day_num)

    if tag == "(a.m.)" and prev_date:
        return prev_date

    if tag.startswith("Nativity"):
        return date(advent_year, 12, 25)

    if "New Year" in tag or "Holy Name" in tag:
        return date(advent_year + 1, 1, 1)

    if "Epiphany of" in tag:
        return bounds.get("epiphany", date(advent_year + 1, 1, 6))

    if tag == "Su" or (label and "Sunday" in label):
        # Christmas Sunday entries (First/Second Sunday after Christmas)
        # provide Eucharistic readings, not daily office readings.
        # The date-tagged entries (Dec 26, 27, etc.) provide the daily office
        # readings and already cover these dates. Skip Sunday entries.
        return None

    return None


def _resolve_epiphany_fixed_date(tag, label, bounds):
    advent_year = bounds["advent_1"].year
    m = re.match(r"^(Jan)\s+(\d+)$", tag)
    if m:
        return date(advent_year + 1, 1, int(m.group(2)))
    if "Epiphany of" in tag:
        return bounds.get("epiphany", date(advent_year + 1, 1, 6))
    if tag == "Epiphany of the Lord":
        return bounds.get("epiphany", date(advent_year + 1, 1, 6))
    return None


def map_template_to_dates(blocks, bounds):
    """Map parsed template blocks to calendar dates.

    Multi-pass approach:
      1. Numbered-season blocks (Advent, Lent, Easter, Epiphany, Pentecost, Trinity)
         map using Sunday anchors + weekday offsets.
      2. Christmas fixed-date blocks (Dec 22-31, Jan 1-2) parse date strings.
      3. Epiphany fixed-date blocks (Jan 3-9) parse date strings.
      4. Holy Week blocks map using Easter offsets.
      5. Ordinary Time blocks walk forward sequentially from Trinity Thursday.
    """
    entries = []
    prev_date = None
    ordinary_blocks = []
    day_offset = {"Th": -3, "F": -2, "Sa": -1, "Su": 0, "M": 1, "Tu": 2, "T": 2, "W": 3}

    for block in blocks:
        season = block.get("season")
        if block.get("alternative_of"):
            continue
        if season == "TransfigurationAlt":
            continue
        if season == "Ordinary":
            ordinary_blocks.append(block)
            continue

        dt = _resolve_date(block, bounds, prev_date)
        if dt:
            prev_date = dt
            entry = _build_entry(block, dt)
            if entry:
                entries.append(entry)

    # Pass 5: Ordinary Time — sequential walk from Trinity Thursday
    trinity = bounds["trinity"]
    current_date = trinity + timedelta(days=4)  # Thursday after Trinity
    advent_next = bounds["advent_1_next"]

    for block in ordinary_blocks:
        tag = block.get("day_tag", "")
        if tag in day_offset and current_date < advent_next:
            entry = _build_entry(block, current_date)
            if entry:
                entries.append(entry)
            current_date += timedelta(days=1)

    entries.sort(key=lambda e: e["date"])
    return entries


def _build_entry(block, dt):
    """Build an output entry dict from a template block and calendar date."""
    date_str = dt.isoformat()

    track1 = block.get("track1", [])
    track2 = block.get("track2", [])

    if not track1 and not track2:
        return None

    # Normalize readings
    t1_readings = [normalize_citation(r) for r in track1 if r.strip()]
    t2_readings = [normalize_citation(r) for r in track2 if r.strip()]

    if not t1_readings:
        return None

    # Determine reading format:
    #   3 readings (weekday):  psalm, first_reading (OT), second_reading (NT)
    #   4 readings (Sunday/festival): OT, Psalm, NT/Epistle, Gospel
    #   2 readings:  psalm, first_reading (or just two readings)
    n = len(t1_readings)

    if n >= 4:
        # Sunday/festival format: index 1 is always the Psalm
        psalm = t1_readings[1]
        first_reading = t1_readings[0]
        second_reading = t1_readings[2]
        gospel = t1_readings[3] if n > 3 else ""
    elif n == 3:
        # Weekday format: index 0 is the psalm
        psalm = t1_readings[0]
        first_reading = t1_readings[1]
        second_reading = t1_readings[2]
        gospel = ""
    elif n == 2:
        psalm = t1_readings[0]
        first_reading = t1_readings[1]
        second_reading = ""
        gospel = ""
    elif n == 1:
        psalm = t1_readings[0]
        first_reading = ""
        second_reading = ""
        gospel = ""
    else:
        psalm = ""
        first_reading = ""
        second_reading = ""
        gospel = ""

    week_label = _make_week_label(block, dt)

    result = {
        "date": date_str,
        "week_label": week_label,
    }

    if block.get("two_track"):
        # For two-track entries, readings always have 3 elements (psalm + 2 readings)
        # Track 2 uses the same format as track 1
        t2_n = len(t2_readings)
        if t2_n >= 4:
            t2_psalm = t2_readings[1]
            t2_first = t2_readings[0]
            t2_second = t2_readings[2]
        elif t2_n == 3:
            t2_psalm = t2_readings[0]
            t2_first = t2_readings[1]
            t2_second = t2_readings[2]
        elif t2_n == 2:
            t2_psalm = t2_readings[0]
            t2_first = t2_readings[1]
            t2_second = ""
        elif t2_n == 1:
            t2_psalm = t2_readings[0]
            t2_first = ""
            t2_second = ""
        else:
            t2_psalm = ""
            t2_first = ""
            t2_second = ""
        result["track1"] = {
            "psalm": psalm,
            "first_reading": first_reading,
            "second_reading": second_reading,
        }
        result["track2"] = {
            "psalm": t2_psalm,
            "first_reading": t2_first,
            "second_reading": t2_second,
        }
    else:
        result["psalm"] = psalm
        result["first_reading"] = first_reading
        result["second_reading"] = second_reading

    if gospel:
        result["gospel"] = gospel

    return result


def _make_week_label(block, dt):
    """Create a human-readable week label."""
    season = block.get("season", "")
    week = block.get("week")
    tag = block.get("day_tag", "")
    label = block.get("label")

    weekday_name = WEEKDAY_NAMES.get(WEEKDAY_ABBR.get(tag, -1), tag)

    if label and "Sunday" in (label or ""):
        return label

    if season == "Advent" and week:
        return f"Advent {week} – {weekday_name}"
    if season == "Christmas":
        if label:
            return label
        return f"Christmas – {tag}"
    if season == "Epiphany":
        if week:
            return f"Epiphany {week} – {weekday_name}"
        if label:
            return label
        return f"Epiphany – {tag}"
    if season == "Lent" and week:
        return f"Lent {week} – {weekday_name}"
    if season == "HolyWeek":
        return label or f"Holy Week – {tag}"
    if season == "Easter":
        if week:
            return f"Easter {week} – {weekday_name}"
        return label or f"Easter – {tag}"
    if season == "Pentecost":
        return f"Pentecost – {weekday_name}" if weekday_name else "Pentecost"
    if season == "Trinity":
        return f"Trinity – {weekday_name}" if weekday_name else "Trinity"
    if season == "Ordinary":
        return f"Ordinary Time – {weekday_name}"
    if label:
        return label
    return f"{tag}"


def output_json(entries, output_dir):
    """Write entries to monthly JSON files."""
    os.makedirs(output_dir, exist_ok=True)
    by_month = defaultdict(dict)
    for entry in entries:
        date_str = entry["date"]
        month_key = date_str[:7]
        by_month[month_key][date_str] = entry

    for month_key, days in sorted(by_month.items()):
        out = {date_str: days[date_str] for date_str in sorted(days.keys())}
        filepath = os.path.join(output_dir, f"{month_key}.json")
        with open(filepath, "w") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)
        print(f"  Wrote {len(days)} days → {filepath}")


def verify_entries(entries, bounds):
    """Verify output integrity."""
    print(f"\nVerification — {len(entries)} total days extracted")

    # Check date coverage
    min_date = min(e["date"] for e in entries)
    max_date = max(e["date"] for e in entries)
    print(f"  Date range: {min_date} → {max_date}")

    # Count days with psalm/first/second readings
    with_readings = sum(1 for e in entries if e.get("psalm") or e.get("track1"))
    print(f"  Days with readings: {with_readings}")

    # Check for missing psalms
    missing_psalm = [e for e in entries
                     if not e.get("psalm") and not (e.get("track1") and e.get("track1", {}).get("psalm"))]
    if missing_psalm:
        print(f"  WARNING: {len(missing_psalm)} days missing psalm:")
        for e in missing_psalm[:10]:
            print(f"    {e['date']}: {e.get('week_label', '')}")

    # Count two-track days
    two_track = sum(1 for e in entries if e.get("track2") and e.get("track2", {}).get("psalm"))
    print(f"  Two-track days: {two_track}")

    # Verify contiguous dates (no gaps)
    dates = sorted(set(e["date"] for e in entries))
    gaps = []
    for i in range(len(dates) - 1):
        expected_next = date.fromisoformat(dates[i]) + timedelta(days=1)
        actual_next = date.fromisoformat(dates[i + 1])
        if expected_next != actual_next and expected_next < date.fromisoformat(dates[-1]):
            gaps.append((dates[i], dates[i + 1]))
    if gaps:
        print(f"  WARNING: {len(gaps)} date gaps:")
        for g in gaps[:20]:
            print(f"    {g[0]} → {g[1]}")
    else:
        print(f"  Date continuity: all dates contiguous")

    # Verify season bounds coverage
    key_dates = [
        ("Advent 1", bounds["advent_1"]),
        ("Christmas", bounds["christmas"]),
        ("Epiphany", bounds["epiphany"]),
        ("Ash Wednesday", bounds["ash_wednesday"]),
        ("Easter", bounds["easter"]),
        ("Pentecost", bounds["pentecost"]),
        ("Trinity", bounds["trinity"]),
        ("Christ the King", bounds["christ_the_king"]),
    ]
    entry_dates = set(e["date"] for e in entries)
    print(f"\n  Season boundary coverage:")
    for name, dt in key_dates:
        status = "✓" if dt.isoformat() in entry_dates else "✗"
        print(f"    {status} {name}: {dt.isoformat()}")

    return len(entries) > 0


def main():
    parser = argparse.ArgumentParser(description="Extract RCL Daily Readings from RTF")
    parser.add_argument("--year", type=int, help="Advent year (start of church year). Default: current year",
                        default=None)
    parser.add_argument("--rtf", type=str, help="Path to RTF source file",
                        default=None)
    parser.add_argument("--output-dir", type=str,
                        default=os.path.join(PROJECT_ROOT, "data", "rcl-daily"))
    parser.add_argument("--season-bounds", type=str,
                        help="Path to season_bounds.json (computed if not provided)")
    args = parser.parse_args()

    # Determine year
    if args.year:
        advent_year = args.year
    else:
        today = date.today()
        if today.month >= 11:
            advent_year = today.year
        else:
            advent_year = today.year - 1

    print(f"RCL Daily Extraction — Year B (church year {advent_year}–{advent_year + 1})")

    # Determine RTF path
    if args.rtf:
        rtf_path = args.rtf
    else:
        rtf_path = os.path.join(SOURCES_DIR, "rcl_year_b.rtf")

    if not os.path.exists(rtf_path):
        print(f"ERROR: RTF file not found: {rtf_path}")
        sys.exit(1)

    print(f"  Source: {rtf_path}")

    # Compute season bounds
    if args.season_bounds and os.path.exists(args.season_bounds):
        with open(args.season_bounds) as f:
            bounds_raw = json.load(f)
        # Convert string dates to date objects
        bounds = {}
        for k, v in bounds_raw.items():
            bounds[k] = date.fromisoformat(v)
        print(f"  Using season bounds from: {args.season_bounds}")
    else:
        bounds = compute_season_bounds(advent_year)
        print(f"  Computed season bounds (Easter: {bounds['easter']})")

    print(f"\n  Key bounds:")
    print(f"    Advent 1:      {bounds['advent_1']}")
    print(f"    Christmas:     {bounds['christmas']}")
    print(f"    Epiphany:      {bounds['epiphany']}")
    print(f"    Ash Wednesday: {bounds['ash_wednesday']}")
    print(f"    Easter:        {bounds['easter']}")
    print(f"    Pentecost:     {bounds['pentecost']}")
    print(f"    Trinity:       {bounds['trinity']}")
    print(f"    Christ King:   {bounds['christ_the_king']}")

    # Convert RTF to text
    print(f"\nConverting RTF → text...")
    text = rtf_to_text(rtf_path)

    # Parse template
    print(f"Parsing Year B template ({len(text)} chars)...")
    blocks = parse_rtf_template(text)
    print(f"  Parsed {len(blocks)} day entries")

    # Map to dates
    print(f"Mapping to calendar dates...")
    entries = map_template_to_dates(blocks, bounds)
    print(f"  Mapped {len(entries)} entries to dates")

    # Verify
    verify_entries(entries, bounds)

    # Output
    print(f"\nWriting JSON output...")
    output_json(entries, args.output_dir)

    print(f"\nDone. {len(entries)} days extracted to {args.output_dir}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
