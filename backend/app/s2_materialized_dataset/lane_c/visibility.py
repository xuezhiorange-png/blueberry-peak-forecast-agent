"""Point-in-time visibility evaluation for Lane C."""

from __future__ import annotations

from datetime import UTC, datetime

from backend.app.s2_materialized_dataset.lane_c.cutoff import validate_forecast_cutoff_context
from backend.app.s2_materialized_dataset.lane_c.hashes import compute_pit_visibility_content_hash
from backend.app.s2_materialized_dataset.lane_c.schemas import (
    ForecastCutoffContext,
    PitVisibilityBlockReason,
    PitVisibilityDecision,
    SourceRowIdentity,
    SourceRowLifecycleTimestamps,
)


def _is_timezone_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def _timestamps_contain_naive_value(timestamps: SourceRowLifecycleTimestamps) -> bool:
    for value in (
        timestamps.source_recorded_at,
        timestamps.source_available_at,
        timestamps.source_revised_at,
        timestamps.source_finalized_at,
        timestamps.source_cancelled_at,
    ):
        if value is not None and not _is_timezone_aware(value):
            return True
    return False


def _timestamps_are_contradictory(timestamps: SourceRowLifecycleTimestamps) -> bool:
    if timestamps.source_finalized_at is not None and timestamps.source_cancelled_at is not None:
        return True
    if (
        timestamps.source_recorded_at is not None
        and timestamps.source_cancelled_at is not None
        and timestamps.source_cancelled_at < timestamps.source_recorded_at
    ):
        return True
    return False


def _is_cancelled_at_or_before_cutoff(
    *,
    timestamps: SourceRowLifecycleTimestamps,
    cutoff: datetime,
) -> bool:
    if timestamps.source_cancelled_at is None:
        return False
    cancelled_at = timestamps.source_cancelled_at.astimezone(UTC)
    return cancelled_at <= cutoff


def evaluate_pit_visibility(
    *,
    source_row_identity: SourceRowIdentity,
    timestamps: SourceRowLifecycleTimestamps,
    cutoff_context: ForecastCutoffContext,
) -> PitVisibilityDecision:
    validated_context = validate_forecast_cutoff_context(cutoff_context)
    cutoff = validated_context.forecast_cutoff_at

    if _timestamps_contain_naive_value(timestamps):
        return _decision(
            source_row_identity=source_row_identity,
            timestamps=timestamps,
            cutoff_context=validated_context,
            eligible=False,
            blocked=True,
            block_reason=PitVisibilityBlockReason.NAIVE_TIMESTAMP,
        )

    if _timestamps_are_contradictory(timestamps):
        return _decision(
            source_row_identity=source_row_identity,
            timestamps=timestamps,
            cutoff_context=validated_context,
            eligible=False,
            blocked=True,
            block_reason=PitVisibilityBlockReason.CONTRADICTORY_TIMESTAMPS,
        )

    if timestamps.source_available_at is None:
        return _decision(
            source_row_identity=source_row_identity,
            timestamps=timestamps,
            cutoff_context=validated_context,
            eligible=False,
            blocked=True,
            block_reason=PitVisibilityBlockReason.SOURCE_AVAILABLE_MISSING,
        )

    available_at = timestamps.source_available_at.astimezone(UTC)
    if available_at > cutoff:
        return _decision(
            source_row_identity=source_row_identity,
            timestamps=timestamps,
            cutoff_context=validated_context,
            eligible=False,
            blocked=True,
            block_reason=PitVisibilityBlockReason.SOURCE_AVAILABLE_AFTER_CUTOFF,
        )

    if _is_cancelled_at_or_before_cutoff(timestamps=timestamps, cutoff=cutoff):
        return _decision(
            source_row_identity=source_row_identity,
            timestamps=timestamps,
            cutoff_context=validated_context,
            eligible=False,
            blocked=True,
            block_reason=PitVisibilityBlockReason.SOURCE_CANCELLED,
        )

    return _decision(
        source_row_identity=source_row_identity,
        timestamps=timestamps,
        cutoff_context=validated_context,
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


def evaluate_idfl_label_side_visibility(
    *,
    source_row_identity: SourceRowIdentity,
) -> None:
    """IDFL label-side visibility is not point-in-time replayable and has no PIT row."""

    _ = source_row_identity
    return None


__all__ = ["evaluate_idfl_label_side_visibility", "evaluate_pit_visibility"]
