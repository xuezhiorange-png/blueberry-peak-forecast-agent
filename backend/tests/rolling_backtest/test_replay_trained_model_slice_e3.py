"""TASK-012 Slice E3 — focused unit tests for the replay-trained HTTP API.

These tests are layered on top of the §10 contract obligations
activated in ``test_replay_trained_model_slice_e1.py``. They cover
the thin HTTP adapter in ``backend.app.api.rolling_backtest_replay_trained``
with deterministic monkey-patches at the service boundary so the
tests do NOT require a live PostgreSQL.

The PostgreSQL-backed E2/E3 evidence tests live in
``backend/tests/integration/test_task012_slice_e3_postgres.py`` and
exercise the real Slice E2 service and the real HTTP transport
through a fresh session and ASGITransport.
"""

from __future__ import annotations

from typing import Any, cast

import httpx
import pytest
from httpx import ASGITransport

from backend.app.api import rolling_backtest_replay_trained
from backend.app.main import create_app
from backend.app.rolling_backtest.enums import Task10ModelPolicy
from backend.app.rolling_backtest.replay_trained_service import (
    ReplayTrainedExecutionRequest,
    ReplayTrainedExecutionResult,
    ReplayTrainedPersistedIdentity,
    ReplayTrainedPersistedIdentityIntegrityError,
    ReplayTrainedServiceBlockerError,
    ReplayTrainedServiceConflictError,
    ReplayTrainedServiceError,
    ReplayTrainedServiceNotFoundError,
)

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def app() -> Any:
    return create_app()


@pytest.fixture
def client(app: Any) -> Any:
    transport = ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _stub_result(*, created: bool = True) -> ReplayTrainedExecutionResult:
    """Build a deterministic E2 result object for unit testing.

    The ``created`` flag controls the 201/200 disposition that the
    HTTP layer reads from the service result. ``created=True`` means
    the service persisted a new prediction row (HTTP 201); ``created=False``
    means the service re-loaded a prior prediction for the same
    idempotency key + canonical request hash (HTTP 200).
    """
    created_flag = created

    class _Result:
        created = created_flag
        prediction_run_id = 4242
        prediction_hash = "a" * 64
        request_payload_hash = "a" * 64
        training_manifest_hash = "a" * 64
        model_config_hash = "a" * 64
        model_artifact_hash = "a" * 64
        task9_run_id = 91
        task9_result_hash = "a" * 64
        filtered_training_row_count = 3
        filtered_label_row_count = 2
        training_execution_status = "completed"
        training_eligibility_status = "eligible"
        prediction_execution_status = "completed"
        prediction_mode = "residual_corrected"
        audit_identity = "a" * 64

        def to_payload(self) -> dict[str, object]:
            return {
                "service_version": "task12-slice-e3-unit",
                "model_policy": Task10ModelPolicy.REPLAY_TRAINED_MODEL.value,
                "task12_policy_version": "task12-policy-unit",
                "replay_attempt_id": "attempt-unit",
                "replay_node_id": "node-unit",
                "scenario_id": "scenario-unit",
                "training_manifest_hash": "a" * 64,
                "training_dataset_hash": "a" * 64,
                "model_config_hash": "a" * 64,
                "model_artifact_hash": "a" * 64,
                "model_code_version": "task10-code-unit",
                "forecast_cutoff_at": "2026-03-15T12:00:00Z",
                "training_cutoff_at": "2026-03-14T12:00:00Z",
                "task9_run_id": 91,
                "task9_result_hash": "a" * 64,
                "prediction_run_id": 4242,
                "prediction_hash": "a" * 64,
                "request_payload_hash": "a" * 64,
                "filtered_training_row_count": 3,
                "filtered_label_row_count": 2,
                "training_execution_status": "completed",
                "training_eligibility_status": "eligible",
                "prediction_execution_status": "completed",
                "prediction_mode": "residual_corrected",
                "task10_training_run_id": 7,
                "task10_training_signature": "a" * 64,
                "task10_manifest_hash": "a" * 64,
                "task10_config_hash": "a" * 64,
                "task10_artifact_hashes": ["a" * 64],
                "idempotency_key": "idem-unit",
                "caller_identity": "test:unit",
                "no_implicit_selection": True,
                "no_cross_run_substitution": True,
            }

    return cast(ReplayTrainedExecutionResult, _Result())


