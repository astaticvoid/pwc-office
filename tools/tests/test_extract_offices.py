"""
Unit tests for extract_offices.py parsing functions.

Run: python3 -m pytest tools/tests/ -v
     (from the repo root)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from extract_offices import _group_alternatives, _fix_casing, _reflow_leader_prose


# ── _fix_casing ───────────────────────────────────────────────────────────────

class TestFixCasing:
    """_fix_casing only normalises a space before ! or ? (a PDF extraction
    artifact) now — every casing-correction rule that used to live here
    (force-capitalising the start of a response, standalone "i" -> "I", and
    the curly-apostrophe straightening that existed only to feed those two
    regexes) was checked against fitz's raw per-span output and found to
    have zero live effect on the current dataset — worse, the apostrophe
    straightening was actively wrong (flattened a genuine curly apostrophe
    in 2 places). Removed 2026-07-26; see BUGS.md."""

    def _fix(self, text, seg_type="response"):
        return _fix_casing({"type": seg_type, "text": text})["text"]

    def test_does_not_force_capitalise_response(self):
        # Regression guard: an earlier version force-capitalised every response's
        # first letter (inherited from the pre-fitz pdfplumber extractor, which
        # mis-decoded small-caps fonts as lowercase). fitz already decodes casing
        # correctly, so forcing a capital wrongly overrode genuine grammatical
        # continuations like the doxology's "as it was in the beginning..." —
        # see BUGS.md.
        original = "as it was in the beginning, is now, and will be for ever. Amen."
        assert self._fix(original) == original

    def test_does_not_fix_standalone_i(self):
        # Regression guard: a standalone-lowercase-"i" fix used to live here.
        # Confirmed zero live effect on the current dataset; removed.
        original = "here i am, Lord."
        assert self._fix(original) == original

    def test_does_not_straighten_apostrophes(self):
        # Regression guard: this used to flatten the source's genuine curly
        # apostrophe to a straight one (only to feed the two regexes above).
        original = "you proclaimed God’s gracious reign."
        assert self._fix(original) == original

    def test_space_before_punctuation_normalised(self):
        assert self._fix("Really ?") == "Really?"
        assert self._fix("Amazing !") == "Amazing!"

    def test_applies_regardless_of_segment_type(self):
        assert self._fix("Really ?", seg_type="leader") == "Really?"

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


# ── _reflow_leader_prose ───────────────────────────────────────────────────────

class TestReflowLeaderProse:
    """Tests for joining PDF column-wrap line breaks in leader (prose)
    segments — used for both seasonal_collects and litany.

    litany used to go through a separate _reflow_litany_prose that kept a
    break after "terminal punctuation" (comma/semicolon/period/etc.), on the
    theory that marked an intro-rubric -> petition boundary. Checked against
    the source PDF: every litany leader is one continuous petition, and
    ordinary mid-sentence commas/periods aren't a break signal — that
    heuristic produced 46 false breaks across the real dataset (e.g. "Show
    your good will to all who live in this city, the poor and the rich," /
    "the elderly and the young, men and women." printed as one sentence,
    split on the comma). Removed 2026-07-26 in favour of this function's
    unconditional join; see BUGS.md."""

    def test_joins_mid_clause_wraps(self):
        segs = [{"type": "leader", "text": "Watchful at all times, let us pray to God for strength to stand with\nconfidence."}]
        _reflow_leader_prose(segs)
        assert segs[0]["text"] == "Watchful at all times, let us pray to God for strength to stand with confidence."

    def test_joins_across_sentence_breaks_too(self):
        # Regression guard: this used to preserve the break here (period
        # before the \n) as an intro-rubric/petition boundary. It's an
        # ordinary column wrap like any other and must join.
        segs = [{"type": "leader", "text": "Let us pray to the Creator of the universe.\nHoly One, by the good news of our salvation"}]
        _reflow_leader_prose(segs)
        assert segs[0]["text"] == "Let us pray to the Creator of the universe. Holy One, by the good news of our salvation"

    def test_joins_across_comma_breaks_too(self):
        # Regression guard: this used to preserve the break here (comma
        # before the \n). Confirmed against the source PDF this is one
        # continuous sentence wrapped by the printed column width.
        segs = [{"type": "leader", "text": "Encompass us with your light as with a cloak,\nand conquer the darkness of our night."}]
        _reflow_leader_prose(segs)
        assert segs[0]["text"] == "Encompass us with your light as with a cloak, and conquer the darkness of our night."

    def test_ignores_rubric_segments(self):
        segs = [{"type": "rubric", "text": "The Litany is said or sung."}]
        original = segs[0]["text"]
        _reflow_leader_prose(segs)
        assert segs[0]["text"] == original

    def test_ignores_response_segments(self):
        segs = [{"type": "response", "text": "Holy One,\nhear and have mercy."}]
        original = segs[0]["text"]
        _reflow_leader_prose(segs)
        assert segs[0]["text"] == original

    def test_single_line_unchanged(self):
        segs = [{"type": "leader", "text": "God of Israel, may this day be one of fulfillment and peace."}]
        _reflow_leader_prose(segs)
        assert segs[0]["text"] == "God of Israel, may this day be one of fulfillment and peace."

    def test_recurses_into_alternatives(self):
        segs = [{"type": "alternatives", "groups": [{"label": "I", "segments": [{"type": "leader", "text": "O God of our salvation, guard and direct your Church\nin the way of unity, service, and praise."}]}]}]
        _reflow_leader_prose(segs)
        assert segs[0]["groups"][0]["segments"][0]["text"] == "O God of our salvation, guard and direct your Church in the way of unity, service, and praise."
