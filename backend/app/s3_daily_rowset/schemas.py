"""Pydantic schemas for S3-A daily rowset materialization."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict

EXPECTED_MATERIALIZED_DATASET_IDENTITY_SHA256 = (
    "f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785"
)
EXPECTED_DATASET_ID = "source-002"
EXPECTED_DATASET_VERSION = "e5-live-v1"
HORIZON_DAYS = frozenset({7, 14, 21})
SUSTAINED_PEAK_WINDOW_DAYS = frozenset({3, 7})


class DailyRowStatus(StrEnum):
    OBSERVED = "OBSERVED"
    UNKNOWN = "UNKNOWN"
    EXCLUDED = "EXCLUDED"


class MaterializationOutcome(StrEnum):
    SUCCESS = "SUCCESS"
    REJECTED = "REJECTED"
    CELL_EXCLUDED = "CELL_EXCLUDED"
    NOT_COMPUTABLE = "NOT_COMPUTABLE"


class ReasonCode(StrEnum):
    TARGET_DATE_CUTOFF_HORIZON_MISMATCH = "TARGET_DATE_CUTOFF_HORIZON_MISMATCH"
    WINDOW_REJECTED_UNKNOWN_OR_EXCLUDED_DAY = "WINDOW_REJECTED_UNKNOWN_OR_EXCLUDED_DAY"
    FORECAST_UNAVAILABLE = "FORECAST_UNAVAILABLE"
    TEST_PARTITION_NOT_ALLOWED = "TEST_PARTITION_NOT_ALLOWED"
    SEASON_YEAR_DERIVATION_FAILURE = "SEASON_YEAR_DERIVATION_FAILURE"
    DATASET_IDENTITY_MISMATCH = "DATASET_IDENTITY_MISMATCH"


class WindowKind(StrEnum):
    HORIZON = "HORIZON"
    COMPLETE_SEASON = "COMPLETE_SEASON"


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class DatasetIdentity(_FrozenModel):
    dataset_id: str
    dataset_version: str
    materialized_dataset_identity_sha256: str


class DatasetIdentityMismatchError(ValueError):
    """Raised when the bound S2 dataset identity does not match."""


class EvaluationInstanceCell(_FrozenModel):
    season: str
    farm: str
    subfarm: str
    variety: str
    model_id: str
    forecast_cutoff_at: datetime
    forecast_quantile: str


class HorizonWindowRequest(_FrozenModel):
    evaluation_window_days: Literal[7, 14, 21]
    forecast_target_date: date | None = None


class DailyRow(_FrozenModel):
    business_date: date
    daily_row_status: DailyRowStatus
    actual_harvest_quantity_kg: Decimal | None = None
    forecast_harvest_quantity_kg: Decimal | None = None


class DailyRowsetResult(_FrozenModel):
    outcome: MaterializationOutcome
    reason_code: ReasonCode | None = None
    window_kind: WindowKind
    evaluation_window_days: int | None = None
    window_start_date: date | None = None
    window_end_date: date | None = None
    daily_rows: tuple[DailyRow, ...] = ()
    rowset_identity_sha256: str | None = None
    sustained_peak_pass_allowed: bool = False
    current_s3_daily_rowset_completeness_verified: bool = False


class SustainedPeakPredicateResult(_FrozenModel):
    window_days: int
    predicate_defined: bool = True
    pass_allowed: bool = False
    conflict_status: Literal["UNRESOLVED"] = "UNRESOLVED"


class CompletenessPredicateId(StrEnum):
    FULL_CALENDAR_DAY_COVERAGE_IN_WINDOW = "FULL_CALENDAR_DAY_COVERAGE_IN_WINDOW"
    NO_SILENT_MISSING_DAYS = "NO_SILENT_MISSING_DAYS"
    NO_ZERO_FILL_FOR_UNKNOWN = "NO_ZERO_FILL_FOR_UNKNOWN"
    OBSERVED_KG_TRACEABLE_TO_SOURCE_002_GRAIN = "OBSERVED_KG_TRACEABLE_TO_SOURCE_002_GRAIN"
    FORECAST_DAILY_CURVE_VISIBLE_AT_CUTOFF = "FORECAST_DAILY_CURVE_VISIBLE_AT_CUTOFF"


class PredicateStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"


class CompletenessPredicateResult(_FrozenModel):
    predicate_id: CompletenessPredicateId
    status: PredicateStatus


class WindowCompletenessVerificationResult(_FrozenModel):
    window_predicates_all_pass: bool
    predicates: tuple[CompletenessPredicateResult, ...]
    dataset_completeness_verified: bool = False
    current_s3_daily_rowset_completeness_verified: bool = False
    evaluation_instance_registry_available: bool = False
    materialization_outcome: MaterializationOutcome
    rowset_identity_sha256: str | None = None
