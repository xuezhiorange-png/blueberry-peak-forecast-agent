# ruff: noqa: E501
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_EVEN
from enum import StrEnum
from typing import Final, Mapping, Sequence

from backend.app.rolling_backtest.canonical import canonical_json_value, sha256_payload
from backend.app.rolling_backtest.enums import METRIC_POLICY_VERSION

PHASE4B_METRIC_DEFINITION_VERSION: Final[str] = "task11-phase4b-metrics-v1"
DEFAULT_SCOPE_DIMENSIONS: Final[tuple[str, ...]] = (
    "run_id", "node_id", "season_id", "factory_id", "horizon", "calendar_phase", "mode", "model_version"
)


class EvaluationMaskState(StrEnum):
    INCLUDED = "included"
    TRUE_ZERO = "true_zero"
    EXCLUDED = "excluded"
    BLOCKED = "blocked"
    WITHHELD = "withheld"


class MetricBlockerKind(StrEnum):
    ZERO_DENOMINATOR = "zero_denominator"
    ZERO_ACTUAL_DENOMINATOR = "zero_actual_denominator"


@dataclass(frozen=True, slots=True)
class EvaluationMetricRow:
    run_id: str
    node_id: str
    season_id: str
    factory_id: str
    horizon: str
    calendar_phase: str
    mode: str
    model_version: str
    forecast_output_id: str
    evaluation_as_of_date: date
    mask_state: EvaluationMaskState = EvaluationMaskState.INCLUDED
    target_kg: Decimal | None = None
    prediction_p50_kg: Decimal | None = None
    prediction_p80_kg: Decimal | None = None
    prediction_p90_kg: Decimal | None = None
    structural_p50_kg: Decimal | None = None
    corrected_p50_kg: Decimal | None = None

    @property
    def row_identity(self) -> tuple[str, str, str]:
        return (self.forecast_output_id, self.node_id, self.evaluation_as_of_date.isoformat())


@dataclass(frozen=True, slots=True)
class MetricBlocker:
    kind: MetricBlockerKind
    metric_name: str
    reason: str

    def to_payload(self) -> dict[str, str]:
        return {"kind": self.kind.value, "metric_name": self.metric_name, "reason": self.reason}


@dataclass(frozen=True, slots=True)
class MetricOutput:
    metric_name: str
    metric_scope_identity: str
    scope: Mapping[str, str]
    value: Decimal | int | None
    blocker: MetricBlocker | None
    audit_payload: Mapping[str, object]

    def canonical_payload(self) -> dict[str, object]:
        return {
            "audit_payload": self.audit_payload,
            "blocker": None if self.blocker is None else self.blocker.to_payload(),
            "metric_name": self.metric_name,
            "metric_scope_identity": self.metric_scope_identity,
            "scope": dict(self.scope),
            "value": canonical_json_value(self.value),
        }

    def canonical_payload_hash(self) -> str:
        return sha256_payload(self.canonical_payload())


type Pair = tuple[EvaluationMetricRow, Decimal, Decimal]


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_EVEN)


def _mean(values: Sequence[Decimal]) -> Decimal:
    return _q(sum(values, Decimal("0")) / Decimal(len(values)))


def _median(values: Sequence[Decimal]) -> Decimal:
    ordered = tuple(sorted(values))
    mid = len(ordered) // 2
    return _q(ordered[mid]) if len(ordered) % 2 else _mean((ordered[mid - 1], ordered[mid]))


def _active(row: EvaluationMetricRow) -> bool:
    return row.mask_state in {EvaluationMaskState.INCLUDED, EvaluationMaskState.TRUE_ZERO}


def _scope_value(row: EvaluationMetricRow, dimension: str) -> str:
    return str(getattr(row, dimension))


def _pairs(rows: Sequence[EvaluationMetricRow]) -> list[Pair]:
    pairs: list[Pair] = []
    for row in rows:
        if not _active(row) or row.target_kg is None or row.prediction_p50_kg is None:
            continue
        pairs.append((row, row.target_kg, row.prediction_p50_kg))
    return pairs


def _id(scope: Mapping[str, str], metric: str, mask_hash: str, version: str) -> str:
    return sha256_payload({"evaluation_mask_hash": mask_hash, "metric_definition_version": version, "metric_name": metric, "scope": dict(scope)})


def _out(metric: str, scope: Mapping[str, str], value: Decimal | int | None, error: MetricBlocker | None, rows: Sequence[EvaluationMetricRow], pair_count: int, mask_hash: str, version: str) -> MetricOutput:
    identity = _id(scope, metric, mask_hash, version)
    return MetricOutput(metric, identity, scope, value, error, {"blocked_reasons": [] if error is None else [error.to_payload()], "comparable_row_count": pair_count, "evaluation_mask_hash": mask_hash, "metric_definition_version": version, "metric_name": metric, "metric_policy_version": METRIC_POLICY_VERSION, "metric_scope_identity": identity, "row_count": len(rows)})


def validate_unique_row_identities(rows: Sequence[EvaluationMetricRow]) -> None:
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        if row.row_identity in seen:
            raise ValueError("duplicate evaluation row identity")
        seen.add(row.row_identity)


