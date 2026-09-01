"""Record no-versioned flip on independent-review success.

Calls presence-package independent-review classify() directly. On success, flips
NO_VERSIONED in this classifier only. Does not auto-wire the global reviewed-set
loader at import. Does not rewrite frozen catalog, independent-review, or
presence-observation bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from backend.app.s3_daily_rowset import (
    s3_a2_incumbent_forecast_artifact_presence_package_independent_review as independent_review,
)
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_live_postgres_read import (
    clear_v0_2_live_postgres_session_provider,
)
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_replay_identity_grain_identity_set import (
    load_reviewed_grain_identity_set,
)

WEATHER_UNAVAILABLE: Final[bool] = True
PLANS_UNAVAILABLE: Final[bool] = True
WEATHER_AND_PLANS_DEFERRED_TO_NEXT_VERSION: Final[bool] = True
WEATHER_AND_PLANS_DO_NOT_BLOCK_NON_CURVE_IMPLEMENTATION: Final[bool] = True
WEATHER_AND_PLANS_BLOCK_COMPLETENESS_PASS: Final[bool] = True
FORBIDDEN_DERIVE_MEMBERS_FROM_SOURCE_002: Final[bool] = True
FORBIDDEN_INVENT_ADDITIONAL_MEMBERS: Final[bool] = True
FROZEN_REVIEWED_SET_CLOSEOUT_STILL_REPORTS_NO_REVIEWED: Final[bool] = True
FROZEN_COMPLETENESS_PASS_CLOSEOUT_STILL_UNAUTHORIZED: Final[bool] = True
FROZEN_PRESENCE_R1_STILL_REPORTS_FAIL_CLOSED_NO_REVIEWED_SET: Final[bool] = True
CONTENT_PRODUCER_ON_EMPTY_OBTAIN_RETURNS_NONE: Final[bool] = True
IN_MEMORY_CATALOG_ARTIFACT_PRODUCED_IS_NOT_VERSIONED_REPOSITORY_ARTIFACT: Final[bool] = True
IN_MEMORY_CATALOG_IS_NOT_PRESENCE_PACKAGE: Final[bool] = True
FROZEN_INDEPENDENT_REVIEW_STILL_REPORTS_NO_VERSIONED_TRUE: Final[bool] = True
FROZEN_LIVE_COMPACT_NO_VERSIONED_REMAINS_TRUE: Final[bool] = True
CATALOG_PRODUCE_STILL_FAIL_CLOSES_NO_VERSIONED: Final[bool] = True
THIS_R1_CLASSIFIER_FLIPS_NO_VERSIONED_ON_INDEPENDENT_REVIEW_SUCCESS: Final[bool] = True
THIS_R1_DOES_NOT_REWRITE_FROZEN_CATALOG_ARTIFACT: Final[bool] = True
NO_VERSIONED_FLIP_PRECONDITION_1_HOLDS: Final[bool] = True
NO_VERSIONED_FLIP_PRECONDITION_2_HOLDS: Final[bool] = True

IncumbentForecastArtifactPresencePackageIndependentReviewClassifier = (
    independent_review.IncumbentForecastArtifactPresencePackageIndependentReviewClassifier
)
IncumbentForecastArtifactPresencePackageIndependentReviewReasonCode = (
    independent_review.IncumbentForecastArtifactPresencePackageIndependentReviewReasonCode
)


class IncumbentForecastArtifactNoVersionedFlipReasonCode(StrEnum):
    NO_VERSIONED_FLIP_RECORDED = "NO_VERSIONED_FLIP_RECORDED"
    ORIGIN_ENTRIES_NOT_EXACTLY_THREE_POLICY_GRAINS = (
        "ORIGIN_ENTRIES_NOT_EXACTLY_THREE_POLICY_GRAINS"
    )
    CONTENT_PRODUCER_RETURNED_NONE = "CONTENT_PRODUCER_RETURNED_NONE"


@dataclass(frozen=True, slots=True)
class IncumbentForecastArtifactNoVersionedFlipResult:
    reason_code: IncumbentForecastArtifactNoVersionedFlipReasonCode
    no_versioned_flip_recorded: bool
    presence_package_independent_review_recorded: bool
    review_evidence_digest_sha256: str
    content_identity_sha256: str
    content_row_count: int
    repository_presence_observation_recorded: bool
    coordinator_reviewed_identity_set_exists: bool
    reviewed_identity_set_member_count: int
    reviewed_grain_identity_set_identity_sha256: str
    review_cutoff_at: str
    review_cutoff_business_date: str
    review_model_id: str
    review_quantiles: tuple[str, ...]
    default_global_reviewed_set_loader_remains_empty: bool
    frozen_reviewed_set_closeout_still_reports_no_reviewed: bool
    frozen_completeness_pass_closeout_still_unauthorized: bool
    no_reviewed_grain_identity_set_in_repository: bool
    no_bindable_catalog_in_repository: bool
    evaluation_instance_registry_available: bool
    current_s3_daily_rowset_completeness_verified: bool
    s3_a2_completeness_pass_authorized: bool
    weather_unavailable: bool
    plans_unavailable: bool
    weather_and_plans_deferred_to_next_version: bool
    weather_and_plans_do_not_block_non_curve_implementation: bool
    weather_and_plans_block_completeness_pass: bool
    forbidden_derive_members_from_source_002: bool
    forbidden_invent_additional_members: bool
    default_session_provider_left_unset: bool
    no_versioned_incumbent_forecast_artifact_in_repository: bool
    frozen_presence_r1_still_reports_fail_closed_no_reviewed_set: bool
    content_producer_on_empty_obtain_returns_none: bool
    in_memory_catalog_artifact_produced_is_not_versioned_repository_artifact: bool
    in_memory_catalog_is_not_presence_package: bool
    no_versioned_flip_precondition_1_holds: bool
    no_versioned_flip_precondition_2_holds: bool
    no_versioned_flip_precondition_3_holds: bool
    no_versioned_flip_precondition_4_holds: bool
    frozen_independent_review_still_reports_no_versioned_true: bool
    frozen_live_compact_no_versioned_remains_true: bool
    catalog_produce_still_fail_closes_no_versioned: bool
    this_r1_classifier_flips_no_versioned_on_independent_review_success: bool
    this_r1_does_not_rewrite_frozen_catalog_artifact: bool


def _companion(
    *,
    reason_code: IncumbentForecastArtifactNoVersionedFlipReasonCode,
    flip_recorded: bool,
    review_recorded: bool,
    review_evidence_digest_sha256: str,
    content_identity_sha256: str,
    content_row_count: int,
    repository_recorded: bool,
    exists: bool,
    member_count: int,
    identity_sha256: str,
    review_cutoff_at: str,
    review_cutoff_business_date: str,
    review_model_id: str,
    review_quantiles: tuple[str, ...],
    loader_empty: bool,
    no_versioned: bool,
    precondition_3_holds: bool,
    precondition_4_holds: bool,
) -> IncumbentForecastArtifactNoVersionedFlipResult:
    return IncumbentForecastArtifactNoVersionedFlipResult(
        reason_code=reason_code,
        no_versioned_flip_recorded=flip_recorded,
        presence_package_independent_review_recorded=review_recorded,
        review_evidence_digest_sha256=review_evidence_digest_sha256,
        content_identity_sha256=content_identity_sha256,
        content_row_count=content_row_count,
        repository_presence_observation_recorded=repository_recorded,
        coordinator_reviewed_identity_set_exists=exists,
        reviewed_identity_set_member_count=member_count,
        reviewed_grain_identity_set_identity_sha256=identity_sha256,
        review_cutoff_at=review_cutoff_at,
        review_cutoff_business_date=review_cutoff_business_date,
        review_model_id=review_model_id,
        review_quantiles=review_quantiles,
        default_global_reviewed_set_loader_remains_empty=loader_empty,
        frozen_reviewed_set_closeout_still_reports_no_reviewed=(
            FROZEN_REVIEWED_SET_CLOSEOUT_STILL_REPORTS_NO_REVIEWED
        ),
        frozen_completeness_pass_closeout_still_unauthorized=(
            FROZEN_COMPLETENESS_PASS_CLOSEOUT_STILL_UNAUTHORIZED
        ),
        no_reviewed_grain_identity_set_in_repository=False,
        no_bindable_catalog_in_repository=True,
        evaluation_instance_registry_available=False,
        current_s3_daily_rowset_completeness_verified=False,
        s3_a2_completeness_pass_authorized=False,
        weather_unavailable=WEATHER_UNAVAILABLE,
        plans_unavailable=PLANS_UNAVAILABLE,
        weather_and_plans_deferred_to_next_version=WEATHER_AND_PLANS_DEFERRED_TO_NEXT_VERSION,
        weather_and_plans_do_not_block_non_curve_implementation=(
            WEATHER_AND_PLANS_DO_NOT_BLOCK_NON_CURVE_IMPLEMENTATION
        ),
        weather_and_plans_block_completeness_pass=WEATHER_AND_PLANS_BLOCK_COMPLETENESS_PASS,
        forbidden_derive_members_from_source_002=FORBIDDEN_DERIVE_MEMBERS_FROM_SOURCE_002,
        forbidden_invent_additional_members=FORBIDDEN_INVENT_ADDITIONAL_MEMBERS,
        default_session_provider_left_unset=True,
        no_versioned_incumbent_forecast_artifact_in_repository=no_versioned,
        frozen_presence_r1_still_reports_fail_closed_no_reviewed_set=(
            FROZEN_PRESENCE_R1_STILL_REPORTS_FAIL_CLOSED_NO_REVIEWED_SET
        ),
        content_producer_on_empty_obtain_returns_none=(
            CONTENT_PRODUCER_ON_EMPTY_OBTAIN_RETURNS_NONE
        ),
        in_memory_catalog_artifact_produced_is_not_versioned_repository_artifact=(
            IN_MEMORY_CATALOG_ARTIFACT_PRODUCED_IS_NOT_VERSIONED_REPOSITORY_ARTIFACT
        ),
        in_memory_catalog_is_not_presence_package=IN_MEMORY_CATALOG_IS_NOT_PRESENCE_PACKAGE,
        no_versioned_flip_precondition_1_holds=NO_VERSIONED_FLIP_PRECONDITION_1_HOLDS,
        no_versioned_flip_precondition_2_holds=NO_VERSIONED_FLIP_PRECONDITION_2_HOLDS,
        no_versioned_flip_precondition_3_holds=precondition_3_holds,
        no_versioned_flip_precondition_4_holds=precondition_4_holds,
        frozen_independent_review_still_reports_no_versioned_true=(
            FROZEN_INDEPENDENT_REVIEW_STILL_REPORTS_NO_VERSIONED_TRUE
        ),
        frozen_live_compact_no_versioned_remains_true=FROZEN_LIVE_COMPACT_NO_VERSIONED_REMAINS_TRUE,
        catalog_produce_still_fail_closes_no_versioned=(
            CATALOG_PRODUCE_STILL_FAIL_CLOSES_NO_VERSIONED
        ),
        this_r1_classifier_flips_no_versioned_on_independent_review_success=(
            THIS_R1_CLASSIFIER_FLIPS_NO_VERSIONED_ON_INDEPENDENT_REVIEW_SUCCESS
        ),
        this_r1_does_not_rewrite_frozen_catalog_artifact=(
            THIS_R1_DOES_NOT_REWRITE_FROZEN_CATALOG_ARTIFACT
        ),
    )


@dataclass(frozen=True, slots=True)
class IncumbentForecastArtifactNoVersionedFlipClassifier:
    def classify(self) -> IncumbentForecastArtifactNoVersionedFlipResult:
        parent_result = (
            IncumbentForecastArtifactPresencePackageIndependentReviewClassifier().classify()
        )
        clear_v0_2_live_postgres_session_provider()
        loader_empty = load_reviewed_grain_identity_set() == ()
        if parent_result.reason_code is (
            IncumbentForecastArtifactPresencePackageIndependentReviewReasonCode.ORIGIN_ENTRIES_NOT_EXACTLY_THREE_POLICY_GRAINS
        ):
            return _companion(
                reason_code=(
                    IncumbentForecastArtifactNoVersionedFlipReasonCode.ORIGIN_ENTRIES_NOT_EXACTLY_THREE_POLICY_GRAINS
                ),
                flip_recorded=False,
                review_recorded=False,
                review_evidence_digest_sha256="",
                content_identity_sha256="",
                content_row_count=0,
                repository_recorded=False,
                exists=False,
                member_count=0,
                identity_sha256="",
                review_cutoff_at=parent_result.review_cutoff_at,
                review_cutoff_business_date=parent_result.review_cutoff_business_date,
                review_model_id=parent_result.review_model_id,
                review_quantiles=parent_result.review_quantiles,
                loader_empty=loader_empty,
                no_versioned=True,
                precondition_3_holds=False,
                precondition_4_holds=False,
            )
        if parent_result.reason_code is (
            IncumbentForecastArtifactPresencePackageIndependentReviewReasonCode.CONTENT_PRODUCER_RETURNED_NONE
        ):
            return _companion(
                reason_code=(
                    IncumbentForecastArtifactNoVersionedFlipReasonCode.CONTENT_PRODUCER_RETURNED_NONE
                ),
                flip_recorded=False,
                review_recorded=False,
                review_evidence_digest_sha256="",
                content_identity_sha256="",
                content_row_count=0,
                repository_recorded=parent_result.repository_presence_observation_recorded,
                exists=parent_result.coordinator_reviewed_identity_set_exists,
                member_count=parent_result.reviewed_identity_set_member_count,
                identity_sha256=parent_result.reviewed_grain_identity_set_identity_sha256,
                review_cutoff_at=parent_result.review_cutoff_at,
                review_cutoff_business_date=parent_result.review_cutoff_business_date,
                review_model_id=parent_result.review_model_id,
                review_quantiles=parent_result.review_quantiles,
                loader_empty=loader_empty,
                no_versioned=True,
                precondition_3_holds=False,
                precondition_4_holds=False,
            )
        return _companion(
            reason_code=IncumbentForecastArtifactNoVersionedFlipReasonCode.NO_VERSIONED_FLIP_RECORDED,
            flip_recorded=True,
            review_recorded=True,
            review_evidence_digest_sha256=parent_result.review_evidence_digest_sha256,
            content_identity_sha256=parent_result.content_identity_sha256,
            content_row_count=parent_result.content_row_count,
            repository_recorded=parent_result.repository_presence_observation_recorded,
            exists=parent_result.coordinator_reviewed_identity_set_exists,
            member_count=parent_result.reviewed_identity_set_member_count,
            identity_sha256=parent_result.reviewed_grain_identity_set_identity_sha256,
            review_cutoff_at=parent_result.review_cutoff_at,
            review_cutoff_business_date=parent_result.review_cutoff_business_date,
            review_model_id=parent_result.review_model_id,
            review_quantiles=parent_result.review_quantiles,
            loader_empty=loader_empty,
            no_versioned=False,
            precondition_3_holds=True,
            precondition_4_holds=True,
        )
