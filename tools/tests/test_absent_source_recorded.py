"""A deleted extraction input is recorded, not forgotten.

`source_hashes()` used to skip a listed source that did not exist. The key then
simply vanished from the committed manifest on the next `make extract`, taking
with it any record that the input was ever expected — so `check_data_integrity`
had nothing to miss.

That is not hypothetical. Reproduced against the real tree:

    rm data/corrections.json && make extract && make test

republished every office with `data/offices.json` reverting from `c7522a6dd4e7`
to `c2953ce5d05c` — the Synod errata and every other correction silently gone —
and printed "Integrity check passed."

Recording `null` makes the manifest a statement of the full expected input set
rather than of whatever happened to be lying around when it was written, and a
null is drift — so that sequence now fails instead of deploying.

A warning would not have been enough. `check-integrity` is the gate on
`deploy-staging` and `deploy`, so anything that still exits 0 ships the tree
anyway; the first attempt at this warned, and the corrections-dropped tree
deployed exactly as before. Retiring an input for real means removing it from
`EXTRACTION_SOURCES`, which is a reviewable edit — unlike a file going missing
from someone's worktree.
"""

import importlib.util
import json
import pathlib

import pytest

TOOLS = pathlib.Path(__file__).resolve().parent.parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


uem = _load("update_extract_manifest")
cdi = _load("check_data_integrity")


@pytest.fixture
def fake_root(tmp_path, monkeypatch):
    """A tree containing every EXTRACTION_SOURCES entry, so absence is the
    single variable under test."""
    for rel in uem.EXTRACTION_SOURCES:
        if "*" in rel:
            rel = rel.replace("*", "2026")
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"contents of {rel}")
    monkeypatch.setattr(cdi, "ROOT", tmp_path)
    return tmp_path


def test_a_present_source_is_hashed(fake_root):
    recorded = uem.source_hashes(fake_root)
    assert recorded["data/corrections.json"], "a present source must carry a hash"


def test_an_absent_source_is_recorded_as_null_not_dropped(fake_root):
    (fake_root / "data" / "corrections.json").unlink()
    recorded = uem.source_hashes(fake_root)
    assert "data/corrections.json" in recorded, \
        "the key vanished — the manifest no longer records that the input was expected"
    assert recorded["data/corrections.json"] is None


def test_still_absent_is_drift_and_blocks(fake_root):
    """data/ was published without an input the pipeline declares it needs. A
    warning would not do: check-integrity is the gate on deploy-staging and
    deploy, so anything short of drift ships the corrections-dropped tree.

    Retiring an input for real is an edit to EXTRACTION_SOURCES, which is
    reviewable. A file missing from a worktree is not."""
    (fake_root / "data" / "corrections.json").unlink()
    drifted = cdi.check_sources({"source_hashes": {"data/corrections.json": None}})
    assert drifted, "an absent recorded source must fail, not merely warn"


def test_a_source_reappearing_is_also_drift(fake_root):
    """The other direction: data/ was published without the input and the input
    is back, so the published files predate it."""
    drifted = cdi.check_sources({"source_hashes": {"data/corrections.json": None}})
    assert drifted
    assert "present again now" in drifted[0]


def test_a_recorded_hash_that_no_longer_matches_is_still_drift(fake_root):
    """The pre-existing behaviour, pinned so the null handling cannot swallow it."""
    drifted = cdi.check_sources({"source_hashes": {"data/corrections.json": "0" * 64}})
    assert drifted == ["data/corrections.json"]


def test_the_drift_message_names_the_retirement_path(fake_root, capsys):
    """Its siblings all say what to do; this one used to say nothing, and
    `make extract` — the obvious guess — regenerates the identical null and
    cannot clear it."""
    (fake_root / "data" / "corrections.json").unlink()
    cdi.check_sources({"source_hashes": {"data/corrections.json": None}})
    assert "EXTRACTION_SOURCES" in capsys.readouterr().out


def test_retiring_an_input_is_removing_it_from_the_list(fake_root, capsys):
    """The supported way out. Nothing recorded, nothing to drift against."""
    drifted = cdi.check_sources({"source_hashes": {
        "tools/extract_lib.py": uem.file_sha256(fake_root / "tools" / "extract_lib.py"),
    }})
    assert drifted == []
    assert "SOURCES OK   1 extraction source(s)" in capsys.readouterr().out


def test_globs_record_concrete_paths_and_no_null(fake_root):
    """A pattern names a set, so zero matches is not an absence to record —
    it is indistinguishable from a year not yet added."""
    recorded = uem.source_hashes(fake_root)
    assert "sources/bas_short_2026.csv" in recorded
    assert not any("*" in k for k in recorded)
    for csv in (fake_root / "sources").glob("bas_short_*.csv"):
        csv.unlink()
    assert not [k for k in uem.source_hashes(fake_root) if k.startswith("sources/")]


def test_regenerating_then_checking_does_not_launder_the_absence(fake_root, capsys):
    """The whole flow, which is where the previous design failed.

    `make extract` rewrites the manifest and `check-integrity` then reads what
    was just written — the laundering pattern that hid a stale offices.json for
    days. Writing the null and reading it back in one breath must still be a
    non-zero exit, or the guard only works for someone reading a stale manifest.
    """
    (fake_root / "data" / "corrections.json").unlink()
    manifest = json.loads(json.dumps({"source_hashes": uem.source_hashes(fake_root)}))
    assert cdi.check_sources(manifest), \
        "regenerate-then-check passed — the absence was laundered by the rewrite"


def test_an_old_manifest_without_nulls_is_read_exactly_as_before(fake_root):
    """Manifests committed before this change record no nulls. They must take
    the pre-existing branches unchanged, so a bisect across this commit does not
    produce a spurious verdict."""
    lib = fake_root / "tools" / "extract_lib.py"
    assert cdi.check_sources({"source_hashes": {
        "tools/extract_lib.py": uem.file_sha256(lib),
    }}) == []
    lib.write_text("edited")
    assert cdi.check_sources({"source_hashes": {
        "tools/extract_lib.py": "0" * 64,
    }}) == ["tools/extract_lib.py"]
