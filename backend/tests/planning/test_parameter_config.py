from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from backend.app.planning.config import load_parameter_inference_config


def _write_config(path: Path, *, extra_feature: str | None = None) -> None:
    extra = f"\n  unused_field: {extra_feature}\n" if extra_feature is not None else "\n"
    path.write_text(
        f"""
resolver_version: "task5-v1"
resolver:
  address_fuzzy_match_min_score: 0.75
  nearest_reference_distance_km: 20
  climate_zone_radius_km: 80
similarity:
  max_distance_km: 300
  max_altitude_difference_m: 800
  township_bonus: 0.30
  county_bonus: 0.20
  climate_zone_bonus: 0.25
  same_farm_bonus: 1.00
  distance_weight: 0.25
  altitude_weight: 0.20
  recency_weight: 0.10
  ambiguity_margin: 0.05
fallback:
  same_farm_variety:
    minimum_sample_count: 2
    minimum_season_count: 2
    maximum_historical_mape: 0.20
  same_township_altitude_variety:
    minimum_sample_count: 3
    minimum_season_count: 2
    maximum_historical_mape: 0.25
  same_county_climate_zone_variety:
    minimum_sample_count: 4
    minimum_season_count: 2
    maximum_historical_mape: 0.30
  same_province_variety:
    minimum_sample_count: 5
    minimum_season_count: 3
    maximum_historical_mape: 0.35
  literature_variety_prior:
    minimum_sample_count: 1
    minimum_season_count: 0
    maximum_historical_mape: null
uncertainty:
  widen_low_confidence_factor: 1.50
  widen_below_minimum_factor: 1.25
confidence:
  high_min_score: 0.80
  medium_min_score: 0.50
  same_farm_high_min_seasons: 2
  high_max_historical_mape: 0.20
  medium_max_historical_mape: 0.30
  missing_error_penalty: 0.15
  fallback_below_minimum_penalty: 0.20
  unresolved_location_penalty: 0.20
{extra}
""",
        encoding="utf-8",
    )


def test_load_parameter_inference_config_uses_all_declared_fields(tmp_path: Path) -> None:
    config_path = tmp_path / "parameter_inference.yaml"
    _write_config(config_path)

    config = load_parameter_inference_config(config_path)

    assert config.rules.resolver_version == "task5-v1"
    assert config.rules.resolver.address_fuzzy_match_min_score == Decimal("0.75")
    assert config.rules.similarity.max_distance_km == 300
    assert config.rules.fallback.same_farm_variety.minimum_sample_count == 2
    assert config.rules.uncertainty.widen_low_confidence_factor == 1.50
    assert config.rules.confidence.high_min_score == Decimal("0.80")
    assert len(config.config_hash) == 64


def test_load_parameter_inference_config_rejects_unknown_fields(tmp_path: Path) -> None:
    config_path = tmp_path / "parameter_inference.yaml"
    _write_config(config_path, extra_feature="oops")

    with pytest.raises(ValueError):
        load_parameter_inference_config(config_path)
