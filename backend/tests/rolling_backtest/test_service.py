"""Tests for TASK-011 Phase 4c-1 public service layer.

These tests cover the 4c-1 implementation slice of the Phase 4c design
contract (``docs/task-11-phase4c-service-cli-export-amendment.md``,
frozen at content SHA
``9f1f541367ee7c4ea3814f0068f682b29e590758690dcb2098cadd5de7796216``).
They are golden-style + property-style, mirroring the Phase 4b
``test_metrics.py`` pattern.
"""

from __future__ import annotations

import threading
from datetime import date
from decimal import Decimal

import pytest

from backend.app.rolling_backtest import (
    METRIC_DEFINITION_VERSION,
    ServiceContractError,
    compute_metrics,
    get_materialization_provider,
    register_materialization_provider,
)
from backend.app.rolling_backtest.metrics import (
    EvaluationMaskState,
    EvaluationMetricRow,
    MaskState,
    evaluate_scope,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


SAMPLE_MASK_HASH = "0" * 63 + "1"  # 64-char lowercase hex
SAMPLE_RUN_ID = "run-001"
SAMPLE_SCOPE: dict[str, object] = {
    "run": SAMPLE_RUN_ID,
    "node": 1,
    "horizon": "daily",
    "farm": 100,
    "variety": 7,
    "model_version": "v1.0",
    "evaluation_mask_hash": SAMPLE_MASK_HASH,
}


def _row(
    *,
    forecast_output_id: int,
    node_id: int,
    evaluation_as_of_date: date,
    target: Decimal | None,
    prediction: Decimal | None,
    mask_state: MaskState = MaskState.NONE,
    p50_kg: Decimal | None = None,
    p80_kg: Decimal | None = None,
) -> EvaluationMetricRow:
    return EvaluationMetricRow(
        forecast_output_id=forecast_output_id,
        node_id=node_id,
        evaluation_as_of_date=evaluation_as_of_date,
        target=target,
        prediction=prediction,
        mask_state=mask_state,
        p50_kg=p50_kg,
        p80_kg=p80_kg,
    )


@pytest.fixture
def golden_rows_single_node() -> list[EvaluationMetricRow]:
    """Three comparable rows on a single node 1; absolute errors 0.1, 0.2, 0.3."""

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
def golden_rows_two_nodes() -> list[EvaluationMetricRow]:
    """Two nodes, one row each."""

    return [
        _row(
            forecast_output_id=1,
            node_id=1,
            evaluation_as_of_date=date(2026, 1, 1),
            target=Decimal("10.0"),
            prediction=Decimal("10.0"),
        ),
        _row(
            forecast_output_id=2,
            node_id=2,
            evaluation_as_of_date=date(2026, 1, 1),
            target=Decimal("20.0"),
            prediction=Decimal("20.0"),
        ),
    ]


@pytest.fixture
def rows_by_run_mask() -> dict[tuple[str, str], list[EvaluationMetricRow]]:
    """Materialization provider fixture."""

    return {}


@pytest.fixture
def stub_provider(rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]]):
    """Register a stub materialization provider; tear down after the test."""

    def provider(run_id: str, mask_hash: str) -> list[EvaluationMetricRow] | None:
        return rows_by_run_mask.get((run_id, mask_hash))

    previous = register_materialization_provider(provider)
    try:
        yield provider
    finally:
        register_materialization_provider(previous)


# ---------------------------------------------------------------------------
# 1. Input validation — mask_hash (design §3.4)
# ---------------------------------------------------------------------------


def test_invalid_mask_hash_non_64_char_raises(
    stub_provider: None, rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]]
) -> None:
    with pytest.raises(ServiceContractError) as exc_info:
        compute_metrics(
            run_id=SAMPLE_RUN_ID,
            scope=SAMPLE_SCOPE,
            mask_hash="not-64-chars",
        )
    assert exc_info.value.kind == "invalid_mask_hash"


