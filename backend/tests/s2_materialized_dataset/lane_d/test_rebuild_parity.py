"""Lane D rebuild parity tests."""

from __future__ import annotations

from datetime import date

from backend.app.s2_materialized_dataset.lane_d.builder import (
    materialize_partition_bytes,
    rebuild_partition_bytes,
)
from backend.app.s2_materialized_dataset.lane_d.partitions import partition_for_name
from backend.app.s2_materialized_dataset.shared.contracts import PartitionName
from backend.tests.s2_materialized_dataset.lane_d.conftest import make_row


def test_rebuild_produces_identical_content_hash() -> None:
    rows = (
        make_row(harvest_business_date=date(2025, 9, 1)),
        make_row(
            harvest_business_date=date(2026, 2, 1),
            source_row_identity="source-row-2",
            cleaned_row_identity="cleaned-row-2",
            pit_visibility_identity="pit-vis-2",
            revision_winner_identity="rev-win-2",
        ),
    )
    partition = partition_for_name(PartitionName.TRAIN)
    first = materialize_partition_bytes(partition=partition, upstream_rows=rows)
    second = rebuild_partition_bytes(partition=partition, upstream_rows=rows)
    assert first.content_sha256 == second.content_sha256
    assert first.byte_count == second.byte_count
    assert first.row_count == second.row_count


def test_test_rebuild_is_deterministic() -> None:
    partition = partition_for_name(PartitionName.TEST)
    first = rebuild_partition_bytes(partition=partition, upstream_rows=())
    second = rebuild_partition_bytes(partition=partition, upstream_rows=())
    assert first == second
