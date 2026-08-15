"""
Unit tests for extract_fats.py bio parsing.

Run: .venv/bin/python3 -m pytest tools/tests/ -v
     (from the repo root) — same command as the make test-tools tier.
"""
import sys
from pathlib import Path

# Allow importing from tools/ without installing a package.
sys.path.insert(0, str(Path(__file__).parent.parent))

from extract_fats import (  # noqa: E402, I001
    _description_from_header,
    _fats_keys,
    _normalize_citation,
    _page_text_without_margin_artifacts,
    _restore_title_space,
    parse_bio,
    parse_propers,
)


class _FakePage:
    """Minimal fitz.Page stand-in: plain text plus span geometry."""

    def __init__(self, text: str, spans: list[tuple[float, str]]):
        self._text = text
        # spans: (bbox_x0, span_text). Only bbox[0] is semantically relevant
        # — the helper drops spans whose x0 < 0; the other bbox coordinates
        # are dummy constants.
        self._spans = [{"bbox": [x0, 0, x0 + 10, 10], "text": t} for x0, t in spans]

    def get_text(self, spec: str = "") -> str | dict:
        if spec == "dict":
            return {"blocks": [{"lines": [{"spans": self._spans}]}]}
        return self._text


# ── _page_text_without_margin_artifacts ────────────────────────────────────────

class TestPageTextWithoutMarginArtifacts:
    def test_no_off_page_spans_returns_text_unchanged(self):
        page = _FakePage("Martin\n11 November\nbio line", [])
        assert (
            _page_text_without_margin_artifacts(page)
            == "Martin\n11 November\nbio line"
        )

    def test_drops_line_that_is_exactly_an_artifact(self):
        # 'y' is the January drop-cap remnant; the corrupted first line is 'y'.
        page = _FakePage("y\nMartin\n11 November\nbio line", [(-2.0, "y")])
        assert (
            _page_text_without_margin_artifacts(page)
            == "Martin\n11 November\nbio line"
        )

    def test_keeps_legitimate_line_containing_artifact_text(self):
        # A real line 'Yesterday' must not be dropped just because a stray
        # 'y' span sits off-page — the match is exact, not substring.
        page = _FakePage(
            "Yesterday\nMartin\n11 November\nbio line",
            [(-2.0, "y")],
        )
        assert (
            _page_text_without_margin_artifacts(page)
            == "Yesterday\nMartin\n11 November\nbio line"
        )

    def test_multi_artifact_page_drops_each(self):
        page = _FakePage(
            "mber\ny\nMartin\n11 November\nbio line",
            [(-2.0, "mber"), (-5.0, "y")],
        )
        assert (
            _page_text_without_margin_artifacts(page)
            == "Martin\n11 November\nbio line"
        )


# ── parse_bio ─────────────────────────────────────────────────────────────────

