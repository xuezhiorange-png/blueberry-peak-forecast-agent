"""RAW_IMPORT_BATCH_IDENTITY construction and idempotent registration."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.orm import Session

from backend.app.s2_materialized_dataset.lane_a.hashes import (
    compute_raw_import_batch_content_sha256,
    compute_raw_import_batch_identity_hash,
    ordered_source_row_content_hashes,
)
from backend.app.s2_materialized_dataset.lane_a.persistence import (
    fetch_import_batch_by_external_identity,
    fetch_import_batch_by_identity_hash,
    insert_import_batch,
)
from backend.app.s2_materialized_dataset.lane_a.schemas import (
    ImportBatchIdempotencyConflict,
    ImportBatchRegistration,
    ImportBatchRegistrationResult,
    RawImportBatchIdentity,
    RawImportBatchIdentityInput,
    SourceRowIdentity,
)


def _ordered_row_hashes(
    source_row_identities: Iterable[SourceRowIdentity],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    rows = tuple(source_row_identities)
    ordered_rows = sorted(
        rows,
        key=lambda row: (
            row.source_system,
            row.external_logical_record_id,
            row.revision_number,
            row.external_revision_id,
        ),
    )
    content_hashes = ordered_source_row_content_hashes(
        {
            "source_system": row.source_system,
            "external_logical_record_id": row.external_logical_record_id,
            "revision_number": row.revision_number,
            "external_revision_id": row.external_revision_id,
            "content_sha256": row.content_sha256,
        }
        for row in ordered_rows
    )
    identity_hashes = tuple(row.source_row_identity_hash for row in ordered_rows)
    return content_hashes, identity_hashes


def build_raw_import_batch_identity(
    *,
    batch_input: RawImportBatchIdentityInput,
    raw_source_artifact_identity_hash: str,
    source_row_identities: Iterable[SourceRowIdentity],
) -> RawImportBatchIdentity:
    ordered_content_hashes, ordered_identity_hashes = _ordered_row_hashes(source_row_identities)
    content_sha256 = compute_raw_import_batch_content_sha256(
        ordered_row_content_hashes=ordered_content_hashes,
    )
    raw_import_batch_identity_hash = compute_raw_import_batch_identity_hash(
        batch_input=batch_input,
        raw_source_artifact_identity_hash=raw_source_artifact_identity_hash,
        ordered_row_content_hashes=ordered_content_hashes,
        ordered_row_identity_hashes=ordered_identity_hashes,
    )
    return RawImportBatchIdentity(
        raw_import_batch_identity_hash=raw_import_batch_identity_hash,
        content_sha256=content_sha256,
        raw_source_artifact_identity_hash=raw_source_artifact_identity_hash,
        external_batch_id=batch_input.external_batch_id,
        source_system=batch_input.source_system,
        source_dataset=batch_input.source_dataset,
        raw_payload_hash=batch_input.raw_payload_hash,
        import_policy_version=batch_input.import_policy_version,
        schema_version=batch_input.schema_version,
        mapping_policy_version=batch_input.mapping_policy_version,
        validation_policy_version=batch_input.validation_policy_version,
        source_cohort_id=batch_input.source_cohort_id,
        import_request_identity=batch_input.import_request_identity,
        source_row_identity_hashes=ordered_identity_hashes,
    )


def _assert_no_external_batch_conflict(
    *,
    existing: RawImportBatchIdentity,
    candidate: RawImportBatchIdentity,
) -> None:
    if existing.raw_import_batch_identity_hash == candidate.raw_import_batch_identity_hash:
        return
    raise ImportBatchIdempotencyConflict(
        "same external batch identity with different payload or policy versions"
    )


def register_raw_import_batch(
    session: Session,
    *,
    batch_input: RawImportBatchIdentityInput,
    raw_source_artifact_identity_hash: str,
    source_row_identities: Iterable[SourceRowIdentity],
) -> ImportBatchRegistration:
    identity = build_raw_import_batch_identity(
        batch_input=batch_input,
        raw_source_artifact_identity_hash=raw_source_artifact_identity_hash,
        source_row_identities=source_row_identities,
    )

    existing_by_hash = fetch_import_batch_by_identity_hash(
        session,
        raw_import_batch_identity_hash=identity.raw_import_batch_identity_hash,
    )
    if existing_by_hash is not None:
        return ImportBatchRegistration(
            result=ImportBatchRegistrationResult.EXACT_REPLAY,
            identity=existing_by_hash,
        )

    existing_by_external = fetch_import_batch_by_external_identity(
        session,
        raw_source_artifact_identity_hash=raw_source_artifact_identity_hash,
        source_system=batch_input.source_system,
        external_batch_id=batch_input.external_batch_id,
    )
    if existing_by_external is not None:
        _assert_no_external_batch_conflict(existing=existing_by_external, candidate=identity)
        return ImportBatchRegistration(
            result=ImportBatchRegistrationResult.EXACT_REPLAY,
            identity=existing_by_external,
        )

    insert_import_batch(session, identity=identity)
    return ImportBatchRegistration(
        result=ImportBatchRegistrationResult.FIRST_SEEN,
        identity=identity,
    )
