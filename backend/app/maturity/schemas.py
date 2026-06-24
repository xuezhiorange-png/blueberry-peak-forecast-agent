from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Literal

PersistedMaturityRunStatus = Literal["running", "completed", "failed", "unavailable"]
ExecutionStatus = Literal["completed", "skipped", "running", "failed", "unavailable", "dry_run"]


@dataclass(frozen=True)
class MaturityManifestRow:
    season_id: int
    analytics_build_run_id: int
    farm_key: str
    farm_id: int
    subfarm_key: str
    subfarm_id: int | None
    variety_id: int
    location_reference_id: int
    production_plan_id: int
    base_temperature_search_run_id: int
    anchor_event: str
    facility_type: str
    include: bool
    sample_weight: Decimal
    exclusion_reason: str | None = None


@dataclass(frozen=True)
class MaturityDailyPrediction:
    prediction_date: date
    phenology_coordinate_day: Decimal
    p50_kg: Decimal
    p80_kg: Decimal
    p90_kg: Decimal
    cumulative_p50_kg: Decimal
    cumulative_p80_kg: Decimal
    cumulative_p90_kg: Decimal
    curve_share: Decimal
    confidence_level: Literal["high", "medium", "low"]
    quality_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class MaturityModelExecutionResult:
    status: ExecutionStatus
    run_id: int | None
    source_signature: str
    config_hash: str
    model_version: str
    model_family: str
    sample_count: int
    distinct_season_count: int
    distinct_farm_count: int
    distinct_subfarm_count: int
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    training_metrics: dict[str, Any]
    calibration_metrics: dict[str, Any]
    artifact: dict[str, Any]
    input_snapshot: dict[str, Any]
    error_message: str | None = None


@dataclass(frozen=True)
class MaturityForecastExecutionResult:
    status: ExecutionStatus
    run_id: int | None
    model_run_id: int
    source_signature: str
    config_hash: str
    model_version: str
    axis_mode: Literal["observed_phenology_axis", "calendar_proxy_axis"]
    expected_marketable_total_kg: Decimal
    expected_total_source: str
    daily_predictions: tuple[MaturityDailyPrediction, ...]
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    input_snapshot: dict[str, Any]
    error_message: str | None = None


@dataclass(frozen=True)
class GroupCurveArtifact:
    group_key: str
    level: Literal["climate_zone_variety", "province_variety", "variety_global"]
    density: tuple[Decimal, ...]
    peak_day: Decimal
    sample_count: int
    distinct_season_count: int
    distinct_farm_count: int
    distinct_subfarm_count: int
    parent_group_key: str | None
    shrinkage: Decimal
    warnings: tuple[str, ...] = ()
    fallback_reason: str | None = None


@dataclass(frozen=True)
class TrainingDensityPoint:
    relative_day: int
    proxy_share: Decimal
    loss_weight: Decimal
    disturbance_reason: str | None
    included_in_loss: bool


@dataclass(frozen=True)
class ShiftModelArtifact:
    enabled: bool
    intercept_days: Decimal
    coefficients: dict[str, Decimal]
    category_vocabulary: dict[str, tuple[str, ...]]
    reference_categories: dict[str, str]
    unknown_categories: dict[str, str]
    unknown_handling_rules: dict[str, str]
    feature_order: tuple[str, ...]
    scaler_center: dict[str, Decimal]
    scaler_scale: dict[str, Decimal]
    feature_units: dict[str, str]
    missing_value_rules: dict[str, str]
    bounds: tuple[Decimal, Decimal]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResolvedTrainingSample:
    manifest_row: MaturityManifestRow
    season_code: str
    season_end_date: date
    climate_zone_id: int
    province: str
    altitude_m: Decimal | None
    tree_age_years: Decimal | None
    anchor_date: date
    expected_total_kg: Decimal
    expected_total_source: str
    plan_id: int
    plan_version: int
    plan_row_hash: str
    plan_available_at: date
    plan_effective_from: date
    plan_effective_to: date | None
    mapping_row_hash: str
    location_reference_source_hash: str
    analytics_build_run_finished_at: date | None
    analytics_provenance: dict[str, Any]
    fact_row_fingerprint: tuple[dict[str, Any], ...]
    base_temperature_source_signature: str
    base_temperature_training_cutoff: date
    base_temperature_feature_version: str
    base_temperature_config_hash: str
    selected_base_temperature: Decimal
    reference_effective_temperature_per_day: Decimal | None
    observation_fingerprint: tuple[dict[str, Any], ...]
    holiday_summary: dict[str, Any]
    density_points: tuple[tuple[int, Decimal], ...]
    training_points: tuple[TrainingDensityPoint, ...]
    feature_values: dict[str, Decimal | str | None]
    warnings: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
