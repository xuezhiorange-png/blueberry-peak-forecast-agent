"""Partition byte materialization for Lane D."""

from __future__ import annotations

from backend.app.s2_materialized_dataset.lane_d.canonical import (
    build_partition_bytes,
    build_test_synthetic_bytes,
)
from backend.app.s2_materialized_dataset.lane_d.hashing import content_sha256
from backend.app.s2_materialized_dataset.lane_d.partitions import PartitionSpec
from backend.app.s2_materialized_dataset.lane_d.schemas import MaterializedPartitionBytes
from backend.app.s2_materialized_dataset.shared.contracts import (
    SPLIT_POLICY_VERSION,
    MaterializableRow,
    PartitionName,
)


def _rows_for_partition(
    rows: tuple[MaterializableRow, ...],
    partition: PartitionSpec,
) -> tuple[MaterializableRow, ...]:
    return tuple(
        row
        for row in rows
        if partition.start_date <= row.harvest_business_date <= partition.end_date
    )


def materialize_partition_bytes(
    *,
    partition: PartitionSpec,
    upstream_rows: tuple[MaterializableRow, ...],
) -> MaterializedPartitionBytes:
    if partition.name is PartitionName.TEST:
        content_bytes = build_test_synthetic_bytes(
            partition_name=partition.name.value,
            partition_start_date=partition.start_date.isoformat(),
            partition_end_date=partition.end_date.isoformat(),
            split_policy_version=SPLIT_POLICY_VERSION,
        )
        row_count = 0
    else:
        selected = _rows_for_partition(upstream_rows, partition)
        content_bytes = build_partition_bytes(selected)
        row_count = len(selected)
    byte_count = len(content_bytes)
    return MaterializedPartitionBytes(
        partition_name=partition.name,
        content_bytes=content_bytes,
        row_count=row_count,
        byte_count=byte_count,
        content_sha256=content_sha256(content_bytes),
    )


def rebuild_partition_bytes(
    *,
    partition: PartitionSpec,
    upstream_rows: tuple[MaterializableRow, ...],
) -> MaterializedPartitionBytes:
    """Deterministic rebuild helper for hash replay verification."""
    return materialize_partition_bytes(partition=partition, upstream_rows=upstream_rows)


def rows_for_partition(
    rows: tuple[MaterializableRow, ...],
    partition: PartitionSpec,
) -> tuple[MaterializableRow, ...]:
    return _rows_for_partition(rows, partition)
