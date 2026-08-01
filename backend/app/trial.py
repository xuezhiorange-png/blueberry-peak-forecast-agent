"""Thin application boundary for the V0.2-S4 trial API.

The module deliberately owns transport mapping only. Forecast, label, quality,
and persistence semantics remain owned by the existing S1-S3 services.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Protocol

from fastapi import Depends
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator
from sqlalchemy import and_, or_, select
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
    ActualHarvestApiRecordInput,
    ActualHarvestApiRecordOutput,
)
from backend.app.actual_harvest_import.commit_service import commit_batch
from backend.app.actual_harvest_import.enums import (
    ActualHarvestImportBatchStatus,
    ActualHarvestImportChannel,
)
from backend.app.actual_harvest_import.lifecycle import (
    Clock,
    append_import_records,
    create_import,
    get_import,
    seal_import,
    utc_now,
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
from backend.app.core_forecast.application import execute_core_forecast_run
from backend.app.core_forecast.persistence import (
    CoreForecastPersistenceIntegrityError,
    CoreForecastRunRepository,
)
from backend.app.core_forecast.repository import (
    MarketableRetentionPolicyConflictError,
    MarketableRetentionPolicyMissingError,
    SqlAlchemyCoreForecastRepository,
)
from backend.app.core_forecast.schemas import (
    CompleteDailyMarketableCurveRequest,
    CoreForecastExecutionResult,
    CoreForecastScope,
    ExecuteCoreForecastRunRequest,
)
from backend.app.forecast_quality.canonical import emit_s3_decimal
from backend.app.models.core_forecast import CoreForecastCodeAuthorityModel
from backend.app.models.harvest_state import HarvestStateRun
from backend.app.models.master_data import Factory, Farm, Season, Subfarm, Variety
from backend.app.models.production_plan import FarmSeasonVarietyPlan
from backend.app.models.trial import (
    CoreForecastMarketablePolicyEntryModel,
    CoreForecastMarketablePolicyModel,
)
from backend.app.repositories.trial_forecast_evidence import (
    TrialForecastEvidence,
    TrialForecastEvidenceConflictError,
    TrialForecastEvidenceError,
    TrialForecastEvidenceInputError,
    TrialForecastEvidenceIntegrityError,
    TrialForecastEvidenceNotFoundError,
    authorize_and_load_forecast_evidence,
    compute_trial_business_scope_hash,
    create_forecast_evidence_and_binding_in_result_boundary,
)
from backend.app.rolling_backtest.canonical import canonical_json_dumps


class TrialApiErrorCode(StrEnum):
    REQUEST_INVALID = "TRIAL_REQUEST_INVALID"
    INPUT_NOT_SUPPORTED = "TRIAL_INPUT_NOT_SUPPORTED"
    AUTHORITY_NOT_FOUND = "AUTHORITY_NOT_FOUND"
    AUTHORITY_UNAVAILABLE = "TRIAL_AUTHORITY_UNAVAILABLE"
    EVIDENCE_CONFLICT = "EVIDENCE_CONFLICT"
    MARKETABLE_RETENTION_POLICY_MISSING = "MARKETABLE_RETENTION_POLICY_MISSING"
    MARKETABLE_RETENTION_POLICY_CONFLICT = "MARKETABLE_RETENTION_POLICY_CONFLICT"
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
    AUTHORIZATION_FORBIDDEN = "TRIAL_AUTHORIZATION_FORBIDDEN"
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


class TrialActualHarvestImportCreateRequest(_FrozenModel):
    """Browser-safe inputs for creating an actual-harvest import batch."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    source_system: StrictStr = Field(min_length=1, max_length=256)
    source_dataset: StrictStr = Field(min_length=1, max_length=256)
    source_version: StrictStr = Field(min_length=1, max_length=128)
    external_batch_id: StrictStr = Field(min_length=1, max_length=256)
    expected_record_count_or_null: StrictInt | None = Field(default=None, ge=0)
    request_idempotency_key: StrictStr = Field(min_length=1, max_length=256)


