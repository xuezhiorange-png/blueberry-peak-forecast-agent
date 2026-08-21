"""RAW_SOURCE_ARTIFACT_IDENTITY construction and registration."""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.s2_materialized_dataset.lane_a.hashes import (
    compute_raw_source_artifact_identity_hash,
    compute_source_artifact_sha256,
)
from backend.app.s2_materialized_dataset.lane_a.persistence import (
    fetch_source_artifact_by_identity_hash,
    insert_source_artifact,
)
from backend.app.s2_materialized_dataset.lane_a.schemas import (
    RawSourceArtifactIdentity,
    RawSourceArtifactIdentityInput,
    SourceArtifactIntegrityConflict,
    SourceArtifactRegistration,
    SourceArtifactRegistrationResult,
)


def build_raw_source_artifact_identity(
    *,
    artifact_input: RawSourceArtifactIdentityInput,
    artifact_bytes: bytes,
) -> RawSourceArtifactIdentity:
    source_artifact_sha256 = compute_source_artifact_sha256(artifact_bytes)
    source_artifact_identity_hash = compute_raw_source_artifact_identity_hash(
        artifact_input=artifact_input,
    )
    return RawSourceArtifactIdentity(
        source_artifact_identity_hash=source_artifact_identity_hash,
        source_artifact_sha256=source_artifact_sha256,
        source_system=artifact_input.source_system,
        source_dataset=artifact_input.source_dataset,
        source_version=artifact_input.source_version,
        source_snapshot_reference=artifact_input.source_snapshot_reference,
        source_object_identity=artifact_input.source_object_identity,
        source_artifact_sequence=artifact_input.source_artifact_sequence,
        schema_version=artifact_input.schema_version,
        mapping_policy_version=artifact_input.mapping_policy_version,
        source_artifact_identity_version=artifact_input.source_artifact_identity_version,
        source_owner_attestation=artifact_input.source_owner_attestation,
        cohort_manifest_reference=artifact_input.cohort_manifest_reference,
        custody_record_reference=artifact_input.custody_record_reference,
        storage_locator_hash=artifact_input.storage_locator_hash,
    )


def register_raw_source_artifact(
    session: Session,
    *,
    artifact_input: RawSourceArtifactIdentityInput,
    artifact_bytes: bytes,
) -> SourceArtifactRegistration:
    identity = build_raw_source_artifact_identity(
        artifact_input=artifact_input,
        artifact_bytes=artifact_bytes,
    )
    existing = fetch_source_artifact_by_identity_hash(
        session,
        source_artifact_identity_hash=identity.source_artifact_identity_hash,
    )
    if existing is not None:
        if existing.source_artifact_sha256 != identity.source_artifact_sha256:
            raise SourceArtifactIntegrityConflict(
                "duplicate source artifact identity with different immutable bytes"
            )
        return SourceArtifactRegistration(
            result=SourceArtifactRegistrationResult.EXACT_REPLAY,
            identity=existing,
        )

    insert_source_artifact(session, identity=identity)
    return SourceArtifactRegistration(
        result=SourceArtifactRegistrationResult.FIRST_SEEN,
        identity=identity,
    )
