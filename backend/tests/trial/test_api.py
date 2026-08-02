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
)
from backend.app.actual_harvest_import.enums import ActualHarvestImportChannel
from backend.app.db.session import get_db_session
from backend.app.main import create_app
from backend.app.trial import (
    DefaultTrialApplicationService,
    TrialActualHarvestCommitResponse,
    TrialActualHarvestImportCreateRequest,
    TrialActualHarvestImportCreateResponse,
    TrialActualHarvestImportStatusResponse,
    TrialActualHarvestInvalidRowsResponse,
    TrialActualHarvestUploadMetadata,
    TrialActualHarvestUploadResponse,
    TrialApiError,
    TrialApiErrorCode,
    TrialCsvDocument,
    TrialForecastBacklogSummaryResponse,
    TrialForecastCreateRequest,
    TrialForecastDailyCurveResponse,
    TrialForecastDailyRow,
    TrialForecastInputAuthorityItem,
    TrialForecastInputAuthorityResponse,
    TrialForecastInventorySummaryResponse,
    TrialForecastPolicyVersionsResponse,
    TrialForecastSingleDayPeakResponse,
    TrialForecastSummaryResponse,
    TrialForecastSustainedSevenDayPeakResponse,
    TrialQualityComparisonResponse,
    TrialQualityReportCreateRequest,
    TrialQualityReportResponse,
    get_trial_service,
    serialize_csv,
)

NOW = datetime(2026, 7, 29, 8, 0, tzinfo=UTC)


def _actor(
    *,
    preview: bool = True,
    create: bool = True,
    channels: frozenset[ActualHarvestImportChannel] | None = None,
) -> ActualHarvestActorContext:
    return ActualHarvestActorContext(
        identity="trial-user-1",
        allowed_source_systems=frozenset({"synthetic-farm-system"}),
        allowed_channels=channels or frozenset({ActualHarvestImportChannel.API}),
        may_create=create,
        may_append=create,
        may_preview=preview,
        may_seal=create,
        may_cancel=create,
        may_validate=create,
        may_commit=create,
        may_read_forecast_authority=create,
        may_create_forecast=create,
        may_read_forecast=preview,
        may_export_forecast=preview,
        may_create_quality=create,
        may_read_quality=preview,
        may_read_quality_comparison=preview,
        may_export_quality=preview,
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
        single_day_peak=TrialForecastSingleDayPeakResponse(
            date=date(2026, 1, 2),
            quantity_kg=Decimal("14.000000"),
            tie_break="EARLIEST_DATE",
        ),
        sustained_seven_day_peak=TrialForecastSustainedSevenDayPeakResponse(
            start_date=date(2026, 1, 2),
            end_date=date(2026, 1, 8),
            cumulative_quantity_kg=Decimal("98.000000"),
            daily_average_kg_per_day=Decimal("14.000000"),
            window_days=7,
            metric="ROLLING_CUMULATIVE",
            date_continuity="STRICT_CALENDAR_DAYS",
            tie_break="EARLIEST_START_DATE",
        ),
        season_cumulative_quantity=Decimal("22.000000"),
        mature_inventory_summary=TrialForecastInventorySummaryResponse(
            opening_quantity_kg=Decimal("3.000000"),
            closing_quantity_kg=Decimal("2.000000"),
        ),
        backlog_summary=TrialForecastBacklogSummaryResponse(quantity_kg=Decimal("0.000000")),
        model_version="model-v1",
        parameter_version="parameter-v1",
        policy_versions=TrialForecastPolicyVersionsResponse(forecast="policy-v1"),
        canonical_public_hash="a" * 64,
    )


def _curve() -> TrialForecastDailyCurveResponse:
    return TrialForecastDailyCurveResponse(
        run_id="forecast-public-1",
        forecast_cutoff_at=NOW,
        rows=(_forecast_row(1, "10.000000"), _forecast_row(2, "12.000000")),
    )


