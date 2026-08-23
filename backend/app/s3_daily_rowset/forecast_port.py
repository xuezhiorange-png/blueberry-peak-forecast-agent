"""Incumbent daily forecast curve provider port for S3-A."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from backend.app.s3_daily_rowset.schemas import EvaluationInstanceCell


class ForecastAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class ForecastDayResult:
    availability: ForecastAvailability
    forecast_harvest_quantity_kg: Decimal | None = None


class IncumbentDailyCurveProvider:
    """Read-only incumbent replay port; production adapters must be PIT-visible."""

    def forecast_kg_for_day(
        self,
        cell: EvaluationInstanceCell,
        *,
        business_date: date,
    ) -> ForecastDayResult:
        raise NotImplementedError


@dataclass
class FakeIncumbentDailyCurveProvider(IncumbentDailyCurveProvider):
    """Test double for incumbent daily curves. Not for production use."""

    forecasts: dict[date, Decimal] | None = None
    unavailable: bool = False

    def forecast_kg_for_day(
        self,
        cell: EvaluationInstanceCell,
        *,
        business_date: date,
    ) -> ForecastDayResult:
        del cell
        if self.unavailable:
            return ForecastDayResult(availability=ForecastAvailability.UNAVAILABLE)
        if self.forecasts is None or business_date not in self.forecasts:
            return ForecastDayResult(availability=ForecastAvailability.UNAVAILABLE)
        return ForecastDayResult(
            availability=ForecastAvailability.AVAILABLE,
            forecast_harvest_quantity_kg=self.forecasts[business_date],
        )
