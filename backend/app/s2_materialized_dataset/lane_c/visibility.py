"""Point-in-time visibility evaluation for Lane C."""

from __future__ import annotations

from backend.app.s2_materialized_dataset.lane_c.cutoff import normalize_forecast_cutoff_at
from backend.app.s2_materialized_dataset.lane_c.hashes import compute_pit_visibility_content_hash
from backend.app.s2_materialized_dataset.lane_c.schemas import (
    ForecastCutoffContext,
    PitVisibilityBlockReason,
    PitVisibilityDecision,
    SourceRowIdentity,
    SourceRowLifecycleTimestamps,
)


def _timestamps_are_contradictory(timestamps: SourceRowLifecycleTimestamps) -> bool:
    if timestamps.source_finalized_at is not None and timestamps.source_cancelled_at is not None:
        return True
    if (
        timestamps.source_recorded_at is not None
        and timestamps.source_cancelled_at is not None
        and timestamps.source_cancelled_at < timestamps.source_recorded_at
    ):
        return True
    if (
        timestamps.source_available_at is not None
        and timestamps.source_revised_at is not None
        and timestamps.source_revised_at > timestamps.source_available_at
    ):
        return True
    return False


def evaluate_pit_visibility(
    *,
    source_row_identity: SourceRowIdentity,
    timestamps: SourceRowLifecycleTimestamps,
    cutoff_context: ForecastCutoffContext,
) -> PitVisibilityDecision:
    cutoff = normalize_forecast_cutoff_at(cutoff_context.forecast_cutoff_at)

    if _timestamps_are_contradictory(timestamps):
        return _decision(
            source_row_identity=source_row_identity,
            timestamps=timestamps,
            cutoff_context=cutoff_context,
            eligible=False,
            blocked=True,
            block_reason=PitVisibilityBlockReason.CONTRADICTORY_TIMESTAMPS,
        )

    if timestamps.source_available_at is None:
        return _decision(
            source_row_identity=source_row_identity,
            timestamps=timestamps,
            cutoff_context=cutoff_context,
            eligible=False,
            blocked=True,
            block_reason=PitVisibilityBlockReason.SOURCE_AVAILABLE_MISSING,
        )

    available_at = normalize_forecast_cutoff_at(timestamps.source_available_at)
    if available_at > cutoff:
        return _decision(
            source_row_identity=source_row_identity,
            timestamps=timestamps,
            cutoff_context=cutoff_context,
            eligible=False,
            blocked=True,
            block_reason=PitVisibilityBlockReason.SOURCE_AVAILABLE_AFTER_CUTOFF,
        )

    return _decision(
        source_row_identity=source_row_identity,
        timestamps=timestamps,
        cutoff_context=cutoff_context,
        eligible=True,
        blocked=False,
        block_reason=None,
    )


def _decision(
    *,
    source_row_identity: SourceRowIdentity,
    timestamps: SourceRowLifecycleTimestamps,
    cutoff_context: ForecastCutoffContext,
    eligible: bool,
    blocked: bool,
    block_reason: PitVisibilityBlockReason | None,
) -> PitVisibilityDecision:
    content_sha256 = compute_pit_visibility_content_hash(
        source_row_identity=source_row_identity,
        timestamps=timestamps,
        cutoff_context=cutoff_context,
        eligible=eligible,
        blocked=blocked,
        block_reason=None if block_reason is None else block_reason.value,
    )
    return PitVisibilityDecision(
        source_row_identity=source_row_identity,
        timestamps=timestamps,
        cutoff_context=cutoff_context,
        eligible=eligible,
        blocked=blocked,
        block_reason=block_reason,
        content_sha256=content_sha256,
    )


__all__ = ["evaluate_pit_visibility"]
