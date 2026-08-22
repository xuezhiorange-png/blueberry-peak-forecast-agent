"""Lane C PIT visibility and revision-winner schemas."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

IDFL_LABEL_SIDE_POINT_IN_TIME_REPLAY_REQUIRED = False
SOURCE_AVAILABLE_AT_REQUIRED_FOR_IDFL_LABEL_SIDE = False
FORECAST_INPUT_VISIBILITY_POLICY_REUSED_FOR_ACTUAL_LABEL = False
VISIBILITY_BOUNDARY = (
    "NOT_POINT_IN_TIME_REPLAYABLE_FOR_IDFL_LABEL_SIDE;"
    " SOURCE_OBJECT_COMPLETENESS_AUTHORITY_REQUIRED;"
    " SOURCE_OBJECT_BOUND_ROW_LINEAGE_REQUIRED;"
    " FORECAST_INPUT_VISIBILITY_DOMAIN_SEPARATE"
)


class PitVisibilityBlockReason(StrEnum):
    SOURCE_AVAILABLE_MISSING = "SOURCE_AVAILABLE_MISSING"
    SOURCE_AVAILABLE_AFTER_CUTOFF = "SOURCE_AVAILABLE_AFTER_CUTOFF"
    SOURCE_CANCELLED = "SOURCE_CANCELLED"
    CONTRADICTORY_TIMESTAMPS = "CONTRADICTORY_TIMESTAMPS"
    NAIVE_TIMESTAMP = "NAIVE_TIMESTAMP"
    INDETERMINATE_VISIBILITY = "INDETERMINATE_VISIBILITY"


class RevisionWinnerBlockReason(StrEnum):
    NOT_APPLICABLE_FOR_IDFL_LABEL_SIDE = "NOT_APPLICABLE_FOR_IDFL_LABEL_SIDE"
    NO_VISIBLE_CANDIDATE_AT_CUTOFF = "NO_VISIBLE_CANDIDATE_AT_CUTOFF"
    MULTIPLE_VISIBLE_TERMINALS = "MULTIPLE_VISIBLE_TERMINALS"
    DUPLICATE_REVISION_CANDIDATE_IDENTITY = "DUPLICATE_REVISION_CANDIDATE_IDENTITY"
    CONTRADICTORY_EVIDENCE = "CONTRADICTORY_EVIDENCE"
    NO_WINNER = "NO_WINNER"


class RevisionWinnerMode(StrEnum):
    IDFL_LABEL_SIDE = "IDFL_LABEL_SIDE"
    REPLAY_REVISION_GRAPH = "REPLAY_REVISION_GRAPH"


class SourceRowIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_row_identity_hash: str = Field(min_length=64, max_length=64)
    source_system: str = Field(min_length=1)
    external_logical_record_id: str = Field(min_length=1)
    external_revision_id: str = Field(min_length=1)
    revision_number: int = Field(ge=1)
    raw_source_artifact_identity_hash: str = Field(min_length=64, max_length=64)
    raw_import_batch_identity_hash: str = Field(min_length=64, max_length=64)

    @field_validator(
        "source_row_identity_hash",
        "raw_source_artifact_identity_hash",
        "raw_import_batch_identity_hash",
    )
    @classmethod
    def _validate_sha256(cls, value: str) -> str:
        if value.lower() != value or any(
            character not in "0123456789abcdef" for character in value
        ):
            raise ValueError("hash must be lowercase sha256 hex")
        return value


class SourceRowLifecycleTimestamps(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_recorded_at: datetime | None
    source_available_at: datetime | None
    source_revised_at: datetime | None
    source_finalized_at: datetime | None
    source_cancelled_at: datetime | None


class ForecastCutoffContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    forecast_cutoff_at: datetime
    visibility_policy_version: str = "v0-3-s2-pit-visibility-v1"
    visibility_schema_version: str = "v0-3-s2-pit-visibility-schema-v1"
    forecast_cutoff_identity_version: str = "v0-3-s2-forecast-cutoff-identity-v1"
    revision_winner_policy_version: str = "v0-3-s2-revision-winner-v1"
    revision_schema_version: str = "v0-3-s2-revision-schema-v1"


class IdflLabelSideContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    visibility_policy_version: str = "v0-3-s2-idfl-label-side-visibility-v1"
    visibility_schema_version: str = "v0-3-s2-idfl-label-side-visibility-schema-v1"
    forecast_cutoff_identity_version: str = "v0-3-s2-idfl-forecast-cutoff-not-applicable-v1"
    revision_winner_policy_version: str = "v0-3-s2-idfl-revision-winner-v1"
    revision_schema_version: str = "v0-3-s2-idfl-revision-schema-v1"
    visibility_boundary: str = VISIBILITY_BOUNDARY


class LogicalRecordKey(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_system: str = Field(min_length=1)
    external_logical_record_id: str = Field(min_length=1)


class RevisionCandidateRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    logical_record_key: LogicalRecordKey
    source_row_identity: SourceRowIdentity
    timestamps: SourceRowLifecycleTimestamps
    record_status: str
    supersedes_external_revision_id: str | None
    finalized_at_or_null: datetime | None = None


class PitVisibilityDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_row_identity: SourceRowIdentity
    timestamps: SourceRowLifecycleTimestamps
    cutoff_context: ForecastCutoffContext
    eligible: bool
    blocked: bool
    block_reason: PitVisibilityBlockReason | None
    content_sha256: str


class RevisionWinnerDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    logical_record_key: LogicalRecordKey
    source_row_identity: SourceRowIdentity | None = None
    timestamps: SourceRowLifecycleTimestamps | None = None
    cutoff_context: ForecastCutoffContext | None = None
    idfl_label_side_context: IdflLabelSideContext | None = None
    mode: RevisionWinnerMode
    revision_winner_required: bool
    winner_manifest_required: bool
    winner_source_row_identity: SourceRowIdentity | None
    blocked: bool
    no_winner_reason: RevisionWinnerBlockReason | None
    ordered_candidate_identities: tuple[str, ...]
    content_sha256: str

    @model_validator(mode="after")
    def _validate_context_by_mode(self) -> RevisionWinnerDecision:
        if self.mode is RevisionWinnerMode.IDFL_LABEL_SIDE:
            if self.cutoff_context is not None:
                raise ValueError("IDFL_LABEL_SIDE decisions must not carry forecast cutoff context")
            if self.idfl_label_side_context is None:
                raise ValueError("IDFL_LABEL_SIDE decisions require idfl_label_side_context")
            return self
        if self.idfl_label_side_context is not None:
            raise ValueError("replay decisions must not carry idfl_label_side_context")
        if self.cutoff_context is None:
            raise ValueError("replay decisions require cutoff_context")
        return self


__all__ = [
    "FORECAST_INPUT_VISIBILITY_POLICY_REUSED_FOR_ACTUAL_LABEL",
    "ForecastCutoffContext",
    "IdflLabelSideContext",
    "IDFL_LABEL_SIDE_POINT_IN_TIME_REPLAY_REQUIRED",
    "LogicalRecordKey",
    "PitVisibilityBlockReason",
    "PitVisibilityDecision",
    "RevisionCandidateRecord",
    "RevisionWinnerBlockReason",
    "RevisionWinnerDecision",
    "RevisionWinnerMode",
    "SOURCE_AVAILABLE_AT_REQUIRED_FOR_IDFL_LABEL_SIDE",
    "SourceRowIdentity",
    "SourceRowLifecycleTimestamps",
    "VISIBILITY_BOUNDARY",
]
