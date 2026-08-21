"""Lane D rebuild parity tests."""

from __future__ import annotations

from datetime import UTC, date, datetime

from backend.app.s2_materialized_dataset.lane_d.builder import (
    materialize_partition_bytes,
    rebuild_partition_bytes,
    rows_for_partition,
    verify_partition_rebuild_hash_replay,
)
from backend.app.s2_materialized_dataset.lane_d.hashing import (
    materialized_partition_identity_sha256,
)
from backend.app.s2_materialized_dataset.lane_d.partitions import partition_for_name
from backend.app.s2_materialized_dataset.shared.contracts import (
    PartitionName,
    RebuildHashReplayStatus,
)
from backend.tests.s2_materialized_dataset.lane_d.conftest import complete_upstream, make_row


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


def test_replay_verification_sets_pass_only_after_hash_match() -> None:
    upstream = complete_upstream()
    partition = partition_for_name(PartitionName.TRAIN)
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
    started = datetime(2026, 4, 1, tzinfo=UTC)
    _bytes, manifest, status = verify_partition_rebuild_hash_replay(
        dataset_id="materialized-ds-1",
        dataset_version="v1",
        partition=partition,
        upstream_rows=rows,
        upstream=upstream,
        lineage_complete=True,
        build_started_at=started,
        build_completed_at=started,
        partition_identity_sha256=partition_identity,
    )
    assert status is RebuildHashReplayStatus.PASS
    assert manifest.rebuild_hash_replay_status is RebuildHashReplayStatus.PASS
