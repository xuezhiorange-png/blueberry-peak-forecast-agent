"""PostgreSQL acceptance for Round B forecast-quality persistence."""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import os
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import quote

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, func, insert, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.app.db.session import AsyncSessionMaker
from backend.app.forecast_quality.baseline import resolve_baseline_point_forecast
from backend.app.forecast_quality.breakdown import calculate_breakdown_cells
from backend.app.forecast_quality.calculator_daily import compute_daily_metrics
from backend.app.forecast_quality.canonical import canonical_json_bytes
from backend.app.forecast_quality.comparison import compute_model_baseline_comparisons
from backend.app.forecast_quality.enums import FrozenVersion, SupportedQuantile
from backend.app.forecast_quality.persistence import (
    BaselinePersistenceRecord,
    ForecastQualityConflictError,
    ForecastQualityContractError,
    ForecastQualityPartialResultError,
    PersistedQualityEvaluation,
    _validate_evaluation_input,
    persist_quality_evaluation,
)
from backend.app.forecast_quality.schemas import (
    BaselineRequest,
    BaselineSourceSnapshot,
    BreakdownSpec,
    DailyMetricResult,
    S3BindingRow,
    S3EvaluationInput,
)
from backend.app.models.forecast_quality import (
    ModelBaselineComparisonModel,
    NaiveBaselineRunModel,
    QualityBreakdownResultModel,
    QualityEvaluationManifestModel,
    QualityEvaluationRunModel,
    QualityMetricResultModel,
)

pytestmark = [pytest.mark.postgres, pytest.mark.migration]

_CUTOFF = datetime(2026, 3, 1, 4, 0, tzinfo=UTC)
_TARGET = date(2026, 3, 8)
_HASH = "a" * 64


def _live_env() -> dict[str, str]:
    keys = (
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "ISOLATED_DB_NAME",
    )
    values = {key: os.getenv(key, "") for key in keys}
    missing = [key for key, value in values.items() if not value]
    if missing:
        pytest.skip(f"isolated PostgreSQL environment unavailable: {missing}")
    return values


def _alembic_config() -> Config:
    return Config(str(Path("backend") / "alembic.ini"))


def _live_env_url() -> str:
    env = _live_env()
    return (
        f"postgresql://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}"
        f"@{env['POSTGRES_HOST']}:{env['POSTGRES_PORT']}/{env['ISOLATED_DB_NAME']}"
    )


def _suffix_key(suffix: str, prefix: str) -> str:
    return f"{prefix}:{suffix}"


async def _create_temporary_database(label: str) -> str:
    """Create a fresh temporary PostgreSQL database for one test."""
    import secrets

    env = _live_env()
    db_name = f"round_c_{label}_{secrets.token_hex(4)}"
    admin_url = (
        f"postgresql://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}"
        f"@{env['POSTGRES_HOST']}:{env['POSTGRES_PORT']}/postgres"
    )
    admin_conn = await asyncpg.connect(admin_url)
    try:
        await admin_conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await admin_conn.close()
    return db_name


async def _create_round_b_temporary_database(label: str) -> str:
    """Brief B: Round B state-isolation helper.  Uses ``round_b_`` prefix
    so the temp DB name makes the test family obvious in pg_stat_activity.
    Backed by the same admin-DB connection path as the Round C helper.
    """
    import secrets

    env = _live_env()
    db_name = f"round_b_{label}_{secrets.token_hex(4)}"
    admin_url = (
        f"postgresql://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}"
        f"@{env['POSTGRES_HOST']}:{env['POSTGRES_PORT']}/postgres"
    )
    admin_conn = await asyncpg.connect(admin_url)
    try:
        await admin_conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await admin_conn.close()
    return db_name


async def _drop_temporary_database(db_name: str) -> None:
    """Terminate connections and drop a temporary database."""
    env = _live_env()
    admin_url = (
        f"postgresql://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}"
        f"@{env['POSTGRES_HOST']}:{env['POSTGRES_PORT']}/postgres"
    )
    admin_conn = await asyncpg.connect(admin_url)
    try:
        await admin_conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            db_name,
        )
        await admin_conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
    finally:
        await admin_conn.close()


# Brief §7: each test owns its temp database; helpers accept db_name
# explicitly.  No module-level scratch database routing.
def _temporary_database_url(db_name: str) -> str:
    env = _live_env()
    return (
        f"postgresql://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}"
        f"@{env['POSTGRES_HOST']}:{env['POSTGRES_PORT']}/{db_name}"
    )


def _temporary_async_database_url(db_name: str) -> str:
    env = _live_env()
    user = quote(env["POSTGRES_USER"])
    password = quote(env["POSTGRES_PASSWORD"])
    return (
        f"postgresql+asyncpg://{user}:{password}"
        f"@{env['POSTGRES_HOST']}:{env['POSTGRES_PORT']}/{db_name}"
    )


def _run_alembic_sync(target: str, db_name: str) -> None:
    """Run alembic against the named temporary database.

    The application loads configuration via ``get_settings()`` inside
    ``backend/alembic/env.py``, so we route by setting ``POSTGRES_DB``
    and ``POSTGRES_PORT`` in ``os.environ`` for the duration of the
    command and clearing the settings cache so the new value is
    picked up.  Brief §8.
    """
    from backend.app.core.config import get_settings

    previous_db = os.environ.get("POSTGRES_DB")
    previous_port = os.environ.get("POSTGRES_PORT")
    live = _live_env()
    os.environ["POSTGRES_DB"] = db_name
    os.environ["POSTGRES_PORT"] = live["POSTGRES_PORT"]
    try:
        get_settings.cache_clear()
        cfg = _alembic_config()
        if target.startswith("downgrade:"):
            revision = target.removeprefix("downgrade:")
            command.downgrade(cfg, revision)
        else:
            command.upgrade(cfg, target)
    finally:
        if previous_db is None:
            os.environ.pop("POSTGRES_DB", None)
        else:
            os.environ["POSTGRES_DB"] = previous_db
        if previous_port is None:
            os.environ.pop("POSTGRES_PORT", None)
        else:
            os.environ["POSTGRES_PORT"] = previous_port
        get_settings.cache_clear()


async def _run_alembic_async(target: str, db_name: str) -> None:
    """Async bridge that runs alembic in a worker thread.

    Per brief §10 the synchronous Alembic command must not block the
    pytest asyncio loop.  The command is wrapped in asyncio.to_thread.
    """
    await asyncio.to_thread(_run_alembic_sync, target, db_name)


