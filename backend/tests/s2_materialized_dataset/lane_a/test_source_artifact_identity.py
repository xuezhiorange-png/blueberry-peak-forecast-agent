from __future__ import annotations

import pytest

from backend.app.s2_materialized_dataset.lane_a.schemas import (
    RawSourceArtifactIdentityInput,
    SourceArtifactIntegrityConflict,
    SourceArtifactRegistrationResult,
)
from backend.app.s2_materialized_dataset.lane_a.source_artifact import (
    build_raw_source_artifact_identity,
    register_raw_source_artifact,
)

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def _artifact_input(
    *,
    artifact_sequence: int = 1,
    snapshot_reference: str = "synthetic-snapshot-ref-v1",
    object_identity: str = "synthetic-object-ref-v1",
) -> RawSourceArtifactIdentityInput:
    return RawSourceArtifactIdentityInput(
        source_system="synthetic-scan-weight-system",
        source_dataset="synthetic-daily-marketable-net-kg",
        source_version="synthetic-source-v1",
        source_snapshot_reference=snapshot_reference,
        source_object_identity=object_identity,
        source_artifact_sequence=artifact_sequence,
        schema_version="synthetic-schema-v1",
        mapping_policy_version="synthetic-mapping-policy-v1",
        source_artifact_identity_version="v0-3-s2-source-artifact-identity-v1",
        source_owner_attestation="synthetic-owner-attestation-v1",
        cohort_manifest_reference="source-002-s1-cohort-v1",
        custody_record_reference="synthetic-custody-record-v1",
        storage_locator_hash="1" * 64,
    )


def test_source_artifact_identity_is_deterministic_from_synthetic_fixture(
    synthetic_artifact_bytes: bytes,
) -> None:
    first = build_raw_source_artifact_identity(
        artifact_input=_artifact_input(),
        artifact_bytes=synthetic_artifact_bytes,
    )
    second = build_raw_source_artifact_identity(
        artifact_input=_artifact_input(),
        artifact_bytes=synthetic_artifact_bytes,
    )

    assert first.source_artifact_identity_hash == second.source_artifact_identity_hash
    assert first.source_artifact_sha256 == second.source_artifact_sha256
    assert len(first.source_artifact_identity_hash) == 64
    assert first.source_artifact_identity_hash.islower()


def test_source_artifact_sha256_is_over_immutable_bytes_only(
    synthetic_artifact_bytes: bytes,
    synthetic_second_artifact_bytes: bytes,
) -> None:
    same_metadata = _artifact_input()
    first = build_raw_source_artifact_identity(
        artifact_input=same_metadata,
        artifact_bytes=synthetic_artifact_bytes,
    )
    second = build_raw_source_artifact_identity(
        artifact_input=same_metadata,
        artifact_bytes=synthetic_second_artifact_bytes,
    )

    assert first.source_artifact_sha256 != second.source_artifact_sha256
    assert first.source_artifact_identity_hash == second.source_artifact_identity_hash


def test_register_source_artifact_replays_exact_identity(
    lane_a_session,
    synthetic_artifact_bytes: bytes,
) -> None:
    artifact_input = _artifact_input()
    first = register_raw_source_artifact(
        lane_a_session,
        artifact_input=artifact_input,
        artifact_bytes=synthetic_artifact_bytes,
    )
    second = register_raw_source_artifact(
        lane_a_session,
        artifact_input=artifact_input,
        artifact_bytes=synthetic_artifact_bytes,
    )

    assert first.result == SourceArtifactRegistrationResult.FIRST_SEEN
    assert second.result == SourceArtifactRegistrationResult.EXACT_REPLAY
    assert (
        first.identity.source_artifact_identity_hash
        == second.identity.source_artifact_identity_hash
    )


def test_duplicate_source_artifact_identity_with_different_bytes_is_conflict(
    lane_a_session,
    synthetic_artifact_bytes: bytes,
    synthetic_second_artifact_bytes: bytes,
) -> None:
    artifact_input = _artifact_input()
    register_raw_source_artifact(
        lane_a_session,
        artifact_input=artifact_input,
        artifact_bytes=synthetic_artifact_bytes,
    )

    with pytest.raises(SourceArtifactIntegrityConflict):
        register_raw_source_artifact(
            lane_a_session,
            artifact_input=artifact_input,
            artifact_bytes=synthetic_second_artifact_bytes,
        )


def test_different_artifact_sequence_produces_distinct_identity(
    synthetic_artifact_bytes: bytes,
) -> None:
    first = build_raw_source_artifact_identity(
        artifact_input=_artifact_input(artifact_sequence=1),
        artifact_bytes=synthetic_artifact_bytes,
    )
    second = build_raw_source_artifact_identity(
        artifact_input=_artifact_input(artifact_sequence=2),
        artifact_bytes=synthetic_artifact_bytes,
    )

    assert first.source_artifact_identity_hash != second.source_artifact_identity_hash
