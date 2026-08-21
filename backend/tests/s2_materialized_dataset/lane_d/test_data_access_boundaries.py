"""Lane D data-access boundary tests (contract §10)."""

from __future__ import annotations

from backend.app.s2_materialized_dataset.lane_d.builder import materialize_partition_bytes
from backend.app.s2_materialized_dataset.lane_d.partitions import partition_for_name
from backend.app.s2_materialized_dataset.shared.contracts import (
    SOURCE_002_ROW_LEVEL_READ,
    PartitionName,
)
from backend.tests.s2_materialized_dataset.lane_d.conftest import complete_upstream


def test_source_002_row_level_read_is_false() -> None:
    assert SOURCE_002_ROW_LEVEL_READ is False


def test_test_materialization_does_not_expose_real_test_rows() -> None:
    upstream = complete_upstream()
    test_partition = partition_for_name(PartitionName.TEST)
    result = materialize_partition_bytes(
        partition=test_partition,
        upstream_rows=upstream.lane_b.iter_materializable_rows(),
    )
    assert result.row_count == 0
    assert b"s2_test_partition_synthetic" in result.content_bytes
