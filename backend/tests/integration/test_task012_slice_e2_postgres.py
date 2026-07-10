"""PostgreSQL evidence for TASK-012 Slice E2.

These tests deliberately use the real Task 9/Task 3 authorities and the
existing Task 10 application/persistence path.  No delegate or in-memory
idempotency substitute is allowed in this file.
"""

from __future__ import annotations

import asyncio
import copy
import os
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from backend.app.db.session import AsyncSessionMaker
from backend.app.models.harvest_state import HarvestStateRun
from backend.app.models.residual_model import ResidualModelPredictionRun
from backend.app.residual_model.config import load_residual_model_config_from_snapshot
from backend.app.residual_model.training_manifest import build_residual_training_manifest
from backend.app.rolling_backtest.canonical import sha256_payload
from backend.app.rolling_backtest.enums import Task10ModelPolicy
from backend.app.rolling_backtest.replay_trained_identity import (
    TrainingManifestPayload,
    project_replay_trained_identity,
)
from backend.app.rolling_backtest.replay_trained_service import (
    ReplayTrainedExecutionRequest,
    ReplayTrainedServiceBlockerError,
    ReplayTrainedServiceConflictError,
    _actual_input_rows,
    _actual_manifest_payload,
    _dataset_identity,
    _task10_model_config_projection,
    execute_replay_trained_prediction,
)
from backend.tests.integration.test_residual_model_persistence import _seed_prediction_fixture
from backend.tests.residual_model.test_training_manifest import (
    _config,
    _diverse_training_samples,
    _supplemental_features,
)

pytestmark = pytest.mark.integration


def _require_postgres() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("set RUN_POSTGRES_INTEGRATION=1 when PostgreSQL is available")


def _relaxed_task10_config():
    base = _config()
    snapshot = copy.deepcopy(base.snapshot)
    snapshot["eligibility"] = {
        **snapshot["eligibility"],
        "min_training_rows": 1,
        "min_seasons": 1,
        "min_factories": 1,
        "max_validation_wmape": 10.0,
        "require_improvement_over_structural": False,
        "max_fallback_rate": 1.0,
    }
    return load_residual_model_config_from_snapshot(snapshot)


