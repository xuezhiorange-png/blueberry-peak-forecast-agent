"""Quality gate evaluation for Lane D materialized datasets."""

from __future__ import annotations

from backend.app.s2_materialized_dataset.lane_d.partitions import FROZEN_PARTITIONS, PartitionSpec
from backend.app.s2_materialized_dataset.lane_d.schemas import PartitionManifest
from backend.app.s2_materialized_dataset.shared.contracts import (
    PARTITION_DATE_FIELD,
    SOURCE_COHORT_MANIFEST_SHA256,
    QualityGateStatus,
    RebuildHashReplayStatus,
)


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
