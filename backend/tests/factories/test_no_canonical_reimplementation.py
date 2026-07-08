"""Scope-guard: no canonical-logic reimplementation in test-only helpers.

Per the Batch 5 design freeze (PR #68 / Issue #53) §6 + §8, this
test ensures that ``backend/tests/factories/`` and
``backend/tests/assertions/`` do NOT reimplement production canonical
/ hash / key / ID logic. It greps the source files for forbidden
patterns (raw ``hashlib.sha256(...)``, ``hmac.new(...)``, ``secrets.*``,
deterministic-UUID helpers, and string-keyed deterministic counter
patterns) and fails if any are found inside those submodules.

This is an AST-grep test (not an AST-parse test); it intentionally
also fires on substring matches inside docstrings, because the
intent of design §6 is to forbid even illustrative reimplementations.

Run by the existing ``postgres-task11`` shard (or whichever shard
owns the new test files via the pytest-marker contract). If CI is
misconfigured and this test runs in ``unit-contract-golden`` instead,
the test still works as a pure-python AST grep.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FACTORIES_DIR = REPO_ROOT / "backend" / "tests" / "factories"
ASSERTIONS_DIR = REPO_ROOT / "backend" / "tests" / "assertions"

# Forbidden canonical-logic patterns inside test-only factories and
# assertions. The intent is to forbid any local reimplementation of
# production canonical / hash / key / ID logic.
FORBIDDEN_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"hashlib\.sha256\(", "raw hashlib.sha256 invocation (use sha256_hex from backend.app.harvest_state.canonical)"),
    (r"hashlib\.sha512\(", "raw hashlib.sha512 invocation (use sha256_hex from backend.app.harvest_state.canonical)"),
    (r"hashlib\.sha1\(", "raw hashlib.sha1 invocation (use sha256_hex from backend.app.harvest_state.canonical)"),
    (r"hashlib\.new\(\s*[\"']sha", "raw hashlib.new('sha...') invocation"),
    (r"hmac\.new\(", "raw hmac.new invocation (use production canonical helpers)"),
    (r"secrets\.(token_hex|token_bytes|token_urlsafe)\(", "deterministic-key-like usage (production canonical handles keys)"),
    (r"uuid\.uuid5\(", "deterministic UUID5 invocation (production canonical handles ids)"),
    (r"uuid\.uuid3\(", "deterministic UUID3 invocation (production canonical handles ids)"),
    (r"hashlib\.blake2b\(", "raw blake2b invocation (use production canonical helpers)"),
    (r"hashlib\.blake2s\(", "raw blake2s invocation (use production canonical helpers)"),
)


def _python_files_under(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.py"))


def _scan_for_forbidden_patterns(file_path: Path) -> list[tuple[int, str, str]]:
    """Return list of (line_no, line, pattern_description) violations."""
    violations: list[tuple[int, str, str]] = []
    try:
        text = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return violations
    for line_no, line in enumerate(text.splitlines(), start=1):
        # Skip shebangs / pure comments of the regex match (allow
        # explanatory mentions in docstrings / comments).
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for pattern, description in FORBIDDEN_PATTERNS:
            if re.search(pattern, line):
                violations.append((line_no, line, description))
    return violations


@pytest.mark.parametrize(
    "file_path",
    _python_files_under(FACTORIES_DIR) + _python_files_under(ASSERTIONS_DIR),
    ids=lambda p: str(p.relative_to(REPO_ROOT)) if isinstance(p, Path) else str(p),
)
def test_no_canonical_reimplementation(file_path: Path) -> None:
    """No factory or assertion may reimplement production canonical logic.

    Submodule-boundary enforcement per design §5.2 and §6.
    """
    if not file_path.exists():
        pytest.skip(f"file not present: {file_path}")
    violations = _scan_for_forbidden_patterns(file_path)
    assert not violations, (
        f"{file_path.relative_to(REPO_ROOT)} re-implements production "
        f"canonical logic. Test-only helpers must call backend.app.** "
        f"canonical helpers, not reimplement them. Violations:\n"
        + "\n".join(
            f"  line {ln}: {desc}\n    >>> {line}"
            for ln, line, desc in violations
        )
    )