"""Every published file is derived on every run, even with nothing to correct.

`apply_corrections.py` is the last stage of four pipeline chains. It reads a
`.build/` artifact and writes the file the app, the manifest and the integrity
check consume. Correcting that file is the incidental part — deriving it is the
job.

Wrapping a chain in `if corrections.get(<category>):` breaks that, and breaks it
invisibly: with a pre-existing published file the stale copy simply survives, and
`update_extract_manifest.py` then rehashes it so `make check-integrity` passes.
That shipped for `office_text` and turned CI red for four days with
`ERROR: missing data files: ['data/offices.json']` before anyone connected the
two. The other three chains carried the identical guard.

Ask of these tests what defect makes them fail: re-introducing any guard that
makes a derivation conditional on there being a correction to apply.
"""

import importlib.util
import json
import pathlib
import shutil

import pytest

TOOLS = pathlib.Path(__file__).resolve().parent.parent


def _load(monkeypatch, root: pathlib.Path):
    """Import apply_corrections with its ROOT/DATA/BUILD pointed at a tmpdir."""
    spec = importlib.util.spec_from_file_location(
        "apply_corrections_undertest", TOOLS / "apply_corrections.py"
    )
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.syspath_prepend(str(TOOLS))
    spec.loader.exec_module(mod)
    mod.ROOT = root
    mod.DATA = root / "data"
    mod.BUILD = root / ".build"
    mod.CORRECTIONS = root / "data" / "corrections.json"
    mod._misses.clear()
    return mod


OFFICES = {"advent-mp": {"title": "T", "litany": [{"type": "leader", "text": "hello"}]}}
PSALTER = {"1": {"text": "Blessed is the one"}}
FATS = {"Alban": {"bio": "a martyr"}}
LECTIONARY = {"2026-01": {"2026-01-01": {"morning": {"lessons": ["Gen 1"], "psalms": ["100"]}}}}


@pytest.fixture
def tree(tmp_path):
    """A .build/ holding every stage artifact, and an empty data/."""
    build, data = tmp_path / ".build", tmp_path / "data"
    (build / "lectionary").mkdir(parents=True)
    data.mkdir()
    (build / "offices.2-normalized.json").write_text(json.dumps(OFFICES))
    (build / "psalter.1-extract.json").write_text(json.dumps(PSALTER))
    (build / "fats-saints.1-extract.json").write_text(json.dumps(FATS))
    for month, days in LECTIONARY.items():
        (build / "lectionary" / f"{month}.json").write_text(json.dumps(days))
    return tmp_path


ALL_EMPTY = {
    "version": 1, "office_text": [], "psalter": [], "fats": [],
    "lectionary_citations": [], "lectionary_psalms": [], "lectionary_lessons": [],
    "lectionary_names": [], "lectionary_ranks": [], "lectionary_colours": [],
    "lectionary_notes": [],
}


@pytest.mark.parametrize("published,expected", [
    ("data/offices.json", OFFICES),
    ("data/psalter.json", PSALTER),
    ("data/fats/saints.json", FATS),
    ("data/lectionary/2026-01.json", LECTIONARY["2026-01"]),
])
def test_derived_when_every_correction_list_is_empty(tree, monkeypatch, published, expected):
    """The steady state AGENTS.md drives toward: corrections migrated into the
    extractors, every list empty. Each published file must still be derived."""
    (tree / "data" / "corrections.json").write_text(json.dumps(ALL_EMPTY))
    mod = _load(monkeypatch, tree)
    mod.main()
    out = tree / published
    assert out.exists(), f"{published} was not derived with an empty correction list"
    assert json.loads(out.read_text()) == expected


@pytest.mark.parametrize("published", [
    "data/offices.json", "data/psalter.json",
    "data/fats/saints.json", "data/lectionary/2026-01.json",
])
def test_derived_when_the_manifest_is_absent_entirely(tree, monkeypatch, published):
    """Deleting corrections.json once nothing needs correcting must not silently
    publish nothing."""
    mod = _load(monkeypatch, tree)
    mod.main()
    assert (tree / published).exists(), f"{published} was not derived without a manifest"


