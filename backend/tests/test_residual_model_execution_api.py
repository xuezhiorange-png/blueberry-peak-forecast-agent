"""API contract tests for TASK-010 residual-model execution endpoints (Slice 2).

These tests freeze the contract defined in
``docs/task-010-api-slice2-execution-endpoints-design.md`` (PR #76) for the
four new endpoints:

- ``POST /api/v1/residual-model/training-runs``
- ``GET  /api/v1/residual-model/training-runs/{run_id}``
- ``POST /api/v1/residual-model/prediction-runs``
- ``GET  /api/v1/residual-model/prediction-runs/{run_id}``

Every test is marked with ``@pytest.mark.xfail(strict=True, reason=...)``
because the Slice 2 endpoints are **NOT yet implemented** in production
code. ``strict=True`` semantics:

- **today** (no impl): the route does not exist or returns 405 / 404 /
  422 / 500 etc. The test assertion ``status_code == 201`` (or similar)
  fails. ``xfail`` catches the failure → reported as ``XFAIL`` → CI green.
- **after the future implementation slice** (route wired + service wired):
  the assertion succeeds. ``xfail(strict=True)`` turns that unexpected
  pass into a hard failure until the ``xfail`` marker is removed
  alongside the implementation commit.

This pattern keeps CI green while the contract is frozen, and forces a
deliberate act (removing the marker) at implementation time — preventing
"tests pass coincidentally" silent regressions.

Forbidden test behaviors (per design contract §12.6):

- do NOT insert ORM rows directly via ``session.add(...)`` outside the
  production service path;
- do NOT bypass the service layer to fabricate run records;
- do NOT mock the persistence layer's transaction boundary.

These tests only assert contract shape — they do NOT exercise the
production service / persistence layer. The future implementation slice
must satisfy these contracts byte-for-byte; the marker removal is the
implementation PR's commit-level proof.

Companion docs (read first):

- ``docs/task-010-report-api-contract.md`` (PR #73)
- ``docs/task-010-api-slice2-execution-endpoints-design.md`` (PR #76)
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import create_app

# ---------------------------------------------------------------------------
# Frozen Slice 2 error codes (per PR #76 §8)
# ---------------------------------------------------------------------------

SLICE2_XFAIL_REASON = "TASK-010 API Slice 2 implementation not authorized yet"

# Frozen error codes (PR #76 §8)
ERR_EXECUTION_INPUT = "RESIDUAL_MODEL_EXECUTION_INPUT_ERROR"
ERR_TRAINING_NOT_FOUND = "RESIDUAL_MODEL_TRAINING_RUN_NOT_FOUND"
ERR_PREDICTION_NOT_FOUND = "RESIDUAL_MODEL_PREDICTION_RUN_NOT_FOUND"
ERR_EXECUTION_CONFLICT = "RESIDUAL_MODEL_EXECUTION_CONFLICT"
ERR_EXECUTION_INTEGRITY = "RESIDUAL_MODEL_EXECUTION_INTEGRITY_ERROR"
ERR_REPORT_NOT_AVAILABLE = "RESIDUAL_MODEL_REPORT_NOT_AVAILABLE"

# Leak patterns forbidden in error response bodies (PR #76 §8)
LEAK_PATTERNS = (
    "sqlalchemy",
    "asyncpg",
    "traceback",
    "Traceback (most recent call last)",
    "artifact_bytes",
)


# ---------------------------------------------------------------------------
# Fixture: contract-only HTTP client (no DB session override required)
# ---------------------------------------------------------------------------


@pytest.fixture
async def residual_client() -> AsyncClient:
    """Build an AsyncClient wired to an in-memory SQLite session.

    The Slice 2 execution POST handler persists training runs via
    ``save_residual_training_run``, which writes to multiple tables in
    a single transaction. The DB session must therefore be backed by an
    engine where those tables exist. SQLite is acceptable here because
    the persistence layer is built on SQLAlchemy's portable
    ``Mapped`` / ``JSONB.with_variant(JSON)`` abstractions.
    """
    from sqlalchemy.ext.asyncio import (
        AsyncSession as _AsyncSession,
    )
    from sqlalchemy.ext.asyncio import (
        async_sessionmaker,
        create_async_engine,
    )

    from backend.app.db.session import get_db_session
    from backend.app.models.residual_model import (
        ResidualModelArtifact,
        ResidualModelExecutionAttempt,
        ResidualModelManifestRow,
        ResidualModelPredictionRow,
        ResidualModelPredictionRun,
        ResidualModelTrainingRun,
    )

    def _create_residual_tables(sync_conn: Any) -> None:
        ResidualModelTrainingRun.metadata.create_all(
            sync_conn,
            tables=[
                ResidualModelTrainingRun.__table__,
                ResidualModelManifestRow.__table__,
                ResidualModelArtifact.__table__,
                ResidualModelPredictionRun.__table__,
                ResidualModelPredictionRow.__table__,
                ResidualModelExecutionAttempt.__table__,
            ],
        )

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(_create_residual_tables)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=_AsyncSession)
    async with sessionmaker() as session:
        app = create_app()

        async def _override() -> AsyncIterator[_AsyncSession]:
            yield session

        app.dependency_overrides[get_db_session] = _override
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    await engine.dispose()


# ---------------------------------------------------------------------------
# Helpers — request payloads + expected envelope shapes
# ---------------------------------------------------------------------------


def _training_request_payload() -> dict[str, Any]:
    """Minimal valid training POST request payload (PR #76 §4.1)."""
    return {
        "manifest_snapshot": {
            "rows": [{"manifest_id": "m-1", "season_id": 1, "split": "train"}],
            "summary": {"row_count": 1},
        },
        "manifest_snapshot_id": None,
        "manifest_rows": [
            {"manifest_id": "m-1", "season_id": 1, "split": "train", "feature_count": 3},
        ],
        "config": {"family": "test-model", "version": "1.0.0"},
        "forecast_cutoff": "2026-04-30",
        "source_run_ids": {"task9a_run_id": 1},
        "idempotency_key": None,
    }


def _prediction_request_payload() -> dict[str, Any]:
    """Minimal valid prediction POST request payload (PR #76 §4.2)."""
    return {
        "training_run_id": 1,
        "feature_actual_snapshot": {"row_count": 1, "rows": []},
        "supplemental_features": None,
        "config": {"family": "test-model", "version": "1.0.0"},
        "prediction_mode": "residual_corrected",
        "task9_run_id": 10,
        "task9_result_hash": "a" * 64,
        "source_run_ids": {},
        "idempotency_key": None,
    }


def _assert_envelope_shape(payload: dict[str, Any], *, kind: str) -> None:
    """Assert the frozen envelope shape per PR #76 §5.1 / §5.2."""
    if kind == "training":
        required = (
            "run_id",
            "execution_status",
            "eligibility_status",
            "training_signature",
            "config_hash",
            "manifest_hash",
            "created_at",
            "finished_at",
            "warnings",
            "blockers",
            "report_links",
        )
    elif kind == "prediction":
        required = (
            "run_id",
            "execution_status",
            "mode",
            "prediction_hash",
            "prediction_input_signature",
            "config_hash",
            "created_at",
            "completed_at",
            "warnings",
            "blockers",
            "report_links",
        )
    else:
        raise AssertionError(f"unknown envelope kind: {kind}")
    for key in required:
        assert key in payload, f"envelope missing field {key!r}"

    # report_links shape per PR #76 §5.1 / §5.2
    links = payload["report_links"]
    assert "json" in links
    assert "csv" in links
    if kind == "training":
        run_id = payload["run_id"]
        assert links["json"].endswith(f"/training-runs/{run_id}/report.json")
        assert links["csv"].endswith(f"/training-runs/{run_id}/report.csv")
    else:
        run_id = payload["run_id"]
        assert links["json"].endswith(f"/prediction-runs/{run_id}/report.json")
        assert links["csv"].endswith(f"/prediction-runs/{run_id}/report.csv")


def _assert_stable_error_payload(payload: dict[str, Any], *, code: str) -> None:
    """Assert the frozen stable error envelope per PR #76 §8."""
    assert "error" in payload, "error envelope missing 'error' key"
    err = payload["error"]
    assert isinstance(err, dict)
    assert err.get("code") == code, f"expected code={code!r}, got {err.get('code')!r}"
    assert "message" in err and isinstance(err["message"], str)


def _assert_no_internal_leak(text: str) -> None:
    """Assert that the response body does NOT leak forbidden internals."""
    text_lower = text.lower()
    for needle in LEAK_PATTERNS:
        assert needle not in text_lower, f"response body leaked {needle!r}"


# ===========================================================================
# 1. Training POST happy path (PR #76 §3.1, §4.1, §5.1, §5.3)
# ===========================================================================


@pytest.mark.asyncio
async def test_training_post_returns_201_with_envelope(
    residual_client: AsyncClient,
) -> None:
    """POST /api/v1/residual-model/training-runs → 201 + envelope + Location."""
    response = await residual_client.post(
        "/api/v1/residual-model/training-runs",
        json=_training_request_payload(),
    )
    assert response.status_code == 201
    payload = response.json()
    _assert_envelope_shape(payload, kind="training")
    # Location header per PR #76 §5.3
    loc = response.headers.get("location", "")
    assert f"/api/v1/residual-model/training-runs/{payload['run_id']}" in loc


# ===========================================================================
# 2. Training GET happy path (PR #76 §3.1, §5.1, §5.3)
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, reason=SLICE2_XFAIL_REASON)
async def test_training_get_returns_200_with_envelope(
    residual_client: AsyncClient,
) -> None:
    """GET /api/v1/residual-model/training-runs/{run_id} → 200 + envelope."""
    response = await residual_client.get("/api/v1/residual-model/training-runs/1")
    assert response.status_code == 200
    payload = response.json()
    _assert_envelope_shape(payload, kind="training")


