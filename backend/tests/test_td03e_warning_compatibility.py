"""Compatibility checks for warning fixes, against the accepted TD-03D code."""

from __future__ import annotations

import ast
import hashlib
import importlib
import json
import os
import sqlite3
import subprocess
import sys
import types
import warnings
from contextlib import closing
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError
from pydantic.warnings import PydanticDeprecatedSince20

from backend.app.planning.json_types import canonical_json_value
from backend.app.planning.plan_hashing import plan_row_hash
from backend.app.schemas import production_plans

ROOT = Path(__file__).resolve().parents[2]
BASE = "a3d0ea9b7a0faac273cd9f6504257c90f429ccc1"
SCHEMA_PATH = "backend/app/schemas/production_plans.py"
pytestmark = [pytest.mark.unit, pytest.mark.contract]


@pytest.fixture(scope="module")
def legacy_schemas():
    # This is immutable, reviewed code, never a source-data or model fallback.
    source = subprocess.check_output(["git", "show", f"{BASE}:{SCHEMA_PATH}"], cwd=ROOT)
    name = "td03e_legacy_production_plans"
    module = types.ModuleType(name)
    sys.modules[name] = module
    try:
        with pytest.warns(PydanticDeprecatedSince20) as diagnostics:
            exec(compile(source, SCHEMA_PATH, "exec"), module.__dict__)
        assert len(diagnostics) == 12
        yield module
    finally:
        del sys.modules[name]


def _create_payload(value: Decimal, optional: Decimal | None) -> dict:
    return {
        "farm_id": 1,
        "season_id": 2,
        "variety_id": 3,
        "planted_area_mu": value,
        "expected_yield_kg_per_mu": value,
        "marketable_rate": value,
        "tree_age_years": optional,
        "expected_total_marketable_kg": optional,
        "version": 1,
        "effective_from": date(2026, 1, 1),
        "available_at": date(2025, 12, 1),
        "source_type": "SYNTHETIC_TEST_FIXTURE",
        "notes": "合成兼容性检查",
    }


def _read_payload(payload: dict) -> dict:
    return {
        **dict.fromkeys(production_plans.ProductionPlanRead.model_fields),
        **payload,
        "plan_id": 4,
        "farm_name": "SYNTHETIC",
        "season_code": "2025-2026",
        "variety_code": "SYNTHETIC",
        "variety_name": "SYNTHETIC",
        "derived_total_marketable_kg": payload["planted_area_mu"],
        "total_difference_kg": payload["expected_total_marketable_kg"],
        "row_hash": "a" * 64,
        "warnings": [],
        "created_at": datetime(2026, 1, 1, 8, 0, 0, 123456, tzinfo=UTC),
        "updated_at": datetime(2026, 1, 2, tzinfo=timezone(timedelta(hours=8))),
    }


@pytest.mark.parametrize("value", ["-0.000000", "1.230000", "1E+20", "1E-20", "-12.345678"])
@pytest.mark.parametrize("optional", [None, Decimal("0.000000"), Decimal("3.140000")])
def test_production_plan_decimal_dumps_and_row_hash_match_accepted_code(
    legacy_schemas, value, optional
):
    payload = _create_payload(Decimal(value), optional)
    for name, data in (
        ("ProductionPlanCreate", payload),
        ("ProductionPlanRead", _read_payload(payload)),
        ("ProductionPlanList", {"items": [_read_payload(payload)], "total": 1}),
    ):
        old = getattr(legacy_schemas, name)(**data)
        new = getattr(production_plans, name)(**data)
        for options in ({}, {"exclude_none": True}, {"exclude_unset": True}, {"round_trip": True}):
            assert new.model_dump(**options) == old.model_dump(**options)
            assert new.model_dump(mode="json", **options) == old.model_dump(mode="json", **options)
            assert new.model_dump_json(**options) == old.model_dump_json(**options)
        assert canonical_json_value(new.model_dump()) == canonical_json_value(old.model_dump())
        assert plan_row_hash(new.model_dump()) == plan_row_hash(old.model_dump())
        if name != "ProductionPlanList":
            assert isinstance(new.model_dump()["planted_area_mu"], Decimal)
            assert isinstance(new.model_dump(mode="json")["planted_area_mu"], str)


@pytest.mark.parametrize(
    "name", ["ProductionPlanCreate", "ProductionPlanRead", "ProductionPlanList"]
)
@pytest.mark.parametrize("mode", ["validation", "serialization"])
def test_production_plan_json_schemas_match_accepted_code(legacy_schemas, name, mode):
    assert getattr(production_plans, name).model_json_schema(mode=mode) == getattr(
        legacy_schemas, name
    ).model_json_schema(mode=mode)


