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

from backend.app.actual_harvest_import.api_auth import ActualHarvestActorContext
from backend.app.actual_harvest_import.api_errors import (
    ActualHarvestApiError,
    ActualHarvestApiErrorCode,
)
from backend.app.actual_harvest_import.commit_hashes import (
    CommitManifestInput,
    compute_commit_manifest_hash,
    compute_record_manifest_hash,
    order_records_for_commit,
)
from backend.app.actual_harvest_import.commit_persistence import (
    build_commit_manifest,
    get_batch_for_update,
    get_current_validation_run,
    get_existing_commit_manifest,
    get_mapping_snapshot,
    get_validation_result,
)
from backend.app.actual_harvest_import.enums import (
    ActualHarvestImportBatchStatus,
    ActualHarvestImportChannel,
)
from backend.app.actual_harvest_import.validation import validate_sha256_hex


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _require_evidence_hash(label: str, value: str | None) -> str:
    """Fail-closed narrow: ORM `Mapped[str] nullable=False` columns are
    typed as `str | None` by static analysers (SQLAlchemy `Mapped` is not
    smart-narrowed by mypy). This helper forces the runtime value through
    the project's canonical SHA-256 hex validator so the returned
    annotation is `str` and downstream code can rely on it without
    casting, `type: ignore`, or `Any`."""

    try:
        return validate_sha256_hex(value, field_name=label)
    except ValueError as exc:
        raise ActualHarvestApiError(
            ActualHarvestApiErrorCode.COMMIT_EVIDENCE_DRIFT,
            f"required evidence hash missing or malformed: {label}",
            status_code=409,
        ) from exc


def _unauthorized() -> ActualHarvestApiError:
    # Concealment: unauthorized actors see the same error as a missing
    # batch so the existence of the import_id is not disclosed.
    return ActualHarvestApiError(
        ActualHarvestApiErrorCode.IMPORT_BATCH_NOT_FOUND,
        "actual-harvest import batch was not found",
        status_code=404,
    )


def _reauthorize_under_lock(
    *,
    actor: ActualHarvestActorContext,
    submitted_by_identity: str,
    batch_source_system: str,
    batch_import_channel: str,
) -> None:
    """Re-authorize the actor AFTER acquiring the row lock.

    The first line of defence is at the API endpoint where the actor is
    constructed from the request's authenticated principal. This second
    pass inside the row lock guarantees that the authorization still
    holds against the freshly-locked batch and that the actor still
    holds `may_commit`. Any failure here returns the same
    `IMPORT_BATCH_NOT_FOUND` error as a non-existent batch to avoid
    leaking the existence of the resource to a non-owner.
    """
    if not actor.may_commit:
        raise _unauthorized()
    if actor.identity != submitted_by_identity:
        raise _unauthorized()
    if batch_source_system not in actor.allowed_source_systems:
        raise _unauthorized()
    try:
        channel = ActualHarvestImportChannel(batch_import_channel)
    except ValueError:
        raise _unauthorized() from None
    if channel not in actor.allowed_channels:
        raise _unauthorized()


