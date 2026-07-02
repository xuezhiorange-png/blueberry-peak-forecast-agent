from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text

from backend.app.db.session import AsyncSessionMaker
from backend.app.models.residual_model import (
    ResidualModelArtifact,
    ResidualModelExecutionAttempt,
    ResidualModelManifestRow,
    ResidualModelPredictionRow,
    ResidualModelPredictionRun,
    ResidualModelTrainingRun,
)
from backend.app.residual_model.application import (
    ResidualPredictionApplicationIntegrityError,
    ResidualTrainingApplicationIntegrityError,
    execute_residual_prediction,
    execute_residual_training,
)
from backend.app.residual_model.persistence import (
    load_residual_prediction_run_by_id,
    load_residual_training_run_by_id,
    training_result_json_payload,
)
from backend.app.residual_model.schemas import (
    ResidualPredictionRequest,
    ResidualTrainingSampleSpec,
)
from backend.tests.harvest_state.conftest import make_request
from backend.tests.residual_model.test_training_manifest import (
    _config,
    _diverse_training_samples,
    _persist_task9_run,
    _seed_build_run,
    _seed_daily_fact,
    _seed_master_data,
    _seed_season,
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
    )
    rules = replace(config.rules, eligibility=eligibility)
    return replace(config, rules=rules)


async def _seed_prediction_fixture() -> dict[str, int]:
    async with AsyncSessionMaker() as session:
        season_id, factory_id, variety_id = await _seed_master_data(session)
        validation_season_id = await _seed_season(
            session,
            season_id=2,
            code="2026-2027",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
        )
        task9_run_id, output = await _persist_task9_run(session)
        validation_payload = make_request()
        validation_payload["initial_inventory_cohorts"][0]["remaining_quantity_kg"] = Decimal("6")
        validation_payload["initial_opening_mature_inventory_kg"] = Decimal("31")
        validation_task9_run_id, _validation_output = await _persist_task9_run(
            session,
            payload=validation_payload,
        )
        as_of_date = _snapshot_as_of_date(output)
        label_build = await _seed_build_run(
            session,
            build_run_id=1,
            season_id=season_id,
            source_max_raw_id=100,
            config_hash="a" * 64,
            finished_at=datetime(2026, 3, 20, tzinfo=UTC),
            covered_factory_ids=(factory_id,),
            analysis_start_date=date(2026, 1, 1),
            analysis_end_date=date(2026, 3, 20),
        )
        feature_build = await _seed_build_run(
            session,
            build_run_id=2,
            season_id=season_id,
            source_max_raw_id=50,
            config_hash="b" * 64,
            finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
            covered_factory_ids=(factory_id,),
            analysis_start_date=date(2026, 1, 1),
            analysis_end_date=date(2026, 2, 27),
        )
        for index, target_date in enumerate((date(2026, 3, 1), date(2026, 3, 2), date(2026, 3, 3))):
            await _seed_daily_fact(
                session,
                fact_id=100 + index,
                build_run_id=label_build.id,
                season_id=season_id,
                factory_id=factory_id,
                variety_id=variety_id,
                receipt_date=target_date,
                weight_kg=Decimal("100") + Decimal(index),
            )
        for offset, weight in ((1, Decimal("11")), (3, Decimal("13")), (7, Decimal("17"))):
            await _seed_daily_fact(
                session,
                fact_id=200 + offset,
                build_run_id=feature_build.id,
                season_id=season_id,
                factory_id=factory_id,
                variety_id=variety_id,
                receipt_date=as_of_date - timedelta(days=offset),
                weight_kg=weight,
            )
        validation_label_build = await _seed_build_run(
            session,
            build_run_id=101,
            season_id=validation_season_id,
            source_max_raw_id=200,
            config_hash="c" * 64,
            finished_at=datetime(2026, 3, 20, tzinfo=UTC),
            covered_factory_ids=(factory_id,),
        )
        validation_feature_build = await _seed_build_run(
            session,
            build_run_id=102,
            season_id=validation_season_id,
            source_max_raw_id=150,
            config_hash="d" * 64,
            finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
            covered_factory_ids=(factory_id,),
        )
        for index, target_date in enumerate((date(2026, 3, 1), date(2026, 3, 2), date(2026, 3, 3))):
            await _seed_daily_fact(
                session,
                fact_id=300 + index,
                build_run_id=validation_label_build.id,
                season_id=validation_season_id,
                factory_id=factory_id,
                variety_id=variety_id,
                receipt_date=target_date,
                weight_kg=Decimal("120") + Decimal(index),
            )
        for offset, weight in ((1, Decimal("21")), (3, Decimal("23")), (7, Decimal("27"))):
            await _seed_daily_fact(
                session,
                fact_id=400 + offset,
                build_run_id=validation_feature_build.id,
                season_id=validation_season_id,
                factory_id=factory_id,
                variety_id=variety_id,
                receipt_date=as_of_date - timedelta(days=offset),
                weight_kg=weight,
            )
        await session.commit()
        return {
            "train_task9_run_id": task9_run_id,
            "validation_task9_run_id": validation_task9_run_id,
            "train_label_build_run_id": label_build.id,
            "train_feature_build_run_id": feature_build.id,
            "validation_label_build_run_id": validation_label_build.id,
            "validation_feature_build_run_id": validation_feature_build.id,
            "season_id": season_id,
            "validation_season_id": validation_season_id,
            "factory_id": factory_id,
        }


