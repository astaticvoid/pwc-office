"""
Unit tests for convert_lectionary.py parsing functions.

Run: python3 -m pytest tools/tests/ -v
     (from the repo root)
"""
import sys
from pathlib import Path

# Allow importing from tools/ without installing a package.
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from convert_lectionary import (
    alternate_identity,
    detect_bounds,
    eve_identity,
    is_calendar_name,
    parse_commemorations,
    parse_extra,
    parse_lesson,
    parse_name_meta,
    parse_observances,
    parse_psalm_field,
    parse_single_office,
    unjoined_co_commemorations,
    unlabelled_alternates,
    unmatched_eve_offices,
    untyped_note_dates,
)

ROOT = Path(__file__).resolve().parent.parent.parent

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

    def test_a_branch_naming_itself_before_its_psalms_is_labelled(self):
        office = parse_single_office(
            "Eve of Corpus Christi: Ps 110, 111; Ex 16:2-15; Jn 6:22-35; Coll 304"
        )
        assert office["label"] == "Eve of Corpus Christi"
        assert office["psalms"] == ["110", "111"]

    def test_a_branch_naming_itself_before_a_cross_reference_is_labelled(self):
        # The name is a name whatever field follows it (#131).
        office = parse_single_office(
            "Feria: As Proper 9, except: 2 Tim 1:1-12; Ps 123; Mk 12:18-27"
        )
        assert office["label"] == "Feria"
        assert office["note"] == "As Proper 9, except: 2 Tim 1:1-12"
        assert office["psalms"] == ["123"]

    def test_a_psalm_verse_range_is_not_a_label(self):
        office = parse_single_office("Ps 119:1-24; Am 3:12-4:5; 2 Pet 3:1-10")
        assert "label" not in office
        assert office["psalms"] == ["119:1-24"]

    def test_a_clause_carrying_a_colon_is_not_a_label(self):
        # Without the name in front, "As Proper 9, except:" must not be read as
        # one — the comma is what separates a clause from a name.
        office = parse_single_office(
            "As Proper 9, except: 2 Tim 1:1-12; Ps 123; Mk 12:18-27"
        )
        assert "label" not in office

    def test_the_pick_two_marker_is_read_as_a_count_not_as_the_branch_prefix(self):
        # The marker ends in a colon, so a branch opening with it satisfies the
        # prefix pattern; the count is read first so there is nothing left for
        # the prefix rule to take.
        office = parse_single_office(
            "Two of the following three readings: Jon 2:2-9; Eph 6:10-20; Jn 11:17-27"
        )
        assert office["lessons_pick"] == 2
        assert "label" not in office and "rubric" not in office
        assert office["lessons"] == ["Jon 2:2-9", "Eph 6:10-20", "Jn 11:17-27"]

    def test_a_named_branch_keeps_both_its_name_and_the_pick_two_marker(self):
        office = parse_single_office(
            "Eve of Corpus Christi: Ps 110; "
            "Two of the following three readings: Jon 2:2-9; Eph 6:10-20; Jn 11:17-27"
        )
        assert office["label"] == "Eve of Corpus Christi"
        assert office["lessons_pick"] == 2

    def test_a_rubric_in_the_prefix_is_a_rubric_not_a_label(self):
        # #132: the prefix slot holds whatever the branch opens with. Only a
        # calendar name belongs in `label`.
        office = parse_single_office(
            "This office is only to be used before the Great Vigil: "
            "Ps 27; (Job 19:21-27a); Rom 8:1-11; Coll 320"
        )
        assert office["rubric"] == "This office is only to be used before the Great Vigil"
        assert "label" not in office

    def test_a_prefix_rubric_does_not_become_a_lesson(self):
        # Leaving it in the text would hand the lesson renderer a sentence.
        office = parse_single_office(
            "This office is only to be used before the Great Vigil: "
            "Ps 27; (Job 19:21-27a); Rom 8:1-11; Coll 320"
        )
        assert office["lessons"] == [
            {"citation": "Job 19:21-27a", "optional": True}, "Rom 8:1-11"
        ]
        assert office["psalms"] == ["27"]


