from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator


@dataclass(frozen=True)
class ResolverRules:
    address_fuzzy_match_min_score: Decimal
    nearest_reference_distance_km: Decimal
    climate_zone_radius_km: Decimal


@dataclass(frozen=True)
class SimilarityRules:
    max_distance_km: Decimal
    max_altitude_difference_m: Decimal
    township_bonus: Decimal
    county_bonus: Decimal
    climate_zone_bonus: Decimal
    same_farm_bonus: Decimal
    distance_weight: Decimal
    altitude_weight: Decimal
    recency_weight: Decimal
    ambiguity_margin: Decimal


@dataclass(frozen=True)
class FallbackRule:
    minimum_sample_count: int
    minimum_season_count: int
    maximum_historical_mape: Decimal | None


@dataclass(frozen=True)
class FallbackRules:
    same_farm_variety: FallbackRule
    same_township_altitude_variety: FallbackRule
    same_county_climate_zone_variety: FallbackRule
    same_province_variety: FallbackRule
    literature_variety_prior: FallbackRule


@dataclass(frozen=True)
class UncertaintyRules:
    widen_low_confidence_factor: Decimal
    widen_below_minimum_factor: Decimal


@dataclass(frozen=True)
class ConfidenceRules:
    high_min_score: Decimal
    medium_min_score: Decimal
    same_farm_high_min_seasons: int
    high_max_historical_mape: Decimal
    medium_max_historical_mape: Decimal
    missing_error_penalty: Decimal
    fallback_below_minimum_penalty: Decimal
    unresolved_location_penalty: Decimal


@dataclass(frozen=True)
class ParameterInferenceRules:
    resolver_version: str
    resolver: ResolverRules
    similarity: SimilarityRules
    fallback: FallbackRules
    uncertainty: UncertaintyRules
    confidence: ConfidenceRules


@dataclass(frozen=True)
class ParameterInferenceConfig:
    rules: ParameterInferenceRules
    config_hash: str
    snapshot: dict[str, Any]


class _FallbackRuleFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minimum_sample_count: int
    minimum_season_count: int
    maximum_historical_mape: Decimal | None

    @field_validator("minimum_sample_count", "minimum_season_count")
    @classmethod
    def _validate_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("fallback counts must be non-negative")
        return value


class _SimilarityFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_distance_km: Decimal
    max_altitude_difference_m: Decimal
    township_bonus: Decimal
    county_bonus: Decimal
    climate_zone_bonus: Decimal
    same_farm_bonus: Decimal
    distance_weight: Decimal
    altitude_weight: Decimal
    recency_weight: Decimal
    ambiguity_margin: Decimal


class _ResolverFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    address_fuzzy_match_min_score: Decimal
    nearest_reference_distance_km: Decimal
    climate_zone_radius_km: Decimal


class _FallbackFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    same_farm_variety: _FallbackRuleFile
    same_township_altitude_variety: _FallbackRuleFile
    same_county_climate_zone_variety: _FallbackRuleFile
    same_province_variety: _FallbackRuleFile
    literature_variety_prior: _FallbackRuleFile


class _UncertaintyFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    widen_low_confidence_factor: Decimal
    widen_below_minimum_factor: Decimal


class _ConfidenceFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    high_min_score: Decimal
    medium_min_score: Decimal
    same_farm_high_min_seasons: int
    high_max_historical_mape: Decimal
    medium_max_historical_mape: Decimal
    missing_error_penalty: Decimal
    fallback_below_minimum_penalty: Decimal
    unresolved_location_penalty: Decimal


class _ConfigFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolver_version: str
    resolver: _ResolverFile
    similarity: _SimilarityFile
    fallback: _FallbackFile
    uncertainty: _UncertaintyFile
    confidence: _ConfidenceFile


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


def _to_fallback_rule(rule: _FallbackRuleFile) -> FallbackRule:
    return FallbackRule(
        minimum_sample_count=rule.minimum_sample_count,
        minimum_season_count=rule.minimum_season_count,
        maximum_historical_mape=rule.maximum_historical_mape,
    )


def load_parameter_inference_config(path: Path) -> ParameterInferenceConfig:
    snapshot = _read_yaml(path)
    try:
        parsed = _ConfigFile.model_validate(snapshot)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc

    return ParameterInferenceConfig(
        rules=ParameterInferenceRules(
            resolver_version=parsed.resolver_version,
            resolver=ResolverRules(**parsed.resolver.model_dump()),
            similarity=SimilarityRules(**parsed.similarity.model_dump()),
            fallback=FallbackRules(
                same_farm_variety=_to_fallback_rule(parsed.fallback.same_farm_variety),
                same_township_altitude_variety=_to_fallback_rule(
                    parsed.fallback.same_township_altitude_variety
                ),
                same_county_climate_zone_variety=_to_fallback_rule(
                    parsed.fallback.same_county_climate_zone_variety
                ),
                same_province_variety=_to_fallback_rule(parsed.fallback.same_province_variety),
                literature_variety_prior=_to_fallback_rule(
                    parsed.fallback.literature_variety_prior
                ),
            ),
            uncertainty=UncertaintyRules(**parsed.uncertainty.model_dump()),
            confidence=ConfidenceRules(**parsed.confidence.model_dump()),
        ),
        config_hash=_config_hash(snapshot),
        snapshot=snapshot,
    )