def _assert_hash_equal(label: str, expected: str | None, actual: str | None) -> None:
    """Drift guard: every required evidence hash must equal its run-side
    value. We compare exact strings, never only length, so a drift in
    the *value* (not just the format) is caught.
    """
    if expected is None or actual is None:
        raise ActualHarvestApiError(
            ActualHarvestApiErrorCode.COMMIT_EVIDENCE_DRIFT,
            f"required evidence hash missing: {label}",
            status_code=409,
        )
    if expected != actual:
        raise ActualHarvestApiError(
            ActualHarvestApiErrorCode.COMMIT_EVIDENCE_DRIFT,
            f"evidence drift on {label}",
            status_code=409,
        )


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
    actor: ActualHarvestActorContext,
) -> CommitResult:
    """Step 1-14 of the S1 §六 algorithm.

    1. SELECT batch WHERE import_id = ? FOR UPDATE
    1.5. Re-authorize actor under the lock (may_commit, owner,
         source_system, channel)
    2. Reload validation run, validation result, mapping snapshot inside lock
    3. If batch.status == COMMITTED:
       - Reload existing manifest
       - If instance_identity_hash matches, return original (zero write)
       - Else raise COMMIT_EVIDENCE_CONFLICT
    4. If batch.status != VALIDATED: raise IMPORT_BATCH_NOT_VALIDATED
    5. Load current VALIDATED validation run
    6. Verify request validation_run_instance_identity_hash matches run
    7. Verify active_attempt_id IS NULL; counts are 0/0; valid_count==record_count
    8. Reload batch records + recompute record manifest + cross-check
       validation_result and mapping_snapshot hashes
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
        raise _unauthorized()

    # Step 1.5 — re-authorize under the row lock.
    _reauthorize_under_lock(
        actor=actor,
        submitted_by_identity=batch.submitted_by_identity,
        batch_source_system=batch.source_system,
        batch_import_channel=batch.import_channel,
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
        if existing.validation_run_instance_identity_hash != validation_run_instance_identity_hash:
            raise ActualHarvestApiError(
                ActualHarvestApiErrorCode.COMMIT_EVIDENCE_CONFLICT,
                "commit evidence conflicts with existing committed manifest",
                status_code=409,
            )
        return CommitResult(
            commit_manifest_hash=existing.commit_manifest_hash,
            commit_policy_version=existing.commit_policy_version,
            validation_run_instance_identity_hash=(existing.validation_run_instance_identity_hash),
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
    if validation_run.instance_identity_hash != validation_run_instance_identity_hash:
        raise ActualHarvestApiError(
            ActualHarvestApiErrorCode.COMMIT_EVIDENCE_DRIFT,
            "validation_run_instance_identity_hash does not match current run",
            status_code=409,
        )

    # Step 7 — run + batch count invariants
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
            ActualHarvestApiErrorCode.COMMIT_EVIDENCE_DRIFT,
            "validation run valid_count does not match batch record count",
            status_code=409,
        )
    if batch.valid_record_count != batch.record_count:
        raise ActualHarvestApiError(
            ActualHarvestApiErrorCode.COMMIT_EVIDENCE_DRIFT,
            "batch valid_record_count does not match batch record count",
            status_code=409,
        )
    if batch.invalid_record_count != 0:
        raise ActualHarvestApiError(
            ActualHarvestApiErrorCode.COMMIT_EVIDENCE_DRIFT,
            "batch has invalid records",
            status_code=409,
        )

    # Step 7.5 — load validation result and mapping snapshot, then
    # cross-check every required evidence hash against the current run.
    validation_result = await get_validation_result(session, validation_run.id)
    if validation_result is None:
        raise ActualHarvestApiError(
            ActualHarvestApiErrorCode.COMMIT_EVIDENCE_DRIFT,
            "validation result not found for current run",
            status_code=409,
        )
    mapping_snapshot = await get_mapping_snapshot(session, validation_run.id)
    if mapping_snapshot is None:
        raise ActualHarvestApiError(
            ActualHarvestApiErrorCode.COMMIT_EVIDENCE_DRIFT,
            "mapping snapshot not found for current run",
            status_code=409,
        )

    # Step 7.55 — narrow every Optional ORM hash to a `str` local.
    # Once narrowed, ALL downstream code MUST use these locals instead of
    # re-reading the Optional ORM property. This is the mypy fix surface.
    seal_manifest_hash = _require_evidence_hash(
        "seal_manifest_hash",
        batch.seal_manifest_hash_or_null,
    )
    seal_manifest_hash_run = _require_evidence_hash(
        "validation_run.seal_manifest_hash",
        validation_run.seal_manifest_hash,
    )
    canonical_batch_hash = _require_evidence_hash(
        "canonical_batch_hash",
        batch.canonical_batch_hash_or_null,
    )
    record_manifest_hash_stored = _require_evidence_hash(
        "record_manifest_hash",
        validation_run.record_manifest_hash,
    )
    validation_result_hash_run = _require_evidence_hash(
        "validation_result_hash",
        validation_run.validation_result_hash,
    )
    mapping_snapshot_hash_run = _require_evidence_hash(
        "mapping_snapshot_hash",
        validation_run.mapping_snapshot_hash,
    )
    resolved_identity_snapshot_hash_run = _require_evidence_hash(
        "resolved_identity_snapshot_hash",
        validation_run.resolved_identity_snapshot_hash,
    )
    lineage_graph_hash_run = _require_evidence_hash(
        "lineage_graph_hash",
        validation_run.lineage_graph_hash,
    )
    committed_lineage_basis_hash_run = _require_evidence_hash(
        "committed_lineage_basis_hash",
        validation_run.committed_lineage_basis_hash,
    )
    registry_content_hash_run = _require_evidence_hash(
        "registry_content_hash",
        validation_run.registry_content_hash,
    )
    validation_result_hash_local = _require_evidence_hash(
        "validation_result.validation_result_hash",
        validation_result.validation_result_hash,
    )
    lineage_graph_hash_local = _require_evidence_hash(
        "validation_result.lineage_graph_hash",
        validation_result.lineage_graph_hash,
    )
    committed_lineage_basis_hash_local = _require_evidence_hash(
        "validation_result.committed_lineage_basis_hash",
        validation_result.committed_lineage_basis_hash,
    )
    mapping_snapshot_hash_local = _require_evidence_hash(
        "validation_result.mapping_snapshot_hash",
        validation_result.mapping_snapshot_hash,
    )
    resolved_identity_snapshot_hash_local = _require_evidence_hash(
        "validation_result.resolved_identity_snapshot_hash",
        validation_result.resolved_identity_snapshot_hash,
    )
    mapping_snapshot_hash_snapshot = _require_evidence_hash(
        "mapping_snapshot.mapping_snapshot_hash",
        mapping_snapshot.mapping_snapshot_hash,
    )
    resolved_identity_snapshot_hash_snapshot = _require_evidence_hash(
        "mapping_snapshot.resolved_identity_snapshot_hash",
        mapping_snapshot.resolved_identity_snapshot_hash,
    )
    registry_content_hash_snapshot = _require_evidence_hash(
        "mapping_snapshot.registry_content_hash",
        mapping_snapshot.registry_content_hash,
    )

    # Step 7.6 — full cross-check between validation_result,
    # mapping_snapshot, and validation_run.
    _assert_hash_equal(
        "validation_result.validation_result_hash",
        expected=validation_result_hash_run,
        actual=validation_result_hash_local,
    )
    _assert_hash_equal(
        "validation_result.lineage_graph_hash",
        expected=lineage_graph_hash_run,
        actual=lineage_graph_hash_local,
    )
    _assert_hash_equal(
        "validation_result.committed_lineage_basis_hash",
        expected=committed_lineage_basis_hash_run,
        actual=committed_lineage_basis_hash_local,
    )
    _assert_hash_equal(
        "validation_result.mapping_snapshot_hash",
        expected=mapping_snapshot_hash_run,
        actual=mapping_snapshot_hash_local,
    )
    _assert_hash_equal(
        "validation_result.resolved_identity_snapshot_hash",
        expected=resolved_identity_snapshot_hash_run,
        actual=resolved_identity_snapshot_hash_local,
    )
    _assert_hash_equal(
        "mapping_snapshot.mapping_snapshot_hash",
        expected=mapping_snapshot_hash_run,
        actual=mapping_snapshot_hash_snapshot,
    )
    _assert_hash_equal(
        "mapping_snapshot.resolved_identity_snapshot_hash",
        expected=resolved_identity_snapshot_hash_run,
        actual=resolved_identity_snapshot_hash_snapshot,
    )
    _assert_hash_equal(
        "mapping_snapshot.registry_content_hash",
        expected=registry_content_hash_run,
        actual=registry_content_hash_snapshot,
    )

    # Step 7.7 — batch↔run seal/cross-check
    _assert_hash_equal(
        "batch.seal_manifest_hash",
        expected=seal_manifest_hash_run,
        actual=seal_manifest_hash,
    )

    # Step 8 — reload records + recompute record manifest
    await session.refresh(batch, attribute_names=["records"])
    records = list(batch.records)
    if len(records) != batch.record_count:
        raise ActualHarvestApiError(
            ActualHarvestApiErrorCode.COMMIT_EVIDENCE_DRIFT,
            "loaded record count does not match batch record count",
            status_code=409,
        )
    ordered = order_records_for_commit(records)
    if len(ordered) != batch.record_count:
        raise ActualHarvestApiError(
            ActualHarvestApiErrorCode.COMMIT_EVIDENCE_DRIFT,
            "ordered revisions do not match batch record count",
            status_code=409,
        )
    record_manifest_hash = compute_record_manifest_hash(ordered)
    _assert_hash_equal(
        "validation_run.record_manifest_hash",
        expected=record_manifest_hash_stored,
        actual=record_manifest_hash,
    )

    # Step 9 — compute commit_manifest_hash
    commit_manifest_hash = compute_commit_manifest_hash(
        CommitManifestInput(
            import_id=batch.import_id,
            validation_run_instance_identity_hash=(validation_run.instance_identity_hash),
            seal_manifest_hash=seal_manifest_hash,
            canonical_batch_hash=canonical_batch_hash,
            record_manifest_hash=record_manifest_hash,
            validation_result_hash=validation_result_hash_run,
            mapping_snapshot_hash=mapping_snapshot_hash_run,
            resolved_identity_snapshot_hash=resolved_identity_snapshot_hash_run,
            lineage_graph_hash=lineage_graph_hash_run,
            committed_lineage_basis_hash=committed_lineage_basis_hash_run,
            registry_content_hash=registry_content_hash_run,
            source_semantics_attestation_hash=(batch.source_semantics_attestation_hash),
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
        committed_by_identity=actor.identity,
        committed_at=committed_at,
        committed_record_count=batch.record_count,
        seal_manifest_hash=seal_manifest_hash,
        canonical_batch_hash=canonical_batch_hash,
        record_manifest_hash=record_manifest_hash,
        validation_result_hash=validation_result_hash_run,
        mapping_snapshot_hash=mapping_snapshot_hash_run,
        resolved_identity_snapshot_hash=resolved_identity_snapshot_hash_run,
        lineage_graph_hash=lineage_graph_hash_run,
        committed_lineage_basis_hash=committed_lineage_basis_hash_run,
        registry_content_hash=registry_content_hash_run,
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
        validation_run_instance_identity_hash=(manifest.validation_run_instance_identity_hash),
        committed_record_count=manifest.committed_record_count,
        committed_at=manifest.committed_at,
        committed_by_identity=manifest.committed_by_identity,
        reused_existing_commit=False,
    )


__all__ = ["CommitResult", "commit_batch"]