class TestIsCalendarName:
    """#132: a name is capitalised but for its particles; a rubric is a
    sentence. The two arrive in the same position and must be told apart."""

    @pytest.mark.parametrize("prefix", [
        "Feria",
        "Corpus Christi",
        "Eve of Saint Peter and Saint Paul",   # the longest name shipped
        "Eve of the Transfiguration",
        "Proper 10",
        "Easter VII",
        "Uganda",
    ])
    def test_calendar_names(self, prefix):
        assert is_calendar_name(prefix)

    @pytest.mark.parametrize("prefix", [
        "This office is only to be used before the Great Vigil",
        "This office may be said before the Vigil",
    ])
    def test_rubrics(self, prefix):
        assert not is_calendar_name(prefix)

    def test_every_label_the_shipped_csv_produces_is_a_name(self):
        # The classifier decides what reaches `label`, so the corpus is the
        # check on it: a rubric slipping through would be set as a caption.
        import csv as _csv
        import re as _re

        from convert_lectionary import RE_OR_SPLIT, clean

        paths = sorted((ROOT / "sources").glob("bas_short_*.csv"))
        if not paths:
            pytest.skip("no sources/bas_short_*.csv in this checkout")
        labels = set()
        for path in paths:
            with open(path, newline="", encoding="utf-8") as f:
                for row in _csv.reader(f, quoting=_csv.QUOTE_MINIMAL):
                    if len(row) < 5 or not _re.match(r"\d{4}-\d{2}-\d{2}", row[0].strip()):
                        continue
                    for idx in (3, 4):
                        for branch in RE_OR_SPLIT.split(clean(row[idx])):
                            office = parse_single_office(branch.strip())
                            if "label" in office:
                                labels.add(office["label"])
        assert labels, "expected the CSV to produce labels"
        assert {name for name in labels if not is_calendar_name(name)} == set()


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
        # An eve ranks `eve`, not `feria` (#128): it is not standing in for a
        # feria, and 2026-01-03 puts an eve on both sides of one toggle.
        assert alternate_identity(
            "Eve of the Ascension",
            ["Eve of Ascension Sunday (White or Gold) [if kept on Sunday]"],
        ) == {"colour": "White or Gold", "optional": True, "rank": "eve"}

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


# \u2500\u2500 eve_identity \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

class TestEveIdentity:
    """#128: an eve in the primary slot carries its own identity."""

    def test_containment_match(self):
        assert eve_identity(
            "Eve of Saint Mary",
            ["Dietrich Bonhoeffer and Maximilien Kolbe, Martyrs, 1945, 1941 - Com (Green)",
             "Day of discipline and self-denial",
             "Eve of Saint Mary the Virgin (White)"],
        ) == {"colour": "White", "rank": "eve",
              "title": "Eve of Saint Mary the Virgin"}

    def test_sole_eve_line_when_containment_fails(self):
        # ACC abbreviates in the office column and does not in the name column;
        # neither string contains the other.
        assert eve_identity(
            "Eve of Saint John the Baptist",
            ["Feria (Green)", "Eve of the Birth of Saint John the Baptist (White)"],
        ) == {"colour": "White", "rank": "eve",
              "title": "Eve of the Birth of Saint John the Baptist"}

    def test_two_eve_lines_keep_containment(self):
        # 2026-01-03 names two eves; the fallback must not pick arbitrarily.
        lines = ["Christmas Feria (White)",
                 "Eve of the Epiphany (White or Gold) [if kept on Sunday]",
                 "Eve of Christmas II (White)"]
        assert eve_identity("Eve of Epiphany", lines)["title"] == "Eve of the Epiphany"
        assert eve_identity("Eve of Christmas II", lines)["title"] == "Eve of Christmas II"

    def test_optional_is_dropped(self):
        # The bracket belongs to the alternate toggle; an eve in the primary
        # slot has no toggle to be optional within.
        assert "optional" not in eve_identity(
            "Eve of Epiphany",
            ["Eve of the Epiphany (White or Gold) [if kept on Sunday]"],
        )

    def test_non_eve_match_returns_none(self):
        # Containment can land on a line that is not an eve at all; there is
        # no eve identity to take from it.
        assert eve_identity("Eve of Sunday", ["Feria (Green)"]) is None

    def test_no_line_returns_none(self):
        assert eve_identity("Eve of Saint Mary", ["Feria (Green)"]) is None


# \u2500\u2500 parse_extra \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

