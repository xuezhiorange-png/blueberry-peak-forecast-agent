"""Single B1 product calculation. No fitting, labels, weather or evaluation calls."""

from datetime import date, timedelta
from decimal import Decimal
from statistics import median
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.area_yield.composite_r5 import compose
from backend.app.area_yield.confirmed_shape_r3a import predict
from backend.app.area_yield.data import digest
from backend.app.area_yield.evaluation import summaries
from backend.app.area_yield.shape_r3 import canonical_farm, normalize, season_calendar
from backend.app.area_yield.total_yield_r4 import emit, positive

POLICY = "AREA_YIELD_B1_V1"


class AreaDrivenForecastRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    forecast_method: Literal["AREA_DRIVEN_B1"] = "AREA_DRIVEN_B1"
    farm: str = Field(min_length=1, max_length=200)
    productive_area_mu: str
    target_season: str = Field(pattern=r"^\d{4}-\d{4}$")
    season_start: date | None = None
    season_end: date | None = None
    as_of: date | None = None

    @field_validator("productive_area_mu")
    @classmethod
    def area(cls, value: str) -> str:
        positive(value)
        return value

    @field_validator("farm")
    @classmethod
    def farm_identity(cls, value: str) -> str:
        return canonical_farm(value, [])

    @field_validator("target_season")
    @classmethod
    def season(cls, value: str) -> str:
        if int(value[5:]) != int(value[:4]) + 1:
            raise ValueError("consecutive season years required")
        return value


class DailyAreaForecast(BaseModel):
    date: date
    predicted_kg: str
    share: str


class AreaDrivenForecastResult(BaseModel):
    forecast_method: Literal["AREA_DRIVEN_B1"] = "AREA_DRIVEN_B1"
    canonical_farm: str
    identity_status: str
    requested_productive_area_mu: str
    target_season: str
    season_start: date
    season_end: date
    season_window_status: str
    history_cutoff: date
    predicted_yield_kg_per_mu: str
    predicted_total_kg: str
    total_model: str
    total_model_source_season: str
    fallback_used: bool
    fallback_reason: str | None
    shape_model: str = "GLOBAL_RIDGE_TWO_ANNUAL_HARMONICS"
    daily_forecast: list[DailyAreaForecast]
    single_day_peak: dict[str, str]
    rolling_7day_peak: dict[str, str]
    mass_balance: dict[str, Any]
    model_version: str
    forecast_policy_version: str = POLICY
    authority_hash: str
    shape_hash: str
    source_hashes: list[str]
    result_hash: str = ""
    limitations: list[str]


def check_hash(payload: dict[str, Any]) -> None:
    if payload.get("hash") != digest({k: v for k, v in payload.items() if k != "hash"}):
        raise ValueError("authority hash mismatch")


