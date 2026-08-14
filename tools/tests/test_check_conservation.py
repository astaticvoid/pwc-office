"""
Unit tests for check_conservation.py.

The check exists to fail, so most of these assert that it does. A conservation
check that has quietly lost the ability to report a dropped or invented line is
worse than no check at all: it reads as evidence and is not (cf. #70, #71 and
tools/test_rule_mutations.cjs, which makes the same argument for the qa rules).

The corpus is synthetic throughout — no PDF, no data/, and no book text, so
these run anywhere and in well under a second.

Run: python3 -m pytest tools/tests/test_check_conservation.py -v
     (from the repo root)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from check_conservation import (
    Finding,
    ShippedForm,
    SourceLine,
    _fix_whitespace,
    check_form,
    line_id,
    reconcile,
    squash,
)


def src(*lines) -> list:
    """Build source lines as (type, text) or plain text defaulting to leader."""
    out = []
    for item in lines:
        typ, text = item if isinstance(item, tuple) else ("leader", item)
        line = SourceLine(typ, text)
        line.section = "litany"
        line.consumed_as = typ
        out.append(line)
    return out


def shipped(*segments, section="litany") -> ShippedForm:
    """Build a shipped form from (type, text) pairs in one section."""
    return ShippedForm(
        {section: [{"type": t, "text": x} for t, x in segments]}, {})


def run(source, form, corrections=None, pre=None):
    return check_form("test-mp", source, form, pre, corrections or [])


# ── Text normalisation ────────────────────────────────────────────────────────


class TestSquash:
    def test_collapses_typesetting_only(self):
        assert squash("one two   three\nfour") == "one two three four"

    def test_composition_is_not_a_difference(self):
        assert squash("Noël") == squash("Noël")

    def test_wording_is_a_difference(self):
        assert squash("the light") != squash("the Light")

    def test_id_is_stable_and_carries_no_text(self):
        ident = line_id("Morning Prayer continues.")
        assert ident == line_id("Morning  Prayer\ncontinues.")
        assert len(ident) == 10 and ident.isalnum()


class TestFixWhitespace:
    """Routed through the extractor's own function, not a copy of its rules.

    The probe has to look like an ordinary office: _normalize_whitespace skips
    underscore-prefixed keys and only walks list-valued fields, so an earlier
    probe keyed "_probe" silently returned its input unchanged and every
    whitespace artifact in the corpus read as a dropped line.
    """

    def test_applies_the_extractors_replacements(self):
        assert _fix_whitespace("Amen .") == "Amen."
        assert _fix_whitespace("this city ,") == "this city,"

    def test_leaves_clean_text_alone(self):
        assert _fix_whitespace("and will be for ever. Amen.") == \
            "and will be for ever. Amen."


# ── PAGE → DATA: is anything printed missing? ─────────────────────────────────


class TestPageToData:
    def test_dropped_line_is_reported(self):
        page, _, findings = run(src("kept line", "dropped line"),
                                shipped(("leader", "kept line")))
        assert page["UNACCOUNTED"] == 1
        assert [f.text for f in findings if f.direction == "page"] == ["dropped line"]

    def test_verbatim_line_is_accounted(self):
        page, _, findings = run(src("kept line"), shipped(("leader", "kept line")))
        assert page["verbatim"] == 1 and not findings

    def test_reflowed_line_is_accounted(self):
        page, _, _ = run(src("a broken", "line of prose"),
                         shipped(("leader", "a broken line of prose")))
        assert page["reflowed"] == 2

    def test_whitespace_artifact_is_accounted(self):
        page, _, _ = run(src("for ever. Amen ."),
                         shipped(("leader", "for ever. Amen.")))
        assert page["whitespace"] == 1

    def test_heading_consumed_as_structure_is_accounted(self):
        line = SourceLine("heading", "The Litany")
        line.section, line.consumed_as = "litany", "heading"
        page, _, _ = run([line], shipped(("leader", "unrelated")))
        assert page["heading"] == 1

    def test_bare_separator_is_accounted(self):
        page, _, _ = run(src(("rubric", "Or")), shipped(("leader", "unrelated")))
        assert page["separator"] == 1

    def test_a_word_changed_in_the_data_is_reported(self):
        """The defect a substring match must not absorb."""
        page, _, _ = run(src("the world he lived and died to save"),
                         shipped(("leader", "the world he loved and died to save")))
        assert page["UNACCOUNTED"] == 1

    def test_a_manifest_entry_that_reproduces_the_change_accounts_for_it(self):
        """Extracted intact, then changed by an audited entry — the ADR 0005 path."""
        page, _, _ = run(src("printed wording"),
                         shipped(("leader", "shipped wording")),
                         pre=shipped(("leader", "printed wording")),
                         corrections=[{"office": "test-mp", "field": "litany",
                                       "old": "printed", "new": "shipped"}])
        assert page["corrected"] == 1 and page["UNACCOUNTED"] == 0

    def test_a_printed_line_straddling_the_correction_is_accounted(self):
        """The shape that broke the line-overlap rule on 30 forms.

        The page wraps mid-way through the corrected sentence and runs on into
        the next one, so the printed line contains neither `old` nor is
        contained by it. Reconstruction still explains it.
        """
        page, _, _ = run(src("A Reading from the Lectionary is read. After a",
                             "period of silence one of the following is said."),
                         shipped(("rubric", "A Reading is read. After a period "
                                            "of silence one of the following is said.")),
                         pre=shipped(("rubric", "A Reading from the Lectionary is "
                                                "read. After a period of silence one "
                                                "of the following is said.")),
                         corrections=[{"office": "*", "field": "litany",
                                       "old": "A Reading from the Lectionary is read.",
                                       "new": "A Reading is read."}])
        assert page["UNACCOUNTED"] == 0

    def test_an_entry_on_another_field_does_not_excuse_it(self):
        page, _, _ = run(src("printed wording"),
                         shipped(("leader", "shipped wording")),
                         pre=shipped(("leader", "printed wording")),
                         corrections=[{"office": "test-mp", "field": "canticle",
                                       "old": "printed", "new": "shipped"}])
        assert page["UNACCOUNTED"] == 1

    def test_an_entry_on_another_office_does_not_excuse_it(self):
        page, _, _ = run(src("printed wording"),
                         shipped(("leader", "shipped wording")),
                         pre=shipped(("leader", "printed wording")),
                         corrections=[{"office": "other-mp", "field": "litany",
                                       "old": "printed", "new": "shipped"}])
        assert page["UNACCOUNTED"] == 1

    def test_an_entry_elsewhere_in_the_field_does_not_excuse_a_dropped_line(self):
        """The hole that made this rule worth rewriting.

        Keyed on {office, field}, one unrelated three-word errata fix vouched
        for every line in the section — 121 of the corpus's form-fields carry an
        entry, so most of the book was exempt from the defect (#84) the check
        exists to catch.
        """
        page, _, _ = run(src("some other petition entirely"),
                         shipped(("leader", "shipped wording")),
                         pre=shipped(("leader", "printed wording")),
                         corrections=[{"office": "*", "field": "litany",
                                       "old": "printed", "new": "shipped"}])
        assert page["UNACCOUNTED"] == 1

    def test_a_line_lost_before_the_correction_stage_is_not_excused(self):
        """The line never reached the pre-correction artifact, so the
        corrections stage cannot be what changed it."""
        page, _, _ = run(src("printed wording"),
                         shipped(("leader", "unrelated")),
                         pre=shipped(("leader", "unrelated")),
                         corrections=[{"office": "*", "field": "litany",
                                       "old": "printed", "new": "shipped"}])
        assert page["UNACCOUNTED"] == 1


# ── DATA → PAGE: is anything shipped that was never printed? ──────────────────


class TestDataToPage:
    def test_invented_line_is_reported(self):
        _, data, findings = run(src("printed line"),
                                shipped(("leader", "printed line"),
                                        ("leader", "invented line")))
        assert data["UNACCOUNTED"] == 1
        assert [f.text for f in findings if f.direction == "data"] == ["invented line"]

    def test_joined_line_is_accounted(self):
        _, data, _ = run(src("a broken", "line of prose"),
                         shipped(("leader", "a broken line of prose")))
        assert data["printed-joined"] == 1

    def test_roman_group_label_is_structural(self):
        form = ShippedForm({"canticle": [{"type": "alternatives", "groups": [
            {"label": "I", "segments": [{"type": "leader", "text": "printed line"}]},
        ]}]}, {})
        _, data, findings = run(src("printed line"), form)
        assert data["structural"] == 1 and not findings

    def test_suffix_change_is_caught_here_and_only_here(self):
        """A shipped line the page prints as a prefix of it.

        The page → data direction accounts for this one by substring, which is
        why the check runs both ways — this is the #101 shape.
        """
        page, data, _ = run(src("he ascended into heaven"),
                            shipped(("response", "he ascended into heaven,")))
        assert page["reflowed"] == 1          # absorbed going that way
        assert data["UNACCOUNTED"] == 1       # caught coming back

    def test_a_manifest_entry_accounts_for_text_it_introduced(self):
        _, data, _ = run(src("printed line"),
                         shipped(("leader", "introduced line")),
                         pre=shipped(("leader", "printed line")),
                         corrections=[{"office": "*", "field": "litany",
                                       "old": "printed", "new": "introduced"}])
        assert data["corrected"] == 1 and data["UNACCOUNTED"] == 0

    def test_a_correction_may_not_vouch_for_extractor_invention(self):
        """The line is already in the pre-correction artifact, so the extractor
        invented it and the corrections stage merely inherited it."""
        _, data, _ = run(src("printed line"),
                         shipped(("leader", "printed line"),
                                 ("leader", "invented line")),
                         pre=shipped(("leader", "printed line"),
                                     ("leader", "invented line")),
                         corrections=[{"office": "*", "field": "litany",
                                       "old": "printed", "new": "introduced"}])
        assert data["UNACCOUNTED"] == 1

    def test_a_correction_may_not_vouch_for_text_appended_after_it(self):
        """The reviewer's mutation: an invented line in a field that carries a
        correction. The manifest explains its own edit and nothing else."""
        _, data, _ = run(src("printed line"),
                         shipped(("leader", "introduced line"),
                                 ("leader", "a line no rite ever printed")),
                         pre=shipped(("leader", "printed line")),
                         corrections=[{"office": "*", "field": "litany",
                                       "old": "printed", "new": "introduced"}])
        assert data["UNACCOUNTED"] == 1


# ── Baseline reconciliation ───────────────────────────────────────────────────


def finding(text, direction="page", section="litany"):
    return Finding("test-mp", section, "rubric", text, direction)


def entry(text, lines, direction="page", section="litany", issue=93):
    return {"id": line_id(text), "direction": direction, "section": section,
            "lines": lines, "issue": issue, "why": "test"}


class TestReconcile:
    def test_exact_match_is_known_and_passes(self):
        known, errors = reconcile([finding("a"), finding("a")],
                                  [entry("a", 2)])
        assert not errors
        assert [k["found"] for k in known] == [2]

    def test_a_defect_that_grew_fails(self):
        _, errors = reconcile([finding("a")] * 3, [entry("a", 2)])
        assert len(errors) == 1 and "expects 2" in errors[0]

    def test_a_defect_that_shrank_fails(self):
        _, errors = reconcile([finding("a")], [entry("a", 2)])
        assert len(errors) == 1 and "expects 2" in errors[0]

    def test_a_fixed_defect_fails_until_its_entry_is_deleted(self):
        _, errors = reconcile([], [entry("a", 2)])
        assert len(errors) == 1 and "no longer fires" in errors[0]

    def test_a_new_defect_fails(self):
        _, errors = reconcile([finding("a"), finding("b")], [entry("a", 1)])
        assert len(errors) == 1 and "no rule accounts for it" in errors[0]

    def test_direction_is_part_of_the_key(self):
        _, errors = reconcile([finding("a", direction="data")], [entry("a", 1)])
        assert len(errors) == 2  # the entry went stale, and the finding is new

    def test_a_clean_corpus_passes(self):
        known, errors = reconcile([], [])
        assert not known and not errors
