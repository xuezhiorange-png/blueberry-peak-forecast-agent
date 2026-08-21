"""SOURCE_ROW_IDENTITY construction and append-only lineage registration."""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.s2_materialized_dataset.lane_a.hashes import (
    compute_source_row_content_hash,
    compute_source_row_identity_hash,
)
from backend.app.s2_materialized_dataset.lane_a.persistence import (
    derive_winner_selection_blocked,
    fetch_source_row_by_identity_and_content,
    fetch_source_rows_by_identity_hash,
    insert_source_row_lineage,
)
from backend.app.s2_materialized_dataset.lane_a.schemas import (
    MissingExternalLogicalRecordIdError,
    SourceRowIdentity,
    SourceRowLineageInput,
    SourceRowRegistration,
    SourceRowRegistrationResult,
)


def _require_external_logical_record_id(row_input: SourceRowLineageInput) -> None:
    if not row_input.external_logical_record_id.strip():
        raise MissingExternalLogicalRecordIdError(
            "source row ingestion requires a stable external logical record identity"
        )


def build_source_row_identity(
    *,
    artifact_identity_hash: str,
    batch_identity_hash: str,
    row_input: SourceRowLineageInput,
) -> SourceRowIdentity:
    _require_external_logical_record_id(row_input)
    content_sha256 = compute_source_row_content_hash(business_content=row_input.business_content)
    source_row_identity_hash = compute_source_row_identity_hash(
        artifact_identity_hash=artifact_identity_hash,
        row_input=row_input,
    )
    return SourceRowIdentity(
        source_row_identity_hash=source_row_identity_hash,
        content_sha256=content_sha256,
        raw_source_artifact_identity_hash=artifact_identity_hash,
        raw_import_batch_identity_hash=batch_identity_hash,
        external_logical_record_id=row_input.external_logical_record_id,
        external_revision_id=row_input.external_revision_id,
        revision_number=row_input.revision_number,
        source_system=row_input.source_system,
        source_version=row_input.source_version,
        schema_version=row_input.schema_version,
        source_row_identity_version=row_input.source_row_identity_version,
        source_sheet_name=row_input.source_sheet_name,
        source_row_number=row_input.source_row_number,
        source_column_mapping_snapshot_hash=row_input.source_column_mapping_snapshot_hash,
        winner_selection_blocked=False,
    )


def _with_derived_blocked_state(
    session: Session,
    *,
    identity: SourceRowIdentity,
) -> SourceRowIdentity:
    return identity.model_copy(
        update={
            "winner_selection_blocked": derive_winner_selection_blocked(
                session,
                raw_source_artifact_identity_hash=identity.raw_source_artifact_identity_hash,
                source_system=identity.source_system,
                external_logical_record_id=identity.external_logical_record_id,
                source_row_identity_hash=identity.source_row_identity_hash,
            )
        }
    )


def register_source_row_lineage(
    session: Session,
    *,
    artifact_identity_hash: str,
    batch_identity_hash: str,
    row_input: SourceRowLineageInput,
) -> SourceRowRegistration:
    identity = build_source_row_identity(
        artifact_identity_hash=artifact_identity_hash,
        batch_identity_hash=batch_identity_hash,
        row_input=row_input,
    )

    existing = fetch_source_row_by_identity_and_content(
        session,
        source_row_identity_hash=identity.source_row_identity_hash,
        content_sha256=identity.content_sha256,
    )
    if existing is not None:
        return SourceRowRegistration(
            result=SourceRowRegistrationResult.EXACT_REPLAY,
            identity=_with_derived_blocked_state(session, identity=existing),
        )

    conflicting_rows = fetch_source_rows_by_identity_hash(
        session,
        source_row_identity_hash=identity.source_row_identity_hash,
    )
    if conflicting_rows:
        insert_source_row_lineage(session, identity=identity)
        persisted = fetch_source_row_by_identity_and_content(
            session,
            source_row_identity_hash=identity.source_row_identity_hash,
            content_sha256=identity.content_sha256,
        )
        assert persisted is not None
        return SourceRowRegistration(
            result=SourceRowRegistrationResult.CONTENT_CONFLICT_CANDIDATE,
            identity=_with_derived_blocked_state(session, identity=persisted),
        )

    insert_source_row_lineage(session, identity=identity)
    persisted = fetch_source_row_by_identity_and_content(
        session,
        source_row_identity_hash=identity.source_row_identity_hash,
        content_sha256=identity.content_sha256,
    )
    assert persisted is not None
    return SourceRowRegistration(
        result=SourceRowRegistrationResult.FIRST_SEEN,
        identity=_with_derived_blocked_state(session, identity=persisted),
    )
