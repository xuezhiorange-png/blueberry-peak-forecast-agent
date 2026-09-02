"""Authority-layer live-bindability and registry AVAILABLE classifier.

Consumes bare-default catalog production, frozen binding, and committed
versioned authority-package artifacts. Does not modify frozen binding.py or
registry.py, invent tonnes, or leave session providers installed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

from backend.app.rolling_backtest.canonical import sha256_payload
from backend.app.s3_daily_rowset.binding import (
    BINDING_REQUIREMENT_IDS,
    BindingClassification,
    BindingReasonCode,
    CatalogBindingResult,
)
from backend.app.s3_daily_rowset.catalog_artifact import (
    CatalogArtifactReasonCode,
    EvaluationInstanceCatalogArtifactProductionService,
)
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_live_postgres_read import (
    clear_v0_2_live_postgres_session_provider,
)
from backend.app.s3_daily_rowset.registry import (
    REGISTRY_SOURCE_STATUS_UNBOUND,
    V0_3_S3_ACTUALS_AUTHORITY,
    V0_3_S3_FORECASTS_AUTHORITY,
    CatalogSourceKind,
    EvaluationInstanceCatalogPort,
    EvaluationInstanceRegistryService,
    RegistryCatalogEntry,
)
from backend.app.s3_daily_rowset.schemas import (
    EXPECTED_DATASET_ID,
    EXPECTED_DATASET_VERSION,
    EXPECTED_MATERIALIZED_DATASET_IDENTITY_SHA256,
    DatasetIdentity,
    PredicateStatus,
)

REVIEWER_ROLE: Final[str] = "COORDINATOR"
ACTUALS_AUTHORITY: Final[str] = "V0_3_S2_SOURCE_002_E5_LIVE_V1_TRAIN_AND_VALIDATION"
FORECASTS_AUTHORITY: Final[str] = "V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF"
DECLARED_CATALOG_SOURCE_KIND: Final[str] = "V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF"
PINNED_CATALOG_IDENTITY_SHA256: Final[str] = (
    "00f6bc532dfd97f2d625fc1347bf2a7663299fda206bd472df4c2c32c54ab5af"
)
PINNED_CATALOG_ENTRY_COUNT: Final[int] = 2427
REVIEW_EVIDENCE_DIGEST_SHA256: Final[str] = (
    "40e03141b52188cafe9e9cb6842d14f2ebd6caa3abe1fd80142ad71162781f64"
)
REGISTRY_SOURCE_STATUS_BOUND_V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF: Final[str] = (
    "BOUND_V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF"
)
LIVE_BINDABLE_AUTHORITY_PACKAGE_VERSION: Final[str] = (
    "s3-a2-default-catalog-live-bindable-authority-package-v1"
)
REGISTRY_AVAILABLE_CLOSEOUT_PACKAGE_VERSION: Final[str] = (
    "s3-a2-default-catalog-registry-available-closeout-package-v1"
)
AUTHORITY_PACKAGE_ARTIFACT_PATH: Final[Path] = Path(
    "backend/app/s3_daily_rowset/authority_packages/"
    "default_catalog_live_bindable_authority_package_v1.json"
)
REGISTRY_AVAILABLE_CLOSEOUT_PACKAGE_ARTIFACT_PATH: Final[Path] = Path(
    "backend/app/s3_daily_rowset/authority_packages/"
    "default_catalog_registry_available_closeout_package_v1.json"
)
PARENT_CONTRACT_EVIDENCE_JSON_SHA256: Final[str] = (
    "d81f0d3f8b4f9fb42496ac0186f91dac6e1164c3b08b765bf445393dd10a8c2c"
)
PARENT_GRANT_EVIDENCE_JSON_SHA256: Final[str] = (
    "5e3a5413a8d29663cd6688237d0accac802235723902fa9b4caed4b3153ac6eb"
)
DEFAULT_DATASET_IDENTITY = DatasetIdentity(
    dataset_id=EXPECTED_DATASET_ID,
    dataset_version=EXPECTED_DATASET_VERSION,
    materialized_dataset_identity_sha256=EXPECTED_MATERIALIZED_DATASET_IDENTITY_SHA256,
)
ALLOWED_CATALOG_PARTITIONS: Final[frozenset[str]] = frozenset({"TRAIN", "VALIDATION"})


class AuthorityClassification(StrEnum):
    NOT_CLASSIFIED = "NOT_CLASSIFIED"
    LIVE_BINDABLE = "LIVE_BINDABLE"


class AuthorityReasonCode(StrEnum):
    CATALOG_NOT_PRODUCED = "CATALOG_NOT_PRODUCED"
    CATALOG_PINS_MISMATCH = "CATALOG_PINS_MISMATCH"
    FROZEN_BINDING_PRECONDITIONS_NOT_MET = "FROZEN_BINDING_PRECONDITIONS_NOT_MET"
    AUTHORITY_PACKAGE_NOT_VALID = "AUTHORITY_PACKAGE_NOT_VALID"
    REGISTRY_AUTHORITY_NOT_BOUND = "REGISTRY_AUTHORITY_NOT_BOUND"
    AVAILABLE_CLOSEOUT_PACKAGE_NOT_VALID = "AVAILABLE_CLOSEOUT_PACKAGE_NOT_VALID"
    LIVE_BINDABLE_CATALOG = "LIVE_BINDABLE_CATALOG"


@dataclass(frozen=True, slots=True)
class DefaultCatalogLiveBindableAuthorityPackage:
    package_kind: str
    artifact_or_package_version: str
    catalog_identity_sha256: str
    catalog_entry_count: int
    dataset_identity: DatasetIdentity
    actuals_authority: str
    forecasts_authority: str
    catalog_source_kind: str
    reviewer_role: str
    train_and_validation_only_rule: bool
    test_sealed_rule: bool
    harvest_date_not_forecast_cutoff_rule: bool
    reviewed_grain_identity_set_identity_sha256: str
    content_identity_sha256: str
    coordinator_review_evidence_digest_sha256: str
    parent_contract_evidence_json_sha256: str
    parent_grant_evidence_json_sha256: str
    authority_evidence_digest_sha256: str


@dataclass(frozen=True, slots=True)
class DefaultCatalogRegistryAvailableCloseoutPackage:
    package_kind: str
    artifact_or_package_version: str
    catalog_identity_sha256: str
    catalog_entry_count: int
    registry_snapshot_identity_sha256: str
    authority_evidence_digest_sha256: str
    authorized_live_bindable_classification_required: bool
    authority_classification_success: str
    authority_reason_code_success: str
    registry_source_status_success: str
    reviewer_role: str
    train_and_validation_only_rule: bool
    test_sealed_rule: bool
    parent_contract_evidence_json_sha256: str
    parent_grant_evidence_json_sha256: str
    registry_available_closeout_evidence_digest_sha256: str


@dataclass(frozen=True, slots=True)
class LiveBindabilityAndRegistryAvailabilityClassificationResult:
    reason_code: AuthorityReasonCode
    catalog_produced: bool
    catalog_identity_sha256: str | None
    catalog_entry_count: int
    catalog_source_kind: str | None
    binding_classification: BindingClassification | None
    binding_reason_code: BindingReasonCode | None
    in_memory_structural_acceptance: bool
    frozen_binding_classifies_live_bindable: bool
    authority_classification: AuthorityClassification
    authorized_live_bindable_classification: bool
    authority_package_version: str | None
    authority_evidence_digest_sha256: str | None
    registry_available_closeout_package_version: str | None
    registry_available_closeout_evidence_digest_sha256: str | None
    registry_source_status: str
    registry_snapshot_identity_sha256: str | None
    registry_snapshot_identity_matches_bound_catalog_identity: bool
    coordinator_reviewed_available_closeout_exists: bool
    no_bindable_catalog_in_repository: bool
    evaluation_instance_registry_available: bool
    no_versioned_incumbent_forecast_artifact_in_repository: bool
    current_s3_daily_rowset_completeness_verified: bool
    live_bindability_implemented: bool
    registry_availability_implemented: bool
    unique_remaining_gap_closed: bool


def _require_json_int(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{key} must be a JSON integer")
    return value


def hashable_versioned_authority_package_payload(payload: dict[str, object]) -> dict[str, object]:
    return {
        key: value for key, value in payload.items() if key != "authority_evidence_digest_sha256"
    }


def hashable_versioned_closeout_package_payload(payload: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in payload.items()
        if key != "registry_available_closeout_evidence_digest_sha256"
    }


def compute_versioned_authority_package_evidence_digest_sha256(
    payload: dict[str, object],
) -> str:
    return sha256_payload(hashable_versioned_authority_package_payload(payload))


def compute_versioned_closeout_package_evidence_digest_sha256(
    payload: dict[str, object],
) -> str:
    return sha256_payload(hashable_versioned_closeout_package_payload(payload))


def authority_package_self_digest_valid(
    package: DefaultCatalogLiveBindableAuthorityPackage,
) -> bool:
    payload = _authority_package_to_payload(package)
    return package.authority_evidence_digest_sha256 == (
        compute_versioned_authority_package_evidence_digest_sha256(payload)
    )


def closeout_package_self_digest_valid(
    package: DefaultCatalogRegistryAvailableCloseoutPackage,
) -> bool:
    payload = _closeout_package_to_payload(package)
    return package.registry_available_closeout_evidence_digest_sha256 == (
        compute_versioned_closeout_package_evidence_digest_sha256(payload)
    )


def _authority_package_to_payload(
    package: DefaultCatalogLiveBindableAuthorityPackage,
) -> dict[str, object]:
    return {
        "package_kind": package.package_kind,
        "artifact_or_package_version": package.artifact_or_package_version,
        "catalog_identity_sha256": package.catalog_identity_sha256,
        "catalog_entry_count": package.catalog_entry_count,
        "dataset_identity": package.dataset_identity.model_dump(),
        "actuals_authority": package.actuals_authority,
        "forecasts_authority": package.forecasts_authority,
        "catalog_source_kind": package.catalog_source_kind,
        "reviewer_role": package.reviewer_role,
        "train_and_validation_only_rule": package.train_and_validation_only_rule,
        "test_sealed_rule": package.test_sealed_rule,
        "harvest_date_not_forecast_cutoff_rule": package.harvest_date_not_forecast_cutoff_rule,
        "reviewed_grain_identity_set_identity_sha256": (
            package.reviewed_grain_identity_set_identity_sha256
        ),
        "content_identity_sha256": package.content_identity_sha256,
        "coordinator_review_evidence_digest_sha256": (
            package.coordinator_review_evidence_digest_sha256
        ),
        "parent_contract_evidence_json_sha256": package.parent_contract_evidence_json_sha256,
        "parent_grant_evidence_json_sha256": package.parent_grant_evidence_json_sha256,
        "authority_evidence_digest_sha256": package.authority_evidence_digest_sha256,
    }


def _closeout_package_to_payload(
    package: DefaultCatalogRegistryAvailableCloseoutPackage,
) -> dict[str, object]:
    return {
        "package_kind": package.package_kind,
        "artifact_or_package_version": package.artifact_or_package_version,
        "catalog_identity_sha256": package.catalog_identity_sha256,
        "catalog_entry_count": package.catalog_entry_count,
        "registry_snapshot_identity_sha256": package.registry_snapshot_identity_sha256,
        "authority_evidence_digest_sha256": package.authority_evidence_digest_sha256,
        "authorized_live_bindable_classification_required": (
            package.authorized_live_bindable_classification_required
        ),
        "authority_classification_success": package.authority_classification_success,
        "authority_reason_code_success": package.authority_reason_code_success,
        "registry_source_status_success": package.registry_source_status_success,
        "reviewer_role": package.reviewer_role,
        "train_and_validation_only_rule": package.train_and_validation_only_rule,
        "test_sealed_rule": package.test_sealed_rule,
        "parent_contract_evidence_json_sha256": package.parent_contract_evidence_json_sha256,
        "parent_grant_evidence_json_sha256": package.parent_grant_evidence_json_sha256,
        "registry_available_closeout_evidence_digest_sha256": (
            package.registry_available_closeout_evidence_digest_sha256
        ),
    }


def _parse_authority_package(
    payload: dict[str, object],
) -> DefaultCatalogLiveBindableAuthorityPackage:
    dataset_identity = DatasetIdentity.model_validate(payload["dataset_identity"])
    return DefaultCatalogLiveBindableAuthorityPackage(
        package_kind=str(payload["package_kind"]),
        artifact_or_package_version=str(payload["artifact_or_package_version"]),
        catalog_identity_sha256=str(payload["catalog_identity_sha256"]),
        catalog_entry_count=_require_json_int(payload, "catalog_entry_count"),
        dataset_identity=dataset_identity,
        actuals_authority=str(payload["actuals_authority"]),
        forecasts_authority=str(payload["forecasts_authority"]),
        catalog_source_kind=str(payload["catalog_source_kind"]),
        reviewer_role=str(payload["reviewer_role"]),
        train_and_validation_only_rule=bool(payload["train_and_validation_only_rule"]),
        test_sealed_rule=bool(payload["test_sealed_rule"]),
        harvest_date_not_forecast_cutoff_rule=bool(
            payload["harvest_date_not_forecast_cutoff_rule"]
        ),
        reviewed_grain_identity_set_identity_sha256=str(
            payload["reviewed_grain_identity_set_identity_sha256"]
        ),
        content_identity_sha256=str(payload["content_identity_sha256"]),
        coordinator_review_evidence_digest_sha256=str(
            payload["coordinator_review_evidence_digest_sha256"]
        ),
        parent_contract_evidence_json_sha256=str(payload["parent_contract_evidence_json_sha256"]),
        parent_grant_evidence_json_sha256=str(payload["parent_grant_evidence_json_sha256"]),
        authority_evidence_digest_sha256=str(payload["authority_evidence_digest_sha256"]),
    )


def _parse_closeout_package(
    payload: dict[str, object],
) -> DefaultCatalogRegistryAvailableCloseoutPackage:
    return DefaultCatalogRegistryAvailableCloseoutPackage(
        package_kind=str(payload["package_kind"]),
        artifact_or_package_version=str(payload["artifact_or_package_version"]),
        catalog_identity_sha256=str(payload["catalog_identity_sha256"]),
        catalog_entry_count=_require_json_int(payload, "catalog_entry_count"),
        registry_snapshot_identity_sha256=str(payload["registry_snapshot_identity_sha256"]),
        authority_evidence_digest_sha256=str(payload["authority_evidence_digest_sha256"]),
        authorized_live_bindable_classification_required=bool(
            payload["authorized_live_bindable_classification_required"]
        ),
        authority_classification_success=str(payload["authority_classification_success"]),
        authority_reason_code_success=str(payload["authority_reason_code_success"]),
        registry_source_status_success=str(payload["registry_source_status_success"]),
        reviewer_role=str(payload["reviewer_role"]),
        train_and_validation_only_rule=bool(payload["train_and_validation_only_rule"]),
        test_sealed_rule=bool(payload["test_sealed_rule"]),
        parent_contract_evidence_json_sha256=str(payload["parent_contract_evidence_json_sha256"]),
        parent_grant_evidence_json_sha256=str(payload["parent_grant_evidence_json_sha256"]),
        registry_available_closeout_evidence_digest_sha256=str(
            payload["registry_available_closeout_evidence_digest_sha256"]
        ),
    )


def load_versioned_default_catalog_live_bindable_authority_package(
    *,
    artifact_path: Path = AUTHORITY_PACKAGE_ARTIFACT_PATH,
) -> DefaultCatalogLiveBindableAuthorityPackage | None:
    if not artifact_path.is_file():
        return None
    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if payload.get("artifact_or_package_version") != LIVE_BINDABLE_AUTHORITY_PACKAGE_VERSION:
        return None
    digest = compute_versioned_authority_package_evidence_digest_sha256(payload)
    if digest != payload.get("authority_evidence_digest_sha256"):
        return None
    try:
        return _parse_authority_package(payload)
    except (KeyError, TypeError, ValueError):
        return None


def load_versioned_default_catalog_registry_available_closeout_package(
    *,
    artifact_path: Path = REGISTRY_AVAILABLE_CLOSEOUT_PACKAGE_ARTIFACT_PATH,
) -> DefaultCatalogRegistryAvailableCloseoutPackage | None:
    if not artifact_path.is_file():
        return None
    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if payload.get("artifact_or_package_version") != REGISTRY_AVAILABLE_CLOSEOUT_PACKAGE_VERSION:
        return None
    digest = compute_versioned_closeout_package_evidence_digest_sha256(payload)
    if digest != payload.get("registry_available_closeout_evidence_digest_sha256"):
        return None
    try:
        return _parse_closeout_package(payload)
    except (KeyError, TypeError, ValueError):
        return None


def _dataset_identity_matches(dataset_identity: DatasetIdentity) -> bool:
    return (
        dataset_identity.dataset_id == EXPECTED_DATASET_ID
        and dataset_identity.dataset_version == EXPECTED_DATASET_VERSION
        and dataset_identity.materialized_dataset_identity_sha256
        == EXPECTED_MATERIALIZED_DATASET_IDENTITY_SHA256
    )


def _catalog_partitions_valid(entries: tuple[RegistryCatalogEntry, ...]) -> bool:
    if not entries:
        return False
    return all(entry.partition in ALLOWED_CATALOG_PARTITIONS for entry in entries)


def _frozen_binding_all_requirements_pass(binding: CatalogBindingResult) -> bool:
    if len(binding.requirements) != len(BINDING_REQUIREMENT_IDS):
        return False
    requirement_ids = {requirement.requirement_id for requirement in binding.requirements}
    if requirement_ids != set(BINDING_REQUIREMENT_IDS):
        return False
    return all(requirement.status == PredicateStatus.PASS for requirement in binding.requirements)


def _authority_package_matches_runtime(
    *,
    authority_package: DefaultCatalogLiveBindableAuthorityPackage,
    catalog_identity_sha256: str,
    catalog_entry_count: int,
    dataset_identity: DatasetIdentity,
) -> bool:
    return (
        authority_package.catalog_identity_sha256 == catalog_identity_sha256
        and authority_package.catalog_entry_count == catalog_entry_count
        and authority_package.dataset_identity == dataset_identity
        and authority_package.actuals_authority == ACTUALS_AUTHORITY
        and authority_package.forecasts_authority == FORECASTS_AUTHORITY
        and authority_package.catalog_source_kind == DECLARED_CATALOG_SOURCE_KIND
        and authority_package.reviewer_role == REVIEWER_ROLE
        and authority_package.train_and_validation_only_rule
        and authority_package.test_sealed_rule
        and authority_package.harvest_date_not_forecast_cutoff_rule
        and authority_package.coordinator_review_evidence_digest_sha256
        == REVIEW_EVIDENCE_DIGEST_SHA256
        and authority_package.parent_contract_evidence_json_sha256
        == PARENT_CONTRACT_EVIDENCE_JSON_SHA256
        and authority_package.parent_grant_evidence_json_sha256 == PARENT_GRANT_EVIDENCE_JSON_SHA256
    )


def _closeout_package_matches_runtime(
    *,
    closeout_package: DefaultCatalogRegistryAvailableCloseoutPackage,
    authority_package: DefaultCatalogLiveBindableAuthorityPackage,
    catalog_identity_sha256: str,
    catalog_entry_count: int,
    registry_source_status: str,
    registry_snapshot_identity_sha256: str | None,
) -> bool:
    return (
        closeout_package.catalog_identity_sha256 == catalog_identity_sha256
        and closeout_package.catalog_entry_count == catalog_entry_count
        and closeout_package.registry_snapshot_identity_sha256 == catalog_identity_sha256
        and closeout_package.registry_snapshot_identity_sha256 == registry_snapshot_identity_sha256
        and closeout_package.authority_evidence_digest_sha256
        == authority_package.authority_evidence_digest_sha256
        and closeout_package.authorized_live_bindable_classification_required
        and closeout_package.authority_classification_success
        == AuthorityClassification.LIVE_BINDABLE.value
        and closeout_package.authority_reason_code_success
        == AuthorityReasonCode.LIVE_BINDABLE_CATALOG.value
        and closeout_package.registry_source_status_success == registry_source_status
        and closeout_package.reviewer_role == REVIEWER_ROLE
        and closeout_package.train_and_validation_only_rule
        and closeout_package.test_sealed_rule
        and closeout_package.parent_contract_evidence_json_sha256
        == PARENT_CONTRACT_EVIDENCE_JSON_SHA256
        and closeout_package.parent_grant_evidence_json_sha256 == PARENT_GRANT_EVIDENCE_JSON_SHA256
    )


def _clear_construction_cache() -> None:
    from backend.app.s3_daily_rowset import (
        s3_a2_default_catalog_live_origin_construction as construction,
    )

    construction._cached_maker_id = construction._CACHE_MISS
    construction._cached_bundle = None


def _fail_result(
    *,
    reason_code: AuthorityReasonCode,
    catalog_produced: bool,
    catalog_identity_sha256: str | None,
    catalog_entry_count: int,
    catalog_source_kind: str | None = None,
    binding: CatalogBindingResult | None,
    authority_classification: AuthorityClassification = AuthorityClassification.NOT_CLASSIFIED,
    authorized_live_bindable_classification: bool = False,
    authority_package_version: str | None = None,
    authority_evidence_digest_sha256: str | None = None,
    registry_available_closeout_package_version: str | None = None,
    registry_available_closeout_evidence_digest_sha256: str | None = None,
    registry_source_status: str = REGISTRY_SOURCE_STATUS_UNBOUND,
    registry_snapshot_identity_sha256: str | None = None,
    registry_snapshot_identity_matches_bound_catalog_identity: bool = False,
) -> LiveBindabilityAndRegistryAvailabilityClassificationResult:
    return LiveBindabilityAndRegistryAvailabilityClassificationResult(
        reason_code=reason_code,
        catalog_produced=catalog_produced,
        catalog_identity_sha256=catalog_identity_sha256,
        catalog_entry_count=catalog_entry_count,
        catalog_source_kind=catalog_source_kind,
        binding_classification=binding.classification if binding is not None else None,
        binding_reason_code=binding.reason_code if binding is not None else None,
        in_memory_structural_acceptance=(
            binding.in_memory_structural_acceptance if binding is not None else False
        ),
        frozen_binding_classifies_live_bindable=False,
        authority_classification=authority_classification,
        authorized_live_bindable_classification=authorized_live_bindable_classification,
        authority_package_version=authority_package_version,
        authority_evidence_digest_sha256=authority_evidence_digest_sha256,
        registry_available_closeout_package_version=registry_available_closeout_package_version,
        registry_available_closeout_evidence_digest_sha256=(
            registry_available_closeout_evidence_digest_sha256
        ),
        registry_source_status=registry_source_status,
        registry_snapshot_identity_sha256=registry_snapshot_identity_sha256,
        registry_snapshot_identity_matches_bound_catalog_identity=(
            registry_snapshot_identity_matches_bound_catalog_identity
        ),
        coordinator_reviewed_available_closeout_exists=False,
        no_bindable_catalog_in_repository=True,
        evaluation_instance_registry_available=False,
        no_versioned_incumbent_forecast_artifact_in_repository=True,
        current_s3_daily_rowset_completeness_verified=False,
        live_bindability_implemented=False,
        registry_availability_implemented=False,
        unique_remaining_gap_closed=False,
    )


def _stage_two_fail_result(
    *,
    reason_code: AuthorityReasonCode,
    catalog_identity_sha256: str,
    catalog_entry_count: int,
    catalog_source_kind: str,
    binding: CatalogBindingResult,
    authority_package: DefaultCatalogLiveBindableAuthorityPackage,
    registry_source_status: str,
    registry_snapshot_identity_sha256: str | None,
    registry_snapshot_identity_matches_bound_catalog_identity: bool,
    closeout_package: DefaultCatalogRegistryAvailableCloseoutPackage | None = None,
) -> LiveBindabilityAndRegistryAvailabilityClassificationResult:
    closeout_version = (
        closeout_package.artifact_or_package_version if closeout_package is not None else None
    )
    closeout_digest = (
        closeout_package.registry_available_closeout_evidence_digest_sha256
        if closeout_package is not None
        else None
    )
    return LiveBindabilityAndRegistryAvailabilityClassificationResult(
        reason_code=reason_code,
        catalog_produced=True,
        catalog_identity_sha256=catalog_identity_sha256,
        catalog_entry_count=catalog_entry_count,
        catalog_source_kind=catalog_source_kind,
        binding_classification=binding.classification,
        binding_reason_code=binding.reason_code,
        in_memory_structural_acceptance=binding.in_memory_structural_acceptance,
        frozen_binding_classifies_live_bindable=False,
        authority_classification=AuthorityClassification.LIVE_BINDABLE,
        authorized_live_bindable_classification=True,
        authority_package_version=authority_package.artifact_or_package_version,
        authority_evidence_digest_sha256=authority_package.authority_evidence_digest_sha256,
        registry_available_closeout_package_version=closeout_version,
        registry_available_closeout_evidence_digest_sha256=closeout_digest,
        registry_source_status=registry_source_status,
        registry_snapshot_identity_sha256=registry_snapshot_identity_sha256,
        registry_snapshot_identity_matches_bound_catalog_identity=(
            registry_snapshot_identity_matches_bound_catalog_identity
        ),
        coordinator_reviewed_available_closeout_exists=False,
        no_bindable_catalog_in_repository=False,
        evaluation_instance_registry_available=False,
        no_versioned_incumbent_forecast_artifact_in_repository=True,
        current_s3_daily_rowset_completeness_verified=False,
        live_bindability_implemented=True,
        registry_availability_implemented=False,
        unique_remaining_gap_closed=False,
    )


def _authority_registry_source_status(
    *,
    catalog: EvaluationInstanceCatalogPort,
    catalog_identity_sha256: str,
    dataset_identity: DatasetIdentity,
) -> tuple[str, str | None, bool]:
    registry_service = EvaluationInstanceRegistryService(
        dataset_identity=dataset_identity,
        catalog=catalog,
    )
    snapshot = registry_service.snapshot()
    identity_matches = (
        snapshot.registry_identity_sha256 is not None
        and snapshot.registry_identity_sha256 == catalog_identity_sha256
    )
    if (
        catalog.source_kind() == CatalogSourceKind.V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF
        and snapshot.in_scope_cells
        and identity_matches
        and snapshot.actuals_authority == V0_3_S3_ACTUALS_AUTHORITY
        and snapshot.forecasts_authority == V0_3_S3_FORECASTS_AUTHORITY
    ):
        return (
            REGISTRY_SOURCE_STATUS_BOUND_V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF,
            snapshot.registry_identity_sha256,
            True,
        )
    return REGISTRY_SOURCE_STATUS_UNBOUND, snapshot.registry_identity_sha256, identity_matches


@dataclass(frozen=True, slots=True)
class DefaultCatalogLiveBindabilityAndRegistryAvailabilityClassifier:
    dataset_identity: DatasetIdentity = DEFAULT_DATASET_IDENTITY

    def classify(self) -> LiveBindabilityAndRegistryAvailabilityClassificationResult:
        try:
            produced = EvaluationInstanceCatalogArtifactProductionService(
                dataset_identity=self.dataset_identity,
            ).produce()
        finally:
            clear_v0_2_live_postgres_session_provider()
            _clear_construction_cache()

        binding = produced.binding_result
        catalog_produced = produced.reason_code is CatalogArtifactReasonCode.ARTIFACT_PRODUCED
        if not catalog_produced:
            return _fail_result(
                reason_code=AuthorityReasonCode.CATALOG_NOT_PRODUCED,
                catalog_produced=False,
                catalog_identity_sha256=None,
                catalog_entry_count=0,
                binding=binding,
            )

        catalog_identity = produced.catalog_identity_sha256
        entry_count = len(produced.catalog.entries())
        catalog_source_kind = produced.catalog.source_kind().value
        if (
            catalog_identity != PINNED_CATALOG_IDENTITY_SHA256
            or entry_count != PINNED_CATALOG_ENTRY_COUNT
        ):
            return _fail_result(
                reason_code=AuthorityReasonCode.CATALOG_PINS_MISMATCH,
                catalog_produced=True,
                catalog_identity_sha256=catalog_identity,
                catalog_entry_count=entry_count,
                catalog_source_kind=catalog_source_kind,
                binding=binding,
            )

        if catalog_source_kind != DECLARED_CATALOG_SOURCE_KIND:
            return _fail_result(
                reason_code=AuthorityReasonCode.CATALOG_PINS_MISMATCH,
                catalog_produced=True,
                catalog_identity_sha256=catalog_identity,
                catalog_entry_count=entry_count,
                catalog_source_kind=catalog_source_kind,
                binding=binding,
            )

        if not _catalog_partitions_valid(produced.catalog.entries()):
            return _fail_result(
                reason_code=AuthorityReasonCode.CATALOG_PINS_MISMATCH,
                catalog_produced=True,
                catalog_identity_sha256=catalog_identity,
                catalog_entry_count=entry_count,
                catalog_source_kind=catalog_source_kind,
                binding=binding,
            )

        if binding is None:
            return _fail_result(
                reason_code=AuthorityReasonCode.FROZEN_BINDING_PRECONDITIONS_NOT_MET,
                catalog_produced=True,
                catalog_identity_sha256=catalog_identity,
                catalog_entry_count=entry_count,
                catalog_source_kind=catalog_source_kind,
                binding=None,
            )

        frozen_ok = (
            binding.classification is BindingClassification.NOT_BINDABLE
            and binding.reason_code is BindingReasonCode.NOT_BINDABLE
            and binding.in_memory_structural_acceptance
            and _frozen_binding_all_requirements_pass(binding)
        )
        if not frozen_ok:
            return _fail_result(
                reason_code=AuthorityReasonCode.FROZEN_BINDING_PRECONDITIONS_NOT_MET,
                catalog_produced=True,
                catalog_identity_sha256=catalog_identity,
                catalog_entry_count=entry_count,
                catalog_source_kind=catalog_source_kind,
                binding=binding,
            )

        authority_package = load_versioned_default_catalog_live_bindable_authority_package()
        authority_valid = (
            authority_package is not None
            and authority_package_self_digest_valid(authority_package)
            and _authority_package_matches_runtime(
                authority_package=authority_package,
                catalog_identity_sha256=catalog_identity,
                catalog_entry_count=entry_count,
                dataset_identity=self.dataset_identity,
            )
        )
        if not authority_valid or authority_package is None:
            return _fail_result(
                reason_code=AuthorityReasonCode.AUTHORITY_PACKAGE_NOT_VALID,
                catalog_produced=True,
                catalog_identity_sha256=catalog_identity,
                catalog_entry_count=entry_count,
                catalog_source_kind=catalog_source_kind,
                binding=binding,
                authority_package_version=(
                    authority_package.artifact_or_package_version
                    if authority_package is not None
                    else None
                ),
                authority_evidence_digest_sha256=(
                    authority_package.authority_evidence_digest_sha256
                    if authority_package is not None
                    else None
                ),
            )

        registry_source_status, registry_snapshot_identity, identity_matches = (
            _authority_registry_source_status(
                catalog=produced.catalog,
                catalog_identity_sha256=catalog_identity,
                dataset_identity=self.dataset_identity,
            )
        )
        if (
            registry_source_status
            != REGISTRY_SOURCE_STATUS_BOUND_V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF
        ):
            return _fail_result(
                reason_code=AuthorityReasonCode.REGISTRY_AUTHORITY_NOT_BOUND,
                catalog_produced=True,
                catalog_identity_sha256=catalog_identity,
                catalog_entry_count=entry_count,
                catalog_source_kind=catalog_source_kind,
                binding=binding,
                authority_package_version=authority_package.artifact_or_package_version,
                authority_evidence_digest_sha256=authority_package.authority_evidence_digest_sha256,
                registry_source_status=registry_source_status,
                registry_snapshot_identity_sha256=registry_snapshot_identity,
                registry_snapshot_identity_matches_bound_catalog_identity=identity_matches,
            )

        closeout_package = load_versioned_default_catalog_registry_available_closeout_package()
        closeout_valid = (
            closeout_package is not None
            and closeout_package_self_digest_valid(closeout_package)
            and _closeout_package_matches_runtime(
                closeout_package=closeout_package,
                authority_package=authority_package,
                catalog_identity_sha256=catalog_identity,
                catalog_entry_count=entry_count,
                registry_source_status=registry_source_status,
                registry_snapshot_identity_sha256=registry_snapshot_identity,
            )
        )
        if not closeout_valid or closeout_package is None:
            return _stage_two_fail_result(
                reason_code=AuthorityReasonCode.AVAILABLE_CLOSEOUT_PACKAGE_NOT_VALID,
                catalog_identity_sha256=catalog_identity,
                catalog_entry_count=entry_count,
                catalog_source_kind=catalog_source_kind,
                binding=binding,
                authority_package=authority_package,
                registry_source_status=registry_source_status,
                registry_snapshot_identity_sha256=registry_snapshot_identity,
                registry_snapshot_identity_matches_bound_catalog_identity=identity_matches,
                closeout_package=closeout_package,
            )

        return LiveBindabilityAndRegistryAvailabilityClassificationResult(
            reason_code=AuthorityReasonCode.LIVE_BINDABLE_CATALOG,
            catalog_produced=True,
            catalog_identity_sha256=catalog_identity,
            catalog_entry_count=entry_count,
            catalog_source_kind=catalog_source_kind,
            binding_classification=binding.classification,
            binding_reason_code=binding.reason_code,
            in_memory_structural_acceptance=binding.in_memory_structural_acceptance,
            frozen_binding_classifies_live_bindable=False,
            authority_classification=AuthorityClassification.LIVE_BINDABLE,
            authorized_live_bindable_classification=True,
            authority_package_version=authority_package.artifact_or_package_version,
            authority_evidence_digest_sha256=authority_package.authority_evidence_digest_sha256,
            registry_available_closeout_package_version=closeout_package.artifact_or_package_version,
            registry_available_closeout_evidence_digest_sha256=(
                closeout_package.registry_available_closeout_evidence_digest_sha256
            ),
            registry_source_status=registry_source_status,
            registry_snapshot_identity_sha256=registry_snapshot_identity,
            registry_snapshot_identity_matches_bound_catalog_identity=identity_matches,
            coordinator_reviewed_available_closeout_exists=True,
            no_bindable_catalog_in_repository=False,
            evaluation_instance_registry_available=True,
            no_versioned_incumbent_forecast_artifact_in_repository=True,
            current_s3_daily_rowset_completeness_verified=False,
            live_bindability_implemented=True,
            registry_availability_implemented=True,
            unique_remaining_gap_closed=True,
        )
