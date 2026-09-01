"""Record incumbent forecast artifact content for coordinator-reviewed grains.

Calls repository-presence observation classify() directly, then frozen
IncumbentForecastArtifactContentProducer with landed identity-set members.
Does not auto-wire the global reviewed-set loader at import. Does not invoke
frozen closeout classifiers, catalog produce/construction, rewrite frozen
content-producer bytes, invent members, weather, plans, or tonnes, or flip
NO_VERSIONED.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from backend.app.s3_daily_rowset import (
    s3_a2_incumbent_forecast_artifact_repository_presence_observation as repo_presence_obs,
)
from backend.app.s3_daily_rowset.catalog_artifact import IncumbentForecastArtifactEntry
from backend.app.s3_daily_rowset.incumbent_forecast_artifact_content import (
    IncumbentForecastArtifactContentProducer,
)
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_live_postgres_read import (
    clear_v0_2_live_postgres_session_provider,
)
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_replay_identity_grain_identity_set import (
    load_reviewed_grain_identity_set,
)
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_replay_identity_grain_row_presence import (
    ReviewedGrainIdentity,
)
from backend.app.s3_daily_rowset.registry import CatalogSourceKind
from backend.app.s3_daily_rowset.s3_a2_coordinator_reviewed_live_origin_grain_identity_set import (
    REVIEW_CUTOFF_AT,
    REVIEW_CUTOFF_BUSINESS_DATE,
    REVIEW_MODEL_ID,
    REVIEW_QUANTILES,
    REVIEWED_GRAIN_IDENTITY_SET_IDENTITY_SHA256,
    load_coordinator_reviewed_live_origin_grain_identity_set,
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
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY: Final[bool] = True
FROZEN_PRESENCE_R1_STILL_REPORTS_FAIL_CLOSED_NO_REVIEWED_SET: Final[bool] = True
CONTENT_PRODUCER_ON_EMPTY_OBTAIN_RETURNS_NONE: Final[bool] = True
IN_MEMORY_CATALOG_ARTIFACT_PRODUCED_IS_NOT_VERSIONED_REPOSITORY_ARTIFACT: Final[bool] = True
NO_VERSIONED_FLIP_PRECONDITION_1_HOLDS: Final[bool] = True
NO_VERSIONED_FLIP_PRECONDITION_2_HOLDS: Final[bool] = True
NO_VERSIONED_FLIP_PRECONDITION_4_HOLDS: Final[bool] = False

IncumbentForecastArtifactRepositoryPresenceObservationClassifier = (
    repo_presence_obs.IncumbentForecastArtifactRepositoryPresenceObservationClassifier
)
IncumbentForecastArtifactRepositoryPresenceObservationReasonCode = (
    repo_presence_obs.IncumbentForecastArtifactRepositoryPresenceObservationReasonCode
)


class IncumbentForecastArtifactContentForReviewedGrainsReasonCode(StrEnum):
    CONTENT_FOR_REVIEWED_GRAINS_RECORDED = "CONTENT_FOR_REVIEWED_GRAINS_RECORDED"
    ORIGIN_ENTRIES_NOT_EXACTLY_THREE_POLICY_GRAINS = (
        "ORIGIN_ENTRIES_NOT_EXACTLY_THREE_POLICY_GRAINS"
    )
    CONTENT_PRODUCER_RETURNED_NONE = "CONTENT_PRODUCER_RETURNED_NONE"


@dataclass(frozen=True, slots=True)
class IncumbentForecastArtifactContentForReviewedGrainsResult:
    reason_code: IncumbentForecastArtifactContentForReviewedGrainsReasonCode
    content_for_reviewed_grains_recorded: bool
    content_identity_sha256: str
    content_row_count: int
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
    no_versioned_flip_precondition_1_holds: bool
    no_versioned_flip_precondition_2_holds: bool
    no_versioned_flip_precondition_3_holds: bool
    no_versioned_flip_precondition_4_holds: bool


def _members_to_replay_rows(
    members: tuple[ReviewedGrainIdentity, ...],
) -> tuple[IncumbentForecastArtifactEntry, ...]:
    return tuple(
        IncumbentForecastArtifactEntry(
            model_id=member.model_id,
            forecast_cutoff_at=member.forecast_cutoff_at,
            forecast_quantile=member.forecast_quantile,
        )
        for member in members
    )


def _companion(
    *,
    reason_code: IncumbentForecastArtifactContentForReviewedGrainsReasonCode,
    content_recorded: bool,
    content_identity_sha256: str,
    content_row_count: int,
    exists: bool,
    member_count: int,
    identity_sha256: str,
    loader_empty: bool,
    precondition_3_holds: bool,
) -> IncumbentForecastArtifactContentForReviewedGrainsResult:
    return IncumbentForecastArtifactContentForReviewedGrainsResult(
        reason_code=reason_code,
        content_for_reviewed_grains_recorded=content_recorded,
        content_identity_sha256=content_identity_sha256,
        content_row_count=content_row_count,
        coordinator_reviewed_identity_set_exists=exists,
        reviewed_identity_set_member_count=member_count,
        reviewed_grain_identity_set_identity_sha256=identity_sha256,
        review_cutoff_at=REVIEW_CUTOFF_AT,
        review_cutoff_business_date=REVIEW_CUTOFF_BUSINESS_DATE,
        review_model_id=REVIEW_MODEL_ID,
        review_quantiles=REVIEW_QUANTILES,
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
        no_versioned_incumbent_forecast_artifact_in_repository=(
            NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY
        ),
        frozen_presence_r1_still_reports_fail_closed_no_reviewed_set=(
            FROZEN_PRESENCE_R1_STILL_REPORTS_FAIL_CLOSED_NO_REVIEWED_SET
        ),
        content_producer_on_empty_obtain_returns_none=(
            CONTENT_PRODUCER_ON_EMPTY_OBTAIN_RETURNS_NONE
        ),
        in_memory_catalog_artifact_produced_is_not_versioned_repository_artifact=(
            IN_MEMORY_CATALOG_ARTIFACT_PRODUCED_IS_NOT_VERSIONED_REPOSITORY_ARTIFACT
        ),
        no_versioned_flip_precondition_1_holds=NO_VERSIONED_FLIP_PRECONDITION_1_HOLDS,
        no_versioned_flip_precondition_2_holds=NO_VERSIONED_FLIP_PRECONDITION_2_HOLDS,
        no_versioned_flip_precondition_3_holds=precondition_3_holds,
        no_versioned_flip_precondition_4_holds=NO_VERSIONED_FLIP_PRECONDITION_4_HOLDS,
    )


@dataclass(frozen=True, slots=True)
class IncumbentForecastArtifactContentForReviewedGrainsClassifier:
    def classify(self) -> IncumbentForecastArtifactContentForReviewedGrainsResult:
        presence_result = (
            IncumbentForecastArtifactRepositoryPresenceObservationClassifier().classify()
        )
        clear_v0_2_live_postgres_session_provider()
        loader_empty = load_reviewed_grain_identity_set() == ()
        if presence_result.reason_code is (
            IncumbentForecastArtifactRepositoryPresenceObservationReasonCode.ORIGIN_ENTRIES_NOT_EXACTLY_THREE_POLICY_GRAINS
        ):
            return _companion(
                reason_code=(
                    IncumbentForecastArtifactContentForReviewedGrainsReasonCode.ORIGIN_ENTRIES_NOT_EXACTLY_THREE_POLICY_GRAINS
                ),
                content_recorded=False,
                content_identity_sha256="",
                content_row_count=0,
                exists=False,
                member_count=0,
                identity_sha256="",
                loader_empty=loader_empty,
                precondition_3_holds=False,
            )
        identity_set = load_coordinator_reviewed_live_origin_grain_identity_set()
        replay_rows = _members_to_replay_rows(identity_set.members)
        produced = IncumbentForecastArtifactContentProducer(
            replay_rows=replay_rows,
            declared_catalog_source_kind=(
                CatalogSourceKind.V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF
            ),
            uses_harvest_date_as_forecast_cutoff=False,
        ).produce()
        if produced is None:
            return _companion(
                reason_code=(
                    IncumbentForecastArtifactContentForReviewedGrainsReasonCode.CONTENT_PRODUCER_RETURNED_NONE
                ),
                content_recorded=False,
                content_identity_sha256="",
                content_row_count=0,
                exists=True,
                member_count=presence_result.reviewed_identity_set_member_count,
                identity_sha256=REVIEWED_GRAIN_IDENTITY_SET_IDENTITY_SHA256,
                loader_empty=loader_empty,
                precondition_3_holds=False,
            )
        return _companion(
            reason_code=(
                IncumbentForecastArtifactContentForReviewedGrainsReasonCode.CONTENT_FOR_REVIEWED_GRAINS_RECORDED
            ),
            content_recorded=True,
            content_identity_sha256=produced.content_identity_sha256,
            content_row_count=len(produced.rows),
            exists=True,
            member_count=presence_result.reviewed_identity_set_member_count,
            identity_sha256=REVIEWED_GRAIN_IDENTITY_SET_IDENTITY_SHA256,
            loader_empty=loader_empty,
            precondition_3_holds=True,
        )
