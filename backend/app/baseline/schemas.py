from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class SelectedBuildRun:
    season_id: int
    season_code: str
    season_start_date: date
    build_run_id: int
    aggregation_version: str
    source_max_raw_id: int
    config_hash: str


@dataclass(frozen=True)
class BaselineSample:
    season_id: int
    season_code: str
    season_start_date: date
    factory_id: int
    factory_name: str
    build_run_id: int
    total_weight_kg: Decimal
    stable_median_3d_peak_kg: Decimal
    peak_concentration: Decimal
    variety_hhi: Decimal
    farm_hhi: Decimal
    subfarm_hhi: Decimal
    single_day_peak_kg: Decimal


@dataclass(frozen=True)
class LeakageAuditCheck:
    name: str
    passed: bool
    evidence: str


@dataclass(frozen=True)
class ErrorMetrics:
    evaluated_row_count: int
    excluded_row_count: int
    negative_prediction_count: int
    mape: Decimal | None
    mdape: Decimal | None
    wmape: Decimal | None
    mae_kg: Decimal | None
    mae_tonne: Decimal | None
    mean_bias_kg: Decimal | None
    exclusion_counts: dict[str, int]


@dataclass(frozen=True)
class BacktestResultRow:
    baseline_name: str
    target_season_id: int
    target_season_code: str
    factory_id: int
    factory_name: str
    previous_season_id: int | None
    previous_season_code: str | None
    fold_key: str
    status: str
    actual_stable_peak_kg: Decimal | None
    predicted_stable_peak_kg: Decimal | None
    absolute_error_kg: Decimal | None
    signed_error_kg: Decimal | None
    ape: Decimal | None
    input_features: dict[str, Any] = field(default_factory=dict)
    training_season_codes: list[str] = field(default_factory=list)
    model_metadata: dict[str, Any] = field(default_factory=dict)
    exclusion_reason: str | None = None
