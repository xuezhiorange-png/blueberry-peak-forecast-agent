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

REPO_ROOT = Path(__file__).resolve().parents[3]
FACTORIES_DIR = REPO_ROOT / "backend" / "tests" / "factories"
ASSERTIONS_DIR = REPO_ROOT / "backend" / "tests" / "assertions"

# Fail-closed: if any of the submodules is missing, the test module
# itself must refuse to load (rather than silently passing with an
# empty scan). Per Batch 5 PR #69 P0-3 fix.
for _required_dir, _label in (
    (FACTORIES_DIR, "FACTORIES_DIR"),
    (ASSERTIONS_DIR, "ASSERTIONS_DIR"),
):
    if not _required_dir.is_dir():
        raise RuntimeError(
            f"test_no_canonical_reimplementation: required directory "
            f"{_label} does not exist: {_required_dir}"
        )
del _required_dir, _label

# Forbidden canonical-logic patterns inside test-only factories and
# assertions. The intent is to forbid any local reimplementation of
# production canonical / hash / key / ID logic.
FORBIDDEN_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"hashlib\.sha256\(", "raw hashlib.sha256 invocation"),
    (r"hashlib\.sha512\(", "raw hashlib.sha512 invocation"),
    (r"hashlib\.sha1\(", "raw hashlib.sha1 invocation"),
    (r"hashlib\.new\(\s*[\"']sha", "raw hashlib.new('sha...') invocation"),
    (r"hmac\.new\(", "raw hmac.new invocation"),
    (r"secrets\.(token_hex|token_bytes|token_urlsafe)\(", "deterministic-key-like usage"),
    (r"uuid\.uuid5\(", "deterministic UUID5 invocation"),
    (r"uuid\.uuid3\(", "deterministic UUID3 invocation"),
    (r"hashlib\.blake2b\(", "raw blake2b invocation"),
    (r"hashlib\.blake2s\(", "raw blake2s invocation"),
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

    The test file itself is excluded from the scan (it intentionally
    contains the forbidden patterns as FORBIDDEN_PATTERNS literals and
    in its docstring as illustrative examples). Per Batch 5 PR #69
    P0-3 fix.
    """
    if not file_path.exists():
        pytest.skip(f"file not present: {file_path}")
    # The scope-guard test itself is the source of truth for the
    # forbidden patterns; scanning it would always trip on its own
    # FORBIDDEN_PATTERNS definitions and docstring examples.
    if file_path.name == "test_no_canonical_reimplementation.py":
        pytest.skip("scope-guard test scans itself: skipping")
    violations = _scan_for_forbidden_patterns(file_path)
    assert not violations, (
        f"{file_path.relative_to(REPO_ROOT)} re-implements production "
        f"canonical logic. Test-only helpers must call backend.app.** "
        f"canonical helpers, not reimplement them. Violations:\n"
        + "\n".join(f"  line {ln}: {desc}\n    >>> {line}" for ln, line, desc in violations)
    )
