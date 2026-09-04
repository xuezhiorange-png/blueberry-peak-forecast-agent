"""PIT-visible incumbent daily curve provider backed by persisted Task 8 rows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from backend.app.s3_daily_rowset.forecast_port import (
    ForecastAvailability,
    ForecastDayResult,
    IncumbentDailyCurveProvider,
)
from backend.app.s3_daily_rowset.pit_visible_incumbent_daily_curve_loader import (
    PitVisibleIncumbentDailyCurveIndex,
)
from backend.app.s3_daily_rowset.schemas import EvaluationInstanceCell


@dataclass(frozen=True, slots=True)
class PitVisibleIncumbentDailyCurveProvider(IncumbentDailyCurveProvider):
    index: PitVisibleIncumbentDailyCurveIndex

    @property
    def is_lawful_production_provider(self) -> bool:
        return True

    def forecast_kg_for_day(
        self,
        cell: EvaluationInstanceCell,
        *,
        business_date: date,
    ) -> ForecastDayResult:
        if cell.forecast_cutoff_at != self.index.forecast_cutoff_at:
            return ForecastDayResult(availability=ForecastAvailability.UNAVAILABLE)
        lookup_key = (
            cell.season,
            cell.farm,
            cell.subfarm,
            cell.variety,
            cell.forecast_quantile,
            business_date,
        )
        matched = self.index.cells.get(lookup_key)
        if matched is None:
            return ForecastDayResult(availability=ForecastAvailability.UNAVAILABLE)
        forecast_kg = matched.forecast_kg
        if isinstance(forecast_kg, float):
            raise TypeError("native float forecast values are forbidden on live paths")
        return ForecastDayResult(
            availability=ForecastAvailability.AVAILABLE,
            forecast_harvest_quantity_kg=forecast_kg,
        )
