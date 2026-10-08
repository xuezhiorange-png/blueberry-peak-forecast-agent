"""V0.17 read contracts. Decimal quantities cross the wire as exact strings."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

Capability = Literal[
    "GET_FORECAST_OVERVIEW",
    "GET_FORECAST_CURVE",
    "GET_HIERARCHICAL_FORECAST",
    "GET_FORECAST_UNCERTAINTY",
    "GET_FORECAST_ATTRIBUTION",
    "GET_FORECAST_QUALITY",
]
ReadStatus = Literal[
    "READY", "PARTIAL", "EMPTY", "NOT_AVAILABLE", "AUTHORITY_MISMATCH", "NO_CURRENT_ACTUAL", "ERROR"
]
Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Identifier = Annotated[str, Field(min_length=1, max_length=200)]
HierarchyLevel = Literal["COMPANY", "REGION", "BASE"]


class ReadModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ForecastIdentity(ReadModel):
    source_kind: Literal["OPERATIONAL_PEAK", "HIERARCHICAL"]
    forecast_family: Identifier
    run_id: int = Field(gt=0, le=9223372036854775807)
    hierarchy_level: HierarchyLevel
    entity_id: Identifier
    target_season: str = Field(pattern=r"^\d{4}-\d{4}$")
    origin_date: date
    baseline_id: Identifier
    policy_version: Identifier


class ForecastReadQuery(ForecastIdentity):
    expected_source_result_hash: Hash | None = None


class QualityReadQuery(ReadModel):
    mode: Literal["HISTORICAL_VALIDATION", "CURRENT_PRODUCTION_ACCURACY"] = "HISTORICAL_VALIDATION"
    model_id: Literal["V0_15_S5_M1_RIDGE"] = "V0_15_S5_M1_RIDGE"
    expected_source_result_hash: Hash | None = None


class HierarchyIdentity(ReadModel):
    hierarchy_level: HierarchyLevel
    entity_id: Identifier
    hierarchy_authority_hash: Hash | None = None


class AuthorityIdentity(ReadModel):
    authority_hash: Hash
    source_policy_version: str
    source_baseline_id: str
    source_evidence_hashes: dict[str, Hash] = Field(default_factory=dict)


class DailyReadRow(ReadModel):
    forecast_run_id: int
    hierarchy_level: HierarchyLevel
    entity_id: str
    origin_date: date
    target_date: date
    lead_day: int = Field(ge=1, le=15)
    point_forecast_kg: StrictStr
    source_result_hash: Hash
    status: Literal["READY"] = "READY"

    @field_validator("point_forecast_kg")
    @classmethod
    def quantity(cls, value: str) -> str:
        number = Decimal(value)
        if not number.is_finite() or number < 0:
            raise ValueError("INVALID_QUANTITY")
        return value


class CurveData(ReadModel):
    daily_rows: list[DailyReadRow]
    data_completeness: str
    available_day_count: int


class OverviewData(ReadModel):
    forecast_7d_total_kg: str | None
    forecast_15d_total_kg: str | None
    peak_date: date | None
    peak_daily_quantity_kg: str | None
    peak_scope: Literal["SAVED_DAILY_CURVE_D1_THROUGH_AVAILABLE_D15"] = (
        "SAVED_DAILY_CURVE_D1_THROUGH_AVAILABLE_D15"
    )
    forecast_origin: date
    forecast_scope: HierarchyIdentity
    forecast_run_identity: ForecastIdentity
    data_completeness: str
    forecast_7d_status: str
    forecast_15d_status: str
    high_load_dates: list[DailyReadRow]
    high_load_semantics: Literal["DESCRIPTIVE_QUANTITY_DESC_DATE_ASC_NO_ALERT_THRESHOLD"] = (
        "DESCRIPTIVE_QUANTITY_DESC_DATE_ASC_NO_ALERT_THRESHOLD"
    )


class HierarchyData(CurveData):
    reconciliation_method: Literal["BOTTOM_UP_EXACT_SUM"] | None
    source_status: str
    child_expected_count: int | None = None
    child_included_count: int | None = None
    missing_child_count: int | None = None


class IntervalCoverage(ReadModel):
    interval: Literal["PI80", "PI90", "UPPER80", "UPPER90"]
    candidate_row_count: int
    computable_row_count: int
    not_computable_row_count: int
    covered_row_count: int
    empirical_coverage: str
    nominal_coverage: str
    observation: Literal["UNDER_NOMINAL"]


class HorizonQuality(ReadModel):
    horizon: Literal["H1", "H3", "H7", "H15"]
    point_status: Literal["READY", "NOT_AVAILABLE"]
    daily_row_count: int | None = None
    scorable_origin_count: int | None = None
    wape: str | None = None
    mae_kg: str | None = None
    bias_kg: str | None = None
    cumulative_wape: str | None = None
    interval_status: Literal["READY", "NOT_AVAILABLE"]
    interval_coverage: list[IntervalCoverage] = Field(default_factory=list)


class QualityData(ReadModel):
    model_id: Literal["V0_15_S5_M1_RIDGE"] = "V0_15_S5_M1_RIDGE"
    source_split: Literal["EXPOSED_OOT"] = "EXPOSED_OOT"
    target_season: Literal["2025-2026"] = "2025-2026"
    scope: Literal["BASE_COHORT_AGGREGATE"] = "BASE_COHORT_AGGREGATE"
    horizons: list[HorizonQuality]
    strict_pit: Literal[False] = False
    historical_actual_available_at_proven: Literal[False] = False
    retrospective_authority_used: Literal[True] = True
    current_season_actual_available: Literal[False] = False
    current_actual_message: str = "当前产季暂无可用于正式评分的实际采收数据。"
    production_accuracy_validated: Literal[False] = False
    prospective_interval_coverage_validated: Literal[False] = False


class ReadResponse[T: ReadModel](ReadModel):
    schema_version: Literal["V0_17_FORECAST_INTELLIGENCE_READ_R1"] = (
        "V0_17_FORECAST_INTELLIGENCE_READ_R1"
    )
    capability: Capability
    status: ReadStatus
    forecast_identity: ForecastIdentity | None = None
    hierarchy_identity: HierarchyIdentity | None = None
    authority_identity: AuthorityIdentity | None = None
    source_kind: str
    source_run_id: int | None = None
    source_rerun_of_run_id: int | None = None
    source_result_hash: Hash | None = None
    policy_version: str
    projection_policy_version: Literal["V0_17_FORECAST_INTELLIGENCE_READ_PROJECTION_R1"] = (
        "V0_17_FORECAST_INTELLIGENCE_READ_PROJECTION_R1"
    )
    evidence_mode: Literal["SAVED_FORECAST", "RETROSPECTIVE_OBSERVATION", "NO_CURRENT_ACTUAL"]
    data: T | None = None
    unavailable_reason: str | None = None
    point_forecast_is_proven_p50: Literal[False] = False
    upper_planning_bound_is_quantile: Literal[False] = False
    attribution_is_causal: Literal[False] = False
    projection_hash: Hash


class ReadError(RuntimeError):
    def __init__(self, code: str, status_code: int) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(code)