class TestParseBio:
    def test_basic_bio(self):
        page = "\n".join([
            "Martin",
            "11 November",
            "Bishop of Tours, 397 — Memorial",
            "Today the Church honours Martin, a fourth-century bishop of",
            "Tours who was filled with power from on high.",
        ])
        bio = parse_bio(page)
        assert bio is not None
        assert bio["name"] == "Martin"
        assert bio["date"] == "November 11"
        assert bio["rank"] == "memorial"
        assert bio["bio"].startswith("Today the Church honours Martin")

    def test_em_dash_prose_does_not_truncate_bio(self):
        # Regression: an em-dash in the bio prose ("citizens — all these")
        # used to be read as a rank line, cutting the first paragraph off the
        # bio (Canada Day, July 1).
        page = "\n".join([
            "Canada Day",
            "1 July",
            "Canada Day is a national holiday, not a feast of the Church; and",
            "yet it is right that we Christians offer prayer and thanksgiving",
            "today, because all the good things which we enjoy as Canadi-",
            "ans have their origin as gifts of God. The resources of our land",
            "and the oceans which border it, our diversity as Canadian peo-",
            "ple, the heritage of Confederation and our nation's continuing",
            "efforts to ensure peace and justice for all its citizens — all these",
            "things call the Church to remember and celebrate the God who",
            "gave them.",
        ])
        bio = parse_bio(page)
        assert bio is not None
        assert bio["bio"].startswith("Canada Day is a national holiday")
        assert "citizens — all these" in bio["bio"]

    def test_em_dash_rank_line_still_ends_header(self):
        # The fix must not break the real rank-line case.
        page = "\n".join([
            "Saint Stephen",
            "26 December",
            "Deacon and Martyr — Holy Day",
            "Saint Stephen, full of grace and power, did great wonders",
        ])
        bio = parse_bio(page)
        assert bio is not None
        assert bio["rank"] == "holy_day"
        assert bio["bio"].startswith("Saint Stephen, full of grace")

    def test_no_rank_leaves_rank_none(self):
        page = "\n".join([
            "Canada Day",
            "1 July",
            "Canada Day is a national holiday, not a feast of the Church.",
        ])
        bio = parse_bio(page)
        assert bio is not None
        assert bio["rank"] is None

    def test_em_dash_unknown_suffix_in_header_keeps_scanning(self):
        # An em-dash whose suffix is NOT a rank word (a descriptor line,
        # not bio prose) must not end the header scan — the real rank line
        # that follows on its own line must still be found.
        page = "\n".join([
            "Clement",
            "23 November",
            "Bishop of Rome, c. 100 — early father",
            "Memorial",
            "Clement wrote a letter to the Corinthians",
        ])
        bio = parse_bio(page)
        assert bio is not None
        assert bio["rank"] == "memorial"
        assert bio["bio"].startswith("Clement wrote a letter")

    def test_description_is_extracted(self):
        page = "\n".join([
            "Augustine",
            "26 May",
            "First Archbishop of Canterbury, 605 — Memorial",
            "Today we remember Augustine, the first archbishop of",
        ])
        bio = parse_bio(page)
        assert bio is not None
        assert bio["description"] == "First Archbishop of Canterbury, 605"

    def test_no_description_when_rank_is_bare(self):
        page = "\n".join([
            "The Epiphany of the Lord",
            "6 January",
            "Principal Feast",
            "Today we commemorate an episode which is recorded",
        ])
        bio = parse_bio(page)
        assert bio is not None
        assert bio["description"] == ""

    def test_wrapped_either_note_continuation_is_not_name(self):
        # Regression (#105): the "Either X or Y may be commemorated" note wraps
        # to a second line ("...may be commemo-\nrated on this day."); the
        # continuation was read as part of the name.
        page = "\n".join([
            "Either Philip Lindel Tsen or Paul Shinji Sasaki (p. 92) may be commemo-",
            "rated on this day.",
            "Philip Lindel Tsen",
            "24 February",
            "Memorial",
            "Philip Lindel Tsen was born in 1885.",
        ])
        bio = parse_bio(page)
        assert bio is not None
        assert bio["name"] == "Philip Lindel Tsen"
        assert bio["date"] == "February 24"
        assert bio["bio"].startswith("Philip Lindel Tsen was born")

    def test_wrapped_either_note_continuation_this_date(self):
        # The other wrap shape: "...may be commemorated on\nthis date."
        page = "\n".join([
            "Either Marguerite Bourgeoys or John Horden (p. 50) may be commemorated on",
            "this date.",
            "Marguerite Bourgeoys",
            "12 January",
            "Commemoration",
            "Marguerite Bourgeoys was born in France.",
        ])
        bio = parse_bio(page)
        assert bio is not None
        assert bio["name"] == "Marguerite Bourgeoys"

    def test_title_space_restored_before_saint(self):
        # Regression (#105): the bold heading arrives as a single span with the
        # space before the title dropped by the PDF text layer ("ofSaint").
        page = "\n".join([
            "The Confession ofSaint Peter the Apostle",
            "18 January",
            "Holy Day",
            "Today we commemorate the confession of Peter.",
        ])
        bio = parse_bio(page)
        assert bio is not None
        assert bio["name"] == "The Confession of Saint Peter the Apostle"


