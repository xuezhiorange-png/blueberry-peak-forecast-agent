"""Lane C PIT visibility and revision-winner schemas."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PitVisibilityBlockReason(StrEnum):
    SOURCE_AVAILABLE_MISSING = "SOURCE_AVAILABLE_MISSING"
    SOURCE_AVAILABLE_AFTER_CUTOFF = "SOURCE_AVAILABLE_AFTER_CUTOFF"
    CONTRADICTORY_TIMESTAMPS = "CONTRADICTORY_TIMESTAMPS"
    INDETERMINATE_VISIBILITY = "INDETERMINATE_VISIBILITY"


class RevisionWinnerBlockReason(StrEnum):
    NOT_APPLICABLE_FOR_IDFL_LABEL_SIDE = "NOT_APPLICABLE_FOR_IDFL_LABEL_SIDE"
    NO_VISIBLE_CANDIDATE_AT_CUTOFF = "NO_VISIBLE_CANDIDATE_AT_CUTOFF"
    MULTIPLE_VISIBLE_TERMINALS = "MULTIPLE_VISIBLE_TERMINALS"
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
    cutoff_context: ForecastCutoffContext
    mode: RevisionWinnerMode
    revision_winner_required: bool
    winner_manifest_required: bool
    winner_source_row_identity: SourceRowIdentity | None
    blocked: bool
    no_winner_reason: RevisionWinnerBlockReason | None
    ordered_candidate_identities: tuple[str, ...]
    content_sha256: str


__all__ = [
    "ForecastCutoffContext",
    "LogicalRecordKey",
    "PitVisibilityBlockReason",
    "PitVisibilityDecision",
    "RevisionCandidateRecord",
    "RevisionWinnerBlockReason",
    "RevisionWinnerDecision",
    "RevisionWinnerMode",
    "SourceRowIdentity",
    "SourceRowLifecycleTimestamps",
]
