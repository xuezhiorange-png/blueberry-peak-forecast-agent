from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from backend.app.rolling_backtest.metrics import (
    EvaluationMaskState,
    EvaluationMetricRow,
    MetricBlockerKind,
    compute_metric_outputs,
    metric_output_by_name,
)

MASK_HASH = "a" * 64


def _row(fid: str, day: int, target: str, p50: str, p80: str) -> EvaluationMetricRow:
    return EvaluationMetricRow(
        run_id="run-1",
        node_id="node-1",
        season_id="2026",
        factory_id="factory-a",
        horizon="daily",
        calendar_phase="peak",
        mode="retrospective_replay",
        model_version="model-v1",
        forecast_output_id=fid,
        evaluation_as_of_date=date(2026, 3, day),
        target_kg=Decimal(target),
        prediction_p50_kg=Decimal(p50),
        prediction_p80_kg=Decimal(p80),
        prediction_p90_kg=Decimal(p80) + Decimal("10"),
        structural_p50_kg=Decimal(p50) - Decimal("5"),
        corrected_p50_kg=Decimal(p50),
    )


def test_metric_formulas_and_mask_semantics() -> None:
    rows = (
        _row("f1", 1, "100", "90", "110"),
        _row("f2", 2, "200", "220", "230"),
        _row("f3", 3, "0", "0", "5"),
        EvaluationMetricRow(
            run_id="run-1",
            node_id="node-1",
            season_id="2026",
            factory_id="factory-a",
            horizon="daily",
            calendar_phase="peak",
            mode="retrospective_replay",
            model_version="model-v1",
            forecast_output_id="f4",
            evaluation_as_of_date=date(2026, 3, 4),
            mask_state=EvaluationMaskState.EXCLUDED,
            target_kg=Decimal("500"),
            prediction_p50_kg=Decimal("700"),
            prediction_p80_kg=Decimal("710"),
            prediction_p90_kg=Decimal("720"),
        ),
    )
    outputs = compute_metric_outputs(rows, evaluation_mask_hash=MASK_HASH)

    assert metric_output_by_name(outputs, "row_count").value == 4
    assert metric_output_by_name(outputs, "comparable_row_count").value == 3
    assert metric_output_by_name(outputs, "masked_row_count").value == 1
    assert metric_output_by_name(outputs, "mean_absolute_error").value == Decimal("10.00000000")
    assert metric_output_by_name(outputs, "wmape").value == Decimal("0.10000000")
    assert metric_output_by_name(outputs, "cumulative_relative_error").value == Decimal("0.03333333")
    assert metric_output_by_name(outputs, "pinball_loss_p50").value == Decimal("5.00000000")
    assert metric_output_by_name(outputs, "peak_magnitude_error_p50").value == Decimal("20.00000000")
    assert metric_output_by_name(outputs, "interval_width_median_p80_p50").value == Decimal("10.00000000")


def test_metric_hashes_are_order_independent() -> None:
    rows = (_row("f1", 1, "10", "12", "13"), _row("f2", 2, "20", "18", "19"))
    left = compute_metric_outputs(rows, evaluation_mask_hash=MASK_HASH)
    right = compute_metric_outputs(tuple(reversed(rows)), evaluation_mask_hash=MASK_HASH)
    assert [(item.metric_name, item.canonical_payload_hash()) for item in left] == [
        (item.metric_name, item.canonical_payload_hash()) for item in right
    ]


def test_zero_actual_denominator_and_duplicate_row_guards() -> None:
    rows = (_row("f1", 1, "0", "10", "10"), _row("f2", 2, "0", "0", "0"))
    wmape = metric_output_by_name(compute_metric_outputs(rows, evaluation_mask_hash=MASK_HASH), "wmape")
    assert wmape.value is None
    assert wmape.blocker is not None
    assert wmape.blocker.kind is MetricBlockerKind.ZERO_ACTUAL_DENOMINATOR

    with pytest.raises(ValueError, match="duplicate evaluation row identity"):
        compute_metric_outputs((rows[0], rows[0]), evaluation_mask_hash=MASK_HASH)

    with pytest.raises(ValueError, match="evaluation_mask_hash"):
        compute_metric_outputs(rows, evaluation_mask_hash="bad")
