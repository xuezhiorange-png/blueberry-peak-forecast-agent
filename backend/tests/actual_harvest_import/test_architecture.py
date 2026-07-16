from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.contract]

PACKAGE_ROOT = Path(__file__).parents[2] / "app" / "actual_harvest_import"
CONTRACT_FILES = ("__init__.py", "enums.py", "schemas.py", "validation.py")
FORBIDDEN_IMPORTS = {
    "sqlalchemy",
    "alembic",
    "fastapi",
    "starlette",
    "xlrd",
    "openpyxl",
    "pandas",
    "numpy",
    "backend.app.models",
    "backend.app.api",
    "backend.app.cli",
    "backend.app.harvest_state.persistence",
}


def test_contract_package_has_no_persistence_parser_or_api_imports() -> None:
    imports: set[str] = set()
    for filename in CONTRACT_FILES:
        path = PACKAGE_ROOT / filename
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
    assert not {
        import_name
        for import_name in imports
        if any(
            import_name == forbidden or import_name.startswith(f"{forbidden}.")
            for forbidden in FORBIDDEN_IMPORTS
        )
    }


def test_contract_package_contains_no_implementation_layers() -> None:
    source = "\n".join(
        (PACKAGE_ROOT / filename).read_text(encoding="utf-8") for filename in CONTRACT_FILES
    )
    assert "sqlalchemy" not in source
    assert "alembic" not in source
    assert "def parse_" not in source
    assert "def commit_" not in source
    assert "def persist_" not in source
