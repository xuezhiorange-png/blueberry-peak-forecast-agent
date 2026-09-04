"""Thin application boundary for the V0.2-S4 trial API.

The module deliberately owns transport mapping only. Forecast, label, quality,
and persistence semantics remain owned by the existing S1-S3 services.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Literal, Protocol, cast

from fastapi import Depends
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)
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
from backend.app.actual_harvest_labels.enums import ActualHarvestLabelVisibilityMode
from backend.app.actual_harvest_labels.hashes import (
    AGGREGATION_POLICY_VERSION,
    SNAPSHOT_POLICY_VERSION,
    WINNER_POLICY_VERSION,
)
from backend.app.actual_harvest_labels.persistence import (
    load_label_rows_for_snapshot,
    load_winners_for_snapshot,
)
from backend.app.actual_harvest_labels.schemas import ActualHarvestLabelSnapshotRequest
from backend.app.actual_harvest_labels.service import (
    ActualHarvestLabelSnapshotError,
    create_label_snapshot,
)
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
from backend.app.forecast_quality.baseline import resolve_baseline_point_forecast
from backend.app.forecast_quality.breakdown import calculate_breakdown_cells
from backend.app.forecast_quality.calculator_daily import compute_daily_metrics
from backend.app.forecast_quality.canonical import emit_s3_decimal
from backend.app.forecast_quality.comparison import (
    ComparisonBaselineRecord,
    compute_model_baseline_comparisons,
)
from backend.app.forecast_quality.enums import (
    FrozenVersion,
    SupportedQuantile,
)
from backend.app.forecast_quality.persistence import (
    ROUND_C_PERSISTENCE_SCHEMA_VERSION,
    BaselinePersistenceRecord,
    ForecastQualityConflictError,
    ForecastQualityContractError,
    ForecastQualityPartialResultError,
    ForecastQualityPersistenceError,
    load_quality_evaluation_by_instance_hash,
    persist_quality_evaluation,
    resolve_trial_quality_request_replay,
)
from backend.app.forecast_quality.schemas import (
    BaselineRequest,
    BaselineSourceSnapshot,
    BreakdownSpec,
    DailyMetricResult,
    QualityStatusEvidenceCell,
    S3BindingRow,
    S3EvaluationInput,
)
from backend.app.forecast_quality.status_evidence import (
    build_frozen_quality_status_evidence,
)
from backend.app.harvest_state.persistence import load_harvest_state_output_by_id
from backend.app.models.core_forecast import (
    CoreForecastCodeAuthorityModel,
    CoreForecastDailyRowModel,
    CoreForecastRunModel,
)
from backend.app.models.harvest_state import HarvestStateRun
from backend.app.models.master_data import Factory, Farm, Season, Subfarm, Variety
from backend.app.models.production_plan import FarmSeasonVarietyPlan
from backend.app.models.residual_model import (
    ResidualModelPredictionRun,
    ResidualModelTrainingRun,
)
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
from backend.app.repositories.trial_resource_binding import (
    TrialResourceBindingError,
    TrialResourceKind,
    TrialResourceNotFoundError,
    authorize_trial_resource,
    create_quality_binding_in_result_boundary,
)
from backend.app.residual_model.persistence import (
    load_residual_prediction_run_by_id,
    load_residual_training_run_by_id,
)
from backend.app.residual_model.schemas import (
    ResidualPredictionExecutionResult,
    ResidualPredictionRow,
    ResidualTrainingExecutionResult,
)
from backend.app.rolling_backtest.canonical import canonical_json_dumps
from backend.app.rolling_backtest.errors import RollingBacktestCanonicalParityError
from backend.app.rolling_backtest.orchestration import run_s2_historical_binding
from backend.app.rolling_backtest.persisted_forecast_authority import task9_member_identity_hash
from backend.app.rolling_backtest.persistence import (
    load_s2_historical_binding_by_instance_hash,
)
from backend.app.rolling_backtest.schemas import (
    S2ForecastAuthorityBundle,
    S2HistoricalBacktestRequest,
    S2HistoricalBindingCandidate,
    S2PersistedAuthorityReferences,
)


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
    QUALITY_AUTHORITY_UNAVAILABLE = "QUALITY_AUTHORITY_UNAVAILABLE"
    QUALITY_PERSISTENCE_UNAVAILABLE = "QUALITY_PERSISTENCE_UNAVAILABLE"
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


def _canonical_public_quantity(value: object) -> Decimal:
    if isinstance(value, (bool, float)) or value is None:
        raise ValueError("quantities must be finite canonical Decimal values")
    try:
        quantity = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception as error:
        raise ValueError("quantities must be finite canonical Decimal values") from error
    if not quantity.is_finite() or quantity < 0:
        raise ValueError("quantities must be finite and non-negative")
    exponent = quantity.as_tuple().exponent
    if not isinstance(exponent, int) or exponent < -6:
        raise ValueError("quantities must use at most six decimal places")
    try:
        return quantity.quantize(Decimal("0.000001"))
    except Exception as error:
        raise ValueError("quantities must use canonical six-place precision") from error


class TrialForecastSingleDayPeakResponse(_FrozenModel):
    date: date
    quantity_kg: Decimal
    tie_break: Literal["EARLIEST_DATE"]

    _canonical_quantity = field_validator("quantity_kg", mode="before")(_canonical_public_quantity)


class TrialForecastSustainedSevenDayPeakResponse(_FrozenModel):
    start_date: date
    end_date: date
    cumulative_quantity_kg: Decimal
    daily_average_kg_per_day: Decimal
    window_days: Literal[7]
    metric: Literal["ROLLING_CUMULATIVE"]
    date_continuity: Literal["STRICT_CALENDAR_DAYS"]
    tie_break: Literal["EARLIEST_START_DATE"]

    _canonical_quantity = field_validator(
        "cumulative_quantity_kg", "daily_average_kg_per_day", mode="before"
    )(_canonical_public_quantity)

    @model_validator(mode="after")
    def _require_contiguous_window(self) -> TrialForecastSustainedSevenDayPeakResponse:
        if self.end_date != self.start_date + timedelta(days=6):
            raise ValueError("sustained peak window must contain seven calendar days")
        return self


class TrialForecastInventorySummaryResponse(_FrozenModel):
    opening_quantity_kg: Decimal
    closing_quantity_kg: Decimal

    _canonical_quantity = field_validator(
        "opening_quantity_kg", "closing_quantity_kg", mode="before"
    )(_canonical_public_quantity)


class TrialForecastBacklogSummaryResponse(_FrozenModel):
    quantity_kg: Decimal

    _canonical_quantity = field_validator("quantity_kg", mode="before")(_canonical_public_quantity)


class TrialForecastPolicyVersionsResponse(_FrozenModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    forecast: StrictStr = Field(min_length=1)


class TrialForecastSummaryResponse(_FrozenModel):
    run_id: StrictStr
    status: StrictStr
    daily_p50_series: tuple[TrialForecastDailyRow, ...]
    daily_p80_series: tuple[TrialForecastDailyRow, ...]
    daily_p90_series: tuple[TrialForecastDailyRow, ...]
    single_day_peak: TrialForecastSingleDayPeakResponse
    sustained_seven_day_peak: TrialForecastSustainedSevenDayPeakResponse
    season_cumulative_quantity: Decimal | None = None
    mature_inventory_summary: TrialForecastInventorySummaryResponse
    backlog_summary: TrialForecastBacklogSummaryResponse
    data_gap_summaries: tuple[StrictStr, ...] = ()
    blocker_summaries: tuple[StrictStr, ...] = ()
    model_version: StrictStr
    parameter_version: StrictStr
    policy_versions: TrialForecastPolicyVersionsResponse
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
    forecast_run_id: StrictStr = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    actual_harvest_import_id: StrictStr = Field(min_length=1, max_length=256)
    forecast_cutoff_at: datetime
    label_observation_cutoff_at: datetime
    requested_horizons_days: tuple[StrictInt, ...]
    request_idempotency_key: StrictStr = Field(min_length=1, max_length=256)

    @field_validator("forecast_cutoff_at", "label_observation_cutoff_at")
    @classmethod
    def _timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        return value

    @field_validator("requested_horizons_days", mode="before")
    @classmethod
    def _exact_horizons(cls, value: object) -> tuple[int, ...]:
        if not isinstance(value, (tuple, list)):
            raise ValueError("requested_horizons_days must be a tuple or list")
        if any(isinstance(item, bool) or not isinstance(item, int) for item in value):
            raise ValueError("requested_horizons_days must contain strict integers")
        result = tuple(value)
        if result != (7, 14, 21):
            raise ValueError("requested_horizons_days must be exactly (7, 14, 21)")
        return result


class TrialQualityDailyOverlayRow(_FrozenModel):
    business_date: date
    forecast_p50_kg_or_null: Decimal | None
    forecast_p80_kg_or_null: Decimal | None
    forecast_p90_kg_or_null: Decimal | None
    actual_quantity_kg_or_null: Decimal | None
    actual_available: bool
    coverage_state: Literal["AVAILABLE", "EXCLUDED", "NOT_COMPUTABLE"]
    exclusion_reason_codes: tuple[StrictStr, ...] = ()

    @field_validator(
        "forecast_p50_kg_or_null",
        "forecast_p80_kg_or_null",
        "forecast_p90_kg_or_null",
        "actual_quantity_kg_or_null",
        mode="before",
    )
    @classmethod
    def _reject_float(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("native float is not a canonical Decimal")
        return value


class TrialQualityMetric(_FrozenModel):
    metric_name: StrictStr
    metric_status: StrictStr
    metric_value_or_null: Decimal | None
    numerator_or_null: Decimal | None
    denominator_or_null: Decimal | None
    reason_codes: tuple[StrictStr, ...] = ()

    @field_validator(
        "metric_value_or_null",
        "numerator_or_null",
        "denominator_or_null",
        mode="before",
    )
    @classmethod
    def _reject_float(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("native float is not a canonical Decimal")
        return value


class TrialQualityPeakMetric(_FrozenModel):
    metric_status: StrictStr
    metric_value_or_null: Decimal | None
    business_date_or_null: date | None
    window_start_date_or_null: date | None
    window_end_date_or_null: date | None
    reason_codes: tuple[StrictStr, ...] = ()
    quantile: Literal["P50", "P80", "P90"] = "P50"
    forecast_horizon_days: StrictInt = 7

    @field_validator("metric_value_or_null", mode="before")
    @classmethod
    def _reject_float(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("native float is not a canonical Decimal")
        return value


class TrialQualityCoverageMetric(_FrozenModel):
    quantile: Literal["P80", "P90"]
    metric_status: StrictStr
    covered_count_or_null: StrictInt | None = None
    total_count: StrictInt
    coverage_ratio_or_null: Decimal | None
    reason_codes: tuple[StrictStr, ...] = ()
    forecast_horizon_days: StrictInt = 7

    @field_validator("coverage_ratio_or_null", mode="before")
    @classmethod
    def _reject_float(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("native float is not a canonical Decimal")
        return value


class TrialQualityIntervalMetric(_FrozenModel):
    metric_status: StrictStr
    lower_bound_available: bool
    lower_bound_value_or_null: Decimal | None
    upper_bound_value_or_null: Decimal | None
    metric_value_or_null: Decimal | None
    reason_codes: tuple[StrictStr, ...] = ()
    quantile: Literal["P80", "P90"] = "P80"
    forecast_horizon_days: StrictInt = 7

    @field_validator(
        "lower_bound_value_or_null",
        "upper_bound_value_or_null",
        "metric_value_or_null",
        mode="before",
    )
    @classmethod
    def _reject_float(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("native float is not a canonical Decimal")
        return value


class TrialQualityBreakdownIdentity(_FrozenModel):
    forecast_horizon_days: Literal[7, 14, 21]
    farm_business_key: StrictStr
    subfarm_business_key: StrictStr
    variety_business_key: StrictStr
    season_business_key: StrictStr
    model_identity: StrictStr


class TrialQualityMetricValues(_FrozenModel):
    daily_mae: Decimal | None = None
    daily_wape: Decimal | None = None
    daily_smape: Decimal | None = None
    daily_mape: Decimal | None = None
    daily_bias_kg: Decimal | None = None
    daily_relative_bias: Decimal | None = None
    daily_absolute_error_sum_kg: Decimal | None = None

    @field_validator("*", mode="before")
    @classmethod
    def _reject_float(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("native float is not a canonical Decimal")
        return value


class TrialQualityRowCounts(_FrozenModel):
    total: StrictInt = 0
    comparable: StrictInt = 0
    covered: StrictInt = 0
    excluded: StrictInt = 0
    not_computable: StrictInt = 0


class TrialQualityBreakdown(_FrozenModel):
    breakdown_identity: TrialQualityBreakdownIdentity
    metric_status: StrictStr
    coverage_ratio_or_null: Decimal | None
    comparable_row_count: StrictInt
    excluded_row_count: StrictInt
    not_computable_row_count: StrictInt
    metric_values: TrialQualityMetricValues
    reason_codes: tuple[StrictStr, ...] = ()

    @field_validator("coverage_ratio_or_null", mode="before")
    @classmethod
    def _reject_float(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("native float is not a canonical Decimal")
        return value


class TrialQualityBaselineResult(_FrozenModel):
    baseline_quantile: StrictStr
    metric_status: StrictStr
    baseline_value_kg_or_null: Decimal | None
    comparison_availability: StrictStr
    analog_date_or_null: date | None
    reason_codes: tuple[StrictStr, ...] = ()

    @field_validator("baseline_value_kg_or_null", mode="before")
    @classmethod
    def _reject_float(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("native float is not a canonical Decimal")
        return value


class TrialQualityComparisonDelta(_FrozenModel):
    comparison_name: StrictStr
    comparison_availability: StrictStr
    metric_status: StrictStr
    model_value_or_null: Decimal | None
    baseline_value_or_null: Decimal | None
    delta_value_or_null: Decimal | None
    forecast_horizon_days: StrictInt
    common_comparable_row_count: StrictInt
    model_only_row_count: StrictInt
    baseline_only_row_count: StrictInt
    excluded_row_count: StrictInt
    not_computable_row_count: StrictInt
    reason_codes: tuple[StrictStr, ...] = ()
    baseline_member_set_hash: StrictStr = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    comparison_key_hash: StrictStr = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    canonical_hash: StrictStr = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")

    @field_validator(
        "model_value_or_null",
        "baseline_value_or_null",
        "delta_value_or_null",
        mode="before",
    )
    @classmethod
    def _reject_float(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("native float is not a canonical Decimal")
        return value


class TrialQualityEvidenceIdentity(_FrozenModel):
    forecast_run_id: StrictStr = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    actual_harvest_import_id: StrictStr = Field(min_length=1, max_length=256)
    actual_label_snapshot_identity: StrictStr = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    s2_run_identity: StrictStr = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    s2_manifest_identity: StrictStr = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    s2_binding_row_set_hash: StrictStr = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    evaluation_request_hash: StrictStr = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    evaluation_instance_hash: StrictStr = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    quality_manifest_hash: StrictStr = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    metric_result_set_hash: StrictStr = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    breakdown_result_set_hash: StrictStr = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    baseline_result_set_hash: StrictStr = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    comparison_result_set_hash: StrictStr = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    metric_policy_version: StrictStr
    baseline_policy_version: StrictStr
    comparison_policy_version_or_null: StrictStr | None
    model_identity: StrictStr


class TrialQualityReportResponse(_FrozenModel):
    report_id: StrictStr = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    forecast_identity: TrialQualityEvidenceIdentity
    actual_label_snapshot_identity: StrictStr
    forecast_cutoff_at: datetime
    label_observation_cutoff_at: datetime
    requested_horizons_days: tuple[StrictInt, ...]
    horizons: tuple[TrialQualityHorizonMetrics, ...]
    daily_metrics: tuple[TrialQualityMetric, ...]
    cumulative_error: TrialQualityMetric
    single_day_peak: TrialQualityPeakMetric
    sustained_seven_day_peak: TrialQualityPeakMetric
    p80_coverage: TrialQualityCoverageMetric
    p90_coverage: TrialQualityCoverageMetric
    interval_metric: TrialQualityIntervalMetric
    breakdowns: tuple[TrialQualityBreakdown, ...]
    naive_baseline_results: tuple[TrialQualityBaselineResult, ...]
    computability_status: StrictStr
    reason_codes: tuple[StrictStr, ...]
    coverage_counts: TrialQualityRowCounts
    excluded_row_counts: TrialQualityRowCounts

    @field_validator("forecast_cutoff_at", "label_observation_cutoff_at")
    @classmethod
    def _response_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        return value


class TrialQualityHorizonMetrics(_FrozenModel):
    horizon_days: Literal[7, 14, 21]
    daily_overlay: tuple[TrialQualityDailyOverlayRow, ...]
    daily_metrics: tuple[TrialQualityMetric, ...]
    cumulative_metric: TrialQualityMetric
    single_day_peak: TrialQualityPeakMetric
    sustained_seven_day_peak: TrialQualityPeakMetric
    p80_coverage: TrialQualityCoverageMetric
    p90_coverage: TrialQualityCoverageMetric
    interval_metric: TrialQualityIntervalMetric
    coverage_counts: TrialQualityRowCounts
    excluded_row_counts: TrialQualityRowCounts
    reason_codes: tuple[StrictStr, ...] = ()
    single_day_peaks: tuple[TrialQualityPeakMetric, ...] = ()
    sustained_seven_day_peaks: tuple[TrialQualityPeakMetric, ...] = ()
    interval_metrics: tuple[TrialQualityIntervalMetric, ...] = ()


TrialQualityReportResponse.model_rebuild()


class TrialQualityComparisonResponse(_FrozenModel):
    report_id: StrictStr = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    comparison_availability: StrictStr
    comparison_status: StrictStr
    comparison_policy_version: StrictStr
    model_baseline_deltas: tuple[TrialQualityComparisonDelta, ...]
    reason_codes: tuple[StrictStr, ...]
    comparison_public_hash: StrictStr = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )


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
        _require_import_upload_scope(
            batch,
            actor,
            "may_append",
            upload_channel=metadata.channel,
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
        _require_quality_permission(actor, "may_create_quality")
        return await _run_mutation(
            session,
            lambda: _create_quality_report(
                session,
                request=request,
                actor=actor,
                clock=self.clock,
            ),
        )

    async def get_quality_report(
        self, session: AsyncSession, report_id: str, actor: ActualHarvestActorContext
    ) -> TrialQualityReportResponse:
        _require_quality_permission(actor, "may_read_quality")
        read_model = await _load_quality_read_model(session, report_id, actor)
        return await _project_quality_report(session, read_model, actor)

    async def get_quality_comparison(
        self, session: AsyncSession, report_id: str, actor: ActualHarvestActorContext
    ) -> TrialQualityComparisonResponse:
        _require_quality_permission(actor, "may_read_quality_comparison")
        read_model = await _load_quality_read_model(session, report_id, actor)
        return _project_quality_comparison(read_model)

    async def export_quality_report(
        self, session: AsyncSession, report_id: str, actor: ActualHarvestActorContext
    ) -> TrialCsvDocument:
        _require_quality_permission(actor, "may_export_quality")
        read_model = await _load_quality_read_model(session, report_id, actor)
        report = await _project_quality_report(session, read_model, actor)
        return _project_quality_csv(report)


@dataclass(frozen=True)
class _QualityReadContext:
    quality: Any
    s2: Any
    forecast_evidence: TrialForecastEvidence
    parent_forecast_public_id: str
    parent_import_id: str


def _require_quality_permission(actor: ActualHarvestActorContext, permission: str) -> None:
    if (
        not actor.identity.strip()
        or not actor.allowed_source_systems
        or not all(item.strip() for item in actor.allowed_source_systems)
        or ActualHarvestImportChannel.API not in actor.allowed_channels
    ):
        raise _resource_not_found()
    try:
        require_actor_scope(
            actor,
            source_system=sorted(actor.allowed_source_systems)[0],
            channel=ActualHarvestImportChannel.API,
            permission=permission,
        )
    except ActualHarvestApiError as error:
        raise _resource_not_found() from error


def _quality_error(
    code: TrialApiErrorCode,
    *,
    status_code: int,
    retryable: bool = False,
) -> TrialApiError:
    return TrialApiError(
        code,
        status_code=status_code,
        message="The Quality request could not be completed.",
        retryable=retryable,
    )


def _persisted_subfarm_identity_matches(
    persisted_subfarm_business_key: str,
    *,
    farm_business_key: str,
    subfarm_business_key_or_null: str | None,
) -> bool:
    """Compare the two persisted public spellings of a subfarm key."""

    if subfarm_business_key_or_null is None:
        return False
    return persisted_subfarm_business_key in {
        subfarm_business_key_or_null,
        f"{farm_business_key}/{subfarm_business_key_or_null}",
    }


async def _load_quality_parent_forecast(
    session: AsyncSession,
    *,
    request: TrialQualityReportCreateRequest,
    actor: ActualHarvestActorContext,
) -> tuple[TrialForecastEvidence, Any, ActualHarvestImportBatchModel]:
    try:
        evidence = await authorize_and_load_forecast_evidence(
            session,
            public_forecast_id=request.forecast_run_id,
            owner_identity=actor.identity,
        )
    except (TrialForecastEvidenceNotFoundError, TrialResourceNotFoundError) as error:
        raise _resource_not_found() from error
    except (TrialForecastEvidenceIntegrityError, TrialForecastEvidenceConflictError) as error:
        raise _quality_error(TrialApiErrorCode.EVIDENCE_CONFLICT, status_code=409) from error
    except TrialForecastEvidenceError as error:
        raise _quality_error(
            TrialApiErrorCode.QUALITY_PERSISTENCE_UNAVAILABLE,
            status_code=503,
            retryable=True,
        ) from error

    try:
        persisted = await CoreForecastRunRepository(session).get_run_by_request_hash(
            request.forecast_run_id
        )
    except CoreForecastPersistenceIntegrityError as error:
        raise _quality_error(TrialApiErrorCode.EVIDENCE_CONFLICT, status_code=409) from error
    if persisted is None or persisted.run.request_hash != request.forecast_run_id:
        raise _resource_not_found()
    if persisted.run.forecast_effective_cutoff_at is None:
        raise _quality_error(TrialApiErrorCode.EVIDENCE_CONFLICT, status_code=409)
    cutoff = _aware_datetime(persisted.run.forecast_effective_cutoff_at)
    if cutoff != _aware_datetime(request.forecast_cutoff_at):
        raise _quality_error(TrialApiErrorCode.REQUEST_INVALID, status_code=422)
    core_request = persisted.request.curve_request
    resolved_identity = persisted.request.resolved_identity
    if (
        resolved_identity is None
        or len(core_request.scopes) != 1
        or len(resolved_identity.scopes) != 1
        or core_request.forecast_season_id != persisted.run.forecast_season_id
        or core_request.destination_factory_id != persisted.run.destination_factory_id
        or resolved_identity.season_business_key != evidence.season_business_key
        or resolved_identity.factory_business_key != evidence.destination_factory_business_key
    ):
        raise _quality_error(TrialApiErrorCode.EVIDENCE_CONFLICT, status_code=409)
    resolved_scope = resolved_identity.scopes[0]
    if (
        resolved_scope.farm_business_key != evidence.farm_business_key
        or not _persisted_subfarm_identity_matches(
            resolved_scope.subfarm_business_key,
            farm_business_key=evidence.farm_business_key,
            subfarm_business_key_or_null=evidence.subfarm_business_key_or_null,
        )
        or resolved_scope.variety_business_key != evidence.variety_business_key
    ):
        raise _quality_error(TrialApiErrorCode.EVIDENCE_CONFLICT, status_code=409)
    import_batch = await session.scalar(
        select(ActualHarvestImportBatchModel).where(
            ActualHarvestImportBatchModel.import_id == request.actual_harvest_import_id,
            ActualHarvestImportBatchModel.submitted_by_identity == actor.identity,
            ActualHarvestImportBatchModel.status == ActualHarvestImportBatchStatus.COMMITTED.value,
        )
    )
    if import_batch is None or import_batch.source_system not in actor.allowed_source_systems:
        raise _resource_not_found()
    return evidence, persisted, import_batch


def _quality_request_identity(
    request: TrialQualityReportCreateRequest,
    *,
    actor_identity: str,
    server_owned_evidence: Mapping[str, object] | None = None,
) -> dict[str, object]:
    identity: dict[str, object] = {
        "schema_version": ROUND_C_PERSISTENCE_SCHEMA_VERSION,
        "actor_identity": actor_identity,
        "request_idempotency_key": request.request_idempotency_key,
        "canonical_request": {
            "forecast_run_id": request.forecast_run_id,
            "actual_harvest_import_id": request.actual_harvest_import_id,
            "forecast_cutoff_at": _aware_datetime(request.forecast_cutoff_at).isoformat(),
            "label_observation_cutoff_at": _aware_datetime(
                request.label_observation_cutoff_at
            ).isoformat(),
            "requested_horizons_days": request.requested_horizons_days,
        },
    }
    if server_owned_evidence is not None:
        identity["server_owned_evidence"] = dict(server_owned_evidence)
    return identity


async def _create_quality_label_snapshot(
    session: AsyncSession,
    *,
    request: TrialQualityReportCreateRequest,
    actor: ActualHarvestActorContext,
    evidence: TrialForecastEvidence,
    persisted: Any,
    import_batch: ActualHarvestImportBatchModel,
) -> Any:
    snapshot_key = hashlib.sha256(
        canonical_json_dumps(
            {
                "actor_identity": actor.identity,
                "request_idempotency_key": request.request_idempotency_key,
                "canonical_request": _quality_request_identity(
                    request,
                    actor_identity=actor.identity,
                )["canonical_request"],
            }
        ).encode("utf-8")
    ).hexdigest()
    snapshot_request = ActualHarvestLabelSnapshotRequest(
        snapshot_idempotency_key=f"trial-quality:{snapshot_key}",
        source_system=import_batch.source_system,
        visibility_mode=ActualHarvestLabelVisibilityMode.AS_OF_EVALUATION,
        label_observation_cutoff_at_or_null=_aware_datetime(request.label_observation_cutoff_at),
        harvest_date_start=persisted.run.forecast_start_date,
        harvest_date_end=persisted.run.forecast_end_date,
        season_business_keys=(evidence.season_business_key,),
        farm_business_keys_or_empty_for_all=(evidence.farm_business_key,),
        variety_business_keys_or_empty_for_all=(evidence.variety_business_key,),
        snapshot_policy_version=SNAPSHOT_POLICY_VERSION,
        winner_policy_version=WINNER_POLICY_VERSION,
        aggregation_policy_version=AGGREGATION_POLICY_VERSION,
    )
    try:
        return await create_label_snapshot(
            session,
            request=snapshot_request,
            created_by_identity=actor.identity,
        )
    except ActualHarvestLabelSnapshotError as error:
        raise _quality_error(
            TrialApiErrorCode.QUALITY_AUTHORITY_UNAVAILABLE,
            status_code=503,
            retryable=True,
        ) from error


async def _build_quality_s2_candidates(
    session: AsyncSession,
    *,
    request: TrialQualityReportCreateRequest,
    evidence: TrialForecastEvidence,
    persisted: Any,
    snapshot: Any,
) -> tuple[S2HistoricalBacktestRequest, tuple[S2HistoricalBindingCandidate, ...]]:
    """Bind the existing persisted authorities into the S2 runner contract."""

    core_run = await session.get(CoreForecastRunModel, persisted.run.run_id)
    if core_run is None:
        raise _quality_error(TrialApiErrorCode.QUALITY_AUTHORITY_UNAVAILABLE, status_code=503)
    core_rows = tuple(
        await session.scalars(
            select(CoreForecastDailyRowModel).where(
                CoreForecastDailyRowModel.core_forecast_run_id == core_run.id
            )
        )
    )
    if not core_rows:
        raise _quality_error(TrialApiErrorCode.QUALITY_AUTHORITY_UNAVAILABLE, status_code=503)
    core_repository = SqlAlchemyCoreForecastRepository(session)
    task9_authority = await core_repository.load_task9_authority(
        core_run.task9_harvest_state_run_id
    )
    task9_output = await load_harvest_state_output_by_id(
        session,
        run_id=core_run.task9_harvest_state_run_id,
    )
    task9_run = await session.get(HarvestStateRun, core_run.task9_harvest_state_run_id)
    code_authority = persisted.code_authority
    if (
        task9_authority is None
        or task9_output is None
        or task9_run is None
        or code_authority is None
    ):
        raise _quality_error(
            TrialApiErrorCode.QUALITY_AUTHORITY_UNAVAILABLE,
            status_code=503,
        )

    prediction_runs = tuple(
        await session.scalars(
            select(ResidualModelPredictionRun).where(
                ResidualModelPredictionRun.task9_run_id == task9_run.id,
                ResidualModelPredictionRun.execution_status == "completed",
            )
        )
    )
    prediction_outputs: list[
        tuple[
            ResidualModelPredictionRun,
            ResidualPredictionExecutionResult,
            ResidualTrainingExecutionResult,
            ResidualModelTrainingRun,
        ]
    ] = []
    for persisted_prediction_run in prediction_runs:
        if (
            persisted_prediction_run.id <= 0
            or persisted_prediction_run.task9_run_id != task9_run.id
            or persisted_prediction_run.execution_status != "completed"
        ):
            raise _quality_error(TrialApiErrorCode.EVIDENCE_CONFLICT, status_code=409)
        output = await load_residual_prediction_run_by_id(
            session,
            run_id=persisted_prediction_run.id,
        )
        if output is None or output.model_run_id is None:
            raise _quality_error(TrialApiErrorCode.EVIDENCE_CONFLICT, status_code=409)
        if (
            output.model_run_id != persisted_prediction_run.training_run_id
            or output.task9_run_id != persisted_prediction_run.task9_run_id
            or output.task9_result_hash != persisted_prediction_run.task9_result_hash
            or output.prediction_hash != persisted_prediction_run.prediction_hash
        ):
            raise _quality_error(TrialApiErrorCode.EVIDENCE_CONFLICT, status_code=409)
        training_output = await load_residual_training_run_by_id(
            session,
            run_id=output.model_run_id,
        )
        training_row = await session.get(ResidualModelTrainingRun, output.model_run_id)
        if training_output is None or training_row is None:
            raise _quality_error(TrialApiErrorCode.EVIDENCE_CONFLICT, status_code=409)
        prediction_outputs.append(
            (
                persisted_prediction_run,
                output,
                training_output,
                training_row,
            )
        )
    if not prediction_outputs:
        raise _quality_error(TrialApiErrorCode.QUALITY_AUTHORITY_UNAVAILABLE, status_code=503)

    label_rows = tuple(await load_label_rows_for_snapshot(session, snapshot.header.snapshot_id))
    winner_rows = tuple(await load_winners_for_snapshot(session, snapshot.header.snapshot_id))
    mapping_version = next(
        (row.mapping_policy_version for row in winner_rows if row.mapping_policy_version),
        "actual-harvest-mapping-v1",
    )
    resolver_version = next(
        (row.season_resolver_version for row in winner_rows if row.season_resolver_version),
        "actual-harvest-season-resolver-v1",
    )
    resolved_identity_snapshot_hash = next(
        (
            row.resolved_identity_snapshot_hash
            for row in winner_rows
            if row.resolved_identity_snapshot_hash
        ),
        snapshot.header.label_snapshot_hash,
    )
    s2_request = S2HistoricalBacktestRequest(
        season_business_keys=(evidence.season_business_key,),
        farm_business_keys=(evidence.farm_business_key,),
        subfarm_business_keys=(evidence.subfarm_business_key_or_null or "",),
        variety_business_keys=(evidence.variety_business_key,),
        master_identity_resolver_version=resolver_version,
        mapping_policy_version=mapping_version,
        resolved_identity_snapshot_hash=resolved_identity_snapshot_hash,
        authority_selection_policy_version="v0.2-s2-authority-v1",
        forecast_cutoff_at=_aware_datetime(request.forecast_cutoff_at),
        label_observation_cutoff_at=_aware_datetime(request.label_observation_cutoff_at),
        label_visibility_mode="AS_OF_EVALUATION",
        requested_horizons_days=request.requested_horizons_days,
    )

    candidates: list[S2HistoricalBindingCandidate] = []
    for horizon in request.requested_horizons_days:
        target_date = request.forecast_cutoff_at.date() + timedelta(days=horizon)
        for quantile in ("P50", "P80", "P90"):
            matching_core = tuple(
                row
                for row in core_rows
                if row.date == target_date
                and row.forecast_quantile == quantile
                and row.farm_id == core_rows[0].farm_id
                and row.subfarm_id == core_rows[0].subfarm_id
                and row.variety_id == core_rows[0].variety_id
                and row.destination_factory_id == core_run.destination_factory_id
            )
            if len(matching_core) != 1:
                raise _quality_error(
                    TrialApiErrorCode.QUALITY_AUTHORITY_UNAVAILABLE,
                    status_code=503,
                )
            core_row = matching_core[0]
            matching_members = tuple(
                member
                for member in task9_authority.member_rows
                if member.state_date == target_date
                and member.forecast_quantile == quantile
                and member.farm_id == core_row.farm_id
                and member.subfarm_id == core_row.subfarm_id
                and member.variety_id == core_row.variety_id
                and member.destination_factory_id == core_row.destination_factory_id
            )
            if len(matching_members) != 1:
                raise _quality_error(
                    TrialApiErrorCode.QUALITY_AUTHORITY_UNAVAILABLE,
                    status_code=503,
                )
            task9_member = matching_members[0]
            task9_member_hash = task9_member_identity_hash(task9_member)
            matching_predictions: list[
                tuple[
                    ResidualModelPredictionRun,
                    ResidualPredictionExecutionResult,
                    ResidualTrainingExecutionResult,
                    ResidualModelTrainingRun,
                    ResidualPredictionRow,
                ]
            ] = []
            for (
                persisted_prediction_run,
                output,
                training_output,
                training_row,
            ) in prediction_outputs:
                rows = tuple(
                    row
                    for row in output.rows
                    if row.arrival_local_date == target_date
                    and row.forecast_horizon_days == horizon
                    and row.destination_factory_id == core_run.destination_factory_id
                )
                if len(rows) == 1:
                    matching_predictions.append(
                        (
                            persisted_prediction_run,
                            output,
                            training_output,
                            training_row,
                            rows[0],
                        )
                    )
            if not matching_predictions:
                raise _quality_error(
                    TrialApiErrorCode.QUALITY_AUTHORITY_UNAVAILABLE,
                    status_code=503,
                )
            if len(matching_predictions) > 1:
                raise _quality_error(TrialApiErrorCode.EVIDENCE_CONFLICT, status_code=409)
            (
                persisted_prediction_run,
                prediction_output,
                training_output,
                training_row,
                prediction_row,
            ) = matching_predictions[0]

            exact_labels = tuple(
                row
                for row in label_rows
                if row.season_business_key == evidence.season_business_key
                and row.farm_business_key == evidence.farm_business_key
                and row.subfarm_business_key == evidence.subfarm_business_key_or_null
                and row.variety_business_key == evidence.variety_business_key
                and row.harvest_business_date == target_date
            )
            if len(exact_labels) > 1:
                raise _quality_error(TrialApiErrorCode.EVIDENCE_CONFLICT, status_code=409)
            label_row = exact_labels[0] if exact_labels else None
            winner_row = None
            if label_row is not None:
                try:
                    contributing_hashes = tuple(json.loads(label_row.contributing_winner_hashes))
                except (TypeError, json.JSONDecodeError) as error:
                    raise _quality_error(
                        TrialApiErrorCode.EVIDENCE_CONFLICT,
                        status_code=409,
                    ) from error
                matching_winners = tuple(
                    row for row in winner_rows if row.winner_row_hash in contributing_hashes
                )
                if len(matching_winners) != len(contributing_hashes) or not matching_winners:
                    raise _quality_error(TrialApiErrorCode.EVIDENCE_CONFLICT, status_code=409)
                winner_row = sorted(matching_winners, key=lambda row: row.winner_row_hash)[0]

            authority = S2ForecastAuthorityBundle(
                forecast_run_identity_hash=core_run.result_hash,
                daily_row_identity_hash=core_row.row_hash,
                task9_authority_identity_hash=task9_output.result_hash,
                task9_member_identity_hash=task9_member_hash,
                task10_authority_identity_hash=prediction_output.prediction_hash,
                task10_model_identity_hash=training_output.training_signature,
                task10_replay_identity_hash=prediction_output.prediction_input_signature,
                task10_prediction_row_identity_hash=prediction_row.prediction_hash,
                historical_code_authority_id=code_authority.authority_id,
                forecast_code_identity=code_authority.authority_hash,
                historical_code_identity=code_authority.source_commit_sha,
                build_artifact_hash=code_authority.build_artifact_hash,
                config_bundle_hash=code_authority.config_bundle_hash,
                model_identity=core_run.task8_artifact_hash,
                parameter_identity=core_row.marketable_policy_hash,
                data_identity=core_run.forecast_input_hash,
                available_at=task9_run.forecast_effective_cutoff_at,
                task10_model_available_at=training_row.finished_at,
                historical_code_available_at=code_authority.available_at,
            )
            candidates.append(
                S2HistoricalBindingCandidate(
                    season_id=core_run.forecast_season_id,
                    season_business_key=evidence.season_business_key,
                    farm_business_key=evidence.farm_business_key,
                    subfarm_business_key=evidence.subfarm_business_key_or_null or "",
                    variety_business_key=evidence.variety_business_key,
                    forecast_quantile=quantile,
                    horizon_days=horizon,
                    target_date=target_date,
                    forecast_cutoff_at=_aware_datetime(request.forecast_cutoff_at),
                    forecast_value_kg=core_row.model_harvested_marketable_quantity_kg,
                    forecast_authority=authority,
                    persisted_authority_references=S2PersistedAuthorityReferences(
                        core_forecast_run_id=core_run.id,
                        core_forecast_daily_row_id=core_row.id,
                        task9_run_id=task9_run.id,
                        task10_prediction_run_id=persisted_prediction_run.id,
                        label_snapshot_id=snapshot.header.snapshot_id,
                        label_row_id=None if label_row is None else label_row.id,
                        label_winner_id=None if winner_row is None else winner_row.id,
                    ),
                    authority_verification="PERSISTED",
                )
            )
    return s2_request, tuple(candidates)


def _quality_s2_row_set_hash(rows: Sequence[Any]) -> str:
    return hashlib.sha256(
        canonical_json_dumps({"row_hashes": sorted(row.row_hash for row in rows)}).encode("utf-8")
    ).hexdigest()


def _quality_s3_rows(s2: Any) -> tuple[S3BindingRow, ...]:
    result: list[S3BindingRow] = []
    for row in s2.rows:
        actual = row.actual_label
        result.append(
            S3BindingRow(
                forecast_business_key=row.binding_key_hash,
                actual_physical_key=(None if actual is None else actual.label_row_identity_hash),
                stable_actual_identity=(None if actual is None else actual.label_row_identity_hash),
                forecast_value_kg=Decimal(row.forecast_value_kg),
                actual_value_kg=(
                    None if row.actual_value_kg is None else Decimal(row.actual_value_kg)
                ),
                forecast_quantile=SupportedQuantile(row.forecast_quantile),
                forecast_horizon_days=row.horizon_days,
                forecast_target_date=row.target_date,
                forecast_cutoff_at=_aware_datetime(row.forecast_cutoff_at),
                s2_status=row.row_status,
                season_business_key=row.season_business_key,
                farm_business_key=row.farm_business_key,
                subfarm_business_key=row.subfarm_business_key,
                variety_business_key=row.variety_business_key,
                model_identity=row.forecast_authority.model_identity,
                actual_visibility_timestamp=(
                    None if actual is None else _aware_datetime(actual.visibility_timestamp)
                ),
            )
        )
    return tuple(result)


def _quality_snapshot_source_rows(snapshot: Any, cutoff: datetime) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    for row in snapshot.label_rows:
        rows.append(
            {
                "target_date": row["harvest_business_date"],
                "farm_business_key": row["farm_business_key"],
                "subfarm_business_key": row["subfarm_business_key"],
                "variety_business_key": row["variety_business_key"],
                "actual_value_kg": Decimal(str(row["exact_decimal_quantity_sum_kg"])),
                "physical_key": row["label_row_hash"],
                "source_kind": "FARM_PICK",
                "visibility_timestamp": cutoff,
            }
        )
    return tuple(rows)


async def _build_quality_calculation_inputs(
    session: AsyncSession,
    *,
    request: TrialQualityReportCreateRequest,
    evidence: TrialForecastEvidence,
    persisted: Any,
    s2: Any,
    snapshot: Any,
) -> tuple[
    S3EvaluationInput,
    tuple[DailyMetricResult, ...],
    tuple[dict[str, object], ...],
    tuple[BaselinePersistenceRecord, ...],
    tuple[Any, ...],
]:
    row_set_hash = _quality_s2_row_set_hash(s2.rows)
    evaluation_input = S3EvaluationInput(
        rows=_quality_s3_rows(s2),
        s2_run_identity=s2.instance_hash,
        s2_manifest_identity=s2.manifest_hash,
        s2_binding_row_set_hash=row_set_hash,
        metric_policy_version=FrozenVersion.METRIC_INPUT_MASK_V1,
        baseline_policy_version=FrozenVersion.NAIVE_BASELINE_POLICY_V1,
    )
    season = await session.get(Season, persisted.run.forecast_season_id)
    if season is None:
        raise _quality_error(TrialApiErrorCode.QUALITY_AUTHORITY_UNAVAILABLE, status_code=503)
    label_cutoff = _aware_datetime(request.label_observation_cutoff_at)
    source_rows = _quality_snapshot_source_rows(snapshot, label_cutoff)
    metric_results: list[DailyMetricResult] = []
    breakdown_results: list[dict[str, object]] = []
    baseline_records: list[BaselinePersistenceRecord] = []
    comparison_records: list[Any] = []
    for horizon in request.requested_horizons_days:
        spec = BreakdownSpec(
            forecast_horizon_days=horizon,
            farm_business_key=evidence.farm_business_key,
            subfarm_business_key=evidence.subfarm_business_key_or_null or "",
            variety_business_key=evidence.variety_business_key,
            season_business_key=evidence.season_business_key,
            model_identity=next(
                row.forecast_authority.model_identity
                for row in s2.rows
                if row.horizon_days == horizon and row.forecast_quantile == "P50"
            ),
        )
        metric = compute_daily_metrics(evaluation_input, spec)
        metric_results.append(metric)
        breakdown_results.extend(calculate_breakdown_cells(evaluation_input.rows, spec))
        p50_row = next(
            row for row in s2.rows if row.horizon_days == horizon and row.forecast_quantile == "P50"
        )
        baseline_request = BaselineRequest(
            current_target_date=p50_row.target_date,
            current_season_start=season.start_date,
            current_season_end=season.end_date,
            prior_season_start=season.start_date - timedelta(days=365),
            prior_season_end=season.end_date - timedelta(days=365),
            prior_season_identity=f"{season.code}-prior",
            current_forecast_cutoff_at=_aware_datetime(request.forecast_cutoff_at),
            farm_business_key=evidence.farm_business_key,
            subfarm_business_key=evidence.subfarm_business_key_or_null or "",
            variety_business_key=evidence.variety_business_key,
            requested_quantile="P50",
            metric_policy_version=FrozenVersion.METRIC_INPUT_MASK_V1,
            baseline_policy_version=FrozenVersion.NAIVE_BASELINE_POLICY_V1,
        )
        baseline_snapshot = BaselineSourceSnapshot(
            source_snapshot_identity=snapshot.header.snapshot_instance_identity_hash,
            source_snapshot_hash=snapshot.header.label_snapshot_hash,
            source_row_set_hash=snapshot.header.label_row_set_hash,
            visibility_manifest_hash=snapshot.header.winner_manifest_hash,
            visibility_cutoff_at=label_cutoff,
            season_analog_mapping_policy_version=FrozenVersion.SEASON_ANALOG_MAPPING_V1,
            actual_rows=source_rows,
        )
        baseline_result = resolve_baseline_point_forecast(baseline_request, baseline_snapshot)
        baseline_records.append(
            BaselinePersistenceRecord(
                request=baseline_request,
                snapshot=baseline_snapshot,
                result=baseline_result,
            )
        )
        comparison_records.extend(
            compute_model_baseline_comparisons(
                evaluation_input=evaluation_input,
                breakdown_spec=spec,
                baseline_records=(
                    ComparisonBaselineRecord(
                        request=baseline_request,
                        snapshot=baseline_snapshot,
                        result=baseline_result,
                    ),
                ),
            )
        )
    return (
        evaluation_input,
        tuple(metric_results),
        tuple(breakdown_results),
        tuple(baseline_records),
        tuple(comparison_records),
    )


async def _create_quality_report(
    session: AsyncSession,
    *,
    request: TrialQualityReportCreateRequest,
    actor: ActualHarvestActorContext,
    clock: Clock,
) -> TrialQualityReportResponse:
    del clock
    request_identity = _quality_request_identity(request, actor_identity=actor.identity)
    try:
        replay = await session.run_sync(
            lambda sync_session: resolve_trial_quality_request_replay(
                sync_session,
                schema_version=ROUND_C_PERSISTENCE_SCHEMA_VERSION,
                actor_identity=actor.identity,
                request_idempotency_key=request.request_idempotency_key,
                canonical_request=cast(Mapping[str, object], request_identity["canonical_request"]),
            )
        )
    except ForecastQualityConflictError as error:
        raise TrialApiError(
            TrialApiErrorCode.CONFLICTING_REPLAY,
            status_code=409,
            message="Request conflicts with an existing replay.",
        ) from error
    except (ForecastQualityPartialResultError, ForecastQualityContractError) as error:
        raise _quality_error(TrialApiErrorCode.EVIDENCE_CONFLICT, status_code=409) from error
    except ForecastQualityPersistenceError as error:
        raise _quality_error(
            TrialApiErrorCode.QUALITY_PERSISTENCE_UNAVAILABLE,
            status_code=503,
            retryable=True,
        ) from error
    if replay is not None:
        try:
            binding = await authorize_trial_resource(
                session,
                resource_kind=TrialResourceKind.QUALITY_REPORT,
                public_resource_id=replay.evaluation_instance_hash,
                owner_identity=actor.identity,
            )
        except TrialResourceNotFoundError as error:
            raise _quality_error(TrialApiErrorCode.EVIDENCE_CONFLICT, status_code=409) from error
        if (
            binding.parent_forecast_public_id_or_null != request.forecast_run_id
            or binding.parent_import_id_or_null != request.actual_harvest_import_id
        ):
            raise TrialApiError(
                TrialApiErrorCode.CONFLICTING_REPLAY,
                status_code=409,
                message="Request conflicts with an existing replay.",
            )
        read_model = await _load_quality_read_model(session, replay.evaluation_instance_hash, actor)
        return await _project_quality_report(session, read_model, actor)
    evidence, persisted, import_batch = await _load_quality_parent_forecast(
        session,
        request=request,
        actor=actor,
    )
    snapshot = await _create_quality_label_snapshot(
        session,
        request=request,
        actor=actor,
        evidence=evidence,
        persisted=persisted,
        import_batch=import_batch,
    )
    s2_request, candidates = await _build_quality_s2_candidates(
        session,
        request=request,
        evidence=evidence,
        persisted=persisted,
        snapshot=snapshot,
    )
    try:
        s2_run = await run_s2_historical_binding(
            session,
            request=s2_request,
            candidates=candidates,
        )
        s2 = await load_s2_historical_binding_by_instance_hash(
            session,
            instance_hash=s2_run.instance_hash,
        )
        (
            evaluation_input,
            metric_results,
            breakdown_results,
            baseline_records,
            comparison_records,
        ) = await _build_quality_calculation_inputs(
            session,
            request=request,
            evidence=evidence,
            persisted=persisted,
            s2=s2,
            snapshot=snapshot,
        )
        status_evidence: tuple[QualityStatusEvidenceCell, ...] = (
            build_frozen_quality_status_evidence(
                requested_horizons_days=request.requested_horizons_days,
                rows=evaluation_input.rows,
                source_s2_run_identity=evaluation_input.s2_run_identity,
                source_s2_manifest_identity=evaluation_input.s2_manifest_identity,
                source_s2_binding_row_set_hash=evaluation_input.s2_binding_row_set_hash,
            )
        )
        request_identity = _quality_request_identity(
            request,
            actor_identity=actor.identity,
            server_owned_evidence={
                "label_snapshot_identity": snapshot.header.snapshot_instance_identity_hash,
                "label_snapshot_hash": snapshot.header.label_snapshot_hash,
                "s2_instance_hash": s2.instance_hash,
                "s2_manifest_hash": s2.manifest_hash,
            },
        )
        persisted_quality = await session.run_sync(
            lambda sync_session: persist_quality_evaluation(
                sync_session,
                evaluation_input=evaluation_input,
                metric_results=metric_results,
                status_evidence=status_evidence,
                breakdown_results=breakdown_results,
                baseline_records=baseline_records,
                comparison_records=comparison_records,
                manifest_payload={},
                comparison_contract_enabled=True,
                request_identity_payload=request_identity,
            )
        )
        await create_quality_binding_in_result_boundary(
            session,
            public_quality_report_id=persisted_quality.evaluation_instance_hash,
            owner_identity=actor.identity,
            business_scope_hash=evidence.business_scope_hash,
            parent_forecast_public_id=request.forecast_run_id,
            parent_import_id=request.actual_harvest_import_id,
        )
        await session.flush()
    except TrialResourceNotFoundError as error:
        raise _resource_not_found() from error
    except (ForecastQualityConflictError, TrialResourceBindingError) as error:
        raise TrialApiError(
            TrialApiErrorCode.CONFLICTING_REPLAY,
            status_code=409,
            message="Request conflicts with an existing replay.",
        ) from error
    except (ForecastQualityPartialResultError, ForecastQualityContractError) as error:
        raise _quality_error(TrialApiErrorCode.EVIDENCE_CONFLICT, status_code=409) from error
    except ForecastQualityPersistenceError as error:
        raise _quality_error(
            TrialApiErrorCode.QUALITY_PERSISTENCE_UNAVAILABLE,
            status_code=503,
            retryable=True,
        ) from error
    except (RollingBacktestCanonicalParityError, ValueError) as error:
        raise _quality_error(
            TrialApiErrorCode.QUALITY_AUTHORITY_UNAVAILABLE,
            status_code=503,
            retryable=True,
        ) from error
    read_model = await _load_quality_read_model(
        session,
        persisted_quality.evaluation_instance_hash,
        actor,
    )
    return await _project_quality_report(session, read_model, actor)


async def _load_quality_read_model(
    session: AsyncSession,
    report_id: str,
    actor: ActualHarvestActorContext,
) -> _QualityReadContext:
    if re.fullmatch(r"[0-9a-f]{64}", report_id) is None:
        raise _resource_not_found()
    try:
        binding = await authorize_trial_resource(
            session,
            resource_kind=TrialResourceKind.QUALITY_REPORT,
            public_resource_id=report_id,
            owner_identity=actor.identity,
        )
    except TrialResourceNotFoundError as error:
        raise _resource_not_found() from error
    try:
        quality = await session.run_sync(
            lambda sync_session: load_quality_evaluation_by_instance_hash(
                sync_session,
                evaluation_instance_hash=report_id,
            )
        )
    except (ForecastQualityPartialResultError, ForecastQualityContractError) as error:
        raise _quality_error(TrialApiErrorCode.EVIDENCE_CONFLICT, status_code=409) from error
    run_identity = quality.run_payload.get("trial_request_identity")
    if not isinstance(run_identity, Mapping):
        raise _quality_error(TrialApiErrorCode.EVIDENCE_CONFLICT, status_code=409)
    canonical_request = run_identity.get("canonical_request")
    if not isinstance(canonical_request, Mapping):
        raise _quality_error(TrialApiErrorCode.EVIDENCE_CONFLICT, status_code=409)
    parent_forecast_id = canonical_request.get("forecast_run_id")
    parent_import_id = canonical_request.get("actual_harvest_import_id")
    s2_identity = quality.run_payload.get("s2_run_identity")
    if (
        not isinstance(parent_forecast_id, str)
        or not isinstance(parent_import_id, str)
        or not isinstance(s2_identity, str)
        or binding.parent_forecast_public_id_or_null != parent_forecast_id
        or binding.parent_import_id_or_null != parent_import_id
    ):
        raise _quality_error(TrialApiErrorCode.EVIDENCE_CONFLICT, status_code=409)
    try:
        s2 = await load_s2_historical_binding_by_instance_hash(
            session,
            instance_hash=s2_identity,
        )
        forecast_evidence = await authorize_and_load_forecast_evidence(
            session,
            public_forecast_id=parent_forecast_id,
            owner_identity=actor.identity,
        )
    except (TrialForecastEvidenceNotFoundError, TrialResourceNotFoundError) as error:
        raise _resource_not_found() from error
    except (TrialForecastEvidenceIntegrityError, TrialForecastEvidenceConflictError) as error:
        raise _quality_error(TrialApiErrorCode.EVIDENCE_CONFLICT, status_code=409) from error
    except RollingBacktestCanonicalParityError as error:
        raise _quality_error(TrialApiErrorCode.EVIDENCE_CONFLICT, status_code=409) from error
    except ForecastQualityPartialResultError as error:
        raise _quality_error(TrialApiErrorCode.EVIDENCE_CONFLICT, status_code=409) from error
    except ForecastQualityPersistenceError as error:
        raise _quality_error(
            TrialApiErrorCode.QUALITY_PERSISTENCE_UNAVAILABLE,
            status_code=503,
            retryable=True,
        ) from error
    if binding.business_scope_hash != forecast_evidence.business_scope_hash:
        raise _quality_error(TrialApiErrorCode.EVIDENCE_CONFLICT, status_code=409)
    return _QualityReadContext(
        quality=quality,
        s2=s2,
        forecast_evidence=forecast_evidence,
        parent_forecast_public_id=parent_forecast_id,
        parent_import_id=parent_import_id,
    )


def _quality_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value)).quantize(Decimal("0.000001"))


def _quality_metric_from_cell(
    payload: Mapping[str, object], *, name: str | None = None
) -> TrialQualityMetric:
    cell = payload.get("metric_cell")
    if not isinstance(cell, Mapping):
        raise _quality_error(TrialApiErrorCode.EVIDENCE_CONFLICT, status_code=409)
    reason = str(cell.get("reason_code", "EVIDENCE_CONFLICT"))
    return TrialQualityMetric(
        metric_name=name or str(cell.get("metric_name", "")),
        metric_status=str(cell.get("metric_status", "NOT_COMPUTABLE")),
        metric_value_or_null=_quality_decimal(cell.get("metric_value")),
        numerator_or_null=_quality_decimal(cell.get("numerator")),
        denominator_or_null=_quality_decimal(cell.get("denominator")),
        reason_codes=(reason,),
    )


def _quality_overlay_rows(
    rows: Sequence[Any],
    *,
    horizon: int,
) -> tuple[TrialQualityDailyOverlayRow, ...]:
    grouped: dict[date, list[Any]] = {}
    for row in rows:
        if row.horizon_days == horizon:
            grouped.setdefault(row.target_date, []).append(row)
    output: list[TrialQualityDailyOverlayRow] = []
    for target_date in sorted(grouped):
        values = grouped[target_date]
        by_quantile = {row.forecast_quantile: row for row in values}
        if set(by_quantile) != {"P50", "P80", "P90"} or len(by_quantile) != len(values):
            raise _quality_error(TrialApiErrorCode.EVIDENCE_CONFLICT, status_code=409)
        p50, p80, p90 = (by_quantile[name] for name in ("P50", "P80", "P90"))
        actuals = {row.actual_value_kg for row in values}
        statuses = {row.row_status for row in values}
        reasons = tuple(sorted({str(row.reason_code) for row in values if row.reason_code}))
        if len(actuals) != 1 or len(statuses) != 1:
            raise _quality_error(TrialApiErrorCode.EVIDENCE_CONFLICT, status_code=409)
        status = next(iter(statuses))
        if status == "COMPARABLE":
            coverage_state = "AVAILABLE"
        elif status == "EXCLUDED":
            coverage_state = "EXCLUDED"
        else:
            coverage_state = "NOT_COMPUTABLE"
        output.append(
            TrialQualityDailyOverlayRow(
                business_date=target_date,
                forecast_p50_kg_or_null=_quality_decimal(p50.forecast_value_kg),
                forecast_p80_kg_or_null=_quality_decimal(p80.forecast_value_kg),
                forecast_p90_kg_or_null=_quality_decimal(p90.forecast_value_kg),
                actual_quantity_kg_or_null=_quality_decimal(next(iter(actuals))),
                actual_available=status == "COMPARABLE",
                coverage_state=coverage_state,
                exclusion_reason_codes=reasons,
            )
        )
    return tuple(output)


def _quality_status_payload(
    metric_payloads: Sequence[Mapping[str, object]],
    *,
    metric_name: str,
    horizon: int,
    quantile: str,
) -> Mapping[str, object]:
    matches = []
    for payload in metric_payloads:
        status = payload.get("status_evidence")
        if not isinstance(status, Mapping):
            continue
        if (
            status.get("metric_name") == metric_name
            and status.get("forecast_horizon_days") == horizon
            and status.get("forecast_quantile") == quantile
        ):
            matches.append(status)
    if len(matches) != 1:
        raise _quality_error(TrialApiErrorCode.EVIDENCE_CONFLICT, status_code=409)
    return matches[0]


def _quality_status_reason(payload: Mapping[str, object]) -> tuple[str, ...]:
    reason = payload.get("reason_code")
    return () if reason in (None, "") else (str(reason),)


def _quality_status_coverage(
    metric_payloads: Sequence[Mapping[str, object]],
    *,
    horizon: int,
    quantile: Literal["P80", "P90"],
) -> TrialQualityCoverageMetric:
    payload = _quality_status_payload(
        metric_payloads,
        metric_name=f"{quantile.lower()}_upper_coverage",
        horizon=horizon,
        quantile=quantile,
    )
    candidate_count = payload.get("candidate_row_count_or_null")
    if (
        not isinstance(candidate_count, int)
        or isinstance(candidate_count, bool)
        or candidate_count < 0
    ):
        raise _quality_error(TrialApiErrorCode.EVIDENCE_CONFLICT, status_code=409)
    return TrialQualityCoverageMetric(
        quantile=quantile,
        forecast_horizon_days=horizon,
        metric_status=str(payload.get("metric_status", "")),
        covered_count_or_null=None,
        total_count=candidate_count,
        coverage_ratio_or_null=None,
        reason_codes=_quality_status_reason(payload),
    )


def _quality_status_peak(
    metric_payloads: Sequence[Mapping[str, object]],
    *,
    metric_name: str,
    horizon: int,
    quantile: Literal["P50", "P80", "P90"],
) -> TrialQualityPeakMetric:
    payload = _quality_status_payload(
        metric_payloads,
        metric_name=metric_name,
        horizon=horizon,
        quantile=quantile,
    )
    return TrialQualityPeakMetric(
        quantile=quantile,
        forecast_horizon_days=horizon,
        metric_status=str(payload.get("metric_status", "")),
        metric_value_or_null=_quality_decimal(payload.get("metric_value")),
        business_date_or_null=(
            None
            if payload.get("business_date_or_null") is None
            else date.fromisoformat(str(payload["business_date_or_null"]))
        ),
        window_start_date_or_null=(
            None
            if payload.get("window_start_date_or_null") is None
            else date.fromisoformat(str(payload["window_start_date_or_null"]))
        ),
        window_end_date_or_null=(
            None
            if payload.get("window_end_date_or_null") is None
            else date.fromisoformat(str(payload["window_end_date_or_null"]))
        ),
        reason_codes=_quality_status_reason(payload),
    )


def _quality_status_interval(
    metric_payloads: Sequence[Mapping[str, object]],
    *,
    horizon: int,
    quantile: Literal["P80", "P90"],
) -> TrialQualityIntervalMetric:
    payload = _quality_status_payload(
        metric_payloads,
        metric_name="prediction_interval",
        horizon=horizon,
        quantile=quantile,
    )
    lower_available = payload.get("lower_bound_available_or_null")
    if not isinstance(lower_available, bool):
        raise _quality_error(TrialApiErrorCode.EVIDENCE_CONFLICT, status_code=409)
    return TrialQualityIntervalMetric(
        quantile=quantile,
        forecast_horizon_days=horizon,
        metric_status=str(payload.get("metric_status", "")),
        lower_bound_available=lower_available,
        lower_bound_value_or_null=_quality_decimal(payload.get("lower_bound_value_or_null")),
        upper_bound_value_or_null=_quality_decimal(payload.get("upper_bound_value_or_null")),
        metric_value_or_null=_quality_decimal(payload.get("metric_value")),
        reason_codes=_quality_status_reason(payload),
    )


async def _project_quality_report(
    session: AsyncSession,
    context: _QualityReadContext,
    actor: ActualHarvestActorContext,
) -> TrialQualityReportResponse:
    del session, actor
    quality = context.quality
    s2 = context.s2
    run_identity = quality.run_payload["trial_request_identity"]
    request_payload = run_identity["canonical_request"]
    server_owned = run_identity.get("server_owned_evidence", {})
    if not isinstance(server_owned, Mapping):
        server_owned = {}
    overlays: list[TrialQualityHorizonMetrics] = []
    metric_payloads = quality.metrics
    for horizon in (7, 14, 21):
        overlay = _quality_overlay_rows(s2.rows, horizon=horizon)
        metrics: list[TrialQualityMetric] = []
        for payload in metric_payloads:
            daily = payload.get("daily_metric_result")
            if (
                isinstance(daily, Mapping)
                and daily.get("breakdown_identity", {}).get("forecast_horizon_days") == horizon
            ):
                metrics.append(_quality_metric_from_cell(payload))
        cumulative = next(
            (item for item in metrics if item.metric_name == "daily_absolute_error_sum_kg"),
            TrialQualityMetric(
                metric_name="cumulative_error",
                metric_status="NOT_COMPUTABLE",
                metric_value_or_null=None,
                numerator_or_null=None,
                denominator_or_null=None,
                reason_codes=("NO_S2_BINDING_ROWS",),
            ),
        )
        if cumulative.metric_name != "cumulative_error":
            cumulative = cumulative.model_copy(update={"metric_name": "cumulative_error"})
        coverage_p80 = _quality_status_coverage(metric_payloads, horizon=horizon, quantile="P80")
        coverage_p90 = _quality_status_coverage(metric_payloads, horizon=horizon, quantile="P90")
        single_day_peaks = tuple(
            _quality_status_peak(
                metric_payloads,
                metric_name="single_day_peak",
                horizon=horizon,
                quantile=quantile,
            )
            for quantile in cast(tuple[Literal["P50", "P80", "P90"], ...], ("P50", "P80", "P90"))
        )
        sustained_peaks = tuple(
            _quality_status_peak(
                metric_payloads,
                metric_name="sustained_seven_day_peak",
                horizon=horizon,
                quantile=quantile,
            )
            for quantile in cast(tuple[Literal["P50", "P80", "P90"], ...], ("P50", "P80", "P90"))
        )
        interval_metrics = tuple(
            _quality_status_interval(metric_payloads, horizon=horizon, quantile=quantile)
            for quantile in cast(tuple[Literal["P80", "P90"], ...], ("P80", "P90"))
        )
        overlays.append(
            TrialQualityHorizonMetrics(
                horizon_days=horizon,
                daily_overlay=overlay,
                daily_metrics=tuple(metrics),
                cumulative_metric=cumulative,
                single_day_peak=single_day_peaks[0],
                sustained_seven_day_peak=sustained_peaks[0],
                p80_coverage=coverage_p80,
                p90_coverage=coverage_p90,
                interval_metric=interval_metrics[0],
                coverage_counts={
                    "total": len(overlay),
                    "covered": sum(item.actual_available for item in overlay),
                },
                excluded_row_counts={
                    "total": len(overlay),
                    "excluded": sum(item.coverage_state == "EXCLUDED" for item in overlay),
                    "not_computable": sum(
                        item.coverage_state == "NOT_COMPUTABLE" for item in overlay
                    ),
                },
                single_day_peaks=single_day_peaks,
                sustained_seven_day_peaks=sustained_peaks,
                interval_metrics=interval_metrics,
            )
        )
    first_row = s2.rows[0]
    label_snapshot_identity = server_owned.get("label_snapshot_identity")
    if not isinstance(label_snapshot_identity, str) or not label_snapshot_identity:
        raise _quality_error(TrialApiErrorCode.EVIDENCE_CONFLICT, status_code=409)
    model_identity = first_row.forecast_authority.model_identity
    if not isinstance(model_identity, str) or not model_identity.strip():
        raise _quality_error(TrialApiErrorCode.EVIDENCE_CONFLICT, status_code=409)
    identity = TrialQualityEvidenceIdentity(
        forecast_run_id=context.parent_forecast_public_id,
        actual_harvest_import_id=context.parent_import_id,
        actual_label_snapshot_identity=label_snapshot_identity,
        s2_run_identity=str(quality.run_payload["s2_run_identity"]),
        s2_manifest_identity=str(quality.run_payload["s2_manifest_identity"]),
        s2_binding_row_set_hash=str(quality.run_payload["s2_binding_row_set_hash"]),
        evaluation_request_hash=quality.evaluation_request_hash,
        evaluation_instance_hash=quality.evaluation_instance_hash,
        quality_manifest_hash=hashlib.sha256(
            canonical_json_dumps(quality.manifest_payload).encode("utf-8")
        ).hexdigest(),
        metric_result_set_hash=str(quality.manifest_payload["metric_result_set_hash"]),
        breakdown_result_set_hash=str(quality.manifest_payload["breakdown_result_set_hash"]),
        baseline_result_set_hash=str(quality.manifest_payload["baseline_result_set_hash"]),
        comparison_result_set_hash=str(quality.manifest_payload["comparison_result_set_hash"]),
        metric_policy_version=str(quality.run_payload["metric_policy_version"]),
        baseline_policy_version=str(quality.run_payload["baseline_policy_version"]),
        comparison_policy_version_or_null=quality.run_payload.get("comparison_policy_version"),
        model_identity=model_identity,
    )
    top = overlays[0]
    all_reasons = tuple(
        sorted(
            {
                reason
                for horizon in overlays
                for reason in horizon.reason_codes
                + tuple(
                    code for row in horizon.daily_overlay for code in row.exclusion_reason_codes
                )
            }
        )
    )
    return TrialQualityReportResponse(
        report_id=quality.evaluation_instance_hash,
        forecast_identity=identity,
        actual_label_snapshot_identity=identity.actual_label_snapshot_identity,
        forecast_cutoff_at=_aware_datetime(
            datetime.fromisoformat(str(request_payload["forecast_cutoff_at"]))
        ),
        label_observation_cutoff_at=_aware_datetime(
            datetime.fromisoformat(str(request_payload["label_observation_cutoff_at"]))
        ),
        requested_horizons_days=tuple(request_payload["requested_horizons_days"]),
        horizons=tuple(overlays),
        daily_metrics=top.daily_metrics,
        cumulative_error=top.cumulative_metric,
        single_day_peak=top.single_day_peak,
        sustained_seven_day_peak=top.sustained_seven_day_peak,
        p80_coverage=top.p80_coverage,
        p90_coverage=top.p90_coverage,
        interval_metric=top.interval_metric,
        breakdowns=tuple(
            TrialQualityBreakdown(
                breakdown_identity=TrialQualityBreakdownIdentity.model_validate(
                    dict(payload.get("cell_identity", {}))
                ),
                metric_status=str(payload.get("metric_status", "NOT_COMPUTABLE")),
                coverage_ratio_or_null=_quality_decimal(payload.get("coverage_ratio")),
                comparable_row_count=int(payload.get("s2_comparable_row_count", 0)),
                excluded_row_count=int(payload.get("s2_excluded_row_count", 0)),
                not_computable_row_count=int(payload.get("s2_not_computable_row_count", 0)),
                metric_values=TrialQualityMetricValues.model_validate(
                    {
                        str(key): _quality_decimal(value)
                        for key, value in dict(payload.get("metric_values", {})).items()
                    }
                ),
                reason_codes=(str(payload.get("reason_code", "")),),
            )
            for payload in quality.breakdowns
        ),
        naive_baseline_results=tuple(
            TrialQualityBaselineResult(
                baseline_quantile=str(payload.get("result", {}).get("baseline_quantile", "P50")),
                metric_status=str(payload.get("result", {}).get("metric_status", "NOT_COMPUTABLE")),
                baseline_value_kg_or_null=_quality_decimal(
                    payload.get("result", {}).get("baseline_point_forecast_kg")
                ),
                comparison_availability=str(
                    payload.get("result", {}).get("comparison_availability", "BLOCKED")
                ),
                analog_date_or_null=(
                    None
                    if payload.get("result", {}).get("analog_date") is None
                    else date.fromisoformat(str(payload["result"]["analog_date"]))
                ),
                reason_codes=(str(payload.get("result", {}).get("reason_code", "")),),
            )
            for payload in quality.baselines
        ),
        computability_status="COMPUTED"
        if any(item.coverage_state == "AVAILABLE" for item in top.daily_overlay)
        else "NOT_COMPUTABLE",
        reason_codes=all_reasons,
        coverage_counts=top.coverage_counts,
        excluded_row_counts=top.excluded_row_counts,
    )


def _project_quality_comparison(
    context: _QualityReadContext,
) -> TrialQualityComparisonResponse:
    quality = context.quality
    deltas: list[TrialQualityComparisonDelta] = []
    for payload in quality.comparisons:
        identity = payload.get("normalized_breakdown_identity", {})
        deltas.append(
            TrialQualityComparisonDelta(
                comparison_name=str(payload.get("comparison_name", "")),
                comparison_availability=str(payload.get("comparison_availability", "BLOCKED")),
                metric_status=str(payload.get("metric_status", "NOT_COMPUTABLE")),
                model_value_or_null=_quality_decimal(payload.get("model_value")),
                baseline_value_or_null=_quality_decimal(payload.get("baseline_value")),
                delta_value_or_null=_quality_decimal(payload.get("delta_value")),
                forecast_horizon_days=int(
                    str(
                        payload.get(
                            "forecast_horizon_days",
                            identity.get("forecast_horizon_days", 0),
                        )
                    )
                ),
                common_comparable_row_count=int(payload.get("common_comparable_row_count", 0)),
                model_only_row_count=int(payload.get("model_only_row_count", 0)),
                baseline_only_row_count=int(payload.get("baseline_only_row_count", 0)),
                excluded_row_count=int(payload.get("excluded_row_count", 0)),
                not_computable_row_count=int(payload.get("not_computable_row_count", 0)),
                reason_codes=(str(payload.get("reason_code", "")),),
                baseline_member_set_hash=str(payload.get("baseline_member_set_hash", "")),
                comparison_key_hash=str(payload.get("comparison_key_hash", "")),
                canonical_hash=hashlib.sha256(
                    canonical_json_dumps(payload).encode("utf-8")
                ).hexdigest(),
            )
        )
    manifest = quality.manifest_payload
    return TrialQualityComparisonResponse(
        report_id=quality.evaluation_instance_hash,
        comparison_availability="AVAILABLE" if deltas else "BLOCKED",
        comparison_status="COMPUTED" if deltas else "NOT_COMPUTABLE",
        comparison_policy_version=str(
            quality.run_payload.get("comparison_policy_version", "v0.2-s3-comparison-policy-v1")
        ),
        model_baseline_deltas=tuple(deltas),
        reason_codes=() if deltas else ("NO_COMPARISON_ROWS",),
        comparison_public_hash=str(manifest["comparison_result_set_hash"]),
    )


def _project_quality_csv(report: TrialQualityReportResponse) -> TrialCsvDocument:
    rows: list[tuple[object, ...]] = []
    type_order = {"OVERLAY": 0, "METRIC": 1, "PEAK": 2, "COVERAGE": 3, "INTERVAL": 4}
    for horizon in report.horizons:
        for overlay in horizon.daily_overlay:
            for quantile, value in (
                ("P50", overlay.forecast_p50_kg_or_null),
                ("P80", overlay.forecast_p80_kg_or_null),
                ("P90", overlay.forecast_p90_kg_or_null),
            ):
                rows.append(
                    (
                        "OVERLAY",
                        horizon.horizon_days,
                        overlay.business_date,
                        "",
                        quantile,
                        value,
                        overlay.actual_quantity_kg_or_null,
                        overlay.coverage_state,
                        None,
                        None,
                        None,
                        overlay.coverage_state,
                        "|".join(sorted(overlay.exclusion_reason_codes)),
                    )
                )
        for metric in horizon.daily_metrics + (horizon.cumulative_metric,):
            rows.append(
                (
                    "METRIC",
                    horizon.horizon_days,
                    None,
                    metric.metric_name,
                    "",
                    None,
                    None,
                    None,
                    metric.metric_value_or_null,
                    metric.numerator_or_null,
                    metric.denominator_or_null,
                    None,
                    "|".join(sorted(metric.reason_codes)),
                )
            )
        for name, peak_metrics in (
            ("single_day_peak", horizon.single_day_peaks),
            ("sustained_seven_day_peak", horizon.sustained_seven_day_peaks),
        ):
            for peak_metric in peak_metrics:
                rows.append(
                    (
                        "PEAK",
                        horizon.horizon_days,
                        peak_metric.business_date_or_null,
                        name,
                        peak_metric.quantile,
                        None,
                        None,
                        peak_metric.metric_status,
                        peak_metric.metric_value_or_null,
                        None,
                        None,
                        None,
                        "|".join(sorted(peak_metric.reason_codes)),
                    )
                )
        for coverage in (horizon.p80_coverage, horizon.p90_coverage):
            rows.append(
                (
                    "COVERAGE",
                    horizon.horizon_days,
                    None,
                    "",
                    coverage.quantile,
                    None,
                    None,
                    coverage.metric_status,
                    coverage.coverage_ratio_or_null,
                    coverage.covered_count_or_null,
                    coverage.total_count,
                    coverage.metric_status,
                    "|".join(sorted(coverage.reason_codes)),
                )
            )
        for interval in horizon.interval_metrics:
            rows.append(
                (
                    "INTERVAL",
                    horizon.horizon_days,
                    None,
                    "prediction_interval",
                    interval.quantile,
                    None,
                    None,
                    interval.metric_status,
                    interval.metric_value_or_null,
                    None,
                    None,
                    None,
                    "|".join(sorted(interval.reason_codes)),
                )
            )
    rows.sort(
        key=lambda row: (
            type_order[str(row[0])],
            int(str(row[1])),
            row[2] or date.min,
            str(row[3]),
            {"P50": 0, "P80": 1, "P90": 2, "": 3}.get(str(row[4]), 4),
        )
    )
    return TrialCsvDocument(
        filename=f"{report.report_id}.csv",
        content=serialize_csv(
            (
                "record_type",
                "horizon_days",
                "business_date",
                "metric_name",
                "quantile",
                "forecast_value_kg",
                "actual_quantity_kg",
                "metric_status",
                "metric_value",
                "numerator",
                "denominator",
                "coverage_state",
                "reason_codes",
            ),
            rows,
        ),
    )


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
    if not rows or p50 is None or last_p50 is None:
        raise _evidence_conflict()
    first_row = rows[0]
    policy_version = first_row.marketable_policy_version
    policy_hash = first_row.marketable_policy_hash
    if not isinstance(policy_version, str) or not policy_version.strip():
        raise _evidence_conflict()
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
        single_day_peak=TrialForecastSingleDayPeakResponse(
            date=p50.single_day_peak.date,
            quantity_kg=Decimal(p50.single_day_peak.quantity_kg),
            tie_break=p50.single_day_peak.tie_break,
        ),
        sustained_seven_day_peak=TrialForecastSustainedSevenDayPeakResponse(
            start_date=p50.sustained_7day_peak.start_date,
            end_date=p50.sustained_7day_peak.end_date,
            cumulative_quantity_kg=Decimal(p50.sustained_7day_peak.cumulative_quantity_kg),
            daily_average_kg_per_day=Decimal(p50.sustained_7day_peak.daily_average_kg_per_day),
            window_days=p50.sustained_7day_peak.window_days,
            metric=p50.sustained_7day_peak.metric,
            date_continuity=p50.sustained_7day_peak.date_continuity,
            tie_break=p50.sustained_7day_peak.tie_break,
        ),
        season_cumulative_quantity=(
            Decimal(p50.season_cumulative_effective_marketable_kg) if p50 is not None else None
        ),
        mature_inventory_summary=TrialForecastInventorySummaryResponse(
            opening_quantity_kg=Decimal(last_p50.opening_mature_inventory_kg),
            closing_quantity_kg=Decimal(last_p50.closing_mature_inventory_kg),
        ),
        backlog_summary=TrialForecastBacklogSummaryResponse(
            quantity_kg=Decimal(last_p50.unharvested_backlog_kg),
        ),
        model_version=first_row.task8_artifact_hash,
        parameter_version=first_row.task9_result_hash,
        policy_versions=TrialForecastPolicyVersionsResponse(forecast=policy_version),
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


def _require_import_upload_scope(
    batch: ActualHarvestApiBatchSummary,
    actor: ActualHarvestActorContext,
    permission: str,
    *,
    upload_channel: ActualHarvestImportChannel,
) -> None:
    """Authorize a file transport without changing the persisted batch channel."""

    _require_import_scope(batch, actor, permission, conceal_mismatch=True)
    try:
        persisted_channel = ActualHarvestImportChannel(batch.import_channel)
    except ValueError as error:
        raise _concealed_import_scope_error() from error

    if upload_channel not in {
        ActualHarvestImportChannel.CSV,
        ActualHarvestImportChannel.XLSX,
    }:
        raise _concealed_import_scope_error()
    if (
        persisted_channel is not ActualHarvestImportChannel.API
        and persisted_channel is not upload_channel
    ):
        raise _concealed_import_scope_error()

    try:
        require_actor_scope(
            actor,
            source_system=batch.source_system,
            channel=upload_channel,
            permission=permission,
            submitted_by_identity=batch.submitted_by_identity,
            hide_identity_mismatch=True,
        )
    except ActualHarvestApiError as error:
        if error.code in {
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
    "TrialForecastSingleDayPeakResponse",
    "TrialForecastSustainedSevenDayPeakResponse",
    "TrialForecastInventorySummaryResponse",
    "TrialForecastBacklogSummaryResponse",
    "TrialForecastPolicyVersionsResponse",
    "TrialForecastInputAuthorityItem",
    "TrialForecastInputAuthorityResponse",
    "TrialForecastScope",
    "TrialForecastSummaryResponse",
    "TrialCsvExportResponse",
    "TrialQualityComparisonResponse",
    "TrialQualityComparisonDelta",
    "TrialQualityCsvExportResponse",
    "TrialQualityCoverageMetric",
    "TrialQualityDailyOverlayRow",
    "TrialQualityEvidenceIdentity",
    "TrialQualityHorizonMetrics",
    "TrialQualityIntervalMetric",
    "TrialQualityMetric",
    "TrialQualityPeakMetric",
    "TrialQualityBaselineResult",
    "TrialQualityBreakdown",
    "TrialQualityBreakdownIdentity",
    "TrialQualityMetricValues",
    "TrialQualityRowCounts",
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
