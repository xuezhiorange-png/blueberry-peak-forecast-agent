"""API contract tests for TASK-010 residual-model report download endpoints.

These tests verify:
- 200 + correct media_type + Content-Disposition + ZIP namelist + JSON shape
- 404 stable error payload for missing training / prediction runs
- 500 stable error payload for persistence / loader integrity errors, with
  zero leakage of sqlalchemy / asyncpg / traceback / local paths / artifact
  binary into the response body.

Strategy:
- Use AsyncClient + ASGITransport with dependency_overrides[get_db_session]
  (matches existing backend/tests/test_harvest_state_api.py pattern).
- The persistence layer requires a complex seed (artifact SHA-256 chain,
  manifest row payload integrity, dependency versions, etc.) that is far
  out of scope for an API contract test. So happy-path tests use
  monkeypatch to inject pre-built ResidualTrainingExecutionResult /
  ResidualPredictionExecutionResult + ORM-like run objects with the
  fields the renderer needs (id / created_at / manifest_snapshot).
- Missing-run tests hit the API with a non-existent run id and rely on
  the real loader path (which returns None for a missing run).
- Integrity-error tests monkeypatch the loader to raise.
- The API module is the canonical place to monkeypatch: FastAPI route
  handlers use the local reference at call time, so patching at the
  persistence / repositories module would not affect the route.
"""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.app.db.session import get_db_session
from backend.app.main import create_app
from backend.app.models.residual_model import (
    ResidualModelArtifact,
    ResidualModelExecutionAttempt,
    ResidualModelManifestRow,
    ResidualModelPredictionRow,
    ResidualModelPredictionRun,
    ResidualModelTrainingRun,
)
from backend.app.residual_model.reporting import (
    PREDICTION_CSV_REPORT_SCHEMA_VERSION,
    PREDICTION_JSON_REPORT_SCHEMA_VERSION,
    TRAINING_CSV_REPORT_SCHEMA_VERSION,
    TRAINING_JSON_REPORT_SCHEMA_VERSION,
)
from backend.app.residual_model.schemas import (
    ResidualPredictionExecutionResult,
    ResidualPredictionRow,
    ResidualTrainingExecutionResult,
)

# ---------------------------------------------------------------------------
# Helpers — ORM-like run shim
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _RunShim:
    """Minimal ORM-like object for the API module's `run` variable.

    The real ORM row carries hundreds of columns. The API only needs:
    - run.id             (for renderer run_id + Content-Disposition filename)
    - run.created_at     (for renderer created_at)
    - run.manifest_snapshot (for training renderers' manifest_snapshot)
    """

    id: int
    created_at: datetime
    manifest_snapshot: dict[str, Any]


def _training_manifest_snapshot() -> dict[str, Any]:
    return {
        "rows": [
            {
                "manifest_id": "m-1",
                "season_id": 1,
                "split": "train",
                "feature_count": 3,
                "source_refs": ["analytics", "task9"],
            }
        ],
        "summary": {"row_count": 1},
    }


def _async_return(value: Any) -> Any:
    """Build a coroutine factory that returns ``value`` when awaited.

    Useful for monkeypatching async loader functions in API tests so
    the route handler can still ``await`` them.
    """

    async def _coro(*args: Any, **kwargs: Any) -> Any:
        return value

    return _coro


def _build_training_result() -> ResidualTrainingExecutionResult:
    return ResidualTrainingExecutionResult(
        execution_status="completed",
        eligibility_status="eligible",
        model_family="test-model",
        model_version="1.0.0",
        feature_schema_version="1",
        artifact_schema_version="1",
        training_signature="a" * 64,
        config_hash="b" * 64,
        manifest_hash="c" * 64,
        sample_count=10,
        distinct_season_count=1,
        distinct_factory_count=1,
        warnings=(),
        blockers=(),
        feature_audit_summary={"visible": ["f1", "f2"]},
        metrics={"feature_names": ["f1", "f2"]},
        eligibility_reasons=(),
        input_snapshot={"manifest_summary": {"row_count": 1}},
        artifacts=(),  # bytes not needed for JSON; CSV renderer uses output.artifacts
    )


