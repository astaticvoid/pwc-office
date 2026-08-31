"""The iOS build-number bump must move both configurations together.

TestFlight rejects a build number that has already been uploaded, so every ship
needs a fresh CURRENT_PROJECT_VERSION (CFBundleVersion). The value lives twice
in the pbxproj — the Debug and Release build configurations — and Xcode reads
both, so a bump that touched one and not the other would silently ship the same
build number twice, or a stale number. The tool must move both together, touch
nothing else in the file, and refuse (without writing) when the file cannot be
read unambiguously: configurations that disagree, or a count of version entries
other than two.
"""

import importlib.util
import pathlib
import textwrap

import pytest

TOOLS = pathlib.Path(__file__).resolve().parent.parent

_SPEC = importlib.util.spec_from_file_location(
    "bump_ios_version", TOOLS / "bump_ios_version.py"
)
biv = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(biv)

ENTRY = "\t\t\t\tCURRENT_PROJECT_VERSION = {n};"

TWO_ONES = textwrap.dedent(
    """\
    // header comment
    a = 1;
    {e1}
    \t\t\t\tMARKETING_VERSION = 1.0;
    a = 2;
    {e2}
    \t\t\t\tMARKETING_VERSION = 1.0;
    tail
    """
).format(e1=ENTRY.format(n=1), e2=ENTRY.format(n=1))


@pytest.fixture
def pbxproj(tmp_path, monkeypatch):
    path = tmp_path / "project.pbxproj"
    path.write_text(TWO_ONES)
    monkeypatch.setattr(biv, "PBXPROJ", path)
    return path


def test_bumps_both_configurations_together(pbxproj):
    assert biv.main([]) == 0
    text = pbxproj.read_text()
    assert text.count("CURRENT_PROJECT_VERSION = 2;") == 2
    assert "CURRENT_PROJECT_VERSION = 1;" not in text


def test_touches_nothing_else(pbxproj):
    assert biv.main([]) == 0
    expected = TWO_ONES.replace(ENTRY.format(n=1), ENTRY.format(n=2))
    assert pbxproj.read_text() == expected


def test_increment_amount(pbxproj):
    assert biv.main(["3"]) == 0
    assert pbxproj.read_text().count("CURRENT_PROJECT_VERSION = 4;") == 2


def test_refuses_mismatched_configurations(pbxproj, capsys):
    mismatched = TWO_ONES.replace(
        "a = 2;\n" + ENTRY.format(n=1),
        "a = 2;\n" + ENTRY.format(n=4),
    )
    pbxproj.write_text(mismatched)
    assert biv.main([]) == 1
    assert "CURRENT_PROJECT_VERSION = 1;" in pbxproj.read_text()  # untouched
    assert "disagree" in capsys.readouterr().out


def test_refuses_wrong_entry_count(pbxproj, capsys):
    one_entry = TWO_ONES.replace(
        "a = 2;\n" + ENTRY.format(n=1) + "\n",
        "",
    )
    pbxproj.write_text(one_entry)
    assert biv.main([]) == 1
    assert "expected 2" in capsys.readouterr().out
