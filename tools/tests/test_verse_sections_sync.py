"""`_VERSE_SECTIONS` (Python) and `VERSE_SECTIONS` (JS) must agree.

Both encode "line breaks in this section are intentional liturgical structure",
but with different consequences: the Python set decides whether `_LINE_JOIN`
rewrites the *shipped data*, while the JS set decides whether the
`no-prose-line-breaks` rule *flags* it. Where JS lists a section Python does
not, extraction joins the lines and validation stays quiet about it.

That gap shipped a real bug: `lords_prayer_intro` was in the JS list and absent
from the Python one, so all 30 forms shipped the Lord's Prayer with "Forgive us
our sins / as we forgive those who sin against us." joined into a single line
(#33). AGENTS.md already said the two "must stay in sync" — enforced by nothing
but a comment in each file. This is that enforcement.

The remaining divergences are recorded in KNOWN_DIVERGENCES so new drift fails
immediately while the backlog stays visible. Reconciling them is not mechanical
and is tracked in #36 — `litany`, for instance, is JS-only but is genuinely
prose (#9), so it must come *out* of the JS list rather than into the Python one.
"""

import ast
import pathlib
import re

import pytest

TOOLS = pathlib.Path(__file__).resolve().parent.parent
PY_SRC = TOOLS / "extract_offices.py"
JS_SRC = TOOLS / "validate_office.cjs"

# Sections that legitimately differ today, each pending adjudication in #36.
# Removing an entry here after reconciling it is the intended workflow; adding
# one requires justifying why the two layers should disagree.
KNOWN_DIVERGENCES = {
    "opening_responses",      # JS-only
    "responsory",             # JS-only
    "thanksgiving_for_light",  # JS-only
    "lords_prayer",           # JS-only — phantom, no such section key exists
    "intercessions",          # JS-only
    "litany",                 # JS-only — genuinely prose, see #9; remove from JS
    "dismissal",              # JS-only
    "doxology",               # Python-only
}


def _python_verse_sections():
    """`_VERSE_SECTIONS` is a local inside `_normalize_whitespace`, so read it
    from the AST rather than importing the module."""
    tree = ast.parse(PY_SRC.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(t, ast.Name) and t.id == "_VERSE_SECTIONS"
            for t in node.targets
        ):
            continue
        # frozenset({...})
        call = node.value
        assert isinstance(call, ast.Call), "_VERSE_SECTIONS is no longer a frozenset(...) call"
        return {ast.literal_eval(e) for e in call.args[0].elts}
    raise AssertionError("_VERSE_SECTIONS not found in extract_offices.py")


def _js_verse_sections():
    src = JS_SRC.read_text(encoding="utf-8")
    m = re.search(r"const VERSE_SECTIONS = \[(.*?)\];", src, re.S)
    assert m, "VERSE_SECTIONS not found in validate_office.cjs"
    return set(re.findall(r"'([^']+)'", m.group(1)))


def test_verse_sections_are_in_sync():
    py, js = _python_verse_sections(), _js_verse_sections()
    unexpected = (py ^ js) - KNOWN_DIVERGENCES
    assert not unexpected, (
        "_VERSE_SECTIONS (extract_offices.py) and VERSE_SECTIONS "
        "(validate_office.cjs) disagree on: " + ", ".join(sorted(unexpected))
        + ". A section in only the JS list is joined by _LINE_JOIN during "
        "extraction but not flagged by no-prose-line-breaks — the shape of #33. "
        "Reconcile against the source PDF, or add to KNOWN_DIVERGENCES with a "
        "reason if the two layers genuinely should differ."
    )


@pytest.mark.parametrize("section", sorted(KNOWN_DIVERGENCES))
def test_known_divergences_are_not_stale(section):
    """A divergence that has been reconciled must be removed from the list,
    the same staleness discipline validate_corrections.py applies."""
    py, js = _python_verse_sections(), _js_verse_sections()
    assert section in (py ^ js), (
        f"{section!r} is listed in KNOWN_DIVERGENCES but the two lists now "
        f"agree on it — remove it from the allowlist (see #36)."
    )
