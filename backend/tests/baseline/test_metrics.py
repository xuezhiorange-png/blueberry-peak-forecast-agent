from __future__ import annotations

from decimal import Decimal

from backend.app.baseline.metrics import (
    aggregate_error_metrics,
    build_leakage_audit,
    evaluated_row,
    excluded_row,
)


def test_error_metrics_compute_mape_mdape_and_wmape() -> None:
    rows = [
        evaluated_row(
            baseline_name="ridge_structure",
            target_season_id=1,
            target_season_code="2024-2025",
            factory_id=1,
            factory_name="A",
            fold_key="season:2024-2025",
            actual_stable_peak_kg=Decimal("100"),
            predicted_stable_peak_kg=Decimal("80"),
        ),
        evaluated_row(
            baseline_name="ridge_structure",
            target_season_id=2,
            target_season_code="2025-2026",
            factory_id=2,
            factory_name="B",
            fold_key="season:2025-2026",
            actual_stable_peak_kg=Decimal("200"),
            predicted_stable_peak_kg=Decimal("250"),
        ),
    ]
    metrics = aggregate_error_metrics(rows)
    assert metrics.mape == Decimal("0.2250000000")
    assert metrics.mdape == Decimal("0.2250000000")
    assert metrics.wmape == Decimal("0.2333333333")
    assert metrics.mae_kg == Decimal("35.000000")
    assert metrics.mae_tonne == Decimal("0.035000")
    assert metrics.mean_bias_kg == Decimal("15.000000")


def test_non_positive_actual_peak_is_excluded() -> None:
    row = excluded_row(
        baseline_name="ridge_structure",
        target_season_id=1,
        target_season_code="2024-2025",
        factory_id=1,
        factory_name="A",
        fold_key="season:2024-2025",
        exclusion_reason="non_positive_actual_peak",
        actual_stable_peak_kg=Decimal("0"),
    )
    metrics = aggregate_error_metrics([row])
    assert metrics.evaluated_row_count == 0
    assert metrics.excluded_row_count == 1
    assert metrics.exclusion_counts["non_positive_actual_peak"] == 1


def test_negative_prediction_is_not_clipped() -> None:
    row = evaluated_row(
        baseline_name="ridge_structure",
        target_season_id=1,
        target_season_code="2024-2025",
        factory_id=1,
        factory_name="A",
        fold_key="season:2024-2025",
        actual_stable_peak_kg=Decimal("100"),
        predicted_stable_peak_kg=Decimal("-10"),
    )
    metrics = aggregate_error_metrics([row])
    assert row.predicted_stable_peak_kg == Decimal("-10.000000")
    assert metrics.negative_prediction_count == 1


def test_mape_under_ten_percent_triggers_leakage_audit() -> None:
    rows = [
        evaluated_row(
            baseline_name="ridge_structure",
            target_season_id=1,
            target_season_code="2024-2025",
            factory_id=1,
            factory_name="A",
            fold_key="season:2024-2025",
            actual_stable_peak_kg=Decimal("100"),
            predicted_stable_peak_kg=Decimal("95"),
        )
    ]
    metrics = aggregate_error_metrics(rows)
    audit = build_leakage_audit(
        rows=rows,
        metrics=metrics,
        target_uses_peak_concentration=False,
        scaler_fit_on_test_rows=False,
        model_trained_on_test_rows=False,
        alpha_selected_on_full_data=False,
        duplicate_train_test_samples=False,
        previous_season_pairing_skipped_gap=False,
        duplicate_build_run_counted_twice=False,
        excluded_rows_counted_as_zero=False,
    )
    assert metrics.mape is not None and metrics.mape < Decimal("0.1000000000")
    assert len(audit) == 10
    assert all(check.passed for check in audit)
