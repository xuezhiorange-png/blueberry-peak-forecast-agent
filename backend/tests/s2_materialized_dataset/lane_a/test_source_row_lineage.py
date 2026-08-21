from __future__ import annotations

from decimal import Decimal

import pytest

from backend.app.s2_materialized_dataset.lane_a.import_batch import register_raw_import_batch
from backend.app.s2_materialized_dataset.lane_a.lineage import query_source_row_lineage_chain
from backend.app.s2_materialized_dataset.lane_a.schemas import (
    MissingExternalLogicalRecordIdError,
    RawImportBatchIdentityInput,
    RawSourceArtifactIdentityInput,
    SourceRowBusinessContent,
    SourceRowLineageInput,
    SourceRowRegistrationResult,
    SourceRowRevisionConflict,
)
from backend.app.s2_materialized_dataset.lane_a.source_artifact import register_raw_source_artifact
from backend.app.s2_materialized_dataset.lane_a.source_row import (
    build_source_row_identity,
    register_source_row_lineage,
)

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


def _batch_input() -> RawImportBatchIdentityInput:
    return RawImportBatchIdentityInput(
        external_batch_id="synthetic-batch-001",
        source_system="synthetic-scan-weight-system",
        source_dataset="synthetic-daily-marketable-net-kg",
        raw_payload_hash="a" * 64,
        import_policy_version="v0-3-s2-raw-import-policy-v1",
        schema_version="synthetic-schema-v1",
        mapping_policy_version="synthetic-mapping-policy-v1",
        validation_policy_version="synthetic-validation-policy-v1",
        source_cohort_id="source-002-s1-cohort-v1",
        import_request_identity="synthetic-import-request-v1",
    )


def _row_input(
    *,
    logical_id: str = "logical-record-001",
    revision_number: int = 1,
    row_number: int = 42,
    quantity: Decimal = Decimal("123.4500"),
) -> SourceRowLineageInput:
    return SourceRowLineageInput(
        external_logical_record_id=logical_id,
        external_revision_id=f"revision-{revision_number}",
        revision_number=revision_number,
        source_system="synthetic-scan-weight-system",
        source_version="synthetic-source-v1",
        schema_version="synthetic-schema-v1",
        source_row_identity_version="v0-3-s2-source-row-identity-v1",
        source_sheet_name="Sheet1",
        source_row_number=row_number,
        source_column_mapping_snapshot_hash="2" * 64,
        business_content=SourceRowBusinessContent(
            harvest_business_date="2026-02-10",
            farm_code="farm-a",
            subfarm_or_plot_code="subfarm-a",
            variety_code="variety-a",
            actual_harvest_quantity_kg=quantity,
        ),
    )


def _register_chain(session, artifact_bytes: bytes):
    artifact = register_raw_source_artifact(
        session,
        artifact_input=_artifact_input(),
        artifact_bytes=artifact_bytes,
    ).identity
    row = build_source_row_identity(
        artifact_identity_hash=artifact.source_artifact_identity_hash,
        batch_identity_hash="b" * 64,
        row_input=_row_input(),
    )
    batch = register_raw_import_batch(
        session,
        batch_input=_batch_input(),
        raw_source_artifact_identity_hash=artifact.source_artifact_identity_hash,
        source_row_identities=(row,),
    ).identity
    row = build_source_row_identity(
        artifact_identity_hash=artifact.source_artifact_identity_hash,
        batch_identity_hash=batch.raw_import_batch_identity_hash,
        row_input=_row_input(),
    )
    registered_row = register_source_row_lineage(
        session,
        artifact_identity_hash=artifact.source_artifact_identity_hash,
        batch_identity_hash=batch.raw_import_batch_identity_hash,
        row_input=_row_input(),
    )
    return artifact, batch, registered_row


def test_source_row_identity_rejects_missing_external_logical_record_id() -> None:
    row_input = _row_input()
    invalid = row_input.model_copy(update={"external_logical_record_id": "   "})

    with pytest.raises(MissingExternalLogicalRecordIdError):
        build_source_row_identity(
            artifact_identity_hash="a" * 64,
            batch_identity_hash="b" * 64,
            row_input=invalid,
        )


