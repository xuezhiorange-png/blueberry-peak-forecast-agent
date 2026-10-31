"""The lifecycle correction must not rewrite the historical authority."""

import ast
import hashlib
import json
from pathlib import Path

import pytest

from backend.tests.historical_source import historical_bytes
from backend.tests.local_auth.test_runtime_evidence_contract import (
    MERGED_S1,
    REVISED_RUNTIME_SOURCES,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = "backend/tests/integration/test_rolling_backtest_orchestration.py"
pytestmark = [pytest.mark.unit, pytest.mark.contract]


def test_fixture_preserves_historical_digest_assertions_and_test_identities():
    original = historical_bytes(FIXTURE, MERGED_S1)
    authority = json.loads((ROOT / "docs/v0-18/s1/local-auth-runtime-r1.json").read_text())
    assert hashlib.sha256(original).hexdigest() == authority["source_evidence_sha256"][FIXTURE]
    assert FIXTURE in REVISED_RUNTIME_SOURCES
    old, new = ast.parse(original), ast.parse((ROOT / FIXTURE).read_text())
    assert [
        ast.dump(n)
        for n in sorted(ast.walk(old), key=lambda n: getattr(n, "lineno", -1))
        if isinstance(n, ast.Assert)
    ] == [
        ast.dump(n)
        for n in sorted(ast.walk(new), key=lambda n: getattr(n, "lineno", -1))
        if isinstance(n, ast.Assert)
    ]
    assert [
        (n.name, type(n).__name__)
        for n in old.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ] == [
        (n.name, type(n).__name__)
        for n in new.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    # Only the proved daily-I/O block gains a session context; no original
    # expression, query, assertion, marker or other function may change.
    helper = next(
        n
        for n in new.body
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "_build_real_orchestration_command"
    )
    contexts = [n for n in helper.body if isinstance(n, ast.AsyncWith)]
    assert len(contexts) == 2
    added = contexts[-1]
    assert len(added.body) == 1 and isinstance(added.body[0], ast.For)
    index = helper.body.index(added)
    helper.body[index : index + 1] = added.body
    assert ast.dump(old) == ast.dump(new)
