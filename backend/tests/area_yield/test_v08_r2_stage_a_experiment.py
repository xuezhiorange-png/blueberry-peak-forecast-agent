from __future__ import annotations

from decimal import Decimal

import pytest

from backend.app.area_yield.v08_r2_stage_a import (
    R2ExperimentError,
    fit_stage_a,
    grouped_leave_one_base_out_folds,
    pooled_training_yield,
    predict_yield,
    run_grouped_cv,
    select_cv_candidate,
    stage_b_shape_hash,
    validate_peak_date_invariance,
    validate_training_dataset_hash,
    validate_training_rows,
)


def _rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for base, yields in (("A", ("100", "200")), ("B", ("300",)), ("C", ("500",))):
        seasons = ("2023-2024", "2024-2025")
        for index, yield_value in enumerate(yields):
            area = Decimal("100")
            total = area * Decimal(yield_value)
            rows.append(
                {
                    "base_id": base,
                    "canonical_base_name": base,
                    "season": seasons[index],
                    "area_mu": str(area),
                    "season_total_quantity_kg": str(total),
                    "yield_kg_per_mu": yield_value,
                    "strict_training_eligible": "true",
                    "daily_curve_available": "true",
                }
            )
    return rows


def _full_training_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    season_bases = {
        "2023-2024": [f"B{index:02d}" for index in range(15)],
        "2024-2025": [
            *[f"B{index:02d}" for index in range(11)],
            *[f"B{index:02d}" for index in range(15, 26)],
        ],
    }
    for season, bases in season_bases.items():
        for base_index, base in enumerate(bases):
            area = Decimal(100 + base_index)
            yield_value = Decimal(300 + 13 * base_index + (100 if season == "2024-2025" else 0))
            rows.append(
                {
                    "base_id": base,
                    "canonical_base_name": base,
                    "season": season,
                    "area_mu": str(area),
                    "season_total_quantity_kg": str(area * yield_value),
                    "yield_kg_per_mu": str(yield_value),
                    "strict_training_eligible": "true",
                    "daily_curve_available": "true",
                }
            )
    return rows


def test_grouped_leave_one_base_out_never_splits_same_base() -> None:
    rows = _rows()
    folds = grouped_leave_one_base_out_folds(rows)
    assert len(folds) == 3
    for fold in folds:
        validation = set(fold["validation_base_ids"])
        training = set(fold["training_base_ids"])
        assert len(validation) == 1
        assert validation.isdisjoint(training)
        assert all(
            len({row["season"] for row in rows if row["base_id"] == base})
            == sum(row["base_id"] == base for row in rows)
            for base in validation
        )


def test_shrinkage_zero_support_falls_back_to_global_and_weight_is_below_one() -> None:
    model = fit_stage_a(_rows(), "SHRINKAGE_BASE_YIELD", Decimal("1"))
    global_yield = Decimal(model["global_yield_kg_per_mu"])
    assert predict_yield(model, "UNSEEN") == global_yield
    assert model["base_support"].get("UNSEEN", 0) == 0
    for base_id, count in model["base_support"].items():
        assert Decimal(model["shrinkage_weights"][base_id]) == Decimal(count) / (
            Decimal(count) + Decimal("1")
        )
        assert Decimal(0) <= Decimal(model["shrinkage_weights"][base_id]) < Decimal(1)


def test_global_candidate_reuses_area_weighted_pooled_training_yield() -> None:
    rows = _rows()
    model = fit_stage_a(rows, "GLOBAL_POOLED_YIELD", None)
    expected = sum(Decimal(row["season_total_quantity_kg"]) for row in rows) / sum(
        Decimal(row["area_mu"]) for row in rows
    )
    assert Decimal(model["global_yield_kg_per_mu"]) == expected


def test_cv_tie_break_prefers_simplest_candidate_without_benchmark_input() -> None:
    summary = [
        {
            "model_candidate": "REGULARIZED_BASE_EFFECT",
            "hyperparameter": "1",
            "cv_wape": "0.2",
            "complexity_rank": 2,
            "absolute_bias_kg": "0",
        },
        {
            "model_candidate": "SHRINKAGE_BASE_YIELD",
            "hyperparameter": "8",
            "cv_wape": "0.2000000000001",
            "complexity_rank": 1,
            "absolute_bias_kg": "100",
        },
        {
            "model_candidate": "GLOBAL_POOLED_YIELD",
            "hyperparameter": "NONE",
            "cv_wape": "0.2000000000002",
            "complexity_rank": 0,
            "absolute_bias_kg": "500",
        },
    ]
    selected = select_cv_candidate(summary, tie_tolerance=Decimal("1e-12"))
    assert selected["model_candidate"] == "GLOBAL_POOLED_YIELD"


