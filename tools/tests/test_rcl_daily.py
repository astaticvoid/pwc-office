"""
Unit tests for RCL Daily lectionary extraction.

Run: python3 -m pytest tools/tests/test_rcl_daily.py -v
"""

import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from extract_rcl_daily import (
    compute_season_bounds,
    easter_date,
    advent_sunday,
    parse_rtf_template,
    rtf_to_text,
    is_citation,
    _is_date_range_label,
    _resolve_date,
    normalize_citation,
)


# ── Easter date calculation ──────────────────────────────────────────────────

class TestEasterDate:
    def test_easter_2027(self):
        d = easter_date(2027)
        assert d == date(2027, 3, 28)

    def test_easter_2026(self):
        d = easter_date(2026)
        assert d == date(2026, 4, 5)

    def test_easter_2025(self):
        d = easter_date(2025)
        assert d == date(2025, 4, 20)

    def test_easter_2024(self):
        d = easter_date(2024)
        assert d == date(2024, 3, 31)


class TestAdventSunday:
    def test_advent_2026(self):
        d = advent_sunday(2026)
        assert d == date(2026, 11, 29)

    def test_advent_2025(self):
        d = advent_sunday(2025)
        assert d == date(2025, 11, 30)

    def test_advent_2027(self):
        d = advent_sunday(2027)
        assert d == date(2027, 11, 28)


# ── Season bounds ────────────────────────────────────────────────────────────

class TestSeasonBounds:
    def test_all_keys_present(self):
        bounds = compute_season_bounds(2026)
        required = [
            "advent_1", "christmas", "epiphany", "baptism",
            "ash_wednesday", "easter", "pentecost", "trinity",
            "christ_the_king", "advent_1_next"
        ]
        for k in required:
            assert k in bounds, f"Missing key: {k}"

    def test_bounds_are_dates(self):
        bounds = compute_season_bounds(2026)
        for k, v in bounds.items():
            assert isinstance(v, date), f"{k} is not a date: {v!r}"

    def test_church_year_order(self):
        bounds = compute_season_bounds(2026)
        order = [
            "advent_1", "christmas", "epiphany", "ash_wednesday",
            "easter", "pentecost", "trinity", "christ_the_king", "advent_1_next"
        ]
        prev = None
        for key in order:
            if key in bounds:
                if prev:
                    assert bounds[key] > prev, f"{key} must be after {prev}"
                prev = bounds[key]

    def test_lent_ash_wed_relation(self):
        bounds = compute_season_bounds(2026)
        assert bounds["ash_wednesday"] + timedelta(days=4) == bounds["lent_1"]


# ── Citation detection ─────────────────────────────────────────────────────

class TestIsCitation:
    def test_psalm(self):
        assert is_citation("Psalm 80:1-7, 17-19")

    def test_book_chapter(self):
        assert is_citation("Zechariah 13:1-9")

    def test_numbered_book(self):
        assert is_citation("1 Corinthians 1:3-9")

    def test_range(self):
        assert is_citation("Mark 13:24-37")

    def test_not_citation(self):
        assert not is_citation("First Sunday of Advent")


class TestIsDateRangeLabel:
    def test_single_month(self):
        assert _is_date_range_label("May 24-28")
        assert _is_date_range_label("November 6-12")

    def test_two_months(self):
        assert _is_date_range_label("May 29--June 4")
        assert _is_date_range_label("June 26—July 2")

    def test_three_months_false(self):
        assert not _is_date_range_label("Psalm 80:1-7")
        assert not _is_date_range_label("Zechariah 13:1-9")
        assert not _is_date_range_label("Revelation 14:6-13")


class TestNormalizeCitation:
    def test_spaces(self):
        assert normalize_citation("  Psalm  80:1-7  ") == "Psalm 80:1-7"

    def test_em_dash(self):
        assert normalize_citation("Luke 2:1—20") == "Luke 2:1-20"


# ── RTF parsing ─────────────────────────────────────────────────────────────

def _load_blocks():
    """Helper to load parsed blocks from the Year B RTF."""
    rtf_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "sources", "rcl", "rcl_year_b.rtf"
    )
    text = rtf_to_text(rtf_path)
    return parse_rtf_template(text)


