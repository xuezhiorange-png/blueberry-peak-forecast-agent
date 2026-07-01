from __future__ import annotations

from datetime import date, timedelta

from backend.app.rolling_backtest.enums import DefaultNodeKey
from backend.app.rolling_backtest.schemas import DefaultRollingNodeDate


def resolve_default_node_dates(season_year: int) -> tuple[DefaultRollingNodeDate, ...]:
    as_of_dates = (
        (DefaultNodeKey.FEBRUARY_END, date(season_year, 3, 1) - timedelta(days=1)),
        (DefaultNodeKey.MARCH_15, date(season_year, 3, 15)),
        (DefaultNodeKey.MARCH_31, date(season_year, 3, 31)),
        (DefaultNodeKey.APRIL_07, date(season_year, 4, 7)),
    )
    return tuple(
        DefaultRollingNodeDate(
            node_key=node_key,
            as_of_local_date=as_of_local_date,
            forecast_start_local_date=as_of_local_date + timedelta(days=1),
        )
        for node_key, as_of_local_date in as_of_dates
    )