def test_training_dataset_hash_mismatch_fails_closed() -> None:
    with pytest.raises(R2ExperimentError, match="BLOCKED_TRAINING_DATASET_DRIFT"):
        validate_training_dataset_hash(b"changed", "0" * 64)


def test_stage_b_hash_is_canonical_and_order_independent() -> None:
    rows = [
        {"base_id": "B", "date": "2025-07-22", "predicted_share": "0.25"},
        {"base_id": "A", "date": "2025-07-22", "predicted_share": "0.75"},
    ]
    assert stage_b_shape_hash(rows) == stage_b_shape_hash(list(reversed(rows)))


def test_stage_b_shape_hash_detects_any_share_change() -> None:
    original = [{"base_id": "A", "date": "2025-07-22", "predicted_share": "1"}]
    changed = [{"base_id": "A", "date": "2025-07-22", "predicted_share": "0.9"}]
    assert stage_b_shape_hash(original) != stage_b_shape_hash(changed)


def test_peak_date_invariance_gate_fails_if_stage_b_effectively_changes() -> None:
    r1 = {"B1": {"single_day_peak_date": "2026-03-01", "rolling7_start_date": "2026-03-01"}}
    r2 = {"B1": {"single_day_peak_date": "2026-03-02", "rolling7_start_date": "2026-03-01"}}
    with pytest.raises(R2ExperimentError, match="BLOCKED_STAGE_B_PEAK_DATE_DRIFT"):
        validate_peak_date_invariance(r1, r2)


def test_peak_date_invariance_gate_accepts_same_dates() -> None:
    peaks = {"B1": {"single_day_peak_date": "2026-03-01", "rolling7_start_date": "2026-03-01"}}
    assert validate_peak_date_invariance(peaks, peaks) == (0, 0)


def test_candidate_a_b_c_vocabulary_is_closed() -> None:
    with pytest.raises(R2ExperimentError, match="UNAUTHORIZED_STAGE_A_CANDIDATE"):
        fit_stage_a(_rows(), "EXTRA_MODEL", None)


def test_frozen_training_cohort_accepts_exact_37_row_season_counts() -> None:
    rows = _full_training_rows()
    validate_training_rows(rows)
    assert len(rows) == 37
    assert sum(row["season"] == "2023-2024" for row in rows) == 15
    assert sum(row["season"] == "2024-2025" for row in rows) == 22


def test_training_cohort_rejects_wrong_row_count() -> None:
    with pytest.raises(R2ExperimentError, match="TRAINING_COHORT_MUST_BE_37"):
        validate_training_rows(_full_training_rows()[:-1])


def test_training_cohort_rejects_frozen_benchmark_season() -> None:
    rows = _full_training_rows()
    rows[0] = {**rows[0], "season": "2025-2026"}
    with pytest.raises(R2ExperimentError, match="OOT_OR_UNAUTHORIZED_SEASON"):
        validate_training_rows(rows)


def test_training_cohort_rejects_blocked_training_row() -> None:
    rows = _full_training_rows()
    rows[0] = {**rows[0], "strict_training_eligible": "false"}
    with pytest.raises(R2ExperimentError, match="BLOCKED_TRAINING_ROW_INCLUDED"):
        validate_training_rows(rows)


def test_training_cohort_rejects_duplicate_base_season_key() -> None:
    rows = _full_training_rows()
    rows[1] = {**rows[1], "base_id": rows[0]["base_id"]}
    with pytest.raises(R2ExperimentError, match="37_UNIQUE_BASE_SEASONS"):
        validate_training_rows(rows)


def test_training_cohort_rejects_nonpositive_area_and_total() -> None:
    rows = _full_training_rows()
    rows[0] = {**rows[0], "area_mu": "0"}
    with pytest.raises(R2ExperimentError, match="NONPOSITIVE_TRAINING_AREA"):
        validate_training_rows(rows)
    rows = _full_training_rows()
    rows[0] = {**rows[0], "season_total_quantity_kg": "0"}
    with pytest.raises(R2ExperimentError, match="NONPOSITIVE_TRAINING_SEASON_TOTAL"):
        validate_training_rows(rows)


def test_leave_one_base_out_assigns_each_training_row_to_validation_once() -> None:
    rows = _full_training_rows()
    folds = grouped_leave_one_base_out_folds(rows)
    assert len(folds) == 26
    validation_keys = [
        (row["base_id"], row["season"]) for fold in folds for row in fold["validation_rows"]
    ]
    assert len(validation_keys) == 37
    assert len(set(validation_keys)) == 37