def _stub_request(
    *,
    idempotency_key: str = "idem-unit",
) -> ReplayTrainedExecutionRequest:
    """Build a minimal E2 request whose ``to_payload()`` round-trips a
    complete valid request body. We instantiate a frozen dataclass by
    going through the same payload path the E2 service uses.

    The request body MUST satisfy the HTTP transport's strict nested
    schemas (P0-#5 spec): each manifest row carries every required
    field, each training sample / supplemental feature is fully
    typed, ``task10_config_snapshot`` and ``feature_actual_snapshot``
    are JSON-compatible, and ``source_run_ids`` uses the frozen
    ``SourceRunIdsSchema``. The E2 service dataclass still accepts
    the loose ``dict[str, object]`` shape internally — the strict
    contract is enforced at the wire boundary by the HTTP schema.
    """
    from datetime import UTC, datetime

    from backend.app.residual_model.config import load_residual_model_config
    from backend.app.rolling_backtest.canonical import sha256_payload
    from backend.app.rolling_backtest.replay_trained_identity import (
        ModelConfigPayload,
        TrainingManifestPayload,
    )
    from backend.app.rolling_backtest.replay_trained_service import (
        FeatureValue,
    )

    # Compute the expected task9_replay_binding_identity from the same
    # inputs the E2 _validate_request recomputes (see
    # replay_trained_service._validate_request).
    expected_binding = sha256_payload(
        {
            "task9_run_id": 91,
            "task9_result_hash": "9" * 64,
            "is_replay": True,
            "replay_code_version": "task12-unit-replay-v1",
        }
    )

    manifest = TrainingManifestPayload(
        replay_attempt_id="attempt-unit",
        replay_node_id="node-unit",
        scenario_id="scenario-unit",
        forecast_cutoff_at=datetime(2026, 3, 15, 12, 0, 0, tzinfo=UTC),
        training_cutoff_at=datetime(2026, 3, 14, 12, 0, 0, tzinfo=UTC),
        allowed_training_season_ids=(2023, 2024, 2025),
        feature_visibility_policy_version="task12-unit-feature-v1",
        label_visibility_policy_version="task12-unit-label-v1",
        artifact_visibility_policy_version="task12-unit-artifact-v1",
        validation_policy_version="task12-unit-validation-v1",
        training_dataset_hash="1" * 64,
        task8_curve_identity="task8-curve-unit",
        task9_replay_binding_identity=expected_binding,
        row_count=2,
        excluded_row_count=0,
    )
    model_config = ModelConfigPayload(
        algorithm_family="task12-unit-contract",
        hyperparameters={"max_depth": 3, "shuffle": False},
        random_seed=20260710,
        deterministic_serialization_version="task12-unit-json-v1",
    )
    config = load_residual_model_config(__import__("pathlib").Path("configs/residual_model.yaml"))
    snapshot = dict(config.snapshot)
    snapshot["eligibility"] = {
        **dict(snapshot["eligibility"]),
        "min_training_rows": 0,
        "min_seasons": 0,
        "min_factories": 0,
        "max_validation_wmape": 10.0,
        "require_improvement_over_structural": False,
        "max_fallback_rate": 1.0,
    }
    artifact_payload = {
        "model_policy": Task10ModelPolicy.REPLAY_TRAINED_MODEL.value,
        "task12_policy_version": "task12-policy-unit",
        "replay_attempt_id": "attempt-unit",
        "replay_node_id": "node-unit",
        "forecast_cutoff_at": "2026-03-15T12:00:00Z",
        "training_cutoff_at": "2026-03-14T12:00:00Z",
        "training_manifest_hash": "a" * 64,
        "training_dataset_hash": "a" * 64,
        "model_config_hash": "a" * 64,
        "model_artifact_hash": "a" * 64,
        "model_code_version": "task10-code-unit",
    }
    # Build the strict manifest row payload (one minimal row that
    # satisfies every required field of :class:`ManifestRowSchema`).
    manifest_row_dict: dict[str, object] = {
        "season_id": 2025,
        "destination_factory_id": 1,
        "task9_run_id": 91,
        "task9_result_hash": "9" * 64,
        "as_of_date": "2026-03-13",
        "target_arrival_local_date": "2026-03-14",
        "forecast_horizon_days": 1,
        "label_actual_snapshot": {
            "build_run_id": 1,
            "source_max_raw_id": 100,
            "aggregation_version": "task12-unit-agg-v1",
            "config_hash": "a" * 64,
            "source_cutoff": "2026-03-13T00:00:00Z",
        },
        "feature_actual_snapshot": {
            "build_run_id": 2,
            "source_max_raw_id": 100,
            "aggregation_version": "task12-unit-agg-v1",
            "config_hash": "b" * 64,
            "source_cutoff": "2026-03-13T00:00:00Z",
        },
        "observed_effective_receipt_kg": 10.0,
        "structural_p50_kg": 1.0,
        "structural_p80_kg": 2.0,
        "structural_p90_kg": 3.0,
        "residual_label_kg": 0.0,
        "feature_values": [],
        "feature_visibility_audit": None,
        "feature_vector_hash": "a" * 64,
        "feature_visibility_audit_hash": "b" * 64,
        "split": "train",
        "include": True,
        "sample_weight": 1.0,
        "exclusion_reason": None,
        "source_refs": ["unit"],
    }
    sample_request = ReplayTrainedExecutionRequest(
        model_policy=Task10ModelPolicy.REPLAY_TRAINED_MODEL,
        task12_policy_version="task12-policy-unit",
        replay_attempt_id="attempt-unit",
        replay_node_id="node-unit",
        scenario_id="scenario-unit",
        forecast_cutoff_at=datetime(2026, 3, 15, 12, 0, 0, tzinfo=UTC),
        training_cutoff_at=datetime(2026, 3, 14, 12, 0, 0, tzinfo=UTC),
        allowed_training_season_ids=(2023, 2024, 2025),
        training_manifest=manifest,
        model_config=model_config,
        model_code_version="task10-code-unit",
        replay_code_version="task12-unit-replay-v1",
        task9_run_id=91,
        task9_result_hash="9" * 64,
        is_replay=True,
        task10_config_snapshot=snapshot,
        manifest_rows_payload=(manifest_row_dict,),
        training_rows=(
            {"observation_date": "2026-03-13", "value": 1},
            {"observation_date": "2026-03-14", "value": 2},
        ),
        label_rows=(
            {
                "observation_date": "2026-03-13",
                "label_availability_date": "2026-03-14",
                "value": 10,
            },
        ),
        source_run_ids={"task9a_run_id": 91},
        artifact_identity_json=artifact_payload,
        artifact_identity_manifest=dict(artifact_payload),
        feature_actual_snapshot={"source": "unit"},
        idempotency_key=idempotency_key,
        caller_identity="test:unit",
        training_samples=(
            __import__(
                "backend.app.residual_model.schemas",
                fromlist=["ResidualTrainingSampleSpec"],
            ).ResidualTrainingSampleSpec(
                task9_run_id=91,
                label_analytics_build_run_id=1,
                feature_analytics_build_run_id=2,
                split="train",
            ),
        ),
        supplemental_feature_values=cast(tuple[FeatureValue, ...], ()),
    )
    return sample_request