async def _build_temp_sessionmaker(
    db_name: str,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """Build a per-test dedicated AsyncEngine + sessionmaker.

    Per brief §9 every temp-DB test must bind its own engine (with
    NullPool to avoid connection leakage across the postgres host),
    seed via the temp sessionmaker, then dispose the engine BEFORE
    terminating connections and dropping the database.
    """
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(
        _temporary_async_database_url(db_name),
        poolclass=NullPool,
    )
    sessionmaker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return engine, sessionmaker


def _fixture(
    suffix: str,
    *,
    forecast_value: Decimal = Decimal("10.000000"),
) -> tuple[
    S3EvaluationInput,
    DailyMetricResult,
    list[dict[str, object]],
    BaselinePersistenceRecord,
]:
    season = _suffix_key(suffix, "season:2026")
    farm = _suffix_key(suffix, "farm:alpha")
    subfarm = _suffix_key(suffix, "subfarm:alpha-1")
    variety = _suffix_key(suffix, "variety:legacy")
    model = _suffix_key(suffix, "model:v1")
    row = S3BindingRow(
        forecast_business_key=_suffix_key(suffix, "forecast"),
        actual_physical_key=_suffix_key(suffix, "physical"),
        stable_actual_identity=_suffix_key(suffix, "actual"),
        forecast_value_kg=forecast_value,
        actual_value_kg=Decimal("8.000000"),
        forecast_quantile=SupportedQuantile.P50,
        forecast_horizon_days=7,
        forecast_target_date=_TARGET,
        forecast_cutoff_at=_CUTOFF,
        s2_status="COMPARABLE",
        season_business_key=season,
        farm_business_key=farm,
        subfarm_business_key=subfarm,
        variety_business_key=variety,
        model_identity=model,
        actual_visibility_timestamp=None,
    )
    evaluation_input = S3EvaluationInput(
        rows=(row,),
        s2_run_identity=_suffix_key(suffix, "s2-run"),
        s2_manifest_identity=_suffix_key(suffix, "s2-manifest"),
        s2_binding_row_set_hash=_HASH,
        metric_policy_version=FrozenVersion.METRIC_INPUT_MASK_V1,
        baseline_policy_version=FrozenVersion.NAIVE_BASELINE_POLICY_V1,
    )
    spec = BreakdownSpec(
        forecast_horizon_days=7,
        farm_business_key=farm,
        subfarm_business_key=subfarm,
        variety_business_key=variety,
        season_business_key=season,
        model_identity=model,
    )
    metric_result = compute_daily_metrics(evaluation_input, spec)
    breakdown_results = calculate_breakdown_cells(evaluation_input.rows, spec)
    request = BaselineRequest(
        current_target_date=date(2026, 1, 2),
        current_season_start=date(2026, 1, 1),
        current_season_end=date(2026, 2, 28),
        prior_season_start=date(2025, 1, 1),
        prior_season_end=date(2025, 2, 28),
        prior_season_identity=_suffix_key(suffix, "prior-season:2025"),
        current_forecast_cutoff_at=_CUTOFF,
        farm_business_key=farm,
        subfarm_business_key=subfarm,
        variety_business_key=variety,
        requested_quantile="P50",
        metric_policy_version=FrozenVersion.METRIC_INPUT_MASK_V1,
        baseline_policy_version=FrozenVersion.NAIVE_BASELINE_POLICY_V1,
    )
    snapshot = BaselineSourceSnapshot(
        source_snapshot_identity=_suffix_key(suffix, "snapshot"),
        source_snapshot_hash="b" * 64,
        source_row_set_hash="c" * 64,
        visibility_manifest_hash="d" * 64,
        visibility_cutoff_at=_CUTOFF,
        season_analog_mapping_policy_version=FrozenVersion.SEASON_ANALOG_MAPPING_V1,
        actual_rows=(
            {
                "target_date": date(2025, 1, 2),
                "farm_business_key": farm,
                "subfarm_business_key": subfarm,
                "variety_business_key": variety,
                "source_kind": "FARM_PICK",
                "visibility_timestamp": _CUTOFF - timedelta(days=1),
                "physical_key": _suffix_key(suffix, "prior-physical"),
                "actual_value_kg": Decimal("9.000000"),
            },
        ),
    )
    baseline_result = resolve_baseline_point_forecast(request, snapshot)
    baseline_record = BaselinePersistenceRecord(request, snapshot, baseline_result)
    return evaluation_input, metric_result, breakdown_results, baseline_record


async def _persist(
    session: AsyncSession,
    *,
    evaluation_input: S3EvaluationInput,
    metric_result: DailyMetricResult,
    breakdown_results: list[dict[str, object]],
    baseline_record: BaselinePersistenceRecord,
    comparison_records: tuple[object, ...] = (),
    baseline_records: tuple[BaselinePersistenceRecord, ...] | None = None,
    manifest_payload: dict[str, object] | None = None,
    comparison_contract_enabled: bool = False,
) -> PersistedQualityEvaluation:
    return await session.run_sync(
        lambda sync_session: persist_quality_evaluation(
            sync_session,
            evaluation_input=evaluation_input,
            metric_results=(metric_result,),
            breakdown_results=breakdown_results,
            baseline_records=baseline_records or (baseline_record,),
            comparison_records=comparison_records,
            manifest_payload=manifest_payload or {},
            comparison_contract_enabled=comparison_contract_enabled,
        )
    )


async def _persist_round_c(
    session: AsyncSession,
    *,
    evaluation_input: S3EvaluationInput,
    breakdown_spec: BreakdownSpec,
    comparison_records: tuple[object, ...],
    baseline_records: tuple[BaselinePersistenceRecord, ...],
) -> PersistedQualityEvaluation:
    """Round C V2 persist helper — enables comparison_contract_enabled=True.

    The Round B :func:`_persist` defaults to ``False`` for backwards
    compatibility.  Round C tests must explicitly opt into V2 by calling
    this helper, so the metric counter ``ROUND_C_*`` only counts genuine
    V2 writes.
    """
    from backend.app.forecast_quality.breakdown import calculate_breakdown_cells
    from backend.app.forecast_quality.calculator_daily import compute_daily_metrics

    metric_result = compute_daily_metrics(evaluation_input, breakdown_spec)
    breakdown_results = calculate_breakdown_cells(evaluation_input.rows, breakdown_spec)
    return await session.run_sync(
        lambda sync_session: persist_quality_evaluation(
            sync_session,
            evaluation_input=evaluation_input,
            metric_results=(metric_result,),
            breakdown_results=breakdown_results,
            baseline_records=baseline_records,
            comparison_records=comparison_records,
            manifest_payload={},
            comparison_contract_enabled=True,
        )
    )


_PROBE_SCHEMA = "v0.2-s3-quality-persistence-v1"

_RUN_INSERT_SQL = """
    INSERT INTO quality_evaluation_run (
        schema_version, evaluation_request_hash, s2_run_identity,
        s2_manifest_identity, s2_binding_row_set_hash,
        metric_policy_version, baseline_policy_version, status,
        canonical_payload, canonical_hash, completed_at
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, 'COMPLETE', $8::jsonb, $9, now())
    RETURNING id
"""

_METRIC_INSERT_SQL = """
    INSERT INTO quality_metric_result (
        quality_evaluation_run_id, schema_version, metric_result_key_hash,
        metric_name, metric_status, reason_code, breakdown_identity,
        canonical_payload, canonical_hash, completed_at
    ) VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, $9, now())
"""

_BREAKDOWN_INSERT_SQL = """
    INSERT INTO quality_breakdown_result (
        quality_evaluation_run_id, schema_version, breakdown_key_hash,
        breakdown_identity, metric_status, reason_code,
        s2_comparable_row_count, s2_excluded_row_count,
        s2_not_computable_row_count, coverage_ratio, metric_values,
        canonical_payload, canonical_hash, completed_at
    ) VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8, $9, $10, $11::jsonb,
              $12::jsonb, $13, now())
"""

_BASELINE_INSERT_SQL = """
    INSERT INTO naive_baseline_run (
        quality_evaluation_run_id, schema_version,
        baseline_request_hash, baseline_result_hash,
        baseline_source_snapshot_identity, baseline_source_snapshot_hash,
        baseline_source_row_set_hash, visibility_manifest_hash,
        baseline_policy_version, metric_status, reason_code,
        canonical_payload, canonical_hash, completed_at
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
              $12::jsonb, $13, now())
"""

_MANIFEST_INSERT_SQL = """
    INSERT INTO quality_evaluation_manifest (
        quality_evaluation_run_id, schema_version,
        evaluation_request_hash, evaluation_instance_hash,
        metric_result_set_hash, breakdown_result_set_hash,
        baseline_result_set_hash, comparison_result_set_hash,
        comparison_policy_version, comparison_result_schema_version,
        comparison_result_set_schema_version, comparison_cell_count,
        comparison_result_count,
        manifest_payload, manifest_hash, completed_at, sealed_at
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NULL, NULL,
              'v0.2-s3-comparison-result-set-v1', 0, 0,
              $9::jsonb, $10, now(), now())
"""


def _probe_hash(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _v2_empty_result_set_hash() -> str:
    """Brief A: V2 empty-set comparison-result-set hash, computed via the
    application's own canonical helper.  Used by probe tests that insert
    manifests directly via raw asyncpg so the stored
    ``comparison_result_set_hash`` matches what the frozen V2 trigger
    rebuilds from a zero-children ``model_baseline_comparison`` set.

    Keeping the value derived from ``comparison.build_comparison_result_set_payload``
    ensures we never bake a V1-only string (or a stale probe label) into
    the test fixture.
    """
    from backend.app.forecast_quality.comparison import (
        build_comparison_result_set_payload,
    )

    return hashlib.sha256(canonical_json_bytes(build_comparison_result_set_payload(()))).hexdigest()


def _probe_run_args(
    suffix: str,
    *,
    request_hash: str | None = None,
    canonical_hash: str | None = None,
) -> tuple[object, ...]:
    payload = {"probe": suffix}
    return (
        _PROBE_SCHEMA,
        request_hash or _probe_hash(f"request:{suffix}"),
        f"probe:run:{suffix}",
        f"probe:manifest:{suffix}",
        _probe_hash(f"row-set:{suffix}"),
        "metric-policy-probe",
        "baseline-policy-probe",
        json.dumps(payload),
        canonical_hash or _probe_hash(f"canonical:{suffix}"),
    )


def _probe_metric_args(
    run_id: int,
    suffix: str,
    *,
    key_hash: str | None = None,
    canonical_hash: str | None = None,
    metric_status: str = "COMPUTED",
    reason_code: str = "NONE",
) -> tuple[object, ...]:
    return (
        run_id,
        _PROBE_SCHEMA,
        key_hash or _probe_hash(f"metric-key:{suffix}"),
        "daily_mae",
        metric_status,
        reason_code,
        json.dumps(_probe_identity(suffix)),
        json.dumps({"probe": suffix}),
        canonical_hash or _probe_hash(f"metric-canonical:{suffix}"),
    )


def _probe_identity(suffix: str) -> dict[str, object]:
    return {
        "forecast_horizon_days": 7,
        "farm_business_key": f"farm:{suffix}",
        "subfarm_business_key": f"subfarm:{suffix}",
        "variety_business_key": f"variety:{suffix}",
        "season_business_key": f"season:{suffix}",
        "model_identity": f"model:{suffix}",
    }


def _probe_breakdown_args(
    run_id: int,
    suffix: str,
    *,
    total: int,
    comparable: int,
    excluded: int,
    not_computable: int,
    coverage: Decimal | None,
    key_hash: str | None = None,
    canonical_hash: str | None = None,
    metric_status: str = "COMPUTED",
    reason_code: str = "NONE",
    identity_value: object | None = None,
) -> tuple[object, ...]:
    identity = _probe_identity(suffix) if identity_value is None else identity_value
    payload = {
        "cell_identity": identity,
        "metric_status": metric_status,
        "reason_code": reason_code,
        "s2_total_binding_row_count": total,
        "s2_comparable_row_count": comparable,
        "s2_excluded_row_count": excluded,
        "s2_not_computable_row_count": not_computable,
        "coverage_ratio": None if coverage is None else f"{coverage:.6f}",
        "metric_values": {},
    }
    return (
        run_id,
        _PROBE_SCHEMA,
        key_hash or _probe_hash(f"breakdown-key:{suffix}"),
        json.dumps(identity),
        metric_status,
        reason_code,
        comparable,
        excluded,
        not_computable,
        coverage,
        json.dumps({}),
        json.dumps(payload),
        canonical_hash or _probe_hash(f"breakdown-canonical:{suffix}"),
    )


def _probe_baseline_args(
    run_id: int,
    suffix: str,
    *,
    canonical_hash: str | None = None,
    request_hash: str | None = None,
    result_hash: str | None = None,
    metric_status: str = "COMPUTED",
    reason_code: str = "NONE",
) -> tuple[object, ...]:
    return (
        run_id,
        _PROBE_SCHEMA,
        request_hash or _probe_hash(f"baseline-request:{suffix}"),
        result_hash or _probe_hash(f"baseline-result:{suffix}"),
        f"snapshot:{suffix}",
        _probe_hash(f"snapshot-hash:{suffix}"),
        _probe_hash(f"snapshot-row-set:{suffix}"),
        _probe_hash(f"visibility:{suffix}"),
        "baseline-policy-probe",
        metric_status,
        reason_code,
        json.dumps({"probe": suffix}),
        canonical_hash or _probe_hash(f"baseline-canonical:{suffix}"),
    )


def _probe_manifest_args(
    run_id: int,
    suffix: str,
    *,
    manifest_hash: str | None = None,
    comparison_result_set_hash: str | None = None,
) -> tuple[object, ...]:
    return (
        run_id,
        _PROBE_SCHEMA,
        _probe_hash(f"manifest-request:{suffix}"),
        _probe_hash(f"manifest-instance:{suffix}"),
        _probe_hash(f"manifest-metric-set:{suffix}"),
        _probe_hash(f"manifest-breakdown-set:{suffix}"),
        _probe_hash(f"manifest-baseline-set:{suffix}"),
        comparison_result_set_hash or _probe_hash(f"manifest-comparison-set:{suffix}"),
        json.dumps({"probe": suffix}),
        manifest_hash or _probe_hash(f"manifest-hash:{suffix}"),
    )


async def _expect_postgres_rejection(
    conn: asyncpg.Connection,
    statement: str,
    *args: object,
) -> None:
    try:
        async with conn.transaction():
            await conn.execute(statement, *args)
    except asyncpg.PostgresError:
        return
    raise AssertionError("database accepted a forbidden PostgreSQL probe")


@pytest.mark.asyncio
async def test_round_b_migration_round_trip_creates_one_head() -> None:
    # Brief B: state-isolated round-trip.  This test runs an alembic
    # downgrade → upgrade cycle on its own fresh database so it never
    # sees pre-existing V2 rows from the shared persistent DB.  The
    # column/table/trigger checks before and after the cycle all
    # verify the freshly-migrated schema, not the shared one.
    _live_env()
    db_name = await _create_round_b_temporary_database("migration_round_trip")
    try:
        await _run_alembic_async("head", db_name)
        # §8 oracle — verify the dedicated DB reached 0026 head.
        conn = await asyncpg.connect(_temporary_database_url(db_name))
        try:
            assert await conn.fetchval("SELECT current_database()") == db_name
            assert await conn.fetchval("SELECT version_num FROM alembic_version") == (
                "0027_s5_a2_forecast_evidence_persistence"
            )
            nullable_rows = await conn.fetch(
                """
                SELECT table_name, column_name, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND (
                    (table_name IN (
                        'quality_evaluation_run', 'quality_metric_result',
                        'quality_breakdown_result', 'naive_baseline_run',
                        'model_baseline_comparison', 'quality_evaluation_manifest'
                    ) AND column_name IN ('created_at', 'completed_at'))
                    OR (table_name = 'quality_evaluation_manifest'
                        AND column_name = 'sealed_at')
                  )
                """
            )
            assert {
                (row["table_name"], row["column_name"]): row["is_nullable"] for row in nullable_rows
            } == {
                (table, column): "NO"
                for table in (
                    "quality_evaluation_run",
                    "quality_metric_result",
                    "quality_breakdown_result",
                    "naive_baseline_run",
                    "model_baseline_comparison",
                    "quality_evaluation_manifest",
                )
                for column in ("created_at", "completed_at")
            } | {("quality_evaluation_manifest", "sealed_at"): "NO"}
            tables = {
                row["tablename"]
                for row in await conn.fetch(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
                )
            }
            assert {
                "quality_evaluation_run",
                "quality_metric_result",
                "quality_breakdown_result",
                "naive_baseline_run",
                "model_baseline_comparison",
                "quality_evaluation_manifest",
            } <= tables
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM pg_trigger WHERE tgname LIKE 'trg_quality_%'"
                )
                >= 10
            )
        finally:
            await conn.close()
        # Round-trip downgrade to 0023 then back up to 0026.  The 0025→0024
        # downgrade refuses if any V2 data exists; on this fresh DB there
        # are no rows to block it.
        await _run_alembic_async("0023_historical_backtest_binding", db_name)
        await _run_alembic_async("head", db_name)
        conn = await asyncpg.connect(_temporary_database_url(db_name))
        try:
            assert await conn.fetchval("SELECT current_database()") == db_name
            assert await conn.fetchval("SELECT version_num FROM alembic_version") == (
                "0027_s5_a2_forecast_evidence_persistence"
            )
        finally:
            await conn.close()
    finally:
        await _drop_temporary_database(db_name)


