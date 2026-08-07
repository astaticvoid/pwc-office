"""Tests for the office_text correction walker.

Each case is a way a correction could apply to text nobody intended. The
manifest's whole safety story is that `validate_corrections.py` and
`apply_corrections.py` reach the same verdict, so these test the shared
`corrections_lib` both of them call rather than either script.
"""

import importlib.util
import pathlib

_SPEC = importlib.util.spec_from_file_location(
    "corrections_lib",
    pathlib.Path(__file__).resolve().parent.parent / "corrections_lib.py",
)
corrections_lib = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(corrections_lib)

check_office_text = corrections_lib.check_office_text
count_occurrences = corrections_lib.count_occurrences
iter_text_segments = corrections_lib.iter_text_segments
replace_occurrences = corrections_lib.replace_occurrences


def _field():
    """A field shaped like a real office section: rubric, plain segments, and
    an `alternatives` block whose groups hold more segments."""
    return [
        {"type": "rubric", "text": "The Responsory is said or sung."},
        {"type": "leader", "text": "your life is hid with Christ in God."},
        {
            "type": "alternatives",
            "groups": [
                {"label": "I", "segments": [{"type": "leader", "text": "hid away"}]},
                {"label": "II", "segments": [{"type": "response", "text": "no match"}]},
            ],
        },
    ]


def test_descends_into_alternatives_groups():
    texts = [s["text"] for s in iter_text_segments(_field())]
    assert "hid away" in texts, "segments nested in alternatives groups must be reachable"


def test_does_not_follow_shared_references():
    """A shared block is reachable from many forms. Correcting one through a
    form would silently rewrite every other form that shares it, so the walk
    stops at the reference and shared text is corrected at `_shared`."""
    field = [
        {"type": "leader", "text": "local text"},
        {"type": "shared", "key": "doxology"},
    ]
    assert [s["text"] for s in iter_text_segments(field)] == ["local text"]


def test_substring_replace_is_scoped_to_matching_segments():
    field = _field()
    assert replace_occurrences(field, "hid with Christ", "hidden with Christ") == 1
    assert field[1]["text"] == "your life is hidden with Christ in God."
    # The other "hid" is a different word in a different segment — untouched.
    assert field[2]["groups"][0]["segments"][0]["text"] == "hid away"


def test_count_defaults_to_one_and_rejects_extra_matches():
    """Two matches where the author expected one means the correction is about
    to rewrite text they never looked at. That is an error, not a bonus."""
    field = [
        {"type": "leader", "text": "Amen."},
        {"type": "response", "text": "Amen."},
    ]
    problem = check_office_text({"old": "Amen.", "new": "Amen!"}, field)
    assert problem and "found 2" in problem


def test_explicit_count_permits_a_repeated_refrain():
    """Responsory refrains repeat verbatim; correcting one means correcting all."""
    field = [
        {"type": "response", "text": "you feet"},
        {"type": "response", "text": "you feet"},
        {"type": "response", "text": "you feet"},
    ]
    c = {"old": "you feet", "new": "your feet", "count": 3}
    assert check_office_text(c, field) is None
    assert replace_occurrences(field, c["old"], c["new"]) == 3


def test_missing_old_is_reported_rather_than_skipped():
    problem = check_office_text({"old": "not present", "new": "x"}, _field())
    assert problem and "found 0" in problem


def test_nbsp_near_miss_gets_an_actionable_message():
    """The psalter and invitatory carry non-breaking spaces. A correction typed
    with an ordinary space silently matches nothing, which reads identical to a
    stale correction — so say which it is."""
    field = [{"type": "label", "text": "Invitatory Psalm: Psalm\xa095:1–7"}]
    problem = check_office_text({"old": "Psalm 95:1–7", "new": "x"}, field)
    assert problem and "non-breaking space" in problem


def test_whole_field_form_requires_exact_equality():
    """A non-string `old` is a structural edit — deleting or reordering
    segments — and must match the field exactly before it replaces it."""
    field = [{"type": "leader", "text": "a"}]
    assert check_office_text({"old": [{"type": "leader", "text": "a"}], "new": []}, field) is None
    assert check_office_text({"old": [{"type": "leader", "text": "b"}], "new": []}, field)


def test_plain_string_fields_are_still_correctable():
    """Every office `title` is a bare string, not a segment structure. The
    substring path must reach it — walking segments alone silently reports
    "found 0", which reads as a stale correction and sends the author hunting
    the extractor for a bug that isn't there."""
    field = "The Gathering of the Community"
    assert check_office_text({"old": "Gathering", "new": "Assembling"}, field) is None
    assert count_occurrences(field, "Gathering") == 1


def test_shared_reference_field_says_so_instead_of_found_zero():
    """17 office fields are bare shared references. Correcting one through the
    form is the mistake the design invites, so name it rather than reporting it
    as a missing match."""
    field = {"type": "shared", "key": "reading_response_seasonal"}
    problem = check_office_text({"old": "Holy Word", "new": "x"}, field)
    assert problem and "reading_response_seasonal" in problem
    assert "found 0" not in problem


def test_count_occurrences_counts_repeats_within_one_segment():
    field = [{"type": "leader", "text": "ours and ours"}]
    assert count_occurrences(field, "ours") == 2
