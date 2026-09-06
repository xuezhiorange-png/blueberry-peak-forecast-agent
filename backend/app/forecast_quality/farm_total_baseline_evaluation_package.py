"""Deterministic in-memory Farm-total baseline evaluation package (V0.3 S3)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any

from backend.app.forecast_quality.canonical import canonical_json_bytes, emit_s3_decimal
from backend.app.forecast_quality.farm_total_baseline_estimator import (
    FarmTotalBaselineEstimatorState,
    FarmTotalBaselinePoint,
    FarmTotalBaselineProjectionResult,
    FarmTotalBaselineTargetKey,
    FarmTotalBaselineTargetOutcome,
    FarmTotalBaselineTargetStatus,
    derive_farm_total_baseline_estimator,
    project_farm_total_baseline,
)
from backend.app.forecast_quality.farm_total_dataset import (
    FarmTotalDatasetRow,
    FarmTotalTrainingDataset,
    FarmTotalValidationDataset,
)

FARM_TOTAL_BASELINE_EVALUATION_PACKAGE_SCHEMA_VERSION = (
    "v0-3-s3-farm-total-baseline-evaluation-package-v1"
)
FARM_TOTAL_BASELINE_ESTIMATOR_SEMANTIC_IDENTITY_SHA256 = (
    "39722ff8e8a520813975cd7270b6453db388633bffee9c90fb12140440431463"
)


class FarmTotalBaselineEvaluationPackageBlocker(StrEnum):
    NON_VALIDATION_PARTITION = "NON_VALIDATION_PARTITION"
    NON_VALIDATION_ROW_PARTITION = "NON_VALIDATION_ROW_PARTITION"
    DUPLICATE_VALIDATION_TARGET_KEY = "DUPLICATE_VALIDATION_TARGET_KEY"


class FarmTotalBaselineEvaluationPackageError(ValueError):
    """Raised when evaluation-package preconditions are violated."""

    def __init__(self, blocker: FarmTotalBaselineEvaluationPackageBlocker) -> None:
        super().__init__(blocker.value)
        self.blocker = blocker


@dataclass(frozen=True, slots=True)
class FarmTotalBaselineTargetKeySet:
    target_keys: tuple[FarmTotalBaselineTargetKey, ...]
    target_identity_set_sha256: str


@dataclass(frozen=True, slots=True)
class FarmTotalBaselineEvaluationPackageDiagnostics:
    target_count: int
    emitted_point_count: int
    blocked_target_count: int
    ready_target_count: int
    insufficient_train_support_target_count: int
    unseen_group_target_count: int


@dataclass(frozen=True, slots=True)
class FarmTotalBaselineEvaluationPackage:
    schema_version: str
    train_dataset_sha256: str
    validation_dataset_sha256: str
    target_keys: tuple[FarmTotalBaselineTargetKey, ...]
    estimator_state: FarmTotalBaselineEstimatorState
    projection_result: FarmTotalBaselineProjectionResult
    diagnostics: FarmTotalBaselineEvaluationPackageDiagnostics
    target_count: int
    emitted_point_count: int
    blocked_target_count: int
    estimator_state_sha256: str
    target_identity_set_sha256: str
    baseline_point_set_sha256: str
    target_outcome_set_sha256: str
    prediction_identity_sha256: str
    package_sha256: str


def _target_key_sort_key(key: FarmTotalBaselineTargetKey) -> tuple[str, str, date]:
    return (
        key.season_business_key,
        key.baseline_farm_group_key,
        key.harvest_business_date,
    )


def _point_sort_key(point: FarmTotalBaselinePoint) -> tuple[str, str, date]:
    return (
        point.season_business_key,
        point.baseline_farm_group_key,
        point.harvest_business_date,
    )


def _sha256_canonical(payload: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _target_identity_preimage(key: FarmTotalBaselineTargetKey) -> dict[str, Any]:
    return {
        "season_business_key": key.season_business_key,
        "baseline_farm_group_key": key.baseline_farm_group_key,
        "harvest_business_date": key.harvest_business_date,
    }


def compute_farm_total_baseline_target_identity_set_sha256(
    target_keys: tuple[FarmTotalBaselineTargetKey, ...],
) -> str:
    ordered = sorted(target_keys, key=_target_key_sort_key)
    preimage = [_target_identity_preimage(key) for key in ordered]
    return _sha256_canonical(preimage)


def compute_farm_total_baseline_estimator_state_sha256(
    estimator_state: FarmTotalBaselineEstimatorState,
) -> str:
    preimage = [
        {
            "baseline_farm_group_key": estimate.baseline_farm_group_key,
            "train_support_count": estimate.train_support_count,
            "status": estimate.status,
            "baseline_harvest_quantity_kg": (
                emit_s3_decimal(estimate.baseline_harvest_quantity_kg)
                if estimate.baseline_harvest_quantity_kg is not None
                else None
            ),
        }
        for estimate in sorted(
            estimator_state.group_estimates,
            key=lambda estimate: estimate.baseline_farm_group_key,
        )
    ]
    return _sha256_canonical(preimage)


def compute_farm_total_baseline_point_set_sha256(
    points: tuple[FarmTotalBaselinePoint, ...],
) -> str:
    ordered = sorted(points, key=_point_sort_key)
    preimage = [
        {
            "season_business_key": point.season_business_key,
            "baseline_farm_group_key": point.baseline_farm_group_key,
            "harvest_business_date": point.harvest_business_date,
            "baseline_harvest_quantity_kg": emit_s3_decimal(point.baseline_harvest_quantity_kg),
        }
        for point in ordered
    ]
    return _sha256_canonical(preimage)


def compute_farm_total_baseline_target_outcome_set_sha256(
    target_outcomes: tuple[FarmTotalBaselineTargetOutcome, ...],
) -> str:
    ordered = sorted(
        target_outcomes,
        key=lambda outcome: _target_key_sort_key(outcome.target_key),
    )
    preimage = [
        {
            "season_business_key": outcome.target_key.season_business_key,
            "baseline_farm_group_key": outcome.target_key.baseline_farm_group_key,
            "harvest_business_date": outcome.target_key.harvest_business_date,
            "status": outcome.status,
            "point_present": outcome.point is not None,
            "baseline_harvest_quantity_kg": (
                emit_s3_decimal(outcome.point.baseline_harvest_quantity_kg)
                if outcome.point is not None
                else None
            ),
        }
        for outcome in ordered
    ]
    return _sha256_canonical(preimage)


def compute_farm_total_baseline_prediction_identity_sha256(
    *,
    train_dataset_sha256: str,
    estimator_state_sha256: str,
    target_identity_set_sha256: str,
    baseline_point_set_sha256: str,
    target_outcome_set_sha256: str,
) -> str:
    preimage = {
        "schema_version": FARM_TOTAL_BASELINE_EVALUATION_PACKAGE_SCHEMA_VERSION,
        "train_dataset_sha256": train_dataset_sha256,
        "frozen_estimator_semantic_identity": (
            FARM_TOTAL_BASELINE_ESTIMATOR_SEMANTIC_IDENTITY_SHA256
        ),
        "estimator_state_sha256": estimator_state_sha256,
        "target_identity_set_sha256": target_identity_set_sha256,
        "baseline_point_set_sha256": baseline_point_set_sha256,
        "target_outcome_set_sha256": target_outcome_set_sha256,
    }
    return _sha256_canonical(preimage)


def compute_farm_total_baseline_evaluation_package_sha256(
    *,
    train_dataset_sha256: str,
    validation_dataset_sha256: str,
    estimator_state_sha256: str,
    target_identity_set_sha256: str,
    baseline_point_set_sha256: str,
    target_outcome_set_sha256: str,
    prediction_identity_sha256: str,
    target_count: int,
    emitted_point_count: int,
    blocked_target_count: int,
) -> str:
    preimage = {
        "schema_version": FARM_TOTAL_BASELINE_EVALUATION_PACKAGE_SCHEMA_VERSION,
        "train_dataset_sha256": train_dataset_sha256,
        "validation_dataset_sha256": validation_dataset_sha256,
        "estimator_state_sha256": estimator_state_sha256,
        "target_identity_set_sha256": target_identity_set_sha256,
        "baseline_point_set_sha256": baseline_point_set_sha256,
        "target_outcome_set_sha256": target_outcome_set_sha256,
        "prediction_identity_sha256": prediction_identity_sha256,
        "target_count": target_count,
        "emitted_point_count": emitted_point_count,
        "blocked_target_count": blocked_target_count,
    }
    return _sha256_canonical(preimage)


def _extract_validation_target_identity(row: FarmTotalDatasetRow) -> FarmTotalBaselineTargetKey:
    return FarmTotalBaselineTargetKey(
        season_business_key=row.season_business_key,
        baseline_farm_group_key=row.baseline_farm_group_key,
        harvest_business_date=row.harvest_business_date,
    )


def build_farm_total_validation_target_keys(
    validation_dataset: FarmTotalValidationDataset,
) -> FarmTotalBaselineTargetKeySet:
    partition_dataset = validation_dataset.partition_dataset
    if partition_dataset.partition != "VALIDATION":
        raise FarmTotalBaselineEvaluationPackageError(
            FarmTotalBaselineEvaluationPackageBlocker.NON_VALIDATION_PARTITION
        )

    for row in partition_dataset.rows:
        if row.partition != "VALIDATION":
            raise FarmTotalBaselineEvaluationPackageError(
                FarmTotalBaselineEvaluationPackageBlocker.NON_VALIDATION_ROW_PARTITION
            )

    seen: set[tuple[str, str, date]] = set()
    target_keys: list[FarmTotalBaselineTargetKey] = []
    for row in partition_dataset.rows:
        identity = (
            row.season_business_key,
            row.baseline_farm_group_key,
            row.harvest_business_date,
        )
        if identity in seen:
            raise FarmTotalBaselineEvaluationPackageError(
                FarmTotalBaselineEvaluationPackageBlocker.DUPLICATE_VALIDATION_TARGET_KEY
            )
        seen.add(identity)
        target_keys.append(_extract_validation_target_identity(row))

    ordered = tuple(sorted(target_keys, key=_target_key_sort_key))
    identity_sha256 = compute_farm_total_baseline_target_identity_set_sha256(ordered)
    return FarmTotalBaselineTargetKeySet(
        target_keys=ordered,
        target_identity_set_sha256=identity_sha256,
    )


def _build_package_diagnostics(
    target_keys: tuple[FarmTotalBaselineTargetKey, ...],
    projection_result: FarmTotalBaselineProjectionResult,
) -> FarmTotalBaselineEvaluationPackageDiagnostics:
    ready_target_count = 0
    insufficient_train_support_target_count = 0
    unseen_group_target_count = 0
    for outcome in projection_result.target_outcomes:
        if outcome.status is FarmTotalBaselineTargetStatus.READY:
            ready_target_count += 1
        elif outcome.status is FarmTotalBaselineTargetStatus.INSUFFICIENT_TRAIN_SUPPORT:
            insufficient_train_support_target_count += 1
        elif outcome.status is FarmTotalBaselineTargetStatus.UNSEEN_GROUP:
            unseen_group_target_count += 1

    target_count = len(target_keys)
    emitted_point_count = len(projection_result.points)
    blocked_target_count = insufficient_train_support_target_count + unseen_group_target_count
    return FarmTotalBaselineEvaluationPackageDiagnostics(
        target_count=target_count,
        emitted_point_count=emitted_point_count,
        blocked_target_count=blocked_target_count,
        ready_target_count=ready_target_count,
        insufficient_train_support_target_count=insufficient_train_support_target_count,
        unseen_group_target_count=unseen_group_target_count,
    )


def build_farm_total_baseline_evaluation_package(
    *,
    train_dataset: FarmTotalTrainingDataset,
    validation_dataset: FarmTotalValidationDataset,
) -> FarmTotalBaselineEvaluationPackage:
    target_key_set = build_farm_total_validation_target_keys(validation_dataset)
    estimator_state = derive_farm_total_baseline_estimator(train_dataset)
    projection_result = project_farm_total_baseline(
        estimator_state,
        target_key_set.target_keys,
    )
    diagnostics = _build_package_diagnostics(target_key_set.target_keys, projection_result)

    train_dataset_sha256 = train_dataset.partition_dataset.dataset_sha256
    validation_dataset_sha256 = validation_dataset.partition_dataset.dataset_sha256

    estimator_state_sha256 = compute_farm_total_baseline_estimator_state_sha256(estimator_state)
    baseline_point_set_sha256 = compute_farm_total_baseline_point_set_sha256(
        projection_result.points
    )
    target_outcome_set_sha256 = compute_farm_total_baseline_target_outcome_set_sha256(
        projection_result.target_outcomes
    )
    prediction_identity_sha256 = compute_farm_total_baseline_prediction_identity_sha256(
        train_dataset_sha256=train_dataset_sha256,
        estimator_state_sha256=estimator_state_sha256,
        target_identity_set_sha256=target_key_set.target_identity_set_sha256,
        baseline_point_set_sha256=baseline_point_set_sha256,
        target_outcome_set_sha256=target_outcome_set_sha256,
    )
    package_sha256 = compute_farm_total_baseline_evaluation_package_sha256(
        train_dataset_sha256=train_dataset_sha256,
        validation_dataset_sha256=validation_dataset_sha256,
        estimator_state_sha256=estimator_state_sha256,
        target_identity_set_sha256=target_key_set.target_identity_set_sha256,
        baseline_point_set_sha256=baseline_point_set_sha256,
        target_outcome_set_sha256=target_outcome_set_sha256,
        prediction_identity_sha256=prediction_identity_sha256,
        target_count=diagnostics.target_count,
        emitted_point_count=diagnostics.emitted_point_count,
        blocked_target_count=diagnostics.blocked_target_count,
    )

    return FarmTotalBaselineEvaluationPackage(
        schema_version=FARM_TOTAL_BASELINE_EVALUATION_PACKAGE_SCHEMA_VERSION,
        train_dataset_sha256=train_dataset_sha256,
        validation_dataset_sha256=validation_dataset_sha256,
        target_keys=target_key_set.target_keys,
        estimator_state=estimator_state,
        projection_result=projection_result,
        diagnostics=diagnostics,
        target_count=diagnostics.target_count,
        emitted_point_count=diagnostics.emitted_point_count,
        blocked_target_count=diagnostics.blocked_target_count,
        estimator_state_sha256=estimator_state_sha256,
        target_identity_set_sha256=target_key_set.target_identity_set_sha256,
        baseline_point_set_sha256=baseline_point_set_sha256,
        target_outcome_set_sha256=target_outcome_set_sha256,
        prediction_identity_sha256=prediction_identity_sha256,
        package_sha256=package_sha256,
    )