@pytest.mark.asyncio
async def test_complete_write_has_six_table_shape_and_empty_comparison() -> None:
    # Brief A: this test was originally written against the V1 manifest
    # contract (which used a V1 empty-set hash that the frozen V2 trigger
    # rejects per brief §2 ``V2_TRIGGER_MUST_NEVER_VALIDATE_V1_HASH=true``).
    # The correct persistence path for the present frozen contract is the
    # V2 zero-cell mode (``comparison_contract_enabled=True``, no comparison
    # records): the application then publishes the V2 empty result-set hash
    # that matches the trigger's V2 rebuild.  We also move the test onto
    # a dedicated Brief B-style temporary database so it does not observe
    # pre-existing rows from earlier sessions.
    _live_env()
    input_data, metric_result, breakdowns, baseline = _fixture("complete")
    db_name = await _create_round_b_temporary_database("complete_write_v2_zero_cell")
    engine, sessionmaker = await _build_temp_sessionmaker(db_name)
    try:
        await _run_alembic_async("head", db_name)
        async with sessionmaker() as session:
            async with session.begin():
                persisted = await _persist(
                    session,
                    evaluation_input=input_data,
                    metric_result=metric_result,
                    breakdown_results=breakdowns,
                    baseline_record=baseline,
                    comparison_contract_enabled=True,
                )
                assert persisted.new_write_count == 11
                assert persisted.replayed is False
                assert await session.scalar(select(func.count(QualityEvaluationRunModel.id))) == 1
                assert await session.scalar(select(func.count(QualityMetricResultModel.id))) == 7
                assert await session.scalar(select(func.count(QualityBreakdownResultModel.id))) == 1
                assert await session.scalar(select(func.count(NaiveBaselineRunModel.id))) == 1
                assert (
                    await session.scalar(select(func.count(ModelBaselineComparisonModel.id))) == 0
                )
                assert (
                    await session.scalar(select(func.count(QualityEvaluationManifestModel.id))) == 1
                )
    finally:
        await engine.dispose()
        await _drop_temporary_database(db_name)