@pytest.mark.integration
async def test_residual_model_tables_exist_after_migration_upgrade() -> None:
    _require_postgres()
    async with AsyncSessionMaker() as session:
        for table_name in (
            "residual_model_training_run",
            "residual_model_manifest_row",
            "residual_model_artifact",
            "residual_model_prediction_run",
            "residual_model_prediction_row",
            "residual_model_execution_attempt",
        ):
            exists = await session.scalar(select(func.to_regclass(table_name)))
            assert exists == table_name


@pytest.mark.integration
async def test_postgres_execute_residual_training_completed_eligible_round_trip() -> None:
    _require_postgres()
    fixture = await _seed_prediction_fixture()

    samples = _diverse_training_samples(
        task9_run_id=fixture["train_task9_run_id"],
        label_build_run_id=fixture["train_label_build_run_id"],
        feature_build_run_id=fixture["train_feature_build_run_id"],
        validation_task9_run_id=fixture["validation_task9_run_id"],
        validation_label_build_run_id=fixture["validation_label_build_run_id"],
        validation_feature_build_run_id=fixture["validation_feature_build_run_id"],
        as_of_date=date(2026, 2, 28),
    )

    async with AsyncSessionMaker() as session:
        training_result, training_run_id = await execute_residual_training(
            session,
            samples=samples,
            config=_relaxed_config(),
        )
        loaded = await load_residual_training_run_by_id(session, run_id=training_run_id)

        assert training_result.blockers == ()
        assert training_result.input_snapshot["manifest_summary"]["included_row_count"] > 0
        assert training_result.execution_status == "completed"
        assert training_result.eligibility_status == "eligible"
        assert loaded is not None
        assert training_result_json_payload(loaded) == training_result_json_payload(training_result)
        assert {item.quantile_label: item.artifact_bytes for item in loaded.artifacts} == {
            item.quantile_label: item.artifact_bytes for item in training_result.artifacts
        }
        assert await session.scalar(select(func.count()).select_from(ResidualModelTrainingRun)) == 1
        expected_manifest_row_count = int(
            training_result.input_snapshot["manifest_summary"]["row_count"]
        )
        assert (
            await session.scalar(select(func.count()).select_from(ResidualModelManifestRow))
            == expected_manifest_row_count
        )
        assert training_result.input_snapshot["manifest_summary"]["included_row_count"] > 0
        assert await session.scalar(select(func.count()).select_from(ResidualModelArtifact)) == 3