def _build_prediction_result(
    *,
    with_warnings: bool = False,
    with_blockers: bool = False,
) -> ResidualPredictionExecutionResult:
    return ResidualPredictionExecutionResult(
        execution_status="completed",
        mode="residual_corrected",
        model_run_id=1,
        task9_run_id=10,
        task9_result_hash="a" * 64,
        config_hash="b" * 64,
        prediction_input_signature="d" * 64,
        prediction_hash="e" * 64,
        warnings=("some warning",) if with_warnings else (),
        blockers=("some blocker",) if with_blockers else (),
        fallback_reason=None,
        rows=(
            ResidualPredictionRow(
                model_run_id=1,
                prediction_run_id=0,
                task9_run_id=10,
                task9_result_hash="a" * 64,
                destination_factory_id=1,
                arrival_local_date=__import__("datetime").date(2026, 3, 2),
                forecast_horizon_days=1,
                structural_p50_kg="100",
                structural_p80_kg="110",
                structural_p90_kg="120",
                raw_residual_p50_kg="0",
                raw_residual_p80_kg="0",
                raw_residual_p90_kg="0",
                corrected_raw_p50_kg="100",
                corrected_raw_p80_kg="110",
                corrected_raw_p90_kg="120",
                corrected_p50_kg="100",
                corrected_p80_kg="110",
                corrected_p90_kg="120",
                nonnegative_projection_applied=False,
                quantile_projection_applied=False,
                projection_reasons=[],
                feature_vector_hash="a" * 64,
                feature_audit_hash="a" * 64,
                prediction_hash="a" * 64,
                mode="residual_corrected",
            ),
        ),
        input_snapshot={"some": "input"},
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def residual_db_session() -> AsyncIterator[AsyncSession]:
    """Empty SQLite session with residual_model tables created.

    The API contract tests below do NOT exercise the real persistence
    loader (Section 6 / 8 / 8.5 / 8.7 / 10 integrity chain) — they
    monkeypatch the loaders. But missing-run tests use the real
    get_residual_training_run / get_residual_prediction_run queries,
    so the tables must exist for those to return None instead of
    OperationalError.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(_create_residual_tables)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sessionmaker() as session:
        yield session
    await engine.dispose()


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


@pytest.fixture
async def residual_client(residual_db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def _override() -> AsyncIterator[AsyncSession]:
        yield residual_db_session

    app.dependency_overrides[get_db_session] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


# ---------------------------------------------------------------------------
# 1. Training JSON endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_training_json_endpoint_returns_200_with_expected_shape(
    residual_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = 42
    run_shim = _RunShim(
        id=run_id,
        created_at=datetime(2026, 6, 26, 12, 0, tzinfo=UTC),
        manifest_snapshot=_training_manifest_snapshot(),
    )
    loaded = _build_training_result()

    async def _fake_get(session: AsyncSession, *, run_id: int) -> _RunShim | None:
        return run_shim if run_id == run_id else None

    # Patch at the API module namespace (handlers use local reference).
    monkeypatch.setattr(
        "backend.app.api.residual_model.get_residual_training_run",
        _fake_get,
    )
    monkeypatch.setattr(
        "backend.app.api.residual_model.load_residual_training_run_by_id",
        _async_return(loaded),
    )

    response = await residual_client.get(
        f"/api/v1/residual-model/training-runs/{run_id}/report.json"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    payload = response.json()
    assert payload["report_schema_version"] == TRAINING_JSON_REPORT_SCHEMA_VERSION
    assert payload["report_schema_version"] == "task10-residual-training-report-v1"
    assert payload["run"]["run_id"] == run_id
    # No artifact_bytes leakage
    assert "artifact_bytes" not in response.text
    # Content-Disposition
    cd = response.headers["content-disposition"]
    assert f'filename="residual-training-run-{run_id}.json"' in cd


# ---------------------------------------------------------------------------
# 2. Training CSV endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_training_csv_endpoint_returns_zip_with_expected_namelist(
    residual_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = 7
    run_shim = _RunShim(
        id=run_id,
        created_at=datetime(2026, 6, 26, 12, 0, tzinfo=UTC),
        manifest_snapshot=_training_manifest_snapshot(),
    )
    loaded = _build_training_result()

    monkeypatch.setattr(
        "backend.app.api.residual_model.get_residual_training_run",
        _async_return(run_shim),
    )
    monkeypatch.setattr(
        "backend.app.api.residual_model.load_residual_training_run_by_id",
        _async_return(loaded),
    )

    response = await residual_client.get(
        f"/api/v1/residual-model/training-runs/{run_id}/report.csv"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = set(archive.namelist())
        for required in (
            "manifest.json",
            "run.csv",
            "artifacts.csv",
            "metrics.json",
            "warnings.csv",
            "blockers.csv",
        ):
            assert required in names, f"missing {required} in {sorted(names)}"
        # manifest_rows.csv is present when manifest_snapshot has rows
        assert "manifest_rows.csv" in names
        # Verify schema_version in manifest.json
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["report_schema_version"] == TRAINING_CSV_REPORT_SCHEMA_VERSION
        assert manifest["report_schema_version"] == "task10-residual-training-csv-report-v1"
    cd = response.headers["content-disposition"]
    assert f'filename="residual-training-run-{run_id}.zip"' in cd


# ---------------------------------------------------------------------------
# 3. Prediction JSON endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prediction_json_endpoint_returns_200_with_expected_shape(
    residual_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = 99
    run_shim = _RunShim(
        id=run_id,
        created_at=datetime(2026, 6, 26, 12, 0, tzinfo=UTC),
        manifest_snapshot={},
    )
    loaded = _build_prediction_result(with_warnings=True, with_blockers=True)

    monkeypatch.setattr(
        "backend.app.api.residual_model.get_residual_prediction_run",
        _async_return(run_shim),
    )
    monkeypatch.setattr(
        "backend.app.api.residual_model.load_residual_prediction_run_by_id",
        _async_return(loaded),
    )

    response = await residual_client.get(
        f"/api/v1/residual-model/prediction-runs/{run_id}/report.json"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    payload = response.json()
    assert payload["report_schema_version"] == PREDICTION_JSON_REPORT_SCHEMA_VERSION
    assert payload["report_schema_version"] == "task10-residual-prediction-report-v1"
    assert payload["run"]["run_id"] == run_id
    # warnings / blockers preserved (not silently dropped)
    assert "some warning" in payload["output"]["warnings"]
    assert "some blocker" in payload["output"]["blockers"]
    cd = response.headers["content-disposition"]
    assert f'filename="residual-prediction-run-{run_id}.json"' in cd


# ---------------------------------------------------------------------------
# 4. Prediction CSV endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prediction_csv_endpoint_returns_zip_with_expected_namelist(
    residual_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = 100
    run_shim = _RunShim(
        id=run_id,
        created_at=datetime(2026, 6, 26, 12, 0, tzinfo=UTC),
        manifest_snapshot={},
    )
    loaded = _build_prediction_result()

    monkeypatch.setattr(
        "backend.app.api.residual_model.get_residual_prediction_run",
        _async_return(run_shim),
    )
    monkeypatch.setattr(
        "backend.app.api.residual_model.load_residual_prediction_run_by_id",
        _async_return(loaded),
    )

    response = await residual_client.get(
        f"/api/v1/residual-model/prediction-runs/{run_id}/report.csv"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = set(archive.namelist())
        for required in (
            "manifest.json",
            "run.csv",
            "prediction_rows.csv",
            "warnings.csv",
            "blockers.csv",
        ):
            assert required in names, f"missing {required} in {sorted(names)}"
        # CSV does NOT include artifacts.csv or metrics.json (those are
        # training-only)
        assert "artifacts.csv" not in names
        assert "metrics.json" not in names
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["report_schema_version"] == PREDICTION_CSV_REPORT_SCHEMA_VERSION
    cd = response.headers["content-disposition"]
    assert f'filename="residual-prediction-run-{run_id}.zip"' in cd


# ---------------------------------------------------------------------------
# 5. Missing run → 404 stable payload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_training_run_returns_stable_404_payload(
    residual_client: AsyncClient,
) -> None:
    response = await residual_client.get("/api/v1/residual-model/training-runs/999/report.json")

    assert response.status_code == 404
    body = response.json()
    assert body == {
        "error": {
            "code": "RESIDUAL_MODEL_TRAINING_RUN_NOT_FOUND",
            "message": "Residual-model training run was not found.",
        }
    }
    assert "detail" not in body


@pytest.mark.asyncio
async def test_missing_prediction_run_returns_stable_404_payload(
    residual_client: AsyncClient,
) -> None:
    response = await residual_client.get("/api/v1/residual-model/prediction-runs/999/report.json")

    assert response.status_code == 404
    body = response.json()
    assert body == {
        "error": {
            "code": "RESIDUAL_MODEL_PREDICTION_RUN_NOT_FOUND",
            "message": "Residual-model prediction run was not found.",
        }
    }
    assert "detail" not in body


@pytest.mark.asyncio
async def test_missing_training_run_csv_returns_stable_404_payload(
    residual_client: AsyncClient,
) -> None:
    response = await residual_client.get("/api/v1/residual-model/training-runs/999/report.csv")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "RESIDUAL_MODEL_TRAINING_RUN_NOT_FOUND"
    assert "detail" not in body


@pytest.mark.asyncio
async def test_missing_prediction_run_csv_returns_stable_404_payload(
    residual_client: AsyncClient,
) -> None:
    response = await residual_client.get("/api/v1/residual-model/prediction-runs/999/report.csv")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "RESIDUAL_MODEL_PREDICTION_RUN_NOT_FOUND"
    assert "detail" not in body


# ---------------------------------------------------------------------------
# 6. Integrity error shielding → 500 stable payload, no internal leakage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_training_integrity_error_returns_stable_500_without_leak(
    residual_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = 5
    run_shim = _RunShim(
        id=run_id,
        created_at=datetime(2026, 6, 26, 12, 0, tzinfo=UTC),
        manifest_snapshot=_training_manifest_snapshot(),
    )

    async def _fake_get(session: AsyncSession, *, run_id: int) -> _RunShim:
        return run_shim

    async def _raise_sqlalchemy_error(
        session: AsyncSession, *, run_id: int
    ) -> ResidualTrainingExecutionResult:
        # Simulate an internal sqlalchemy/asyncpg-style exception that
        # contains strings that MUST NOT leak through the API.
        raise RuntimeError(
            "sqlalchemy.exc.OperationalError: "
            "asyncpg connection to /var/lib/postgresql/data failed; "
            "Traceback (most recent call last): File '/app/secret/path.py' line 42"
        )

    monkeypatch.setattr(
        "backend.app.api.residual_model.get_residual_training_run",
        _fake_get,
    )
    monkeypatch.setattr(
        "backend.app.api.residual_model.load_residual_training_run_by_id",
        _raise_sqlalchemy_error,
    )

    response = await residual_client.get(
        f"/api/v1/residual-model/training-runs/{run_id}/report.json"
    )

    assert response.status_code == 500
    body = response.json()
    assert body == {
        "error": {
            "code": "RESIDUAL_MODEL_REPORT_INTEGRITY_ERROR",
            "message": "Residual-model report could not be generated.",
        }
    }
    serialized = str(body).lower()
    assert "detail" not in body
    assert "traceback" not in serialized
    assert "sqlalchemy" not in serialized
    assert "asyncpg" not in serialized
    assert "/var/lib/postgresql" not in serialized
    assert "/app/secret/path" not in serialized
    assert "artifact_bytes" not in serialized


@pytest.mark.asyncio
async def test_prediction_integrity_error_returns_stable_500_without_leak(
    residual_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = 5

    async def _fake_get(session: AsyncSession, *, run_id: int) -> _RunShim:
        return _RunShim(
            id=run_id,
            created_at=datetime(2026, 6, 26, 12, 0, tzinfo=UTC),
            manifest_snapshot={},
        )

    async def _raise_internal(
        session: AsyncSession, *, run_id: int
    ) -> ResidualPredictionExecutionResult:
        raise RuntimeError("sqlalchemy.exc.OperationalError: asyncpg traceback leak attempt")

    monkeypatch.setattr(
        "backend.app.api.residual_model.get_residual_prediction_run",
        _fake_get,
    )
    monkeypatch.setattr(
        "backend.app.api.residual_model.load_residual_prediction_run_by_id",
        _raise_internal,
    )

    response = await residual_client.get(
        f"/api/v1/residual-model/prediction-runs/{run_id}/report.json"
    )

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "RESIDUAL_MODEL_REPORT_INTEGRITY_ERROR"
    serialized = str(body).lower()
    assert "detail" not in body
    assert "traceback" not in serialized
    assert "sqlalchemy" not in serialized
    assert "asyncpg" not in serialized


# ---------------------------------------------------------------------------
# Path validation: non-integer run_id → 422 with FastAPI default detail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_integer_run_id_uses_fastapi_default_422(
    residual_client: AsyncClient,
) -> None:
    """Non-integer run_id is rejected by FastAPI's Path(..., int) validation.

    The TASK-010 contract only requires stable payloads for 404 (missing
    run) and 500 (integrity error). For 422 validation, FastAPI's default
    `{"detail": [...]}` is acceptable.
    """
    response = await residual_client.get(
        "/api/v1/residual-model/training-runs/not-an-int/report.json"
    )
    assert response.status_code == 422
    body = response.json()
    assert "detail" in body  # FastAPI default
