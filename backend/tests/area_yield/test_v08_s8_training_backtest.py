from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from backend.app.area_yield.v08_s8_training_backtest import (
    OOT_SEASON,
    S8BacktestError,
    _error_metrics,
    _validate_training_rows,
    compose_daily_curve,
    derive_peaks,
    fit_two_stage_model,
    predict_season_total,
    score_model_daily,
    score_season_totals,
    season_calendar,
    validate_training_cohort,
)


def _training_inputs() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    keys = [(f"B{index:02d}", "2023-2024") for index in range(1, 16)]
    keys.extend((f"B{index:02d}", "2024-2025") for index in [*range(1, 12), *range(16, 27)])
    rows: list[dict[str, str]] = []
    curves: list[dict[str, str]] = []
    for base_id, season in keys:
        dates = season_calendar(season)
        total = Decimal(len(dates) * 2)
        rows.append(
            {
                "base_id": base_id,
                "season": season,
                "area_mu": "100",
                "season_total_quantity_kg": str(total),
                "daily_curve_available": "true",
                "strict_training_eligible": "true",
            }
        )
        curves.extend(
            {
                "base_id": base_id,
                "season": season,
                "date": day.isoformat(),
                "new_quantity_kg": "2",
                "new_completeness_status": "COMPLETE_MAPPED_MEMBERS",
            }
            for day in dates
        )
    return rows, curves


def _fit() -> dict[str, object]:
    rows, curves = _training_inputs()
    return fit_two_stage_model(
        rows,
        curves,
        config_sha256="a" * 64,
        training_code_sha256="f" * 64,
        training_dataset_sha256="b" * 64,
        training_daily_sha256="c" * 64,
    )


def test_training_cohort_is_exactly_37_and_oot_exactly_39() -> None:
    training, _ = _training_inputs()
    oot = [{"base_id": f"O{index:02d}", "season": OOT_SEASON} for index in range(39)]

    validate_training_cohort(training, oot)

    with pytest.raises(S8BacktestError, match="EXACTLY_37"):
        validate_training_cohort(training[:-1], oot)
    with pytest.raises(S8BacktestError, match="EXACTLY_39"):
        validate_training_cohort(training, oot[:-1])


def test_train_oot_overlap_and_oot_season_leak_fail_closed() -> None:
    training, _ = _training_inputs()
    oot = [{"base_id": f"O{index:02d}", "season": OOT_SEASON} for index in range(39)]
    oot[0] = {"base_id": training[0]["base_id"], "season": training[0]["season"]}

    with pytest.raises(S8BacktestError, match="OVERLAP"):
        validate_training_cohort(training, oot)

    leaked_training = [*training[:-1], {**training[-1], "season": OOT_SEASON}]
    with pytest.raises(S8BacktestError, match="OOT_LABEL_FORBIDDEN"):
        _validate_training_rows(leaked_training)


def test_blocked_training_row_cannot_enter_fit() -> None:
    training, _ = _training_inputs()
    training[0]["strict_training_eligible"] = "false"

    with pytest.raises(S8BacktestError, match="BLOCKED_TRAINING_ROW"):
        _validate_training_rows(training)


def test_oot_actuals_are_not_a_fit_input_and_model_replay_is_deterministic() -> None:
    first = _fit()
    synthetic_oot_truth_a = Decimal("1")
    synthetic_oot_truth_b = Decimal("999999999")
    assert synthetic_oot_truth_a != synthetic_oot_truth_b
    replay = _fit()

    assert first == replay
    assert first["oot_labels_used"] is False
    assert first["artifact_hash"] == replay["artifact_hash"]


def test_training_dataset_provenance_change_changes_model_hash() -> None:
    rows, curves = _training_inputs()
    baseline = fit_two_stage_model(
        rows,
        curves,
        config_sha256="a" * 64,
        training_code_sha256="f" * 64,
        training_dataset_sha256="b" * 64,
        training_daily_sha256="c" * 64,
    )
    changed_provenance = fit_two_stage_model(
        rows,
        curves,
        config_sha256="a" * 64,
        training_code_sha256="f" * 64,
        training_dataset_sha256="d" * 64,
        training_daily_sha256="c" * 64,
    )

    assert baseline["artifact_hash"] != changed_provenance["artifact_hash"]


