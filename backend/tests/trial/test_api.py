from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.actual_harvest_import.api_auth import (
    ActualHarvestActorContext,
    get_actual_harvest_actor,
)
from backend.app.actual_harvest_import.api_errors import ActualHarvestApiError
from backend.app.actual_harvest_import.api_schemas import (
    ActualHarvestApiCommitRequest,
    ActualHarvestApiCreateImportRequest,
)
from backend.app.actual_harvest_import.enums import ActualHarvestImportChannel
from backend.app.db.session import get_db_session
from backend.app.main import create_app
from backend.app.trial import (
    TrialActualHarvestCommitResponse,
    TrialActualHarvestImportCreateResponse,
    TrialActualHarvestImportStatusResponse,
    TrialActualHarvestInvalidRowsResponse,
    TrialActualHarvestUploadMetadata,
    TrialActualHarvestUploadResponse,
    TrialApiError,
    TrialApiErrorCode,
    TrialCsvDocument,
    TrialForecastCreateRequest,
    TrialForecastDailyCurveResponse,
    TrialForecastDailyRow,
    TrialForecastSummaryResponse,
    TrialQualityComparisonResponse,
    TrialQualityReportCreateRequest,
    TrialQualityReportResponse,
    get_trial_service,
    serialize_csv,
)

NOW = datetime(2026, 7, 29, 8, 0, tzinfo=UTC)


def _actor(*, preview: bool = True, create: bool = True) -> ActualHarvestActorContext:
    return ActualHarvestActorContext(
        identity="trial-user-1",
        allowed_source_systems=frozenset({"synthetic-farm-system"}),
        allowed_channels=frozenset({ActualHarvestImportChannel.API}),
        may_create=create,
        may_append=create,
        may_preview=preview,
        may_seal=create,
        may_cancel=create,
        may_validate=create,
        may_commit=create,
    )


def _forecast_row(day: int, value: str) -> TrialForecastDailyRow:
    return TrialForecastDailyRow(
        target_date=date(2026, 1, day),
        p50_value_kg=Decimal(value),
        p80_value_kg=Decimal(value) + Decimal("1"),
        p90_value_kg=Decimal(value) + Decimal("2"),
        row_status="COMPLETED",
    )


def _forecast() -> TrialForecastSummaryResponse:
    rows = (_forecast_row(1, "10.000000"), _forecast_row(2, "12.000000"))
    return TrialForecastSummaryResponse(
        run_id="forecast-public-1",
        status="COMPLETED",
        daily_p50_series=rows,
        daily_p80_series=rows,
        daily_p90_series=rows,
        single_day_peak={"target_date": "2026-01-02", "quantity_kg": "14.000000"},
        sustained_seven_day_peak=None,
        season_cumulative_quantity=Decimal("22.000000"),
        mature_inventory_summary={"quantity_kg": "3.000000"},
        backlog_summary={"quantity_kg": "0.000000"},
        model_version="model-v1",
        parameter_version="parameter-v1",
        policy_versions={"forecast": "policy-v1"},
        canonical_public_hash="a" * 64,
    )


def _curve() -> TrialForecastDailyCurveResponse:
    return TrialForecastDailyCurveResponse(
        run_id="forecast-public-1",
        forecast_cutoff_at=NOW,
        rows=(_forecast_row(1, "10.000000"), _forecast_row(2, "12.000000")),
    )


