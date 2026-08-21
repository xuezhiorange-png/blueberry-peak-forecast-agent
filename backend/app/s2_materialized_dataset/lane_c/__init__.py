"""Lane C: point-in-time visibility and revision-winner projections."""

from __future__ import annotations

from backend.app.s2_materialized_dataset.lane_c.cutoff import (
    ForecastCutoffValidationError,
    normalize_forecast_cutoff_at,
    validate_forecast_cutoff_context,
)
from backend.app.s2_materialized_dataset.lane_c.persistence import LaneCPersistenceStore
from backend.app.s2_materialized_dataset.lane_c.revision_winner import (
    IDFL_REVISION_WINNER_REQUIRED,
    LATEST_ROW_FALLBACK_ALLOWED,
    REVISION_WINNER_ALGORITHM,
    resolve_revision_winner,
)
from backend.app.s2_materialized_dataset.lane_c.schemas import (
    ForecastCutoffContext,
    LogicalRecordKey,
    PitVisibilityBlockReason,
    PitVisibilityDecision,
    RevisionCandidateRecord,
    RevisionWinnerBlockReason,
    RevisionWinnerDecision,
    RevisionWinnerMode,
    SourceRowIdentity,
    SourceRowLifecycleTimestamps,
)
from backend.app.s2_materialized_dataset.lane_c.visibility import evaluate_pit_visibility

__all__ = [
    "ForecastCutoffContext",
    "ForecastCutoffValidationError",
    "IDFL_REVISION_WINNER_REQUIRED",
    "LATEST_ROW_FALLBACK_ALLOWED",
    "LaneCPersistenceStore",
    "LogicalRecordKey",
    "PitVisibilityBlockReason",
    "PitVisibilityDecision",
    "REVISION_WINNER_ALGORITHM",
    "RevisionCandidateRecord",
    "RevisionWinnerBlockReason",
    "RevisionWinnerDecision",
    "RevisionWinnerMode",
    "SourceRowIdentity",
    "SourceRowLifecycleTimestamps",
    "evaluate_pit_visibility",
    "normalize_forecast_cutoff_at",
    "resolve_revision_winner",
    "validate_forecast_cutoff_context",
]
