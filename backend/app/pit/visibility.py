"""Single point-in-time visibility policy for V0.6 S1 records."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


class PITVisibilityError(ValueError):
    """Raised when a record is not visible at a forecast cutoff."""

    code = "PIT_RECORD_NOT_VISIBLE"


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone-aware datetime is required")
    return value.astimezone(UTC)


def record_visible_at(record: Any, forecast_created_at: datetime) -> bool:
    """Return whether a record's explicit ``known_at`` is visible.

    The function is deliberately strict: records without an explicit
    ``known_at`` are not treated as visible by guessing from another clock.
    The existing actual-harvest adapter supplies ``known_at`` from its
    persisted import receipt semantics before calling this policy.
    """

    known_at = getattr(record, "known_at", None)
    if not isinstance(known_at, datetime):
        return False
    return as_utc(known_at) <= as_utc(forecast_created_at)


def weather_forecast_visible_at(record: Any, forecast_created_at: datetime) -> bool:
    """Apply the additional as-issued weather cutoff."""

    issued_at = getattr(record, "issued_at", None)
    if not isinstance(issued_at, datetime):
        return False
    return record_visible_at(record, forecast_created_at) and as_utc(issued_at) <= as_utc(
        forecast_created_at
    )


def require_record_visible_at(record: Any, forecast_created_at: datetime) -> None:
    if not record_visible_at(record, forecast_created_at):
        raise PITVisibilityError("PIT_RECORD_NOT_VISIBLE")


def require_weather_forecast_visible_at(record: Any, forecast_created_at: datetime) -> None:
    if not weather_forecast_visible_at(record, forecast_created_at):
        raise PITVisibilityError("PIT_WEATHER_NOT_VISIBLE")
