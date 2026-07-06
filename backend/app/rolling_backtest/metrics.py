from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_EVEN
from enum import StrEnum
from typing import Final, Mapping, Sequence

from backend.app.rolling_backtest.canonical import JsonValue, canonical_json_value, sha256_payload
from backend.app.rolling_backtest.enums import METRIC_POLICY_VERSION

PHASE4B_METRIC_DEFINITION_VERSION: Final[str] = "task11-phase4b-metrics-v1"
DEFAULT_SCOPE_DIMENSIONS: Final[tuple[str, ...]] = (
    "run_id", "node_id", "season_id", "factory_id", "horizon",
    "calendar_phase", "mode", "model_version",
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

    def to_payload(self) -> dict[str, JsonValue]:
        return {"kind": self.kind.value, "metric_name": self.metric_name, "reason": self.reason}


@dataclass(frozen=True, slots=True)
class MetricOutput:
    metric_name: str
    metric_scope_identity: str
    scope: Mapping[str, str]
    value: Decimal | int | None
    blocker: MetricBlocker | None
    audit_payload: Mapping[str, JsonValue]

    def canonical_payload(self) -> dict[str, JsonValue]:
        return {
            "audit_payload": canonical_json_value(self.audit_payload),
            "blocker": None if self.blocker is None else self.blocker.to_payload(),
            "metric_name": self.metric_name,
            "metric_scope_identity": self.metric_scope_identity,
            "scope": canonical_json_value(dict(self.scope)),
            "value": canonical_json_value(self.value),
        }

    def canonical_payload_hash(self) -> str:
        return sha256_payload(self.canonical_payload())


def _scope_value(row: EvaluationMetricRow, dimension: str) -> str:
    return str(getattr(row, dimension))


def _active(row: EvaluationMetricRow) -> bool:
    return row.mask_state in {EvaluationMaskState.INCLUDED, EvaluationMaskState.TRUE_ZERO}


def _q(value: Decimal, scale: int = 8) -> Decimal:
    return value.quantize(Decimal("1").scaleb(-scale), rounding=ROUND_HALF_EVEN)


def _mean(values: Sequence[Decimal]) -> Decimal:
    return _q(sum(values, Decimal("0")) / Decimal(len(values)))


def _median(values: Sequence[Decimal]) -> Decimal:
    ordered = tuple(sorted(values))
    mid = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return _q(ordered[mid])
    return _mean((ordered[mid - 1], ordered[mid]))


def _scope_identity(
    scope: Mapping[str, str], metric: str, evaluation_mask_hash: str, version: str
) -> str:
    return sha256_payload(
        {
            "evaluation_mask_hash": evaluation_mask_hash,
            "metric_definition_version": version,
            "metric_name": metric,
            "scope": dict(scope),
        }
    )


def _output(
    metric: str,
    scope: Mapping[str, str],
    value: Decimal | int | None,
    error: MetricBlocker | None,
    rows: Sequence[EvaluationMetricRow],
    comparable_count: int,
    evaluation_mask_hash: str,
    version: str,
) -> MetricOutput:
    identity = _scope_identity(scope, metric, evaluation_mask_hash, version)
    return MetricOutput(
        metric_name=metric,
        metric_scope_identity=identity,
        scope=scope,
        value=value,
        blocker=error,
        audit_payload={
            "blocked_reasons": [] if error is None else [error.to_payload()],
            "comparable_row_count": comparable_count,
            "evaluation_mask_hash": evaluation_mask_hash,
            "metric_definition_version": version,
            "metric_name": metric,
            "metric_policy_version": METRIC_POLICY_VERSION,
            "metric_scope_identity": identity,
            "row_count": len(rows),
        },
    )


def validate_unique_row_identities(rows: Sequence[EvaluationMetricRow]) -> None:
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        if row.row_identity in seen:
            raise ValueError("duplicate evaluation row identity")
        seen.add(row.row_identity)


def _compute_one_scope(
    scope: Mapping[str, str],
    rows: Sequence[EvaluationMetricRow],
    evaluation_mask_hash: str,
    version: str,
) -> list[MetricOutput]:
    comparable = [
        row for row in rows
        if _active(row) and row.target_kg is not None and row.prediction_p50_kg is not None
    ]
    out: list[MetricOutput] = []
    masked = sum(1 for row in rows if row.mask_state in {EvaluationMaskState.EXCLUDED, EvaluationMaskState.BLOCKED})
    withheld = sum(1 for row in rows if row.mask_state is EvaluationMaskState.WITHHELD)
    for metric, value in (
        ("row_count", len(rows)),
        ("comparable_row_count", len(comparable)),
        ("masked_row_count", masked),
        ("withheld_row_count", withheld),
    ):
        out.append(_output(metric, scope, value, None, rows, len(comparable), evaluation_mask_hash, version))

    if not comparable:
        for metric in ("mean_absolute_error", "wmape", "cumulative_relative_error"):
            error = MetricBlocker(MetricBlockerKind.ZERO_DENOMINATOR, metric, "no comparable rows")
            out.append(_output(metric, scope, None, error, rows, 0, evaluation_mask_hash, version))
        return out

    actuals = [row.target_kg for row in comparable if row.target_kg is not None]
    p50s = [row.prediction_p50_kg for row in comparable if row.prediction_p50_kg is not None]
    errors = [prediction - actual for prediction, actual in zip(p50s, actuals, strict=True)]
    abs_errors = [abs(error) for error in errors]
    total_actual = sum(actuals, Decimal("0"))
    total_prediction = sum(p50s, Decimal("0"))
    out.append(_output("mean_absolute_error", scope, _mean(abs_errors), None, rows, len(comparable), evaluation_mask_hash, version))

    for metric, numerator in (
        ("wmape", sum(abs_errors, Decimal("0"))),
        ("cumulative_relative_error", total_prediction - total_actual),
    ):
        if total_actual == 0:
            error = MetricBlocker(MetricBlockerKind.ZERO_ACTUAL_DENOMINATOR, metric, "actual total is zero")
            out.append(_output(metric, scope, None, error, rows, len(comparable), evaluation_mask_hash, version))
        else:
            out.append(_output(metric, scope, _q(numerator / total_actual), None, rows, len(comparable), evaluation_mask_hash, version))

    pinball = [Decimal("0.5") * abs(error) for error in errors]
    coverage = sum(1 for row in comparable if row.target_kg <= row.prediction_p50_kg)
    out.append(_output("pinball_loss_p50", scope, _mean(pinball), None, rows, len(comparable), evaluation_mask_hash, version))
    out.append(_output("empirical_coverage_p50", scope, _q(Decimal(coverage) / Decimal(len(comparable))), None, rows, len(comparable), evaluation_mask_hash, version))

    actual_peak = min(comparable, key=lambda row: (-(row.target_kg or Decimal("0")), row.evaluation_as_of_date, row.forecast_output_id))
    predicted_peak = min(comparable, key=lambda row: (-(row.prediction_p50_kg or Decimal("0")), row.evaluation_as_of_date, row.forecast_output_id))
    if actual_peak.target_kg is None or predicted_peak.prediction_p50_kg is None:
        raise AssertionError("comparable peak row has missing data")
    date_error = (predicted_peak.evaluation_as_of_date - actual_peak.evaluation_as_of_date).days
    magnitude_error = predicted_peak.prediction_p50_kg - actual_peak.target_kg
    out.append(_output("peak_date_error_days_p50", scope, date_error, None, rows, len(comparable), evaluation_mask_hash, version))
    out.append(_output("peak_magnitude_error_p50", scope, _q(magnitude_error), None, rows, len(comparable), evaluation_mask_hash, version))

    active_rows = [row for row in rows if _active(row)]
    crossings = sum(
        1 for row in active_rows
        if (row.prediction_p50_kg is not None and row.prediction_p80_kg is not None and row.prediction_p50_kg > row.prediction_p80_kg)
        or (row.prediction_p80_kg is not None and row.prediction_p90_kg is not None and row.prediction_p80_kg > row.prediction_p90_kg)
    )
    widths = [
        row.prediction_p80_kg - row.prediction_p50_kg for row in active_rows
        if row.prediction_p80_kg is not None and row.prediction_p50_kg is not None
    ]
    out.append(_output("quantile_crossing_count", scope, crossings, None, rows, len(comparable), evaluation_mask_hash, version))
    if widths:
        out.append(_output("interval_width_mean_p80_p50", scope, _mean(widths), None, rows, len(comparable), evaluation_mask_hash, version))
        out.append(_output("interval_width_median_p80_p50", scope, _median(widths), None, rows, len(comparable), evaluation_mask_hash, version))

    corrections = [
        row.corrected_p50_kg - row.structural_p50_kg for row in active_rows
        if row.corrected_p50_kg is not None and row.structural_p50_kg is not None
    ]
    out.append(_output("correction_magnitude_count", scope, len(corrections), None, rows, len(comparable), evaluation_mask_hash, version))
    if corrections:
        out.append(_output("correction_magnitude_median", scope, _median(corrections), None, rows, len(comparable), evaluation_mask_hash, version))
    return out


def compute_metric_outputs(
    rows: Sequence[EvaluationMetricRow],
    *,
    evaluation_mask_hash: str,
    scope_dimensions: Sequence[str] = DEFAULT_SCOPE_DIMENSIONS,
    metric_definition_version: str = PHASE4B_METRIC_DEFINITION_VERSION,
) -> tuple[MetricOutput, ...]:
    if len(evaluation_mask_hash) != 64 or evaluation_mask_hash.lower() != evaluation_mask_hash:
        raise ValueError("evaluation_mask_hash must be a lowercase SHA-256 hex digest")
    validate_unique_row_identities(rows)
    grouped: defaultdict[tuple[tuple[str, str], ...], list[EvaluationMetricRow]] = defaultdict(list)
    for row in rows:
        key = tuple((dimension, _scope_value(row, dimension)) for dimension in scope_dimensions)
        grouped[key].append(row)

    outputs: list[MetricOutput] = []
    for key, group in sorted(grouped.items()):
        scope = dict(key)
        ordered = tuple(sorted(group, key=lambda row: (row.node_id, row.evaluation_as_of_date, row.forecast_output_id)))
        outputs.extend(_compute_one_scope(scope, ordered, evaluation_mask_hash, metric_definition_version))
    return tuple(sorted(outputs, key=lambda output: (tuple(output.scope.items()), output.metric_name)))


def metric_output_by_name(outputs: Sequence[MetricOutput], metric_name: str) -> MetricOutput:
    matches = [output for output in outputs if output.metric_name == metric_name]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one output for metric {metric_name!r}, got {len(matches)}")
    return matches[0]
