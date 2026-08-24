"""S3-A2 evaluation instance catalog binding validation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from backend.app.s3_daily_rowset.registry import (
    FORBIDDEN_CATALOG_SOURCE_KINDS,
    HORIZON_H7_SUCCESS_FIXTURE_HASH,
    REGISTRY_SOURCE_STATUS_UNBOUND,
    V0_3_S3_ACTUALS_AUTHORITY,
    V0_3_S3_FORECASTS_AUTHORITY,
    CatalogSourceKind,
    EvaluationInstanceCatalogPort,
    EvaluationInstanceRegistryService,
    ForbiddenCatalogSourceError,
    UnboundEvaluationInstanceCatalog,
)
from backend.app.s3_daily_rowset.schemas import (
    EXPECTED_DATASET_ID,
    EXPECTED_DATASET_VERSION,
    EXPECTED_MATERIALIZED_DATASET_IDENTITY_SHA256,
    DatasetIdentity,
    PredicateStatus,
)


class BindingClassification(StrEnum):
    UNBOUND_CATALOG_NOT_BINDABLE = "UNBOUND_CATALOG_NOT_BINDABLE"
    EMPTY_CATALOG_NOT_BINDABLE = "EMPTY_CATALOG_NOT_BINDABLE"
    FIXTURE_ONLY_CATALOG_NOT_BINDABLE = "FIXTURE_ONLY_CATALOG_NOT_BINDABLE"
    FORBIDDEN_SUBSTITUTION = "FORBIDDEN_SUBSTITUTION"
    NOT_BINDABLE = "NOT_BINDABLE"


class BindingReasonCode(StrEnum):
    UNBOUND_CATALOG = "UNBOUND_CATALOG"
    EMPTY_CATALOG = "EMPTY_CATALOG"
    MISSING_REGISTRY_IDENTITY = "MISSING_REGISTRY_IDENTITY"
    DATASET_IDENTITY_MISMATCH = "DATASET_IDENTITY_MISMATCH"
    FORBIDDEN_CATALOG_SOURCE = "FORBIDDEN_CATALOG_SOURCE"
    FORBIDDEN_H7_FIXTURE_IDENTITY = "FORBIDDEN_H7_FIXTURE_IDENTITY"
    COMPLETE_SEASON_PASS_CLAIM_FORBIDDEN = "COMPLETE_SEASON_PASS_CLAIM_FORBIDDEN"
    HARVEST_DATE_AS_CUTOFF_FORBIDDEN = "HARVEST_DATE_AS_CUTOFF_FORBIDDEN"
    TEST_PARTITION_NOT_ALLOWED = "TEST_PARTITION_NOT_ALLOWED"
    NO_IN_SCOPE_CELLS = "NO_IN_SCOPE_CELLS"
    FIXTURE_ONLY_NOT_LIVE_BINDABLE = "FIXTURE_ONLY_NOT_LIVE_BINDABLE"
    NOT_BINDABLE = "NOT_BINDABLE"


class BindingRequirementId(StrEnum):
    VERSIONED_REGISTRY_IDENTITY = "VERSIONED_REGISTRY_IDENTITY"
    AUTHORITATIVE_SOURCE_LINEAGE = "AUTHORITATIVE_SOURCE_LINEAGE"
    EXPLICIT_CELL_ENUMERATION = "EXPLICIT_CELL_ENUMERATION"
    PARTITION_LABELS = "PARTITION_LABELS"
    NON_EMPTY_IN_SCOPE_SET = "NON_EMPTY_IN_SCOPE_SET"


BINDING_REQUIREMENT_IDS: tuple[BindingRequirementId, ...] = (
    BindingRequirementId.VERSIONED_REGISTRY_IDENTITY,
    BindingRequirementId.AUTHORITATIVE_SOURCE_LINEAGE,
    BindingRequirementId.EXPLICIT_CELL_ENUMERATION,
    BindingRequirementId.PARTITION_LABELS,
    BindingRequirementId.NON_EMPTY_IN_SCOPE_SET,
)


@dataclass(frozen=True, slots=True)
class BindingRequirementResult:
    requirement_id: BindingRequirementId
    status: PredicateStatus


@dataclass(frozen=True, slots=True)
class CatalogBindingLineage:
    actuals_authority: str
    forecasts_authority: str
    dataset_id: str
    dataset_version: str
    materialized_dataset_identity_sha256: str


@dataclass(frozen=True, slots=True)
class CatalogBindingCandidate:
    catalog: EvaluationInstanceCatalogPort
    lineage: CatalogBindingLineage | None = None
    claims_complete_season_dataset_pass: bool = False
    uses_harvest_date_as_forecast_cutoff: bool = False


@dataclass(frozen=True, slots=True)
class CatalogBindingResult:
    classification: BindingClassification
    in_memory_structural_acceptance: bool
    requirements: tuple[BindingRequirementResult, ...]
    reason_code: BindingReasonCode
    evaluation_instance_registry_available: bool = False
    current_s3_daily_rowset_completeness_verified: bool = False
    no_bindable_catalog_in_repository: bool = True
    registry_source_status: str = REGISTRY_SOURCE_STATUS_UNBOUND


def expected_catalog_binding_lineage() -> CatalogBindingLineage:
    return CatalogBindingLineage(
        actuals_authority=V0_3_S3_ACTUALS_AUTHORITY,
        forecasts_authority=V0_3_S3_FORECASTS_AUTHORITY,
        dataset_id=EXPECTED_DATASET_ID,
        dataset_version=EXPECTED_DATASET_VERSION,
        materialized_dataset_identity_sha256=EXPECTED_MATERIALIZED_DATASET_IDENTITY_SHA256,
    )


def _fail_all_requirements() -> tuple[BindingRequirementResult, ...]:
    return tuple(
        BindingRequirementResult(requirement_id=requirement_id, status=PredicateStatus.FAIL)
        for requirement_id in BINDING_REQUIREMENT_IDS
    )


def _build_result(
    *,
    classification: BindingClassification,
    in_memory_structural_acceptance: bool,
    requirements: tuple[BindingRequirementResult, ...],
    reason_code: BindingReasonCode,
) -> CatalogBindingResult:
    return CatalogBindingResult(
        classification=classification,
        in_memory_structural_acceptance=in_memory_structural_acceptance,
        requirements=requirements,
        reason_code=reason_code,
    )


def _lineage_matches(lineage: CatalogBindingLineage | None) -> bool:
    if lineage is None:
        return False
    expected = expected_catalog_binding_lineage()
    return (
        lineage.actuals_authority == expected.actuals_authority
        and lineage.forecasts_authority == expected.forecasts_authority
        and lineage.dataset_id == expected.dataset_id
        and lineage.dataset_version == expected.dataset_version
        and lineage.materialized_dataset_identity_sha256
        == expected.materialized_dataset_identity_sha256
    )


@dataclass
class EvaluationInstanceCatalogBindingService:
    dataset_identity: DatasetIdentity
    candidate: CatalogBindingCandidate | None = None

    def validate(self) -> CatalogBindingResult:
        if self.candidate is None:
            return _build_result(
                classification=BindingClassification.UNBOUND_CATALOG_NOT_BINDABLE,
                in_memory_structural_acceptance=False,
                requirements=_fail_all_requirements(),
                reason_code=BindingReasonCode.UNBOUND_CATALOG,
            )

        catalog = self.candidate.catalog
        source_kind = catalog.source_kind()

        if self.candidate.claims_complete_season_dataset_pass:
            return _build_result(
                classification=BindingClassification.FORBIDDEN_SUBSTITUTION,
                in_memory_structural_acceptance=False,
                requirements=_fail_all_requirements(),
                reason_code=BindingReasonCode.COMPLETE_SEASON_PASS_CLAIM_FORBIDDEN,
            )

        if self.candidate.uses_harvest_date_as_forecast_cutoff:
            return _build_result(
                classification=BindingClassification.FORBIDDEN_SUBSTITUTION,
                in_memory_structural_acceptance=False,
                requirements=_fail_all_requirements(),
                reason_code=BindingReasonCode.HARVEST_DATE_AS_CUTOFF_FORBIDDEN,
            )

        if source_kind in FORBIDDEN_CATALOG_SOURCE_KINDS:
            return _build_result(
                classification=BindingClassification.FORBIDDEN_SUBSTITUTION,
                in_memory_structural_acceptance=False,
                requirements=_fail_all_requirements(),
                reason_code=BindingReasonCode.FORBIDDEN_CATALOG_SOURCE,
            )

        if source_kind == CatalogSourceKind.UNBOUND:
            return _build_result(
                classification=BindingClassification.UNBOUND_CATALOG_NOT_BINDABLE,
                in_memory_structural_acceptance=False,
                requirements=_fail_all_requirements(),
                reason_code=BindingReasonCode.UNBOUND_CATALOG,
            )

        registry_identity = catalog.identity_sha256()
        if registry_identity == HORIZON_H7_SUCCESS_FIXTURE_HASH:
            return _build_result(
                classification=BindingClassification.FORBIDDEN_SUBSTITUTION,
                in_memory_structural_acceptance=False,
                requirements=_fail_all_requirements(),
                reason_code=BindingReasonCode.FORBIDDEN_H7_FIXTURE_IDENTITY,
            )

        entries = catalog.entries()
        if not entries:
            return _build_result(
                classification=BindingClassification.EMPTY_CATALOG_NOT_BINDABLE,
                in_memory_structural_acceptance=False,
                requirements=_fail_all_requirements(),
                reason_code=BindingReasonCode.EMPTY_CATALOG,
            )

        requirement_1 = PredicateStatus.PASS if registry_identity else PredicateStatus.FAIL
        requirement_2 = (
            PredicateStatus.PASS
            if _lineage_matches(self.candidate.lineage)
            else PredicateStatus.FAIL
        )
        requirement_3 = PredicateStatus.PASS
        requirement_4 = (
            PredicateStatus.PASS
            if all(entry.partition in {"TRAIN", "VALIDATION"} for entry in entries)
            else PredicateStatus.FAIL
        )

        if any(entry.partition == "TEST" for entry in entries):
            requirements = (
                BindingRequirementResult(
                    requirement_id=BindingRequirementId.VERSIONED_REGISTRY_IDENTITY,
                    status=requirement_1,
                ),
                BindingRequirementResult(
                    requirement_id=BindingRequirementId.AUTHORITATIVE_SOURCE_LINEAGE,
                    status=requirement_2,
                ),
                BindingRequirementResult(
                    requirement_id=BindingRequirementId.EXPLICIT_CELL_ENUMERATION,
                    status=requirement_3,
                ),
                BindingRequirementResult(
                    requirement_id=BindingRequirementId.PARTITION_LABELS,
                    status=PredicateStatus.FAIL,
                ),
                BindingRequirementResult(
                    requirement_id=BindingRequirementId.NON_EMPTY_IN_SCOPE_SET,
                    status=PredicateStatus.FAIL,
                ),
            )
            return _build_result(
                classification=BindingClassification.NOT_BINDABLE,
                in_memory_structural_acceptance=False,
                requirements=requirements,
                reason_code=BindingReasonCode.TEST_PARTITION_NOT_ALLOWED,
            )

        try:
            registry = EvaluationInstanceRegistryService(
                dataset_identity=self.dataset_identity,
                catalog=catalog,
            )
        except ForbiddenCatalogSourceError:
            return _build_result(
                classification=BindingClassification.FORBIDDEN_SUBSTITUTION,
                in_memory_structural_acceptance=False,
                requirements=_fail_all_requirements(),
                reason_code=BindingReasonCode.FORBIDDEN_CATALOG_SOURCE,
            )

        in_scope_cells = registry.list_in_scope_cells()
        requirement_5 = PredicateStatus.PASS if in_scope_cells else PredicateStatus.FAIL

        requirements = (
            BindingRequirementResult(
                requirement_id=BindingRequirementId.VERSIONED_REGISTRY_IDENTITY,
                status=requirement_1,
            ),
            BindingRequirementResult(
                requirement_id=BindingRequirementId.AUTHORITATIVE_SOURCE_LINEAGE,
                status=requirement_2,
            ),
            BindingRequirementResult(
                requirement_id=BindingRequirementId.EXPLICIT_CELL_ENUMERATION,
                status=requirement_3,
            ),
            BindingRequirementResult(
                requirement_id=BindingRequirementId.PARTITION_LABELS,
                status=requirement_4,
            ),
            BindingRequirementResult(
                requirement_id=BindingRequirementId.NON_EMPTY_IN_SCOPE_SET,
                status=requirement_5,
            ),
        )

        all_pass = all(requirement.status == PredicateStatus.PASS for requirement in requirements)

        if not all_pass:
            reason_code = BindingReasonCode.NO_IN_SCOPE_CELLS
            if requirement_1 == PredicateStatus.FAIL:
                reason_code = BindingReasonCode.MISSING_REGISTRY_IDENTITY
            elif requirement_2 == PredicateStatus.FAIL:
                reason_code = BindingReasonCode.DATASET_IDENTITY_MISMATCH
            return _build_result(
                classification=BindingClassification.NOT_BINDABLE,
                in_memory_structural_acceptance=False,
                requirements=requirements,
                reason_code=reason_code,
            )

        if source_kind == CatalogSourceKind.BOUND_FIXTURE:
            return _build_result(
                classification=BindingClassification.FIXTURE_ONLY_CATALOG_NOT_BINDABLE,
                in_memory_structural_acceptance=True,
                requirements=requirements,
                reason_code=BindingReasonCode.FIXTURE_ONLY_NOT_LIVE_BINDABLE,
            )

        return _build_result(
            classification=BindingClassification.NOT_BINDABLE,
            in_memory_structural_acceptance=True,
            requirements=requirements,
            reason_code=BindingReasonCode.NOT_BINDABLE,
        )

    def default_catalog(self) -> EvaluationInstanceCatalogPort:
        if self.candidate is None:
            return UnboundEvaluationInstanceCatalog()
        return self.candidate.catalog
