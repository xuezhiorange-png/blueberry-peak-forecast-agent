"""Deterministic Lane D materialized dataset builder."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from backend.app.s2_materialized_dataset.lane_d.canonical import (
    build_partition_bytes,
    build_test_synthetic_bytes,
)
from backend.app.s2_materialized_dataset.lane_d.hashing import (
    content_sha256,
    materialized_dataset_identity_sha256,
    materialized_partition_identity_sha256,
    partition_row_identities,
)
from backend.app.s2_materialized_dataset.lane_d.manifest import build_partition_manifest
from backend.app.s2_materialized_dataset.lane_d.partitions import FROZEN_PARTITIONS, PartitionSpec
from backend.app.s2_materialized_dataset.lane_d.schemas import (
    MaterializedDatasetResult,
    MaterializedPartitionBytes,
    PartitionManifest,
)
from backend.app.s2_materialized_dataset.shared.contracts import (
    PARTITION_DATE_FIELD,
    SOURCE_COHORT_MANIFEST_SHA256,
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


def rows_for_partition(
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
        selected = rows_for_partition(upstream_rows, partition)
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


def evaluate_quality_gate(
    *,
    lineage_complete: bool,
    partition_manifests: tuple[PartitionManifest, ...],
    partition_specs: tuple[PartitionSpec, ...] = FROZEN_PARTITIONS,
) -> QualityGateStatus:
    """Accept only when lineage, replay, boundaries, and cohort binding all pass."""
    if not lineage_complete:
        return QualityGateStatus.REJECTED
    if len(partition_manifests) != len(partition_specs):
        return QualityGateStatus.REJECTED
    for manifest, spec in zip(partition_manifests, partition_specs, strict=True):
        if manifest.rebuild_hash_replay_status is not RebuildHashReplayStatus.PASS:
            return QualityGateStatus.REJECTED
        if manifest.partition_name != spec.name:
            return QualityGateStatus.REJECTED
        if manifest.partition_start_date != spec.start_date:
            return QualityGateStatus.REJECTED
        if manifest.partition_end_date != spec.end_date:
            return QualityGateStatus.REJECTED
        if manifest.partition_date_field != PARTITION_DATE_FIELD:
            return QualityGateStatus.REJECTED
        if manifest.source_cohort_manifest_sha256 != SOURCE_COHORT_MANIFEST_SHA256:
            return QualityGateStatus.REJECTED
        if not manifest.partition_identity_sha256:
            return QualityGateStatus.REJECTED
        if manifest.row_count < 0 or manifest.byte_count < 0:
            return QualityGateStatus.REJECTED
        if len(manifest.content_sha256) != 64 or len(manifest.manifest_sha256) != 64:
            return QualityGateStatus.REJECTED
    return QualityGateStatus.ACCEPTED


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
    partition_identities: list[str] = []
    partition_content_hashes: list[str] = []

    for partition in FROZEN_PARTITIONS:
        selected_rows = rows_for_partition(upstream_rows, partition)
        cleaned_identities, pit_identities = partition_row_identities(selected_rows)
        partition_identity = materialized_partition_identity_sha256(
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            partition_name=partition.name,
            partition_start_date=partition.start_date,
            partition_end_date=partition.end_date,
            ordered_cleaned_row_identities=cleaned_identities,
            ordered_pit_visibility_identities=pit_identities,
        )
        _partition_bytes, manifest, replay_status = verify_partition_rebuild_hash_replay(
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            partition=partition,
            upstream_rows=upstream_rows,
            upstream=upstream,
            lineage_complete=True,
            build_started_at=started,
            build_completed_at=completed,
            partition_identity_sha256=partition_identity,
        )
        if replay_status is not RebuildHashReplayStatus.PASS:
            raise MaterializedDatasetBuildError(
                f"rebuild_hash_replay_status=FAIL for partition {partition.name.value}"
            )
        partition_identities.append(partition_identity)
        partition_content_hashes.append(manifest.content_sha256)
        partition_manifests.append(manifest)

    dataset_identity = materialized_dataset_identity_sha256(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        raw_policy_version=upstream.lane_a.raw_policy_version,
        cleaning_policy_version=upstream.lane_b.cleaning_policy_version,
        correction_policy_version=upstream.lane_b.correction_policy_version,
        exclusion_policy_version=upstream.lane_b.exclusion_policy_version,
        visibility_policy_version=upstream.lane_c.visibility_policy_version,
        revision_winner_policy_version=upstream.lane_c.revision_winner_policy_version,
        ordered_partition_identities=tuple(partition_identities),
        ordered_partition_content_hashes=tuple(partition_content_hashes),
    )

    provisional = tuple(partition_manifests)
    quality_status = evaluate_quality_gate(
        lineage_complete=True,
        partition_manifests=provisional,
    )
    if quality_status is not QualityGateStatus.ACCEPTED:
        raise MaterializedDatasetBuildError(
            "quality_gate_status=REJECTED after replay verification"
        )

    final_manifests = tuple(
        manifest.model_copy(update={"quality_gate_status": quality_status})
        for manifest in provisional
    )

    return MaterializedDatasetResult(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        materialized_dataset_identity_sha256=dataset_identity,
        lineage_complete=True,
        quality_gate_status=quality_status,
        partitions=final_manifests,
    )
