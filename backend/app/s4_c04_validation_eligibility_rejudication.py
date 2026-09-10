"""Pure re-adjudication of frozen C04 validation evidence.

This module intentionally accepts already-frozen metric observations.  It does
not load SOURCE-002, read VALIDATION rows, invoke a scorer, or touch the
durable validation-budget authority.  It exists so a policy correction can be
replayed against R1 evidence without creating a second evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from backend.app.s4_experiment import (
    SPARSE_COMPLETE_WINDOW_METRICS,
    V3_COMPLETE_DAILY_ROWSET_AUTHORITY,
    V3_EVALUATION_SURFACE_ID,
    V3_FORECAST_HORIZONS,
    V3_MISSING_DAY_ZERO_FILL,
    CandidateEligibilityResult,
    CoverageQualityEvidence,
    MetricObservation,
    evaluate_candidate_guardrails_v4_breakdown_reporting,
)

C04_REJUDICATION_POLICY: Final[str] = "v0.3-s4-guardrail-policy-v4-breakdown-reporting-floor"


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


def readjudicate_c04_run(
    candidate: FrozenC04RunMetrics,
    incumbent: FrozenC04RunMetrics,
    *,
    coverage_quality: CoverageQualityEvidence,
) -> CandidateEligibilityResult:
    """Apply only the V4 policy to frozen candidate/incumbent metrics."""

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


def readjudicate_c04_runs(
    candidates: tuple[FrozenC04RunMetrics, ...],
    incumbent: FrozenC04RunMetrics,
    *,
    coverage_quality: CoverageQualityEvidence,
) -> tuple[CandidateEligibilityResult, ...]:
    """Re-adjudicate the predeclared C04 run set without new execution."""

    if tuple(run.run_ordinal for run in candidates) != (1, 2, 3, 4):
        raise ValueError("C04 R1 evidence must contain run ordinals 1, 2, 3, 4")
    return tuple(
        readjudicate_c04_run(run, incumbent, coverage_quality=coverage_quality)
        for run in candidates
    )


__all__ = [
    "C04_REJUDICATION_POLICY",
    "FrozenC04RunMetrics",
    "readjudicate_c04_run",
    "readjudicate_c04_runs",
]
