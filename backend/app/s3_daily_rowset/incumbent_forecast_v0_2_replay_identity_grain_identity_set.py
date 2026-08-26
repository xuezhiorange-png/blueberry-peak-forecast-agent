"""S3-A2 incumbent forecast V0.2 replay-identity grain identity-set loader fail-closed."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_replay_identity_grain_row_presence import (
    ReviewedGrainIdentity,
    ReviewedGrainIdentitySetProvider,
)

ReviewedGrainIdentitySetArtifactLocator = Callable[[], bool]
ReviewedGrainIdentitySetLoader = Callable[[], tuple[ReviewedGrainIdentity, ...]]

_artifact_locator: ReviewedGrainIdentitySetArtifactLocator | None = None
_identity_set_loader: ReviewedGrainIdentitySetLoader | None = None


def set_v0_2_reviewed_grain_identity_set_artifact_locator(
    locator: ReviewedGrainIdentitySetArtifactLocator | None,
) -> None:
    global _artifact_locator
    _artifact_locator = locator


def clear_v0_2_reviewed_grain_identity_set_artifact_locator() -> None:
    set_v0_2_reviewed_grain_identity_set_artifact_locator(None)


def set_v0_2_reviewed_grain_identity_set_loader(
    loader: ReviewedGrainIdentitySetLoader | None,
) -> None:
    global _identity_set_loader
    _identity_set_loader = loader


def clear_v0_2_reviewed_grain_identity_set_loader() -> None:
    set_v0_2_reviewed_grain_identity_set_loader(None)


def reviewed_grain_identity_set_artifact_available() -> bool:
    if _artifact_locator is None:
        return False
    try:
        return _artifact_locator()
    except Exception:
        return False


def load_reviewed_grain_identity_set() -> tuple[ReviewedGrainIdentity, ...]:
    if not reviewed_grain_identity_set_artifact_available():
        return ()
    if _identity_set_loader is None:
        return ()
    try:
        loaded = _identity_set_loader()
    except Exception:
        return ()
    return _validated_members(loaded)


def grain_row_presence_reviewed_set_provider() -> ReviewedGrainIdentitySetProvider:
    return load_reviewed_grain_identity_set


def _validated_members(
    loaded: tuple[ReviewedGrainIdentity, ...] | None,
) -> tuple[ReviewedGrainIdentity, ...]:
    if not loaded:
        return ()
    validated: list[ReviewedGrainIdentity] = []
    for member in loaded:
        if not isinstance(member, ReviewedGrainIdentity):
            return ()
        cutoff = member.forecast_cutoff_at
        if not isinstance(cutoff, datetime):
            return ()
        if cutoff.tzinfo is None or cutoff.utcoffset() is None:
            return ()
        if not member.model_id or not member.forecast_quantile:
            return ()
        validated.append(member)
    return tuple(validated)
