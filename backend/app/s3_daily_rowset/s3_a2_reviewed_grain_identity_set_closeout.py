"""Classify whether reviewed grain identity-set closeout preconditions hold.

Reuses already-landed AVAILABLE-closeout classification. Does not rewrite
frozen catalog, binding, grain, bindable-repository, or AVAILABLE-closeout
bytes, invent members, flip NO_REVIEWED, or leave a session provider set.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from backend.app.s3_daily_rowset.binding import BindingClassification, BindingReasonCode
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_live_postgres_read import (
    clear_v0_2_live_postgres_session_provider,
)
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_replay_identity_grain_identity_set import (
    load_reviewed_grain_identity_set,
    reviewed_grain_identity_set_artifact_available,
)
from backend.app.s3_daily_rowset.s3_a2_default_catalog_bindable_repository import (
    BindableRepositoryReasonCode,
)
from backend.app.s3_daily_rowset.s3_a2_evaluation_instance_registry_available_closeout import (
    AvailableCloseoutReasonCode,
    EvaluationInstanceRegistryAvailableCloseoutClassifier,
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


class ReviewedSetCloseoutReasonCode(StrEnum):
    CATALOG_NOT_PRODUCED = "CATALOG_NOT_PRODUCED"
    REVIEWED_SET_CLOSEOUT_PRECONDITIONS_NOT_MET = "REVIEWED_SET_CLOSEOUT_PRECONDITIONS_NOT_MET"


@dataclass(frozen=True, slots=True)
class ReviewedSetCloseoutClassificationResult:
    reason_code: ReviewedSetCloseoutReasonCode
    catalog_produced: bool
    catalog_identity_sha256: str | None
    catalog_entry_count: int
    available_closeout_reason_code: AvailableCloseoutReasonCode | None
    bindable_repository_reason_code: BindableRepositoryReasonCode | None
    binding_classification: BindingClassification | None
    binding_reason_code: BindingReasonCode | None
    in_memory_structural_acceptance: bool
    coordinator_reviewed_identity_set_exists: bool = False
    live_origin_grains_are_reviewed_set: bool = False
    reviewed_identity_set_member_count: int = 0
    no_reviewed_grain_identity_set_in_repository: bool = True
    no_bindable_catalog_in_repository: bool = True
    evaluation_instance_registry_available: bool = False
    current_s3_daily_rowset_completeness_verified: bool = False


@dataclass(frozen=True, slots=True)
class ReviewedGrainIdentitySetCloseoutClassifier:
    dataset_identity: DatasetIdentity = DEFAULT_DATASET_IDENTITY

    def classify(self) -> ReviewedSetCloseoutClassificationResult:
        try:
            available = EvaluationInstanceRegistryAvailableCloseoutClassifier(
                dataset_identity=self.dataset_identity,
            ).classify()
            coordinator_reviewed = reviewed_grain_identity_set_artifact_available()
            members = load_reviewed_grain_identity_set()
        finally:
            clear_v0_2_live_postgres_session_provider()
            from backend.app.s3_daily_rowset import (
                s3_a2_default_catalog_live_origin_construction as construction,
            )

            construction._cached_maker_id = construction._CACHE_MISS
            construction._cached_bundle = None

        if not available.catalog_produced:
            return ReviewedSetCloseoutClassificationResult(
                reason_code=ReviewedSetCloseoutReasonCode.CATALOG_NOT_PRODUCED,
                catalog_produced=False,
                catalog_identity_sha256=None,
                catalog_entry_count=0,
                available_closeout_reason_code=available.reason_code,
                bindable_repository_reason_code=available.bindable_repository_reason_code,
                binding_classification=available.binding_classification,
                binding_reason_code=available.binding_reason_code,
                in_memory_structural_acceptance=False,
                coordinator_reviewed_identity_set_exists=False,
                live_origin_grains_are_reviewed_set=False,
                reviewed_identity_set_member_count=0,
                no_reviewed_grain_identity_set_in_repository=True,
                no_bindable_catalog_in_repository=True,
                evaluation_instance_registry_available=False,
                current_s3_daily_rowset_completeness_verified=False,
            )

        # Live-origin policy grains are not a coordinator-reviewed identity set.
        # Must not flip NO_REVIEWED, NO_BINDABLE, or AVAILABLE.
        return ReviewedSetCloseoutClassificationResult(
            reason_code=ReviewedSetCloseoutReasonCode.REVIEWED_SET_CLOSEOUT_PRECONDITIONS_NOT_MET,
            catalog_produced=True,
            catalog_identity_sha256=available.catalog_identity_sha256,
            catalog_entry_count=available.catalog_entry_count,
            available_closeout_reason_code=available.reason_code,
            bindable_repository_reason_code=available.bindable_repository_reason_code,
            binding_classification=available.binding_classification,
            binding_reason_code=available.binding_reason_code,
            in_memory_structural_acceptance=available.in_memory_structural_acceptance,
            coordinator_reviewed_identity_set_exists=coordinator_reviewed and bool(members),
            live_origin_grains_are_reviewed_set=False,
            reviewed_identity_set_member_count=len(members) if coordinator_reviewed else 0,
            no_reviewed_grain_identity_set_in_repository=True,
            no_bindable_catalog_in_repository=True,
            evaluation_instance_registry_available=False,
            current_s3_daily_rowset_completeness_verified=False,
        )
