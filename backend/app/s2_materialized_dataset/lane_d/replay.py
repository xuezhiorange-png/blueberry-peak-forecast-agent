"""Independent rebuild and hash replay verification for Lane D."""

from __future__ import annotations

from datetime import datetime

from backend.app.s2_materialized_dataset.lane_d.identity import (
    materialized_partition_identity_sha256,
    partition_row_identities,
)
from backend.app.s2_materialized_dataset.lane_d.manifest import build_partition_manifest
from backend.app.s2_materialized_dataset.lane_d.materialize import (
    materialize_partition_bytes,
    rebuild_partition_bytes,
    rows_for_partition,
)
from backend.app.s2_materialized_dataset.lane_d.partitions import PartitionSpec
from backend.app.s2_materialized_dataset.lane_d.schemas import (
    MaterializedPartitionBytes,
    PartitionManifest,
)
from backend.app.s2_materialized_dataset.shared.contracts import (
    MaterializableRow,
    QualityGateStatus,
    RebuildHashReplayStatus,
    UpstreamBundlePort,
)


def verify_partition_rebuild_hash_replay(
    *,
    dataset_id: str,
    dataset_version: str,
    partition: PartitionSpec,
    upstream_rows: tuple[MaterializableRow, ...],
    upstream: UpstreamBundlePort,
    lineage_complete: bool,
    build_started_at: datetime,
    build_completed_at: datetime,
    partition_identity_sha256: str,
) -> tuple[MaterializedPartitionBytes, PartitionManifest, RebuildHashReplayStatus]:
    """Rebuild independently and compare content_sha256 and manifest_sha256."""
    initial_bytes = materialize_partition_bytes(
        partition=partition,
        upstream_rows=upstream_rows,
    )
    rebuilt_bytes = rebuild_partition_bytes(
        partition=partition,
        upstream_rows=upstream_rows,
    )
    content_match = initial_bytes.content_sha256 == rebuilt_bytes.content_sha256

    selected_rows = rows_for_partition(upstream_rows, partition)
    cleaned_identities, pit_identities = partition_row_identities(selected_rows)
    replay_partition_identity = materialized_partition_identity_sha256(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        partition_name=partition.name,
        partition_start_date=partition.start_date,
        partition_end_date=partition.end_date,
        ordered_cleaned_row_identities=cleaned_identities,
        ordered_pit_visibility_identities=pit_identities,
    )
    identity_match = partition_identity_sha256 == replay_partition_identity

    initial_manifest = build_partition_manifest(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        partition=partition,
        upstream=upstream,
        row_count=initial_bytes.row_count,
        byte_count=initial_bytes.byte_count,
        content_hash=initial_bytes.content_sha256,
        partition_identity_sha256=partition_identity_sha256,
        lineage_complete=lineage_complete,
        build_started_at=build_started_at,
        build_completed_at=build_completed_at,
        quality_gate_status=QualityGateStatus.REJECTED,
        rebuild_hash_replay_status=RebuildHashReplayStatus.NOT_RUN,
    )
    rebuilt_manifest = build_partition_manifest(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        partition=partition,
        upstream=upstream,
        row_count=rebuilt_bytes.row_count,
        byte_count=rebuilt_bytes.byte_count,
        content_hash=rebuilt_bytes.content_sha256,
        partition_identity_sha256=replay_partition_identity,
        lineage_complete=lineage_complete,
        build_started_at=build_started_at,
        build_completed_at=build_completed_at,
        quality_gate_status=QualityGateStatus.REJECTED,
        rebuild_hash_replay_status=RebuildHashReplayStatus.NOT_RUN,
    )
    manifest_match = initial_manifest.manifest_sha256 == rebuilt_manifest.manifest_sha256

    if content_match and manifest_match and identity_match:
        replay_status = RebuildHashReplayStatus.PASS
    else:
        replay_status = RebuildHashReplayStatus.FAIL

    final_manifest = build_partition_manifest(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        partition=partition,
        upstream=upstream,
        row_count=initial_bytes.row_count,
        byte_count=initial_bytes.byte_count,
        content_hash=initial_bytes.content_sha256,
        partition_identity_sha256=partition_identity_sha256,
        lineage_complete=lineage_complete,
        build_started_at=build_started_at,
        build_completed_at=build_completed_at,
        quality_gate_status=QualityGateStatus.REJECTED,
        rebuild_hash_replay_status=replay_status,
    )
    return initial_bytes, final_manifest, replay_status
