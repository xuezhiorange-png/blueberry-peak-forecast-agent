"""Lane D partition boundary tests."""

from __future__ import annotations

from datetime import date

from backend.app.s2_materialized_dataset.lane_d.partitions import (
    FROZEN_PARTITIONS,
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    VALIDATION_END,
    VALIDATION_START,
    partition_for_name,
)
from backend.app.s2_materialized_dataset.shared.contracts import (
    PARTITION_DATE_FIELD,
    SPLIT_POLICY_VERSION,
    PartitionName,
)


def test_frozen_partitions_match_s1_authority() -> None:
    train, validation, test = FROZEN_PARTITIONS
    assert train.name is PartitionName.TRAIN
    assert train.start_date == TRAIN_START == date(2025, 8, 5)
    assert train.end_date == TRAIN_END == date(2026, 1, 30)
    assert validation.name is PartitionName.VALIDATION
    assert validation.start_date == VALIDATION_START == date(2026, 1, 31)
    assert validation.end_date == VALIDATION_END == date(2026, 3, 9)
    assert test.name is PartitionName.TEST
    assert test.start_date == TEST_START == date(2026, 3, 10)
    assert test.end_date == TEST_END == date(2026, 4, 16)


def test_partition_date_field_is_harvest_business_date_only() -> None:
    for partition in FROZEN_PARTITIONS:
        assert partition.date_field == PARTITION_DATE_FIELD == "HARVEST_BUSINESS_DATE"
        assert partition.split_policy_version == SPLIT_POLICY_VERSION


def test_partition_lookup_by_name() -> None:
    assert partition_for_name(PartitionName.VALIDATION).start_date == VALIDATION_START
