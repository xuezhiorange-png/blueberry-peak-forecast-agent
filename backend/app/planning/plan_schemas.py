from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


class ProductionPlanValidationError(ValueError):
    pass


class ProductionPlanNotFoundError(ValueError):
    pass


class ProductionPlanUnavailableError(ValueError):
    pass


class ProductionPlanVersionConflictError(ValueError):
    pass


class ProductionPlanIntervalConflictError(ValueError):
    pass


@dataclass(frozen=True)
class ProductionPlanRecord:
    id: int
    farm_id: int
    farm_name: str
    subfarm_id: int | None
    subfarm_name: str | None
    season_id: int
    season_code: str
    variety_id: int
    variety_code: str
    variety_name: str
    planted_area_mu: Decimal
    expected_yield_kg_per_mu: Decimal
    marketable_rate: Decimal
    tree_age_years: Decimal | None
    pruning_date: date | None
    flowering_start_date: date | None
    flowering_peak_date: date | None
    flowering_end_date: date | None
    first_pick_date: date | None
    expected_total_marketable_kg: Decimal | None
    derived_total_marketable_kg: Decimal
    total_difference_kg: Decimal | None
    version: int
    effective_from: date
    effective_to: date | None
    available_at: date
    source_type: str
    source_name: str | None
    source_version: str | None
    notes: str | None
    row_hash: str
    warnings: tuple[str, ...]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ProductionPlanMutationResult:
    record: ProductionPlanRecord
    created: bool


@dataclass(frozen=True)
class ProductionPlanImportErrorRow:
    row_number: int
    field: str
    message: str


@dataclass(frozen=True)
class ProductionPlanImportExecutionResult:
    status: str
    file_sha256: str
    row_count: int
    inserted_count: int
    skipped_count: int
    rejected_count: int
    duplicate_count: int
    unknown_farm_count: int
    unknown_subfarm_count: int
    unknown_season_count: int
    unknown_variety_count: int
    invalid_date_count: int
    invalid_numeric_count: int
    overlap_conflict_count: int
    version_conflict_count: int
    error_rows: tuple[ProductionPlanImportErrorRow, ...]
    audit_run_id: int | None = None
    error_message: str | None = None