@pytest.mark.parametrize(
    "invalid",
    [
        {"planted_area_mu": "not-a-number"},
        {"marketable_rate": "NaN"},
        {"unexpected": 1},
        {"effective_to": date(2025, 1, 1)},
        {"flowering_start_date": date(2026, 3, 1), "flowering_peak_date": date(2026, 2, 1)},
    ],
)
def test_production_plan_validation_errors_remain_identical(legacy_schemas, invalid):
    errors = []
    for model in (legacy_schemas.ProductionPlanCreate, production_plans.ProductionPlanCreate):
        with pytest.raises(ValidationError) as failure:
            model(**{**_create_payload(Decimal("100"), None), **invalid})
        errors.append(failure.value.errors(include_context=False, include_url=False))
    assert errors[0] == errors[1]


def test_production_plan_schema_build_no_longer_uses_deprecated_encoders():
    source = (ROOT / SCHEMA_PATH).read_bytes()
    name = "td03e_current_production_plans"
    module = types.ModuleType(name)
    sys.modules[name] = module
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", PydanticDeprecatedSince20)
            exec(compile(source, SCHEMA_PATH, "exec"), module.__dict__)
            for model in (module.ProductionPlanCreate, module.ProductionPlanRead):
                model.model_json_schema(mode="serialization")
    finally:
        del sys.modules[name]


@pytest.mark.parametrize("seed", ["0", "7"])
def test_complete_openapi_and_duplicate_id_diagnostics_are_unchanged(seed):
    probe = """
import collections, json, subprocess, sys, types, warnings
with warnings.catch_warnings(record=True) as diagnostics:
    warnings.simplefilter("always")
    if sys.argv[1] == "legacy":
        name = "backend.app.schemas.production_plans"
        module = types.ModuleType(name)
        sys.modules[name] = module
        source = subprocess.check_output(["git", "show", sys.argv[2]])
        exec(compile(source, "production_plans.py", "exec"), module.__dict__)
    from backend.app.core.config import AppSettings
    from backend.app.main import create_app
    schema = create_app(AppSettings(app_env="test")).openapi()
print(json.dumps({"schema": schema, "duplicate_ids": sorted(str(w.message) for w in diagnostics
    if "Duplicate Operation ID" in str(w.message)), "deprecated_encoders": sum(
    w.category.__name__ == "PydanticDeprecatedSince20" for w in diagnostics)}, sort_keys=True))
"""
    results = []
    for mode in ("legacy", "current"):
        result = subprocess.run(
            [sys.executable, "-c", probe, mode, f"{BASE}:{SCHEMA_PATH}"],
            cwd=ROOT,
            env={**os.environ, "PYTHONHASHSEED": seed, "APP_ENV": "test"},
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        results.append(json.loads(result.stdout))
    old, new = results
    assert old["schema"] == new["schema"]
    assert old["duplicate_ids"] == new["duplicate_ids"]
    assert len(new["duplicate_ids"]) == 3  # Preserved risk; not an arbitrary API rename.
    assert old["deprecated_encoders"] > 0
    assert new["deprecated_encoders"] == 0


@pytest.mark.parametrize(
    "relative,async_count,sync_count",
    [
        ("actual_harvest_import/test_commit_contract.py", 7, 3),
        ("actual_harvest_import/test_i7_label_snapshot.py", 59, 9),
        ("residual_model/test_state_matrix.py", 9, 3),
    ],
)
def test_asyncio_mark_is_not_inherited_by_synchronous_tests(relative, async_count, sync_count):
    tree = ast.parse((ROOT / "backend/tests" / relative).read_text())
    module_marks = [
        n
        for n in tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in n.targets)
    ]
    assert all("asyncio" not in ast.unparse(mark) for mark in module_marks)
    tests = [
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_")
    ]
    assert sum(isinstance(n, ast.AsyncFunctionDef) for n in tests) == async_count
    assert sum(isinstance(n, ast.FunctionDef) for n in tests) == sync_count


@pytest.mark.parametrize(
    "shim,canonical",
    [
        ("postgres_test_support", "profile"),
        ("migration_isolation_helpers", "migration"),
        ("concurrency_isolation_helpers", "concurrency"),
    ],
)
def test_legacy_database_shims_keep_identity_and_intentional_deprecation(shim, canonical):
    probe = """
import importlib, sys, warnings
with warnings.catch_warnings(record=True) as diagnostics:
    warnings.simplefilter("always", DeprecationWarning)
    shim = importlib.import_module("backend.tests." + sys.argv[1])
    current = importlib.import_module("backend.tests.db." + sys.argv[2])
assert len(diagnostics) == 1
assert diagnostics[0].category is DeprecationWarning
assert "has moved" in str(diagnostics[0].message)
assert all(getattr(shim, name) is getattr(current, name) for name in shim.__all__)
"""
    subprocess.run([sys.executable, "-c", probe, shim, canonical], cwd=ROOT, check=True, timeout=30)


