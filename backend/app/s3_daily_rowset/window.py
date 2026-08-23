"""Evaluation window anchoring for S3-A daily rowset materialization."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from backend.app.s3_daily_rowset.schemas import (
    HORIZON_DAYS,
    SUSTAINED_PEAK_WINDOW_DAYS,
    DailyRow,
    SustainedPeakPredicateResult,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")
DEFAULT_IN_SEASON_MONTHS = frozenset({1, 2, 3, 4})
_SEASON_RANGE_PATTERN = re.compile(r"^(?P<start>\d{4})[-~](?P<end>\d{2,4})$")


def cutoff_business_date(forecast_cutoff_at: datetime) -> date:
    if forecast_cutoff_at.tzinfo is None or forecast_cutoff_at.utcoffset() is None:
        raise ValueError("forecast_cutoff_at must be timezone-aware")
    return forecast_cutoff_at.astimezone(SHANGHAI).date()


def horizon_window_dates(forecast_cutoff_at: datetime, horizon_days: int) -> tuple[date, ...]:
    if horizon_days not in HORIZON_DAYS:
        raise ValueError(f"unsupported horizon_days: {horizon_days}")
    start = cutoff_business_date(forecast_cutoff_at) + timedelta(days=1)
    end = cutoff_business_date(forecast_cutoff_at) + timedelta(days=horizon_days)
    dates: list[date] = []
    current = start
    while current <= end:
        dates.append(current)
        current += timedelta(days=1)
    return tuple(dates)


def expected_forecast_target_date(forecast_cutoff_at: datetime, horizon_days: int) -> date:
    return cutoff_business_date(forecast_cutoff_at) + timedelta(days=horizon_days)


def derive_season_year(season: str) -> int | None:
    stripped = season.strip()
    if not stripped:
        return None
    if stripped.isdigit() and len(stripped) == 4:
        return int(stripped)
    match = _SEASON_RANGE_PATTERN.match(stripped)
    if match is None:
        return None
    end_token = match.group("end")
    if len(end_token) == 4:
        return int(end_token)
    start_year = int(match.group("start"))
    century = start_year // 100
    suffix = int(end_token)
    return century * 100 + suffix


def complete_season_window_dates(season: str) -> tuple[date, ...]:
    season_year = derive_season_year(season)
    if season_year is None:
        raise ValueError("season year could not be derived")
    start = date(season_year, 1, 1)
    end = date(season_year, 4, 30)
    dates: list[date] = []
    current = start
    while current <= end:
        dates.append(current)
        current += timedelta(days=1)
    return tuple(dates)


def window_within_default_month_scope(window_dates: tuple[date, ...], season: str) -> bool:
    season_year = derive_season_year(season)
    if season_year is None:
        return False
    season_start = date(season_year, 1, 1)
    season_end = date(season_year, 4, 30)
    return all(season_start <= day <= season_end for day in window_dates)


@dataclass(frozen=True, slots=True)
class SustainedPeakCompletenessPredicate:
    window_days: int

    def evaluate(self, daily_rows: tuple[DailyRow, ...]) -> SustainedPeakPredicateResult:
        if self.window_days not in SUSTAINED_PEAK_WINDOW_DAYS:
            raise ValueError(f"unsupported sustained peak window: {self.window_days}")
        return SustainedPeakPredicateResult(
            window_days=self.window_days,
            pass_allowed=False,
        )


def sustained_peak_completeness_predicate(window_days: int) -> SustainedPeakCompletenessPredicate:
    return SustainedPeakCompletenessPredicate(window_days=window_days)
