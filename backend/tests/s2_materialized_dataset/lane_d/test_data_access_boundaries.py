"""Lane D data-access boundary tests (contract §10)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from backend.app.s2_materialized_dataset.lane_d.builder import materialize_partition_bytes
from backend.app.s2_materialized_dataset.lane_d.partitions import partition_for_name
from backend.app.s2_materialized_dataset.shared.contracts import (
    SOURCE_002_CONTROLLED_SQL_MATERIALIZATION_ENABLED,
    SOURCE_002_ROW_LEVEL_READ,
    PartitionName,
)
from backend.tests.s2_materialized_dataset.lane_d.conftest import complete_upstream


def test_source_002_row_level_read_is_false() -> None:
    assert SOURCE_002_ROW_LEVEL_READ is False


def test_source_002_controlled_sql_materialization_enabled() -> None:
    assert SOURCE_002_CONTROLLED_SQL_MATERIALIZATION_ENABLED is True


def test_test_materialization_does_not_expose_real_test_rows() -> None:
    upstream = complete_upstream()
    test_partition = partition_for_name(PartitionName.TEST)
    result = materialize_partition_bytes(
        partition=test_partition,
        upstream_rows=upstream.lane_b.iter_materializable_rows(),
    )
    assert result.row_count == 0
    assert b"s2_test_partition_synthetic" in result.content_bytes


@pytest.mark.asyncio
async def test_api_response_excludes_partition_byte_payloads(
    lane_d_api_client: AsyncClient,
    persisted_dataset,
) -> None:
    response = await lane_d_api_client.get(
        f"/api/v1/materialized-datasets/{persisted_dataset.dataset_id}/versions/{persisted_dataset.dataset_version}"
    )
    assert response.status_code == 200
    payload = response.json()
    assert "content_bytes" not in payload
    for partition in payload["partitions"]:
        assert "content_bytes" not in partition
    test_partition = next(
        partition for partition in payload["partitions"] if partition["partition_name"] == "TEST"
    )
    assert test_partition["row_count"] == 0
    assert "s2_test_partition_synthetic" not in str(payload)
