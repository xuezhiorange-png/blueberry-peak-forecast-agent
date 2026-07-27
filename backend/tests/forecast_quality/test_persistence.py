"""PostgreSQL acceptance for Round B forecast-quality persistence."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import AsyncSessionMaker
from backend.app.forecast_quality.baseline import resolve_baseline_point_forecast
from backend.app.forecast_quality.breakdown import calculate_breakdown_cells
from backend.app.forecast_quality.calculator_daily import compute_daily_metrics
from backend.app.forecast_quality.canonical import canonical_json_bytes
from backend.app.forecast_quality.enums import FrozenVersion, SupportedQuantile
from backend.app.forecast_quality.persistence import (
    BaselinePersistenceRecord,
    ForecastQualityContractError,
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


def _suffix_key(suffix: str, prefix: str) -> str:
    return f"{prefix}:{suffix}"


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
    manifest_payload: dict[str, object] | None = None,
) -> PersistedQualityEvaluation:
    return await session.run_sync(
        lambda sync_session: persist_quality_evaluation(
            sync_session,
            evaluation_input=evaluation_input,
            metric_results=(metric_result,),
            breakdown_results=breakdown_results,
            baseline_records=(baseline_record,),
            comparison_records=(),
            manifest_payload=manifest_payload or {},
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
        manifest_payload, manifest_hash, completed_at, sealed_at
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, now(), now())
"""


def _probe_hash(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


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
) -> tuple[object, ...]:
    return (
        run_id,
        _PROBE_SCHEMA,
        _probe_hash(f"manifest-request:{suffix}"),
        _probe_hash(f"manifest-instance:{suffix}"),
        _probe_hash(f"manifest-metric-set:{suffix}"),
        _probe_hash(f"manifest-breakdown-set:{suffix}"),
        _probe_hash(f"manifest-baseline-set:{suffix}"),
        _probe_hash(f"manifest-comparison-set:{suffix}"),
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
    env = _live_env()
    url = (
        f"postgresql://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}"
        f"@{env['POSTGRES_HOST']}:{env['POSTGRES_PORT']}/{env['ISOLATED_DB_NAME']}"
    )
    conn = await asyncpg.connect(url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == (
            "0024_s3_forecast_quality_persistence"
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
            await conn.fetchval("SELECT count(*) FROM pg_trigger WHERE tgname LIKE 'trg_quality_%'")
            >= 10
        )
    finally:
        await conn.close()
    await asyncio.to_thread(
        command.downgrade,
        _alembic_config(),
        "0023_historical_backtest_binding",
    )
    await asyncio.to_thread(command.upgrade, _alembic_config(), "head")
    conn = await asyncpg.connect(url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == (
            "0024_s3_forecast_quality_persistence"
        )
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_complete_write_has_six_table_shape_and_empty_comparison() -> None:
    _live_env()
    input_data, metric_result, breakdowns, baseline = _fixture("complete")
    async with AsyncSessionMaker() as session:
        async with session.begin():
            persisted = await _persist(
                session,
                evaluation_input=input_data,
                metric_result=metric_result,
                breakdown_results=breakdowns,
                baseline_record=baseline,
            )
            assert persisted.new_write_count == 11
            assert persisted.replayed is False
            assert await session.scalar(select(func.count(QualityEvaluationRunModel.id))) == 1
            assert await session.scalar(select(func.count(QualityMetricResultModel.id))) == 7
            assert await session.scalar(select(func.count(QualityBreakdownResultModel.id))) == 1
            assert await session.scalar(select(func.count(NaiveBaselineRunModel.id))) == 1
            assert await session.scalar(select(func.count(ModelBaselineComparisonModel.id))) == 0
            assert await session.scalar(select(func.count(QualityEvaluationManifestModel.id))) == 1


@pytest.mark.asyncio
async def test_persistence_one_third_coverage_is_quantized_to_six_places() -> None:
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
    async with AsyncSessionMaker() as session:
        async with session.begin():
            persisted = await _persist(
                session,
                evaluation_input=input_data,
                metric_result=metric_result,
                breakdown_results=[breakdown],
                baseline_record=baseline,
            )
            stored = await session.scalar(
                select(QualityBreakdownResultModel.coverage_ratio).where(
                    QualityBreakdownResultModel.quality_evaluation_run_id == persisted.run_id
                )
            )
            assert stored == Decimal("0.333333")
    print("PERSISTENCE_ONE_THIRD_RESULT=PASS")


@pytest.mark.asyncio
async def test_persistence_half_even_tie_coverage_is_quantized() -> None:
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
    async with AsyncSessionMaker() as session:
        async with session.begin():
            persisted = await _persist(
                session,
                evaluation_input=input_data,
                metric_result=metric_result,
                breakdown_results=[breakdown],
                baseline_record=baseline,
            )
            stored = await session.scalar(
                select(QualityBreakdownResultModel.coverage_ratio).where(
                    QualityBreakdownResultModel.quality_evaluation_run_id == persisted.run_id
                )
            )
            assert stored == Decimal("0.007812")
    print("PERSISTENCE_HALF_EVEN_TIE_RESULT=PASS")


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
    _live_env()
    input_data, metric_result, breakdowns, baseline = _fixture("immutability")
    async with AsyncSessionMaker() as session:
        async with session.begin():
            persisted = await _persist(
                session,
                evaluation_input=input_data,
                metric_result=metric_result,
                breakdown_results=breakdowns,
                baseline_record=baseline,
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


@pytest.mark.asyncio
async def test_nonempty_comparison_fails_before_database_write() -> None:
    _live_env()
    input_data, metric_result, breakdowns, baseline = _fixture("comparison")
    request_hash = _validate_evaluation_input(input_data)[1]
    async with AsyncSessionMaker() as session:
        with pytest.raises(Exception, match="NONEMPTY_COMPARISON_RECORDS_FAIL_CLOSED"):
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
        assert "fk_model_baseline_comparison_baseline" in constraints
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
            "uq_model_baseline_comparison_canonical_hash",
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
    env = _live_env()
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
    url = (
        f"postgresql://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}"
        f"@{env['POSTGRES_HOST']}:{env['POSTGRES_PORT']}/{env['ISOLATED_DB_NAME']}"
    )
    conn = await asyncpg.connect(url)
    try:
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
    env = _live_env()
    url = (
        f"postgresql://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}"
        f"@{env['POSTGRES_HOST']}:{env['POSTGRES_PORT']}/{env['ISOLATED_DB_NAME']}"
    )
    conn = await asyncpg.connect(url)
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
        await conn.execute(
            _MANIFEST_INSERT_SQL,
            *_probe_manifest_args(run1, "seed", manifest_hash=manifest_hash),
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
