"""Observe the already-landed coordinator-reviewed live-origin identity-set.

Calls load_coordinator_reviewed_live_origin_grain_identity_set directly.
Does not auto-wire the global reviewed-set locator at import. Temporary
install happens only inside classify() and is uninstalled in finally.
Does not rewrite frozen closeout, grain-loader, binding, or landing bytes,
invent members, weather, plans, or tonnes, or flip completeness PASS.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_live_postgres_read import (
    clear_v0_2_live_postgres_session_provider,
)
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_replay_identity_grain_identity_set import (
    load_reviewed_grain_identity_set,
)
from backend.app.s3_daily_rowset.s3_a2_coordinator_reviewed_live_origin_grain_identity_set import (
    REVIEW_CUTOFF_AT,
    REVIEW_CUTOFF_BUSINESS_DATE,
    REVIEW_MODEL_ID,
    REVIEW_QUANTILES,
    REVIEWED_GRAIN_IDENTITY_SET_IDENTITY_SHA256,
    install_into_reviewed_set_loader,
    load_coordinator_reviewed_live_origin_grain_identity_set,
    uninstall_from_reviewed_set_loader,
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


class ObservationReasonCode(StrEnum):
    COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_OBSERVED = (
        "COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_OBSERVED"
    )
    ORIGIN_ENTRIES_NOT_EXACTLY_THREE_POLICY_GRAINS = (
        "ORIGIN_ENTRIES_NOT_EXACTLY_THREE_POLICY_GRAINS"
    )


@dataclass(frozen=True, slots=True)
class CoordinatorReviewedLiveOriginGrainIdentitySetObservationResult:
    reason_code: ObservationReasonCode
    coordinator_reviewed_identity_set_exists: bool
    reviewed_identity_set_member_count: int
    reviewed_grain_identity_set_identity_sha256: str
    artifact_available: bool
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


def _clear_construction_cache() -> None:
    from backend.app.s3_daily_rowset import (
        s3_a2_default_catalog_live_origin_construction as construction,
    )

    construction._cached_maker_id = construction._CACHE_MISS
    construction._cached_bundle = None


def _companion(
    *,
    reason_code: ObservationReasonCode,
    exists: bool,
    member_count: int,
    identity_sha256: str,
    artifact_available: bool,
    loader_empty: bool,
) -> CoordinatorReviewedLiveOriginGrainIdentitySetObservationResult:
    return CoordinatorReviewedLiveOriginGrainIdentitySetObservationResult(
        reason_code=reason_code,
        coordinator_reviewed_identity_set_exists=exists,
        reviewed_identity_set_member_count=member_count,
        reviewed_grain_identity_set_identity_sha256=identity_sha256,
        artifact_available=artifact_available,
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
    )


@dataclass(frozen=True, slots=True)
class CoordinatorReviewedLiveOriginGrainIdentitySetObservationClassifier:
    def classify(self) -> CoordinatorReviewedLiveOriginGrainIdentitySetObservationResult:
        artifact = None
        try:
            artifact = load_coordinator_reviewed_live_origin_grain_identity_set()
            if artifact.artifact_available:
                install_into_reviewed_set_loader()
                load_reviewed_grain_identity_set()
        finally:
            uninstall_from_reviewed_set_loader()
            clear_v0_2_live_postgres_session_provider()
            _clear_construction_cache()

        loader_empty = load_reviewed_grain_identity_set() == ()
        if artifact is None or not artifact.artifact_available:
            return _companion(
                reason_code=ObservationReasonCode.ORIGIN_ENTRIES_NOT_EXACTLY_THREE_POLICY_GRAINS,
                exists=False,
                member_count=0,
                identity_sha256="",
                artifact_available=False,
                loader_empty=loader_empty,
            )
        return _companion(
            reason_code=(
                ObservationReasonCode.COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_OBSERVED
            ),
            exists=True,
            member_count=len(artifact.members),
            identity_sha256=REVIEWED_GRAIN_IDENTITY_SET_IDENTITY_SHA256,
            artifact_available=True,
            loader_empty=loader_empty,
        )
