"""
Unit tests for extract_fats.py bio parsing.

Run: python3 -m pytest tools/tests/ -v
     (from the repo root)
"""
import sys
from pathlib import Path

# Allow importing from tools/ without installing a package.
sys.path.insert(0, str(Path(__file__).parent.parent))

from extract_fats import parse_bio  # noqa: E402, I001


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