class TestParseExtra:
    """#127: a cell carrying two kinds of note yields one note per kind."""

    def test_single_type_keeps_the_cell_whole(self):
        assert parse_extra(
            "Note: The DOL provides two sets of readings for evening prayer.",
            "2026-08-14",
        ) == [{"type": "source_note",
               "text": "Note: The DOL provides two sets of readings for evening prayer."}]

    def test_empty_cell(self):
        assert parse_extra("", "2026-08-14") is None

    def test_list_type_splits_on_br_runs(self):
        # 2026-06-28 fused a precedence rule and its sourcing into one cell;
        # typing the cell as a whole suppressed both.
        notes = parse_extra(
            "Eve of Precedence: The first Eve takes precedence.<br><br>"
            "Note: The DOL does not provide readings for it.",
            "2026-06-28",
        )
        assert notes == [
            {"type": "precedence_rule",
             "text": "Eve of Precedence: The first Eve takes precedence."},
            {"type": "source_note",
             "text": "Note: The DOL does not provide readings for it."},
        ]

    def test_single_br_splits_too(self):
        # 2025-12-29 separates its two notes with one <br>, not two.
        assert [n["type"] for n in parse_extra("First.<br>Second.", "2025-12-29")] \
            == ["source_note", "source_note"]

    def test_segment_count_mismatch_is_fatal(self):
        # A silent off-by-one would retype every note after the change.
        with pytest.raises(SystemExit, match="re-split the cell"):
            parse_extra("Only one segment.", "2026-06-28")

    def test_untyped_date_defaults_to_pastoral(self):
        # The default is why untyped_note_dates gates extraction: on its own it
        # would file a new year's apparatus notes as customs to observe.
        assert parse_extra("Gaudete Sunday: rose vestments.", "2026-03-01") \
            == [{"type": "pastoral", "text": "Gaudete Sunday: rose vestments."}]


# ── untyped_note_dates ────────────────────────────────────────────────────────

class TestUntypedNoteDates:
    """The intake gate: NOTE_TYPES is per-date and carries to no new year."""

    def _row(self, date_str, extra):
        return [date_str, "Feria (Green)", "", "", "", extra]

    def test_a_new_years_note_is_reported(self):
        rows = {"2027-08-14": self._row("2027-08-14", "Note: The DOL provides two sets.")}
        assert untyped_note_dates(rows) == [
            ("2027-08-14", ["Note: The DOL provides two sets."])
        ]

    def test_segments_are_split_for_the_worklist(self):
        # The reporter shows the shape so the entry can be typed per segment.
        rows = {"2027-06-28": self._row("2027-06-28", "One rule.<br><br>Two sourcing.")}
        assert untyped_note_dates(rows)[0][1] == ["One rule.", "Two sourcing."]

    def test_a_typed_date_is_not_reported(self):
        rows = {"2026-08-14": self._row("2026-08-14", "Note: anything.")}
        assert untyped_note_dates(rows) == []

    def test_a_date_with_no_note_is_not_reported(self):
        rows = {"2027-08-14": self._row("2027-08-14", "   ")}
        assert untyped_note_dates(rows) == []

    def test_the_current_csv_is_fully_typed(self):
        # The gate must pass on shipped data or it is not a gate, it is a wall.
        import csv as _csv
        import re as _re
        rows = {}
        for path in sorted((ROOT / "sources").glob("bas_short_*.csv")):
            with open(path, newline="", encoding="utf-8") as f:
                for row in _csv.reader(f, quoting=_csv.QUOTE_MINIMAL):
                    if len(row) >= 5 and _re.match(r"\d{4}-\d{2}-\d{2}", row[0].strip()):
                        rows[row[0].strip()] = row
        if not rows:
            pytest.skip("no sources/bas_short_*.csv in this checkout")
        assert untyped_note_dates(rows) == []


# ── unmatched_eve_offices ─────────────────────────────────────────────────────

