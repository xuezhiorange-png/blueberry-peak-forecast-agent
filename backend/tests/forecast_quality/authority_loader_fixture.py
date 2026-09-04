"""Minimal sqlite fixtures for persisted forecast authority loader tests."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models.core_forecast import (
    CoreForecastCodeAuthorityModel,
    CoreForecastDailyRowModel,
    CoreForecastRunModel,
)
from backend.app.models.harvest_state import HarvestStateDailyMemberRowModel, HarvestStateRun
from backend.app.models.residual_model import (
    ResidualModelPredictionRow,
    ResidualModelPredictionRun,
    ResidualModelTrainingRun,
)
from backend.app.rolling_backtest.orchestration import _task9_member_identity_hash


def _fixture_hash(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


HASH_A = _fixture_hash("authority-fixture-a")
HASH_B = _fixture_hash("authority-fixture-b")
HASH_C = _fixture_hash("authority-fixture-c")
HASH_D = _fixture_hash("authority-fixture-d")
HASH_E = _fixture_hash("authority-fixture-e")
HASH_F = _fixture_hash("authority-fixture-f")
HASH_0 = _fixture_hash("authority-fixture-0")
HASH_1 = _fixture_hash("authority-fixture-1")
HASH_2 = _fixture_hash("authority-fixture-2")
HASH_3 = _fixture_hash("authority-fixture-3")
HASH_4 = _fixture_hash("authority-fixture-4")
HASH_5 = _fixture_hash("authority-fixture-5")
HASH_6 = _fixture_hash("authority-fixture-6")
HASH_7 = _fixture_hash("authority-fixture-7")
HASH_8 = _fixture_hash("authority-fixture-8")
HASH_9 = _fixture_hash("authority-fixture-9")
HASH_AA = _fixture_hash("authority-fixture-aa")
HASH_BB = _fixture_hash("authority-fixture-bb")
HASH_CC = _fixture_hash("authority-fixture-cc")
HASH_DD = _fixture_hash("authority-fixture-dd")
HASH_EE = _fixture_hash("authority-fixture-ee")
HASH_FF = _fixture_hash("authority-fixture-ff")

CUTOFF_AT = datetime(2026, 2, 28, 4, 0, tzinfo=UTC)
TASK8_RUN_ID = 401
TASK9_RUN_ID = 901
CORE_RUN_ID = 1001
CODE_AUTHORITY_ID = 501
FACTORY_ID = 701
FARM_ID = 101
SUBFARM_ID = 1101
VARIETY_ID = 2101
TRAINING_RUN_ID = 301
PREDICTION_RUN_ID = 302


def _core_daily_row(
    *,
    row_id: int,
    core_run_id: int,
    target_date: date,
    forecast_quantile: str,
    row_hash: str,
    farm_id: int = FARM_ID,
    subfarm_id: int = SUBFARM_ID,
    variety_id: int = VARIETY_ID,
) -> CoreForecastDailyRowModel:
    zero = Decimal("0")
    one = Decimal("1")
    return CoreForecastDailyRowModel(
        id=row_id,
        core_forecast_run_id=core_run_id,
        date=target_date,
        forecast_quantile=forecast_quantile,
        farm_id=farm_id,
        subfarm_id=subfarm_id,
        variety_id=variety_id,
        destination_factory_id=FACTORY_ID,
        natural_maturity_supply_kg=one,
        opening_mature_inventory_kg=zero,
        available_mature_quantity_kg=one,
        mature_inventory_loss_quantity_kg=zero,
        harvestable_mature_quantity_kg=one,
        effective_harvest_capacity_kg=one,
        model_harvested_marketable_quantity_kg=one,
        closing_mature_inventory_kg=zero,
        unharvested_backlog_kg=zero,
        sorting_retention_rate=one,
        postharvest_retention_rate=one,
        effective_marketable_quantity_kg=one,
        task8_forecast_run_id=TASK8_RUN_ID,
        task9_harvest_state_run_id=TASK9_RUN_ID,
        task8_artifact_hash=HASH_BB,
        task9_result_hash=HASH_C,
        marketable_policy_version="policy-v1",
        marketable_policy_hash=HASH_CC,
        row_hash=row_hash,
    )


def _task9_member(
    *,
    member_id: int,
    target_date: date,
    forecast_quantile: str,
    farm_id: int = FARM_ID,
    subfarm_id: int = SUBFARM_ID,
    variety_id: int = VARIETY_ID,
) -> HarvestStateDailyMemberRowModel:
    zero = Decimal("0")
    one = Decimal("1")
    return HarvestStateDailyMemberRowModel(
        id=member_id,
        harvest_state_run_id=TASK9_RUN_ID,
        state_date=target_date,
        forecast_quantile=forecast_quantile,
        capacity_pool_id=f"pool-{member_id}",
        capacity_pool_grain="SUBFARM_VARIETY",
        capacity_pool_membership_hash=HASH_D,
        farm_id=farm_id,
        subfarm_id=subfarm_id,
        subfarm_identity_key=str(subfarm_id),
        variety_id=variety_id,
        destination_factory_id=FACTORY_ID,
        opening_mature_inventory_kg=zero,
        natural_maturity_supply_kg=one,
        available_mature_quantity_kg=one,
        mature_inventory_loss_quantity_kg=zero,
        harvestable_mature_quantity_kg=one,
        allocated_harvest_capacity_kg=one,
        harvested_quantity_kg=one,
        closing_mature_inventory_kg=zero,
        unharvested_backlog_kg=zero,
        arrival_quantity_kg=one,
        opening_cohort_count=0,
        closing_cohort_count=0,
        cohort_source_ref_hashes=[],
    )


def _prediction_row(
    *,
    row_id: int,
    prediction_run_id: int,
    target_date: date,
    horizon_days: int,
    row_hash: str,
) -> ResidualModelPredictionRow:
    zero = Decimal("0")
    one = Decimal("1")
    return ResidualModelPredictionRow(
        id=row_id,
        prediction_run_id=prediction_run_id,
        model_run_id=TRAINING_RUN_ID,
        task9_run_id=TASK9_RUN_ID,
        task9_result_hash=HASH_C,
        destination_factory_id=FACTORY_ID,
        arrival_local_date=target_date,
        forecast_horizon_days=horizon_days,
        structural_p50_kg=one,
        structural_p80_kg=one,
        structural_p90_kg=one,
        raw_residual_p50_kg=zero,
        raw_residual_p80_kg=zero,
        raw_residual_p90_kg=zero,
        corrected_raw_p50_kg=one,
        corrected_raw_p80_kg=one,
        corrected_raw_p90_kg=one,
        corrected_p50_kg=one,
        corrected_p80_kg=one,
        corrected_p90_kg=one,
        nonnegative_projection_applied=False,
        quantile_projection_applied=False,
        projection_reasons=[],
        feature_vector_hash=HASH_E,
        feature_audit_hash=HASH_F,
        prediction_row_hash=row_hash,
        mode="structural_only",
        fallback_reason="fixture",
    )


def seed_canonical_authority_fixture(session: Session) -> dict[str, object]:
    """Seed one canonical authority chain with two core rows and two quantiles."""
    code_authority = CoreForecastCodeAuthorityModel(
        id=CODE_AUTHORITY_ID,
        authority_schema_version="v0.1-core-forecast-code-authority-v1",
        source_commit_sha="a" * 40,
        engine_code_hash=HASH_0,
        build_artifact_hash=HASH_1,
        config_bundle_hash=HASH_2,
        available_at=CUTOFF_AT,
        canonical_payload={"schema_version": "v0.1-core-forecast-code-authority-v1"},
        authority_hash=HASH_3,
    )
    task9_run = HarvestStateRun(
        id=TASK9_RUN_ID,
        status="completed",
        output_schema_version="task9-output-v1",
        result_hash_schema_version="task9a-result-hash-v2",
        resolved_parameter_snapshot_schema_version="task9-params-v1",
        source_ref_schema_version="task9-source-ref-v1",
        stable_cohort_key_schema_version="task9-cohort-v1",
        input_snapshot={},
        resolved_parameter_snapshot={},
        source_ref_catalog=[],
        warnings=[],
        blockers=[],
        mass_balance_result={},
        continuity_result={},
        canonical_output={},
        config_hash=HASH_4,
        result_hash=HASH_C,
        canonical_payload_hash=HASH_5,
        forecast_start_date=date(2026, 1, 1),
        forecast_end_date=date(2026, 4, 30),
        as_of_date=date(2026, 1, 1),
        destination_factory_id=FACTORY_ID,
        forecast_season_id=1,
        pool_row_count=1,
        member_row_count=1,
        cohort_row_count=0,
        future_arrival_row_count=0,
        forecast_effective_cutoff_at=CUTOFF_AT,
    )
    core_run = CoreForecastRunModel(
        id=CORE_RUN_ID,
        status="completed",
        run_schema_version="v0.1-core-forecast-run-authority-v2",
        request_schema_version="v0.1-core-forecast-request-authority-v2",
        date_basis="HARVEST_BUSINESS_DATE",
        forecast_input_hash=HASH_6,
        request_hash=HASH_7,
        result_hash=HASH_A,
        retention_policy_snapshot_hash=HASH_8,
        curve_hash=HASH_9,
        metrics_hash=HASH_AA,
        code_authority_id=CODE_AUTHORITY_ID,
        code_authority_hash=HASH_3,
        code_authority_available_at=CUTOFF_AT,
        forecast_effective_cutoff_at=CUTOFF_AT,
        request_snapshot={},
        forecast_season_id=1,
        forecast_season_code="2025~2026",
        forecast_start_date=date(2026, 1, 1),
        forecast_end_date=date(2026, 4, 30),
        destination_factory_id=FACTORY_ID,
        task8_forecast_run_id=TASK8_RUN_ID,
        task8_artifact_hash=HASH_BB,
        task9_harvest_state_run_id=TASK9_RUN_ID,
        task9_result_hash=HASH_C,
        daily_row_count=3,
        metric_row_count=3,
        completed_at=CUTOFF_AT,
    )
    date_a = date(2026, 3, 7)
    date_b = date(2026, 3, 14)
    core_row_p50_a = _core_daily_row(
        row_id=2001,
        core_run_id=CORE_RUN_ID,
        target_date=date_a,
        forecast_quantile="P50",
        row_hash=HASH_B,
    )
    core_row_p80_a = _core_daily_row(
        row_id=2002,
        core_run_id=CORE_RUN_ID,
        target_date=date_a,
        forecast_quantile="P80",
        row_hash=HASH_DD,
    )
    core_row_p50_b = _core_daily_row(
        row_id=2003,
        core_run_id=CORE_RUN_ID,
        target_date=date_b,
        forecast_quantile="P50",
        row_hash=HASH_EE,
    )
    member_p50_a = _task9_member(member_id=3001, target_date=date_a, forecast_quantile="P50")
    member_p80_a = _task9_member(member_id=3002, target_date=date_a, forecast_quantile="P80")
    member_p50_b = _task9_member(member_id=3003, target_date=date_b, forecast_quantile="P50")
    training_run = ResidualModelTrainingRun(
        id=TRAINING_RUN_ID,
        execution_status="completed",
        eligibility_status="not_evaluated",
        model_family="histgb",
        model_version="v1",
        feature_schema_version="task10-features-v1",
        feature_schema_hash=HASH_FF,
        artifact_schema_version="task10-artifact-v1",
        training_signature=HASH_0,
        config_hash=HASH_1,
        config_snapshot={},
        manifest_hash=HASH_2,
        manifest_snapshot={},
        feature_audit_summary={},
        category_encoding_snapshot=[],
        training_metrics={},
        validation_metrics={},
        eligibility_reasons=[],
        warnings=[],
        blockers=[],
        input_snapshot={},
        canonical_output={},
        canonical_payload_hash=HASH_3,
        sample_count=1,
        distinct_season_count=1,
        distinct_factory_count=1,
        distinct_grain_count=1,
        manifest_row_count=1,
        expected_artifact_count=0,
        python_version="3.12.0",
        numpy_version="1.26.0",
        sklearn_version="1.4.0",
        finished_at=CUTOFF_AT,
    )
    prediction_run = ResidualModelPredictionRun(
        id=PREDICTION_RUN_ID,
        training_run_id=TRAINING_RUN_ID,
        task9_run_id=TASK9_RUN_ID,
        task9_result_hash=HASH_C,
        prediction_target_kind="LEGACY_RESIDUAL_CORRECTION",
        execution_status="completed",
        mode="structural_only",
        config_hash=HASH_1,
        feature_schema_version="task10-features-v1",
        feature_schema_hash=HASH_FF,
        artifact_hashes=[],
        prediction_input_signature=HASH_4,
        prediction_hash=HASH_D,
        feature_audit={},
        warnings=[],
        blockers=[],
        fallback_reason="fixture-structural-only",
        expected_prediction_row_count=2,
        input_snapshot={"training_signature": HASH_0},
        canonical_output={},
        canonical_payload_hash=HASH_5,
        completed_at=CUTOFF_AT,
    )
    pred_row_h7_a = _prediction_row(
        row_id=4001,
        prediction_run_id=PREDICTION_RUN_ID,
        target_date=date_a,
        horizon_days=7,
        row_hash=HASH_6,
    )
    pred_row_h14_b = _prediction_row(
        row_id=4002,
        prediction_run_id=PREDICTION_RUN_ID,
        target_date=date_b,
        horizon_days=14,
        row_hash=HASH_7,
    )
    session.add_all(
        [
            code_authority,
            task9_run,
            core_run,
            core_row_p50_a,
            core_row_p80_a,
            core_row_p50_b,
            member_p50_a,
            member_p80_a,
            member_p50_b,
            training_run,
            prediction_run,
            pred_row_h7_a,
            pred_row_h14_b,
        ]
    )
    session.commit()
    return {
        "core_row_p50_a": core_row_p50_a,
        "core_row_p80_a": core_row_p80_a,
        "core_row_p50_b": core_row_p50_b,
        "member_p50_a": member_p50_a,
        "member_p80_a": member_p80_a,
        "member_p50_b": member_p50_b,
        "pred_row_h7_a": pred_row_h7_a,
        "pred_row_h14_b": pred_row_h14_b,
    }


@pytest.fixture
def authority_loader_session() -> Iterator[Session]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.close()

    tables = [
        CoreForecastCodeAuthorityModel.__table__,
        CoreForecastRunModel.__table__,
        CoreForecastDailyRowModel.__table__,
        HarvestStateRun.__table__,
        HarvestStateDailyMemberRowModel.__table__,
        ResidualModelTrainingRun.__table__,
        ResidualModelPredictionRun.__table__,
        ResidualModelPredictionRow.__table__,
    ]
    for table in tables:
        table.create(engine, checkfirst=True)

    maker = sessionmaker(bind=engine, expire_on_commit=False)
    with maker() as session:
        yield session
    engine.dispose()


def build_canonical_bundle_for_binding(
    fixture: dict[str, object],
    *,
    core_row: CoreForecastDailyRowModel,
    member: HarvestStateDailyMemberRowModel,
    prediction_row: ResidualModelPredictionRow,
) -> dict[str, str]:
    """Mirror trial/orchestration identity fields for equivalence checks."""
    return {
        "daily_row_identity_hash": core_row.row_hash,
        "task9_member_identity_hash": _task9_member_identity_hash(member),
        "task10_prediction_row_identity_hash": prediction_row.prediction_row_hash,
    }