def _scope_metrics(scope: Mapping[str, str], rows: Sequence[EvaluationMetricRow], mask_hash: str, version: str) -> list[MetricOutput]:
    pairs = _pairs(rows)
    outputs: list[MetricOutput] = []
    masked = sum(1 for row in rows if row.mask_state in {EvaluationMaskState.EXCLUDED, EvaluationMaskState.BLOCKED})
    withheld = sum(1 for row in rows if row.mask_state is EvaluationMaskState.WITHHELD)
    for metric, value in (("row_count", len(rows)), ("comparable_row_count", len(pairs)), ("masked_row_count", masked), ("withheld_row_count", withheld)):
        outputs.append(_out(metric, scope, value, None, rows, len(pairs), mask_hash, version))
    if not pairs:
        for metric in ("mean_absolute_error", "wmape", "cumulative_relative_error"):
            error = MetricBlocker(MetricBlockerKind.ZERO_DENOMINATOR, metric, "no comparable rows")
            outputs.append(_out(metric, scope, None, error, rows, 0, mask_hash, version))
        return outputs

    errors = [prediction - actual for _, actual, prediction in pairs]
    abs_errors = [abs(error) for error in errors]
    total_actual = sum((actual for _, actual, _ in pairs), Decimal("0"))
    total_prediction = sum((prediction for _, _, prediction in pairs), Decimal("0"))
    outputs.append(_out("mean_absolute_error", scope, _mean(abs_errors), None, rows, len(pairs), mask_hash, version))
    for metric, numerator in (("wmape", sum(abs_errors, Decimal("0"))), ("cumulative_relative_error", total_prediction - total_actual)):
        if total_actual == 0:
            error = MetricBlocker(MetricBlockerKind.ZERO_ACTUAL_DENOMINATOR, metric, "actual total is zero")
            outputs.append(_out(metric, scope, None, error, rows, len(pairs), mask_hash, version))
        else:
            outputs.append(_out(metric, scope, _q(numerator / total_actual), None, rows, len(pairs), mask_hash, version))
    outputs.append(_out("pinball_loss_p50", scope, _mean([Decimal("0.5") * abs(error) for error in errors]), None, rows, len(pairs), mask_hash, version))
    covered = sum(1 for _, actual, prediction in pairs if actual <= prediction)
    outputs.append(_out("empirical_coverage_p50", scope, _q(Decimal(covered) / Decimal(len(pairs))), None, rows, len(pairs), mask_hash, version))

    actual_peak = min(pairs, key=lambda item: (-item[1], item[0].evaluation_as_of_date, item[0].forecast_output_id))
    predicted_peak = min(pairs, key=lambda item: (-item[2], item[0].evaluation_as_of_date, item[0].forecast_output_id))
    outputs.append(_out("peak_date_error_days_p50", scope, (predicted_peak[0].evaluation_as_of_date - actual_peak[0].evaluation_as_of_date).days, None, rows, len(pairs), mask_hash, version))
    outputs.append(_out("peak_magnitude_error_p50", scope, _q(predicted_peak[2] - actual_peak[1]), None, rows, len(pairs), mask_hash, version))

    active_rows = [row for row in rows if _active(row)]
    crossings = sum(1 for row in active_rows if (row.prediction_p50_kg is not None and row.prediction_p80_kg is not None and row.prediction_p50_kg > row.prediction_p80_kg) or (row.prediction_p80_kg is not None and row.prediction_p90_kg is not None and row.prediction_p80_kg > row.prediction_p90_kg))
    widths = [row.prediction_p80_kg - row.prediction_p50_kg for row in active_rows if row.prediction_p80_kg is not None and row.prediction_p50_kg is not None]
    corrections = [row.corrected_p50_kg - row.structural_p50_kg for row in active_rows if row.corrected_p50_kg is not None and row.structural_p50_kg is not None]
    outputs.append(_out("quantile_crossing_count", scope, crossings, None, rows, len(pairs), mask_hash, version))
    outputs.append(_out("correction_magnitude_count", scope, len(corrections), None, rows, len(pairs), mask_hash, version))
    if widths:
        outputs.append(_out("interval_width_mean_p80_p50", scope, _mean(widths), None, rows, len(pairs), mask_hash, version))
        outputs.append(_out("interval_width_median_p80_p50", scope, _median(widths), None, rows, len(pairs), mask_hash, version))
    if corrections:
        outputs.append(_out("correction_magnitude_median", scope, _median(corrections), None, rows, len(pairs), mask_hash, version))
    return outputs


def compute_metric_outputs(rows: Sequence[EvaluationMetricRow], *, evaluation_mask_hash: str, scope_dimensions: Sequence[str] = DEFAULT_SCOPE_DIMENSIONS, metric_definition_version: str = PHASE4B_METRIC_DEFINITION_VERSION) -> tuple[MetricOutput, ...]:
    if len(evaluation_mask_hash) != 64 or evaluation_mask_hash.lower() != evaluation_mask_hash:
        raise ValueError("evaluation_mask_hash must be a lowercase SHA-256 hex digest")
    validate_unique_row_identities(rows)
    grouped: defaultdict[tuple[tuple[str, str], ...], list[EvaluationMetricRow]] = defaultdict(list)
    for row in rows:
        grouped[tuple((dimension, _scope_value(row, dimension)) for dimension in scope_dimensions)].append(row)
    outputs: list[MetricOutput] = []
    for key, group in sorted(grouped.items()):
        scope = dict(key)
        ordered = tuple(sorted(group, key=lambda row: (row.node_id, row.evaluation_as_of_date, row.forecast_output_id)))
        outputs.extend(_scope_metrics(scope, ordered, evaluation_mask_hash, metric_definition_version))
    return tuple(sorted(outputs, key=lambda item: (tuple(item.scope.items()), item.metric_name)))


def metric_output_by_name(outputs: Sequence[MetricOutput], metric_name: str) -> MetricOutput:
    matches = [output for output in outputs if output.metric_name == metric_name]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one output for metric {metric_name!r}, got {len(matches)}")
    return matches[0]
