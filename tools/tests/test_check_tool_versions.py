"""The recorded toolchain version must survive the JSON round-trip.

`fitz.version` is a tuple. The manifest holds what `json.load` produced, which
is a list. Comparing them with `==` is always False, so the check printed
VERSION WARN on every run since it was written — including every run where the
versions matched. A warning that always fires is a warning nobody reads, which
is the failure mode that matters: PyMuPDF decides line breaks from sub-point
geometry, so real drift in it is worth seeing.
"""

import importlib.util
import json
import pathlib
import sys

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "check_data_integrity",
    pathlib.Path(__file__).resolve().parent.parent / "check_data_integrity.py",
)
cdi = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cdi)


def test_tuple_matches_the_json_decoded_list():
    """The exact shape the manifest produces: recorded as a list, compared
    against the tuple PyMuPDF reports."""
    assert cdi._same_version(("1.28.0", "1.28.0", None), ["1.28.0", "1.28.0", None])


def test_a_real_version_difference_is_still_a_difference():
    assert not cdi._same_version(("1.28.0", "1.29.0", None), ["1.28.0", "1.28.0", None])


def test_plain_strings_still_compare():
    assert cdi._same_version("1.28.0", "1.28.0")
    assert not cdi._same_version("1.28.0", "not found")


def test_matching_versions_report_ok_not_warn(capsys):
    """The regression itself: a matching version printed WARN."""
    fitz = pytest.importorskip("fitz")
    cdi.check_tool_versions({"tool_versions": {"fitz": list(fitz.version)}})
    out = capsys.readouterr().out
    assert "VERSION OK" in out
    assert "VERSION WARN" not in out


@pytest.fixture
def no_fitz(monkeypatch):
    """Make `import fitz` raise ImportError, as on a checkout without PyMuPDF."""
    import builtins
    real_import = builtins.__import__

    def fake(name, *args, **kwargs):
        if name == "fitz":
            raise ImportError("no fitz")
        return real_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "fitz", raising=False)
    monkeypatch.setattr(builtins, "__import__", fake)


def test_absent_fitz_warns_and_does_not_crash(no_fitz, capsys):
    """`fitz_ver` is bound only on the success path, so the early return is
    load-bearing: without it this raises UnboundLocalError out of main(), which
    exits 1 and takes `make test` with it — the only way this function can
    affect the exit status."""
    cdi.check_tool_versions({"tool_versions": {"fitz": ["1.28.0", "1.28.0", None]}})
    assert "VERSION WARN" in capsys.readouterr().out


def test_absent_fitz_is_silent_when_the_manifest_also_recorded_none(no_fitz, capsys):
    cdi.check_tool_versions({"tool_versions": {"fitz": "not found"}})
    assert capsys.readouterr().out == ""


def test_fitz_appearing_since_the_manifest_was_written_warns(capsys):
    pytest.importorskip("fitz")
    cdi.check_tool_versions({"tool_versions": {"fitz": "not found"}})
    assert "now available" in capsys.readouterr().out


def test_main_actually_calls_the_check(tmp_path, monkeypatch, capsys):
    """Coverage of the function is worthless if nothing calls it: deleting the
    call from main() otherwise leaves this file entirely green."""
    pytest.importorskip("fitz")
    manifest = tmp_path / "extract_manifest.json"
    manifest.write_text(json.dumps({
        "tool_versions": {"fitz": ["9.9.9", "9.9.9", None]}, "files": {},
    }))
    monkeypatch.setattr(cdi, "MANIFEST_PATH", manifest)
    monkeypatch.setattr(cdi, "ROOT", tmp_path)
    cdi.main()
    assert "VERSION WARN" in capsys.readouterr().out


def test_version_drift_never_changes_the_exit_status(capsys):
    """A version difference is a proxy for extraction drift, and a known-unsound
    one: the 2026-08-03 manifest was written under MuPDF 1.29.0 and re-running
    under 1.28.0 reproduced data/offices.json byte for byte. The file hashes
    measure the thing itself and decide the exit status; this only reports."""
    cdi.check_tool_versions({"tool_versions": {"fitz": ["9.9.9", "9.9.9", None]}})
    assert "VERSION WARN" in capsys.readouterr().out


def test_no_recorded_versions_is_silent(capsys):
    cdi.check_tool_versions({})
    assert capsys.readouterr().out == ""


def test_a_manifest_with_no_fitz_entry_reports_ok_not_warn(capsys):
    """`tool_versions` present but carrying no fitz key — pre-#51 manifests look
    like this. Nothing was recorded, so there is nothing to disagree with."""
    pytest.importorskip("fitz")
    cdi.check_tool_versions({"tool_versions": {"something-else": "1.0"}})
    out = capsys.readouterr().out
    assert "VERSION OK" in out
    assert "VERSION WARN" not in out


def test_a_broken_fitz_install_is_not_swallowed(monkeypatch, capsys):
    """Only ImportError means "PyMuPDF isn't here". Widening the except would
    turn a corrupt install — which extraction cannot survive — into a cheerful
    warning and let the run continue."""
    import builtins
    real_import = builtins.__import__

    def fake(name, *args, **kwargs):
        if name == "fitz":
            raise RuntimeError("corrupt shared library")
        return real_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "fitz", raising=False)
    monkeypatch.setattr(builtins, "__import__", fake)
    with pytest.raises(RuntimeError):
        cdi.check_tool_versions({"tool_versions": {"fitz": ["1.28.0", "1.28.0", None]}})
