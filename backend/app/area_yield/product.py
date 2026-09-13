"""Single B1 product calculation. No fitting, labels, weather or evaluation calls."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.area_yield.composite_r5 import compose
from backend.app.area_yield.confirmed_shape_r3a import predict
from backend.app.area_yield.data import digest
from backend.app.area_yield.evaluation import summaries
from backend.app.area_yield.product_errors import (
    AreaForecastAuthorityError,
    AreaForecastInputError,
    AreaForecastRequestError,
)
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
        if not 1 <= int(value[:4]) <= 9998 or int(value[5:]) != int(value[:4]) + 1:
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
    total_model: Literal["SAME_FARM_PRIOR_SEASON_YIELD"]
    total_model_source_season: str
    fallback_used: Literal[False]
    fallback_reason: None
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
        raise AreaForecastAuthorityError("authority payload hash mismatch")


def forecast_by_area(
    request: AreaDrivenForecastRequest, authority: dict[str, Any]
) -> AreaDrivenForecastResult:
    """Server-owned, hash-pinned history. Unknown identities stay distinct, not fuzzy matched."""
    check_hash(authority)
    calendar = season_calendar(request.target_season)
    start, end = request.season_start or calendar[0], request.season_end or calendar[-1]
    if (request.season_start is None) != (request.season_end is None):
        raise AreaForecastInputError("BOTH_WINDOW_BOUNDS_REQUIRED")
    if start not in calendar or end not in calendar or (end - start).days < 6:
        raise AreaForecastInputError("WINDOW_REQUIRES_SEVEN_DAYS_INSIDE_TARGET_SEASON")
    # Explicit bounds define the requested business season, not a rescaled sub-query.
    # The season-year guard below still excludes all target-season actual facts.
    cutoff = request.as_of or start - timedelta(days=1)
    if cutoff >= start:
        raise AreaForecastInputError("AS_OF_MUST_PRECEDE_TARGET_SEASON")
    shape = authority["shape"]
    check_hash(shape)
    if (
        shape["kind"] != "ridge"
        or shape["alpha"] != 10.0
        or len(shape["coefficients"]) != 4
        or shape["calendar"] != "JULY_01_THROUGH_JUNE_30"
    ):
        raise AreaForecastAuthorityError("frozen global shape required")
    if (
        date.fromisoformat(authority["shape_available_on"]) > cutoff
        or season_calendar(shape["training_season"])[-1] > cutoff
    ):
        raise AreaForecastInputError("SHAPE_HISTORY_UNAVAILABLE_AT_CUTOFF")
    farm = authority.get("aliases", {}).get(request.farm, request.farm)
    rows = authority["history"]
    if len({(r["farm"], r["season"]) for r in rows}) != len(rows):
        raise AreaForecastAuthorityError("duplicate farm-season history")
    own = [r for r in rows if r["farm"] == farm]
    if not own:
        raise AreaForecastRequestError("UNSUPPORTED_CANONICAL_FARM")
    year = int(request.target_season[:4])
    source_season = f"{year - 1:04d}-{year:04d}"
    prior = [r for r in own if r["season"] == source_season]
    if not prior:
        raise AreaForecastRequestError("PRIOR_SEASON_HISTORY_MISSING")
    selected = prior[0]
    if selected["completeness"] not in {"COMPLETE", "STRICT_ELIGIBLE"}:
        raise AreaForecastRequestError("PRIOR_SEASON_HISTORY_INCOMPLETE")
    if selected["area_basis"] not in {
        "MEASURED",
        "BUSINESS_REPORTED",
        "BUSINESS_CONFIRMED",
        "AUTHORIZED_CALIBRATION",
    }:
        raise AreaForecastRequestError("PRIOR_SEASON_AREA_UNAUTHORIZED")
    if (
        date.fromisoformat(selected["available_on"]) > cutoff
        or date.fromisoformat(selected["end"]) > cutoff
    ):
        raise AreaForecastRequestError("PRIOR_SEASON_HISTORY_UNAVAILABLE_AT_CUTOFF")
    if len(selected["source_hash"]) != 64:
        raise AreaForecastAuthorityError("history source hash required")
    used = [selected]
    value = positive(selected["yield_kg_per_mu"])
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
        identity_status="EXACT_OR_AUTHORIZED_ALIAS",
        requested_productive_area_mu=request.productive_area_mu,
        target_season=request.target_season,
        season_start=start,
        season_end=end,
        season_window_status="CALLER_SPECIFIED" if request.season_start else "FORECAST_ASSUMPTION",
        history_cutoff=cutoff,
        predicted_yield_kg_per_mu=emit(value),
        predicted_total_kg=total,
        total_model="SAME_FARM_PRIOR_SEASON_YIELD",
        total_model_source_season=source_season,
        fallback_used=False,
        fallback_reason=None,
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
