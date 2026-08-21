"""Lane D rebuild parity tests."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
import sqlalchemy as sa

from backend.app.s2_materialized_dataset.lane_d.builder import (
    BuildTimestamps,
    materialize_partition_bytes,
    rebuild_partition_bytes,
    rows_for_partition,
    verify_partition_rebuild_hash_replay,
)
from backend.app.s2_materialized_dataset.lane_d.hashing import (
    materialized_partition_identity_sha256,
)
from backend.app.s2_materialized_dataset.lane_d.partitions import partition_for_name
from backend.app.s2_materialized_dataset.lane_d.service import (
    MaterializedDatasetConflictError,
    S2MaterializedDatasetModel,
    S2MaterializedMaterializableRowModel,
    S2MaterializedPartitionModel,
    persist_materialized_dataset,
    rebuild_materialized_dataset_from_storage,
    verify_storage_rebuild_parity,
)
from backend.app.s2_materialized_dataset.shared.contracts import (
    PartitionName,
    RebuildHashReplayStatus,
)
from backend.tests.s2_materialized_dataset.lane_d.conftest import (
    _identity_hash,
    complete_upstream,
    make_row,
)

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def test_rebuild_produces_identical_content_hash() -> None:
    rows = (
        make_row(harvest_business_date=date(2025, 9, 1)),
        make_row(
            harvest_business_date=date(2026, 2, 1),
            source_row_identity=_identity_hash("source-row-2"),
            cleaned_row_identity=_identity_hash("cleaned-row-2"),
            pit_visibility_identity=_identity_hash("pit-vis-2"),
            revision_winner_identity=_identity_hash("rev-win-2"),
        ),
    )
    partition = partition_for_name(PartitionName.TRAIN)
    first = materialize_partition_bytes(partition=partition, upstream_rows=rows)
    second = rebuild_partition_bytes(partition=partition, upstream_rows=rows)
    assert first.content_sha256 == second.content_sha256
    assert first.byte_count == second.byte_count
    assert first.row_count == second.row_count


def test_test_rebuild_is_deterministic() -> None:
    partition = partition_for_name(PartitionName.TEST)
    first = rebuild_partition_bytes(partition=partition, upstream_rows=())
    second = rebuild_partition_bytes(partition=partition, upstream_rows=())
    assert first == second


def test_replay_verification_sets_pass_only_after_hash_match() -> None:
    upstream = complete_upstream()
    partition = partition_for_name(PartitionName.TRAIN)
    rows = upstream.lane_b.iter_materializable_rows()
    selected_rows = rows_for_partition(rows, partition)
    partition_identity = materialized_partition_identity_sha256(
        dataset_id="materialized-ds-1",
        dataset_version="v1",
        partition_name=partition.name,
        partition_start_date=partition.start_date,
        partition_end_date=partition.end_date,
        ordered_cleaned_row_identities=tuple(row.cleaned_row_identity for row in selected_rows),
        ordered_pit_visibility_identities=tuple(
            row.pit_visibility_identity for row in selected_rows
        ),
    )
    started = datetime(2026, 4, 1, tzinfo=UTC)
    _bytes, manifest, status = verify_partition_rebuild_hash_replay(
        dataset_id="materialized-ds-1",
        dataset_version="v1",
        partition=partition,
        upstream_rows=rows,
        upstream=upstream,
        lineage_complete=True,
        build_started_at=started,
        build_completed_at=started,
        partition_identity_sha256=partition_identity,
    )
    assert status is RebuildHashReplayStatus.PASS
    assert manifest.rebuild_hash_replay_status is RebuildHashReplayStatus.PASS


def test_persist_is_idempotent_for_same_identity(lane_d_migrated_session) -> None:
    upstream = complete_upstream()
    timestamps = BuildTimestamps(
        started_at=datetime(2026, 4, 1, tzinfo=UTC),
        completed_at=datetime(2026, 4, 1, tzinfo=UTC),
    )
    first = persist_materialized_dataset(
        lane_d_migrated_session,
        dataset_id="materialized-ds-1",
        dataset_version="v1",
        upstream=upstream,
        timestamps=timestamps,
    )
    lane_d_migrated_session.commit()
    dataset_count = lane_d_migrated_session.scalar(
        sa.select(sa.func.count()).select_from(S2MaterializedDatasetModel)
    )
    row_count = lane_d_migrated_session.scalar(
        sa.select(sa.func.count()).select_from(S2MaterializedMaterializableRowModel)
    )
    second = persist_materialized_dataset(
        lane_d_migrated_session,
        dataset_id="materialized-ds-1",
        dataset_version="v1",
        upstream=upstream,
        timestamps=timestamps,
    )
    lane_d_migrated_session.commit()
    assert second.materialized_dataset_identity_sha256 == first.materialized_dataset_identity_sha256
    assert (
        lane_d_migrated_session.scalar(
            sa.select(sa.func.count()).select_from(S2MaterializedDatasetModel)
        )
        == dataset_count
    )
    assert (
        lane_d_migrated_session.scalar(
            sa.select(sa.func.count()).select_from(S2MaterializedMaterializableRowModel)
        )
        == row_count
    )


def test_persist_conflicts_when_same_version_differs(lane_d_migrated_session) -> None:
    upstream = complete_upstream()
    timestamps = BuildTimestamps(
        started_at=datetime(2026, 4, 1, tzinfo=UTC),
        completed_at=datetime(2026, 4, 1, tzinfo=UTC),
    )
    persist_materialized_dataset(
        lane_d_migrated_session,
        dataset_id="materialized-ds-1",
        dataset_version="v1",
        upstream=upstream,
        timestamps=timestamps,
    )
    lane_d_migrated_session.commit()
    conflicting_upstream = complete_upstream(
        rows=(
            make_row(harvest_business_date=date(2025, 10, 1)),
            make_row(
                harvest_business_date=date(2026, 2, 15),
                source_row_identity=_identity_hash("source-row-2"),
                cleaned_row_identity=_identity_hash("cleaned-row-2"),
                pit_visibility_identity=_identity_hash("pit-vis-2"),
                revision_winner_identity=_identity_hash("rev-win-2"),
            ),
        )
    )
    with pytest.raises(MaterializedDatasetConflictError):
        persist_materialized_dataset(
            lane_d_migrated_session,
            dataset_id="materialized-ds-1",
            dataset_version="v1",
            upstream=conflicting_upstream,
            timestamps=timestamps,
        )


def test_storage_rebuild_matches_persisted_hashes(lane_d_migrated_session) -> None:
    upstream = complete_upstream()
    timestamps = BuildTimestamps(
        started_at=datetime(2026, 4, 1, tzinfo=UTC),
        completed_at=datetime(2026, 4, 1, tzinfo=UTC),
    )
    persisted = persist_materialized_dataset(
        lane_d_migrated_session,
        dataset_id="materialized-ds-1",
        dataset_version="v1",
        upstream=upstream,
        timestamps=timestamps,
    )
    lane_d_migrated_session.commit()
    verify_storage_rebuild_parity(
        lane_d_migrated_session,
        dataset_id="materialized-ds-1",
        dataset_version="v1",
    )
    rebuilt = rebuild_materialized_dataset_from_storage(
        lane_d_migrated_session,
        dataset_id="materialized-ds-1",
        dataset_version="v1",
    )
    assert rebuilt.materialized_dataset_identity_sha256 == (
        persisted.materialized_dataset_identity_sha256
    )
    persisted_by_name = {manifest.partition_name: manifest for manifest in persisted.partitions}
    for rebuilt_manifest in rebuilt.partitions:
        stored_manifest = persisted_by_name[rebuilt_manifest.partition_name]
        assert rebuilt_manifest.content_sha256 == stored_manifest.content_sha256
        assert rebuilt_manifest.manifest_sha256 == stored_manifest.manifest_sha256


def test_loaded_partitions_include_synthetic_test_placeholder(lane_d_migrated_session) -> None:
    upstream = complete_upstream()
    timestamps = BuildTimestamps(
        started_at=datetime(2026, 4, 1, tzinfo=UTC),
        completed_at=datetime(2026, 4, 1, tzinfo=UTC),
    )
    result = persist_materialized_dataset(
        lane_d_migrated_session,
        dataset_id="materialized-ds-1",
        dataset_version="v1",
        upstream=upstream,
        timestamps=timestamps,
    )
    lane_d_migrated_session.commit()
    by_name = {manifest.partition_name: manifest for manifest in result.partitions}
    assert by_name[PartitionName.TEST].row_count == 0
    partition_row = lane_d_migrated_session.scalar(
        sa.select(S2MaterializedPartitionModel).where(
            S2MaterializedPartitionModel.partition_name == PartitionName.TEST.value
        )
    )
    assert partition_row is not None
    assert b"s2_test_partition_synthetic" in partition_row.content_bytes


def test_persisted_rows_do_not_coerce_unknown_days_to_zero(lane_d_migrated_session) -> None:
    upstream = complete_upstream(
        rows=(
            make_row(harvest_business_date=date(2025, 9, 1), quantity="42.500000"),
            make_row(
                harvest_business_date=date(2026, 2, 15),
                quantity="17.250000",
                source_row_identity=_identity_hash("source-row-2"),
                cleaned_row_identity=_identity_hash("cleaned-row-2"),
                pit_visibility_identity=_identity_hash("pit-vis-2"),
                revision_winner_identity=_identity_hash("rev-win-2"),
            ),
        )
    )
    timestamps = BuildTimestamps(
        started_at=datetime(2026, 4, 1, tzinfo=UTC),
        completed_at=datetime(2026, 4, 1, tzinfo=UTC),
    )
    persist_materialized_dataset(
        lane_d_migrated_session,
        dataset_id="materialized-ds-1",
        dataset_version="v1",
        upstream=upstream,
        timestamps=timestamps,
    )
    lane_d_migrated_session.commit()
    quantities = lane_d_migrated_session.scalars(
        sa.select(S2MaterializedMaterializableRowModel.actual_harvest_quantity_kg)
    ).all()
    assert quantities == [
        upstream.lane_b.rows[0].actual_harvest_quantity_kg,
        upstream.lane_b.rows[1].actual_harvest_quantity_kg,
    ]
    assert all(quantity != 0 for quantity in quantities)
