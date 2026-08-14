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
    _page_text_without_margin_artifacts,
    _restore_title_space,
    parse_bio,
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