class TestUnmatchedEveOffices:
    """The eve gate (#128): an 'Eve of …' office label with no matching name
    line blocks extraction — shared by main()'s gate and the intake tool."""

    def _row(self, name, morning="", evening=""):
        return ["2026-08-14", name, "", morning, evening, ""]

    def test_an_unmatched_eve_office_is_reported(self):
        rows = {"2026-08-14": self._row(
            "Feria (Green)",
            morning="Eve of Saint Mary the Virgin: Ps 45; Prov 8:22-31; Coll 536",
        )}
        assert unmatched_eve_offices(rows) == [
            ("2026-08-14", "morning", "Eve of Saint Mary the Virgin",
             ["Feria (Green)"])
        ]

    def test_an_eve_that_matches_a_name_line_is_not_reported(self):
        rows = {"2026-08-14": self._row(
            "Eve of Saint Mary the Virgin (Blue)",
            morning="Eve of Saint Mary the Virgin: Ps 45; Prov 8:22-31; Coll 536",
        )}
        assert unmatched_eve_offices(rows) == []

    def test_a_non_eve_office_is_not_reported(self):
        rows = {"2026-08-14": self._row(
            "Feria (Green)",
            morning="Ps 45; Prov 8:22-31; Coll 536",
        )}
        assert unmatched_eve_offices(rows) == []

    def test_the_current_csv_has_no_unmatched_eves(self):
        # The gate must pass on shipped data or it is not a gate, it is a wall.
        import csv as _csv
        import re as _re
        rows = {}
        for path in sorted((ROOT / "sources").glob("bas_short_*.csv")):
            with open(path, newline="", encoding="utf-8") as f:
                for row in _csv.reader(f, quoting=_csv.QUOTE_MINIMAL):
                    if len(row) >= 5 and _re.match(r"\d{4}-\d{2}-\d{2}", row[0].strip()):
                        rows[row[0].strip()] = row
        if not rows:
            pytest.skip("no sources/bas_short_*.csv in this checkout")
        assert unmatched_eve_offices(rows) == []


# ── parse_commemorations ──────────────────────────────────────────────────────

class TestParseCommemorations:
    """#129: a ranked line after the first names someone else the day
    remembers. Whether it stands equal to the day is read from rank+colour."""

    def test_a_day_naming_one_observance_has_no_commemorations(self):
        assert parse_commemorations("Wednesday (Green)") == ([], "")

    def test_the_day_is_line_one_even_when_it_carries_no_rank(self):
        # An Ember day has no rank suffix and still governs the line under it,
        # so standing is judged against the day rather than against the first
        # line that happens to be ranked.
        raw = ("Rogation Day (Violet or White)\n"
               "Florence Nightingale, Nurse, Social Reformer, 1910 - Com (White)")
        commemorations, join = parse_commemorations(raw)
        assert commemorations == [{
            "name": "Florence Nightingale, Nurse, Social Reformer, 1910",
            "rank": "commemoration", "colour": "White",
        }]
        assert join == ""

    def test_two_commemorations_under_an_unranked_day_are_not_coequal(self):
        # Both match each other; neither matches the day, which is what counts.
        raw = ("Lenten Ember Day (Violet)\n"
               "George Herbert, Priest and Poet, 1633 - Com (Violet)\n"
               "Another Commemoration - Com (Violet)\n"
               "Or Both Together")
        commemorations, join = parse_commemorations(raw)
        assert [c.get("coequal") for c in commemorations] == [None, None]
        assert join == ""

    def test_a_commemoration_under_a_holy_day_is_not_coequal(self):
        raw = ("The Holy Innocents - HD (Red)\n"
               "Thomas Becket, Archbishop of Canterbury, 1170 - Com (White)")
        commemorations, join = parse_commemorations(raw)
        assert commemorations == [{
            "name": "Thomas Becket, Archbishop of Canterbury, 1170",
            "rank": "commemoration", "colour": "White",
        }]
        assert join == ""

    def test_two_commemorations_of_one_rank_and_colour_are_coequal(self):
        raw = ("John Wyclyf, Reformer, 1384 - Com (Green)\n"
               "Jan Hus, Reformer, 1415 - Com (Green)\n"
               "Or Both Together")
        commemorations, join = parse_commemorations(raw)
        assert commemorations[0]["coequal"] is True
        assert join == "or"

    def test_the_join_is_read_from_between_the_pair_too(self):
        # "And / or" sits between the two lines; "Or Both Together" after them.
        raw = ("Philip Lindel Tsen, Bishop of Honan, 1954 - Com (Violet)\n"
               "And / or\n"
               "Paul Shinji Sasaki, Bishop of Mid-Japan & Tokyo, 1946 - Com (Violet)")
        commemorations, join = parse_commemorations(raw)
        assert commemorations[0]["coequal"] is True
        assert join == "and / or"

    def test_a_coequal_pair_with_an_unread_joining_returns_no_word(self):
        raw = ("John Wyclyf, Reformer, 1384 - Com (Green)\n"
               "Jan Hus, Reformer, 1415 - Com (Green)\n"
               "Or Either Of Them")
        commemorations, join = parse_commemorations(raw)
        assert commemorations[0]["coequal"] is True
        assert join == ""          # the gate reports it rather than guessing


