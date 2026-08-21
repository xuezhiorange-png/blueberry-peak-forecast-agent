"""Lane D quality gate evaluation tests."""

from __future__ import annotations

from datetime import UTC, datetime

from backend.app.s2_materialized_dataset.lane_d.builder import (
    BuildTimestamps,
    build_materialized_dataset,
)
from backend.app.s2_materialized_dataset.lane_d.quality import evaluate_quality_gate
from backend.app.s2_materialized_dataset.shared.contracts import (
    QualityGateStatus,
    RebuildHashReplayStatus,
)
from backend.tests.s2_materialized_dataset.lane_d.conftest import complete_upstream


def test_quality_gate_rejects_incomplete_lineage() -> None:
    upstream = complete_upstream()
    result = build_materialized_dataset(
        dataset_id="materialized-ds-1",
        dataset_version="v1",
        upstream=upstream,
        timestamps=BuildTimestamps(
            started_at=datetime(2026, 4, 1, tzinfo=UTC),
            completed_at=datetime(2026, 4, 1, tzinfo=UTC),
        ),
    )
    rejected = evaluate_quality_gate(
        lineage_complete=False,
        partition_manifests=result.partitions,
    )
    assert rejected is QualityGateStatus.REJECTED


def test_quality_gate_rejects_failed_replay() -> None:
    upstream = complete_upstream()
    result = build_materialized_dataset(
        dataset_id="materialized-ds-1",
        dataset_version="v1",
        upstream=upstream,
        timestamps=BuildTimestamps(
            started_at=datetime(2026, 4, 1, tzinfo=UTC),
            completed_at=datetime(2026, 4, 1, tzinfo=UTC),
        ),
    )
    failed_manifest = result.partitions[0].model_copy(
        update={"rebuild_hash_replay_status": RebuildHashReplayStatus.FAIL}
    )
    partitions = (failed_manifest, *result.partitions[1:])
    rejected = evaluate_quality_gate(
        lineage_complete=True,
        partition_manifests=partitions,
    )
    assert rejected is QualityGateStatus.REJECTED


def test_builder_quality_gate_is_not_empty_stamp() -> None:
    upstream = complete_upstream()
    result = build_materialized_dataset(
        dataset_id="materialized-ds-1",
        dataset_version="v1",
        upstream=upstream,
        timestamps=BuildTimestamps(
            started_at=datetime(2026, 4, 1, tzinfo=UTC),
            completed_at=datetime(2026, 4, 1, tzinfo=UTC),
        ),
    )
    assert evaluate_quality_gate(
        lineage_complete=result.lineage_complete,
        partition_manifests=result.partitions,
    ) is QualityGateStatus.ACCEPTED