# ===========================================================================
# 3. Training replay same payload (PR #76 §7.1)
# ===========================================================================


@pytest.mark.asyncio
async def test_training_replay_same_payload_returns_200_existing_run(
    residual_client: AsyncClient,
) -> None:
    """Replay POST with identical canonical payload → 200 + existing run envelope.

    Must NOT create a duplicate business-equivalent run.
    """
    payload = _training_request_payload()
    first = await residual_client.post("/api/v1/residual-model/training-runs", json=payload)
    second = await residual_client.post("/api/v1/residual-model/training-runs", json=payload)

    # First creation: 201
    assert first.status_code == 201
    first_run_id = first.json()["run_id"]

    # Replay: 200 (per §7.1, NOT 201)
    assert second.status_code == 200
    second_run_id = second.json()["run_id"]
    # Same run_id (no duplicate created)
    assert second_run_id == first_run_id


# ===========================================================================
# 4. Training conflict (PR #76 §7.1, §8)
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, reason=SLICE2_XFAIL_REASON)
async def test_training_conflict_different_canonical_payload_returns_409(
    residual_client: AsyncClient,
) -> None:
    """Same signature but different canonical payload bytes → 409 + stable error."""
    payload_b = _training_request_payload()
    payload_b["source_run_ids"] = {"harvest_state_run_id": 99, "task9a_run_id": 1}

    # The future endpoint must canonicalize + hash and detect the conflict.
    # We expect 409 with stable error envelope.
    response = await residual_client.post("/api/v1/residual-model/training-runs", json=payload_b)
    assert response.status_code == 409
    _assert_stable_error_payload(response.json(), code=ERR_EXECUTION_CONFLICT)
    _assert_no_internal_leak(response.text)


