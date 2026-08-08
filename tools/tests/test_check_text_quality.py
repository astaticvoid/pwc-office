"""
Unit tests for check_text_quality.py — column-wrap detector (Batch 19.2).

Run: python3 -m pytest tools/tests/ -v  (from the repo root)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import check_text_quality
from check_text_quality import (_check_prose_wraps, _seasonal_collect_leaders,
                                _litany_leaders, check_prose_fields)


class TestColumnWrap:
    def _wraps(self, text):
        findings = []
        _check_prose_wraps(text, "loc", findings)
        return findings

    def test_single_line_prose_ok(self):
        assert self._wraps("Almighty God, you sent your Son. Amen.") == []

    def test_mid_clause_wrap_flagged(self):
        # Non-final line ends without terminal punctuation → suspected wrap.
        findings = self._wraps("Almighty God, you sent your Son\n"
                               "to be the light of the world. Amen.")
        assert len(findings) == 1
        assert findings[0][1] == "column_wrap"

    def test_comma_break_allowed(self):
        # A line ending in a comma is a natural clause break, not a wrap.
        assert self._wraps("Almighty God,\nyou sent your Son. Amen.") == []

    def test_last_line_never_flagged(self):
        # The final line has no following line to wrap into.
        assert self._wraps("first line ends clean.\ntrailing fragment") == []

    def test_terminal_punctuation_variants(self):
        # em-dash, colon, semicolon, close-quote all count as terminal.
        assert self._wraps("who lives and reigns—\nnow and for ever. Amen.") == []
        assert self._wraps("let us pray:\nour Father. Amen.") == []


class TestSeasonalCollectLeaders:
    def test_recurses_into_alternatives(self):
        segs = [{
            "type": "alternatives",
            "groups": [
                {"label": "I", "segments": [{"type": "leader", "text": "Collect one."}]},
                {"label": "II", "segments": [{"type": "leader", "text": "Collect two."}]},
            ],
        }]
        out = []
        _seasonal_collect_leaders(segs, "sc", out)
        assert [t for _, t in out] == ["Collect one.", "Collect two."]

    def test_ignores_rubric_and_response(self):
        segs = [
            {"type": "rubric", "text": "The Collect."},
            {"type": "leader", "text": "Almighty God. Amen."},
            {"type": "response", "text": "Amen."},
        ]
        out = []
        _seasonal_collect_leaders(segs, "sc", out)
        assert [t for _, t in out] == ["Almighty God. Amen."]


class TestLitanyLeaders:
    def test_extracts_litany_leaders(self):
        segs = [
            {"type": "rubric", "text": "The Litany is said or sung."},
            {"type": "leader", "text": "God of Israel, may this day be one of fulfillment and peace."},
            {"type": "response", "text": "Holy One, hear and have mercy."},
        ]
        out = []
        _litany_leaders(segs, "lit", out)
        assert [t for _, t in out] == ["God of Israel, may this day be one of fulfillment and peace."]

    def test_flags_mid_clause_wrap_in_litany(self):
        wraps = []
        _check_prose_wraps("Watchful at all times, let us pray to God for strength to stand with\nconfidence.", "loc", wraps)
        assert len(wraps) == 1
        assert wraps[0][0] == "loc"
        assert wraps[0][1] == "column_wrap"
        assert "stand with" in wraps[0][2]

    def test_accepts_sentence_break_in_litany(self):
        wraps = []
        _check_prose_wraps("Let us pray to the Creator of the universe.\nHoly One, by the good news of our salvation", "loc", wraps)
        assert wraps == []


class TestEachLeaderScannedOnce:
    """A stray `_check_prose_wraps` call sat outside the litany loop, re-scanning
    on the loop's leaked `text`/`loc`. It double-reported the last leader of every
    litany, and where a form's litany yielded no leaders at all it reported again
    against whatever the previous form or section had left in those names — a
    finding attributed to a location that had already been scanned."""

    def _findings(self, tmp_path, monkeypatch, offices):
        data = tmp_path / "data"
        data.mkdir()
        (data / "offices.json").write_text(json.dumps(offices))
        monkeypatch.setattr(check_text_quality, "ROOT", tmp_path)
        findings = []
        check_prose_fields(findings)
        return findings

    def test_last_litany_leader_reported_once(self, tmp_path, monkeypatch):
        findings = self._findings(tmp_path, monkeypatch, {
            "form-a": {"litany": [
                {"type": "leader", "text": "Comfort and sustain\nthose who are lonely."},
                {"type": "leader", "text": "Give your peace to all\nwho have passed from this life."},
            ]},
        })
        assert len(findings) == len(set(findings)) == 2

    def test_a_litany_with_no_leaders_reports_nothing_of_its_own(self, tmp_path, monkeypatch):
        # form-b's litany has no leader to scan. Nothing about form-b may be
        # reported, and form-a must not be reported a second time under it.
        findings = self._findings(tmp_path, monkeypatch, {
            "form-a": {"litany": [
                {"type": "leader", "text": "Fill all who proclaim the word\nof truth."},
            ]},
            "form-b": {
                "seasonal_collects": [
                    {"type": "leader", "text": "Almighty God, you sent your Son\nto be the light."},
                ],
                "litany": [{"type": "response", "text": "Hear and have mercy."}],
            },
        })
        locations = [loc for loc, _, _ in findings]
        assert len(locations) == len(set(locations)) == 2
        assert sorted(locations) == [
            "offices.json['form-a'].litany[0]",
            "offices.json['form-b'].seasonal_collects[0]",
        ]