def test_leave_one_base_out_folds_are_stably_ordered() -> None:
    rows = _full_training_rows()
    first = grouped_leave_one_base_out_folds(rows)
    second = grouped_leave_one_base_out_folds(list(reversed(rows)))
    assert [fold["fold_id"] for fold in first] == [fold["fold_id"] for fold in second]
    assert [fold["validation_base_ids"] for fold in first] == [
        fold["validation_base_ids"] for fold in second
    ]


def test_grouped_lobo_cannot_tune_shrinkage_for_unseen_validation_bases() -> None:
    rows = _full_training_rows()
    _, fold_results, summary = run_grouped_cv(
        rows,
        [
            {
                "model_candidate": "GLOBAL_POOLED_YIELD",
                "hyperparameters": [None],
                "complexity_rank": 0,
            },
            {
                "model_candidate": "SHRINKAGE_BASE_YIELD",
                "hyperparameters": ["0.25", "1", "8"],
                "complexity_rank": 1,
            },
        ],
    )
    global_wape = next(
        row["cv_wape"] for row in summary if row["model_candidate"] == "GLOBAL_POOLED_YIELD"
    )
    shrinkage_wapes = {
        row["cv_wape"] for row in summary if row["model_candidate"] == "SHRINKAGE_BASE_YIELD"
    }
    assert shrinkage_wapes == {global_wape}
    assert len(fold_results) == 26 * 4
    assert all(row["validation_base_count"] == "1" for row in fold_results)


def test_pooled_yield_is_repeatable_and_positive() -> None:
    rows = _full_training_rows()
    pooled = pooled_training_yield(rows)
    assert pooled == pooled_training_yield(list(reversed(rows)))
    assert pooled > 0


def test_shrinkage_single_history_moves_estimate_toward_global() -> None:
    rows = _full_training_rows()
    model = fit_stage_a(rows, "SHRINKAGE_BASE_YIELD", Decimal("1"))
    base = next(base for base, count in model["base_support"].items() if count == 1)
    base_mean = Decimal(next(row["yield_kg_per_mu"] for row in rows if row["base_id"] == base))
    global_yield = Decimal(model["global_yield_kg_per_mu"])
    shrunk = predict_yield(model, base)
    assert abs(shrunk - global_yield) < abs(base_mean - global_yield)


def test_stronger_shrinkage_lambda_moves_single_history_toward_global() -> None:
    rows = _full_training_rows()
    weak = fit_stage_a(rows, "SHRINKAGE_BASE_YIELD", Decimal("0.25"))
    strong = fit_stage_a(rows, "SHRINKAGE_BASE_YIELD", Decimal("8"))
    base = next(base for base, count in weak["base_support"].items() if count == 1)
    global_yield = Decimal(weak["global_yield_kg_per_mu"])
    assert abs(predict_yield(strong, base) - global_yield) < abs(
        predict_yield(weak, base) - global_yield
    )


def test_global_candidate_predicts_same_yield_for_known_and_unknown_bases() -> None:
    model = fit_stage_a(_full_training_rows(), "GLOBAL_POOLED_YIELD", None)
    assert predict_yield(model, "B00") == predict_yield(model, "UNSEEN")


def test_regularized_candidate_replay_is_deterministic_and_positive() -> None:
    rows = _full_training_rows()
    first = fit_stage_a(rows, "REGULARIZED_BASE_EFFECT", Decimal("10"))
    second = fit_stage_a(list(reversed(rows)), "REGULARIZED_BASE_EFFECT", Decimal("10"))
    assert first == second
    assert predict_yield(first, "B00") > 0
    assert predict_yield(first, "UNSEEN") > 0


def test_peak_dates_are_invariant_under_positive_total_rescaling() -> None:
    from backend.app.area_yield.v08_s8_training_backtest import derive_peaks

    values = ["0", "1", "3", "8", "8", "2", "1"]
    first = [
        {
            "date": f"2026-01-{index + 1:02d}",
            "predicted_daily_quantity_kg": value,
        }
        for index, value in enumerate(values)
    ]
    second = [
        {
            **row,
            "predicted_daily_quantity_kg": str(Decimal(row["predicted_daily_quantity_kg"]) * 9),
        }
        for row in first
    ]
    first_peaks = derive_peaks(first)
    second_peaks = derive_peaks(second)
    assert first_peaks["single_day_peak_date"] == second_peaks["single_day_peak_date"]
    assert first_peaks["rolling7_start_date"] == second_peaks["rolling7_start_date"]
