"""Tests for detect_bounds() canonical phrase matching.

BUG-02: detect_bounds() previously used ad-hoc `in` substring checks.
CANONICAL_BOUNDS_PHRASES now defines the expected wording per key.
Exact matches (== or startswith) are silent; fuzzy matches emit a warning.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from convert_lectionary import CANONICAL_BOUNDS_PHRASES, detect_bounds


def _row(date, name):
    return [date, name, '', '', '']


# ── Exact canonical phrases ───────────────────────────────────────────────────

def test_all_canonical_bounds_found_without_warnings(capsys):
    rows = [
        _row('2025-11-30', 'First Sunday of Advent'),
        _row('2025-12-25', 'Birth of the Lord'),
        _row('2026-01-11', 'Baptism of the Lord'),
        _row('2026-02-02', 'Presentation of the Lord'),
        _row('2026-02-18', 'Ash Wednesday'),
        _row('2026-03-22', 'Fifth Sunday in Lent'),
        _row('2026-03-29', 'Palm Sunday'),
        _row('2026-04-05', 'Easter Day'),
        _row('2026-05-14', 'Ascension of the Lord'),
        _row('2026-05-24', 'Day of Pentecost'),
        _row('2026-05-31', 'Trinity Sunday'),
        _row('2026-11-01', 'All Saints'),
    ]
    bounds = detect_bounds(rows)
    for key in CANONICAL_BOUNDS_PHRASES:
        assert key in bounds, f"Missing bound: {key}"
    assert 'WARNING' not in capsys.readouterr().err


# ── Fuzzy match ───────────────────────────────────────────────────────────────

def test_article_prefix_is_an_exact_match(capsys):
    # The source writes every feast with a leading article. That is the normal
    # form, not a near miss, so it must not warn (#45).
    rows = [_row('2025-11-30', 'The First Sunday of Advent')]
    bounds = detect_bounds(rows)
    assert bounds['advent_i'] == '2025-11-30'
    assert 'WARNING' not in capsys.readouterr().err


def test_rank_and_colour_decorations_are_an_exact_match(capsys):
    # "the baptism of the lord - hd [proper 1] (white)" is how the CSV writes
    # a feast; the decorations are stripped before matching.
    rows = [_row('2026-01-11', 'The Baptism of the Lord - HD [Proper 1] (white)')]
    bounds = detect_bounds(rows)
    assert bounds['epiphany'] == '2026-01-11'
    assert 'WARNING' not in capsys.readouterr().err


def test_phrase_buried_in_a_sentence_still_warns(capsys):
    # A real near miss: the phrase appears, but not as this row's title.
    rows = [_row('2025-11-30', 'Readings for the First Sunday of Advent begin overleaf')]
    bounds = detect_bounds(rows)
    assert bounds['advent_i'] == '2025-11-30'
    err = capsys.readouterr().err
    assert 'WARNING' in err
    assert 'advent_i' in err


def test_fuzzy_match_easter_with_suffix(capsys):
    rows = [_row('2026-04-05', 'Easter Day  Principal Feast')]
    bounds = detect_bounds(rows)
    # startswith('easter day') → exact match, no warning
    assert 'easter' in bounds
    assert 'WARNING' not in capsys.readouterr().err


def test_pentecost_with_the_prefix_is_exact(capsys):
    rows = [_row('2026-05-24', 'The Day of Pentecost')]
    bounds = detect_bounds(rows)
    assert 'pentecost' in bounds
    assert 'WARNING' not in capsys.readouterr().err
