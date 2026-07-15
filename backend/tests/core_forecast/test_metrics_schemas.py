from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.app.core_forecast.schemas import (
    QuantileCoreForecastMetrics,
    SingleDayPeakMetric,
    SustainedSevenDayPeakMetric,
)


def _peak_payload(quantity: object) -> dict[str, object]:
    return {
        "date": date(2026, 3, 18),
        "quantity_kg": quantity,
        "tie_break": "EARLIEST_DATE",
    }


def test_single_day_peak_accepts_exact_six_decimal_string() -> None:
    metric = SingleDayPeakMetric(**_peak_payload("12.340000"))
    assert metric.quantity_kg == "12.340000"


@pytest.mark.parametrize(
    "value",
    [
        "1",
        "1.0",
        "1.000",
        "1.0000000",
        "01.000000",
        "-0.000000",
        "-1.000000",
        "1e0",
        "1E+0",
        "NaN",
        "Infinity",
        1.0,
        True,
        Decimal("1.000000"),
    ],
)
def test_single_day_peak_rejects_non_canonical_quantity(value: object) -> None:
    with pytest.raises(ValidationError):
        SingleDayPeakMetric(**_peak_payload(value))


def test_sustained_peak_requires_exact_calendar_window() -> None:
    with pytest.raises(ValidationError):
        SustainedSevenDayPeakMetric(
            start_date=date(2026, 3, 15),
            end_date=date(2026, 3, 22),
            cumulative_quantity_kg="585.465120",
            daily_average_kg_per_day="83.637874",
            window_days=7,
            metric="ROLLING_CUMULATIVE",
            date_continuity="STRICT_CALENDAR_DAYS",
            tie_break="EARLIEST_START_DATE",
        )


def test_quantile_metric_has_frozen_six_place_outputs() -> None:
    metric = QuantileCoreForecastMetrics(
        forecast_quantile="P50",
        single_day_peak=SingleDayPeakMetric(**_peak_payload("0.000000")),
        sustained_7day_peak=SustainedSevenDayPeakMetric(
            start_date=date(2026, 3, 15),
            end_date=date(2026, 3, 21),
            cumulative_quantity_kg="0.000000",
            daily_average_kg_per_day="0.000000",
            window_days=7,
            metric="ROLLING_CUMULATIVE",
            date_continuity="STRICT_CALENDAR_DAYS",
            tie_break="EARLIEST_START_DATE",
        ),
        season_cumulative_effective_marketable_kg="0.000000",
    )
    assert metric.model_config["frozen"] is True