def _quality() -> TrialQualityReportResponse:
    return TrialQualityReportResponse(
        report_id="quality-public-1",
        forecast_identity={"run_id": "forecast-public-1", "model_version": "model-v1"},
        actual_label_snapshot_identity="label-snapshot-1",
        forecast_cutoff_at=NOW,
        label_observation_cutoff_at=NOW,
        forecast_horizon_days=7,
        daily_metrics=({"metric_name": "daily_mae", "metric_status": "COMPUTED"},),
        cumulative_error_status="NOT_COMPUTABLE",
        single_day_peak_error_status="NOT_COMPUTABLE",
        sustained_seven_day_peak_error_status="NOT_COMPUTABLE",
        p80_p90_metric_status="NOT_COMPUTABLE",
        interval_metric_status="NOT_COMPUTABLE",
        breakdowns=(),
        naive_baseline_result={"metric_status": "COMPUTED", "value_kg": "10.000000"},
        computability_status="COMPUTED",
        reason_codes=(),
        coverage_counts={"total": 2, "comparable": 2},
        excluded_row_counts={"excluded": 0, "not_computable": 0},
    )


class SyntheticTrialService:
    def __init__(self) -> None:
        self.forecast_requests: dict[str, TrialForecastCreateRequest] = {}
        self.quality_requests: dict[str, TrialQualityReportCreateRequest] = {}

    async def create_forecast(
        self,
        session: AsyncSession,
        request: TrialForecastCreateRequest,
        actor: ActualHarvestActorContext,
    ) -> TrialForecastSummaryResponse:
        del session
        if not actor.may_create:
            raise TrialApiError(
                TrialApiErrorCode.RESOURCE_NOT_FOUND, status_code=404, message="missing"
            )
        previous = self.forecast_requests.get(request.request_idempotency_key)
        if previous is not None and previous != request:
            raise TrialApiError(
                TrialApiErrorCode.CONFLICTING_REPLAY,
                status_code=409,
                message="conflict",
            )
        self.forecast_requests[request.request_idempotency_key] = request
        return _forecast()

    async def get_forecast(
        self,
        session: AsyncSession,
        run_id: str,
        actor: ActualHarvestActorContext,
    ) -> TrialForecastSummaryResponse:
        del session
        if not actor.may_preview or run_id != "forecast-public-1":
            raise TrialApiError(
                TrialApiErrorCode.RESOURCE_NOT_FOUND, status_code=404, message="missing"
            )
        return _forecast()

    async def get_daily_curve(
        self,
        session: AsyncSession,
        run_id: str,
        actor: ActualHarvestActorContext,
    ) -> TrialForecastDailyCurveResponse:
        del session
        if not actor.may_preview or run_id != "forecast-public-1":
            raise TrialApiError(
                TrialApiErrorCode.RESOURCE_NOT_FOUND, status_code=404, message="missing"
            )
        return _curve()

    async def export_forecast(
        self,
        session: AsyncSession,
        run_id: str,
        actor: ActualHarvestActorContext,
    ) -> TrialCsvDocument:
        del session
        if not actor.may_preview or run_id != "forecast-public-1":
            raise TrialApiError(
                TrialApiErrorCode.RESOURCE_NOT_FOUND, status_code=404, message="missing"
            )
        return TrialCsvDocument(
            filename="forecast-public-1.csv",
            content=serialize_csv(
                ("target_date", "p50_value_kg"),
                (("2026-01-01", Decimal("10.000000")), ("2026-01-02", Decimal("12.000000"))),
            ),
        )

    async def create_import(
        self,
        session: AsyncSession,
        request: ActualHarvestApiCreateImportRequest,
        actor: ActualHarvestActorContext,
    ) -> TrialActualHarvestImportCreateResponse:
        del session, request
        if not actor.may_create:
            raise TrialApiError(
                TrialApiErrorCode.RESOURCE_NOT_FOUND, status_code=404, message="missing"
            )
        return TrialActualHarvestImportCreateResponse(
            import_id="import-public-1",
            status="UPLOADING",
            source_system="synthetic-farm-system",
            source_dataset="synthetic-dataset",
            source_version="v1",
            expected_record_count_or_null=2,
            policy_version="actual-harvest-api-policy-v1",
            canonical_public_hash="b" * 64,
        )

    async def get_import(
        self,
        session: AsyncSession,
        import_id: str,
        actor: ActualHarvestActorContext,
    ) -> TrialActualHarvestImportStatusResponse:
        del session
        if not actor.may_preview or import_id != "import-public-1":
            raise TrialApiError(
                TrialApiErrorCode.RESOURCE_NOT_FOUND, status_code=404, message="missing"
            )
        return TrialActualHarvestImportStatusResponse(
            import_id=import_id,
            status="VALIDATED",
            record_count=2,
            valid_record_count=2,
            invalid_record_count=0,
            committed_record_count=0,
            validation_status="VALIDATED",
            validation_reason_codes=(),
            validation_evidence_hash="c" * 64,
        )

    async def commit_import(
        self,
        session: AsyncSession,
        import_id: str,
        request: ActualHarvestApiCommitRequest,
        actor: ActualHarvestActorContext,
    ) -> TrialActualHarvestCommitResponse:
        del session, request
        if not actor.may_commit or import_id != "import-public-1":
            raise TrialApiError(
                TrialApiErrorCode.RESOURCE_NOT_FOUND, status_code=404, message="missing"
            )
        return TrialActualHarvestCommitResponse(
            import_id=import_id,
            status="COMMITTED",
            committed_record_count=2,
            commit_policy_version="actual-harvest-commit-policy-v1",
            commit_manifest_hash="d" * 64,
            reused_existing_commit=True,
        )

    async def upload_import(
        self,
        session: AsyncSession,
        import_id: str,
        content: bytes,
        metadata: TrialActualHarvestUploadMetadata,
        actor: ActualHarvestActorContext,
    ) -> TrialActualHarvestUploadResponse:
        del session, content, metadata, actor
        return TrialActualHarvestUploadResponse(
            import_id=import_id,
            server_status="VALIDATED",
            source_file_name="harvest.csv",
            source_mime_type="text/csv",
            source_file_sha256="a" * 64,
            uploaded_record_count=2,
            valid_record_count=2,
            invalid_record_count=0,
            validation_status="VALIDATED",
            validation_run_instance_identity_hash_or_null="b" * 64,
            validation_result_hash_or_null="c" * 64,
            reason_codes=(),
        )

    async def get_import_errors(
        self,
        session: AsyncSession,
        import_id: str,
        *,
        page_size: int,
        page_token: str | None,
        actor: ActualHarvestActorContext,
    ) -> TrialActualHarvestInvalidRowsResponse:
        del session, page_size, page_token, actor
        return TrialActualHarvestInvalidRowsResponse(
            import_id=import_id,
            validation_status="VALIDATION_FAILED",
            validation_run_instance_identity_hash_or_null="b" * 64,
            rows=(),
            next_page_token=None,
        )

    async def create_quality_report(
        self,
        session: AsyncSession,
        request: TrialQualityReportCreateRequest,
        actor: ActualHarvestActorContext,
    ) -> TrialQualityReportResponse:
        del session
        if not actor.may_create:
            raise TrialApiError(
                TrialApiErrorCode.RESOURCE_NOT_FOUND, status_code=404, message="missing"
            )
        previous = self.quality_requests.get(request.request_idempotency_key)
        if previous is not None and previous != request:
            raise TrialApiError(
                TrialApiErrorCode.CONFLICTING_REPLAY,
                status_code=409,
                message="conflict",
            )
        self.quality_requests[request.request_idempotency_key] = request
        return _quality()

    async def get_quality_report(
        self,
        session: AsyncSession,
        report_id: str,
        actor: ActualHarvestActorContext,
    ) -> TrialQualityReportResponse:
        del session
        if not actor.may_preview or report_id != "quality-public-1":
            raise TrialApiError(
                TrialApiErrorCode.RESOURCE_NOT_FOUND, status_code=404, message="missing"
            )
        return _quality()

    async def get_quality_comparison(
        self,
        session: AsyncSession,
        report_id: str,
        actor: ActualHarvestActorContext,
    ) -> TrialQualityComparisonResponse:
        del session
        if not actor.may_preview or report_id != "quality-public-1":
            raise TrialApiError(
                TrialApiErrorCode.RESOURCE_NOT_FOUND, status_code=404, message="missing"
            )
        return TrialQualityComparisonResponse(
            report_id=report_id,
            comparison_availability="BLOCKED",
            comparison_status="NOT_COMPUTABLE",
            comparison_policy_version="v0.2-s3-comparison-policy-v1",
            model_baseline_deltas=(),
            reason_codes=("COMPARISON_NOT_AVAILABLE",),
            comparison_public_hash="e" * 64,
        )

    async def export_quality_report(
        self,
        session: AsyncSession,
        report_id: str,
        actor: ActualHarvestActorContext,
    ) -> TrialCsvDocument:
        del session
        if not actor.may_preview or report_id != "quality-public-1":
            raise TrialApiError(
                TrialApiErrorCode.RESOURCE_NOT_FOUND, status_code=404, message="missing"
            )
        return TrialCsvDocument(
            filename="quality-public-1.csv",
            content=serialize_csv(
                ("metric_name", "metric_value"),
                (("daily_mae", Decimal("1.000000")),),
            ),
        )


