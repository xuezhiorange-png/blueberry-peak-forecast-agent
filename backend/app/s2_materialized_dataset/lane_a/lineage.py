"""Lane A lineage query boundary."""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.s2_materialized_dataset.lane_a.persistence import (
    fetch_import_batch_by_identity_hash,
    fetch_source_artifact_by_identity_hash,
    fetch_source_row_by_identity_and_content,
)
from backend.app.s2_materialized_dataset.lane_a.schemas import (
    LaneALineageNotFoundError,
    SourceRowLineageChain,
)


def query_source_row_lineage_chain(
    session: Session,
    *,
    source_row_identity_hash: str,
    content_sha256: str,
) -> SourceRowLineageChain:
    source_row = fetch_source_row_by_identity_and_content(
        session,
        source_row_identity_hash=source_row_identity_hash,
        content_sha256=content_sha256,
    )
    if source_row is None:
        raise LaneALineageNotFoundError("source row lineage reference was not found")

    import_batch = fetch_import_batch_by_identity_hash(
        session,
        raw_import_batch_identity_hash=source_row.raw_import_batch_identity_hash,
    )
    if import_batch is None:
        raise LaneALineageNotFoundError("import batch lineage reference was not found")

    source_artifact = fetch_source_artifact_by_identity_hash(
        session,
        source_artifact_identity_hash=source_row.raw_source_artifact_identity_hash,
    )
    if source_artifact is None:
        raise LaneALineageNotFoundError("source artifact lineage reference was not found")

    return SourceRowLineageChain(
        source_artifact=source_artifact,
        import_batch=import_batch,
        source_row=source_row,
    )
