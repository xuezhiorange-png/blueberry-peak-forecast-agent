"""S3-A amendment §8.1 completeness predicate verification."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from backend.app.s3_daily_rowset.schemas import (
    CompletenessPredicateId,
    CompletenessPredicateResult,
    DailyRowsetResult,
    DailyRowStatus,
    MaterializationOutcome,
    PredicateStatus,
    WindowCompletenessVerificationResult,
)

COMPLETENESS_PREDICATE_IDS: tuple[CompletenessPredicateId, ...] = (
    CompletenessPredicateId.FULL_CALENDAR_DAY_COVERAGE_IN_WINDOW,
    CompletenessPredicateId.NO_SILENT_MISSING_DAYS,
    CompletenessPredicateId.NO_ZERO_FILL_FOR_UNKNOWN,
    CompletenessPredicateId.OBSERVED_KG_TRACEABLE_TO_SOURCE_002_GRAIN,
    CompletenessPredicateId.FORECAST_DAILY_CURVE_VISIBLE_AT_CUTOFF,
)


def _calendar_dates_inclusive(start: date, end: date) -> tuple[date, ...]:
    dates: list[date] = []
    current = start
    while current <= end:
        dates.append(current)
        current += timedelta(days=1)
    return tuple(dates)


def _predicate_full_calendar_day_coverage(rowset: DailyRowsetResult) -> PredicateStatus:
    if (
        rowset.window_start_date is None
        or rowset.window_end_date is None
        or rowset.outcome != MaterializationOutcome.SUCCESS
    ):
        return PredicateStatus.FAIL
    expected_dates = _calendar_dates_inclusive(
        rowset.window_start_date,
        rowset.window_end_date,
    )
    if len(rowset.daily_rows) != len(expected_dates):
        return PredicateStatus.FAIL
    actual_dates = tuple(row.business_date for row in rowset.daily_rows)
    return PredicateStatus.PASS if actual_dates == expected_dates else PredicateStatus.FAIL


def _predicate_no_silent_missing_days(rowset: DailyRowsetResult) -> PredicateStatus:
    if rowset.outcome != MaterializationOutcome.SUCCESS:
        return PredicateStatus.FAIL
    if not rowset.daily_rows:
        return PredicateStatus.FAIL
    dates = [row.business_date for row in rowset.daily_rows]
    if len(dates) != len(set(dates)):
        return PredicateStatus.FAIL
    return _predicate_full_calendar_day_coverage(rowset)


def _predicate_no_zero_fill_for_unknown(rowset: DailyRowsetResult) -> PredicateStatus:
    if rowset.outcome != MaterializationOutcome.SUCCESS:
        return PredicateStatus.FAIL
    for row in rowset.daily_rows:
        if row.daily_row_status in {DailyRowStatus.UNKNOWN, DailyRowStatus.EXCLUDED}:
            if row.actual_harvest_quantity_kg is not None:
                return PredicateStatus.FAIL
        if row.daily_row_status == DailyRowStatus.OBSERVED:
            if row.actual_harvest_quantity_kg is None:
                return PredicateStatus.FAIL
    return PredicateStatus.PASS


def _predicate_observed_kg_traceable(rowset: DailyRowsetResult) -> PredicateStatus:
    if rowset.outcome != MaterializationOutcome.SUCCESS:
        return PredicateStatus.FAIL
    if not rowset.rowset_identity_sha256:
        return PredicateStatus.FAIL
    for row in rowset.daily_rows:
        if row.daily_row_status == DailyRowStatus.OBSERVED:
            if row.actual_harvest_quantity_kg is None:
                return PredicateStatus.FAIL
    return PredicateStatus.PASS


def _predicate_forecast_visible_at_cutoff(rowset: DailyRowsetResult) -> PredicateStatus:
    if rowset.outcome != MaterializationOutcome.SUCCESS:
        return PredicateStatus.FAIL
    for row in rowset.daily_rows:
        if row.forecast_harvest_quantity_kg is None:
            return PredicateStatus.FAIL
    return PredicateStatus.PASS


_PREDICATE_EVALUATORS = {
    CompletenessPredicateId.FULL_CALENDAR_DAY_COVERAGE_IN_WINDOW: (
        _predicate_full_calendar_day_coverage
    ),
    CompletenessPredicateId.NO_SILENT_MISSING_DAYS: _predicate_no_silent_missing_days,
    CompletenessPredicateId.NO_ZERO_FILL_FOR_UNKNOWN: _predicate_no_zero_fill_for_unknown,
    CompletenessPredicateId.OBSERVED_KG_TRACEABLE_TO_SOURCE_002_GRAIN: (
        _predicate_observed_kg_traceable
    ),
    CompletenessPredicateId.FORECAST_DAILY_CURVE_VISIBLE_AT_CUTOFF: (
        _predicate_forecast_visible_at_cutoff
    ),
}


@dataclass(frozen=True, slots=True)
class CompletenessVerifier:
    """Evaluate amendment §8.1 predicates on a single materialized window."""

    def verify_window(self, rowset: DailyRowsetResult) -> WindowCompletenessVerificationResult:
        predicates = tuple(
            CompletenessPredicateResult(
                predicate_id=predicate_id,
                status=_PREDICATE_EVALUATORS[predicate_id](rowset),
            )
            for predicate_id in COMPLETENESS_PREDICATE_IDS
        )
        window_predicates_all_pass = all(
            predicate.status == PredicateStatus.PASS for predicate in predicates
        )
        return WindowCompletenessVerificationResult(
            window_predicates_all_pass=window_predicates_all_pass,
            predicates=predicates,
            dataset_completeness_verified=False,
            current_s3_daily_rowset_completeness_verified=False,
            evaluation_instance_registry_available=False,
            materialization_outcome=rowset.outcome,
            rowset_identity_sha256=rowset.rowset_identity_sha256,
        )
