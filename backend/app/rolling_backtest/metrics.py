"""TASK-011 Phase 4b — metric formulas and scoped metrics.

This module is the first implementation slice of the Phase 4b design contract
(`docs/task-11-phase4b-metric-formulas-amendment.md` on main). It implements the
deterministic counter / aggregate-error / coverage / structural-parity metric
formulas described in the design, restricted to a small, frozen subset
sufficient to exercise the public surface end-to-end.

Hard constraints (mirrored from the design §10 stop conditions):

* Read-only over Phase 4a materialization. No schema or migration change.
* No Phase 4c service / CLI / export code.
* No Task 10 ``replay_trained_model`` mutation.
* Decimal canonical, ``ROUND_HALF_EVEN`` rounding. No native ``float`` in
  payload or hash inputs.
* Deterministic ordering: canonical input order is
  ``sorted(rows, key=lambda r: (r.node_id, r.evaluation_as_of_date, r.forecast_output_id))``.
* Stable, versioned metric definition identity. Bumping
  ``METRIC_DEFINITION_VERSION`` requires a new design amendment.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_EVEN, Decimal
from enum import StrEnum
from typing import Any, Final, cast

# ---------------------------------------------------------------------------
# Frozen metric definition identity. Bumping requires a new design amendment.
# ---------------------------------------------------------------------------

METRIC_DEFINITION_VERSION: Final[str] = "4b-1.0.0"

# Default decimal scale used when caller does not pin a scale. 6 dp is the
# house rounding used by Phase 4a downstream.
DEFAULT_DECIMAL_SCALE: Final[int] = 6

# Default hash for "no rows in scope" — used only when an empty payload still
# needs a stable identity. Never appears on a real evaluation_mask_hash.
EMPTY_MASK_HASH: Final[str] = "0" * 64


class MaskState(StrEnum):
    """Phase 4a evaluation row mask states consumed by Phase 4b metrics.

    The design contract §5 reserves ``WITHHELD`` for future schema extensions;
    the implementation accommodates it now so that callers do not need a code
    change to render a future state.
    """

    NONE = "none"
    TRUE_ZERO = "true_zero"
    EXCLUDED = "excluded"
    BLOCKED = "blocked"
    WITHHELD = "withheld"


# Mask states that count as masked (excluded + blocked) — used by
# ``masked_row_count``. Withheld has its own counter.
_MASKED_STATES: Final[frozenset[MaskState]] = frozenset({MaskState.EXCLUDED, MaskState.BLOCKED})


class MetricBlockerKind(StrEnum):
    """Blocker kinds emitted by the metric pipeline.

    Mirrors design §7. Only the kinds exercised by the first implementation
    slice are listed here; reserved kinds are deliberately omitted.
    """

    ZERO_DENOMINATOR = "zero_denominator"
    DUPLICATE_ROW_IDENTITY = "duplicate_row_identity"
    INVALID_MASK_HASH = "invalid_mask_hash"
    NON_COMPARABLE_ROW = "non_comparable_row"


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EvaluationMetricRow:
    """A single Phase 4a evaluation row in scope of a metric computation.

    All quantitites are ``Decimal`` to keep the canonical payload hash stable
    across Python / PostgreSQL boundaries (per design §6 + §8).
    """

    forecast_output_id: int
    node_id: int
    evaluation_as_of_date: date
    target: Decimal | None
    prediction: Decimal | None
    mask_state: MaskState = MaskState.NONE
    p50_low: Decimal | None = None
    p50_high: Decimal | None = None
    p80_low: Decimal | None = None
    p80_high: Decimal | None = None
    peak_date: date | None = None

    def __post_init__(self) -> None:
        if self.forecast_output_id <= 0:
            raise ValueError("forecast_output_id must be positive")
        if self.node_id <= 0:
            raise ValueError("node_id must be positive")
        if (
            self.evaluation_mask_state() not in MaskState.__members__.values()
        ):  # pragma: no cover - typed
            raise ValueError("mask_state must be a MaskState member")

    # Convenience alias used by docs and tests.
    def evaluation_mask_state(self) -> MaskState:
        return self.mask_state


@dataclass(frozen=True, slots=True)
class EvaluationMaskState:
    """Mask state descriptor — held by callers for hash binding and audit."""

    evaluation_mask_hash: str
    state_counts: Mapping[MaskState, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.evaluation_mask_hash or len(self.evaluation_mask_hash) != 64:
            raise ValueError("evaluation_mask_hash must be a 64-char hex string")
        if any(c not in "0123456789abcdef" for c in self.evaluation_mask_hash):
            raise ValueError("evaluation_mask_hash must be lowercase hex")

    @classmethod
    def empty(cls) -> EvaluationMaskState:
        return cls(evaluation_mask_hash=EMPTY_MASK_HASH, state_counts={})


# ---------------------------------------------------------------------------
# Blocker / output
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MetricBlocker:
    """Design §7 blocker payload."""

    kind: MetricBlockerKind
    metric: str
    scope_id: str
    message: str
    evaluation_mask_hash: str
    metric_definition_version: str = METRIC_DEFINITION_VERSION

    def to_payload(self) -> dict[str, str]:
        return {
            "kind": self.kind.value,
            "metric": self.metric,
            "scope_id": self.scope_id,
            "message": self.message,
            "evaluation_mask_hash": self.evaluation_mask_hash,
            "metric_definition_version": self.metric_definition_version,
        }


@dataclass(frozen=True, slots=True)
class MetricOutput:
    """Per-metric output (design §6 audit payload)."""

    metric_name: str
    metric_value: Decimal | None
    metric_scope_identity: str
    evaluation_mask_hash: str
    comparable_row_count: int
    blocked_reasons: tuple[MetricBlocker, ...] = ()
    decimal_scale: int = DEFAULT_DECIMAL_SCALE
    metric_definition_version: str = METRIC_DEFINITION_VERSION

    def to_audit_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "metric_name": self.metric_name,
            "metric_value": _canonical_decimal(self.metric_value)
            if self.metric_value is not None
            else None,
            "metric_scope_identity": self.metric_scope_identity,
            "evaluation_mask_hash": self.evaluation_mask_hash,
            "comparable_row_count": self.comparable_row_count,
            "blocked_reasons": [b.to_payload() for b in self.blocked_reasons],
            "decimal_scale": self.decimal_scale,
            "metric_definition_version": self.metric_definition_version,
        }
        return payload


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _canonical_decimal(value: Decimal | None) -> str:
    if value is None:
        return "null"
    if not value.is_finite():
        raise ValueError("non-finite Decimal is not allowed in canonical payload")
    # Banker's rounding to the scale implied by the value itself; full
    # scale-pinning is applied where the design demands it.
    return format(value, "f")


def _quantize(value: Decimal, scale: int) -> Decimal:
    if not value.is_finite():
        raise ValueError("non-finite Decimal cannot be quantized")
    return value.quantize(Decimal(1).scaleb(-scale), rounding=ROUND_HALF_EVEN)


def _canonical_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, Decimal):
        return _canonical_decimal(value)
    if isinstance(value, (list, tuple)):
        return [_canonical_json_value(item) for item in value]
    if isinstance(value, Mapping):
        return {str(k): _canonical_json_value(v) for k, v in sorted(value.items())}
    if isinstance(value, (datetime, date)):
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=UTC)
            else:
                value = value.astimezone(UTC)
            return value.isoformat().replace("+00:00", "Z")
        return value.isoformat()
    raise TypeError(f"unsupported canonical JSON value type: {type(value).__name__}")


def canonical_payload_hash(payload: Mapping[str, Any]) -> str:
    """Compute the SHA-256 hash of the canonical JSON serialization."""

    normalized = _canonical_json_value(dict(payload))
    encoded = json.dumps(normalized, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _row_identity(row: EvaluationMetricRow) -> tuple[int, int, date]:
    return (row.forecast_output_id, row.node_id, row.evaluation_as_of_date)


def _is_comparable(row: EvaluationMetricRow) -> bool:
    if row.target is None or row.prediction is None:
        return False
    if row.mask_state in (MaskState.EXCLUDED, MaskState.BLOCKED, MaskState.WITHHELD):
        return False
    return True


def _validate_rows(
    rows: Iterable[EvaluationMetricRow], *, expected_mask_hash: str
) -> list[EvaluationMetricRow]:
    materialized = list(rows)
    seen: set[tuple[int, int, date]] = set()
    for row in materialized:
        ident = _row_identity(row)
        if ident in seen:
            raise MetricInputError(
                f"duplicate evaluation row identity: forecast_output_id={ident[0]} "
                f"node_id={ident[1]} evaluation_as_of_date={ident[2].isoformat()}"
            )
        seen.add(ident)
    if expected_mask_hash and expected_mask_hash != EMPTY_MASK_HASH:
        if len(expected_mask_hash) != 64 or any(
            c not in "0123456789abcdef" for c in expected_mask_hash
        ):
            raise MetricInputError(
                "invalid evaluation_mask_hash: must be 64-char lowercase hex "
                f"(got {expected_mask_hash!r})"
            )
    return materialized


class MetricInputError(ValueError):
    """Raised for malformed metric input (e.g. invalid mask hash, duplicate rows)."""


def _scope_identity(
    *,
    run_id: str,
    node_id: int,
    horizon: str,
    farm_id: int | None,
    variety_id: int | None,
    model_version: str,
    evaluation_mask_hash: str,
    metric_family: str,
    decimal_scale: int,
) -> str:
    payload = {
        "run": run_id,
        "node": str(node_id),
        "horizon": horizon,
        "farm": "" if farm_id is None else str(farm_id),
        "variety": "" if variety_id is None else str(variety_id),
        "model_version": model_version,
        "evaluation_mask_hash": evaluation_mask_hash,
        "metric_family": metric_family,
        "decimal_scale": str(decimal_scale),
    }
    return canonical_payload_hash(payload)


def _ordered(rows: Iterable[EvaluationMetricRow]) -> list[EvaluationMetricRow]:
    return sorted(rows, key=lambda r: (r.node_id, r.evaluation_as_of_date, r.forecast_output_id))


# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------


def row_count(rows: Iterable[EvaluationMetricRow], mask: EvaluationMaskState) -> int:
    materialized = _validate_rows(rows, expected_mask_hash=mask.evaluation_mask_hash)
    return len(materialized)


def comparable_row_count(
    rows: Iterable[EvaluationMetricRow],
    mask: EvaluationMaskState,
) -> int:
    materialized = _validate_rows(rows, expected_mask_hash=mask.evaluation_mask_hash)
    return sum(1 for r in materialized if _is_comparable(r))


def masked_row_count(rows: Iterable[EvaluationMetricRow], mask: EvaluationMaskState) -> int:
    materialized = _validate_rows(rows, expected_mask_hash=mask.evaluation_mask_hash)
    return sum(1 for r in materialized if r.mask_state in _MASKED_STATES)


def withheld_row_count(rows: Iterable[EvaluationMetricRow], mask: EvaluationMaskState) -> int:
    materialized = _validate_rows(rows, expected_mask_hash=mask.evaluation_mask_hash)
    return sum(1 for r in materialized if r.mask_state == MaskState.WITHHELD)


# ---------------------------------------------------------------------------
# Aggregate error metrics
# ---------------------------------------------------------------------------


def mean_absolute_error(
    rows: Iterable[EvaluationMetricRow],
    mask: EvaluationMaskState,
    *,
    scope: Mapping[str, Any],
    decimal_scale: int = DEFAULT_DECIMAL_SCALE,
) -> MetricOutput:
    materialized = _ordered(_validate_rows(rows, expected_mask_hash=mask.evaluation_mask_hash))
    comparable = [r for r in materialized if _is_comparable(r)]
    blockers: list[MetricBlocker] = []
    if not comparable:
        blockers.append(
            MetricBlocker(
                kind=MetricBlockerKind.ZERO_DENOMINATOR,
                metric="mean_absolute_error",
                scope_id=scope_identity_for(
                    scope, decimal_scale=decimal_scale, metric_family="mean_absolute_error"
                ),
                message="comparable_row_count == 0; cannot compute MAE",
                evaluation_mask_hash=mask.evaluation_mask_hash,
            )
        )
        return _output(
            "mean_absolute_error",
            None,
            len(comparable),
            mask.evaluation_mask_hash,
            decimal_scale,
            tuple(blockers),
            scope,
        )
    diffs: list[Decimal] = [
        r.prediction - r.target
        for r in comparable
        if r.prediction is not None and r.target is not None
    ]
    total = sum((abs(d) for d in diffs), Decimal(0))
    value = _quantize(total / Decimal(len(comparable)), decimal_scale)
    return _output(
        "mean_absolute_error",
        value,
        len(comparable),
        mask.evaluation_mask_hash,
        decimal_scale,
        tuple(blockers),
        scope,
    )


def wmape(
    rows: Iterable[EvaluationMetricRow],
    mask: EvaluationMaskState,
    *,
    scope: Mapping[str, Any],
    decimal_scale: int = DEFAULT_DECIMAL_SCALE,
) -> MetricOutput:
    """Weighted Mean Absolute Percentage Error (``sum(|err|) / sum(|target|)``).

    Returns ``MetricBlocker(ZERO_DENOMINATOR)`` when ``sum(|target|) == 0``
    on the comparable set (per design §3.3 zero-denominator rule + the
    implementation guidance in the issue that reserves WMAPE alongside MAE).
    """

    materialized = _ordered(_validate_rows(rows, expected_mask_hash=mask.evaluation_mask_hash))
    comparable = [r for r in materialized if _is_comparable(r)]
    blockers: list[MetricBlocker] = []
    if not comparable:
        blockers.append(
            MetricBlocker(
                kind=MetricBlockerKind.ZERO_DENOMINATOR,
                metric="wmape",
                scope_id=scope_identity_for(
                    scope, decimal_scale=decimal_scale, metric_family="wmape"
                ),
                message="comparable_row_count == 0; cannot compute WMAPE",
                evaluation_mask_hash=mask.evaluation_mask_hash,
            )
        )
        return _output(
            "wmape",
            None,
            len(comparable),
            mask.evaluation_mask_hash,
            decimal_scale,
            tuple(blockers),
            scope,
        )
    abs_err_sum = sum(
        (
            abs(r.prediction - r.target)
            for r in comparable
            if r.prediction is not None and r.target is not None
        ),
        Decimal(0),
    )
    abs_target_sum = sum((abs(r.target) for r in comparable if r.target is not None), Decimal(0))
    if abs_target_sum == 0:
        blockers.append(
            MetricBlocker(
                kind=MetricBlockerKind.ZERO_DENOMINATOR,
                metric="wmape",
                scope_id=scope_identity_for(
                    scope, decimal_scale=decimal_scale, metric_family="wmape"
                ),
                message="sum(|target|) == 0; WMAPE denominator is zero",
                evaluation_mask_hash=mask.evaluation_mask_hash,
            )
        )
        return _output(
            "wmape",
            None,
            len(comparable),
            mask.evaluation_mask_hash,
            decimal_scale,
            tuple(blockers),
            scope,
        )
    value = _quantize(abs_err_sum / abs_target_sum, decimal_scale)
    return _output(
        "wmape",
        value,
        len(comparable),
        mask.evaluation_mask_hash,
        decimal_scale,
        tuple(blockers),
        scope,
    )


def cumulative_relative_error(
    rows: Iterable[EvaluationMetricRow],
    mask: EvaluationMaskState,
    *,
    scope: Mapping[str, Any],
    decimal_scale: int = DEFAULT_DECIMAL_SCALE,
) -> MetricOutput:
    materialized = _ordered(_validate_rows(rows, expected_mask_hash=mask.evaluation_mask_hash))
    comparable = [r for r in materialized if _is_comparable(r)]
    blockers: list[MetricBlocker] = []
    if not comparable:
        blockers.append(
            MetricBlocker(
                kind=MetricBlockerKind.ZERO_DENOMINATOR,
                metric="cumulative_relative_error",
                scope_id=scope_identity_for(
                    scope, decimal_scale=decimal_scale, metric_family="cumulative_relative_error"
                ),
                message="comparable_row_count == 0; cannot compute cumulative relative error",
                evaluation_mask_hash=mask.evaluation_mask_hash,
            )
        )
        return _output(
            "cumulative_relative_error",
            None,
            len(comparable),
            mask.evaluation_mask_hash,
            decimal_scale,
            tuple(blockers),
            scope,
        )
    abs_err_sum = sum(
        (
            abs(r.prediction - r.target)
            for r in comparable
            if r.prediction is not None and r.target is not None
        ),
        Decimal(0),
    )
    abs_target_sum = sum((abs(r.target) for r in comparable if r.target is not None), Decimal(0))
    if abs_target_sum == 0:
        blockers.append(
            MetricBlocker(
                kind=MetricBlockerKind.ZERO_DENOMINATOR,
                metric="cumulative_relative_error",
                scope_id=scope_identity_for(
                    scope, decimal_scale=decimal_scale, metric_family="cumulative_relative_error"
                ),
                message="sum(|target|) == 0; cumulative relative error denominator is zero",
                evaluation_mask_hash=mask.evaluation_mask_hash,
            )
        )
        return _output(
            "cumulative_relative_error",
            None,
            len(comparable),
            mask.evaluation_mask_hash,
            decimal_scale,
            tuple(blockers),
            scope,
        )
    value = _quantize(abs_err_sum / abs_target_sum, decimal_scale)
    return _output(
        "cumulative_relative_error",
        value,
        len(comparable),
        mask.evaluation_mask_hash,
        decimal_scale,
        tuple(blockers),
        scope,
    )


def pinball_loss_p50(
    rows: Iterable[EvaluationMetricRow],
    mask: EvaluationMaskState,
    *,
    scope: Mapping[str, Any],
    decimal_scale: int = DEFAULT_DECIMAL_SCALE,
) -> MetricOutput:
    materialized = _ordered(_validate_rows(rows, expected_mask_hash=mask.evaluation_mask_hash))
    comparable = [r for r in materialized if _is_comparable(r)]
    blockers: list[MetricBlocker] = []
    if not comparable:
        blockers.append(
            MetricBlocker(
                kind=MetricBlockerKind.ZERO_DENOMINATOR,
                metric="pinball_loss_p50",
                scope_id=scope_identity_for(
                    scope, decimal_scale=decimal_scale, metric_family="pinball_loss_p50"
                ),
                message="comparable_row_count == 0; cannot compute pinball loss",
                evaluation_mask_hash=mask.evaluation_mask_hash,
            )
        )
        return _output(
            "pinball_loss_p50",
            None,
            len(comparable),
            mask.evaluation_mask_hash,
            decimal_scale,
            tuple(blockers),
            scope,
        )
    tau = Decimal("0.5")
    total = Decimal(0)
    for r in comparable:
        if r.prediction is None or r.target is None:
            continue
        diff = r.prediction - r.target
        if diff >= 0:
            total += tau * diff
        else:
            total += (tau - Decimal(1)) * diff
    value = _quantize(total / Decimal(len(comparable)), decimal_scale)
    return _output(
        "pinball_loss_p50",
        value,
        len(comparable),
        mask.evaluation_mask_hash,
        decimal_scale,
        tuple(blockers),
        scope,
    )


def empirical_coverage_p50(
    rows: Iterable[EvaluationMetricRow],
    mask: EvaluationMaskState,
    *,
    scope: Mapping[str, Any],
    decimal_scale: int = DEFAULT_DECIMAL_SCALE,
) -> MetricOutput:
    materialized = _ordered(_validate_rows(rows, expected_mask_hash=mask.evaluation_mask_hash))
    blockers: list[MetricBlocker] = []
    if not materialized:
        blockers.append(
            MetricBlocker(
                kind=MetricBlockerKind.ZERO_DENOMINATOR,
                metric="empirical_coverage_p50",
                scope_id=scope_identity_for(
                    scope, decimal_scale=decimal_scale, metric_family="empirical_coverage_p50"
                ),
                message="row_count == 0; cannot compute empirical coverage",
                evaluation_mask_hash=mask.evaluation_mask_hash,
            )
        )
        return _output(
            "empirical_coverage_p50",
            None,
            0,
            mask.evaluation_mask_hash,
            decimal_scale,
            tuple(blockers),
            scope,
        )
    in_band = 0
    denom = 0
    for r in materialized:
        if r.p50_low is None or r.p50_high is None or r.target is None:
            continue
        if r.mask_state in (MaskState.EXCLUDED, MaskState.BLOCKED, MaskState.WITHHELD):
            continue
        denom += 1
        if r.p50_low <= r.target <= r.p50_high:
            in_band += 1
    if denom == 0:
        blockers.append(
            MetricBlocker(
                kind=MetricBlockerKind.ZERO_DENOMINATOR,
                metric="empirical_coverage_p50",
                scope_id=scope_identity_for(
                    scope, decimal_scale=decimal_scale, metric_family="empirical_coverage_p50"
                ),
                message="comparable_row_count == 0 for coverage; cannot compute empirical coverage",
                evaluation_mask_hash=mask.evaluation_mask_hash,
            )
        )
        return _output(
            "empirical_coverage_p50",
            None,
            0,
            mask.evaluation_mask_hash,
            decimal_scale,
            tuple(blockers),
            scope,
        )
    value = _quantize(Decimal(in_band) / Decimal(denom), decimal_scale)
    return _output(
        "empirical_coverage_p50",
        value,
        denom,
        mask.evaluation_mask_hash,
        decimal_scale,
        tuple(blockers),
        scope,
    )


# ---------------------------------------------------------------------------
# Peak / interval-width / crossing metrics
# ---------------------------------------------------------------------------


def peak_date_error_days_p50(
    rows: Iterable[EvaluationMetricRow],
    mask: EvaluationMaskState,
    *,
    scope: Mapping[str, Any],
    decimal_scale: int = DEFAULT_DECIMAL_SCALE,
) -> MetricOutput:
    materialized = _ordered(_validate_rows(rows, expected_mask_hash=mask.evaluation_mask_hash))
    blockers: list[MetricBlocker] = []
    comparable = [r for r in materialized if _is_comparable(r) and r.peak_date is not None]
    if not comparable:
        blockers.append(
            MetricBlocker(
                kind=MetricBlockerKind.ZERO_DENOMINATOR,
                metric="peak_date_error_days_p50",
                scope_id=scope_identity_for(
                    scope, decimal_scale=decimal_scale, metric_family="peak_date_error_days_p50"
                ),
                message="no comparable rows with peak_date; cannot compute peak-date error",
                evaluation_mask_hash=mask.evaluation_mask_hash,
            )
        )
        return _output(
            "peak_date_error_days_p50",
            None,
            len(comparable),
            mask.evaluation_mask_hash,
            decimal_scale,
            tuple(blockers),
            scope,
        )
    abs_diffs: list[int] = []
    for r in comparable:
        if r.peak_date is None:
            continue
        abs_diffs.append(abs((r.peak_date - r.evaluation_as_of_date).days))
    median = _median(abs_diffs)
    value = _quantize(Decimal(median), decimal_scale)
    return _output(
        "peak_date_error_days_p50",
        value,
        len(comparable),
        mask.evaluation_mask_hash,
        decimal_scale,
        tuple(blockers),
        scope,
    )


def peak_magnitude_error_p50(
    rows: Iterable[EvaluationMetricRow],
    mask: EvaluationMaskState,
    *,
    scope: Mapping[str, Any],
    decimal_scale: int = DEFAULT_DECIMAL_SCALE,
) -> MetricOutput:
    materialized = _ordered(_validate_rows(rows, expected_mask_hash=mask.evaluation_mask_hash))
    blockers: list[MetricBlocker] = []
    comparable_targets: list[Decimal] = [
        r.target for r in materialized if _is_comparable(r) and r.target is not None
    ]
    comparable_predictions: list[Decimal] = [
        r.prediction for r in materialized if _is_comparable(r) and r.prediction is not None
    ]
    if not comparable_targets or not comparable_predictions:
        blockers.append(
            MetricBlocker(
                kind=MetricBlockerKind.ZERO_DENOMINATOR,
                metric="peak_magnitude_error_p50",
                scope_id=scope_identity_for(
                    scope, decimal_scale=decimal_scale, metric_family="peak_magnitude_error_p50"
                ),
                message="no comparable rows; cannot compute peak magnitude error",
                evaluation_mask_hash=mask.evaluation_mask_hash,
            )
        )
        return _output(
            "peak_magnitude_error_p50",
            None,
            len(comparable_targets),
            mask.evaluation_mask_hash,
            decimal_scale,
            tuple(blockers),
            scope,
        )
    peak_target = max(comparable_targets)
    peak_prediction = max(comparable_predictions)
    value = _quantize(abs(peak_prediction - peak_target), decimal_scale)
    return _output(
        "peak_magnitude_error_p50",
        value,
        len(comparable_targets),
        mask.evaluation_mask_hash,
        decimal_scale,
        tuple(blockers),
        scope,
    )


def quantile_crossing_count(
    rows: Iterable[EvaluationMetricRow],
    mask: EvaluationMaskState,
    *,
    scope: Mapping[str, Any],
    decimal_scale: int = DEFAULT_DECIMAL_SCALE,
) -> MetricOutput:
    materialized = _ordered(_validate_rows(rows, expected_mask_hash=mask.evaluation_mask_hash))
    blockers: list[MetricBlocker] = []
    crossings = 0
    for r in materialized:
        if r.mask_state in (MaskState.EXCLUDED, MaskState.BLOCKED, MaskState.WITHHELD):
            continue
        if r.p50_low is None or r.p50_high is None or r.p80_low is None or r.p80_high is None:
            continue
        # Crossing = inner (p50) band extends beyond outer (p80) band.
        if r.p50_low < r.p80_low or r.p50_high > r.p80_high:
            crossings += 1
    value = _quantize(Decimal(crossings), decimal_scale)
    return _output(
        "quantile_crossing_count",
        value,
        len(materialized),
        mask.evaluation_mask_hash,
        decimal_scale,
        tuple(blockers),
        scope,
    )


def _interval_width(p_low: Decimal, p_high: Decimal) -> Decimal:
    return p_high - p_low


def interval_width_mean_p80_p50(
    rows: Iterable[EvaluationMetricRow],
    mask: EvaluationMaskState,
    *,
    scope: Mapping[str, Any],
    decimal_scale: int = DEFAULT_DECIMAL_SCALE,
) -> MetricOutput:
    materialized = _ordered(_validate_rows(rows, expected_mask_hash=mask.evaluation_mask_hash))
    blockers: list[MetricBlocker] = []
    widths: list[Decimal] = []
    for r in materialized:
        if r.mask_state in (MaskState.EXCLUDED, MaskState.BLOCKED, MaskState.WITHHELD):
            continue
        if r.p50_low is None or r.p50_high is None or r.p80_low is None or r.p80_high is None:
            continue
        widths.append(
            _interval_width(r.p80_low, r.p80_high) - _interval_width(r.p50_low, r.p50_high)
        )
    if not widths:
        blockers.append(
            MetricBlocker(
                kind=MetricBlockerKind.ZERO_DENOMINATOR,
                metric="interval_width_mean_p80_p50",
                scope_id=scope_identity_for(
                    scope, decimal_scale=decimal_scale, metric_family="interval_width_mean_p80_p50"
                ),
                message="no comparable rows with p50/p80 interval bounds",
                evaluation_mask_hash=mask.evaluation_mask_hash,
            )
        )
        return _output(
            "interval_width_mean_p80_p50",
            None,
            0,
            mask.evaluation_mask_hash,
            decimal_scale,
            tuple(blockers),
            scope,
        )
    value = _quantize(sum(widths, Decimal(0)) / Decimal(len(widths)), decimal_scale)
    return _output(
        "interval_width_mean_p80_p50",
        value,
        len(widths),
        mask.evaluation_mask_hash,
        decimal_scale,
        tuple(blockers),
        scope,
    )


def interval_width_median_p80_p50(
    rows: Iterable[EvaluationMetricRow],
    mask: EvaluationMaskState,
    *,
    scope: Mapping[str, Any],
    decimal_scale: int = DEFAULT_DECIMAL_SCALE,
) -> MetricOutput:
    materialized = _ordered(_validate_rows(rows, expected_mask_hash=mask.evaluation_mask_hash))
    blockers: list[MetricBlocker] = []
    widths: list[Decimal] = []
    for r in materialized:
        if r.mask_state in (MaskState.EXCLUDED, MaskState.BLOCKED, MaskState.WITHHELD):
            continue
        if r.p50_low is None or r.p50_high is None or r.p80_low is None or r.p80_high is None:
            continue
        widths.append(
            _interval_width(r.p80_low, r.p80_high) - _interval_width(r.p50_low, r.p50_high)
        )
    if not widths:
        blockers.append(
            MetricBlocker(
                kind=MetricBlockerKind.ZERO_DENOMINATOR,
                metric="interval_width_median_p80_p50",
                scope_id=scope_identity_for(
                    scope,
                    decimal_scale=decimal_scale,
                    metric_family="interval_width_median_p80_p50",
                ),
                message="no comparable rows with p50/p80 interval bounds",
                evaluation_mask_hash=mask.evaluation_mask_hash,
            )
        )
        return _output(
            "interval_width_median_p80_p50",
            None,
            0,
            mask.evaluation_mask_hash,
            decimal_scale,
            tuple(blockers),
            scope,
        )
    value = _quantize(Decimal(_median(widths)), decimal_scale)
    return _output(
        "interval_width_median_p80_p50",
        value,
        len(widths),
        mask.evaluation_mask_hash,
        decimal_scale,
        tuple(blockers),
        scope,
    )


# ---------------------------------------------------------------------------
# Correction metrics (against the Phase 4a corrected-vs-structural path)
# ---------------------------------------------------------------------------


def correction_magnitude_count(
    structural_rows: Iterable[EvaluationMetricRow],
    corrected_rows: Iterable[EvaluationMetricRow],
    mask: EvaluationMaskState,
    *,
    scope: Mapping[str, Any],
    decimal_scale: int = DEFAULT_DECIMAL_SCALE,
) -> MetricOutput:
    return _correction_metric(
        structural_rows,
        corrected_rows,
        mask,
        scope=scope,
        decimal_scale=decimal_scale,
        count_only=True,
    )


def correction_magnitude_median(
    structural_rows: Iterable[EvaluationMetricRow],
    corrected_rows: Iterable[EvaluationMetricRow],
    mask: EvaluationMaskState,
    *,
    scope: Mapping[str, Any],
    decimal_scale: int = DEFAULT_DECIMAL_SCALE,
) -> MetricOutput:
    return _correction_metric(
        structural_rows,
        corrected_rows,
        mask,
        scope=scope,
        decimal_scale=decimal_scale,
        count_only=False,
    )


def _correction_metric(
    structural_rows: Iterable[EvaluationMetricRow],
    corrected_rows: Iterable[EvaluationMetricRow],
    mask: EvaluationMaskState,
    *,
    scope: Mapping[str, Any],
    decimal_scale: int,
    count_only: bool,
) -> MetricOutput:
    metric_name = "correction_magnitude_count" if count_only else "correction_magnitude_median"
    # Validate each input set for dup rows + mask hash independently.
    structural = _ordered(
        _validate_rows(structural_rows, expected_mask_hash=mask.evaluation_mask_hash)
    )
    corrected = _ordered(
        _validate_rows(corrected_rows, expected_mask_hash=mask.evaluation_mask_hash)
    )
    # structural_corrected_row_set_parity: identities must match, but row
    # objects themselves can differ (predictions will differ). Compare
    # identity keys only.
    structural_ids = {_row_identity(r) for r in structural}
    corrected_ids = {_row_identity(r) for r in corrected}
    if structural_ids != corrected_ids:
        raise MetricInputError(
            "structural and corrected row identities differ; "
            "structural_corrected_row_set_parity violated"
        )
    # Index by identity for diffing.
    structural_by_id: dict[tuple[int, int, date], EvaluationMetricRow] = {
        _row_identity(r): r for r in structural
    }
    corrected_by_id: dict[tuple[int, int, date], EvaluationMetricRow] = {
        _row_identity(r): r for r in corrected
    }
    diffs: list[Decimal] = []
    for ident in sorted(corrected_ids):
        s_row = structural_by_id[ident]
        c_row = corrected_by_id[ident]
        if c_row.prediction is None or s_row.prediction is None:
            continue
        if c_row.mask_state in (MaskState.EXCLUDED, MaskState.BLOCKED, MaskState.WITHHELD):
            continue
        if s_row.mask_state in (MaskState.EXCLUDED, MaskState.BLOCKED, MaskState.WITHHELD):
            continue
        diffs.append(abs(c_row.prediction - s_row.prediction))
    if count_only:
        value = _quantize(Decimal(len(diffs)), decimal_scale)
    else:
        if not diffs:
            return _output(
                metric_name,
                None,
                0,
                mask.evaluation_mask_hash,
                decimal_scale,
                (
                    MetricBlocker(
                        kind=MetricBlockerKind.ZERO_DENOMINATOR,
                        metric=metric_name,
                        scope_id=scope_identity_for(
                            scope, decimal_scale=decimal_scale, metric_family=metric_name
                        ),
                        message="no correction pairs; cannot compute median magnitude",
                        evaluation_mask_hash=mask.evaluation_mask_hash,
                    ),
                ),
                scope,
            )
        value = _quantize(Decimal(_median(diffs)), decimal_scale)
    return _output(
        metric_name,
        value,
        len(diffs),
        mask.evaluation_mask_hash,
        decimal_scale,
        (),
        scope,
    )


# ---------------------------------------------------------------------------
# Helpers (output, scope identity, median)
# ---------------------------------------------------------------------------


def scope_identity_for(
    scope: Mapping[str, Any],
    *,
    decimal_scale: int,
    metric_family: str,
) -> str:
    run_id = str(scope.get("run", ""))
    node_id = scope.get("node")
    if node_id is None:
        raise MetricInputError("scope must include 'node'")
    horizon = str(scope.get("horizon", "daily"))
    farm_id = scope.get("farm")
    variety_id = scope.get("variety")
    model_version = str(scope.get("model_version", ""))
    evaluation_mask_hash = str(scope.get("evaluation_mask_hash", ""))
    return _scope_identity(
        run_id=run_id,
        node_id=int(node_id),
        horizon=horizon,
        farm_id=int(farm_id) if farm_id is not None else None,
        variety_id=int(variety_id) if variety_id is not None else None,
        model_version=model_version,
        evaluation_mask_hash=evaluation_mask_hash,
        metric_family=metric_family,
        decimal_scale=decimal_scale,
    )


def _output(
    metric_name: str,
    value: Decimal | None,
    comparable_row_count: int,
    evaluation_mask_hash: str,
    decimal_scale: int,
    blockers: tuple[MetricBlocker, ...],
    scope: Mapping[str, Any],
) -> MetricOutput:
    scope_id = scope_identity_for(scope, decimal_scale=decimal_scale, metric_family=metric_name)
    return MetricOutput(
        metric_name=metric_name,
        metric_value=value,
        metric_scope_identity=scope_id,
        evaluation_mask_hash=evaluation_mask_hash,
        comparable_row_count=comparable_row_count,
        blocked_reasons=blockers,
        decimal_scale=decimal_scale,
    )


def _median(values: list[int] | list[Decimal]) -> int | Decimal:
    if not values:
        raise ValueError("cannot take median of empty sequence")
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2 == 1:
        result = ordered[mid]
        return cast(int | Decimal, result)
    # Even-length sequence: average the two middle values.
    left = cast(int | Decimal, ordered[mid - 1])
    right = cast(int | Decimal, ordered[mid])
    if isinstance(left, int) and isinstance(right, int):
        # Keep int when both are int and even sum is exactly representable.
        summed = left + right
        if summed % 2 == 0:
            return summed // 2
        # Odd sum: return as Decimal so the half is exact.
        return Decimal(summed) / Decimal(2)
    return (Decimal(left) + Decimal(right)) / Decimal(2)


# ---------------------------------------------------------------------------
# Public surface — top-level evaluation entry point
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    """Aggregate of every metric output for a single scope."""

    outputs: tuple[MetricOutput, ...]
    canonical_payload_hash: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "outputs": [o.to_audit_payload() for o in self.outputs],
            "canonical_payload_hash": self.canonical_payload_hash,
            "metric_definition_version": METRIC_DEFINITION_VERSION,
        }


def evaluate_scope(
    rows: Iterable[EvaluationMetricRow],
    mask: EvaluationMaskState,
    *,
    scope: Mapping[str, Any],
    decimal_scale: int = DEFAULT_DECIMAL_SCALE,
) -> EvaluationResult:
    """Run every supported metric for a single scope and return a stable payload."""

    materialized = _ordered(_validate_rows(rows, expected_mask_hash=mask.evaluation_mask_hash))
    counter_outputs: list[MetricOutput] = []
    counters: list[MetricOutput] = [
        _counter_output(
            "row_count",
            row_count(materialized, mask),
            mask.evaluation_mask_hash,
            scope,
            decimal_scale,
        ),
        _counter_output(
            "comparable_row_count",
            comparable_row_count(materialized, mask),
            mask.evaluation_mask_hash,
            scope,
            decimal_scale,
        ),
        _counter_output(
            "masked_row_count",
            masked_row_count(materialized, mask),
            mask.evaluation_mask_hash,
            scope,
            decimal_scale,
        ),
        _counter_output(
            "withheld_row_count",
            withheld_row_count(materialized, mask),
            mask.evaluation_mask_hash,
            scope,
            decimal_scale,
        ),
    ]
    counter_outputs.extend(counters)
    aggregate_outputs: list[MetricOutput] = [
        mean_absolute_error(materialized, mask, scope=scope, decimal_scale=decimal_scale),
        wmape(materialized, mask, scope=scope, decimal_scale=decimal_scale),
        cumulative_relative_error(materialized, mask, scope=scope, decimal_scale=decimal_scale),
        pinball_loss_p50(materialized, mask, scope=scope, decimal_scale=decimal_scale),
        empirical_coverage_p50(materialized, mask, scope=scope, decimal_scale=decimal_scale),
        peak_date_error_days_p50(materialized, mask, scope=scope, decimal_scale=decimal_scale),
        peak_magnitude_error_p50(materialized, mask, scope=scope, decimal_scale=decimal_scale),
        quantile_crossing_count(materialized, mask, scope=scope, decimal_scale=decimal_scale),
        interval_width_mean_p80_p50(materialized, mask, scope=scope, decimal_scale=decimal_scale),
        interval_width_median_p80_p50(materialized, mask, scope=scope, decimal_scale=decimal_scale),
    ]
    counter_outputs.extend(aggregate_outputs)
    payload = {
        "outputs": [o.to_audit_payload() for o in counter_outputs],
        "metric_definition_version": METRIC_DEFINITION_VERSION,
    }
    digest = canonical_payload_hash(payload)
    return EvaluationResult(outputs=tuple(counter_outputs), canonical_payload_hash=digest)


def _counter_output(
    metric_name: str,
    count: int,
    evaluation_mask_hash: str,
    scope: Mapping[str, Any],
    decimal_scale: int,
) -> MetricOutput:
    return MetricOutput(
        metric_name=metric_name,
        metric_value=Decimal(count),
        metric_scope_identity=scope_identity_for(
            scope, decimal_scale=decimal_scale, metric_family=metric_name
        ),
        evaluation_mask_hash=evaluation_mask_hash,
        comparable_row_count=count,
        blocked_reasons=(),
        decimal_scale=0,
    )


# ---------------------------------------------------------------------------
# Scoped metrics (split by ``factory_id`` for now; further dimensions reserved)
# ---------------------------------------------------------------------------


def split_by_factory(
    rows: Iterable[EvaluationMetricRow],
    mask: EvaluationMaskState,
    *,
    run_id: str,
    horizon: str,
    model_version: str,
    decimal_scale: int = DEFAULT_DECIMAL_SCALE,
) -> dict[int, EvaluationResult]:
    """Group rows by ``node_id`` (the factory dimension) and evaluate each group.

    The function is intentionally small — Phase 4b design §4 lists the
    supported grouping dimensions but reserves aggregation across scopes to
    Phase 4c. We implement the per-factory split as the only canonical
    grouping in this slice, with room to grow.
    """

    materialized = _ordered(_validate_rows(rows, expected_mask_hash=mask.evaluation_mask_hash))
    by_factory: dict[int, list[EvaluationMetricRow]] = {}
    for row in materialized:
        by_factory.setdefault(row.node_id, []).append(row)
    results: dict[int, EvaluationResult] = {}
    for factory_id, group_rows in sorted(by_factory.items()):
        scope = {
            "run": run_id,
            "node": factory_id,
            "horizon": horizon,
            "farm": None,
            "variety": None,
            "model_version": model_version,
            "evaluation_mask_hash": mask.evaluation_mask_hash,
        }
        results[factory_id] = evaluate_scope(
            group_rows, mask, scope=scope, decimal_scale=decimal_scale
        )
    return results
