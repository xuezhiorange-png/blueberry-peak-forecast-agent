from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.app.planning.config import FallbackRule, SimilarityRules
from backend.app.planning.schemas import (
    CandidateObservation,
    ResolvedLocation,
)
from backend.app.planning.similarity import (
    fallback_order,
    haversine_distance_km,
    rank_parameter_candidates,
    select_fallback_level,
)


def _location() -> ResolvedLocation:
    return ResolvedLocation(
        status="resolved",
        location_reference_id=1,
        address_raw="云南省 红河州 弥勒市 西三镇",
        address_normalized="云南省 红河州 弥勒市 西三镇",
        province="云南省",
        prefecture="红河州",
        county="弥勒市",
        township="西三镇",
        village=None,
        farm_name="农场A",
        latitude=Decimal("24.400000"),
        longitude=Decimal("103.400000"),
        altitude_m=Decimal("1800"),
        climate_zone_id=10,
        climate_zone_code="zone-a",
        climate_zone_mapping_method="reference",
        climate_zone_confidence=Decimal("1.0"),
        candidate_count=1,
        confidence_score=Decimal("1.0"),
        warnings=(),
        candidates=(),
        reproducibility_snapshot={},
    )


def _candidate(
    *,
    observation_id: int,
    source_level: str,
    township: str | None = "西三镇",
    county: str | None = "弥勒市",
    climate_zone_id: int | None = 10,
    farm_name: str | None = "农场A",
    altitude_m: str | None = "1810",
    latitude: str = "24.410000",
    longitude: str = "103.410000",
    season_code: str = "2024-2025",
) -> CandidateObservation:
    return CandidateObservation(
        observation_id=observation_id,
        parameter_type="yield_kg_per_mu",
        variety_id=1,
        scalar_value=Decimal("1000"),
        sample_weight=Decimal("1"),
        source_level=source_level,
        farm_id=1 if farm_name else None,
        subfarm_id=None,
        location_reference_id=None,
        climate_zone_id=climate_zone_id,
        province="云南省",
        prefecture="红河州",
        county=county,
        township=township,
        farm_name=farm_name,
        altitude_m=Decimal(altitude_m) if altitude_m is not None else None,
        latitude=Decimal(latitude),
        longitude=Decimal(longitude),
        season_id=1,
        season_code=season_code,
        season_end_date=date(2025, 4, 30),
        historical_mape=Decimal("0.10"),
        date_mae_days=Decimal("2"),
        p90_coverage=Decimal("0.85"),
        valid_from=date(2024, 1, 1),
        valid_to=None,
        available_at=date(2025, 5, 1),
        source_version="v1",
    )


def test_haversine_distance_km_returns_zero_for_same_coordinate() -> None:
    assert haversine_distance_km(24.4, 103.4, 24.4, 103.4) == Decimal("0")


def test_rank_parameter_candidates_prefers_same_farm_then_stable_tie_break() -> None:
    rules = SimilarityRules(
        max_distance_km=Decimal("300"),
        max_altitude_difference_m=Decimal("800"),
        township_bonus=Decimal("0.30"),
        county_bonus=Decimal("0.20"),
        climate_zone_bonus=Decimal("0.25"),
        same_farm_bonus=Decimal("1.00"),
        distance_weight=Decimal("0.25"),
        altitude_weight=Decimal("0.20"),
        recency_weight=Decimal("0.10"),
        ambiguity_margin=Decimal("0.05"),
    )
    ranked = rank_parameter_candidates(
        resolved_location=_location(),
        candidates=[
            _candidate(
                observation_id=2,
                source_level="same_county_climate_zone_variety",
                farm_name=None,
            ),
            _candidate(observation_id=1, source_level="same_farm_variety"),
        ],
        rules=rules,
        as_of_date=date(2026, 1, 1),
    )

    assert [item.observation_id for item in ranked] == [1, 2]


def test_select_fallback_level_uses_first_satisfied_level_without_cross_level_mix() -> None:
    levels = fallback_order()
    rules = {
        "same_farm_variety": FallbackRule(
            minimum_sample_count=2,
            minimum_season_count=2,
            maximum_historical_mape=Decimal("0.20"),
        ),
        "same_township_altitude_variety": FallbackRule(
            minimum_sample_count=3,
            minimum_season_count=2,
            maximum_historical_mape=Decimal("0.25"),
        ),
    }
    chosen = select_fallback_level(
        level_order=levels[:2],
        grouped_candidates={
            "same_farm_variety": [_candidate(observation_id=1, source_level="same_farm_variety")],
            "same_township_altitude_variety": [
                _candidate(observation_id=2, source_level="same_township_altitude_variety"),
                _candidate(observation_id=3, source_level="same_township_altitude_variety"),
                _candidate(
                    observation_id=4,
                    source_level="same_township_altitude_variety",
                    season_code="2023-2024",
                ),
            ],
        },
        fallback_rules=rules,
    )

    assert chosen.level == "same_township_altitude_variety"
    assert chosen.fallback_below_minimum is False