class TestParseRtfTemplate:
    def test_parses_entries(self):
        blocks = _load_blocks()
        assert len(blocks) > 300, f"Expected >300 blocks, got {len(blocks)}"

    def test_advent_entries(self):
        blocks = _load_blocks()
        advent = [b for b in blocks if b.get("season") == "Advent"]
        assert len(advent) > 0
        weeks = set(b.get("week") for b in advent)
        assert weeks == {1, 2, 3, 4}

    def test_lent_entries(self):
        blocks = _load_blocks()
        lent = [b for b in blocks if b.get("season") == "Lent"]
        assert len(lent) > 0
        weeks = set(b.get("week") for b in lent)
        for w in [1, 2, 3, 4, 5, 6]:
            assert w in weeks, f"Missing Lent week {w}"

    def test_christmas_entries(self):
        blocks = _load_blocks()
        christmas = [b for b in blocks if b.get("season") == "Christmas"]
        assert len(christmas) > 0
        tags = [b.get("day_tag") for b in christmas]
        assert "Dec 25" in tags

    def test_easter_entries(self):
        blocks = _load_blocks()
        easter = [b for b in blocks if b.get("season") == "Easter"]
        assert len(easter) > 0

    def test_ordinary_entries(self):
        blocks = _load_blocks()
        ordinary = [b for b in blocks if b.get("season") == "Ordinary"]
        assert len(ordinary) > 150

    def test_weekday_readings_have_three(self):
        """Weekday entries should have psalm + 2 readings (3 total)."""
        blocks = _load_blocks()
        weekday_entries = [
            b for b in blocks
            if b.get("day_tag") in ("Th", "F", "Sa", "M", "Tu", "T", "W")
            and b.get("season") not in ("Ordinary",)
            and not b.get("two_track")
        ]
        for b in weekday_entries[:20]:
            t1 = b.get("track1", [])
            assert len(t1) == 3, (
                f"{b.get('season')} {b.get('week')} {b.get('day_tag')}: "
                f"expected 3 readings, got {len(t1)}: {t1}"
            )

    def test_sunday_readings_have_four(self):
        """Sunday entries should have 4 readings (OT, Psalm, NT, Gospel)."""
        blocks = _load_blocks()
        sunday_entries = [
            b for b in blocks
            if b.get("day_tag") == "Su"
            and b.get("season") in ("Advent", "Lent", "Easter", "Epiphany", "Pentecost", "Trinity")
        ]
        for b in sunday_entries[:15]:
            t1 = b.get("track1", [])
            label = b.get("label", "")
            # Skip entries that are "Palms" alternatives
            if "Vigil" in label:
                continue
            assert len(t1) == 4, (
                f"{b.get('season')} {b.get('week')}: "
                f"expected 4 readings, got {len(t1)}: {t1}"
            )

    def test_no_empty_readings(self):
        """No block should have empty strings mixed with real readings."""
        blocks = _load_blocks()
        for b in blocks:
            t1 = b.get("track1", [])
            t2 = b.get("track2", [])
            for r in t1:
                assert r.strip(), f"Empty reading in {b.get('day_tag')} {b.get('label')}"
            for r in t2:
                assert r.strip(), f"Empty track2 reading in {b.get('day_tag')} {b.get('label')}"

    def test_two_track_entries_have_t2(self):
        """Two-track entries should have track2 content."""
        blocks = _load_blocks()
        two_track = [b for b in blocks if b.get("two_track")]
        assert len(two_track) > 50
        empty_t2 = [b for b in two_track if not b.get("track2")]
        assert len(empty_t2) == 0, f"{len(empty_t2)} two-track entries have empty track2"


# ── Date resolution ─────────────────────────────────────────────────────────

class TestResolveDate:
    def setup_method(self):
        self.bounds = compute_season_bounds(2026)

    def _find_block(self, season, day_tag, label_contains=None):
        blocks = _load_blocks()
        for b in blocks:
            if b.get("season") == season and b.get("day_tag") == day_tag:
                if label_contains:
                    if label_contains in str(b.get("label", "")):
                        return b
                else:
                    return b
        return None

    def test_advent_1_thursday(self):
        b = self._find_block("Advent", "Th")
        assert b is not None
        dt = _resolve_date(b, self.bounds, None)
        assert dt == date(2026, 11, 26)

    def test_advent_1_sunday(self):
        b = self._find_block("Advent", "Su", "First Sunday")
        assert b is not None
        dt = _resolve_date(b, self.bounds, None)
        assert dt == date(2026, 11, 29)

    def test_christmas_day(self):
        b = self._find_block("Christmas", "Dec 25")
        assert b is not None
        dt = _resolve_date(b, self.bounds, None)
        assert dt == date(2026, 12, 25)

    def test_epiphany(self):
        b = self._find_block("Epiphany", "Jan 6")
        if b is None:
            b = self._find_block("Christmas", "Jan 6")
        if b is None:
            blocks = _load_blocks()
            for b2 in blocks:
                if "Epiphany" in str(b2.get("label", "")) and "Jan" in str(b2.get("day_tag", "")):
                    b = b2
                    break
        assert b is not None
        dt = _resolve_date(b, self.bounds, None)
        assert dt == date(2027, 1, 6)

    def test_ash_wednesday(self):
        b = self._find_block("Lent", "W", "Ash Wednesday")
        assert b is not None
        dt = _resolve_date(b, self.bounds, None)
        assert dt == date(2027, 2, 10)

    def test_easter_sunday(self):
        b = self._find_block("HolyWeek", "Su", "Easter Day")
        if b is None:
            b = self._find_block("Easter", "Su", "Resurrection")
        assert b is not None
        dt = _resolve_date(b, self.bounds, None)
        assert dt == date(2027, 3, 28)

    def test_pentecost(self):
        b = self._find_block("Pentecost", "Su", "Pentecost")
        assert b is not None
        dt = _resolve_date(b, self.bounds, None)
        assert dt == date(2027, 5, 16)


# ── End-to-end: run extraction and validate output ──────────────────────────

class TestExtractionOutput:
    def test_output_exists(self):
        output_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "data", "rcl-daily"
        )
        assert os.path.isdir(output_dir), f"Output directory not found: {output_dir}"
        files = os.listdir(output_dir)
        json_files = [f for f in files if f.endswith(".json")]
        assert len(json_files) >= 12, f"Expected >=12 monthly files, got {len(json_files)}"

    def test_output_is_valid_json(self):
        output_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "data", "rcl-daily"
        )
        for fname in os.listdir(output_dir):
            if fname.endswith(".json"):
                with open(os.path.join(output_dir, fname)) as f:
                    data = json.load(f)
                assert isinstance(data, dict), f"{fname} is not a dict"
                for date_str, entry in data.items():
                    assert isinstance(entry, dict), f"{fname}/{date_str} is not a dict"
                    assert "date" in entry, f"{fname}/{date_str} missing date"
                    assert entry["date"] == date_str, (
                        f"{fname}/{date_str} date mismatch: {entry['date']}"
                    )
