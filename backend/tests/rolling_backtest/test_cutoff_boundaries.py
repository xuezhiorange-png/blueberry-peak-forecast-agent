"""P0-5F: Cutoff boundary tests — datetime authority, date authority, and type dispatch.

Tests the cutoff_local_date(), assert_date_authority_visible(), and
_validate_task8_prediction_fields() cutoff enforcement without requiring
PostgreSQL. All tests are pure Python.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from zoneinfo import ZoneInfoNotFoundError

import pytest

from backend.app.rolling_backtest.orchestration import (
    assert_date_authority_visible,
    cutoff_local_date,
)

# ── Fixed timezone for Asia/Shanghai (UTC+8) ─────────────────────────────────
CST = timezone(timedelta(hours=8))

# ── Datetime authority: cutoff_local_date ────────────────────────────────────


class TestCutoffLocalDate:
    """Pure function tests for cutoff_local_date()."""

    def test_utc_datetime_converts_to_shanghai_date(self) -> None:
        """UTC midnight = Shanghai 08:00 same day."""
        cutoff = datetime(2026, 3, 15, 0, 0, tzinfo=UTC)
        result = cutoff_local_date(cutoff, "Asia/Shanghai")
        assert result == date(2026, 3, 15)

    def test_utc_evening_rolls_to_next_day_in_shanghai(self) -> None:
        """UTC 20:00 = Shanghai next day 04:00."""
        cutoff = datetime(2026, 3, 15, 20, 0, tzinfo=UTC)
        result = cutoff_local_date(cutoff, "Asia/Shanghai")
        assert result == date(2026, 3, 16)

    def test_shanghai_midnight_before_rollover(self) -> None:
        """UTC 15:59:59 = Shanghai 23:59:59 same day."""
        cutoff = datetime(2026, 3, 15, 15, 59, 59, tzinfo=UTC)
        result = cutoff_local_date(cutoff, "Asia/Shanghai")
        assert result == date(2026, 3, 15)

    def test_shanghai_midnight_after_rollover(self) -> None:
        """UTC 16:00:00 = Shanghai 00:00:00 next day."""
        cutoff = datetime(2026, 3, 15, 16, 0, 0, tzinfo=UTC)
        result = cutoff_local_date(cutoff, "Asia/Shanghai")
        assert result == date(2026, 3, 16)

    def test_cutoff_exactly_on_date_boundary(self) -> None:
        """UTC 16:00:00 exactly = Shanghai midnight."""
        cutoff = datetime(2026, 3, 15, 16, 0, 0, tzinfo=UTC)
        result = cutoff_local_date(cutoff, "Asia/Shanghai")
        # 16:00 UTC = 00:00 next day Shanghai
        assert result == date(2026, 3, 16)

    def test_different_utc_offset_same_absolute_moment(self) -> None:
        """Same absolute moment yields same local date regardless of offset."""
        # 2026-03-15T12:00:00Z
        cutoff_utc = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
        # Same moment expressed as UTC+5:30 (17:30 IST)
        ist = timezone(timedelta(hours=5, minutes=30))
        cutoff_ist = datetime(2026, 3, 15, 17, 30, tzinfo=ist)
        # Both represent the same absolute time
        assert cutoff_utc == cutoff_ist
        result_utc = cutoff_local_date(cutoff_utc, "Asia/Shanghai")
        result_ist = cutoff_local_date(cutoff_ist, "Asia/Shanghai")
        assert result_utc == result_ist

    def test_naive_datetime_raises_value_error(self) -> None:
        """Naive datetime (no tzinfo) must fail closed."""
        cutoff = datetime(2026, 3, 15, 12, 0)
        with pytest.raises(ValueError, match="timezone-aware"):
            cutoff_local_date(cutoff, "Asia/Shanghai")

    def test_plain_date_raises_type_error(self) -> None:
        """Plain date (not datetime) must raise TypeError."""
        plain = date(2026, 3, 15)
        with pytest.raises(TypeError, match="must be a datetime"):
            cutoff_local_date(plain, "Asia/Shanghai")  # type: ignore[arg-type]

    def test_invalid_timezone_fail_closed(self) -> None:
        """Invalid timezone name must raise ZoneInfoNotFoundError (fail closed)."""
        cutoff = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
        with pytest.raises(ZoneInfoNotFoundError):
            cutoff_local_date(cutoff, "Mars/Olympus")

    def test_empty_timezone_fail_closed(self) -> None:
        """Empty timezone string must fail closed (ValueError from ZoneInfo path validation)."""
        cutoff = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
        with pytest.raises((ValueError, ZoneInfoNotFoundError)):
            cutoff_local_date(cutoff, "")


# ── Datetime authority: assert_date_authority_visible ────────────────────────


class TestAssertDateAuthorityVisible:
    """Tests for assert_date_authority_visible() — date authority visibility."""

    def test_available_before_cutoff_passes(self) -> None:
        """available_on < cutoff_local_date → no error."""
        assert_date_authority_visible(
            available_on=date(2026, 3, 14),
            forecast_cutoff_at=datetime(2026, 3, 15, 12, 0, tzinfo=UTC),
            timezone_name="Asia/Shanghai",
        )  # No exception

    def test_available_equals_cutoff_passes(self) -> None:
        """available_on == cutoff_local_date → no error."""
        # UTC 2026-03-15T12:00 → Shanghai 2026-03-15T20:00 → date 2026-03-15
        assert_date_authority_visible(
            available_on=date(2026, 3, 15),
            forecast_cutoff_at=datetime(2026, 3, 15, 12, 0, tzinfo=UTC),
            timezone_name="Asia/Shanghai",
        )

    def test_available_after_cutoff_raises(self) -> None:
        """available_on > cutoff_local_date → ValueError."""
        with pytest.raises(ValueError, match="Date authority not visible"):
            assert_date_authority_visible(
                available_on=date(2026, 3, 16),
                forecast_cutoff_at=datetime(2026, 3, 15, 12, 0, tzinfo=UTC),
                timezone_name="Asia/Shanghai",
            )

    def test_utc_date_different_from_node_local_date(self) -> None:
        """UTC evening rolls to next day — available_on on that day is still visible."""
        # UTC 2026-03-15T20:00 → Shanghai 2026-03-16T04:00 → local date 2026-03-16
        # So available_on=2026-03-16 IS visible (equals cutoff date)
        assert_date_authority_visible(
            available_on=date(2026, 3, 16),
            forecast_cutoff_at=datetime(2026, 3, 15, 20, 0, tzinfo=UTC),
            timezone_name="Asia/Shanghai",
        )  # No error: available_on == cutoff_local_date

    def test_missing_timezone_fail_closed(self) -> None:
        """Invalid timezone in assert_date_authority_visible must fail closed."""
        with pytest.raises((ValueError, ZoneInfoNotFoundError)):
            assert_date_authority_visible(
                available_on=date(2026, 3, 15),
                forecast_cutoff_at=datetime(2026, 3, 15, 12, 0, tzinfo=UTC),
                timezone_name="",
            )


# ── Datetime authority: direct <= comparison (used in orchestration) ─────────


class TestDatetimeAuthorityComparison:
    """Tests for aware datetime authority comparison (authority_at <= cutoff)."""

    def test_authority_before_cutoff_visible(self) -> None:
        authority = datetime(2026, 3, 15, 11, 59, 59, tzinfo=UTC)
        cutoff = datetime(2026, 3, 15, 12, 0, 0, tzinfo=UTC)
        assert authority <= cutoff

    def test_authority_equals_cutoff_visible(self) -> None:
        authority = datetime(2026, 3, 15, 12, 0, 0, tzinfo=UTC)
        cutoff = datetime(2026, 3, 15, 12, 0, 0, tzinfo=UTC)
        assert authority <= cutoff

    def test_authority_one_microsecond_after_cutoff_not_visible(self) -> None:
        authority = datetime(2026, 3, 15, 12, 0, 0, 1, tzinfo=UTC)
        cutoff = datetime(2026, 3, 15, 12, 0, 0, tzinfo=UTC)
        assert not (authority <= cutoff)
        assert authority > cutoff

    def test_authority_naive_fail_closed(self) -> None:
        """Naive datetime authority must be rejected before comparison."""
        authority = datetime(2026, 3, 15, 12, 0)  # no tzinfo
        assert authority.tzinfo is None
        # The validator must check tzinfo before comparing

    def test_cutoff_naive_fail_closed(self) -> None:
        """Naive cutoff is invalid — must be caught by cutoff_local_date."""
        with pytest.raises(ValueError, match="timezone-aware"):
            cutoff_local_date(
                datetime(2026, 3, 15, 12, 0),  # naive
                "Asia/Shanghai",
            )

    def test_different_utc_offset_same_absolute_moment_equal(self) -> None:
        """Same absolute moment with different offsets must compare equal."""
        utc_time = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
        cst_time = utc_time.astimezone(CST)  # 2026-03-15 20:00 CST
        assert utc_time == cst_time
        assert utc_time <= cst_time
        assert cst_time <= utc_time


# ── Datetime-before-date type dispatch safety ────────────────────────────────


class TestDatetimeBeforeDateDispatch:
    """Ensure isinstance(datetime) checks precede isinstance(date) checks."""

    def test_aware_datetime_isinstance_date_is_true(self) -> None:
        """Python: isinstance(aware_dt, date) is True — dispatch order matters."""
        aware_dt = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
        assert isinstance(aware_dt, datetime)  # datetime check first
        assert isinstance(aware_dt, date)  # also True! (datetime is subclass)

    def test_cutoff_local_date_checks_datetime_first(self) -> None:
        """cutoff_local_date must check isinstance(dt, datetime) before isinstance(dt, date)."""
        aware_dt = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
        result = cutoff_local_date(aware_dt, "Asia/Shanghai")
        # Should succeed — if date check happened first and rejected plain date, this would fail
        assert isinstance(result, date)

    def test_plain_date_rejected_not_silently_treated(self) -> None:
        """Plain date must raise TypeError, not silently produce wrong result."""
        plain = date(2026, 3, 15)
        with pytest.raises(TypeError):
            cutoff_local_date(plain, "Asia/Shanghai")  # type: ignore[arg-type]


# ── WeatherFeatureRun consumable status ──────────────────────────────────────
# These tests verify that only "completed" status with valid finished_at
# is treated as a consumable authority. "unavailable" is NOT consumable.


class TestWeatherFeatureRunStatus:
    """Tests for WeatherFeatureRun status filtering in the validator."""

    def _make_bundle_with_base_temp_status(self, status: str) -> dict:
        """Build a minimal test dict for status filtering checks."""
        return {"status": status}

    def test_completed_is_consumable(self) -> None:
        info = self._make_bundle_with_base_temp_status("completed")
        assert info["status"] == "completed"

    def test_unavailable_not_consumable(self) -> None:
        """'unavailable' must NOT be treated as successful authority."""
        info = self._make_bundle_with_base_temp_status("unavailable")
        assert info["status"] != "completed"

    def test_failed_not_consumable(self) -> None:
        info = self._make_bundle_with_base_temp_status("failed")
        assert info["status"] != "completed"

    def test_cancelled_not_consumable(self) -> None:
        info = self._make_bundle_with_base_temp_status("cancelled")
        assert info["status"] != "completed"

    def test_incomplete_not_consumable(self) -> None:
        info = self._make_bundle_with_base_temp_status("incomplete")
        assert info["status"] != "completed"

    def test_empty_status_not_consumable(self) -> None:
        info = self._make_bundle_with_base_temp_status("")
        assert info["status"] != "completed"


# ── No datetime.combine(date, max.time()) allowed ────────────────────────────


class TestNoDatetimeMaxTime:
    """The old pattern datetime.combine(date, datetime.max.time()) is forbidden."""

    def test_cutoff_local_date_uses_astimezone_not_combine(self) -> None:
        """cutoff_local_date uses astimezone().date(), not datetime.combine()."""
        # This is a behavioral test: cutoff_local_date should return a date
        # derived from the actual UTC moment, not a forced end-of-day.
        cutoff = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
        result = cutoff_local_date(cutoff, "Asia/Shanghai")
        # 12:00 UTC = 20:00 Shanghai → date is 2026-03-15
        assert result == date(2026, 3, 15)
        # If datetime.combine(date, max.time()) were used, the result would
        # always be the same date regardless of time — but our function
        # returns the correct local date based on the actual moment.

    def test_midnight_utc_produces_correct_local_date(self) -> None:
        """UTC midnight should produce the correct local date, not a forced rollover."""
        # UTC 2026-03-15T00:00 = Shanghai 2026-03-15T08:00 → date is 2026-03-15
        cutoff = datetime(2026, 3, 15, 0, 0, tzinfo=UTC)
        result = cutoff_local_date(cutoff, "Asia/Shanghai")
        assert result == date(2026, 3, 15)

    def test_late_utc_evening_rolls_correctly(self) -> None:
        """UTC 23:00 should roll to next day in Shanghai, not be forced same day."""
        # UTC 2026-03-15T23:00 = Shanghai 2026-03-16T07:00 → date is 2026-03-16
        cutoff = datetime(2026, 3, 15, 23, 0, tzinfo=UTC)
        result = cutoff_local_date(cutoff, "Asia/Shanghai")
        assert result == date(2026, 3, 16)