@pytest.mark.parametrize(
    "module,function",
    [
        (
            "backend.tests.trial.test_forecast_evidence",
            "test_sqlite_migration_installs_immutable_guards_and_round_trips",
        ),
    ],
)
def test_sqlite_raw_migration_binds_do_not_use_deprecated_datetime_adapter(module, function):
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        getattr(importlib.import_module(module), function)()


def _assert_frozen_source(relative):
    evidence = json.loads((ROOT / "docs/v0-18/s1/local-auth-runtime-r1.json").read_text())
    assert (
        hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        == evidence["source_evidence_sha256"][relative]
    )


def test_frozen_schema_probe_keeps_its_hash_and_adapter_diagnostics():
    relative = (
        "backend/tests/s3_daily_rowset/"
        "test_incumbent_forecast_replay_identity_persistence_schema.py"
    )
    _assert_frozen_source(relative)
    module = importlib.import_module(relative.removesuffix(".py").replace("/", "."))
    with pytest.warns(DeprecationWarning, match="default datetime adapter") as diagnostics:
        module.test_grain_unique_constraint_rejects_duplicate_triple()
    assert len(diagnostics) == 2


def test_frozen_safety_probe_keeps_its_hash_and_import_diagnostic():
    _assert_frozen_source("backend/tests/safety/test_dev_db_protection.py")
    probe = """
import importlib, warnings
with warnings.catch_warnings(record=True) as diagnostics:
    warnings.simplefilter("always", DeprecationWarning)
    importlib.import_module("backend.tests.safety.test_dev_db_protection")
assert len(diagnostics) == 1
assert diagnostics[0].category is DeprecationWarning
assert "backend.tests.migration_isolation_helpers has moved" in str(diagnostics[0].message)
"""
    subprocess.run([sys.executable, "-c", probe], cwd=ROOT, check=True, timeout=30)


def test_authority_fixture_is_rewritten_before_its_first_import():
    fixture = importlib.import_module("backend.tests.forecast_quality.authority_loader_fixture")
    assert type(fixture.__loader__).__name__ == "AssertionRewritingHook"


@pytest.mark.parametrize(
    "path",
    [
        "backend/app/api/residual_model.py",
        "backend/app/api/production_plans.py",
        "backend/app/api/maturity.py",
        "backend/app/api/master_data.py",
        "backend/app/api/planning.py",
        "backend/app/api/weather.py",
    ],
)
def test_api_only_changes_the_deprecated_status_alias(path):
    from starlette import status

    old = subprocess.check_output(["git", "show", f"{BASE}:{path}"], cwd=ROOT, text=True)
    expected = old.replace("HTTP_422_UNPROCESSABLE_ENTITY", "HTTP_422_UNPROCESSABLE_CONTENT")
    actual = (ROOT / path).read_text()
    assert "HTTP_422_UNPROCESSABLE_ENTITY" not in actual
    assert ast.dump(ast.parse(actual)) == ast.dump(ast.parse(expected))
    assert status.HTTP_422_UNPROCESSABLE_CONTENT == 422


@pytest.mark.parametrize(
    "instant",
    [
        datetime(2026, 2, 15, 16, 0),
        datetime(2026, 2, 15, 16, 0, tzinfo=UTC),
        datetime(2026, 2, 15, 16, 0, 0, 123456, tzinfo=timezone(timedelta(hours=8))),
    ],
)
def test_explicit_sqlite_datetime_text_matches_legacy_adapter_exactly(instant):
    # Preserve the old bytes, including offset and microseconds, without making
    # a global adapter that could change application persistence semantics.
    with closing(sqlite3.connect(":memory:")) as connection:
        with pytest.warns(DeprecationWarning, match="default datetime adapter"):
            legacy = connection.execute("SELECT ?", (instant,)).fetchone()[0]
        explicit = connection.execute("SELECT ?", (instant.isoformat(" "),)).fetchone()[0]
    assert explicit == legacy
    assert datetime.fromisoformat(explicit) == instant


def test_asyncio_auto_and_session_loop_policy_remains_in_force(pytestconfig):
    assert pytestconfig.getini("asyncio_mode") == "auto"
    assert pytestconfig.getini("asyncio_default_test_loop_scope") == "session"
    assert pytestconfig.getini("asyncio_default_fixture_loop_scope") == "session"
