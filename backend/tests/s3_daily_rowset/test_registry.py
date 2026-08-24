"""S3-A2 evaluation instance registry contract tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.app.s3_daily_rowset.registry import (
    CatalogSourceKind,
    EvaluationInstanceRegistryService,
    ForbiddenCatalogSourceError,
    InMemoryEvaluationInstanceCatalog,
    RegistryCatalogEntry,
)
from backend.app.s3_daily_rowset.schemas import (
    DatasetIdentity,
    DatasetIdentityMismatchError,
    EvaluationInstanceCell,
)
from backend.app.s3_daily_rowset.window import complete_season_window_dates
from backend.tests.s3_daily_rowset.conftest import (
    DATASET_IDENTITY,
    HORIZON_H7_SUCCESS_FIXTURE_HASH,
    make_cell,
)


def _registry(
    *,
    catalog: InMemoryEvaluationInstanceCatalog | None = None,
    dataset_identity: DatasetIdentity = DATASET_IDENTITY,
) -> EvaluationInstanceRegistryService:
    return EvaluationInstanceRegistryService(
        dataset_identity=dataset_identity,
        catalog=catalog,
    )


def test_default_unbound_catalog_is_empty_and_not_available() -> None:
    registry = _registry()
    snapshot = registry.snapshot()

    assert snapshot.evaluation_instance_registry_available is False
    assert snapshot.registry_source_status == "NOT_MATERIALIZED_OR_NOT_BOUND"
    assert snapshot.registry_identity_sha256 is None
    assert snapshot.in_scope_cells == ()
    assert snapshot.verification_units == ()
    assert snapshot.dataset_completeness_verified is False
    assert snapshot.current_s3_daily_rowset_completeness_verified is False
    assert registry.list_in_scope_cells() == ()
    assert registry.list_verification_units() == ()


def test_injected_empty_catalog_is_not_verified_or_available() -> None:
    catalog = InMemoryEvaluationInstanceCatalog(
        catalog_entries=(),
        bound_registry_identity_sha256=None,
        catalog_source_kind=CatalogSourceKind.BOUND_FIXTURE,
    )
    registry = _registry(catalog=catalog)
    snapshot = registry.snapshot()

    assert snapshot.evaluation_instance_registry_available is False
    assert snapshot.dataset_completeness_verified is False
    assert snapshot.current_s3_daily_rowset_completeness_verified is False
    assert snapshot.in_scope_cells == ()
    assert snapshot.verification_units == ()


def test_injected_fixture_catalog_lists_cell_and_three_verification_units() -> None:
    cutoff = datetime(2026, 2, 15, 16, 0, tzinfo=UTC)
    cell = make_cell(forecast_cutoff_at=cutoff)
    catalog = InMemoryEvaluationInstanceCatalog(
        catalog_entries=(RegistryCatalogEntry(cell=cell, partition="TRAIN"),),
        bound_registry_identity_sha256="fixture-catalog-identity-sha256-for-tests-only",
        catalog_source_kind=CatalogSourceKind.BOUND_FIXTURE,
    )
    registry = _registry(catalog=catalog)
    snapshot = registry.snapshot()

    assert snapshot.evaluation_instance_registry_available is False
    assert snapshot.dataset_completeness_verified is False
    assert snapshot.current_s3_daily_rowset_completeness_verified is False
    assert len(snapshot.in_scope_cells) == 1
    assert snapshot.in_scope_cells[0].cell == cell
    assert snapshot.in_scope_cells[0].partition == "TRAIN"
    assert len(snapshot.verification_units) == 3
    assert {unit.evaluation_window_days for unit in snapshot.verification_units} == {7, 14, 21}
    assert all(unit.cell == cell for unit in snapshot.verification_units)


def test_rejects_h7_fixture_hash_as_catalog_source() -> None:
    with pytest.raises(ForbiddenCatalogSourceError):
        InMemoryEvaluationInstanceCatalog(
            catalog_entries=(RegistryCatalogEntry(cell=make_cell(), partition="TRAIN"),),
            bound_registry_identity_sha256=HORIZON_H7_SUCCESS_FIXTURE_HASH,
            catalog_source_kind=CatalogSourceKind.BOUND_FIXTURE,
        )

    with pytest.raises(ForbiddenCatalogSourceError):
        _registry(
            catalog=InMemoryEvaluationInstanceCatalog(
                catalog_entries=(),
                bound_registry_identity_sha256=None,
                catalog_source_kind=CatalogSourceKind.H7_FIXTURE_HASH,
            ),
        )


def test_rejects_test_partition_cells_and_complete_season_test_overlap() -> None:
    test_cell = make_cell(
        forecast_cutoff_at=datetime(2026, 2, 28, 16, 0, tzinfo=UTC),
    )
    test_catalog = InMemoryEvaluationInstanceCatalog(
        catalog_entries=(RegistryCatalogEntry(cell=test_cell, partition="TEST"),),
        bound_registry_identity_sha256="test-partition-catalog-identity",
        catalog_source_kind=CatalogSourceKind.BOUND_FIXTURE,
    )
    test_registry = _registry(catalog=test_catalog)
    assert test_registry.list_in_scope_cells() == ()
    assert test_registry.list_verification_units() == ()

    horizon_test_cell = make_cell(
        forecast_cutoff_at=datetime(2026, 3, 9, 16, 0, tzinfo=UTC),
    )
    horizon_test_catalog = InMemoryEvaluationInstanceCatalog(
        catalog_entries=(RegistryCatalogEntry(cell=horizon_test_cell, partition="VALIDATION"),),
        bound_registry_identity_sha256="horizon-test-overlap-catalog-identity",
        catalog_source_kind=CatalogSourceKind.BOUND_FIXTURE,
    )
    horizon_test_registry = _registry(catalog=horizon_test_catalog)
    assert horizon_test_registry.list_in_scope_cells() == ()

    train_cell = make_cell(forecast_cutoff_at=datetime(2026, 2, 15, 16, 0, tzinfo=UTC))
    train_registry = _registry(
        catalog=InMemoryEvaluationInstanceCatalog(
            catalog_entries=(RegistryCatalogEntry(cell=train_cell, partition="TRAIN"),),
            bound_registry_identity_sha256="train-catalog-identity",
            catalog_source_kind=CatalogSourceKind.BOUND_FIXTURE,
        ),
    )
    assert train_registry.complete_season_intersects_test_partition(train_cell.season)
    assert len(train_registry.list_in_scope_cells()) == 1


def test_rejects_forbidden_variety_and_bason_factory_cells() -> None:
    forbidden_variety_cell = make_cell(variety="普鲜")
    forbidden_variety_catalog = InMemoryEvaluationInstanceCatalog(
        catalog_entries=(RegistryCatalogEntry(cell=forbidden_variety_cell, partition="TRAIN"),),
        bound_registry_identity_sha256="forbidden-variety-catalog-identity",
        catalog_source_kind=CatalogSourceKind.BOUND_FIXTURE,
    )
    assert _registry(catalog=forbidden_variety_catalog).list_in_scope_cells() == ()

    bason_cell = make_cell(farm="巴松加工厂")
    bason_catalog = InMemoryEvaluationInstanceCatalog(
        catalog_entries=(RegistryCatalogEntry(cell=bason_cell, partition="TRAIN"),),
        bound_registry_identity_sha256="bason-catalog-identity",
        catalog_source_kind=CatalogSourceKind.BOUND_FIXTURE,
    )
    assert _registry(catalog=bason_catalog).list_in_scope_cells() == ()


def test_dataset_identity_mismatch_fails_closed() -> None:
    bad_identity = DatasetIdentity(
        dataset_id="source-002",
        dataset_version="e5-live-v1",
        materialized_dataset_identity_sha256="0" * 64,
    )
    with pytest.raises(DatasetIdentityMismatchError):
        _registry(dataset_identity=bad_identity)


def test_grain_is_amendment_cell_grain_not_s2_harvest_grain() -> None:
    with pytest.raises(ForbiddenCatalogSourceError):
        _registry(
            catalog=InMemoryEvaluationInstanceCatalog(
                catalog_entries=(),
                bound_registry_identity_sha256=None,
                catalog_source_kind=CatalogSourceKind.S2_HARVEST_GRAIN,
            ),
        )

    cell = make_cell()
    assert isinstance(cell, EvaluationInstanceCell)
    assert cell.forecast_cutoff_at is not None
    assert cell.model_id
    assert cell.forecast_quantile
    assert complete_season_window_dates(cell.season)
