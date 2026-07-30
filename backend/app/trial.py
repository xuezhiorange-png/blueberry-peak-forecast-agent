"""Thin application boundary for the V0.2-S4 trial API.

The module deliberately owns transport mapping only. Forecast, label, quality,
and persistence semantics remain owned by the existing S1-S3 services.
"""

from __future__ import annotations

import csv
import hashlib
import io
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Protocol

from fastapi import Depends
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.actual_harvest_import.api_auth import (
    ActualHarvestActorContext,
    get_actual_harvest_actor,
    require_actor_scope,
)
from backend.app.actual_harvest_import.api_errors import (
    ActualHarvestApiError,
    ActualHarvestApiErrorCode,
)
from backend.app.actual_harvest_import.api_schemas import (
    ActualHarvestApiAppendRecordsRequest,
    ActualHarvestApiBatchSummary,
    ActualHarvestApiCommitRequest,
    ActualHarvestApiCreateImportRequest,
    ActualHarvestApiRecordInput,
    ActualHarvestApiRecordOutput,
)
from backend.app.actual_harvest_import.commit_service import commit_batch
from backend.app.actual_harvest_import.enums import (
    ActualHarvestImportBatchStatus,
    ActualHarvestImportChannel,
)
from backend.app.actual_harvest_import.lifecycle import (
    append_import_records,
    create_import,
    get_import,
    seal_import,
    validate_import,
    validation_errors,
    validation_summary,
)
from backend.app.actual_harvest_import.models import ActualHarvestImportBatchModel
from backend.app.actual_harvest_import.spreadsheet_parser import (
    SpreadsheetParserError,
    parse_csv,
    parse_xlsx,
)
from backend.app.actual_harvest_import.spreadsheet_policy import DEFAULT_SPREADSHEET_POLICY
from backend.app.api.actual_harvest_imports import _run_mutation
from backend.app.forecast_quality.canonical import emit_s3_decimal


class TrialApiErrorCode(StrEnum):
    REQUEST_INVALID = "TRIAL_REQUEST_INVALID"
    AUTHORITY_NOT_FOUND = "AUTHORITY_NOT_FOUND"
    FORECAST_BLOCKED = "FORECAST_BLOCKED"
    IMPORT_PARSE_FAILED = "IMPORT_PARSE_FAILED"
    IMPORT_VALIDATION_FAILED = "IMPORT_VALIDATION_FAILED"
    IMPORT_NOT_READY_FOR_COMMIT = "IMPORT_NOT_READY_FOR_COMMIT"
    EXACT_REPLAY = "EXACT_REPLAY"
    CONFLICTING_REPLAY = "CONFLICTING_REPLAY"
    LABEL_SNAPSHOT_UNAVAILABLE = "LABEL_SNAPSHOT_UNAVAILABLE"
    QUALITY_NOT_COMPUTABLE = "QUALITY_NOT_COMPUTABLE"
    PARTIAL_RESULT_REJECTED = "PARTIAL_RESULT_REJECTED"
    CONCURRENCY_CONFLICT = "CONCURRENCY_CONFLICT"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    AUTHORIZATION_UNAVAILABLE = "TRIAL_AUTHORIZATION_UNAVAILABLE"
    TRIAL_SERVICE_UNAVAILABLE = "TRIAL_SERVICE_UNAVAILABLE"
    INTERNAL_ERROR = "TRIAL_INTERNAL_ERROR"
    UNSUPPORTED_CONTENT_TYPE = "TRIAL_UNSUPPORTED_CONTENT_TYPE"
    UNSAFE_FILE_NAME = "TRIAL_UNSAFE_FILE_NAME"
    FILE_HASH_MISMATCH = "TRIAL_FILE_HASH_MISMATCH"
    FILE_SIZE_EXCEEDED = "TRIAL_FILE_SIZE_EXCEEDED"
    CSV_PARSE_FAILED = "TRIAL_CSV_PARSE_FAILED"
    XLSX_PARSE_FAILED = "TRIAL_XLSX_PARSE_FAILED"
    VALIDATION_FAILED = "TRIAL_VALIDATION_FAILED"


