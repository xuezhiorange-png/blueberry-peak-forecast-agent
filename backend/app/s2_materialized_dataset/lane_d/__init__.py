"""Lane D materialized dataset and split freeze (V0.3-S2 draft)."""

from backend.app.s2_materialized_dataset.lane_d.builder import (
    BuildTimestamps,
    MaterializedDatasetBuildError,
    build_materialized_dataset,
)
from backend.app.s2_materialized_dataset.lane_d.identity import (
    materialized_dataset_identity_sha256,
    materialized_partition_identity_sha256,
)
from backend.app.s2_materialized_dataset.lane_d.materialize import (
    materialize_partition_bytes,
    rebuild_partition_bytes,
)
from backend.app.s2_materialized_dataset.lane_d.partitions import FROZEN_PARTITIONS
from backend.app.s2_materialized_dataset.lane_d.schemas import (
    MaterializedDatasetResult,
    MaterializedPartitionBytes,
    PartitionManifest,
)

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
