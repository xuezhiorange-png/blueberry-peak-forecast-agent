"""Synthetic Lane C fixtures that do not depend on unmerged Lane A/B code."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from backend.app.s2_materialized_dataset.lane_c.schemas import (
    ForecastCutoffContext,
    LogicalRecordKey,
    RevisionCandidateRecord,
    SourceRowIdentity,
    SourceRowLifecycleTimestamps,
)


def _dt(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


@pytest.fixture
def forecast_cutoff() -> datetime:
    return _dt("2026-02-28T12:00:00Z")


@pytest.fixture
def cutoff_context(forecast_cutoff: datetime) -> ForecastCutoffContext:
    return ForecastCutoffContext(forecast_cutoff_at=forecast_cutoff)


@pytest.fixture
def synthetic_source_row_identity() -> SourceRowIdentity:
    return SourceRowIdentity(
        source_row_identity_hash="a" * 64,
        source_system="synthetic-scan-weight",
        external_logical_record_id="LR-001",
        external_revision_id="REV-001",
        revision_number=1,
        raw_source_artifact_identity_hash="b" * 64,
        raw_import_batch_identity_hash="c" * 64,
    )


def make_timestamps(**overrides: datetime | None) -> SourceRowLifecycleTimestamps:
    defaults: dict[str, datetime | None] = {
        "source_recorded_at": _dt("2026-02-27T08:00:00Z"),
        "source_available_at": _dt("2026-02-27T09:00:00Z"),
        "source_revised_at": None,
        "source_finalized_at": None,
        "source_cancelled_at": None,
    }
    defaults.update(overrides)
    return SourceRowLifecycleTimestamps(**defaults)


def make_revision_candidate(
    *,
    logical_record_id: str,
    revision_id: str,
    revision_number: int,
    identity_hash: str,
    timestamps: SourceRowLifecycleTimestamps,
    record_status: str = "ACTIVE",
    supersedes_external_revision_id: str | None = None,
    finalized_at: datetime | None = None,
) -> RevisionCandidateRecord:
    return RevisionCandidateRecord(
        logical_record_key=LogicalRecordKey(
            source_system="synthetic-scan-weight",
            external_logical_record_id=logical_record_id,
        ),
        source_row_identity=SourceRowIdentity(
            source_row_identity_hash=identity_hash,
            source_system="synthetic-scan-weight",
            external_logical_record_id=logical_record_id,
            external_revision_id=revision_id,
            revision_number=revision_number,
            raw_source_artifact_identity_hash="b" * 64,
            raw_import_batch_identity_hash="c" * 64,
        ),
        timestamps=timestamps,
        record_status=record_status,
        supersedes_external_revision_id=supersedes_external_revision_id,
        finalized_at_or_null=finalized_at,
    )


@pytest.fixture
def revision_candidate_factory() -> Any:
    return make_revision_candidate
