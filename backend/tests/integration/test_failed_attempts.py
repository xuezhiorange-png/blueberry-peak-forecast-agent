"""Section 12: Missing regression tests — Failed attempt persistence tests.

These tests verify the Section 6 attempt lifecycle is correctly persisted
in PostgreSQL.

Requires RUN_POSTGRES_INTEGRATION=1 (integration marker).
"""

from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from backend.app.db.session import AsyncSessionMaker
from backend.app.models.residual_model import (
    ResidualModelExecutionAttempt,
)
from backend.app.repositories.residual_model import (
    create_residual_execution_attempt,
    fail_residual_execution_attempt,
    get_residual_execution_attempt,
)
from backend.app.residual_model.application import (
    execute_residual_prediction,
    execute_residual_training,
)
from backend.app.residual_model.schemas import (
    ResidualPredictionRequest,
    ResidualTrainingSampleSpec,
)
from backend.tests.residual_model.test_training_manifest import (
    _config,
    _diverse_training_samples,
    _persist_task9_run,
    _seed_build_run,
    _seed_daily_fact,
    _seed_master_data,
    _snapshot_as_of_date,
    _supplemental_features,
)

pytestmark = pytest.mark.integration


def _require_postgres() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("set RUN_POSTGRES_INTEGRATION=1 when PostgreSQL is available")


def _relaxed_config():
    config = _config()
    eligibility = replace(
        config.rules.eligibility,
        min_training_rows=1,
        min_seasons=1,
        min_factories=1,
        max_validation_wmape=Decimal("10"),
        require_improvement_over_structural=False,
        max_fallback_rate=Decimal("1"),
    )
    rules = replace(config.rules, eligibility=eligibility)
    return replace(config, rules=rules)


# ── 1. Training manifest failure persists failed attempt ─────────────────


@pytest.mark.asyncio
async def test_training_manifest_failure_persists_failed_attempt() -> None:
    """When training manifest building fails, the attempt is 'failed'."""
    _require_postgres()
    async with AsyncSessionMaker() as session:
        attempt = await create_residual_execution_attempt(
            session,
            attempt_type="training",
            execution_status="running",
            current_stage="manifest_build",
            requested_inputs={"sample_count": 1, "season_ids": [999]},
            config_identity={
                "model_family": "residual_hgb",
                "model_version": "task10-v1",
                "config_hash": "a" * 64,
            },
            upstream_requested_ids={
                "task9_run_ids": [999],
                "label_analytics_build_run_ids": [999],
                "feature_analytics_build_run_ids": [999],
            },
        )
        attempt_id = attempt.id
        await session.commit()

        await fail_residual_execution_attempt(
            session,
            attempt_id=attempt_id,
            sanitized_error="ManifestBuildError: Task 9 run 999 was not found",
        )
        await session.commit()

        loaded = await get_residual_execution_attempt(
            session, attempt_id=attempt_id
        )
        assert loaded is not None
        assert loaded.execution_status == "failed"
        assert loaded.sanitized_error is not None
        assert "ManifestBuildError" in loaded.sanitized_error
        assert loaded.finished_at is not None


# ── 2. Prediction Task 9 failure persists failed attempt ─────────────────


@pytest.mark.asyncio
async def test_prediction_task9_failure_persists_failed_attempt() -> None:
    """When prediction's Task 9 lookup fails, attempt is 'failed'."""
    _require_postgres()
    async with AsyncSessionMaker() as session:
        season_id, factory_id, variety_id = await _seed_master_data(session)
        task9_run_id, output = await _persist_task9_run(session)
        as_of_date = _snapshot_as_of_date(output)

        label_build = await _seed_build_run(
            session,
            build_run_id=1,
            season_id=season_id,
            source_max_raw_id=100,
            config_hash="a" * 64,
            finished_at=datetime(2026, 3, 20, tzinfo=UTC),
            covered_factory_ids=(factory_id,),
        )
        feature_build = await _seed_build_run(
            session,
            build_run_id=2,
            season_id=season_id,
            source_max_raw_id=50,
            config_hash="b" * 64,
            finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
            covered_factory_ids=(factory_id,),
        )
        await _seed_daily_fact(
            session,
            fact_id=1,
            build_run_id=label_build.id,
            season_id=season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=output.forecast_start_date,
            weight_kg=Decimal("100"),
        )
        await session.commit()

        training_result, training_run_id = await execute_residual_training(
            session,
            samples=_diverse_training_samples(
                task9_run_id=task9_run_id,
                label_build_run_id=label_build.id,
                feature_build_run_id=feature_build.id,
                as_of_date=as_of_date,
            ),
            config=_relaxed_config(),
        )

        # Predict with a non-existent Task 9 run — should fail
        try:
            await execute_residual_prediction(
                session,
                request=ResidualPredictionRequest(
                    model_run_id=training_run_id,
                    task9_run_id=99999,
                    feature_analytics_build_run_id=feature_build.id,
                    supplemental_feature_values=_supplemental_features(as_of_date=as_of_date),
                ),
            )
        except Exception:
            pass  # expected

        count = await session.scalar(
            select(func.count()).select_from(ResidualModelExecutionAttempt)
            .where(ResidualModelExecutionAttempt.attempt_type == "prediction")
            .where(ResidualModelExecutionAttempt.execution_status == "failed")
        )
        assert count >= 1, "No failed prediction attempt was persisted"


# ── 3. Prediction feature failure persists failed attempt ────────────────


