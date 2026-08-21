"""Lane D manifest field tests."""

from __future__ import annotations

from datetime import UTC, datetime

from backend.app.s2_materialized_dataset.lane_d.manifest import build_partition_manifest
from backend.app.s2_materialized_dataset.lane_d.partitions import partition_for_name
from backend.app.s2_materialized_dataset.shared.contracts import (
    PARTITION_DATE_FIELD,
    PartitionName,
    QualityGateStatus,
    RebuildHashReplayStatus,
)
from backend.tests.s2_materialized_dataset.lane_d.conftest import complete_upstream


def test_manifest_contains_required_metrics() -> None:
    upstream = complete_upstream()
    partition = partition_for_name(PartitionName.TRAIN)
    started = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
    completed = datetime(2026, 4, 1, 12, 1, tzinfo=UTC)
    manifest = build_partition_manifest(
        dataset_id="materialized-ds-1",
        dataset_version="v1",
        partition=partition,
        upstream=upstream,
        row_count=2,
        byte_count=128,
        content_hash="abc123",
        lineage_complete=True,
        build_started_at=started,
        build_completed_at=completed,
        quality_gate_status=QualityGateStatus.ACCEPTED,
        rebuild_hash_replay_status=RebuildHashReplayStatus.PASS,
    )
    assert manifest.row_count == 2
    assert manifest.byte_count == 128
    assert manifest.content_sha256 == "abc123"
    assert len(manifest.manifest_sha256) == 64
    assert manifest.partition_date_field == PARTITION_DATE_FIELD
    assert manifest.lineage_complete is True