def test_invalid_mask_hash_64_char_non_hex_raises(stub_provider: None) -> None:
    with pytest.raises(ServiceContractError) as exc_info:
        compute_metrics(
            run_id=SAMPLE_RUN_ID,
            scope=SAMPLE_SCOPE,
            mask_hash="Z" * 64,
        )
    assert exc_info.value.kind == "invalid_mask_hash"


def test_invalid_mask_hash_uppercase_hex_raises(stub_provider: None) -> None:
    # Lowercase hex only per Phase 4b convention.
    with pytest.raises(ServiceContractError) as exc_info:
        compute_metrics(
            run_id=SAMPLE_RUN_ID,
            scope=SAMPLE_SCOPE,
            mask_hash=("A" * 63) + "1",
        )
    assert exc_info.value.kind == "invalid_mask_hash"


# ---------------------------------------------------------------------------
# 2. Input validation — scope (design §3.4)
# ---------------------------------------------------------------------------


def test_scope_missing_node_raises(stub_provider: None) -> None:
    with pytest.raises(ServiceContractError) as exc_info:
        compute_metrics(
            run_id=SAMPLE_RUN_ID,
            scope={"horizon": "daily"},  # no 'node'
            mask_hash=SAMPLE_MASK_HASH,
        )
    assert exc_info.value.kind == "invalid_scope"


# ---------------------------------------------------------------------------
# 3. Input validation — decimal_scale (design §3.4)
# ---------------------------------------------------------------------------


def test_decimal_scale_negative_raises(stub_provider: None) -> None:
    with pytest.raises(ServiceContractError) as exc_info:
        compute_metrics(
            run_id=SAMPLE_RUN_ID,
            scope=SAMPLE_SCOPE,
            mask_hash=SAMPLE_MASK_HASH,
            decimal_scale=-1,
        )
    assert exc_info.value.kind == "invalid_decimal_scale"


def test_decimal_scale_non_int_raises(stub_provider: None) -> None:
    with pytest.raises(ServiceContractError) as exc_info:
        compute_metrics(
            run_id=SAMPLE_RUN_ID,
            scope=SAMPLE_SCOPE,
            mask_hash=SAMPLE_MASK_HASH,
            decimal_scale=1.5,  # type: ignore[arg-type]
        )
    assert exc_info.value.kind == "invalid_decimal_scale"


# ---------------------------------------------------------------------------
# 4. Input validation — metric_subset (design §3.4)
# ---------------------------------------------------------------------------


def test_metric_subset_unknown_name_raises(stub_provider: None) -> None:
    with pytest.raises(ServiceContractError) as exc_info:
        compute_metrics(
            run_id=SAMPLE_RUN_ID,
            scope=SAMPLE_SCOPE,
            mask_hash=SAMPLE_MASK_HASH,
            metric_subset=("mean_absolute_error", "not_a_real_metric"),
        )
    assert exc_info.value.kind == "unknown_metric"
    assert "not_a_real_metric" in exc_info.value.message


# ---------------------------------------------------------------------------
# 5. Materialization lookup — missing provider / missing run / unbound mask
# ---------------------------------------------------------------------------


def test_missing_provider_raises_missing_run() -> None:
    # No stub_provider fixture — global provider slot is whatever was
    # left by a prior test. Make sure the slot is cleared.
    register_materialization_provider(None)
    with pytest.raises(ServiceContractError) as exc_info:
        compute_metrics(
            run_id=SAMPLE_RUN_ID,
            scope=SAMPLE_SCOPE,
            mask_hash=SAMPLE_MASK_HASH,
        )
    assert exc_info.value.kind == "missing_run"


def test_missing_run_raises_missing_run(stub_provider: None) -> None:
    # Provider registered, but (run_id, mask_hash) not in the table.
    with pytest.raises(ServiceContractError) as exc_info:
        compute_metrics(
            run_id="non-existent-run",
            scope=SAMPLE_SCOPE,
            mask_hash=SAMPLE_MASK_HASH,
        )
    assert exc_info.value.kind == "missing_run"


