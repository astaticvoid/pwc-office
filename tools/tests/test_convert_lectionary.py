"""
Unit tests for convert_lectionary.py parsing functions.

Run: python3 -m pytest tools/tests/ -v
     (from the repo root)
"""
import sys
from pathlib import Path

# Allow importing from tools/ without installing a package.
sys.path.insert(0, str(Path(__file__).parent.parent))

from convert_lectionary import (
    parse_name_meta,
    parse_psalm_field,
    parse_lesson,
    detect_bounds,
)


# ── parse_name_meta ───────────────────────────────────────────────────────────

class TestParseNameMeta:
    def test_plain_feria(self):
        name, rank, colour = parse_name_meta("Wednesday")
        assert name == "Wednesday"
        assert rank == "feria"
        assert colour == ""

    def test_sunday_gets_holy_day_rank(self):
        name, rank, colour = parse_name_meta("Second Sunday of Advent")
        assert rank == "holy_day"

    def test_principal_feast(self):
        # CSV uses " - PF" for Principal Feast
        name, rank, colour = parse_name_meta("Easter Day - PF")
        assert rank == "principal_feast"
        assert "Easter" in name

    def test_colour_extracted(self):
        name, rank, colour = parse_name_meta("Ash Wednesday (Violet/Lenten Array)")
        assert colour == "Violet/Lenten Array"
        assert "Ash Wednesday" in name

    def test_colour_and_suffix_together(self):
        # CSV uses " - Com" for Commemoration
        name, rank, colour = parse_name_meta("St Anselm - Com (White)")
        assert colour == "White"
        assert rank == "commemoration"
        assert "Anselm" in name

    def test_bracket_stripped(self):
        # Content in square brackets (e.g., alternate name) is stripped.
        name, rank, colour = parse_name_meta("Ordinary Time [After Pentecost]")
        assert "[" not in name

    def test_multiline_uses_first_line(self):
        name, rank, colour = parse_name_meta("Palm Sunday\nSunday of the Passion")
        assert "Palm Sunday" in name
        # Second line should not appear in name
        assert "Passion" not in name


# ── parse_psalm_field ─────────────────────────────────────────────────────────

class TestParsePsalmField:
    def test_single_psalm(self):
        result = parse_psalm_field("Ps 23")
        assert result == {"psalms": ["23"]}

    def test_single_psalm_with_verses(self):
        result = parse_psalm_field("Ps 119:1-16")
        assert result == {"psalms": ["119:1-16"]}

    def test_multiple_psalms(self):
        result = parse_psalm_field("Ps 1, 2, 3")
        assert result == {"psalms": ["1", "2", "3"]}

    def test_optional_psalm_in_parens(self):
        result = parse_psalm_field("Ps 139:1-17, (18-23)")
        psalms = result["psalms"]
        # "18-23" becomes "139:18-23" (continuation), marked optional
        assert any(
            isinstance(p, dict) and p.get("optional") and "139:18-23" in p["citation"]
            for p in psalms
        ), f"Expected optional continuation in {psalms}"

    def test_or_split_gives_psalm_sets(self):
        result = parse_psalm_field("Ps 1 or 2")
        assert "psalm_sets" in result
        assert len(result["psalm_sets"]) == 2

    def test_no_ps_prefix_returns_empty(self):
        result = parse_psalm_field("23")
        assert result == {}

    def test_empty_string_returns_empty(self):
        result = parse_psalm_field("")
        assert result == {}

    def test_optional_bracket_group(self):
        result = parse_psalm_field("Ps [4, 5]")
        psalms = result["psalms"]
        assert all(isinstance(p, dict) and p.get("optional") for p in psalms)


# ── parse_lesson ──────────────────────────────────────────────────────────────

class TestParseLesson:
    def test_plain_citation(self):
        assert parse_lesson("John 1:1-14") == "John 1:1-14"

    def test_empty_returns_none(self):
        assert parse_lesson("") is None
        assert parse_lesson("   ") is None

    def test_optional_in_parens(self):
        result = parse_lesson("(Rev 21:1-5)")
        assert isinstance(result, dict)
        assert result["citation"] == "Rev 21:1-5"
        assert result["optional"] is True

    def test_fixes_colon_separator(self):
        # "Mt: 22:23-33" → "Mt 22:23-33"
        assert parse_lesson("Mt: 22:23-33") == "Mt 22:23-33"

    def test_fixes_period_chapter_separator(self):
        # "Gal 4.21-31" → "Gal 4:21-31"
        assert parse_lesson("Gal 4.21-31") == "Gal 4:21-31"

    def test_whitespace_stripped(self):
        assert parse_lesson("  Isa 40:1-11  ") == "Isa 40:1-11"