def forecast_by_area(
    request: AreaDrivenForecastRequest, authority: dict[str, Any]
) -> AreaDrivenForecastResult:
    """Server-owned, hash-pinned history. Unknown identities stay distinct, not fuzzy matched."""
    check_hash(authority)
    calendar = season_calendar(request.target_season)
    start, end = request.season_start or calendar[0], request.season_end or calendar[-1]
    if (request.season_start is None) != (request.season_end is None):
        raise ValueError("both window bounds required")
    if start not in calendar or end not in calendar or (end - start).days < 6:
        raise ValueError("window must contain at least seven days inside target season")
    # Explicit bounds define the requested business season, not a rescaled sub-query.
    # The season-year guard below still excludes all target-season actual facts.
    cutoff = request.as_of or start - timedelta(days=1)
    if cutoff >= start:
        raise ValueError("as_of must precede target season")
    shape = authority["shape"]
    check_hash(shape)
    if (
        shape["kind"] != "ridge"
        or shape["alpha"] != 10.0
        or len(shape["coefficients"]) != 4
        or shape["calendar"] != "JULY_01_THROUGH_JUNE_30"
    ):
        raise ValueError("frozen global shape required")
    if (
        date.fromisoformat(authority["shape_available_on"]) > cutoff
        or season_calendar(shape["training_season"])[-1] > cutoff
    ):
        raise ValueError("shape history unavailable at cutoff")
    farm = authority.get("aliases", {}).get(request.farm, request.farm)
    rows = authority["history"]
    if len({(r["farm"], r["season"]) for r in rows}) != len(rows):
        raise ValueError("duplicate farm-season history")
    usable = [
        r
        for r in rows
        if r["completeness"] in {"COMPLETE", "STRICT_ELIGIBLE"}
        and r["area_basis"]
        in {"MEASURED", "BUSINESS_REPORTED", "BUSINESS_CONFIRMED", "AUTHORIZED_CALIBRATION"}
        and date.fromisoformat(r["available_on"]) <= cutoff
        and date.fromisoformat(r["end"]) <= cutoff
        and int(r["season"][:4]) < int(request.target_season[:4])
    ]
    if not usable:
        raise ValueError("no eligible history for global fallback")
    for r in usable:
        positive(r["yield_kg_per_mu"])
        if len(r["source_hash"]) != 64:
            raise ValueError("history source hash required")
    own = [r for r in usable if r["farm"] == farm]
    fallback = not own
    if own:
        selected = max(own, key=lambda r: r["season"])
        source_season = selected["season"]
        used = [selected]
        value = positive(selected["yield_kg_per_mu"])
        reason = None
    else:
        source_season = max(r["season"] for r in usable)
        used = sorted([r for r in usable if r["season"] == source_season], key=lambda r: r["farm"])
        value = median([positive(r["yield_kg_per_mu"]) for r in used])
        history = [r for r in rows if r["farm"] == farm]
        reason = "NO_PRIOR_SEASON" if not history else "OTHER"
        if any(r["completeness"] not in {"COMPLETE", "STRICT_ELIGIBLE"} for r in history):
            reason = "PRIOR_SEASON_INCOMPLETE"
        elif any(
            r["area_basis"]
            not in {"MEASURED", "BUSINESS_REPORTED", "BUSINESS_CONFIRMED", "AUTHORIZED_CALIBRATION"}
            for r in history
        ):
            reason = "NO_VALID_AREA_HISTORY"
    total = emit(positive(request.productive_area_mu) * value)
    raw = predict(shape, request.target_season)
    indexes = [i for i, d in enumerate(calendar) if start <= d <= end]
    shares = normalize([raw[i] for i in indexes])
    quantities = compose(total, shares)
    days = [calendar[i] for i in indexes]
    metrics = summaries(days, quantities)
    peak, week = metrics["single_day_peak"], metrics["rolling_7day_peak"]
    difference = sum(quantities, Decimal(0)) - Decimal(total)
    tolerance = Decimal("0.0000005") * len(days) + Decimal(total) * Decimal("1e-12")
    result = AreaDrivenForecastResult(
        canonical_farm=farm,
        identity_status="EXACT_OR_AUTHORIZED_ALIAS"
        if any(r["farm"] == farm for r in rows)
        else "UNREGISTERED_EXACT_LABEL",
        requested_productive_area_mu=request.productive_area_mu,
        target_season=request.target_season,
        season_start=start,
        season_end=end,
        season_window_status="CALLER_SPECIFIED" if request.season_start else "FORECAST_ASSUMPTION",
        history_cutoff=cutoff,
        predicted_yield_kg_per_mu=emit(value),
        predicted_total_kg=total,
        total_model="GLOBAL_MEDIAN_YIELD_PER_MU" if fallback else "SAME_FARM_PRIOR_SEASON_YIELD",
        total_model_source_season=source_season,
        fallback_used=fallback,
        fallback_reason=reason,
        daily_forecast=[
            DailyAreaForecast(date=d, predicted_kg=emit(q), share=str(s))
            for d, q, s in zip(days, quantities, shares, strict=True)
        ],
        single_day_peak={"date": peak["date"], "kg": peak["quantity_kg"]},
        rolling_7day_peak={
            "start_date": week["start_date"],
            "end_date": week["end_date"],
            "total_kg": week["cumulative_quantity_kg"],
        },
        mass_balance={
            "daily_sum_kg": emit(sum(quantities, Decimal(0))),
            "predicted_total_kg": total,
            "difference_kg": emit(difference),
            "tolerance_kg": str(tolerance),
            "pass": abs(difference) <= tolerance,
        },
        model_version=authority["model_version"],
        authority_hash=authority["hash"],
        shape_hash=shape["hash"],
        source_hashes=sorted({r["source_hash"] for r in used}),
        limitations=[
            "B1_ENGINEERING_POLICY_NOT_STATISTICAL_WINNER",
            "LINEAR_AREA_SCALING_NOT_VALIDATED",
            "POINT_FORECAST_UNCALIBRATED",
            "NOT_PRODUCTION_APPROVAL",
            "JULY_JUNE_CALENDAR_ASSUMPTION_UNLESS_CALLER_WINDOW",
            "NO_STRICT_HISTORICAL_PIT_CLAIM",
        ],
    )
    result.result_hash = digest(result.model_dump(mode="json", exclude={"result_hash"}))
    return result