class TrialApiError(RuntimeError):
    """Stable error boundary for the page API."""

    def __init__(
        self,
        code: TrialApiErrorCode,
        *,
        status_code: int,
        message: str,
        retryable: bool = False,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.message = message
        self.retryable = retryable
        self.details = dict(details or {})


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TrialForecastCreateRequest(_FrozenModel):
    season_business_key: StrictStr = Field(min_length=1, max_length=256)
    farm_business_keys: tuple[StrictStr, ...] = Field(min_length=1)
    subfarm_business_keys: tuple[StrictStr, ...] = Field(min_length=1)
    variety_business_keys: tuple[StrictStr, ...] = Field(min_length=1)
    requested_horizons_days: tuple[StrictInt, ...] = Field(min_length=1)
    forecast_quantiles: tuple[StrictStr, ...] = Field(min_length=1)
    forecast_cutoff_at: datetime
    label_observation_cutoff_at_or_null: datetime | None = None
    request_idempotency_key: StrictStr = Field(min_length=1, max_length=256)
    model_identity: StrictStr = Field(min_length=1, max_length=256)
    parameter_version: StrictStr = Field(min_length=1, max_length=128)
    policy_versions: dict[StrictStr, StrictStr]

    @field_validator("forecast_cutoff_at", "label_observation_cutoff_at_or_null")
    @classmethod
    def _timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("timestamps must be timezone-aware")
        return value

    @field_validator("requested_horizons_days")
    @classmethod
    def _valid_horizons(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if any(item <= 0 for item in value):
            raise ValueError("forecast horizons must be positive")
        if len(set(value)) != len(value):
            raise ValueError("forecast horizons must be unique")
        return value

    @field_validator("forecast_quantiles")
    @classmethod
    def _valid_quantiles(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(item not in {"P50", "P80", "P90"} for item in value):
            raise ValueError("forecast quantiles must be P50, P80, or P90")
        return value


class TrialForecastDailyRow(_FrozenModel):
    target_date: date
    p50_value_kg: Decimal | None
    p80_value_kg: Decimal | None
    p90_value_kg: Decimal | None
    row_status: StrictStr
    reason_codes: tuple[StrictStr, ...] = ()

    @field_validator("p50_value_kg", "p80_value_kg", "p90_value_kg", mode="before")
    @classmethod
    def _reject_native_float(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("native float is not a canonical quantity")
        return value


class TrialForecastSummaryResponse(_FrozenModel):
    run_id: StrictStr
    status: StrictStr
    daily_p50_series: tuple[TrialForecastDailyRow, ...]
    daily_p80_series: tuple[TrialForecastDailyRow, ...]
    daily_p90_series: tuple[TrialForecastDailyRow, ...]
    single_day_peak: dict[str, object] | None = None
    sustained_seven_day_peak: dict[str, object] | None = None
    season_cumulative_quantity: Decimal | None = None
    mature_inventory_summary: dict[str, object] | None = None
    backlog_summary: dict[str, object] | None = None
    data_gap_summaries: tuple[StrictStr, ...] = ()
    blocker_summaries: tuple[StrictStr, ...] = ()
    model_version: StrictStr
    parameter_version: StrictStr
    policy_versions: dict[StrictStr, StrictStr]
    canonical_public_hash: StrictStr


class TrialForecastDailyCurveResponse(_FrozenModel):
    run_id: StrictStr
    forecast_cutoff_at: datetime
    rows: tuple[TrialForecastDailyRow, ...]

    @field_validator("forecast_cutoff_at")
    @classmethod
    def _timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        return value


class TrialActualHarvestImportCreateResponse(_FrozenModel):
    import_id: StrictStr
    status: StrictStr
    source_system: StrictStr
    source_dataset: StrictStr
    source_version: StrictStr
    expected_record_count_or_null: int | None
    policy_version: StrictStr
    canonical_public_hash: StrictStr | None


class TrialActualHarvestImportStatusResponse(_FrozenModel):
    import_id: StrictStr
    status: StrictStr
    record_count: StrictInt
    valid_record_count: StrictInt
    invalid_record_count: StrictInt
    committed_record_count: StrictInt
    validation_status: StrictStr
    validation_reason_codes: tuple[StrictStr, ...]
    validation_evidence_hash: StrictStr | None


class TrialActualHarvestUploadResponse(_FrozenModel):
    import_id: StrictStr
    server_status: StrictStr
    source_file_name: StrictStr
    source_mime_type: StrictStr
    source_file_sha256: StrictStr
    uploaded_record_count: StrictInt
    valid_record_count: StrictInt
    invalid_record_count: StrictInt
    validation_status: StrictStr
    validation_run_instance_identity_hash_or_null: StrictStr | None
    validation_result_hash_or_null: StrictStr | None
    reason_codes: tuple[StrictStr, ...]


class TrialActualHarvestInvalidRow(_FrozenModel):
    severity: StrictStr
    error_code: StrictStr
    record_index: int | None
    external_logical_record_id: StrictStr | None
    external_revision_id: StrictStr | None
    field_path: StrictStr | None
    message_template_id: StrictStr
    details: dict[str, object] = Field(default_factory=dict)


class TrialActualHarvestInvalidRowsResponse(_FrozenModel):
    import_id: StrictStr
    validation_status: StrictStr
    validation_run_instance_identity_hash_or_null: StrictStr | None
    rows: tuple[TrialActualHarvestInvalidRow, ...]
    next_page_token: StrictStr | None


class TrialActualHarvestCommitResponse(_FrozenModel):
    import_id: StrictStr
    status: StrictStr
    committed_record_count: StrictInt
    commit_policy_version: StrictStr
    commit_manifest_hash: StrictStr
    reused_existing_commit: bool


class TrialQualityReportCreateRequest(_FrozenModel):
    forecast_run_id: StrictStr = Field(min_length=1, max_length=256)
    actual_label_snapshot_identity: StrictStr = Field(min_length=1, max_length=256)
    forecast_cutoff_at: datetime
    label_observation_cutoff_at: datetime
    forecast_horizon_days: StrictInt = Field(gt=0)
    quality_policy_version: StrictStr = Field(min_length=1, max_length=128)
    baseline_policy_version: StrictStr = Field(min_length=1, max_length=128)
    request_idempotency_key: StrictStr = Field(min_length=1, max_length=256)

    @field_validator("forecast_cutoff_at", "label_observation_cutoff_at")
    @classmethod
    def _timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        return value


class TrialQualityReportResponse(_FrozenModel):
    report_id: StrictStr
    forecast_identity: dict[str, object]
    actual_label_snapshot_identity: StrictStr
    forecast_cutoff_at: datetime
    label_observation_cutoff_at: datetime
    forecast_horizon_days: StrictInt
    daily_metrics: tuple[dict[str, object], ...]
    cumulative_error_status: StrictStr
    single_day_peak_error_status: StrictStr
    sustained_seven_day_peak_error_status: StrictStr
    p80_p90_metric_status: StrictStr
    interval_metric_status: StrictStr
    breakdowns: tuple[dict[str, object], ...]
    naive_baseline_result: dict[str, object] | None
    computability_status: StrictStr
    reason_codes: tuple[StrictStr, ...]
    coverage_counts: dict[str, StrictInt]
    excluded_row_counts: dict[str, StrictInt]


class TrialQualityComparisonResponse(_FrozenModel):
    report_id: StrictStr
    comparison_availability: StrictStr
    comparison_status: StrictStr
    comparison_policy_version: StrictStr
    model_baseline_deltas: tuple[dict[str, object], ...]
    reason_codes: tuple[StrictStr, ...]
    comparison_public_hash: StrictStr


class TrialErrorResponse(_FrozenModel):
    request_id: StrictStr | None
    status: str = "ERROR"
    code: StrictStr
    message_template_id: StrictStr
    retryable: bool
    details: dict[str, object] = Field(default_factory=dict)


class TrialCsvExportResponse(_FrozenModel):
    resource_id: StrictStr
    filename: StrictStr
    content_type: StrictStr
    content_sha256: StrictStr
    byte_size: StrictInt


class TrialForecastCsvExportResponse(TrialCsvExportResponse):
    pass


class TrialQualityCsvExportResponse(TrialForecastCsvExportResponse):
    pass


@dataclass(frozen=True)
class TrialActualHarvestUploadMetadata:
    file_name: str
    mime_type: str
    channel: ActualHarvestImportChannel
    sha256: str | None = None


@dataclass(frozen=True)
class TrialCsvDocument:
    filename: str
    content: bytes


class TrialApplicationService(Protocol):
    async def create_forecast(
        self,
        session: AsyncSession,
        request: TrialForecastCreateRequest,
        actor: ActualHarvestActorContext,
    ) -> TrialForecastSummaryResponse: ...

    async def get_forecast(
        self,
        session: AsyncSession,
        run_id: str,
        actor: ActualHarvestActorContext,
    ) -> TrialForecastSummaryResponse: ...

    async def get_daily_curve(
        self,
        session: AsyncSession,
        run_id: str,
        actor: ActualHarvestActorContext,
    ) -> TrialForecastDailyCurveResponse: ...

    async def export_forecast(
        self,
        session: AsyncSession,
        run_id: str,
        actor: ActualHarvestActorContext,
    ) -> TrialCsvDocument: ...

    async def create_import(
        self,
        session: AsyncSession,
        request: ActualHarvestApiCreateImportRequest,
        actor: ActualHarvestActorContext,
    ) -> TrialActualHarvestImportCreateResponse: ...

    async def get_import(
        self,
        session: AsyncSession,
        import_id: str,
        actor: ActualHarvestActorContext,
    ) -> TrialActualHarvestImportStatusResponse: ...

    async def commit_import(
        self,
        session: AsyncSession,
        import_id: str,
        request: ActualHarvestApiCommitRequest,
        actor: ActualHarvestActorContext,
    ) -> TrialActualHarvestCommitResponse: ...

    async def upload_import(
        self,
        session: AsyncSession,
        import_id: str,
        content: bytes,
        metadata: TrialActualHarvestUploadMetadata,
        actor: ActualHarvestActorContext,
    ) -> TrialActualHarvestUploadResponse: ...

    async def get_import_errors(
        self,
        session: AsyncSession,
        import_id: str,
        *,
        page_size: int,
        page_token: str | None,
        actor: ActualHarvestActorContext,
    ) -> TrialActualHarvestInvalidRowsResponse: ...

    async def create_quality_report(
        self,
        session: AsyncSession,
        request: TrialQualityReportCreateRequest,
        actor: ActualHarvestActorContext,
    ) -> TrialQualityReportResponse: ...

    async def get_quality_report(
        self,
        session: AsyncSession,
        report_id: str,
        actor: ActualHarvestActorContext,
    ) -> TrialQualityReportResponse: ...

    async def get_quality_comparison(
        self,
        session: AsyncSession,
        report_id: str,
        actor: ActualHarvestActorContext,
    ) -> TrialQualityComparisonResponse: ...

    async def export_quality_report(
        self,
        session: AsyncSession,
        report_id: str,
        actor: ActualHarvestActorContext,
    ) -> TrialCsvDocument: ...


class DefaultTrialApplicationService:
    """Default boundary that reuses existing lifecycle services.

    Forecast and quality providers are intentionally fail-closed until their
    existing authority repositories are wired by the application composition
    layer. Tests inject a deterministic synthetic provider through the same
    dependency seam; no domain algorithm is duplicated here.
    """

    async def create_import(
        self,
        session: AsyncSession,
        request: ActualHarvestApiCreateImportRequest,
        actor: ActualHarvestActorContext,
    ) -> TrialActualHarvestImportCreateResponse:
        _require_permission(actor, "may_create")
        summary, _ = await _run_mutation(session, lambda: create_import(session, request))
        return TrialActualHarvestImportCreateResponse(
            import_id=summary.import_id,
            status=_public_import_status(summary.status),
            source_system=summary.source_system,
            source_dataset=summary.source_dataset,
            source_version=summary.source_version,
            expected_record_count_or_null=summary.expected_record_count_or_null,
            policy_version="actual-harvest-api-policy-v1",
            canonical_public_hash=summary.canonical_batch_hash_or_null,
        )

    async def get_import(
        self,
        session: AsyncSession,
        import_id: str,
        actor: ActualHarvestActorContext,
    ) -> TrialActualHarvestImportStatusResponse:
        _require_permission(actor, "may_preview")
        summary = await get_import(session, import_id)
        validation = await validation_summary(session, import_id)
        return TrialActualHarvestImportStatusResponse(
            import_id=summary.import_id,
            status=_public_import_status(summary.status),
            record_count=summary.record_count,
            valid_record_count=summary.valid_record_count,
            invalid_record_count=summary.invalid_record_count,
            committed_record_count=summary.committed_record_count,
            validation_status=validation.validation_status,
            validation_reason_codes=(
                ("VALIDATION_FAILED",)
                if validation.validation_status == "VALIDATION_FAILED"
                else ()
            ),
            validation_evidence_hash=validation.validation_result_hash
            or summary.seal_manifest_hash_or_null,
        )

    async def commit_import(
        self,
        session: AsyncSession,
        import_id: str,
        request: ActualHarvestApiCommitRequest,
        actor: ActualHarvestActorContext,
    ) -> TrialActualHarvestCommitResponse:
        _require_permission(actor, "may_commit")
        result = await _run_mutation(
            session,
            lambda: commit_batch(
                session,
                import_id=import_id,
                validation_run_instance_identity_hash=request.validation_run_instance_identity_hash,
                actor=actor,
            ),
        )
        return TrialActualHarvestCommitResponse(
            import_id=import_id,
            status="COMMITTED",
            committed_record_count=result.committed_record_count,
            commit_policy_version=result.commit_policy_version,
            commit_manifest_hash=result.commit_manifest_hash,
            reused_existing_commit=result.reused_existing_commit,
        )

    async def upload_import(
        self,
        session: AsyncSession,
        import_id: str,
        content: bytes,
        metadata: TrialActualHarvestUploadMetadata,
        actor: ActualHarvestActorContext,
    ) -> TrialActualHarvestUploadResponse:
        _require_permission(actor, "may_append")
        batch = await get_import(session, import_id)
        require_actor_scope(
            actor,
            source_system=batch.source_system,
            channel=metadata.channel,
            permission="may_append",
            submitted_by_identity=batch.submitted_by_identity,
            hide_identity_mismatch=True,
        )
        if not content:
            raise TrialApiError(
                TrialApiErrorCode.REQUEST_INVALID,
                status_code=422,
                message="Uploaded file is empty.",
            )
        if len(content) > DEFAULT_SPREADSHEET_POLICY.max_file_size_bytes:
            raise TrialApiError(
                TrialApiErrorCode.FILE_SIZE_EXCEEDED,
                status_code=413,
                message="Uploaded file exceeds the supported size.",
            )
        actual_hash = hashlib.sha256(content).hexdigest()
        if metadata.sha256 is not None and metadata.sha256 != actual_hash:
            raise TrialApiError(
                TrialApiErrorCode.FILE_HASH_MISMATCH,
                status_code=422,
                message="Uploaded file hash does not match.",
            )
        try:
            parsed = parse_csv(content) if metadata.channel.value == "csv" else parse_xlsx(content)
        except SpreadsheetParserError as error:
            code = (
                TrialApiErrorCode.CSV_PARSE_FAILED
                if metadata.channel.value == "csv"
                else TrialApiErrorCode.XLSX_PARSE_FAILED
            )
            raise TrialApiError(code, status_code=422, message="File parsing failed.") from error
        records = tuple(
            ActualHarvestApiRecordInput.model_validate(
                record.model_dump(exclude={"source_row_number", "source_sheet_name"})
            )
            for record in parsed.records
        )
        append_request = ActualHarvestApiAppendRecordsRequest(records=records)

        async def append_and_record_metadata() -> tuple[
            ActualHarvestApiBatchSummary,
            tuple[ActualHarvestApiRecordOutput, ...],
            bool,
        ]:
            await session.run_sync(
                lambda sync_session: _store_upload_metadata(
                    sync_session,
                    import_id=import_id,
                    file_name=metadata.file_name,
                    file_hash=actual_hash,
                )
            )
            return await append_import_records(session, import_id, append_request)

        await _run_mutation(session, append_and_record_metadata)
        await _run_mutation(
            session,
            lambda: seal_import(session, import_id, actor_identity=actor.identity),
        )
        summary = await validate_import(session, import_id)
        return TrialActualHarvestUploadResponse(
            import_id=import_id,
            server_status=summary.validation_status,
            source_file_name=metadata.file_name,
            source_mime_type=metadata.mime_type,
            source_file_sha256=actual_hash,
            uploaded_record_count=len(records),
            valid_record_count=summary.valid_count,
            invalid_record_count=summary.invalid_count,
            validation_status=summary.validation_status,
            validation_run_instance_identity_hash_or_null=summary.validation_run_identity,
            validation_result_hash_or_null=summary.validation_result_hash,
            reason_codes=tuple(
                ("VALIDATION_FAILED",) if summary.validation_status == "VALIDATION_FAILED" else ()
            ),
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
        _require_permission(actor, "may_validate")
        summary, rows, next_token = await validation_errors(
            session, import_id, page_size=page_size, page_token=page_token
        )
        return TrialActualHarvestInvalidRowsResponse(
            import_id=import_id,
            validation_status=summary.validation_status,
            validation_run_instance_identity_hash_or_null=summary.validation_run_identity,
            rows=tuple(TrialActualHarvestInvalidRow.model_validate(row) for row in rows),
            next_page_token=next_token,
        )

    async def create_forecast(
        self,
        session: AsyncSession,
        request: TrialForecastCreateRequest,
        actor: ActualHarvestActorContext,
    ) -> TrialForecastSummaryResponse:
        del session, request, actor
        raise _service_unavailable("forecast authority adapter")

    async def get_forecast(
        self, session: AsyncSession, run_id: str, actor: ActualHarvestActorContext
    ) -> TrialForecastSummaryResponse:
        del session, run_id, actor
        raise _service_unavailable("forecast read adapter")

    async def get_daily_curve(
        self, session: AsyncSession, run_id: str, actor: ActualHarvestActorContext
    ) -> TrialForecastDailyCurveResponse:
        del session, run_id, actor
        raise _service_unavailable("daily curve read adapter")

    async def export_forecast(
        self, session: AsyncSession, run_id: str, actor: ActualHarvestActorContext
    ) -> TrialCsvDocument:
        del session, run_id, actor
        raise _service_unavailable("forecast export adapter")

    async def create_quality_report(
        self,
        session: AsyncSession,
        request: TrialQualityReportCreateRequest,
        actor: ActualHarvestActorContext,
    ) -> TrialQualityReportResponse:
        del session, request, actor
        raise _service_unavailable("quality persistence adapter")

    async def get_quality_report(
        self, session: AsyncSession, report_id: str, actor: ActualHarvestActorContext
    ) -> TrialQualityReportResponse:
        del session, report_id, actor
        raise _service_unavailable("quality read adapter")

    async def get_quality_comparison(
        self, session: AsyncSession, report_id: str, actor: ActualHarvestActorContext
    ) -> TrialQualityComparisonResponse:
        del session, report_id, actor
        raise _service_unavailable("quality comparison adapter")

    async def export_quality_report(
        self, session: AsyncSession, report_id: str, actor: ActualHarvestActorContext
    ) -> TrialCsvDocument:
        del session, report_id, actor
        raise _service_unavailable("quality export adapter")


def get_trial_service() -> DefaultTrialApplicationService:
    return DefaultTrialApplicationService()


TrialServiceDep = Annotated[TrialApplicationService, Depends(get_trial_service)]
TrialActorDep = Annotated[ActualHarvestActorContext, Depends(get_actual_harvest_actor)]


def _require_permission(actor: ActualHarvestActorContext, permission: str) -> None:
    if not actor.identity or not getattr(actor, permission, False):
        raise TrialApiError(
            TrialApiErrorCode.RESOURCE_NOT_FOUND,
            status_code=404,
            message="Resource was not found.",
        )


def _store_upload_metadata(
    session: Any,
    *,
    import_id: str,
    file_name: str,
    file_hash: str,
) -> None:
    batch = session.scalar(
        select(ActualHarvestImportBatchModel).where(
            ActualHarvestImportBatchModel.import_id == import_id
        )
    )
    if batch is None:
        raise ActualHarvestApiError(
            ActualHarvestApiErrorCode.IMPORT_BATCH_NOT_FOUND,
            "actual-harvest import batch was not found",
            status_code=404,
        )
    batch.source_file_name_or_null = file_name
    batch.source_file_hash_or_null = file_hash


def _service_unavailable(component: str) -> TrialApiError:
    del component
    return TrialApiError(
        TrialApiErrorCode.TRIAL_SERVICE_UNAVAILABLE,
        status_code=503,
        message="The trial service is temporarily unavailable.",
        retryable=True,
    )


def _public_import_status(status: str) -> str:
    if status in {item.value for item in ActualHarvestImportBatchStatus}:
        return status
    return status


def map_actual_harvest_error(error: ActualHarvestApiError) -> TrialApiError:
    code_map: dict[ActualHarvestApiErrorCode, tuple[TrialApiErrorCode, int, bool, str]] = {
        ActualHarvestApiErrorCode.ACTUAL_HARVEST_AUTHORIZATION_UNAVAILABLE: (
            TrialApiErrorCode.AUTHORIZATION_UNAVAILABLE,
            503,
            True,
            "Trial authorization is unavailable.",
        ),
        ActualHarvestApiErrorCode.ACTUAL_HARVEST_SCOPE_FORBIDDEN: (
            TrialApiErrorCode.RESOURCE_NOT_FOUND,
            404,
            False,
            "Resource was not found.",
        ),
        ActualHarvestApiErrorCode.ACTUAL_HARVEST_ACTOR_MISMATCH: (
            TrialApiErrorCode.RESOURCE_NOT_FOUND,
            404,
            False,
            "Resource was not found.",
        ),
        ActualHarvestApiErrorCode.IMPORT_BATCH_NOT_FOUND: (
            TrialApiErrorCode.RESOURCE_NOT_FOUND,
            404,
            False,
            "Resource was not found.",
        ),
        ActualHarvestApiErrorCode.IMPORT_BATCH_NOT_VALIDATED: (
            TrialApiErrorCode.IMPORT_NOT_READY_FOR_COMMIT,
            409,
            False,
            "Import is not ready for commit.",
        ),
        ActualHarvestApiErrorCode.COMMIT_EVIDENCE_CONFLICT: (
            TrialApiErrorCode.CONFLICTING_REPLAY,
            409,
            False,
            "Request conflicts with existing evidence.",
        ),
        ActualHarvestApiErrorCode.COMMIT_EVIDENCE_DRIFT: (
            TrialApiErrorCode.CONFLICTING_REPLAY,
            409,
            False,
            "Request conflicts with existing evidence.",
        ),
        ActualHarvestApiErrorCode.COMMIT_PERSISTENCE_FAILED: (
            TrialApiErrorCode.CONCURRENCY_CONFLICT,
            409,
            True,
            "Concurrent persistence conflict.",
        ),
        ActualHarvestApiErrorCode.API_REQUEST_INVALID: (
            TrialApiErrorCode.REQUEST_INVALID,
            422,
            False,
            "Request is invalid.",
        ),
        ActualHarvestApiErrorCode.API_CONTENT_TYPE_UNSUPPORTED: (
            TrialApiErrorCode.UNSUPPORTED_CONTENT_TYPE,
            415,
            False,
            "Request content type is unsupported.",
        ),
        ActualHarvestApiErrorCode.API_REQUEST_BODY_TOO_LARGE: (
            TrialApiErrorCode.FILE_SIZE_EXCEEDED,
            413,
            False,
            "Uploaded file exceeds the supported size.",
        ),
        ActualHarvestApiErrorCode.IMPORT_BATCH_NOT_UPLOADING: (
            TrialApiErrorCode.CONCURRENCY_CONFLICT,
            409,
            False,
            "Import is not accepting uploads.",
        ),
    }
    code, status, retryable, message = code_map.get(
        error.code,
        (TrialApiErrorCode.INTERNAL_ERROR, 500, False, "The trial request failed."),
    )
    return TrialApiError(
        code,
        status_code=status,
        message=message,
        retryable=retryable,
    )


def map_unhandled_error(error: Exception) -> TrialApiError:
    del error
    return TrialApiError(
        TrialApiErrorCode.INTERNAL_ERROR,
        status_code=500,
        message="The trial request failed.",
    )


def serialize_csv(
    headers: Sequence[str],
    rows: Sequence[Sequence[object]],
) -> bytes:
    """Serialize a stable UTF-8 CSV without formula injection."""
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow(tuple(_csv_value(value) for value in row))
    return output.getvalue().encode("utf-8")


def _csv_value(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return emit_s3_decimal(value)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("CSV timestamps must be timezone-aware")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def csv_response_metadata(resource_id: str, document: TrialCsvDocument) -> TrialCsvExportResponse:
    import hashlib

    return TrialCsvExportResponse(
        resource_id=resource_id,
        filename=document.filename,
        content_type="text/csv; charset=utf-8",
        content_sha256=hashlib.sha256(document.content).hexdigest(),
        byte_size=len(document.content),
    )


__all__ = [
    "DefaultTrialApplicationService",
    "TrialActualHarvestCommitResponse",
    "TrialActualHarvestImportCreateResponse",
    "TrialActualHarvestImportStatusResponse",
    "TrialActualHarvestInvalidRow",
    "TrialActualHarvestInvalidRowsResponse",
    "TrialActualHarvestUploadMetadata",
    "TrialActualHarvestUploadResponse",
    "TrialApiError",
    "TrialApiErrorCode",
    "TrialApplicationService",
    "TrialCsvDocument",
    "TrialErrorResponse",
    "TrialForecastCreateRequest",
    "TrialForecastCsvExportResponse",
    "TrialForecastDailyCurveResponse",
    "TrialForecastDailyRow",
    "TrialForecastSummaryResponse",
    "TrialCsvExportResponse",
    "TrialQualityComparisonResponse",
    "TrialQualityCsvExportResponse",
    "TrialQualityReportCreateRequest",
    "TrialQualityReportResponse",
    "TrialServiceDep",
    "TrialActorDep",
    "csv_response_metadata",
    "get_trial_service",
    "map_actual_harvest_error",
    "map_unhandled_error",
    "serialize_csv",
]
