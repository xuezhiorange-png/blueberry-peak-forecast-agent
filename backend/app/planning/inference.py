from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from backend.app.planning.config import ParameterInferenceRules
from backend.app.planning.quantiles import clipped_interval, weighted_quantile, widen_interval
from backend.app.planning.schemas import (
    CandidateObservation,
    ParameterInferenceValue,
    ResolvedLocation,
)
from backend.app.planning.similarity import (
    fallback_order,
    group_candidates_by_level,
    rank_parameter_candidates,
    select_fallback_level,
)


def merge_duplicate_varieties(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[int] = set()
    normalized: list[dict[str, Any]] = []
    for row in rows:
        variety_id = int(row["variety_id"])
        area = Decimal(str(row["planted_area_mu"]))
        if area <= 0:
            raise ValueError("planted_area_mu must be greater than 0")
        if variety_id in seen:
            raise ValueError("duplicate variety is not allowed")
        seen.add(variety_id)
        normalized.append({"variety_id": variety_id, "planted_area_mu": area})
    return normalized


def eligible_as_of_date(
    observation: CandidateObservation,
    *,
    as_of_date: date,
) -> bool:
    if observation.valid_from > as_of_date:
        return False
    if observation.valid_to is not None and observation.valid_to < as_of_date:
        return False
    if observation.available_at is not None:
        return observation.available_at <= as_of_date
    if observation.season_end_date is not None:
        return observation.season_end_date <= as_of_date
    return False


def _group_candidates(
    candidates: list[CandidateObservation],
) -> dict[str, list[CandidateObservation]]:
    grouped: dict[str, list[CandidateObservation]] = defaultdict(list)
    for candidate in candidates:
        grouped[candidate.source_level].append(candidate)
    return dict(grouped)


def _mean_historical_mape(candidates: list[CandidateObservation]) -> Decimal | None:
    values = [item.historical_mape for item in candidates if item.historical_mape is not None]
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def _level_meets_rule(
    candidates: list[CandidateObservation],
    *,
    minimum_sample_count: int,
    minimum_season_count: int,
    maximum_historical_mape: Decimal | None,
) -> bool:
    season_count = len({item.season_code for item in candidates if item.season_code is not None})
    if len(candidates) < minimum_sample_count or season_count < minimum_season_count:
        return False
    if maximum_historical_mape is None:
        return True
    historical_mape = _mean_historical_mape(candidates)
    if historical_mape is None:
        return False
    return historical_mape <= maximum_historical_mape


def _choose_level(
    grouped: dict[str, list[CandidateObservation]],
    rules: ParameterInferenceRules,
) -> tuple[str | None, list[CandidateObservation], bool]:
    for level in fallback_order():
        candidates = grouped.get(level, [])
        if not candidates:
            continue
        rule = getattr(rules.fallback, level)
        if _level_meets_rule(
            candidates,
            minimum_sample_count=rule.minimum_sample_count,
            minimum_season_count=rule.minimum_season_count,
            maximum_historical_mape=rule.maximum_historical_mape,
        ):
            return level, candidates, False

    for level in fallback_order():
        candidates = grouped.get(level, [])
        if candidates:
            return level, candidates, True
    return None, [], False


def _fallback_rule_map(rules: ParameterInferenceRules) -> dict[str, Any]:
    return {
        level: getattr(rules.fallback, level)
        for level in fallback_order()
    }


def _select_candidates(
    *,
    candidates: list[CandidateObservation],
    rules: ParameterInferenceRules,
    resolved_location: ResolvedLocation | None,
    as_of_date: date | None,
) -> tuple[str | None, list[CandidateObservation], bool]:
    if resolved_location is None or as_of_date is None:
        return _choose_level(_group_candidates(candidates), rules)

    ranked = rank_parameter_candidates(
        resolved_location=resolved_location,
        candidates=candidates,
        rules=rules.similarity,
        as_of_date=as_of_date,
    )
    grouped = group_candidates_by_level(ranked)
    selection = select_fallback_level(
        level_order=fallback_order(),
        grouped_candidates=grouped,
        fallback_rules=_fallback_rule_map(rules),
    )
    return (
        selection.level,
        [item.candidate for item in selection.candidates],
        selection.fallback_below_minimum,
    )


def _confidence(
    *,
    level: str,
    sample_count: int,
    season_count: int,
    historical_mape: Decimal | None,
    fallback_below_minimum: bool,
    location_status: Literal["resolved", "ambiguous", "unresolved"],
    rules: ParameterInferenceRules,
) -> tuple[Literal["high", "medium", "low"], Decimal, tuple[str, ...]]:
    score = Decimal("0.40")
    missing: list[str] = []
    if level == "same_farm_variety":
        score += Decimal("0.40")
    elif level in {"same_township_altitude_variety", "same_county_climate_zone_variety"}:
        score += Decimal("0.20")

    if season_count >= rules.confidence.same_farm_high_min_seasons:
        score += Decimal("0.10")
    if sample_count >= 3:
        score += Decimal("0.10")
    if historical_mape is None:
        score -= rules.confidence.missing_error_penalty
        missing.append("historical_mape")
    elif historical_mape <= rules.confidence.high_max_historical_mape:
        score += Decimal("0.10")
    elif historical_mape > rules.confidence.medium_max_historical_mape:
        score -= Decimal("0.10")
    if fallback_below_minimum:
        score -= rules.confidence.fallback_below_minimum_penalty
        missing.append("minimum_sample_or_season_requirement")
    if location_status != "resolved":
        score -= rules.confidence.unresolved_location_penalty
        missing.append("location_resolution")
    score = max(Decimal("0"), min(Decimal("1"), score))
    if score >= rules.confidence.high_min_score and level == "same_farm_variety":
        return "high", score, tuple(dict.fromkeys(missing))
    if score >= rules.confidence.medium_min_score:
        return "medium", score, tuple(dict.fromkeys(missing))
    return "low", score, tuple(dict.fromkeys(missing))


def infer_parameter(
    *,
    parameter_type: str,
    candidates: list[CandidateObservation],
    rules: ParameterInferenceRules,
    floor: Decimal | None = None,
    ceiling: Decimal | None = None,
    resolved_location: ResolvedLocation | None = None,
    as_of_date: date | None = None,
) -> ParameterInferenceValue:
    if not candidates:
        return ParameterInferenceValue(
            parameter_type=parameter_type,
            status="unavailable",
            p50_value=None,
            p80_lower=None,
            p80_upper=None,
            source_level=None,
            confidence_level=None,
            confidence_score=None,
            sample_count=0,
            season_count=0,
            farm_count=0,
            source_observation_ids=(),
            fallback_below_minimum=False,
            missing_evidence=("no_historical_observations",),
        )

    level, selected, fallback_below_minimum = _select_candidates(
        candidates=candidates,
        rules=rules,
        resolved_location=resolved_location,
        as_of_date=as_of_date,
    )
    if level is None or not selected:
        return ParameterInferenceValue(
            parameter_type=parameter_type,
            status="unavailable",
            p50_value=None,
            p80_lower=None,
            p80_upper=None,
            source_level=None,
            confidence_level=None,
            confidence_score=None,
            sample_count=0,
            season_count=0,
            farm_count=0,
            source_observation_ids=(),
            fallback_below_minimum=False,
            missing_evidence=("no_historical_observations",),
        )

    values = [item.scalar_value for item in selected]
    weights = [item.sample_weight for item in selected]
    raw_lower = weighted_quantile(values, weights, Decimal("0.10"))
    p50_value = weighted_quantile(values, weights, Decimal("0.50"))
    raw_upper = weighted_quantile(values, weights, Decimal("0.90"))
    lower = raw_lower
    upper = raw_upper
    sample_count = len(selected)
    season_count = len({item.season_code for item in selected if item.season_code is not None})
    farm_count = len({item.farm_id for item in selected if item.farm_id is not None})
    historical_mape = _mean_historical_mape(selected)
    confidence_level, confidence_score, missing = _confidence(
        level=level,
        sample_count=sample_count,
        season_count=season_count,
        historical_mape=historical_mape,
        fallback_below_minimum=fallback_below_minimum,
        location_status=(resolved_location.status if resolved_location is not None else "resolved"),
        rules=rules,
    )
    if confidence_level == "low":
        lower, upper = widen_interval(
            lower,
            upper,
            factor=rules.uncertainty.widen_low_confidence_factor,
            floor=floor or Decimal("0"),
            ceiling=ceiling,
        )
    if fallback_below_minimum:
        lower, upper = widen_interval(
            lower,
            upper,
            factor=rules.uncertainty.widen_below_minimum_factor,
            floor=floor or Decimal("0"),
            ceiling=ceiling,
        )
    if floor is not None or ceiling is not None:
        lower, upper = clipped_interval(
            lower,
            upper,
            floor=floor or Decimal("0"),
            ceiling=ceiling,
        )

    return ParameterInferenceValue(
        parameter_type=parameter_type,
        status="available",
        p50_value=p50_value,
        p80_lower=lower,
        p80_upper=upper,
        source_level=level,
        confidence_level=confidence_level,
        confidence_score=confidence_score,
        sample_count=sample_count,
        season_count=season_count,
        farm_count=farm_count,
        source_observation_ids=tuple(item.observation_id for item in selected),
        fallback_below_minimum=fallback_below_minimum,
        missing_evidence=missing,
    )
