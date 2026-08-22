from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.s2_materialized_dataset.lane_a.hashes import compute_source_artifact_sha256
from backend.app.s2_materialized_dataset.lane_a.lineage import (
    controlled_ingest_source_002_from_environment,
    run_source_002_identity_verification,
)
from backend.app.s2_materialized_dataset.lane_a.schemas import (
    SOURCE_002_BYTE_COUNT,
    SOURCE_002_COHORT_ID,
    SOURCE_002_COHORT_MANIFEST_SHA256,
    SOURCE_002_DECLARED_ROW_COUNT,
    SOURCE_002_FORBIDDEN_BASENAMES,
    SOURCE_002_OBJECT_SHA256,
    SOURCE_002_OBSERVED_SCHEMA_SHA256,
    SOURCE_002_SCHEMA_VERSION,
    SOURCE_002_SNAPSHOT_REFERENCE,
    SOURCE_002_SOURCE_DATASET,
    SOURCE_002_SOURCE_SYSTEM,
    SOURCE_002_SOURCE_VERSION,
    RawSourceArtifactIdentityInput,
    Source002ControlledIngestBlocked,
    Source002IdentityFailureCode,
    Source002IdentityVerificationStatus,
    SourceArtifactIntegrityConflict,
    SourceArtifactRegistrationResult,
)
from backend.app.s2_materialized_dataset.lane_a.schemas import (
    SOURCE_002_EXPECTED_HEADERS,
    Source002ParseError,
)
from backend.app.s2_materialized_dataset.lane_a.source_artifact import (
    build_raw_source_artifact_identity,
    register_raw_source_artifact,
    source_002_frozen_storage_locator_hash,
    verify_source_002_frozen_object_identity,
)
from backend.app.s2_materialized_dataset.lane_a.source_row import (
    compute_source_002_observed_schema_sha256,
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


def test_source_002_e1_fails_closed_when_frozen_object_is_absent(tmp_path: Path) -> None:
    record = run_source_002_identity_verification(search_roots=(tmp_path,))

    assert record.status == Source002IdentityVerificationStatus.FAIL
    assert record.failure_code == Source002IdentityFailureCode.OBJECT_NOT_FOUND
    assert record.ingest_authorized is False
    assert record.object_present is False


def test_source_002_e1_rejects_forbidden_receipt_workbook(tmp_path: Path) -> None:
    forbidden_name = next(iter(SOURCE_002_FORBIDDEN_BASENAMES))
    forbidden_path = tmp_path / forbidden_name
    forbidden_path.write_bytes(b"forbidden-receipt-bytes")

    record, artifact_bytes, matched_path = verify_source_002_frozen_object_identity(
        search_roots=(tmp_path,)
    )

    assert record.status == Source002IdentityVerificationStatus.FAIL
    assert record.failure_code == Source002IdentityFailureCode.OBJECT_NOT_FOUND
    assert artifact_bytes is None
    assert matched_path is None


def test_source_002_e1_rejects_byte_count_without_matching_object_sha256(tmp_path: Path) -> None:
    mismatched_path = tmp_path / "candidate-source-002.xls"
    mismatched_path.write_bytes(b"x" * SOURCE_002_BYTE_COUNT)

    record, artifact_bytes, matched_path = verify_source_002_frozen_object_identity(
        search_roots=(tmp_path,)
    )

    assert record.status == Source002IdentityVerificationStatus.FAIL
    assert record.failure_code == Source002IdentityFailureCode.OBJECT_NOT_FOUND
    assert artifact_bytes is None
    assert matched_path is None
    assert compute_source_artifact_sha256(mismatched_path.read_bytes()) != SOURCE_002_OBJECT_SHA256


def test_source_002_e1_record_binds_frozen_identity_metadata() -> None:
    record = run_source_002_identity_verification()

    assert record.source_system == SOURCE_002_SOURCE_SYSTEM
    assert record.source_dataset == SOURCE_002_SOURCE_DATASET
    assert record.source_version == SOURCE_002_SOURCE_VERSION
    assert record.source_snapshot_reference == SOURCE_002_SNAPSHOT_REFERENCE
    assert record.observed_schema_version == SOURCE_002_SCHEMA_VERSION
    assert record.source_cohort_id == SOURCE_002_COHORT_ID
    assert record.source_cohort_manifest_sha256 == SOURCE_002_COHORT_MANIFEST_SHA256
    assert record.declared_source_row_count in (None, SOURCE_002_DECLARED_ROW_COUNT)
    assert record.observed_schema_sha256 in (None, SOURCE_002_OBSERVED_SCHEMA_SHA256)


def test_source_002_e2_is_blocked_when_e1_does_not_pass(lane_a_session) -> None:
    with pytest.raises(Source002ControlledIngestBlocked):
        controlled_ingest_source_002_from_environment(lane_a_session)


def test_source_002_storage_locator_hash_is_cross_environment_stable() -> None:
    first = source_002_frozen_storage_locator_hash()
    second = source_002_frozen_storage_locator_hash()

    assert first == second
    assert first != "b8808e32eec032060894b9839dae7969bccad50ba4bf0c399fe19c5b16958eb9"
    assert len(first) == 64


def test_source_002_observed_schema_sha256_matches_s1_binding() -> None:
    observed = compute_source_002_observed_schema_sha256(
        header_fields=SOURCE_002_EXPECTED_HEADERS,
    )

    assert observed == SOURCE_002_OBSERVED_SCHEMA_SHA256


def test_source_002_observed_schema_sha256_rejects_non_frozen_headers() -> None:
    with pytest.raises(Source002ParseError):
        compute_source_002_observed_schema_sha256(header_fields=("时间",))


def test_source_002_e1_skips_wrong_size_before_reading_bytes(tmp_path: Path, monkeypatch) -> None:
    reads: list[Path] = []
    original_read_bytes = Path.read_bytes

    def _tracking_read_bytes(self: Path) -> bytes:
        reads.append(self)
        return original_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", _tracking_read_bytes)

    wrong_size_path = tmp_path / "wrong-size-candidate.xls"
    wrong_size_path.write_bytes(b"x" * (SOURCE_002_BYTE_COUNT - 1))

    record, _, _ = verify_source_002_frozen_object_identity(search_roots=(tmp_path,))

    assert record.failure_code == Source002IdentityFailureCode.OBJECT_NOT_FOUND
    assert reads == []
