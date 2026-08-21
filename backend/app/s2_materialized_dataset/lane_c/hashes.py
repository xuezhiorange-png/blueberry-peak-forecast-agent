"""Lane C canonical hash helpers for PIT visibility and revision winner."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from backend.app.rolling_backtest.canonical import sha256_payload
from backend.app.s2_materialized_dataset.lane_c.schemas import (
    ForecastCutoffContext,
    LogicalRecordKey,
    RevisionCandidateRecord,
    SourceRowIdentity,
    SourceRowLifecycleTimestamps,
)

VISIBILITY_HASH_POLICY_VERSION = "v0-3-s2-pit-visibility-hash-v1"
REVISION_WINNER_HASH_POLICY_VERSION = "v0-3-s2-revision-winner-hash-v1"


def _canonical_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.isoformat()


def _timestamps_payload(timestamps: SourceRowLifecycleTimestamps) -> dict[str, str | None]:
    return {
        "source_recorded_at": _canonical_datetime(timestamps.source_recorded_at),
        "source_available_at": _canonical_datetime(timestamps.source_available_at),
        "source_revised_at": _canonical_datetime(timestamps.source_revised_at),
        "source_finalized_at": _canonical_datetime(timestamps.source_finalized_at),
        "source_cancelled_at": _canonical_datetime(timestamps.source_cancelled_at),
    }


def _source_row_identity_payload(identity: SourceRowIdentity) -> dict[str, Any]:
    return {
        "source_row_identity_hash": identity.source_row_identity_hash,
        "source_system": identity.source_system,
        "external_logical_record_id": identity.external_logical_record_id,
        "external_revision_id": identity.external_revision_id,
        "revision_number": identity.revision_number,
        "raw_source_artifact_identity_hash": identity.raw_source_artifact_identity_hash,
        "raw_import_batch_identity_hash": identity.raw_import_batch_identity_hash,
    }


def compute_pit_visibility_content_hash(
    *,
    source_row_identity: SourceRowIdentity,
    timestamps: SourceRowLifecycleTimestamps,
    cutoff_context: ForecastCutoffContext,
    eligible: bool,
    blocked: bool,
    block_reason: str | None,
) -> str:
    payload = {
        "policy_version": VISIBILITY_HASH_POLICY_VERSION,
        "source_row_identity": _source_row_identity_payload(source_row_identity),
        "timestamps": _timestamps_payload(timestamps),
        "forecast_cutoff_at": _canonical_datetime(cutoff_context.forecast_cutoff_at),
        "visibility_policy_version": cutoff_context.visibility_policy_version,
        "visibility_schema_version": cutoff_context.visibility_schema_version,
        "forecast_cutoff_identity_version": cutoff_context.forecast_cutoff_identity_version,
        "eligible": eligible,
        "blocked": blocked,
        "block_reason": block_reason,
    }
    return sha256_payload(payload)


def _candidate_sort_key(candidate: RevisionCandidateRecord) -> tuple[int, str, str]:
    return (
        candidate.source_row_identity.revision_number,
        candidate.source_row_identity.external_revision_id,
        candidate.source_row_identity.source_row_identity_hash,
    )


def ordered_candidate_identity_hashes(
    candidates: Sequence[RevisionCandidateRecord],
) -> tuple[str, ...]:
    ordered = sorted(candidates, key=_candidate_sort_key)
    return tuple(item.source_row_identity.source_row_identity_hash for item in ordered)


def compute_revision_winner_content_hash(
    *,
    logical_record_key: LogicalRecordKey,
    cutoff_context: ForecastCutoffContext,
    ordered_candidate_identities: Sequence[str],
    winner_source_row_identity_hash: str | None,
    blocked: bool,
    no_winner_reason: str | None,
    mode: str,
) -> str:
    payload = {
        "policy_version": REVISION_WINNER_HASH_POLICY_VERSION,
        "logical_record_key": {
            "source_system": logical_record_key.source_system,
            "external_logical_record_id": logical_record_key.external_logical_record_id,
        },
        "forecast_cutoff_at": _canonical_datetime(cutoff_context.forecast_cutoff_at),
        "revision_winner_policy_version": cutoff_context.revision_winner_policy_version,
        "revision_schema_version": cutoff_context.revision_schema_version,
        "visibility_policy_version": cutoff_context.visibility_policy_version,
        "mode": mode,
        "ordered_revision_candidate_identities": list(ordered_candidate_identities),
        "winner_source_row_identity_hash": winner_source_row_identity_hash,
        "blocked": blocked,
        "no_winner_reason": no_winner_reason,
    }
    return sha256_payload(payload)


__all__ = [
    "REVISION_WINNER_HASH_POLICY_VERSION",
    "VISIBILITY_HASH_POLICY_VERSION",
    "compute_pit_visibility_content_hash",
    "compute_revision_winner_content_hash",
    "ordered_candidate_identity_hashes",
]
