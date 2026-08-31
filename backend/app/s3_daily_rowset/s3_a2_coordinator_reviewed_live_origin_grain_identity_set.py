"""Coordinator-reviewed live-origin grain identity-set artifact.

Members are copied from frozen replay_identity_origin_entries, not harvested
from SOURCE_002. The global reviewed-set locator is not wired at import.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Final

from backend.app.rolling_backtest.canonical import sha256_payload
from backend.app.s3_daily_rowset.incumbent_forecast_replay_identity_origin import (
    replay_identity_origin_entries,
)
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_replay_identity_grain_identity_set import (
    clear_v0_2_reviewed_grain_identity_set_artifact_locator,
    clear_v0_2_reviewed_grain_identity_set_loader,
    set_v0_2_reviewed_grain_identity_set_artifact_locator,
    set_v0_2_reviewed_grain_identity_set_loader,
)
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_replay_identity_grain_row_presence import (
    ReviewedGrainIdentity,
)

REVIEW_MEMBER_COUNT: Final[int] = 3
REVIEW_CUTOFF_AT: Final[str] = "2026-02-16T00:00:00+08:00"
REVIEW_CUTOFF_BUSINESS_DATE: Final[str] = "2026-02-16"
REVIEW_MODEL_ID: Final[str] = "V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF"
REVIEW_QUANTILES: Final[tuple[str, ...]] = ("P50", "P80", "P90")
ORIGIN_ENTRIES_NOT_EXACTLY_THREE_POLICY_GRAINS: Final[str] = (
    "ORIGIN_ENTRIES_NOT_EXACTLY_THREE_POLICY_GRAINS"
)
COORDINATOR_REVIEW_ATTESTATION: Final[str] = (
    "coordinator-reviewed live-origin grain identity-set; "
    "members copied from frozen replay_identity_origin_entries; "
    "not harvested from SOURCE_002; weather and plans deferred"
)
FORBIDDEN_DERIVE_FROM_SOURCE_002: Final[str] = "FORBIDDEN_DERIVE_FROM_SOURCE_002"
FORBIDDEN_INVENT_MEMBERS: Final[str] = "FORBIDDEN_INVENT_MEMBERS"
FORBIDDEN_TREAT_LIVE_ORIGIN_GRAINS_AS_REVIEWED_SET_WITHOUT_THIS_ARTIFACT: Final[str] = (
    "FORBIDDEN_TREAT_LIVE_ORIGIN_GRAINS_AS_REVIEWED_SET_WITHOUT_THIS_ARTIFACT"
)


@dataclass(frozen=True, slots=True)
class CoordinatorReviewedLiveOriginGrainIdentitySetArtifact:
    artifact_id: str
    review_cutoff_business_date: date
    review_cutoff_at: str
    review_model_id: str
    review_quantiles: tuple[str, ...]
    members: tuple[ReviewedGrainIdentity, ...]
    coordinator_review_attestation: str
    artifact_available: bool
    reason_code: str | None = None


def hashable_reviewed_grain_identity_set_payload() -> dict[str, object]:
    return {
        "review_cutoff_business_date": REVIEW_CUTOFF_BUSINESS_DATE,
        "review_cutoff_at": REVIEW_CUTOFF_AT,
        "review_model_id": REVIEW_MODEL_ID,
        "review_quantiles": list(REVIEW_QUANTILES),
        "members": [
            {
                "forecast_cutoff_at": REVIEW_CUTOFF_AT,
                "model_id": REVIEW_MODEL_ID,
                "forecast_quantile": quantile,
            }
            for quantile in REVIEW_QUANTILES
        ],
    }


def reviewed_grain_identity_set_identity_sha256() -> str:
    return sha256_payload(hashable_reviewed_grain_identity_set_payload())


REVIEWED_GRAIN_IDENTITY_SET_IDENTITY_SHA256: Final[str] = (
    reviewed_grain_identity_set_identity_sha256()
)


def _members_from_origin() -> tuple[ReviewedGrainIdentity, ...]:
    return tuple(
        ReviewedGrainIdentity(
            forecast_cutoff_at=entry.forecast_cutoff_at,
            model_id=entry.model_id,
            forecast_quantile=entry.forecast_quantile,
        )
        for entry in replay_identity_origin_entries()
    )


def _is_exact_reviewed_policy_set(members: tuple[ReviewedGrainIdentity, ...]) -> bool:
    if len(members) != REVIEW_MEMBER_COUNT:
        return False
    if tuple(member.forecast_quantile for member in members) != REVIEW_QUANTILES:
        return False
    for member in members:
        if member.forecast_cutoff_at.isoformat() != REVIEW_CUTOFF_AT:
            return False
        if member.model_id != REVIEW_MODEL_ID:
            return False
    return True


def load_coordinator_reviewed_live_origin_grain_identity_set() -> (
    CoordinatorReviewedLiveOriginGrainIdentitySetArtifact
):
    members = _members_from_origin()
    available = _is_exact_reviewed_policy_set(members)
    return CoordinatorReviewedLiveOriginGrainIdentitySetArtifact(
        artifact_id=REVIEWED_GRAIN_IDENTITY_SET_IDENTITY_SHA256 if available else "",
        review_cutoff_business_date=date.fromisoformat(REVIEW_CUTOFF_BUSINESS_DATE),
        review_cutoff_at=REVIEW_CUTOFF_AT,
        review_model_id=REVIEW_MODEL_ID,
        review_quantiles=REVIEW_QUANTILES,
        members=members if available else (),
        coordinator_review_attestation=COORDINATOR_REVIEW_ATTESTATION,
        artifact_available=available,
        reason_code=None if available else ORIGIN_ENTRIES_NOT_EXACTLY_THREE_POLICY_GRAINS,
    )


def _artifact_locator() -> bool:
    return load_coordinator_reviewed_live_origin_grain_identity_set().artifact_available


def _identity_set_loader() -> tuple[ReviewedGrainIdentity, ...]:
    artifact = load_coordinator_reviewed_live_origin_grain_identity_set()
    if not artifact.artifact_available:
        return ()
    return artifact.members


def install_into_reviewed_set_loader() -> None:
    """Wire this artifact into the existing reviewed-set loader. Not called at import."""
    set_v0_2_reviewed_grain_identity_set_artifact_locator(_artifact_locator)
    set_v0_2_reviewed_grain_identity_set_loader(_identity_set_loader)


def uninstall_from_reviewed_set_loader() -> None:
    clear_v0_2_reviewed_grain_identity_set_artifact_locator()
    clear_v0_2_reviewed_grain_identity_set_loader()