# ---------------------------------------------------------------------------
# POST: 201 first execution (service returns created=True), 200 exact replay
# (service returns created=False). The HTTP layer MUST NOT recompute the
# disposition; it MUST read result.created from the service.
# ---------------------------------------------------------------------------


async def test_post_returns_201_then_200_for_exact_replay(
    monkeypatch: pytest.MonkeyPatch,
    client: Any,
) -> None:
    """POST first-execution returns 201; the same exact canonical request
    returns 200 with the same envelope. The service is the single source
    of truth for the canonical payload AND the 201/200 disposition.
    """
    recorded: list[bool] = []

    async def _fake_execute(
        session: object, *, request: ReplayTrainedExecutionRequest
    ) -> ReplayTrainedExecutionResult:
        is_replay = bool(recorded)
        recorded.append(is_replay)
        return _stub_result(created=not is_replay)

    monkeypatch.setattr(
        rolling_backtest_replay_trained,
        "execute_replay_trained_prediction",
        _fake_execute,
    )

    request = _stub_request(idempotency_key="idem-post-201-then-200")
    body = request.to_payload()
    body["idempotency_key"] = "idem-post-201-then-200"

    async with client as c:
        first = await c.post("/api/v1/rolling-backtest/replay-trained-predictions", json=body)
        assert first.status_code == 201, first.text
        first_payload = first.json()
        assert first_payload["disposition"] == "created"
        assert first_payload["prediction_run_id"] == 4242
        assert first_payload["model_policy"] == "replay_trained_model"

        second = await c.post("/api/v1/rolling-backtest/replay-trained-predictions", json=body)
        assert second.status_code == 200, second.text
        second_payload = second.json()
        assert second_payload["disposition"] == "idempotent_replay"
        # All canonical identity fields must match; only ``disposition`` may differ
        for key, value in first_payload.items():
            if key == "disposition":
                continue
            assert second_payload.get(key) == value, (key, value, second_payload.get(key))


# ---------------------------------------------------------------------------
# POST: 422 for non-object body (Pydantic schema validation)
# ---------------------------------------------------------------------------


async def test_post_returns_422_for_non_object_body(client: Any) -> None:
    async with client as c:
        response = await c.post(
            "/api/v1/rolling-backtest/replay-trained-predictions", json=[1, 2, 3]
        )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "TASK012_REPLAY_TRAINED_INPUT_INVALID"
    assert body["error"]["blocker"] is None
    assert body["error"]["identity"] == {}


# ---------------------------------------------------------------------------
# POST: 422 for missing identity (Pydantic strict schema)
# ---------------------------------------------------------------------------


async def test_post_returns_422_for_missing_identity(
    monkeypatch: pytest.MonkeyPatch,
    client: Any,
) -> None:
    async def _fake_execute(
        session: object, *, request: ReplayTrainedExecutionRequest
    ) -> ReplayTrainedExecutionResult:
        return _stub_result()

    monkeypatch.setattr(
        rolling_backtest_replay_trained,
        "execute_replay_trained_prediction",
        _fake_execute,
    )

    async with client as c:
        response = await c.post(
            "/api/v1/rolling-backtest/replay-trained-predictions",
            json={"idempotency_key": "idem-missing"},
        )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "TASK012_REPLAY_TRAINED_INPUT_INVALID"


# ---------------------------------------------------------------------------
# POST: 409 for idempotency / canonical hash conflict (service raises)
# ---------------------------------------------------------------------------


async def test_post_returns_409_for_idempotency_conflict(
    monkeypatch: pytest.MonkeyPatch,
    client: Any,
) -> None:
    async def _raise_conflict(
        session: object, *, request: ReplayTrainedExecutionRequest
    ) -> ReplayTrainedExecutionResult:
        raise ReplayTrainedServiceConflictError(
            "idempotency_key_payload_mismatch: internal stack trace /var/secrets/creds",
            mismatched_fields=("idempotency_key_payload_mismatch",),
        )

    monkeypatch.setattr(
        rolling_backtest_replay_trained,
        "execute_replay_trained_prediction",
        _raise_conflict,
    )

    request = _stub_request(idempotency_key="idem-conflict")
    body = request.to_payload()
    body["idempotency_key"] = "idem-conflict"

    async with client as c:
        response = await c.post("/api/v1/rolling-backtest/replay-trained-predictions", json=body)
    assert response.status_code == 409
    body_payload = response.json()
    assert body_payload["error"]["code"] == "TASK012_REPLAY_TRAINED_CONFLICT"
    assert body_payload["error"]["identity"]["mismatched_fields"] == [
        "idempotency_key_payload_mismatch"
    ]
    # Internal exception text MUST NOT leak to client
    assert "/var/secrets" not in response.text
    assert "idempotency_key_payload_mismatch: internal" not in response.text


