from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Literal


@dataclass(frozen=True)
class ResolvedLocation:
    status: Literal["resolved", "ambiguous", "unresolved"]
    location_reference_id: int | None
    address_raw: str | None
    address_normalized: str | None
    province: str | None
    prefecture: str | None
    county: str | None
    township: str | None
    village: str | None
    farm_name: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    altitude_m: Decimal | None
    climate_zone_id: int | None
    climate_zone_code: str | None
    climate_zone_mapping_method: str | None
    climate_zone_confidence: Decimal | None
    candidate_count: int
    confidence_score: Decimal | None
    warnings: tuple[str, ...] = ()
    candidates: tuple[dict[str, Any], ...] = ()
    reproducibility_snapshot: dict[str, Any] = field(default_factory=dict)
    climate_zone_version: str | None = None
    climate_zone_distance_km: Decimal | None = None
    climate_zone_altitude_difference_m: Decimal | None = None
    climate_zone_score: Decimal | None = None


@dataclass(frozen=True)
class ClimateZoneImportErrorRow:
    row_number: int
    field: str
    message: str


@dataclass(frozen=True)
class ClimateZoneImportExecutionResult:
    status: str
    file_sha256: str
    zone_version: str | None
    dry_run: bool
    total_rows: int
    valid_rows: int
    invalid_rows: int
    inserted_rows: int
    skipped_rows: int
    updated_rows: int
    conflict_rows: int
    error_rows: tuple[ClimateZoneImportErrorRow, ...]
    warnings: tuple[str, ...]
    audit_run_id: int | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class CandidateObservation:
    observation_id: int
    parameter_type: str
    variety_id: int
    scalar_value: Decimal
    sample_weight: Decimal
    source_level: str
    farm_id: int | None
    subfarm_id: int | None
    location_reference_id: int | None
    climate_zone_id: int | None
    province: str | None
    prefecture: str | None
    county: str | None
    township: str | None
    farm_name: str | None
    altitude_m: Decimal | None
    latitude: Decimal
    longitude: Decimal
    season_id: int | None
    season_code: str | None
    season_end_date: date | None
    historical_mape: Decimal | None
    date_mae_days: Decimal | None
    p90_coverage: Decimal | None
    valid_from: date
    valid_to: date | None
    available_at: date | None
    source_version: str


@dataclass(frozen=True)
class RankedObservation:
    observation_id: int
    source_level: str
    similarity_score: Decimal
    distance_km: Decimal
    altitude_difference_m: Decimal | None
    candidate: CandidateObservation


@dataclass(frozen=True)
class FallbackSelection:
    level: str
    candidates: tuple[RankedObservation, ...]
    fallback_below_minimum: bool


@dataclass(frozen=True)
class ParameterInferenceValue:
    parameter_type: str
    status: Literal["available", "unavailable"]
    p50_value: Decimal | None
    p80_lower: Decimal | None
    p80_upper: Decimal | None
    source_level: str | None
    confidence_level: Literal["high", "medium", "low"] | None
    confidence_score: Decimal | None
    sample_count: int
    season_count: int
    farm_count: int
    source_observation_ids: tuple[int, ...]
    fallback_below_minimum: bool
    missing_evidence: tuple[str, ...]
    source_version: str | None = None
    source_versions: tuple[str, ...] = ()
    distance_range_km: tuple[Decimal, Decimal] | None = None
    altitude_difference_range_m: tuple[Decimal, Decimal] | None = None
    historical_mape: Decimal | None = None
    date_mae_days: Decimal | None = None
    p90_coverage: Decimal | None = None
    historical_mape_observation_count: int = 0
    date_mae_days_observation_count: int = 0
    p90_coverage_observation_count: int = 0


@dataclass(frozen=True)
class ImportExecutionResult:
    status: Literal["dry_run", "draft", "active", "skipped", "failed"]
    inserted_row_count: int
    skipped_row_count: int
    file_sha256: str
    error_message: str | None = None


@dataclass(frozen=True)
class ParameterInferenceExecutionResult:
    status: Literal["completed", "skipped", "running", "failed", "dry_run"]
    task_id: int | None
    run_id: int | None
    input_hash: str
    as_of_date: date
    resolver_version: str
    library_version: str | None
    config_hash: str
    source_signature: str
    resolved_location: dict[str, Any]
    similar_historical_samples: list[dict[str, Any]]
    variety_parameters: list[dict[str, Any]]
    warnings: tuple[str, ...]
    missing_data: tuple[str, ...]
    reproducibility_snapshot: dict[str, Any]
    error_message: str | None = None
