"""Frozen-policy ledger qualification and prior-season lookup, never model fitting."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import numpy as np

from backend.app.area_yield.ledger_r3a import qualify
from backend.app.area_yield.shape_r3 import normalize, season_calendar
from backend.app.area_yield.total_yield_r4 import Area, emit, positive


@dataclass(frozen=True)
class FarmSeasonQualification:
    canonical_farm: str
    season: str
    source_hash: str
    coverage_start: str
    coverage_end: str
    source_complete: bool
    active_span_global_unknown_days: tuple[str, ...]
    ledger_zero_semantics_authorized: bool
    season_completeness_status: str
    area_bound: bool
    productive_area_mu: str | None
    area_basis: str | None
    total_evaluable: bool
    shape_evaluable: bool
    peak_evaluation_status: str
    seven_day_evaluation_status: str
    exclusion_reasons: tuple[str, ...]


def validate_daily(rows: list[dict[str, str]]) -> None:
    """New intake is observed farm-day aggregate only; no empty/duplicate labels."""
    seen = set()
    if not rows:
        raise ValueError("empty source")
    for r in rows:
        farm = r["canonical_farm_id"]
        d = date.fromisoformat(r["date"])
        try:
            value = Decimal(r["daily_harvest_kg"])
        except InvalidOperation as exc:
            raise ValueError("null or invalid quantity") from exc
        key = farm, d
        if not farm or farm != farm.strip() or not value.is_finite() or value < 0 or key in seen:
            raise ValueError("invalid source value, identity or duplicate farm-day")
        seen.add(key)


def build_qualifications(
    rows: list[dict[str, str]],
    season: str,
    source_hash: str,
    start: date,
    end: date,
    complete: bool,
    zeros: bool,
    matched: set[str],
    areas: dict[str, Area],
) -> tuple[list[FarmSeasonQualification], dict[str, list[dict[str, str]]], list[dict[str, Any]]]:
    validate_daily(rows)
    days = season_calendar(season)
    if not days[0] <= start <= end <= days[-1]:
        raise ValueError("coverage outside season")
    if any(not start <= date.fromisoformat(r["date"]) <= end for r in rows):
        raise ValueError("source outside declared coverage")
    if len(source_hash) != 64 or any(c not in "0123456789abcdef" for c in source_hash):
        raise ValueError("source hash required")
    matrix, calendar = qualify(rows, season, start, end, complete and zeros, matched)
    active = {r["date"] for r in calendar if r["source_active_day"]}
    unknown = {r["date"] for r in calendar if not r["source_active_day"]}
    observed = {(r["canonical_farm_id"], r["date"]): r["daily_harvest_kg"] for r in rows}
    result, curves = [], {}
    for r in matrix:
        farm = r["farm"]
        area = areas.get(farm)
        value = str(area.validate(farm)) if area else None
        reasons = r["exclusion_reason"].split(";") if r["exclusion_reason"] else []
        status = "STRICT_ELIGIBLE"
        if not complete or not zeros:
            status = "SOURCE_INCOMPLETE"
        elif r["active_span_global_unknown_days"]:
            status = "GLOBAL_UNKNOWN_BLOCKED"
        elif r["days_from_file_start"] is not None and r["days_from_file_start"] < 14:
            status = "LEFT_CENSORED"
        elif r["days_to_file_end"] is not None and r["days_to_file_end"] < 14:
            status = "RIGHT_CENSORED"
        elif not r["strict_eligible"]:
            status = "NOT_ELIGIBLE_OTHER"
        strict = status == "STRICT_ELIGIBLE"
        # Area is orthogonal to season completeness; never hides a source blocker.
        if area is None:
            reasons.append("AREA_MISSING")
        result.append(
            FarmSeasonQualification(
                farm,
                season,
                source_hash,
                str(start),
                str(end),
                complete,
                tuple(
                    sorted(
                        d
                        for d in unknown
                        if r["first_positive_date"] <= d <= r["last_positive_date"]
                    )
                ),
                zeros,
                status,
                area is not None,
                value,
                area.basis if area else None,
                strict and area is not None,
                strict,
                "NOT_COMPUTABLE_OTHER",
                "NOT_COMPUTABLE_OTHER",
                tuple(reasons),
            )
        )
        curves[farm] = [
            {
                "farm": farm,
                "date": str(d),
                "quantity": observed.get(
                    (farm, str(d)), "0" if complete and zeros and str(d) in active else ""
                ),
                "status": "OBSERVED"
                if (farm, str(d)) in observed
                else "SOURCE_ACTIVE_LEDGER_ZERO"
                if complete and zeros and str(d) in active
                else "UNKNOWN_GLOBAL_NO_RECORD",
            }
            for d in days
        ]
    return result, curves, calendar


def prior_prediction(
    history: list[dict[str, str]],
    train_season: str,
    target_season: str,
    area: str | None,
) -> tuple[list[float], str | None]:
    """R3B's frozen interpolation rule and R4's prior lookup; no coefficient fit.

    Unknown history remains unknown. Interpolation is prediction-only, exactly
    equivalent to the single-farm R3B empirical positions/values path.
    """
    train_days, target_days = season_calendar(train_season), season_calendar(target_season)
    if target_days[0] <= train_days[-1]:
        raise ValueError("target must follow history")
    if [r["date"] for r in history] != [str(d) for d in train_days]:
        raise ValueError("history calendar mismatch")
    if len({r["farm"] for r in history}) != 1:
        raise ValueError("mixed farm history")
    known = [(i, Decimal(r["quantity"])) for i, r in enumerate(history) if r["quantity"] != ""]
    if any(not v.is_finite() or v < 0 for _, v in known):
        raise ValueError("invalid history")
    total = sum((v for _, v in known), Decimal(0))
    positive(str(total))
    shares = normalize(
        np.interp(
            np.arange(len(target_days)) / len(target_days),
            [i / len(train_days) for i, _ in known],
            [float(v / total) for _, v in known],
        ).tolist()
    )
    return shares, emit(total / positive(area)) if area is not None else None
