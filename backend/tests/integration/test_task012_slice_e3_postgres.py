"""PostgreSQL evidence for TASK-012 Slice E3 HTTP API.

These tests exercise the real HTTP transport through
``ASGITransport(create_app())`` against the real PostgreSQL database
and the real Slice E2 application service. They prove the frozen
POST/GET status matrix, idempotent replay semantics, and exact
prediction retrieval without any fake response.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy import select

from backend.app.db.session import AsyncSessionMaker
from backend.app.main import create_app
from backend.app.models.harvest_state import HarvestStateRun
from backend.app.models.residual_model import ResidualModelPredictionRun
from backend.app.rolling_backtest.canonical import sha256_payload
from backend.app.rolling_backtest.replay_trained_service import (
    ReplayTrainedExecutionRequest,
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
        from backend.app.rolling_backtest.replay_trained_identity import (
            TrainingManifestPayload,
            project_replay_trained_identity,
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


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    _require_postgres()
    app = create_app()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


async def _post_via_service(request: ReplayTrainedExecutionRequest) -> int:
    async with AsyncSessionMaker() as session:
        result = await execute_replay_trained_prediction(session, request=request)
    return int(result.prediction_run_id)


@pytest.mark.integration
async def test_postgres_post_first_execution_returns_201_and_persists(
    client: httpx.AsyncClient,
) -> None:
    request = await _make_request(idempotency_key="task12-e3-post-201")
    body = request.to_payload()
    body["idempotency_key"] = "task12-e3-post-201"
    response = await client.post("/api/v1/rolling-backtest/replay-trained-predictions", json=body)
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["prediction_run_id"] > 0
    assert payload["model_policy"] == "replay_trained_model"
    assert payload["audit_identity"]
    assert payload["task9_run_id"] == request.task9_run_id
    assert payload["idempotency_key"] == "task12-e3-post-201"

    # Persisted prediction reloads identically from the DB
    async with AsyncSessionMaker() as session:
        row = await session.get(ResidualModelPredictionRun, payload["prediction_run_id"])
        assert row is not None
        context = row.input_snapshot["task12_replay"]
        assert context["idempotency_key"] == "task12-e3-post-201"
        assert row.typed_attempt["task12_replay"]["audit_identity"] == payload["audit_identity"]


@pytest.mark.integration
async def test_postgres_post_exact_replay_returns_200_with_same_envelope(
    client: httpx.AsyncClient,
) -> None:
    request = await _make_request(idempotency_key="task12-e3-post-200")
    body = request.to_payload()
    body["idempotency_key"] = "task12-e3-post-200"

    first = await client.post("/api/v1/rolling-backtest/replay-trained-predictions", json=body)
    assert first.status_code == 201, first.text
    first_payload = first.json()

    second = await client.post("/api/v1/rolling-backtest/replay-trained-predictions", json=body)
    assert second.status_code == 200, second.text
    assert second.json() == first_payload

    async with AsyncSessionMaker() as session:
        count = await session.scalar(
            select(__import__("sqlalchemy").func.count())
            .select_from(ResidualModelPredictionRun)
            .where(
                ResidualModelPredictionRun.input_snapshot["task12_replay"][
                    "idempotency_key"
                ].as_string()
                == "task12-e3-post-200"
            )
        )
        # Replay must not create a second semantic prediction row
        assert count == 1


@pytest.mark.integration
async def test_postgres_post_idempotency_conflict_returns_409(
    client: httpx.AsyncClient,
) -> None:
    request = await _make_request(idempotency_key="task12-e3-post-409")
    body = request.to_payload()
    body["idempotency_key"] = "task12-e3-post-409"

    first = await client.post("/api/v1/rolling-backtest/replay-trained-predictions", json=body)
    assert first.status_code == 201, first.text

    # Reuse same idempotency_key with a different canonical request
    body["caller_identity"] = "integration:different-caller"
    second = await client.post("/api/v1/rolling-backtest/replay-trained-predictions", json=body)
    assert second.status_code == 409, second.text
    body_payload = second.json()
    assert body_payload["error"]["code"] == "TASK012_REPLAY_TRAINED_CONFLICT"
    assert body_payload["error"]["identity"]["mismatched_fields"] == [
        "idempotency_key_payload_mismatch"
    ]


@pytest.mark.integration
async def test_postgres_post_invalid_request_returns_422(
    client: httpx.AsyncClient,
) -> None:
    cases: list[tuple[dict[str, object], str]] = [
        ({"idempotency_key": ""}, "empty idempotency_key"),
        ({"idempotency_key": "idem-e3-422"}, "missing required identity fields"),
        (
            {
                "idempotency_key": "idem-e3-422",
                "model_policy": "replay_trained_model",
                "task9_result_hash": "Z" * 64,
            },
            "uppercase hash",
        ),
        (
            {
                "idempotency_key": "idem-e3-422",
                "model_policy": "replay_trained_model",
                "forecast_cutoff_at": "2026-03-15T12:00:00",
                "training_cutoff_at": "2026-03-15T12:00:00Z",
            },
            "naive datetime (no tz)",
        ),
        (
            {
                "idempotency_key": "idem-e3-422",
                "model_policy": "historically_available_model",
            },
            "policy is not replay_trained_model",
        ),
    ]
    for body, label in cases:
        response = await client.post(
            "/api/v1/rolling-backtest/replay-trained-predictions", json=body
        )
        assert response.status_code == 422, f"{label}: {response.text}"
        assert response.json()["error"]["code"] == "TASK012_REPLAY_TRAINED_INPUT_INVALID"


@pytest.mark.integration
async def test_postgres_post_missing_task9_authority_returns_409_blocker(
    client: httpx.AsyncClient,
) -> None:
    request = await _make_request(idempotency_key="task12-e3-post-blocker")
    async with AsyncSessionMaker() as session:
        run = await session.get(HarvestStateRun, request.task9_run_id)
        assert run is not None
        run.is_replay = False
        run.forecast_effective_cutoff_at = None
        run.replay_executed_at = None
        run.replay_code_version = None
        run.replay_run_correlation_id = None
        await session.commit()

    body = request.to_payload()
    body["idempotency_key"] = "task12-e3-post-blocker"
    response = await client.post("/api/v1/rolling-backtest/replay-trained-predictions", json=body)
    # Amendment §7.2 maps blocker / 404 to stable 409 envelope with TASK-012 code
    assert response.status_code == 409, response.text
    payload = response.json()
    assert payload["error"]["code"] == "TASK012_REPLAY_TRAINED_BLOCKED"
    assert (
        "task9_replay_run_missing_or_not_replay"
        in payload["error"]["identity"]["mismatched_fields"]
    )


@pytest.mark.integration
async def test_postgres_get_exact_prediction_returns_200_with_persisted_identity(
    client: httpx.AsyncClient,
) -> None:
    request = await _make_request(idempotency_key="task12-e3-get-200")
    prediction_run_id = await _post_via_service(request)

    response = await client.get(
        f"/api/v1/rolling-backtest/replay-trained-predictions/{prediction_run_id}"
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["prediction_run_id"] == prediction_run_id
    assert payload["model_policy"] == "replay_trained_model"
    assert payload["task9_run_id"] == request.task9_run_id
    assert payload["audit_identity"]


@pytest.mark.integration
async def test_postgres_get_missing_prediction_returns_404(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/api/v1/rolling-backtest/replay-trained-predictions/999999")
    assert response.status_code == 404, response.text
    body = response.json()
    assert body["error"]["code"] == "TASK012_REPLAY_TRAINED_NOT_FOUND"
    assert body["error"]["identity"]["prediction_run_id"] == 999999


@pytest.mark.integration
async def test_postgres_get_does_not_re_execute_or_mutate_state(
    client: httpx.AsyncClient,
) -> None:
    request = await _make_request(idempotency_key="task12-e3-get-noop")
    prediction_run_id = await _post_via_service(request)

    async with AsyncSessionMaker() as session:
        before_count = await session.scalar(
            select(__import__("sqlalchemy").func.count()).select_from(ResidualModelPredictionRun)
        )

    # Hit the GET endpoint 3 times in a row; nothing should change in the DB
    for _ in range(3):
        response = await client.get(
            f"/api/v1/rolling-backtest/replay-trained-predictions/{prediction_run_id}"
        )
        assert response.status_code == 200

    async with AsyncSessionMaker() as session:
        after_count = await session.scalar(
            select(__import__("sqlalchemy").func.count()).select_from(ResidualModelPredictionRun)
        )
    assert before_count == after_count


@pytest.mark.integration
async def test_postgres_get_rejects_no_implicit_latest_or_current(
    client: httpx.AsyncClient,
) -> None:
    # No "latest", "current", "most_recent", or "now()" selector exists.
    # The path parameter is the ONLY selector; sending a non-integer
    # path is rejected by FastAPI before the route runs.
    response = await client.get("/api/v1/rolling-backtest/replay-trained-predictions/latest")
    # FastAPI Path(..., ge=1) coerces; the request is rejected.
    assert response.status_code in (404, 422)
