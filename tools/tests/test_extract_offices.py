"""
Unit tests for extract_offices.py parsing functions.

Run: python3 -m pytest tools/tests/ -v
     (from the repo root)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from extract_offices import (
    _dedup_shared,
    _group_alternatives,
    _hoist_office_transition,
    _is_structural_rubric,
    _normalize_whitespace,
    _reflow_by_geometry,
    _rehome_reading_handoff,
)

# ── normalize_whitespace space-punct fix ─────────────────────────────────────


class TestNormalizeWhitespaceSpacePunct:
    """_normalize_whitespace closes a space before punctuation, and leaves the
    text otherwise alone. Two live instances ("Holy One !", "this city ,") are
    handled by .replace() in _fix() (#15)."""

    def test_space_before_punctuation_normalised(self):
        office = {
            "test": {
                "section": [
                    {"type": "response", "text": "Really ?"},
                    {"type": "leader", "text": "Amazing !"},
                    {"type": "leader", "text": "Truly ,"},
                ]
            }
        }
        norm = _normalize_whitespace(office)
        segs = norm["test"]["section"]
        assert segs[0]["text"] == "Really?"
        assert segs[1]["text"] == "Amazing!"
        assert segs[2]["text"] == "Truly,"

    def test_does_not_alter_text_without_artifact(self):
        original = "as it was in the beginning, is now, and will be for ever. Amen."
        office = {"test": {"section": [{"type": "response", "text": original}]}}
        norm = _normalize_whitespace(office)
        assert norm["test"]["section"][0]["text"] == original

    def test_does_not_alter_period(self):
        original = "For [ . . . and ] all the saints."
        office = {"test": {"section": [{"type": "leader", "text": original}]}}
        norm = _normalize_whitespace(office)
        assert norm["test"]["section"][0]["text"] == original

    def test_does_not_straighten_apostrophes(self):
        original = "you proclaimed God’s gracious reign."
        office = {"test": {"section": [{"type": "response", "text": original}]}}
        norm = _normalize_whitespace(office)
        assert norm["test"]["section"][0]["text"] == original


# ── _group_alternatives ───────────────────────────────────────────────────────


def seg(type_, text):
    return {"type": type_, "text": text}


class TestGroupAlternatives:
    """
    _group_alternatives turns Or/or separator rubrics into
    {type: "alternatives", groups: [...]} nodes.
    """

    def test_no_alternatives_passthrough(self):
        segs = [
            seg("leader", "The Lord be with you."),
            seg("response", "And also with you."),
        ]
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
            seg(
                "rubric", "After the Canticle one of the following may be said or sung."
            ),
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
            seg(
                "rubric",
                "At the end of the Canticle one of the following may be said or sung.",
            ),
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


# ── _hoist_office_transition ──────────────────────────────────────────────────


def _alt(groups):
    return {"type": "alternatives", "groups": groups}


class TestHoistOfficeTransition:
    """Section-closing "{office} Prayer continues with …" rubrics must not ride
    inside the alternatives block they follow. The trailer can be a RUN of
    rubrics — transition plus whatever the book prints after it (#93)."""

    def test_single_transition_is_hoisted(self):
        segs = [_alt([{"label": "I", "segments": [
            seg("leader", "Collect text."),
            seg("rubric", "Morning Prayer continues with the Litany."),
        ]}])]
        result = _hoist_office_transition(segs)
        assert len(result) == 2
        assert result[0]["type"] == "alternatives"
        assert result[0]["groups"][0]["segments"][-1]["text"] == "Collect text."
        assert result[1]["text"] == "Morning Prayer continues with the Litany."

    def test_transition_run_is_hoisted_together(self):
        # The ordinary-time collects: the last group ends with the hand-off AND
        # the heading-styled rubric printed after it. Both leave the group (#93).
        segs = [_alt([{"label": "II", "segments": [
            seg("leader", "God of glory, by the raising of your Son…"),
            seg("rubric", "Morning Prayer continues with the Lord’s Prayer."),
            seg("rubric", "The Lord’s Prayer"),
        ]}])]
        result = _hoist_office_transition(segs)
        assert len(result) == 3
        assert result[0]["groups"][0]["segments"][-1]["type"] == "leader"
        assert [s["text"] for s in result[1:]] == [
            "Morning Prayer continues with the Lord’s Prayer.",
            "The Lord’s Prayer",
        ]

    def test_rubric_run_without_transition_stays(self):
        segs = [_alt([{"label": "I", "segments": [
            seg("leader", "Option A."),
            seg("rubric", "Some other trailing rubric."),
            seg("rubric", "And one more after it."),
        ]}])]
        result = _hoist_office_transition(segs)
        assert len(result) == 1
        assert [s["text"] for s in result[0]["groups"][0]["segments"][1:]] == [
            "Some other trailing rubric.",
            "And one more after it.",
        ]

    def test_rubric_before_transition_stays_in_the_group(self):
        # Only the tail from the first transition onward is hoisted (#93 review):
        # a rubric printed before the transition is still the group's content.
        segs = [_alt([{"label": "I", "segments": [
            seg("leader", "Option A."),
            seg("rubric", "At the end of the Canticle one of the following may be said."),
            seg("rubric", "Morning Prayer continues with the Litany."),
        ]}])]
        result = _hoist_office_transition(segs)
        group_segs = result[0]["groups"][0]["segments"]
        assert group_segs[-1]["text"].startswith("At the end of the Canticle")
        assert len(result) == 2
        assert result[1]["text"] == "Morning Prayer continues with the Litany."

    def test_no_alternatives_tail_untouched(self):
        segs = [seg("rubric", "Morning Prayer continues with the Dismissal.")]
        assert _hoist_office_transition(segs) == segs

    def test_transition_split_over_two_lines_is_hoisted(self):
        # The transition is a printed sentence, and the column may set it over
        # two lines. Missing it leaves it inside the group, where _dedup_shared
        # keys by shape and gives every form one office's copy (#138).
        segs = [_alt([{"label": "I", "segments": [
            seg("leader", "Collect text."),
            seg("rubric", "Morning\nPrayer continues with the Litany."),
        ]}])]
        result = _hoist_office_transition(segs)
        assert len(result) == 2
        assert result[1]["text"] == "Morning\nPrayer continues with the Litany."

    def test_transition_across_a_non_breaking_space_is_hoisted(self):
        segs = [_alt([{"label": "I", "segments": [
            seg("leader", "Collect text."),
            seg("rubric", "Evening Prayer\u00a0continues with the Litany."),
        ]}])]
        assert len(_hoist_office_transition(segs)) == 2


class TestStructuralRubric:
    """A "continues with…" rubric must not merge with its neighbours, and the
    page may have set the phrase across a break or a non-breaking space."""

    def test_phrase_is_structural_across_whitespace(self):
        for text in ("Morning Prayer continues with the Litany.",
                     "Morning\nPrayer continues with the Litany.",
                     "Evening Prayer\u00a0continues with the Litany."):
            assert _is_structural_rubric(text), text

    def test_ordinary_rubric_is_not_structural(self):
        assert not _is_structural_rubric("A Psalm is said or sung.")


# ── _rehome_reading_handoff ───────────────────────────────────────────────────


def _rubric_sections(handoff):
    return {
        "psalm_rubrics": [
            seg("label", "The Psalm"),
            seg("rubric", "A Psalm is said or sung."),
            seg("rubric", "At the end of the Psalm the following is said."),
            seg("rubric", handoff),
        ],
        "reading_rubrics": [
            seg("label", "The Reading"),
            seg("rubric", "A Reading is read."),
        ],
    }


class TestRehomeReadingHandoff:
    """The hand-off is printed at the foot of the Psalm block and introduces the
    Reading, so it ships with the reading rubrics, after the section label (#84).
    The match reads a sentence, not a line: a break the reflow judged structural
    would otherwise hide the sentence and leave the rubric under "The Psalm"."""

    def test_handoff_moves_below_the_reading_label(self):
        sections = _rubric_sections("Morning Prayer continues with the Reading.")
        _rehome_reading_handoff(sections)
        assert [s["text"] for s in sections["reading_rubrics"]] == [
            "The Reading",
            "Morning Prayer continues with the Reading.",
            "A Reading is read.",
        ]
        assert sections["psalm_rubrics"][-1]["text"].startswith("At the end of the Psalm")

    def test_handoff_split_over_two_lines_still_moves(self):
        sections = _rubric_sections("Evening Prayer continues with the\nReading.")
        _rehome_reading_handoff(sections)
        assert len(sections["psalm_rubrics"]) == 3
        assert sections["reading_rubrics"][1]["text"].startswith("Evening Prayer continues")

    def test_unlabelled_reading_block_takes_it_first(self):
        sections = _rubric_sections("Morning Prayer continues with the Reading.")
        sections["reading_rubrics"] = sections["reading_rubrics"][1:]
        _rehome_reading_handoff(sections)
        assert sections["reading_rubrics"][0]["text"].endswith("continues with the Reading.")

    def test_other_transitions_stay_in_the_psalm_block(self):
        sections = _rubric_sections("Morning Prayer continues with the Canticle.")
        _rehome_reading_handoff(sections)
        assert len(sections["psalm_rubrics"]) == 4
        assert len(sections["reading_rubrics"]) == 2

    def test_missing_reading_block_is_left_alone(self):
        sections = _rubric_sections("Morning Prayer continues with the Reading.")
        del sections["reading_rubrics"]
        _rehome_reading_handoff(sections)
        assert len(sections["psalm_rubrics"]) == 4


# ── _reflow_by_geometry ───────────────────────────────────────────────────────


def _seg(text, slacks, leads=None, gaps=None):
    """A merged leader segment with the per-break geometry _merge attaches."""
    n = text.count("\n")
    return {
        "type": "leader",
        "text": text,
        "break_slacks": slacks,
        "break_leads": leads if leads is not None else [12.5] * n,
        "break_gaps": gaps if gaps is not None else [20.0] * n,
    }


class TestReflowByGeometry:
    """Line breaks are decided per break from the page, not per section.

    `slack` is what would have been left over had the next line's first word
    been pulled up. Negative means the typesetter had no choice and the break is
    a column wrap; positive means the break was chosen. See #39.

    These replace tests for _reflow_leader_prose, which joined unconditionally.
    Two of those asserted behaviour now known to be wrong — it flattened the
    litany bidding into the first petition (#40) and joined verse couplets — so
    they are not preserved here.
    """

    def test_joins_a_forced_break(self):
        segs = [_seg("...strength to stand with\nconfidence.", [-18.0])]
        _reflow_by_geometry(segs)
        assert segs[0]["text"] == "...strength to stand with confidence."

    def test_keeps_a_chosen_break(self):
        segs = [_seg("Encompass us with your light as with a cloak,\n"
                     "and conquer the darkness of our night.", [+64.0])]
        _reflow_by_geometry(segs)
        assert "\n" in segs[0]["text"]

    def test_paragraph_leading_becomes_a_blank_line(self):
        # The litany bidding stands apart from the first petition (#40); the
        # leading is decisive even though the line ran nearly full.
        segs = [_seg("Let us pray to the Creator of the universe.\n"
                     "Holy One, by the good news of our salvation",
                     [-5.0], leads=[21.5])]
        _reflow_by_geometry(segs)
        assert segs[0]["text"].startswith(
            "Let us pray to the Creator of the universe.\n\nHoly One,")

    def test_dead_band_keeps_verse_but_joins_prose(self):
        # Geometry cannot decide within the measure's own precision, so each
        # section falls back to its own mode.
        text = "in your realm of glory the poor are blessed,\nthe hungry filled."
        verse = [_seg(text, [+1.0])]
        _reflow_by_geometry(verse, prose=False)
        assert "\n" in verse[0]["text"]
        prose = [_seg(text, [+1.0])]
        _reflow_by_geometry(prose, prose=True)
        assert "\n" not in prose[0]["text"]

    def test_falls_back_to_joining_when_geometry_is_missing(self):
        # A later pass rewrote the text, so the per-break lists no longer line
        # up. Guessing which break is which would be worse than joining.
        segs = {"type": "leader", "text": "one\ntwo\nthree", "break_slacks": [+50.0]}
        _reflow_by_geometry([segs])
        assert segs["text"] == "one two three"

    def test_ignores_rubric_and_response_segments(self):
        segs = [{"type": "rubric", "text": "The Litany is said or sung."},
                {"type": "response", "text": "Holy One,\nhear and have mercy."}]
        before = [s["text"] for s in segs]
        _reflow_by_geometry(segs)
        assert [s["text"] for s in segs] == before

    def test_single_line_unchanged(self):
        segs = [_seg("God of Israel, may this day be one of fulfillment and peace.", [])]
        _reflow_by_geometry(segs)
        assert segs[0]["text"] == (
            "God of Israel, may this day be one of fulfillment and peace.")

    def test_recurses_into_alternatives(self):
        inner = _seg("O God of our salvation, guard and direct your Church\n"
                     "in the way of unity, service, and praise.", [-12.0])
        segs = [{"type": "alternatives",
                 "groups": [{"label": "I", "segments": [inner]}]}]
        _reflow_by_geometry(segs)
        assert segs[0]["groups"][0]["segments"][0]["text"] == (
            "O God of our salvation, guard and direct your Church "
            "in the way of unity, service, and praise.")


# ── _dedup_shared reconciliation (#103) ──────────────────────────────────────


def _affirmation(text):
    """A 2-group affirmation-shaped alternatives block (passes _is_affirmation)."""
    return {
        "type": "alternatives",
        "groups": [
            {"label": "Apostles' Creed", "segments": [seg("leader", text)]},
            {"label": "II",
             "segments": [seg("leader", "I believe in one God the Father almighty")]},
        ],
    }


_APOSTLES = (
    "I believe in Jesus Christ his only Son our Lord who was conceived by the Holy "
    "Spirit born of the Virgin Mary suffered under Pontius Pilate was crucified dead "
    "and buried he descended into hell the third day he rose again from the dead he "
    "ascended into heaven and sitteth on the right hand of God the Father almighty"
)


class TestDedupSharedReconciliation:
    """#103: a divergence an office_text correction against _shared.<key> already
    reconciles must not re-warn on every extract, but the warning must re-arm when
    the correction is removed and still fire for a genuinely new divergence."""

    COMMA = [{"office": "_shared", "field": "affirmation",
              "old": "he ascended into heaven", "new": "he ascended into heaven,"}]

    def _run(self, canon, divergent, corrections, monkeypatch, capsys):
        monkeypatch.setattr(
            "extract_offices._load_shared_corrections",
            lambda: {"affirmation": corrections},
        )
        # advent-mp is first, so it becomes the canonical copy (#101).
        offices = {
            "advent-mp": {"affirmation": [canon]},
            "advent-ep": {"affirmation": [divergent]},
        }
        _dedup_shared(offices)
        return capsys.readouterr().out

    def test_reconciled_divergence_is_silent(self, monkeypatch, capsys):
        canon = _affirmation(_APOSTLES)  # advent-mp's creed, comma missing
        divergent = _affirmation(
            _APOSTLES.replace("he ascended into heaven", "he ascended into heaven,"))
        out = self._run(canon, divergent, self.COMMA, monkeypatch, capsys)
        assert "WARNING" not in out

    def test_removing_the_correction_rearms_the_warning(self, monkeypatch, capsys):
        canon = _affirmation(_APOSTLES)
        divergent = _affirmation(
            _APOSTLES.replace("he ascended into heaven", "he ascended into heaven,"))
        out = self._run(canon, divergent, [], monkeypatch, capsys)
        assert "WARNING" in out

    def test_unrelated_divergence_still_fires(self, monkeypatch, capsys):
        # A different word change on the same key: the comma correction must not
        # vouch for it.
        canon = _affirmation(_APOSTLES)
        unrelated = _affirmation(_APOSTLES.replace("conceived by", "wrought by"))
        out = self._run(canon, unrelated, self.COMMA, monkeypatch, capsys)
        assert "WARNING" in out

    def test_reconciliation_never_mutates_the_canonical(self, monkeypatch):
        # The reconciliation runs replace_occurrences on a deepcopy; the stored
        # canonical, the divergent block, and the input offices must be untouched.
        canon = _affirmation(_APOSTLES)
        divergent = _affirmation(
            _APOSTLES.replace("he ascended into heaven", "he ascended into heaven,"))
        monkeypatch.setattr(
            "extract_offices._load_shared_corrections",
            lambda: {"affirmation": self.COMMA},
        )
        offices = {"advent-mp": {"affirmation": [canon]},
                   "advent-ep": {"affirmation": [divergent]}}
        out = _dedup_shared(offices)
        # The stored shared block is the first form's copy, exactly as given.
        assert out["_shared"]["affirmation"] == canon
        # Both forms now reference it; neither block was rewritten by the trial.
        assert out["advent-mp"]["affirmation"] == [{"type": "shared", "key": "affirmation"}]
        assert out["advent-ep"]["affirmation"] == [{"type": "shared", "key": "affirmation"}]
        assert offices["advent-mp"]["affirmation"][0] == canon
        assert offices["advent-ep"]["affirmation"][0] == divergent
