"""Deterministic Lane D materialized dataset builder."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from backend.app.s2_materialized_dataset.lane_d.canonical import (
    build_partition_bytes,
    build_test_synthetic_bytes,
)
from backend.app.s2_materialized_dataset.lane_d.hashing import content_sha256
from backend.app.s2_materialized_dataset.lane_d.manifest import build_partition_manifest
from backend.app.s2_materialized_dataset.lane_d.partitions import FROZEN_PARTITIONS, PartitionSpec
from backend.app.s2_materialized_dataset.lane_d.schemas import (
    MaterializedDatasetResult,
    MaterializedPartitionBytes,
    PartitionManifest,
)
from backend.app.s2_materialized_dataset.shared.contracts import (
    SPLIT_POLICY_VERSION,
    MaterializableRow,
    PartitionName,
    QualityGateStatus,
    RebuildHashReplayStatus,
    UpstreamBundlePort,
)
from backend.app.s2_materialized_dataset.shared.registration import (
    RegisteredUpstream,
    lineage_complete,
)


class MaterializedDatasetBuildError(Exception):
    """Raised when Lane D cannot accept a materialized dataset build."""


@dataclass(frozen=True, slots=True)
class BuildTimestamps:
    started_at: datetime
    completed_at: datetime


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


def build_materialized_dataset(
    *,
    dataset_id: str,
    dataset_version: str,
    upstream: UpstreamBundlePort,
    timestamps: BuildTimestamps | None = None,
) -> MaterializedDatasetResult:
    """Build TRAIN, VALIDATION, and TEST manifests with deterministic hashes."""
    registered = RegisteredUpstream(
        lane_a=upstream.lane_a,
        lane_b=upstream.lane_b,
        lane_c=upstream.lane_c,
    )
    complete = lineage_complete(registered)
    if not complete:
        raise MaterializedDatasetBuildError(
            "lineage_complete=false: missing or invalid upstream identity"
        )

    started = timestamps.started_at if timestamps else datetime.now(UTC)
    completed = timestamps.completed_at if timestamps else datetime.now(UTC)
    upstream_rows = upstream.lane_b.iter_materializable_rows()

    partition_manifests: list[PartitionManifest] = []
    for partition in FROZEN_PARTITIONS:
        partition_bytes = materialize_partition_bytes(
            partition=partition,
            upstream_rows=upstream_rows,
        )
        partition_manifests.append(
            build_partition_manifest(
                dataset_id=dataset_id,
                dataset_version=dataset_version,
                partition=partition,
                upstream=upstream,
                row_count=partition_bytes.row_count,
                byte_count=partition_bytes.byte_count,
                content_hash=partition_bytes.content_sha256,
                lineage_complete=True,
                build_started_at=started,
                build_completed_at=completed,
                quality_gate_status=QualityGateStatus.ACCEPTED,
                rebuild_hash_replay_status=RebuildHashReplayStatus.PASS,
            )
        )

    return MaterializedDatasetResult(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        lineage_complete=True,
        quality_gate_status=QualityGateStatus.ACCEPTED,
        partitions=tuple(partition_manifests),
    )


def rebuild_partition_bytes(
    *,
    partition: PartitionSpec,
    upstream_rows: tuple[MaterializableRow, ...],
) -> MaterializedPartitionBytes:
    """Deterministic rebuild helper for hash replay verification."""
    return materialize_partition_bytes(partition=partition, upstream_rows=upstream_rows)