@pytest.fixture
def synthetic_service() -> SyntheticTrialService:
    return SyntheticTrialService()


@pytest.fixture
def trial_app(synthetic_service: SyntheticTrialService):
    app = create_app()

    async def _session() -> AsyncIterator[None]:
        yield None

    _actor_fixture = _actor_context()
    app.dependency_overrides[get_db_session] = _session
    app.dependency_overrides[get_actual_harvest_actor] = lambda: _actor_fixture
    app.dependency_overrides[get_trial_service] = lambda: synthetic_service
    return app


def _actor_context() -> ActualHarvestActorContext:
    return _actor()


@pytest.fixture
async def client(trial_app) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=trial_app), base_url="http://test"
    ) as client:
        yield client


def _forecast_request(*, key: str = "forecast-key", model: str = "model-v1") -> dict[str, Any]:
    return {
        "season_business_key": "season-2026",
        "farm_business_keys": ["farm-a"],
        "subfarm_business_keys": ["subfarm-a"],
        "variety_business_keys": ["variety-a"],
        "requested_horizons_days": [7],
        "forecast_quantiles": ["P50", "P80", "P90"],
        "forecast_cutoff_at": NOW.isoformat(),
        "label_observation_cutoff_at_or_null": NOW.isoformat(),
        "request_idempotency_key": key,
        "model_identity": model,
        "parameter_version": "parameter-v1",
        "policy_versions": {"forecast": "policy-v1"},
    }


