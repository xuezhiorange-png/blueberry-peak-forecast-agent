"""Keep old assertions, source identities and read results across the resource fix."""

from __future__ import annotations

import ast
import copy
from pathlib import Path

import pytest

from backend.tests.historical_source import historical_bytes
from backend.tests.td03g_historical_source import (
    BASE,
    EXPECTED_BLOBS,
    OBTAIN,
    QUERY,
    fixed_bytes,
    source_blob,
)


def original(path: Path) -> ast.Module:
    return ast.parse(historical_bytes(str(path), BASE))


def without_imports(tree: ast.AST) -> str:
    class Imports(ast.NodeTransformer):
        def visit_Import(self, node):
            return None

        def visit_ImportFrom(self, node):
            return None

    return ast.dump(Imports().visit(copy.deepcopy(tree)), include_attributes=False)


def test_historical_reader_adaptation_preserves_every_original_test_body_and_hash():
    adapted = []
    for path in sorted(Path("backend/tests/s3_daily_rowset").glob("test_*.py")):
        current = ast.parse(path.read_text())
        if not any(
            isinstance(node, ast.ImportFrom)
            and node.module == "backend.tests.td03g_historical_source"
            for node in current.body
        ):
            continue
        adapted.append(path)
        old = original(path)
        old_reader = next(
            node
            for node in old.body
            if isinstance(node, ast.FunctionDef) and node.name == "_git_blob"
        )
        reader = next(
            node
            for node in current.body
            if isinstance(node, ast.FunctionDef) and node.name == "_git_blob"
        )
        assert ast.unparse(reader.body[0]) == "return source_blob(path)"
        reader.body = copy.deepcopy(old_reader.body)
        assert without_imports(current) == without_imports(old), str(path)
    assert len(adapted) == 39


def test_td03f_controlled_diagnostic_keeps_assertions_on_its_exact_old_source():
    path = Path("backend/tests/integration/test_asyncpg_resource_lifecycle.py")
    old = original(path)
    current = ast.parse(path.read_text())
    for node in current.body:
        if isinstance(node, ast.FunctionDef) and node.name == (
            "test_controlled_default_probe_cross_loop_diagnostic"
        ):
            node.body = [
                statement
                for statement in node.body
                if not (
                    isinstance(statement, ast.Assign)
                    and isinstance(statement.value, ast.Call)
                    and isinstance(statement.value.func, ast.Name)
                    and statement.value.func.id == "frozen_query_module"
                )
            ]
    assert without_imports(current) == without_imports(old)
    assert fixed_bytes(QUERY) == historical_bytes(QUERY, BASE)


def test_historical_blob_seam_is_exact_and_does_not_hide_live_document_changes(tmp_path):
    assert source_blob(OBTAIN) == "97be63307d002d6878649cd241ff94f5149e0f8a"
    assert source_blob(Path(OBTAIN).resolve()) == source_blob(OBTAIN)
    assert len(EXPECTED_BLOBS) == 15
    for path in EXPECTED_BLOBS:
        assert fixed_bytes(path) == historical_bytes(path, BASE)
    document = tmp_path / "evidence.txt"
    document.write_text("original synthetic metadata")
    first = source_blob(document)
    document.write_text("changed synthetic metadata")
    assert source_blob(document) != first
    with pytest.raises(KeyError):
        fixed_bytes("backend/app/db/session.py")


def test_historical_code_tampering_cannot_select_a_matching_fallback(monkeypatch):
    import backend.tests.td03g_historical_source as seam

    monkeypatch.setattr(seam, "historical_bytes", lambda *args: b"tampered")
    with pytest.raises(AssertionError, match="Historical code Blob mismatch"):
        seam.fixed_bytes(OBTAIN)


def test_runtime_queries_models_payloads_and_authority_logic_are_unchanged():
    paths = [
        *Path("backend/app/s3_daily_rowset").glob("*.py"),
        Path("backend/app/forecast_quality/train_val_pairing_materialization_live_async.py"),
    ]

    class ResourceEdits(ast.NodeTransformer):
        def visit_Call(self, node):
            self.generic_visit(node)
            if isinstance(node.func, ast.Name) and node.func.id == "loop_owned_session":
                return ast.Call(func=node.args[0], args=[], keywords=[])
            return node

        def visit_ExceptHandler(self, node):
            if isinstance(node.type, ast.Name) and node.type.id == "LoopResourceUnavailable":
                assert len(node.body) == 1 and isinstance(node.body[0], ast.Raise)
                return None
            return self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node):
            self.generic_visit(node)
            if (
                node.body
                and isinstance(node.body[0], ast.Assign)
                and ast.unparse(node.body[0]).startswith("held = loop_bound_connection(session)")
            ):
                assert isinstance(node.body[1], ast.If)
                node.body = node.body[2:]
            return node

    changed = 0
    for path in paths:
        text = path.read_text()
        if "from backend.app.db.loop_resources import" not in text:
            continue
        changed += 1
        current = ResourceEdits().visit(ast.parse(text))
        old = original(path)
        if path.name.endswith("live_async_connection.py"):
            # Only this function's acquisition/cleanup implementation changed;
            # its public checks, envelopes and failure reasons remain identical.
            current.body = [
                node
                for node in current.body
                if not (
                    isinstance(node, ast.AsyncFunctionDef) and node.name == "_obtain_from_engine"
                )
            ]
            old.body = [
                node
                for node in old.body
                if not (
                    isinstance(node, ast.AsyncFunctionDef) and node.name == "_obtain_from_engine"
                )
            ]
        assert without_imports(current) == without_imports(old), str(path)
    assert changed == 16


def test_resource_boundary_never_constructs_an_engine_or_replacement_source():
    tree = ast.parse(Path("backend/app/db/loop_resources.py").read_text())
    forbidden = {"create_engine", "create_async_engine", "AsyncEngine", "async_sessionmaker"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            assert not (isinstance(node.func, ast.Name) and node.func.id in forbidden)
    assert "NullPool" not in ast.unparse(tree)
    assert "asyncio.run(" not in ast.unparse(tree)
    assert "Thread(" not in ast.unparse(tree)
