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
    PsalterShipped,
    PsalterSourceLine,
    ShippedForm,
    SourceLine,
    _fix_whitespace,
    check_form,
    check_psalter,
    line_id,
    read_psalter_source,
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

    def test_a_shared_block_entry_accounts_for_the_shared_line(self):
        """The #101 shape with the manifest entry that now addresses it.

        Before apply_manifest only carried form_key / "*" corrections, an
        office:"_shared" entry never reached the reconstruction, so a shared
        block the manifest authorises stayed unaccounted — exactly the
        divergence it was written to excuse.
        """
        def shared_form(creed_text: str) -> ShippedForm:
            return ShippedForm(
                {"affirmation": {"type": "shared", "key": "affirmation"}},
                {"affirmation": [{"type": "response", "text": creed_text}]},
            )
        _, data, findings = run(
            src("he ascended into heaven"),
            shared_form("he ascended into heaven,"),
            pre=shared_form("he ascended into heaven"),
            corrections=[{"office": "_shared", "field": "affirmation",
                          "old": "he ascended into heaven",
                          "new": "he ascended into heaven,"}],
        )
        assert data["corrected"] == 1 and data["UNACCOUNTED"] == 0
        assert not findings

    def test_a_shared_ref_field_is_corrected_by_its_key_entry(self):
        """The #91 shape: a form field 'reading_response' is a reference to a
        _shared block whose key ('reading_response_ordinary') differs from the
        form section name. apply_manifest must honour the entry (office
        '_shared', field = the key) through the section→key map, or the
        authorised divergence stays unaccounted."""
        def rr_form(third: str) -> ShippedForm:
            return ShippedForm(
                {"reading_response": {"type": "shared", "key": "reading_response_ordinary"}},
                {"reading_response_ordinary": {"type": "alternatives", "groups": [
                    {"label": "I", "segments": [{"type": "leader",
                                                 "text": "The word of the Lord."}]},
                    {"label": "III", "segments": [{"type": "leader", "text": third}]},
                ]}},
            )
        _, data, findings = run(
            src("The word of the Lord.", "Holy wisdom, holy word."),
            rr_form("Holy Word, Holy Wisdom."),
            pre=rr_form("Holy wisdom, holy word."),
            corrections=[{"office": "_shared", "field": "reading_response_ordinary",
                          "old": "Holy wisdom, holy word.",
                          "new": "Holy Word, Holy Wisdom."}],
        )
        assert data["corrected"] == 1 and data["UNACCOUNTED"] == 0
        assert not findings

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


# ── Psalter chain (#102) ──────────────────────────────────────────────────────
#
# The psalter conservation check (--chain psalter) is the first non-office
# chain to share the two-direction methodology. Its load-bearing claims, like
# the offices ones above, are that it FAILS when a line is dropped or invented,
# and that the `corrected` rule only ever excuses a divergence the manifest
# actually reconstructs.

def psalter_shipped(pre_text, shipped_text, corrections, title=""):
    """A single-psalm PsalterShipped from pre/shipped texts + corrections.

    Title defaults to empty so verse-only tests do not ship a title that the
    synthetic page never prints (which would itself be an unaccounted line);
    head tests pass an explicit title.
    """
    return PsalterShipped(
        {"1": {"number": 1, "book": 1, "title": title, "text": shipped_text}},
        {"1": {"number": 1, "book": 1, "title": title, "text": pre_text}},
        corrections,
    )


def psl(*items):
    """Build psalter source lines.

    ('type','text',psalm) for verse/cont; ('head','text',psalm,title) for heads.
    """
    out = []
    for it in items:
        if it[0] == "head":
            _, text, psalm, title = it
            out.append(PsalterSourceLine("head", text, psalm, title))
        else:
            _, text, psalm = it
            out.append(PsalterSourceLine(it[0], text, psalm))
    return out


