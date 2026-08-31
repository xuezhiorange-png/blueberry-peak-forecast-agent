"""Classify whether the already-produced live-origin catalog is bindable.

Reuses frozen catalog production and frozen binding. Does not rewrite those
bytes, invent tonnes, flip AVAILABLE, or leave a session provider set.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from backend.app.s3_daily_rowset.binding import BindingClassification, BindingReasonCode
from backend.app.s3_daily_rowset.catalog_artifact import (
    CatalogArtifactReasonCode,
    EvaluationInstanceCatalogArtifactProductionService,
)
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_live_postgres_read import (
    clear_v0_2_live_postgres_session_provider,
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


class BindableRepositoryReasonCode(StrEnum):
    CATALOG_NOT_PRODUCED = "CATALOG_NOT_PRODUCED"
    NOT_BINDABLE = "NOT_BINDABLE"


@dataclass(frozen=True, slots=True)
class BindableRepositoryClassificationResult:
    reason_code: BindableRepositoryReasonCode
    catalog_produced: bool
    catalog_identity_sha256: str | None
    catalog_entry_count: int
    binding_classification: BindingClassification | None
    binding_reason_code: BindingReasonCode | None
    in_memory_structural_acceptance: bool
    no_bindable_catalog_in_repository: bool = True
    evaluation_instance_registry_available: bool = False
    current_s3_daily_rowset_completeness_verified: bool = False


@dataclass(frozen=True, slots=True)
class DefaultCatalogBindableRepositoryClassifier:
    dataset_identity: DatasetIdentity = DEFAULT_DATASET_IDENTITY

    def classify(self) -> BindableRepositoryClassificationResult:
        try:
            produced = EvaluationInstanceCatalogArtifactProductionService(
                dataset_identity=self.dataset_identity,
            ).produce()
        finally:
            clear_v0_2_live_postgres_session_provider()
            from backend.app.s3_daily_rowset import (
                s3_a2_default_catalog_live_origin_construction as construction,
            )

            construction._cached_maker_id = construction._CACHE_MISS
            construction._cached_bundle = None

        binding = produced.binding_result
        catalog_produced = produced.reason_code is CatalogArtifactReasonCode.ARTIFACT_PRODUCED
        if not catalog_produced:
            return BindableRepositoryClassificationResult(
                reason_code=BindableRepositoryReasonCode.CATALOG_NOT_PRODUCED,
                catalog_produced=False,
                catalog_identity_sha256=None,
                catalog_entry_count=0,
                binding_classification=binding.classification if binding is not None else None,
                binding_reason_code=binding.reason_code if binding is not None else None,
                in_memory_structural_acceptance=False,
                no_bindable_catalog_in_repository=True,
                evaluation_instance_registry_available=False,
                current_s3_daily_rowset_completeness_verified=False,
            )

        return BindableRepositoryClassificationResult(
            reason_code=BindableRepositoryReasonCode.NOT_BINDABLE,
            catalog_produced=True,
            catalog_identity_sha256=produced.catalog_identity_sha256,
            catalog_entry_count=len(produced.catalog.entries()),
            binding_classification=binding.classification if binding is not None else None,
            binding_reason_code=binding.reason_code if binding is not None else None,
            in_memory_structural_acceptance=(
                binding.in_memory_structural_acceptance if binding is not None else False
            ),
            no_bindable_catalog_in_repository=True,
            evaluation_instance_registry_available=False,
            current_s3_daily_rowset_completeness_verified=False,
        )
