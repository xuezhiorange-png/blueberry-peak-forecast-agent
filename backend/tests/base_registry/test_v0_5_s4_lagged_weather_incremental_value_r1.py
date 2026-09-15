"""Contract tests for the frozen V0.5-S4 matched weather ablation."""

from datetime import date
from decimal import Decimal

import pytest

from scripts.audit_v0_5_s3_training_eligibility_r1 import dates_between, season_window
from scripts.run_v0_5_s4_lagged_weather_incremental_value_r1 import (
    CONTROL_MODEL_ID,
    HORIZONS,
    MODEL_PARAMS,
    REPORT_HORIZONS,
    STRUCTURAL_FEATURE_NAMES,
    WEATHER_FEATURE_NAMES,
    WEATHER_MODEL_ID,
    _weather_feature_vector,
    build_feature_vector,
    build_origin_catalog,
    canonical_number,
    nonnegative_prediction,
    split_base_ids,
    structural_features,
    window_metrics,
    window_records,
)


def _weather_row(day: date, value: str = "10.0") -> dict[str, object]:
    return {
        "local_date": day.isoformat(),
        "local_day_mean_temperature_c": value,
        "sampled_local_day_tmin_c": "5.0",
        "sampled_local_day_tmax_c": "15.0",
        "local_day_precipitation_mm": "1.0",
        "local_day_solar_energy_j_m2": "100.0",
        "local_day_mean_wind_speed_10m_m_s": "2.0",
    }


def _prediction_row(
    model_id: str,
    horizon: int,
    target_day: date,
    actual: str,
    predicted: str,
) -> dict[str, str]:
    return {
        "model_id": model_id,
        "fold_id": "B",
        "base_id": "base-a",
        "season": "2025-2026",
        "origin_id": "base-a|2025-2026|2025-01-01",
        "origin_date": "2025-01-01",
        "target_date": target_day.isoformat(),
        "forecast_horizon_days": str(horizon),
        "target_label_known": "True",
        "actual_kg": actual,
        "predicted_daily_kg": predicted,
    }


def test_frozen_candidates_share_parameters_and_only_weather_adds_features() -> None:
    assert CONTROL_MODEL_ID == "S4_MATCHED_NO_WEATHER_ORIGIN_HORIZON_HGBR_V1"
    assert WEATHER_MODEL_ID == "S4_LAGGED_WEATHER_ORIGIN_HORIZON_HGBR_V1"
    assert REPORT_HORIZONS == (1, 3, 7, 15)
    assert HORIZONS == tuple(range(1, 16))
    assert STRUCTURAL_FEATURE_NAMES == (
        "productive_area_mu",
        "target_business_season_day_index",
        "target_business_season_progress",
        "target_business_season_progress_sin",
        "target_business_season_progress_cos",
        "forecast_horizon_days",
    )
    assert WEATHER_FEATURE_NAMES == (
        "tmean_7d_mean",
        "tmean_14d_mean",
        "tmin_7d_min",
        "tmin_14d_min",
        "tmax_7d_max",
        "tmax_14d_max",
        "precip_7d_sum",
        "precip_14d_sum",
        "solar_7d_sum",
        "solar_14d_sum",
        "wind_7d_mean",
        "wind_14d_mean",
    )
    assert MODEL_PARAMS == {
        "loss": "squared_error",
        "learning_rate": 0.05,
        "max_iter": 300,
        "max_leaf_nodes": 31,
        "max_depth": 6,
        "min_samples_leaf": 10,
        "l2_regularization": 0.1,
        "early_stopping": False,
        "random_state": 20260915,
    }


def test_structural_features_are_deterministic_and_horizon_aware() -> None:
    args = ("2025-2026", date(2025, 9, 1), Decimal("12.5"), 7)
    first = structural_features(*args)
    second = structural_features(*args)

    assert first == second
    assert len(first) == len(STRUCTURAL_FEATURE_NAMES)
    assert first[-1] == 7.0
    assert first != structural_features(args[0], args[1], args[2], 8)