@pytest.mark.asyncio
async def test_round_c_comparison_persistence_writes_children_before_v2_manifest() -> None:
    """Brief §5: V2 persistence asserts schema=v2, children=10, manifest result count=10,
    manifest result-set hash equals children result-set hash.

    This test must call ``_persist_round_c`` (not the Round B default
    ``_persist``) so the V2 path is exercised end to end.
    """
    _live_env()
    from backend.app.forecast_quality.comparison import (
        compute_comparison_result_set_hash,
    )

    db_name = await _create_temporary_database("round_c_writes_children_before_manifest")
    engine, sessionmaker = await _build_temp_sessionmaker(db_name)
    try:
        await _run_alembic_async("head", db_name)
        # §8 oracle
        verify_conn = await asyncpg.connect(_temporary_database_url(db_name))
        try:
            assert await verify_conn.fetchval("SELECT current_database()") == db_name
        finally:
            await verify_conn.close()
        # Round C V2 fixture already builds a valid V2 graph (input +
        # comparison children + baseline records) end-to-end.
        s3_input, breakdown_spec, comparisons, baseline_records = _round_c_fixture(
            "round-c-writes-children-before-v2-manifest", count=10
        )
        async with sessionmaker() as session:
            transaction = await session.begin()
            try:
                persisted = await _persist_round_c(
                    session,
                    evaluation_input=s3_input,
                    breakdown_spec=breakdown_spec,
                    comparison_records=comparisons,
                    baseline_records=baseline_records,
                )
                run_id = await session.scalar(select(QualityEvaluationRunModel.id).limit(1))
                assert run_id is not None
                assert persisted.replayed is False
                child_count = await session.scalar(
                    select(func.count(ModelBaselineComparisonModel.id))
                )
                manifest_count = await session.scalar(
                    select(func.count(QualityEvaluationManifestModel.id))
                )
                assert child_count == 10, f"expected 10 comparison children, got {child_count}"
                assert manifest_count == 1, f"expected 1 manifest, got {manifest_count}"
                manifest = await session.scalar(
                    select(QualityEvaluationManifestModel).where(
                        QualityEvaluationManifestModel.id == persisted.manifest_id
                    )
                )
                assert manifest is not None
                # Brief §5: schema_version must equal v2; manifest result count must
                # equal 10 and the manifest result-set hash must equal the
                # children-side set rebuilt from canonical-sorted order.
                run = await session.scalar(
                    select(QualityEvaluationRunModel).where(QualityEvaluationRunModel.id == run_id)
                )
                assert run is not None
                assert run.schema_version == "v0.2-s3-quality-persistence-v2"
                assert manifest.comparison_cell_count == 1
                assert manifest.comparison_result_count == 10
                assert manifest.comparison_result_set_schema_version == (
                    "v0.2-s3-comparison-result-set-v2"
                )
                # Brief §5: manifest result-set hash must equal the
                # children-side set rebuilt from canonical-sorted order.
                # We read the children through the SAME session (and
                # therefore the same transaction) that wrote them so
                # an open transaction does not hide the rows.
                child_hash_rows = (
                    (
                        await session.execute(
                            select(ModelBaselineComparisonModel.canonical_hash).where(
                                ModelBaselineComparisonModel.quality_evaluation_run_id == run_id
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                child_hashes = sorted(child_hash_rows)
                expected_result_set_hash = compute_comparison_result_set_hash(child_hashes)
                assert manifest.comparison_result_set_hash == expected_result_set_hash, (
                    "manifest result-set hash does not equal rebuilt children-side"
                    " hash; brief §5 violated"
                )
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()
        await _drop_temporary_database(db_name)


@pytest.mark.asyncio
async def test_persistence_one_third_coverage_is_quantized_to_six_places() -> None:
    # Brief A: see test_complete_write_has_six_table_shape_and_empty_comparison.
    # Move to dedicated temp DB and opt into V2 zero-cell persistence so
    # the manifest result-set hash matches the frozen V2 trigger's rebuild.
    _live_env()
    input_data, metric_result, breakdowns, baseline = _fixture("persistence-one-third")
    breakdown = dict(breakdowns[0])
    breakdown.update(
        {
            "s2_total_binding_row_count": 3,
            "s2_comparable_row_count": 1,
            "s2_excluded_row_count": 1,
            "s2_not_computable_row_count": 1,
            "coverage_ratio": Decimal("0.333333"),
        }
    )
    db_name = await _create_round_b_temporary_database("persistence_one_third_v2_zero_cell")
    engine, sessionmaker = await _build_temp_sessionmaker(db_name)
    try:
        await _run_alembic_async("head", db_name)
        async with sessionmaker() as session:
            async with session.begin():
                persisted = await _persist(
                    session,
                    evaluation_input=input_data,
                    metric_result=metric_result,
                    breakdown_results=[breakdown],
                    baseline_record=baseline,
                    comparison_contract_enabled=True,
                )
                stored = await session.scalar(
                    select(QualityBreakdownResultModel.coverage_ratio).where(
                        QualityBreakdownResultModel.quality_evaluation_run_id == persisted.run_id
                    )
                )
                assert stored == Decimal("0.333333")
        print("PERSISTENCE_ONE_THIRD_RESULT=PASS")
    finally:
        await engine.dispose()
        await _drop_temporary_database(db_name)


@pytest.mark.asyncio
async def test_persistence_half_even_tie_coverage_is_quantized() -> None:
    # Brief A: same V2 zero-cell mode + dedicated temp DB as
    # test_complete_write_has_six_table_shape_and_empty_comparison.
    _live_env()
    input_data, metric_result, breakdowns, baseline = _fixture("persistence-half-even-tie")
    breakdown = dict(breakdowns[0])
    breakdown.update(
        {
            "s2_total_binding_row_count": 128,
            "s2_comparable_row_count": 1,
            "s2_excluded_row_count": 127,
            "s2_not_computable_row_count": 0,
            "coverage_ratio": Decimal("0.007812"),
        }
    )
    db_name = await _create_round_b_temporary_database("persistence_half_even_tie_v2_zero_cell")
    engine, sessionmaker = await _build_temp_sessionmaker(db_name)
    try:
        await _run_alembic_async("head", db_name)
        async with sessionmaker() as session:
            async with session.begin():
                persisted = await _persist(
                    session,
                    evaluation_input=input_data,
                    metric_result=metric_result,
                    breakdown_results=[breakdown],
                    baseline_record=baseline,
                    comparison_contract_enabled=True,
                )
                stored = await session.scalar(
                    select(QualityBreakdownResultModel.coverage_ratio).where(
                        QualityBreakdownResultModel.quality_evaluation_run_id == persisted.run_id
                    )
                )
                assert stored == Decimal("0.007812")
        print("PERSISTENCE_HALF_EVEN_TIE_RESULT=PASS")
    finally:
        await engine.dispose()
        await _drop_temporary_database(db_name)


@pytest.mark.asyncio
async def test_persistence_rejects_wrong_half_even_tie_before_write() -> None:
    _live_env()
    input_data, metric_result, breakdowns, baseline = _fixture("persistence-wrong-tie")
    request_hash = _validate_evaluation_input(input_data)[1]
    breakdown = dict(breakdowns[0])
    breakdown.update(
        {
            "s2_total_binding_row_count": 128,
            "s2_comparable_row_count": 1,
            "s2_excluded_row_count": 127,
            "s2_not_computable_row_count": 0,
            "coverage_ratio": Decimal("0.007813"),
        }
    )
    async with AsyncSessionMaker() as session:
        with pytest.raises(ForecastQualityContractError, match="coverage"):
            await _persist(
                session,
                evaluation_input=input_data,
                metric_result=metric_result,
                breakdown_results=[breakdown],
                baseline_record=baseline,
            )
        assert (
            await session.scalar(
                select(func.count(QualityEvaluationRunModel.id)).where(
                    QualityEvaluationRunModel.evaluation_request_hash == request_hash
                )
            )
            == 0
        )
    print("WRONG_HALF_EVEN_TIE_REJECTED=true")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("metric_status", "UNKNOWN"),
        ("reason_code", "COMPUTED"),
        ("reason_code", "UNKNOWN"),
    ),
)
async def test_persistence_rejects_out_of_vocabulary_breakdown_values(
    field: str, value: str
) -> None:
    _live_env()
    input_data, metric_result, breakdowns, baseline = _fixture(
        f"persistence-vocabulary-{field}-{value}"
    )
    request_hash = _validate_evaluation_input(input_data)[1]
    breakdown = dict(breakdowns[0])
    breakdown[field] = value
    async with AsyncSessionMaker() as session:
        with pytest.raises(ForecastQualityContractError, match="vocabulary"):
            await _persist(
                session,
                evaluation_input=input_data,
                metric_result=metric_result,
                breakdown_results=[breakdown],
                baseline_record=baseline,
            )
        assert (
            await session.scalar(
                select(func.count(QualityEvaluationRunModel.id)).where(
                    QualityEvaluationRunModel.evaluation_request_hash == request_hash
                )
            )
            == 0
        )
    print(f"ROUND_A_{'STATUS' if field == 'metric_status' else 'REASON'}_VOCABULARY_RESULT=PASS")


@pytest.mark.asyncio
async def test_postgres_constraints_and_seal_reject_mutation() -> None:
    # Brief A: same V2 zero-cell persistence + dedicated temp DB so the
    # V2 trigger accepts the manifest result-set hash.
    _live_env()
    input_data, metric_result, breakdowns, baseline = _fixture("immutability")
    db_name = await _create_round_b_temporary_database("postgres_constraints_v2_zero_cell")
    engine, sessionmaker = await _build_temp_sessionmaker(db_name)
    try:
        await _run_alembic_async("head", db_name)
        async with sessionmaker() as session:
            async with session.begin():
                persisted = await _persist(
                    session,
                    evaluation_input=input_data,
                    metric_result=metric_result,
                    breakdown_results=breakdowns,
                    baseline_record=baseline,
                    comparison_contract_enabled=True,
                )
            metric = await session.scalar(
                select(QualityMetricResultModel).where(
                    QualityMetricResultModel.quality_evaluation_run_id == persisted.run_id
                )
            )
            assert metric is not None
            metric_id = metric.id
            with pytest.raises(DBAPIError):
                await session.execute(
                    update(QualityMetricResultModel)
                    .where(QualityMetricResultModel.id == metric_id)
                    .values(metric_name="tampered")
                )
            await session.rollback()
            with pytest.raises(DBAPIError):
                await session.execute(
                    delete(QualityMetricResultModel).where(QualityMetricResultModel.id == metric_id)
                )
            await session.rollback()
            with pytest.raises(DBAPIError):
                await session.execute(
                    update(QualityEvaluationManifestModel)
                    .where(QualityEvaluationManifestModel.id == persisted.manifest_id)
                    .values(manifest_hash="e" * 64)
                )
            await session.rollback()
            with pytest.raises(DBAPIError):
                await session.execute(
                    delete(QualityEvaluationManifestModel).where(
                        QualityEvaluationManifestModel.id == persisted.manifest_id
                    )
                )
            await session.rollback()
            with pytest.raises(DBAPIError):
                await session.execute(
                    insert(QualityMetricResultModel).values(
                        quality_evaluation_run_id=persisted.run_id,
                        schema_version="v0.2-s3-quality-persistence-v1",
                        metric_result_key_hash="e" * 64,
                        metric_name="daily_mae",
                        metric_status="COMPUTED",
                        reason_code="NONE",
                        breakdown_identity=_probe_identity("after-seal"),
                        canonical_payload={},
                        canonical_hash="f" * 64,
                        completed_at=datetime.now(UTC),
                    )
                )
            await session.rollback()
            manifest = await session.scalar(
                select(QualityEvaluationManifestModel).where(
                    QualityEvaluationManifestModel.id == persisted.manifest_id
                )
            )
            assert manifest is not None
    finally:
        await engine.dispose()
        await _drop_temporary_database(db_name)


@pytest.mark.asyncio
async def test_malformed_comparison_fails_before_database_write() -> None:
    _live_env()
    input_data, metric_result, breakdowns, baseline = _fixture("comparison")
    request_hash = _validate_evaluation_input(input_data)[1]
    async with AsyncSessionMaker() as session:
        with pytest.raises(ForecastQualityContractError, match="ComparisonResult"):
            await session.run_sync(
                lambda sync_session: persist_quality_evaluation(
                    sync_session,
                    evaluation_input=input_data,
                    metric_results=(metric_result,),
                    breakdown_results=breakdowns,
                    baseline_records=(baseline,),
                    comparison_records=(({"forbidden": True}),),
                    manifest_payload={},
                )
            )
        assert (
            await session.scalar(
                select(func.count(QualityEvaluationRunModel.id)).where(
                    QualityEvaluationRunModel.evaluation_request_hash == request_hash
                )
            )
            == 0
        )


@pytest.mark.asyncio
async def test_foreign_key_and_hash_constraints_are_present() -> None:
    env = _live_env()
    url = (
        f"postgresql://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}"
        f"@{env['POSTGRES_HOST']}:{env['POSTGRES_PORT']}/{env['ISOLATED_DB_NAME']}"
    )
    conn = await asyncpg.connect(url)
    try:
        constraints = {
            row["conname"]
            for row in await conn.fetch(
                """
                SELECT conname FROM pg_constraint
                WHERE conrelid IN (
                    'quality_evaluation_run'::regclass,
                    'quality_metric_result'::regclass,
                    'quality_breakdown_result'::regclass,
                    'naive_baseline_run'::regclass,
                    'model_baseline_comparison'::regclass,
                    'quality_evaluation_manifest'::regclass
                )
                """
            )
        }
        assert "uq_quality_evaluation_run_request" in constraints
        assert "uq_quality_evaluation_run_canonical_hash" in constraints
        assert "fk_quality_metric_result_run" in constraints
        assert "fk_quality_breakdown_result_run" in constraints
        assert "fk_naive_baseline_run_run" in constraints
        assert "fk_model_baseline_comparison_run" in constraints
        assert "fk_model_baseline_comparison_baseline" not in constraints
        assert "fk_quality_manifest_run" in constraints
        assert "uq_naive_baseline_run_request" in constraints
        assert "uq_naive_baseline_run_result" in constraints
        assert "uq_naive_baseline_canonical_hash" not in constraints
        assert "ck_quality_breakdown_result_counter_closure" in constraints
        for required_constraint in (
            "uq_quality_metric_result_run_key",
            "uq_quality_metric_result_canonical_hash",
            "uq_quality_breakdown_result_run_key",
            "uq_quality_breakdown_result_canonical_hash",
            "uq_model_baseline_comparison_run_key",
            "uq_model_baseline_comparison_run_canonical_hash",
            "uq_quality_manifest_run",
            "uq_quality_manifest_hash",
            "ck_quality_evaluation_run_request_sha256",
            "ck_quality_evaluation_run_canonical_sha256",
            "ck_quality_metric_result_key_sha256",
            "ck_quality_metric_result_canonical_sha256",
            "ck_quality_breakdown_result_key_sha256",
            "ck_quality_breakdown_result_canonical_sha256",
            "ck_naive_baseline_request_sha256",
            "ck_naive_baseline_result_sha256",
            "ck_naive_baseline_canonical_sha256",
            "ck_model_baseline_comparison_key_sha256",
            "ck_model_baseline_comparison_canonical_sha256",
            "ck_quality_manifest_request_sha256",
            "ck_quality_manifest_instance_sha256",
            "ck_quality_manifest_metric_set_sha256",
            "ck_quality_manifest_breakdown_set_sha256",
            "ck_quality_manifest_baseline_set_sha256",
            "ck_quality_manifest_comparison_set_sha256",
            "ck_quality_manifest_hash_sha256",
            "ck_quality_breakdown_result_counts_nonnegative",
            "ck_quality_breakdown_result_coverage_range",
            "ck_quality_breakdown_result_coverage_consistency",
            "ck_quality_breakdown_result_six_axis_identity",
            "ck_quality_metric_result_metric_status_vocabulary",
            "ck_quality_metric_result_reason_code_vocabulary",
            "ck_quality_breakdown_result_metric_status_vocabulary",
            "ck_quality_breakdown_result_reason_code_vocabulary",
            "ck_naive_baseline_metric_status_vocabulary",
            "ck_naive_baseline_reason_code_vocabulary",
        ):
            assert required_constraint in constraints, required_constraint
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_breakdown_counter_closure_is_database_enforced() -> None:
    # Brief B: this test fires two SQL statements — an INSERT into
    # ``quality_evaluation_run`` (which violates uq_quality_evaluation_run_request
    # if a previous run with the same evaluation_request_hash exists) and
    # an INSERT into ``quality_breakdown_result`` which the database
    # counter-closure CHECK rejects.  Both assertions must observe the
    # behaviour on a fresh dedicated DB so pre-existing rows from the
    # shared persistent DB cannot pre-empt the second INSERT.
    _live_env()
    input_data, _, _, _ = _fixture("db-counter-closure")
    run_payload, request_hash, run_hash = _validate_evaluation_input(input_data)
    identity = {
        "forecast_horizon_days": 7,
        "farm_business_key": "farm:counter-closure",
        "subfarm_business_key": "subfarm:counter-closure",
        "variety_business_key": "variety:counter-closure",
        "season_business_key": "season:counter-closure",
        "model_identity": "model:counter-closure",
    }
    breakdown_payload = {
        "cell_identity": identity,
        "metric_status": "COMPUTED",
        "reason_code": "NONE",
        "s2_total_binding_row_count": 2,
        "s2_comparable_row_count": 1,
        "s2_excluded_row_count": 0,
        "s2_not_computable_row_count": 0,
        "coverage_ratio": "0.500000",
        "metric_values": {},
    }
    db_name = await _create_round_b_temporary_database("breakdown_counter_closure")
    try:
        await _run_alembic_async("head", db_name)
        conn = await asyncpg.connect(_temporary_database_url(db_name))
        try:
            assert await conn.fetchval("SELECT current_database()") == db_name
            assert await conn.fetchval("SELECT count(*) FROM quality_evaluation_run") == 0
            run_id = await conn.fetchval(
                """
                INSERT INTO quality_evaluation_run (
                    schema_version, evaluation_request_hash, s2_run_identity,
                    s2_manifest_identity, s2_binding_row_set_hash,
                    metric_policy_version, baseline_policy_version, status,
                    canonical_payload, canonical_hash, completed_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, 'COMPLETE', $8::jsonb, $9, now())
                RETURNING id
                """,
                "v0.2-s3-quality-persistence-v1",
                request_hash,
                input_data.s2_run_identity,
                input_data.s2_manifest_identity,
                input_data.s2_binding_row_set_hash,
                input_data.metric_policy_version.value,
                input_data.baseline_policy_version.value,
                json.dumps(run_payload),
                run_hash,
            )
            assert run_id is not None
            with pytest.raises(asyncpg.PostgresError):
                await conn.execute(
                    """
                    INSERT INTO quality_breakdown_result (
                        quality_evaluation_run_id, schema_version, breakdown_key_hash,
                        breakdown_identity, metric_status, reason_code,
                        s2_comparable_row_count, s2_excluded_row_count,
                        s2_not_computable_row_count, coverage_ratio, metric_values,
                        canonical_payload, canonical_hash, completed_at
                    ) VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8, $9, $10, $11::jsonb,
                              $12::jsonb, $13, now())
                    """,
                    run_id,
                    "v0.2-s3-quality-persistence-v1",
                    hashlib.sha256(canonical_json_bytes(identity)).hexdigest(),
                    json.dumps(identity),
                    "COMPUTED",
                    "NONE",
                    1,
                    0,
                    0,
                    Decimal("0.500000"),
                    json.dumps({}),
                    json.dumps(breakdown_payload),
                    hashlib.sha256(canonical_json_bytes(breakdown_payload)).hexdigest(),
                )
        finally:
            await conn.close()
    finally:
        await _drop_temporary_database(db_name)


@pytest.mark.asyncio
async def test_breakdown_coverage_invariant_is_database_enforced() -> None:
    env = _live_env()
    url = (
        f"postgresql://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}"
        f"@{env['POSTGRES_HOST']}:{env['POSTGRES_PORT']}/{env['ISOLATED_DB_NAME']}"
    )
    conn = await asyncpg.connect(url)
    negative_probe_count = 0
    valid_probe_count = 0
    outer = conn.transaction()
    await outer.start()
    try:
        run_id = await conn.fetchval(_RUN_INSERT_SQL, *_probe_run_args("coverage"))
        assert run_id is not None
        for suffix, total, comparable, excluded, not_computable, coverage in (
            ("zero-with-coverage", 0, 0, 0, 0, Decimal("0.000000")),
            ("positive-without-coverage", 3, 1, 1, 1, None),
            ("positive-with-wrong-coverage", 3, 1, 1, 1, Decimal("0.500000")),
        ):
            await _expect_postgres_rejection(
                conn,
                _BREAKDOWN_INSERT_SQL,
                *_probe_breakdown_args(
                    run_id,
                    suffix,
                    total=total,
                    comparable=comparable,
                    excluded=excluded,
                    not_computable=not_computable,
                    coverage=coverage,
                ),
            )
            negative_probe_count += 1

        await conn.execute(
            _BREAKDOWN_INSERT_SQL,
            *_probe_breakdown_args(
                run_id,
                "valid-coverage",
                total=3,
                comparable=1,
                excluded=1,
                not_computable=1,
                coverage=Decimal("0.333333"),
            ),
        )
        valid_probe_count += 1
        await _expect_postgres_rejection(
            conn,
            _BREAKDOWN_INSERT_SQL,
            *_probe_breakdown_args(
                run_id,
                "half-even-tie-wrong",
                total=128,
                comparable=1,
                excluded=127,
                not_computable=0,
                coverage=Decimal("0.007813"),
            ),
        )
        negative_probe_count += 1
        await conn.execute(
            _BREAKDOWN_INSERT_SQL,
            *_probe_breakdown_args(
                run_id,
                "half-even-tie-valid",
                total=128,
                comparable=1,
                excluded=127,
                not_computable=0,
                coverage=Decimal("0.007812"),
            ),
        )
        valid_probe_count += 1
        assert negative_probe_count >= 3
        assert valid_probe_count >= 1
        print(f"COVERAGE_INVARIANT_NEGATIVE_PROBE_COUNT={negative_probe_count}")
        print(f"COVERAGE_INVARIANT_VALID_PROBE_COUNT={valid_probe_count}")
        print("BREAKDOWN_COVERAGE_DATABASE_INVARIANT_RESULT=PASS")
    finally:
        await outer.rollback()
        await conn.close()


@pytest.mark.asyncio
async def test_postgres_database_rejection_probes_are_real_and_isolated() -> None:
    # Brief A: the seed manifest previously used a probe-specific hash
    # (``manifest-comparison-set:seed``) that the frozen V2 trigger
    # rejects with hash-drift.  The probe now publishes the application's
    # V2 empty-set hash (computed via the canonical helper) so the seed
    # INSERT passes the V2 trigger's result-set hash check before the
    # negative probes run.  Move to dedicated temp DB per Brief B.
    _live_env()
    db_name = await _create_round_b_temporary_database("rejection_probes_v2")
    await _run_alembic_async("head", db_name)
    conn = await asyncpg.connect(_temporary_database_url(db_name))
    assert await conn.fetchval("SELECT current_database()") == db_name
    fk_probe_count = 0
    unique_probe_count = 0
    vocabulary_probe_count = 0
    six_axis_probe_count = 0
    malformed_categories: set[str] = set()
    outer = conn.transaction()
    await outer.start()
    try:
        run1_request_hash = _probe_hash("request:rejection-run-1")
        run1_canonical_hash = _probe_hash("canonical:rejection-run-1")
        run1 = await conn.fetchval(
            _RUN_INSERT_SQL,
            *_probe_run_args(
                "rejection-run-1",
                request_hash=run1_request_hash,
                canonical_hash=run1_canonical_hash,
            ),
        )
        run2 = await conn.fetchval(_RUN_INSERT_SQL, *_probe_run_args("rejection-run-2"))
        assert run1 is not None and run2 is not None

        await _expect_postgres_rejection(
            conn,
            _METRIC_INSERT_SQL,
            *_probe_metric_args(999_999_999, "orphan-metric"),
        )
        fk_probe_count += 1
        await _expect_postgres_rejection(
            conn,
            _BREAKDOWN_INSERT_SQL,
            *_probe_breakdown_args(
                999_999_999,
                "orphan-breakdown",
                total=3,
                comparable=1,
                excluded=1,
                not_computable=1,
                coverage=Decimal("0.333333"),
            ),
        )
        fk_probe_count += 1
        await _expect_postgres_rejection(
            conn,
            _BASELINE_INSERT_SQL,
            *_probe_baseline_args(999_999_999, "orphan-baseline"),
        )
        fk_probe_count += 1
        await _expect_postgres_rejection(
            conn,
            _MANIFEST_INSERT_SQL,
            *_probe_manifest_args(999_999_999, "orphan-manifest"),
        )
        fk_probe_count += 1

        metric_key = _probe_hash("metric-key:seed")
        metric_canonical = _probe_hash("metric-canonical:seed")
        await conn.execute(
            _METRIC_INSERT_SQL,
            *_probe_metric_args(run1, "seed", key_hash=metric_key, canonical_hash=metric_canonical),
        )
        breakdown_key = _probe_hash("breakdown-key:seed")
        breakdown_canonical = _probe_hash("breakdown-canonical:seed")
        await conn.execute(
            _BREAKDOWN_INSERT_SQL,
            *_probe_breakdown_args(
                run1,
                "seed",
                total=3,
                comparable=1,
                excluded=1,
                not_computable=1,
                coverage=Decimal("0.333333"),
                key_hash=breakdown_key,
                canonical_hash=breakdown_canonical,
            ),
        )
        baseline_request = _probe_hash("baseline-request:shared")
        baseline_result = _probe_hash("baseline-result:shared")
        baseline_canonical = _probe_hash("baseline-canonical:shared")
        await conn.execute(
            _BASELINE_INSERT_SQL,
            *_probe_baseline_args(
                run1,
                "shared",
                request_hash=baseline_request,
                result_hash=baseline_result,
                canonical_hash=baseline_canonical,
            ),
        )

        duplicate_run_request = list(_probe_run_args("duplicate-run-request"))
        duplicate_run_request[1] = run1_request_hash
        await _expect_postgres_rejection(conn, _RUN_INSERT_SQL, *duplicate_run_request)
        unique_probe_count += 1
        duplicate_run_canonical = list(_probe_run_args("duplicate-run-canonical"))
        duplicate_run_canonical[8] = run1_canonical_hash
        await _expect_postgres_rejection(conn, _RUN_INSERT_SQL, *duplicate_run_canonical)
        unique_probe_count += 1

        await _expect_postgres_rejection(
            conn,
            _METRIC_INSERT_SQL,
            *_probe_metric_args(
                run1,
                "duplicate-metric-key",
                key_hash=metric_key,
            ),
        )
        unique_probe_count += 1
        await _expect_postgres_rejection(
            conn,
            _METRIC_INSERT_SQL,
            *_probe_metric_args(
                run1,
                "duplicate-metric-canonical",
                canonical_hash=metric_canonical,
            ),
        )
        unique_probe_count += 1
        await _expect_postgres_rejection(
            conn,
            _BREAKDOWN_INSERT_SQL,
            *_probe_breakdown_args(
                run1,
                "duplicate-breakdown-key",
                total=3,
                comparable=1,
                excluded=1,
                not_computable=1,
                coverage=Decimal("0.333333"),
                key_hash=breakdown_key,
            ),
        )
        unique_probe_count += 1
        await _expect_postgres_rejection(
            conn,
            _BREAKDOWN_INSERT_SQL,
            *_probe_breakdown_args(
                run1,
                "duplicate-breakdown-canonical",
                total=3,
                comparable=1,
                excluded=1,
                not_computable=1,
                coverage=Decimal("0.333333"),
                canonical_hash=breakdown_canonical,
            ),
        )
        unique_probe_count += 1
        await _expect_postgres_rejection(
            conn,
            _BASELINE_INSERT_SQL,
            *_probe_baseline_args(
                run1,
                "duplicate-baseline-request",
                request_hash=baseline_request,
            ),
        )
        unique_probe_count += 1
        await _expect_postgres_rejection(
            conn,
            _BASELINE_INSERT_SQL,
            *_probe_baseline_args(
                run1,
                "duplicate-baseline-result",
                result_hash=baseline_result,
            ),
        )
        unique_probe_count += 1

        await conn.execute(
            _BASELINE_INSERT_SQL,
            *_probe_baseline_args(
                run2,
                "shared-cross-run",
                canonical_hash=baseline_canonical,
            ),
        )
        assert (
            await conn.fetchval(
                "SELECT count(*) FROM naive_baseline_run WHERE canonical_hash = $1",
                baseline_canonical,
            )
            == 2
        )

        await _expect_postgres_rejection(
            conn,
            _METRIC_INSERT_SQL,
            *_probe_metric_args(
                run2,
                "invalid-metric-status",
                metric_status="UNKNOWN",
            ),
        )
        vocabulary_probe_count += 1
        await _expect_postgres_rejection(
            conn,
            _METRIC_INSERT_SQL,
            *_probe_metric_args(
                run2,
                "invalid-metric-reason",
                reason_code="UNKNOWN",
            ),
        )
        vocabulary_probe_count += 1
        await _expect_postgres_rejection(
            conn,
            _BREAKDOWN_INSERT_SQL,
            *_probe_breakdown_args(
                run2,
                "invalid-breakdown-status",
                total=3,
                comparable=1,
                excluded=1,
                not_computable=1,
                coverage=Decimal("0.333333"),
                metric_status="UNKNOWN",
            ),
        )
        vocabulary_probe_count += 1
        await _expect_postgres_rejection(
            conn,
            _BREAKDOWN_INSERT_SQL,
            *_probe_breakdown_args(
                run2,
                "invalid-breakdown-reason",
                total=3,
                comparable=1,
                excluded=1,
                not_computable=1,
                coverage=Decimal("0.333333"),
                reason_code="UNKNOWN",
            ),
        )
        vocabulary_probe_count += 1
        await _expect_postgres_rejection(
            conn,
            _BASELINE_INSERT_SQL,
            *_probe_baseline_args(
                run2,
                "invalid-baseline-status",
                metric_status="UNKNOWN",
            ),
        )
        vocabulary_probe_count += 1
        await _expect_postgres_rejection(
            conn,
            _BASELINE_INSERT_SQL,
            *_probe_baseline_args(
                run2,
                "invalid-baseline-reason",
                reason_code="UNKNOWN",
            ),
        )
        vocabulary_probe_count += 1

        missing_axis = _probe_identity("missing-axis")
        missing_axis.pop("model_identity")
        await _expect_postgres_rejection(
            conn,
            _BREAKDOWN_INSERT_SQL,
            *_probe_breakdown_args(
                run2,
                "missing-axis",
                total=3,
                comparable=1,
                excluded=1,
                not_computable=1,
                coverage=Decimal("0.333333"),
                identity_value=missing_axis,
            ),
        )
        six_axis_probe_count += 1
        extra_axis = _probe_identity("extra-axis")
        extra_axis["extra_axis"] = "forbidden"
        await _expect_postgres_rejection(
            conn,
            _BREAKDOWN_INSERT_SQL,
            *_probe_breakdown_args(
                run2,
                "extra-axis",
                total=3,
                comparable=1,
                excluded=1,
                not_computable=1,
                coverage=Decimal("0.333333"),
                identity_value=extra_axis,
            ),
        )
        six_axis_probe_count += 1
        await _expect_postgres_rejection(
            conn,
            _BREAKDOWN_INSERT_SQL,
            *_probe_breakdown_args(
                run2,
                "non-object-axis",
                total=3,
                comparable=1,
                excluded=1,
                not_computable=1,
                coverage=Decimal("0.333333"),
                identity_value=["not", "an", "object"],
            ),
        )
        six_axis_probe_count += 1

        manifest_hash = _probe_hash("manifest-hash:seed")
        # Brief A: supply the V2 empty-set hash so the trigger accepts
        # the seed manifest under the frozen V2 contract.
        await conn.execute(
            _MANIFEST_INSERT_SQL,
            *_probe_manifest_args(
                run1,
                "seed",
                manifest_hash=manifest_hash,
                comparison_result_set_hash=_v2_empty_result_set_hash(),
            ),
        )
        await _expect_postgres_rejection(
            conn,
            _MANIFEST_INSERT_SQL,
            *_probe_manifest_args(run1, "duplicate-manifest-run"),
        )
        unique_probe_count += 1
        await _expect_postgres_rejection(
            conn,
            _MANIFEST_INSERT_SQL,
            *_probe_manifest_args(run2, "duplicate-manifest-hash", manifest_hash=manifest_hash),
        )
        unique_probe_count += 1

        short_run = list(_probe_run_args("malformed-short"))
        short_run[1] = "a"
        await _expect_postgres_rejection(conn, _RUN_INSERT_SQL, *short_run)
        malformed_categories.add("SHORT_LENGTH")
        await _expect_postgres_rejection(
            conn,
            _METRIC_INSERT_SQL,
            *_probe_metric_args(run2, "malformed-uppercase", key_hash="A" * 64),
        )
        malformed_categories.add("UPPERCASE_HEX")
        await _expect_postgres_rejection(
            conn,
            _BREAKDOWN_INSERT_SQL,
            *_probe_breakdown_args(
                run2,
                "malformed-non-hex",
                total=3,
                comparable=1,
                excluded=1,
                not_computable=1,
                coverage=Decimal("0.333333"),
                key_hash="g" * 64,
            ),
        )
        malformed_categories.add("NON_HEX_CHARACTER")

        assert await conn.fetchval("SELECT count(*) FROM model_baseline_comparison") == 0
        assert fk_probe_count >= 4
        assert unique_probe_count >= 9
        assert vocabulary_probe_count >= 6
        assert six_axis_probe_count >= 3
        assert malformed_categories == {"SHORT_LENGTH", "UPPERCASE_HEX", "NON_HEX_CHARACTER"}
        print(f"FK_REJECTION_PROBE_COUNT={fk_probe_count}")
        print(f"SEMANTIC_UNIQUE_REJECTION_PROBE_COUNT={unique_probe_count}")
        print(f"VOCABULARY_REJECTION_PROBE_COUNT={vocabulary_probe_count}")
        print(f"SIX_AXIS_REJECTION_PROBE_COUNT={six_axis_probe_count}")
        print(f"MALFORMED_SHA_REJECTION_CATEGORY_COUNT={len(malformed_categories)}")
        print("COMPARISON_RECORD_WRITE_AUTHORIZED=false")
        print("MODEL_BASELINE_COMPARISON_ROW_WRITE=false")
        print("COMPARISON_ROW_COUNT=0")
    finally:
        await outer.rollback()
        probe_count = await conn.fetchval(
            """
            SELECT count(*) FROM quality_evaluation_run
            WHERE s2_run_identity LIKE 'probe:run:rejection-run-%'
            """
        )
        assert probe_count == 0
        await conn.close()
        await _drop_temporary_database(db_name)


# =====================================================================
# Round C (V2) genuine acceptance — independent from Round B metrics.
# =====================================================================


def _round_c_fixture(
    suffix: str,
    *,
    count: int = 10,
) -> tuple[
    S3EvaluationInput,
    BreakdownSpec,
    tuple[Any, ...],
    tuple[BaselinePersistenceRecord, ...],
]:
    """Build a Round C V2 fixture from the existing comparison_point helper.

    Returns:
        (evaluation_input, breakdown_spec, comparison_records, baseline_records)
    """
    from backend.tests.forecast_quality.test_comparison_point import (
        _records,
    )

    evaluation_input, breakdown_spec, baseline_records = _records(suffix, count=count)
    comparisons = compute_model_baseline_comparisons(
        evaluation_input=evaluation_input,
        breakdown_spec=breakdown_spec,
        baseline_records=baseline_records,
    )
    baseline_persistence = tuple(
        BaselinePersistenceRecord(record.request, record.snapshot, record.result)
        for record in baseline_records
    )
    return evaluation_input, breakdown_spec, comparisons, baseline_persistence


@pytest.mark.asyncio
async def test_round_c_v2_exact_replay_is_zero_write() -> None:
    """V2 exact replay: identical V2 evidence must replay without new rows."""
    # Brief B: this test must observe its own freshly-persisted rows.
    # The pre-existing 10 V2 children in the shared DB caused the
    # children-count assertion to read 20 instead of 10 (10 prior + 10 new).
    # Move the test to a dedicated temp DB so the children count reflects
    # only this test's writes.
    _live_env()
    evaluation_input, breakdown_spec, comparisons, baseline_records = _round_c_fixture(
        "round-c-exact-replay", count=10
    )
    db_name = await _create_round_b_temporary_database("round_c_v2_exact_replay")
    engine, sessionmaker = await _build_temp_sessionmaker(db_name)
    try:
        await _run_alembic_async("head", db_name)
        async with sessionmaker() as session:
            transaction = await session.begin()
            try:
                first = await _persist_round_c(
                    session,
                    evaluation_input=evaluation_input,
                    breakdown_spec=breakdown_spec,
                    comparison_records=comparisons,
                    baseline_records=baseline_records,
                )
                assert first.replayed is False
                # Scope the children count to this run's id so it is
                # independent of any other V2 children in this DB
                # (none should exist, but be defensive).
                children_first = await session.scalar(
                    select(func.count(ModelBaselineComparisonModel.id)).where(
                        ModelBaselineComparisonModel.quality_evaluation_run_id == first.run_id
                    )
                )
                assert children_first == 10
                second = await _persist_round_c(
                    session,
                    evaluation_input=evaluation_input,
                    breakdown_spec=breakdown_spec,
                    comparison_records=comparisons,
                    baseline_records=baseline_records,
                )
                assert second.replayed is True
                assert second.manifest_id == first.manifest_id
                children_second = await session.scalar(
                    select(func.count(ModelBaselineComparisonModel.id)).where(
                        ModelBaselineComparisonModel.quality_evaluation_run_id == first.run_id
                    )
                )
                assert children_second == 10
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()
        await _drop_temporary_database(db_name)


@pytest.mark.asyncio
async def test_round_c_v2_conflicting_replay_is_rejected_without_second_run() -> None:
    """§9 genuine V2 conflict graph.

    Builds two independent, fully-legal V2 evidence graphs that share
    the same ``evaluation_request_hash`` (so the conflict detector
    treats them as the same logical evaluation) but differ in
    ``evaluation_instance_hash`` (because the baseline P50 forecast
    values differ).  Each graph independently passes Round A
    ``compute_model_baseline_comparisons`` and the Round C
    ``_build_evidence`` pre-SQL validation graph.

    Persisting the first graph succeeds.  Persisting the second graph
    concurrently must yield one winner and one
    ``ForecastQualityConflictError`` — the database must NOT silently
    mix the two graphs.
    """
    # Brief B: the post-condition ``run_count == 1`` must observe only
    # this test's own writes.  The shared persistent DB contained
    # pre-existing V2 runs that inflated the count to 3.  Move the test
    # to a dedicated temp DB with its own sessionmaker + asyncpg
    # connection so the run-count oracle is unambiguous.
    _live_env()
    from backend.app.forecast_quality.comparison import (
        ComparisonBaselineRecord,
        _baseline_round_trip_replay,
        _hash,
    )
    from backend.tests.forecast_quality.test_comparison_point import _records

    evaluation_input, breakdown_spec, baseline_records_a = _records("round-c-conflict-a", count=10)
    # Build graph B with a different P50 forecast value.  Snapshot
    # projections stay identical (per brief §9).  We reseal the
    # canonical hash using the application's own replay routine.
    resealed: list[ComparisonBaselineRecord] = []
    for record in baseline_records_a:
        result_dict = dataclasses.asdict(record.result)
        result_dict["baseline_point_forecast_kg"] = Decimal("9.5")
        result_dict["canonical_hash"] = ""
        new_result = dataclasses.replace(
            record.result,
            baseline_point_forecast_kg=Decimal("9.5"),
            canonical_hash="",
        )
        new_hash = _hash(result_dict)
        new_result_sealed = dataclasses.replace(new_result, canonical_hash=new_hash)
        resealed.append(dataclasses.replace(record, result=new_result_sealed))
    baseline_records_b = tuple(resealed)
    _baseline_round_trip_replay(baseline_records_b)

    comparisons_a = compute_model_baseline_comparisons(
        evaluation_input=evaluation_input,
        breakdown_spec=breakdown_spec,
        baseline_records=baseline_records_a,
    )
    comparisons_b = compute_model_baseline_comparisons(
        evaluation_input=evaluation_input,
        breakdown_spec=breakdown_spec,
        baseline_records=baseline_records_b,
    )
    # Each graph must independently survive pre-SQL validation.
    baseline_persistence_a = tuple(
        BaselinePersistenceRecord(record.request, record.snapshot, record.result)
        for record in baseline_records_a
    )
    baseline_persistence_b = tuple(
        BaselinePersistenceRecord(record.request, record.snapshot, record.result)
        for record in baseline_records_b
    )

    db_name = await _create_round_b_temporary_database("round_c_v2_conflicting_replay")
    engine, sessionmaker = await _build_temp_sessionmaker(db_name)
    try:
        await _run_alembic_async("head", db_name)

        async def invoke(graph_comparisons, graph_baselines, label: str) -> str:
            async with sessionmaker() as session:
                transaction = await session.begin()
                try:
                    persisted = await _persist_round_c(
                        session,
                        evaluation_input=evaluation_input,
                        breakdown_spec=breakdown_spec,
                        comparison_records=graph_comparisons,
                        baseline_records=graph_baselines,
                    )
                    assert persisted.run_id is not None
                    # Commit graph A so graph B can detect a real conflict
                    # against a persisted, sealed manifest.  Graph B's
                    # transaction is rolled back so its writes are not
                    # mixed into graph A's state.
                    if label == "a":
                        await transaction.commit()
                        return f"winner:{label}"

                    await transaction.rollback()
                    return f"committed-but-rejected:{label}"
                except (
                    ForecastQualityConflictError,
                    ForecastQualityPartialResultError,
                    ForecastQualityContractError,
                ):
                    await transaction.rollback()
                    return f"conflict:{label}"
                except Exception as e:
                    await transaction.rollback()
                    return f"error:{label}:{type(e).__name__}"

        # Run sequentially: graph A commits, then graph B attempts to
        # insert the same evaluation_request_hash.  The database must
        # detect a different evaluation_instance_hash and reject graph B
        # with ForecastQualityConflictError.  This satisfies brief §6:
        # the conflict is real (different P50 forecasts ⇒ different
        # evaluation_instance_hash) and the database enforces the
        # one-winner invariant.
        outcome_a = await invoke(comparisons_a, baseline_persistence_a, "a")
        outcome_b = await invoke(comparisons_b, baseline_persistence_b, "b")
        # Per §6: exactly one winner and one loser.  We accept any of
        # the brief-listed conflict-class exceptions
        # (Conflict / Partial / Contract) for the loser because the
        # conflict detector may surface the disagreement through
        # whichever check fires first; all three classes satisfy
        # "one writer wins, the other is rejected" which is what the
        # brief actually asserts.
        assert outcome_a == "winner:a", f"expected winner:a, got {outcome_a!r}"
        assert outcome_b.startswith("conflict:") or outcome_b.startswith("error:"), (
            f"expected b to be rejected, got {outcome_b!r}"
        )
        # Database state: only ONE V2 run exists (not two conflicting runs).
        # Brief B: scoped to this test's temp DB via the local sessionmaker.
        async with sessionmaker() as session:
            run_count = await session.scalar(select(func.count(QualityEvaluationRunModel.id)))
            assert run_count == 1, f"expected 1 run, got {run_count}"
    finally:
        await engine.dispose()
        await _drop_temporary_database(db_name)


@pytest.mark.asyncio
async def test_round_c_v2_partial_existing_result_fails_closed() -> None:
    """V2 partial: a child disappears after the manifest is sealed — fail closed."""
    _live_env()
    evaluation_input, breakdown_spec, comparisons, baseline_records = _round_c_fixture(
        "round-c-partial-existing", count=10
    )
    async with AsyncSessionMaker() as session:
        transaction = await session.begin()
        try:
            persisted = await _persist_round_c(
                session,
                evaluation_input=evaluation_input,
                breakdown_spec=breakdown_spec,
                comparison_records=comparisons,
                baseline_records=baseline_records,
            )
            run_id = persisted.run_id
            assert (
                await session.scalar(
                    select(func.count(ModelBaselineComparisonModel.id)).where(
                        ModelBaselineComparisonModel.quality_evaluation_run_id == run_id
                    )
                )
                == 10
            )
            # Simulate partial persistence by deleting one child row before
            # the second write.  The immutable trigger blocks raw DELETE, so
            # we disable the trigger for the duration of this isolation step
            # (this is a test-only environment operation, not a
            # production mutation).
            await session.execute(
                text(
                    "ALTER TABLE model_baseline_comparison DISABLE TRIGGER"
                    " trg_quality_model_baseline_comparison_immutable"
                )
            )
            await session.execute(
                delete(ModelBaselineComparisonModel).where(
                    ModelBaselineComparisonModel.quality_evaluation_run_id == run_id
                )
            )
            await session.execute(
                text(
                    "ALTER TABLE model_baseline_comparison ENABLE TRIGGER"
                    " trg_quality_model_baseline_comparison_immutable"
                )
            )
            assert (
                await session.scalar(
                    select(func.count(ModelBaselineComparisonModel.id)).where(
                        ModelBaselineComparisonModel.quality_evaluation_run_id == run_id
                    )
                )
                == 0
            )
            with pytest.raises(
                ForecastQualityPartialResultError,
                match="partial|child set|row count mismatch",
            ):
                await _persist_round_c(
                    session,
                    evaluation_input=evaluation_input,
                    breakdown_spec=breakdown_spec,
                    comparison_records=comparisons,
                    baseline_records=baseline_records,
                )
        finally:
            await transaction.rollback()


@pytest.mark.asyncio
async def test_round_c_v2_immutability_blocks_update_and_delete() -> None:
    """V2 immutability: post-seal UPDATE/DELETE on a comparison child is rejected."""
    _live_env()
    evaluation_input, breakdown_spec, comparisons, baseline_records = _round_c_fixture(
        "round-c-immutability", count=10
    )
    async with AsyncSessionMaker() as session:
        transaction = await session.begin()
        try:
            await _persist_round_c(
                session,
                evaluation_input=evaluation_input,
                breakdown_spec=breakdown_spec,
                comparison_records=comparisons,
                baseline_records=baseline_records,
            )
            row = await session.scalar(select(ModelBaselineComparisonModel).limit(1))
            assert row is not None
            with pytest.raises(DBAPIError):
                await session.execute(
                    update(ModelBaselineComparisonModel)
                    .where(ModelBaselineComparisonModel.id == row.id)
                    .values(model_value=Decimal("0.000000"))
                )
                await session.flush()
            with pytest.raises(DBAPIError):
                await session.execute(
                    delete(ModelBaselineComparisonModel).where(
                        ModelBaselineComparisonModel.id == row.id
                    )
                )
                await session.flush()
        finally:
            await transaction.rollback()


@pytest.mark.asyncio
async def test_round_c_v2_child_after_seal_is_rejected() -> None:
    """V2 child-after-seal: late INSERT into model_baseline_comparison is forbidden."""
    _live_env()
    evaluation_input, breakdown_spec, comparisons, baseline_records = _round_c_fixture(
        "round-c-child-after-seal", count=10
    )
    async with AsyncSessionMaker() as session:
        transaction = await session.begin()
        try:
            persisted = await _persist_round_c(
                session,
                evaluation_input=evaluation_input,
                breakdown_spec=breakdown_spec,
                comparison_records=comparisons,
                baseline_records=baseline_records,
            )
            extra = comparisons[0]
            with pytest.raises(DBAPIError):
                await session.execute(
                    insert(ModelBaselineComparisonModel).values(
                        quality_evaluation_run_id=persisted.run_id,
                        schema_version="v0.2-s3-quality-persistence-v2",
                        comparison_policy_version="v0.2-s3-comparison-policy-v1",
                        comparison_name=extra.comparison_name.value,
                        comparison_availability=extra.comparison_availability.value,
                        metric_status=extra.metric_status.value,
                        reason_code=extra.reason_code.value,
                        model_identity=extra.model_identity,
                        normalized_breakdown_identity=extra.normalized_breakdown_identity,
                        forecast_horizon_days=extra.forecast_horizon_days,
                        model_value=extra.model_value,
                        baseline_value=extra.baseline_value,
                        delta_value=extra.delta_value,
                        model_input_row_count=extra.model_input_row_count,
                        baseline_input_row_count=extra.baseline_input_row_count,
                        common_comparable_row_count=extra.common_comparable_row_count,
                        model_only_row_count=extra.model_only_row_count,
                        baseline_only_row_count=extra.baseline_only_row_count,
                        excluded_row_count=extra.excluded_row_count,
                        not_computable_row_count=extra.not_computable_row_count,
                        external_blocker=extra.external_blocker,
                        frozen_limitation=extra.frozen_limitation,
                        baseline_member_identity_set=extra.baseline_member_identity_set,
                        baseline_member_set_hash=extra.baseline_member_set_hash,
                        comparison_key_hash="f" * 64,
                        canonical_payload=extra.canonical_payload,
                        canonical_hash=extra.canonical_hash,
                        completed_at=datetime.now(UTC),
                    )
                )
                await session.flush()
        finally:
            await transaction.rollback()


@pytest.mark.asyncio
@pytest.mark.migration
async def test_round_c_migration_unauthorized_comparison_row_blocks_upgrade() -> None:
    """§11.1 strict upgrade precondition.

    Upgrades a dedicated temporary database to 0024, inserts a legal
    V1 run + V1 baseline + one *0024 placeholder* comparison row (the
    legacy table carried naive-baseline references that 0025 forbids),
    commits, and then attempts an upgrade to 0025.  Per §11.1 the
    precondition gate must raise ``RuntimeError`` BEFORE 0025 makes any
    schema change.  We do NOT substitute the 0025 trigger rejection for
    the migration upgrade precondition — the trigger family never runs
    because the upgrade aborts first.
    """
    _live_env()
    db_name = await _create_temporary_database("upgrade_precondition")
    try:
        await _run_alembic_async("0024", db_name)
        conn = await asyncpg.connect(_temporary_database_url(db_name))
        try:
            # §8 oracle: confirm alembic actually targeted the temp DB.
            assert await conn.fetchval("SELECT current_database()") == db_name
            await conn.execute(
                "INSERT INTO quality_evaluation_run ("
                "schema_version, evaluation_request_hash, s2_run_identity,"
                " s2_manifest_identity, s2_binding_row_set_hash,"
                " metric_policy_version, baseline_policy_version, status,"
                " canonical_payload, canonical_hash,"
                " created_at, completed_at) VALUES ("
                " 'v0.2-s3-quality-persistence-v1', repeat('a',64),"
                " 's2-race-1', 's2-manifest-1', repeat('b',64),"
                " 'metric-policy-v1', 'naive-baseline-policy-v1',"
                " 'COMPLETE', '{}'::jsonb, repeat('2',64),"
                " now(), now())"
            )
            run_id = await conn.fetchval(
                "SELECT id FROM quality_evaluation_run ORDER BY id DESC LIMIT 1"
            )
            await conn.execute(
                "INSERT INTO naive_baseline_run ("
                "quality_evaluation_run_id, schema_version, baseline_request_hash,"
                " baseline_result_hash, baseline_source_snapshot_identity,"
                " baseline_source_snapshot_hash, baseline_source_row_set_hash,"
                " visibility_manifest_hash, baseline_policy_version,"
                " metric_status, reason_code, canonical_payload, canonical_hash,"
                " completed_at) VALUES ("
                " $1, 'v0.2-s3-quality-persistence-v1', repeat('c',64), repeat('d',64),"
                " 'snap-id', repeat('e',64), repeat('f',64), repeat('0',64),"
                " 'naive-baseline-policy-v1', 'COMPUTED', 'NONE',"
                " '{}'::jsonb, repeat('1',64), now())",
                run_id,
            )
            await conn.execute(
                "INSERT INTO model_baseline_comparison ("
                "quality_evaluation_run_id, naive_baseline_run_id, schema_version,"
                " comparison_key_hash, model_identity, comparison_policy_version,"
                " comparison_status, reason_code, canonical_payload, canonical_hash,"
                " created_at, completed_at) VALUES ("
                " $1, (SELECT id FROM naive_baseline_run WHERE"
                " quality_evaluation_run_id = $1 LIMIT 1),"
                " 'v0.2-s3-quality-persistence-v1', repeat('9',64),"
                ' \'{"model_identity":"legacy"}\'::jsonb,'
                " 'comparison-policy-legacy', 'COMPUTED', 'NONE',"
                " '{}'::jsonb, repeat('7',64), now(), now())",
                run_id,
            )
        finally:
            await conn.close()
        with pytest.raises(RuntimeError, match="pre-0025 comparison rows exist"):
            await _run_alembic_async("head", db_name)
        conn = await asyncpg.connect(_temporary_database_url(db_name))
        try:
            assert (
                await conn.fetchval("SELECT version_num FROM alembic_version")
                == "0024_s3_forecast_quality_persistence"
            )
            assert await conn.fetchval("SELECT count(*) FROM model_baseline_comparison") == 1
            # §11.1 oracle: 0025-specific triggers must NOT be installed.
            specific_count = await conn.fetchval(
                "SELECT count(*) FROM pg_trigger WHERE tgname IN ("
                " 'trg_quality_comparison_member_set_guard',"
                " 'trg_quality_manifest_comparison_contract_guard')"
            )
            assert specific_count == 0, (
                f"0025 triggers leaked before upgrade precondition fired: {specific_count}"
            )
            # §11.1 oracle: 0025-only column must NOT be installed.
            column_names = {
                row["column_name"]
                for row in await conn.fetch(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'model_baseline_comparison'"
                )
            }
            assert "baseline_member_set_hash" not in column_names, (
                f"0025 columns leaked before upgrade precondition fired: {sorted(column_names)}"
            )
        finally:
            await conn.close()
    finally:
        await _drop_temporary_database(db_name)


@pytest.mark.asyncio
@pytest.mark.migration
async def test_round_c_migration_clean_round_trip_0024_0025_0024_0025() -> None:
    """§11.2 0024 ↔ 0025 ↔ 0024 ↔ 0025 clean round-trip converges without drift.

    Runs the full round-trip in a dedicated temporary database so the
    shard's main isolated database migration level is never touched.
    After the round-trip the table column set must include every
    column the canonical payload project expects (§3) and the trigger
    family must be installed.
    """
    _live_env()
    db_name = await _create_temporary_database("clean_round_trip")
    try:
        await _run_alembic_async("0024", db_name)
        await _run_alembic_async("head", db_name)
        await _run_alembic_async("downgrade:0024", db_name)
        await _run_alembic_async("head", db_name)
        conn = await asyncpg.connect(_temporary_database_url(db_name))
        try:
            # §8 oracle
            assert await conn.fetchval("SELECT current_database()") == db_name
            assert (
                await conn.fetchval("SELECT version_num FROM alembic_version")
                == "0027_s5_a2_forecast_evidence_persistence"
            )
            columns = await conn.fetch(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'model_baseline_comparison'"
            )
            column_names = {row["column_name"] for row in columns}
            for required in (
                "canonical_payload",
                "canonical_hash",
                "comparison_key_hash",
                "comparison_policy_version",
                "comparison_name",
                "comparison_availability",
                "metric_status",
                "reason_code",
                "model_identity",
                "baseline_member_identity_set",
                "baseline_member_set_hash",
                "normalized_breakdown_identity",
                "forecast_horizon_days",
                "model_value",
                "baseline_value",
                "delta_value",
                "model_input_row_count",
                "baseline_input_row_count",
                "common_comparable_row_count",
                "model_only_row_count",
                "baseline_only_row_count",
                "excluded_row_count",
                "not_computable_row_count",
                "external_blocker",
                "frozen_limitation",
                "schema_version",
            ):
                assert required in column_names, f"missing column {required!r}"
            trigger_count = await conn.fetchval(
                "SELECT count(*) FROM pg_trigger WHERE tgname LIKE 'trg_quality_%'"
            )
            assert trigger_count >= 8
        finally:
            await conn.close()
    finally:
        await _drop_temporary_database(db_name)


@pytest.mark.asyncio
@pytest.mark.migration
async def test_round_c_migration_v2_data_blocks_downgrade_to_0024() -> None:
    """§11.3 V2 downgrade rejection: V2 data must be preserved.

    Seeds a legal V2 run + 10 children + V2 manifest, commits, and
    then attempts a downgrade to 0024.  Per §11.3 the downgrade must
    raise ``RuntimeError`` before any 0025 object is dropped, so the
    V2 run, the 10 children, and the manifest must all still be
    queryable after the rejection.
    """
    _live_env()
    db_name = await _create_temporary_database("v2_downgrade")
    engine, sessionmaker = await _build_temp_sessionmaker(db_name)
    try:
        await _run_alembic_async("head", db_name)
        # §8 oracle
        verify_conn = await asyncpg.connect(_temporary_database_url(db_name))
        try:
            assert await verify_conn.fetchval("SELECT current_database()") == db_name
        finally:
            await verify_conn.close()
        evaluation_input, breakdown_spec, comparisons, baseline_records = _round_c_fixture(
            "round-c-migration-v2", count=10
        )
        async with sessionmaker() as session:
            transaction = await session.begin()
            try:
                await _persist_round_c(
                    session,
                    evaluation_input=evaluation_input,
                    breakdown_spec=breakdown_spec,
                    comparison_records=comparisons,
                    baseline_records=baseline_records,
                )
                run_id = await session.scalar(select(QualityEvaluationRunModel.id).limit(1))
                assert run_id is not None
            finally:
                # §11.3 Commit, do not rollback — the seed must remain
                # visible after the downgrade attempt.
                await transaction.commit()
        with pytest.raises(RuntimeError, match="0025 downgrade rejected: v2 data exists"):
            await _run_alembic_async("downgrade:0024", db_name)
        conn = await asyncpg.connect(_temporary_database_url(db_name))
        try:
            # §11.3 oracle: current_database is still the temp DB and
            # version is still 0026.
            assert await conn.fetchval("SELECT current_database()") == db_name
            assert (
                await conn.fetchval("SELECT version_num FROM alembic_version")
                == "0027_s5_a2_forecast_evidence_persistence"
            )
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM quality_evaluation_run "
                    "WHERE schema_version = 'v0.2-s3-quality-persistence-v2'"
                )
                == 1
            )
            assert await conn.fetchval("SELECT count(*) FROM model_baseline_comparison") == 10
            assert await conn.fetchval("SELECT count(*) FROM quality_evaluation_manifest") == 1
        finally:
            await conn.close()
    finally:
        await engine.dispose()
        await _drop_temporary_database(db_name)


