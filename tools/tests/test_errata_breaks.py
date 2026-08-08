"""
Tests for the errata-break exemption (ADR 0012).

Two rules read sanctioned line breaks out of `data/corrections.json`:
`collect-and-dismissal-no-orphan-breaks` in validate_office.cjs, and the litany
column-wrap scan here. They must agree — but they are in different languages, so
`corrections_lib.py`'s remedy of one shared walk is unavailable. The conformance
test at the bottom is the substitute: one fixture, both readers, identical sets.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import check_text_quality
from check_text_quality import errata_breaks

ROOT = Path(__file__).resolve().parent.parent.parent

OFFICES = {
    "_shared": {"reading_response_ordinary": [{"type": "leader", "text": "Holy Word."}]},
    "ordinary-monday-mp": {
        "dismissal": [{"type": "leader", "text": "May God, who has called us\nout of darkness."}],
        "reading_response": {"type": "shared", "key": "reading_response_ordinary"},
    },
    "ordinary-tuesday-mp": {
        "dismissal": [{"type": "leader", "text": "May God, who has called us\nout of darkness."}],
    },
}


def _manifest(*corrections):
    return {"office_text": list(corrections)}


def _breaks(tmp_path, monkeypatch, manifest, offices=OFFICES):
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    (data / "corrections.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(check_text_quality, "ROOT", tmp_path)
    return errata_breaks(offices)


class TestScope:
    def test_vouches_only_where_the_correction_points(self, tmp_path, monkeypatch):
        # The same line exists at tuesday, which has no correction. Global
        # matching would sanction it there too and make the lifecycle property
        # ("drop the correction and the line stops being sanctioned") false,
        # since six dismissal lines repeat verbatim across two to four forms.
        got = _breaks(tmp_path, monkeypatch, _manifest({
            "id": "errata-x", "source": "pwc-errata-ordinary",
            "office": "ordinary-monday-mp", "field": "dismissal",
            "old": "a", "new": "May God, who has called us\nout of darkness.",
        }))
        assert got == {"ordinary-monday-mp|dismissal May God, who has called us"}

    def test_shared_correction_vouches_at_every_referencing_form(self, tmp_path, monkeypatch):
        # The opposite of corrections_lib.iter_text_segments, which refuses to
        # follow shared references. Applying through one would rewrite siblings
        # silently; vouching through one is right, because the text is there.
        got = _breaks(tmp_path, monkeypatch, _manifest({
            "id": "errata-s", "source": "pwc-errata-ordinary",
            "office": "_shared", "field": "reading_response_ordinary",
            "old": "a", "new": "Holy Word,\nholy Wisdom.",
        }))
        assert got == {"ordinary-monday-mp|reading_response Holy Word,"}


class TestSelection:
    def test_keyed_on_source_not_on_an_id_prefix(self, tmp_path, monkeypatch):
        # An id is a label; renaming one must not change what is enforced.
        got = _breaks(tmp_path, monkeypatch, _manifest({
            "id": "errata-looks-right", "source": "editorial",
            "office": "ordinary-monday-mp", "field": "dismissal",
            "old": "a", "new": "May God, who has called us\nout of darkness.",
        }))
        assert got == set()

    def test_blank_lines_vouch_for_nothing(self, tmp_path, monkeypatch):
        # An errata block with a stanza gap yields "" from the split. It is
        # inert at both call sites only because they test truthiness first.
        got = _breaks(tmp_path, monkeypatch, _manifest({
            "id": "errata-b", "source": "pwc-errata-seasonal",
            "office": "ordinary-monday-mp", "field": "dismissal",
            "old": "a", "new": "First line.\n\nSecond line,\nthird.",
        }))
        assert all(not e.endswith(" ") for e in got)
        assert got == {"ordinary-monday-mp|dismissal First line.",
                       "ordinary-monday-mp|dismissal Second line,"}

    def test_last_line_is_not_a_break(self, tmp_path, monkeypatch):
        got = _breaks(tmp_path, monkeypatch, _manifest({
            "id": "errata-l", "source": "pwc-errata-seasonal",
            "office": "ordinary-monday-mp", "field": "dismissal",
            "old": "a", "new": "Only line, no break.",
        }))
        assert got == set()

    def test_whole_field_corrections_are_ignored(self, tmp_path, monkeypatch):
        got = _breaks(tmp_path, monkeypatch, _manifest({
            "id": "errata-w", "source": "pwc-errata-seasonal",
            "office": "ordinary-monday-mp", "field": "dismissal",
            "old": [], "new": [{"type": "leader", "text": "a\nb"}],
        }))
        assert got == set()


class TestFailsOpenOnTheExemption:
    def test_absent_manifest_sanctions_nothing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(check_text_quality, "ROOT", tmp_path)
        assert errata_breaks(OFFICES) == set()

    def test_unreadable_manifest_sanctions_nothing(self, tmp_path, monkeypatch):
        data = tmp_path / "data"
        data.mkdir()
        (data / "corrections.json").write_text("{not json")
        monkeypatch.setattr(check_text_quality, "ROOT", tmp_path)
        # Failing open on the exemption is failing closed on the rule.
        assert errata_breaks(OFFICES) == set()


class TestScannerHonoursScope:
    def test_a_sanctioned_line_is_not_flagged_at_its_own_location(self):
        findings = []
        check_text_quality._check_prose_wraps(
            "May God, who has called us\nout of darkness.", "loc", findings,
            frozenset({"ordinary-monday-mp|dismissal May God, who has called us"}),
            "ordinary-monday-mp|dismissal")
        assert findings == []

    def test_the_same_line_is_still_flagged_elsewhere(self):
        findings = []
        check_text_quality._check_prose_wraps(
            "May God, who has called us\nout of darkness.", "loc", findings,
            frozenset({"ordinary-monday-mp|dismissal May God, who has called us"}),
            "ordinary-tuesday-mp|dismissal")
        assert len(findings) == 1


def test_js_and_python_agree_on_the_same_manifest(tmp_path, monkeypatch):
    """The conformance test the two-language split makes necessary.

    validate_office.cjs and check_text_quality.py each hand-roll the same walk
    over office_text. Nothing but this test holds them to one reading — and they
    have already drifted once, on whether a line is trimmed at one end or both.
    """
    manifest = _manifest(
        {"id": "e1", "source": "pwc-errata-ordinary", "office": "ordinary-monday-mp",
         "field": "dismissal", "old": "a", "new": "May God, who has called us\nout of darkness."},
        {"id": "e2", "source": "pwc-errata-seasonal", "office": "_shared",
         "field": "reading_response_ordinary", "old": "a", "new": "Holy Word,\nholy Wisdom."},
        {"id": "e3", "source": "editorial", "office": "ordinary-tuesday-mp",
         "field": "dismissal", "old": "a", "new": "Not errata,\nso not sanctioned."},
        {"id": "e4", "source": "pwc-errata-seasonal", "office": "ordinary-tuesday-mp",
         "field": "dismissal", "old": "a", "new": "Stanza one.\n\nStanza two,\nend."},
    )
    py = _breaks(tmp_path, monkeypatch, manifest)

    script = """
    const { readFileSync } = require('fs');
    const offices = JSON.parse(readFileSync(process.argv[1], 'utf8'));
    const corr = JSON.parse(readFileSync(process.argv[2], 'utf8'));
    const sharedUsers = {};
    for (const [fk, form] of Object.entries(offices)) {
      if (fk.startsWith('_')) continue;
      for (const [field, value] of Object.entries(form)) {
        if (value && value.type === 'shared' && value.key) {
          (sharedUsers[value.key] ||= []).push(`${fk}|${field}`);
        }
      }
    }
    const out = new Set();
    for (const c of corr.office_text || []) {
      if (!String(c.source || '').startsWith('pwc-errata-')) continue;
      if (typeof c.new !== 'string') continue;
      const targets = c.office === '_shared'
        ? (sharedUsers[c.field] || []) : [`${c.office}|${c.field}`];
      const lines = c.new.split('\\n');
      for (let i = 0; i < lines.length - 1; i++) {
        const line = lines[i].trim();
        if (!line) continue;
        for (const t of targets) out.add(`${t} ${line}`);
      }
    }
    console.log(JSON.stringify([...out].sort()));
    """
    offices_file = tmp_path / "offices.json"
    offices_file.write_text(json.dumps(OFFICES))
    corr_file = tmp_path / "data" / "corrections.json"

    try:
        result = subprocess.run(
            ["node", "-e", script, "--", str(offices_file), str(corr_file)],
            capture_output=True, text=True, cwd=str(ROOT))
    except FileNotFoundError:
        pytest.skip("node is not installed")

    # Skip only when node is genuinely absent. A node that runs and fails is a
    # failure — skipping on any non-zero would have hidden the argv bug that
    # made this test silently not run at all.
    assert result.returncode == 0, f"node errored: {result.stderr.strip()[:300]}"
    assert sorted(py) == json.loads(result.stdout)


def test_the_js_snippet_matches_the_validator_it_stands_in_for():
    """Guard the guard: the conformance test embeds a copy of the validator's
    reader, so it is only meaningful while the two stay identical."""
    src = (ROOT / "tools" / "validate_office.cjs").read_text()
    for line in ("if (!String(c.source || '').startsWith('pwc-errata-')) continue;",
                 "? (sharedUsers[c.field] || [])",
                 "const line = lines[i].trim();",
                 "for (const t of targets) ERRATA_BREAKS.add(`${t} ${line}`);"):
        assert line in src, f"validate_office.cjs no longer contains: {line}"