def test_weather_features_use_only_trailing_history_through_origin() -> None:
    origin = date(2025, 8, 20)
    weather = {
        origin.fromordinal(origin.toordinal() - offset): _weather_row(
            origin.fromordinal(origin.toordinal() - offset), value=str(offset)
        )
        for offset in range(13, -1, -1)
    }
    weather[origin.fromordinal(origin.toordinal() + 1)] = _weather_row(
        origin.fromordinal(origin.toordinal() + 1), value="999.0"
    )

    first = _weather_feature_vector(weather, "base-a", origin)
    weather[origin.fromordinal(origin.toordinal() + 1)] = _weather_row(
        origin.fromordinal(origin.toordinal() + 1), value="-999.0"
    )
    second = _weather_feature_vector(weather, "base-a", origin)

    assert first == second
    assert len(first) == len(WEATHER_FEATURE_NAMES)
    missing = dict(weather)
    del missing[origin.fromordinal(origin.toordinal() - 13)]
    with pytest.raises(ValueError, match="incomplete trailing weather history"):
        _weather_feature_vector(missing, "base-a", origin)


def test_build_feature_vector_keeps_control_weather_boundary_explicit() -> None:
    origin = date(2025, 8, 20)
    weather = {
        origin.fromordinal(origin.toordinal() - offset): _weather_row(origin)
        for offset in range(13, -1, -1)
    }
    control = build_feature_vector(
        "2025-2026",
        date(2025, 8, 21),
        Decimal("100"),
        1,
        "base-a",
        origin,
        {"base-a": weather},
        False,
    )
    weather_features = build_feature_vector(
        "2025-2026",
        date(2025, 8, 21),
        Decimal("100"),
        1,
        "base-a",
        origin,
        {"base-a": weather},
        True,
    )
    assert weather_features[: len(control)] == control
    assert len(weather_features) == len(STRUCTURAL_FEATURE_NAMES) + len(WEATHER_FEATURE_NAMES)


def test_origin_catalog_excludes_unlabeled_pairs_and_filters_same_origins() -> None:
    season = "2025-2026"
    start, end = season_window(season)
    weather_by_base = {
        base_id: {day: _weather_row(day) for day in dates_between(start, end)}
        for base_id in ("base-a", "base-b")
    }
    result = build_origin_catalog(
        (season,),
        ("base-a", "base-b"),
        weather_by_base,
        {("base-a", season)},
    )

    assert result["origins"]
    assert {origin["base_id"] for origin in result["origins"]} == {"base-a"}
    assert len(result["pre_by_window"]["W15"]) > len(result["post_by_window"]["W15"])
    assert len(result["filtered_w15"]) > 0
    assert all(
        date.fromisoformat(str(origin["weather_feature_max_date"]))
        <= date.fromisoformat(str(origin["origin_date"]))
        for origin in result["origins"]
    )


def test_split_base_ids_is_deterministic_and_reports_natural_oob() -> None:
    assert split_base_ids({"b", "a"}, {"b", "c"}) == {
        "train": ["a", "b"],
        "validation": ["b", "c"],
        "seen": ["b"],
        "natural_oob": ["c"],
    }


def test_window_peak_uses_earliest_date_on_equal_peak() -> None:
    rows = [
        _prediction_row(CONTROL_MODEL_ID, 1, date(2025, 1, 1), "3.0", "2.0"),
        _prediction_row(CONTROL_MODEL_ID, 2, date(2025, 1, 2), "3.0", "2.0"),
    ]
    rows.extend(
        _prediction_row(CONTROL_MODEL_ID, horizon, date(2025, 1, horizon), "1.0", "1.0")
        for horizon in range(3, 8)
    )

    records = window_records(rows, CONTROL_MODEL_ID, "B", {"base-a"}, 7)

    assert len(records) == 1
    assert records[0]["actual_peak_date"] == "2025-01-01"
    assert records[0]["predicted_peak_date"] == "2025-01-01"


def test_window_metrics_does_not_impute_unknown_target_labels() -> None:
    rows = [
        _prediction_row(
            CONTROL_MODEL_ID,
            horizon,
            date(2025, 1, horizon),
            "1.0" if horizon != 3 else "",
            "1.0",
        )
        for horizon in range(1, 8)
    ]
    for row in rows:
        if row["forecast_horizon_days"] == "3":
            row["target_label_known"] = "False"

    result = window_metrics(rows, CONTROL_MODEL_ID, "B", {"base-a"}, 7)

    assert result["origin_count"] == 0
    assert result["unique_base_count"] == 0
    assert result["macro_base_equal"]["total_wape"] is None


def test_nonnegative_prediction_and_number_serialization_are_fail_closed() -> None:
    assert nonnegative_prediction(-1.0) == (0.0, True)
    assert nonnegative_prediction(1.25) == (1.25, False)
    assert canonical_number(Decimal("1.25")) == "1.250000000000"
    with pytest.raises(ValueError, match="finite"):
        nonnegative_prediction(float("nan"))
