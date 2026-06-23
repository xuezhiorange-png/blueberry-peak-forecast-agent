from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Literal, Protocol


class WeatherProvider(Protocol):
    provider_code: str
    provider_version: str
    dataset_version: str
    location_type: Literal["station", "grid"]

    def parse_location_rows(self) -> list[WeatherSourceLocationRecord]: ...

    def parse_observation_rows(self) -> list[DailyWeatherRecord]: ...


@dataclass(frozen=True)
class WeatherSourceLocationRecord:
    provider_code: str
    provider_version: str
    dataset_version: str
    external_location_id: str
    location_type: Literal["station", "grid"]
    name: str | None
    latitude: Decimal
    longitude: Decimal
    altitude_m: Decimal | None
    timezone_name: str
    grid_resolution: str | None
    source_version: str
    valid_from: date
    valid_to: date | None
    source_row_number: int
    quality_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class DailyWeatherRecord:
    provider_code: str
    provider_version: str
    dataset_version: str
    external_location_id: str
    observation_date: date
    temperature_min_c: Decimal
    temperature_max_c: Decimal
    temperature_mean_c: Decimal | None
    temperature_mean_source: Literal["provided", "derived"]
    precipitation_mm: Decimal
    solar_radiation_mj_m2: Decimal | None
    available_at: date
    quality_code: str | None
    quality_flags: tuple[str, ...]
    source_version: str
    source_row_number: int


@dataclass(frozen=True)
class WeatherSourceSelection:
    observation_date: date
    observation_id: int
    weather_source_location_id: int
    provider_code: str
    source_version: str
    available_at: date
    temperature_min_c: Decimal
    temperature_max_c: Decimal
    temperature_mean_c: Decimal
    precipitation_mm: Decimal
    solar_radiation_mj_m2: Decimal | None
    quality_code: str | None
    quality_flags: tuple[str, ...]


@dataclass(frozen=True)
class WeatherMappingResult:
    status: Literal["resolved", "unavailable", "conflict"]
    mapping_id: int | None
    location_reference_id: int
    weather_source_location_id: int | None
    mapping_method: str | None
    distance_km: Decimal | None
    altitude_difference_m: Decimal | None
    mapping_score: Decimal | None
    confidence_level: Literal["high", "medium", "low"] | None
    mapping_version: str
    config_hash: str
    provider_code: str | None
    external_location_id: str | None
    warnings: tuple[str, ...] = ()
    reproducibility_snapshot: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WeatherWindowFeature:
    window_days: int
    status: Literal["available", "unavailable"]
    effective_temperature_sum: Decimal | None
    solar_radiation_sum: Decimal | None
    precipitation_sum: Decimal | None
    minimum_temperature: Decimal | None
    mean_diurnal_temperature_range: Decimal | None
    maximum_consecutive_rainy_days: int | None
    observed_day_count: int
    expected_day_count: int
    coverage_ratio: Decimal
    missing_dates: tuple[date, ...]
    quality_flags: tuple[str, ...]
    source_observation_ids: tuple[int, ...]


@dataclass(frozen=True)
class PhenologyTimeline:
    plan_id: int
    plan_version: int
    pruning_date: date | None
    flowering_start_date: date | None
    flowering_peak_date: date | None
    flowering_end_date: date | None
    first_pick_date: date | None
    days_since_pruning: int | None
    days_since_flowering_start: int | None
    days_since_flowering_peak: int | None
    days_since_flowering_end: int | None
    days_until_first_pick: int | None
    anchor_event: str | None
    anchor_date: date | None
    cumulative_effective_temperature: Decimal | None
    cumulative_expected_day_count: int
    cumulative_observed_day_count: int
    cumulative_coverage_ratio: Decimal | None
    cumulative_missing_dates: tuple[date, ...]
    selected_weather_mapping_id: int | None
    weather_feature_version: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class BaseTemperatureTrainingSample:
    plan_id: int
    anchor_event: str
    target_event: str
    sample_weight: Decimal
    include: bool
    exclusion_reason: str | None


@dataclass(frozen=True)
class BaseTemperatureCandidateScore:
    base_temperature: Decimal
    fold_count: int
    evaluated_sample_count: int
    mae_days: Decimal | None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class BaseTemperatureSearchExecutionResult:
    status: Literal["completed", "skipped", "running", "failed", "unavailable", "dry_run"]
    run_id: int | None
    source_signature: str
    config_hash: str
    feature_version: str
    selected_base_temperature: Decimal | None
    scoring_method: str
    selected_score: Decimal | None
    sample_count: int
    distinct_season_count: int
    candidate_scores: tuple[BaseTemperatureCandidateScore, ...]
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    input_snapshot: dict[str, Any]
    error_message: str | None = None


@dataclass(frozen=True)
class WeatherFeatureExecutionResult:
    status: Literal["completed", "skipped", "running", "failed", "unavailable", "dry_run"]
    run_id: int | None
    source_signature: str
    feature_version: str
    config_hash: str
    mapping: dict[str, Any]
    weather_source_version: str
    plan: dict[str, Any]
    windows: tuple[WeatherWindowFeature, ...]
    timeline: PhenologyTimeline
    weather_observation_ids: tuple[int, ...]
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    input_snapshot: dict[str, Any]
    error_message: str | None = None
