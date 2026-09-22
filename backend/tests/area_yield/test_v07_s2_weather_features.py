from datetime import date, datetime, timedelta
from decimal import Decimal
from subprocess import run
from sys import executable
from zoneinfo import ZoneInfo

import pytest

from backend.app.area_yield.data import digest
from backend.app.area_yield.weather_features import (
    LANE_A,
    LANE_B,
    LANE_C,
    PRIMARY_FEATURE_COUNT,
    PRIMARY_HORIZONS,
    PRIMARY_WINDOWS_DAYS,
    WEATHER_ROLE,
    WEATHER_SOURCE,
    WeatherDailyObservation,
    WeatherFeatureError,
    build_feature_manifest,
    build_feature_row,
    season_to_date_visible_observations,
    validate_observation_visibility,
    validate_weather_lane,
)

ORIGIN = datetime(2025, 8, 15, tzinfo=ZoneInfo("Asia/Shanghai"))
DATASET_HASH = "a" * 64


def observations(
    *, base_id: str = "base-a", end: date = date(2025, 8, 14)
) -> list[WeatherDailyObservation]:
    rows: list[WeatherDailyObservation] = []
    for offset in range(70):
        day = end - timedelta(days=offset)
        payload = {
            "base_id": base_id,
            "local_date": day.isoformat(),
            "offset": offset,
        }
        rows.append(
            WeatherDailyObservation(
                base_id=base_id,
                local_date=day,
                mean_temperature_c=Decimal("20") + offset,
                tmin_c=Decimal("10") + offset,
                tmax_c=Decimal("30") + offset,
                precipitation_mm=Decimal("1.5"),
                solar_energy_j_m2=Decimal("1000000"),
                wind_speed_m_s=Decimal("2.5"),
                source_row_hash=digest(payload),
                source_dataset_hash=DATASET_HASH,
            )
        )
    return rows


def build(*, rows: list[WeatherDailyObservation] | None = None, origin: datetime = ORIGIN):
    return build_feature_row(
        observations=rows or observations(),
        base_id="base-a",
        forecast_origin=origin,
        target_start=origin.date(),
        target_end=origin.date() + timedelta(days=6),
        source_dataset_hash=DATASET_HASH,
    )


@pytest.mark.unit
def test_primary_feature_policy_is_small_and_explicit() -> None:
    assert PRIMARY_WINDOWS_DAYS == (7, 14, 30)
    assert PRIMARY_HORIZONS == {"H1": 1, "H7": 7, "H15": 15}
    assert PRIMARY_FEATURE_COUNT == 18


@pytest.mark.unit
def test_d_minus_one_weather_is_visible_and_d_plus_one_is_rejected() -> None:
    row = build()
    assert row.feature_window_end == date(2025, 8, 14)
    assert row.max_source_observation_time < row.forecast_origin

    source = observations()[0]
    future = WeatherDailyObservation(
        base_id=source.base_id,
        local_date=date(2025, 8, 16),
        mean_temperature_c=source.mean_temperature_c,
        tmin_c=source.tmin_c,
        tmax_c=source.tmax_c,
        precipitation_mm=source.precipitation_mm,
        solar_energy_j_m2=source.solar_energy_j_m2,
        wind_speed_m_s=source.wind_speed_m_s,
        source_row_hash=source.source_row_hash,
        source_dataset_hash=source.source_dataset_hash,
    )
    with pytest.raises(WeatherFeatureError, match="FUTURE_REALIZED_WEATHER_NOT_VISIBLE"):
        validate_observation_visibility([future], forecast_origin=ORIGIN)


