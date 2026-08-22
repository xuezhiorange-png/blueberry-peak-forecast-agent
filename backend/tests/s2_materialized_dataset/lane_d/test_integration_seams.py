"""Lane D integration seam tests against shared contracts."""

from __future__ import annotations

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
from backend.app.s2_materialized_dataset.lane_d.builder import build_materialized_dataset
from backend.app.s2_materialized_dataset.shared.contracts import (
    MATERIALIZED_DATASET_API_POLICY_VERSION,
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
)

pytestmark = [pytest.mark.unit, pytest.mark.contract]


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
