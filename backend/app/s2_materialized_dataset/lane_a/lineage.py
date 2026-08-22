"""Lane A lineage query boundary and SOURCE_002 controlled ingest."""

from __future__ import annotations

import logging
from hashlib import sha256
from pathlib import Path

from sqlalchemy.orm import Session

from backend.app.s2_materialized_dataset.lane_a.import_batch import register_raw_import_batch
from backend.app.s2_materialized_dataset.lane_a.persistence import (
    fetch_import_batch_by_identity_hash,
    fetch_source_artifact_by_identity_hash,
    fetch_source_row_by_identity_and_content,
)
from backend.app.s2_materialized_dataset.lane_a.schemas import (
    SOURCE_002_COHORT_ID,
    SOURCE_002_CONTROLLED_EXTERNAL_BATCH_ID,
    SOURCE_002_CONTROLLED_IMPORT_REQUEST_IDENTITY,
    SOURCE_002_IMPORT_POLICY_VERSION,
    SOURCE_002_INGEST_BATCH_SIZE,
    SOURCE_002_INGEST_PROGRESS_INTERVAL,
    SOURCE_002_MAPPING_POLICY_VERSION,
    SOURCE_002_MAPPING_SNAPSHOT_HASH,
    SOURCE_002_SCHEMA_VERSION,
    SOURCE_002_SOURCE_DATASET,
    SOURCE_002_SOURCE_SYSTEM,
    SOURCE_002_VALIDATION_POLICY_VERSION,
    LaneALineageNotFoundError,
    RawImportBatchIdentityInput,
    Source002ControlledIngestBlocked,
    Source002ControlledIngestResult,
    Source002IdentityVerificationRecord,
    Source002IdentityVerificationStatus,
    SourceRowLineageChain,
)
from backend.app.s2_materialized_dataset.lane_a.source_artifact import (
    build_source_002_artifact_input,
    register_raw_source_artifact,
    verify_source_002_frozen_object_identity,
)
from backend.app.s2_materialized_dataset.lane_a.source_row import (
    build_source_row_identity,
    iter_source_002_row_inputs,
    register_source_row_identities_batched,
)

logger = logging.getLogger(__name__)


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


def run_source_002_identity_verification(
    *,
    search_roots: tuple[Path, ...] = (),
) -> Source002IdentityVerificationRecord:
    verification, _, _ = verify_source_002_frozen_object_identity(search_roots=search_roots)
    return verification


def controlled_ingest_source_002(
    session: Session,
    *,
    verification: Source002IdentityVerificationRecord,
    artifact_bytes: bytes,
    storage_locator_hash: str | None = None,
) -> Source002ControlledIngestResult:
    if verification.status != Source002IdentityVerificationStatus.PASS:
        raise Source002ControlledIngestBlocked(
            "SOURCE_002 controlled ingest requires a passing E1 identity verification"
        )
    if verification.source_cohort_id != SOURCE_002_COHORT_ID:
        raise Source002ControlledIngestBlocked("SOURCE_002 cohort identity binding mismatch")

    artifact_registration = register_raw_source_artifact(
        session,
        artifact_input=build_source_002_artifact_input(
            storage_locator_hash=storage_locator_hash,
        ),
        artifact_bytes=artifact_bytes,
    )
    artifact_hash = artifact_registration.identity.source_artifact_identity_hash
    row_inputs = iter_source_002_row_inputs(
        artifact_bytes,
        source_column_mapping_snapshot_hash=SOURCE_002_MAPPING_SNAPSHOT_HASH,
    )
    placeholder_rows = tuple(
        build_source_row_identity(
            artifact_identity_hash=artifact_hash,
            batch_identity_hash="0" * 64,
            row_input=row_input,
        )
        for row_input in row_inputs
    )
    batch_input = RawImportBatchIdentityInput(
        external_batch_id=SOURCE_002_CONTROLLED_EXTERNAL_BATCH_ID,
        source_system=SOURCE_002_SOURCE_SYSTEM,
        source_dataset=SOURCE_002_SOURCE_DATASET,
        raw_payload_hash=sha256(artifact_bytes).hexdigest(),
        import_policy_version=SOURCE_002_IMPORT_POLICY_VERSION,
        schema_version=SOURCE_002_SCHEMA_VERSION,
        mapping_policy_version=SOURCE_002_MAPPING_POLICY_VERSION,
        validation_policy_version=SOURCE_002_VALIDATION_POLICY_VERSION,
        source_cohort_id=SOURCE_002_COHORT_ID,
        import_request_identity=SOURCE_002_CONTROLLED_IMPORT_REQUEST_IDENTITY,
    )
    batch_registration = register_raw_import_batch(
        session,
        batch_input=batch_input,
        raw_source_artifact_identity_hash=artifact_hash,
        source_row_identities=placeholder_rows,
    )
    batch_hash = batch_registration.identity.raw_import_batch_identity_hash
    row_identities = tuple(
        identity.model_copy(update={"raw_import_batch_identity_hash": batch_hash})
        for identity in placeholder_rows
    )
    logger.info(
        "lane_a source_002 row ingest starting rows=%s batch_size=%s",
        len(row_identities),
        SOURCE_002_INGEST_BATCH_SIZE,
    )
    row_summary = register_source_row_identities_batched(
        session,
        batch_identity_hash=batch_hash,
        row_identities=row_identities,
        batch_size=SOURCE_002_INGEST_BATCH_SIZE,
        progress_interval=SOURCE_002_INGEST_PROGRESS_INTERVAL,
        progress_logger=logger,
    )

    return Source002ControlledIngestResult(
        verification=verification,
        artifact_registration=artifact_registration,
        batch_registration=batch_registration,
        source_row_count=len(row_identities),
        first_seen_row_count=row_summary.first_seen_count,
        replay_row_count=row_summary.replay_count,
    )


def controlled_ingest_source_002_from_environment(
    session: Session,
    *,
    search_roots: tuple[Path, ...] = (),
) -> Source002ControlledIngestResult:
    verification, artifact_bytes, path = verify_source_002_frozen_object_identity(
        search_roots=search_roots
    )
    if verification.status != Source002IdentityVerificationStatus.PASS:
        raise Source002ControlledIngestBlocked(
            "SOURCE_002 controlled ingest requires a passing E1 identity verification"
        )
    if artifact_bytes is None or path is None:
        raise Source002ControlledIngestBlocked(
            "SOURCE_002 controlled ingest requires verified immutable bytes"
        )
    return controlled_ingest_source_002(
        session,
        verification=verification,
        artifact_bytes=artifact_bytes,
    )
