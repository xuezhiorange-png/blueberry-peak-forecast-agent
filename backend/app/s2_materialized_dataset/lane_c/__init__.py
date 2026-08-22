"""Lane C: point-in-time visibility and revision-winner projections."""

from __future__ import annotations

from backend.app.s2_materialized_dataset.lane_c.cutoff import (
    ForecastCutoffValidationError,
    normalize_forecast_cutoff_at,
    validate_forecast_cutoff_context,
)
from backend.app.s2_materialized_dataset.lane_c.persistence import (
    PIT_CUTOFF_NOT_APPLICABLE_FOR_IDFL_NO_FABRICATION,
    LaneCPersistenceStore,
    Source002E4Result,
    controlled_persist_source_002_idfl_from_environment,
    idfl_null_timestamps,
    persist_idfl_revision_winner_decision,
    resolve_idfl_label_side_pit_status,
)
from backend.app.s2_materialized_dataset.lane_c.revision_winner import (
    IDFL_REVISION_WINNER_REQUIRED,
    LATEST_ROW_FALLBACK_ALLOWED,
    REVISION_WINNER_ALGORITHM,
    resolve_idfl_revision_winner_for_source_row,
    resolve_revision_winner,
)
from backend.app.s2_materialized_dataset.lane_c.schemas import (
    FORECAST_INPUT_VISIBILITY_POLICY_REUSED_FOR_ACTUAL_LABEL,
    IDFL_LABEL_SIDE_POINT_IN_TIME_REPLAY_REQUIRED,
    SOURCE_AVAILABLE_AT_REQUIRED_FOR_IDFL_LABEL_SIDE,
    VISIBILITY_BOUNDARY,
    ForecastCutoffContext,
    IdflLabelSideContext,
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
from backend.app.s2_materialized_dataset.lane_c.visibility import (
    evaluate_idfl_label_side_visibility,
    evaluate_pit_visibility,
)

__all__ = [
    "FORECAST_INPUT_VISIBILITY_POLICY_REUSED_FOR_ACTUAL_LABEL",
    "ForecastCutoffContext",
    "ForecastCutoffValidationError",
    "IDFL_LABEL_SIDE_POINT_IN_TIME_REPLAY_REQUIRED",
    "IDFL_REVISION_WINNER_REQUIRED",
    "IdflLabelSideContext",
    "LATEST_ROW_FALLBACK_ALLOWED",
    "LaneCPersistenceStore",
    "LogicalRecordKey",
    "PIT_CUTOFF_NOT_APPLICABLE_FOR_IDFL_NO_FABRICATION",
    "PitVisibilityBlockReason",
    "PitVisibilityDecision",
    "REVISION_WINNER_ALGORITHM",
    "RevisionCandidateRecord",
    "RevisionWinnerBlockReason",
    "RevisionWinnerDecision",
    "RevisionWinnerMode",
    "SOURCE_AVAILABLE_AT_REQUIRED_FOR_IDFL_LABEL_SIDE",
    "Source002E4Result",
    "SourceRowIdentity",
    "SourceRowLifecycleTimestamps",
    "VISIBILITY_BOUNDARY",
    "controlled_persist_source_002_idfl_from_environment",
    "evaluate_idfl_label_side_visibility",
    "evaluate_pit_visibility",
    "idfl_null_timestamps",
    "normalize_forecast_cutoff_at",
    "persist_idfl_revision_winner_decision",
    "resolve_idfl_label_side_pit_status",
    "resolve_idfl_revision_winner_for_source_row",
    "resolve_revision_winner",
    "validate_forecast_cutoff_context",
]
