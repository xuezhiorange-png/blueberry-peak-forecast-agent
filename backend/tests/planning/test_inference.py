from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from backend.app.planning.config import (
    ConfidenceRules,
    FallbackRule,
    FallbackRules,
    ParameterInferenceRules,
    ResolverRules,
    SimilarityRules,
    UncertaintyRules,
)
from backend.app.planning.inference import (
    eligible_as_of_date,
    infer_parameter,
    merge_duplicate_varieties,
)
from backend.app.planning.schemas import CandidateObservation, ResolvedLocation
from backend.app.planning.similarity import haversine_distance_km


def _rules() -> ParameterInferenceRules:
    return ParameterInferenceRules(
        resolver_version="task5-v1",
        resolver=ResolverRules(
            address_fuzzy_match_min_score=Decimal("0.75"),
            nearest_reference_distance_km=Decimal("20"),
            climate_zone_radius_km=Decimal("80"),
        ),
        similarity=SimilarityRules(
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
        ),
        fallback=FallbackRules(
            same_farm_variety=FallbackRule(2, 2, Decimal("0.20")),
            same_township_altitude_variety=FallbackRule(3, 2, Decimal("0.25")),
            same_county_climate_zone_variety=FallbackRule(4, 2, Decimal("0.30")),
            same_province_variety=FallbackRule(5, 3, Decimal("0.35")),
            literature_variety_prior=FallbackRule(1, 0, None),
        ),
        uncertainty=UncertaintyRules(
            widen_low_confidence_factor=Decimal("1.50"),
            widen_below_minimum_factor=Decimal("1.25"),
        ),
        confidence=ConfidenceRules(
            high_min_score=Decimal("0.80"),
            medium_min_score=Decimal("0.50"),
            same_farm_high_min_seasons=2,
            high_max_historical_mape=Decimal("0.20"),
            medium_max_historical_mape=Decimal("0.30"),
            missing_error_penalty=Decimal("0.15"),
            fallback_below_minimum_penalty=Decimal("0.20"),
            unresolved_location_penalty=Decimal("0.20"),
        ),
    )


def _candidate(
    *,
    observation_id: int,
    scalar_value: str,
    sample_weight: str = "1",
    source_level: str,
    season_code: str | None = "2024-2025",
    season_end_date: date | None = date(2025, 4, 30),
    available_at: date | None = date(2025, 5, 1),
    historical_mape: str | None = "0.10",
    date_mae_days: str | None = "2",
    p90_coverage: str | None = "0.85",
    distance_latlon: tuple[str, str] = ("24.400000", "103.400000"),
    altitude_m: str | None = "1800",
    township: str | None = "西三镇",
    county: str | None = "弥勒市",
    climate_zone_id: int | None = 10,
    farm_name: str | None = None,
    source_version: str = "v1",
) -> CandidateObservation:
    return CandidateObservation(
        observation_id=observation_id,
        parameter_type="yield_kg_per_mu",
        variety_id=1,
        scalar_value=Decimal(scalar_value),
        sample_weight=Decimal(sample_weight),
        source_level=source_level,
        farm_id=1 if source_level == "same_farm_variety" else None,
        subfarm_id=None,
        location_reference_id=None,
        climate_zone_id=climate_zone_id,
        province="云南省",
        prefecture="红河州",
        county=county,
        township=township,
        farm_name=(
            farm_name
            if farm_name is not None
            else ("农场A" if source_level == "same_farm_variety" else None)
        ),
        altitude_m=Decimal(altitude_m) if altitude_m is not None else None,
        latitude=Decimal(distance_latlon[0]) if distance_latlon[0] is not None else None,
        longitude=Decimal(distance_latlon[1]) if distance_latlon[1] is not None else None,
        season_id=1 if season_code is not None else None,
        season_code=season_code,
        season_end_date=season_end_date,
        historical_mape=Decimal(historical_mape) if historical_mape is not None else None,
        date_mae_days=Decimal(date_mae_days) if date_mae_days is not None else None,
        p90_coverage=Decimal(p90_coverage) if p90_coverage is not None else None,
        valid_from=date(2024, 1, 1),
        valid_to=None,
        available_at=available_at,
        source_version=source_version,
    )


