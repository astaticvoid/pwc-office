"""
Unit tests for check_text_quality.py — column-wrap detector (Batch 19.2).

Run: python3 -m pytest tools/tests/ -v  (from the repo root)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from check_text_quality import _check_prose_wraps, _seasonal_collect_leaders


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
