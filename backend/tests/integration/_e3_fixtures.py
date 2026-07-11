"""Shared fixtures and request builders for TASK-012 Slice E3 PostgreSQL contracts.

This helper module deliberately does NOT start with ``test_`` so the
default pytest collection skips it. The Slice E3 test functions live
in the domain-2 owned file
``backend/tests/integration/test_rolling_backtest_orchestration.py``
and import the builders from here. This keeps each pytest node in the
PR CI ``postgres-domain-2`` shard and the ``main`` canary
``full-suite-canary`` shard executed exactly once, satisfying the
workflow hard boundary.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from sqlalchemy import select

from backend.app.db.session import AsyncSessionMaker
from backend.app.models.harvest_state import HarvestStateRun
from backend.app.rolling_backtest.canonical import sha256_payload
from backend.app.rolling_backtest.replay_trained_identity import (
    TrainingManifestPayload,
    project_replay_trained_identity,
)
from backend.app.rolling_backtest.replay_trained_service import (
    ReplayTrainedExecutionRequest,
    _actual_input_rows,
    _actual_manifest_payload,
    _dataset_identity,
    _task10_model_config_projection,
    execute_replay_trained_prediction,
)
from backend.tests.integration.test_residual_model_persistence import (
    _seed_prediction_fixture,
)
from backend.tests.residual_model.test_training_manifest import (
    _config,
    _diverse_training_samples,
    _supplemental_features,
)


def require_postgres() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest_skip("set RUN_POSTGRES_INTEGRATION=1 when PostgreSQL is available")


def pytest_skip(reason: str) -> None:
    import pytest

    pytest.skip(reason)


def relaxed_task10_config():
    snapshot = dict(_config().snapshot)
    snapshot["eligibility"] = {
        **snapshot["eligibility"],
        "min_training_rows": 1,
        "min_seasons": 1,
        "min_factories": 1,
        "max_validation_wmape": 10.0,
        "require_improvement_over_structural": False,
        "max_fallback_rate": 1.0,
    }
    from backend.app.residual_model.config import load_residual_model_config_from_snapshot

    return load_residual_model_config_from_snapshot(snapshot)


async def make_replay_trained_request(*, idempotency_key: str) -> ReplayTrainedExecutionRequest:
    """Build a complete valid :class:`ReplayTrainedExecutionRequest`.

    Used by the Slice E3 PG tests in
    ``test_rolling_backtest_orchestration.py`` so that they can mutate
    exactly one field on a copy of the request, instead of starting
    from a half-empty dict (which would mask the true failure cause).
    """
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
        from backend.app.residual_model.training_manifest import (
            build_residual_training_manifest,
        )

        rebuilt_rows = await build_residual_training_manifest(session, samples=samples)
        manifest_payload = _actual_manifest_payload(rebuilt_rows)
        training_rows, label_rows = _actual_input_rows(rebuilt_rows)
        dataset_hash = _dataset_identity(
            training_rows=training_rows,
            label_rows=label_rows,
            manifest_rows=manifest_payload,
        )
        config = relaxed_task10_config()
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
            replay_attempt_id="task12-e3-fixture-attempt",
            replay_node_id="task12-e3-fixture-node",
            scenario_id="task12-e3-fixture-scenario",
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
            "model_policy": "replay_trained_model",
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
            model_policy="replay_trained_model",
            task12_policy_version="task12-policy-v1",
            replay_attempt_id="task12-e3-fixture-attempt",
            replay_node_id="task12-e3-fixture-node",
            scenario_id="task12-e3-fixture-scenario",
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
            caller_identity="integration:task12-e3",
            training_samples=tuple(samples),
            supplemental_feature_values=_supplemental_features(
                as_of_date=datetime(2026, 2, 28, tzinfo=UTC).date()
            ),
        )


async def post_via_service(request: ReplayTrainedExecutionRequest) -> int:
    async with AsyncSessionMaker() as session:
        result = await execute_replay_trained_prediction(session, request=request)
    return int(result.prediction_run_id)