def test_merge_duplicate_varieties_rejects_same_variety_twice() -> None:
    with pytest.raises(ValueError):
        merge_duplicate_varieties(
            [
                {"variety_id": 1, "planted_area_mu": Decimal("700")},
                {"variety_id": 1, "planted_area_mu": Decimal("300")},
            ]
        )


def test_merge_duplicate_varieties_rejects_non_positive_area() -> None:
    with pytest.raises(ValueError):
        merge_duplicate_varieties([{"variety_id": 1, "planted_area_mu": Decimal("0")}])


def test_eligible_as_of_date_excludes_future_season_and_future_available_date() -> None:
    assert (
        eligible_as_of_date(
            _candidate(
                observation_id=1,
                scalar_value="1000",
                source_level="same_farm_variety",
                season_end_date=date(2026, 4, 30),
                available_at=date(2026, 5, 1),
            ),
            as_of_date=date(2026, 1, 1),
        )
        is False
    )


def test_infer_parameter_returns_unavailable_when_no_candidates() -> None:
    result = infer_parameter(
        parameter_type="yield_kg_per_mu",
        candidates=[],
        rules=_rules(),
    )

    assert result.status == "unavailable"


def test_infer_parameter_uses_first_satisfied_level_and_computes_weighted_p50_p80() -> None:
    result = infer_parameter(
        parameter_type="yield_kg_per_mu",
        candidates=[
            _candidate(observation_id=1, scalar_value="900", source_level="same_farm_variety"),
            _candidate(
                observation_id=2,
                scalar_value="1000",
                source_level="same_farm_variety",
                season_code="2023-2024",
                season_end_date=date(2024, 4, 30),
                available_at=date(2024, 5, 1),
            ),
            _candidate(
                observation_id=3,
                scalar_value="1100",
                source_level="same_township_altitude_variety",
            ),
            _candidate(
                observation_id=4,
                scalar_value="1200",
                source_level="same_township_altitude_variety",
                season_code="2023-2024",
            ),
            _candidate(
                observation_id=5,
                scalar_value="1300",
                source_level="same_township_altitude_variety",
                season_code="2022-2023",
            ),
        ],
        rules=_rules(),
    )

    assert result.status == "available"
    assert result.source_level == "same_farm_variety"
    assert result.p50_value == Decimal("900")
    assert result.p80_lower == Decimal("900")
    assert result.p80_upper == Decimal("1000")


def test_infer_parameter_marks_low_confidence_and_widens_when_below_minimum() -> None:
    result = infer_parameter(
        parameter_type="marketable_rate",
        candidates=[
            _candidate(
                observation_id=1,
                scalar_value="0.82",
                source_level="same_province_variety",
                historical_mape=None,
            )
        ],
        rules=_rules(),
        floor=Decimal("0"),
        ceiling=Decimal("1"),
    )

    assert result.status == "available"
    assert result.fallback_below_minimum is True
    assert result.confidence_level == "low"
    assert result.p80_lower <= Decimal("0.82") <= result.p80_upper
    assert result.p80_lower >= Decimal("0")
    assert result.p80_upper <= Decimal("1")


def _resolved_location() -> ResolvedLocation:
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
        climate_zone_distance_km=None,
        climate_zone_altitude_difference_m=Decimal("0"),
        climate_zone_score=Decimal("1.0"),
    )


def test_infer_parameter_skips_level_when_historical_mape_exceeds_maximum() -> None:
    result = infer_parameter(
        parameter_type="yield_kg_per_mu",
        candidates=[
            _candidate(
                observation_id=1,
                scalar_value="900",
                source_level="same_farm_variety",
                historical_mape="0.40",
            ),
            _candidate(
                observation_id=2,
                scalar_value="950",
                source_level="same_farm_variety",
                season_code="2023-2024",
                season_end_date=date(2024, 4, 30),
                available_at=date(2024, 5, 1),
                historical_mape="0.40",
            ),
            _candidate(
                observation_id=3,
                scalar_value="1000",
                source_level="same_township_altitude_variety",
                historical_mape="0.10",
            ),
            _candidate(
                observation_id=4,
                scalar_value="1020",
                source_level="same_township_altitude_variety",
                season_code="2023-2024",
                season_end_date=date(2024, 4, 30),
                available_at=date(2024, 5, 1),
                historical_mape="0.10",
            ),
            _candidate(
                observation_id=5,
                scalar_value="1040",
                source_level="same_township_altitude_variety",
                season_code="2022-2023",
                season_end_date=date(2023, 4, 30),
                available_at=date(2023, 5, 1),
                historical_mape="0.10",
            ),
        ],
        rules=_rules(),
    )

    assert result.status == "available"
    assert result.source_level == "same_township_altitude_variety"