def _quality() -> TrialQualityReportResponse:
    identity = {
        "forecast_run_id": "a" * 64,
        "actual_harvest_import_id": "import-public-1",
        "actual_label_snapshot_identity": "a" * 64,
        "s2_run_identity": "b" * 64,
        "s2_manifest_identity": "c" * 64,
        "s2_binding_row_set_hash": "d" * 64,
        "evaluation_request_hash": "e" * 64,
        "evaluation_instance_hash": "f" * 64,
        "quality_manifest_hash": "1" * 64,
        "metric_result_set_hash": "2" * 64,
        "breakdown_result_set_hash": "3" * 64,
        "baseline_result_set_hash": "4" * 64,
        "comparison_result_set_hash": "5" * 64,
        "metric_policy_version": "metric-v1",
        "baseline_policy_version": "baseline-v1",
        "comparison_policy_version_or_null": None,
        "model_identity": "model-v1",
    }
    metric = {
        "metric_name": "daily_mae",
        "metric_status": "COMPUTED",
        "metric_value_or_null": "1.000000",
        "numerator_or_null": "1.000000",
        "denominator_or_null": "1.000000",
        "reason_codes": [],
    }
    peak = {
        "metric_status": "NOT_COMPUTABLE",
        "metric_value_or_null": None,
        "business_date_or_null": None,
        "window_start_date_or_null": None,
        "window_end_date_or_null": None,
        "reason_codes": ["NOT_AVAILABLE"],
    }
    coverage = {
        "quantile": "P80",
        "metric_status": "COMPUTED",
        "covered_count_or_null": 2,
        "total_count": 2,
        "coverage_ratio_or_null": "1.000000",
        "reason_codes": [],
    }

    def horizon(days: int) -> dict[str, object]:
        return {
            "horizon_days": days,
            "daily_overlay": [
                {
                    "business_date": "2026-01-01",
                    "forecast_p50_kg_or_null": "10.000000",
                    "forecast_p80_kg_or_null": "11.000000",
                    "forecast_p90_kg_or_null": "12.000000",
                    "actual_quantity_kg_or_null": "9.000000",
                    "actual_available": True,
                    "coverage_state": "AVAILABLE",
                    "exclusion_reason_codes": [],
                }
            ],
            "daily_metrics": [metric],
            "cumulative_metric": {**metric, "metric_name": "cumulative_error"},
            "single_day_peak": peak,
            "sustained_seven_day_peak": peak,
            "p80_coverage": coverage,
            "p90_coverage": {**coverage, "quantile": "P90"},
            "interval_metric": {
                "metric_status": "NOT_COMPUTABLE",
                "lower_bound_available": False,
                "lower_bound_value_or_null": None,
                "upper_bound_value_or_null": None,
                "metric_value_or_null": None,
                "reason_codes": ["NOT_AVAILABLE"],
            },
            "coverage_counts": {"total": 2, "covered": 2},
            "excluded_row_counts": {"excluded": 0, "not_computable": 0},
            "reason_codes": [],
        }

    return TrialQualityReportResponse.model_validate(
        {
            "report_id": "a" * 64,
            "forecast_identity": identity,
            "actual_label_snapshot_identity": "a" * 64,
            "forecast_cutoff_at": NOW,
            "label_observation_cutoff_at": NOW,
            "requested_horizons_days": [7, 14, 21],
            "horizons": [horizon(7), horizon(14), horizon(21)],
            "daily_metrics": [metric],
            "cumulative_error": {**metric, "metric_name": "cumulative_error"},
            "single_day_peak": peak,
            "sustained_seven_day_peak": peak,
            "p80_coverage": coverage,
            "p90_coverage": {**coverage, "quantile": "P90"},
            "interval_metric": {
                "metric_status": "NOT_COMPUTABLE",
                "lower_bound_available": False,
                "lower_bound_value_or_null": None,
                "upper_bound_value_or_null": None,
                "metric_value_or_null": None,
                "reason_codes": ["NOT_AVAILABLE"],
            },
            "breakdowns": [],
            "naive_baseline_results": [],
            "computability_status": "COMPUTED",
            "reason_codes": [],
            "coverage_counts": {"total": 2, "comparable": 2},
            "excluded_row_counts": {"excluded": 0, "not_computable": 0},
        }
    )