# ── _restore_title_space ─────────────────────────────────────────────────────

class TestRestoreTitleSpace:
    def test_restores_space_before_saint(self):
        assert _restore_title_space("The Confession ofSaint Peter the Apostle") \
            == "The Confession of Saint Peter the Apostle"

    def test_leaves_spaced_saint_untouched(self):
        assert _restore_title_space("Companions of Saint Paul") \
            == "Companions of Saint Paul"

    def test_does_not_split_mcdonald(self):
        # A generic lower→upper insertion would mangle this; the title-specific
        # rule must leave it alone.
        assert _restore_title_space("Robert McDonald") == "Robert McDonald"


# ── _description_from_header ──────────────────────────────────────────────────

class TestDescriptionFromHeader:
    def test_rank_on_same_line(self):
        assert _description_from_header(
            ["First Archbishop of Canterbury, 605 — Memorial"]
        ) == "First Archbishop of Canterbury, 605"

    def test_wrapped_rank_on_next_line(self):
        assert _description_from_header(
            ["Religious, Founder of the Society, 1915", "— Commemoration"]
        ) == "Religious, Founder of the Society, 1915"

    def test_wrapped_rank_with_trailing_dash(self):
        assert _description_from_header(
            ["Religious, Founder of the Sisterhood, 1921 —", "Commemoration"]
        ) == "Religious, Founder of the Sisterhood, 1921"

    def test_bare_rank_has_no_description(self):
        assert _description_from_header(["Principal Feast"]) == ""

    def test_empty_header_has_no_description(self):
        assert _description_from_header([]) == ""


# ── _fats_keys ────────────────────────────────────────────────────────────────

class TestFatsKeys:
    def test_unique_name_keys_on_itself(self):
        assert _fats_keys([("Martin", "Bishop of Tours, 397", "November 11")]) \
            == ["Martin"]

    def test_colliding_names_are_disambiguated_by_description(self):
        keys = _fats_keys([
            ("Augustine", "First Archbishop of Canterbury, 605", "May 26"),
            ("Augustine", "Bishop of Hippo, Teacher of the Faith, 430",
             "August 28"),
        ])
        assert keys == [
            "Augustine, First Archbishop of Canterbury, 605",
            "Augustine, Bishop of Hippo, Teacher of the Faith, 430",
        ]

    def test_collision_without_description_falls_back_to_date(self):
        keys = _fats_keys([
            ("John", "", "May 6"),
            ("John", "", "December 27"),
        ])
        assert keys == ["John (May 6)", "John (December 27)"]


# ── _normalize_citation ───────────────────────────────────────────────────────

