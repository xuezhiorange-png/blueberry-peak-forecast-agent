"""Section 5: Freeze non-eligible/blocked training prediction state matrix.

Tests allowed and disallowed state transitions for residual prediction
based on the training run state matrix:

  - running / failed         → ResidualTrainingApplicationIntegrityError
  - missing training run      → ResidualTrainingApplicationIntegrityError
  - blocked / not_evaluated   → structural_only / model_blocked
  - completed / ineligible    → structural_only / model_not_eligible
  - completed / eligible      → residual_corrected (or structural_only if artifacts fail)
  - feature blockers          → structural_only / feature_visibility_failed
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import CheckConstraint, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.residual_model import (
    ResidualModelPredictionRow,
    ResidualModelPredictionRun,
    ResidualModelTrainingRun,
)
from backend.app.residual_model.application import (
    ResidualTrainingApplicationIntegrityError,
    execute_residual_prediction,
    execute_residual_training,
)
from backend.app.residual_model.persistence import (
    ResidualModelPersistenceError,
    save_residual_prediction_run,
)
from backend.app.residual_model.schemas import (
    ResidualPredictionExecutionResult,
    ResidualPredictionRequest,
    ResidualTrainingSampleSpec,
)
from backend.app.residual_model.service import (
    structural_only_prediction,
)
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

pytestmark = pytest.mark.asyncio
pytest_plugins = ("backend.tests.residual_model.test_training_manifest",)


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


# =========================================================================
# Validation-layer tests
# =========================================================================


class TestValidatePredictionResult:
    """Test _validate_prediction_result rejects invalid state combinations.

    These tests exercise the validation by calling save_residual_prediction_run.
    """

    @pytest.mark.asyncio
    async def test_blocked_prediction_with_rows_rejected(
        self, sqlite_session: AsyncSession
    ) -> None:
        """blocked + rows → ResidualModelPersistenceError."""
        prediction = structural_only_prediction(
            model_run_id=None,
            task9_run_id=10,
            task9_result_hash="a" * 64,
            config_hash="b" * 64,
            structural_rows=[
                {
                    "destination_factory_id": 1,
                    "arrival_local_date": date(2026, 3, 2),
                    "forecast_horizon_days": 1,
                    "structural_p50_kg": Decimal("100"),
                    "structural_p80_kg": Decimal("110"),
                    "structural_p90_kg": Decimal("120"),
                }
            ],
            fallback_reason="model_blocked",
        )
        blocked_with_rows = ResidualPredictionExecutionResult(
            execution_status="blocked",
            mode="blocked",
            model_run_id=None,
            task9_run_id=10,
            task9_result_hash="a" * 64,
            config_hash="b" * 64,
            prediction_input_signature=prediction.prediction_input_signature,
            prediction_hash=prediction.prediction_hash,
            warnings=(),
            blockers=(),
            fallback_reason="model_blocked",
            rows=prediction.rows,
            input_snapshot=prediction.input_snapshot,
        )
        with pytest.raises(
            ResidualModelPersistenceError,
            match="blocked prediction run must not contain rows",
        ):
            await save_residual_prediction_run(
                sqlite_session,
                result=blocked_with_rows,
                feature_schema_version="task10-features-v1",
                feature_schema_hash="f" * 64,
                artifact_hashes=[],
            )

    @pytest.mark.asyncio
    async def test_failed_prediction_with_rows_rejected(
        self, sqlite_session: AsyncSession
    ) -> None:
        """failed + rows → ResidualModelPersistenceError."""
        prediction = structural_only_prediction(
            model_run_id=None,
            task9_run_id=10,
            task9_result_hash="a" * 64,
            config_hash="b" * 64,
            structural_rows=[
                {
                    "destination_factory_id": 1,
                    "arrival_local_date": date(2026, 3, 2),
                    "forecast_horizon_days": 1,
                    "structural_p50_kg": Decimal("100"),
                    "structural_p80_kg": Decimal("110"),
                    "structural_p90_kg": Decimal("120"),
                }
            ],
            fallback_reason="model_not_eligible",
        )
        failed_with_rows = ResidualPredictionExecutionResult(
            execution_status="failed",
            mode="structural_only",
            model_run_id=None,
            task9_run_id=10,
            task9_result_hash="a" * 64,
            config_hash="b" * 64,
            prediction_input_signature=prediction.prediction_input_signature,
            prediction_hash=prediction.prediction_hash,
            warnings=(),
            blockers=(),
            fallback_reason="model_not_eligible",
            rows=prediction.rows,
            input_snapshot=prediction.input_snapshot,
        )
        with pytest.raises(
            ResidualModelPersistenceError,
            match="failed prediction run must not contain rows",
        ):
            await save_residual_prediction_run(
                sqlite_session,
                result=failed_with_rows,
                feature_schema_version="task10-features-v1",
                feature_schema_hash="f" * 64,
                artifact_hashes=[],
            )

    @pytest.mark.asyncio
    async def test_structural_only_has_fallback_reason(
        self, sqlite_session: AsyncSession
    ) -> None:
        """structural_only prediction must carry fallback_reason."""
        prediction = structural_only_prediction(
            model_run_id=None,
            task9_run_id=10,
            task9_result_hash="a" * 64,
            config_hash="b" * 64,
            structural_rows=[
                {
                    "destination_factory_id": 1,
                    "arrival_local_date": date(2026, 3, 2),
                    "forecast_horizon_days": 1,
                    "structural_p50_kg": Decimal("100"),
                    "structural_p80_kg": Decimal("110"),
                    "structural_p90_kg": Decimal("120"),
                }
            ],
            fallback_reason="model_not_eligible",
        )
        assert prediction.fallback_reason is not None
        assert prediction.mode == "structural_only"
        assert prediction.execution_status == "completed"


# =========================================================================
# Application-level state transition tests
# =========================================================================


class TestApplicationStateTransitions:
    """Section 5: Freeze non-eligible/blocked training prediction state matrix."""

    # ----------------------------------------------------------------
    # Disallowed states → typed errors
    # ----------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_missing_training_run_raises_error(
        self, sqlite_session: AsyncSession
    ) -> None:
        """Missing training run → ResidualTrainingApplicationIntegrityError."""
        season_id, factory_id, variety_id = await _seed_master_data(sqlite_session)
        task9_run_id, output = await _persist_task9_run(sqlite_session)
        await _seed_build_run(
            sqlite_session,
            build_run_id=2,
            season_id=season_id,
            source_max_raw_id=50,
            config_hash="b" * 64,
            finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
            covered_factory_ids=(factory_id,),
        )

        with pytest.raises(
            ResidualTrainingApplicationIntegrityError, match="was not found"
        ):
            await execute_residual_prediction(
                sqlite_session,
                request=ResidualPredictionRequest(
                    model_run_id=99999,
                    task9_run_id=task9_run_id,
                    supplemental_feature_values=(),
                ),
            )

    @pytest.mark.asyncio
    async def test_running_training_run_raises_error(
        self, sqlite_session: AsyncSession
    ) -> None:
        """running training run → ResidualTrainingApplicationIntegrityError."""
        season_id, factory_id, variety_id = await _seed_master_data(sqlite_session)
        task9_run_id, output = await _persist_task9_run(sqlite_session)
        label_build = await _seed_build_run(
            sqlite_session, build_run_id=1, season_id=season_id,
            source_max_raw_id=100, config_hash="a" * 64,
            finished_at=datetime(2026, 3, 20, tzinfo=UTC),
            covered_factory_ids=(factory_id,),
        )
        feature_build = await _seed_build_run(
            sqlite_session, build_run_id=2, season_id=season_id,
            source_max_raw_id=50, config_hash="b" * 64,
            finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
            covered_factory_ids=(factory_id,),
        )

        _, training_run_id = await execute_residual_training(
            sqlite_session,
            samples=[
                ResidualTrainingSampleSpec(
                    task9_run_id=task9_run_id,
                    label_analytics_build_run_id=label_build.id,
                    feature_analytics_build_run_id=feature_build.id,
                    split="train",
                )
            ],
            config=_relaxed_config(),
        )

        # Override execution_status to running
        await sqlite_session.execute(
            text(
                "UPDATE residual_model_training_run "
                "SET execution_status = 'running', eligibility_status = 'not_evaluated' "
                f"WHERE id = {training_run_id}"
            )
        )
        await sqlite_session.commit()

        with pytest.raises(
            ResidualTrainingApplicationIntegrityError, match="running"
        ):
            await execute_residual_prediction(
                sqlite_session,
                request=ResidualPredictionRequest(
                    model_run_id=training_run_id,
                    task9_run_id=task9_run_id,
                    supplemental_feature_values=(),
                ),
            )

    @pytest.mark.asyncio
    async def test_failed_training_run_raises_error(
        self, sqlite_session: AsyncSession
    ) -> None:
        """failed training run → ResidualTrainingApplicationIntegrityError."""
        season_id, factory_id, variety_id = await _seed_master_data(sqlite_session)
        task9_run_id, output = await _persist_task9_run(sqlite_session)
        label_build = await _seed_build_run(
            sqlite_session, build_run_id=1, season_id=season_id,
            source_max_raw_id=100, config_hash="a" * 64,
            finished_at=datetime(2026, 3, 20, tzinfo=UTC),
            covered_factory_ids=(factory_id,),
        )
        feature_build = await _seed_build_run(
            sqlite_session, build_run_id=2, season_id=season_id,
            source_max_raw_id=50, config_hash="b" * 64,
            finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
            covered_factory_ids=(factory_id,),
        )

        _, training_run_id = await execute_residual_training(
            sqlite_session,
            samples=[
                ResidualTrainingSampleSpec(
                    task9_run_id=task9_run_id,
                    label_analytics_build_run_id=label_build.id,
                    feature_analytics_build_run_id=feature_build.id,
                    split="train",
                )
            ],
            config=_relaxed_config(),
        )

        await sqlite_session.execute(
            text(
                "UPDATE residual_model_training_run "
                "SET execution_status = 'failed' "
                f"WHERE id = {training_run_id}"
            )
        )
        await sqlite_session.commit()

        with pytest.raises(
            ResidualTrainingApplicationIntegrityError, match="failed"
        ):
            await execute_residual_prediction(
                sqlite_session,
                request=ResidualPredictionRequest(
                    model_run_id=training_run_id,
                    task9_run_id=task9_run_id,
                    supplemental_feature_values=(),
                ),
            )

    # ----------------------------------------------------------------
    # Allowed non-eligible states → structural_only
    # ----------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_blocked_training_run_produces_structural_only(
        self, sqlite_session: AsyncSession
    ) -> None:
        """blocked training run → structural_only / model_blocked."""
        season_id, factory_id, variety_id = await _seed_master_data(sqlite_session)
        task9_run_id, output = await _persist_task9_run(sqlite_session)
        feature_build = await _seed_build_run(
            sqlite_session, build_run_id=2, season_id=season_id,
            source_max_raw_id=50, config_hash="b" * 64,
            finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
            covered_factory_ids=(factory_id,),
        )

        # Empty samples → blocked training run
        _, training_run_id = await execute_residual_training(
            sqlite_session, samples=[], config=_relaxed_config(),
        )

        tr = (
            await sqlite_session.execute(
                select(ResidualModelTrainingRun).where(
                    ResidualModelTrainingRun.id == training_run_id
                )
            )
        ).scalar_one()
        assert tr.execution_status == "blocked"
        assert tr.eligibility_status == "not_evaluated"

        result, _ = await execute_residual_prediction(
            sqlite_session,
            request=ResidualPredictionRequest(
                model_run_id=training_run_id,
                task9_run_id=task9_run_id,
                feature_analytics_build_run_id=feature_build.id,
                supplemental_feature_values=(),
            ),
        )
        assert result.mode == "structural_only"
        assert result.execution_status == "completed"
        assert result.fallback_reason == "model_blocked"
        assert result.input_snapshot.get("artifact_hashes") == []

    @pytest.mark.asyncio
    async def test_completed_ineligible_produces_structural_only(
        self, sqlite_session: AsyncSession
    ) -> None:
        """completed+ineligible training run → structural_only / model_not_eligible."""
        season_id, factory_id, variety_id = await _seed_master_data(sqlite_session)
        task9_run_id, output = await _persist_task9_run(sqlite_session)
        as_of_date = _snapshot_as_of_date(output)
        label_build = await _seed_build_run(
            sqlite_session, build_run_id=1, season_id=season_id,
            source_max_raw_id=100, config_hash="a" * 64,
            finished_at=datetime(2026, 3, 20, tzinfo=UTC),
            covered_factory_ids=(factory_id,),
        )
        feature_build = await _seed_build_run(
            sqlite_session, build_run_id=2, season_id=season_id,
            source_max_raw_id=50, config_hash="b" * 64,
            finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
            covered_factory_ids=(factory_id,),
        )
        await _seed_daily_fact(
            sqlite_session, fact_id=1, build_run_id=label_build.id,
            season_id=season_id, factory_id=factory_id, variety_id=variety_id,
            receipt_date=output.forecast_start_date, weight_kg=Decimal("100"),
        )
        for offset, fact_id in ((1, 2), (3, 3), (7, 4)):
            await _seed_daily_fact(
                sqlite_session, fact_id=fact_id, build_run_id=feature_build.id,
                season_id=season_id, factory_id=factory_id, variety_id=variety_id,
                receipt_date=as_of_date - timedelta(days=offset),
                weight_kg=Decimal("10") + Decimal(offset),
            )
        await sqlite_session.commit()

        # Strict config → ineligible
        _, training_run_id = await execute_residual_training(
            sqlite_session,
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

        tr = (
            await sqlite_session.execute(
                select(ResidualModelTrainingRun).where(
                    ResidualModelTrainingRun.id == training_run_id
                )
            )
        ).scalar_one()
        assert tr.execution_status == "completed"
        assert tr.eligibility_status == "ineligible"

        result, _ = await execute_residual_prediction(
            sqlite_session,
            request=ResidualPredictionRequest(
                model_run_id=training_run_id,
                task9_run_id=task9_run_id,
                feature_analytics_build_run_id=feature_build.id,
                supplemental_feature_values=(),
            ),
        )
        assert result.mode == "structural_only"
        assert result.execution_status == "completed"
        assert result.fallback_reason == "model_not_eligible"
        assert result.input_snapshot.get("artifact_hashes") == []

    @pytest.mark.asyncio
    async def test_completed_eligible_produces_residual_corrected(
        self, sqlite_session: AsyncSession
    ) -> None:
        """completed+eligible training run → residual_corrected."""
        season_id, factory_id, variety_id = await _seed_master_data(sqlite_session)
        validation_season_id = await _seed_season(
            sqlite_session, season_id=2, code="2026-2027",
            start_date=date(2026, 1, 1), end_date=date(2026, 3, 31),
        )
        task9_run_id, output = await _persist_task9_run(sqlite_session)
        as_of_date = _snapshot_as_of_date(output)
        label_build = await _seed_build_run(
            sqlite_session, build_run_id=1, season_id=season_id,
            source_max_raw_id=100, config_hash="a" * 64,
            finished_at=datetime(2026, 3, 20, tzinfo=UTC),
            covered_factory_ids=(factory_id,),
        )
        feature_build = await _seed_build_run(
            sqlite_session, build_run_id=2, season_id=season_id,
            source_max_raw_id=50, config_hash="b" * 64,
            finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
            covered_factory_ids=(factory_id,),
        )
        await _seed_build_run(
            sqlite_session, build_run_id=101, season_id=validation_season_id,
            source_max_raw_id=200, config_hash="c" * 64,
            finished_at=datetime(2026, 3, 20, tzinfo=UTC),
            covered_factory_ids=(factory_id,),
        )
        await _seed_build_run(
            sqlite_session, build_run_id=102, season_id=validation_season_id,
            source_max_raw_id=150, config_hash="d" * 64,
            finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
            covered_factory_ids=(factory_id,),
        )
        for index, target_date in enumerate(
            (date(2026, 3, 1), date(2026, 3, 2), date(2026, 3, 3))
        ):
            await _seed_daily_fact(
                sqlite_session, fact_id=100 + index,
                build_run_id=label_build.id, season_id=season_id,
                factory_id=factory_id, variety_id=variety_id,
                receipt_date=target_date, weight_kg=Decimal("100") + Decimal(index),
            )
        for offset, fact_id in ((1, 200), (3, 201), (7, 202)):
            await _seed_daily_fact(
                sqlite_session, fact_id=fact_id,
                build_run_id=feature_build.id, season_id=season_id,
                factory_id=factory_id, variety_id=variety_id,
                receipt_date=as_of_date - timedelta(days=offset),
                weight_kg=Decimal("11") + Decimal(offset),
            )
        await sqlite_session.commit()

        # Relaxed config → eligible
        _, training_run_id = await execute_residual_training(
            sqlite_session,
            samples=_diverse_training_samples(
                task9_run_id=task9_run_id,
                label_build_run_id=label_build.id,
                feature_build_run_id=feature_build.id,
                as_of_date=as_of_date,
            ),
            config=_relaxed_config(),
        )

        tr = (
            await sqlite_session.execute(
                select(ResidualModelTrainingRun).where(
                    ResidualModelTrainingRun.id == training_run_id
                )
            )
        ).scalar_one()
        assert tr.execution_status == "completed"
        assert tr.eligibility_status == "eligible"

        # Verify the model artifact hashes exist in training artifacts
        from backend.app.repositories.residual_model import list_residual_artifacts
        artifacts = await list_residual_artifacts(sqlite_session, training_run_id=training_run_id)
        assert len(artifacts) == 3

        result, _ = await execute_residual_prediction(
            sqlite_session,
            request=ResidualPredictionRequest(
                model_run_id=training_run_id,
                task9_run_id=task9_run_id,
                feature_analytics_build_run_id=feature_build.id,
                supplemental_feature_values=_supplemental_features(as_of_date=as_of_date),
            ),
        )
        assert result.execution_status == "completed"
        assert result.mode in ("residual_corrected", "structural_only")
        if result.mode == "residual_corrected":
            assert result.fallback_reason is None
        else:
            assert result.fallback_reason is not None


# =========================================================================
# ORM constraint presence tests (no DB required)
# =========================================================================


class TestORMConstraints:
    """Verify ORM constraints reflect cross-state rules."""

    def test_failed_zero_rows_constraint_exists(self) -> None:
        """failed → expected_prediction_row_count=0 constraint must exist."""
        constraints = [
            c.name
            for c in ResidualModelPredictionRun.__table_args__
            if isinstance(c, CheckConstraint)
        ]
        assert "ck_residual_model_prediction_run_failed_zero" in constraints

    def test_blocked_zero_rows_constraint_exists(self) -> None:
        """blocked → expected_prediction_row_count=0 constraint must exist."""
        constraints = [
            c.name
            for c in ResidualModelPredictionRun.__table_args__
            if isinstance(c, CheckConstraint)
        ]
        assert "ck_residual_model_prediction_run_blocked_zero" in constraints

    def test_structural_fallback_constraint_exists(self) -> None:
        """structural_only → fallback_reason NOT NULL constraint must exist."""
        run_constraints = [
            c.name
            for c in ResidualModelPredictionRun.__table_args__
            if isinstance(c, CheckConstraint)
        ]
        assert "ck_residual_model_prediction_run_structural_fallback" in run_constraints

        row_constraints = [
            c.name
            for c in ResidualModelPredictionRow.__table_args__
            if isinstance(c, CheckConstraint)
        ]
        assert "ck_residual_model_prediction_row_structural_fallback" in row_constraints
        assert (
            "ck_residual_model_prediction_row_corrected_no_fallback"
            in row_constraints
        )