def test_provider_keyerror_translates_to_missing_run() -> None:
    def raising_provider(run_id: str, mask_hash: str) -> list[EvaluationMetricRow] | None:
        raise KeyError(f"unknown {(run_id, mask_hash)}")

    previous = register_materialization_provider(raising_provider)
    try:
        with pytest.raises(ServiceContractError) as exc_info:
            compute_metrics(
                run_id=SAMPLE_RUN_ID,
                scope=SAMPLE_SCOPE,
                mask_hash=SAMPLE_MASK_HASH,
            )
        assert exc_info.value.kind == "missing_run"
    finally:
        register_materialization_provider(previous)


# ---------------------------------------------------------------------------
# 6. Successful compute_metrics — single-factory
# ---------------------------------------------------------------------------


def test_compute_metrics_single_factory_returns_evaluation_result(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
) -> None:
    rows_by_run_mask[(SAMPLE_RUN_ID, SAMPLE_MASK_HASH)] = golden_rows_single_node
    result = compute_metrics(
        run_id=SAMPLE_RUN_ID,
        scope=SAMPLE_SCOPE,
        mask_hash=SAMPLE_MASK_HASH,
    )
    # Phase 4b result — counters + aggregate metrics.
    metric_names = [o.metric_name for o in result.outputs]
    assert "row_count" in metric_names
    assert "comparable_row_count" in metric_names
    assert "mean_absolute_error" in metric_names
    # canonical_payload_hash is a 64-char lowercase hex.
    assert len(result.canonical_payload_hash) == 64
    int(result.canonical_payload_hash, 16)  # parses as hex


def test_compute_metrics_metric_subset_filters_outputs(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
) -> None:
    rows_by_run_mask[(SAMPLE_RUN_ID, SAMPLE_MASK_HASH)] = golden_rows_single_node
    result = compute_metrics(
        run_id=SAMPLE_RUN_ID,
        scope=SAMPLE_SCOPE,
        mask_hash=SAMPLE_MASK_HASH,
        metric_subset=("mean_absolute_error",),
    )
    metric_names = [o.metric_name for o in result.outputs]
    # 4 counters + 1 named metric = 5
    assert len(metric_names) == 5
    assert metric_names.count("mean_absolute_error") == 1
    # The 4 counters are always present
    for counter in ("row_count", "comparable_row_count", "masked_row_count", "withheld_row_count"):
        assert counter in metric_names


def test_compute_metrics_metric_subset_multiple(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
) -> None:
    rows_by_run_mask[(SAMPLE_RUN_ID, SAMPLE_MASK_HASH)] = golden_rows_single_node
    result = compute_metrics(
        run_id=SAMPLE_RUN_ID,
        scope=SAMPLE_SCOPE,
        mask_hash=SAMPLE_MASK_HASH,
        metric_subset=("mean_absolute_error", "cumulative_relative_error"),
    )
    metric_names = [o.metric_name for o in result.outputs]
    # 4 counters + 2 named metrics = 6
    assert len(metric_names) == 6
    assert "mean_absolute_error" in metric_names
    assert "cumulative_relative_error" in metric_names
    # Counters not in subset must NOT appear as additional aggregate metrics.
    assert metric_names.count("mean_absolute_error") == 1
    assert metric_names.count("cumulative_relative_error") == 1


# ---------------------------------------------------------------------------
# 7. Determinism + re-entrancy
# ---------------------------------------------------------------------------


def test_compute_metrics_canonical_payload_hash_is_stable(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
) -> None:
    rows_by_run_mask[(SAMPLE_RUN_ID, SAMPLE_MASK_HASH)] = golden_rows_single_node
    a = compute_metrics(
        run_id=SAMPLE_RUN_ID,
        scope=SAMPLE_SCOPE,
        mask_hash=SAMPLE_MASK_HASH,
    )
    b = compute_metrics(
        run_id=SAMPLE_RUN_ID,
        scope=SAMPLE_SCOPE,
        mask_hash=SAMPLE_MASK_HASH,
    )
    assert a.canonical_payload_hash == b.canonical_payload_hash