@pytest.mark.parametrize("artifact", [
    "offices.2-normalized.json",
    "psalter.1-extract.json",
    "fats-saints.1-extract.json",
    "lectionary",
])
def test_missing_stage_input_fails_loudly(tree, monkeypatch, capsys, artifact):
    """A pipeline that did not run should say so, not raise FileNotFoundError
    from whichever stage happened to read first.

    Parametrised over every input because offices is derived first: a test that
    only unlinks the offices artifact exits before any other `_stage_input` call
    is reached, so it passes just as happily with the other three unchecked.
    """
    (tree / "data" / "corrections.json").write_text(json.dumps(ALL_EMPTY))
    target = tree / ".build" / artifact
    shutil.rmtree(target) if target.is_dir() else target.unlink()
    mod = _load(monkeypatch, tree)
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 1
    assert "make extract" in capsys.readouterr().err


def test_a_missing_late_input_publishes_nothing_at_all(tree, monkeypatch):
    """Inputs are checked before the first write, so a chain that cannot run
    aborts the whole stage rather than half of it.

    Validating lazily in derivation order would rewrite data/offices.json and
    only then discover the psalter artifact is gone, leaving data/ partly
    re-derived against a stale manifest — which check-integrity reports as
    "modified outside the extraction pipeline", the wrong remediation entirely.
    """
    (tree / "data" / "corrections.json").write_text(json.dumps(ALL_EMPTY))
    (tree / ".build" / "psalter.1-extract.json").unlink()
    mod = _load(monkeypatch, tree)
    with pytest.raises(SystemExit):
        mod.main()
    assert not (tree / "data" / "offices.json").exists(), \
        "offices.json was published before a later stage input was found missing"


def test_empty_lectionary_artifact_is_a_missing_input_not_an_empty_mirror(
    tree, monkeypatch, capsys
):
    """_seed_lectionary mirrors .build/lectionary exactly, deleting published
    months absent from it. So an empty source directory does not mean "nothing
    to copy" — it means "delete every published month", which it did at exit 0.
    An existence check alone does not distinguish the two."""
    (tree / "data" / "corrections.json").write_text(json.dumps(ALL_EMPTY))
    published = tree / "data" / "lectionary"
    published.mkdir()
    (published / "2026-01.json").write_text("{}")
    for month in (tree / ".build" / "lectionary").glob("*.json"):
        month.unlink()
    mod = _load(monkeypatch, tree)
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 1
    assert "make extract" in capsys.readouterr().err
    assert (published / "2026-01.json").exists(), \
        "published months were deleted by an empty build artifact"


def test_a_real_correction_still_applies(tree, monkeypatch):
    """The derivation being unconditional must not stop corrections working."""
    (tree / "data" / "corrections.json").write_text(json.dumps({
        **ALL_EMPTY,
        "psalter": [{"id": "p1", "psalm": 1, "old": "Blessed", "new": "Happy"}],
    }))
    mod = _load(monkeypatch, tree)
    mod.main()
    assert json.loads((tree / "data" / "psalter.json").read_text())["1"]["text"] \
        == "Happy is the one"


def test_a_lectionary_psalm_correction_replaces_the_indexed_entry(tree, monkeypatch):
    """#149: a bad psalm[] entry (a CSV typo surviving into a merged citation's
    `omit` span) is replaced whole, by date/office/index, like the other
    lectionary correction categories."""
    (tree / "data" / "corrections.json").write_text(json.dumps({
        **ALL_EMPTY,
        "lectionary_psalms": [{
            "id": "ps1", "date": "2026-01-01", "office": "morning", "index": 0,
            "old": "100", "new": {"citation": "100:1-5", "omit": [{"citation": "100:3-5"}]},
        }],
    }))
    mod = _load(monkeypatch, tree)
    mod.main()
    day = json.loads((tree / "data" / "lectionary" / "2026-01.json").read_text())["2026-01-01"]
    assert day["morning"]["psalms"] == [{"citation": "100:1-5", "omit": [{"citation": "100:3-5"}]}]