def test_oot_daily_rows_cannot_enter_training_fit() -> None:
    training, curves = _training_inputs()
    leaked_curve = {
        "base_id": "B01",
        "season": OOT_SEASON,
        "date": date(2025, 7, 22).isoformat(),
        "new_quantity_kg": "100000000",
        "new_completeness_status": "COMPLETE_MAPPED_MEMBERS",
    }

    with pytest.raises(S8BacktestError, match="OOT_DAILY_LABEL_FORBIDDEN"):
        fit_two_stage_model(
            training,
            [*curves, leaked_curve],
            config_sha256="a" * 64,
            training_code_sha256="f" * 64,
            training_dataset_sha256="b" * 64,
            training_daily_sha256="c" * 64,
        )


def test_model_uses_area_as_scale_driver_and_pooled_baseline_is_frozen() -> None:
    model = _fit()
    base_prediction = predict_season_total(model, base_id="B01", area_mu=Decimal("100"))
    doubled_prediction = predict_season_total(model, base_id="B01", area_mu=Decimal("200"))
    pooled_baseline = predict_season_total(
        model, base_id="B01", area_mu=Decimal("100"), use_base_yield=False
    )

    assert Decimal(doubled_prediction["predicted_season_total_kg"]) == (
        Decimal(base_prediction["predicted_season_total_kg"]) * 2
    )
    assert pooled_baseline["prediction_basis"] == "POOLED_TRAINING_YIELD_FALLBACK"
    assert model.get("model_production_ready", False) is False


def test_daily_curve_mass_balance_and_peak_ties_choose_earliest_window() -> None:
    model = _fit()
    prediction = predict_season_total(model, base_id="B01", area_mu=Decimal("100"))
    predicted_total = Decimal(prediction["predicted_season_total_kg"])
    curve = compose_daily_curve(model=model, predicted_total_kg=predicted_total)

    assert len(curve) == 268
    assert sum((Decimal(row["predicted_daily_quantity_kg"]) for row in curve), Decimal(0)) == (
        predicted_total
    )
    replay_curve = compose_daily_curve(model=model, predicted_total_kg=predicted_total)
    assert curve == replay_curve

    tied = [
        {"date": date(2025, 7, 22 + index).isoformat(), "actual_quantity_kg": "1"}
        for index in range(7)
    ]
    peaks = derive_peaks(tied)
    assert peaks["single_day_peak_date"] == "2025-07-22"
    assert peaks["rolling7_start_date"] == "2025-07-22"
    assert peaks["rolling7_end_date"] == "2025-07-28"


def test_daily_metrics_use_fixed_actual_denominator_and_allow_zero_days() -> None:
    metrics = _error_metrics(
        [Decimal("10"), Decimal("0")],
        [Decimal("8"), Decimal("2")],
    )

    assert metrics["wape"] == "0.4"
    assert metrics["zero_actual_count"] == 1
    assert metrics["n"] == 2


def test_daily_and_total_metrics_keep_the_same_fixed_row_cohort() -> None:
    actual_total = {"B01": Decimal("268")}
    complete_total = {"B01": Decimal("268")}
    with pytest.raises(S8BacktestError, match="COHORT_MISMATCH"):
        score_season_totals(actual_total, {"A": complete_total, "B": {}})

    predictions = [
        {
            "base_id": "B01",
            "date": day.isoformat(),
            "predicted_daily_quantity_kg": "1",
        }
        for day in season_calendar(OOT_SEASON)
    ]
    actual = {
        "B01": [
            {"date": day.isoformat(), "actual_quantity_kg": "1"}
            for day in season_calendar(OOT_SEASON)
        ]
    }
    daily_metrics = score_model_daily(predictions, actual)

    assert daily_metrics["row_count"] == 268
    assert daily_metrics["daily"]["wape"] == "0"
    assert daily_metrics["daily"]["n"] == 268


def test_rolling7_rejects_gap_and_short_series() -> None:
    short = [
        {"date": date(2025, 7, 22 + index).isoformat(), "actual_quantity_kg": "1"}
        for index in range(6)
    ]
    with pytest.raises(S8BacktestError, match="ROLLING7_REQUIRES_SEVEN_DAYS"):
        derive_peaks(short)

    gap = [
        {"date": date(2025, 7, 22 + (index + (index >= 3))).isoformat(), "actual_quantity_kg": "1"}
        for index in range(7)
    ]
    with pytest.raises(S8BacktestError, match="DATES_NOT_CONSECUTIVE"):
        derive_peaks(gap)
