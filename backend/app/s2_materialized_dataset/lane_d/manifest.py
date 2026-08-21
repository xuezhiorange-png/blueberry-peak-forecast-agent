"""Manifest construction for Lane D materialized partitions."""

from __future__ import annotations

from datetime import datetime

from backend.app.s2_materialized_dataset.lane_d.hashing import manifest_sha256
from backend.app.s2_materialized_dataset.lane_d.partitions import PartitionSpec
from backend.app.s2_materialized_dataset.lane_d.schemas import PartitionManifest
from backend.app.s2_materialized_dataset.shared.contracts import (
    BUILDER_VERSION,
    CANONICAL_GRAIN,
    DATASET_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    MATERIALIZED_PARTITION_SCHEMA_VERSION,
    PARTITION_DATE_FIELD,
    SOURCE_COHORT_ID,
    SPLIT_POLICY_VERSION,
    TARGET_DECISION,
    QualityGateStatus,
    RebuildHashReplayStatus,
    UpstreamBundlePort,
)


def build_partition_manifest(
    *,
    dataset_id: str,
    dataset_version: str,
    partition: PartitionSpec,
    upstream: UpstreamBundlePort,
    row_count: int,
    byte_count: int,
    content_hash: str,
    lineage_complete: bool,
    build_started_at: datetime,
    build_completed_at: datetime,
    quality_gate_status: QualityGateStatus,
    rebuild_hash_replay_status: RebuildHashReplayStatus,
) -> PartitionManifest:
    lane_a = upstream.lane_a
    lane_b = upstream.lane_b
    lane_c = upstream.lane_c
    payload = {
        "builder_version": BUILDER_VERSION,
        "build_completed_at": build_completed_at,
        "build_started_at": build_started_at,
        "byte_count": byte_count,
        "canonical_grain": CANONICAL_GRAIN,
        "cleaning_policy_version": lane_b.cleaning_policy_version,
        "content_sha256": content_hash,
        "correction_policy_version": lane_b.correction_policy_version,
        "dataset_id": dataset_id,
        "dataset_schema_version": DATASET_SCHEMA_VERSION,
        "dataset_version": dataset_version,
        "exclusion_policy_version": lane_b.exclusion_policy_version,
        "lineage_complete": lineage_complete,
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "materialized_partition_schema_version": MATERIALIZED_PARTITION_SCHEMA_VERSION,
        "partition_date_field": PARTITION_DATE_FIELD,
        "partition_end_date": partition.end_date,
        "partition_name": partition.name,
        "partition_start_date": partition.start_date,
        "quality_gate_status": quality_gate_status,
        "raw_policy_version": lane_a.raw_policy_version,
        "rebuild_hash_replay_status": rebuild_hash_replay_status,
        "revision_winner_policy_version": lane_c.revision_winner_policy_version,
        "row_count": row_count,
        "source_cohort_id": SOURCE_COHORT_ID,
        "source_cohort_manifest_sha256": lane_a.source_cohort_manifest_sha256,
        "split_policy_version": SPLIT_POLICY_VERSION,
        "target_decision": TARGET_DECISION,
        "visibility_policy_version": lane_c.visibility_policy_version,
    }
    digest = manifest_sha256(payload)
    return PartitionManifest(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        partition_name=partition.name,
        source_cohort_id=SOURCE_COHORT_ID,
        source_cohort_manifest_sha256=lane_a.source_cohort_manifest_sha256,
        target_decision=TARGET_DECISION,
        canonical_grain=CANONICAL_GRAIN,
        partition_date_field=PARTITION_DATE_FIELD,
        partition_start_date=partition.start_date,
        partition_end_date=partition.end_date,
        raw_policy_version=lane_a.raw_policy_version,
        cleaning_policy_version=lane_b.cleaning_policy_version,
        correction_policy_version=lane_b.correction_policy_version,
        exclusion_policy_version=lane_b.exclusion_policy_version,
        visibility_policy_version=lane_c.visibility_policy_version,
        revision_winner_policy_version=lane_c.revision_winner_policy_version,
        split_policy_version=SPLIT_POLICY_VERSION,
        builder_version=BUILDER_VERSION,
        dataset_schema_version=DATASET_SCHEMA_VERSION,
        manifest_schema_version=MANIFEST_SCHEMA_VERSION,
        materialized_partition_schema_version=MATERIALIZED_PARTITION_SCHEMA_VERSION,
        row_count=row_count,
        byte_count=byte_count,
        content_sha256=content_hash,
        manifest_sha256=digest,
        build_started_at=build_started_at,
        build_completed_at=build_completed_at,
        lineage_complete=lineage_complete,
        quality_gate_status=quality_gate_status,
        rebuild_hash_replay_status=rebuild_hash_replay_status,
    )
