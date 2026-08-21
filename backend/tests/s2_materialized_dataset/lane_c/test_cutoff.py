from __future__ import annotations

from datetime import UTC, date, datetime, time

import pytest

from backend.app.s2_materialized_dataset.lane_c.cutoff import (
    ForecastCutoffValidationError,
    normalize_forecast_cutoff_at,
    validate_forecast_cutoff_context,
)
from backend.app.s2_materialized_dataset.lane_c.schemas import ForecastCutoffContext


def test_normalize_forecast_cutoff_at_preserves_utc_aware_value() -> None:
    value = datetime(2026, 2, 28, 12, 0, tzinfo=UTC)
    assert normalize_forecast_cutoff_at(value) == value


def test_normalize_forecast_cutoff_at_rejects_naive_datetime() -> None:
    with pytest.raises(ForecastCutoffValidationError, match="timezone-aware"):
        normalize_forecast_cutoff_at(datetime(2026, 2, 28, 12, 0))


def test_validate_forecast_cutoff_context_accepts_canonical_context() -> None:
    context = ForecastCutoffContext(forecast_cutoff_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC))
    validated = validate_forecast_cutoff_context(context)
    assert validated.forecast_cutoff_at == context.forecast_cutoff_at


def test_validate_forecast_cutoff_context_rejects_date_only_value() -> None:
    with pytest.raises(ForecastCutoffValidationError, match="timezone-aware"):
        validate_forecast_cutoff_context(
            ForecastCutoffContext(forecast_cutoff_at=date(2026, 2, 28))  # type: ignore[arg-type]
        )


def test_validate_forecast_cutoff_context_rejects_end_of_day_substitute() -> None:
    with pytest.raises(ForecastCutoffValidationError, match="exact"):
        validate_forecast_cutoff_context(
            ForecastCutoffContext(
                forecast_cutoff_at=datetime.combine(date(2026, 2, 28), time.max, tzinfo=UTC)
            )
        )