class TestNormalizeCitation:
    def test_dot_becomes_colon(self):
        assert _normalize_citation("Numbers 6.22-27") == "Numbers 6:22-27"

    def test_en_dash_becomes_hyphen(self):
        assert _normalize_citation("Numbers 6.22–27") == "Numbers 6:22-27"

    def test_verse_list_keeps_every_span(self):
        assert _normalize_citation("Isaiah 32.1–5, 16–18") == "Isaiah 32:1-5, 16-18"

    def test_cross_chapter_range_takes_the_em_dash(self):
        # parseRanges reads the em dash as the cross-chapter marker; a hyphen
        # here would make "1 John 1:5-2:2" a verse range within chapter 1.
        assert _normalize_citation("1 John 1.5–2.2") == "1 John 1:5—2:2"

    def test_cross_chapter_and_verse_range_on_one_line(self):
        assert (_normalize_citation("Acts 6.8–7.2a, 51c–60")
                == "Acts 6:8—7:2a, 51c-60")

    def test_numbered_book_is_untouched(self):
        assert _normalize_citation("2 Timothy 1.13–14, 2.1–3") == "2 Timothy 1:13-14, 2:1-3"

    def test_semicolon_separated_spans(self):
        assert (_normalize_citation("Acts 11.19–30; 13.1–3")
                == "Acts 11:19-30; 13:1-3")

    def test_cross_chapter_range_starting_on_a_part_verse(self):
        # The lookbehind has to admit the part-verse letter: read as a verse
        # range, "15:51c-16:2" loses 16:2 in parseRanges.
        assert (_normalize_citation("1 Corinthians 15.51c–16.2")
                == "1 Corinthians 15:51c—16:2")

    def test_cross_chapter_range_written_with_an_ascii_hyphen(self):
        # The book is not consistent about which dash a range carries — "Psalm
        # 119.89-96" is printed with a hyphen — so the dash cannot be what marks
        # a range as crossing chapters.
        assert _normalize_citation("1 John 1.5-2.2") == "1 John 1:5—2:2"

    def test_ascii_hyphen_within_a_chapter_is_left_alone(self):
        assert _normalize_citation("119.89-96") == "119:89-96"

    def test_canticle_has_nothing_to_normalize(self):
        assert _normalize_citation("Canticle 6 (Seek the Lord)") == "Canticle 6 (Seek the Lord)"


# ── parse_propers ─────────────────────────────────────────────────────────────

def _propers(*lines: str) -> str:
    """A propers page carrying only the readings block the tests care about."""
    return "\n".join(["Readings", *lines, "Prayer over the Gifts", "Gracious God,"])


