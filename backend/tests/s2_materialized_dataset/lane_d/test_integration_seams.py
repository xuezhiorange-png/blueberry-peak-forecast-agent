"""Lane D integration seam tests against shared contracts."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import sqlalchemy as sa
from httpx import AsyncClient

from backend.app.main import create_app
from backend.app.models import (
    S2MaterializedDatasetModel,
    S2MaterializedMaterializableRowModel,
    S2MaterializedPartitionModel,
)
from backend.app.repositories import (
    load_materialized_dataset_result,
    persist_materialized_dataset,
    verify_storage_rebuild_parity,
)
from backend.app.s2_materialized_dataset.lane_d.builder import (
    BuildTimestamps,
    build_materialized_dataset,
)
from backend.app.s2_materialized_dataset.lane_d.partitions import TEST_END, TEST_START
from backend.app.s2_materialized_dataset.lane_d.service import (
    Source002E5MaterializationError,
    _build_source_002_materializable_rows_from_cleaned,
    compute_grain_revision_winner_identity,
    compute_idfl_pit_visibility_not_applicable_identity,
    controlled_materialize_source_002_from_environment,
    partition_row_counts_for_e5_report,
    source_002_harvest_date_allowed_for_materialization,
    verify_source_002_sql_boundaries,
)
from backend.app.s2_materialized_dataset.shared.contracts import (
    MATERIALIZED_DATASET_API_POLICY_VERSION,
    SOURCE_002_EXPECTED_IDFL_SQL_ROW_COUNT,
    SOURCE_002_EXPECTED_NON_EXCLUDED_GRAIN_COUNT,
    SOURCE_002_ROW_LEVEL_READ,
    PartitionName,
)
from backend.app.s2_materialized_dataset.shared.registration import (
    register_upstream,
    upstream_bundle_from_registered,
)
from backend.tests.s2_materialized_dataset.lane_d.conftest import (
    LANE_D_MIGRATION_DOWN_REVISION,
    LANE_D_MIGRATION_REVISION,
    assert_lane_d_alembic_head_and_revision_contract,
    complete_upstream,
    make_row,
)

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def _fake_source_002_cleaned_row(
    *,
    harvest_business_date: date,
    collapsed_hash: str,
    quantity: str = "10.0",
    presence: str = "KNOWN",
) -> SimpleNamespace:
    return SimpleNamespace(
        season_business_key="2025~2026",
        farm_business_key="farm-a",
        subfarm_business_key="subfarm-1",
        variety_business_key="variety-x",
        harvest_business_date=harvest_business_date,
        source_row_identity_hash=collapsed_hash,
        cleaned_row_identity_hash="b" * 64,
        quantity_presence_status=presence,
        effective_actual_harvest_quantity_kg=(
            None if presence == "UNKNOWN_NOT_ZERO" else Decimal(quantity)
        ),
    )


def test_source_002_loader_excludes_test_window_grains_from_materializable_rows() -> None:
    train_hash = "a" * 64
    test_hash = "c" * 64
    contributor_train = "d" * 64
    contributor_test = "e" * 64
    cleaned_rows = (
        _fake_source_002_cleaned_row(
            harvest_business_date=date(2025, 9, 1),
            collapsed_hash=train_hash,
        ),
        _fake_source_002_cleaned_row(
            harvest_business_date=TEST_START,
            collapsed_hash=test_hash,
        ),
        _fake_source_002_cleaned_row(
            harvest_business_date=TEST_END,
            collapsed_hash=test_hash,
        ),
    )
    grain_index = {
        train_hash: (contributor_train,),
        test_hash: (contributor_test,),
    }
    idfl_by_identity = {
        contributor_train: "1" * 64,
        contributor_test: "2" * 64,
    }
    rows, test_window_skipped = _build_source_002_materializable_rows_from_cleaned(
        cleaned_rows=cleaned_rows,
        grain_index=grain_index,
        idfl_by_identity=idfl_by_identity,
    )
    assert len(rows) == 1
    assert test_window_skipped == 2
    assert rows[0].harvest_business_date == date(2025, 9, 1)
    assert all(
        source_002_harvest_date_allowed_for_materialization(row.harvest_business_date)
        for row in rows
    )
    assert not any(TEST_START <= row.harvest_business_date <= TEST_END for row in rows)


def test_source_002_loader_allows_explicit_zero_kg_known_quantity() -> None:
    collapsed_hash = "f" * 64
    contributor = "0" * 64
    rows, skipped = _build_source_002_materializable_rows_from_cleaned(
        cleaned_rows=(
            _fake_source_002_cleaned_row(
                harvest_business_date=date(2026, 2, 1),
                collapsed_hash=collapsed_hash,
                quantity="0",
            ),
        ),
        grain_index={collapsed_hash: (contributor,)},
        idfl_by_identity={contributor: "3" * 64},
    )
    assert skipped == 0
    assert len(rows) == 1
    assert rows[0].actual_harvest_quantity_kg == Decimal("0")


def test_source_002_loader_rejects_unknown_not_zero_grains() -> None:
    collapsed_hash = "9" * 64
    contributor = "8" * 64
    with pytest.raises(Source002E5MaterializationError, match="UNKNOWN_NOT_ZERO"):
        _build_source_002_materializable_rows_from_cleaned(
            cleaned_rows=(
                _fake_source_002_cleaned_row(
                    harvest_business_date=date(2026, 2, 1),
                    collapsed_hash=collapsed_hash,
                    presence="UNKNOWN_NOT_ZERO",
                ),
            ),
            grain_index={collapsed_hash: (contributor,)},
            idfl_by_identity={contributor: "4" * 64},
        )


def test_source_002_filtered_bundle_persist_has_no_test_window_rows_in_table(
    lane_d_migrated_session,
) -> None:
    train_hash = "a" * 64
    test_hash = "c" * 64
    contributor_train = "d" * 64
    contributor_test = "e" * 64
    rows, test_window_skipped = _build_source_002_materializable_rows_from_cleaned(
        cleaned_rows=(
            _fake_source_002_cleaned_row(
                harvest_business_date=date(2025, 9, 1),
                collapsed_hash=train_hash,
            ),
            _fake_source_002_cleaned_row(
                harvest_business_date=TEST_START,
                collapsed_hash=test_hash,
            ),
        ),
        grain_index={
            train_hash: (contributor_train,),
            test_hash: (contributor_test,),
        },
        idfl_by_identity={
            contributor_train: "1" * 64,
            contributor_test: "2" * 64,
        },
    )
    assert test_window_skipped == 1
    upstream = complete_upstream(rows=rows)
    timestamps = BuildTimestamps(
        started_at=datetime(2026, 4, 1, tzinfo=UTC),
        completed_at=datetime(2026, 4, 1, tzinfo=UTC),
    )
    result = persist_materialized_dataset(
        lane_d_migrated_session,
        dataset_id="materialized-ds-source-002-filtered",
        dataset_version="v1",
        upstream=upstream,
        timestamps=timestamps,
    )
    lane_d_migrated_session.commit()
    test_partition = next(
        partition
        for partition in result.partitions
        if partition.partition_name is PartitionName.TEST
    )
    assert test_partition.row_count == 0
    train_rows, val_rows, test_rows = partition_row_counts_for_e5_report(rows)
    assert test_rows == 0
    assert train_rows == 1
    test_window_row_count = lane_d_migrated_session.scalar(
        sa.select(sa.func.count())
        .select_from(S2MaterializedMaterializableRowModel)
        .where(
            S2MaterializedMaterializableRowModel.harvest_business_date >= TEST_START,
            S2MaterializedMaterializableRowModel.harvest_business_date <= TEST_END,
        )
    )
    assert test_window_row_count == 0


def test_builder_consumes_registered_upstream_bundle() -> None:
    upstream = complete_upstream()
    registered = register_upstream(
        lane_a=upstream.lane_a,
        lane_b=upstream.lane_b,
        lane_c=upstream.lane_c,
    )
    bundle = upstream_bundle_from_registered(registered)
    result = build_materialized_dataset(
        dataset_id="materialized-ds-1",
        dataset_version="v1",
        upstream=bundle,
        timestamps=None,
    )
    assert len(result.partitions) == 3
    for manifest in result.partitions:
        assert manifest.row_count >= 0
        assert manifest.byte_count >= 0
        assert len(manifest.content_sha256) == 64
        assert len(manifest.partition_identity_sha256) == 64
        assert len(manifest.manifest_sha256) == 64
    assert len(result.materialized_dataset_identity_sha256) == 64


@pytest.mark.migration
def test_lane_d_migration_head_and_revision_contract() -> None:
    assert_lane_d_alembic_head_and_revision_contract()


@pytest.mark.migration
def test_lane_d_migration_creates_tables_with_numeric_and_hash_checks(
    lane_d_migrated_session,
) -> None:
    inspector = sa.inspect(lane_d_migrated_session.bind)
    assert {
        "s2_materialized_dataset",
        "s2_materialized_materializable_row",
        "s2_materialized_partition",
    }.issubset(set(inspector.get_table_names()))
    row_columns = {
        column["name"]: column
        for column in inspector.get_columns("s2_materialized_materializable_row")
    }
    assert "NUMERIC" in str(row_columns["actual_harvest_quantity_kg"]["type"]).upper()
    dataset_columns = {
        column["name"]: column for column in inspector.get_columns("s2_materialized_dataset")
    }
    assert len(str(dataset_columns["materialized_dataset_identity_sha256"]["type"])) > 0


@pytest.mark.migration
def test_lane_d_tables_reject_update_under_migration_triggers(
    lane_d_migrated_session,
    persisted_dataset,
) -> None:
    dataset_row = lane_d_migrated_session.scalar(
        sa.select(S2MaterializedDatasetModel).where(
            S2MaterializedDatasetModel.dataset_id == persisted_dataset.dataset_id
        )
    )
    assert dataset_row is not None
    with pytest.raises(sa.exc.IntegrityError):
        lane_d_migrated_session.execute(
            sa.text(
                """
                UPDATE s2_materialized_dataset
                SET lineage_complete = 0
                WHERE id = :row_id
                """
            ),
            {"row_id": dataset_row.id},
        )
        lane_d_migrated_session.commit()
    lane_d_migrated_session.rollback()
    with pytest.raises(sa.exc.IntegrityError):
        lane_d_migrated_session.execute(
            sa.text(
                """
                DELETE FROM s2_materialized_materializable_row
                WHERE materialized_dataset_id = :row_id
                """
            ),
            {"row_id": dataset_row.id},
        )
        lane_d_migrated_session.commit()
    lane_d_migrated_session.rollback()


def test_models_init_exports_lane_d_orm_models() -> None:
    assert S2MaterializedDatasetModel.__tablename__ == "s2_materialized_dataset"
    assert (
        S2MaterializedMaterializableRowModel.__tablename__ == "s2_materialized_materializable_row"
    )
    assert S2MaterializedPartitionModel.__tablename__ == "s2_materialized_partition"


def test_repositories_init_reexports_lane_d_service() -> None:
    assert callable(persist_materialized_dataset)
    assert callable(load_materialized_dataset_result)
    assert callable(verify_storage_rebuild_parity)


def test_main_includes_materialized_datasets_router() -> None:
    schema = create_app().openapi()
    assert (
        "/api/v1/materialized-datasets/{dataset_id}/versions/{dataset_version}" in schema["paths"]
    )


def test_api_init_exports_materialized_datasets_router() -> None:
    from backend.app.api import materialized_datasets_router

    assert materialized_datasets_router is materialized_datasets_router
    assert any(route.path for route in materialized_datasets_router.routes)


def test_source_002_row_level_read_remains_false() -> None:
    assert SOURCE_002_ROW_LEVEL_READ is False


def test_pit_visibility_not_applicable_identity_is_stable() -> None:
    first = compute_idfl_pit_visibility_not_applicable_identity()
    second = compute_idfl_pit_visibility_not_applicable_identity()
    assert first == second
    assert len(first) == 64


def test_grain_revision_winner_identity_singleton_uses_content_hash() -> None:
    content_hash = "a" * 64
    assert compute_grain_revision_winner_identity((content_hash,)) == content_hash


def test_grain_revision_winner_identity_multi_contributor_is_deterministic() -> None:
    hashes = ("b" * 64, "a" * 64)
    assert compute_grain_revision_winner_identity(hashes) == compute_grain_revision_winner_identity(
        tuple(reversed(hashes))
    )
    assert compute_grain_revision_winner_identity(hashes) != hashes[0]


def test_verify_sql_boundaries_fail_closed_on_idfl_count(monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock()
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.service.count_idfl_label_side_winner_sql_rows",
        lambda _session: 1,
    )
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.service.count_pit_visibility_sql_rows",
        lambda _session: 0,
    )
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.service.count_revision_winner_sql_rows",
        lambda _session: 0,
    )
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.service.count_non_excluded_cleaned_grain_sql_rows",
        lambda _session: SOURCE_002_EXPECTED_NON_EXCLUDED_GRAIN_COUNT,
    )
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.service._verify_kg_equal_from_sql_and_replay",
        lambda *_args, **_kwargs: True,
    )
    with pytest.raises(Source002E5MaterializationError, match="IDFL SQL count mismatch"):
        verify_source_002_sql_boundaries(
            session,
            artifact_bytes=b"bytes",
            batch=MagicMock(),
        )


def test_verify_sql_boundaries_fail_closed_on_pit_sql(monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock()
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.service.count_idfl_label_side_winner_sql_rows",
        lambda _session: SOURCE_002_EXPECTED_IDFL_SQL_ROW_COUNT,
    )
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.service.count_pit_visibility_sql_rows",
        lambda _session: 1,
    )
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.service.count_revision_winner_sql_rows",
        lambda _session: 0,
    )
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.service.count_non_excluded_cleaned_grain_sql_rows",
        lambda _session: SOURCE_002_EXPECTED_NON_EXCLUDED_GRAIN_COUNT,
    )
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.service._verify_kg_equal_from_sql_and_replay",
        lambda *_args, **_kwargs: True,
    )
    with pytest.raises(Source002E5MaterializationError, match="PIT SQL must be 0"):
        verify_source_002_sql_boundaries(
            session,
            artifact_bytes=b"bytes",
            batch=MagicMock(),
        )


def test_verify_sql_boundaries_fail_closed_on_kg_equal(monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock()
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.service.count_idfl_label_side_winner_sql_rows",
        lambda _session: SOURCE_002_EXPECTED_IDFL_SQL_ROW_COUNT,
    )
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.service.count_pit_visibility_sql_rows",
        lambda _session: 0,
    )
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.service.count_revision_winner_sql_rows",
        lambda _session: 0,
    )
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.service.count_non_excluded_cleaned_grain_sql_rows",
        lambda _session: SOURCE_002_EXPECTED_NON_EXCLUDED_GRAIN_COUNT,
    )
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.service._verify_kg_equal_from_sql_and_replay",
        lambda *_args, **_kwargs: False,
    )
    with pytest.raises(Source002E5MaterializationError, match="kg_equal is not true"):
        verify_source_002_sql_boundaries(
            session,
            artifact_bytes=b"bytes",
            batch=MagicMock(),
        )


def test_verify_sql_boundaries_fail_closed_on_old_winner_sql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock()
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.service.count_idfl_label_side_winner_sql_rows",
        lambda _session: SOURCE_002_EXPECTED_IDFL_SQL_ROW_COUNT,
    )
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.service.count_pit_visibility_sql_rows",
        lambda _session: 0,
    )
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.service.count_revision_winner_sql_rows",
        lambda _session: 1,
    )
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.service.count_non_excluded_cleaned_grain_sql_rows",
        lambda _session: SOURCE_002_EXPECTED_NON_EXCLUDED_GRAIN_COUNT,
    )
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.service._verify_kg_equal_from_sql_and_replay",
        lambda *_args, **_kwargs: True,
    )
    with pytest.raises(Source002E5MaterializationError, match="old revision winner SQL"):
        verify_source_002_sql_boundaries(
            session,
            artifact_bytes=b"bytes",
            batch=MagicMock(),
        )


def test_verify_sql_boundaries_fail_closed_on_non_excluded_grain_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock()
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.service.count_idfl_label_side_winner_sql_rows",
        lambda _session: SOURCE_002_EXPECTED_IDFL_SQL_ROW_COUNT,
    )
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.service.count_pit_visibility_sql_rows",
        lambda _session: 0,
    )
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.service.count_revision_winner_sql_rows",
        lambda _session: 0,
    )
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.service.count_non_excluded_cleaned_grain_sql_rows",
        lambda _session: 1,
    )
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.service._verify_kg_equal_from_sql_and_replay",
        lambda *_args, **_kwargs: True,
    )
    with pytest.raises(Source002E5MaterializationError, match="non-excluded grain count mismatch"):
        verify_source_002_sql_boundaries(
            session,
            artifact_bytes=b"bytes",
            batch=MagicMock(),
        )


def test_controlled_materialize_reports_object_missing_without_frozen_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "backend.app.s2_materialized_dataset.lane_d.service._source_002_frozen_object_available",
        lambda _roots: False,
    )
    report = controlled_materialize_source_002_from_environment(
        MagicMock(),
        dataset_id="source-002",
        dataset_version="e5-v1",
        persist=False,
    )
    assert report.rebuild_parity == "OBJECT_MISSING"
    assert report.dataset_identity is None
    assert report.test_rows == 0


def test_e5_report_test_rows_zero_when_upstream_has_test_window_grains() -> None:
    upstream = complete_upstream(
        rows=(
            make_row(harvest_business_date=date(2025, 9, 1)),
            make_row(
                harvest_business_date=TEST_START,
                source_row_identity="c" * 64,
                cleaned_row_identity="d" * 64,
                pit_visibility_identity="e" * 64,
                revision_winner_identity="f" * 64,
            ),
        )
    )
    train_rows, val_rows, test_rows = partition_row_counts_for_e5_report(
        upstream.lane_b.iter_materializable_rows()
    )
    assert test_rows == 0
    assert train_rows == 1
    assert val_rows == 0


def test_persisted_test_partition_row_count_zero_with_upstream_test_window_grains(
    lane_d_migrated_session,
) -> None:
    upstream = complete_upstream(
        rows=(
            make_row(harvest_business_date=date(2025, 9, 1)),
            make_row(
                harvest_business_date=TEST_END,
                source_row_identity="1" * 64,
                cleaned_row_identity="2" * 64,
                pit_visibility_identity="3" * 64,
                revision_winner_identity="4" * 64,
            ),
        )
    )
    timestamps = BuildTimestamps(
        started_at=datetime(2026, 4, 1, tzinfo=UTC),
        completed_at=datetime(2026, 4, 1, tzinfo=UTC),
    )
    result = persist_materialized_dataset(
        lane_d_migrated_session,
        dataset_id="materialized-ds-test-window",
        dataset_version="v1",
        upstream=upstream,
        timestamps=timestamps,
    )
    lane_d_migrated_session.commit()
    test_partition = next(
        partition
        for partition in result.partitions
        if partition.partition_name is PartitionName.TEST
    )
    assert test_partition.row_count == 0
    _, _, test_rows = partition_row_counts_for_e5_report(upstream.lane_b.iter_materializable_rows())
    assert test_rows == 0


@pytest.mark.asyncio
async def test_api_returns_manifest_hashes_without_test_bytes(
    lane_d_api_client: AsyncClient,
    persisted_dataset,
) -> None:
    response = await lane_d_api_client.get(
        f"/api/v1/materialized-datasets/{persisted_dataset.dataset_id}/versions/{persisted_dataset.dataset_version}"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["materialized_dataset_identity_sha256"] == (
        persisted_dataset.materialized_dataset_identity_sha256
    )
    assert payload["provenance"]["api_policy_version"] == MATERIALIZED_DATASET_API_POLICY_VERSION
    assert len(payload["partitions"]) == 3
    partition_names = {partition["partition_name"] for partition in payload["partitions"]}
    assert partition_names == {
        PartitionName.TRAIN.value,
        PartitionName.VALIDATION.value,
        PartitionName.TEST.value,
    }
    test_partition = next(
        partition for partition in payload["partitions"] if partition["partition_name"] == "TEST"
    )
    assert test_partition["row_count"] == 0
    assert "content_bytes" not in payload
    assert "content_bytes" not in test_partition
    assert len(test_partition["content_sha256"]) == 64


@pytest.mark.asyncio
async def test_api_returns_404_for_missing_dataset(lane_d_api_client: AsyncClient) -> None:
    response = await lane_d_api_client.get(
        "/api/v1/materialized-datasets/missing-dataset/versions/v0"
    )
    assert response.status_code == 404


def test_lane_d_revision_chain_constants() -> None:
    assert LANE_D_MIGRATION_REVISION == "d4e8f1a2b3c5"
    assert LANE_D_MIGRATION_DOWN_REVISION == "8c6aead9f8e9"
