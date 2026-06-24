from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator


@dataclass(frozen=True)
class CurveRules:
    version: str
    support_min_day: int
    support_max_day: int
    spline_degree: int
    spline_knot_count: int
    ridge_alpha: Decimal


@dataclass(frozen=True)
class PoolingRules:
    minimum_samples: int
    minimum_seasons: int
    minimum_farms: int
    minimum_subfarms: int
    full_pooling_sample_target: int


@dataclass(frozen=True)
class OffsetRules:
    maximum_abs_shift_days: Decimal
    minimum_training_samples: int


@dataclass(frozen=True)
class HolidayRules:
    spring_festival_codes: tuple[str, ...]
    disturbance_weight: Decimal
    exclude_from_loss: bool


@dataclass(frozen=True)
class IntervalRules:
    p80_quantile: Decimal
    p90_quantile: Decimal
    calendar_proxy_widening_factor: Decimal
    uncalibrated_widening_factor: Decimal


@dataclass(frozen=True)
class ForecastRules:
    p50_mass_tolerance_kg: Decimal
    observed_phase_adjustment_max_days: Decimal
    minimum_observed_axis_coverage_ratio: Decimal


@dataclass(frozen=True)
class MaturityCurveRules:
    curve: CurveRules
    pooling: PoolingRules
    offset: OffsetRules
    holidays: HolidayRules
    intervals: IntervalRules
    forecast: ForecastRules
    random_seed: int
    model_family: Literal["shared_spline_partial_pooling"]


@dataclass(frozen=True)
class MaturityCurveConfig:
    rules: MaturityCurveRules
    config_hash: str
    snapshot: dict[str, Any]


class _CurveFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    support_min_day: int
    support_max_day: int
    spline_degree: int
    spline_knot_count: int
    ridge_alpha: Decimal

    @field_validator("spline_degree")
    @classmethod
    def _validate_degree(cls, value: int) -> int:
        if value < 1:
            raise ValueError("spline_degree must be positive")
        return value

    @field_validator("spline_knot_count")
    @classmethod
    def _validate_knots(cls, value: int) -> int:
        if value < 3:
            raise ValueError("spline_knot_count must be at least 3")
        return value


class _PoolingFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minimum_samples: int
    minimum_seasons: int
    minimum_farms: int
    minimum_subfarms: int
    full_pooling_sample_target: int


class _OffsetFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    maximum_abs_shift_days: Decimal
    minimum_training_samples: int


class _HolidayFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spring_festival_codes: list[str]
    disturbance_weight: Decimal
    exclude_from_loss: bool

    @field_validator("disturbance_weight")
    @classmethod
    def _validate_weight(cls, value: Decimal) -> Decimal:
        if value < 0 or value > 1:
            raise ValueError("disturbance_weight must be between 0 and 1")
        return value


class _IntervalFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    p80_quantile: Decimal
    p90_quantile: Decimal
    calendar_proxy_widening_factor: Decimal
    uncalibrated_widening_factor: Decimal

    @field_validator("p80_quantile", "p90_quantile")
    @classmethod
    def _validate_quantile(cls, value: Decimal) -> Decimal:
        if value <= 0 or value >= 1:
            raise ValueError("interval quantiles must be between 0 and 1")
        return value


class _ForecastFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    p50_mass_tolerance_kg: Decimal
    observed_phase_adjustment_max_days: Decimal
    minimum_observed_axis_coverage_ratio: Decimal

    @field_validator("minimum_observed_axis_coverage_ratio")
    @classmethod
    def _validate_coverage_ratio(cls, value: Decimal) -> Decimal:
        if value <= 0 or value > 1:
            raise ValueError("minimum_observed_axis_coverage_ratio must be between 0 and 1")
        return value


class _ConfigFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_family: Literal["shared_spline_partial_pooling"]
    random_seed: int
    curve: _CurveFile
    pooling: _PoolingFile
    offset: _OffsetFile
    holidays: _HolidayFile
    intervals: _IntervalFile
    forecast: _ForecastFile


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return data


def _stable_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _config_hash(snapshot: dict[str, Any]) -> str:
    return hashlib.sha256(_stable_json(snapshot).encode("utf-8")).hexdigest()


def load_maturity_curve_config(path: Path) -> MaturityCurveConfig:
    snapshot = _read_yaml(path)
    try:
        parsed = _ConfigFile.model_validate(snapshot)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
    if parsed.curve.support_max_day <= parsed.curve.support_min_day:
        raise ValueError("curve support_max_day must be greater than support_min_day")
    return MaturityCurveConfig(
        rules=MaturityCurveRules(
            curve=CurveRules(**parsed.curve.model_dump()),
            pooling=PoolingRules(**parsed.pooling.model_dump()),
            offset=OffsetRules(**parsed.offset.model_dump()),
            holidays=HolidayRules(
                spring_festival_codes=tuple(parsed.holidays.spring_festival_codes),
                disturbance_weight=parsed.holidays.disturbance_weight,
                exclude_from_loss=parsed.holidays.exclude_from_loss,
            ),
            intervals=IntervalRules(**parsed.intervals.model_dump()),
            forecast=ForecastRules(**parsed.forecast.model_dump()),
            random_seed=parsed.random_seed,
            model_family=parsed.model_family,
        ),
        config_hash=_config_hash(snapshot),
        snapshot=snapshot,
    )
