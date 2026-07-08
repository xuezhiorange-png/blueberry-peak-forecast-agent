"""Scope-guard: import-boundary rules per design §5.

Per the Batch 5 design freeze (PR #68 / Issue #53) §5, the three
submodules ``backend/tests/factories/``, ``backend/tests/assertions/``,
and ``backend/tests/db/`` MUST NOT cross-import in the forbidden
directions:

- ``assertions/`` MUST NOT import from ``factories/``.
- ``db/`` MUST NOT import from ``factories/`` or ``assertions/``.
- ``factories/`` MUST NOT import from ``assertions/``.

This test uses Python's :mod:`ast` module to walk each submodule's
source files and fails CI if any forbidden import is detected.

Run by the ``unit-contract-golden`` shard (pure python, no DB).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
FACTORIES_DIR = REPO_ROOT / "backend" / "tests" / "factories"
ASSERTIONS_DIR = REPO_ROOT / "backend" / "tests" / "assertions"
DB_DIR = REPO_ROOT / "backend" / "tests" / "db"

# Fail-closed: if any of the submodules is missing, the test module
# itself must refuse to load (rather than silently passing with an
# empty scan). Per Batch 5 PR #69 P0-3 fix.
for _required_dir, _label in (
    (FACTORIES_DIR, "FACTORIES_DIR"),
    (ASSERTIONS_DIR, "ASSERTIONS_DIR"),
    (DB_DIR, "DB_DIR"),
):
    if not _required_dir.is_dir():
        raise RuntimeError(
            f"test_import_boundaries: required directory {_label} does not exist: {_required_dir}"
        )
del _required_dir, _label

# Map (source_submodule, target_submodule) -> human-readable rule.
FORBIDDEN_IMPORTS: tuple[tuple[str, str, str], ...] = (
    ("assertions", "factories", "assertions/ MUST NOT import from factories/"),
    ("factories", "assertions", "factories/ MUST NOT import from assertions/"),
    ("db", "factories", "db/ MUST NOT import from factories/"),
    ("db", "assertions", "db/ MUST NOT import from assertions/"),
)


def _imports_of_file(file_path: Path) -> list[str]:
    """Return list of top-level module names imported by ``file_path``."""
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            # Normalize relative imports to their absolute form so
            # the rule matches both ``from backend.tests.X import ...``
            # and the package-relative form.
            if node.level and node.level > 0:
                # Resolve relative to ``backend.tests.<submodule>``.
                # We re-anchor the dotted module as needed; for our
                # purposes we always know these files live under
                # ``backend/tests/<submodule>/`` so a relative import
                # of ``..factories`` from ``db/foo.py`` means
                # ``backend.tests.factories``.
                package = "backend.tests"
                # node.level counts how many ``.`` are at the front.
                # node.level == 1 means ``from .X`` ⇒ same package.
                # node.level == 2 means ``from ..X`` ⇒ one level up.
                base_parts = package.split(".")
                if node.level > len(base_parts):
                    continue
                base = ".".join(base_parts[: len(base_parts) - (node.level - 1)])
                # node.module is relative to that base.
                if node.module:
                    full = f"{base}.{node.module}"
                else:
                    full = base
                imports.append(full)
            else:
                imports.append(node.module)
    return imports


def _submodule_of(file_path: Path) -> str:
    """Return 'factories' | 'assertions' | 'db' for a file path under one of those dirs."""
    rel = file_path.relative_to(REPO_ROOT)
    parts = rel.parts
    # rel = ('backend', 'tests', '<submodule>', '<file>.py')
    if len(parts) >= 3 and parts[0] == "backend" and parts[1] == "tests":
        return parts[2]
    return ""


def _files_under(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.py"))


@pytest.mark.parametrize(
    "file_path",
    _files_under(FACTORIES_DIR) + _files_under(ASSERTIONS_DIR) + _files_under(DB_DIR),
    ids=lambda p: str(p.relative_to(REPO_ROOT)) if isinstance(p, Path) else str(p),
)
def test_no_forbidden_imports(file_path: Path) -> None:
    """Verify the per-submodule import-boundary rules of design §5."""
    if not file_path.exists():
        pytest.skip(f"file not present: {file_path}")
    source_submodule = _submodule_of(file_path)
    if not source_submodule:
        pytest.skip(f"file is not under a Batch 5 submodule: {file_path}")
    for imported_module in _imports_of_file(file_path):
        for src, tgt, message in FORBIDDEN_IMPORTS:
            if source_submodule != src:
                continue
            # Match the target submodule anywhere in the imported module path.
            if f".tests.{tgt}" in imported_module or imported_module.endswith(f".tests.{tgt}"):
                pytest.fail(
                    f"{file_path.relative_to(REPO_ROOT)}: forbidden import "
                    f"{imported_module!r}. {message}"
                )
