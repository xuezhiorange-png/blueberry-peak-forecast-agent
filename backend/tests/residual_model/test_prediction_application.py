from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.harvest_state.canonical import canonical_json_value
from backend.app.models.harvest_state import HarvestStateRun
from backend.app.models.residual_model import (
    ResidualModelArtifact,
    ResidualModelPredictionRun,
    ResidualModelTrainingRun,
)
from backend.app.residual_model.application import (
    ResidualModelVersionNotVisibleError,
    ResidualPredictionApplicationIntegrityError,
    ResidualReplayTrainedAuthorityError,
    execute_residual_prediction,
    execute_residual_training,
)
from backend.app.residual_model.canonical import canonical_payload_hash
from backend.app.residual_model.manifest import manifest_hash
from backend.app.residual_model.persistence import (
    _prediction_hash_from_result,
    _prediction_payload_hash,
    load_residual_prediction_run_by_id,
)
from backend.app.residual_model.prediction_features import build_prediction_feature_rows
from backend.app.residual_model.replay_training_authority import (
    actual_input_rows,
    actual_manifest_payload,
    dataset_identity,
)
from backend.app.residual_model.schemas import (
    ResidualPredictionExecutionResult,
    ResidualPredictionRequest,
    ResidualTrainingSampleSpec,
)
from backend.app.residual_model.training_manifest import build_residual_training_manifest
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


async def _set_model_authority_times(
    session: AsyncSession,
    *,
    training_run_id: int,
    authority_at: datetime,
) -> None:
    """Make synthetic persisted model authorities historical for prediction tests."""

    await session.execute(
        update(ResidualModelTrainingRun)
        .where(ResidualModelTrainingRun.id == training_run_id)
        .values(finished_at=authority_at)
    )
    await session.execute(
        update(ResidualModelArtifact)
        .where(ResidualModelArtifact.training_run_id == training_run_id)
        .values(created_at=authority_at)
    )
    await session.commit()


async def _full_task12_replay_context(
    session: AsyncSession,
    *,
    samples: list[ResidualTrainingSampleSpec],
    config_hash: str,
    cutoff: datetime,
    task9_run_id: int,
    task9_result_hash: str,
    training_cutoff_at: datetime | None = None,
) -> dict[str, object]:
    """Build the same execution-pass field shape as production ``_task12_context``."""

    manifest_rows = await build_residual_training_manifest(session, samples=samples)
    training_manifest_hash = manifest_hash(manifest_rows)
    training_rows, label_rows = actual_input_rows(manifest_rows)
    manifest_payload = actual_manifest_payload(manifest_rows)
    training_dataset_hash = dataset_identity(
        training_rows=training_rows,
        label_rows=label_rows,
        manifest_rows=manifest_payload,
    )
    effective_training_cutoff = training_cutoff_at or (cutoff - timedelta(days=1))
    model_code_version = "test-residual-model-v1"
    return {
        "task12_replay": {
            "model_policy": "replay_trained_model",
            "task12_policy_version": "test-task12-v1",
            "replay_attempt_id": "attempt-1",
            "replay_node_id": "node-1",
            "scenario_id": "scenario-1",
            "forecast_cutoff_at": cutoff.isoformat(),
            "training_cutoff_at": effective_training_cutoff.isoformat(),
            "training_manifest_hash": training_manifest_hash,
            "training_dataset_hash": training_dataset_hash,
            "model_config_hash": config_hash,
            "model_artifact_hash": canonical_payload_hash(
                {
                    "model_code_version": model_code_version,
                    "training_manifest_hash": training_manifest_hash,
                    "model_config_hash": config_hash,
                }
            ),
            "model_code_version": model_code_version,
            "replay_code_version": "test-replay-v1",
            "task9_run_id": task9_run_id,
            "task9_result_hash": task9_result_hash,
            "task10_training_run_id": None,
            "task10_training_signature": None,
            "task10_manifest_hash": training_manifest_hash,
            "task10_config_hash": config_hash,
            "task10_artifact_hashes": [],
            "is_replay": True,
            "idempotency_key": "task12-test-idempotency",
            "caller_identity": "task12-test-caller",
            "request_payload_hash": canonical_payload_hash(
                {
                    "task9_run_id": task9_run_id,
                    "task9_result_hash": task9_result_hash,
                    "training_cutoff_at": effective_training_cutoff.isoformat(),
                }
            ),
        }
    }


async def _mutate_replay_authority_context(
    session: AsyncSession,
    *,
    training_run_id: int,
    input_snapshot_updates: dict[str, object] | None = None,
    typed_attempt_updates: dict[str, object] | None = None,
    remove_typed_attempt: bool = False,
) -> None:
    training_run = await session.get(ResidualModelTrainingRun, training_run_id)
    assert training_run is not None
    snapshot = dict(training_run.input_snapshot)
    input_context = dict(snapshot["task12_replay"])
    input_context.update(input_snapshot_updates or {})
    snapshot["task12_replay"] = input_context
    training_run.input_snapshot = canonical_json_value(snapshot)
    if remove_typed_attempt:
        training_run.typed_attempt = None
    else:
        typed_attempt = dict(training_run.typed_attempt or {})
        typed_context = dict(typed_attempt["task12_replay"])
        typed_context.update(typed_attempt_updates or {})
        typed_attempt["task12_replay"] = typed_context
        training_run.typed_attempt = canonical_json_value(typed_attempt)
    await session.commit()