@pytest.mark.integration
async def test_postgres_execute_residual_training_same_signature_is_idempotent() -> None:
    _require_postgres()
    fixture = await _seed_prediction_fixture()
    samples = _diverse_training_samples(
        task9_run_id=fixture["train_task9_run_id"],
        label_build_run_id=fixture["train_label_build_run_id"],
        feature_build_run_id=fixture["train_feature_build_run_id"],
        validation_task9_run_id=fixture["validation_task9_run_id"],
        validation_label_build_run_id=fixture["validation_label_build_run_id"],
        validation_feature_build_run_id=fixture["validation_feature_build_run_id"],
        as_of_date=date(2026, 2, 28),
    )

    async with AsyncSessionMaker() as session:
        first_result, first_run_id = await execute_residual_training(
            session,
            samples=samples,
            config=_relaxed_config(),
        )
        second_result, second_run_id = await execute_residual_training(
            session,
            samples=samples,
            config=_relaxed_config(),
        )

        assert first_run_id == second_run_id
        assert first_result.training_signature == second_result.training_signature
        assert await session.scalar(select(func.count()).select_from(ResidualModelTrainingRun)) == 1
        expected_manifest_row_count = int(
            first_result.input_snapshot["manifest_summary"]["row_count"]
        )
        assert (
            await session.scalar(select(func.count()).select_from(ResidualModelManifestRow))
            == expected_manifest_row_count
        )
        assert first_result.input_snapshot["manifest_summary"]["included_row_count"] > 0
        assert await session.scalar(select(func.count()).select_from(ResidualModelArtifact)) == 3


@pytest.mark.integration
async def test_postgres_execute_residual_prediction_round_trip() -> None:
    _require_postgres()
    fixture = await _seed_prediction_fixture()
    samples = _diverse_training_samples(
        task9_run_id=fixture["train_task9_run_id"],
        label_build_run_id=fixture["train_label_build_run_id"],
        feature_build_run_id=fixture["train_feature_build_run_id"],
        validation_task9_run_id=fixture["validation_task9_run_id"],
        validation_label_build_run_id=fixture["validation_label_build_run_id"],
        validation_feature_build_run_id=fixture["validation_feature_build_run_id"],
        as_of_date=date(2026, 2, 28),
    )

    async with AsyncSessionMaker() as session:
        training_result, training_run_id = await execute_residual_training(
            session,
            samples=samples,
            config=_relaxed_config(),
        )
        assert training_result.eligibility_status == "eligible"

        prediction_result, prediction_run_id = await execute_residual_prediction(
            session,
            request=ResidualPredictionRequest(
                model_run_id=training_run_id,
                task9_run_id=fixture["train_task9_run_id"],
                feature_analytics_build_run_id=fixture["train_feature_build_run_id"],
                supplemental_feature_values=_supplemental_features(as_of_date=date(2026, 2, 28)),
            ),
        )
        loaded = await load_residual_prediction_run_by_id(session, run_id=prediction_run_id)

        assert prediction_result.execution_status == "completed"
        assert prediction_result.mode == "residual_corrected"
        assert loaded is not None
        assert loaded.model_dump(mode="json") == prediction_result.model_dump(mode="json")
        assert (
            await session.scalar(select(func.count()).select_from(ResidualModelPredictionRun)) == 1
        )
        assert await session.scalar(
            select(func.count()).select_from(ResidualModelPredictionRow)
        ) == len(prediction_result.rows)


@pytest.mark.integration
async def test_postgres_execute_residual_prediction_structural_only_for_ineligible_model() -> None:
    _require_postgres()
    fixture = await _seed_prediction_fixture()

    async with AsyncSessionMaker() as session:
        training_result, training_run_id = await execute_residual_training(
            session,
            samples=[
                ResidualTrainingSampleSpec(
                    task9_run_id=fixture["train_task9_run_id"],
                    label_analytics_build_run_id=fixture["train_label_build_run_id"],
                    feature_analytics_build_run_id=fixture["train_feature_build_run_id"],
                    split="train",
                    supplemental_feature_values=_supplemental_features(
                        as_of_date=date(2026, 2, 28)
                    ),
                )
            ],
            config=_config(),
        )
        assert training_result.eligibility_status == "ineligible"

        prediction_result, _prediction_run_id = await execute_residual_prediction(
            session,
            request=ResidualPredictionRequest(
                model_run_id=training_run_id,
                task9_run_id=fixture["train_task9_run_id"],
                feature_analytics_build_run_id=fixture["train_feature_build_run_id"],
                supplemental_feature_values=_supplemental_features(as_of_date=date(2026, 2, 28)),
            ),
        )

        assert prediction_result.execution_status == "completed"
        assert prediction_result.mode == "structural_only"
        assert prediction_result.fallback_reason == "model_not_eligible"