# ── detect_bounds ─────────────────────────────────────────────────────────────

class TestDetectBounds:
    """
    detect_bounds() scans CSV rows for liturgical boundary dates.
    Each row is [date_str, name_col, ...].
    """

    def _rows(self, *entries):
        """Build minimal rows from (date, name) pairs."""
        return [[date, name] for date, name in entries]

    def test_advent_i(self):
        rows = self._rows(("2025-11-30", "First Sunday of Advent"))
        bounds = detect_bounds(rows)
        assert bounds.get("advent_i") == "2025-11-30"

    def test_advent_ii(self):
        rows = self._rows(
            ("2025-11-30", "First Sunday of Advent"),
            ("2026-11-29", "First Sunday of Advent"),
        )
        bounds = detect_bounds(rows)
        assert bounds.get("advent_i") == "2025-11-30"
        assert bounds.get("advent_ii") == "2026-11-29"

    def test_christmas(self):
        rows = self._rows(("2025-12-25", "The Birth of the Lord (Christmas Day)  Principal Feast"))
        bounds = detect_bounds(rows)
        assert bounds.get("christmas") == "2025-12-25"

    def test_epiphany(self):
        rows = self._rows(("2026-01-11", "The Baptism of the Lord"))
        bounds = detect_bounds(rows)
        assert bounds.get("epiphany") == "2026-01-11"

    def test_ash_wednesday(self):
        rows = self._rows(("2026-02-18", "Ash Wednesday"))
        bounds = detect_bounds(rows)
        assert bounds.get("ash_wednesday") == "2026-02-18"

    def test_passiontide(self):
        rows = self._rows(("2026-03-22", "Fifth Sunday in Lent (Passion Sunday)"))
        bounds = detect_bounds(rows)
        assert bounds.get("passiontide") == "2026-03-22"

    def test_easter(self):
        rows = self._rows(("2026-04-05", "Easter Day  Principal Feast"))
        bounds = detect_bounds(rows)
        assert bounds.get("easter") == "2026-04-05"

    def test_pentecost(self):
        rows = self._rows(("2026-05-24", "The Day of Pentecost"))
        bounds = detect_bounds(rows)
        assert bounds.get("pentecost") == "2026-05-24"

    def test_trinity_sunday(self):
        rows = self._rows(("2026-05-31", "Trinity Sunday"))
        bounds = detect_bounds(rows)
        assert bounds.get("trinity_sunday") == "2026-05-31"

    def test_all_saints(self):
        rows = self._rows(("2026-11-01", "All Saints' Day  Principal Feast"))
        bounds = detect_bounds(rows)
        assert bounds.get("all_saints") == "2026-11-01"

    def test_ignores_non_date_rows(self):
        rows = [["not-a-date", "Header"], ["2026-04-05", "Easter Day  Principal Feast"]]
        bounds = detect_bounds(rows)
        assert bounds.get("easter") == "2026-04-05"

    def test_full_year(self):
        """All 8 required keys present from a realistic row set."""
        rows = self._rows(
            ("2025-11-30", "First Sunday of Advent"),
            ("2025-12-25", "The Birth of the Lord"),
            ("2026-01-11", "The Baptism of the Lord"),
            ("2026-02-18", "Ash Wednesday"),
            ("2026-04-05", "Easter Day  Principal Feast"),
            ("2026-05-24", "The Day of Pentecost"),
            ("2026-05-31", "Trinity Sunday"),
            ("2026-11-01", "All Saints' Day"),
        )
        bounds = detect_bounds(rows)
        required = ['advent_i', 'christmas', 'epiphany', 'ash_wednesday',
                    'easter', 'pentecost', 'trinity_sunday', 'all_saints']
        for key in required:
            assert key in bounds, f"Missing required bound: {key}"
