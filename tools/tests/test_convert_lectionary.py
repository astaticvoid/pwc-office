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
    alternate_identity,
    detect_bounds,
    parse_lesson,
    parse_name_meta,
    parse_observances,
    parse_psalm_field,
    parse_single_office,
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


# ── parse_single_office ───────────────────────────────────────────────────────

class TestParseSingleOffice:
    def test_coll_above_pseudo_lesson_dropped(self):
        # BUG-26: "Coll above/below" is a propers cross-reference, not a lesson.
        office = parse_single_office("Ps 78:1-39; Num 14:26-45; Acts 15:1-12; Coll above")
        assert office["lessons"] == ["Num 14:26-45", "Acts 15:1-12"]

    def test_coll_below_with_parenthetical_dropped(self):
        office = parse_single_office(
            "Ps 63; Isa 40:25-31; Coll below (Eve of National Indigenous Day of Prayer)"
        )
        assert office["lessons"] == ["Isa 40:25-31"]

    def test_o_antiphon_pseudo_lesson_dropped(self):
        # BUG-33: "O Antiphon" is delivered as a typed note, not a lesson.
        office = parse_single_office("Ps 89:1-29; Isa 9:2-7; 2 Pet 1:1-11; O Antiphon")
        assert office["lessons"] == ["Isa 9:2-7", "2 Pet 1:1-11"]


# ── parse_observances ─────────────────────────────────────────────────────────

class TestParseObservances:
    """ADR 0017: observances are extracted from every line of the CSV name
    column, not hand-transcribed per date."""

    def test_phrase_marker(self):
        assert parse_observances("Day of discipline and self-denial") == ["fast_day"]

    def test_marker_after_br(self):
        assert parse_observances(
            "Clement of Alexandria, Priest, c. 210 - Com (Violet or Blue)<br>"
            "Day of discipline and self-denial"
        ) == ["fast_day"]

    def test_eve_without_article(self):
        assert parse_observances("Eve of Advent II (Violet or Blue)") == ["eve_of:Advent II"]

    def test_eve_with_article(self):
        assert parse_observances("Eve of the Epiphany (White or Gold)") == ["eve_of:the Epiphany"]

    def test_eve_colon_target(self):
        assert parse_observances(
            "Eve of the Sunday of the Passion: Palm Sunday (Red)"
        ) == ["eve_of:the Sunday of the Passion: Palm Sunday"]

    def test_eve_bracket_decoration(self):
        assert parse_observances(
            "Eve of Ascension Sunday (White or Gold) [if kept on Sunday]"
        ) == ["eve_of:Ascension Sunday", "ascension_sunday_option"]

    def test_eve_of_sunday_ignored(self):
        # Most Saturdays carry "Eve of Sunday" — a plain eve, not an observance.
        assert parse_observances("Feria (Green)<br>Eve of Sunday (Green)") is None

    def test_primary_line_marker(self):
        # National Indigenous Day of Prayer is the entire primary line on its
        # date — the classifier must see all lines, not just line 2+.
        assert parse_observances(
            "National Indigenous Day of Prayer (Green or other appropriate colour)"
        ) == ["national_indigenous_day_of_prayer"]

    def test_eve_companion(self):
        assert parse_observances(
            "Feria (Green)<br>Eve of Harvest Thanksgiving (White)"
        ) == ["eve_of:Harvest Thanksgiving", "harvest_thanksgiving"]

    def test_corpus_christi_eve_has_no_companion(self):
        # Structurally identical to the Ascension eve line, but the source data
        # carries no same-date companion (ADR 0017 point 5 judgment call).
        assert parse_observances(
            "Eve of Corpus Christi (White) [if also celebrated on Sunday]"
        ) == ["eve_of:Corpus Christi"]

    def test_line_order_preserved(self):
        assert parse_observances(
            "World Day of Prayer<br>Day of discipline and self-denial"
        ) == ["world_day_of_prayer", "fast_day"]

    def test_separator_and_commemoration_ignored(self):
        assert parse_observances(
            "Philip Lindel Tsen, Bishop of Honan, 1954 - Com (Violet)<br>"
            "And / or<br>"
            "Paul Shinji Sasaki, Bishop of Mid-Japan & Tokyo, 1946 - Com (Violet)"
        ) is None

    def test_easter_eve(self):
        assert parse_observances(
            "Holy Saturday (Red)<br>Day of discipline and self-denial<br>"
            "Easter Eve (White or Gold)"
        ) == ["fast_day", "easter_eve"]

    def test_all_saints_eve(self):
        # The gap the hand-written dict missed (issue #56 comment); the
        # extractor finds it automatically.
        assert parse_observances(
            "Saints of the Reformation Era - Com (Green)<br>"
            "Eve of All Saints\u2019 Day (White or Gold)"
        ) == ["eve_of:All Saints\u2019 Day"]

    def test_civil_marker_remembrance_day(self):
        assert parse_observances(
            "Martin, Bishop of Tours, 397 - Mem (White)<br>"
            "Remembrance Day (Violet or Black)"
        ) == ["remembrance_day"]

    def test_civil_marker_new_year_day(self):
        # CSV uses U+2019; the phrase vocabulary is ASCII.
        assert parse_observances(
            "The Naming of Jesus - HD (White)<br>New Year\u2019s Day<br>"
            "Within the Octave of Christmas"
        ) == ["new_year_day", "octave_of_christmas"]

    def test_civil_marker_accession_day(self):
        assert parse_observances(
            "Nativity of the Blessed Virgin Mary - Mem (White)<br>"
            "Accession Day of HM King Charles III (Green)<br>Season of Creation"
        ) == ["accession_day", "season_of_creation"]

    def test_unknown_eve_target_warns(self, capsys):
        assert parse_observances("Eve of the Nativity (White)") is None
        assert "unrecognized" in capsys.readouterr().err

    def test_rephrased_marker_warns(self, capsys):
        # ADR 0017 negative consequence: ACC rephrasing a marker must warn
        # rather than silently dropping the line.
        assert parse_observances("Day of fasting and self-denial") is None
        assert "similar to" in capsys.readouterr().err

    def test_distant_unmatched_line_is_silent(self, capsys):
        assert parse_observances(
            "Florence Nightingale, Nurse, Social Reformer, 1910 - Com (White)"
        ) is None
        assert capsys.readouterr().err == ""


