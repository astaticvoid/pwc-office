"""Every `from <sibling tool> import NAME` resolves to a name that still exists.

Regression guard for a real breakage: ADR 0011 removed `_DIVINE_FIXES` from
`extract_offices.py`, but `extract_form_text.py` still did

    from extract_offices import OFFICES, _is_noise, _MAJOR_HDRS, _DIVINE_FIXES

so that module died with an ImportError on line 33. `make generate-golden`
and `make check-book` were both broken for as long as it took to notice,
because nothing in `make test` imports `extract_form_text` — the tools are
scripts invoked by the Makefile, not library code under test. See issue #4.

This checks statically (via AST) rather than by importing: several tools do
real work at module scope (`check_dist.py` validates and prints), so actually
importing them all would make this test slow, order-dependent, and reliant on
a built `dist/`.
"""

import ast
import pathlib

import pytest

TOOLS = pathlib.Path(__file__).resolve().parent.parent
LOCAL_MODULES = {p.stem: p for p in TOOLS.glob("*.py")}


def _module_ast(path):
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _names_defined_by(path):
    """Top-level names a module exposes: assignments, defs, classes, imports."""
    names = set()
    for node in _module_ast(path).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                names.update(
                    n.id for n in ast.walk(tgt) if isinstance(n, ast.Name)
                )
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            # Re-exports count: `from x import y` makes `y` importable here too.
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
    return names


def _cross_tool_imports(path):
    """(target_module, imported_name, lineno) for each sibling-tool import."""
    for node in _module_ast(path).body:
        if not isinstance(node, ast.ImportFrom) or node.level:
            continue
        if node.module not in LOCAL_MODULES:
            continue
        for alias in node.names:
            if alias.name != "*":
                yield node.module, alias.name, node.lineno


@pytest.mark.parametrize(
    "tool", sorted(LOCAL_MODULES), ids=sorted(LOCAL_MODULES)
)
def test_cross_tool_imports_resolve(tool):
    path = LOCAL_MODULES[tool]
    missing = [
        f"{path.name}:{lineno}: `from {target} import {name}` — "
        f"{target}.py no longer defines {name}"
        for target, name, lineno in _cross_tool_imports(path)
        if name not in _names_defined_by(LOCAL_MODULES[target])
    ]
    assert not missing, "\n".join(missing)