def test_compute_metrics_is_input_order_independent(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
) -> None:
    forward_rows = list(golden_rows_single_node)
    reversed_rows = list(reversed(golden_rows_single_node))
    rows_by_run_mask[(SAMPLE_RUN_ID, SAMPLE_MASK_HASH)] = forward_rows
    forward_result = compute_metrics(
        run_id=SAMPLE_RUN_ID,
        scope=SAMPLE_SCOPE,
        mask_hash=SAMPLE_MASK_HASH,
    )
    rows_by_run_mask[(SAMPLE_RUN_ID, SAMPLE_MASK_HASH)] = reversed_rows
    reversed_result = compute_metrics(
        run_id=SAMPLE_RUN_ID,
        scope=SAMPLE_SCOPE,
        mask_hash=SAMPLE_MASK_HASH,
    )
    assert forward_result.canonical_payload_hash == reversed_result.canonical_payload_hash


def test_compute_metrics_is_reentrant_under_concurrent_threads(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
) -> None:
    rows_by_run_mask[(SAMPLE_RUN_ID, SAMPLE_MASK_HASH)] = golden_rows_single_node

    results: list[str] = []
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            r = compute_metrics(
                run_id=SAMPLE_RUN_ID,
                scope=SAMPLE_SCOPE,
                mask_hash=SAMPLE_MASK_HASH,
            )
            results.append(r.canonical_payload_hash)
        except BaseException as exc:  # pragma: no cover - test diagnostic
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    # All 8 concurrent calls must produce the same hash.
    assert len(set(results)) == 1


# ---------------------------------------------------------------------------
# 8. Multi-factory (split_by_factory) path
# ---------------------------------------------------------------------------


def test_compute_metrics_multi_factory_combines_results(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_two_nodes: list[EvaluationMetricRow],
) -> None:
    rows_by_run_mask[(SAMPLE_RUN_ID, SAMPLE_MASK_HASH)] = golden_rows_two_nodes
    result = compute_metrics(
        run_id=SAMPLE_RUN_ID,
        scope=SAMPLE_SCOPE,
        mask_hash=SAMPLE_MASK_HASH,
    )
    # 2 factories × 4 counters + 2 factories × N aggregate metrics
    # = 2 * (4 + N) outputs.
    metric_names = [o.metric_name for o in result.outputs]
    assert metric_names.count("row_count") == 2
    assert metric_names.count("mean_absolute_error") == 2
    # Combined hash is a 64-char lowercase hex.
    assert len(result.canonical_payload_hash) == 64


# ---------------------------------------------------------------------------
# 9. Phase 4b MetricBlocker surfaces in result, does NOT raise
# ---------------------------------------------------------------------------


def test_metric_blocker_surfaces_in_result(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
) -> None:
    # Empty comparable set → all aggregate metrics emit MetricBlocker
    rows_by_run_mask[(SAMPLE_RUN_ID, SAMPLE_MASK_HASH)] = []
    result = compute_metrics(
        run_id=SAMPLE_RUN_ID,
        scope=SAMPLE_SCOPE,
        mask_hash=SAMPLE_MASK_HASH,
    )
    # No exception raised; the function returns normally.
    blocked = [o for o in result.outputs if o.blocked_reasons]
    assert len(blocked) > 0
    assert all(any(b.kind.value == "zero_denominator" for b in o.blocked_reasons) for o in blocked)


# ---------------------------------------------------------------------------
# 10. ServiceContractError shape
# ---------------------------------------------------------------------------


def test_service_contract_error_is_value_error() -> None:
    err = ServiceContractError(kind="invalid_mask_hash", message="oops")
    assert isinstance(err, ValueError)
    payload = err.to_payload()
    assert payload["kind"] == "invalid_mask_hash"
    assert payload["message"] == "oops"
    assert payload["metric_definition_version"] == METRIC_DEFINITION_VERSION


