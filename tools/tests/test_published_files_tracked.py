"""Every published data file is covered by the integrity manifest.

`check_data_integrity.py` can only report drift in files the manifest records.
A published file left out is not partially protected — it is entirely invisible:
hand-edit it, or leave it stale after an extractor change, and the check still
prints "Integrity check passed."

`data/season_bounds.json` sat outside the manifest that way. It is written by
`convert_lectionary.py`, fetched by `web/app.js` and `cli/office.js`, and
required by `check_dist.py`, and nothing would have noticed it drifting. Adding
it fixes that instance; this test is what makes the next omission fail rather
than go unnoticed, by deriving the expectation from the consumer instead of
restating the same list a second time.
"""

import ast
import importlib.util
import pathlib

import pytest

TOOLS = pathlib.Path(__file__).resolve().parent.parent

_SPEC = importlib.util.spec_from_file_location(
    "update_extract_manifest", TOOLS / "update_extract_manifest.py"
)
uem = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(uem)

def _paths_required_by_check_dist() -> set[str]:
    """The `data/…json` paths named in `check_dist.py`, read via AST.

    Derived from the consumer rather than restated here: a file worth failing
    the build over is a file worth guarding the integrity of, so adding one
    there cannot silently skip this check.

    Parsed rather than regexed. A pattern like `data/[a-z_/]*\\.json` cannot
    match a path containing a digit, hyphen or capital — `data/bcp1962/…` or
    `data/lectionary-index.json` would simply not be seen, and because the other
    literals still match, a non-emptiness guard would not notice. Every string
    constant is inspected instead, so the match set cannot silently shrink.
    """
    tree = ast.parse((TOOLS / "check_dist.py").read_text(encoding="utf-8"))
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.startswith("data/")
        and node.value.endswith(".json")
    }


def test_the_derivation_actually_sees_the_published_files():
    """Guard on the guard: if the parse stopped finding anything, the check
    below would pass vacuously. season_bounds.json is named because it is the
    omission that prompted this file."""
    required = _paths_required_by_check_dist()
    assert "data/season_bounds.json" in required, (
        f"check_dist.py no longer names season_bounds.json where this can see "
        f"it — found {sorted(required)}"
    )


def test_check_dist_requirements_are_all_in_the_manifest():
    """No exclusion list. `data/paragraphs.json` is published and app-fetched but
    not currently required by check_dist.py; if that changes, this should fail
    and force the question rather than quietly subtracting it."""
    missing = _paths_required_by_check_dist() - set(uem.PUBLISHED_FILES)
    assert not missing, (
        f"named by check_dist.py but absent from PUBLISHED_FILES, so "
        f"check-integrity cannot see them: {sorted(missing)}"
    )


def test_every_tracked_file_actually_exists_in_a_built_tree():
    """A typo in PUBLISHED_FILES makes `make extract` fail rather than silently
    track nothing — this catches it in the local edit-then-`make test` loop.

    Gated on data/lectionary/ rather than on any member of PUBLISHED_FILES: the
    failure this module exists for is a derivation chain that stops writing its
    published file, and using one of those files as the sentinel would skip the
    test in exactly that case.
    """
    root = TOOLS.parent
    if not (root / "data" / "lectionary").is_dir():
        pytest.skip("data/ not extracted in this checkout")
    for rel in uem.PUBLISHED_FILES:
        assert (root / rel).exists(), f"{rel} is tracked but does not exist"
