"""Lane D materialized dataset and split freeze (V0.3-S2 draft)."""

from __future__ import annotations

from typing import Any

__all__ = [
    "FROZEN_PARTITIONS",
    "BuildTimestamps",
    "MaterializedDatasetBuildError",
    "MaterializedDatasetResult",
    "MaterializedPartitionBytes",
    "PartitionManifest",
    "build_materialized_dataset",
    "materialized_dataset_identity_sha256",
    "materialized_partition_identity_sha256",
    "materialize_partition_bytes",
    "rebuild_partition_bytes",
]


def __getattr__(name: str) -> Any:
    if name in {
        "BuildTimestamps",
        "MaterializedDatasetBuildError",
        "build_materialized_dataset",
        "materialize_partition_bytes",
        "rebuild_partition_bytes",
    }:
        from backend.app.s2_materialized_dataset.lane_d import builder as lane_d_builder

        return getattr(lane_d_builder, name)
    if name in {"materialized_dataset_identity_sha256", "materialized_partition_identity_sha256"}:
        from backend.app.s2_materialized_dataset.lane_d import hashing as lane_d_hashing

        return getattr(lane_d_hashing, name)
    if name == "FROZEN_PARTITIONS":
        from backend.app.s2_materialized_dataset.lane_d import partitions as lane_d_partitions

        return lane_d_partitions.FROZEN_PARTITIONS
    if name in {"MaterializedDatasetResult", "MaterializedPartitionBytes", "PartitionManifest"}:
        from backend.app.s2_materialized_dataset.lane_d import schemas as lane_d_schemas

        return getattr(lane_d_schemas, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
