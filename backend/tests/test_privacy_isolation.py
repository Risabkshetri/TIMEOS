"""Enforces docs/TIMEOS_ENGINEERING_SPEC.md ADR-006: the AI layer is structurally isolated from
the data layer. This test (and the import-linter contract in pyproject.toml) must exist from
Phase 0 onward and must fail the build the moment it is violated — it is not something to defer
until Phase 7/8 actually write AI code.
"""

import ast
from pathlib import Path

FORBIDDEN_FOR_AI = {"timeos.models", "timeos.db", "sqlalchemy", "asyncpg", "psycopg"}

AI_PACKAGE = Path(__file__).resolve().parents[1] / "timeos" / "ai"


def _imported_modules(py_file: Path) -> set[str]:
    tree = ast.parse(py_file.read_text(), filename=str(py_file))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_ai_package_exists():
    assert AI_PACKAGE.is_dir(), "timeos/ai package is missing"


def test_ai_module_has_no_forbidden_imports():
    violations: dict[str, set[str]] = {}
    for py_file in AI_PACKAGE.rglob("*.py"):
        imported = _imported_modules(py_file)
        hit = {
            m
            for m in imported
            if m in FORBIDDEN_FOR_AI
            or any(m.startswith(f"{forbidden}.") for forbidden in FORBIDDEN_FOR_AI)
        }
        if hit:
            violations[str(py_file)] = hit
    assert not violations, (
        f"timeos.ai must never import the data layer, but found: {violations}"
    )