# ---------------------------------------------------------------------------
# POST: 409 for structured TASK-012 blocker (service raises)
# ---------------------------------------------------------------------------


async def test_post_returns_409_for_blocker(
    monkeypatch: pytest.MonkeyPatch,
    client: Any,
) -> None:
    async def _raise_blocker(
        session: object, *, request: ReplayTrainedExecutionRequest
    ) -> ReplayTrainedExecutionResult:
        raise ReplayTrainedServiceBlockerError(
            "internal: training_rows_empty payload",
            blocker_code="task12_training_rows_empty",
            mismatched_fields=("training_rows_empty",),
        )

    monkeypatch.setattr(
        rolling_backtest_replay_trained,
        "execute_replay_trained_prediction",
        _raise_blocker,
    )

    request = _stub_request(idempotency_key="idem-blocker")
    body = request.to_payload()
    body["idempotency_key"] = "idem-blocker"

    async with client as c:
        response = await c.post("/api/v1/rolling-backtest/replay-trained-predictions", json=body)
    assert response.status_code == 409
    body_payload = response.json()
    assert body_payload["error"]["code"] == "TASK012_REPLAY_TRAINED_BLOCKED"
    assert body_payload["error"]["blocker"] == "task12_training_rows_empty"
    # Internal exception text MUST NOT leak to client
    assert "internal: training_rows_empty" not in response.text


# ---------------------------------------------------------------------------
# POST: 500 for unexpected internal failure (no leak of traceback / SQL)
# ---------------------------------------------------------------------------


async def test_post_returns_500_for_unexpected_failure(
    monkeypatch: pytest.MonkeyPatch,
    client: Any,
) -> None:
    async def _raise_unexpected(
        session: object, *, request: ReplayTrainedExecutionRequest
    ) -> ReplayTrainedExecutionResult:
        raise RuntimeError(
            "Traceback (most recent call last):\n"
            "  File '/srv/blueberry/replay_trained_service.py', line 1\n"
            "    raise SQLAlchemyError('DSN=postgres://root:***@host/db')\n"
        )

    monkeypatch.setattr(
        rolling_backtest_replay_trained,
        "execute_replay_trained_prediction",
        _raise_unexpected,
    )

    request = _stub_request(idempotency_key="idem-500")
    body = request.to_payload()
    body["idempotency_key"] = "idem-500"

    async with client as c:
        response = await c.post("/api/v1/rolling-backtest/replay-trained-predictions", json=body)
    assert response.status_code == 500
    body_payload = response.json()
    assert body_payload["error"]["code"] == "TASK012_REPLAY_TRAINED_INTEGRITY_ERROR"
    for forbidden in (
        "Traceback",
        "SQLAlchemy",
        "postgres://",
        "hunter2",
        "/srv/blueberry",
        "replay_trained_service.py",
        "DSN=",
    ):
        assert forbidden not in response.text, forbidden


# ---------------------------------------------------------------------------
# GET: 200 exact retrieval
# ---------------------------------------------------------------------------


async def test_get_returns_200_with_persisted_identity(
    monkeypatch: pytest.MonkeyPatch,
    client: Any,
) -> None:
    """GET returns 200 with the persisted TASK-012 identity for the exact
    ``prediction_run_id`` it is asked for. The endpoint does NOT re-execute
    the E2 service.
    """

    async def _fake_load(
        session: object, *, prediction_run_id: int
    ) -> ReplayTrainedPersistedIdentity:
        return ReplayTrainedPersistedIdentity(
            prediction_run_id=prediction_run_id,
            prediction_hash="z" * 64,
            request_payload_hash="h" * 64,
            model_policy="replay_trained_model",
            task12_policy_version="task12-policy-e3",
            replay_attempt_id="attempt-e3",
            replay_node_id="node-e3",
            scenario_id="scenario-e3",
            training_manifest_hash="m" * 64,
            training_dataset_hash="d" * 64,
            model_config_hash="c" * 64,
            model_artifact_hash="a" * 64,
            model_code_version="task10-code-e3",
            forecast_cutoff_at="2026-03-15T12:00:00Z",
            training_cutoff_at="2026-03-14T12:00:00Z",
            task9_run_id=91,
            task9_result_hash="9" * 64,
            task10_training_run_id=7,
            task10_training_signature="s" * 64,
            task10_manifest_hash="mh" * 32,
            task10_config_hash="ch" * 32,
            task10_artifact_hashes=("ah" * 32,),
            filtered_training_row_count=3,
            filtered_label_row_count=2,
            training_execution_status="completed",
            training_eligibility_status="eligible",
            prediction_execution_status="completed",
            prediction_mode="residual_corrected",
            idempotency_key="idem-e3-get-200",
            caller_identity="test:e3-get-200",
            audit_identity="audit-" + "y" * 56,
        )

    async def _service_should_not_run(
        session: object, *, request: ReplayTrainedExecutionRequest
    ) -> ReplayTrainedExecutionResult:
        raise AssertionError("GET endpoint must not call the Slice E2 service")

    monkeypatch.setattr(
        rolling_backtest_replay_trained,
        "load_replay_trained_prediction",
        _fake_load,
    )
    monkeypatch.setattr(
        rolling_backtest_replay_trained,
        "execute_replay_trained_prediction",
        _service_should_not_run,
    )

    async with client as c:
        response = await c.get("/api/v1/rolling-backtest/replay-trained-predictions/4242")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["prediction_run_id"] == 4242
    assert body["model_policy"] == "replay_trained_model"
    assert body["audit_identity"].startswith("audit-")
    assert body["idempotency_key"] == "idem-e3-get-200"


