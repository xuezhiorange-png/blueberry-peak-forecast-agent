"""Record catalog no-versioned closeout after parent no-versioned flip success.

Calls parent no-versioned-flip classify(), then default catalog produce() on
success. Records that catalog produce still fail-closes NO_VERSIONED without
flipping live compact NO_VERSIONED. Does not auto-wire the global reviewed-set
loader at import.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from backend.app.s3_daily_rowset import (
    s3_a2_incumbent_forecast_artifact_no_versioned_flip as no_versioned_flip,
)
from backend.app.s3_daily_rowset.catalog_artifact import (
    CatalogArtifactReasonCode,
    EvaluationInstanceCatalogArtifactProductionService,
)
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_live_postgres_read import (
    clear_v0_2_live_postgres_session_provider,
)
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_replay_identity_grain_identity_set import (
    load_reviewed_grain_identity_set,
)
from backend.app.s3_daily_rowset.schemas import (
    EXPECTED_DATASET_ID,
    EXPECTED_DATASET_VERSION,
    EXPECTED_MATERIALIZED_DATASET_IDENTITY_SHA256,
    DatasetIdentity,
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
THIS_R1_RECORDS_CATALOG_STILL_FAIL_CLOSES_NO_VERSIONED: Final[bool] = True
THIS_R1_DOES_NOT_FLIP_NO_VERSIONED: Final[bool] = True
THIS_R1_MUST_NOT_FLIP_LIVE_COMPACT_NO_VERSIONED: Final[bool] = True
THIS_R1_MUST_NOT_MAKE_DEFAULT_CATALOG_PRODUCE_SUCCEED: Final[bool] = True
NO_VERSIONED_FLIP_PRECONDITION_1_HOLDS: Final[bool] = True
NO_VERSIONED_FLIP_PRECONDITION_2_HOLDS: Final[bool] = True

DEFAULT_DATASET_IDENTITY = DatasetIdentity(
    dataset_id=EXPECTED_DATASET_ID,
    dataset_version=EXPECTED_DATASET_VERSION,
    materialized_dataset_identity_sha256=EXPECTED_MATERIALIZED_DATASET_IDENTITY_SHA256,
)

IncumbentForecastArtifactNoVersionedFlipClassifier = (
    no_versioned_flip.IncumbentForecastArtifactNoVersionedFlipClassifier
)
IncumbentForecastArtifactNoVersionedFlipReasonCode = (
    no_versioned_flip.IncumbentForecastArtifactNoVersionedFlipReasonCode
)


class IncumbentForecastArtifactCatalogNoVersionedCloseoutReasonCode(StrEnum):
    CATALOG_NO_VERSIONED_CLOSEOUT_RECORDED = "CATALOG_NO_VERSIONED_CLOSEOUT_RECORDED"
    ORIGIN_ENTRIES_NOT_EXACTLY_THREE_POLICY_GRAINS = (
        "ORIGIN_ENTRIES_NOT_EXACTLY_THREE_POLICY_GRAINS"
    )
    CONTENT_PRODUCER_RETURNED_NONE = "CONTENT_PRODUCER_RETURNED_NONE"
    CATALOG_PRODUCE_UNEXPECTED_OUTCOME = "CATALOG_PRODUCE_UNEXPECTED_OUTCOME"


@dataclass(frozen=True, slots=True)
class IncumbentForecastArtifactCatalogNoVersionedCloseoutResult:
    reason_code: IncumbentForecastArtifactCatalogNoVersionedCloseoutReasonCode
    closeout_recorded: bool
    catalog_produce_still_fail_closes_no_versioned: bool
    catalog_produce_reason_code: CatalogArtifactReasonCode | None
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
    this_r1_records_catalog_still_fail_closes_no_versioned: bool
    this_r1_does_not_flip_no_versioned: bool
    this_r1_must_not_flip_live_compact_no_versioned: bool
    this_r1_must_not_make_default_catalog_produce_succeed: bool
    this_r1_classifier_flips_no_versioned_on_independent_review_success: bool
    this_r1_does_not_rewrite_frozen_catalog_artifact: bool


def _companion(
    *,
    reason_code: IncumbentForecastArtifactCatalogNoVersionedCloseoutReasonCode,
    closeout_recorded: bool,
    catalog_produce_still_fail_closes: bool,
    catalog_produce_reason_code: CatalogArtifactReasonCode | None,
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
) -> IncumbentForecastArtifactCatalogNoVersionedCloseoutResult:
    return IncumbentForecastArtifactCatalogNoVersionedCloseoutResult(
        reason_code=reason_code,
        closeout_recorded=closeout_recorded,
        catalog_produce_still_fail_closes_no_versioned=catalog_produce_still_fail_closes,
        catalog_produce_reason_code=catalog_produce_reason_code,
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
        this_r1_records_catalog_still_fail_closes_no_versioned=(
            THIS_R1_RECORDS_CATALOG_STILL_FAIL_CLOSES_NO_VERSIONED
        ),
        this_r1_does_not_flip_no_versioned=THIS_R1_DOES_NOT_FLIP_NO_VERSIONED,
        this_r1_must_not_flip_live_compact_no_versioned=(
            THIS_R1_MUST_NOT_FLIP_LIVE_COMPACT_NO_VERSIONED
        ),
        this_r1_must_not_make_default_catalog_produce_succeed=(
            THIS_R1_MUST_NOT_MAKE_DEFAULT_CATALOG_PRODUCE_SUCCEED
        ),
        this_r1_classifier_flips_no_versioned_on_independent_review_success=(
            THIS_R1_CLASSIFIER_FLIPS_NO_VERSIONED_ON_INDEPENDENT_REVIEW_SUCCESS
        ),
        this_r1_does_not_rewrite_frozen_catalog_artifact=(
            THIS_R1_DOES_NOT_REWRITE_FROZEN_CATALOG_ARTIFACT
        ),
    )


@dataclass(frozen=True, slots=True)
class IncumbentForecastArtifactCatalogNoVersionedCloseoutClassifier:
    dataset_identity: DatasetIdentity = DEFAULT_DATASET_IDENTITY

    def classify(self) -> IncumbentForecastArtifactCatalogNoVersionedCloseoutResult:
        parent_result = IncumbentForecastArtifactNoVersionedFlipClassifier().classify()
        clear_v0_2_live_postgres_session_provider()
        loader_empty = load_reviewed_grain_identity_set() == ()
        if parent_result.reason_code is (
            IncumbentForecastArtifactNoVersionedFlipReasonCode.ORIGIN_ENTRIES_NOT_EXACTLY_THREE_POLICY_GRAINS
        ):
            return _companion(
                reason_code=(
                    IncumbentForecastArtifactCatalogNoVersionedCloseoutReasonCode.ORIGIN_ENTRIES_NOT_EXACTLY_THREE_POLICY_GRAINS
                ),
                closeout_recorded=False,
                catalog_produce_still_fail_closes=False,
                catalog_produce_reason_code=None,
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
            IncumbentForecastArtifactNoVersionedFlipReasonCode.CONTENT_PRODUCER_RETURNED_NONE
        ):
            return _companion(
                reason_code=(
                    IncumbentForecastArtifactCatalogNoVersionedCloseoutReasonCode.CONTENT_PRODUCER_RETURNED_NONE
                ),
                closeout_recorded=False,
                catalog_produce_still_fail_closes=False,
                catalog_produce_reason_code=None,
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
        produced = EvaluationInstanceCatalogArtifactProductionService(
            dataset_identity=self.dataset_identity,
        ).produce()
        clear_v0_2_live_postgres_session_provider()
        if produced.reason_code is not (
            CatalogArtifactReasonCode.NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
        ):
            return _companion(
                reason_code=(
                    IncumbentForecastArtifactCatalogNoVersionedCloseoutReasonCode.CATALOG_PRODUCE_UNEXPECTED_OUTCOME
                ),
                closeout_recorded=False,
                catalog_produce_still_fail_closes=False,
                catalog_produce_reason_code=produced.reason_code,
                flip_recorded=parent_result.no_versioned_flip_recorded,
                review_recorded=parent_result.presence_package_independent_review_recorded,
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
                no_versioned=True,
                precondition_3_holds=True,
                precondition_4_holds=True,
            )
        return _companion(
            reason_code=(
                IncumbentForecastArtifactCatalogNoVersionedCloseoutReasonCode.CATALOG_NO_VERSIONED_CLOSEOUT_RECORDED
            ),
            closeout_recorded=True,
            catalog_produce_still_fail_closes=True,
            catalog_produce_reason_code=produced.reason_code,
            flip_recorded=parent_result.no_versioned_flip_recorded,
            review_recorded=parent_result.presence_package_independent_review_recorded,
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
            no_versioned=True,
            precondition_3_holds=True,
            precondition_4_holds=True,
        )
