"""The mobile-sync staleness guard must fail on any dist/native mismatch.

`npx cap sync` deletes each native web dir and re-copies it from dist/, so the
copy is authoritative but only as fresh as the last sync — and it is gitignored,
so staleness is invisible to git. An Xcode archive then bundles the old copy
behind a clean `git status` (that is exactly how the first TestFlight ship went
stale). check_mobile_sync.py is the only signal; these tests pin the two
directions it must hold and the tolerance it may not exceed:

  - every dist/ file must exist in the synced dir with identical bytes
    (a missing or differing file fails and names it)
  - nothing may linger in the synced dir that dist/ no longer has,
    except the Capacitor-injected plugin shims — which must all be present
    (an interrupted sync is a failure, not a pass)
"""

import importlib.util
import pathlib

import pytest

TOOLS = pathlib.Path(__file__).resolve().parent.parent

_SPEC = importlib.util.spec_from_file_location(
    "check_mobile_sync", TOOLS / "check_mobile_sync.py"
)
cms = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cms)


def _write(path: pathlib.Path, content: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """dist/ with a couple of files (one nested), mirrored into ios public."""
    dist = tmp_path / "dist"
    ios = tmp_path / "ios"
    android = tmp_path / "android"
    for rel, content in (
        ("index.html", "html"),
        ("app.js", "app"),
        ("data/version.json", "version"),
    ):
        _write(dist / rel, content)
        _write(ios / rel, content)
        _write(android / rel, content)
    # Capacitor shims are injected into the native dirs after the copy.
    for public in (ios, android):
        for shim in ("capacitor-plugins.js", "cordova.js", "cordova_plugins.js"):
            _write(public / shim, "shim")
    monkeypatch.setattr(cms, "DIST", dist)
    monkeypatch.setattr(cms, "PLATFORMS", {"ios": ios, "android": android})
    return dist, ios, android


def test_matching_tree_passes(tree):
    assert cms.main() == 0


def test_missing_file_fails_and_names_it(tree, capsys):
    dist, ios, _ = tree
    (ios / "app.js").unlink()
    assert cms.main() == 1
    out = capsys.readouterr().out
    assert "app.js" in out and "absent from ios" in out
    assert "android" not in out  # android still matches; only ios failed


def test_differing_file_fails(tree):
    dist, ios, _ = tree
    (ios / "data" / "version.json").write_text("different")
    assert cms.main() == 1


def test_leftover_file_fails(tree, capsys):
    dist, ios, _ = tree
    (ios / "stale-debris.txt").write_text("x")
    assert cms.main() == 1
    assert "stale-debris.txt" in capsys.readouterr().out


def test_injected_shims_are_required(tree):
    dist, ios, _ = tree
    (ios / "capacitor-plugins.js").unlink()  # interrupted sync
    assert cms.main() == 1


def test_no_native_platforms_is_a_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(cms, "DIST", tmp_path / "dist")
    monkeypatch.setattr(cms, "PLATFORMS", {"ios": tmp_path / "nope"})
    _write(tmp_path / "dist" / "index.html")
    assert cms.main() == 0


def test_missing_dist_dir_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(cms, "DIST", tmp_path / "dist")  # does not exist
    monkeypatch.setattr(cms, "PLATFORMS", {"ios": tmp_path / "public"})
    assert cms.main() == 1