@pytest.mark.unit
def test_feature_row_never_uses_future_weather_and_origin_changes_hash() -> None:
    base_rows = observations()
    first = build(rows=base_rows)
    future = WeatherDailyObservation(
        base_id="base-a",
        local_date=date(2025, 8, 16),
        mean_temperature_c=Decimal("999"),
        tmin_c=Decimal("999"),
        tmax_c=Decimal("999"),
        precipitation_mm=Decimal("999"),
        solar_energy_j_m2=Decimal("999"),
        wind_speed_m_s=Decimal("999"),
        source_row_hash="future-row",
        source_dataset_hash=DATASET_HASH,
    )
    with_future = build(rows=base_rows + [future])
    assert first.feature_hash == with_future.feature_hash

    source = observations()[0]
    previous = WeatherDailyObservation(
        base_id="base-a",
        local_date=date(2025, 8, 15),
        mean_temperature_c=source.mean_temperature_c,
        tmin_c=source.tmin_c,
        tmax_c=source.tmax_c,
        precipitation_mm=source.precipitation_mm,
        solar_energy_j_m2=source.solar_energy_j_m2,
        wind_speed_m_s=source.wind_speed_m_s,
        source_row_hash="previous-row",
        source_dataset_hash=DATASET_HASH,
    )
    shifted_origin = datetime(2025, 8, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
    assert (
        first.feature_hash
        != build(rows=base_rows + [previous, future], origin=shifted_origin).feature_hash
    )


@pytest.mark.unit
def test_season_to_date_view_stops_at_origin_cutoff() -> None:
    visible = season_to_date_visible_observations(
        observations(end=date(2025, 8, 15)),
        season_start=date(2025, 7, 1),
        forecast_origin=ORIGIN,
    )
    assert visible
    assert max(row.local_date for row in visible) == date(2025, 8, 14)
    assert all(row.local_date < ORIGIN.date() for row in visible)


@pytest.mark.unit
def test_incomplete_window_fails_closed_without_zero_fill() -> None:
    rows = observations()
    rows = [row for row in rows if row.local_date != date(2025, 8, 1)]
    with pytest.raises(WeatherFeatureError, match="HISTORICAL_WEATHER_WINDOW_INCOMPLETE"):
        build(rows=rows)


@pytest.mark.unit
def test_weather_lanes_cannot_change_source_semantics() -> None:
    validate_weather_lane(lane=LANE_A, source=WEATHER_SOURCE, role=WEATHER_ROLE)
    validate_weather_lane(
        lane=LANE_C,
        source=WEATHER_SOURCE,
        role=LANE_C,
        research_only=True,
    )
    with pytest.raises(WeatherFeatureError, match="WEATHER_SOURCE_ROLE_MISMATCH"):
        validate_weather_lane(lane=LANE_B, source=WEATHER_SOURCE, role=WEATHER_ROLE)
    with pytest.raises(WeatherFeatureError, match="WEATHER_SOURCE_ROLE_MISMATCH"):
        validate_weather_lane(
            lane=LANE_B,
            source=WEATHER_SOURCE,
            role="AS_ISSUED_FORECAST",
        )
    with pytest.raises(WeatherFeatureError, match="ORACLE_WEATHER_REQUIRES_RESEARCH_ONLY"):
        validate_weather_lane(lane=LANE_C, source=WEATHER_SOURCE, role=LANE_C)


@pytest.mark.unit
def test_same_input_has_same_feature_and_manifest_hash() -> None:
    first = build()
    second = build()
    first_manifest = build_feature_manifest([first], source_dataset_hash=DATASET_HASH)
    second_manifest = build_feature_manifest([second], source_dataset_hash=DATASET_HASH)
    assert first.to_dict() == second.to_dict()
    assert first_manifest == second_manifest


@pytest.mark.unit
def test_non_weather_base_is_not_interpolated() -> None:
    with pytest.raises(WeatherFeatureError, match="HISTORICAL_WEATHER_WINDOW_INCOMPLETE"):
        build(
            rows=[
                row for row in observations(base_id="base-a") if row.local_date != date(2025, 8, 1)
            ]
        )


@pytest.mark.unit
def test_fresh_process_can_load_feature_contract() -> None:
    completed = run(
        [
            executable,
            "-c",
            (
                "from backend.app.area_yield.weather_features import "
                "PRIMARY_FEATURE_COUNT; print(PRIMARY_FEATURE_COUNT)"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.strip() == "18"
