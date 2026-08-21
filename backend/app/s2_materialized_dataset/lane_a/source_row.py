"""SOURCE_ROW_IDENTITY construction and append-only lineage registration."""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.s2_materialized_dataset.lane_a.hashes import (
    compute_source_row_content_hash,
    compute_source_row_identity_hash,
)
from backend.app.s2_materialized_dataset.lane_a.persistence import (
    fetch_source_row_by_identity_hash,
    fetch_source_rows_by_logical_key,
    insert_source_row_lineage,
    mark_logical_record_candidates_blocked,
)
from backend.app.s2_materialized_dataset.lane_a.schemas import (
    MissingExternalLogicalRecordIdError,
    SourceRowIdentity,
    SourceRowLineageInput,
    SourceRowRegistration,
    SourceRowRegistrationResult,
    SourceRowRevisionConflict,
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

    existing = fetch_source_row_by_identity_hash(
        session,
        source_row_identity_hash=identity.source_row_identity_hash,
    )
    if existing is not None:
        if existing.content_sha256 != identity.content_sha256:
            raise SourceRowRevisionConflict(
                "same source row identity with different canonical content"
            )
        refreshed = fetch_source_row_by_identity_hash(
            session,
            source_row_identity_hash=identity.source_row_identity_hash,
        )
        assert refreshed is not None
        return SourceRowRegistration(
            result=SourceRowRegistrationResult.EXACT_REPLAY,
            identity=refreshed,
        )

    logical_candidates = fetch_source_rows_by_logical_key(
        session,
        raw_source_artifact_identity_hash=artifact_identity_hash,
        source_system=row_input.source_system,
        external_logical_record_id=row_input.external_logical_record_id,
    )
    if logical_candidates:
        mark_logical_record_candidates_blocked(
            session,
            raw_source_artifact_identity_hash=artifact_identity_hash,
            source_system=row_input.source_system,
            external_logical_record_id=row_input.external_logical_record_id,
        )
        identity = identity.model_copy(update={"winner_selection_blocked": True})

    insert_source_row_lineage(session, identity=identity)
    if logical_candidates:
        mark_logical_record_candidates_blocked(
            session,
            raw_source_artifact_identity_hash=artifact_identity_hash,
            source_system=row_input.source_system,
            external_logical_record_id=row_input.external_logical_record_id,
        )
        refreshed = fetch_source_row_by_identity_hash(
            session,
            source_row_identity_hash=identity.source_row_identity_hash,
        )
        assert refreshed is not None
        identity = refreshed

    return SourceRowRegistration(
        result=SourceRowRegistrationResult.FIRST_SEEN,
        identity=identity,
    )