@pytest.mark.integration
async def test_postgres_artifact_hash_corruption_forces_structural_only_fallback() -> None:
    _require_postgres()
    fixture = await _seed_prediction_fixture()
    samples = _diverse_training_samples(
        task9_run_id=fixture["train_task9_run_id"],
        label_build_run_id=fixture["train_label_build_run_id"],
        feature_build_run_id=fixture["train_feature_build_run_id"],
        validation_task9_run_id=fixture["validation_task9_run_id"],
        validation_label_build_run_id=fixture["validation_label_build_run_id"],
        validation_feature_build_run_id=fixture["validation_feature_build_run_id"],
        as_of_date=date(2026, 2, 28),
    )

    async with AsyncSessionMaker() as session:
        _training_result, training_run_id = await execute_residual_training(
            session,
            samples=samples,
            config=_relaxed_config(),
        )
        await session.execute(
            text(
                """
                UPDATE residual_model_artifact
                SET artifact_sha256 = :artifact_sha256
                WHERE training_run_id = :training_run_id
                  AND quantile_label = 'P50'
                """
            ),
            {
                "artifact_sha256": "f" * 64,
                "training_run_id": training_run_id,
            },
        )
        await session.commit()

        prediction_result, _prediction_run_id = await execute_residual_prediction(
            session,
            request=ResidualPredictionRequest(
                model_run_id=training_run_id,
                task9_run_id=fixture["train_task9_run_id"],
                feature_analytics_build_run_id=fixture["train_feature_build_run_id"],
                supplemental_feature_values=_supplemental_features(as_of_date=date(2026, 2, 28)),
            ),
        )

        assert prediction_result.execution_status == "completed"
        assert prediction_result.mode == "structural_only"
        assert prediction_result.fallback_reason == "artifact_validation_failed"


# ── Section 6: Failed-attempt persistence tests ──────────────────────────────


@pytest.mark.integration
async def test_postgres_training_manifest_build_failure_persists_failed_attempt() -> None:
    """Manifest build failure persists a failed attempt record."""
    _require_postgres()
    fixture = await _seed_prediction_fixture()

    # Use non-existent task9_run_id to trigger manifest build failure
    samples = [
        ResidualTrainingSampleSpec(
            task9_run_id=999999,
            label_analytics_build_run_id=fixture["train_label_build_run_id"],
            feature_analytics_build_run_id=fixture["train_feature_build_run_id"],
            split="train",
            supplemental_feature_values=_supplemental_features(as_of_date=date(2026, 2, 28)),
        )
    ]

    with pytest.raises(ResidualTrainingApplicationIntegrityError):
        async with AsyncSessionMaker() as session:
            await execute_residual_training(
                session,
                samples=samples,
                config=_relaxed_config(),
            )

    # Verify attempt record was persisted as failed
    async with AsyncSessionMaker() as session:
        attempts = (
            await session.scalars(
                select(ResidualModelExecutionAttempt)
                .order_by(ResidualModelExecutionAttempt.id.desc())
                .limit(1)
            )
        ).all()
        assert len(attempts) == 1
        attempt = attempts[0]
        assert attempt.attempt_type == "training"
        assert attempt.execution_status == "failed"
        assert attempt.current_stage == "manifest_build"
        assert attempt.sanitized_error is not None
        assert len(attempt.sanitized_error) > 0
        assert attempt.finished_at is not None
        assert attempt.linked_training_run_id is None
        assert attempt.linked_prediction_run_id is None