class SyntheticTrialService:
    def __init__(self) -> None:
        self.forecast_requests: dict[str, TrialForecastCreateRequest] = {}
        self.quality_requests: dict[str, TrialQualityReportCreateRequest] = {}
        self.upload_calls: list[str] = []

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
        key = (
            request.farm_business_key,
            request.subfarm_business_key_or_null,
            request.variety_business_key,
            request.season_business_key,
            request.destination_factory_business_key,
        )
        previous = self.forecast_requests.get(str(key))
        if previous is not None and previous != request:
            raise TrialApiError(
                TrialApiErrorCode.CONFLICTING_REPLAY,
                status_code=409,
                message="conflict",
            )
        self.forecast_requests[str(key)] = request
        return _forecast()

    async def get_forecast_input_authority(
        self,
        session: AsyncSession,
        actor: ActualHarvestActorContext,
    ) -> TrialForecastInputAuthorityResponse:
        del session
        if not actor.may_read_forecast_authority:
            raise TrialApiError(
                TrialApiErrorCode.RESOURCE_NOT_FOUND, status_code=404, message="missing"
            )
        return TrialForecastInputAuthorityResponse(
            forecast_input_authority_hash="a" * 64,
            authority_available_at=NOW,
            items=(
                TrialForecastInputAuthorityItem(
                    farm_business_key="farm-a",
                    subfarm_business_key_or_null="subfarm-a",
                    season_business_key="season-2026",
                    variety_business_key="variety-a",
                    destination_factory_business_key="factory-a",
                    plan_version="1",
                    plan_row_hash="b" * 64,
                    planting_area_mu=Decimal("10.000000"),
                ),
            ),
        )

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
                ("target_date", "p50_value_kg", "p80_value_kg", "p90_value_kg", "row_status"),
                (
                    (
                        "2026-01-01",
                        Decimal("10.000000"),
                        Decimal("11.000000"),
                        Decimal("12.000000"),
                        "COMPLETED",
                    ),
                    (
                        "2026-01-02",
                        Decimal("12.000000"),
                        Decimal("13.000000"),
                        Decimal("14.000000"),
                        "COMPLETED",
                    ),
                ),
            ),
        )

    async def create_import(
        self,
        session: AsyncSession,
        request: TrialActualHarvestImportCreateRequest,
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

    async def authorize_import_upload(
        self,
        session: AsyncSession,
        import_id: str,
        actor: ActualHarvestActorContext,
    ) -> None:
        del session
        self.upload_calls.append("authorize_import_upload")
        if not actor.may_append or import_id != "import-public-1":
            raise TrialApiError(
                TrialApiErrorCode.RESOURCE_NOT_FOUND, status_code=404, message="missing"
            )

    async def upload_import(
        self,
        session: AsyncSession,
        import_id: str,
        content: bytes,
        metadata: TrialActualHarvestUploadMetadata,
        actor: ActualHarvestActorContext,
    ) -> TrialActualHarvestUploadResponse:
        self.upload_calls.append("upload_import")
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
            report_id="a" * 64,
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
        "farm_business_key": "farm-a",
        "subfarm_business_key_or_null": "subfarm-a",
        "variety_business_key": "variety-a",
        "season_business_key": "season-2026",
        "destination_factory_business_key": "factory-a",
        "forecast_cutoff_at": NOW.isoformat(),
        "forecast_input_authority_hash": "a" * 64,
        "plan_row_hash": "b" * 64 if model == "model-v1" else "c" * 64,
        "planting_area_mu": "10.000000",
        "flowering_date_or_null": None,
        "maturity_stage_or_null": None,
        "already_picked_quantity_kg_or_null": None,
    }


def _quality_request(*, key: str = "quality-key") -> dict[str, Any]:
    return {
        "forecast_run_id": "a" * 64,
        "actual_harvest_import_id": "import-public-1",
        "forecast_cutoff_at": NOW.isoformat(),
        "label_observation_cutoff_at": NOW.isoformat(),
        "requested_horizons_days": [7, 14, 21],
        "request_idempotency_key": key,
    }


@pytest.mark.asyncio
async def test_forecast_create_api_acceptance(client: AsyncClient) -> None:
    response = await client.post("/api/v1/trial/forecasts", json=_forecast_request())
    assert response.status_code == 200
    assert response.json()["run_id"] == "forecast-public-1"


@pytest.mark.asyncio
async def test_forecast_input_authority_api_acceptance(client: AsyncClient) -> None:
    response = await client.get("/api/v1/trial/forecast-input-authority")
    assert response.status_code == 200
    assert response.json()["forecast_input_authority_hash"] == "a" * 64
    assert "farm_id" not in str(response.json())


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
    assert response.headers["content-disposition"] == (
        'attachment; filename="forecast-public-1.csv"'
    )
    assert response.text.splitlines()[0] == (
        "target_date,p50_value_kg,p80_value_kg,p90_value_kg,row_status"
    )
    assert response.text.splitlines()[1:] == [
        "2026-01-01,10.000000,11.000000,12.000000,COMPLETED",
        "2026-01-02,12.000000,13.000000,14.000000,COMPLETED",
    ]


@pytest.mark.asyncio
async def test_actual_import_create_api_acceptance(client: AsyncClient) -> None:
    body = {
        "source_system": "synthetic-farm-system",
        "source_dataset": "synthetic-dataset",
        "source_version": "v1",
        "external_batch_id": "batch-1",
        "request_idempotency_key": "import-key-1",
    }
    response = await client.post("/api/v1/trial/actual-harvest/imports", json=body)
    assert response.status_code == 200
    assert response.json()["status"] == "UPLOADING"


