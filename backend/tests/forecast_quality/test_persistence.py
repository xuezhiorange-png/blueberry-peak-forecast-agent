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
                    reason_code="COMPUTED",
                    breakdown_identity={},
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
        "reason_code": "COMPUTED",
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
                "COMPUTED",
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
