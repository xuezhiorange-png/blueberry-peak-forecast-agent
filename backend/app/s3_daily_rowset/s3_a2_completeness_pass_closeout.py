"""Classify whether completeness PASS closeout preconditions hold.

Reuses already-landed reviewed-set closeout classification. Does not rewrite
frozen catalog, binding, completeness, grain, bindable-repository,
AVAILABLE-closeout, or reviewed-set closeout bytes, invent weather, plans,
tonnes, or members, flip completeness PASS, or leave a session provider set.
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
)
from backend.app.s3_daily_rowset.s3_a2_evaluation_instance_registry_available_closeout import (
    AvailableCloseoutReasonCode,
)
from backend.app.s3_daily_rowset.s3_a2_reviewed_grain_identity_set_closeout import (
    ReviewedGrainIdentitySetCloseoutClassifier,
    ReviewedSetCloseoutReasonCode,
)
from backend.app.s3_daily_rowset.schemas import (
    EXPECTED_DATASET_ID,
    EXPECTED_DATASET_VERSION,
    EXPECTED_MATERIALIZED_DATASET_IDENTITY_SHA256,
    DatasetIdentity,
)

HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF = True
WEATHER_UNAVAILABLE = True
PLANS_UNAVAILABLE = True
WEATHER_AND_PLANS_BLOCK_COMPLETENESS_PASS = True
FORBIDDEN_INVENT_WEATHER = True
FORBIDDEN_INVENT_PLANS = True
FORBIDDEN_TREAT_LIVE_ORIGIN_GRAINS_AS_REVIEWED_SET = True
DEFAULT_DATASET_IDENTITY = DatasetIdentity(
    dataset_id=EXPECTED_DATASET_ID,
    dataset_version=EXPECTED_DATASET_VERSION,
    materialized_dataset_identity_sha256=EXPECTED_MATERIALIZED_DATASET_IDENTITY_SHA256,
)


class CompletenessPassCloseoutReasonCode(StrEnum):
    CATALOG_NOT_PRODUCED = "CATALOG_NOT_PRODUCED"
    COMPLETENESS_PASS_CLOSEOUT_PRECONDITIONS_NOT_MET = (
        "COMPLETENESS_PASS_CLOSEOUT_PRECONDITIONS_NOT_MET"
    )


@dataclass(frozen=True, slots=True)
class CompletenessPassCloseoutClassificationResult:
    reason_code: CompletenessPassCloseoutReasonCode
    catalog_produced: bool
    catalog_identity_sha256: str | None
    catalog_entry_count: int
    reviewed_set_closeout_reason_code: ReviewedSetCloseoutReasonCode | None
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
    s3_a2_completeness_pass_authorized: bool = False
    weather_unavailable: bool = True
    plans_unavailable: bool = True
    weather_and_plans_block_completeness_pass: bool = True
    forbidden_treat_live_origin_grains_as_reviewed_set: bool = True


@dataclass(frozen=True, slots=True)
class CompletenessPassCloseoutClassifier:
    dataset_identity: DatasetIdentity = DEFAULT_DATASET_IDENTITY

    def classify(self) -> CompletenessPassCloseoutClassificationResult:
        try:
            reviewed = ReviewedGrainIdentitySetCloseoutClassifier(
                dataset_identity=self.dataset_identity,
            ).classify()
        finally:
            clear_v0_2_live_postgres_session_provider()
            from backend.app.s3_daily_rowset import (
                s3_a2_default_catalog_live_origin_construction as construction,
            )

            construction._cached_maker_id = construction._CACHE_MISS
            construction._cached_bundle = None

        if not reviewed.catalog_produced:
            return CompletenessPassCloseoutClassificationResult(
                reason_code=CompletenessPassCloseoutReasonCode.CATALOG_NOT_PRODUCED,
                catalog_produced=False,
                catalog_identity_sha256=None,
                catalog_entry_count=0,
                reviewed_set_closeout_reason_code=reviewed.reason_code,
                available_closeout_reason_code=reviewed.available_closeout_reason_code,
                bindable_repository_reason_code=reviewed.bindable_repository_reason_code,
                binding_classification=reviewed.binding_classification,
                binding_reason_code=reviewed.binding_reason_code,
                in_memory_structural_acceptance=False,
                coordinator_reviewed_identity_set_exists=False,
                live_origin_grains_are_reviewed_set=False,
                reviewed_identity_set_member_count=0,
                no_reviewed_grain_identity_set_in_repository=True,
                no_bindable_catalog_in_repository=True,
                evaluation_instance_registry_available=False,
                current_s3_daily_rowset_completeness_verified=False,
                s3_a2_completeness_pass_authorized=False,
                weather_unavailable=WEATHER_UNAVAILABLE,
                plans_unavailable=PLANS_UNAVAILABLE,
                weather_and_plans_block_completeness_pass=(
                    WEATHER_AND_PLANS_BLOCK_COMPLETENESS_PASS
                ),
                forbidden_treat_live_origin_grains_as_reviewed_set=(
                    FORBIDDEN_TREAT_LIVE_ORIGIN_GRAINS_AS_REVIEWED_SET
                ),
            )

        # Weather and plans remain unavailable and block completeness PASS.
        # Reviewed-set closeout, AVAILABLE closeout, and bindable-repository
        # preconditions are also unmet. Live-origin grains are not a reviewed set.
        return CompletenessPassCloseoutClassificationResult(
            reason_code=(
                CompletenessPassCloseoutReasonCode.COMPLETENESS_PASS_CLOSEOUT_PRECONDITIONS_NOT_MET
            ),
            catalog_produced=True,
            catalog_identity_sha256=reviewed.catalog_identity_sha256,
            catalog_entry_count=reviewed.catalog_entry_count,
            reviewed_set_closeout_reason_code=reviewed.reason_code,
            available_closeout_reason_code=reviewed.available_closeout_reason_code,
            bindable_repository_reason_code=reviewed.bindable_repository_reason_code,
            binding_classification=reviewed.binding_classification,
            binding_reason_code=reviewed.binding_reason_code,
            in_memory_structural_acceptance=reviewed.in_memory_structural_acceptance,
            coordinator_reviewed_identity_set_exists=(
                reviewed.coordinator_reviewed_identity_set_exists
            ),
            live_origin_grains_are_reviewed_set=False,
            reviewed_identity_set_member_count=reviewed.reviewed_identity_set_member_count,
            no_reviewed_grain_identity_set_in_repository=True,
            no_bindable_catalog_in_repository=True,
            evaluation_instance_registry_available=False,
            current_s3_daily_rowset_completeness_verified=False,
            s3_a2_completeness_pass_authorized=False,
            weather_unavailable=WEATHER_UNAVAILABLE,
            plans_unavailable=PLANS_UNAVAILABLE,
            weather_and_plans_block_completeness_pass=WEATHER_AND_PLANS_BLOCK_COMPLETENESS_PASS,
            forbidden_treat_live_origin_grains_as_reviewed_set=(
                FORBIDDEN_TREAT_LIVE_ORIGIN_GRAINS_AS_REVIEWED_SET
            ),
        )