def test_infer_parameter_uses_similarity_rank_for_source_observation_order() -> None:
    result = infer_parameter(
        parameter_type="yield_kg_per_mu",
        candidates=[
            _candidate(
                observation_id=1,
                scalar_value="900",
                source_level="same_province_variety",
                township=None,
                county=None,
                climate_zone_id=None,
                farm_name=None,
                distance_latlon=("26.000000", "103.400000"),
                season_code="2024-2025",
            ),
            _candidate(
                observation_id=2,
                scalar_value="950",
                source_level="same_province_variety",
                township=None,
                county=None,
                climate_zone_id=None,
                farm_name=None,
                distance_latlon=("24.410000", "103.410000"),
                season_code="2023-2024",
            ),
        ],
        rules=_rules(),
        resolved_location=_resolved_location(),
        as_of_date=date(2026, 1, 1),
    )

    assert result.status == "available"
    assert result.source_observation_ids == (2, 1)


def test_infer_parameter_exposes_selected_audit_ranges_and_weighted_metrics() -> None:
    result = infer_parameter(
        parameter_type="yield_kg_per_mu",
        candidates=[
            _candidate(
                observation_id=1,
                scalar_value="900",
                sample_weight="1",
                source_level="same_farm_variety",
                season_code="2024-2025",
                historical_mape="0.10",
                date_mae_days="2",
                p90_coverage="0.80",
                distance_latlon=("24.401000", "103.401000"),
                altitude_m="1810",
                source_version="param-v2",
            ),
            _candidate(
                observation_id=2,
                scalar_value="1000",
                sample_weight="3",
                source_level="same_farm_variety",
                season_code="2023-2024",
                season_end_date=date(2024, 4, 30),
                available_at=date(2024, 5, 1),
                historical_mape="0.30",
                date_mae_days="4",
                p90_coverage="0.90",
                distance_latlon=("24.430000", "103.430000"),
                altitude_m=None,
                source_version="param-v1",
            ),
        ],
        rules=_rules(),
        resolved_location=_resolved_location(),
        as_of_date=date(2026, 1, 1),
    )

    expected_min_distance = haversine_distance_km(24.4, 103.4, 24.401, 103.401)
    expected_max_distance = haversine_distance_km(24.4, 103.4, 24.43, 103.43)

    assert result.status == "available"
    assert result.source_version is None
    assert result.source_versions == ("param-v1", "param-v2")
    assert result.distance_range_km == (expected_min_distance, expected_max_distance)
    assert result.altitude_difference_range_m == (Decimal("10.0"), Decimal("10.0"))
    assert result.historical_mape == Decimal("0.25")
    assert result.date_mae_days == Decimal("3.5")
    assert result.p90_coverage == Decimal("0.875")
    assert result.historical_mape_observation_count == 2
    assert result.date_mae_days_observation_count == 2
    assert result.p90_coverage_observation_count == 2


def test_infer_parameter_returns_none_for_missing_optional_audit_fields() -> None:
    result = infer_parameter(
        parameter_type="yield_kg_per_mu",
        candidates=[
            _candidate(
                observation_id=1,
                scalar_value="900",
                source_level="same_farm_variety",
                historical_mape=None,
                date_mae_days=None,
                p90_coverage=None,
                altitude_m=None,
            ),
            _candidate(
                observation_id=2,
                scalar_value="1000",
                source_level="same_farm_variety",
                season_code="2023-2024",
                season_end_date=date(2024, 4, 30),
                available_at=date(2024, 5, 1),
                historical_mape=None,
                date_mae_days=None,
                p90_coverage=None,
                altitude_m=None,
            ),
        ],
        rules=_rules(),
        resolved_location=_resolved_location(),
        as_of_date=date(2026, 1, 1),
    )

    assert result.status == "available"
    assert result.altitude_difference_range_m is None
    assert result.historical_mape is None
    assert result.date_mae_days is None
    assert result.p90_coverage is None
    assert result.historical_mape_observation_count == 0
    assert result.date_mae_days_observation_count == 0
    assert result.p90_coverage_observation_count == 0
