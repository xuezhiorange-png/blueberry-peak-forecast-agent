"""Deterministic Farm-total baseline VALIDATION scoring (V0.3 S3)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any, NoReturn

from backend.app.forecast_quality.canonical import canonical_json_bytes, emit_s3_decimal
from backend.app.forecast_quality.farm_total_baseline_estimator import (
    FarmTotalBaselinePoint,
    FarmTotalBaselineTargetKey,
    FarmTotalBaselineTargetOutcome,
    FarmTotalBaselineTargetStatus,
)
from backend.app.forecast_quality.farm_total_baseline_evaluation_package import (
    FarmTotalBaselineEvaluationPackage,
    compute_farm_total_baseline_estimator_state_sha256,
    compute_farm_total_baseline_evaluation_package_sha256,
    compute_farm_total_baseline_point_set_sha256,
    compute_farm_total_baseline_prediction_identity_sha256,
    compute_farm_total_baseline_target_identity_set_sha256,
    compute_farm_total_baseline_target_outcome_set_sha256,
)
from backend.app.forecast_quality.farm_total_dataset import (
    FarmTotalDatasetRow,
    FarmTotalValidationDataset,
    compute_partition_dataset_sha256,
)

FARM_TOTAL_BASELINE_VALIDATION_SCORE_PACKAGE_SCHEMA_VERSION = (
    "v0-3-s3-farm-total-baseline-validation-score-package-v1"
)
FARM_TOTAL_BASELINE_VALIDATION_SCORING_POLICY_VERSION = (
    "v0-3-s3-farm-total-baseline-validation-scoring-v1"
)
SCORING_TARGET_GRAIN = "SEASON_X_BASELINE_FARM_GROUP_X_HARVEST_BUSINESS_DATE"

VALIDATION_ACTUAL_FINITE_DECIMAL_REQUIRED = True
VALIDATION_ACTUAL_NONNEGATIVE_PRECONDITION_REQUIRED = True
NEGATIVE_VALIDATION_ACTUAL_BLOCKER = "NEGATIVE_VALIDATION_ACTUAL"
NEGATIVE_VALIDATION_ACTUAL_ACTION = "STRUCTURAL_FAIL_CLOSED"
NEGATIVE_VALIDATION_ACTUAL_IS_NOT_ZERO = True
UPSTREAM_NONNEGATIVE_GUARANTEE_CLAIMED = False


class FarmTotalBaselineValidationScoringBlocker(StrEnum):
    """Stable fail-closed blockers for scorer inputs."""

    NON_VALIDATION_PARTITION = "NON_VALIDATION_PARTITION"
    NON_VALIDATION_ROW_PARTITION = "NON_VALIDATION_ROW_PARTITION"
    VALIDATION_DATASET_IDENTITY_MISMATCH = "VALIDATION_DATASET_IDENTITY_MISMATCH"
    VALIDATION_DATASET_CONTENT_HASH_MISMATCH = "VALIDATION_DATASET_CONTENT_HASH_MISMATCH"
    TARGET_IDENTITY_SET_MISMATCH = "TARGET_IDENTITY_SET_MISMATCH"
    DUPLICATE_VALIDATION_TARGET_KEY = "DUPLICATE_VALIDATION_TARGET_KEY"
    PACKAGE_IDENTITY_MISMATCH = "PACKAGE_IDENTITY_MISMATCH"
    PACKAGE_DIAGNOSTIC_MISMATCH = "PACKAGE_DIAGNOSTIC_MISMATCH"
    READY_BASELINE_POINT_MISSING = "READY_BASELINE_POINT_MISSING"
    READY_ACTUAL_MISSING = "READY_ACTUAL_MISSING"
    BLOCKED_TARGET_POINT_PRESENT = "BLOCKED_TARGET_POINT_PRESENT"
    INVALID_VALIDATION_ACTUAL_DECIMAL = "INVALID_VALIDATION_ACTUAL_DECIMAL"
    NEGATIVE_VALIDATION_ACTUAL = "NEGATIVE_VALIDATION_ACTUAL"
    TARGET_COUNT_CLOSURE_MISMATCH = "TARGET_COUNT_CLOSURE_MISMATCH"
    COMPARABLE_READY_COUNT_MISMATCH = "COMPARABLE_READY_COUNT_MISMATCH"


class FarmTotalBaselineValidationMetricStatus(StrEnum):
    COMPUTED = "COMPUTED"
    NOT_COMPUTABLE = "NOT_COMPUTABLE"


class FarmTotalBaselineValidationMetricReason(StrEnum):
    NONE = "NONE"
    NO_COMPARABLE_TARGETS = "NO_COMPARABLE_TARGETS"
    WAPE_DENOMINATOR_ZERO = "WAPE_DENOMINATOR_ZERO"


class FarmTotalBaselineValidationScoringError(ValueError):
    """Raised when validation scoring cannot satisfy its fail-closed contract."""

    def __init__(
        self,
        blocker: FarmTotalBaselineValidationScoringBlocker,
        *,
        reason_code: str | None = None,
        negative_validation_actual_count: int = 0,
    ) -> None:
        self.blocker = blocker
        self.reason_code = reason_code or blocker.value
        self.negative_validation_actual_count = negative_validation_actual_count
        super().__init__(self.reason_code)


@dataclass(frozen=True, slots=True)
class FarmTotalBaselineValidationMetricCell:
    metric_name: str
    metric_value: Decimal | None
    metric_status: FarmTotalBaselineValidationMetricStatus
    reason_code: FarmTotalBaselineValidationMetricReason
    numerator: Decimal | None
    denominator: Decimal | None


@dataclass(frozen=True, slots=True)
class FarmTotalBaselineValidationScoreDiagnostics:
    target_count: int
    comparable_target_count: int
    blocked_target_count: int
    ready_target_count: int
    insufficient_train_support_target_count: int
    unseen_group_target_count: int
    negative_validation_actual_count: int


@dataclass(frozen=True, slots=True)
class FarmTotalBaselineValidationScorePackage:
    schema_version: str
    scoring_policy_version: str
    evaluation_package_sha256: str
    validation_dataset_sha256: str
    target_identity_set_sha256: str
    baseline_point_set_sha256: str
    target_outcome_set_sha256: str
    scoring_target_actual_set_sha256: str
    scoring_input_sha256: str
    diagnostics: FarmTotalBaselineValidationScoreDiagnostics
    metric_cells: tuple[FarmTotalBaselineValidationMetricCell, ...]
    metric_result_set_sha256: str
    score_package_sha256: str

    @property
    def package_sha256(self) -> str:
        """Compatibility alias for callers that name the result hash package_sha256."""

        return self.score_package_sha256


TargetIdentity = tuple[str, str, date]


def _target_identity(key: FarmTotalBaselineTargetKey) -> TargetIdentity:
    return (
        key.season_business_key,
        key.baseline_farm_group_key,
        key.harvest_business_date,
    )


def _target_sort_key(key: FarmTotalBaselineTargetKey) -> TargetIdentity:
    return _target_identity(key)


def _point_identity(point: FarmTotalBaselinePoint) -> TargetIdentity:
    return (
        point.season_business_key,
        point.baseline_farm_group_key,
        point.harvest_business_date,
    )


def _row_identity(row: FarmTotalDatasetRow) -> TargetIdentity:
    return (
        row.season_business_key,
        row.baseline_farm_group_key,
        row.harvest_business_date,
    )


def _sha256_canonical(payload: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _raise(
    blocker: FarmTotalBaselineValidationScoringBlocker,
    *,
    reason_code: str | None = None,
    negative_validation_actual_count: int = 0,
) -> NoReturn:
    raise FarmTotalBaselineValidationScoringError(
        blocker,
        reason_code=reason_code,
        negative_validation_actual_count=negative_validation_actual_count,
    )


def _diagnostics_payload(
    diagnostics: FarmTotalBaselineValidationScoreDiagnostics,
) -> dict[str, int]:
    return {
        "target_count": diagnostics.target_count,
        "comparable_target_count": diagnostics.comparable_target_count,
        "blocked_target_count": diagnostics.blocked_target_count,
        "ready_target_count": diagnostics.ready_target_count,
        "insufficient_train_support_target_count": (
            diagnostics.insufficient_train_support_target_count
        ),
        "unseen_group_target_count": diagnostics.unseen_group_target_count,
        "negative_validation_actual_count": diagnostics.negative_validation_actual_count,
    }


def _metric_value_payload(value: Decimal | None) -> str | None:
    return emit_s3_decimal(value) if value is not None else None


def _metric_cell_payload(cell: FarmTotalBaselineValidationMetricCell) -> dict[str, Any]:
    return {
        "metric_name": cell.metric_name,
        "metric_value": _metric_value_payload(cell.metric_value),
        "metric_status": cell.metric_status.value,
        "reason_code": cell.reason_code.value,
        "numerator": _metric_value_payload(cell.numerator),
        "denominator": _metric_value_payload(cell.denominator),
    }


def _quantized_decimal(value: Decimal) -> Decimal:
    return Decimal(emit_s3_decimal(value))


def _validate_package_diagnostics(
    package: FarmTotalBaselineEvaluationPackage,
) -> tuple[
    dict[TargetIdentity, FarmTotalBaselineTargetOutcome],
    dict[TargetIdentity, FarmTotalBaselinePoint],
]:
    if package.schema_version != "v0-3-s3-farm-total-baseline-evaluation-package-v1":
        _raise(FarmTotalBaselineValidationScoringBlocker.PACKAGE_IDENTITY_MISMATCH)

    target_identities: list[TargetIdentity] = []
    for key in package.target_keys:
        if not isinstance(key, FarmTotalBaselineTargetKey):
            _raise(FarmTotalBaselineValidationScoringBlocker.PACKAGE_IDENTITY_MISMATCH)
        target_identities.append(_target_identity(key))
    if len(set(target_identities)) != len(target_identities):
        _raise(FarmTotalBaselineValidationScoringBlocker.PACKAGE_IDENTITY_MISMATCH)
    target_identity_set = set(target_identities)

    outcomes_by_identity: dict[TargetIdentity, FarmTotalBaselineTargetOutcome] = {}
    for outcome in package.projection_result.target_outcomes:
        if not isinstance(outcome, FarmTotalBaselineTargetOutcome):
            _raise(FarmTotalBaselineValidationScoringBlocker.PACKAGE_IDENTITY_MISMATCH)
        if not isinstance(outcome.target_key, FarmTotalBaselineTargetKey):
            _raise(FarmTotalBaselineValidationScoringBlocker.PACKAGE_IDENTITY_MISMATCH)
        identity = _target_identity(outcome.target_key)
        if identity not in target_identity_set or identity in outcomes_by_identity:
            _raise(FarmTotalBaselineValidationScoringBlocker.PACKAGE_DIAGNOSTIC_MISMATCH)
        if not isinstance(outcome.status, FarmTotalBaselineTargetStatus):
            _raise(FarmTotalBaselineValidationScoringBlocker.PACKAGE_DIAGNOSTIC_MISMATCH)
        outcomes_by_identity[identity] = outcome

    if set(outcomes_by_identity) != target_identity_set:
        _raise(FarmTotalBaselineValidationScoringBlocker.PACKAGE_DIAGNOSTIC_MISMATCH)

    points_by_identity: dict[TargetIdentity, FarmTotalBaselinePoint] = {}
    for point in package.projection_result.points:
        if not isinstance(point, FarmTotalBaselinePoint):
            _raise(FarmTotalBaselineValidationScoringBlocker.PACKAGE_IDENTITY_MISMATCH)
        identity = _point_identity(point)
        if identity in points_by_identity:
            _raise(FarmTotalBaselineValidationScoringBlocker.PACKAGE_IDENTITY_MISMATCH)
        points_by_identity[identity] = point

    ready_count = 0
    insufficient_count = 0
    unseen_count = 0
    for identity, outcome in outcomes_by_identity.items():
        if outcome.status is FarmTotalBaselineTargetStatus.READY:
            ready_count += 1
            if outcome.point is None or identity not in points_by_identity:
                _raise(FarmTotalBaselineValidationScoringBlocker.READY_BASELINE_POINT_MISSING)
            if _point_identity(outcome.point) != identity:
                _raise(FarmTotalBaselineValidationScoringBlocker.PACKAGE_DIAGNOSTIC_MISMATCH)
        elif outcome.status is FarmTotalBaselineTargetStatus.INSUFFICIENT_TRAIN_SUPPORT:
            insufficient_count += 1
            if outcome.point is not None or identity in points_by_identity:
                _raise(FarmTotalBaselineValidationScoringBlocker.BLOCKED_TARGET_POINT_PRESENT)
        elif outcome.status is FarmTotalBaselineTargetStatus.UNSEEN_GROUP:
            unseen_count += 1
            if outcome.point is not None or identity in points_by_identity:
                _raise(FarmTotalBaselineValidationScoringBlocker.BLOCKED_TARGET_POINT_PRESENT)
        else:
            _raise(FarmTotalBaselineValidationScoringBlocker.PACKAGE_DIAGNOSTIC_MISMATCH)

    if set(points_by_identity) != {
        identity
        for identity, outcome in outcomes_by_identity.items()
        if outcome.status is FarmTotalBaselineTargetStatus.READY
    }:
        _raise(FarmTotalBaselineValidationScoringBlocker.PACKAGE_DIAGNOSTIC_MISMATCH)

    diagnostics = package.diagnostics
    expected = (
        len(target_identities),
        len(points_by_identity),
        insufficient_count + unseen_count,
        ready_count,
        insufficient_count,
        unseen_count,
    )
    actual = (
        diagnostics.target_count,
        diagnostics.emitted_point_count,
        diagnostics.blocked_target_count,
        diagnostics.ready_target_count,
        diagnostics.insufficient_train_support_target_count,
        diagnostics.unseen_group_target_count,
    )
    if actual != expected or (
        package.target_count != diagnostics.target_count
        or package.emitted_point_count != diagnostics.emitted_point_count
        or package.blocked_target_count != diagnostics.blocked_target_count
    ):
        _raise(FarmTotalBaselineValidationScoringBlocker.PACKAGE_DIAGNOSTIC_MISMATCH)

    return outcomes_by_identity, points_by_identity


def _validate_package_identities(package: FarmTotalBaselineEvaluationPackage) -> None:
    try:
        expected_estimator_state_sha256 = compute_farm_total_baseline_estimator_state_sha256(
            package.estimator_state
        )
        expected_target_identity_set_sha256 = (
            compute_farm_total_baseline_target_identity_set_sha256(package.target_keys)
        )
        expected_baseline_point_set_sha256 = compute_farm_total_baseline_point_set_sha256(
            package.projection_result.points
        )
        expected_target_outcome_set_sha256 = compute_farm_total_baseline_target_outcome_set_sha256(
            package.projection_result.target_outcomes
        )
        expected_prediction_identity_sha256 = (
            compute_farm_total_baseline_prediction_identity_sha256(
                train_dataset_sha256=package.train_dataset_sha256,
                estimator_state_sha256=package.estimator_state_sha256,
                target_identity_set_sha256=package.target_identity_set_sha256,
                baseline_point_set_sha256=package.baseline_point_set_sha256,
                target_outcome_set_sha256=package.target_outcome_set_sha256,
            )
        )
        expected_package_sha256 = compute_farm_total_baseline_evaluation_package_sha256(
            train_dataset_sha256=package.train_dataset_sha256,
            validation_dataset_sha256=package.validation_dataset_sha256,
            estimator_state_sha256=package.estimator_state_sha256,
            target_identity_set_sha256=package.target_identity_set_sha256,
            baseline_point_set_sha256=package.baseline_point_set_sha256,
            target_outcome_set_sha256=package.target_outcome_set_sha256,
            prediction_identity_sha256=package.prediction_identity_sha256,
            target_count=package.target_count,
            emitted_point_count=package.emitted_point_count,
            blocked_target_count=package.blocked_target_count,
        )
    except Exception:
        _raise(FarmTotalBaselineValidationScoringBlocker.PACKAGE_IDENTITY_MISMATCH)

    expected_values = (
        (package.estimator_state_sha256, expected_estimator_state_sha256),
        (package.target_identity_set_sha256, expected_target_identity_set_sha256),
        (package.baseline_point_set_sha256, expected_baseline_point_set_sha256),
        (package.target_outcome_set_sha256, expected_target_outcome_set_sha256),
        (package.prediction_identity_sha256, expected_prediction_identity_sha256),
        (package.package_sha256, expected_package_sha256),
    )
    if any(actual != expected for actual, expected in expected_values):
        _raise(FarmTotalBaselineValidationScoringBlocker.PACKAGE_IDENTITY_MISMATCH)


def _invalid_actual_in_rows(rows: tuple[FarmTotalDatasetRow, ...]) -> bool:
    return any(
        not isinstance(row.actual_harvest_quantity_kg, Decimal)
        or not row.actual_harvest_quantity_kg.is_finite()
        for row in rows
    )


def _missing_actual_in_rows(rows: tuple[FarmTotalDatasetRow, ...]) -> bool:
    return any(row.actual_harvest_quantity_kg is None for row in rows)


def _validate_validation_dataset(
    *,
    evaluation_package: FarmTotalBaselineEvaluationPackage,
    validation_dataset: FarmTotalValidationDataset,
) -> tuple[
    dict[TargetIdentity, FarmTotalDatasetRow],
    tuple[FarmTotalBaselineTargetKey, ...],
]:
    partition_dataset = validation_dataset.partition_dataset
    if partition_dataset.partition != "VALIDATION":
        _raise(FarmTotalBaselineValidationScoringBlocker.NON_VALIDATION_PARTITION)

    rows = tuple(partition_dataset.rows)
    if any(row.partition != "VALIDATION" for row in rows):
        _raise(FarmTotalBaselineValidationScoringBlocker.NON_VALIDATION_ROW_PARTITION)

    if partition_dataset.dataset_sha256 != evaluation_package.validation_dataset_sha256:
        _raise(FarmTotalBaselineValidationScoringBlocker.VALIDATION_DATASET_IDENTITY_MISMATCH)

    ordered_rows = tuple(sorted(rows, key=_row_identity))
    try:
        recomputed_dataset_sha256 = compute_partition_dataset_sha256(ordered_rows)
    except Exception:
        if _missing_actual_in_rows(rows):
            _raise(FarmTotalBaselineValidationScoringBlocker.READY_ACTUAL_MISSING)
        if _invalid_actual_in_rows(rows):
            _raise(FarmTotalBaselineValidationScoringBlocker.INVALID_VALIDATION_ACTUAL_DECIMAL)
        _raise(FarmTotalBaselineValidationScoringBlocker.VALIDATION_DATASET_CONTENT_HASH_MISMATCH)
    if recomputed_dataset_sha256 != partition_dataset.dataset_sha256:
        _raise(FarmTotalBaselineValidationScoringBlocker.VALIDATION_DATASET_CONTENT_HASH_MISMATCH)

    rows_by_identity: dict[TargetIdentity, FarmTotalDatasetRow] = {}
    for row in ordered_rows:
        identity = _row_identity(row)
        if identity in rows_by_identity:
            _raise(FarmTotalBaselineValidationScoringBlocker.DUPLICATE_VALIDATION_TARGET_KEY)
        rows_by_identity[identity] = row

    validation_target_keys = tuple(
        FarmTotalBaselineTargetKey(
            season_business_key=row.season_business_key,
            baseline_farm_group_key=row.baseline_farm_group_key,
            harvest_business_date=row.harvest_business_date,
        )
        for row in ordered_rows
    )
    try:
        validation_target_identity_set_sha256 = (
            compute_farm_total_baseline_target_identity_set_sha256(validation_target_keys)
        )
    except Exception:
        _raise(FarmTotalBaselineValidationScoringBlocker.TARGET_IDENTITY_SET_MISMATCH)
    package_target_identities = {_target_identity(key) for key in evaluation_package.target_keys}
    if (
        set(rows_by_identity) != package_target_identities
        or validation_target_identity_set_sha256
        != evaluation_package.target_identity_set_sha256
    ):
        _raise(FarmTotalBaselineValidationScoringBlocker.TARGET_IDENTITY_SET_MISMATCH)

    return rows_by_identity, validation_target_keys


def _actual_set_sha256(
    rows_by_identity: dict[TargetIdentity, FarmTotalDatasetRow],
) -> str:
    payload = [
        {
            "season_business_key": row.season_business_key,
            "baseline_farm_group_key": row.baseline_farm_group_key,
            "harvest_business_date": row.harvest_business_date,
            "actual_harvest_quantity_kg": row.actual_harvest_quantity_kg,
        }
        for _, row in sorted(rows_by_identity.items(), key=lambda item: item[0])
    ]
    return _sha256_canonical(payload)


def _build_metric_cells(
    comparable: list[tuple[FarmTotalBaselineTargetKey, Decimal, Decimal]],
) -> tuple[FarmTotalBaselineValidationMetricCell, ...]:
    if not comparable:
        return (
            FarmTotalBaselineValidationMetricCell(
                metric_name="MAE",
                metric_value=None,
                metric_status=FarmTotalBaselineValidationMetricStatus.NOT_COMPUTABLE,
                reason_code=FarmTotalBaselineValidationMetricReason.NO_COMPARABLE_TARGETS,
                numerator=None,
                denominator=None,
            ),
            FarmTotalBaselineValidationMetricCell(
                metric_name="WAPE",
                metric_value=None,
                metric_status=FarmTotalBaselineValidationMetricStatus.NOT_COMPUTABLE,
                reason_code=FarmTotalBaselineValidationMetricReason.NO_COMPARABLE_TARGETS,
                numerator=None,
                denominator=None,
            ),
            FarmTotalBaselineValidationMetricCell(
                metric_name="SMAPE",
                metric_value=None,
                metric_status=FarmTotalBaselineValidationMetricStatus.NOT_COMPUTABLE,
                reason_code=FarmTotalBaselineValidationMetricReason.NO_COMPARABLE_TARGETS,
                numerator=None,
                denominator=None,
            ),
        )

    absolute_error_sum = sum(
        (abs(prediction - actual) for _, prediction, actual in comparable),
        Decimal("0"),
    )
    actual_sum = sum((actual for _, _, actual in comparable), Decimal("0"))
    target_count_decimal = Decimal(len(comparable))
    smape_terms = (
        (
            Decimal("0")
            if prediction == 0 and actual == 0
            else Decimal("2") * abs(prediction - actual) / (abs(prediction) + abs(actual))
        )
        for _, prediction, actual in comparable
    )
    smape_numerator = sum(smape_terms, Decimal("0"))


    mae_numerator = _quantized_decimal(absolute_error_sum)
    mae_denominator = _quantized_decimal(target_count_decimal)
    mae_value = _quantized_decimal(absolute_error_sum / target_count_decimal)
    mae = FarmTotalBaselineValidationMetricCell(
        metric_name="MAE",
        metric_value=mae_value,
        metric_status=FarmTotalBaselineValidationMetricStatus.COMPUTED,
        reason_code=FarmTotalBaselineValidationMetricReason.NONE,
        numerator=mae_numerator,
        denominator=mae_denominator,
    )

    wape_numerator = _quantized_decimal(absolute_error_sum)
    wape_denominator = _quantized_decimal(actual_sum)
    if actual_sum == 0:
        wape = FarmTotalBaselineValidationMetricCell(
            metric_name="WAPE",
            metric_value=None,
            metric_status=FarmTotalBaselineValidationMetricStatus.NOT_COMPUTABLE,
            reason_code=FarmTotalBaselineValidationMetricReason.WAPE_DENOMINATOR_ZERO,
            numerator=wape_numerator,
            denominator=wape_denominator,
        )
    else:
        wape = FarmTotalBaselineValidationMetricCell(
            metric_name="WAPE",
            metric_value=_quantized_decimal(absolute_error_sum / actual_sum),
            metric_status=FarmTotalBaselineValidationMetricStatus.COMPUTED,
            reason_code=FarmTotalBaselineValidationMetricReason.NONE,
            numerator=wape_numerator,
            denominator=wape_denominator,
        )

    smape = FarmTotalBaselineValidationMetricCell(
        metric_name="SMAPE",
        metric_value=_quantized_decimal(smape_numerator / target_count_decimal),
        metric_status=FarmTotalBaselineValidationMetricStatus.COMPUTED,
        reason_code=FarmTotalBaselineValidationMetricReason.NONE,
        numerator=_quantized_decimal(smape_numerator),
        denominator=_quantized_decimal(target_count_decimal),
    )
    return (mae, wape, smape)


def _score_package_sha256(
    *,
    evaluation_package_sha256: str,
    validation_dataset_sha256: str,
    target_identity_set_sha256: str,
    baseline_point_set_sha256: str,
    target_outcome_set_sha256: str,
    scoring_target_actual_set_sha256: str,
    scoring_input_sha256: str,
    diagnostics: FarmTotalBaselineValidationScoreDiagnostics,
    metric_result_set_sha256: str,
) -> str:
    return _sha256_canonical(
        {
            "schema_version": FARM_TOTAL_BASELINE_VALIDATION_SCORE_PACKAGE_SCHEMA_VERSION,
            "scoring_policy_version": FARM_TOTAL_BASELINE_VALIDATION_SCORING_POLICY_VERSION,
            "evaluation_package_sha256": evaluation_package_sha256,
            "validation_dataset_sha256": validation_dataset_sha256,
            "target_identity_set_sha256": target_identity_set_sha256,
            "baseline_point_set_sha256": baseline_point_set_sha256,
            "target_outcome_set_sha256": target_outcome_set_sha256,
            "scoring_target_actual_set_sha256": scoring_target_actual_set_sha256,
            "scoring_input_sha256": scoring_input_sha256,
            "diagnostics": _diagnostics_payload(diagnostics),
            "metric_result_set_sha256": metric_result_set_sha256,
        }
    )


def score_farm_total_baseline_validation(
    *,
    evaluation_package: FarmTotalBaselineEvaluationPackage,
    validation_dataset: FarmTotalValidationDataset,
) -> FarmTotalBaselineValidationScorePackage:
    """Score an already-built Farm-total baseline package against VALIDATION rows."""

    if not isinstance(evaluation_package, FarmTotalBaselineEvaluationPackage):
        _raise(FarmTotalBaselineValidationScoringBlocker.PACKAGE_IDENTITY_MISMATCH)

    outcomes_by_identity, points_by_identity = _validate_package_diagnostics(evaluation_package)
    _validate_package_identities(evaluation_package)
    rows_by_identity, _ = _validate_validation_dataset(
        evaluation_package=evaluation_package,
        validation_dataset=validation_dataset,
    )

    comparable: list[tuple[FarmTotalBaselineTargetKey, Decimal, Decimal]] = []
    negative_count = 0
    for target_key in sorted(evaluation_package.target_keys, key=_target_sort_key):
        identity = _target_identity(target_key)
        outcome = outcomes_by_identity[identity]
        if outcome.status is not FarmTotalBaselineTargetStatus.READY:
            continue
        row = rows_by_identity.get(identity)
        if row is None:
            _raise(FarmTotalBaselineValidationScoringBlocker.READY_ACTUAL_MISSING)
        actual = row.actual_harvest_quantity_kg
        if not isinstance(actual, Decimal) or not actual.is_finite():
            _raise(FarmTotalBaselineValidationScoringBlocker.INVALID_VALIDATION_ACTUAL_DECIMAL)
        if actual < 0:
            negative_count += 1
        point = points_by_identity.get(identity)
        if point is None:
            _raise(FarmTotalBaselineValidationScoringBlocker.READY_BASELINE_POINT_MISSING)
        prediction = point.baseline_harvest_quantity_kg
        comparable.append((target_key, prediction, actual))

    target_count = len(evaluation_package.target_keys)
    ready_count = sum(
        outcome.status is FarmTotalBaselineTargetStatus.READY
        for outcome in outcomes_by_identity.values()
    )
    insufficient_count = sum(
        outcome.status is FarmTotalBaselineTargetStatus.INSUFFICIENT_TRAIN_SUPPORT
        for outcome in outcomes_by_identity.values()
    )
    unseen_count = sum(
        outcome.status is FarmTotalBaselineTargetStatus.UNSEEN_GROUP
        for outcome in outcomes_by_identity.values()
    )
    blocked_count = insufficient_count + unseen_count
    comparable_count = len(comparable)

    if target_count != comparable_count + blocked_count:
        _raise(FarmTotalBaselineValidationScoringBlocker.TARGET_COUNT_CLOSURE_MISMATCH)
    if comparable_count != ready_count:
        _raise(FarmTotalBaselineValidationScoringBlocker.COMPARABLE_READY_COUNT_MISMATCH)
    if blocked_count != insufficient_count + unseen_count:
        _raise(FarmTotalBaselineValidationScoringBlocker.TARGET_COUNT_CLOSURE_MISMATCH)
    if negative_count != 0:
        _raise(
            FarmTotalBaselineValidationScoringBlocker.NEGATIVE_VALIDATION_ACTUAL,
            negative_validation_actual_count=negative_count,
        )

    diagnostics = FarmTotalBaselineValidationScoreDiagnostics(
        target_count=target_count,
        comparable_target_count=comparable_count,
        blocked_target_count=blocked_count,
        ready_target_count=ready_count,
        insufficient_train_support_target_count=insufficient_count,
        unseen_group_target_count=unseen_count,
        negative_validation_actual_count=negative_count,
    )
    scoring_target_actual_set_sha256 = _actual_set_sha256(rows_by_identity)
    scoring_input_sha256 = _sha256_canonical(
        {
            "schema_version": FARM_TOTAL_BASELINE_VALIDATION_SCORE_PACKAGE_SCHEMA_VERSION,
            "scoring_policy_version": FARM_TOTAL_BASELINE_VALIDATION_SCORING_POLICY_VERSION,
            "evaluation_package_sha256": evaluation_package.package_sha256,
            "validation_dataset_sha256": validation_dataset.partition_dataset.dataset_sha256,
            "target_identity_set_sha256": evaluation_package.target_identity_set_sha256,
            "baseline_point_set_sha256": evaluation_package.baseline_point_set_sha256,
            "target_outcome_set_sha256": evaluation_package.target_outcome_set_sha256,
            "scoring_target_actual_set_sha256": scoring_target_actual_set_sha256,
            **_diagnostics_payload(diagnostics),
        }
    )
    metric_cells = _build_metric_cells(comparable)
    metric_result_set_sha256 = _sha256_canonical(
        [_metric_cell_payload(cell) for cell in metric_cells]
    )
    score_package_sha256 = _score_package_sha256(
        evaluation_package_sha256=evaluation_package.package_sha256,
        validation_dataset_sha256=validation_dataset.partition_dataset.dataset_sha256,
        target_identity_set_sha256=evaluation_package.target_identity_set_sha256,
        baseline_point_set_sha256=evaluation_package.baseline_point_set_sha256,
        target_outcome_set_sha256=evaluation_package.target_outcome_set_sha256,
        scoring_target_actual_set_sha256=scoring_target_actual_set_sha256,
        scoring_input_sha256=scoring_input_sha256,
        diagnostics=diagnostics,
        metric_result_set_sha256=metric_result_set_sha256,
    )
    return FarmTotalBaselineValidationScorePackage(
        schema_version=FARM_TOTAL_BASELINE_VALIDATION_SCORE_PACKAGE_SCHEMA_VERSION,
        scoring_policy_version=FARM_TOTAL_BASELINE_VALIDATION_SCORING_POLICY_VERSION,
        evaluation_package_sha256=evaluation_package.package_sha256,
        validation_dataset_sha256=validation_dataset.partition_dataset.dataset_sha256,
        target_identity_set_sha256=evaluation_package.target_identity_set_sha256,
        baseline_point_set_sha256=evaluation_package.baseline_point_set_sha256,
        target_outcome_set_sha256=evaluation_package.target_outcome_set_sha256,
        scoring_target_actual_set_sha256=scoring_target_actual_set_sha256,
        scoring_input_sha256=scoring_input_sha256,
        diagnostics=diagnostics,
        metric_cells=metric_cells,
        metric_result_set_sha256=metric_result_set_sha256,
        score_package_sha256=score_package_sha256,
    )


__all__ = [
    "FARM_TOTAL_BASELINE_VALIDATION_SCORE_PACKAGE_SCHEMA_VERSION",
    "FARM_TOTAL_BASELINE_VALIDATION_SCORING_POLICY_VERSION",
    "NEGATIVE_VALIDATION_ACTUAL_ACTION",
    "NEGATIVE_VALIDATION_ACTUAL_BLOCKER",
    "NEGATIVE_VALIDATION_ACTUAL_IS_NOT_ZERO",
    "SCORING_TARGET_GRAIN",
    "UPSTREAM_NONNEGATIVE_GUARANTEE_CLAIMED",
    "VALIDATION_ACTUAL_FINITE_DECIMAL_REQUIRED",
    "VALIDATION_ACTUAL_NONNEGATIVE_PRECONDITION_REQUIRED",
    "FarmTotalBaselineValidationMetricCell",
    "FarmTotalBaselineValidationMetricReason",
    "FarmTotalBaselineValidationMetricStatus",
    "FarmTotalBaselineValidationScoreDiagnostics",
    "FarmTotalBaselineValidationScorePackage",
    "FarmTotalBaselineValidationScoringBlocker",
    "FarmTotalBaselineValidationScoringError",
    "score_farm_total_baseline_validation",
]
