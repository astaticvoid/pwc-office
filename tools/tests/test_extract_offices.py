"""
Unit tests for extract_offices.py parsing functions.

Run: python3 -m pytest tools/tests/ -v
     (from the repo root)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from extract_offices import _char_type, _group_alternatives, _fix_casing


# ── _char_type ────────────────────────────────────────────────────────────────

def _char(fontname="", size=10, color=None):
    """Build a minimal pdfplumber char dict for testing."""
    return {
        "fontname": fontname,
        "size": size,
        "non_stroking_color": color or (0, 0, 0),
    }


class TestCharType:
    def test_red_text_is_rubric(self):
        # Red: R > threshold, G < threshold
        assert _char_type(_char(color=(0.8, 0.0, 0.0))) == "rubric"

    def test_bold_large_is_heading(self):
        assert _char_type(_char(fontname="TimesNewRomanPS-BoldMT", size=12)) == "heading"

    def test_bold_small_is_response(self):
        assert _char_type(_char(fontname="TimesNewRomanPS-BoldMT", size=9)) == "response"

    def test_italic_small_is_footer(self):
        assert _char_type(_char(fontname="TimesNewRomanPS-ItalicMT", size=8)) == "footer"

    def test_plain_is_leader(self):
        assert _char_type(_char(fontname="TimesNewRomanPSMT", size=10)) == "leader"

    def test_italic_large_not_footer(self):
        # Italic ≥10pt → leader (footer threshold is <10)
        assert _char_type(_char(fontname="TimesNewRomanPS-ItalicMT", size=10)) == "leader"

    def test_non_red_large_bold_is_heading(self):
        # Ensure heading threshold (≥11) is respected
        assert _char_type(_char(fontname="TimesNewRomanPS-BoldMT", size=11)) == "heading"
        assert _char_type(_char(fontname="TimesNewRomanPS-BoldMT", size=10)) == "response"


# ── _fix_casing ───────────────────────────────────────────────────────────────

class TestFixCasing:
    def _response(self, text):
        return _fix_casing({"type": "response", "text": text})["text"]

    def _leader(self, text):
        return _fix_casing({"type": "leader", "text": text})["text"]

    def test_capitalises_response_first_char(self):
        assert self._response("holy one, accomplish your purposes in us.")[0].isupper()

    def test_conjunction_start_stays_lowercase(self):
        # "and", "or", "but" etc. are continuation words — must not be uppercased.
        assert self._response("and your ministers be clothed with salvation.")[0].islower()

    def test_standalone_i_fixed(self):
        assert " I " in self._response("here i am, Lord.")

    def test_leader_not_modified(self):
        # Non-response types should not be capitalised by _fix_casing.
        original = "the lord is my shepherd;"
        assert self._leader(original) == original

    def test_empty_text_safe(self):
        result = _fix_casing({"type": "response", "text": ""})
        assert result["text"] == ""


# ── _group_alternatives ───────────────────────────────────────────���───────────

def seg(type_, text):
    return {"type": type_, "text": text}


class TestGroupAlternatives:
    """
    _group_alternatives turns Or/or separator rubrics into
    {type: "alternatives", groups: [...]} nodes.
    """

    def test_no_alternatives_passthrough(self):
        segs = [seg("leader", "The Lord be with you."), seg("response", "And also with you.")]
        result = _group_alternatives(segs)
        assert result == segs

    def test_unnamed_bare_or(self):
        segs = [
            seg("leader", "Option A"),
            seg("rubric", "Or"),
            seg("leader", "Option B"),
        ]
        result = _group_alternatives(segs)
        assert len(result) == 1
        alt = result[0]
        assert alt["type"] == "alternatives"
        assert len(alt["groups"]) == 2
        assert alt["groups"][0]["label"] == "I"
        assert alt["groups"][1]["label"] == "II"

    def test_named_or_rubric(self):
        # Preamble before the first Or\nName is flushed to result as a standalone
        # segment; the alternatives block follows it.
        segs = [
            seg("leader", "Option A text"),
            seg("rubric", "Or\nSong of Mary"),
            seg("leader", "Magnificent text"),
        ]
        result = _group_alternatives(segs)
        # result[0] = flushed preamble; result[1] = alternatives block
        assert len(result) == 2
        assert result[0] == seg("leader", "Option A text")
        alt = result[1]
        assert alt["type"] == "alternatives"
        labels = [g["label"] for g in alt["groups"]]
        assert "Song of Mary" in labels

    def test_block_sep_starts_unnamed_groups(self):
        # Block-sep rubrics are now emitted as a plain segment before the
        # alternatives group (Batch 15 — fixes missing intro rubric in rendered output).
        segs = [
            seg("rubric", "One of the following may be said or sung."),
            seg("leader", "Glory be option A"),
            seg("rubric", "Or"),
            seg("leader", "Glory be option B"),
        ]
        result = _group_alternatives(segs)
        assert len(result) == 2
        assert result[0]["type"] == "rubric"
        assert result[0]["text"] == "One of the following may be said or sung."
        assert result[1]["type"] == "alternatives"

    def test_canticle_doxology_intro_emitted_as_rubric(self):
        # "After the Canticle…" should appear as a rubric segment BEFORE
        # the alternatives block, not be discarded.
        segs = [
            seg("rubric", "After the Canticle one of the following may be said or sung."),
            seg("leader", "Glory I"),
            seg("rubric", "Or"),
            seg("leader", "Glory II"),
        ]
        result = _group_alternatives(segs)
        # First segment: the intro rubric
        assert result[0]["type"] == "rubric"
        assert "After the Canticle" in result[0]["text"]
        # Second segment: the alternatives block
        assert result[1]["type"] == "alternatives"

    def test_canticle_doxology_intro_at_end_of_canticle(self):
        segs = [
            seg("rubric", "At the end of the Canticle one of the following may be said or sung."),
            seg("leader", "Glory I"),
            seg("rubric", "Or"),
            seg("leader", "Glory II"),
        ]
        result = _group_alternatives(segs)
        assert result[0]["type"] == "rubric"
        assert "At the end of the Canticle" in result[0]["text"]
        assert result[1]["type"] == "alternatives"

    def test_segments_before_alternatives_preserved(self):
        segs = [
            seg("leader", "Preamble text"),
            seg("rubric", "Or"),
            seg("leader", "Option A"),
            seg("rubric", "Or"),
            seg("leader", "Option B"),
        ]
        result = _group_alternatives(segs)
        # The preamble before the first bare "Or" becomes group I;
        # subsequent Or values become group II, III.
        assert result[0]["type"] == "alternatives"
        assert len(result[0]["groups"]) == 3

    def test_empty_input(self):
        assert _group_alternatives([]) == []
