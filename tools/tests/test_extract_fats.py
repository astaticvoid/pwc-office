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
    _page_text_without_margin_artifacts,
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
