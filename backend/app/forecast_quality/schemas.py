from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from .enums import (
    ComparisonAvailability,
    FrozenVersion,
    MetricStatus,
    ReasonCode,
    SupportedQuantile,
)


@dataclass(frozen=True)
class ActualPhysicalRecord:
    physical_key: str
    stable_actual_identity: str
    actual_value_kg: Decimal


@dataclass(frozen=True)
class S3EvaluationInput:
    rows: Sequence[S3BindingRow]
    s2_run_identity: str
    s2_manifest_identity: str
    s2_binding_row_set_hash: str
    metric_policy_version: FrozenVersion
    baseline_policy_version: FrozenVersion


@dataclass(frozen=True)
class S3BindingRow:
    forecast_business_key: str
    actual_physical_key: str | None
    stable_actual_identity: str | None
    forecast_value_kg: Decimal | None
    actual_value_kg: Decimal | None
    forecast_quantile: SupportedQuantile
    forecast_horizon_days: int
    forecast_target_date: date
    forecast_cutoff_at: datetime
    s2_status: str
    season_business_key: str
    farm_business_key: str
    subfarm_business_key: str
    variety_business_key: str
    model_identity: str
    actual_visibility_timestamp: datetime | None


@dataclass(frozen=True)
class FarmDailyActualAggregate:
    season_business_key: str
    farm_business_key: str
    variety_business_key: str
    target_date: date
    actual_value_kg: Decimal
    unique_actual_physical_rows: int


@dataclass(frozen=True)
class FarmDailyForecastAggregate:
    season_business_key: str
    farm_business_key: str
    variety_business_key: str
    target_date: date
    forecast_cutoff_at: datetime
    model_identity: str
    forecast_quantile: SupportedQuantile
    forecast_horizon_days: int
    forecast_value_kg: Decimal
    source_forecast_business_keys: Sequence[str]


@dataclass(frozen=True)
class MetricValueCell:
    metric_name: str
    metric_value: Decimal | None
    metric_status: MetricStatus
    reason_code: ReasonCode
    numerator: Decimal | None
    denominator: Decimal | None
    mape_eligible_row_count: int
    mape_zero_actual_row_count: int


@dataclass(frozen=True)
class DailyMetricResult:
    s2_run_identity: str
    s2_manifest_identity: str
    s2_binding_row_set_hash: str
    metric_policy_version: FrozenVersion
    baseline_policy_version: FrozenVersion
    breakdown_identity: dict[str, str | int]
    s2_total_binding_row_count: int
    s2_comparable_binding_row_count: int
    s2_excluded_binding_row_count: int
    s2_not_computable_binding_row_count: int
    coverage_ratio: Decimal | None
    metric_input_mask_policy_version: FrozenVersion
    metric_input_mask_hash: str
    metric_input_row_count: int
    metric_input_quantile: SupportedQuantile
    unique_actual_physical_row_count: int
    mape_eligible_row_count: int
    mape_zero_actual_row_count: int
    mape_zero_actual_reason_code: ReasonCode | None
    metric_cells: Sequence[MetricValueCell]
    canonical_hash: str


@dataclass(frozen=True)
class BreakdownSpec:
    forecast_horizon_days: int
    farm_business_key: str
    subfarm_business_key: str
    variety_business_key: str
    season_business_key: str
    model_identity: str


@dataclass(frozen=True)
class BaselineRequest:
    current_target_date: date
    current_season_start: date
    current_season_end: date
    prior_season_start: date
    prior_season_end: date
    prior_season_identity: str
    current_forecast_cutoff_at: datetime
    farm_business_key: str
    subfarm_business_key: str
    variety_business_key: str
    requested_quantile: str
    metric_policy_version: FrozenVersion
    baseline_policy_version: FrozenVersion


@dataclass(frozen=True)
class BaselineSourceSnapshot:
    source_snapshot_identity: str
    source_snapshot_hash: str
    source_row_set_hash: str
    visibility_manifest_hash: str
    visibility_cutoff_at: datetime
    season_analog_mapping_policy_version: FrozenVersion
    actual_rows: Sequence[Mapping[str, Any]]


@dataclass(frozen=True)
class BaselineResult:
    baseline_point_forecast_kg: Decimal | None
    baseline_quantile: str
    comparison_availability: ComparisonAvailability
    metric_status: MetricStatus
    reason_code: ReasonCode
    analog_date: date | None
    source_snapshot_identity: str
    source_snapshot_hash: str
    source_row_set_hash: str
    visibility_manifest_hash: str
    canonical_hash: str
