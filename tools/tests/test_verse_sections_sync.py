"""The two verse-section lists must hold a subset relationship, not equality.

`VERSE_SECTIONS` (tools/validate_office.cjs) answers "does this section contain
*any* intentional line breaks?", so the `no-prose-line-breaks` rule should not
flag a `\\n` there.

`_VERSE_SECTIONS` (tools/extract_offices.py) answers a stricter question: "are
*all* breaks here intentional, so `_LINE_JOIN` must never fire?"

A section can hold both real verse breaks and PDF column wraps, and then belongs
in the first list but not the second. `litany` is the clear case: roughly 110 of
its 153 breaks are deliberate and the remainder are true wraps, so no
section-level verdict is right for it.

`thanksgiving_for_light` was previously described here as the clear case, on the
grounds that all four of its joinable breaks were column wraps "identified by the
trailing space the PDF leaves on a wrapped line". That identification was wrong —
a trailing space marks a line that does not end its block, not a line that was
wrapped. Remeasured by reflow (does the next line's first word fit?), all 70 of
its breaks are deliberate, and it is now in the Python set as well.

So the invariant is **Python ⊆ JS**, plus: neither list may name a section that
does not exist. AGENTS.md previously said the two "must stay in sync", which is
what let #33 through — `lords_prayer_intro` is a pure-verse section (every break
intentional) that was in the JS list and missing from the Python one, so all 30
forms shipped the Lord's Prayer with a joined line.

See #36 for the adjudication of each section against the source PDF.
"""

import ast
import json
import pathlib
import re
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
TOOLS = ROOT / "tools"
PY_SRC = TOOLS / "extract_offices.py"
JS_SRC = TOOLS / "validate_office.cjs"

# `doxology` exists only during extraction — normalize_offices.py hoists it into
# `_shared`, so it is never a section name at render time and cannot appear in
# the JS list. The only legitimate Python-side entry with no JS counterpart.
EXTRACTION_ONLY = {"doxology"}


def _python_verse_sections():
    """`_VERSE_SECTIONS` is a local inside `_normalize_whitespace`, so read it
    from the AST rather than importing the module."""
    tree = ast.parse(PY_SRC.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(t, ast.Name) and t.id == "_VERSE_SECTIONS" for t in node.targets
        ):
            continue
        call = node.value
        assert isinstance(call, ast.Call), "_VERSE_SECTIONS is no longer a frozenset(...) call"
        return {ast.literal_eval(e) for e in call.args[0].elts}
    raise AssertionError("_VERSE_SECTIONS not found in extract_offices.py")


def _js_verse_sections():
    src = JS_SRC.read_text(encoding="utf-8")
    m = re.search(r"const VERSE_SECTIONS = \[(.*?)\];", src, re.S)
    assert m, "VERSE_SECTIONS not found in validate_office.cjs"
    return set(re.findall(r"'([^']+)'", m.group(1)))


def _real_section_names():
    """Section names that actually reach the renderer, straight from
    segmentsToJSON — the same source the validator's rules walk."""
    script = """
    (async () => {
      const { readFileSync } = require('fs');
      const { segmentsToJSON } = await import('./web/render.js');
      const offices = JSON.parse(readFileSync('./data/offices.json', 'utf8'));
      const shared = offices._shared || {};
      const seen = new Set();
      for (const fk of Object.keys(offices).filter(k => !k.startsWith('_')))
        for (const item of segmentsToJSON(offices[fk], shared))
          if (item.section) seen.add(item.section);
      console.log(JSON.stringify([...seen]));
    })();
    """
    out = subprocess.run(
        ["node", "-e", script], cwd=ROOT, capture_output=True, text=True, timeout=120
    )
    assert out.returncode == 0, f"node failed: {out.stderr[-400:]}"
    return set(json.loads(out.stdout.strip().splitlines()[-1]))


def test_python_verse_sections_are_a_subset_of_js():
    py, js = _python_verse_sections(), _js_verse_sections()
    missing = py - js - EXTRACTION_ONLY
    assert not missing, (
        "these are in _VERSE_SECTIONS (extract_offices.py) but not VERSE_SECTIONS "
        f"(validate_office.cjs): {', '.join(sorted(missing))}. If extraction never "
        "joins a section's line breaks, the validator must not flag them as prose "
        "orphans either. Add them to the JS list, or to EXTRACTION_ONLY if the "
        "section is hoisted into _shared and never reaches the renderer."
    )


@pytest.mark.parametrize("listname", ["python", "js"])
def test_no_phantom_sections(listname):
    """Neither list may name a section that does not exist — `lords_prayer` sat
    in the JS list despite the real key being `lords_prayer_intro` (#36)."""
    real = _real_section_names()
    entries = _python_verse_sections() if listname == "python" else _js_verse_sections()
    phantom = entries - real - EXTRACTION_ONLY
    assert not phantom, (
        f"{listname} VERSE_SECTIONS names sections that never reach the renderer: "
        f"{', '.join(sorted(phantom))}. Real section names come from "
        "segmentsToJSON(); fix the spelling or drop the entry."
    )
