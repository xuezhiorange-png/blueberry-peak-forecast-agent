from datetime import date
from decimal import Decimal

import pytest

from backend.app.forecast_quality.operational_peak import (
    BASELINE_ID,
    COMPUTABLE_FULL_WINDOW,
    NOT_COMPUTABLE_FULL_WINDOW,
    OperationalPeakForecastError,
    OperationalPeakForecastRequest,
    forecast_operational_peak,
    load_frozen_reference_profile,
    nearest_reference_bin,
    summarize_window,
)

REGISTRY = {
    "bases": [
        {
            "base_id": "base-yangliu",
            "canonical_base_name": "保山杨柳基地",
            "productive_area_mu": "394.000000",
            "active": True,
        }
    ]
}
PROFILE = {bin_id: Decimal("1.000000000000") for bin_id in range(42)}


def request(origin: date) -> OperationalPeakForecastRequest:
    return OperationalPeakForecastRequest("base-yangliu", "2026-2027", origin)


def test_april_08_has_complete_w7_but_not_w15() -> None:
    result = forecast_operational_peak(request(date(2027, 4, 8)), REGISTRY, PROFILE)

    assert len(result.daily_forecast) == 7
    assert result.forecast_7d.status == COMPUTABLE_FULL_WINDOW
    assert result.forecast_7d.start_date == date(2027, 4, 9)
    assert result.forecast_7d.end_date == date(2027, 4, 15)
    assert result.forecast_15d.status == NOT_COMPUTABLE_FULL_WINDOW
    assert result.forecast_15d.total_kg is None
    assert result.forecast_15d.peak_date is None


def test_april_10_reports_only_remaining_business_days() -> None:
    result = forecast_operational_peak(request(date(2027, 4, 10)), REGISTRY, PROFILE)

    assert [row.date for row in result.daily_forecast] == [
        date(2027, 4, day) for day in range(11, 16)
    ]
    assert result.forecast_7d.status == NOT_COMPUTABLE_FULL_WINDOW
    assert result.forecast_15d.status == NOT_COMPUTABLE_FULL_WINDOW
    assert result.remaining_business_window.available_days == 5
    assert result.remaining_business_window.total_kg == Decimal("1970.000000")


def test_march_31_has_complete_w15_and_april_01_does_not() -> None:
    march_result = forecast_operational_peak(request(date(2027, 3, 31)), REGISTRY, PROFILE)
    april_result = forecast_operational_peak(request(date(2027, 4, 1)), REGISTRY, PROFILE)

    assert march_result.forecast_15d.status == COMPUTABLE_FULL_WINDOW
    assert march_result.forecast_15d.available_days == 15
    assert april_result.forecast_15d.status == NOT_COMPUTABLE_FULL_WINDOW
    assert april_result.forecast_15d.available_days == 14


def test_peak_tie_break_is_earliest_date_and_window_mass_matches_daily_rows() -> None:
    result = forecast_operational_peak(request(date(2027, 4, 8)), REGISTRY, PROFILE)

    assert result.forecast_7d.peak_date == date(2027, 4, 9)
    assert result.forecast_7d.peak_kg == Decimal("394.000000")
    assert result.forecast_7d.total_kg == sum(
        (row.predicted_kg for row in result.daily_forecast), Decimal(0)
    )


def test_missing_daily_prediction_is_not_shortened_into_a_valid_window() -> None:
    result = forecast_operational_peak(request(date(2027, 4, 8)), REGISTRY, PROFILE)
    incomplete = result.daily_forecast[:-1]

    summary = summarize_window(
        incomplete,
        origin_date=date(2027, 4, 8),
        window_days=7,
        business_start=date(2026, 7, 1),
        business_end=date(2027, 4, 15),
    )

    assert summary.status == NOT_COMPUTABLE_FULL_WINDOW
    assert summary.reason == "MISSING_DAILY_PREDICTION"
    assert summary.total_kg is None
    assert summary.peak_date is None


def test_unregistered_base_fails_closed() -> None:
    with pytest.raises(OperationalPeakForecastError) as error:
        forecast_operational_peak(
            OperationalPeakForecastRequest("unknown-base", "2026-2027", date(2027, 4, 8)),
            REGISTRY,
            PROFILE,
        )

    assert error.value.code == "UNREGISTERED_BASE"


def test_frozen_profile_id_and_nearest_bin_tie_are_deterministic() -> None:
    profile = load_frozen_reference_profile(
        {
            "reference_id": BASELINE_ID,
            "missing_bin_policy": "NEAREST_AVAILABLE_TRAIN_BIN_EARLIER_TIE",
            "validation_labels_used": False,
            "profile_kg_per_mu_by_7_day_bin": {"1": "2.0", "3": "4.0"},
        }
    )
    assert profile == {1: Decimal("2.0"), 3: Decimal("4.0")}
    assert nearest_reference_bin(2, (1, 3)) == 1
    result = forecast_operational_peak(request(date(2027, 4, 8)), REGISTRY, profile)
    assert all(row.reference_bin == 3 for row in result.daily_forecast)


def test_replay_is_deterministic_and_weather_is_explicitly_unused() -> None:
    first = forecast_operational_peak(request(date(2027, 3, 31)), REGISTRY, PROFILE)
    second = forecast_operational_peak(request(date(2027, 3, 31)), REGISTRY, PROFILE)

    assert first.to_mapping() == second.to_mapping()
    assert first.result_hash == second.result_hash
    assert first.weather_used is False
    assert first.weather is None
    assert "full_season_total_kg" not in first.to_mapping()


@pytest.mark.parametrize(
    "bad_season",
    ["2026-2026", "2026-2028", "2026~2027", "not-a-season"],
)
def test_invalid_business_season_fails_closed(bad_season: str) -> None:
    with pytest.raises(OperationalPeakForecastError) as error:
        forecast_operational_peak(
            OperationalPeakForecastRequest("base-yangliu", bad_season, date(2027, 4, 8)),
            REGISTRY,
            PROFILE,
        )
    assert error.value.code == "INVALID_REQUEST"


def test_origin_outside_business_window_fails_closed() -> None:
    with pytest.raises(OperationalPeakForecastError) as error:
        forecast_operational_peak(request(date(2027, 4, 16)), REGISTRY, PROFILE)
    assert error.value.code == "INVALID_REQUEST"
