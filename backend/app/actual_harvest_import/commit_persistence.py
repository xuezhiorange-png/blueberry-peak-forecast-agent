"""S1 commit persistence helpers.

All operations are PURE — they MUST NOT call session.commit() or
session.rollback(). Transaction ownership stays with the API route's
caller-owned transaction boundary (per S1 §六).

Frozen contract:
- Single transaction
- No background worker
- No attempt ledger, no lease, no heartbeat, no fencing
- INSERT-only on actual_harvest_commit_manifest
- UPDATE / DELETE blocked by trigger (immutability)
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.actual_harvest_import.commit_models import (
    COMMIT_POLICY_VERSION,
    ActualHarvestCommitManifestModel,
)
from backend.app.actual_harvest_import.models import ActualHarvestImportBatchModel
from backend.app.actual_harvest_import.validation_models import (
    ActualHarvestMappingSnapshotModel,
    ActualHarvestValidationResultModel,
    ActualHarvestValidationRunModel,
)


async def get_batch_for_update(
    session: AsyncSession, import_id: str
) -> ActualHarvestImportBatchModel | None:
    """SELECT ... FOR UPDATE the import batch by import_id.

    Returns None if the batch does not exist. Caller is responsible for
    raising IMPORT_BATCH_NOT_FOUND with concealment semantics.
    """
    from sqlalchemy.orm import selectinload

    result = await session.execute(
        select(ActualHarvestImportBatchModel)
        .where(ActualHarvestImportBatchModel.import_id == import_id)
        .options(selectinload(ActualHarvestImportBatchModel.records))
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def get_current_validation_run(
    session: AsyncSession, batch_id: int
) -> ActualHarvestValidationRunModel | None:
    """Return the unique current VALIDATED validation run for a batch."""
    result = await session.execute(
        select(ActualHarvestValidationRunModel).where(
            ActualHarvestValidationRunModel.batch_id == batch_id,
            ActualHarvestValidationRunModel.is_current.is_(True),
            ActualHarvestValidationRunModel.status == "VALIDATED",
        )
    )
    return result.scalar_one_or_none()


async def get_validation_result(
    session: AsyncSession, validation_run_id: int
) -> ActualHarvestValidationResultModel | None:
    result = await session.execute(
        select(ActualHarvestValidationResultModel).where(
            ActualHarvestValidationResultModel.validation_run_id == validation_run_id
        )
    )
    return result.scalar_one_or_none()


async def get_mapping_snapshot(
    session: AsyncSession, validation_run_id: int
) -> ActualHarvestMappingSnapshotModel | None:
    """Return the unique mapping snapshot for the given validation run.

    Per S1 §六 step 7.6, every required evidence hash on the snapshot
    must match the corresponding hash on the validation run before a
    commit can proceed. The cross-check is performed in
    `commit_service.commit_batch`; this helper only fetches the row.
    """
    result = await session.execute(
        select(ActualHarvestMappingSnapshotModel).where(
            ActualHarvestMappingSnapshotModel.validation_run_id == validation_run_id
        )
    )
    return result.scalar_one_or_none()


async def get_existing_commit_manifest(
    session: AsyncSession, batch_id: int
) -> ActualHarvestCommitManifestModel | None:
    """Return the (at most one) existing commit manifest for this batch.

    Because UNIQUE(batch_id), there can be at most one such row.
    """
    result = await session.execute(
        select(ActualHarvestCommitManifestModel).where(
            ActualHarvestCommitManifestModel.batch_id == batch_id
        )
    )
    return result.scalar_one_or_none()


async def list_batch_records(
    session: AsyncSession, batch_id: int
) -> Sequence[ActualHarvestImportBatchModel]:
    """Return the batch's existing import records (the source revisions).

    The actual `records` collection is loaded via the relationship; this
    helper is a thin shim that triggers a fresh SELECT so the order returned
    by caller is deterministic.
    """
    result = await session.execute(
        select(ActualHarvestImportBatchModel).where(ActualHarvestImportBatchModel.id == batch_id)
    )
    batch = result.scalar_one_or_none()
    if batch is None:
        return ()
    # Force load via the relationship
    await session.refresh(batch, attribute_names=["records"])
    return batch.records  # type: ignore[return-value]


def build_commit_manifest(
    *,
    batch: ActualHarvestImportBatchModel,
    validation_run: ActualHarvestValidationRunModel,
    validation_result: ActualHarvestValidationResultModel,
    commit_manifest_hash: str,
    committed_by_identity: str,
    committed_at: datetime,
    committed_record_count: int,
    seal_manifest_hash: str,
    canonical_batch_hash: str,
    record_manifest_hash: str,
    validation_result_hash: str,
    mapping_snapshot_hash: str,
    resolved_identity_snapshot_hash: str,
    lineage_graph_hash: str,
    committed_lineage_basis_hash: str,
    registry_content_hash: str,
) -> ActualHarvestCommitManifestModel:
    """Assemble the immutable commit-manifest row from the validated inputs.

    The caller is responsible for INSERTING this row inside the caller-owned
    transaction. The persistence layer does not commit. All evidence-hash
    parameters are typed as `str` because the caller (commit_service) is
    responsible for narrowing them via `_require_evidence_hash` immediately
    after loading the Optional ORM properties.
    """
    del validation_result  # already validated by caller; we only need its hashes
    return ActualHarvestCommitManifestModel(
        batch_id=batch.id,
        validation_run_id=validation_run.id,
        commit_policy_version=COMMIT_POLICY_VERSION,
        validation_run_instance_identity_hash=(validation_run.instance_identity_hash),
        commit_manifest_hash=commit_manifest_hash,
        seal_manifest_hash=seal_manifest_hash,
        canonical_batch_hash=canonical_batch_hash,
        record_manifest_hash=record_manifest_hash,
        validation_result_hash=validation_result_hash,
        mapping_snapshot_hash=mapping_snapshot_hash,
        resolved_identity_snapshot_hash=resolved_identity_snapshot_hash,
        lineage_graph_hash=lineage_graph_hash,
        committed_lineage_basis_hash=committed_lineage_basis_hash,
        registry_content_hash=registry_content_hash,
        source_semantics_attestation_hash=(batch.source_semantics_attestation_hash),
        committed_record_count=committed_record_count,
        committed_by_identity=committed_by_identity,
        committed_at=committed_at,
    )


__all__ = [
    "build_commit_manifest",
    "get_batch_for_update",
    "get_current_validation_run",
    "get_existing_commit_manifest",
    "get_mapping_snapshot",
    "get_validation_result",
    "list_batch_records",
]
