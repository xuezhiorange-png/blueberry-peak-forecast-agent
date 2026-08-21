from __future__ import annotations

from decimal import Decimal

import pytest

from backend.app.s2_materialized_dataset.lane_a.import_batch import (
    build_raw_import_batch_identity,
    register_raw_import_batch,
)
from backend.app.s2_materialized_dataset.lane_a.persistence import (
    fetch_import_batch_by_identity_hash,
)
from backend.app.s2_materialized_dataset.lane_a.schemas import (
    ImportBatchIdempotencyConflict,
    ImportBatchRegistrationResult,
    RawImportBatchIdentityInput,
    RawSourceArtifactIdentityInput,
    SourceRowBusinessContent,
    SourceRowLineageInput,
)
from backend.app.s2_materialized_dataset.lane_a.source_artifact import (
    build_raw_source_artifact_identity,
    register_raw_source_artifact,
)
from backend.app.s2_materialized_dataset.lane_a.source_row import build_source_row_identity

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def _artifact_input() -> RawSourceArtifactIdentityInput:
    return RawSourceArtifactIdentityInput(
        source_system="synthetic-scan-weight-system",
        source_dataset="synthetic-daily-marketable-net-kg",
        source_version="synthetic-source-v1",
        source_snapshot_reference="synthetic-snapshot-ref-v1",
        source_object_identity="synthetic-object-ref-v1",
        source_artifact_sequence=1,
        schema_version="synthetic-schema-v1",
        mapping_policy_version="synthetic-mapping-policy-v1",
        source_artifact_identity_version="v0-3-s2-source-artifact-identity-v1",
        source_owner_attestation="synthetic-owner-attestation-v1",
        cohort_manifest_reference="source-002-s1-cohort-v1",
        custody_record_reference="synthetic-custody-record-v1",
        storage_locator_hash="1" * 64,
    )


def _row_input(*, logical_id: str = "logical-record-001", revision_number: int = 1):
    return SourceRowLineageInput(
        external_logical_record_id=logical_id,
        external_revision_id=f"revision-{revision_number}",
        revision_number=revision_number,
        source_system="synthetic-scan-weight-system",
        source_version="synthetic-source-v1",
        schema_version="synthetic-schema-v1",
        source_row_identity_version="v0-3-s2-source-row-identity-v1",
        source_sheet_name="Sheet1",
        source_row_number=42,
        source_column_mapping_snapshot_hash="2" * 64,
        business_content=SourceRowBusinessContent(
            harvest_business_date="2026-02-10",
            farm_code="farm-a",
            subfarm_or_plot_code="subfarm-a",
            variety_code="variety-a",
            actual_harvest_quantity_kg=Decimal("123.4500"),
        ),
    )


def _batch_input(*, raw_payload_hash: str = "a" * 64) -> RawImportBatchIdentityInput:
    return RawImportBatchIdentityInput(
        external_batch_id="synthetic-batch-001",
        source_system="synthetic-scan-weight-system",
        source_dataset="synthetic-daily-marketable-net-kg",
        raw_payload_hash=raw_payload_hash,
        import_policy_version="v0-3-s2-raw-import-policy-v1",
        schema_version="synthetic-schema-v1",
        mapping_policy_version="synthetic-mapping-policy-v1",
        validation_policy_version="synthetic-validation-policy-v1",
        source_cohort_id="source-002-s1-cohort-v1",
        import_request_identity="synthetic-import-request-v1",
    )


def _register_artifact(session, artifact_bytes: bytes):
    return register_raw_source_artifact(
        session,
        artifact_input=_artifact_input(),
        artifact_bytes=artifact_bytes,
    ).identity


def test_import_batch_identity_orders_source_row_content_hashes(
    synthetic_artifact_bytes: bytes,
) -> None:
    artifact = build_raw_source_artifact_identity(
        artifact_input=_artifact_input(),
        artifact_bytes=synthetic_artifact_bytes,
    )
    row_a = build_source_row_identity(
        artifact_identity_hash=artifact.source_artifact_identity_hash,
        batch_identity_hash="b" * 64,
        row_input=_row_input(logical_id="logical-a"),
    )
    row_b = build_source_row_identity(
        artifact_identity_hash=artifact.source_artifact_identity_hash,
        batch_identity_hash="b" * 64,
        row_input=_row_input(logical_id="logical-b"),
    )
    first = build_raw_import_batch_identity(
        batch_input=_batch_input(),
        raw_source_artifact_identity_hash=artifact.source_artifact_identity_hash,
        source_row_identities=(row_b, row_a),
    )
    second = build_raw_import_batch_identity(
        batch_input=_batch_input(),
        raw_source_artifact_identity_hash=artifact.source_artifact_identity_hash,
        source_row_identities=(row_a, row_b),
    )

    assert first.raw_import_batch_identity_hash == second.raw_import_batch_identity_hash