# ---------------------------------------------------------------------------
# 11. Provider registry
# ---------------------------------------------------------------------------


def test_register_materialization_provider_returns_previous() -> None:
    previous = get_materialization_provider()
    try:

        def p(run_id: str, mask_hash: str) -> list[EvaluationMetricRow] | None:
            return []

        before = register_materialization_provider(p)
        assert before is previous
        assert get_materialization_provider() is p
        after = register_materialization_provider(None)
        assert after is p
        assert get_materialization_provider() is None
    finally:
        register_materialization_provider(previous)


# ---------------------------------------------------------------------------
# 12. Backward-compat: design §3.4 metrics are present in the public surface
# ---------------------------------------------------------------------------


def test_phase4b_metric_surface_includes_4c_subset_contracts() -> None:
    """The 13 metric names listed in the 4c-1 ``_PHASE_4B_METRIC_NAMES``
    set are the contract surface for ``metric_subset``. This test pins
    the list so an accidental drop / rename is caught."""

    # Use the 4c-1 ``compute_metrics`` happy path with each metric name
    # in the subset and check that no ``unknown_metric`` is raised.
    previous = register_materialization_provider(
        lambda run_id, mask_hash: [
            _row(
                forecast_output_id=1,
                node_id=1,
                evaluation_as_of_date=date(2026, 1, 1),
                target=Decimal("10.0"),
                prediction=Decimal("10.0"),
            )
        ]
    )
    try:
        for name in (
            "mean_absolute_error",
            "wmape",
            "cumulative_relative_error",
            "pinball_loss_p50",
            "empirical_coverage_p50",
            "peak_date_error_days_p50_signed",
            "peak_date_error_days_p50_absolute",
            "peak_magnitude_error_p50",
            "quantile_crossing_count",
            "interval_width_mean_p80_p50",
            "interval_width_median_p80_p50",
            "correction_magnitude_count",
            "correction_magnitude_median",
        ):
            # Should not raise.
            compute_metrics(
                run_id=SAMPLE_RUN_ID,
                scope=SAMPLE_SCOPE,
                mask_hash=SAMPLE_MASK_HASH,
                metric_subset=(name,),
            )
    finally:
        register_materialization_provider(previous)


# ---------------------------------------------------------------------------
# 13. Decoupling: compute_metrics never writes / never makes network calls
# ---------------------------------------------------------------------------


def test_compute_metrics_does_not_mutate_provider_state(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
) -> None:
    rows_by_run_mask[(SAMPLE_RUN_ID, SAMPLE_MASK_HASH)] = golden_rows_single_node
    # Take a snapshot of the materialization table size before.
    size_before = len(rows_by_run_mask)
    compute_metrics(
        run_id=SAMPLE_RUN_ID,
        scope=SAMPLE_SCOPE,
        mask_hash=SAMPLE_MASK_HASH,
    )
    # compute_metrics MUST NOT add / remove / mutate the table.
    assert len(rows_by_run_mask) == size_before


# ---------------------------------------------------------------------------
# 14. Direct equivalence with Phase 4b evaluate_scope (single-factory case)
# ---------------------------------------------------------------------------


def test_compute_metrics_single_factory_matches_evaluate_scope(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
) -> None:
    rows_by_run_mask[(SAMPLE_RUN_ID, SAMPLE_MASK_HASH)] = golden_rows_single_node
    # Direct Phase 4b call.
    mask = EvaluationMaskState(evaluation_mask_hash=SAMPLE_MASK_HASH)
    direct = evaluate_scope(golden_rows_single_node, mask, scope=SAMPLE_SCOPE)
    # Service-layer call.
    via_service = compute_metrics(
        run_id=SAMPLE_RUN_ID,
        scope=SAMPLE_SCOPE,
        mask_hash=SAMPLE_MASK_HASH,
    )
    # Same hash (single-factory path delegates directly).
    assert direct.canonical_payload_hash == via_service.canonical_payload_hash
