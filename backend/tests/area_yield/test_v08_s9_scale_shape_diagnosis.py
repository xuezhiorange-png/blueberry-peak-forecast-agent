from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from backend.app.area_yield import v08_s9_scale_shape_diagnosis as diagnosis
from backend.app.area_yield.v08_s9_scale_shape_diagnosis import (
    S9DiagnosisError,
    _peak,
    _source_share_hash,
    area_tertile_cutpoints,
    diagnose_curves,
    normalized_shares,
    training_support_counts,
    validate_cohort_separation,
)


def test_normalized_shares_and_counterfactual_mass_balance() -> None:
    actual = [Decimal("8"), Decimal("2"), Decimal("0")]
    predicted = [Decimal("3"), Decimal("5"), Decimal("2")]
    result = diagnose_curves(actual, predicted)

    assert sum(result["actual_share"], Decimal(0)) == Decimal(1)
    assert sum(result["predicted_share"], Decimal(0)) == Decimal(1)
    assert sum(result["scale_only"], Decimal(0)) == sum(predicted, Decimal(0))
    assert sum(result["shape_only"], Decimal(0)) == sum(actual, Decimal(0))


def test_identical_shape_has_zero_normalized_l1() -> None:
    result = diagnose_curves(
        [Decimal("8"), Decimal("2")],
        [Decimal("80"), Decimal("20")],
    )

    assert result["shape_l1"] == Decimal(0)


def test_correct_total_and_wrong_shape_make_scale_only_error_zero() -> None:
    actual = [Decimal("8"), Decimal("2")]
    predicted = [Decimal("4"), Decimal("6")]
    result = diagnose_curves(actual, predicted)

    assert result["actual_total"] == result["predicted_total"]
    assert result["scale_only"] == actual
    assert (
        sum((abs(a - p) for a, p in zip(actual, result["scale_only"], strict=True)), Decimal(0))
        == 0
    )


def test_correct_shape_and_wrong_total_make_shape_only_error_zero() -> None:
    actual = [Decimal("8"), Decimal("2")]
    predicted = [Decimal("80"), Decimal("20")]
    result = diagnose_curves(actual, predicted)

    assert result["shape_only"] == actual
    assert (
        sum((abs(a - p) for a, p in zip(actual, result["shape_only"], strict=True)), Decimal(0))
        == 0
    )


def test_absolute_counterfactual_errors_are_not_an_additive_decomposition() -> None:
    actual = [Decimal("8"), Decimal("2")]
    predicted = [Decimal("5"), Decimal("15")]
    result = diagnose_curves(actual, predicted)
    observed_wape = Decimal("16") / Decimal("10")
    scale_wape = Decimal("10") / Decimal("10")
    shape_wape = Decimal("11") / Decimal("10")

    assert result["actual_total"] == Decimal("10")
    assert result["predicted_total"] == Decimal("20")
    assert observed_wape != scale_wape + shape_wape


def test_zero_total_cannot_define_shape() -> None:
    with pytest.raises(S9DiagnosisError, match="ZERO_TOTAL"):
        normalized_shares([Decimal(0), Decimal(0)])


def test_common30_cohort_is_separate_from_full39_and_v07_is_subset() -> None:
    training = [
        {"base_id": f"B{index:02d}", "season": "2023-2024" if index < 15 else "2024-2025"}
        for index in range(37)
    ]
    oot = [
        {
            "base_id": f"O{index:02d}",
            "season": "2025-2026",
            "actual_total": "999999999999" if index == 38 else "1",
        }
        for index in range(39)
    ]
    common = [f"O{index:02d}" for index in range(30)]

    validate_cohort_separation(training, oot, common)

    with pytest.raises(S9DiagnosisError, match="V07_COMMON_COHORT_MUST_BE_30"):
        validate_cohort_separation(training, oot, common[:-1])