class TestParsePropers:
    def test_readings_psalm_and_refrain_are_separated(self):
        p = parse_propers(_propers(
            "Wisdom 7.7–10, 15–16",
            "Psalm 27.1–6, 12–13",
            "Refrain",
            "Your face, O Lord, will I seek.",
            "John 5.19–24",
        ))
        assert p["readings"] == ["Wisdom 7:7-10, 15-16", "John 5:19-24"]
        assert p["psalm"] == "27:1-6, 12-13"
        assert p["refrain"] == "Your face, O Lord, will I seek."

    def test_alternative_refrain_pointer_is_not_a_reading(self):
        p = parse_propers(_propers(
            "Numbers 6.22–27",
            "Psalm 67",
            "Refrain",
            "May God give us his blessing.",
            "Or v. 1 or CR 4",
            "Luke 2.15–21",
        ))
        assert p["readings"] == ["Numbers 6:22-27", "Luke 2:15-21"]
        assert p["refrain"] == "May God give us his blessing."

    def test_alternative_reading_shares_the_pointer_word(self):
        # "Or Isaiah 52.7–10" opens like a refrain pointer and is a reading.
        p = parse_propers(_propers(
            "Or Isaiah 52.7–10",
            "Psalm 98",
            "Refrain",
            "As above",
            "Or v. 5 or CR 3",
            "Hebrews 1.1–12",
        ))
        assert p["readings"] == ["Or Isaiah 52:7-10", "Hebrews 1:1-12"]
        assert p["refrain"] == "As above"

    def test_wrapped_refrain_is_joined(self):
        p = parse_propers(_propers(
            "Revelation 7.9–17",
            "Psalm 34.1–10",
            "Refrain",
            "Taste and see that the Lord is good; happy are they who",
            "trust in him.",
            "Or v. 9 or Alleluia!",
            "1 John 3.1–3",
        ))
        assert p["refrain"] == ("Taste and see that the Lord is good; "
                                "happy are they who trust in him.")
        assert p["readings"] == ["Revelation 7:9-17", "1 John 3:1-3"]

    def test_pointer_starting_on_the_refrain_line_and_wrapping(self):
        # "…to the poor. Or v. 9 or" / "Alleluia!" — the pointer begins on the
        # refrain's own line and finishes on the next, which is neither refrain
        # nor reading.
        p = parse_propers(_propers(
            "Job 29.11–16",
            "Psalm 112",
            "Refrain",
            "Happy are they who have given to the poor. Or v. 9 or",
            "Alleluia!",
            "Matthew 25.31–40",
        ))
        assert p["refrain"] == "Happy are they who have given to the poor."
        assert p["readings"] == ["Job 29:11-16", "Matthew 25:31-40"]

    def test_pointer_starting_on_a_continuation_line(self):
        # The wrap and the pointer are each in the corpus; together they are
        # not. Read as a reading, the leftover ships as a citation of nothing.
        p = parse_propers(_propers(
            "Revelation 7.9–17",
            "Psalm 34.1–10",
            "Refrain",
            "Taste and see that the Lord is good; happy are they who",
            "trust in him. Or v. 9 or",
            "Alleluia!",
            "1 John 3.1–3",
        ))
        assert p["refrain"] == ("Taste and see that the Lord is good; "
                                "happy are they who trust in him.")
        assert p["readings"] == ["Revelation 7:9-17", "1 John 3:1-3"]

    def test_finished_refrain_does_not_swallow_the_heading_below_it(self):
        p = parse_propers(_propers(
            "Daniel 7.1–3, 15–18",
            "Psalm 149",
            "Refrain",
            "Sing to the Lord a new song.",
            "Optional Readings",
            "Luke 6.20–36",
        ))
        assert p["refrain"] == "Sing to the Lord a new song."
        assert p["readings"] == ["Daniel 7:1-3, 15-18", "Luke 6:20-36"]

    def test_pointerless_refrain_ends_without_terminal_punctuation(self):
        # "As above" finishes there — nothing below it continues it.
        p = parse_propers(_propers(
            "Isaiah 62.6–7, 10–12",
            "Psalm 97",
            "Refrain",
            "As above",
            "Or v. 11 or CR 3",
            "Titus 3.4–7",
        ))
        assert p["refrain"] == "As above"
        assert p["readings"] == ["Isaiah 62:6-7, 10-12", "Titus 3:4-7"]

    def test_appendix_heading_with_a_colon(self):
        p = parse_propers(_propers(
            "I John 4.7–12",
            "Psalm 34.1–8",
            "Refrain:",
            "Taste and see that the Lord is good.",
            "Matthew 25.31–40",
        ))
        assert p["refrain"] == "Taste and see that the Lord is good."
        assert p["readings"] == ["I John 4:7-12", "Matthew 25:31-40"]

    def test_appendix_heading_carrying_the_refrain_itself(self):
        p = parse_propers(_propers(
            "Psalm 116.1–12",
            "Refrain Common Refrain 7: Behold, I come to do your will, O God.",
            "Galatians 3.23–28",
            "Luke 10.1–9",
        ))
        assert p["refrain"] == "Common Refrain 7: Behold, I come to do your will, O God."
        assert p["readings"] == ["Galatians 3:23-28", "Luke 10:1-9"]

    def test_set_markers_and_headings_are_not_readings(self):
        p = parse_propers(_propers(
            "A",
            "Revelation 21.1–6a",
            "Psalm 24.1–6",
            "Refrain",
            "The Lord of hosts, he is the King of glory.",
            "John 11.32–44",
            "Optional Readings",
            "Titus 3.4–7",
        ))
        assert p["readings"] == ["Revelation 21:1-6a", "John 11:32-44", "Titus 3:4-7"]

    def test_several_sets_keep_the_last_psalm_and_its_refrain(self):
        p = parse_propers(_propers(
            "Revelation 21.1–6a",
            "Psalm 24.1–6",
            "Refrain",
            "The Lord of hosts, he is the King of glory.",
            "John 11.32–44",
            "Daniel 7.1–3, 15–18",
            "Psalm 149",
            "Refrain",
            "Sing to the Lord a new song.",
            "Luke 6.20–36",
        ))
        assert p["psalm"] == "149"
        assert p["refrain"] == "Sing to the Lord a new song."
