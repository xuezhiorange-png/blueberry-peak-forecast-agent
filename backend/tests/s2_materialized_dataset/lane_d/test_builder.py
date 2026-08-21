"""Lane D deterministic builder tests."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from backend.app.s2_materialized_dataset.lane_d.builder import (
    BuildTimestamps,
    MaterializedDatasetBuildError,
    build_materialized_dataset,
    evaluate_quality_gate,
    materialize_partition_bytes,
)
from backend.app.s2_materialized_dataset.lane_d.hashing import materialized_dataset_identity_sha256
from backend.app.s2_materialized_dataset.lane_d.partitions import partition_for_name
from backend.app.s2_materialized_dataset.shared.contracts import (
    PARTITION_DATE_FIELD,
    PartitionName,
    QualityGateStatus,
    RebuildHashReplayStatus,
)
from backend.tests.s2_materialized_dataset.lane_d.conftest import (
    FakeLaneA,
    complete_upstream,
    make_row,
)


def test_builder_splits_rows_by_harvest_business_date() -> None:
    rows = (
        make_row(harvest_business_date=date(2025, 9, 1)),
        make_row(
            harvest_business_date=date(2026, 2, 1),
            source_row_identity="source-row-2",
            cleaned_row_identity="cleaned-row-2",
            pit_visibility_identity="pit-vis-2",
            revision_winner_identity="rev-win-2",
        ),
        make_row(
            harvest_business_date=date(2026, 3, 15),
            source_row_identity="source-row-3",
            cleaned_row_identity="cleaned-row-3",
            pit_visibility_identity="pit-vis-3",
            revision_winner_identity="rev-win-3",
        ),
    )
    upstream = complete_upstream(rows=rows)
    timestamps = BuildTimestamps(
        started_at=datetime(2026, 4, 1, 0, 0, tzinfo=UTC),
        completed_at=datetime(2026, 4, 1, 0, 1, tzinfo=UTC),
    )
    result = build_materialized_dataset(
        dataset_id="materialized-ds-1",
        dataset_version="v1",
        upstream=upstream,
        timestamps=timestamps,
    )
    by_name = {manifest.partition_name: manifest for manifest in result.partitions}
    assert by_name[PartitionName.TRAIN].row_count == 1
    assert by_name[PartitionName.VALIDATION].row_count == 1
    assert by_name[PartitionName.TEST].row_count == 0
    assert result.lineage_complete is True
    assert result.quality_gate_status is QualityGateStatus.ACCEPTED
    assert len(result.materialized_dataset_identity_sha256) == 64
    for manifest in result.partitions:
        assert manifest.rebuild_hash_replay_status is RebuildHashReplayStatus.PASS
        assert manifest.partition_identity_sha256 != manifest.content_sha256


def test_builder_fail_closed_when_lineage_incomplete() -> None:
    upstream = complete_upstream()
    upstream = type(upstream)(
        lane_a=FakeLaneA(lineage_present=False),
        lane_b=upstream.lane_b,
        lane_c=upstream.lane_c,
    )
    with pytest.raises(MaterializedDatasetBuildError, match="lineage_complete=false"):
        build_materialized_dataset(
            dataset_id="materialized-ds-1",
            dataset_version="v1",
            upstream=upstream,
        )


def test_test_partition_uses_synthetic_bytes_only() -> None:
    upstream = complete_upstream(
        rows=(
            make_row(
                harvest_business_date=date(2026, 3, 15),
                source_row_identity="source-row-test",
                cleaned_row_identity="cleaned-row-test",
                pit_visibility_identity="pit-vis-test",
                revision_winner_identity="rev-win-test",
            ),
        )
    )
    test_partition = partition_for_name(PartitionName.TEST)
    partition_bytes = materialize_partition_bytes(
        partition=test_partition,
        upstream_rows=upstream.lane_b.iter_materializable_rows(),
    )
    assert partition_bytes.row_count == 0
    assert b"s2_test_partition_synthetic" in partition_bytes.content_bytes
    assert partition_bytes.byte_count == len(partition_bytes.content_bytes)
    assert len(partition_bytes.content_sha256) == 64


def test_partition_date_field_is_harvest_business_date() -> None:
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
    for manifest in result.partitions:
        assert manifest.partition_date_field == PARTITION_DATE_FIELD


def test_dataset_identity_is_deterministic() -> None:
    upstream = complete_upstream()
    timestamps = BuildTimestamps(
        started_at=datetime(2026, 4, 1, tzinfo=UTC),
        completed_at=datetime(2026, 4, 1, tzinfo=UTC),
    )
    first = build_materialized_dataset(
        dataset_id="materialized-ds-1",
        dataset_version="v1",
        upstream=upstream,
        timestamps=timestamps,
    )
    second = build_materialized_dataset(
        dataset_id="materialized-ds-1",
        dataset_version="v1",
        upstream=upstream,
        timestamps=timestamps,
    )
    assert first.materialized_dataset_identity_sha256 == second.materialized_dataset_identity_sha256
    assert len(first.materialized_dataset_identity_sha256) == 64


def test_dataset_identity_binds_partition_identities_and_content_hashes() -> None:
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
    recomputed = materialized_dataset_identity_sha256(
        dataset_id=result.dataset_id,
        dataset_version=result.dataset_version,
        raw_policy_version=upstream.lane_a.raw_policy_version,
        cleaning_policy_version=upstream.lane_b.cleaning_policy_version,
        correction_policy_version=upstream.lane_b.correction_policy_version,
        exclusion_policy_version=upstream.lane_b.exclusion_policy_version,
        visibility_policy_version=upstream.lane_c.visibility_policy_version,
        revision_winner_policy_version=upstream.lane_c.revision_winner_policy_version,
        ordered_partition_identities=tuple(
            manifest.partition_identity_sha256 for manifest in result.partitions
        ),
        ordered_partition_content_hashes=tuple(
            manifest.content_sha256 for manifest in result.partitions
        ),
    )
    assert recomputed == result.materialized_dataset_identity_sha256


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
    assert (
        evaluate_quality_gate(
            lineage_complete=result.lineage_complete,
            partition_manifests=result.partitions,
        )
        is QualityGateStatus.ACCEPTED
    )
