"""data/ matching the manifest does not mean it came from the current extractor.

Hashes over data/ catch a file edited by hand. They say nothing about the more
likely mistake: changing an extractor and not re-running the pipeline, which
leaves code and data disagreeing while every recorded hash still matches. That
state was fully green — 201 tests, coherence 100/100 — and would have deployed
(#51).

These tests pin the source hashes into the manifest and prove the check fires.
"""

import importlib.util
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


integrity = _load("check_data_integrity")
manifest_tool = _load("update_extract_manifest")

MANIFEST = ROOT / "tools" / "extract_manifest.json"


@pytest.fixture
def manifest():
    if not MANIFEST.exists():
        pytest.skip("manifest not generated")
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_manifest_records_source_hashes(manifest):
    recorded = manifest.get("source_hashes")
    assert recorded, (
        "extract_manifest.json has no source_hashes. Without them, editing an "
        "extractor and skipping `make extract` passes every check. Run `make extract`."
    )
    expected = {rel for rel in manifest_tool.EXTRACTION_SOURCES if (ROOT / rel).exists()}
    assert set(recorded) == expected, (
        f"source_hashes covers {sorted(set(recorded))} but EXTRACTION_SOURCES "
        f"expects {sorted(expected)} — re-run `make extract` after changing the list."
    )


def test_clean_tree_reports_no_drift(manifest):
    assert integrity.check_sources(manifest) == []


def test_a_changed_source_is_detected(manifest):
    # The regression this exists for: one source no longer matches what produced
    # the data. Simulated by corrupting the recorded hash, which is equivalent to
    # editing the file and not re-extracting.
    tampered = dict(manifest)
    tampered["source_hashes"] = dict(manifest["source_hashes"])
    victim = "tools/extract_offices.py"
    assert victim in tampered["source_hashes"], "extractor not tracked"
    tampered["source_hashes"][victim] = "0" * 64
    assert integrity.check_sources(tampered) == [victim]


def test_a_missing_source_is_detected(manifest):
    tampered = dict(manifest)
    tampered["source_hashes"] = {**manifest["source_hashes"], "tools/gone.py": "0" * 64}
    assert "tools/gone.py (missing)" in integrity.check_sources(tampered)


def test_corrections_are_treated_as_a_source(manifest):
    # corrections.json is an input: editing it changes output exactly as editing
    # code does, so it has to be tracked the same way.
    assert "data/corrections.json" in manifest["source_hashes"]
