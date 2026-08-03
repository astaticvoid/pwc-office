"""SECTION_ORDER is the canonical list of sections; the heading map is not.

Two sections — seasonal_collects and lords_prayer_intro — are carved out of the
litany block after section assignment and are named by no heading. An analysis
that walks typed lines and assigns sections via `_heading_to_key` therefore
reports ZERO for them instead of failing, which has silently produced wrong
answers: a sweep of prose sections that missed 334 breaks, and an audit that
reported "seasonal_collects: no breaks sampled" and was believed.

These tests keep the canonical list complete and keep the trap documented.
"""

import ast
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from extract_offices import (  # noqa: E402
    SECTION_ORDER,
    SPLIT_SECTIONS,
    _heading_to_key,
    sections_of,
)

OFFICES = ROOT / "data" / "offices.json"


def _real_sections() -> set[str]:
    data = json.loads(OFFICES.read_text(encoding="utf-8"))
    found = set()
    for form, body in data.items():
        if form.startswith("_") or not isinstance(body, dict):
            continue
        found.update(k for k, v in body.items() if isinstance(v, list))
    return found


@pytest.mark.skipif(not OFFICES.exists(), reason="data/offices.json not extracted")
def test_section_order_covers_every_section_in_the_data():
    missing = _real_sections() - set(SECTION_ORDER) - {"reading_response"}
    assert not missing, (
        f"sections present in data/offices.json but absent from SECTION_ORDER: "
        f"{sorted(missing)}. Anything walking SECTION_ORDER silently skips them — "
        "add them, in the position a form presents them."
    )


def test_split_sections_are_not_reachable_from_any_heading():
    # The property that makes heading-derived assignment incomplete. If a heading
    # ever does yield one of these, the warning in SPLIT_SECTIONS is obsolete.
    tree = ast.parse((ROOT / "tools" / "extract_offices.py").read_text(encoding="utf-8"))
    literals = {
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    headingish = {t for t in literals if t and len(t) < 80}
    produced = {k for k in (_heading_to_key(t) for t in headingish) if isinstance(k, str)}
    assert not (produced & SPLIT_SECTIONS), (
        f"a heading now yields {sorted(produced & SPLIT_SECTIONS)}, which "
        "SPLIT_SECTIONS says is impossible — update the constant and its comment."
    )


def test_split_sections_are_listed_in_section_order():
    assert SPLIT_SECTIONS <= set(SECTION_ORDER)


@pytest.mark.skipif(not OFFICES.exists(), reason="data/offices.json not extracted")
def test_sections_of_finds_the_split_sections():
    # The regression this accessor exists to prevent: a form with collects must
    # report them, where heading-derived walking would return nothing.
    data = json.loads(OFFICES.read_text(encoding="utf-8"))
    with_collects = [
        f for f, body in data.items()
        if not f.startswith("_") and isinstance(body, dict) and body.get("seasonal_collects")
    ]
    assert with_collects, "no form has seasonal_collects — fixture assumption broken"
    keys = dict(sections_of(data[with_collects[0]]))
    assert "seasonal_collects" in keys


@pytest.mark.skipif(not OFFICES.exists(), reason="data/offices.json not extracted")
def test_sections_of_yields_canonical_order():
    data = json.loads(OFFICES.read_text(encoding="utf-8"))
    form = data["advent-mp"]
    yielded = [k for k, _ in sections_of(form)]
    assert yielded == [k for k in SECTION_ORDER if form.get(k)]