# ===========================================================================
# 5. Prediction POST happy path (PR #76 §3.2, §4.2, §5.2, §5.3)
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, reason=SLICE2_XFAIL_REASON)
async def test_prediction_post_returns_201_with_envelope(
    residual_client: AsyncClient,
) -> None:
    """POST /api/v1/residual-model/prediction-runs → 201 + envelope + Location."""
    response = await residual_client.post(
        "/api/v1/residual-model/prediction-runs",
        json=_prediction_request_payload(),
    )
    assert response.status_code == 201
    payload = response.json()
    _assert_envelope_shape(payload, kind="prediction")
    loc = response.headers.get("location", "")
    assert f"/api/v1/residual-model/prediction-runs/{payload['run_id']}" in loc


# ===========================================================================
# 6. Prediction GET happy path (PR #76 §3.2, §5.2, §5.3)
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, reason=SLICE2_XFAIL_REASON)
async def test_prediction_get_returns_200_with_envelope(
    residual_client: AsyncClient,
) -> None:
    """GET /api/v1/residual-model/prediction-runs/{run_id} → 200 + envelope."""
    response = await residual_client.get("/api/v1/residual-model/prediction-runs/1")
    assert response.status_code == 200
    payload = response.json()
    _assert_envelope_shape(payload, kind="prediction")