async def _seed_eligible_prediction_fixture(
    session: AsyncSession,
    *,
    authority_at: datetime | None = None,
    replay_training_provenance: bool = False,
    training_cutoff_at: datetime | None = None,
    label_finished_at: datetime | None = None,
) -> tuple[int, int, int, date, datetime]:
    season_id, factory_id, variety_id = await _seed_master_data(session)
    validation_season_id = await _seed_season(
        session,
        season_id=2,
        code="2026-2027",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 31),
    )
    task9_run_id, output = await _persist_task9_run(session)
    as_of_date = _snapshot_as_of_date(output)
    cutoff = (
        datetime(2026, 3, 5, 23, 59, 59, 999999, tzinfo=UTC)
        if replay_training_provenance
        else datetime(2026, 2, 28, 23, 59, 59, 999999, tzinfo=UTC)
    )
    task9_run = await session.get(HarvestStateRun, task9_run_id)
    assert task9_run is not None
    if replay_training_provenance:
        task9_run.is_replay = True
        task9_run.forecast_effective_cutoff_at = cutoff
        task9_run.replay_executed_at = cutoff + timedelta(seconds=1)
        task9_run.replay_code_version = "test-replay-v1"
        task9_run.replay_run_correlation_id = "residual-replay-test"
    effective_training_cutoff = training_cutoff_at or (cutoff - timedelta(days=1))
    effective_label_finished_at = label_finished_at or (
        effective_training_cutoff - timedelta(hours=1)
        if replay_training_provenance
        else datetime(2026, 3, 20, tzinfo=UTC)
    )
    label_build = await _seed_build_run(
        session,
        build_run_id=1,
        season_id=season_id,
        source_max_raw_id=100,
        config_hash="a" * 64,
        finished_at=effective_label_finished_at,
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
    validation_label_build = await _seed_build_run(
        session,
        build_run_id=101,
        season_id=validation_season_id,
        source_max_raw_id=200,
        config_hash="c" * 64,
        finished_at=(
            effective_label_finished_at
            if replay_training_provenance
            else datetime(2026, 3, 20, tzinfo=UTC)
        ),
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
            fact_id=100 + index,
            build_run_id=label_build.id,
            season_id=season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=target_date,
            weight_kg=Decimal("100") + Decimal(index),
        )
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
        await _seed_daily_fact(
            session,
            fact_id=400 + offset,
            build_run_id=validation_feature_build.id,
            season_id=validation_season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=as_of_date - timedelta(days=offset),
            weight_kg=weight + Decimal("10"),
        )
    await session.commit()

    samples = _diverse_training_samples(
        task9_run_id=task9_run_id,
        label_build_run_id=label_build.id,
        feature_build_run_id=feature_build.id,
        validation_task9_run_id=task9_run_id,
        validation_label_build_run_id=validation_label_build.id,
        validation_feature_build_run_id=validation_feature_build.id,
        as_of_date=as_of_date,
    )
    config = _relaxed_config()
    training_execution_context: dict[str, object] | None = None
    if replay_training_provenance:
        training_execution_context = await _full_task12_replay_context(
            session,
            samples=samples,
            config_hash=config.config_hash,
            cutoff=cutoff,
            task9_run_id=task9_run_id,
            task9_result_hash=output.result_hash,
            training_cutoff_at=effective_training_cutoff,
        )

    training_result, training_run_id = await execute_residual_training(
        session,
        samples=samples,
        config=config,
        execution_context=training_execution_context,
        typed_attempt=training_execution_context,
    )
    assert training_result.eligibility_status == "eligible"
    resolved_authority_at = authority_at or datetime(2026, 2, 28, 12, 0, tzinfo=UTC)
    await _set_model_authority_times(
        session,
        training_run_id=training_run_id,
        authority_at=resolved_authority_at,
    )
    return task9_run_id, feature_build.id, training_run_id, as_of_date, cutoff


async def test_execute_residual_prediction_persists_and_reloads(
    sqlite_session: AsyncSession,
) -> None:
    season_id, factory_id, variety_id = await _seed_master_data(sqlite_session)
    validation_season_id = await _seed_season(
        sqlite_session,
        season_id=2,
        code="2026-2027",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 31),
    )
    task9_run_id, output = await _persist_task9_run(sqlite_session)
    as_of_date = _snapshot_as_of_date(output)
    label_build = await _seed_build_run(
        sqlite_session,
        build_run_id=1,
        season_id=season_id,
        source_max_raw_id=100,
        config_hash="a" * 64,
        finished_at=datetime(2026, 3, 20, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
    )
    feature_build = await _seed_build_run(
        sqlite_session,
        build_run_id=2,
        season_id=season_id,
        source_max_raw_id=50,
        config_hash="b" * 64,
        finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
    )
    validation_label_build = await _seed_build_run(
        sqlite_session,
        build_run_id=101,
        season_id=validation_season_id,
        source_max_raw_id=200,
        config_hash="c" * 64,
        finished_at=datetime(2026, 3, 20, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
    )
    validation_feature_build = await _seed_build_run(
        sqlite_session,
        build_run_id=102,
        season_id=validation_season_id,
        source_max_raw_id=150,
        config_hash="d" * 64,
        finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
    )
    for index, target_date in enumerate((date(2026, 3, 1), date(2026, 3, 2), date(2026, 3, 3))):
        await _seed_daily_fact(
            sqlite_session,
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
            sqlite_session,
            fact_id=200 + offset,
            build_run_id=feature_build.id,
            season_id=season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=as_of_date - timedelta(days=offset),
            weight_kg=weight,
        )
    for index, target_date in enumerate((date(2026, 3, 1), date(2026, 3, 2), date(2026, 3, 3))):
        await _seed_daily_fact(
            sqlite_session,
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
            sqlite_session,
            fact_id=400 + offset,
            build_run_id=validation_feature_build.id,
            season_id=validation_season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=as_of_date - timedelta(days=offset),
            weight_kg=weight,
        )
    await sqlite_session.commit()

    training_result, training_run_id = await execute_residual_training(
        sqlite_session,
        samples=_diverse_training_samples(
            task9_run_id=task9_run_id,
            label_build_run_id=label_build.id,
            feature_build_run_id=feature_build.id,
            validation_task9_run_id=task9_run_id,
            validation_label_build_run_id=validation_label_build.id,
            validation_feature_build_run_id=validation_feature_build.id,
            as_of_date=as_of_date,
        ),
        config=_relaxed_config(),
    )
    assert training_result.eligibility_status == "eligible"
    await _set_model_authority_times(
        sqlite_session,
        training_run_id=training_run_id,
        authority_at=datetime(2026, 2, 28, 23, 59, 59, 999999, tzinfo=UTC),
    )

    prediction_result, prediction_run_id = await execute_residual_prediction(
        sqlite_session,
        request=ResidualPredictionRequest(
            model_run_id=training_run_id,
            task9_run_id=task9_run_id,
            feature_analytics_build_run_id=feature_build.id,
            supplemental_feature_values=_supplemental_features(as_of_date=as_of_date),
        ),
        typed_attempt={
            "existing_attempt": "preserved",
            "model_artifact_visibility": {"mode": "caller-fake"},
        },
    )

    assert prediction_run_id > 0
    assert prediction_result.execution_status == "completed"
    assert prediction_result.mode == "residual_corrected"
    assert prediction_result.task9_run_id == task9_run_id
    assert prediction_result.rows
    assert any(row.corrected_raw_p50_kg != row.structural_p50_kg for row in prediction_result.rows)
    persisted_prediction = await sqlite_session.get(ResidualModelPredictionRun, prediction_run_id)
    assert persisted_prediction is not None
    assert "model_artifact_visibility" not in prediction_result.input_snapshot
    assert (persisted_prediction.typed_attempt or {})["existing_attempt"] == "preserved"
    visibility = (persisted_prediction.typed_attempt or {})["model_artifact_visibility"]
    assert visibility["mode"] == "historically_available_model"
    assert visibility["forecast_cutoff_at"] == "2026-02-28T23:59:59.999999+00:00"
    assert visibility["training_run_finished_at"] == visibility["forecast_cutoff_at"]
    assert len(visibility["artifact_authorities"]) == 3
    assert all(
        item["created_at"] == visibility["forecast_cutoff_at"]
        for item in visibility["artifact_authorities"]
    )

    # Simulate a PR192 interim persisted row: the audit lived in the
    # canonical input snapshot and its historical output/payload hashes
    # included that field.  The post-correction request must reuse it by
    # business identity instead of raising a hash conflict.
    legacy_input_snapshot = dict(persisted_prediction.input_snapshot)
    legacy_input_snapshot["model_artifact_visibility"] = visibility
    legacy_canonical_output = dict(persisted_prediction.canonical_output)
    legacy_canonical_output["input_snapshot"] = legacy_input_snapshot
    legacy_canonical_output["prediction_hash"] = "0" * 64
    legacy_result = ResidualPredictionExecutionResult.model_validate(legacy_canonical_output)
    legacy_prediction_hash = _prediction_hash_from_result(legacy_result)
    legacy_canonical_output["prediction_hash"] = legacy_prediction_hash
    legacy_result = ResidualPredictionExecutionResult.model_validate(legacy_canonical_output)
    persisted_prediction.input_snapshot = canonical_json_value(legacy_input_snapshot)
    persisted_prediction.canonical_output = canonical_json_value(legacy_canonical_output)
    persisted_prediction.prediction_hash = legacy_prediction_hash
    persisted_prediction.canonical_payload_hash = _prediction_payload_hash(legacy_result)
    await sqlite_session.commit()

    same_result, same_prediction_run_id = await execute_residual_prediction(
        sqlite_session,
        request=ResidualPredictionRequest(
            model_run_id=training_run_id,
            task9_run_id=task9_run_id,
            feature_analytics_build_run_id=feature_build.id,
            supplemental_feature_values=_supplemental_features(as_of_date=as_of_date),
        ),
    )
    assert same_prediction_run_id == prediction_run_id
    assert same_result.prediction_input_signature == prediction_result.prediction_input_signature
    assert same_result.rows == prediction_result.rows
    assert same_result.input_snapshot["model_artifact_visibility"] == visibility


async def test_prediction_feature_build_uses_persisted_exact_forecast_cutoff(
    sqlite_session: AsyncSession,
) -> None:
    await _seed_master_data(sqlite_session)
    task9_run_id, output = await _persist_task9_run(sqlite_session)
    as_of_date = _snapshot_as_of_date(output)
    exact_cutoff = datetime(2026, 3, 1, 4, 0, tzinfo=UTC)
    task9_run = await sqlite_session.get(HarvestStateRun, task9_run_id)
    assert task9_run is not None
    task9_run.is_replay = True
    task9_run.forecast_effective_cutoff_at = exact_cutoff
    task9_run.replay_executed_at = datetime(2026, 3, 1, 5, 0, tzinfo=UTC)
    task9_run.replay_code_version = "test-replay-v1"
    task9_run.replay_run_correlation_id = "prediction-feature-test"
    await sqlite_session.commit()

    (
        _output,
        _structural_rows,
        feature_rows,
        audits,
        _warnings,
        blockers,
        _feature_snapshot,
    ) = await build_prediction_feature_rows(
        sqlite_session,
        task9_run_id=task9_run_id,
        feature_analytics_build_run_id=None,
        supplemental_feature_values=_supplemental_features(
            as_of_date=as_of_date,
            cutoff_at=exact_cutoff,
        ),
    )

    assert feature_rows
    assert audits
    assert blockers == ["MISSING_REQUIRED_FEATURE"]
    assert all(item.known_at == exact_cutoff for item in feature_rows[0])
    assert all(audit.status == "blocked" for audit in audits)
    assert all(
        all(issue.code == "MISSING_REQUIRED_FEATURE" for issue in audit.blockers)
        for audit in audits
    )

    (
        _output,
        _structural_rows,
        _post_cutoff_feature_rows,
        post_cutoff_audits,
        _warnings,
        post_cutoff_blockers,
        _feature_snapshot,
    ) = await build_prediction_feature_rows(
        sqlite_session,
        task9_run_id=task9_run_id,
        feature_analytics_build_run_id=None,
        supplemental_feature_values=_supplemental_features(
            as_of_date=as_of_date,
            cutoff_at=datetime(2026, 3, 1, 10, 0, tzinfo=UTC),
        ),
    )

    assert "FUTURE_KNOWN_AT" in post_cutoff_blockers
    assert any(
        issue.code == "FUTURE_KNOWN_AT" for audit in post_cutoff_audits for issue in audit.blockers
    )


async def test_execute_residual_prediction_falls_back_for_ineligible_model(
    sqlite_session: AsyncSession,
) -> None:
    season_id, factory_id, variety_id = await _seed_master_data(sqlite_session)
    task9_run_id, output = await _persist_task9_run(sqlite_session)
    as_of_date = _snapshot_as_of_date(output)
    label_build = await _seed_build_run(
        sqlite_session,
        build_run_id=1,
        season_id=season_id,
        source_max_raw_id=100,
        config_hash="a" * 64,
        finished_at=datetime(2026, 3, 20, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
    )
    feature_build = await _seed_build_run(
        sqlite_session,
        build_run_id=2,
        season_id=season_id,
        source_max_raw_id=50,
        config_hash="b" * 64,
        finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
    )
    await _seed_daily_fact(
        sqlite_session,
        fact_id=1,
        build_run_id=label_build.id,
        season_id=season_id,
        factory_id=factory_id,
        variety_id=variety_id,
        receipt_date=output.forecast_start_date,
        weight_kg=Decimal("100"),
    )
    for offset, fact_id in ((1, 2), (3, 3), (7, 4)):
        await _seed_daily_fact(
            sqlite_session,
            fact_id=fact_id,
            build_run_id=feature_build.id,
            season_id=season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=as_of_date - timedelta(days=offset),
            weight_kg=Decimal("10") + Decimal(offset),
        )
    await sqlite_session.commit()

    training_result, training_run_id = await execute_residual_training(
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
    assert training_result.eligibility_status == "ineligible"
    await _set_model_authority_times(
        sqlite_session,
        training_run_id=training_run_id,
        authority_at=datetime(2026, 2, 28, 23, 59, 59, 999999, tzinfo=UTC),
    )

    prediction_result, _prediction_run_id = await execute_residual_prediction(
        sqlite_session,
        request=ResidualPredictionRequest(
            model_run_id=training_run_id,
            task9_run_id=task9_run_id,
            feature_analytics_build_run_id=feature_build.id,
            supplemental_feature_values=_supplemental_features(as_of_date=as_of_date),
        ),
    )

    assert prediction_result.execution_status == "completed"
    assert prediction_result.mode == "structural_only"
    assert prediction_result.fallback_reason == "model_not_eligible"
    assert all(row.raw_residual_p50_kg == Decimal("0") for row in prediction_result.rows)


@pytest.mark.parametrize(
    ("column_name", "value"),
    [
        ("python_version", "0.0.0"),
        ("numpy_version", "0.0.0"),
        ("sklearn_version", "0.0.0"),
    ],
)
async def test_execute_residual_prediction_falls_back_for_dependency_version_mismatch(
    sqlite_session: AsyncSession,
    column_name: str,
    value: str,
) -> None:
    season_id, factory_id, variety_id = await _seed_master_data(sqlite_session)
    validation_season_id = await _seed_season(
        sqlite_session,
        season_id=2,
        code="2026-2027",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 31),
    )
    task9_run_id, output = await _persist_task9_run(sqlite_session)
    as_of_date = _snapshot_as_of_date(output)
    label_build = await _seed_build_run(
        sqlite_session,
        build_run_id=1,
        season_id=season_id,
        source_max_raw_id=100,
        config_hash="a" * 64,
        finished_at=datetime(2026, 3, 20, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
    )
    feature_build = await _seed_build_run(
        sqlite_session,
        build_run_id=2,
        season_id=season_id,
        source_max_raw_id=50,
        config_hash="b" * 64,
        finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
    )
    validation_label_build = await _seed_build_run(
        sqlite_session,
        build_run_id=101,
        season_id=validation_season_id,
        source_max_raw_id=200,
        config_hash="c" * 64,
        finished_at=datetime(2026, 3, 20, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
    )
    validation_feature_build = await _seed_build_run(
        sqlite_session,
        build_run_id=102,
        season_id=validation_season_id,
        source_max_raw_id=150,
        config_hash="d" * 64,
        finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
    )
    for index, target_date in enumerate((date(2026, 3, 1), date(2026, 3, 2), date(2026, 3, 3))):
        await _seed_daily_fact(
            sqlite_session,
            fact_id=100 + index,
            build_run_id=label_build.id,
            season_id=season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=target_date,
            weight_kg=Decimal("100") + Decimal(index),
        )
        await _seed_daily_fact(
            sqlite_session,
            fact_id=300 + index,
            build_run_id=validation_label_build.id,
            season_id=validation_season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=target_date,
            weight_kg=Decimal("120") + Decimal(index),
        )
    for offset, weight in ((1, Decimal("11")), (3, Decimal("13")), (7, Decimal("17"))):
        await _seed_daily_fact(
            sqlite_session,
            fact_id=200 + offset,
            build_run_id=feature_build.id,
            season_id=season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=as_of_date - timedelta(days=offset),
            weight_kg=weight,
        )
    for offset, weight in ((1, Decimal("21")), (3, Decimal("23")), (7, Decimal("27"))):
        await _seed_daily_fact(
            sqlite_session,
            fact_id=400 + offset,
            build_run_id=validation_feature_build.id,
            season_id=validation_season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=as_of_date - timedelta(days=offset),
            weight_kg=weight,
        )
    await sqlite_session.commit()

    _training_result, training_run_id = await execute_residual_training(
        sqlite_session,
        samples=_diverse_training_samples(
            task9_run_id=task9_run_id,
            label_build_run_id=label_build.id,
            feature_build_run_id=feature_build.id,
            validation_task9_run_id=task9_run_id,
            validation_label_build_run_id=validation_label_build.id,
            validation_feature_build_run_id=validation_feature_build.id,
            as_of_date=as_of_date,
        ),
        config=_relaxed_config(),
    )
    await _set_model_authority_times(
        sqlite_session,
        training_run_id=training_run_id,
        authority_at=datetime(2026, 2, 28, 23, 59, 59, 999999, tzinfo=UTC),
    )
    await sqlite_session.execute(
        text(f"UPDATE residual_model_training_run SET {column_name} = :value WHERE id = :run_id"),
        {"value": value, "run_id": training_run_id},
    )
    await sqlite_session.commit()

    prediction_result, _prediction_run_id = await execute_residual_prediction(
        sqlite_session,
        request=ResidualPredictionRequest(
            model_run_id=training_run_id,
            task9_run_id=task9_run_id,
            feature_analytics_build_run_id=feature_build.id,
            supplemental_feature_values=_supplemental_features(as_of_date=as_of_date),
        ),
    )

    assert prediction_result.execution_status == "completed"
    assert prediction_result.mode == "structural_only"
    assert prediction_result.fallback_reason == "artifact_validation_failed"


async def test_execute_residual_prediction_fails_when_artifact_identity_query_fails(
    sqlite_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    season_id, factory_id, variety_id = await _seed_master_data(sqlite_session)
    validation_season_id = await _seed_season(
        sqlite_session,
        season_id=2,
        code="2026-2027",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 31),
    )
    task9_run_id, output = await _persist_task9_run(sqlite_session)
    as_of_date = _snapshot_as_of_date(output)
    label_build = await _seed_build_run(
        sqlite_session,
        build_run_id=1,
        season_id=season_id,
        source_max_raw_id=100,
        config_hash="a" * 64,
        finished_at=datetime(2026, 3, 20, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
    )
    feature_build = await _seed_build_run(
        sqlite_session,
        build_run_id=2,
        season_id=season_id,
        source_max_raw_id=50,
        config_hash="b" * 64,
        finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
    )
    validation_label_build = await _seed_build_run(
        sqlite_session,
        build_run_id=101,
        season_id=validation_season_id,
        source_max_raw_id=200,
        config_hash="c" * 64,
        finished_at=datetime(2026, 3, 20, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
    )
    validation_feature_build = await _seed_build_run(
        sqlite_session,
        build_run_id=102,
        season_id=validation_season_id,
        source_max_raw_id=150,
        config_hash="d" * 64,
        finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
    )
    for index, target_date in enumerate((date(2026, 3, 1), date(2026, 3, 2), date(2026, 3, 3))):
        await _seed_daily_fact(
            sqlite_session,
            fact_id=100 + index,
            build_run_id=label_build.id,
            season_id=season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=target_date,
            weight_kg=Decimal("100") + Decimal(index),
        )
        await _seed_daily_fact(
            sqlite_session,
            fact_id=300 + index,
            build_run_id=validation_label_build.id,
            season_id=validation_season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=target_date,
            weight_kg=Decimal("120") + Decimal(index),
        )
    for offset, weight in ((1, Decimal("11")), (3, Decimal("13")), (7, Decimal("17"))):
        await _seed_daily_fact(
            sqlite_session,
            fact_id=200 + offset,
            build_run_id=feature_build.id,
            season_id=season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=as_of_date - timedelta(days=offset),
            weight_kg=weight,
        )
    for offset, weight in ((1, Decimal("21")), (3, Decimal("23")), (7, Decimal("27"))):
        await _seed_daily_fact(
            sqlite_session,
            fact_id=400 + offset,
            build_run_id=validation_feature_build.id,
            season_id=validation_season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=as_of_date - timedelta(days=offset),
            weight_kg=weight,
        )
    await sqlite_session.commit()

    _training_result, training_run_id = await execute_residual_training(
        sqlite_session,
        samples=_diverse_training_samples(
            task9_run_id=task9_run_id,
            label_build_run_id=label_build.id,
            feature_build_run_id=feature_build.id,
            validation_task9_run_id=task9_run_id,
            validation_label_build_run_id=validation_label_build.id,
            validation_feature_build_run_id=validation_feature_build.id,
            as_of_date=as_of_date,
        ),
        config=_relaxed_config(),
    )
    await _set_model_authority_times(
        sqlite_session,
        training_run_id=training_run_id,
        authority_at=datetime(2026, 2, 28, 23, 59, 59, 999999, tzinfo=UTC),
    )

    async def _boom(*args, **kwargs):
        raise SQLAlchemyError("artifact identity query failed")

    monkeypatch.setattr("backend.app.residual_model.application.list_residual_artifacts", _boom)

    with pytest.raises(
        ResidualPredictionApplicationIntegrityError,
        match="Authoritative residual artifact identities could not be loaded",
    ):
        await execute_residual_prediction(
            sqlite_session,
            request=ResidualPredictionRequest(
                model_run_id=training_run_id,
                task9_run_id=task9_run_id,
                feature_analytics_build_run_id=feature_build.id,
                supplemental_feature_values=_supplemental_features(as_of_date=as_of_date),
            ),
        )

    assert (
        await sqlite_session.scalar(select(func.count()).select_from(ResidualModelPredictionRun))
        == 0
    )


async def test_execute_residual_prediction_uses_structural_only_for_unknown_category_row(
    sqlite_session: AsyncSession,
) -> None:
    from backend.app.residual_model.config import load_residual_model_config_from_snapshot

    config = _relaxed_config()
    config = load_residual_model_config_from_snapshot(
        {
            **config.snapshot,
            "eligibility": {
                **config.snapshot["eligibility"],
                "min_training_rows": 1,
                "min_seasons": 1,
                "min_factories": 1,
                "max_validation_wmape": 10.0,
                "require_improvement_over_structural": False,
                "max_fallback_rate": 1.0,
            },
            "categorical_encoding": {
                **config.snapshot["categorical_encoding"],
                "unknown_policy": "structural_only_fallback",
            },
        }
    )
    season_id, factory_id, variety_id = await _seed_master_data(sqlite_session)
    validation_season_id = await _seed_season(
        sqlite_session,
        season_id=2,
        code="2026-2027",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 31),
    )
    task9_run_id, output = await _persist_task9_run(sqlite_session)
    as_of_date = _snapshot_as_of_date(output)
    label_build = await _seed_build_run(
        sqlite_session,
        build_run_id=1,
        season_id=season_id,
        source_max_raw_id=100,
        config_hash="a" * 64,
        finished_at=datetime(2026, 3, 20, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
    )
    feature_build = await _seed_build_run(
        sqlite_session,
        build_run_id=2,
        season_id=season_id,
        source_max_raw_id=50,
        config_hash="b" * 64,
        finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
    )
    validation_label_build = await _seed_build_run(
        sqlite_session,
        build_run_id=101,
        season_id=validation_season_id,
        source_max_raw_id=200,
        config_hash="c" * 64,
        finished_at=datetime(2026, 3, 20, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
    )
    validation_feature_build = await _seed_build_run(
        sqlite_session,
        build_run_id=102,
        season_id=validation_season_id,
        source_max_raw_id=150,
        config_hash="d" * 64,
        finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
    )
    for index, target_date in enumerate((date(2026, 3, 1), date(2026, 3, 2), date(2026, 3, 3))):
        await _seed_daily_fact(
            sqlite_session,
            fact_id=100 + index,
            build_run_id=label_build.id,
            season_id=season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=target_date,
            weight_kg=Decimal("100") + Decimal(index),
        )
        await _seed_daily_fact(
            sqlite_session,
            fact_id=300 + index,
            build_run_id=validation_label_build.id,
            season_id=validation_season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=target_date,
            weight_kg=Decimal("120") + Decimal(index),
        )
    for offset, weight in ((1, Decimal("11")), (3, Decimal("13")), (7, Decimal("17"))):
        await _seed_daily_fact(
            sqlite_session,
            fact_id=200 + offset,
            build_run_id=feature_build.id,
            season_id=season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=as_of_date - timedelta(days=offset),
            weight_kg=weight,
        )
        await _seed_daily_fact(
            sqlite_session,
            fact_id=400 + offset,
            build_run_id=validation_feature_build.id,
            season_id=validation_season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=as_of_date - timedelta(days=offset),
            weight_kg=weight + Decimal("10"),
        )
    await sqlite_session.commit()

    training_result, training_run_id = await execute_residual_training(
        sqlite_session,
        samples=_diverse_training_samples(
            task9_run_id=task9_run_id,
            label_build_run_id=label_build.id,
            feature_build_run_id=feature_build.id,
            validation_task9_run_id=task9_run_id,
            validation_label_build_run_id=validation_label_build.id,
            validation_feature_build_run_id=validation_feature_build.id,
            as_of_date=as_of_date,
        ),
        config=config,
    )
    assert training_result.eligibility_status == "eligible"
    await _set_model_authority_times(
        sqlite_session,
        training_run_id=training_run_id,
        authority_at=datetime(2026, 2, 28, 23, 59, 59, 999999, tzinfo=UTC),
    )

    prediction_result, _prediction_run_id = await execute_residual_prediction(
        sqlite_session,
        request=ResidualPredictionRequest(
            model_run_id=training_run_id,
            task9_run_id=task9_run_id,
            feature_analytics_build_run_id=feature_build.id,
            supplemental_feature_values=_supplemental_features(
                as_of_date=as_of_date,
                destination_factory_category="totally-unknown-category",
            ),
        ),
    )

    assert prediction_result.execution_status == "completed"
    assert prediction_result.mode == "structural_only"
    assert prediction_result.fallback_reason == "unknown_category"
    assert all(row.mode == "structural_only" for row in prediction_result.rows)
    assert all(row.raw_residual_p50_kg == Decimal("0") for row in prediction_result.rows)


async def test_residual_prediction_blocks_training_run_after_forecast_cutoff(
    sqlite_session: AsyncSession,
) -> None:
    (
        task9_run_id,
        feature_build_id,
        training_run_id,
        as_of_date,
        cutoff,
    ) = await _seed_eligible_prediction_fixture(sqlite_session)
    await sqlite_session.execute(
        update(ResidualModelTrainingRun)
        .where(ResidualModelTrainingRun.id == training_run_id)
        .values(finished_at=cutoff + timedelta(seconds=1))
    )
    await sqlite_session.commit()

    with pytest.raises(ResidualModelVersionNotVisibleError) as exc_info:
        await execute_residual_prediction(
            sqlite_session,
            request=ResidualPredictionRequest(
                model_run_id=training_run_id,
                task9_run_id=task9_run_id,
                feature_analytics_build_run_id=feature_build_id,
                supplemental_feature_values=_supplemental_features(as_of_date=as_of_date),
            ),
            execution_context={
                "model_artifact_visibility": {
                    "mode": "historically_available_model",
                    "training_run_finished_at": cutoff.isoformat(),
                }
            },
        )

    assert exc_info.value.code == "MODEL_VERSION_NOT_VISIBLE"
    assert (
        await sqlite_session.scalar(
            select(func.count())
            .select_from(ResidualModelPredictionRun)
            .where(ResidualModelPredictionRun.training_run_id == training_run_id)
        )
        == 0
    )


async def test_residual_prediction_allows_historically_visible_model_before_cutoff(
    sqlite_session: AsyncSession,
) -> None:
    (
        task9_run_id,
        feature_build_id,
        training_run_id,
        as_of_date,
        cutoff,
    ) = await _seed_eligible_prediction_fixture(sqlite_session)

    prediction_result, _prediction_run_id = await execute_residual_prediction(
        sqlite_session,
        request=ResidualPredictionRequest(
            model_run_id=training_run_id,
            task9_run_id=task9_run_id,
            feature_analytics_build_run_id=feature_build_id,
            supplemental_feature_values=_supplemental_features(as_of_date=as_of_date),
        ),
    )

    persisted_prediction = await sqlite_session.get(ResidualModelPredictionRun, _prediction_run_id)
    assert persisted_prediction is not None
    assert "model_artifact_visibility" not in prediction_result.input_snapshot
    visibility = (persisted_prediction.typed_attempt or {})["model_artifact_visibility"]
    assert prediction_result.mode == "residual_corrected"
    assert visibility["training_run_finished_at"] < cutoff.isoformat()
    assert all(
        item["created_at"] < cutoff.isoformat() for item in visibility["artifact_authorities"]
    )


async def test_residual_prediction_checks_every_artifact_for_cutoff_visibility(
    sqlite_session: AsyncSession,
) -> None:
    (
        task9_run_id,
        feature_build_id,
        training_run_id,
        as_of_date,
        cutoff,
    ) = await _seed_eligible_prediction_fixture(sqlite_session)
    artifacts = list(
        (
            await sqlite_session.scalars(
                select(ResidualModelArtifact)
                .where(ResidualModelArtifact.training_run_id == training_run_id)
                .order_by(ResidualModelArtifact.quantile_label.asc())
            )
        ).all()
    )
    assert [artifact.quantile_label for artifact in artifacts] == ["P50", "P80", "P90"]
    await sqlite_session.execute(
        update(ResidualModelArtifact)
        .where(ResidualModelArtifact.id == artifacts[-1].id)
        .values(created_at=cutoff + timedelta(seconds=1))
    )
    await sqlite_session.commit()

    with pytest.raises(ResidualModelVersionNotVisibleError) as exc_info:
        await execute_residual_prediction(
            sqlite_session,
            request=ResidualPredictionRequest(
                model_run_id=training_run_id,
                task9_run_id=task9_run_id,
                feature_analytics_build_run_id=feature_build_id,
                supplemental_feature_values=_supplemental_features(as_of_date=as_of_date),
            ),
        )

    assert exc_info.value.code == "MODEL_VERSION_NOT_VISIBLE"
    assert (
        await sqlite_session.scalar(
            select(func.count())
            .select_from(ResidualModelPredictionRun)
            .where(ResidualModelPredictionRun.training_run_id == training_run_id)
        )
        == 0
    )


async def test_residual_prediction_rejects_naked_replay_trained_bypass(
    sqlite_session: AsyncSession,
) -> None:
    (
        task9_run_id,
        feature_build_id,
        training_run_id,
        as_of_date,
        cutoff,
    ) = await _seed_eligible_prediction_fixture(sqlite_session)
    replay_created_at = cutoff + timedelta(days=1)
    await sqlite_session.execute(
        update(ResidualModelTrainingRun)
        .where(ResidualModelTrainingRun.id == training_run_id)
        .values(finished_at=replay_created_at)
    )
    await sqlite_session.execute(
        update(ResidualModelArtifact)
        .where(ResidualModelArtifact.training_run_id == training_run_id)
        .values(created_at=replay_created_at)
    )
    await sqlite_session.commit()

    with pytest.raises(ResidualReplayTrainedAuthorityError):
        await execute_residual_prediction(
            sqlite_session,
            request=ResidualPredictionRequest(
                model_run_id=training_run_id,
                task9_run_id=task9_run_id,
                feature_analytics_build_run_id=feature_build_id,
                supplemental_feature_values=_supplemental_features(as_of_date=as_of_date),
            ),
            model_policy="replay_trained_model",
        )

    assert (
        await sqlite_session.scalar(
            select(func.count())
            .select_from(ResidualModelPredictionRun)
            .where(ResidualModelPredictionRun.training_run_id == training_run_id)
        )
        == 0
    )


async def test_residual_prediction_rejects_fake_replay_context_for_non_replay_task9(
    sqlite_session: AsyncSession,
) -> None:
    (
        task9_run_id,
        feature_build_id,
        training_run_id,
        as_of_date,
        cutoff,
    ) = await _seed_eligible_prediction_fixture(sqlite_session)
    await sqlite_session.execute(
        update(ResidualModelTrainingRun)
        .where(ResidualModelTrainingRun.id == training_run_id)
        .values(finished_at=cutoff + timedelta(seconds=1))
    )
    await sqlite_session.commit()

    with pytest.raises(ResidualReplayTrainedAuthorityError):
        await execute_residual_prediction(
            sqlite_session,
            request=ResidualPredictionRequest(
                model_run_id=training_run_id,
                task9_run_id=task9_run_id,
                feature_analytics_build_run_id=feature_build_id,
                supplemental_feature_values=_supplemental_features(as_of_date=as_of_date),
            ),
            model_policy="replay_trained_model",
            execution_context={
                "task12_replay": {
                    "model_policy": "replay_trained_model",
                    "is_replay": True,
                    "task9_run_id": task9_run_id,
                    "task9_result_hash": "fake",
                }
            },
        )


async def test_residual_prediction_rejects_replay_without_persisted_task12_authority(
    sqlite_session: AsyncSession,
) -> None:
    (
        task9_run_id,
        feature_build_id,
        training_run_id,
        as_of_date,
        cutoff,
    ) = await _seed_eligible_prediction_fixture(sqlite_session)
    task9_run = await sqlite_session.get(HarvestStateRun, task9_run_id)
    assert task9_run is not None
    task9_run.is_replay = True
    task9_run.forecast_effective_cutoff_at = cutoff
    await sqlite_session.execute(
        update(ResidualModelTrainingRun)
        .where(ResidualModelTrainingRun.id == training_run_id)
        .values(finished_at=cutoff + timedelta(seconds=1))
    )
    await sqlite_session.commit()

    with pytest.raises(ResidualReplayTrainedAuthorityError):
        await execute_residual_prediction(
            sqlite_session,
            request=ResidualPredictionRequest(
                model_run_id=training_run_id,
                task9_run_id=task9_run_id,
                feature_analytics_build_run_id=feature_build_id,
                supplemental_feature_values=_supplemental_features(as_of_date=as_of_date),
            ),
            model_policy="replay_trained_model",
        )


async def test_residual_prediction_allows_valid_persisted_replay_trained_authority(
    sqlite_session: AsyncSession,
) -> None:
    (
        task9_run_id,
        feature_build_id,
        training_run_id,
        as_of_date,
        cutoff,
    ) = await _seed_eligible_prediction_fixture(
        sqlite_session,
        replay_training_provenance=True,
    )
    replay_created_at = cutoff + timedelta(days=1)
    await sqlite_session.execute(
        update(ResidualModelTrainingRun)
        .where(ResidualModelTrainingRun.id == training_run_id)
        .values(finished_at=replay_created_at)
    )
    await sqlite_session.execute(
        update(ResidualModelArtifact)
        .where(ResidualModelArtifact.training_run_id == training_run_id)
        .values(created_at=replay_created_at)
    )
    await sqlite_session.commit()

    prediction_result, prediction_run_id = await execute_residual_prediction(
        sqlite_session,
        request=ResidualPredictionRequest(
            model_run_id=training_run_id,
            task9_run_id=task9_run_id,
            feature_analytics_build_run_id=feature_build_id,
            supplemental_feature_values=_supplemental_features(as_of_date=as_of_date),
        ),
        model_policy="replay_trained_model",
    )

    persisted_prediction = await sqlite_session.get(ResidualModelPredictionRun, prediction_run_id)
    assert persisted_prediction is not None
    assert prediction_result.mode == "residual_corrected"
    assert "model_artifact_visibility" not in prediction_result.input_snapshot
    assert (persisted_prediction.typed_attempt or {})["model_artifact_visibility"][
        "mode"
    ] == "replay_trained_model"


@pytest.mark.parametrize(
    ("mutation",),
    (
        ("future_training_cutoff",),
        ("dataset_mismatch",),
        ("training_manifest_mismatch",),
        ("manifest_mismatch",),
        ("model_config_mismatch",),
        ("config_mismatch",),
        ("typed_attempt_missing",),
        ("typed_attempt_mismatch",),
    ),
)
async def test_replay_prediction_requires_persisted_task12_authority_bindings(
    sqlite_session: AsyncSession,
    mutation: str,
) -> None:
    (
        task9_run_id,
        feature_build_id,
        training_run_id,
        as_of_date,
        cutoff,
    ) = await _seed_eligible_prediction_fixture(
        sqlite_session,
        replay_training_provenance=True,
    )
    if mutation == "future_training_cutoff":
        await _mutate_replay_authority_context(
            sqlite_session,
            training_run_id=training_run_id,
            input_snapshot_updates={
                "training_cutoff_at": (cutoff + timedelta(seconds=1)).isoformat(),
            },
            typed_attempt_updates={
                "training_cutoff_at": (cutoff + timedelta(seconds=1)).isoformat(),
            },
        )
    elif mutation == "dataset_mismatch":
        await _mutate_replay_authority_context(
            sqlite_session,
            training_run_id=training_run_id,
            input_snapshot_updates={"training_dataset_hash": "f" * 64},
            typed_attempt_updates={"training_dataset_hash": "f" * 64},
        )
    elif mutation == "training_manifest_mismatch":
        await _mutate_replay_authority_context(
            sqlite_session,
            training_run_id=training_run_id,
            input_snapshot_updates={"training_manifest_hash": "f" * 64},
            typed_attempt_updates={"training_manifest_hash": "f" * 64},
        )
    elif mutation == "manifest_mismatch":
        await _mutate_replay_authority_context(
            sqlite_session,
            training_run_id=training_run_id,
            input_snapshot_updates={"task10_manifest_hash": "f" * 64},
            typed_attempt_updates={"task10_manifest_hash": "f" * 64},
        )
    elif mutation == "model_config_mismatch":
        await _mutate_replay_authority_context(
            sqlite_session,
            training_run_id=training_run_id,
            input_snapshot_updates={"model_config_hash": "e" * 64},
            typed_attempt_updates={"model_config_hash": "e" * 64},
        )
    elif mutation == "config_mismatch":
        await _mutate_replay_authority_context(
            sqlite_session,
            training_run_id=training_run_id,
            input_snapshot_updates={"task10_config_hash": "e" * 64},
            typed_attempt_updates={"task10_config_hash": "e" * 64},
        )
    elif mutation == "typed_attempt_missing":
        await _mutate_replay_authority_context(
            sqlite_session,
            training_run_id=training_run_id,
            remove_typed_attempt=True,
        )
    else:
        await _mutate_replay_authority_context(
            sqlite_session,
            training_run_id=training_run_id,
            typed_attempt_updates={"task9_result_hash": "d" * 64},
        )

    with pytest.raises(ResidualReplayTrainedAuthorityError):
        await execute_residual_prediction(
            sqlite_session,
            request=ResidualPredictionRequest(
                model_run_id=training_run_id,
                task9_run_id=task9_run_id,
                feature_analytics_build_run_id=feature_build_id,
                supplemental_feature_values=_supplemental_features(as_of_date=as_of_date),
            ),
            model_policy="replay_trained_model",
        )


async def test_replay_prediction_rejects_persisted_future_training_row(
    sqlite_session: AsyncSession,
) -> None:
    (
        task9_run_id,
        feature_build_id,
        training_run_id,
        as_of_date,
        _cutoff,
    ) = await _seed_eligible_prediction_fixture(
        sqlite_session,
        replay_training_provenance=True,
        training_cutoff_at=datetime(2026, 2, 26, 23, 59, 59, tzinfo=UTC),
        label_finished_at=datetime(2026, 3, 4, 12, 0, tzinfo=UTC),
    )
    with pytest.raises(ResidualReplayTrainedAuthorityError, match="training observation"):
        await execute_residual_prediction(
            sqlite_session,
            request=ResidualPredictionRequest(
                model_run_id=training_run_id,
                task9_run_id=task9_run_id,
                feature_analytics_build_run_id=feature_build_id,
                supplemental_feature_values=_supplemental_features(as_of_date=as_of_date),
            ),
            model_policy="replay_trained_model",
        )
    assert (
        await sqlite_session.scalar(
            select(ResidualModelPredictionRun).where(
                ResidualModelPredictionRun.training_run_id == training_run_id
            )
        )
        is None
    )


async def test_replay_prediction_rejects_persisted_future_label_availability(
    sqlite_session: AsyncSession,
) -> None:
    (
        task9_run_id,
        feature_build_id,
        training_run_id,
        as_of_date,
        _cutoff,
    ) = await _seed_eligible_prediction_fixture(
        sqlite_session,
        replay_training_provenance=True,
        label_finished_at=datetime(2026, 3, 6, 12, 0, tzinfo=UTC),
    )

    with pytest.raises(ResidualReplayTrainedAuthorityError, match="label availability"):
        await execute_residual_prediction(
            sqlite_session,
            request=ResidualPredictionRequest(
                model_run_id=training_run_id,
                task9_run_id=task9_run_id,
                feature_analytics_build_run_id=feature_build_id,
                supplemental_feature_values=_supplemental_features(as_of_date=as_of_date),
            ),
            model_policy="replay_trained_model",
        )


async def test_prediction_payload_hash_uses_full_base_result_for_pre_pr192_rows(
    sqlite_session: AsyncSession,
) -> None:
    (
        task9_run_id,
        feature_build_id,
        training_run_id,
        as_of_date,
        _cutoff,
    ) = await _seed_eligible_prediction_fixture(sqlite_session)

    prediction_result, prediction_run_id = await execute_residual_prediction(
        sqlite_session,
        request=ResidualPredictionRequest(
            model_run_id=training_run_id,
            task9_run_id=task9_run_id,
            feature_analytics_build_run_id=feature_build_id,
            supplemental_feature_values=_supplemental_features(as_of_date=as_of_date),
        ),
    )
    persisted_prediction = await sqlite_session.get(ResidualModelPredictionRun, prediction_run_id)
    assert persisted_prediction is not None
    assert "model_artifact_visibility" not in persisted_prediction.input_snapshot

    # A true pre-PR192 row has no input_snapshot audit field and stores the
    # original full-result payload hash, including prediction_hash.
    expected_base_hash = canonical_payload_hash(
        canonical_json_value(prediction_result.model_dump(mode="python"))
    )
    assert _prediction_payload_hash(prediction_result) == expected_base_hash
    assert persisted_prediction.canonical_payload_hash == expected_base_hash
    loaded = await load_residual_prediction_run_by_id(sqlite_session, run_id=prediction_run_id)
    assert loaded is not None
    assert loaded.input_snapshot.get("model_artifact_visibility") is None


async def test_replay_prediction_requires_persisted_exact_forecast_cutoff(
    sqlite_session: AsyncSession,
) -> None:
    (
        task9_run_id,
        feature_build_id,
        training_run_id,
        as_of_date,
        _cutoff,
    ) = await _seed_eligible_prediction_fixture(sqlite_session)
    task9_run = await sqlite_session.get(HarvestStateRun, task9_run_id)
    assert task9_run is not None
    task9_run.is_replay = True
    task9_run.forecast_effective_cutoff_at = None
    await sqlite_session.commit()

    with pytest.raises(
        ResidualPredictionApplicationIntegrityError,
        match="REPLAY_FORECAST_EFFECTIVE_CUTOFF_MISSING",
    ):
        await execute_residual_prediction(
            sqlite_session,
            request=ResidualPredictionRequest(
                model_run_id=training_run_id,
                task9_run_id=task9_run_id,
                feature_analytics_build_run_id=feature_build_id,
                supplemental_feature_values=_supplemental_features(as_of_date=as_of_date),
            ),
            model_policy="replay_trained_model",
            execution_context={"task12_replay": {"model_policy": "replay_trained_model"}},
        )
