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
    ReplayTrainedServiceBlockerError,
    ReplayTrainedServiceConflictError,
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
        prediction_hash = "p" * 64
        request_payload_hash = "h" * 64
        training_manifest_hash = "m" * 64
        model_config_hash = "c" * 64
        model_artifact_hash = "a" * 64
        task9_run_id = 91
        task9_result_hash = "9" * 64
        filtered_training_row_count = 3
        filtered_label_row_count = 2
        training_execution_status = "completed"
        training_eligibility_status = "eligible"
        prediction_execution_status = "completed"
        prediction_mode = "residual_corrected"
        audit_identity = "audit-" + "x" * 56

        def to_payload(self) -> dict[str, object]:
            return {
                "service_version": "task12-slice-e3-unit",
                "model_policy": Task10ModelPolicy.REPLAY_TRAINED_MODEL.value,
                "task12_policy_version": "task12-policy-unit",
                "replay_attempt_id": "attempt-unit",
                "replay_node_id": "node-unit",
                "scenario_id": "scenario-unit",
                "training_manifest_hash": "m" * 64,
                "training_dataset_hash": "d" * 64,
                "model_config_hash": "c" * 64,
                "model_artifact_hash": "a" * 64,
                "model_code_version": "task10-code-unit",
                "forecast_cutoff_at": "2026-03-15T12:00:00Z",
                "training_cutoff_at": "2026-03-14T12:00:00Z",
                "task9_run_id": 91,
                "task9_result_hash": "9" * 64,
                "prediction_run_id": 4242,
                "prediction_hash": "p" * 64,
                "request_payload_hash": "h" * 64,
                "filtered_training_row_count": 3,
                "filtered_label_row_count": 2,
                "training_execution_status": "completed",
                "training_eligibility_status": "eligible",
                "prediction_execution_status": "completed",
                "prediction_mode": "residual_corrected",
                "task10_training_run_id": 7,
                "task10_training_signature": "s" * 64,
                "task10_manifest_hash": "mh" * 32,
                "task10_config_hash": "ch" * 32,
                "task10_artifact_hashes": ["ah" * 32],
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
    """
    from dataclasses import fields
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
    # replay_trained_service._validate_request:573-582).
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
        "training_manifest_hash": "m" * 64,
        "training_dataset_hash": "d" * 64,
        "model_config_hash": "c" * 64,
        "model_artifact_hash": "a" * 64,
        "model_code_version": "task10-code-unit",
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
        manifest_rows_payload=(
            {"season_id": 2025, "destination_factory_id": 1, "split": "train"},
            {"season_id": 2024, "destination_factory_id": 1, "split": "validation"},
        ),
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
    # Sanity: the dataclass has all fields populated.
    assert all(
        getattr(sample_request, f.name, None) is not None
        for f in fields(ReplayTrainedExecutionRequest)
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

    class _StubRow:
        canonical_payload_hash = "z" * 64
        input_snapshot = {
            "task12_replay": {
                "idempotency_key": "idem-e3-get-200",
                "request_payload_hash": "h" * 64,
                "model_policy": "replay_trained_model",
                "task12_policy_version": "task12-policy-e3",
                "replay_attempt_id": "attempt-e3",
                "replay_node_id": "node-e3",
                "scenario_id": "scenario-e3",
                "training_manifest_hash": "m" * 64,
                "training_dataset_hash": "d" * 64,
                "model_config_hash": "c" * 64,
                "model_artifact_hash": "a" * 64,
                "model_code_version": "task10-code-e3",
                "forecast_cutoff_at": "2026-03-15T12:00:00Z",
                "training_cutoff_at": "2026-03-14T12:00:00Z",
                "task9_run_id": 91,
                "task9_result_hash": "9" * 64,
                "task10_training_run_id": 7,
                "task10_training_signature": "s" * 64,
                "task10_manifest_hash": "mh" * 32,
                "task10_config_hash": "ch" * 32,
                "task10_artifact_hashes": ["ah" * 32],
                "filtered_training_row_count": 3,
                "filtered_label_row_count": 2,
                "training_execution_status": "completed",
                "training_eligibility_status": "eligible",
                "prediction_execution_status": "completed",
                "prediction_mode": "residual_corrected",
                "caller_identity": "test:e3-get-200",
                "service_version": "task12-slice-e3-unit",
            }
        }
        typed_attempt = {"task12_replay": {"audit_identity": "audit-" + "y" * 56}}

    async def _fake_get(session: object, *, run_id: int) -> _StubRow | None:
        return _StubRow() if run_id == 4242 else None

    async def _service_should_not_run(
        session: object, *, request: ReplayTrainedExecutionRequest
    ) -> ReplayTrainedExecutionResult:
        raise AssertionError("GET endpoint must not call the Slice E2 service")

    monkeypatch.setattr(
        rolling_backtest_replay_trained,
        "get_residual_prediction_run",
        _fake_get,
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
    async def _fake_get(session: object, *, run_id: int) -> None:
        return None

    monkeypatch.setattr(
        rolling_backtest_replay_trained,
        "get_residual_prediction_run",
        _fake_get,
    )

    async with client as c:
        response = await c.get("/api/v1/rolling-backtest/replay-trained-predictions/9999")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "TASK012_REPLAY_TRAINED_NOT_FOUND"
    assert body["error"]["identity"]["prediction_run_id"] == 9999


# ---------------------------------------------------------------------------
# GET: 500 integrity failure (missing required persisted field)
# ---------------------------------------------------------------------------


async def test_get_returns_500_for_missing_required_field(
    monkeypatch: pytest.MonkeyPatch,
    client: Any,
) -> None:
    class _StubRow:
        canonical_payload_hash = "z" * 64
        # The persisted row is missing the ``task12_replay`` context;
        # the strict loader MUST fail closed (not silently default).
        input_snapshot = {}
        typed_attempt = {}

    async def _fake_get(session: object, *, run_id: int) -> _StubRow | None:
        return _StubRow()

    monkeypatch.setattr(
        rolling_backtest_replay_trained,
        "get_residual_prediction_run",
        _fake_get,
    )

    async with client as c:
        response = await c.get("/api/v1/rolling-backtest/replay-trained-predictions/4242")
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "TASK012_REPLAY_TRAINED_INTEGRITY_ERROR"


# ---------------------------------------------------------------------------
# GET: 500 for unexpected internal failure
# ---------------------------------------------------------------------------


async def test_get_returns_500_for_unexpected_failure(
    monkeypatch: pytest.MonkeyPatch,
    client: Any,
) -> None:
    async def _raise_unexpected(session: object, *, run_id: int) -> object:
        raise RuntimeError(
            "Traceback (most recent call last):\n"
            "  File '/srv/blueberry/replay_trained_service.py', line 1\n"
            "    raise SQLAlchemyError('DSN=postgres://root:***@host/db')\n"
        )

    monkeypatch.setattr(
        rolling_backtest_replay_trained,
        "get_residual_prediction_run",
        _raise_unexpected,
    )

    async with client as c:
        response = await c.get("/api/v1/rolling-backtest/replay-trained-predictions/4242")
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "TASK012_REPLAY_TRAINED_INTEGRITY_ERROR"
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