# ---------------------------------------------------------------------------
# GET: 404 missing
# ---------------------------------------------------------------------------


async def test_get_returns_404_for_missing_prediction(
    monkeypatch: pytest.MonkeyPatch,
    client: Any,
) -> None:
    async def _fake_load(session: object, *, prediction_run_id: int) -> object:
        raise ReplayTrainedServiceNotFoundError(
            "the requested replay-trained prediction was not found",
            identity={"prediction_run_id": prediction_run_id},
        )

    monkeypatch.setattr(
        rolling_backtest_replay_trained,
        "load_replay_trained_prediction",
        _fake_load,
    )

    async with client as c:
        response = await c.get("/api/v1/rolling-backtest/replay-trained-predictions/9999")
    assert response.status_code == 404
    body = response.json()
    # Frozen §7.3 envelope: exactly {code, message, blocker, identity};
    # the not-found selector is exposed under ``error.identity`` (NOT
    # ``error.details`` — that key was a contract regression in the
    # prior round).
    assert body["error"]["code"] == "TASK012_REPLAY_TRAINED_NOT_FOUND"
    assert set(body["error"].keys()) == {"code", "message", "blocker", "identity"}
    assert body["error"]["identity"]["prediction_run_id"] == 9999


# ---------------------------------------------------------------------------
# GET: 500 integrity failure (missing required persisted field)
# ---------------------------------------------------------------------------


async def test_get_returns_500_for_missing_required_field(
    monkeypatch: pytest.MonkeyPatch,
    client: Any,
) -> None:
    async def _fake_load(session: object, *, prediction_run_id: int) -> object:
        # The persisted row is missing the ``task12_replay`` context;
        # the strict loader MUST fail closed (not silently default).
        raise ReplayTrainedPersistedIdentityIntegrityError(
            "persisted input_snapshot.task12_replay is missing",
            mismatched_fields=("input_snapshot_task12_replay_missing",),
        )

    monkeypatch.setattr(
        rolling_backtest_replay_trained,
        "load_replay_trained_prediction",
        _fake_load,
    )

    async with client as c:
        response = await c.get("/api/v1/rolling-backtest/replay-trained-predictions/4242")
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "TASK012_REPLAY_TRAINED_INTEGRITY_ERROR"
    assert set(body["error"].keys()) == {"code", "message", "blocker", "identity"}


# ---------------------------------------------------------------------------
# GET: 500 for unexpected internal failure
# ---------------------------------------------------------------------------


async def test_get_returns_500_for_unexpected_failure(
    monkeypatch: pytest.MonkeyPatch,
    client: Any,
) -> None:
    async def _raise_unexpected(session: object, *, prediction_run_id: int) -> object:
        raise RuntimeError(
            "Traceback (most recent call last):\n"
            "  File '/srv/blueberry/replay_trained_service.py', line 1\n"
            "    raise SQLAlchemyError('DSN=postgres://root:***@host/db')\n"
        )

    monkeypatch.setattr(
        rolling_backtest_replay_trained,
        "load_replay_trained_prediction",
        _raise_unexpected,
    )

    async with client as c:
        response = await c.get("/api/v1/rolling-backtest/replay-trained-predictions/4242")
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "TASK012_REPLAY_TRAINED_INTEGRITY_ERROR"
    assert set(body["error"].keys()) == {"code", "message", "blocker", "identity"}
    for forbidden in (
        "Traceback",
        "SQLAlchemy",
        "postgres://",
        "hunter2",
        "/srv/blueberry",
        "replay_trained_service.py",
        "DSN=",
    ):
        assert forbidden not in response.text, forbidden


# ---------------------------------------------------------------------------
# No implicit latest/current/most-recent selector in source code
# ---------------------------------------------------------------------------


def test_http_adapter_source_uses_no_implicit_latest_selection() -> None:
    """The HTTP adapter source must not contain any implicit
    ``latest`` / ``most_recent`` / ``current_data`` / ``now()``
    selection in executable code (the docstring may mention them as
    the forbidden selectors); the GET path parameter is the only
    retrieval selector.
    """
    import inspect

    source = inspect.getsource(rolling_backtest_replay_trained)
    # Strip docstrings (triple-quoted) before scanning
    cleaned_lines: list[str] = []
    in_docstring = False
    for line in source.splitlines():
        stripped = line.strip()
        if not in_docstring and (stripped.startswith('"""') or stripped.startswith("'''")):
            in_docstring = True
            if stripped.count('"""') >= 2 or stripped.count("'''") >= 2:
                in_docstring = False
            continue
        if in_docstring:
            if '"""' in stripped or "'''" in stripped:
                in_docstring = False
            continue
        if stripped.startswith("#"):
            continue
        cleaned_lines.append(line)
    executable_source = "\n".join(cleaned_lines)
    for forbidden in ("latest", "most_recent", "current_data", "now()"):
        assert forbidden not in executable_source, (
            f"forbidden selector {forbidden!r} appears in executable code"
        )


