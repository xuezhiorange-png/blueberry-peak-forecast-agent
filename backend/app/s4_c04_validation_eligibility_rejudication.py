"""Pure re-adjudication of frozen C04 validation evidence.

This module intentionally accepts already-frozen metric observations.  It does
not load SOURCE-002, read VALIDATION rows, invoke a scorer, or touch the
durable validation-budget authority.  It exists so a policy correction can be
replayed against R1 evidence without creating a second evaluation.

The evidence-bound entry point in this module is deliberately stricter than
the low-level policy evaluator: it loads the immutable R1 JSON, verifies its
content digest, extracts all scalar observations from that file, and refuses
to issue a V4 result unless the R1 file contains real per-cell breakdown
evidence.  A compact axis summary is not enough to prove V4 eligibility.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, cast

from backend.app.s4_experiment import (
    REQUIRED_BREAKDOWN_AXES,
    SPARSE_COMPLETE_WINDOW_METRICS,
    V3_COMPLETE_DAILY_ROWSET_AUTHORITY,
    V3_EVALUATION_SURFACE_ID,
    V3_FORECAST_HORIZONS,
    V3_MISSING_DAY_ZERO_FILL,
    BreakdownAxisEvidence,
    BreakdownCellEvidence,
    CandidateEligibilityResult,
    CoverageQualityEvidence,
    MetricObservation,
    evaluate_candidate_guardrails_v4_breakdown_reporting,
)

C04_REJUDICATION_POLICY: Final[str] = "v0.3-s4-guardrail-policy-v4-breakdown-reporting-floor"
R1_EVIDENCE_RELATIVE_PATH: Final[Path] = Path(
    "docs/v0-3/s4/evidence/s4-c04-controlled-real-validation-r1.json"
)
R1_EVIDENCE_SHA256: Final[str] = "78b1489b28fe0056e1c7fd88165f927c04d16bf1083926048ba4c36e3c1498b3"
R1_BREAKDOWN_EVIDENCE_INSUFFICIENT_REASON: Final[str] = (
    "R1_BREAKDOWN_CELL_EVIDENCE_INSUFFICIENT_FOR_V4_READJUDICATION"
)
R1_EXPECTED_RUN_ORDINALS: Final[tuple[int, ...]] = (1, 2, 3, 4)


class R1EvidenceHashMismatch(ValueError):
    """Raised when the supplied R1 evidence is not the frozen source file."""


class R1EvidenceSchemaError(ValueError):
    """Raised when a frozen R1 evidence payload cannot be parsed safely."""


@dataclass(frozen=True, slots=True)
class FrozenC04RunMetrics:
    """Metric facts copied from one completed R1 run."""

    run_ordinal: int
    multiplier: Decimal
    daily_wape: Decimal
    daily_mae: Decimal
    p80_coverage: Decimal
    p90_coverage: Decimal

    def __post_init__(self) -> None:
        if self.run_ordinal < 0:
            raise ValueError("run_ordinal must be non-negative")
        for name, value in (
            ("multiplier", self.multiplier),
            ("daily_wape", self.daily_wape),
            ("daily_mae", self.daily_mae),
            ("p80_coverage", self.p80_coverage),
            ("p90_coverage", self.p90_coverage),
        ):
            if type(value) is not Decimal or not value.is_finite():
                raise TypeError(f"{name} must be a finite Decimal")


@dataclass(frozen=True, slots=True)
class ParsedC04R1Evidence:
    """Scalar and coverage observations extracted from the immutable R1 JSON."""

    source_path: str
    sha256: str
    candidates: tuple[FrozenC04RunMetrics, ...]
    incumbent: FrozenC04RunMetrics
    candidate_coverage_quality: tuple[CoverageQualityEvidence | None, ...]
    incumbent_coverage_quality: CoverageQualityEvidence | None
    real_breakdown_cell_evidence_available: bool
    missing_breakdown_evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvidenceBoundC04Readjudication:
    """Result of the R3 evidence-bound readjudication entry point."""

    source_path: str
    r1_evidence_sha256: str
    real_breakdown_cell_evidence_available: bool
    run_eligibilities: tuple[str, ...]
    best_validation_run: int | None
    best_multiplier: Decimal | None
    best_daily_wape: Decimal | None
    best_daily_mae: Decimal | None
    validation_outcome: str
    blocker: str | None
    v4_results: tuple[CandidateEligibilityResult, ...] = ()


def _default_r1_evidence_path() -> Path:
    return Path(__file__).resolve().parents[2] / R1_EVIDENCE_RELATIVE_PATH


def _mapping(value: object, *, context: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise R1EvidenceSchemaError(f"{context} must be an object")
    return cast(Mapping[str, object], value)


def _sequence(value: object, *, context: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise R1EvidenceSchemaError(f"{context} must be an array")
    return value


def _decimal_field(payload: Mapping[str, object], field: str, *, context: str) -> Decimal:
    value = payload.get(field)
    if not isinstance(value, str):
        raise R1EvidenceSchemaError(f"{context}.{field} must be a decimal string")
    try:
        parsed = Decimal(value)
    except Exception as exc:  # pragma: no cover - Decimal's concrete errors vary
        raise R1EvidenceSchemaError(f"{context}.{field} is not a Decimal") from exc
    if not parsed.is_finite():
        raise R1EvidenceSchemaError(f"{context}.{field} must be finite")
    return parsed


def _parse_run_metrics(payload: Mapping[str, object], *, context: str) -> FrozenC04RunMetrics:
    ordinal = payload.get("candidate_run_ordinal")
    if type(ordinal) is not int:
        raise R1EvidenceSchemaError(f"{context}.candidate_run_ordinal must be an integer")
    return FrozenC04RunMetrics(
        run_ordinal=ordinal,
        multiplier=_decimal_field(payload, "multiplier", context=context),
        daily_wape=_decimal_field(payload, "candidate_daily_wape", context=context),
        daily_mae=_decimal_field(payload, "candidate_daily_mae", context=context),
        p80_coverage=_decimal_field(payload, "candidate_p80_coverage", context=context),
        p90_coverage=_decimal_field(payload, "candidate_p90_coverage", context=context),
    )


def _parse_cell(
    payload: Mapping[str, object],
    *,
    context: str,
    fallback_cell_id: str | None = None,
) -> BreakdownCellEvidence | None:
    cell_id_value = payload.get("cell_id", fallback_cell_id)
    if not isinstance(cell_id_value, str) or not cell_id_value:
        return None
    comparable_rows = payload.get("comparable_rows", payload.get("comparable_row_count"))
    if type(comparable_rows) is not int or comparable_rows < 0:
        return None
    metric_status = payload.get("metric_status", payload.get("daily_wape_metric_status"))
    if not isinstance(metric_status, str):
        return None
    try:
        return BreakdownCellEvidence(
            cell_id=cell_id_value,
            comparable_rows=comparable_rows,
            metric_status=cast(Any, metric_status),
        )
    except (TypeError, ValueError):
        return None


def _parse_axis_cells(
    payload: Mapping[str, object],
    *,
    axis_name: str,
    context: str,
) -> tuple[BreakdownCellEvidence, ...] | None:
    axis_payload = payload.get(axis_name)
    if not isinstance(axis_payload, Mapping):
        return None

    # A future evidence writer may emit an explicit cells array.  The raw
    # LocalMetricSet shape (cell_id -> cell payload) is also accepted.  The
    # compact R1 summary shape (cell_count/min/max/...) is intentionally
    # rejected because it has no cell identity or cell-level status.
    cells_payload = axis_payload.get("cells")
    if cells_payload is not None:
        cells = _sequence(cells_payload, context=f"{context}.{axis_name}.cells")
        parsed: list[BreakdownCellEvidence] = []
        for index, cell_payload in enumerate(cells):
            cell = _parse_cell(
                _mapping(cell_payload, context=f"{context}.{axis_name}.cells[{index}]"),
                context=f"{context}.{axis_name}.cells[{index}]",
            )
            if cell is None:
                return None
            parsed.append(cell)
        return tuple(parsed)

    if axis_payload and all(isinstance(value, Mapping) for value in axis_payload.values()):
        parsed_by_id: list[BreakdownCellEvidence] = []
        for cell_id, cell_payload in axis_payload.items():
            cell = _parse_cell(
                cast(Mapping[str, object], cell_payload),
                context=f"{context}.{axis_name}.{cell_id}",
                fallback_cell_id=str(cell_id),
            )
            if cell is None:
                return None
            parsed_by_id.append(cell)
        return tuple(parsed_by_id)
    return None


def _parse_coverage_quality(
    payload: Mapping[str, object], *, context: str
) -> tuple[CoverageQualityEvidence | None, tuple[str, ...]]:
    missing: list[str] = []
    breakdown_payload = payload.get("breakdown_metrics")
    if not isinstance(breakdown_payload, Mapping):
        missing.append(f"{context}.breakdown_metrics")
        breakdown_payload = {}

    axes: list[BreakdownAxisEvidence] = []
    for axis_name in REQUIRED_BREAKDOWN_AXES:
        axis_cells = _parse_axis_cells(
            cast(Mapping[str, object], breakdown_payload),
            axis_name=axis_name,
            context=f"{context}.breakdown_metrics",
        )
        if axis_cells is None or not axis_cells:
            missing.append(f"{context}.breakdown_metrics.{axis_name}.cells")
        else:
            axes.append(BreakdownAxisEvidence(axis_name=axis_name, cells=axis_cells))

    no_silent_exclusion = payload.get("no_silent_exclusion")
    if type(no_silent_exclusion) is not bool:
        missing.append(f"{context}.no_silent_exclusion")

    scalar_fields = (
        ("coverage_ratio", "coverage_ratio"),
        (
            "valid_included_canonical_group_coverage",
            "valid_included_canonical_group_coverage",
        ),
        ("missing_data_proportion", "missing_data_proportion"),
    )
    scalar_observations: list[MetricObservation] = []
    for field, metric_name in scalar_fields:
        value = payload.get(field)
        if not isinstance(value, str):
            missing.append(f"{context}.{field}")
            continue
        try:
            parsed_value = Decimal(value)
        except Exception as exc:  # pragma: no cover - Decimal's concrete errors vary
            raise R1EvidenceSchemaError(f"{context}.{field} is not a Decimal") from exc
        if not parsed_value.is_finite():
            raise R1EvidenceSchemaError(f"{context}.{field} must be finite")
        scalar_observations.append(MetricObservation.computed(metric_name, parsed_value))

    if missing:
        return None, tuple(missing)
    assert len(scalar_observations) == 3
    return (
        CoverageQualityEvidence(
            coverage_ratio=scalar_observations[0],
            valid_included_canonical_group_coverage=scalar_observations[1],
            missing_data_proportion=scalar_observations[2],
            breakdown_axes=tuple(axes),
            no_silent_exclusion=cast(bool, no_silent_exclusion),
        ),
        (),
    )


def load_c04_r1_evidence(path: Path | None = None) -> ParsedC04R1Evidence:
    """Load and parse the frozen R1 JSON without touching validation data."""

    evidence_path = _default_r1_evidence_path() if path is None else path
    raw_bytes = evidence_path.read_bytes()
    observed_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    if observed_sha256 != R1_EVIDENCE_SHA256:
        raise R1EvidenceHashMismatch(
            f"R1 evidence digest mismatch: expected {R1_EVIDENCE_SHA256}, "
            f"observed {observed_sha256}"
        )
    try:
        root = _mapping(json.loads(raw_bytes.decode("utf-8")), context="R1 evidence")
    except json.JSONDecodeError as exc:
        raise R1EvidenceSchemaError("R1 evidence is not valid JSON") from exc

    runs_payload = _sequence(root.get("RUNS"), context="R1 evidence.RUNS")
    candidates = tuple(
        _parse_run_metrics(
            _mapping(run, context=f"R1 evidence.RUNS[{index}]"),
            context=f"R1 evidence.RUNS[{index}]",
        )
        for index, run in enumerate(runs_payload)
    )
    if tuple(run.run_ordinal for run in candidates) != R1_EXPECTED_RUN_ORDINALS:
        raise R1EvidenceSchemaError("R1 evidence must contain run ordinals 1, 2, 3, 4")

    incumbent_payload = _mapping(
        root.get("INCUMBENT_METRICS"), context="R1 evidence.INCUMBENT_METRICS"
    )
    incumbent = FrozenC04RunMetrics(
        run_ordinal=0,
        multiplier=_decimal_field(
            root, "INCUMBENT_YIELD_AMPLITUDE_MULTIPLIER", context="R1 evidence"
        ),
        daily_wape=_decimal_field(
            incumbent_payload, "daily_wape", context="R1 evidence.INCUMBENT_METRICS"
        ),
        daily_mae=_decimal_field(
            incumbent_payload, "daily_mae", context="R1 evidence.INCUMBENT_METRICS"
        ),
        p80_coverage=_decimal_field(
            incumbent_payload, "P80_COVERAGE", context="R1 evidence.INCUMBENT_METRICS"
        ),
        p90_coverage=_decimal_field(
            incumbent_payload, "P90_COVERAGE", context="R1 evidence.INCUMBENT_METRICS"
        ),
    )

    coverage_values: list[CoverageQualityEvidence | None] = []
    missing_breakdown_evidence: list[str] = []
    for index, run in enumerate(runs_payload):
        metrics = _mapping(
            _mapping(run, context=f"R1 evidence.RUNS[{index}]").get("candidate_metrics"),
            context=f"R1 evidence.RUNS[{index}].candidate_metrics",
        )
        coverage, missing = _parse_coverage_quality(
            metrics, context=f"R1 evidence.RUNS[{index}].candidate_metrics"
        )
        coverage_values.append(coverage)
        missing_breakdown_evidence.extend(missing)

    incumbent_coverage, incumbent_missing = _parse_coverage_quality(
        incumbent_payload, context="R1 evidence.INCUMBENT_METRICS"
    )
    missing_breakdown_evidence.extend(incumbent_missing)

    return ParsedC04R1Evidence(
        source_path=str(evidence_path),
        sha256=observed_sha256,
        candidates=candidates,
        incumbent=incumbent,
        candidate_coverage_quality=tuple(coverage_values),
        incumbent_coverage_quality=incumbent_coverage,
        real_breakdown_cell_evidence_available=(
            not missing_breakdown_evidence
            and all(value is not None for value in coverage_values)
            and incumbent_coverage is not None
        ),
        missing_breakdown_evidence=tuple(dict.fromkeys(missing_breakdown_evidence)),
    )


def _evaluate_v4_frozen_run(
    candidate: FrozenC04RunMetrics,
    incumbent: FrozenC04RunMetrics,
    *,
    coverage_quality: CoverageQualityEvidence,
) -> CandidateEligibilityResult:
    """Apply only the V4 policy to parser-extracted frozen metrics."""

    complete_window_metrics = {
        metric_name: (
            MetricObservation.not_computable(metric_name),
            MetricObservation.not_computable(metric_name),
        )
        for metric_name in SPARSE_COMPLETE_WINDOW_METRICS
    }
    return evaluate_candidate_guardrails_v4_breakdown_reporting(
        candidate_primary_metric=MetricObservation.computed("daily_wape", candidate.daily_wape),
        incumbent_primary_metric=MetricObservation.computed("daily_wape", incumbent.daily_wape),
        candidate_daily_mae=MetricObservation.computed("daily_mae", candidate.daily_mae),
        incumbent_daily_mae=MetricObservation.computed("daily_mae", incumbent.daily_mae),
        candidate_p80_coverage=MetricObservation.computed("P80_COVERAGE", candidate.p80_coverage),
        incumbent_p80_coverage=MetricObservation.computed("P80_COVERAGE", incumbent.p80_coverage),
        candidate_p90_coverage=MetricObservation.computed("P90_COVERAGE", candidate.p90_coverage),
        incumbent_p90_coverage=MetricObservation.computed("P90_COVERAGE", incumbent.p90_coverage),
        coverage_quality=coverage_quality,
        complete_window_metrics=complete_window_metrics,
        evaluation_surface_identity=V3_EVALUATION_SURFACE_ID,
        forecast_horizons=V3_FORECAST_HORIZONS,
        complete_daily_rowset_authority=V3_COMPLETE_DAILY_ROWSET_AUTHORITY,
        missing_day_zero_fill=V3_MISSING_DAY_ZERO_FILL,
    )


def readjudicate_c04_r1_evidence(
    path: Path | None = None,
) -> EvidenceBoundC04Readjudication:
    """Readjudicate only what the immutable R1 evidence actually proves.

    Scalar run metrics are always extracted from the R1 JSON.  V4 is invoked
    only when every required axis has real cell identities, comparable-row
    counts, metric statuses, global coverage values, and explicit
    ``no_silent_exclusion`` evidence.  The compact R1 summary currently lacks
    those fields, so the current repository result is intentionally
    ``NOT_PROVEN``/``BLOCKED_EVIDENCE_INSUFFICIENT``.
    """

    parsed = load_c04_r1_evidence(path)
    if not parsed.real_breakdown_cell_evidence_available:
        return EvidenceBoundC04Readjudication(
            source_path=parsed.source_path,
            r1_evidence_sha256=parsed.sha256,
            real_breakdown_cell_evidence_available=False,
            run_eligibilities=("NOT_PROVEN",) * len(parsed.candidates),
            best_validation_run=None,
            best_multiplier=None,
            best_daily_wape=None,
            best_daily_mae=None,
            validation_outcome="BLOCKED_EVIDENCE_INSUFFICIENT",
            blocker=R1_BREAKDOWN_EVIDENCE_INSUFFICIENT_REASON,
        )

    if parsed.incumbent_coverage_quality is None or any(
        coverage is None for coverage in parsed.candidate_coverage_quality
    ):
        raise R1EvidenceSchemaError(
            "R1 evidence marked complete without complete coverage evidence"
        )

    results = tuple(
        _evaluate_v4_frozen_run(
            candidate,
            parsed.incumbent,
            coverage_quality=coverage,
        )
        for candidate, coverage in zip(
            parsed.candidates,
            parsed.candidate_coverage_quality,
            strict=True,
        )
        if coverage is not None
    )
    run_eligibilities = tuple(result.status for result in results)
    eligible_runs = tuple(
        (candidate, result)
        for candidate, result in zip(parsed.candidates, results, strict=True)
        if result.candidate_eligible
    )
    if any(result.status == "BLOCKED" for result in results):
        return EvidenceBoundC04Readjudication(
            source_path=parsed.source_path,
            r1_evidence_sha256=parsed.sha256,
            real_breakdown_cell_evidence_available=True,
            run_eligibilities=run_eligibilities,
            best_validation_run=None,
            best_multiplier=None,
            best_daily_wape=None,
            best_daily_mae=None,
            validation_outcome="BLOCKED",
            blocker="V4_EVALUATOR_BLOCKED",
            v4_results=results,
        )
    if not eligible_runs:
        return EvidenceBoundC04Readjudication(
            source_path=parsed.source_path,
            r1_evidence_sha256=parsed.sha256,
            real_breakdown_cell_evidence_available=True,
            run_eligibilities=run_eligibilities,
            best_validation_run=None,
            best_multiplier=None,
            best_daily_wape=None,
            best_daily_mae=None,
            validation_outcome="NO_ELIGIBLE_RUN",
            blocker=None,
            v4_results=results,
        )

    best_wape = min(candidate.daily_wape for candidate, _ in eligible_runs)
    best_runs = tuple(
        (candidate, result)
        for candidate, result in eligible_runs
        if candidate.daily_wape == best_wape
    )
    if len(best_runs) != 1:
        return EvidenceBoundC04Readjudication(
            source_path=parsed.source_path,
            r1_evidence_sha256=parsed.sha256,
            real_breakdown_cell_evidence_available=True,
            run_eligibilities=run_eligibilities,
            best_validation_run=None,
            best_multiplier=None,
            best_daily_wape=None,
            best_daily_mae=None,
            validation_outcome="BLOCKED",
            blocker="C04_TIEBREAK_AUTHORITY_UNAVAILABLE",
            v4_results=results,
        )
    best_candidate, _ = best_runs[0]
    return EvidenceBoundC04Readjudication(
        source_path=parsed.source_path,
        r1_evidence_sha256=parsed.sha256,
        real_breakdown_cell_evidence_available=True,
        run_eligibilities=run_eligibilities,
        best_validation_run=best_candidate.run_ordinal,
        best_multiplier=best_candidate.multiplier,
        best_daily_wape=best_candidate.daily_wape,
        best_daily_mae=best_candidate.daily_mae,
        validation_outcome="HAS_ELIGIBLE_WINNER",
        blocker=None,
        v4_results=results,
    )


__all__ = [
    "C04_REJUDICATION_POLICY",
    "EvidenceBoundC04Readjudication",
    "FrozenC04RunMetrics",
    "ParsedC04R1Evidence",
    "R1_BREAKDOWN_EVIDENCE_INSUFFICIENT_REASON",
    "R1_EVIDENCE_RELATIVE_PATH",
    "R1_EVIDENCE_SHA256",
    "R1EvidenceHashMismatch",
    "R1EvidenceSchemaError",
    "load_c04_r1_evidence",
    "readjudicate_c04_r1_evidence",
]
