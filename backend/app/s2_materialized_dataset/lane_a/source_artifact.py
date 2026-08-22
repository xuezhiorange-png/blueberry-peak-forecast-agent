"""RAW_SOURCE_ARTIFACT_IDENTITY construction and registration."""

from __future__ import annotations

import os
from hashlib import sha256
from pathlib import Path

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
    SOURCE_002_BYTE_COUNT,
    SOURCE_002_COHORT_ID,
    SOURCE_002_COHORT_MANIFEST_SHA256,
    SOURCE_002_CUSTODY_RECORD,
    SOURCE_002_DECLARED_ROW_COUNT,
    SOURCE_002_FORBIDDEN_BASENAMES,
    SOURCE_002_FROZEN_OBJECT_PATH_ENV,
    SOURCE_002_MAPPING_POLICY_VERSION,
    SOURCE_002_OBJECT_IDENTITY,
    SOURCE_002_OBJECT_SHA256,
    SOURCE_002_OBSERVED_SCHEMA_SHA256,
    SOURCE_002_OWNER_ATTESTATION,
    SOURCE_002_SCHEMA_VERSION,
    SOURCE_002_SNAPSHOT_REFERENCE,
    SOURCE_002_SOURCE_DATASET,
    SOURCE_002_SOURCE_SYSTEM,
    SOURCE_002_SOURCE_VERSION,
    RawSourceArtifactIdentity,
    RawSourceArtifactIdentityInput,
    Source002IdentityFailureCode,
    Source002IdentityVerificationRecord,
    Source002IdentityVerificationStatus,
    SourceArtifactIntegrityConflict,
    SourceArtifactRegistration,
    SourceArtifactRegistrationResult,
)
from backend.app.s2_materialized_dataset.lane_a.source_row import (
    extract_source_002_workbook_evidence,
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


def _is_forbidden_source_path(path: Path) -> bool:
    return path.name in SOURCE_002_FORBIDDEN_BASENAMES


def _storage_locator_hash_for_path(path: Path) -> str:
    return sha256(str(path.resolve()).encode("utf-8")).hexdigest()


def storage_locator_hash_for_path(path: Path) -> str:
    return _storage_locator_hash_for_path(path)


def build_source_002_artifact_input(
    *,
    storage_locator_hash: str,
    source_artifact_sequence: int = 1,
) -> RawSourceArtifactIdentityInput:
    return RawSourceArtifactIdentityInput(
        source_system=SOURCE_002_SOURCE_SYSTEM,
        source_dataset=SOURCE_002_SOURCE_DATASET,
        source_version=SOURCE_002_SOURCE_VERSION,
        source_snapshot_reference=SOURCE_002_SNAPSHOT_REFERENCE,
        source_object_identity=SOURCE_002_OBJECT_IDENTITY,
        source_artifact_sequence=source_artifact_sequence,
        schema_version=SOURCE_002_SCHEMA_VERSION,
        mapping_policy_version=SOURCE_002_MAPPING_POLICY_VERSION,
        source_artifact_identity_version="v0-3-s2-source-artifact-identity-v1",
        source_owner_attestation=SOURCE_002_OWNER_ATTESTATION,
        cohort_manifest_reference=SOURCE_002_COHORT_ID,
        custody_record_reference=SOURCE_002_CUSTODY_RECORD,
        storage_locator_hash=storage_locator_hash,
    )


def _failure_record(
    *,
    failure_code: Source002IdentityFailureCode,
    source_object_sha256: str | None = None,
    byte_count: int | None = None,
    declared_source_row_count: int | None = None,
    observed_schema_sha256: str | None = None,
    object_present: bool = False,
) -> Source002IdentityVerificationRecord:
    return Source002IdentityVerificationRecord(
        status=Source002IdentityVerificationStatus.FAIL,
        failure_code=failure_code,
        source_object_sha256=source_object_sha256,
        byte_count=byte_count,
        declared_source_row_count=declared_source_row_count,
        observed_schema_sha256=observed_schema_sha256,
        object_present=object_present,
        ingest_authorized=False,
    )


def _pass_record(
    *,
    source_object_sha256: str,
    byte_count: int,
    declared_source_row_count: int,
    observed_schema_sha256: str,
) -> Source002IdentityVerificationRecord:
    return Source002IdentityVerificationRecord(
        status=Source002IdentityVerificationStatus.PASS,
        failure_code=None,
        source_object_sha256=source_object_sha256,
        byte_count=byte_count,
        declared_source_row_count=declared_source_row_count,
        observed_schema_sha256=observed_schema_sha256,
        source_cohort_manifest_sha256=SOURCE_002_COHORT_MANIFEST_SHA256,
        object_present=True,
        ingest_authorized=True,
    )


def _candidate_paths(*, search_roots: tuple[Path, ...]) -> tuple[Path, ...]:
    explicit = os.environ.get(SOURCE_002_FROZEN_OBJECT_PATH_ENV)
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    for root in search_roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if _is_forbidden_source_path(path):
                continue
            candidates.append(path)
    return tuple(candidates)


def verify_source_002_frozen_object_identity(
    *,
    search_roots: tuple[Path, ...] = (),
) -> tuple[Source002IdentityVerificationRecord, bytes | None, Path | None]:
    for path in _candidate_paths(search_roots=search_roots):
        if _is_forbidden_source_path(path):
            return (
                _failure_record(
                    failure_code=Source002IdentityFailureCode.FORBIDDEN_OBJECT,
                    object_present=True,
                ),
                None,
                path,
            )
        if not path.is_file():
            continue
        artifact_bytes = path.read_bytes()
        byte_count = len(artifact_bytes)
        object_sha256 = compute_source_artifact_sha256(artifact_bytes)
        if byte_count != SOURCE_002_BYTE_COUNT:
            continue
        if object_sha256 != SOURCE_002_OBJECT_SHA256:
            continue
        try:
            evidence = extract_source_002_workbook_evidence(artifact_bytes)
        except Exception:
            return (
                _failure_record(
                    failure_code=Source002IdentityFailureCode.HEADER_MISMATCH,
                    source_object_sha256=object_sha256,
                    byte_count=byte_count,
                    object_present=True,
                ),
                None,
                path,
            )
        if evidence.observed_schema_sha256 != SOURCE_002_OBSERVED_SCHEMA_SHA256:
            return (
                _failure_record(
                    failure_code=Source002IdentityFailureCode.OBSERVED_SCHEMA_SHA256_MISMATCH,
                    source_object_sha256=object_sha256,
                    byte_count=byte_count,
                    declared_source_row_count=evidence.row_count,
                    observed_schema_sha256=evidence.observed_schema_sha256,
                    object_present=True,
                ),
                None,
                path,
            )
        if evidence.row_count != SOURCE_002_DECLARED_ROW_COUNT:
            return (
                _failure_record(
                    failure_code=Source002IdentityFailureCode.ROW_COUNT_MISMATCH,
                    source_object_sha256=object_sha256,
                    byte_count=byte_count,
                    declared_source_row_count=evidence.row_count,
                    observed_schema_sha256=evidence.observed_schema_sha256,
                    object_present=True,
                ),
                None,
                path,
            )
        return (
            _pass_record(
                source_object_sha256=object_sha256,
                byte_count=byte_count,
                declared_source_row_count=evidence.row_count,
                observed_schema_sha256=evidence.observed_schema_sha256,
            ),
            artifact_bytes,
            path,
        )

    return (_failure_record(failure_code=Source002IdentityFailureCode.OBJECT_NOT_FOUND), None, None)