@pytest.mark.asyncio
async def test_actual_import_create_scope_mismatch_is_forbidden_before_lifecycle(
    client: AsyncClient,
    trial_app,
) -> None:
    trial_app.dependency_overrides[get_trial_service] = lambda: DefaultTrialApplicationService()
    trial_app.dependency_overrides[get_actual_harvest_actor] = lambda: _actor(
        channels=frozenset({ActualHarvestImportChannel.CSV})
    )
    body = {
        "source_system": "synthetic-farm-system",
        "source_dataset": "synthetic-dataset",
        "source_version": "v1",
        "external_batch_id": "batch-scope-check",
        "request_idempotency_key": "import-scope-check",
    }
    response = await client.post("/api/v1/trial/actual-harvest/imports", json=body)
    assert response.status_code == 403
    assert response.json()["code"] == "TRIAL_AUTHORIZATION_FORBIDDEN"


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
async def test_actual_import_upload_authorizes_before_upload_service(
    client: AsyncClient,
    synthetic_service: SyntheticTrialService,
) -> None:
    response = await client.post(
        "/api/v1/trial/actual-harvest/imports/import-public-1/upload",
        content=b"raw-csv-bytes",
        headers={"content-type": "text/csv", "x-file-name": "harvest.csv"},
    )
    assert response.status_code == 200
    assert synthetic_service.upload_calls == ["authorize_import_upload", "upload_import"]


@pytest.mark.asyncio
async def test_actual_import_upload_preflight_conceals_before_metadata_or_body(
    client: AsyncClient,
    trial_app,
) -> None:
    class RejectingUploadPreflightService:
        upload_import_called = False

        async def authorize_import_upload(
            self,
            session: AsyncSession,
            import_id: str,
            actor: ActualHarvestActorContext,
        ) -> None:
            del session, import_id, actor
            raise TrialApiError(
                TrialApiErrorCode.RESOURCE_NOT_FOUND,
                status_code=404,
                message="Resource was not found.",
            )

        async def upload_import(
            self,
            session: AsyncSession,
            import_id: str,
            content: bytes,
            metadata: TrialActualHarvestUploadMetadata,
            actor: ActualHarvestActorContext,
        ) -> TrialActualHarvestUploadResponse:
            del session, import_id, content, metadata, actor
            self.upload_import_called = True
            raise AssertionError("upload service must not run after failed preflight")

    service = RejectingUploadPreflightService()
    trial_app.dependency_overrides[get_trial_service] = lambda: service
    response = await client.post(
        "/api/v1/trial/actual-harvest/imports/import-public-1/upload",
        content=b"non-empty-body",
        headers={"content-type": "invalid/content-type", "x-file-name": "../unsafe.csv"},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"
    assert service.upload_import_called is False


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
async def test_quality_permissions_use_shared_actor_parser_and_unknown_fails_closed() -> None:
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("TRIAL_ACTOR_IDENTITY", "quality-actor")
        monkeypatch.setenv("TRIAL_ACTOR_ALLOWED_SOURCE_SYSTEMS", "synthetic-farm-system")
        monkeypatch.setenv("TRIAL_ACTOR_ALLOWED_CHANNELS", "api")
        monkeypatch.setenv(
            "TRIAL_ACTOR_PERMISSIONS",
            "may_create_quality,may_read_quality,may_read_quality_comparison,may_export_quality",
        )
        actor = await get_actual_harvest_actor()
        assert actor.may_create_quality is True
        assert actor.may_read_quality is True
        assert actor.may_read_quality_comparison is True
        assert actor.may_export_quality is True

        monkeypatch.setenv(
            "TRIAL_ACTOR_PERMISSIONS",
            "may_create_quality,unknown_quality_permission",
        )
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
    assert response.json()["coverage_counts"] == {
        "total": 2,
        "comparable": 2,
        "covered": 0,
        "excluded": 0,
        "not_computable": 0,
    }


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


@pytest.mark.asyncio
async def test_default_quality_service_requires_api_channel_and_quality_permission() -> None:
    service = DefaultTrialApplicationService()
    request = TrialQualityReportCreateRequest(**_quality_request())

    async def assert_concealed(actor: ActualHarvestActorContext) -> None:
        for operation in (
            lambda: service.create_quality_report(None, request, actor),
            lambda: service.get_quality_report(None, "a" * 64, actor),
            lambda: service.get_quality_comparison(None, "a" * 64, actor),
            lambda: service.export_quality_report(None, "a" * 64, actor),
        ):
            with pytest.raises(TrialApiError) as caught:
                await operation()
            assert caught.value.code is TrialApiErrorCode.RESOURCE_NOT_FOUND
            assert caught.value.status_code == 404

    await assert_concealed(_actor(channels=frozenset({ActualHarvestImportChannel.CSV})))
    await assert_concealed(_actor(create=False, preview=False))


def test_openapi_schema_acceptance(trial_app) -> None:
    paths = trial_app.openapi()["paths"]
    expected = {
        "/api/v1/trial/forecasts",
        "/api/v1/trial/forecast-input-authority",
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
    assert body["single_day_peak"] == {
        "date": "2026-01-02",
        "quantity_kg": "14.000000",
        "tie_break": "EARLIEST_DATE",
    }
    assert body["season_cumulative_quantity"] == "22.000000"