class TestPsalterCheck:
    def test_verbatim_verse_accounted_both_ways(self):
        sh = psalter_shipped("1 verse one *", "1 verse one *", [])
        page, data, *_ = check_psalter(psl(("verse", "1 verse one *", "1")), sh)
        assert page["verbatim"] == 1 and page["UNACCOUNTED"] == 0
        assert data["printed"] == 1 and data["UNACCOUNTED"] == 0

    def test_dropped_verse_is_reported(self):
        sh = psalter_shipped("1 kept *", "1 kept *", [])
        page, _, _, _, findings = check_psalter(
            psl(("verse", "1 kept *", "1"), ("verse", "1 dropped *", "1")), sh)
        assert page["UNACCOUNTED"] == 1
        assert findings[0].text == "1 dropped *"

    def test_invented_verse_is_reported(self):
        sh = psalter_shipped("1 kept *", "1 kept *\n1 invented *", [])
        _, data, _, _, findings = check_psalter(psl(("verse", "1 kept *", "1")), sh)
        assert data["UNACCOUNTED"] == 1
        assert findings[0].direction == "data" and findings[0].text == "1 invented *"

    def test_a_manifest_entry_accounts_for_the_change_both_ways(self):
        """The psalter shape of ADR 0005: the correction turns pre into shipped."""
        sh = psalter_shipped(
            "Do let them say\nkeep", "Do not let them say\nkeep",
            [{"psalm": 1, "old": "Do let them say", "new": "Do not let them say"}])
        page, data, *_ = check_psalter(
            psl(("verse", "Do let them say", "1"), ("verse", "keep", "1")), sh)
        assert page["corrected"] == 1 and page["UNACCOUNTED"] == 0
        assert data["corrected"] == 1 and data["UNACCOUNTED"] == 0

    def test_a_correction_that_does_not_reconstruct_ships_nothing(self):
        """The fail-closed property: a correction only excuses a divergence it
        actually produces. If applying it does not reproduce the shipped text,
        it cannot account for the dropped line — the psalter shape of the office
        rule's 'requires the line to be absent before the manifest ran'."""
        sh = psalter_shipped(
            "A B", "A C",
            [{"psalm": 1, "old": "B", "new": "X"}])  # reconstructs to "A X", not "A C"
        page, _, _, _, findings = check_psalter(psl(("verse", "A B", "1")), sh)
        assert page["UNACCOUNTED"] == 1
        assert findings[0].text == "A B"

    def test_a_correction_may_not_vouch_for_extractor_invention(self):
        """A line already in the pre-correction artifact is the extractor's, not
        the manifest's — no correction can be credited with introducing it."""
        sh = psalter_shipped(
            "1 printed\n1 invented", "1 printed\n1 invented",
            [{"psalm": 1, "old": "printed", "new": "changed"}])
        _, data, *_ = check_psalter(psl(("verse", "1 printed", "1")), sh)
        # "1 invented" ships but was never printed; it is also in pre, so the
        # correction must not excuse it.
        assert data["UNACCOUNTED"] == 1

    def test_psalm_head_with_incipit_is_structural_when_title_ships(self):
        sh = psalter_shipped("1 kept *", "1 kept *", [],
                             title="Beatus vir qui non abiit")
        page, _, _, _, findings = check_psalter(
            psl(("head", "Psalm 1  Beatus vir qui non abiit", "1",
                 "Beatus vir qui non abiit"),
                ("verse", "1 kept *", "1")), sh)
        assert page["heading"] == 1 and page["UNACCOUNTED"] == 0 and not findings

    def test_psalm_head_without_incipit_is_structural_when_title_empty(self):
        """Psalms 18, 37, 78, 89, 105–107, 119 print no incipit; the empty
        shipped title is the correct state, not a dropped line."""
        sh = psalter_shipped("1 kept *", "1 kept *", [])
        page, _, _, _, findings = check_psalter(
            psl(("head", "Psalm 1", "1", ""), ("verse", "1 kept *", "1")), sh)
        assert page["heading"] == 1 and page["UNACCOUNTED"] == 0 and not findings

    def test_psalm_head_incipit_dropped_from_title_is_reported(self):
        sh = psalter_shipped("1 kept *", "1 kept *", [])
        page, _, _, _, findings = check_psalter(
            psl(("head", "Psalm 1  Beatus vir qui non abiit", "1",
                 "Beatus vir qui non abiit"),
                ("verse", "1 kept *", "1")), sh)
        assert page["UNACCOUNTED"] == 1
        assert findings[0].type == "title"

    def test_source_reader_slices_and_tags(self):
        """The psalter walk restates only the bookkeeping — which psalm a line
        belongs to — and classifies with the extractor's own regexes."""
        lines = [
            (30.0, "Some prefatory office text"),
            (30.0, "BooK V"),
            (30.0, "Psalm 1  Beatus vir qui non abiit"),
            (30.0, "1 Happy are they who have not walked *"),
            (66.0, "in the counsel of the wicked,"),
            (30.0, "Acknowledgements and credits"),
            (30.0, "Psalm 2  Quare fremuerunt gentes?"),
        ]
        out = read_psalter_source(lines)
        assert [(ln.type, ln.psalm, ln.title) for ln in out] == [
            ("head", "1", "Beatus vir qui non abiit"),
            ("verse", "1", ""),
            ("cont", "1", ""),
        ]


class TestReconcileChain:
    """Baseline entries carry an optional `chain` (default offices) so a
    divergence licensed in one chain never claims another's findings."""

    def test_psalter_entry_ignored_when_reconciling_offices(self):
        baseline = [entry("a", 1, section="35", issue=102) | {"chain": "psalter"}]
        _, errors = reconcile([finding("a", section="35")], baseline)
        assert errors and "no rule accounts for it" in errors[0]

    def test_offices_entry_ignored_when_reconciling_psalter(self):
        baseline = [entry("a", 1, issue=94)]  # no chain field -> offices
        _, errors = reconcile([finding("a")], baseline, chain="psalter")
        assert errors and "no rule accounts for it" in errors[0]

    def test_psalter_entry_counts_when_reconciling_psalter(self):
        baseline = [entry("a", 1, section="35", issue=102) | {"chain": "psalter"}]
        known, errors = reconcile([finding("a", section="35")], baseline,
                                  chain="psalter")
        assert not errors and len(known) == 1
