"""S3-A2 evaluation instance catalog artifact production tests."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import pytest

from backend.app.s3_daily_rowset.binding import (
    BindingClassification,
    BindingReasonCode,
)
from backend.app.s3_daily_rowset.catalog_artifact import (
    CatalogArtifactReasonCode,
    EmptyS2IdentityAlignmentPort,
    EvaluationInstanceCatalogArtifactProductionService,
    IncumbentForecastArtifactEntry,
    MissingIncumbentForecastArtifactPort,
    S2AlignedIdentity,
    compute_catalog_identity_sha256,
)
from backend.app.s3_daily_rowset.registry import (
    HORIZON_H7_SUCCESS_FIXTURE_HASH,
    CatalogSourceKind,
    UnboundEvaluationInstanceCatalog,
)
from backend.app.s3_daily_rowset.schemas import DatasetIdentity
from backend.tests.s3_daily_rowset.conftest import DATASET_IDENTITY


@dataclass(frozen=True, slots=True)
class FakeIncumbentForecastArtifactPort:
    entries_value: tuple[IncumbentForecastArtifactEntry, ...]
    catalog_source_kind_value: CatalogSourceKind = CatalogSourceKind.BOUND_FIXTURE
    uses_harvest_date_as_forecast_cutoff_value: bool = False

    def has_versioned_artifact(self) -> bool:
        return bool(self.entries_value)

    def catalog_source_kind(self) -> CatalogSourceKind:
        return self.catalog_source_kind_value

    def entries(self) -> tuple[IncumbentForecastArtifactEntry, ...]:
        return self.entries_value

    def uses_harvest_date_as_forecast_cutoff(self) -> bool:
        return self.uses_harvest_date_as_forecast_cutoff_value


@dataclass(frozen=True, slots=True)
class FakeS2IdentityAlignmentPort:
    identities: tuple[S2AlignedIdentity, ...]
    alignment_source_kind_value: CatalogSourceKind = CatalogSourceKind.BOUND_FIXTURE

    def alignment_source_kind(self) -> CatalogSourceKind:
        return self.alignment_source_kind_value

    def aligned_identities(self) -> tuple[S2AlignedIdentity, ...]:
        return self.identities


def _forecast_entry(
    *,
    cutoff: datetime | None = None,
    model_id: str = "incumbent-v0.2",
    quantile: str = "P50",
) -> IncumbentForecastArtifactEntry:
    if cutoff is None:
        cutoff = datetime(2026, 2, 15, 16, 0, tzinfo=UTC)
    return IncumbentForecastArtifactEntry(
        model_id=model_id,
        forecast_cutoff_at=cutoff,
        forecast_quantile=quantile,
    )


def _aligned_identity(
    *,
    season: str = "2025~2026",
    farm: str = "farm-a",
    subfarm: str = "subfarm-1",
    variety: str = "variety-x",
    partition: Literal["TRAIN", "VALIDATION"] = "TRAIN",
) -> S2AlignedIdentity:
    return S2AlignedIdentity(
        season=season,
        farm=farm,
        subfarm=subfarm,
        variety=variety,
        partition=partition,
    )


def _service(
    *,
    dataset_identity: DatasetIdentity = DATASET_IDENTITY,
    forecast_port: object | None = None,
    alignment_port: object | None = None,
) -> EvaluationInstanceCatalogArtifactProductionService:
    return EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=dataset_identity,
        forecast_port=forecast_port or MissingIncumbentForecastArtifactPort(),
        alignment_port=alignment_port or EmptyS2IdentityAlignmentPort(),
    )


def test_default_construction_without_incumbent_artifact_is_fail_closed() -> None:
    result = _service().produce()

    assert result.reason_code == CatalogArtifactReasonCode.NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
    assert isinstance(result.catalog, UnboundEvaluationInstanceCatalog)
    assert result.catalog_identity_sha256 is None
    assert result.evaluation_instance_registry_available is False
    assert result.current_s3_daily_rowset_completeness_verified is False
    assert result.no_bindable_catalog_in_repository is True
    assert result.registry_source_status == "NOT_MATERIALIZED_OR_NOT_BOUND"
    assert result.binding_result is not None
    assert (
        result.binding_result.classification == BindingClassification.UNBOUND_CATALOG_NOT_BINDABLE
    )
    assert result.binding_result.reason_code == BindingReasonCode.UNBOUND_CATALOG


def test_catalog_identity_must_not_equal_h7_fixture_hash() -> None:
    forecast_port = FakeIncumbentForecastArtifactPort(
        entries_value=(_forecast_entry(),),
    )
    alignment_port = FakeS2IdentityAlignmentPort(
        identities=(_aligned_identity(),),
    )
    result = _service(forecast_port=forecast_port, alignment_port=alignment_port).produce()

    assert result.catalog_identity_sha256 is not None
    assert result.catalog_identity_sha256 != HORIZON_H7_SUCCESS_FIXTURE_HASH


@pytest.mark.parametrize(
    "source_kind",
    [
        CatalogSourceKind.S2_HARVEST_GRAIN,
        CatalogSourceKind.V0_2_S3_BINDING_ROWS,
        CatalogSourceKind.HANDWRITTEN_CUTOFF_LIST,
        CatalogSourceKind.FARM_PICK_DAY_ENUMERATION,
    ],
)
def test_forbidden_forecast_sources_are_rejected(source_kind: CatalogSourceKind) -> None:
    forecast_port = FakeIncumbentForecastArtifactPort(
        entries_value=(_forecast_entry(),),
        catalog_source_kind_value=source_kind,
    )
    alignment_port = FakeS2IdentityAlignmentPort(
        identities=(_aligned_identity(),),
    )
    result = _service(forecast_port=forecast_port, alignment_port=alignment_port).produce()

    assert result.reason_code == CatalogArtifactReasonCode.FORBIDDEN_CATALOG_SOURCE
    assert isinstance(result.catalog, UnboundEvaluationInstanceCatalog)
    assert result.catalog_identity_sha256 is None
    assert result.no_bindable_catalog_in_repository is True


def test_handwritten_farm_list_alignment_source_is_rejected() -> None:
    forecast_port = FakeIncumbentForecastArtifactPort(
        entries_value=(_forecast_entry(),),
    )
    alignment_port = FakeS2IdentityAlignmentPort(
        identities=(_aligned_identity(),),
        alignment_source_kind_value=CatalogSourceKind.HANDWRITTEN_FARM_LIST,
    )
    result = _service(forecast_port=forecast_port, alignment_port=alignment_port).produce()

    assert result.reason_code == CatalogArtifactReasonCode.FORBIDDEN_CATALOG_SOURCE
    assert isinstance(result.catalog, UnboundEvaluationInstanceCatalog)
    assert result.catalog_identity_sha256 is None


def test_harvest_business_date_must_not_be_used_as_forecast_cutoff() -> None:
    forecast_port = FakeIncumbentForecastArtifactPort(
        entries_value=(_forecast_entry(cutoff=datetime(2026, 3, 1, 0, 0, tzinfo=UTC)),),
        uses_harvest_date_as_forecast_cutoff_value=True,
    )
    alignment_port = FakeS2IdentityAlignmentPort(
        identities=(_aligned_identity(),),
    )
    result = _service(forecast_port=forecast_port, alignment_port=alignment_port).produce()

    assert result.reason_code == CatalogArtifactReasonCode.HARVEST_DATE_AS_CUTOFF_FORBIDDEN
    assert isinstance(result.catalog, UnboundEvaluationInstanceCatalog)
    assert result.catalog_identity_sha256 is None


def test_test_intersecting_window_cells_do_not_become_bindable() -> None:
    forecast_port = FakeIncumbentForecastArtifactPort(
        entries_value=(_forecast_entry(cutoff=datetime(2026, 3, 9, 16, 0, tzinfo=UTC)),),
    )
    alignment_port = FakeS2IdentityAlignmentPort(
        identities=(_aligned_identity(partition="VALIDATION"),),
    )
    result = _service(forecast_port=forecast_port, alignment_port=alignment_port).produce()

    assert result.binding_result is not None
    assert result.binding_result.in_memory_structural_acceptance is False
    assert result.binding_result.reason_code == BindingReasonCode.NO_IN_SCOPE_CELLS
    assert result.evaluation_instance_registry_available is False
    assert result.no_bindable_catalog_in_repository is True


@pytest.mark.parametrize(
    ("farm", "variety"),
    [
        ("farm-a", "普鲜"),
        ("farm-a", "普青"),
        ("farm-a", "普冻"),
        ("farm-a", "废果"),
        ("巴松加工厂", "variety-x"),
    ],
)
def test_a2_exclusions_leave_catalog_not_bindable(farm: str, variety: str) -> None:
    forecast_port = FakeIncumbentForecastArtifactPort(
        entries_value=(_forecast_entry(),),
    )
    alignment_port = FakeS2IdentityAlignmentPort(
        identities=(_aligned_identity(farm=farm, variety=variety),),
    )
    result = _service(forecast_port=forecast_port, alignment_port=alignment_port).produce()

    assert result.binding_result is not None
    assert result.binding_result.classification in {
        BindingClassification.NOT_BINDABLE,
        BindingClassification.FIXTURE_ONLY_CATALOG_NOT_BINDABLE,
    }
    assert result.binding_result.in_memory_structural_acceptance is False
    assert result.no_bindable_catalog_in_repository is True


def test_excluded_only_catalog_is_not_bindable() -> None:
    forecast_port = FakeIncumbentForecastArtifactPort(
        entries_value=(_forecast_entry(),),
    )
    alignment_port = FakeS2IdentityAlignmentPort(
        identities=(_aligned_identity(variety="普鲜"),),
    )
    result = _service(forecast_port=forecast_port, alignment_port=alignment_port).produce()

    assert result.binding_result is not None
    assert result.binding_result.in_memory_structural_acceptance is False
    assert result.no_bindable_catalog_in_repository is True
    assert result.evaluation_instance_registry_available is False


def test_complete_season_is_not_treated_as_dataset_pass() -> None:
    result = _service().produce()

    assert result.current_s3_daily_rowset_completeness_verified is False
    if result.binding_result is not None:
        assert result.binding_result.current_s3_daily_rowset_completeness_verified is False


def test_injected_forecast_and_alignment_produces_deterministic_fixture_catalog() -> None:
    forecast_port = FakeIncumbentForecastArtifactPort(
        entries_value=(_forecast_entry(),),
    )
    alignment_port = FakeS2IdentityAlignmentPort(
        identities=(_aligned_identity(),),
    )
    service = _service(forecast_port=forecast_port, alignment_port=alignment_port)
    first = service.produce()
    second = service.produce()

    assert first.reason_code == CatalogArtifactReasonCode.ARTIFACT_PRODUCED
    assert first.catalog_identity_sha256 is not None
    assert first.catalog_identity_sha256 == second.catalog_identity_sha256
    assert first.catalog_identity_sha256 != HORIZON_H7_SUCCESS_FIXTURE_HASH
    assert first.binding_result is not None
    assert (
        first.binding_result.classification
        == BindingClassification.FIXTURE_ONLY_CATALOG_NOT_BINDABLE
    )
    assert first.binding_result.in_memory_structural_acceptance is True
    assert first.evaluation_instance_registry_available is False
    assert first.current_s3_daily_rowset_completeness_verified is False
    assert first.no_bindable_catalog_in_repository is True
    assert first.registry_source_status == "NOT_MATERIALIZED_OR_NOT_BOUND"
    assert len(first.catalog.entries()) == 1
    entry = first.catalog.entries()[0]
    assert entry.partition == "TRAIN"
    assert entry.cell.model_id == "incumbent-v0.2"
    assert entry.cell.forecast_quantile == "P50"


def test_forecast_without_alignment_is_fail_closed() -> None:
    forecast_port = FakeIncumbentForecastArtifactPort(
        entries_value=(_forecast_entry(),),
    )
    result = _service(forecast_port=forecast_port).produce()

    assert result.reason_code == CatalogArtifactReasonCode.NO_S2_IDENTITY_ALIGNMENT
    assert isinstance(result.catalog, UnboundEvaluationInstanceCatalog)
    assert result.catalog_identity_sha256 is None
    assert result.no_bindable_catalog_in_repository is True


def test_dataset_identity_mismatch_is_fail_closed() -> None:
    bad_identity = DatasetIdentity(
        dataset_id="source-002",
        dataset_version="e5-live-v1",
        materialized_dataset_identity_sha256="0" * 64,
    )
    forecast_port = FakeIncumbentForecastArtifactPort(
        entries_value=(_forecast_entry(),),
    )
    alignment_port = FakeS2IdentityAlignmentPort(
        identities=(_aligned_identity(),),
    )
    result = _service(
        dataset_identity=bad_identity,
        forecast_port=forecast_port,
        alignment_port=alignment_port,
    ).produce()

    assert result.reason_code == CatalogArtifactReasonCode.DATASET_IDENTITY_MISMATCH
    assert isinstance(result.catalog, UnboundEvaluationInstanceCatalog)
    assert result.catalog_identity_sha256 is None


def test_production_module_does_not_scan_repository_or_read_source_002_rows() -> None:
    module_path = Path("backend/app/s3_daily_rowset/catalog_artifact.py")
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden_calls = {
        "walk",
        "glob",
        "rglob",
        "read_text",
        "open",
        "listdir",
        "scandir",
    }
    forbidden_modules = {
        "pathlib.Path",
        "os",
        "glob",
        "sqlalchemy",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in {"os", "glob", "pathlib"}
        if isinstance(node, ast.ImportFrom):
            assert node.module not in forbidden_modules
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in forbidden_calls:
                raise AssertionError(f"forbidden call detected: {func.attr}")
            if isinstance(func, ast.Name) and func.id == "open":
                raise AssertionError("forbidden open() call detected")

    assert "SOURCE_002" not in source
    assert "MaterializableRow" not in source
    assert compute_catalog_identity_sha256 is not None
