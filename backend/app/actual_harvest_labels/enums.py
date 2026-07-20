"""I7 label-snapshot enums.

Frozen contract:
- backend/app/actual_harvest_labels/__init__.py
- docs/forecast-quality/q2a-i7-label-snapshot-and-revision-winner-contract.md
"""

from __future__ import annotations

from enum import StrEnum


class ActualHarvestLabelVisibilityMode(StrEnum):
    """How a snapshot interprets the committed source universe at cutoff time.

    The two modes are mutually exclusive for one snapshot and freeze the
    rules in contract sections §7 (AS_OF_EVALUATION) and §7.2
    (FINAL_ADJUDICATED).
    """

    AS_OF_EVALUATION = "AS_OF_EVALUATION"
    FINAL_ADJUDICATED = "FINAL_ADJUDICATED"


class ActualHarvestLabelStructuralFailure(StrEnum):
    """Snapshot-level structural failures (frozen contract §15).

    Each value halts the complete snapshot creation. None is downgraded
    to a coverage exclusion.
    """

    SOURCE_EVIDENCE_DRIFT = "SOURCE_EVIDENCE_DRIFT"
    MAPPING_EVIDENCE_MISSING = "MAPPING_EVIDENCE_MISSING"
    MAPPING_EVIDENCE_DRIFT = "MAPPING_EVIDENCE_DRIFT"
    MISSING_SUPERSEDED_PARENT = "MISSING_SUPERSEDED_PARENT"
    VISIBLE_CHILD_WITH_INVISIBLE_PARENT = "VISIBLE_CHILD_WITH_INVISIBLE_PARENT"
    SUPERSESSION_CHAIN_FORK = "SUPERSESSION_CHAIN_FORK"
    SUPERSESSION_CHAIN_CYCLE = "SUPERSESSION_CHAIN_CYCLE"
    REVISION_NUMBER_DISCONTINUITY = "REVISION_NUMBER_DISCONTINUITY"
    MULTIPLE_VISIBLE_TERMINAL_REVISIONS = "MULTIPLE_VISIBLE_TERMINAL_REVISIONS"
    CORRECTED_WITHOUT_SUCCESSOR = "CORRECTED_WITHOUT_SUCCESSOR"
    FINALIZED_HAS_SUCCESSOR = "FINALIZED_HAS_SUCCESSOR"
    VOID_HAS_SUCCESSOR = "VOID_HAS_SUCCESSOR"
    FINALIZED_AT_REQUIRED = "FINALIZED_AT_REQUIRED"
    SOURCE_SYSTEM_SCOPE_CONFLICT = "SOURCE_SYSTEM_SCOPE_CONFLICT"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    UNSUPPORTED_LABEL_GRAIN = "UNSUPPORTED_LABEL_GRAIN"


class ActualHarvestLabelCoverageExclusion(StrEnum):
    """Coverage exclusions (frozen contract §16).

    Each value allows the snapshot to succeed while reporting the row.
    Lineage corruption must NEVER appear here.
    """

    SOURCE_TIME_UNTRUSTED = "SOURCE_TIME_UNTRUSTED"
    SOURCE_TIME_MISSING = "SOURCE_TIME_MISSING"
    SOURCE_TIME_AFTER_CUTOFF = "SOURCE_TIME_AFTER_CUTOFF"
    NO_VISIBLE_REVISION_AT_CUTOFF = "NO_VISIBLE_REVISION_AT_CUTOFF"
    TERMINAL_VOID = "TERMINAL_VOID"
    STATUS_NOT_VISIBLE_AT_CUTOFF = "STATUS_NOT_VISIBLE_AT_CUTOFF"
    OUTSIDE_REQUEST_SCOPE = "OUTSIDE_REQUEST_SCOPE"


__all__ = [
    "ActualHarvestLabelCoverageExclusion",
    "ActualHarvestLabelStructuralFailure",
    "ActualHarvestLabelVisibilityMode",
]
