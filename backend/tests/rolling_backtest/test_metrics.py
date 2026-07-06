"""Tests for TASK-011 Phase 4b metric formulas and scoped metrics.

These tests cover the first implementation slice of the Phase 4b design
contract (`docs/task-11-phase4b-metric-formulas-amendment.md`). They are
deliberately golden-style: each test pins one metric against fixed inputs
and asserts on exact ``Decimal`` / hash / blocker outcomes.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from backend.app.rolling_backtest.metrics import (
    DEFAULT_DECIMAL_SCALE,
    EMPTY_MASK_HASH,
    METRIC_DEFINITION_VERSION,
    EvaluationMaskState,
    EvaluationMetricRow,
    MaskState,
    MetricBlockerKind,
    canonical_payload_hash,
    correction_magnitude_count,
    correction_magnitude_median,
    cumulative_relative_error,
    empirical_coverage_p50,
    evaluate_scope,
    interval_width_mean_p80_p50,
    interval_width_median_p80_p50,
    masked_row_count,
    mean_absolute_error,
    pinball_loss_p50,
    quantile_crossing_count,
    row_count,
    split_by_factory,
    withheld_row_count,
    wmape,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


SAMPLE_MASK_HASH = "0" * 63 + "1"  # 64-char lowercase hex


def _row(
    *,
    forecast_output_id: int,
    node_id: int,
    evaluation_as_of_date: date,
    target: Decimal | None,
    prediction: Decimal | None,
    mask_state: MaskState = MaskState.NONE,
    p50_low: Decimal | None = None,
    p50_high: Decimal | None = None,
    p80_low: Decimal | None = None,
    p80_high: Decimal | None = None,
    peak_date: date | None = None,
) -> EvaluationMetricRow:
    return EvaluationMetricRow(
        forecast_output_id=forecast_output_id,
        node_id=node_id,
        evaluation_as_of_date=evaluation_as_of_date,
        target=target,
        prediction=prediction,
        mask_state=mask_state,
        p50_low=p50_low,
        p50_high=p50_high,
        p80_low=p80_low,
        p80_high=p80_high,
        peak_date=peak_date,
    )


@pytest.fixture
def mask() -> EvaluationMaskState:
    return EvaluationMaskState(evaluation_mask_hash=SAMPLE_MASK_HASH)


@pytest.fixture
def golden_rows() -> list[EvaluationMetricRow]:
    """Three comparable rows on node 1; absolute errors 0.1, 0.2, 0.3."""

    return [
        _row(
            forecast_output_id=10,
            node_id=1,
            evaluation_as_of_date=date(2026, 1, 1),
            target=Decimal("10.0"),
            prediction=Decimal("10.1"),
        ),
        _row(
            forecast_output_id=11,
            node_id=1,
            evaluation_as_of_date=date(2026, 1, 2),
            target=Decimal("20.0"),
            prediction=Decimal("19.8"),
        ),
        _row(
            forecast_output_id=12,
            node_id=1,
            evaluation_as_of_date=date(2026, 1, 3),
            target=Decimal("30.0"),
            prediction=Decimal("30.3"),
        ),
    ]


@pytest.fixture
def scope() -> dict[str, object]:
    return {
        "run": "run-001",
        "node": 1,
        "horizon": "daily",
        "farm": 100,
        "variety": 7,
        "model_version": "v1.0",
        "evaluation_mask_hash": SAMPLE_MASK_HASH,
    }


# ---------------------------------------------------------------------------
# 1. Core metric formula golden values
# ---------------------------------------------------------------------------


def test_mean_absolute_error_golden_value(
    golden_rows: list[EvaluationMetricRow],
    mask: EvaluationMaskState,
    scope: dict[str, object],
) -> None:
    output = mean_absolute_error(golden_rows, mask, scope=scope)
    assert output.metric_value == Decimal("0.200000")
    assert output.comparable_row_count == 3
    assert output.blocked_reasons == ()


def test_wmape_golden_value(
    golden_rows: list[EvaluationMetricRow],
    mask: EvaluationMaskState,
    scope: dict[str, object],
) -> None:
    output = wmape(golden_rows, mask, scope=scope)
    # sum(|err|) = 0.6, sum(|target|) = 60.0, ratio = 0.01
    assert output.metric_value == Decimal("0.010000")
    assert output.blocked_reasons == ()


def test_cumulative_relative_error_matches_wmape(
    golden_rows: list[EvaluationMetricRow],
    mask: EvaluationMaskState,
    scope: dict[str, object],
) -> None:
    output = cumulative_relative_error(golden_rows, mask, scope=scope)
    assert output.metric_value == Decimal("0.010000")


def test_pinball_loss_p50_zero_when_unbiased(
    golden_rows: list[EvaluationMetricRow],
    mask: EvaluationMaskState,
    scope: dict[str, object],
) -> None:
    output = pinball_loss_p50(golden_rows, mask, scope=scope)
    # signed errors: 0.1, -0.2, 0.3
    # pinball tau=0.5 per-row contributions: 0.5*0.1 + (-0.5)*(-0.2) + 0.5*0.3
    #   = 0.05 + 0.10 + 0.15 = 0.30
    # mean over 3 = 0.10
    assert output.metric_value == Decimal("0.100000")
    assert output.comparable_row_count == 3
    assert output.blocked_reasons == ()


def test_empirical_coverage_p50_perfect_band(
    golden_rows: list[EvaluationMetricRow],
    mask: EvaluationMaskState,
    scope: dict[str, object],
) -> None:
    rows = [
        _row(
            forecast_output_id=20,
            node_id=1,
            evaluation_as_of_date=date(2026, 1, 1),
            target=Decimal("100.0"),
            prediction=Decimal("100.0"),
            p50_low=Decimal("95.0"),
            p50_high=Decimal("105.0"),
        ),
        _row(
            forecast_output_id=21,
            node_id=1,
            evaluation_as_of_date=date(2026, 1, 2),
            target=Decimal("200.0"),
            prediction=Decimal("200.0"),
            p50_low=Decimal("190.0"),
            p50_high=Decimal("210.0"),
        ),
    ]
    output = empirical_coverage_p50(rows, mask, scope=scope)
    assert output.metric_value == Decimal("1.000000")


# ---------------------------------------------------------------------------
# 2. Mask-aware inclusion / exclusion
# ---------------------------------------------------------------------------


def test_excluded_rows_excluded_from_mae(
    mask: EvaluationMaskState, scope: dict[str, object]
) -> None:
    rows = [
        _row(
            forecast_output_id=1,
            node_id=1,
            evaluation_as_of_date=date(2026, 1, 1),
            target=Decimal("10.0"),
            prediction=Decimal("10.0"),
        ),
        _row(
            forecast_output_id=2,
            node_id=1,
            evaluation_as_of_date=date(2026, 1, 2),
            target=Decimal("20.0"),
            prediction=Decimal("999.0"),
            mask_state=MaskState.EXCLUDED,
        ),
    ]
    output = mean_absolute_error(rows, mask, scope=scope)
    # only the first row is comparable; error 0
    assert output.metric_value == Decimal("0.000000")
    assert output.comparable_row_count == 1


def test_blocked_rows_excluded_from_metrics(
    mask: EvaluationMaskState, scope: dict[str, object]
) -> None:
    rows = [
        _row(
            forecast_output_id=1,
            node_id=1,
            evaluation_as_of_date=date(2026, 1, 1),
            target=Decimal("10.0"),
            prediction=Decimal("999.0"),
            mask_state=MaskState.BLOCKED,
        ),
        _row(
            forecast_output_id=2,
            node_id=1,
            evaluation_as_of_date=date(2026, 1, 2),
            target=Decimal("20.0"),
            prediction=Decimal("20.0"),
        ),
    ]
    output = mean_absolute_error(rows, mask, scope=scope)
    assert output.metric_value == Decimal("0.000000")
    assert output.comparable_row_count == 1


def test_true_zero_row_included_with_zero_error(
    mask: EvaluationMaskState, scope: dict[str, object]
) -> None:
    rows = [
        _row(
            forecast_output_id=1,
            node_id=1,
            evaluation_as_of_date=date(2026, 1, 1),
            target=Decimal("0"),
            prediction=Decimal("0"),
            mask_state=MaskState.TRUE_ZERO,
        ),
    ]
    output = mean_absolute_error(rows, mask, scope=scope)
    assert output.metric_value == Decimal("0.000000")
    assert output.comparable_row_count == 1


def test_withheld_rows_counted_in_withheld_row_count(
    mask: EvaluationMaskState, scope: dict[str, object]
) -> None:
    rows = [
        _row(
            forecast_output_id=1,
            node_id=1,
            evaluation_as_of_date=date(2026, 1, 1),
            target=Decimal("10.0"),
            prediction=Decimal("10.0"),
        ),
        _row(
            forecast_output_id=2,
            node_id=1,
            evaluation_as_of_date=date(2026, 1, 2),
            target=Decimal("20.0"),
            prediction=Decimal("20.0"),
            mask_state=MaskState.WITHHELD,
        ),
    ]
    assert row_count(rows, mask) == 2
    assert withheld_row_count(rows, mask) == 1
    assert masked_row_count(rows, mask) == 0


# ---------------------------------------------------------------------------
# 3. Zero actual denominator structured blocker
# ---------------------------------------------------------------------------


def test_wmape_zero_target_denominator_blocks(
    mask: EvaluationMaskState, scope: dict[str, object]
) -> None:
    rows = [
        _row(
            forecast_output_id=1,
            node_id=1,
            evaluation_as_of_date=date(2026, 1, 1),
            target=Decimal("0"),
            prediction=Decimal("5.0"),
        ),
        _row(
            forecast_output_id=2,
            node_id=1,
            evaluation_as_of_date=date(2026, 1, 2),
            target=Decimal("0"),
            prediction=Decimal("7.0"),
        ),
    ]
    output = wmape(rows, mask, scope=scope)
    assert output.metric_value is None
    assert len(output.blocked_reasons) == 1
    assert output.blocked_reasons[0].kind == MetricBlockerKind.ZERO_DENOMINATOR


def test_mae_empty_comparable_blocks(mask: EvaluationMaskState, scope: dict[str, object]) -> None:
    output = mean_absolute_error([], mask, scope=scope)
    assert output.metric_value is None
    assert output.blocked_reasons[0].kind == MetricBlockerKind.ZERO_DENOMINATOR


# ---------------------------------------------------------------------------
# 4. Duplicate evaluation row identity rejection
# ---------------------------------------------------------------------------


def test_duplicate_row_identity_rejected(
    mask: EvaluationMaskState, scope: dict[str, object]
) -> None:
    rows = [
        _row(
            forecast_output_id=1,
            node_id=1,
            evaluation_as_of_date=date(2026, 1, 1),
            target=Decimal("10.0"),
            prediction=Decimal("10.0"),
        ),
        _row(
            forecast_output_id=1,
            node_id=1,
            evaluation_as_of_date=date(2026, 1, 1),
            target=Decimal("20.0"),
            prediction=Decimal("20.0"),
        ),
    ]
    with pytest.raises(ValueError, match="duplicate evaluation row identity"):
        mean_absolute_error(rows, mask, scope=scope)


# ---------------------------------------------------------------------------
# 5. Invalid evaluation_mask_hash rejection
# ---------------------------------------------------------------------------


def test_invalid_mask_hash_rejected_at_construction() -> None:
    # Non-64-char string
    with pytest.raises(ValueError, match="evaluation_mask_hash must be a 64-char hex string"):
        EvaluationMaskState(evaluation_mask_hash="not-64-chars")
    # 64-char but non-hex
    with pytest.raises(ValueError, match="evaluation_mask_hash must be lowercase hex"):
        EvaluationMaskState(evaluation_mask_hash="Z" * 64)


def test_mask_hash_constructor_enforces_hex() -> None:
    with pytest.raises(ValueError):
        EvaluationMaskState(evaluation_mask_hash="Z" * 64)


# ---------------------------------------------------------------------------
# 6. Deterministic output hash independent of input row order
# ---------------------------------------------------------------------------


def test_canonical_payload_hash_independent_of_input_order(
    golden_rows: list[EvaluationMetricRow],
    mask: EvaluationMaskState,
    scope: dict[str, object],
) -> None:
    forward = evaluate_scope(list(golden_rows), mask, scope=scope)
    reversed_rows = list(reversed(golden_rows))
    backward = evaluate_scope(reversed_rows, mask, scope=scope)
    assert forward.canonical_payload_hash == backward.canonical_payload_hash
    for a, b in zip(forward.outputs, backward.outputs, strict=True):
        assert a.metric_value == b.metric_value
        assert a.comparable_row_count == b.comparable_row_count


# ---------------------------------------------------------------------------
# 7. Scoped metrics split by at least ``node_id`` (factory dimension)
# ---------------------------------------------------------------------------


def test_split_by_factory_yields_per_node_results(
    mask: EvaluationMaskState,
) -> None:
    rows = [
        _row(
            forecast_output_id=1,
            node_id=1,
            evaluation_as_of_date=date(2026, 1, 1),
            target=Decimal("10.0"),
            prediction=Decimal("10.0"),
        ),
        _row(
            forecast_output_id=2,
            node_id=1,
            evaluation_as_of_date=date(2026, 1, 2),
            target=Decimal("20.0"),
            prediction=Decimal("20.0"),
        ),
        _row(
            forecast_output_id=3,
            node_id=2,
            evaluation_as_of_date=date(2026, 1, 1),
            target=Decimal("100.0"),
            prediction=Decimal("100.0"),
        ),
    ]
    results = split_by_factory(
        rows,
        mask,
        run_id="run-001",
        horizon="daily",
        model_version="v1.0",
    )
    assert set(results) == {1, 2}
    factory_1 = results[1]
    assert any(o.metric_name == "row_count" and o.metric_value == 2 for o in factory_1.outputs)
    assert any(o.metric_name == "row_count" and o.metric_value == 1 for o in results[2].outputs)


# ---------------------------------------------------------------------------
# 8. Peak / interval-width / crossing / correction metrics
# ---------------------------------------------------------------------------


def test_peak_date_error_days_p50(mask: EvaluationMaskState, scope: dict[str, object]) -> None:
    rows = [
        _row(
            forecast_output_id=1,
            node_id=1,
            evaluation_as_of_date=date(2026, 1, 10),
            target=Decimal("10.0"),
            prediction=Decimal("10.0"),
            peak_date=date(2026, 1, 12),
        ),
        _row(
            forecast_output_id=2,
            node_id=1,
            evaluation_as_of_date=date(2026, 1, 11),
            target=Decimal("20.0"),
            prediction=Decimal("20.0"),
            peak_date=date(2026, 1, 18),
        ),
    ]
    from backend.app.rolling_backtest.metrics import peak_date_error_days_p50

    output = peak_date_error_days_p50(rows, mask, scope=scope)
    # |2 - 7| median = 4.5
    assert output.metric_value == Decimal("4.500000")


def test_quantile_crossing_count(mask: EvaluationMaskState, scope: dict[str, object]) -> None:
    rows = [
        _row(
            forecast_output_id=1,
            node_id=1,
            evaluation_as_of_date=date(2026, 1, 1),
            target=Decimal("10.0"),
            prediction=Decimal("10.0"),
            p50_low=Decimal("9.0"),
            p50_high=Decimal("12.0"),
            p80_low=Decimal("8.0"),
            p80_high=Decimal("13.0"),
        ),
        _row(
            forecast_output_id=2,
            node_id=1,
            evaluation_as_of_date=date(2026, 1, 2),
            target=Decimal("20.0"),
            prediction=Decimal("20.0"),
            p50_low=Decimal("19.0"),
            p50_high=Decimal("22.0"),
            # inner band extends beyond outer band — counts as crossing
            p80_low=Decimal("20.0"),
            p80_high=Decimal("21.0"),
        ),
    ]
    output = quantile_crossing_count(rows, mask, scope=scope)
    assert output.metric_value == Decimal("1.000000")


def test_interval_width_mean_p80_p50(mask: EvaluationMaskState, scope: dict[str, object]) -> None:
    rows = [
        _row(
            forecast_output_id=1,
            node_id=1,
            evaluation_as_of_date=date(2026, 1, 1),
            target=Decimal("10.0"),
            prediction=Decimal("10.0"),
            p50_low=Decimal("9.0"),
            p50_high=Decimal("11.0"),
            p80_low=Decimal("8.0"),
            p80_high=Decimal("12.0"),
        ),
    ]
    output = interval_width_mean_p80_p50(rows, mask, scope=scope)
    # p80 width = 4, p50 width = 2, delta = 2
    assert output.metric_value == Decimal("2.000000")


def test_interval_width_median_p80_p50(mask: EvaluationMaskState, scope: dict[str, object]) -> None:
    rows = [
        _row(
            forecast_output_id=1,
            node_id=1,
            evaluation_as_of_date=date(2026, 1, 1),
            target=Decimal("10.0"),
            prediction=Decimal("10.0"),
            p50_low=Decimal("9.0"),
            p50_high=Decimal("11.0"),
            p80_low=Decimal("8.0"),
            p80_high=Decimal("12.0"),
        ),
    ]
    output = interval_width_median_p80_p50(rows, mask, scope=scope)
    assert output.metric_value == Decimal("2.000000")


def test_correction_magnitude_count_and_median(
    mask: EvaluationMaskState, scope: dict[str, object]
) -> None:
    structural = [
        _row(
            forecast_output_id=1,
            node_id=1,
            evaluation_as_of_date=date(2026, 1, 1),
            target=Decimal("10.0"),
            prediction=Decimal("10.0"),
        ),
        _row(
            forecast_output_id=2,
            node_id=1,
            evaluation_as_of_date=date(2026, 1, 2),
            target=Decimal("20.0"),
            prediction=Decimal("20.0"),
        ),
    ]
    corrected = [
        _row(
            forecast_output_id=1,
            node_id=1,
            evaluation_as_of_date=date(2026, 1, 1),
            target=Decimal("10.0"),
            prediction=Decimal("10.5"),
        ),
        _row(
            forecast_output_id=2,
            node_id=1,
            evaluation_as_of_date=date(2026, 1, 2),
            target=Decimal("20.0"),
            prediction=Decimal("20.5"),
        ),
    ]
    count_output = correction_magnitude_count(structural, corrected, mask, scope=scope)
    median_output = correction_magnitude_median(structural, corrected, mask, scope=scope)
    assert count_output.metric_value == Decimal("2.000000")
    assert median_output.metric_value == Decimal("0.500000")


def test_correction_magnitude_blocked_on_row_set_mismatch(
    mask: EvaluationMaskState, scope: dict[str, object]
) -> None:
    structural = [
        _row(
            forecast_output_id=1,
            node_id=1,
            evaluation_as_of_date=date(2026, 1, 1),
            target=Decimal("10.0"),
            prediction=Decimal("10.0"),
        ),
    ]
    corrected = [
        _row(
            forecast_output_id=2,
            node_id=1,
            evaluation_as_of_date=date(2026, 1, 1),
            target=Decimal("10.0"),
            prediction=Decimal("10.0"),
        ),
    ]
    with pytest.raises(ValueError, match="structural and corrected row identities differ"):
        correction_magnitude_count(structural, corrected, mask, scope=scope)


# ---------------------------------------------------------------------------
# 9. Metric definition version is frozen
# ---------------------------------------------------------------------------


def test_metric_definition_version_is_pinned() -> None:
    assert METRIC_DEFINITION_VERSION == "4b-1.0.0"


def test_default_decimal_scale_is_pinned() -> None:
    assert DEFAULT_DECIMAL_SCALE == 6


def test_empty_mask_hash_constant_is_64_zeroes() -> None:
    assert EMPTY_MASK_HASH == "0" * 64


# ---------------------------------------------------------------------------
# 10. ``evaluate_scope`` returns a stable hash for identical inputs
# ---------------------------------------------------------------------------


def test_evaluate_scope_canonical_hash_is_stable(
    golden_rows: list[EvaluationMetricRow],
    mask: EvaluationMaskState,
    scope: dict[str, object],
) -> None:
    a = evaluate_scope(golden_rows, mask, scope=scope)
    b = evaluate_scope(golden_rows, mask, scope=scope)
    assert a.canonical_payload_hash == b.canonical_payload_hash
    # ``canonical_payload_hash`` covers ``{"outputs": [...], "metric_definition_version"}``,
    # so hashing ``to_payload()`` (which embeds the hash itself) is a
    # different payload by design. Instead, verify the audit payload itself
    # is hash-stable across calls.
    a_payload = {
        "outputs": [o.to_audit_payload() for o in a.outputs],
        "metric_definition_version": METRIC_DEFINITION_VERSION,
    }
    b_payload = {
        "outputs": [o.to_audit_payload() for o in b.outputs],
        "metric_definition_version": METRIC_DEFINITION_VERSION,
    }
    assert canonical_payload_hash(a_payload) == canonical_payload_hash(b_payload)
    assert canonical_payload_hash(a_payload) == a.canonical_payload_hash