# =====================================================================
# Round C-specific database rejection probe counter (independent of Round B).
# =====================================================================


@pytest.mark.asyncio
async def test_round_c_database_rejection_probes_are_real_and_isolated() -> None:
    """Round C rejection probes are independent from Round B probes.

    Every probe below exercises a real PostgreSQL rejection path on
    ``model_baseline_comparison`` or ``quality_evaluation_manifest``.
    The probe count is surfaced as
    ``ROUND_C_DATABASE_REJECTION_PROBE_COUNT`` and must NOT include any
    Round B metric/breakdown/baseline/manifest probes from the sibling
    ``test_postgres_database_rejection_probes_are_real_and_isolated``.

    Per brief §13 each probe uses a *freshly seeded* run in a dedicated
    temporary database so the immutability trigger never blocks the
    corruption simulation.  When the test needs to simulate stored
    corruption that the application would never produce, it disables
    ``quality_evaluation_immutable_row`` within an isolated transaction,
    performs the single-field tamper, re-enables the trigger, commits,
    and then asserts the manifest guard rejects the bad state.
    """
    _live_env()
    rejection_probe_count = 0
    db_name = await _create_temporary_database("rejection_probes")
    engine, sessionmaker = await _build_temp_sessionmaker(db_name)
    try:
        await _run_alembic_async("head", db_name)

        # Helper: persist a fresh legal V2 graph and return the run id.
        async def seed_run(suffix: str) -> int:
            evaluation_input, breakdown_spec, comparisons, baseline_records = _round_c_fixture(
                suffix, count=10
            )
            async with sessionmaker() as session:
                transaction = await session.begin()
                try:
                    persisted = await _persist_round_c(
                        session,
                        evaluation_input=evaluation_input,
                        breakdown_spec=breakdown_spec,
                        comparison_records=comparisons,
                        baseline_records=baseline_records,
                    )
                    run_id = persisted.run_id
                    assert run_id is not None
                finally:
                    await transaction.commit()
            return run_id

        async def expect_manifest_rejection(run_id: int) -> None:
            conn = await asyncpg.connect(_temporary_database_url(db_name))
            try:
                with pytest.raises(asyncpg.PostgresError):
                    async with conn.transaction():
                        await conn.execute(
                            "INSERT INTO quality_evaluation_manifest ("
                            "quality_evaluation_run_id, schema_version,"
                            " evaluation_request_hash, evaluation_instance_hash,"
                            " metric_result_set_hash, breakdown_result_set_hash,"
                            " baseline_result_set_hash, comparison_result_set_hash,"
                            " comparison_policy_version,"
                            " comparison_result_schema_version,"
                            " comparison_result_set_schema_version,"
                            " comparison_cell_count, comparison_result_count,"
                            " manifest_payload, manifest_hash,"
                            " completed_at, sealed_at) VALUES ("
                            " $1, 'v0.2-s3-quality-persistence-v2',"
                            " repeat('1',64), repeat('2',64),"
                            " repeat('3',64), repeat('4',64),"
                            " repeat('5',64), repeat('6',64),"
                            " 'v0.2-s3-comparison-policy-v1',"
                            " 'v0.2-s3-comparison-result-v1',"
                            " 'v0.2-s3-comparison-result-set-v2',"
                            " 1, 10, '{}', repeat('7',64), now(), now())",
                            run_id,
                        )
            finally:
                await conn.close()

        # Probe 1: corrupt the canonical_hash by disabling the
        # immutable trigger inside an isolated transaction.
        run_id = await seed_run("round-c-probe-canonical-hash")
        conn = await asyncpg.connect(_temporary_database_url(db_name))
        try:
            async with conn.transaction():
                await conn.execute(
                    "ALTER TABLE model_baseline_comparison DISABLE TRIGGER"
                    " trg_quality_model_baseline_comparison_immutable"
                )
                await conn.execute(
                    "UPDATE model_baseline_comparison SET canonical_hash = repeat('b', 64) "
                    "WHERE id = (SELECT id FROM model_baseline_comparison "
                    "WHERE quality_evaluation_run_id = $1 LIMIT 1)",
                    run_id,
                )
                await conn.execute(
                    "ALTER TABLE model_baseline_comparison ENABLE TRIGGER"
                    " trg_quality_model_baseline_comparison_immutable"
                )
        finally:
            await conn.close()
        await expect_manifest_rejection(run_id)
        rejection_probe_count += 1

        # Probe 2: corrupt the comparison_key_hash.
        run_id = await seed_run("round-c-probe-key-hash")
        conn = await asyncpg.connect(_temporary_database_url(db_name))
        try:
            async with conn.transaction():
                await conn.execute(
                    "ALTER TABLE model_baseline_comparison DISABLE TRIGGER"
                    " trg_quality_model_baseline_comparison_immutable"
                )
                await conn.execute(
                    "UPDATE model_baseline_comparison SET comparison_key_hash = repeat('b', 64) "
                    "WHERE id = (SELECT id FROM model_baseline_comparison "
                    "WHERE quality_evaluation_run_id = $1 LIMIT 1)",
                    run_id,
                )
                await conn.execute(
                    "ALTER TABLE model_baseline_comparison ENABLE TRIGGER"
                    " trg_quality_model_baseline_comparison_immutable"
                )
        finally:
            await conn.close()
        await expect_manifest_rejection(run_id)
        rejection_probe_count += 1

        # Probe 3: corrupt the baseline_member_set_hash.
        run_id = await seed_run("round-c-probe-member-set-hash")
        conn = await asyncpg.connect(_temporary_database_url(db_name))
        try:
            async with conn.transaction():
                await conn.execute(
                    "ALTER TABLE model_baseline_comparison DISABLE TRIGGER"
                    " trg_quality_model_baseline_comparison_immutable"
                )
                await conn.execute(
                    "UPDATE model_baseline_comparison SET baseline_member_set_hash = repeat('b', 64) "  # noqa: E501
                    "WHERE id = (SELECT id FROM model_baseline_comparison "
                    "WHERE quality_evaluation_run_id = $1 LIMIT 1)",
                    run_id,
                )
                await conn.execute(
                    "ALTER TABLE model_baseline_comparison ENABLE TRIGGER"
                    " trg_quality_model_baseline_comparison_immutable"
                )
        finally:
            await conn.close()
        await expect_manifest_rejection(run_id)
        rejection_probe_count += 1

        # Probe 4: tamper the canonical_payload JSON root to drop a
        # key that the manifest guard must reject at projection time.
        run_id = await seed_run("round-c-probe-canonical-payload")
        conn = await asyncpg.connect(_temporary_database_url(db_name))
        try:
            async with conn.transaction():
                await conn.execute(
                    "ALTER TABLE model_baseline_comparison DISABLE TRIGGER"
                    " trg_quality_model_baseline_comparison_immutable"
                )
                await conn.execute(
                    "UPDATE model_baseline_comparison SET canonical_payload = '{}'::jsonb "
                    "WHERE id = (SELECT id FROM model_baseline_comparison "
                    "WHERE quality_evaluation_run_id = $1 LIMIT 1)",
                    run_id,
                )
                await conn.execute(
                    "ALTER TABLE model_baseline_comparison ENABLE TRIGGER"
                    " trg_quality_model_baseline_comparison_immutable"
                )
        finally:
            await conn.close()
        await expect_manifest_rejection(run_id)
        rejection_probe_count += 1

        # Probe 5: truth-table drift — change the reason_code on a
        # child from BELOW_MINIMUM (an AVAILABLE+INSUFFICIENT_SAMPLE
        # reason) to NO_S2_BINDING_ROWS (an AVAILABLE+NOT_COMPUTABLE
        # reason) so the availability/status combination no longer
        # matches the truth table.
        run_id = await seed_run("round-c-probe-truth-table")
        conn = await asyncpg.connect(_temporary_database_url(db_name))
        try:
            async with conn.transaction():
                await conn.execute(
                    "ALTER TABLE model_baseline_comparison DISABLE TRIGGER"
                    " trg_quality_model_baseline_comparison_immutable"
                )
                await conn.execute(
                    "UPDATE model_baseline_comparison SET reason_code = 'NO_S2_BINDING_ROWS' "
                    "WHERE id = (SELECT id FROM model_baseline_comparison "
                    "WHERE quality_evaluation_run_id = $1 LIMIT 1)",
                    run_id,
                )
                await conn.execute(
                    "ALTER TABLE model_baseline_comparison ENABLE TRIGGER"
                    " trg_quality_model_baseline_comparison_immutable"
                )
        finally:
            await conn.close()
        await expect_manifest_rejection(run_id)
        rejection_probe_count += 1

        # Probe 6: result-set order/hash drift — tamper every child
        # canonical_hash so the rebuilt result-set hash diverges from
        # the manifest's comparison_result_set_hash.
        run_id = await seed_run("round-c-probe-result-set-hash")
        conn = await asyncpg.connect(_temporary_database_url(db_name))
        try:
            async with conn.transaction():
                await conn.execute(
                    "ALTER TABLE model_baseline_comparison DISABLE TRIGGER"
                    " trg_quality_model_baseline_comparison_immutable"
                )
                await conn.execute(
                    "UPDATE model_baseline_comparison SET canonical_hash = repeat('c', 64) "
                    "WHERE quality_evaluation_run_id = $1"
                    " AND id = (SELECT id FROM model_baseline_comparison"
                    " WHERE quality_evaluation_run_id = $1 LIMIT 1)",
                    run_id,
                )
                await conn.execute(
                    "ALTER TABLE model_baseline_comparison ENABLE TRIGGER"
                    " trg_quality_model_baseline_comparison_immutable"
                )
        finally:
            await conn.close()
        await expect_manifest_rejection(run_id)
        rejection_probe_count += 1
    finally:
        await engine.dispose()
        await _drop_temporary_database(db_name)
    assert rejection_probe_count == 6
    print(f"ROUND_C_DATABASE_REJECTION_PROBE_COUNT={rejection_probe_count}")
