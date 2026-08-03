"""Tests for the extraction diff tool.

Each case is a mistake the tool exists to prevent, taken from a session where the
comparison was improvised instead: a path-keyed walker reporting 649 differences
for a change that altered nothing, an intermediate artifact silently compared
against a final one, and one edit counted as two.
"""

import importlib.util
import pathlib

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "diff_extraction",
    pathlib.Path(__file__).resolve().parent.parent / "diff_extraction.py",
)
diff_extraction = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(diff_extraction)
diff = diff_extraction.diff


def _form(**sections):
    return {"title": "Morning Prayer", **sections}


def _seg(text, typ="leader"):
    return {"type": typ, "text": text}


def _changed(report):
    return (len(report["modified"]) + len(report["text_added"])
            + len(report["text_removed"]))


def test_identical_documents_report_nothing():
    doc = {"advent-mp": _form(litany=[_seg("Let us pray."), _seg("Amen.", "response")])}
    assert _changed(diff(doc, doc)) == 0


def test_an_edit_counts_once_not_twice():
    # An edited segment is a removal and an addition in the raw view. Pairing
    # them is why a 14-node change does not get reported as 28.
    before = {"advent-mp": _form(litany=[_seg("Let us pray.\nHoly One,")])}
    after = {"advent-mp": _form(litany=[_seg("Let us pray.\n\nHoly One,")])}
    report = diff(before, after)
    assert len(report["modified"]) == 1
    assert not report["text_added"] and not report["text_removed"]
    assert _changed(report) == 1


def test_insertion_does_not_report_the_whole_section_as_changed():
    # The path-keyed failure: inserting one segment renumbers every sibling
    # after it, which a positional comparison reports as mass change.
    before = {"advent-mp": _form(litany=[_seg("one"), _seg("two"), _seg("three")])}
    after = {"advent-mp": _form(litany=[_seg("one"), _seg("new"), _seg("two"), _seg("three")])}
    report = diff(before, after)
    assert _changed(report) == 1
    assert report["text_added"] == [(("advent-mp", "litany"), "leader", "new")]
    assert report["count_changes"] == [(("advent-mp", "litany"), 3, 4)]


def test_partial_pipeline_is_named_as_a_shared_block_difference():
    # Running extract_offices.py alone leaves a complete-looking file whose
    # _shared is missing the blocks normalize_offices.py creates. The tool has to
    # say so plainly rather than drown it in per-node noise.
    final = {"_shared": {"affirmation": [_seg("I believe")],
                         "reading_response_ordinary": [_seg("The word of the Lord.")]},
             "advent-mp": _form(litany=[_seg("Let us pray.")])}
    partial = {"_shared": {"affirmation": [_seg("I believe")]},
               "advent-mp": _form(litany=[_seg("Let us pray.")])}
    report = diff(final, partial)
    assert report["shared_removed"] == ["reading_response_ordinary"]


def test_reordering_is_reported_even_though_contents_match():
    before = {"advent-mp": _form(litany=[_seg("one"), _seg("two")])}
    after = {"advent-mp": _form(litany=[_seg("two"), _seg("one")])}
    report = diff(before, after)
    assert report["moved"] == [("advent-mp", "litany")]
    assert _changed(report) == 0


def test_finds_segments_nested_in_alternatives_groups():
    # seasonal_collects and others hold their text inside alternatives groups; a
    # walker that only looks at top-level segments silently reports zero.
    before = {"advent-mp": _form(seasonal_collects=[
        {"type": "alternatives", "groups": [{"label": "I", "segments": [_seg("O God,")]}]}])}
    after = {"advent-mp": _form(seasonal_collects=[
        {"type": "alternatives", "groups": [{"label": "I", "segments": [_seg("O Lord,")]}]}])}
    assert _changed(diff(before, after)) == 1


def test_section_and_form_changes_are_reported():
    before = {"advent-mp": _form(litany=[_seg("x")], dismissal=[_seg("y")])}
    after = {"advent-mp": _form(litany=[_seg("x")]), "advent-ep": _form(litany=[_seg("z")])}
    report = diff(before, after)
    assert report["forms_added"] == ["advent-ep"]
    assert ("advent-mp", "dismissal") in report["sections_removed"]


@pytest.mark.parametrize("doc", [
    {"Psalm 1": {"verses": ["Blessed is the one"]}},
    [{"date": "2026-01-01", "readings": ["Gen 1"]}],
])
def test_non_offices_documents_still_compare(doc):
    assert _changed(diff(doc, doc)) == 0
