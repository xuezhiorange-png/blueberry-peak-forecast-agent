"""Build a PIT-visible incumbent daily curve index from persisted Task 8 rows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.master_data import Farm, Season, Subfarm, Variety
from backend.app.models.maturity import MaturityDailyPredictionModel, MaturityForecastRun
from backend.app.models.production_plan import FarmSeasonVarietyPlan
from backend.app.rolling_backtest.persisted_forecast_authority import ForecastQuantile
from backend.app.rolling_backtest.resolution import task8_daily_prediction_payload_hash
from backend.app.rolling_backtest.schemas import S2ForecastAuthorityBundle
from backend.app.s3_daily_rowset.pit_visible_incumbent_forecast_authority_loader import (
    is_synthetic_forecast_authority,
)
from backend.app.s3_daily_rowset.schemas import HORIZON_DAYS
from backend.app.s3_daily_rowset.window import expected_forecast_target_date

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
    task8_daily_prediction_payload_hash: str
    core_daily_row_identity_hash: str
    forecast_run_identity_hash: str
    binding_authorities: dict[int, S2ForecastAuthorityBundle]


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
) -> tuple[int, int, int, int] | None:
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


def _visible_forecast_run_count_for_grain(
    session: Session,
    *,
    season_id: int,
    farm_id: int,
    subfarm_id: int | None,
    variety_id: int,
    forecast_cutoff_at: datetime,
) -> int:
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
    return len(list(session.scalars(query).all()))


def _visible_forecast_run_for_grain(
    session: Session,
    *,
    season_id: int,
    farm_id: int,
    subfarm_id: int | None,
    variety_id: int,
    forecast_cutoff_at: datetime,
) -> MaturityForecastRun | None:
    count = _visible_forecast_run_count_for_grain(
        session,
        season_id=season_id,
        farm_id=farm_id,
        subfarm_id=subfarm_id,
        variety_id=variety_id,
        forecast_cutoff_at=forecast_cutoff_at,
    )
    if count != 1:
        return None
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
    return session.scalar(query)


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
    farm_id: int,
    subfarm_id: int,
    variety_id: int,
    session: Session,
    forecast_cutoff_at: datetime,
) -> None:
    task8_hash = task8_daily_prediction_payload_hash(
        daily,
        forecast_source_signature=forecast_run.source_signature,
    )
    for quantile in ("P50", "P80", "P90"):
        binding_authorities: dict[int, S2ForecastAuthorityBundle] = {}
        core_daily_row_identity_hash: str | None = None
        for horizon_days in sorted(HORIZON_DAYS):
            expected_target = expected_forecast_target_date(forecast_cutoff_at, horizon_days)
            if expected_target != daily.prediction_date:
                continue
            # S3-B live path has no lawful persisted task10_prediction_run_id reference.
            authority = None
            if authority is None or is_synthetic_forecast_authority(authority):
                continue
            binding_authorities[horizon_days] = authority
            if core_daily_row_identity_hash is None:
                core_daily_row_identity_hash = authority.daily_row_identity_hash
            elif core_daily_row_identity_hash != authority.daily_row_identity_hash:
                binding_authorities.clear()
                break
        if core_daily_row_identity_hash is None or not binding_authorities:
            continue
        lookup_key = (season, farm, subfarm, variety, quantile, daily.prediction_date)
        cells[lookup_key] = PitVisibleDailyForecastCell(
            forecast_kg=_forecast_kg_for_quantile(daily, quantile),
            task8_forecast_run_id=forecast_run.id,
            task8_daily_row_id=daily.id,
            task8_daily_prediction_payload_hash=task8_hash,
            core_daily_row_identity_hash=core_daily_row_identity_hash,
            forecast_run_identity_hash=forecast_run.source_signature,
            binding_authorities=binding_authorities,
        )


def build_pit_visible_incumbent_daily_curve_index(
    session: Session,
    *,
    forecast_cutoff_at: datetime,
    grains: frozenset[tuple[str, str, str, str]],
) -> PitVisibleIncumbentDailyCurveIndex:
    """Build a PIT-visible index for exact materialization grains only."""
    cells: dict[tuple[str, str, str, str, str, date], PitVisibleDailyForecastCell] = {}
    grain_forecast_run_count: dict[tuple[str, str, str, str], int] = {}

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
        run_count = _visible_forecast_run_count_for_grain(
            session,
            season_id=season_id,
            farm_id=farm_id,
            subfarm_id=subfarm_id,
            variety_id=variety_id,
            forecast_cutoff_at=forecast_cutoff_at,
        )
        grain_forecast_run_count[grain_key] = run_count
        if run_count != 1:
            continue
        forecast_run = _visible_forecast_run_for_grain(
            session,
            season_id=season_id,
            farm_id=farm_id,
            subfarm_id=subfarm_id,
            variety_id=variety_id,
            forecast_cutoff_at=forecast_cutoff_at,
        )
        if forecast_run is None:
            continue
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
                farm_id=farm_id,
                subfarm_id=subfarm_id,
                variety_id=variety_id,
                session=session,
                forecast_cutoff_at=forecast_cutoff_at,
            )
    return PitVisibleIncumbentDailyCurveIndex(
        forecast_cutoff_at=forecast_cutoff_at,
        cells=cells,
        grain_forecast_run_count=grain_forecast_run_count,
    )
