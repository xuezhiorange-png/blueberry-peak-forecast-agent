"""Incumbent daily forecast curve provider port for S3-A."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum
from zoneinfo import ZoneInfo

from backend.app.rolling_backtest.schemas import S2ForecastAuthorityBundle
from backend.app.s3_daily_rowset.schemas import EvaluationInstanceCell

SHANGHAI = ZoneInfo("Asia/Shanghai")


class ForecastAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class ForecastDayResult:
    availability: ForecastAvailability
    forecast_harvest_quantity_kg: Decimal | None = None


class IncumbentDailyCurveProvider:
    """Read-only incumbent replay port; production adapters must be PIT-visible."""

    @property
    def is_lawful_production_provider(self) -> bool:
        return False

    @property
    def is_placeholder_provider(self) -> bool:
        return False

    def forecast_kg_for_day(
        self,
        cell: EvaluationInstanceCell,
        *,
        business_date: date,
    ) -> ForecastDayResult:
        raise NotImplementedError

    def forecast_authority_for(
        self,
        cell: EvaluationInstanceCell,
        *,
        business_date: date,
        horizon_days: int,
    ) -> S2ForecastAuthorityBundle | None:
        del cell, business_date, horizon_days
        return None


@dataclass
class FakeIncumbentDailyCurveProvider(IncumbentDailyCurveProvider):
    """Test double for incumbent daily curves. Not for production use."""

    forecasts: dict[date, Decimal] | None = None
    unavailable: bool = False
    default_authority: S2ForecastAuthorityBundle | None = None
    authorities: dict[tuple[date, int], S2ForecastAuthorityBundle] | None = None

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

    def forecast_authority_for(
        self,
        cell: EvaluationInstanceCell,
        *,
        business_date: date,
        horizon_days: int,
    ) -> S2ForecastAuthorityBundle | None:
        del cell
        if self.authorities is not None and (business_date, horizon_days) in self.authorities:
            return self.authorities[(business_date, horizon_days)]
        return self.default_authority


@dataclass
class UnavailableIncumbentDailyCurveProvider(IncumbentDailyCurveProvider):
    """Fail-closed provider when no lawful PIT-visible daily curve is bound."""

    @property
    def is_placeholder_provider(self) -> bool:
        return True

    def forecast_kg_for_day(
        self,
        cell: EvaluationInstanceCell,
        *,
        business_date: date,
    ) -> ForecastDayResult:
        del cell, business_date
        return ForecastDayResult(availability=ForecastAvailability.UNAVAILABLE)


@dataclass
class SparseHorizonBindingForecastProvider(IncumbentDailyCurveProvider):
    """Test double mimicking sparse 7/14/21 binding rows only. Not for production."""

    @property
    def is_placeholder_provider(self) -> bool:
        return True

    sparse_horizon_days: tuple[int, ...] = (7, 14, 21)
    forecast_kg: Decimal = Decimal("1.0")

    def forecast_kg_for_day(
        self,
        cell: EvaluationInstanceCell,
        *,
        business_date: date,
    ) -> ForecastDayResult:
        cutoff_date = cell.forecast_cutoff_at.astimezone(SHANGHAI).date()
        sparse_target_dates = {
            cutoff_date + timedelta(days=horizon_days) for horizon_days in self.sparse_horizon_days
        }
        if business_date not in sparse_target_dates:
            return ForecastDayResult(availability=ForecastAvailability.UNAVAILABLE)
        return ForecastDayResult(
            availability=ForecastAvailability.AVAILABLE,
            forecast_harvest_quantity_kg=self.forecast_kg,
        )
