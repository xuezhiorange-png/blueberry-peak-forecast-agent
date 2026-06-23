from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from backend.app.models.weather import WeatherDailyObservation
from backend.app.weather.config import (
    FeatureRules,
    MappingRules,
    SearchRules,
    WeatherFeatureConfig,
    WeatherFeatureRules,
)
from backend.app.weather.schemas import (
    BaseTemperatureCandidateScore,
    PhenologyTimeline,
    WeatherFeatureExecutionResult,
    WeatherSourceSelection,
    WeatherWindowFeature,
)
from backend.app.weather.service import (
    WeatherDataVersionConflictError,
    _candidate_scores_payload,
    _select_visible_observation_per_day,
    _window_feature_from_observations,
)


def _config() -> WeatherFeatureConfig:
    return WeatherFeatureConfig(
        rules=WeatherFeatureRules(
            mapping=MappingRules(
                provider_priorities={"synthetic_station": 0},
                location_type_priorities={"station": 0, "grid": 1},
                maximum_mapping_distance_km=Decimal("150"),
                altitude_penalty_weight=Decimal("0.25"),
                missing_altitude_penalty=Decimal("5"),
                high_confidence_max_score=Decimal("10"),
                medium_confidence_max_score=Decimal("30"),
            ),
            features=FeatureRules(
                version="task7-v1",
                rainy_day_threshold_mm=Decimal("1"),
                rolling_windows=(7, 14, 21),
                minimum_coverage_ratio=Decimal("0.85"),
            ),
            search=SearchRules(
                base_temperature_candidates=(Decimal("2"), Decimal("4")),
                minimum_training_sample_count=3,
                minimum_distinct_season_count=2,
                scoring_method="season_loso_mae_days",
                tie_break_rule="mae_then_temperature",
            ),
        ),
        config_hash="cfg",
        snapshot={},
    )


def _obs(
    *,
    obs_id: int,
    obs_date: date,
    available_at: date,
    source_version: str,
    mean: str,
    row_hash: str,
) -> WeatherDailyObservation:
    return WeatherDailyObservation(
        id=obs_id,
        weather_source_location_id=1,
        observation_date=obs_date,
        temperature_min_c=Decimal("10"),
        temperature_max_c=Decimal("20"),
        temperature_mean_c=Decimal(mean),
        temperature_mean_source="provided",
        precipitation_mm=Decimal("0"),
        solar_radiation_mj_m2=Decimal("12"),
        provider_code="synthetic_station",
        source_version=source_version,
        available_at=available_at,
        quality_code="ok",
        quality_flags=["ok"],
        source_file_sha256=None,
        source_row_number=None,
        row_hash=row_hash,
    )


def _selection(
    day: int,
    *,
    mean_c: str,
    min_c: str = "10",
    max_c: str = "20",
    rain_mm: str = "0",
    solar: str | None = "12",
) -> WeatherSourceSelection:
    return WeatherSourceSelection(
        observation_date=date(2026, 2, day),
        observation_id=day,
        weather_source_location_id=1,
        provider_code="synthetic_station",
        source_version="v1",
        available_at=date(2026, 2, day),
        temperature_min_c=Decimal(min_c),
        temperature_max_c=Decimal(max_c),
        temperature_mean_c=Decimal(mean_c),
        precipitation_mm=Decimal(rain_mm),
        solar_radiation_mj_m2=None if solar is None else Decimal(solar),
        quality_code="ok",
        quality_flags=("ok",),
    )


def test_select_visible_observation_uses_latest_available_version() -> None:
    rows = [
        _obs(
            obs_id=1,
            obs_date=date(2026, 2, 1),
            available_at=date(2026, 2, 2),
            source_version="v1",
            mean="12",
            row_hash="a",
        ),
        _obs(
            obs_id=2,
            obs_date=date(2026, 2, 1),
            available_at=date(2026, 2, 3),
            source_version="v2",
            mean="13",
            row_hash="b",
        ),
    ]

    selected = _select_visible_observation_per_day(rows)

    assert len(selected) == 1
    assert selected[0].observation_id == 2
    assert selected[0].temperature_mean_c == Decimal("13")


def test_select_visible_observation_raises_on_same_priority_conflict() -> None:
    rows = [
        _obs(
            obs_id=1,
            obs_date=date(2026, 2, 1),
            available_at=date(2026, 2, 3),
            source_version="v2",
            mean="13",
            row_hash="a",
        ),
        _obs(
            obs_id=2,
            obs_date=date(2026, 2, 1),
            available_at=date(2026, 2, 3),
            source_version="v2",
            mean="14",
            row_hash="b",
        ),
    ]

    with pytest.raises(WeatherDataVersionConflictError, match="conflicting weather observations"):
        _select_visible_observation_per_day(rows)


