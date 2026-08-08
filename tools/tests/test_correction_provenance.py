"""
Provenance checks on data/corrections.json — `source` and `id`.

ADR 0005 declared three `source` values and said the full schema lived in a
JSON Schema file beside the manifest. The file was never written and the field
grew to six values unremarked. That became load-bearing when ADR 0012 keyed the
QA line-break exemption on `source`: a typo that keeps the `pwc-errata-` prefix
still vouches, and one that loses it silently withdraws the exemption, so the
break it covered is reported as a column wrap by a rule that gates deploy.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from validate_corrections import PERMITTED_SOURCES, VOUCHING_PREFIX, validate_provenance

ROOT = Path(__file__).resolve().parent.parent.parent


def entry(**kw):
    return {"id": "some-id", "source": "editorial", **kw}


class TestSource:
    def test_a_known_source_passes(self):
        assert validate_provenance({"psalter": [entry()]}) == []

    def test_an_unknown_source_is_an_error(self):
        errors = validate_provenance({"psalter": [entry(source="made-up")]})
        assert len(errors) == 1
        assert "unknown source 'made-up'" in errors[0]

    def test_a_missing_source_is_an_error(self):
        errors = validate_provenance({"psalter": [{"id": "x"}]})
        assert len(errors) == 1
        assert "unknown source None" in errors[0]

    def test_a_typo_that_drops_the_vouching_prefix_is_caught(self):
        # The dangerous one: 'pwc-erata-ordinary' no longer starts with
        # 'pwc-errata-', so ADR 0012's exemption silently stops applying and the
        # errata's deliberate break gets reported as a column wrap.
        errors = validate_provenance({"office_text": [entry(source="pwc-erata-ordinary")]})
        assert len(errors) == 1
        assert VOUCHING_PREFIX in errors[0]     # the message explains the stakes

    def test_a_typo_that_keeps_the_vouching_prefix_is_also_caught(self):
        errors = validate_provenance({"office_text": [entry(source="pwc-errata-ordinaryy")]})
        assert len(errors) == 1

    def test_scalar_metadata_is_not_walked(self):
        assert validate_provenance({"version": 3, "psalter": [entry()]}) == []


class TestId:
    def test_a_missing_id_is_an_error(self):
        errors = validate_provenance({"psalter": [{"source": "editorial"}]})
        assert errors == ["psalter[0]: no 'id'"]

    def test_duplicate_ids_are_an_error_across_categories(self):
        # ADR 0005 makes `id` the link to the tracker; two corrections sharing
        # one make that link ambiguous in whichever direction it is followed.
        errors = validate_provenance({
            "psalter": [entry(id="dup")],
            "fats": [entry(id="dup")],
        })
        assert len(errors) == 1
        assert "duplicate id 'dup'" in errors[0]

    def test_distinct_ids_pass(self):
        assert validate_provenance({
            "psalter": [entry(id="one")],
            "fats": [entry(id="two")],
        }) == []


class TestTheRealManifest:
    def _manifest(self):
        return json.loads((ROOT / "data" / "corrections.json").read_text())

    def test_the_committed_manifest_is_clean(self):
        assert validate_provenance(self._manifest()) == []

    def test_every_permitted_source_is_documented(self):
        # The enum is the schema ADR 0005 never got, so each value carries the
        # sentence that says when to reach for it.
        assert all(isinstance(v, str) and v for v in PERMITTED_SOURCES.values())

    def test_only_errata_sources_may_vouch(self):
        # Guards the coupling from the other end: if a non-errata source ever
        # takes the prefix, it silently gains the power to exempt a line break.
        vouching = {s for s in PERMITTED_SOURCES if s.startswith(VOUCHING_PREFIX)}
        assert vouching == {"pwc-errata-ordinary", "pwc-errata-seasonal"}

    def test_the_manifest_uses_no_source_outside_the_enum(self):
        used = {e.get("source")
                for v in self._manifest().values() if isinstance(v, list)
                for e in v}
        assert used <= set(PERMITTED_SOURCES), used - set(PERMITTED_SOURCES)