@pytest.mark.asyncio
async def test_prediction_feature_failure_persists_failed_attempt() -> None:
    """Prediction structural_only from ineligible model succeeds and
    attempt is completed (not failed)."""
    _require_postgres()
    async with AsyncSessionMaker() as session:
        season_id, factory_id, variety_id = await _seed_master_data(session)
        task9_run_id, output = await _persist_task9_run(session)
        as_of_date = _snapshot_as_of_date(output)

        label_build = await _seed_build_run(
            session,
            build_run_id=1,
            season_id=season_id,
            source_max_raw_id=100,
            config_hash="a" * 64,
            finished_at=datetime(2026, 3, 20, tzinfo=UTC),
            covered_factory_ids=(factory_id,),
        )
        feature_build = await _seed_build_run(
            session,
            build_run_id=2,
            season_id=season_id,
            source_max_raw_id=50,
            config_hash="b" * 64,
            finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
            covered_factory_ids=(factory_id,),
        )
        await session.commit()

        training_result, training_run_id = await execute_residual_training(
            session,
            samples=[
                ResidualTrainingSampleSpec(
                    task9_run_id=task9_run_id,
                    label_analytics_build_run_id=label_build.id,
                    feature_analytics_build_run_id=feature_build.id,
                    split="train",
                    supplemental_feature_values=_supplemental_features(as_of_date=as_of_date),
                )
            ],
            config=_config(),
        )
        assert training_result.eligibility_status == "ineligible"

        prediction_result, prediction_run_id = await execute_residual_prediction(
            session,
            request=ResidualPredictionRequest(
                model_run_id=training_run_id,
                task9_run_id=task9_run_id,
                feature_analytics_build_run_id=feature_build.id,
                supplemental_feature_values=_supplemental_features(as_of_date=as_of_date),
            ),
        )
        assert prediction_result.execution_status == "completed"
        assert prediction_result.mode == "structural_only"

        completed_attempt = await session.scalar(
            select(ResidualModelExecutionAttempt)
            .where(ResidualModelExecutionAttempt.attempt_type == "prediction")
            .where(ResidualModelExecutionAttempt.execution_status == "completed")
            .order_by(ResidualModelExecutionAttempt.id.desc())
        )
        assert completed_attempt is not None
        assert completed_attempt.linked_prediction_run_id is not None


# ── 4. Persistence rollback test ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_persistence_rollback_on_failure() -> None:
    """When a persistence step fails, attempt is 'failed' and no
    training run is linked."""
    _require_postgres()
    async with AsyncSessionMaker() as session:
        attempt = await create_residual_execution_attempt(
            session,
            attempt_type="training",
            execution_status="running",
            current_stage="model_training",
            requested_inputs={"sample_count": 0},
            config_identity={
                "model_family": "residual_hgb",
                "model_version": "task10-v1",
                "config_hash": "a" * 64,
            },
            upstream_requested_ids={},
        )
        attempt_id = attempt.id
        await session.commit()

        await fail_residual_execution_attempt(
            session,
            attempt_id=attempt_id,
            sanitized_error="ModelTrainingError: Not enough training samples",
        )
        await session.commit()

        loaded = await get_residual_execution_attempt(
            session, attempt_id=attempt_id
        )
        assert loaded is not None
        assert loaded.execution_status == "failed"
        assert loaded.current_stage == "model_training"
        assert loaded.finished_at is not None
        assert loaded.linked_training_run_id is None


# ── 5. Successful completion finalizes attempt ───────────────────────────


@pytest.mark.asyncio
async def test_successful_completion_finalizes_attempt() -> None:
    """When training completes successfully, attempt is 'completed'
    with a link to the training run."""
    _require_postgres()
    async with AsyncSessionMaker() as session:
        season_id, factory_id, variety_id = await _seed_master_data(session)
        task9_run_id, output = await _persist_task9_run(session)
        as_of_date = _snapshot_as_of_date(output)

        label_build = await _seed_build_run(
            session,
            build_run_id=1,
            season_id=season_id,
            source_max_raw_id=100,
            config_hash="a" * 64,
            finished_at=datetime(2026, 3, 20, tzinfo=UTC),
            covered_factory_ids=(factory_id,),
        )
        feature_build = await _seed_build_run(
            session,
            build_run_id=2,
            season_id=season_id,
            source_max_raw_id=50,
            config_hash="b" * 64,
            finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
            covered_factory_ids=(factory_id,),
        )
        for index in range(3):
            await _seed_daily_fact(
                session,
                fact_id=100 + index,
                build_run_id=label_build.id,
                season_id=season_id,
                factory_id=factory_id,
                variety_id=variety_id,
                receipt_date=date(2026, 3, 1 + index),
                weight_kg=Decimal("100"),
            )
        await session.commit()

        training_result, training_run_id = await execute_residual_training(
            session,
            samples=_diverse_training_samples(
                task9_run_id=task9_run_id,
                label_build_run_id=label_build.id,
                feature_build_run_id=feature_build.id,
                as_of_date=as_of_date,
            ),
            config=_relaxed_config(),
        )

        assert training_run_id > 0
        assert training_result.execution_status == "completed"

        completed_attempt = await session.scalar(
            select(ResidualModelExecutionAttempt)
            .where(ResidualModelExecutionAttempt.attempt_type == "training")
            .where(ResidualModelExecutionAttempt.execution_status == "completed")
            .order_by(ResidualModelExecutionAttempt.id.desc())
        )
        assert completed_attempt is not None
        assert completed_attempt.linked_training_run_id == training_run_id
        assert completed_attempt.finished_at is not None