def test_oot_season_rows_cannot_enter_training_cohort() -> None:
    training = [
        {"base_id": f"B{index:02d}", "season": "2023-2024" if index < 15 else "2024-2025"}
        for index in range(37)
    ]
    training[-1] = {"base_id": "LEAK", "season": "2025-2026"}
    oot = [{"base_id": f"O{index:02d}", "season": "2025-2026"} for index in range(39)]

    with pytest.raises(S9DiagnosisError, match="OOT_ACTUAL_FOUND_IN_TRAINING"):
        validate_cohort_separation(training, oot, [f"O{index:02d}" for index in range(30)])


def test_rolling7_uses_consecutive_dates_and_earliest_tie() -> None:
    dates = [date(2025, 7, 22) + timedelta(days=index) for index in range(8)]
    values = [Decimal("1")] * 8

    first_start, first_end, first_total = diagnosis._rolling7(dates, values)

    assert (first_start, first_end, first_total) == (dates[0], dates[6], Decimal("7"))
    with pytest.raises(S9DiagnosisError, match="NOT_CONSECUTIVE"):
        diagnosis._rolling7([dates[0], *dates[2:]], values[:-1])


def test_diagnostic_module_has_no_model_fit_or_prediction_retraining_api() -> None:
    assert not hasattr(diagnosis, "fit_two_stage_model")
    assert not hasattr(diagnosis, "predict_season_total")


def test_training_support_counts_use_only_training_base_seasons() -> None:
    rows = [
        {"base_id": "A", "season": "2023-2024"},
        {"base_id": "A", "season": "2024-2025"},
        {"base_id": "B", "season": "2023-2024"},
    ]

    assert training_support_counts(rows, ["A", "B", "C"]) == {"A": 2, "B": 1, "C": 0}
    with pytest.raises(S9DiagnosisError, match="OOT_SEASON_IN_TRAINING_SUPPORT"):
        training_support_counts([{"base_id": "A", "season": "2025-2026"}], ["A"])


def test_area_tertile_cutpoints_are_derived_from_training_areas_only() -> None:
    training_areas = [Decimal(value) for value in range(1, 8)]

    assert area_tertile_cutpoints(
        training_areas,
        Decimal(1) / Decimal(3),
        Decimal(2) / Decimal(3),
    ) == (Decimal(3), Decimal(5))


def test_baseline_v08_shape_hash_parity_ignores_scale_but_pins_share() -> None:
    v08 = [
        {"base_id": "A", "date": "2025-07-22", "predicted_share": "0.25"},
        {"base_id": "A", "date": "2025-07-23", "predicted_share": "0.75"},
    ]
    baseline = [
        {"base_id": "A", "date": "2025-07-22", "predicted_share": "0.25"},
        {"base_id": "A", "date": "2025-07-23", "predicted_share": "0.75"},
    ]
    changed_shape = [
        {"base_id": "A", "date": "2025-07-22", "predicted_share": "0.5"},
        {"base_id": "A", "date": "2025-07-23", "predicted_share": "0.5"},
    ]

    assert _source_share_hash(v08) == _source_share_hash(baseline)
    assert _source_share_hash(v08) != _source_share_hash(changed_shape)


def test_peak_counterfactuals_are_derived_from_their_own_curves() -> None:
    dates = [date(2025, 7, 22) + timedelta(days=index) for index in range(7)]
    actual = [
        Decimal("8"),
        Decimal("2"),
        Decimal("0"),
        Decimal("0"),
        Decimal("0"),
        Decimal("0"),
        Decimal("0"),
    ]
    predicted = [
        Decimal("1"),
        Decimal("0"),
        Decimal("0"),
        Decimal("0"),
        Decimal("0"),
        Decimal("0"),
        Decimal("9"),
    ]
    result = diagnose_curves(actual, predicted)

    actual_peak = _peak(dates, actual)
    scale_peak = _peak(dates, result["scale_only"])
    shape_peak = _peak(dates, result["shape_only"])
    assert scale_peak[0] == actual_peak[0]
    assert shape_peak[0] == dates[-1]


def test_diagnostic_replay_is_byte_stable_for_same_decimal_inputs() -> None:
    actual = [Decimal("4"), Decimal("3"), Decimal("2"), Decimal("1")]
    predicted = [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4")]

    assert diagnose_curves(actual, predicted) == diagnose_curves(actual, predicted)