def _quality_request(*, key: str = "quality-key") -> dict[str, Any]:
    return {
        "forecast_run_id": "forecast-public-1",
        "actual_label_snapshot_identity": "label-snapshot-1",
        "forecast_cutoff_at": NOW.isoformat(),
        "label_observation_cutoff_at": NOW.isoformat(),
        "forecast_horizon_days": 7,
        "quality_policy_version": "quality-v1",
        "baseline_policy_version": "baseline-v1",
        "request_idempotency_key": key,
    }


@pytest.mark.asyncio
async def test_forecast_create_api_acceptance(client: AsyncClient) -> None:
    response = await client.post("/api/v1/trial/forecasts", json=_forecast_request())
    assert response.status_code == 200
    assert response.json()["run_id"] == "forecast-public-1"


@pytest.mark.asyncio
async def test_forecast_get_api_acceptance(client: AsyncClient) -> None:
    response = await client.get("/api/v1/trial/forecasts/forecast-public-1")
    assert response.status_code == 200
    assert response.json()["status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_forecast_daily_curve_api_acceptance(client: AsyncClient) -> None:
    response = await client.get("/api/v1/trial/forecasts/forecast-public-1/daily-curve")
    assert response.status_code == 200
    assert len(response.json()["rows"]) == 2


@pytest.mark.asyncio
async def test_forecast_csv_export_acceptance(client: AsyncClient) -> None:
    response = await client.get("/api/v1/trial/forecasts/forecast-public-1/export.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.text.splitlines()[0] == "target_date,p50_value_kg"


@pytest.mark.asyncio
async def test_actual_import_create_api_acceptance(client: AsyncClient) -> None:
    body = {
        "source_system": "synthetic-farm-system",
        "source_dataset": "synthetic-dataset",
        "source_version": "v1",
        "external_batch_id": "batch-1",
        "idempotency_key": "import-key-1",
        "submitted_at": NOW.isoformat(),
        "submitted_by_identity": "trial-user-1",
        "import_channel": "api",
        "raw_payload_hash": "a" * 64,
        "schema_version": "synthetic-v1",
        "mapping_policy_version": "mapping-v1",
        "validation_policy_version": "validation-v1",
        "source_semantics_attestation": {
            "attestation_version": "attestation-v1",
            "physical_event": "FARM_PICK",
            "quantity_basis": "OBSERVED_WEIGHT",
            "quantity_unit": "KG",
            "missing_record_semantics": "UNKNOWN_NOT_ZERO",
        },
        "source_semantics_attestation_hash": "b" * 64,
    }
    response = await client.post("/api/v1/trial/actual-harvest/imports", json=body)
    assert response.status_code == 200
    assert response.json()["status"] == "UPLOADING"


@pytest.mark.asyncio
async def test_actual_import_get_api_acceptance(client: AsyncClient) -> None:
    response = await client.get("/api/v1/trial/actual-harvest/imports/import-public-1")
    assert response.status_code == 200
    assert response.json()["validation_status"] == "VALIDATED"


@pytest.mark.asyncio
async def test_actual_import_commit_api_acceptance(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/trial/actual-harvest/imports/import-public-1/commit",
        json={"validation_run_instance_identity_hash": "f" * 64},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "COMMITTED"


@pytest.mark.asyncio
async def test_actual_import_upload_uses_raw_binary_body(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/trial/actual-harvest/imports/import-public-1/upload",
        content=b"raw-csv-bytes",
        headers={"content-type": "text/csv", "x-file-name": "harvest.csv"},
    )
    assert response.status_code == 200
    assert response.json()["validation_status"] == "VALIDATED"


@pytest.mark.asyncio
async def test_actual_import_errors_api_acceptance(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/trial/actual-harvest/imports/import-public-1/errors",
        params={"page_size": 1, "page_token": "page-1"},
    )
    assert response.status_code == 200
    assert response.json()["validation_status"] == "VALIDATION_FAILED"


@pytest.mark.asyncio
async def test_upload_rejects_unsupported_content_type_with_typed_error(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/trial/actual-harvest/imports/import-public-1/upload",
        content=b"raw-bytes",
        headers={"content-type": "application/octet-stream", "x-file-name": "harvest.csv"},
    )
    assert response.status_code == 415
    assert response.json()["code"] == "TRIAL_UNSUPPORTED_CONTENT_TYPE"


@pytest.mark.asyncio
async def test_actor_configuration_fails_closed_without_server_config() -> None:
    with pytest.MonkeyPatch.context() as monkeypatch:
        for name in (
            "TRIAL_ACTOR_IDENTITY",
            "TRIAL_ACTOR_ALLOWED_SOURCE_SYSTEMS",
            "TRIAL_ACTOR_ALLOWED_CHANNELS",
            "TRIAL_ACTOR_PERMISSIONS",
        ):
            monkeypatch.delenv(name, raising=False)
        with pytest.raises(ActualHarvestApiError) as error:
            await get_actual_harvest_actor()
        assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_quality_report_create_api_acceptance(client: AsyncClient) -> None:
    response = await client.post("/api/v1/trial/quality-reports", json=_quality_request())
    assert response.status_code == 200
    assert response.json()["computability_status"] == "COMPUTED"


@pytest.mark.asyncio
async def test_quality_report_get_api_acceptance(client: AsyncClient) -> None:
    response = await client.get("/api/v1/trial/quality-reports/quality-public-1")
    assert response.status_code == 200
    assert response.json()["coverage_counts"] == {"total": 2, "comparable": 2}


@pytest.mark.asyncio
async def test_quality_comparison_get_api_acceptance(client: AsyncClient) -> None:
    response = await client.get("/api/v1/trial/quality-reports/quality-public-1/comparison")
    assert response.status_code == 200
    assert response.json()["comparison_availability"] == "BLOCKED"


@pytest.mark.asyncio
async def test_quality_csv_export_acceptance(client: AsyncClient) -> None:
    response = await client.get("/api/v1/trial/quality-reports/quality-public-1/export.csv")
    assert response.status_code == 200
    assert response.text.splitlines() == ["metric_name,metric_value", "daily_mae,1.000000"]


def test_openapi_schema_acceptance(trial_app) -> None:
    paths = trial_app.openapi()["paths"]
    expected = {
        "/api/v1/trial/forecasts",
        "/api/v1/trial/forecasts/{run_id}",
        "/api/v1/trial/forecasts/{run_id}/daily-curve",
        "/api/v1/trial/forecasts/{run_id}/export.csv",
        "/api/v1/trial/actual-harvest/imports",
        "/api/v1/trial/actual-harvest/imports/{import_id}",
        "/api/v1/trial/actual-harvest/imports/{import_id}/upload",
        "/api/v1/trial/actual-harvest/imports/{import_id}/errors",
        "/api/v1/trial/actual-harvest/imports/{import_id}/commit",
        "/api/v1/trial/quality-reports",
        "/api/v1/trial/quality-reports/{report_id}",
        "/api/v1/trial/quality-reports/{report_id}/comparison",
        "/api/v1/trial/quality-reports/{report_id}/export.csv",
    }
    assert {path for path in paths if path.startswith("/api/v1/trial")} == expected


@pytest.mark.asyncio
async def test_sanitized_error_acceptance(client: AsyncClient) -> None:
    response = await client.post("/api/v1/trial/forecasts", json={})
    assert response.status_code == 422
    body = response.json()
    serialized = str(body).lower()
    assert body["code"] == "TRIAL_REQUEST_INVALID"
    assert "traceback" not in serialized
    assert "sqlalchemy" not in serialized
    assert "stack" not in serialized


@pytest.mark.asyncio
async def test_authorization_concealment_acceptance(client: AsyncClient, trial_app) -> None:
    trial_app.dependency_overrides[get_actual_harvest_actor] = lambda: _actor(preview=False)
    response = await client.get("/api/v1/trial/forecasts/secret-run")
    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_exact_replay_api_acceptance(client: AsyncClient) -> None:
    first = await client.post("/api/v1/trial/forecasts", json=_forecast_request(key="same"))
    second = await client.post("/api/v1/trial/forecasts", json=_forecast_request(key="same"))
    assert first.status_code == second.status_code == 200
    assert first.json()["canonical_public_hash"] == second.json()["canonical_public_hash"]


@pytest.mark.asyncio
async def test_conflicting_replay_api_acceptance(client: AsyncClient) -> None:
    first = await client.post("/api/v1/trial/forecasts", json=_forecast_request(key="conflict"))
    second = await client.post(
        "/api/v1/trial/forecasts",
        json=_forecast_request(key="conflict", model="model-v2"),
    )
    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["code"] == "CONFLICTING_REPLAY"


@pytest.mark.asyncio
async def test_no_frontend_recomputation_acceptance(client: AsyncClient) -> None:
    response = await client.get("/api/v1/trial/forecasts/forecast-public-1")
    body = response.json()
    assert body["single_day_peak"] == {"target_date": "2026-01-02", "quantity_kg": "14.000000"}
    assert body["season_cumulative_quantity"] == "22.000000"
