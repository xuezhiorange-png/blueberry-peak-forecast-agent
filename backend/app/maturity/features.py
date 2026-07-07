from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from backend.app.models.master_data import Season


def date_range(start_date: date, end_date: date) -> list[date]:
    if end_date < start_date:
        return []
    return [
        start_date + timedelta(days=offset) for offset in range((end_date - start_date).days + 1)
    ]


def analysis_dates(season: Season) -> list[date]:
    return [
        day for day in date_range(season.start_date, season.end_date) if day.month in {1, 2, 3, 4}
    ]


def smooth_series(values: list[Decimal]) -> list[Decimal]:
    smoothed: list[Decimal] = []
    for index in range(len(values)):
        start = max(0, index - 1)
        end = min(len(values), index + 2)
        window = values[start:end]
        smoothed.append(
            (sum(window, Decimal("0")) / Decimal(len(window))).quantize(Decimal("0.000001"))
        )
    return smoothed