async def _make_request(*, idempotency_key: str) -> ReplayTrainedExecutionRequest:
    fixture = await _seed_prediction_fixture()
    cutoff = datetime(2026, 3, 31, 23, 59, tzinfo=UTC)
    async with AsyncSessionMaker() as session:
        for run_id in (fixture["train_task9_run_id"], fixture["validation_task9_run_id"]):
            run = await session.get(HarvestStateRun, run_id)
            assert run is not None
            run.is_replay = True
            run.forecast_effective_cutoff_at = cutoff
            run.replay_executed_at = datetime(2026, 3, 1, tzinfo=UTC)
            run.replay_code_version = "task11-replay-fixture-v1"
            run.replay_run_correlation_id = f"fixture:{run_id}"
        await session.commit()

        samples = _diverse_training_samples(
            task9_run_id=fixture["train_task9_run_id"],
            label_build_run_id=fixture["train_label_build_run_id"],
            feature_build_run_id=fixture["train_feature_build_run_id"],
            validation_task9_run_id=fixture["validation_task9_run_id"],
            validation_label_build_run_id=fixture["validation_label_build_run_id"],
            validation_feature_build_run_id=fixture["validation_feature_build_run_id"],
            as_of_date=datetime(2026, 2, 28, tzinfo=UTC).date(),
            count=30,
        )
        rebuilt_rows = await build_residual_training_manifest(session, samples=samples)
        manifest_payload = _actual_manifest_payload(rebuilt_rows)
        training_rows, label_rows = _actual_input_rows(rebuilt_rows)
        dataset_hash = _dataset_identity(
            training_rows=training_rows,
            label_rows=label_rows,
            manifest_rows=manifest_payload,
        )
        config = _relaxed_task10_config()
        model_config = _task10_model_config_projection(config)
        task9_result_hash = str(
            await session.scalar(
                select(HarvestStateRun.result_hash).where(
                    HarvestStateRun.id == fixture["train_task9_run_id"]
                )
            )
        )
        replay_code_version = "task11-replay-fixture-v1"
        task9_binding = sha256_payload(
            {
                "task9_run_id": fixture["train_task9_run_id"],
                "task9_result_hash": task9_result_hash,
                "is_replay": True,
                "replay_code_version": replay_code_version,
            }
        )
        manifest = TrainingManifestPayload(
            replay_attempt_id="task12-fixture-attempt",
            replay_node_id="task12-fixture-node",
            scenario_id="task12-fixture-scenario",
            forecast_cutoff_at=cutoff,
            training_cutoff_at=cutoff,
            allowed_training_season_ids=(1, 2),
            feature_visibility_policy_version="task12-feature-v1",
            label_visibility_policy_version="task12-label-v1",
            artifact_visibility_policy_version="task12-artifact-v1",
            validation_policy_version="task12-validation-v1",
            training_dataset_hash=dataset_hash,
            task8_curve_identity="task8-fixture-authority",
            task9_replay_binding_identity=task9_binding,
            row_count=len(rebuilt_rows),
            excluded_row_count=sum(1 for row in rebuilt_rows if not row.include),
        )
        projection = project_replay_trained_identity(
            manifest=manifest,
            config=model_config,
            model_code_version="task10-replay-fixture-v1",
            task12_policy_version="task12-policy-v1",
        )
        artifact_identity = {
            "model_policy": Task10ModelPolicy.REPLAY_TRAINED_MODEL.value,
            "task12_policy_version": projection.task12_policy_version,
            "replay_attempt_id": projection.manifest.replay_attempt_id,
            "replay_node_id": projection.manifest.replay_node_id,
            "forecast_cutoff_at": projection.manifest.forecast_cutoff_at,
            "training_cutoff_at": projection.manifest.training_cutoff_at,
            "training_manifest_hash": projection.training_manifest_hash,
            "training_dataset_hash": projection.manifest.training_dataset_hash,
            "model_config_hash": projection.model_config_hash,
            "model_artifact_hash": projection.model_artifact_hash,
            "model_code_version": projection.model_code_version,
        }
        return ReplayTrainedExecutionRequest(
            model_policy=Task10ModelPolicy.REPLAY_TRAINED_MODEL,
            task12_policy_version="task12-policy-v1",
            replay_attempt_id="task12-fixture-attempt",
            replay_node_id="task12-fixture-node",
            scenario_id="task12-fixture-scenario",
            forecast_cutoff_at=cutoff,
            training_cutoff_at=cutoff,
            allowed_training_season_ids=(1, 2),
            training_manifest=manifest,
            model_config=model_config,
            model_code_version="task10-replay-fixture-v1",
            replay_code_version=replay_code_version,
            task9_run_id=fixture["train_task9_run_id"],
            task9_result_hash=task9_result_hash,
            is_replay=True,
            task10_config_snapshot=config.snapshot,
            manifest_rows_payload=tuple(manifest_payload),
            training_rows=tuple(training_rows),
            label_rows=tuple(label_rows),
            source_run_ids={"task9a_run_id": fixture["train_task9_run_id"]},
            artifact_identity_json=artifact_identity,
            artifact_identity_manifest=dict(artifact_identity),
            feature_actual_snapshot=None,
            idempotency_key=idempotency_key,
            caller_identity="integration:task12-e2",
            training_samples=tuple(samples),
            supplemental_feature_values=_supplemental_features(
                as_of_date=datetime(2026, 2, 28, tzinfo=UTC).date()
            ),
        )