def test_source_row_number_is_lineage_not_identity(
    synthetic_artifact_bytes: bytes,
) -> None:
    artifact_hash = "a" * 64
    batch_hash = "b" * 64
    first = build_source_row_identity(
        artifact_identity_hash=artifact_hash,
        batch_identity_hash=batch_hash,
        row_input=_row_input(row_number=10),
    )
    second = build_source_row_identity(
        artifact_identity_hash=artifact_hash,
        batch_identity_hash=batch_hash,
        row_input=_row_input(row_number=99),
    )

    assert first.source_row_identity_hash == second.source_row_identity_hash


def test_register_source_row_replays_exact_identity(
    lane_a_session,
    synthetic_artifact_bytes: bytes,
) -> None:
    artifact, batch, _ = _register_chain(lane_a_session, synthetic_artifact_bytes)
    first = register_source_row_lineage(
        lane_a_session,
        artifact_identity_hash=artifact.source_artifact_identity_hash,
        batch_identity_hash=batch.raw_import_batch_identity_hash,
        row_input=_row_input(),
    )
    second = register_source_row_lineage(
        lane_a_session,
        artifact_identity_hash=artifact.source_artifact_identity_hash,
        batch_identity_hash=batch.raw_import_batch_identity_hash,
        row_input=_row_input(),
    )

    assert first.result == SourceRowRegistrationResult.EXACT_REPLAY
    assert second.result == SourceRowRegistrationResult.EXACT_REPLAY


def test_same_full_identity_with_different_decimal_content_is_revision_conflict(
    lane_a_session,
    synthetic_artifact_bytes: bytes,
) -> None:
    artifact = register_raw_source_artifact(
        lane_a_session,
        artifact_input=_artifact_input(),
        artifact_bytes=synthetic_artifact_bytes,
    ).identity
    row = build_source_row_identity(
        artifact_identity_hash=artifact.source_artifact_identity_hash,
        batch_identity_hash="b" * 64,
        row_input=_row_input(),
    )
    batch = register_raw_import_batch(
        lane_a_session,
        batch_input=_batch_input(),
        raw_source_artifact_identity_hash=artifact.source_artifact_identity_hash,
        source_row_identities=(row,),
    ).identity
    register_source_row_lineage(
        lane_a_session,
        artifact_identity_hash=artifact.source_artifact_identity_hash,
        batch_identity_hash=batch.raw_import_batch_identity_hash,
        row_input=_row_input(quantity=Decimal("100.0000")),
    )

    with pytest.raises(SourceRowRevisionConflict):
        register_source_row_lineage(
            lane_a_session,
            artifact_identity_hash=artifact.source_artifact_identity_hash,
            batch_identity_hash=batch.raw_import_batch_identity_hash,
            row_input=_row_input(quantity=Decimal("100.0001")),
        )


def test_different_revision_for_same_logical_record_retains_both_candidates(
    lane_a_session,
    synthetic_artifact_bytes: bytes,
) -> None:
    artifact, batch, _ = _register_chain(lane_a_session, synthetic_artifact_bytes)
    second = register_source_row_lineage(
        lane_a_session,
        artifact_identity_hash=artifact.source_artifact_identity_hash,
        batch_identity_hash=batch.raw_import_batch_identity_hash,
        row_input=_row_input(revision_number=2),
    )
    first = register_source_row_lineage(
        lane_a_session,
        artifact_identity_hash=artifact.source_artifact_identity_hash,
        batch_identity_hash=batch.raw_import_batch_identity_hash,
        row_input=_row_input(revision_number=1),
    )

    assert first.result == SourceRowRegistrationResult.EXACT_REPLAY
    assert second.result == SourceRowRegistrationResult.FIRST_SEEN
    assert first.identity.winner_selection_blocked is True
    assert second.identity.winner_selection_blocked is True
    assert (
        first.identity.source_row_identity_hash
        != second.identity.source_row_identity_hash
    )


def test_lineage_query_returns_artifact_batch_and_row(
    lane_a_session,
    synthetic_artifact_bytes: bytes,
) -> None:
    artifact, batch, row = _register_chain(lane_a_session, synthetic_artifact_bytes)

    chain = query_source_row_lineage_chain(
        lane_a_session,
        source_row_identity_hash=row.identity.source_row_identity_hash,
    )

    assert (
        chain.source_artifact.source_artifact_identity_hash
        == artifact.source_artifact_identity_hash
    )
    assert chain.import_batch.raw_import_batch_identity_hash == batch.raw_import_batch_identity_hash
    assert chain.source_row.source_row_identity_hash == row.identity.source_row_identity_hash
