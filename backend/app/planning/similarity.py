from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from math import asin, cos, radians, sin, sqrt

from backend.app.planning.config import FallbackRule, SimilarityRules
from backend.app.planning.schemas import (
    CandidateObservation,
    FallbackSelection,
    RankedObservation,
    ResolvedLocation,
)

_FALLBACK_ORDER = (
    "same_farm_variety",
    "same_township_altitude_variety",
    "same_county_climate_zone_variety",
    "same_province_variety",
    "literature_variety_prior",
)


def fallback_order() -> tuple[str, ...]:
    return _FALLBACK_ORDER


def haversine_distance_km(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> Decimal:
    earth_radius_km = 6371.0
    delta_lat = radians(latitude_b - latitude_a)
    delta_lon = radians(longitude_b - longitude_a)
    lat_a = radians(latitude_a)
    lat_b = radians(latitude_b)
    value = (
        sin(delta_lat / 2) ** 2
        + cos(lat_a) * cos(lat_b) * sin(delta_lon / 2) ** 2
    )
    distance = 2 * earth_radius_km * asin(sqrt(value))
    return Decimal(str(distance)).quantize(Decimal("0.000001"))


def _recency_score(season_end_date: date | None, as_of_date: date) -> Decimal:
    if season_end_date is None:
        return Decimal("0")
    days = max((as_of_date - season_end_date).days, 0)
    return Decimal("1") / (Decimal("1") + Decimal(days) / Decimal("365"))


def rank_parameter_candidates(
    *,
    resolved_location: ResolvedLocation,
    candidates: list[CandidateObservation],
    rules: SimilarityRules,
    as_of_date: date,
) -> list[RankedObservation]:
    ranked: list[RankedObservation] = []
    if resolved_location.latitude is None or resolved_location.longitude is None:
        return ranked

    for candidate in candidates:
        distance_km = haversine_distance_km(
            float(resolved_location.latitude),
            float(resolved_location.longitude),
            float(candidate.latitude),
            float(candidate.longitude),
        )
        altitude_difference_m = None
        if resolved_location.altitude_m is not None and candidate.altitude_m is not None:
            altitude_difference_m = abs(resolved_location.altitude_m - candidate.altitude_m)

        score = Decimal("0")
        distance_ratio = max(
            Decimal("0"),
            Decimal("1") - (distance_km / rules.max_distance_km),
        )
        score += distance_ratio * rules.distance_weight
        if altitude_difference_m is not None:
            altitude_ratio = max(
                Decimal("0"),
                Decimal("1") - (altitude_difference_m / rules.max_altitude_difference_m),
            )
            score += altitude_ratio * rules.altitude_weight
        score += _recency_score(candidate.season_end_date, as_of_date) * rules.recency_weight
        if (
            resolved_location.farm_name is not None
            and candidate.farm_name is not None
            and resolved_location.farm_name == candidate.farm_name
        ):
            score += rules.same_farm_bonus
        if (
            resolved_location.township is not None
            and candidate.township is not None
            and resolved_location.township == candidate.township
        ):
            score += rules.township_bonus
        if (
            resolved_location.county is not None
            and candidate.county is not None
            and resolved_location.county == candidate.county
        ):
            score += rules.county_bonus
        if (
            resolved_location.climate_zone_id is not None
            and candidate.climate_zone_id == resolved_location.climate_zone_id
        ):
            score += rules.climate_zone_bonus
        ranked.append(
            RankedObservation(
                observation_id=candidate.observation_id,
                source_level=candidate.source_level,
                similarity_score=score.quantize(Decimal("0.000001")),
                distance_km=distance_km,
                altitude_difference_m=altitude_difference_m,
                candidate=candidate,
            )
        )

    return sorted(
        ranked,
        key=lambda item: (
            -item.similarity_score,
            item.candidate.source_version,
            item.candidate.season_code or "",
            item.observation_id,
        ),
    )


def _historical_mape_within_limit(
    ranked: tuple[RankedObservation, ...],
    *,
    maximum_historical_mape: Decimal | None,
) -> bool:
    if maximum_historical_mape is None:
        return True
    values = [
        row.candidate.historical_mape
        for row in ranked
        if row.candidate.historical_mape is not None
    ]
    if not values:
        return False
    mean_value = sum(values, Decimal("0")) / Decimal(len(values))
    return mean_value <= maximum_historical_mape


def select_fallback_level(
    *,
    level_order: tuple[str, ...],
    grouped_candidates: dict[str, list[RankedObservation]],
    fallback_rules: dict[str, FallbackRule],
) -> FallbackSelection:
    normalized_groups: dict[str, tuple[RankedObservation, ...]] = {}
    for level in level_order:
        normalized_rows: list[RankedObservation] = []
        for row in grouped_candidates.get(level, ()):
            if isinstance(row, RankedObservation):
                normalized_rows.append(row)
            else:
                normalized_rows.append(
                    RankedObservation(
                        observation_id=row.observation_id,
                        source_level=row.source_level,
                        similarity_score=Decimal("0"),
                        distance_km=Decimal("0"),
                        altitude_difference_m=None,
                        candidate=row,
                    )
                )
        normalized_groups[level] = tuple(normalized_rows)

    best_available_level = next(
        (level for level in level_order if normalized_groups.get(level)),
        level_order[-1],
    )
    for level in level_order:
        ranked = normalized_groups.get(level, ())
        if not ranked:
            continue
        rule = fallback_rules[level]
        season_count = len(
            {
                row.candidate.season_code
                for row in ranked
                if row.candidate.season_code is not None
            }
        )
        if (
            len(ranked) >= rule.minimum_sample_count
            and season_count >= rule.minimum_season_count
            and _historical_mape_within_limit(
                ranked,
                maximum_historical_mape=rule.maximum_historical_mape,
            )
        ):
            return FallbackSelection(
                level=level,
                candidates=ranked,
                fallback_below_minimum=False,
            )

    return FallbackSelection(
        level=best_available_level,
        candidates=normalized_groups.get(best_available_level, ()),
        fallback_below_minimum=True,
    )


def group_candidates_by_level(
    ranked_candidates: list[RankedObservation],
) -> dict[str, list[RankedObservation]]:
    grouped: dict[str, list[RankedObservation]] = defaultdict(list)
    for row in ranked_candidates:
        grouped[row.source_level].append(row)
    return dict(grouped)