async def _first_execution_body_async(*, idempotency_key: str) -> dict[str, object]:
    """Build a complete valid POST body for strict-schema tests.

    The P0-#2 spec requires each single-field mutation test to
    start from a complete valid body so the failure message
    isolates the real schema violation, not a cascade of
    "missing required field" errors. This helper builds that
    body by going through the E2 service's frozen dataclass +
    ``to_payload`` path.
    """
    request = _stub_request(idempotency_key=idempotency_key)
    body = request.to_payload()
    body["idempotency_key"] = idempotency_key
    return body  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Strict request schema single-field mutation negative tests (P0-#2 spec)
# ---------------------------------------------------------------------------
#
# Each test below takes a complete valid request body and mutates EXACTLY
# one field. The test asserts the strict Pydantic schema returns 422
# with the stable TASK012_REPLAY_TRAINED_INPUT_INVALID envelope. Each
# mutation is the ONLY change vs. the baseline body so the failure
# message isolates the actual schema violation, not a cascade of
# "missing required field" errors that would mask the real cause.


async def _assert_schema_422(client: Any, body: dict[str, object]) -> None:
    async with client as c:
        response = await c.post("/api/v1/rolling-backtest/replay-trained-predictions", json=body)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "TASK012_REPLAY_TRAINED_INPUT_INVALID"


async def test_schema_rejects_unknown_top_level_field(
    client: Any,
) -> None:
    body = await _first_execution_body_async(idempotency_key="idem-schema-unknown-top")
    body["totally_unknown_top_level_field"] = "should reject"
    await _assert_schema_422(client, body)


async def test_schema_rejects_unknown_training_manifest_field(
    client: Any,
) -> None:
    body = await _first_execution_body_async(idempotency_key="idem-schema-unknown-manifest")
    body["training_manifest"]["totally_unknown_manifest_field"] = "x"
    await _assert_schema_422(client, body)


async def test_schema_rejects_unknown_model_config_field(
    client: Any,
) -> None:
    body = await _first_execution_body_async(idempotency_key="idem-schema-unknown-mc")
    body["model_config"]["totally_unknown_mc_field"] = "x"
    await _assert_schema_422(client, body)


async def test_schema_rejects_is_replay_string_false(
    client: Any,
) -> None:
    body = await _first_execution_body_async(idempotency_key="idem-schema-isreplay-str")
    body["is_replay"] = "false"
    await _assert_schema_422(client, body)


async def test_schema_rejects_is_replay_int_one(
    client: Any,
) -> None:
    body = await _first_execution_body_async(idempotency_key="idem-schema-isreplay-int")
    body["is_replay"] = 1
    await _assert_schema_422(client, body)


async def test_schema_rejects_task9_run_id_bool(
    client: Any,
) -> None:
    body = await _first_execution_body_async(idempotency_key="idem-schema-t9id-bool")
    body["task9_run_id"] = True
    await _assert_schema_422(client, body)


async def test_schema_rejects_task9_run_id_numeric_string(
    client: Any,
) -> None:
    body = await _first_execution_body_async(idempotency_key="idem-schema-t9id-str")
    body["task9_run_id"] = "91"
    await _assert_schema_422(client, body)


async def test_schema_rejects_caller_identity_int(
    client: Any,
) -> None:
    body = await _first_execution_body_async(idempotency_key="idem-schema-caller-int")
    body["caller_identity"] = 123
    await _assert_schema_422(client, body)


async def test_schema_rejects_uppercase_task9_result_hash(
    client: Any,
) -> None:
    body = await _first_execution_body_async(idempotency_key="idem-schema-t9hash-upper")
    body["task9_result_hash"] = "A" * 64
    await _assert_schema_422(client, body)


async def test_schema_rejects_nested_training_dataset_hash_malformed(
    client: Any,
) -> None:
    body = await _first_execution_body_async(idempotency_key="idem-schema-nested-tdh")
    body["training_manifest"]["training_dataset_hash"] = "z" * 64
    await _assert_schema_422(client, body)


async def test_schema_rejects_nested_model_artifact_hash_malformed(
    client: Any,
) -> None:
    body = await _first_execution_body_async(idempotency_key="idem-schema-nested-mah")
    body["model_config"]["deterministic_serialization_version"] = ""  # empty
    await _assert_schema_422(client, body)


async def test_schema_rejects_naive_forecast_cutoff_at(
    client: Any,
) -> None:
    body = await _first_execution_body_async(idempotency_key="idem-schema-naive-fc")
    body["forecast_cutoff_at"] = "2026-03-15T12:00:00"  # no tz
    await _assert_schema_422(client, body)


async def test_schema_rejects_naive_nested_forecast_cutoff_at(
    client: Any,
) -> None:
    body = await _first_execution_body_async(idempotency_key="idem-schema-naive-nested-fc")
    body["training_manifest"]["forecast_cutoff_at"] = "2026-03-15T12:00:00"
    await _assert_schema_422(client, body)


# ---------------------------------------------------------------------------
# Frozen §7.3 envelope exact key set + full code string (P0-#1 spec)
# ---------------------------------------------------------------------------
#
# The public error envelope MUST contain EXACTLY four keys:
# ``code``, ``message``, ``blocker``, ``identity``. No ``details``,
# no ``mismatched_fields``, no other top-level keys. The public
# integrity code MUST be ``TASK012_REPLAY_TRAINED_INTEGRITY_ERROR``
# (with the ``_ERROR`` suffix — the no-suffix form is forbidden
# by the §7.4 contract).
#
# These tests run a single representative case for each error class
# and pin both the exact key set and the full code string.


async def test_post_envelope_keys_and_code_are_exact(
    monkeypatch: pytest.MonkeyPatch,
    client: Any,
) -> None:
    """POST service-error envelope carries exactly the §7.3 keys and
    the frozen §7.4 integrity code string.
    """

    async def _raise_service(
        session: object, *, request: ReplayTrainedExecutionRequest
    ) -> ReplayTrainedExecutionResult:
        raise ReplayTrainedServiceConflictError(
            "test conflict",
            mismatched_fields=("a",),
        )

    monkeypatch.setattr(
        rolling_backtest_replay_trained,
        "execute_replay_trained_prediction",
        _raise_service,
    )

    request = _stub_request(idempotency_key="idem-envelope-conflict")
    body = request.to_payload()
    body["idempotency_key"] = "idem-envelope-conflict"
    async with client as c:
        response = await c.post("/api/v1/rolling-backtest/replay-trained-predictions", json=body)
    assert response.status_code == 409
    err = response.json()["error"]
    assert set(err.keys()) == {"code", "message", "blocker", "identity"}
    assert err["code"] == "TASK012_REPLAY_TRAINED_CONFLICT"
    assert err["message"]
    assert err["blocker"] is None
    assert err["identity"]["mismatched_fields"] == ["a"]


async def test_post_blocker_envelope_keys_and_code_are_exact(
    monkeypatch: pytest.MonkeyPatch,
    client: Any,
) -> None:
    async def _raise_blocker(
        session: object, *, request: ReplayTrainedExecutionRequest
    ) -> ReplayTrainedExecutionResult:
        raise ReplayTrainedServiceBlockerError(
            "test blocker",
            blocker_code="task12_xyz",
            mismatched_fields=("b",),
        )

    monkeypatch.setattr(
        rolling_backtest_replay_trained,
        "execute_replay_trained_prediction",
        _raise_blocker,
    )

    request = _stub_request(idempotency_key="idem-envelope-blocker")
    body = request.to_payload()
    body["idempotency_key"] = "idem-envelope-blocker"
    async with client as c:
        response = await c.post("/api/v1/rolling-backtest/replay-trained-predictions", json=body)
    assert response.status_code == 409
    err = response.json()["error"]
    assert set(err.keys()) == {"code", "message", "blocker", "identity"}
    assert err["code"] == "TASK012_REPLAY_TRAINED_BLOCKED"
    assert err["blocker"] == "task12_xyz"


async def test_post_not_found_envelope_keys_and_code_are_exact(
    monkeypatch: pytest.MonkeyPatch,
    client: Any,
) -> None:
    async def _raise_nf(
        session: object, *, request: ReplayTrainedExecutionRequest
    ) -> ReplayTrainedExecutionResult:
        raise ReplayTrainedServiceNotFoundError(
            "missing",
            identity={"task9_run_id": 999},
        )

    monkeypatch.setattr(
        rolling_backtest_replay_trained,
        "execute_replay_trained_prediction",
        _raise_nf,
    )

    request = _stub_request(idempotency_key="idem-envelope-nf")
    body = request.to_payload()
    body["idempotency_key"] = "idem-envelope-nf"
    async with client as c:
        response = await c.post("/api/v1/rolling-backtest/replay-trained-predictions", json=body)
    assert response.status_code == 404
    err = response.json()["error"]
    assert set(err.keys()) == {"code", "message", "blocker", "identity"}
    assert err["code"] == "TASK012_REPLAY_TRAINED_NOT_FOUND"
    assert err["identity"]["task9_run_id"] == 999


async def test_post_integrity_envelope_keys_and_code_are_exact(
    monkeypatch: pytest.MonkeyPatch,
    client: Any,
) -> None:
    async def _raise_unexpected(
        session: object, *, request: ReplayTrainedExecutionRequest
    ) -> ReplayTrainedExecutionResult:
        raise RuntimeError("internal: boom")

    monkeypatch.setattr(
        rolling_backtest_replay_trained,
        "execute_replay_trained_prediction",
        _raise_unexpected,
    )

    request = _stub_request(idempotency_key="idem-envelope-500")
    body = request.to_payload()
    body["idempotency_key"] = "idem-envelope-500"
    async with client as c:
        response = await c.post("/api/v1/rolling-backtest/replay-trained-predictions", json=body)
    assert response.status_code == 500
    err = response.json()["error"]
    assert set(err.keys()) == {"code", "message", "blocker", "identity"}
    # Frozen §7.4 public integrity code (with ``_ERROR`` suffix).
    assert err["code"] == "TASK012_REPLAY_TRAINED_INTEGRITY_ERROR"
    assert "boom" not in response.text


async def test_post_422_envelope_keys_and_code_are_exact(client: Any) -> None:
    async with client as c:
        response = await c.post(
            "/api/v1/rolling-backtest/replay-trained-predictions",
            json={"idempotency_key": "idem-422"},
        )
    assert response.status_code == 422
    err = response.json()["error"]
    assert set(err.keys()) == {"code", "message", "blocker", "identity"}
    assert err["code"] == "TASK012_REPLAY_TRAINED_INPUT_INVALID"
    assert err["blocker"] is None
    assert err["identity"] == {}


# ---------------------------------------------------------------------------
# Strict nested request structure — unknown-field mutation tests (P0-#5 spec)
# ---------------------------------------------------------------------------
#
# Each test below takes a complete valid request body and mutates EXACTLY
# one nested field. The strict Pydantic schema MUST reject unknown
# fields with a 422 envelope. This replaces the prior
# ``_RowPassthroughBaseModel(extra="allow")`` passthrough which silently
# accepted unknown nested keys.


async def test_schema_rejects_unknown_manifest_row_field(client: Any) -> None:
    body = await _first_execution_body_async(idempotency_key="idem-schema-mr-unknown")
    body["manifest_rows_payload"][0]["unknown_manifest_row_field"] = "x"
    await _assert_schema_422(client, body)


async def test_schema_rejects_unknown_training_row_field(client: Any) -> None:
    body = await _first_execution_body_async(idempotency_key="idem-schema-tr-unknown")
    body["training_rows"][0]["unknown_training_row_field"] = "x"
    await _assert_schema_422(client, body)


async def test_schema_rejects_unknown_label_row_field(client: Any) -> None:
    body = await _first_execution_body_async(idempotency_key="idem-schema-lr-unknown")
    body["label_rows"][0]["unknown_label_row_field"] = "x"
    await _assert_schema_422(client, body)


async def test_schema_rejects_unknown_training_sample_field(client: Any) -> None:
    body = await _first_execution_body_async(idempotency_key="idem-schema-ts-unknown")
    body["training_samples"][0]["unknown_training_sample_field"] = "x"
    await _assert_schema_422(client, body)


async def test_schema_rejects_unknown_supplemental_feature_field(client: Any) -> None:
    body = await _first_execution_body_async(idempotency_key="idem-schema-sf-unknown")
    # Inject one supplemental feature value then add an unknown field.
    body["supplemental_feature_values"].append(
        {
            "feature_name": "x",
            "value": 1,
            "known_at": "2026-03-13T00:00:00Z",
            "source_ref": {"k": "v"},
            "source_version": "v1",
            "source_available_at": "2026-03-13T00:00:00Z",
        }
    )
    body["supplemental_feature_values"][0]["unknown_supplemental_field"] = "x"
    await _assert_schema_422(client, body)


async def test_schema_rejects_unknown_source_run_ids_field(client: Any) -> None:
    body = await _first_execution_body_async(idempotency_key="idem-schema-sri-unknown")
    body["source_run_ids"]["unknown_source_run_id"] = 1
    await _assert_schema_422(client, body)


async def test_schema_rejects_wrong_nested_integer_type(client: Any) -> None:
    body = await _first_execution_body_async(idempotency_key="idem-schema-ts-int")
    # task9_run_id is StrictInt; numeric-string rejected.
    body["training_samples"][0]["task9_run_id"] = "91"
    await _assert_schema_422(client, body)


async def test_schema_rejects_wrong_nested_boolean_type(client: Any) -> None:
    body = await _first_execution_body_async(idempotency_key="idem-schema-mr-bool")
    # include is StrictBool; string rejected.
    body["manifest_rows_payload"][0]["include"] = "true"
    await _assert_schema_422(client, body)


# ---------------------------------------------------------------------------
# Log redaction (P0-#6 spec): no raw idempotency_key in log lines.
# ---------------------------------------------------------------------------


async def test_post_service_error_does_not_log_raw_idempotency_key(
    monkeypatch: pytest.MonkeyPatch,
    client: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The transport layer MUST NOT log the raw ``idempotency_key``.

    The sentinel raw key ``RAW_IDEMPOTENCY_SENTINEL_5e2b`` MUST NOT
    appear anywhere in the captured log output. A non-reversible
    SHA-256[:12] correlation prefix MAY appear.
    """

    raw_sentinel = "RAW_IDEMPOTENCY_SENTINEL_5e2b"

    async def _raise_service(
        session: object, *, request: ReplayTrainedExecutionRequest
    ) -> ReplayTrainedExecutionResult:
        raise ReplayTrainedServiceError("test service error")

    monkeypatch.setattr(
        rolling_backtest_replay_trained,
        "execute_replay_trained_prediction",
        _raise_service,
    )

    request = _stub_request(idempotency_key=raw_sentinel)
    body = request.to_payload()
    body["idempotency_key"] = raw_sentinel
    with caplog.at_level("ERROR"):
        async with client as c:
            response = await c.post(
                "/api/v1/rolling-backtest/replay-trained-predictions", json=body
            )
    assert response.status_code == 500
    assert raw_sentinel not in caplog.text
    # SHA-256[:12] of the sentinel prefix MUST be present so two log
    # lines about the same execution can still be correlated.
    import hashlib

    prefix = hashlib.sha256(raw_sentinel.encode("utf-8")).hexdigest()[:12]
    assert prefix in caplog.text


async def test_post_unexpected_error_does_not_log_raw_idempotency_key(
    monkeypatch: pytest.MonkeyPatch,
    client: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    raw_sentinel = "RAW_IDEMPOTENCY_SENTINEL_unexpected"

    async def _raise_unexpected(
        session: object, *, request: ReplayTrainedExecutionRequest
    ) -> ReplayTrainedExecutionResult:
        raise RuntimeError("kaboom")

    monkeypatch.setattr(
        rolling_backtest_replay_trained,
        "execute_replay_trained_prediction",
        _raise_unexpected,
    )

    request = _stub_request(idempotency_key=raw_sentinel)
    body = request.to_payload()
    body["idempotency_key"] = raw_sentinel
    with caplog.at_level("ERROR"):
        async with client as c:
            response = await c.post(
                "/api/v1/rolling-backtest/replay-trained-predictions", json=body
            )
    assert response.status_code == 500
    assert raw_sentinel not in caplog.text
    import hashlib

    prefix = hashlib.sha256(raw_sentinel.encode("utf-8")).hexdigest()[:12]
    assert prefix in caplog.text