def test_import_batch_content_sha256_differs_from_identity_hash(
    synthetic_artifact_bytes: bytes,
) -> None:
    artifact = build_raw_source_artifact_identity(
        artifact_input=_artifact_input(),
        artifact_bytes=synthetic_artifact_bytes,
    )
    row = build_source_row_identity(
        artifact_identity_hash=artifact.source_artifact_identity_hash,
        batch_identity_hash="b" * 64,
        row_input=_row_input(),
    )
    identity = build_raw_import_batch_identity(
        batch_input=_batch_input(),
        raw_source_artifact_identity_hash=artifact.source_artifact_identity_hash,
        source_row_identities=(row,),
    )

    assert identity.content_sha256 != identity.raw_import_batch_identity_hash


def test_fetch_import_batch_returns_persisted_source_row_identity_hashes(
    lane_a_session,
    synthetic_artifact_bytes: bytes,
) -> None:
    artifact = _register_artifact(lane_a_session, synthetic_artifact_bytes)
    row = build_source_row_identity(
        artifact_identity_hash=artifact.source_artifact_identity_hash,
        batch_identity_hash="b" * 64,
        row_input=_row_input(),
    )
    registered = register_raw_import_batch(
        lane_a_session,
        batch_input=_batch_input(),
        raw_source_artifact_identity_hash=artifact.source_artifact_identity_hash,
        source_row_identities=(row,),
    )
    fetched = fetch_import_batch_by_identity_hash(
        lane_a_session,
        raw_import_batch_identity_hash=registered.identity.raw_import_batch_identity_hash,
    )

    assert fetched is not None
    assert fetched.source_row_identity_hashes == (row.source_row_identity_hash,)


def test_register_import_batch_is_idempotent(
    lane_a_session,
    synthetic_artifact_bytes: bytes,
) -> None:
    artifact = _register_artifact(lane_a_session, synthetic_artifact_bytes)
    row = build_source_row_identity(
        artifact_identity_hash=artifact.source_artifact_identity_hash,
        batch_identity_hash="b" * 64,
        row_input=_row_input(),
    )
    first = register_raw_import_batch(
        lane_a_session,
        batch_input=_batch_input(),
        raw_source_artifact_identity_hash=artifact.source_artifact_identity_hash,
        source_row_identities=(row,),
    )
    second = register_raw_import_batch(
        lane_a_session,
        batch_input=_batch_input(),
        raw_source_artifact_identity_hash=artifact.source_artifact_identity_hash,
        source_row_identities=(row,),
    )

    assert first.result == ImportBatchRegistrationResult.FIRST_SEEN
    assert second.result == ImportBatchRegistrationResult.EXACT_REPLAY
    assert (
        first.identity.raw_import_batch_identity_hash
        == second.identity.raw_import_batch_identity_hash
    )


def test_same_external_batch_with_different_payload_hash_is_conflict(
    lane_a_session,
    synthetic_artifact_bytes: bytes,
) -> None:
    artifact = _register_artifact(lane_a_session, synthetic_artifact_bytes)
    row = build_source_row_identity(
        artifact_identity_hash=artifact.source_artifact_identity_hash,
        batch_identity_hash="b" * 64,
        row_input=_row_input(),
    )
    register_raw_import_batch(
        lane_a_session,
        batch_input=_batch_input(raw_payload_hash="a" * 64),
        raw_source_artifact_identity_hash=artifact.source_artifact_identity_hash,
        source_row_identities=(row,),
    )

    with pytest.raises(ImportBatchIdempotencyConflict):
        register_raw_import_batch(
            lane_a_session,
            batch_input=_batch_input(raw_payload_hash="c" * 64),
            raw_source_artifact_identity_hash=artifact.source_artifact_identity_hash,
            source_row_identities=(row,),
        )


def test_same_external_batch_with_different_policy_version_is_conflict(
    lane_a_session,
    synthetic_artifact_bytes: bytes,
) -> None:
    artifact = _register_artifact(lane_a_session, synthetic_artifact_bytes)
    row = build_source_row_identity(
        artifact_identity_hash=artifact.source_artifact_identity_hash,
        batch_identity_hash="b" * 64,
        row_input=_row_input(),
    )
    register_raw_import_batch(
        lane_a_session,
        batch_input=_batch_input(),
        raw_source_artifact_identity_hash=artifact.source_artifact_identity_hash,
        source_row_identities=(row,),
    )
    changed = _batch_input().model_copy(
        update={"import_policy_version": "v0-3-s2-raw-import-policy-v2"}
    )

    with pytest.raises(ImportBatchIdempotencyConflict):
        register_raw_import_batch(
            lane_a_session,
            batch_input=changed,
            raw_source_artifact_identity_hash=artifact.source_artifact_identity_hash,
            source_row_identities=(row,),
        )