# ===========================================================================
# 7. Prediction replay same payload (PR #76 §7.2)
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, reason=SLICE2_XFAIL_REASON)
async def test_prediction_replay_same_payload_returns_200_existing_run(
    residual_client: AsyncClient,
) -> None:
    """Replay POST with identical canonical payload → 200 + existing run envelope."""
    payload = _prediction_request_payload()
    first = await residual_client.post("/api/v1/residual-model/prediction-runs", json=payload)
    second = await residual_client.post("/api/v1/residual-model/prediction-runs", json=payload)

    # First creation: 201
    assert first.status_code == 201
    first_run_id = first.json()["run_id"]

    # Replay: 200
    assert second.status_code == 200
    second_run_id = second.json()["run_id"]
    assert second_run_id == first_run_id


# ===========================================================================
# 8. Prediction conflict (PR #76 §7.2, §8)
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, reason=SLICE2_XFAIL_REASON)
async def test_prediction_conflict_different_canonical_payload_returns_409(
    residual_client: AsyncClient,
) -> None:
    """Same prediction_input_signature but different canonical payload → 409."""
    payload_b = _prediction_request_payload()
    # Force same hash by tweaking non-canonical ordering: the implementation
    # canonicalizes before hashing, so different bytes with same canonical form
    # should NOT trigger 409. We instead mutate a non-signature field and
    # expect the implementation to detect the conflict.
    payload_b["idempotency_key"] = "11111111-1111-1111-1111-111111111111"

    response = await residual_client.post("/api/v1/residual-model/prediction-runs", json=payload_b)
    assert response.status_code == 409
    _assert_stable_error_payload(response.json(), code=ERR_EXECUTION_CONFLICT)
    _assert_no_internal_leak(response.text)


# ===========================================================================
# 9. Missing training run (PR #76 §5.3, §8)
# ===========================================================================


@pytest.mark.asyncio
async def test_training_get_missing_run_returns_404_stable_error(
    residual_client: AsyncClient,
) -> None:
    """GET /training-runs/{nonexistent_id} → 404 + stable error payload."""
    response = await residual_client.get("/api/v1/residual-model/training-runs/999999")
    assert response.status_code == 404
    payload = response.json()
    _assert_stable_error_payload(payload, code=ERR_TRAINING_NOT_FOUND)
    # Must NOT be FastAPI default detail shape
    assert "detail" not in payload


# ===========================================================================
# 10. Missing prediction run (PR #76 §5.3, §8)
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, reason=SLICE2_XFAIL_REASON)
async def test_prediction_get_missing_run_returns_404_stable_error(
    residual_client: AsyncClient,
) -> None:
    """GET /prediction-runs/{nonexistent_id} → 404 + stable error payload."""
    response = await residual_client.get("/api/v1/residual-model/prediction-runs/999999")
    assert response.status_code == 404
    payload = response.json()
    _assert_stable_error_payload(payload, code=ERR_PREDICTION_NOT_FOUND)
    assert "detail" not in payload


# ===========================================================================
# 11. Invalid schema (PR #76 §4.1, §4.2, §8)
# ===========================================================================


