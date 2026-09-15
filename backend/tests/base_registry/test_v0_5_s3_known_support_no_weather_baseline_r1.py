"""Tests for the frozen known-support no-weather S3 baseline."""

from datetime import date
from decimal import Decimal

import pytest

from scripts.run_v0_5_s3_known_support_no_weather_baseline_r1 import (
    FEATURE_NAMES,
    FOLD_DEFINITIONS,
    MODEL_ID,
    REFERENCE_ID,
    SUPPORT_COUNTS,
    _daily_metrics,
    _evaluate_source,
    build_week_median_reference,
    canonical_number,
    feature_values,
    nearest_available_bin,
    nonnegative_prediction,
    split_base_ids,
    window_peak,
)


def _base(base_id: str, area: str = "100.000000") -> dict[str, object]:
    return {
        "base_id": base_id,
        "canonical_base_name": base_id,
        "productive_area_mu": area,
    }


def _label(
    base_id: str,
    season: str,
    day: str,
    quantity: str,
) -> dict[str, object]:
    return {
        "base_id": base_id,
        "season": season,
        "date": day,
        "label_known": True,
        "observed_harvest_kg": quantity,
    }


def test_frozen_model_and_features_have_no_weather_or_future_target_fields() -> None:
    assert MODEL_ID == "NO_WEATHER_HGBR_DAILY_V1"
    assert REFERENCE_ID == "AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1"
    assert FEATURE_NAMES == (
        "productive_area_mu",
        "business_season_day_index",
        "business_season_progress",
        "business_season_progress_sin",
        "business_season_progress_cos",
    )
    assert all("weather" not in name for name in FEATURE_NAMES)
    assert all("harvest" not in name and "target" not in name for name in FEATURE_NAMES)


def test_feature_values_are_deterministic_calendar_features() -> None:
    first = feature_values("2024-2025", date(2024, 7, 1), Decimal("12.5"))
    second = feature_values("2024-2025", date(2024, 7, 1), Decimal("12.5"))

    assert first == second
    assert first[0] == 12.5
    assert first[1] == 0.0
    assert first[2] == 0.0
    assert first[3] == 0.0
    assert first[4] == 1.0


def test_reference_is_base_equal_and_missing_bins_use_frozen_nearest_policy() -> None:
    train_rows = [
        _label("a", "2023-2024", "2023-07-01", "100.000000"),
        _label("a", "2023-2024", "2023-07-02", "200.000000"),
        _label("b", "2023-2024", "2023-07-01", "300.000000"),
    ]
    bases = {"a": _base("a"), "b": _base("b")}

    reference = build_week_median_reference(train_rows, bases)

    # Per-base means are 1.5 and 3.0 kg/mu; their median is 2.25.
    assert reference[0] == pytest.approx(2.25)
    assert nearest_available_bin(0, [3, 5]) == 3
    assert nearest_available_bin(4, [3, 5]) == 3


def test_area_prediction_projects_negative_values_to_zero_without_rounding_positive() -> None:
    assert nonnegative_prediction(-0.5) == (0.0, True)
    assert nonnegative_prediction(12.345678901234) == (12.345678901234, False)


def test_base_split_is_explicit_seen_and_natural_oob() -> None:
    train, validation = {"a", "b"}, {"b", "c"}

    result = split_base_ids(train, validation)

    assert result == {
        "train": ["a", "b"],
        "validation": ["b", "c"],
        "seen": ["b"],
        "natural_oob": ["c"],
    }


def test_window_peak_uses_earliest_date_on_tie() -> None:
    rows = [
        {"date": "2025-01-02", "value": "3.000000"},
        {"date": "2025-01-01", "value": "3.000000"},
    ]

    assert window_peak(rows) == ("2025-01-01", Decimal("3.000000"))


def test_canonical_number_is_fixed_and_finite() -> None:
    assert canonical_number(Decimal("1.230000")) == "1.230000000000"
    with pytest.raises(ValueError, match="finite"):
        canonical_number(float("nan"))


def test_r3_corrected_scope_keeps_all_39_bases_and_14_natural_oob() -> None:
    fold_b = next(fold for fold in FOLD_DEFINITIONS if fold["fold_id"] == "B")

    assert SUPPORT_COUNTS["2025-2026"] == {"daily": 8892, "W7": 8346, "W15": 8034}
    assert fold_b["expected_validation_base_count"] == 39
    assert fold_b["expected_natural_oob_base_count"] == 14


def test_daily_metrics_reports_base_equal_bias_and_pooled_diagnostic() -> None:
    rows = [
        {
            "model_id": MODEL_ID,
            "base_id": "base-a",
            "label_known": "True",
            "predicted_daily_kg": "3.000000",
            "actual_kg": "1.000000",
        },
        {
            "model_id": MODEL_ID,
            "base_id": "base-a",
            "label_known": "True",
            "predicted_daily_kg": "1.000000",
            "actual_kg": "1.000000",
        },
        {
            "model_id": MODEL_ID,
            "base_id": "base-b",
            "label_known": "True",
            "predicted_daily_kg": "2.000000",
            "actual_kg": "4.000000",
        },
    ]

    result = _daily_metrics(rows, MODEL_ID, {"base-a", "base-b"})

    assert result["unique_base_count"] == 2
    assert result["macro_base_equal"]["mae_kg"] == pytest.approx(1.5)
    assert result["macro_base_equal"]["wape"] == pytest.approx(0.75)
    assert result["macro_base_equal"]["bias_kg"] == pytest.approx(-0.5)
    assert result["row_pooled_diagnostic"]["mae_kg"] == pytest.approx(4 / 3)
    assert result["row_pooled_diagnostic"]["bias_kg"] == pytest.approx(0.0)


def test_evaluation_reports_38_base_weather_common_subset_separately() -> None:
    rows = [
        {
            "model_id": MODEL_ID,
            "fold_id": "B",
            "base_id": "base-a",
            "season": "2025-2026",
            "target_date": "2025-07-01",
            "label_known": "True",
            "predicted_daily_kg": "2.000000",
            "actual_kg": "1.000000",
        },
        {
            "model_id": MODEL_ID,
            "fold_id": "B",
            "base_id": "base-b",
            "season": "2025-2026",
            "target_date": "2025-07-01",
            "label_known": "True",
            "predicted_daily_kg": "2.000000",
            "actual_kg": "1.000000",
        },
    ]
    fold = {"fold_id": "B", "validation_seasons": ["2025-2026"]}
    split = split_base_ids({"base-a"}, {"base-a", "base-b"})

    result = _evaluate_source(rows, MODEL_ID, fold, split, [], {"base-a"})

    assert result["all"]["base_ids"] == ["base-a", "base-b"]
    assert result["common_weather_scope"]["base_ids"] == ["base-a"]
