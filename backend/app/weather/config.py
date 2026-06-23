from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator


@dataclass(frozen=True)
class MappingRules:
    provider_priorities: dict[str, int]
    location_type_priorities: dict[str, int]
    maximum_mapping_distance_km: Decimal
    altitude_penalty_weight: Decimal
    missing_altitude_penalty: Decimal
    high_confidence_max_score: Decimal
    medium_confidence_max_score: Decimal


@dataclass(frozen=True)
class FeatureRules:
    version: str
    rainy_day_threshold_mm: Decimal
    rolling_windows: tuple[int, ...]
    minimum_coverage_ratio: Decimal


@dataclass(frozen=True)
class SearchRules:
    base_temperature_candidates: tuple[Decimal, ...]
    minimum_training_sample_count: int
    minimum_distinct_season_count: int
    scoring_method: Literal["season_loso_mae_days"]
    tie_break_rule: Literal["mae_then_temperature"]


@dataclass(frozen=True)
class WeatherFeatureRules:
    mapping: MappingRules
    features: FeatureRules
    search: SearchRules


@dataclass(frozen=True)
class WeatherFeatureConfig:
    rules: WeatherFeatureRules
    config_hash: str
    snapshot: dict[str, Any]


class _MappingFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_priorities: dict[str, int]
    location_type_priorities: dict[str, int]
    maximum_mapping_distance_km: Decimal
    altitude_penalty_weight: Decimal
    missing_altitude_penalty: Decimal
    high_confidence_max_score: Decimal
    medium_confidence_max_score: Decimal

    @field_validator("provider_priorities", "location_type_priorities")
    @classmethod
    def _validate_priority_map(cls, value: dict[str, int]) -> dict[str, int]:
        if not value:
            raise ValueError("priority maps must not be empty")
        for item in value.values():
            if item < 0:
                raise ValueError("priority values must be non-negative")
        return value


class _FeatureFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    rainy_day_threshold_mm: Decimal
    rolling_windows: list[int]
    minimum_coverage_ratio: Decimal

    @field_validator("minimum_coverage_ratio")
    @classmethod
    def _validate_coverage(cls, value: Decimal) -> Decimal:
        if value < 0 or value > 1:
            raise ValueError("minimum_coverage_ratio must be between 0 and 1")
        return value

    @field_validator("rolling_windows")
    @classmethod
    def _validate_windows(cls, value: list[int]) -> list[int]:
        if value != [7, 14, 21]:
            raise ValueError("rolling_windows must be exactly [7, 14, 21]")
        return value


class _SearchFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_temperature_candidates: list[Decimal]
    minimum_training_sample_count: int
    minimum_distinct_season_count: int
    scoring_method: Literal["season_loso_mae_days"]
    tie_break_rule: Literal["mae_then_temperature"]

    @field_validator("base_temperature_candidates")
    @classmethod
    def _validate_candidates(cls, value: list[Decimal]) -> list[Decimal]:
        if not value:
            raise ValueError("base_temperature_candidates must not be empty")
        normalized = sorted(set(value))
        if len(normalized) != len(value):
            raise ValueError("base_temperature_candidates must be unique")
        return normalized


class _ConfigFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mapping: _MappingFile
    features: _FeatureFile
    search: _SearchFile

    @model_validator(mode="after")
    def _validate_location_type_priorities(self) -> _ConfigFile:
        required = {"station", "grid"}
        present = set(self.mapping.location_type_priorities)
        if present != required:
            raise ValueError("location_type_priorities must define exactly station and grid")
        return self


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


def load_weather_feature_config(path: Path) -> WeatherFeatureConfig:
    snapshot = _read_yaml(path)
    try:
        parsed = _ConfigFile.model_validate(snapshot)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc

    return WeatherFeatureConfig(
        rules=WeatherFeatureRules(
            mapping=MappingRules(**parsed.mapping.model_dump()),
            features=FeatureRules(
                version=parsed.features.version,
                rainy_day_threshold_mm=parsed.features.rainy_day_threshold_mm,
                rolling_windows=tuple(parsed.features.rolling_windows),
                minimum_coverage_ratio=parsed.features.minimum_coverage_ratio,
            ),
            search=SearchRules(
                base_temperature_candidates=tuple(parsed.search.base_temperature_candidates),
                minimum_training_sample_count=parsed.search.minimum_training_sample_count,
                minimum_distinct_season_count=parsed.search.minimum_distinct_season_count,
                scoring_method=parsed.search.scoring_method,
                tie_break_rule=parsed.search.tie_break_rule,
            ),
        ),
        config_hash=_config_hash(snapshot),
        snapshot=snapshot,
    )