@pytest.mark.integration
async def test_postgres_prediction_training_load_failure_persists_failed_attempt() -> None:
    """Non-existent training run triggers a failed attempt record."""
    _require_postgres()
    fixture = await _seed_prediction_fixture()

    with pytest.raises(ResidualTrainingApplicationIntegrityError):
        async with AsyncSessionMaker() as session:
            await execute_residual_prediction(
                session,
                request=ResidualPredictionRequest(
                    model_run_id=999999,
                    task9_run_id=fixture["train_task9_run_id"],
                    feature_analytics_build_run_id=fixture["train_feature_build_run_id"],
                    supplemental_feature_values=_supplemental_features(
                        as_of_date=date(2026, 2, 28)
                    ),
                ),
            )

    # Verify attempt record was persisted as failed
    async with AsyncSessionMaker() as session:
        attempts = (
            await session.scalars(
                select(ResidualModelExecutionAttempt)
                .order_by(ResidualModelExecutionAttempt.id.desc())
                .limit(1)
            )
        ).all()
        assert len(attempts) == 1
        attempt = attempts[0]
        assert attempt.attempt_type == "prediction"
        assert attempt.execution_status == "failed"
        assert attempt.linked_training_run_id is None
        assert attempt.linked_prediction_run_id is None


@pytest.mark.integration
async def test_postgres_prediction_feature_build_failure_persists_failed_attempt() -> None:
    """Non-existent feature build triggers a failed attempt record."""
    _require_postgres()
    fixture = await _seed_prediction_fixture()

    async with AsyncSessionMaker() as session:
        _training_result, train_model_run_id = await execute_residual_training(
            session,
            samples=[
                ResidualTrainingSampleSpec(
                    task9_run_id=fixture["train_task9_run_id"],
                    label_analytics_build_run_id=fixture["train_label_build_run_id"],
                    feature_analytics_build_run_id=fixture["train_feature_build_run_id"],
                    split="train",
                    supplemental_feature_values=_supplemental_features(
                        as_of_date=date(2026, 2, 28)
                    ),
                )
            ],
            config=_relaxed_config(),
        )

    with pytest.raises(ResidualPredictionApplicationIntegrityError):
        async with AsyncSessionMaker() as session:
            await execute_residual_prediction(
                session,
                request=ResidualPredictionRequest(
                    model_run_id=train_model_run_id,
                    task9_run_id=fixture["train_task9_run_id"],
                    feature_analytics_build_run_id=999999,
                    supplemental_feature_values=_supplemental_features(
                        as_of_date=date(2026, 2, 28)
                    ),
                ),
            )

    # Verify attempt record was persisted as failed
    async with AsyncSessionMaker() as session:
        attempts = (
            await session.scalars(
                select(ResidualModelExecutionAttempt)
                .order_by(ResidualModelExecutionAttempt.id.desc())
                .limit(1)
            )
        ).all()
        assert len(attempts) == 1
        attempt = attempts[0]
        assert attempt.attempt_type == "prediction"
        assert attempt.execution_status == "failed"
        assert attempt.linked_training_run_id is None
        assert attempt.linked_prediction_run_id is None


@pytest.mark.integration
async def test_postgres_successful_training_run_attempt_finalized_as_completed() -> None:
    """Successful training run finalizes as completed and linked."""
    _require_postgres()
    fixture = await _seed_prediction_fixture()

    # Perform successful training
    async with AsyncSessionMaker() as session:
        training_result, training_run_id = await execute_residual_training(
            session,
            samples=[
                ResidualTrainingSampleSpec(
                    task9_run_id=fixture["train_task9_run_id"],
                    label_analytics_build_run_id=fixture["train_label_build_run_id"],
                    feature_analytics_build_run_id=fixture["train_feature_build_run_id"],
                    split="train",
                    supplemental_feature_values=_supplemental_features(
                        as_of_date=date(2026, 2, 28)
                    ),
                )
            ],
            config=_relaxed_config(),
        )

        assert training_result.execution_status == "completed"
        assert training_run_id > 0

        # Verify attempt record was persisted as completed
        attempts = (
            await session.scalars(
                select(ResidualModelExecutionAttempt)
                .where(ResidualModelExecutionAttempt.attempt_type == "training")
                .order_by(ResidualModelExecutionAttempt.id.desc())
                .limit(1)
            )
        ).all()
        assert len(attempts) == 1
        attempt = attempts[0]
        assert attempt.execution_status == "completed"
        assert attempt.current_stage == "completed"
        assert attempt.linked_training_run_id == training_run_id
        assert attempt.finished_at is not None