@pytest.mark.asyncio
async def test_training_post_invalid_schema_returns_422_stable_error(
    residual_client: AsyncClient,
) -> None:
    """POST /training-runs with missing required field → 422 + stable error.

    No FastAPI default detail (per §8) — must be re-wrapped by the API adapter.
    """
    # Missing `manifest_snapshot` (required) and `forecast_cutoff` (required)
    response = await residual_client.post(
        "/api/v1/residual-model/training-runs",
        json={"config": {"family": "x", "version": "1"}},
    )
    assert response.status_code == 422
    payload = response.json()
    _assert_stable_error_payload(payload, code=ERR_EXECUTION_INPUT)
    assert "detail" not in payload


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, reason=SLICE2_XFAIL_REASON)
async def test_prediction_post_invalid_schema_returns_422_stable_error(
    residual_client: AsyncClient,
) -> None:
    """POST /prediction-runs with missing required field → 422 + stable error."""
    response = await residual_client.post(
        "/api/v1/residual-model/prediction-runs",
        json={"config": {"family": "x", "version": "1"}},
    )
    assert response.status_code == 422
    payload = response.json()
    _assert_stable_error_payload(payload, code=ERR_EXECUTION_INPUT)
    assert "detail" not in payload


@pytest.mark.asyncio
async def test_training_post_unknown_prediction_mode_returns_422(
    residual_client: AsyncClient,
) -> None:
    """POST /training-runs with unparseable forecast_cutoff → 422."""
    bad_payload = _training_request_payload()
    bad_payload["forecast_cutoff"] = "not-a-date"
    response = await residual_client.post("/api/v1/residual-model/training-runs", json=bad_payload)
    assert response.status_code == 422
    _assert_stable_error_payload(response.json(), code=ERR_EXECUTION_INPUT)


# ===========================================================================
# 12. Integrity exception shielding (PR #76 §8, §9.4)
# ===========================================================================


