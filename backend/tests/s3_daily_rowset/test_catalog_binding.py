"""S3-A2 evaluation instance catalog binding contract tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from backend.app.s3_daily_rowset.binding import (
    BindingClassification,
    BindingReasonCode,
    BindingRequirementId,
    CatalogBindingCandidate,
    CatalogBindingLineage,
    EvaluationInstanceCatalogBindingService,
    expected_catalog_binding_lineage,
)
from backend.app.s3_daily_rowset.registry import (
    CatalogSourceKind,
    EvaluationInstanceCatalogPort,
    ForbiddenCatalogSourceError,
    InMemoryEvaluationInstanceCatalog,
    RegistryCatalogEntry,
)
from backend.app.s3_daily_rowset.schemas import (
    DatasetIdentity,
    PredicateStatus,
)
from backend.tests.s3_daily_rowset.conftest import (
    DATASET_IDENTITY,
    HORIZON_H7_SUCCESS_FIXTURE_HASH,
    make_cell,
)


def _lineage(**overrides: str) -> CatalogBindingLineage:
    base = expected_catalog_binding_lineage()
    return CatalogBindingLineage(
        actuals_authority=overrides.get("actuals_authority", base.actuals_authority),
        forecasts_authority=overrides.get("forecasts_authority", base.forecasts_authority),
        dataset_id=overrides.get("dataset_id", base.dataset_id),
        dataset_version=overrides.get("dataset_version", base.dataset_version),
        materialized_dataset_identity_sha256=overrides.get(
            "materialized_dataset_identity_sha256",
            base.materialized_dataset_identity_sha256,
        ),
    )


def _fixture_catalog(
    *,
    cutoff: datetime | None = None,
    partition: str = "TRAIN",
    identity: str = "fixture-catalog-identity-sha256-for-tests-only",
) -> InMemoryEvaluationInstanceCatalog:
    if cutoff is None:
        cutoff = datetime(2026, 2, 15, 16, 0, tzinfo=UTC)
    cell = make_cell(forecast_cutoff_at=cutoff)
    return InMemoryEvaluationInstanceCatalog(
        catalog_entries=(RegistryCatalogEntry(cell=cell, partition=partition),),
        bound_registry_identity_sha256=identity,
        catalog_source_kind=CatalogSourceKind.BOUND_FIXTURE,
    )


def _candidate(
    catalog: EvaluationInstanceCatalogPort,
    *,
    lineage: CatalogBindingLineage | None = None,
    claims_complete_season_dataset_pass: bool = False,
    uses_harvest_date_as_forecast_cutoff: bool = False,
) -> CatalogBindingCandidate:
    return CatalogBindingCandidate(
        catalog=catalog,
        lineage=lineage if lineage is not None else expected_catalog_binding_lineage(),
        claims_complete_season_dataset_pass=claims_complete_season_dataset_pass,
        uses_harvest_date_as_forecast_cutoff=uses_harvest_date_as_forecast_cutoff,
    )


def _service(
    *,
    candidate: CatalogBindingCandidate | None = None,
    dataset_identity: DatasetIdentity = DATASET_IDENTITY,
) -> EvaluationInstanceCatalogBindingService:
    return EvaluationInstanceCatalogBindingService(
        dataset_identity=dataset_identity,
        candidate=candidate,
    )


def _requirement_status(
    result: object,
    requirement_id: BindingRequirementId,
) -> PredicateStatus:
    binding_result = result
    assert hasattr(binding_result, "requirements")
    for requirement in binding_result.requirements:
        if requirement.requirement_id == requirement_id:
            return requirement.status
    raise AssertionError(f"missing requirement {requirement_id}")


@dataclass(frozen=True, slots=True)
class _ForbiddenSourceCatalog(EvaluationInstanceCatalogPort):
    source_kind_value: CatalogSourceKind

    def source_kind(self) -> CatalogSourceKind:
        return self.source_kind_value

    def identity_sha256(self) -> str | None:
        return "forbidden-source-catalog-identity-for-tests-only"

    def entries(self) -> tuple[RegistryCatalogEntry, ...]:
        return (
            RegistryCatalogEntry(
                cell=make_cell(forecast_cutoff_at=datetime(2026, 2, 15, 16, 0, tzinfo=UTC)),
                partition="TRAIN",
            ),
        )


@dataclass(frozen=True, slots=True)
class _H7IdentityCatalog(EvaluationInstanceCatalogPort):
    catalog_entries: tuple[RegistryCatalogEntry, ...]

    def source_kind(self) -> CatalogSourceKind:
        return CatalogSourceKind.BOUND_FIXTURE

    def identity_sha256(self) -> str | None:
        return HORIZON_H7_SUCCESS_FIXTURE_HASH

    def entries(self) -> tuple[RegistryCatalogEntry, ...]:
        return self.catalog_entries


@dataclass(frozen=True, slots=True)
class _MissingIdentityCatalog(EvaluationInstanceCatalogPort):
    catalog_entries: tuple[RegistryCatalogEntry, ...]

    def source_kind(self) -> CatalogSourceKind:
        return CatalogSourceKind.BOUND_FIXTURE

    def identity_sha256(self) -> str | None:
        return None

    def entries(self) -> tuple[RegistryCatalogEntry, ...]:
        return self.catalog_entries


def test_default_unbound_candidate_is_fail_closed() -> None:
    result = _service().validate()

    assert result.classification == BindingClassification.UNBOUND_CATALOG_NOT_BINDABLE
    assert result.in_memory_structural_acceptance is False
    assert result.evaluation_instance_registry_available is False
    assert result.current_s3_daily_rowset_completeness_verified is False
    assert result.no_bindable_catalog_in_repository is True
    assert result.registry_source_status == "NOT_MATERIALIZED_OR_NOT_BOUND"
    assert result.reason_code == BindingReasonCode.UNBOUND_CATALOG


def test_empty_catalog_is_empty_not_bindable() -> None:
    catalog = InMemoryEvaluationInstanceCatalog(
        catalog_entries=(),
        bound_registry_identity_sha256=None,
        catalog_source_kind=CatalogSourceKind.BOUND_FIXTURE,
    )
    result = _service(candidate=_candidate(catalog)).validate()

    assert result.classification == BindingClassification.EMPTY_CATALOG_NOT_BINDABLE
    assert result.in_memory_structural_acceptance is False
    assert result.evaluation_instance_registry_available is False
    assert result.current_s3_daily_rowset_completeness_verified is False
    assert result.reason_code == BindingReasonCode.EMPTY_CATALOG


def test_missing_lineage_fails_closed() -> None:
    catalog = _fixture_catalog()
    result = _service(
        candidate=CatalogBindingCandidate(
            catalog=catalog,
            lineage=None,
        ),
    ).validate()

    assert result.in_memory_structural_acceptance is False
    assert result.evaluation_instance_registry_available is False
    assert _requirement_status(result, BindingRequirementId.AUTHORITATIVE_SOURCE_LINEAGE) == (
        PredicateStatus.FAIL
    )


def test_missing_registry_identity_fails_closed() -> None:
    catalog = _MissingIdentityCatalog(
        catalog_entries=(
            RegistryCatalogEntry(
                cell=make_cell(forecast_cutoff_at=datetime(2026, 2, 15, 16, 0, tzinfo=UTC)),
                partition="TRAIN",
            ),
        ),
    )
    result = _service(candidate=_candidate(catalog)).validate()

    assert result.in_memory_structural_acceptance is False
    assert _requirement_status(result, BindingRequirementId.VERSIONED_REGISTRY_IDENTITY) == (
        PredicateStatus.FAIL
    )
    assert result.reason_code == BindingReasonCode.MISSING_REGISTRY_IDENTITY


def test_dataset_identity_mismatch_in_lineage_fails_closed() -> None:
    catalog = _fixture_catalog()
    bad_lineage = _lineage(materialized_dataset_identity_sha256="0" * 64)
    result = _service(candidate=_candidate(catalog, lineage=bad_lineage)).validate()

    assert result.in_memory_structural_acceptance is False
    assert _requirement_status(result, BindingRequirementId.AUTHORITATIVE_SOURCE_LINEAGE) == (
        PredicateStatus.FAIL
    )
    assert result.reason_code == BindingReasonCode.DATASET_IDENTITY_MISMATCH


def test_h7_fixture_hash_as_catalog_identity_is_forbidden_substitution() -> None:
    with pytest.raises(ForbiddenCatalogSourceError):
        _fixture_catalog(identity=HORIZON_H7_SUCCESS_FIXTURE_HASH)

    catalog = _H7IdentityCatalog(
        catalog_entries=(
            RegistryCatalogEntry(
                cell=make_cell(forecast_cutoff_at=datetime(2026, 2, 15, 16, 0, tzinfo=UTC)),
                partition="TRAIN",
            ),
        ),
    )
    result = _service(candidate=_candidate(catalog)).validate()

    assert result.classification == BindingClassification.FORBIDDEN_SUBSTITUTION
    assert result.in_memory_structural_acceptance is False
    assert result.reason_code == BindingReasonCode.FORBIDDEN_H7_FIXTURE_IDENTITY


@pytest.mark.parametrize(
    "source_kind",
    [
        CatalogSourceKind.S2_HARVEST_GRAIN,
        CatalogSourceKind.V0_2_S3_BINDING_ROWS,
        CatalogSourceKind.HANDWRITTEN_FARM_LIST,
        CatalogSourceKind.HANDWRITTEN_CUTOFF_LIST,
        CatalogSourceKind.FARM_PICK_DAY_ENUMERATION,
    ],
)
def test_forbidden_catalog_source_kinds_are_forbidden_substitution(
    source_kind: CatalogSourceKind,
) -> None:
    with pytest.raises(ForbiddenCatalogSourceError):
        InMemoryEvaluationInstanceCatalog(
            catalog_entries=(),
            bound_registry_identity_sha256=None,
            catalog_source_kind=source_kind,
        )

    catalog = _ForbiddenSourceCatalog(source_kind_value=source_kind)
    result = _service(candidate=_candidate(catalog)).validate()

    assert result.classification == BindingClassification.FORBIDDEN_SUBSTITUTION
    assert result.in_memory_structural_acceptance is False
    assert result.reason_code == BindingReasonCode.FORBIDDEN_CATALOG_SOURCE


def test_test_partition_cell_is_not_structurally_accepted() -> None:
    catalog = _fixture_catalog(
        cutoff=datetime(2026, 2, 28, 16, 0, tzinfo=UTC),
        partition="TEST",
        identity="test-partition-catalog-identity",
    )
    result = _service(candidate=_candidate(catalog)).validate()

    assert result.in_memory_structural_acceptance is False
    assert (
        _requirement_status(result, BindingRequirementId.PARTITION_LABELS) == PredicateStatus.FAIL
    )
    assert result.reason_code == BindingReasonCode.TEST_PARTITION_NOT_ALLOWED


def test_horizon_window_intersecting_test_partition_is_not_structurally_accepted() -> None:
    catalog = _fixture_catalog(
        cutoff=datetime(2026, 3, 9, 16, 0, tzinfo=UTC),
        partition="VALIDATION",
        identity="horizon-test-overlap-catalog-identity",
    )
    result = _service(candidate=_candidate(catalog)).validate()

    assert result.in_memory_structural_acceptance is False
    assert _requirement_status(result, BindingRequirementId.NON_EMPTY_IN_SCOPE_SET) == (
        PredicateStatus.FAIL
    )
    assert result.reason_code == BindingReasonCode.NO_IN_SCOPE_CELLS


def test_forbidden_variety_excluded_leaves_not_bindable() -> None:
    catalog = InMemoryEvaluationInstanceCatalog(
        catalog_entries=(RegistryCatalogEntry(cell=make_cell(variety="普鲜"), partition="TRAIN"),),
        bound_registry_identity_sha256="forbidden-variety-catalog-identity",
        catalog_source_kind=CatalogSourceKind.BOUND_FIXTURE,
    )
    result = _service(candidate=_candidate(catalog)).validate()

    assert result.classification == BindingClassification.NOT_BINDABLE
    assert result.in_memory_structural_acceptance is False
    assert result.reason_code == BindingReasonCode.NO_IN_SCOPE_CELLS


def test_forbidden_bason_factory_excluded_leaves_not_bindable() -> None:
    catalog = InMemoryEvaluationInstanceCatalog(
        catalog_entries=(
            RegistryCatalogEntry(cell=make_cell(farm="巴松加工厂"), partition="TRAIN"),
        ),
        bound_registry_identity_sha256="bason-catalog-identity",
        catalog_source_kind=CatalogSourceKind.BOUND_FIXTURE,
    )
    result = _service(candidate=_candidate(catalog)).validate()

    assert result.classification == BindingClassification.NOT_BINDABLE
    assert result.in_memory_structural_acceptance is False


def test_structurally_valid_fixture_is_accepted_in_memory_only() -> None:
    catalog = _fixture_catalog()
    result = _service(candidate=_candidate(catalog)).validate()

    assert result.classification == BindingClassification.FIXTURE_ONLY_CATALOG_NOT_BINDABLE
    assert result.in_memory_structural_acceptance is True
    assert result.evaluation_instance_registry_available is False
    assert result.current_s3_daily_rowset_completeness_verified is False
    assert result.no_bindable_catalog_in_repository is True
    assert result.registry_source_status == "NOT_MATERIALIZED_OR_NOT_BOUND"
    assert all(requirement.status == PredicateStatus.PASS for requirement in result.requirements)
    assert result.reason_code == BindingReasonCode.FIXTURE_ONLY_NOT_LIVE_BINDABLE


def test_complete_season_pass_claim_fails_closed() -> None:
    catalog = _fixture_catalog()
    result = _service(
        candidate=_candidate(catalog, claims_complete_season_dataset_pass=True),
    ).validate()

    assert result.classification == BindingClassification.FORBIDDEN_SUBSTITUTION
    assert result.in_memory_structural_acceptance is False
    assert result.reason_code == BindingReasonCode.COMPLETE_SEASON_PASS_CLAIM_FORBIDDEN


def test_harvest_date_as_cutoff_claim_fails_closed() -> None:
    catalog = _fixture_catalog()
    result = _service(
        candidate=_candidate(catalog, uses_harvest_date_as_forecast_cutoff=True),
    ).validate()

    assert result.classification == BindingClassification.FORBIDDEN_SUBSTITUTION
    assert result.in_memory_structural_acceptance is False
    assert result.reason_code == BindingReasonCode.HARVEST_DATE_AS_CUTOFF_FORBIDDEN
