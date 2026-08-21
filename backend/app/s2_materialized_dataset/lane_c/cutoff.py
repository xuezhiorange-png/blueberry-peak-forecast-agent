"""Forecast cutoff normalization and validation for Lane C."""

from __future__ import annotations

from datetime import UTC, date, datetime, time

from backend.app.s2_materialized_dataset.lane_c.schemas import ForecastCutoffContext


class ForecastCutoffValidationError(ValueError):
    """Raised when a forecast cutoff context fails Lane C validation."""


def normalize_forecast_cutoff_at(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def validate_forecast_cutoff_context(context: ForecastCutoffContext) -> ForecastCutoffContext:
    cutoff = context.forecast_cutoff_at
    if isinstance(cutoff, date) and not isinstance(cutoff, datetime):
        raise ForecastCutoffValidationError("forecast_cutoff_at must be a datetime, not a date")
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ForecastCutoffValidationError("forecast_cutoff_at must be timezone-aware")
    normalized = normalize_forecast_cutoff_at(cutoff)
    legacy_end_of_day = datetime.combine(normalized.date(), time.max, tzinfo=UTC)
    if normalized == legacy_end_of_day:
        raise ForecastCutoffValidationError(
            "exact forecast cutoff required; end-of-day substitute is forbidden"
        )
    return context.model_copy(update={"forecast_cutoff_at": normalized})


__all__ = [
    "ForecastCutoffValidationError",
    "normalize_forecast_cutoff_at",
    "validate_forecast_cutoff_context",
]
