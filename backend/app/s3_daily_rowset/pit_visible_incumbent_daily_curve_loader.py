"""Build a PIT-visible incumbent daily curve index from persisted Task 8 rows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.master_data import Farm, Season, Subfarm, Variety
from backend.app.models.maturity import MaturityDailyPredictionModel, MaturityForecastRun
from backend.app.models.production_plan import FarmSeasonVarietyPlan
from backend.app.rolling_backtest.resolution import task8_daily_prediction_payload_hash

ForecastQuantile = Literal["P50", "P80", "P90"]

_QUANTILE_TO_FIELD: dict[ForecastQuantile, str] = {
    "P50": "p50_kg",
    "P80": "p80_kg",
    "P90": "p90_kg",
}


@dataclass(frozen=True, slots=True)
class PitVisibleDailyForecastCell:
    forecast_kg: Decimal
    task8_forecast_run_id: int
    task8_daily_row_id: int
    daily_row_identity_hash: str
    forecast_run_identity_hash: str


@dataclass(frozen=True, slots=True)
class PitVisibleIncumbentDailyCurveIndex:
    forecast_cutoff_at: datetime
    cells: dict[tuple[str, str, str, str, str, date], PitVisibleDailyForecastCell]
    grain_forecast_run_count: dict[tuple[str, str, str, str], int]


def _subfarm_name(subfarm_business_key: str) -> str:
    if "/" in subfarm_business_key:
        return subfarm_business_key.split("/", 1)[1]
    return subfarm_business_key


def _subfarm_business_key(farm_name: str, subfarm_name: str) -> str:
    return f"{farm_name}/{subfarm_name}"


def _resolve_business_grain(
    session: Session,
    *,
    season_business_key: str,
    farm_business_key: str,
    subfarm_business_key: str,
    variety_business_key: str,
) -> tuple[int, int, int | None, int] | None:
    season = session.scalar(select(Season).where(Season.code == season_business_key))
    farm = session.scalar(select(Farm).where(Farm.name == farm_business_key))
    variety = session.scalar(select(Variety).where(Variety.code == variety_business_key))
    if season is None or farm is None or variety is None:
        return None
    subfarm = session.scalar(
        select(Subfarm).where(
            Subfarm.farm_id == farm.id,
            Subfarm.name == _subfarm_name(subfarm_business_key),
        )
    )
    if subfarm is None:
        return None
    return season.id, farm.id, subfarm.id, variety.id


def _visible_forecast_run_for_grain(
    session: Session,
    *,
    season_id: int,
    farm_id: int,
    subfarm_id: int | None,
    variety_id: int,
    forecast_cutoff_at: datetime,
) -> MaturityForecastRun | None:
    query = (
        select(MaturityForecastRun)
        .join(FarmSeasonVarietyPlan, MaturityForecastRun.plan_id == FarmSeasonVarietyPlan.id)
        .where(
            FarmSeasonVarietyPlan.season_id == season_id,
            FarmSeasonVarietyPlan.farm_id == farm_id,
            FarmSeasonVarietyPlan.variety_id == variety_id,
            MaturityForecastRun.status.in_(("completed", "unavailable")),
            MaturityForecastRun.finished_at.is_not(None),
            MaturityForecastRun.finished_at <= forecast_cutoff_at,
        )
    )
    if subfarm_id is None:
        query = query.where(FarmSeasonVarietyPlan.subfarm_id.is_(None))
    else:
        query = query.where(FarmSeasonVarietyPlan.subfarm_id == subfarm_id)
    runs = list(session.scalars(query).all())
    if len(runs) != 1:
        return None
    return runs[0]


def _forecast_kg_for_quantile(
    daily: MaturityDailyPredictionModel,
    quantile: ForecastQuantile,
) -> Decimal:
    value = getattr(daily, _QUANTILE_TO_FIELD[quantile])
    if not isinstance(value, Decimal):
        raise TypeError("task8 daily prediction quantile field must be Decimal")
    return value


def _append_daily_cells(
    cells: dict[tuple[str, str, str, str, str, date], PitVisibleDailyForecastCell],
    *,
    season: str,
    farm: str,
    subfarm: str,
    variety: str,
    forecast_run: MaturityForecastRun,
    daily: MaturityDailyPredictionModel,
) -> None:
    daily_hash = task8_daily_prediction_payload_hash(
        daily,
        forecast_source_signature=forecast_run.source_signature,
    )
    for quantile in ("P50", "P80", "P90"):
        lookup_key = (season, farm, subfarm, variety, quantile, daily.prediction_date)
        cells[lookup_key] = PitVisibleDailyForecastCell(
            forecast_kg=_forecast_kg_for_quantile(daily, quantile),
            task8_forecast_run_id=forecast_run.id,
            task8_daily_row_id=daily.id,
            daily_row_identity_hash=daily_hash,
            forecast_run_identity_hash=forecast_run.source_signature,
        )


def build_pit_visible_incumbent_daily_curve_index(
    session: Session,
    *,
    forecast_cutoff_at: datetime,
    grains: frozenset[tuple[str, str, str, str]] | None = None,
) -> PitVisibleIncumbentDailyCurveIndex:
    cells: dict[tuple[str, str, str, str, str, date], PitVisibleDailyForecastCell] = {}
    grain_forecast_run_count: dict[tuple[str, str, str, str], int] = {}

    if grains is None:
        rows = session.execute(
            select(
                Season.code,
                Farm.name,
                Subfarm.name,
                Variety.code,
                MaturityForecastRun,
                MaturityDailyPredictionModel,
            )
            .join(FarmSeasonVarietyPlan, MaturityForecastRun.plan_id == FarmSeasonVarietyPlan.id)
            .join(Season, FarmSeasonVarietyPlan.season_id == Season.id)
            .join(Farm, FarmSeasonVarietyPlan.farm_id == Farm.id)
            .join(Subfarm, FarmSeasonVarietyPlan.subfarm_id == Subfarm.id)
            .join(Variety, FarmSeasonVarietyPlan.variety_id == Variety.id)
            .join(
                MaturityDailyPredictionModel,
                MaturityDailyPredictionModel.forecast_run_id == MaturityForecastRun.id,
            )
            .where(
                MaturityForecastRun.status.in_(("completed", "unavailable")),
                MaturityForecastRun.finished_at.is_not(None),
                MaturityForecastRun.finished_at <= forecast_cutoff_at,
                MaturityDailyPredictionModel.created_at <= forecast_cutoff_at,
            )
        ).all()
        seen_grains: set[tuple[str, str, str, str]] = set()
        for season_code, farm_name, subfarm_name, variety_code, forecast_run, daily in rows:
            subfarm_key = _subfarm_business_key(farm_name, subfarm_name)
            grain_key = (season_code, farm_name, subfarm_key, variety_code)
            seen_grains.add(grain_key)
            _append_daily_cells(
                cells,
                season=season_code,
                farm=farm_name,
                subfarm=subfarm_key,
                variety=variety_code,
                forecast_run=forecast_run,
                daily=daily,
            )
        for grain_key in seen_grains:
            grain_forecast_run_count[grain_key] = 1
        return PitVisibleIncumbentDailyCurveIndex(
            forecast_cutoff_at=forecast_cutoff_at,
            cells=cells,
            grain_forecast_run_count=grain_forecast_run_count,
        )

    for season, farm, subfarm, variety in sorted(grains):
        grain_key = (season, farm, subfarm, variety)
        resolved = _resolve_business_grain(
            session,
            season_business_key=season,
            farm_business_key=farm,
            subfarm_business_key=subfarm,
            variety_business_key=variety,
        )
        if resolved is None:
            grain_forecast_run_count[grain_key] = 0
            continue
        season_id, farm_id, subfarm_id, variety_id = resolved
        forecast_run = _visible_forecast_run_for_grain(
            session,
            season_id=season_id,
            farm_id=farm_id,
            subfarm_id=subfarm_id,
            variety_id=variety_id,
            forecast_cutoff_at=forecast_cutoff_at,
        )
        if forecast_run is None:
            grain_forecast_run_count[grain_key] = 0
            continue
        grain_forecast_run_count[grain_key] = 1
        daily_rows = session.scalars(
            select(MaturityDailyPredictionModel).where(
                MaturityDailyPredictionModel.forecast_run_id == forecast_run.id,
                MaturityDailyPredictionModel.created_at <= forecast_cutoff_at,
            )
        ).all()
        for daily in daily_rows:
            _append_daily_cells(
                cells,
                season=season,
                farm=farm,
                subfarm=subfarm,
                variety=variety,
                forecast_run=forecast_run,
                daily=daily,
            )
    return PitVisibleIncumbentDailyCurveIndex(
        forecast_cutoff_at=forecast_cutoff_at,
        cells=cells,
        grain_forecast_run_count=grain_forecast_run_count,
    )
