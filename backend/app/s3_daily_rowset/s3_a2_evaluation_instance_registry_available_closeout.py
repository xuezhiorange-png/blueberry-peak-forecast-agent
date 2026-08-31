"""Classify whether AVAILABLE closeout preconditions hold.

Reuses already-landed bindable-repository classification. Does not rewrite
frozen catalog production or binding bytes, invent tonnes, flip AVAILABLE,
or leave a session provider set.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from backend.app.s3_daily_rowset.binding import BindingClassification, BindingReasonCode
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_live_postgres_read import (
    clear_v0_2_live_postgres_session_provider,
)
from backend.app.s3_daily_rowset.s3_a2_default_catalog_bindable_repository import (
    BindableRepositoryReasonCode,
    DefaultCatalogBindableRepositoryClassifier,
)
from backend.app.s3_daily_rowset.schemas import (
    EXPECTED_DATASET_ID,
    EXPECTED_DATASET_VERSION,
    EXPECTED_MATERIALIZED_DATASET_IDENTITY_SHA256,
    DatasetIdentity,
)

HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF = True
DEFAULT_DATASET_IDENTITY = DatasetIdentity(
    dataset_id=EXPECTED_DATASET_ID,
    dataset_version=EXPECTED_DATASET_VERSION,
    materialized_dataset_identity_sha256=EXPECTED_MATERIALIZED_DATASET_IDENTITY_SHA256,
)


class AvailableCloseoutReasonCode(StrEnum):
    CATALOG_NOT_PRODUCED = "CATALOG_NOT_PRODUCED"
    AVAILABLE_CLOSEOUT_PRECONDITIONS_NOT_MET = "AVAILABLE_CLOSEOUT_PRECONDITIONS_NOT_MET"


@dataclass(frozen=True, slots=True)
class AvailableCloseoutClassificationResult:
    reason_code: AvailableCloseoutReasonCode
    catalog_produced: bool
    catalog_identity_sha256: str | None
    catalog_entry_count: int
    bindable_repository_reason_code: BindableRepositoryReasonCode | None
    binding_classification: BindingClassification | None
    binding_reason_code: BindingReasonCode | None
    in_memory_structural_acceptance: bool
    coordinator_reviewed_available_closeout_exists: bool = False
    frozen_binding_classifies_live_bindable: bool = False
    no_bindable_catalog_in_repository: bool = True
    evaluation_instance_registry_available: bool = False
    current_s3_daily_rowset_completeness_verified: bool = False


@dataclass(frozen=True, slots=True)
class EvaluationInstanceRegistryAvailableCloseoutClassifier:
    dataset_identity: DatasetIdentity = DEFAULT_DATASET_IDENTITY

    def classify(self) -> AvailableCloseoutClassificationResult:
        try:
            bindable = DefaultCatalogBindableRepositoryClassifier(
                dataset_identity=self.dataset_identity,
            ).classify()
        finally:
            clear_v0_2_live_postgres_session_provider()
            from backend.app.s3_daily_rowset import (
                s3_a2_default_catalog_live_origin_construction as construction,
            )

            construction._cached_maker_id = construction._CACHE_MISS
            construction._cached_bundle = None

        if not bindable.catalog_produced:
            return AvailableCloseoutClassificationResult(
                reason_code=AvailableCloseoutReasonCode.CATALOG_NOT_PRODUCED,
                catalog_produced=False,
                catalog_identity_sha256=None,
                catalog_entry_count=0,
                bindable_repository_reason_code=bindable.reason_code,
                binding_classification=bindable.binding_classification,
                binding_reason_code=bindable.binding_reason_code,
                in_memory_structural_acceptance=False,
                coordinator_reviewed_available_closeout_exists=False,
                frozen_binding_classifies_live_bindable=False,
                no_bindable_catalog_in_repository=True,
                evaluation_instance_registry_available=False,
                current_s3_daily_rowset_completeness_verified=False,
            )

        # Frozen binding has no live-bindable classification. A coordinator-reviewed
        # AVAILABLE closeout does not exist. Must not flip AVAILABLE or NO_BINDABLE.
        return AvailableCloseoutClassificationResult(
            reason_code=AvailableCloseoutReasonCode.AVAILABLE_CLOSEOUT_PRECONDITIONS_NOT_MET,
            catalog_produced=True,
            catalog_identity_sha256=bindable.catalog_identity_sha256,
            catalog_entry_count=bindable.catalog_entry_count,
            bindable_repository_reason_code=bindable.reason_code,
            binding_classification=bindable.binding_classification,
            binding_reason_code=bindable.binding_reason_code,
            in_memory_structural_acceptance=bindable.in_memory_structural_acceptance,
            coordinator_reviewed_available_closeout_exists=False,
            frozen_binding_classifies_live_bindable=False,
            no_bindable_catalog_in_repository=True,
            evaluation_instance_registry_available=False,
            current_s3_daily_rowset_completeness_verified=False,
        )