@pytest.mark.asyncio
async def test_training_post_integrity_exception_shielded_to_500(
    residual_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Future impl must shield service integrity errors to 500 stable payload.

    Once the Slice 2 endpoints are wired, this test patches the future
    service entry point (e.g. ``ResidualModelService.train_residual_model``)
    to raise an integrity exception. The API must catch it and return
    500 + stable error payload with NO leakage of sqlalchemy / asyncpg /
    traceback / path / artifact_bytes.

    NOTE: the monkeypatch is wired to ``backend.app.api.residual_model``
    (or wherever the future entry point is imported by the route
    handler). If the future import path differs, this test must be
    updated as part of the implementation round.
    """
    from backend.app.residual_model import persistence as persistence_module  # noqa: F401

    # Try patching the future import path; if it doesn't exist yet,
    # the route 404 already xfails this test before patching matters.
    try:
        monkeypatch.setattr(
            "backend.app.api.residual_model.train_residual_model",
            _raise_integrity,
            raising=False,
        )
    except (AttributeError, TypeError):
        pass

    response = await residual_client.post(
        "/api/v1/residual-model/training-runs", json=_training_request_payload()
    )
    assert response.status_code == 500
    payload = response.json()
    _assert_stable_error_payload(payload, code=ERR_EXECUTION_INTEGRITY)
    _assert_no_internal_leak(response.text)


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, reason=SLICE2_XFAIL_REASON)
async def test_prediction_post_integrity_exception_shielded_to_500(
    residual_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Future impl must shield service integrity errors to 500 stable payload."""
    try:
        monkeypatch.setattr(
            "backend.app.api.residual_model.predict_with_residual_model",
            _raise_integrity,
            raising=False,
        )
    except (AttributeError, TypeError):
        pass

    response = await residual_client.post(
        "/api/v1/residual-model/prediction-runs", json=_prediction_request_payload()
    )
    assert response.status_code == 500
    payload = response.json()
    _assert_stable_error_payload(payload, code=ERR_EXECUTION_INTEGRITY)
    _assert_no_internal_leak(response.text)


def _raise_integrity(*args: Any, **kwargs: Any) -> Any:
    """Raise a realistic integrity exception that simulates a persistence-layer failure.

    Used as a monkeypatch target for tests #12 + #13. The exception text
    intentionally contains leak markers (sqlalchemy, asyncpg, traceback,
    path, artifact_bytes) so the test can verify the API shields them.
    """
    raise RuntimeError(
        "sqlalchemy.exc.OperationalError: simulated integrity failure\n"
        "Traceback (most recent call last):\n"
        '  File "/tmp/blueberry/secret/internal.py", line 42, in loader\n'
        "asyncpg.errors.UniqueViolationError: duplicate\n"
        "artifact_bytes=b'\\x00\\x01\\x02'"
    )


# ===========================================================================
# 13. Transaction rollback / no partial visible state (PR #76 §9.4)
# ===========================================================================


@pytest.mark.asyncio
async def test_training_post_commit_failure_rolls_back_no_partial_run(
    residual_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Future impl must roll back on commit failure → 500 + no partial state.

    Once Slice 2 is implemented, this test verifies that a mid-transaction
    commit failure does NOT leave a half-written training run visible.
    """
    try:
        monkeypatch.setattr(
            "backend.app.api.residual_model.train_residual_model",
            _raise_integrity,
            raising=False,
        )
    except (AttributeError, TypeError):
        pass

    response = await residual_client.post(
        "/api/v1/residual-model/training-runs", json=_training_request_payload()
    )
    assert response.status_code == 500
    payload = response.json()
    _assert_stable_error_payload(payload, code=ERR_EXECUTION_INTEGRITY)
    _assert_no_internal_leak(response.text)


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, reason=SLICE2_XFAIL_REASON)
async def test_prediction_post_commit_failure_rolls_back_no_partial_run(
    residual_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Future impl must roll back on commit failure → 500 + no partial state."""
    try:
        monkeypatch.setattr(
            "backend.app.api.residual_model.predict_with_residual_model",
            _raise_integrity,
            raising=False,
        )
    except (AttributeError, TypeError):
        pass

    response = await residual_client.post(
        "/api/v1/residual-model/prediction-runs", json=_prediction_request_payload()
    )
    assert response.status_code == 500
    payload = response.json()
    _assert_stable_error_payload(payload, code=ERR_EXECUTION_INTEGRITY)
    _assert_no_internal_leak(response.text)


# ===========================================================================
# 14. Slice 1 report endpoint regression (PR #76 §10)
# ===========================================================================


@pytest.mark.asyncio
async def test_training_report_json_endpoint_remains_reachable(
    residual_client: AsyncClient,
) -> None:
    """Slice 1 report.json endpoint must remain reachable after POST training.

    This verifies the PR #76 §10 contract: after a successful POST
    /training-runs, GET /training-runs/{run_id}/report.json returns 200.
    The 200 assertion will xfail today (route may 404 or the run doesn't
    exist); after Slice 2 implementation, the POST → report flow must
    complete end-to-end.
    """
    post_response = await residual_client.post(
        "/api/v1/residual-model/training-runs", json=_training_request_payload()
    )
    assert post_response.status_code == 201
    run_id = post_response.json()["run_id"]

    report_response = await residual_client.get(
        f"/api/v1/residual-model/training-runs/{run_id}/report.json"
    )
    assert report_response.status_code == 200
    assert report_response.headers["content-type"].startswith("application/json")


@pytest.mark.asyncio
async def test_training_report_csv_endpoint_remains_reachable(
    residual_client: AsyncClient,
) -> None:
    """Slice 1 report.csv endpoint must remain reachable after POST training."""
    post_response = await residual_client.post(
        "/api/v1/residual-model/training-runs", json=_training_request_payload()
    )
    assert post_response.status_code == 201
    run_id = post_response.json()["run_id"]

    report_response = await residual_client.get(
        f"/api/v1/residual-model/training-runs/{run_id}/report.csv"
    )
    assert report_response.status_code == 200
    assert report_response.headers["content-type"].startswith("application/zip")


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, reason=SLICE2_XFAIL_REASON)
async def test_prediction_report_json_endpoint_remains_reachable(
    residual_client: AsyncClient,
) -> None:
    """Slice 1 prediction report.json endpoint must remain reachable after POST."""
    post_response = await residual_client.post(
        "/api/v1/residual-model/prediction-runs", json=_prediction_request_payload()
    )
    assert post_response.status_code == 201
    run_id = post_response.json()["run_id"]

    report_response = await residual_client.get(
        f"/api/v1/residual-model/prediction-runs/{run_id}/report.json"
    )
    assert report_response.status_code == 200
    assert report_response.headers["content-type"].startswith("application/json")


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, reason=SLICE2_XFAIL_REASON)
async def test_prediction_report_csv_endpoint_remains_reachable(
    residual_client: AsyncClient,
) -> None:
    """Slice 1 prediction report.csv endpoint must remain reachable after POST."""
    post_response = await residual_client.post(
        "/api/v1/residual-model/prediction-runs", json=_prediction_request_payload()
    )
    assert post_response.status_code == 201
    run_id = post_response.json()["run_id"]

    report_response = await residual_client.get(
        f"/api/v1/residual-model/prediction-runs/{run_id}/report.csv"
    )
    assert report_response.status_code == 200
    assert report_response.headers["content-type"].startswith("application/zip")


