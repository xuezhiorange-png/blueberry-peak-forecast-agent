"""S1 commit service — 14-step algorithm (frozen S1 §六).

Caller-owned transaction. No session.commit() / session.rollback() inside.

Fails the batch returns to VALIDATED on any error. Does NOT persist a
COMMITTING or COMMIT_FAILED state. Does NOT introduce an attempt ledger,
lease, heartbeat, fencing token, or generation counter.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.actual_harvest_import.api_errors import (
    ActualHarvestApiError,
    ActualHarvestApiErrorCode,
)
from backend.app.actual_harvest_import.commit_hashes import (
    CommitManifestInput,
    compute_commit_manifest_hash,
    order_records_for_commit,
)
from backend.app.actual_harvest_import.commit_persistence import (
    build_commit_manifest,
    get_batch_for_update,
    get_current_validation_run,
    get_existing_commit_manifest,
    get_validation_result,
)
from backend.app.actual_harvest_import.enums import (
    ActualHarvestImportBatchStatus,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class CommitResult:
    commit_manifest_hash: str
    commit_policy_version: str
    validation_run_instance_identity_hash: str
    committed_record_count: int
    committed_at: datetime
    committed_by_identity: str
    reused_existing_commit: bool


async def commit_batch(
    session: AsyncSession,
    *,
    import_id: str,
    validation_run_instance_identity_hash: str,
    actor_identity: str,
) -> CommitResult:
    """Step 1-14 of the S1 §六 algorithm.

    1. SELECT batch WHERE import_id = ? FOR UPDATE
    2. Reload validation run, validation result, mapping snapshot inside lock
    3. If batch.status == COMMITTED:
       - Reload existing manifest
       - If instance_identity_hash matches, return original (zero write)
       - Else raise COMMIT_EVIDENCE_CONFLICT
    4. If batch.status != VALIDATED: raise IMPORT_BATCH_NOT_VALIDATED
    5. Load current VALIDATED validation run
    6. Verify request validation_run_instance_identity_hash matches run
    7. Verify active_attempt_id IS NULL; counts are 0/0; valid_count==record_count
    8. Reload batch records
    9. Re-derive ordered revisions + commit_manifest_hash from current state
    10. On any evidence drift: raise COMMIT_EVIDENCE_DRIFT
    11. INSERT commit manifest
    12. UPDATE batch status=COMMITTED, committed_record_count, committed_at
    13. session.flush()
    14. Caller commits (no session.commit / rollback here)
    """
    # Step 1
    batch = await get_batch_for_update(session, import_id)
    if batch is None:
        raise ActualHarvestApiError(
            ActualHarvestApiErrorCode.IMPORT_BATCH_NOT_FOUND,
            "actual-harvest import batch was not found",
            status_code=404,
        )

    # Step 3 (replay / conflict)
    if batch.status == ActualHarvestImportBatchStatus.COMMITTED.value:
        existing = await get_existing_commit_manifest(session, batch.id)
        if existing is None:
            # Should be impossible: UNIQUE(batch_id) + status=COMMITTED
            raise ActualHarvestApiError(
                ActualHarvestApiErrorCode.API_INTEGRITY_ERROR,
                "committed batch is missing its manifest",
                status_code=500,
            )
        if (
            existing.validation_run_instance_identity_hash
            != validation_run_instance_identity_hash
        ):
            raise ActualHarvestApiError(
                ActualHarvestApiErrorCode.COMMIT_EVIDENCE_CONFLICT,
                "commit evidence conflicts with existing committed manifest",
                status_code=409,
            )
        return CommitResult(
            commit_manifest_hash=existing.commit_manifest_hash,
            commit_policy_version=existing.commit_policy_version,
            validation_run_instance_identity_hash=(
                existing.validation_run_instance_identity_hash
            ),
            committed_record_count=existing.committed_record_count,
            committed_at=existing.committed_at,
            committed_by_identity=existing.committed_by_identity,
            reused_existing_commit=True,
        )

    # Step 4
    if batch.status != ActualHarvestImportBatchStatus.VALIDATED.value:
        raise ActualHarvestApiError(
            ActualHarvestApiErrorCode.IMPORT_BATCH_NOT_VALIDATED,
            "actual-harvest import batch is not in VALIDATED state",
            status_code=409,
        )

    # Step 5
    validation_run = await get_current_validation_run(session, batch.id)
    if validation_run is None:
        raise ActualHarvestApiError(
            ActualHarvestApiErrorCode.COMMIT_EVIDENCE_DRIFT,
            "no current VALIDATED validation run found for batch",
            status_code=409,
        )

    # Step 6
    if (
        validation_run.instance_identity_hash
        != validation_run_instance_identity_hash
    ):
        raise ActualHarvestApiError(
            ActualHarvestApiErrorCode.COMMIT_EVIDENCE_DRIFT,
            "validation_run_instance_identity_hash does not match current run",
            status_code=409,
        )

    # Step 7
    if validation_run.active_attempt_id is not None:
        raise ActualHarvestApiError(
            ActualHarvestApiErrorCode.COMMIT_EVIDENCE_DRIFT,
            "validation run has an active attempt",
            status_code=409,
        )
    if validation_run.error_count != 0 or validation_run.invalid_count != 0:
        raise ActualHarvestApiError(
            ActualHarvestApiErrorCode.COMMIT_EVIDENCE_DRIFT,
            "validation run has unresolved errors or invalid records",
            status_code=409,
        )
    if validation_run.valid_count != batch.record_count:
        raise ActualHarvestApiError(
            ActualHarvestApiErrorCode.COMMIT_RECORD_COUNT_MISMATCH,
            "validation run valid_count does not match batch record count",
            status_code=409,
        )
    if batch.valid_record_count != batch.record_count:
        raise ActualHarvestApiError(
            ActualHarvestApiErrorCode.COMMIT_RECORD_COUNT_MISMATCH,
            "batch valid_record_count does not match batch record count",
            status_code=409,
        )
    if batch.invalid_record_count != 0:
        raise ActualHarvestApiError(
            ActualHarvestApiErrorCode.COMMIT_EVIDENCE_DRIFT,
            "batch has invalid records",
            status_code=409,
        )

    # Step 7 — load validation result & verify required hashes present
    validation_result = await get_validation_result(session, validation_run.id)
    if validation_result is None:
        raise ActualHarvestApiError(
            ActualHarvestApiErrorCode.COMMIT_EVIDENCE_DRIFT,
            "validation result not found for current run",
            status_code=409,
        )

    # Required evidence hashes consistency
    required = {
        "seal_manifest_hash": batch.seal_manifest_hash_or_null,
        "canonical_batch_hash": batch.canonical_batch_hash_or_null,
        "record_manifest_hash": validation_run.record_manifest_hash,
        "validation_result_hash": validation_run.validation_result_hash,
        "mapping_snapshot_hash": validation_run.mapping_snapshot_hash,
        "resolved_identity_snapshot_hash": (
            validation_run.resolved_identity_snapshot_hash
        ),
        "lineage_graph_hash": validation_run.lineage_graph_hash,
        "committed_lineage_basis_hash": (
            validation_run.committed_lineage_basis_hash
        ),
        "registry_content_hash": validation_run.registry_content_hash,
    }
    for name, value in required.items():
        if not value or len(value) != 64:
            raise ActualHarvestApiError(
                ActualHarvestApiErrorCode.COMMIT_EVIDENCE_DRIFT,
                f"required evidence hash missing: {name}",
                status_code=409,
            )

    # Step 7 — verify seal hash consistency between batch and validation run
    if batch.seal_manifest_hash_or_null != validation_run.seal_manifest_hash:
        raise ActualHarvestApiError(
            ActualHarvestApiErrorCode.COMMIT_EVIDENCE_DRIFT,
            "batch seal_manifest_hash does not match validation run",
            status_code=409,
        )

    # Step 8 + 9 — reload records + derive ordered revisions
    # Force a fresh SELECT on the records relationship because the
    # relationship may be unloaded (we did a scalar SELECT in step 1).
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    await session.refresh(
        batch,
        attribute_names=["records"],
    )
    records = list(batch.records)
    if len(records) != batch.record_count:
        raise ActualHarvestApiError(
            ActualHarvestApiErrorCode.COMMIT_RECORD_COUNT_MISMATCH,
            "loaded record count does not match batch record count",
            status_code=409,
        )
    ordered = order_records_for_commit(records)
    if len(ordered) != batch.record_count:
        raise ActualHarvestApiError(
            ActualHarvestApiErrorCode.COMMIT_RECORD_COUNT_MISMATCH,
            "ordered revisions do not match batch record count",
            status_code=409,
        )

    # Step 9 — compute commit_manifest_hash
    commit_manifest_hash = compute_commit_manifest_hash(
        CommitManifestInput(
            import_id=batch.import_id,
            validation_run_instance_identity_hash=(
                validation_run.instance_identity_hash
            ),
            seal_manifest_hash=batch.seal_manifest_hash_or_null,
            canonical_batch_hash=batch.canonical_batch_hash_or_null,
            record_manifest_hash=validation_run.record_manifest_hash,
            validation_result_hash=validation_run.validation_result_hash,
            mapping_snapshot_hash=validation_run.mapping_snapshot_hash,
            resolved_identity_snapshot_hash=(
                validation_run.resolved_identity_snapshot_hash
            ),
            lineage_graph_hash=validation_run.lineage_graph_hash,
            committed_lineage_basis_hash=(
                validation_run.committed_lineage_basis_hash
            ),
            registry_content_hash=validation_run.registry_content_hash,
            source_semantics_attestation_hash=(
                batch.source_semantics_attestation_hash
            ),
            committed_record_count=batch.record_count,
            ordered_revisions=ordered,
        )
    )

    # Step 11 — INSERT manifest (single row)
    committed_at = _utc_now()
    manifest = build_commit_manifest(
        batch=batch,
        validation_run=validation_run,
        validation_result=validation_result,
        commit_manifest_hash=commit_manifest_hash,
        committed_by_identity=actor_identity,
        committed_at=committed_at,
        committed_record_count=batch.record_count,
    )
    session.add(manifest)

    # Step 12 — UPDATE batch state
    batch.status = ActualHarvestImportBatchStatus.COMMITTED.value
    batch.committed_record_count = batch.record_count
    batch.committed_at_or_null = committed_at

    # Step 13 — flush so DB-level constraint failures surface inside the
    # caller-owned transaction (still no commit/rollback here).
    await session.flush()

    return CommitResult(
        commit_manifest_hash=commit_manifest_hash,
        commit_policy_version=manifest.commit_policy_version,
        validation_run_instance_identity_hash=(
            manifest.validation_run_instance_identity_hash
        ),
        committed_record_count=manifest.committed_record_count,
        committed_at=manifest.committed_at,
        committed_by_identity=manifest.committed_by_identity,
        reused_existing_commit=False,
    )


__all__ = ["CommitResult", "commit_batch"]
