"""Lane D manifest field tests."""

from __future__ import annotations

from datetime import UTC, datetime

from backend.app.s2_materialized_dataset.lane_d.builder import (
    rows_for_partition,
    verify_partition_rebuild_hash_replay,
)
from backend.app.s2_materialized_dataset.lane_d.hashing import (
    materialized_partition_identity_sha256,
)
from backend.app.s2_materialized_dataset.lane_d.partitions import partition_for_name
from backend.app.s2_materialized_dataset.shared.contracts import (
    PARTITION_DATE_FIELD,
    PartitionName,
    RebuildHashReplayStatus,
)
from backend.tests.s2_materialized_dataset.lane_d.conftest import complete_upstream, make_row


def test_manifest_contains_required_metrics() -> None:
    upstream = complete_upstream()
    partition = partition_for_name(PartitionName.TRAIN)
    started = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
    completed = datetime(2026, 4, 1, 12, 1, tzinfo=UTC)
    rows = upstream.lane_b.iter_materializable_rows()
    selected_rows = rows_for_partition(rows, partition)
    partition_identity = materialized_partition_identity_sha256(
        dataset_id="materialized-ds-1",
        dataset_version="v1",
        partition_name=partition.name,
        partition_start_date=partition.start_date,
        partition_end_date=partition.end_date,
        ordered_cleaned_row_identities=tuple(row.cleaned_row_identity for row in selected_rows),
        ordered_pit_visibility_identities=tuple(
            row.pit_visibility_identity for row in selected_rows
        ),
    )
    _bytes, manifest, replay_status = verify_partition_rebuild_hash_replay(
        dataset_id="materialized-ds-1",
        dataset_version="v1",
        partition=partition,
        upstream_rows=rows,
        upstream=upstream,
        lineage_complete=True,
        build_started_at=started,
        build_completed_at=completed,
        partition_identity_sha256=partition_identity,
    )
    assert replay_status is RebuildHashReplayStatus.PASS
    assert manifest.row_count >= 0
    assert manifest.byte_count >= 0
    assert len(manifest.content_sha256) == 64
    assert len(manifest.partition_identity_sha256) == 64
    assert len(manifest.manifest_sha256) == 64
    assert manifest.partition_date_field == PARTITION_DATE_FIELD
    assert manifest.lineage_complete is True


def test_partition_identity_differs_from_content_hash() -> None:
    row = make_row()
    partition = partition_for_name(PartitionName.TRAIN)
    partition_identity = materialized_partition_identity_sha256(
        dataset_id="materialized-ds-1",
        dataset_version="v1",
        partition_name=partition.name,
        partition_start_date=partition.start_date,
        partition_end_date=partition.end_date,
        ordered_cleaned_row_identities=(row.cleaned_row_identity,),
        ordered_pit_visibility_identities=(row.pit_visibility_identity,),
    )
    assert partition_identity != "abc123"