class TrialForecastCreateRequest(_FrozenModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    farm_business_key: StrictStr = Field(min_length=1, max_length=256)
    subfarm_business_key_or_null: StrictStr | None = Field(default=None, max_length=256)
    variety_business_key: StrictStr = Field(min_length=1, max_length=256)
    season_business_key: StrictStr = Field(min_length=1, max_length=256)
    destination_factory_business_key: StrictStr = Field(min_length=1, max_length=256)
    forecast_cutoff_at: datetime
    forecast_input_authority_hash: StrictStr = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    plan_row_hash: StrictStr = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    planting_area_mu: Decimal
    flowering_date_or_null: date | None = None
    maturity_stage_or_null: StrictStr | None = Field(default=None, max_length=128)
    already_picked_quantity_kg_or_null: Decimal | None = None

    @field_validator("forecast_cutoff_at")
    @classmethod
    def _timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("timestamps must be timezone-aware")
        return value

    @field_validator("planting_area_mu", "already_picked_quantity_kg_or_null", mode="before")
    @classmethod
    def _canonical_quantity(cls, value: object) -> Decimal | None:
        if value is None:
            return None
        if isinstance(value, (float, bool)):
            raise ValueError("quantities must be canonical Decimal values")
        try:
            parsed = value if isinstance(value, Decimal) else Decimal(str(value))
        except (ValueError, TypeError, ArithmeticError) as error:
            raise ValueError("quantity must be Decimal-compatible") from error
        if not parsed.is_finite() or parsed < 0:
            raise ValueError("quantity must be finite and non-negative")
        quantized = parsed.quantize(Decimal("0.000001"))
        if parsed != quantized:
            raise ValueError("quantity must have at most six decimal places")
        return quantized


class TrialForecastScope(_FrozenModel):
    farm_business_key: StrictStr
    subfarm_business_key_or_null: StrictStr | None
    season_business_key: StrictStr
    variety_business_key: StrictStr
    destination_factory_business_key: StrictStr


class TrialForecastInputAuthorityItem(_FrozenModel):
    farm_business_key: StrictStr
    subfarm_business_key_or_null: StrictStr | None
    season_business_key: StrictStr
    variety_business_key: StrictStr
    destination_factory_business_key: StrictStr
    plan_version: StrictStr
    plan_row_hash: StrictStr = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    planting_area_mu: Decimal

    @field_validator("planting_area_mu", mode="before")
    @classmethod
    def _reject_float(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("planting area must be canonical Decimal")
        return value


class TrialForecastInputAuthorityResponse(_FrozenModel):
    forecast_input_authority_hash: StrictStr = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    authority_available_at: datetime
    items: tuple[TrialForecastInputAuthorityItem, ...]
    authority_version: StrictStr = "v0.2-trial-forecast-input-authority-v1"

    @field_validator("authority_available_at")
    @classmethod
    def _timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
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
    forecast_scope: TrialForecastScope | None = None
    forecast_start_date: date | None = None
    forecast_end_date: date | None = None
    forecast_cutoff_at: datetime | None = None
    forecast_input_authority_hash: StrictStr | None = None
    plan_row_hash: StrictStr | None = None
    planting_area_mu: Decimal | None = None
    policy_identity: StrictStr | None = None
    policy_hash: StrictStr | None = None
    model_identity: StrictStr | None = None
    parameter_identity: StrictStr | None = None
    code_authority_identity: StrictStr | None = None
    task8_identity: StrictStr | None = None
    task9_identity: StrictStr | None = None
    result_hash: StrictStr | None = None
    curve_hash: StrictStr | None = None
    metrics_hash: StrictStr | None = None

    @field_validator("forecast_cutoff_at")
    @classmethod
    def _optional_timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("timestamps must be timezone-aware")
        return value


class TrialForecastDailyCurveResponse(_FrozenModel):
    run_id: StrictStr
    forecast_cutoff_at: datetime
    rows: tuple[TrialForecastDailyRow, ...]
    forecast_start_date: date | None = None
    forecast_end_date: date | None = None
    forecast_scope: TrialForecastScope | None = None

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
    async def get_forecast_input_authority(
        self,
        session: AsyncSession,
        actor: ActualHarvestActorContext,
    ) -> TrialForecastInputAuthorityResponse: ...

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
        request: TrialActualHarvestImportCreateRequest,
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

    async def authorize_import_upload(
        self,
        session: AsyncSession,
        import_id: str,
        actor: ActualHarvestActorContext,
    ) -> None: ...

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

    def __init__(self, *, clock: Clock = utc_now) -> None:
        self.clock = clock

    async def get_forecast_input_authority(
        self,
        session: AsyncSession,
        actor: ActualHarvestActorContext,
    ) -> TrialForecastInputAuthorityResponse:
        _require_forecast_permission(actor, "may_read_forecast_authority")
        snapshot = await _load_forecast_authority_snapshot(session)
        return snapshot.public_response

    async def create_import(
        self,
        session: AsyncSession,
        request: TrialActualHarvestImportCreateRequest,
        actor: ActualHarvestActorContext,
    ) -> TrialActualHarvestImportCreateResponse:
        if not isinstance(request, TrialActualHarvestImportCreateRequest):
            require_actor_scope(
                actor,
                source_system=request.source_system,
                channel=ActualHarvestImportChannel.API,
                permission="may_create",
                submitted_by_identity=getattr(request, "submitted_by_identity", None),
            )
            raise ActualHarvestApiError(
                ActualHarvestApiErrorCode.API_REQUEST_INVALID,
                "Trial create request contract is invalid",
                status_code=422,
            )
        require_actor_scope(
            actor,
            source_system=request.source_system,
            channel=ActualHarvestImportChannel.API,
            permission="may_create",
            submitted_by_identity=actor.identity,
        )
        from backend.app.actual_harvest_import.trial_create import (
            compose_trial_actual_harvest_create,
        )

        composed = await compose_trial_actual_harvest_create(
            session,
            request,
            actor,
            clock=self.clock,
        )
        summary, _ = await _run_mutation(
            session,
            lambda: create_import(
                session,
                composed.internal_request,
                clock=lambda: composed.created_at,
                replay_identity_hash=composed.create_identity_hash,
            ),
        )
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
        summary = await _load_scoped_import_batch(session, import_id, actor, "may_preview")
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
        await _load_scoped_import_batch(session, import_id, actor, "may_commit")
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

    async def authorize_import_upload(
        self,
        session: AsyncSession,
        import_id: str,
        actor: ActualHarvestActorContext,
    ) -> None:
        await _load_scoped_import_batch(session, import_id, actor, "may_append")

    async def upload_import(
        self,
        session: AsyncSession,
        import_id: str,
        content: bytes,
        metadata: TrialActualHarvestUploadMetadata,
        actor: ActualHarvestActorContext,
    ) -> TrialActualHarvestUploadResponse:
        batch = await _load_scoped_import_batch(session, import_id, actor, "may_append")
        _require_import_scope(
            batch,
            actor,
            "may_append",
            channel=metadata.channel,
            conceal_mismatch=True,
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
        await _load_scoped_import_batch(session, import_id, actor, "may_validate")
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
        _require_forecast_permission(actor, "may_create_forecast")
        if request.subfarm_business_key_or_null is None:
            raise TrialApiError(
                TrialApiErrorCode.INPUT_NOT_SUPPORTED,
                status_code=422,
                message="A concrete subfarm is required for Trial Forecast creation.",
            )
        if any(
            value is not None
            for value in (
                request.flowering_date_or_null,
                request.maturity_stage_or_null,
                request.already_picked_quantity_kg_or_null,
            )
        ):
            raise TrialApiError(
                TrialApiErrorCode.INPUT_NOT_SUPPORTED,
                status_code=422,
                message="The supplied optional forecast input is not supported.",
            )

        async def execute_and_persist() -> TrialForecastSummaryResponse:
            authority = await _resolve_create_authority(session, request)
            execution = await execute_core_forecast_run(
                session,
                request=authority.core_request,
            )
            if execution.status != "COMPLETED" or execution.run is None:
                raise _map_core_execution_error(execution)
            try:
                evidence = await create_forecast_evidence_and_binding_in_result_boundary(
                    session,
                    public_forecast_id=execution.run.request_hash,
                    owner_identity=actor.identity,
                    forecast_input_authority_hash=authority.evidence.forecast_input_authority_hash,
                    authority_available_at=authority.evidence.authority_available_at,
                    farm_business_key=authority.evidence.scope.farm_business_key,
                    subfarm_business_key_or_null=(
                        authority.evidence.scope.subfarm_business_key_or_null
                    ),
                    season_business_key=authority.evidence.scope.season_business_key,
                    variety_business_key=authority.evidence.scope.variety_business_key,
                    destination_factory_business_key=(
                        authority.evidence.scope.destination_factory_business_key
                    ),
                    plan_version=authority.evidence.plan_version,
                    plan_row_hash=authority.evidence.plan_row_hash,
                    planting_area_mu=authority.evidence.planting_area_mu,
                )
            except TrialForecastEvidenceConflictError as error:
                raise TrialApiError(
                    TrialApiErrorCode.CONFLICTING_REPLAY,
                    status_code=409,
                    message="Request conflicts with an existing replay.",
                ) from error
            except TrialForecastEvidenceIntegrityError as error:
                raise TrialApiError(
                    TrialApiErrorCode.EVIDENCE_CONFLICT,
                    status_code=409,
                    message="Forecast evidence integrity cannot be verified.",
                ) from error
            except TrialForecastEvidenceNotFoundError as error:
                raise TrialApiError(
                    TrialApiErrorCode.EVIDENCE_CONFLICT,
                    status_code=409,
                    message="Forecast evidence is unavailable.",
                ) from error
            except TrialForecastEvidenceInputError as error:
                raise TrialApiError(
                    TrialApiErrorCode.REQUEST_INVALID,
                    status_code=422,
                    message="Forecast evidence input is invalid.",
                ) from error
            except TrialForecastEvidenceError as error:
                raise TrialApiError(
                    TrialApiErrorCode.CONCURRENCY_CONFLICT,
                    status_code=409,
                    message="Concurrent persistence conflict.",
                    retryable=True,
                ) from error
            return _project_forecast_summary(
                execution,
                _authority_evidence_from_persisted_evidence(evidence, authority.evidence),
            )

        return await _run_mutation(session, execute_and_persist)

    async def get_forecast(
        self, session: AsyncSession, run_id: str, actor: ActualHarvestActorContext
    ) -> TrialForecastSummaryResponse:
        _, execution, evidence = await _load_verified_forecast(
            session,
            run_id,
            actor,
            permission="may_read_forecast",
        )
        return _project_forecast_summary(execution, evidence)

    async def get_daily_curve(
        self, session: AsyncSession, run_id: str, actor: ActualHarvestActorContext
    ) -> TrialForecastDailyCurveResponse:
        _, execution, evidence = await _load_verified_forecast(
            session,
            run_id,
            actor,
            permission="may_read_forecast",
        )
        return _project_daily_curve(execution, evidence)

    async def export_forecast(
        self, session: AsyncSession, run_id: str, actor: ActualHarvestActorContext
    ) -> TrialCsvDocument:
        _, execution, evidence = await _load_verified_forecast(
            session,
            run_id,
            actor,
            permission="may_export_forecast",
        )
        return _project_forecast_csv(execution, evidence)

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


@dataclass(frozen=True)
class _ForecastAuthorityEvidence:
    scope: TrialForecastScope
    farm_id: int
    subfarm_id: int
    variety_id: int
    season_id: int
    factory_id: int
    plan_row_hash: str
    plan_version: str
    planting_area_mu: Decimal
    forecast_input_authority_hash: str
    authority_available_at: datetime
    business_scope_hash: str


@dataclass(frozen=True)
class _ForecastAuthoritySnapshot:
    public_response: TrialForecastInputAuthorityResponse
    evidence_by_key: Mapping[tuple[str, str | None, str, str, str], _ForecastAuthorityEvidence]


@dataclass(frozen=True)
class _CreateForecastAuthority:
    core_request: ExecuteCoreForecastRunRequest
    evidence: _ForecastAuthorityEvidence
    business_scope_hash: str


def _require_forecast_permission(actor: ActualHarvestActorContext, permission: str) -> None:
    permissions = {
        "may_read_forecast_authority": actor.may_read_forecast_authority,
        "may_create_forecast": actor.may_create_forecast,
        "may_read_forecast": actor.may_read_forecast,
        "may_export_forecast": actor.may_export_forecast,
    }
    if (
        permission not in permissions
        or not actor.identity
        or not actor.allowed_source_systems
        or ActualHarvestImportChannel.API not in actor.allowed_channels
        or not permissions[permission]
    ):
        raise TrialApiError(
            TrialApiErrorCode.RESOURCE_NOT_FOUND,
            status_code=404,
            message="Resource was not found.",
        )


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _canonical_quantity(value: Decimal) -> Decimal:
    parsed = Decimal(value)
    if not parsed.is_finite() or parsed < 0:
        raise ValueError("quantity is invalid")
    quantized = parsed.quantize(Decimal("0.000001"))
    if parsed != quantized:
        raise ValueError("quantity is not canonical")
    return quantized


def _subfarm_public_key(farm: Farm, subfarm: Subfarm) -> str:
    del farm
    return subfarm.name


def _subfarm_key_matches(submitted: str | None, farm: Farm, subfarm: Subfarm | None) -> bool:
    if submitted is None or subfarm is None:
        return submitted is None and subfarm is None
    return submitted in {subfarm.name, f"{farm.name}/{subfarm.name}"}


async def _load_forecast_authority_snapshot(
    session: AsyncSession,
) -> _ForecastAuthoritySnapshot:
    result = await session.execute(
        select(
            FarmSeasonVarietyPlan,
            Farm,
            Season,
            Variety,
            Subfarm,
            Factory,
            CoreForecastMarketablePolicyModel,
        )
        .join(Farm, Farm.id == FarmSeasonVarietyPlan.farm_id)
        .join(Season, Season.id == FarmSeasonVarietyPlan.season_id)
        .join(Variety, Variety.id == FarmSeasonVarietyPlan.variety_id)
        .join(
            Subfarm,
            and_(
                Subfarm.id == FarmSeasonVarietyPlan.subfarm_id,
                Subfarm.farm_id == FarmSeasonVarietyPlan.farm_id,
            ),
        )
        .join(
            CoreForecastMarketablePolicyEntryModel,
            and_(
                CoreForecastMarketablePolicyEntryModel.farm_id == FarmSeasonVarietyPlan.farm_id,
                CoreForecastMarketablePolicyEntryModel.subfarm_id
                == FarmSeasonVarietyPlan.subfarm_id,
                CoreForecastMarketablePolicyEntryModel.variety_id
                == FarmSeasonVarietyPlan.variety_id,
            ),
        )
        .join(
            CoreForecastMarketablePolicyModel,
            and_(
                CoreForecastMarketablePolicyModel.id
                == CoreForecastMarketablePolicyEntryModel.policy_id,
                CoreForecastMarketablePolicyModel.season_id == FarmSeasonVarietyPlan.season_id,
                CoreForecastMarketablePolicyModel.status == "ACTIVE",
            ),
        )
        .join(
            Factory,
            and_(
                Factory.id == CoreForecastMarketablePolicyModel.factory_id,
                Factory.active.is_(True),
                Factory.code.is_not(None),
            ),
        )
    )
    rows = result.all()
    if not rows:
        raise TrialApiError(
            TrialApiErrorCode.AUTHORITY_UNAVAILABLE,
            status_code=503,
            message="Trial authority is unavailable.",
            retryable=True,
        )

    items: list[TrialForecastInputAuthorityItem] = []
    evidence: dict[tuple[str, str | None, str, str, str], _ForecastAuthorityEvidence] = {}
    available_at: list[datetime] = []
    for plan, farm, season, variety, subfarm, factory, policy in rows:
        if plan.subfarm_id is None or factory.code is None:
            raise TrialApiError(
                TrialApiErrorCode.AUTHORITY_UNAVAILABLE,
                status_code=503,
                message="Trial authority is unavailable.",
                retryable=True,
            )
        item = TrialForecastInputAuthorityItem(
            farm_business_key=farm.name,
            subfarm_business_key_or_null=_subfarm_public_key(farm, subfarm),
            season_business_key=season.code,
            variety_business_key=variety.code,
            destination_factory_business_key=factory.code,
            plan_version=str(plan.version),
            plan_row_hash=plan.row_hash,
            planting_area_mu=_canonical_quantity(plan.planted_area_mu),
        )
        key = (
            item.farm_business_key,
            item.subfarm_business_key_or_null,
            item.season_business_key,
            item.variety_business_key,
            item.destination_factory_business_key,
        )
        if key in evidence:
            existing = evidence[key]
            if (
                existing.plan_row_hash != item.plan_row_hash
                or existing.plan_version != item.plan_version
                or existing.planting_area_mu != item.planting_area_mu
            ):
                raise TrialApiError(
                    TrialApiErrorCode.AUTHORITY_UNAVAILABLE,
                    status_code=503,
                    message="Trial authority is unavailable.",
                    retryable=True,
                )
            plan_available_at = datetime.combine(
                plan.available_at,
                datetime.min.time(),
                tzinfo=UTC,
            )
            available_at.append(max(plan_available_at, _aware_datetime(policy.available_at)))
            continue
        plan_available_at = datetime.combine(plan.available_at, datetime.min.time(), tzinfo=UTC)
        policy_available_at = _aware_datetime(policy.available_at)
        available_at.append(max(plan_available_at, policy_available_at))
        items.append(item)
        evidence[key] = _ForecastAuthorityEvidence(
            scope=TrialForecastScope(
                farm_business_key=item.farm_business_key,
                subfarm_business_key_or_null=item.subfarm_business_key_or_null,
                season_business_key=item.season_business_key,
                variety_business_key=item.variety_business_key,
                destination_factory_business_key=item.destination_factory_business_key,
            ),
            farm_id=plan.farm_id,
            subfarm_id=plan.subfarm_id,
            variety_id=plan.variety_id,
            season_id=plan.season_id,
            factory_id=factory.id,
            plan_row_hash=item.plan_row_hash,
            plan_version=item.plan_version,
            planting_area_mu=item.planting_area_mu,
            forecast_input_authority_hash="",
            authority_available_at=max(plan_available_at, policy_available_at),
            business_scope_hash="",
        )

    items = sorted(
        items,
        key=lambda item: (
            item.farm_business_key,
            item.subfarm_business_key_or_null or "",
            item.season_business_key,
            item.variety_business_key,
            item.destination_factory_business_key,
        ),
    )
    authority_available_at = max(available_at)
    payload = {
        "schema_version": "v0.2-trial-forecast-input-authority-v1",
        "authority_available_at": authority_available_at.isoformat(),
        "items": [item.model_dump(mode="json") for item in items],
    }
    authority_hash = hashlib.sha256(canonical_json_dumps(payload).encode("utf-8")).hexdigest()
    for key, item_evidence in tuple(evidence.items()):
        evidence[key] = _with_scope_hash(
            item_evidence,
            authority_hash=authority_hash,
            authority_available_at=authority_available_at,
        )
    return _ForecastAuthoritySnapshot(
        public_response=TrialForecastInputAuthorityResponse(
            forecast_input_authority_hash=authority_hash,
            authority_available_at=authority_available_at,
            items=tuple(items),
            authority_version="v0.2-trial-forecast-input-authority-v1",
        ),
        evidence_by_key=evidence,
    )


def _with_scope_hash(
    evidence: _ForecastAuthorityEvidence,
    *,
    authority_hash: str,
    authority_available_at: datetime,
) -> _ForecastAuthorityEvidence:
    return replace(
        evidence,
        forecast_input_authority_hash=authority_hash,
        authority_available_at=authority_available_at,
        business_scope_hash=compute_trial_business_scope_hash(
            farm_business_key=evidence.scope.farm_business_key,
            subfarm_business_key_or_null=evidence.scope.subfarm_business_key_or_null,
            season_business_key=evidence.scope.season_business_key,
            variety_business_key=evidence.scope.variety_business_key,
            destination_factory_business_key=evidence.scope.destination_factory_business_key,
        ),
    )


async def _resolve_create_authority(
    session: AsyncSession,
    request: TrialForecastCreateRequest,
) -> _CreateForecastAuthority:
    if request.subfarm_business_key_or_null is None:
        raise TrialApiError(
            TrialApiErrorCode.INPUT_NOT_SUPPORTED,
            status_code=422,
            message="A concrete subfarm is required for Trial Forecast creation.",
        )
    snapshot = await _load_forecast_authority_snapshot(session)
    if (
        request.forecast_input_authority_hash
        != snapshot.public_response.forecast_input_authority_hash
    ):
        raise TrialApiError(
            TrialApiErrorCode.EVIDENCE_CONFLICT,
            status_code=409,
            message="Forecast authority evidence is conflicting.",
        )

    candidates = [
        item
        for item in snapshot.evidence_by_key.values()
        if item.scope.farm_business_key == request.farm_business_key
        and item.scope.season_business_key == request.season_business_key
        and item.scope.variety_business_key == request.variety_business_key
        and item.scope.destination_factory_business_key == request.destination_factory_business_key
        and _subfarm_request_matches(request.subfarm_business_key_or_null, item.scope)
    ]
    if not candidates:
        raise _resource_not_found()
    if len(candidates) > 1:
        raise _evidence_conflict()
    public_evidence = candidates[0]

    farm = await _single_master_row(
        session,
        select(Farm).where(Farm.name == request.farm_business_key),
        concealed=True,
    )
    season = await _single_master_row(
        session,
        select(Season).where(Season.code == request.season_business_key),
        concealed=True,
    )
    variety = await _single_master_row(
        session,
        select(Variety).where(Variety.code == request.variety_business_key),
        concealed=True,
    )
    factories = tuple(
        await session.scalars(
            select(Factory).where(
                Factory.code == request.destination_factory_business_key,
                Factory.active.is_(True),
            )
        )
    )
    if len(factories) != 1:
        raise _resource_not_found()
    factory = factories[0]
    subfarm_key = request.subfarm_business_key_or_null
    subfarm_keys = [subfarm_key]
    if subfarm_key.startswith(f"{farm.name}/"):
        subfarm_keys.append(subfarm_key.removeprefix(f"{farm.name}/"))
    subfarms = tuple(
        await session.scalars(
            select(Subfarm).where(
                Subfarm.farm_id == farm.id,
                or_(*(Subfarm.name == value for value in subfarm_keys)),
            )
        )
    )
    if len(subfarms) != 1:
        raise _resource_not_found()
    subfarm = subfarms[0]

    cutoff = _aware_datetime(request.forecast_cutoff_at)
    task9_candidates = tuple(
        run
        for run in await session.scalars(
            select(HarvestStateRun).where(
                HarvestStateRun.status == "completed",
                HarvestStateRun.forecast_season_id == season.id,
                HarvestStateRun.destination_factory_id == factory.id,
            )
        )
        if run.forecast_effective_cutoff_at is not None
        and _aware_datetime(run.forecast_effective_cutoff_at) == cutoff
    )
    if not task9_candidates:
        raise _authority_unavailable()
    if len(task9_candidates) > 1:
        raise _evidence_conflict()
    task9 = task9_candidates[0]
    plans = tuple(
        await session.scalars(
            select(FarmSeasonVarietyPlan).where(
                FarmSeasonVarietyPlan.row_hash == request.plan_row_hash,
                FarmSeasonVarietyPlan.farm_id == farm.id,
                FarmSeasonVarietyPlan.subfarm_id == subfarm.id,
                FarmSeasonVarietyPlan.season_id == season.id,
                FarmSeasonVarietyPlan.variety_id == variety.id,
                FarmSeasonVarietyPlan.available_at <= cutoff.date(),
                FarmSeasonVarietyPlan.effective_from <= task9.forecast_start_date,
                or_(
                    FarmSeasonVarietyPlan.effective_to.is_(None),
                    FarmSeasonVarietyPlan.effective_to >= task9.forecast_start_date,
                ),
            )
        )
    )
    if not plans:
        raise _resource_not_found()
    if len(plans) > 1:
        raise _evidence_conflict()
    plan = plans[0]
    if _canonical_quantity(plan.planted_area_mu) != request.planting_area_mu:
        raise TrialApiError(
            TrialApiErrorCode.REQUEST_INVALID,
            status_code=422,
            message="Forecast request is invalid.",
        )
    if public_evidence.plan_row_hash != plan.row_hash:
        raise _evidence_conflict()
    if task9.maturity_forecast_run_id is None:
        raise _authority_unavailable()

    code_authorities = tuple(
        await session.scalars(
            select(CoreForecastCodeAuthorityModel).where(
                CoreForecastCodeAuthorityModel.available_at <= cutoff
            )
        )
    )
    if not code_authorities:
        raise _authority_unavailable()
    if len(code_authorities) > 1:
        raise _evidence_conflict()
    core_repository = SqlAlchemyCoreForecastRepository(session)
    resolved_identity = await core_repository.resolve_business_identity(
        season_id=season.id,
        factory_id=factory.id,
        scopes=((farm.id, subfarm.id, variety.id),),
    )
    if resolved_identity is None:
        raise _authority_unavailable()
    core_request = ExecuteCoreForecastRunRequest(
        curve_request=CompleteDailyMarketableCurveRequest(
            forecast_season_id=season.id,
            forecast_season_code=season.code,
            forecast_start_date=task9.forecast_start_date,
            forecast_end_date=task9.forecast_end_date,
            destination_factory_id=factory.id,
            task8_forecast_run_id=task9.maturity_forecast_run_id,
            task9_harvest_state_run_id=task9.id,
            scopes=(
                CoreForecastScope(
                    farm_id=farm.id,
                    subfarm_id=subfarm.id,
                    variety_id=variety.id,
                ),
            ),
        ),
        retention_policy=await _select_retention_policy(
            core_repository,
            season_id=season.id,
            factory_id=factory.id,
            cutoff=cutoff,
            start=task9.forecast_start_date,
            end=task9.forecast_end_date,
            scopes=((farm.id, subfarm.id, variety.id),),
        ),
        code_authority_id=code_authorities[0].id,
        resolved_identity=resolved_identity,
        forecast_effective_cutoff_at=cutoff,
    )
    evidence = _with_scope_hash(
        _ForecastAuthorityEvidence(
            **{
                **public_evidence.__dict__,
                "farm_id": farm.id,
                "subfarm_id": subfarm.id,
                "variety_id": variety.id,
                "season_id": season.id,
                "factory_id": factory.id,
            }
        ),
        authority_hash=snapshot.public_response.forecast_input_authority_hash,
        authority_available_at=snapshot.public_response.authority_available_at,
    )
    return _CreateForecastAuthority(
        core_request=core_request,
        evidence=evidence,
        business_scope_hash=evidence.business_scope_hash,
    )


def _subfarm_request_matches(submitted: str | None, scope: TrialForecastScope) -> bool:
    return submitted in {
        scope.subfarm_business_key_or_null,
        f"{scope.farm_business_key}/{scope.subfarm_business_key_or_null}"
        if scope.subfarm_business_key_or_null is not None
        else None,
    }


async def _select_retention_policy(
    repository: SqlAlchemyCoreForecastRepository,
    *,
    season_id: int,
    factory_id: int,
    cutoff: datetime,
    start: date,
    end: date,
    scopes: tuple[tuple[int, int, int], ...],
) -> Any:
    try:
        return await repository.load_marketable_retention_policy(
            season_id=season_id,
            factory_id=factory_id,
            forecast_cutoff_at=cutoff,
            forecast_start_date=start,
            forecast_end_date=end,
            scopes=scopes,
        )
    except MarketableRetentionPolicyMissingError as error:
        raise TrialApiError(
            TrialApiErrorCode.MARKETABLE_RETENTION_POLICY_MISSING,
            status_code=503,
            message="Marketable retention policy is unavailable.",
            retryable=True,
        ) from error
    except MarketableRetentionPolicyConflictError as error:
        raise TrialApiError(
            TrialApiErrorCode.MARKETABLE_RETENTION_POLICY_CONFLICT,
            status_code=409,
            message="Marketable retention policy selection is ambiguous.",
        ) from error


async def _single_master_row(session: AsyncSession, statement: Any, *, concealed: bool) -> Any:
    rows = tuple(await session.scalars(statement))
    if len(rows) != 1:
        if concealed:
            raise _resource_not_found()
        raise _authority_unavailable()
    return rows[0]


def _resource_not_found() -> TrialApiError:
    return TrialApiError(
        TrialApiErrorCode.RESOURCE_NOT_FOUND,
        status_code=404,
        message="Resource was not found.",
    )


def _authority_unavailable() -> TrialApiError:
    return TrialApiError(
        TrialApiErrorCode.AUTHORITY_UNAVAILABLE,
        status_code=503,
        message="Trial authority is unavailable.",
        retryable=True,
    )


def _evidence_conflict() -> TrialApiError:
    return TrialApiError(
        TrialApiErrorCode.EVIDENCE_CONFLICT,
        status_code=409,
        message="Forecast authority evidence is conflicting.",
    )


def _map_core_execution_error(execution: CoreForecastExecutionResult) -> TrialApiError:
    blocker = execution.blockers[0].code if execution.blockers else ""
    if blocker == "MARKETABLE_RETENTION_POLICY_MISSING":
        return TrialApiError(
            TrialApiErrorCode.MARKETABLE_RETENTION_POLICY_MISSING,
            status_code=503,
            message="Marketable retention policy is unavailable.",
            retryable=True,
        )
    if blocker == "MARKETABLE_RETENTION_POLICY_CONFLICT":
        return TrialApiError(
            TrialApiErrorCode.MARKETABLE_RETENTION_POLICY_CONFLICT,
            status_code=409,
            message="Marketable retention policy selection is ambiguous.",
        )
    if blocker in {
        "TASK8_AUTHORITY_NOT_FOUND",
        "TASK9_AUTHORITY_NOT_FOUND",
        "AUTHORITY_SCOPE_MISMATCH",
        "AUTHORITY_LINEAGE_MISMATCH",
        "AUTHORITY_HASH_MALFORMED",
        "CORE_FORECAST_CODE_AUTHORITY_NOT_FOUND",
        "CORE_FORECAST_CODE_AUTHORITY_INVALID",
        "CORE_FORECAST_TASK9_CUTOFF_NOT_AVAILABLE",
        "CORE_FORECAST_TASK9_CUTOFF_MISMATCH",
        "CORE_FORECAST_CODE_AUTHORITY_NOT_AVAILABLE_AT_TASK9_CUTOFF",
    }:
        return _authority_unavailable()
    if blocker in {
        "CORE_FORECAST_PERSISTENCE_CONFLICT",
        "CORE_FORECAST_PERSISTENCE_INTEGRITY_FAILED",
    }:
        return _evidence_conflict()
    return _service_unavailable("core forecast execution")


async def _load_verified_forecast(
    session: AsyncSession,
    run_id: str,
    actor: ActualHarvestActorContext,
    *,
    permission: str,
) -> tuple[Any, CoreForecastExecutionResult, _ForecastAuthorityEvidence]:
    _require_forecast_permission(actor, permission)
    if re.fullmatch(r"[0-9a-f]{64}", run_id) is None:
        raise _resource_not_found()
    try:
        persisted_evidence = await authorize_and_load_forecast_evidence(
            session,
            public_forecast_id=run_id,
            owner_identity=actor.identity,
        )
    except TrialForecastEvidenceNotFoundError as error:
        raise _resource_not_found() from error
    except TrialForecastEvidenceIntegrityError as error:
        raise _evidence_conflict() from error
    except TrialForecastEvidenceConflictError as error:
        raise _evidence_conflict() from error
    except TrialForecastEvidenceError as error:
        raise _service_unavailable("forecast evidence persistence") from error
    try:
        persisted = await CoreForecastRunRepository(session).get_run_by_request_hash(run_id)
    except CoreForecastPersistenceIntegrityError as error:
        raise _evidence_conflict() from error
    if persisted is None or persisted.run.request_hash != run_id:
        raise _resource_not_found()
    evidence = _authority_evidence_from_persisted_evidence(persisted_evidence, persisted)
    execution = CoreForecastExecutionResult(
        status="COMPLETED",
        run=persisted.run,
        daily_curve=persisted.daily_curve,
        metrics=persisted.metrics,
        reused_existing_run=True,
        blockers=(),
    )
    return persisted_evidence, execution, evidence


def _authority_evidence_from_persisted_evidence(
    evidence: TrialForecastEvidence,
    source: _ForecastAuthorityEvidence | Any,
) -> _ForecastAuthorityEvidence:
    """Project immutable public evidence while preserving already-resolved IDs.

    ``source`` is either the creation-time authority carrying the resolved
    database scope IDs, or a hydrated Core Forecast run carrying its persisted
    request identity.  No current master-data or policy rows are consulted.
    """

    if isinstance(source, _ForecastAuthorityEvidence):
        if (
            evidence.business_scope_hash
            != compute_trial_business_scope_hash(
                farm_business_key=evidence.farm_business_key,
                subfarm_business_key_or_null=evidence.subfarm_business_key_or_null,
                season_business_key=evidence.season_business_key,
                variety_business_key=evidence.variety_business_key,
                destination_factory_business_key=evidence.destination_factory_business_key,
            )
            or evidence.subfarm_business_key_or_null is None
        ):
            raise _evidence_conflict()
        return replace(
            source,
            scope=TrialForecastScope(
                farm_business_key=evidence.farm_business_key,
                subfarm_business_key_or_null=evidence.subfarm_business_key_or_null,
                season_business_key=evidence.season_business_key,
                variety_business_key=evidence.variety_business_key,
                destination_factory_business_key=evidence.destination_factory_business_key,
            ),
            plan_row_hash=evidence.plan_row_hash,
            plan_version=evidence.plan_version,
            planting_area_mu=evidence.planting_area_mu,
            forecast_input_authority_hash=evidence.forecast_input_authority_hash,
            authority_available_at=evidence.authority_available_at,
            business_scope_hash=evidence.business_scope_hash,
        )

    persisted = source
    request = persisted.request
    run = persisted.run
    identity = request.resolved_identity
    core_scopes = request.curve_request.scopes
    if identity is None or len(identity.scopes) != 1 or len(core_scopes) != 1:
        raise _evidence_conflict()
    scope_identity = identity.scopes[0]
    core_scope = core_scopes[0]
    subfarm_key = evidence.subfarm_business_key_or_null
    if subfarm_key is None:
        raise _evidence_conflict()
    if (
        run.request_hash != evidence.public_forecast_id
        or identity.season_business_key != evidence.season_business_key
        or identity.factory_business_key != evidence.destination_factory_business_key
        or scope_identity.farm_business_key != evidence.farm_business_key
        or scope_identity.variety_business_key != evidence.variety_business_key
        or scope_identity.subfarm_business_key
        not in {subfarm_key, f"{evidence.farm_business_key}/{subfarm_key}"}
        or run.forecast_season_id != request.curve_request.forecast_season_id
        or run.forecast_season_code != evidence.season_business_key
        or run.destination_factory_id != request.curve_request.destination_factory_id
    ):
        raise _evidence_conflict()
    if evidence.business_scope_hash != compute_trial_business_scope_hash(
        farm_business_key=evidence.farm_business_key,
        subfarm_business_key_or_null=subfarm_key,
        season_business_key=evidence.season_business_key,
        variety_business_key=evidence.variety_business_key,
        destination_factory_business_key=evidence.destination_factory_business_key,
    ):
        raise _evidence_conflict()
    return _ForecastAuthorityEvidence(
        scope=TrialForecastScope(
            farm_business_key=evidence.farm_business_key,
            subfarm_business_key_or_null=subfarm_key,
            season_business_key=evidence.season_business_key,
            variety_business_key=evidence.variety_business_key,
            destination_factory_business_key=evidence.destination_factory_business_key,
        ),
        farm_id=core_scope.farm_id,
        subfarm_id=core_scope.subfarm_id,
        variety_id=core_scope.variety_id,
        season_id=request.curve_request.forecast_season_id,
        factory_id=request.curve_request.destination_factory_id,
        plan_row_hash=evidence.plan_row_hash,
        plan_version=evidence.plan_version,
        planting_area_mu=evidence.planting_area_mu,
        forecast_input_authority_hash=evidence.forecast_input_authority_hash,
        authority_available_at=evidence.authority_available_at,
        business_scope_hash=evidence.business_scope_hash,
    )


def _project_forecast_summary(
    execution: CoreForecastExecutionResult,
    evidence: _ForecastAuthorityEvidence,
) -> TrialForecastSummaryResponse:
    if execution.run is None or execution.daily_curve is None or execution.metrics is None:
        raise _service_unavailable("forecast projection")
    run = execution.run
    rows = _scope_rows(execution, evidence)
    daily_rows = _project_daily_rows(rows)
    metrics = {item.forecast_quantile: item for item in execution.metrics.metrics}
    p50 = metrics.get("P50")
    last_p50 = next((row for row in reversed(rows) if row.forecast_quantile == "P50"), None)
    first_row = rows[0]
    policy_version = first_row.marketable_policy_version
    policy_hash = first_row.marketable_policy_hash
    scope = evidence.scope.model_copy(
        update={"subfarm_business_key_or_null": evidence.scope.subfarm_business_key_or_null}
    )
    cutoff = run.forecast_effective_cutoff_at
    if cutoff is None:
        raise _evidence_conflict()
    return TrialForecastSummaryResponse(
        run_id=run.request_hash,
        status="COMPLETED",
        daily_p50_series=tuple(row for row in daily_rows),
        daily_p80_series=tuple(row for row in daily_rows),
        daily_p90_series=tuple(row for row in daily_rows),
        single_day_peak=(p50.single_day_peak.model_dump(mode="json") if p50 is not None else None),
        sustained_seven_day_peak=(
            p50.sustained_7day_peak.model_dump(mode="json") if p50 is not None else None
        ),
        season_cumulative_quantity=(
            Decimal(p50.season_cumulative_effective_marketable_kg) if p50 is not None else None
        ),
        mature_inventory_summary=(
            {
                "opening_quantity_kg": last_p50.opening_mature_inventory_kg,
                "closing_quantity_kg": last_p50.closing_mature_inventory_kg,
            }
            if last_p50 is not None
            else None
        ),
        backlog_summary=(
            {"quantity_kg": last_p50.unharvested_backlog_kg} if last_p50 is not None else None
        ),
        model_version=first_row.task8_artifact_hash,
        parameter_version=first_row.task9_result_hash,
        policy_versions={"forecast": policy_version},
        canonical_public_hash=run.request_hash,
        forecast_scope=scope,
        forecast_start_date=run.forecast_start_date,
        forecast_end_date=run.forecast_end_date,
        forecast_cutoff_at=_aware_datetime(cutoff),
        forecast_input_authority_hash=evidence.forecast_input_authority_hash,
        plan_row_hash=evidence.plan_row_hash,
        planting_area_mu=evidence.planting_area_mu,
        policy_identity=policy_version,
        policy_hash=policy_hash,
        model_identity=first_row.task8_artifact_hash,
        parameter_identity=first_row.task9_result_hash,
        code_authority_identity=run.code_authority_hash,
        task8_identity=first_row.task8_artifact_hash,
        task9_identity=first_row.task9_result_hash,
        result_hash=run.result_hash,
        curve_hash=run.curve_hash,
        metrics_hash=run.metrics_hash,
    )


def _scope_rows(
    execution: CoreForecastExecutionResult,
    evidence: _ForecastAuthorityEvidence,
) -> tuple[Any, ...]:
    assert execution.daily_curve is not None
    rows = tuple(
        row
        for row in execution.daily_curve.rows
        if row.farm_id == evidence.farm_id
        and row.subfarm_id == evidence.subfarm_id
        and row.variety_id == evidence.variety_id
        and row.destination_factory_id == evidence.factory_id
    )
    return tuple(
        sorted(
            rows,
            key=lambda row: (row.date, {"P50": 0, "P80": 1, "P90": 2}[row.forecast_quantile]),
        )
    )


def _project_daily_rows(rows: Sequence[Any]) -> tuple[TrialForecastDailyRow, ...]:
    by_date: dict[date, dict[str, Any]] = {}
    for row in rows:
        by_date.setdefault(row.date, {})[row.forecast_quantile] = row
    result: list[TrialForecastDailyRow] = []
    for current_date in sorted(by_date):
        values = by_date[current_date]
        if set(values) != {"P50", "P80", "P90"}:
            raise _evidence_conflict()
        result.append(
            TrialForecastDailyRow(
                target_date=current_date,
                p50_value_kg=Decimal(values["P50"].effective_marketable_quantity_kg),
                p80_value_kg=Decimal(values["P80"].effective_marketable_quantity_kg),
                p90_value_kg=Decimal(values["P90"].effective_marketable_quantity_kg),
                row_status="COMPLETED",
            )
        )
    return tuple(result)


def _project_daily_curve(
    execution: CoreForecastExecutionResult,
    evidence: _ForecastAuthorityEvidence,
) -> TrialForecastDailyCurveResponse:
    if execution.run is None:
        raise _service_unavailable("daily curve projection")
    cutoff = execution.run.forecast_effective_cutoff_at
    if cutoff is None:
        raise _evidence_conflict()
    return TrialForecastDailyCurveResponse(
        run_id=execution.run.request_hash,
        forecast_cutoff_at=_aware_datetime(cutoff),
        rows=_project_daily_rows(_scope_rows(execution, evidence)),
        forecast_start_date=execution.run.forecast_start_date,
        forecast_end_date=execution.run.forecast_end_date,
        forecast_scope=evidence.scope,
    )


def _project_forecast_csv(
    execution: CoreForecastExecutionResult,
    evidence: _ForecastAuthorityEvidence,
) -> TrialCsvDocument:
    if execution.run is None:
        raise _service_unavailable("forecast export")
    rows = _project_daily_rows(_scope_rows(execution, evidence))
    return TrialCsvDocument(
        filename=f"{execution.run.request_hash}.csv",
        content=serialize_csv(
            ("target_date", "p50_value_kg", "p80_value_kg", "p90_value_kg", "row_status"),
            tuple(
                (
                    row.target_date,
                    row.p50_value_kg,
                    row.p80_value_kg,
                    row.p90_value_kg,
                    row.row_status,
                )
                for row in rows
            ),
        ),
    )


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


def _concealed_import_scope_error() -> ActualHarvestApiError:
    return ActualHarvestApiError(
        ActualHarvestApiErrorCode.IMPORT_BATCH_NOT_FOUND,
        "actual-harvest import batch was not found",
        status_code=404,
    )


def _require_import_scope(
    batch: ActualHarvestApiBatchSummary,
    actor: ActualHarvestActorContext,
    permission: str,
    *,
    channel: ActualHarvestImportChannel | None = None,
    conceal_mismatch: bool,
) -> None:
    try:
        persisted_channel = ActualHarvestImportChannel(batch.import_channel)
    except ValueError as error:
        if conceal_mismatch:
            raise _concealed_import_scope_error() from error
        raise

    try:
        require_actor_scope(
            actor,
            source_system=batch.source_system,
            channel=persisted_channel,
            permission=permission,
            submitted_by_identity=batch.submitted_by_identity,
            hide_identity_mismatch=conceal_mismatch,
        )
        if channel is not None and channel is not persisted_channel:
            if conceal_mismatch:
                raise _concealed_import_scope_error()
            raise ActualHarvestApiError(
                ActualHarvestApiErrorCode.ACTUAL_HARVEST_SCOPE_FORBIDDEN,
                "uploaded channel does not match the import batch",
                status_code=403,
            )
        if channel is not None:
            require_actor_scope(
                actor,
                source_system=batch.source_system,
                channel=channel,
                permission=permission,
                submitted_by_identity=batch.submitted_by_identity,
                hide_identity_mismatch=conceal_mismatch,
            )
    except ActualHarvestApiError as error:
        if conceal_mismatch and error.code in {
            ActualHarvestApiErrorCode.ACTUAL_HARVEST_ACTOR_MISMATCH,
            ActualHarvestApiErrorCode.ACTUAL_HARVEST_SCOPE_FORBIDDEN,
        }:
            raise _concealed_import_scope_error() from error
        raise


async def _load_scoped_import_batch(
    session: AsyncSession,
    import_id: str,
    actor: ActualHarvestActorContext,
    permission: str,
) -> ActualHarvestApiBatchSummary:
    batch = await get_import(session, import_id)
    _require_import_scope(batch, actor, permission, conceal_mismatch=True)
    return batch


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
            TrialApiErrorCode.AUTHORIZATION_FORBIDDEN,
            403,
            False,
            "Trial authorization scope is forbidden.",
        ),
        ActualHarvestApiErrorCode.ACTUAL_HARVEST_ACTOR_MISMATCH: (
            TrialApiErrorCode.AUTHORIZATION_FORBIDDEN,
            403,
            False,
            "Trial actor identity is forbidden.",
        ),
        ActualHarvestApiErrorCode.IDENTITY_MAPPING_AUTHORITY_UNAVAILABLE: (
            TrialApiErrorCode.AUTHORITY_UNAVAILABLE,
            503,
            True,
            "Trial authority is unavailable.",
        ),
        ActualHarvestApiErrorCode.IDENTITY_MAPPING_AUTHORITY_CONFLICT: (
            TrialApiErrorCode.EVIDENCE_CONFLICT,
            409,
            False,
            "Trial authority is conflicting.",
        ),
        ActualHarvestApiErrorCode.IDENTITY_MAPPING_REGISTRY_HASH_CHANGED: (
            TrialApiErrorCode.EVIDENCE_CONFLICT,
            409,
            False,
            "Trial authority evidence is conflicting.",
        ),
        ActualHarvestApiErrorCode.IDEMPOTENCY_KEY_CONFLICT: (
            TrialApiErrorCode.CONFLICTING_REPLAY,
            409,
            False,
            "Request conflicts with an existing replay.",
        ),
        ActualHarvestApiErrorCode.EXTERNAL_BATCH_ID_CONFLICT: (
            TrialApiErrorCode.CONFLICTING_REPLAY,
            409,
            False,
            "Request conflicts with an existing replay.",
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
    "TrialActualHarvestImportCreateRequest",
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
    "TrialForecastInputAuthorityItem",
    "TrialForecastInputAuthorityResponse",
    "TrialForecastScope",
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
