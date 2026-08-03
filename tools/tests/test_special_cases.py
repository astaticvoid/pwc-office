"""Pin the number of hand-adjudicated special cases in the extractor.

Extraction decisions are supposed to come from measuring the page. Where that is
genuinely impossible a break is adjudicated by hand and named in a list, which is
honest but does not scale and hides the moment the measurement stops working.

So the counts are pinned here. A change is not necessarily wrong — a re-cut PDF
or a new office form could legitimately need one more — but it must be a decision
someone made and recorded, not something that drifts in unnoticed. The build
fails until the number here is updated together with the reason.

The litany lists went from 24 entries to 2 when the right margin stopped being
measured per page (#39). If they start growing again, suspect the measurement
before adding entries.
"""

import ast
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
PY_SRC = ROOT / "tools" / "extract_offices.py"

# name -> (expected count, why it exists)
EXPECTED: dict[str, tuple[int, str]] = {
    "_LITANY_VALLEY_JOIN": (
        0,
        "Litany breaks inside the slack dead band that must be joined. Empty: "
        "every true column wrap in the litany is now settled by geometry.",
    ),
    "_LITANY_VALLEY_KEEP": (
        2,
        "Litany breaks inside the slack dead band that must be kept. Two "
        "couplets whose first line runs nearly the full measure, so the next "
        "word does not fit and the geometry reads as forced. Their neighbouring "
        "petitions are couplets on the same pattern with a repeating response.",
    ),
}


def _string_set_sizes() -> dict[str, int]:
    """Sizes of the module-level frozenset-of-string constants, read via AST."""
    tree = ast.parse(PY_SRC.read_text(encoding="utf-8"))
    sizes: dict[str, int] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        names = [t.id for t in targets if isinstance(t, ast.Name)]
        if not names:
            continue
        call = node.value
        if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                and call.func.id == "frozenset"):
            continue
        if not call.args:                      # frozenset() -> empty
            sizes[names[0]] = 0
            continue
        arg = call.args[0]
        if isinstance(arg, (ast.Set, ast.List, ast.Tuple)):
            sizes[names[0]] = len(arg.elts)
    return sizes


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_special_case_count_is_unchanged(name: str) -> None:
    expected, why = EXPECTED[name]
    sizes = _string_set_sizes()
    assert name in sizes, (
        f"{name} is no longer a module-level frozenset in {PY_SRC.name}. If it "
        "was removed because the extractor stopped needing it, drop its entry "
        "from EXPECTED here too."
    )
    actual = sizes[name]
    assert actual == expected, (
        f"{name} has {actual} entries, expected {expected}.\n\n"
        f"What it is: {why}\n\n"
        "Adding entries means the extractor is falling back on hand adjudication "
        "more often than it used to. Check whether the measurement broke — a bad "
        "text measure or space advance will push correct breaks into the dead "
        "band — before accepting more special cases. If the change is genuinely "
        "right, update the count here and say why in the commit."
    )