class TestUnjoinedCoCommemorations:
    """The co-commemoration gate (#129): naming one of two equal days is the
    app choosing for the reader, so an unread joining blocks extraction."""

    def _row(self, name):
        return ["2026-10-30", name, "", "Ps 1", "Ps 2", ""]

    def test_an_unread_joining_is_reported(self):
        rows = {"2026-10-30": self._row(
            "John Wyclyf, Reformer, 1384 - Com (Green)\n"
            "Jan Hus, Reformer, 1415 - Com (Green)\n"
            "Or Either Of Them")}
        reported = unjoined_co_commemorations(rows)
        assert [d for d, _ in reported] == ["2026-10-30"]

    def test_a_known_joining_is_not_reported(self):
        rows = {"2026-10-30": self._row(
            "John Wyclyf, Reformer, 1384 - Com (Green)\n"
            "Jan Hus, Reformer, 1415 - Com (Green)\n"
            "Or Both Together")}
        assert unjoined_co_commemorations(rows) == []

    def test_a_subordinate_commemoration_needs_no_joining(self):
        rows = {"2026-10-30": self._row(
            "The Holy Innocents - HD (Red)\n"
            "Thomas Becket, Archbishop of Canterbury, 1170 - Com (White)")}
        assert unjoined_co_commemorations(rows) == []

    def test_the_current_csv_has_no_unjoined_co_commemorations(self):
        # The gate must pass on shipped data or it is not a gate, it is a wall.
        import csv as _csv
        import re as _re
        rows = {}
        for path in sorted((ROOT / "sources").glob("bas_short_*.csv")):
            with open(path, newline="", encoding="utf-8") as f:
                for row in _csv.reader(f, quoting=_csv.QUOTE_MINIMAL):
                    if len(row) >= 5 and _re.match(r"\d{4}-\d{2}-\d{2}", row[0].strip()):
                        rows[row[0].strip()] = row
        if not rows:
            pytest.skip("no sources/bas_short_*.csv in this checkout")
        assert unjoined_co_commemorations(rows) == []


# ── unlabelled_alternates ─────────────────────────────────────────────────────

class TestUnlabelledAlternates:
    """The alternate-label gate (#131): a toggle whose second slot has no name
    offers the choice as "Alternate" and keeps the day's colour and rank."""

    def _row(self, morning="", evening=""):
        return ["2026-06-03", "Feria (Green)", "", morning, evening, ""]

    def test_an_unnamed_alternate_is_reported(self):
        rows = {"2026-06-03": self._row(
            morning="Ps 116:10-17; Heb 10:32-39\nOr\nAs Proper 9; Ps 123; Mk 12:18-27",
        )}
        assert unlabelled_alternates(rows) == [
            ("2026-06-03", "morning", "As Proper 9; Ps 123; Mk 12:18-27")
        ]

    def test_a_named_alternate_is_not_reported(self):
        rows = {"2026-06-03": self._row(
            morning="Ps 116:10-17; Heb 10:32-39\nOr\nFeria: As Proper 9; Ps 123",
        )}
        assert unlabelled_alternates(rows) == []

    def test_an_office_with_no_alternate_is_not_reported(self):
        rows = {"2026-06-03": self._row(morning="Ps 116:10-17; Heb 10:32-39")}
        assert unlabelled_alternates(rows) == []

    def test_the_current_csv_has_no_unlabelled_alternates(self):
        # The gate must pass on shipped data or it is not a gate, it is a wall.
        import csv as _csv
        import re as _re
        rows = {}
        for path in sorted((ROOT / "sources").glob("bas_short_*.csv")):
            with open(path, newline="", encoding="utf-8") as f:
                for row in _csv.reader(f, quoting=_csv.QUOTE_MINIMAL):
                    if len(row) >= 5 and _re.match(r"\d{4}-\d{2}-\d{2}", row[0].strip()):
                        rows[row[0].strip()] = row
        if not rows:
            pytest.skip("no sources/bas_short_*.csv in this checkout")
        assert unlabelled_alternates(rows) == []


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
