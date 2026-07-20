"""I7 label-snapshot package.

The package owns the immutable snapshot header + winner / label /
exclusion persistence and the deterministic processing pipeline that
maps the committed source universe to canonical-grain label rows. It
contains no I/O outside the caller's transaction: every helper is pure
or accepts a SQLAlchemy session that the caller owns.

Frozen contract:
- docs/forecast-quality/q2a-i7-label-snapshot-and-revision-winner-contract.md
"""

from __future__ import annotations

from backend.app.actual_harvest_labels.enums import (
    ActualHarvestLabelCoverageExclusion,
    ActualHarvestLabelStructuralFailure,
    ActualHarvestLabelVisibilityMode,
)
from backend.app.actual_harvest_labels.hashes import (
    AGGREGATION_POLICY_VERSION,
    INSTANCE_HASH_POLICY_VERSION,
    REQUEST_HASH_POLICY_VERSION,
    SNAPSHOT_HASH_POLICY_VERSION,
    SNAPSHOT_POLICY_VERSION,
    WINNER_POLICY_VERSION,
    compute_exclusion_manifest_hash,
    compute_exclusion_row_hash,
    compute_label_row_hash,
    compute_label_row_set_hash,
    compute_label_snapshot_hash,
    compute_snapshot_instance_identity_hash,
    compute_snapshot_request_identity_hash,
    compute_source_commit_manifest_set_hash,
    compute_winner_manifest_hash,
    compute_winner_row_hash,
)
from backend.app.actual_harvest_labels.models import (
    EXCLUSION_TABLE_NAME,
    HEADER_TABLE_NAME,
    LABEL_TABLE_NAME,
    WINNER_TABLE_NAME,
    ActualHarvestLabelSnapshotExclusionModel,
    ActualHarvestLabelSnapshotLabelModel,
    ActualHarvestLabelSnapshotModel,
    ActualHarvestLabelSnapshotWinnerModel,
)
from backend.app.actual_harvest_labels.schemas import (
    ActualHarvestExclusionRow,
    ActualHarvestLabelRow,
    ActualHarvestLabelSnapshotHeader,
    ActualHarvestLabelSnapshotRequest,
    ActualHarvestLabelSnapshotResult,
    ActualHarvestWinnerRow,
)

# The service module is imported lazily via ``__getattr__`` to avoid a
# circular import at package load time. The service pulls in
# ``backend.app.actual_harvest_import.*`` and ``backend.app.models.*``,
# both of which can themselves re-enter package initialisation. Callers
# that need the service entry points should import them directly from
# ``backend.app.actual_harvest_labels.service``.


def __getattr__(name: str):  # type: ignore[no-untyped-def]
    if name in (
        "ActualHarvestLabelSnapshotReplay",
        "create_label_snapshot",
        "get_existing_snapshot_by_idempotency_key",
    ):
        from backend.app.actual_harvest_labels import service as _service

        return getattr(_service, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "AGGREGATION_POLICY_VERSION",
    "EXCLUSION_TABLE_NAME",
    "HEADER_TABLE_NAME",
    "INSTANCE_HASH_POLICY_VERSION",
    "LABEL_TABLE_NAME",
    "REQUEST_HASH_POLICY_VERSION",
    "SNAPSHOT_HASH_POLICY_VERSION",
    "SNAPSHOT_POLICY_VERSION",
    "WINNER_TABLE_NAME",
    "WINNER_POLICY_VERSION",
    "ActualHarvestExclusionRow",
    "ActualHarvestLabelCoverageExclusion",
    "ActualHarvestLabelRow",
    "ActualHarvestLabelSnapshotExclusionModel",
    "ActualHarvestLabelSnapshotHeader",
    "ActualHarvestLabelSnapshotLabelModel",
    "ActualHarvestLabelSnapshotModel",
    "ActualHarvestLabelSnapshotReplay",
    "ActualHarvestLabelSnapshotRequest",
    "ActualHarvestLabelSnapshotResult",
    "ActualHarvestLabelSnapshotWinnerModel",
    "ActualHarvestLabelStructuralFailure",
    "ActualHarvestLabelVisibilityMode",
    "ActualHarvestWinnerRow",
    "compute_exclusion_manifest_hash",
    "compute_exclusion_row_hash",
    "compute_label_row_hash",
    "compute_label_row_set_hash",
    "compute_label_snapshot_hash",
    "compute_snapshot_instance_identity_hash",
    "compute_snapshot_request_identity_hash",
    "compute_source_commit_manifest_set_hash",
    "compute_winner_manifest_hash",
    "compute_winner_row_hash",
    "create_label_snapshot",
    "get_existing_snapshot_by_idempotency_key",
]
