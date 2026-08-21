"""Deterministic Lane D materialized dataset builder."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from backend.app.s2_materialized_dataset.lane_d.identity import (
    materialized_dataset_identity_sha256,
    materialized_partition_identity_sha256,
    partition_row_identities,
)
from backend.app.s2_materialized_dataset.lane_d.materialize import rows_for_partition
from backend.app.s2_materialized_dataset.lane_d.partitions import FROZEN_PARTITIONS
from backend.app.s2_materialized_dataset.lane_d.quality import evaluate_quality_gate
from backend.app.s2_materialized_dataset.lane_d.replay import verify_partition_rebuild_hash_replay
from backend.app.s2_materialized_dataset.lane_d.schemas import (
    MaterializedDatasetResult,
    PartitionManifest,
)
from backend.app.s2_materialized_dataset.shared.contracts import (
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