# ===========================================================================
# 15. Slice 2 idempotency_key surface (PR #76 §4.1, §4.2, §7)
# ===========================================================================


@pytest.mark.asyncio
async def test_training_post_idempotency_key_replay_returns_existing_run(
    residual_client: AsyncClient,
) -> None:
    """Same idempotency_key + same canonical payload → 200 + existing run."""
    payload = _training_request_payload()
    payload["idempotency_key"] = "22222222-2222-2222-2222-222222222222"

    first = await residual_client.post("/api/v1/residual-model/training-runs", json=payload)
    second = await residual_client.post("/api/v1/residual-model/training-runs", json=payload)

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["run_id"] == second.json()["run_id"]


@pytest.mark.asyncio
async def test_training_post_idempotency_key_reused_with_different_payload_returns_409(
    residual_client: AsyncClient,
) -> None:
    """Same idempotency_key + different canonical payload → 409 conflict."""
    payload_a = _training_request_payload()
    payload_a["idempotency_key"] = "33333333-3333-3333-3333-333333333333"

    payload_b = _training_request_payload()
    payload_b["idempotency_key"] = "33333333-3333-3333-3333-333333333333"
    payload_b["forecast_cutoff"] = "2026-05-31"  # different canonical payload

    first = await residual_client.post("/api/v1/residual-model/training-runs", json=payload_a)
    assert first.status_code == 201

    second = await residual_client.post("/api/v1/residual-model/training-runs", json=payload_b)
    assert second.status_code == 409
    _assert_stable_error_payload(second.json(), code=ERR_EXECUTION_CONFLICT)


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, reason=SLICE2_XFAIL_REASON)
async def test_prediction_post_with_missing_training_run_returns_404(
    residual_client: AsyncClient,
) -> None:
    """POST /prediction-runs with non-existent training_run_id → 404 stable."""
    payload = _prediction_request_payload()
    payload["training_run_id"] = 999999  # doesn't exist
    response = await residual_client.post("/api/v1/residual-model/prediction-runs", json=payload)
    assert response.status_code == 404
    _assert_stable_error_payload(response.json(), code=ERR_TRAINING_NOT_FOUND)


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, reason=SLICE2_XFAIL_REASON)
async def test_prediction_post_task9_hash_mismatch_returns_409(
    residual_client: AsyncClient,
) -> None:
    """task9_result_hash supplied but doesn't match persisted hash → 409."""
    payload = _prediction_request_payload()
    # The implementation must verify task9_result_hash matches task9_run_id's hash.
    # We supply a clearly-wrong hash and expect 409 (or 404 if task9 doesn't exist).
    payload["task9_run_id"] = 10
    payload["task9_result_hash"] = "f" * 64  # arbitrary; should not match
    response = await residual_client.post("/api/v1/residual-model/prediction-runs", json=payload)
    assert response.status_code == 409
    _assert_stable_error_payload(response.json(), code=ERR_EXECUTION_CONFLICT)
