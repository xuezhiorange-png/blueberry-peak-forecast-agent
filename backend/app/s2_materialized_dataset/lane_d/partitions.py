"""Frozen S1 TRAIN / VALIDATION / TEST partition boundaries for Lane D."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from backend.app.s2_materialized_dataset.shared.contracts import (
    PARTITION_DATE_FIELD,
    SPLIT_POLICY_VERSION,
    PartitionName,
)

TRAIN_START = date(2025, 8, 5)
TRAIN_END = date(2026, 1, 30)
VALIDATION_START = date(2026, 1, 31)
VALIDATION_END = date(2026, 3, 9)
TEST_START = date(2026, 3, 10)
TEST_END = date(2026, 4, 16)


@dataclass(frozen=True, slots=True)
class PartitionSpec:
    name: PartitionName
    start_date: date
    end_date: date
    date_field: str = PARTITION_DATE_FIELD
    split_policy_version: str = SPLIT_POLICY_VERSION


FROZEN_PARTITIONS: tuple[PartitionSpec, ...] = (
    PartitionSpec(PartitionName.TRAIN, TRAIN_START, TRAIN_END),
    PartitionSpec(PartitionName.VALIDATION, VALIDATION_START, VALIDATION_END),
    PartitionSpec(PartitionName.TEST, TEST_START, TEST_END),
)


def partition_for_name(name: PartitionName) -> PartitionSpec:
    for partition in FROZEN_PARTITIONS:
        if partition.name == name:
            return partition
    raise KeyError(f"unknown partition name: {name}")