async def test_postgres_slice_e2_real_success_and_fresh_reload() -> None:
    _require_postgres()
    request = await _make_request(idempotency_key="task12-e2-success")
    async with AsyncSessionMaker() as session:
        result = await execute_replay_trained_prediction(session, request=request)
        assert result.prediction_run_id > 0
        assert result.prediction_hash
        assert result.prediction_mode == "residual_corrected"
        assert result.training_eligibility_status == "eligible"
        prediction_row = await session.get(ResidualModelPredictionRun, result.prediction_run_id)
        assert prediction_row is not None
        context = prediction_row.input_snapshot["task12_replay"]
        assert context["idempotency_key"] == request.idempotency_key
        assert context["task10_training_run_id"] > 0
        assert context["task10_artifact_hashes"]
        assert context["audit_identity"] == result.audit_identity
        assert prediction_row.typed_attempt["task12_replay"]["audit_identity"] == (
            result.audit_identity
        )

    async with AsyncSessionMaker() as fresh_session:
        replayed = await execute_replay_trained_prediction(fresh_session, request=request)
    assert replayed.to_payload() == result.to_payload()


async def test_postgres_slice_e2_same_key_conflict_is_durable() -> None:
    _require_postgres()
    request = await _make_request(idempotency_key="task12-e2-conflict")
    async with AsyncSessionMaker() as session:
        await execute_replay_trained_prediction(session, request=request)
    with pytest.raises(ReplayTrainedServiceConflictError) as exc_info:
        async with AsyncSessionMaker() as session:
            await execute_replay_trained_prediction(
                session,
                request=replace(request, caller_identity="integration:other-caller"),
            )
    assert "idempotency_key_payload_mismatch" in str(exc_info.value)


async def test_postgres_slice_e2_changed_dataset_blocks_before_training() -> None:
    _require_postgres()
    request = await _make_request(idempotency_key="task12-e2-dataset-mismatch")
    changed_rows = list(request.training_rows)
    changed_rows[0] = {**changed_rows[0], "value": "999999"}
    with pytest.raises(ReplayTrainedServiceBlockerError) as exc_info:
        async with AsyncSessionMaker() as session:
            await execute_replay_trained_prediction(
                session,
                request=replace(request, training_rows=tuple(changed_rows)),
            )
    assert exc_info.value.blocker_code == "task12_training_dataset_mismatch"


async def test_postgres_slice_e2_non_replay_task9_authority_blocks() -> None:
    _require_postgres()
    request = await _make_request(idempotency_key="task12-e2-task9-authority")
    async with AsyncSessionMaker() as session:
        run = await session.get(HarvestStateRun, request.task9_run_id)
        assert run is not None
        run.is_replay = False
        await session.commit()
        with pytest.raises(ReplayTrainedServiceBlockerError) as exc_info:
            await execute_replay_trained_prediction(session, request=request)
    assert "task9_replay_run_missing_or_not_replay" in exc_info.value.mismatched_fields


async def test_postgres_slice_e2_task9_hash_mismatch_blocks() -> None:
    _require_postgres()
    request = await _make_request(idempotency_key="task12-e2-task9-hash")
    bad_hash = "f" * 64
    bad_binding = sha256_payload(
        {
            "task9_run_id": request.task9_run_id,
            "task9_result_hash": bad_hash,
            "is_replay": True,
            "replay_code_version": request.replay_code_version,
        }
    )
    bad_manifest = replace(
        request.training_manifest,
        task9_replay_binding_identity=bad_binding,
    )
    with pytest.raises(ReplayTrainedServiceBlockerError) as exc_info:
        async with AsyncSessionMaker() as session:
            await execute_replay_trained_prediction(
                session,
                request=replace(
                    request,
                    task9_result_hash=bad_hash,
                    training_manifest=bad_manifest,
                ),
            )
    assert "task9_result_hash_mismatch" in exc_info.value.mismatched_fields


async def test_postgres_slice_e2_concurrent_exact_requests_share_persisted_result() -> None:
    _require_postgres()
    request = await _make_request(idempotency_key="task12-e2-concurrency")

    async def run_once() -> object:
        async with AsyncSessionMaker() as session:
            return await execute_replay_trained_prediction(session, request=request)

    first, second = await asyncio.gather(run_once(), run_once())
    assert first.to_payload() == second.to_payload()
