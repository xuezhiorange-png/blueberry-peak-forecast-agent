"""Deterministic in-memory Farm-total baseline estimator (V0.3 S3)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from backend.app.forecast_quality.farm_total_dataset import (
    FarmTotalDatasetRow,
    FarmTotalTrainingDataset,
)

MIN_TRAIN_SUPPORT = 5
MIN_TRAIN_SUPPORT_UNIT = "DISTINCT_VALID_TRAIN_HARVEST_DAYS_PER_BASELINE_FARM_GROUP"


class FarmTotalBaselineDerivationBlocker(StrEnum):
    NON_TRAIN_PARTITION = "NON_TRAIN_PARTITION"


class FarmTotalBaselineGroupStatus(StrEnum):
    READY = "READY"
    INSUFFICIENT_TRAIN_SUPPORT = "INSUFFICIENT_TRAIN_SUPPORT"


class FarmTotalBaselineTargetStatus(StrEnum):
    READY = "READY"
    INSUFFICIENT_TRAIN_SUPPORT = "INSUFFICIENT_TRAIN_SUPPORT"
    UNSEEN_GROUP = "UNSEEN_GROUP"


class FarmTotalBaselineDerivationError(ValueError):
    """Raised when TRAIN-only derivation preconditions are violated."""

    def __init__(self, blocker: FarmTotalBaselineDerivationBlocker) -> None:
        super().__init__(blocker.value)
        self.blocker = blocker


@dataclass(frozen=True, slots=True)
class FarmTotalBaselineTargetKey:
    season_business_key: str
    baseline_farm_group_key: str
    harvest_business_date: date


@dataclass(frozen=True, slots=True)
class FarmTotalBaselineGroupEstimate:
    baseline_farm_group_key: str
    train_support_count: int
    baseline_harvest_quantity_kg: Decimal | None
    status: FarmTotalBaselineGroupStatus


@dataclass(frozen=True, slots=True)
class FarmTotalBaselineEstimatorState:
    group_estimates: tuple[FarmTotalBaselineGroupEstimate, ...]


@dataclass(frozen=True, slots=True)
class FarmTotalBaselinePoint:
    season_business_key: str
    baseline_farm_group_key: str
    harvest_business_date: date
    baseline_harvest_quantity_kg: Decimal


@dataclass(frozen=True, slots=True)
class FarmTotalBaselineTargetOutcome:
    target_key: FarmTotalBaselineTargetKey
    status: FarmTotalBaselineTargetStatus
    point: FarmTotalBaselinePoint | None


@dataclass(frozen=True, slots=True)
class FarmTotalBaselineProjectionResult:
    points: tuple[FarmTotalBaselinePoint, ...]
    target_outcomes: tuple[FarmTotalBaselineTargetOutcome, ...]


def _target_key_sort_key(key: FarmTotalBaselineTargetKey) -> tuple[str, str, date]:
    return (
        key.season_business_key,
        key.baseline_farm_group_key,
        key.harvest_business_date,
    )


def _decimal_median(values: tuple[Decimal, ...]) -> Decimal:
    if not values:
        raise ValueError("median requires at least one value")
    ordered = sorted(values)
    count = len(ordered)
    midpoint = count // 2
    if count % 2 == 1:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / Decimal("2")


def _distinct_train_support_count(rows: tuple[FarmTotalDatasetRow, ...]) -> int:
    return len({row.harvest_business_date for row in rows})


def derive_farm_total_baseline_estimator(
    train_dataset: FarmTotalTrainingDataset,
) -> FarmTotalBaselineEstimatorState:
    partition_dataset = train_dataset.partition_dataset
    if partition_dataset.partition != "TRAIN":
        raise FarmTotalBaselineDerivationError(
            FarmTotalBaselineDerivationBlocker.NON_TRAIN_PARTITION
        )

    rows_by_group: dict[str, list[FarmTotalDatasetRow]] = {}
    for row in partition_dataset.rows:
        rows_by_group.setdefault(row.baseline_farm_group_key, []).append(row)

    group_estimates: list[FarmTotalBaselineGroupEstimate] = []
    for group_key in sorted(rows_by_group):
        group_rows = tuple(rows_by_group[group_key])
        support_count = _distinct_train_support_count(group_rows)
        if support_count < MIN_TRAIN_SUPPORT:
            group_estimates.append(
                FarmTotalBaselineGroupEstimate(
                    baseline_farm_group_key=group_key,
                    train_support_count=support_count,
                    baseline_harvest_quantity_kg=None,
                    status=FarmTotalBaselineGroupStatus.INSUFFICIENT_TRAIN_SUPPORT,
                )
            )
            continue

        quantities = tuple(row.actual_harvest_quantity_kg for row in group_rows)
        group_estimates.append(
            FarmTotalBaselineGroupEstimate(
                baseline_farm_group_key=group_key,
                train_support_count=support_count,
                baseline_harvest_quantity_kg=_decimal_median(quantities),
                status=FarmTotalBaselineGroupStatus.READY,
            )
        )

    return FarmTotalBaselineEstimatorState(group_estimates=tuple(group_estimates))


def project_farm_total_baseline(
    estimator_state: FarmTotalBaselineEstimatorState,
    target_keys: tuple[FarmTotalBaselineTargetKey, ...],
) -> FarmTotalBaselineProjectionResult:
    estimates_by_group = {
        estimate.baseline_farm_group_key: estimate for estimate in estimator_state.group_estimates
    }

    outcomes: list[FarmTotalBaselineTargetOutcome] = []
    points: list[FarmTotalBaselinePoint] = []
    for target_key in sorted(target_keys, key=_target_key_sort_key):
        estimate = estimates_by_group.get(target_key.baseline_farm_group_key)
        if estimate is None:
            outcomes.append(
                FarmTotalBaselineTargetOutcome(
                    target_key=target_key,
                    status=FarmTotalBaselineTargetStatus.UNSEEN_GROUP,
                    point=None,
                )
            )
            continue

        if estimate.status is FarmTotalBaselineGroupStatus.INSUFFICIENT_TRAIN_SUPPORT:
            outcomes.append(
                FarmTotalBaselineTargetOutcome(
                    target_key=target_key,
                    status=FarmTotalBaselineTargetStatus.INSUFFICIENT_TRAIN_SUPPORT,
                    point=None,
                )
            )
            continue

        if estimate.baseline_harvest_quantity_kg is None:
            outcomes.append(
                FarmTotalBaselineTargetOutcome(
                    target_key=target_key,
                    status=FarmTotalBaselineTargetStatus.INSUFFICIENT_TRAIN_SUPPORT,
                    point=None,
                )
            )
            continue

        point = FarmTotalBaselinePoint(
            season_business_key=target_key.season_business_key,
            baseline_farm_group_key=target_key.baseline_farm_group_key,
            harvest_business_date=target_key.harvest_business_date,
            baseline_harvest_quantity_kg=estimate.baseline_harvest_quantity_kg,
        )
        points.append(point)
        outcomes.append(
            FarmTotalBaselineTargetOutcome(
                target_key=target_key,
                status=FarmTotalBaselineTargetStatus.READY,
                point=point,
            )
        )

    return FarmTotalBaselineProjectionResult(
        points=tuple(points),
        target_outcomes=tuple(outcomes),
    )
