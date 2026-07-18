"""
Unit tests for extract_offices.py parsing functions.

Run: python3 -m pytest tools/tests/ -v
     (from the repo root)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from extract_offices import _group_alternatives, _fix_casing, _patch_segments, _reflow_litany_prose


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

    def test_holy_one_divine_title_in_response(self):
        # BUG-25: "Holy One" is a divine title (small-caps in the PDF; pdftotext
        # confirms the capitalisation). Applies to response segments only.
        assert self._response("holy one, accomplish your purposes in us.") == \
            "Holy One, accomplish your purposes in us."

    def test_holy_one_leader_untouched(self):
        # Leader segments (canticles, psalms) may legitimately contain lowercase
        # "holy one" — _fix_casing must leave them alone.
        original = "nor let your holy one see the Pit."
        assert self._leader(original) == original


# ── _patch_segments (BUG-36 recursion) ────────────────────────────────────────

class TestPatchSegments:
    def test_patches_flat_response(self):
        segs = [{"type": "response", "text": "your spirit."}]
        _patch_segments(segs, "your spirit.", "your Spirit.")
        assert segs[0]["text"] == "your Spirit."

    def test_patches_response_nested_in_alternatives(self):
        # BUG-36: some patched responses live inside I/II/III groups; the patch
        # must recurse into alternatives (lent-mp opening_responses).
        segs = [{
            "type": "alternatives",
            "groups": [
                {"label": "I", "segments": [
                    {"type": "response", "text": "and sustain us by your bountiful spirit."},
                ]},
            ],
        }]
        _patch_segments(segs, "and sustain us by your bountiful spirit.",
                        "and sustain us by your bountiful Spirit.")
        assert segs[0]["groups"][0]["segments"][0]["text"] == \
            "and sustain us by your bountiful Spirit."

    def test_leaves_non_matching_untouched(self):
        segs = [{"type": "response", "text": "a broken spirit."}]
        _patch_segments(segs, "your spirit.", "your Spirit.")
        assert segs[0]["text"] == "a broken spirit."


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


# ── _reflow_litany_prose ──────────────────────────────────────────────────────

class TestReflowLitanyProse:
    """Tests for smart reflow of PDF column-wrap line breaks in litany leaders."""

    def test_joins_mid_clause_wraps(self):
        segs = [{"type": "leader", "text": "Watchful at all times, let us pray to God for strength to stand with\nconfidence."}]
        _reflow_litany_prose(segs)
        assert segs[0]["text"] == "Watchful at all times, let us pray to God for strength to stand with confidence."

    def test_preserves_sentence_breaks(self):
        segs = [{"type": "leader", "text": "Let us pray to the Creator of the universe.\nHoly One, by the good news of our salvation"}]
        _reflow_litany_prose(segs)
        assert segs[0]["text"] == "Let us pray to the Creator of the universe.\nHoly One, by the good news of our salvation"

    def test_joins_mid_clause_between_sentence_breaks(self):
        segs = [{"type": "leader", "text": "Let us pray to the Creator of the universe.\nHoly One, by the good news of our salvation\nbrought to Mary by the angel:"}]
        _reflow_litany_prose(segs)
        assert segs[0]["text"] == "Let us pray to the Creator of the universe.\nHoly One, by the good news of our salvation brought to Mary by the angel:"

    def test_preserves_comma_break(self):
        segs = [{"type": "leader", "text": "Encompass us with your light as with a cloak,\nand conquer the darkness of our night."}]
        _reflow_litany_prose(segs)
        assert segs[0]["text"] == "Encompass us with your light as with a cloak,\nand conquer the darkness of our night."

    def test_ignores_rubric_segments(self):
        segs = [{"type": "rubric", "text": "The Litany is said or sung."}]
        original = segs[0]["text"]
        _reflow_litany_prose(segs)
        assert segs[0]["text"] == original

    def test_ignores_response_segments(self):
        segs = [{"type": "response", "text": "Holy One,\nhear and have mercy."}]
        original = segs[0]["text"]
        _reflow_litany_prose(segs)
        assert segs[0]["text"] == original

    def test_single_line_unchanged(self):
        segs = [{"type": "leader", "text": "God of Israel, may this day be one of fulfillment and peace."}]
        _reflow_litany_prose(segs)
        assert segs[0]["text"] == "God of Israel, may this day be one of fulfillment and peace."

    def test_recurses_into_alternatives(self):
        segs = [{"type": "alternatives", "groups": [{"label": "I", "segments": [{"type": "leader", "text": "O God of our salvation, guard and direct your Church\nin the way of unity, service, and praise."}]}]}]
        _reflow_litany_prose(segs)
        assert segs[0]["groups"][0]["segments"][0]["text"] == "O God of our salvation, guard and direct your Church in the way of unity, service, and praise."