def test_window_feature_computes_expected_metrics_for_available_window() -> None:
    observations = {
        date(2026, 2, 1): _selection(1, mean_c="12", min_c="8", max_c="16", rain_mm="0"),
        date(2026, 2, 2): _selection(2, mean_c="14", min_c="9", max_c="19", rain_mm="2"),
        date(2026, 2, 3): _selection(3, mean_c="16", min_c="10", max_c="22", rain_mm="3"),
        date(2026, 2, 4): _selection(4, mean_c="15", min_c="11", max_c="21", rain_mm="0"),
        date(2026, 2, 5): _selection(5, mean_c="13", min_c="8", max_c="18", rain_mm="5"),
        date(2026, 2, 6): _selection(6, mean_c="11", min_c="7", max_c="15", rain_mm="0"),
        date(2026, 2, 7): _selection(7, mean_c="10", min_c="6", max_c="14", rain_mm="1"),
    }

    feature = _window_feature_from_observations(
        observations_by_date=observations,
        feature_date=date(2026, 2, 7),
        window_days=7,
        base_temperature=Decimal("5"),
        config=_config(),
    )

    assert feature.status == "available"
    assert feature.observed_day_count == 7
    assert feature.expected_day_count == 7
    assert feature.coverage_ratio == Decimal("1.000000")
    assert feature.effective_temperature_sum == Decimal("56.000000")
    assert feature.precipitation_sum == Decimal("11.000000")
    assert feature.minimum_temperature == Decimal("6.000000")
    assert feature.mean_diurnal_temperature_range == Decimal("9.428571")
    assert feature.maximum_consecutive_rainy_days == 2


def test_window_feature_marks_missing_days_unavailable_without_zero_fill() -> None:
    observations = {
        date(2026, 2, 1): _selection(1, mean_c="12"),
        date(2026, 2, 2): _selection(2, mean_c="14"),
        date(2026, 2, 3): _selection(3, mean_c="16"),
        date(2026, 2, 4): _selection(4, mean_c="15", solar=None),
        date(2026, 2, 6): _selection(6, mean_c="11"),
        date(2026, 2, 7): _selection(7, mean_c="10"),
    }

    feature = _window_feature_from_observations(
        observations_by_date=observations,
        feature_date=date(2026, 2, 7),
        window_days=7,
        base_temperature=Decimal("5"),
        config=_config(),
    )

    assert feature.status == "unavailable"
    assert feature.coverage_ratio == Decimal("0.714286")
    assert feature.effective_temperature_sum is None
    assert feature.missing_dates == (date(2026, 2, 4), date(2026, 2, 5))


def test_execution_result_copy_preserves_nested_weather_dataclasses() -> None:
    feature = WeatherWindowFeature(
        window_days=7,
        status="available",
        effective_temperature_sum=Decimal("10"),
        solar_radiation_sum=Decimal("20"),
        precipitation_sum=Decimal("1"),
        minimum_temperature=Decimal("5"),
        mean_diurnal_temperature_range=Decimal("6"),
        maximum_consecutive_rainy_days=2,
        observed_day_count=7,
        expected_day_count=7,
        coverage_ratio=Decimal("1"),
        missing_dates=(),
        quality_flags=("ok",),
        source_observation_ids=(1, 2),
    )
    timeline = PhenologyTimeline(
        plan_id=1,
        plan_version=2,
        pruning_date=date(2026, 1, 1),
        flowering_start_date=date(2026, 2, 1),
        flowering_peak_date=date(2026, 2, 5),
        flowering_end_date=date(2026, 2, 10),
        first_pick_date=date(2026, 3, 1),
        days_since_pruning=31,
        days_since_flowering_start=0,
        days_since_flowering_peak=-4,
        days_since_flowering_end=-9,
        days_until_first_pick=28,
        anchor_event="flowering_start_date",
        anchor_date=date(2026, 2, 1),
        cumulative_effective_temperature=Decimal("12"),
        cumulative_expected_day_count=1,
        cumulative_observed_day_count=1,
        cumulative_coverage_ratio=Decimal("1"),
        cumulative_missing_dates=(),
        selected_weather_mapping_id=3,
        weather_feature_version="task7-v1",
        warnings=(),
    )
    result = WeatherFeatureExecutionResult(
        status="completed",
        run_id=None,
        source_signature="sig",
        feature_version="task7-v1",
        config_hash="cfg",
        mapping={"mapping_method": "nearest_station"},
        weather_source_version="dataset-v1",
        plan={"plan_id": 1},
        windows=(feature,),
        timeline=timeline,
        weather_observation_ids=(1, 2),
        warnings=(),
        blockers=(),
        input_snapshot={"feature_date": "2026-02-01"},
    )

    copied = replace(result, run_id=7)

    assert isinstance(copied.windows, tuple)
    assert isinstance(copied.windows[0], WeatherWindowFeature)
    assert isinstance(copied.timeline, PhenologyTimeline)


def _assert_json_native(value: object) -> None:
    if value is None or isinstance(value, (str, int, bool)):
        return
    if isinstance(value, list):
        for item in value:
            _assert_json_native(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            assert isinstance(key, str)
            _assert_json_native(item)
        return
    raise AssertionError(f"non-JSON-native value: {type(value).__name__}: {value!r}")


def test_candidate_scores_payload_canonicalizes_for_jsonb() -> None:
    scores = (
        BaseTemperatureCandidateScore(
            base_temperature=Decimal("5.0"),
            fold_count=3,
            evaluated_sample_count=3,
            mae_days=Decimal("1.250000"),
        ),
    )

    payload = _candidate_scores_payload(scores)

    assert payload == {
        "candidates": [
            {
                "base_temperature": "5",
                "fold_count": 3,
                "evaluated_sample_count": 3,
                "mae_days": "1.250000",
                "warnings": [],
            }
        ]
    }
    _assert_json_native(payload)
    json.dumps(payload)