# ── alternate_identity ────────────────────────────────────────────────────────

class TestAlternateIdentity:
    """ADR 0018: office alternates carry the alternate observance's identity."""

    def test_feria_match(self):
        assert alternate_identity(
            "Feria", ["Feria in Christmastide (White)", "Within the Octave of Christmas"]
        ) == {"colour": "White", "optional": False, "rank": "feria"}

    def test_feria_adjective_form(self):
        # "Easter Feria" does not begin with "Feria" but is still a feria.
        assert alternate_identity(
            "Feria", ["Easter Feria (White)"]
        ) == {"colour": "White", "optional": False, "rank": "feria"}

    def test_corpus_christi_match(self):
        assert alternate_identity(
            "Corpus Christi",
            ["The Most Holy Body and Blood of Christ or Corpus Christi (White) "
             "[if also celebrated on Sunday]"],
        ) == {"colour": "White", "optional": True}

    def test_eve_of_ascension(self):
        assert alternate_identity(
            "Eve of the Ascension",
            ["Eve of Ascension Sunday (White or Gold) [if kept on Sunday]"],
        ) == {"colour": "White or Gold", "optional": True, "rank": "feria"}

    def test_no_containment_returns_none(self):
        # "Christmas II" does not appear in "Second Sunday after Christmas".
        assert alternate_identity(
            "Christmas II", ["Second Sunday after Christmas (White)"]
        ) is None

    def test_empty_label_returns_none(self):
        assert alternate_identity("", ["Feria (Green)"]) is None

    def test_apostrophe_normalized(self):
        assert alternate_identity(
            "New Year's Day", ["New Year\u2019s Day"]
        ) == {"optional": False}


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
