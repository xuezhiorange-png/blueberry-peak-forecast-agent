from __future__ import annotations

from datetime import UTC, datetime

from backend.app.actual_harvest_import.api_schemas import (
    ActualHarvestApiCreateImportRequest,
)
from backend.app.actual_harvest_import.canonical_hashes import (
    compute_canonical_record_hash,
    compute_create_payload_hash,
)
from backend.app.actual_harvest_import.enums import (
    ActualHarvestBatchSealStatus,
    ActualHarvestImportBatchStatus,
    ActualHarvestImportChannel,
    ActualHarvestMissingRecordSemantics,
    ActualHarvestPhysicalEvent,
    ActualHarvestQuantityBasis,
    ActualHarvestQuantityUnit,
)
from backend.app.actual_harvest_import.schemas import (
    ActualHarvestSourceSemanticsAttestation,
    CanonicalActualHarvestImportRecord,
)
from backend.app.actual_harvest_import.validation_hashes import (
    ACTUAL_HARVEST_SEASON_RESOLVER_VERSION,
    compute_instance_identity_hash,
    compute_mapping_snapshot_hash,
    compute_request_identity_hash,
    compute_resolved_identity_snapshot_hash,
    compute_validation_result_hash,
)


def _create() -> ActualHarvestApiCreateImportRequest:
    return ActualHarvestApiCreateImportRequest(
        import_channel=ActualHarvestImportChannel.API,
        source_system="farm-system",
        source_dataset="actual-harvest",
        source_version="v1",
        external_batch_id="batch-1",
        idempotency_key="key-1",
        submitted_at=datetime(2026, 7, 18, tzinfo=UTC),
        submitted_by_identity="operator-1",
        raw_payload_hash="a" * 64,
        schema_version="schema-v1",
        mapping_policy_version="mapping-v1",
        validation_policy_version="validation-v1",
        source_semantics_attestation=ActualHarvestSourceSemanticsAttestation(
            attestation_version="v1",
            physical_event=ActualHarvestPhysicalEvent.FARM_PICK,
            quantity_basis=ActualHarvestQuantityBasis.OBSERVED_WEIGHT,
            quantity_unit=ActualHarvestQuantityUnit.KG,
            missing_record_semantics=ActualHarvestMissingRecordSemantics.UNKNOWN_NOT_ZERO,
        ),
        source_semantics_attestation_hash="b" * 64,
    )


def test_create_hash_is_stable_for_equal_payload() -> None:
    assert compute_create_payload_hash(_create()) == compute_create_payload_hash(_create())


def test_record_hash_excludes_transport_provenance() -> None:
    record = {
        "external_logical_record_id": "logical-1",
        "external_revision_id": "revision-1",
        "source_system": "farm-system",
        "external_batch_id": "batch-1",
        "harvest_business_date": "2026-07-17",
        "farm_code": "farm-1",
        "subfarm_or_plot_code": "plot-1",
        "variety_code": "variety-1",
        "actual_harvest_quantity_kg": "1.250000",
        "source_recorded_at": "2026-07-17T08:00:00Z",
        "source_recorded_at_authority_status": "USER_ASSERTED_UNVERIFIED",
        "source_recorded_at_authority_reference_or_null": "source-1",
        "revision_number": 1,
        "record_status": "ACTIVE",
        "supersedes_external_revision_id": None,
        "season_code": None,
        "farm_timezone": None,
        "revised_at": None,
        "finalized_at": None,
        "source_note": None,
    }
    left = CanonicalActualHarvestImportRecord.model_validate(
        {
            **record,
            "import_received_at": "2026-07-18T08:00:00Z",
            "ingested_at": "2026-07-18T08:00:00Z",
        }
    )
    right = CanonicalActualHarvestImportRecord.model_validate(
        {
            **record,
            "import_received_at": "2026-07-18T08:00:00Z",
            "ingested_at": "2026-07-18T08:00:00Z",
            "source_row_number": 99,
            "source_sheet_name": "sheet",
        }
    )
    assert compute_canonical_record_hash(left) == compute_canonical_record_hash(right)


def test_lifecycle_status_values_are_not_validation_or_commit_states() -> None:
    assert ActualHarvestImportBatchStatus.UPLOADING.value == "UPLOADING"
    assert ActualHarvestBatchSealStatus.UNSEALED.value == "UNSEALED"
    assert ActualHarvestImportBatchStatus.COMMITTED.value not in {"UPLOADING", "SEALED"}


def _validation_hash(record_hashes: list[dict[str, object]]) -> str:
    return compute_validation_result_hash(
        seal_manifest_hash="a" * 64,
        mapping_snapshot_hash="b" * 64,
        mapping_policy_version="mapping-v1",
        validation_policy_version="validation-v1",
        record_hashes=record_hashes,
        mapping_outcomes=[],
        nodes=[],
        edges=[],
        errors=[],
        warnings=[],
        counts={"valid": 2, "invalid": 0, "errors": 0, "warnings": 0},
        committed_lineage_basis_hash="c" * 64,
        lineage_graph_hash="d" * 64,
        resolved_identity_snapshot_hash="e" * 64,
    )


def test_validation_result_hash_is_invariant_to_input_and_query_order() -> None:
    records = [
        {
            "source_system": "farm-system",
            "external_logical_record_id": "logical-2",
            "revision_number": 1,
            "external_revision_id": "revision-2",
            "canonical_record_hash": "2" * 64,
        },
        {
            "source_system": "farm-system",
            "external_logical_record_id": "logical-1",
            "revision_number": 1,
            "external_revision_id": "revision-1",
            "canonical_record_hash": "1" * 64,
        },
    ]
    assert _validation_hash(records) == _validation_hash(list(reversed(records)))


def test_validation_result_hash_binds_record_key_to_record_hash() -> None:
    records = [
        {
            "source_system": "farm-system",
            "external_logical_record_id": "logical-1",
            "revision_number": 1,
            "external_revision_id": "revision-1",
            "canonical_record_hash": "1" * 64,
        },
        {
            "source_system": "farm-system",
            "external_logical_record_id": "logical-2",
            "revision_number": 1,
            "external_revision_id": "revision-2",
            "canonical_record_hash": "2" * 64,
        },
    ]
    reassociated = [
        {**records[0], "canonical_record_hash": "2" * 64},
        {**records[1], "canonical_record_hash": "1" * 64},
    ]
    assert _validation_hash(records) != _validation_hash(reassociated)


def test_validation_result_hash_changes_when_record_business_hash_changes() -> None:
    records = [
        {
            "source_system": "farm-system",
            "external_logical_record_id": "logical-1",
            "revision_number": 1,
            "external_revision_id": "revision-1",
            "canonical_record_hash": "1" * 64,
        },
        {
            "source_system": "farm-system",
            "external_logical_record_id": "logical-2",
            "revision_number": 1,
            "external_revision_id": "revision-2",
            "canonical_record_hash": "2" * 64,
        },
    ]
    changed = [{**records[0], "canonical_record_hash": "3" * 64}, records[1]]
    assert _validation_hash(records) != _validation_hash(changed)


def test_season_resolver_version_is_bound_to_validation_identities_and_hashes() -> None:
    kwargs = {
        "import_id": "import-1",
        "seal_manifest_hash": "a" * 64,
        "mapping_policy_version": "mapping-v1",
        "validation_policy_version": "validation-v1",
    }
    request_v1 = compute_request_identity_hash(
        **kwargs, season_resolver_version=ACTUAL_HARVEST_SEASON_RESOLVER_VERSION
    )
    request_v2 = compute_request_identity_hash(**kwargs, season_resolver_version="resolver-v2")
    assert request_v1 != request_v2

    instance_v1 = compute_instance_identity_hash(
        **kwargs,
        committed_lineage_basis_hash="b" * 64,
        season_resolver_version=ACTUAL_HARVEST_SEASON_RESOLVER_VERSION,
    )
    instance_v2 = compute_instance_identity_hash(
        **kwargs,
        committed_lineage_basis_hash="b" * 64,
        season_resolver_version="resolver-v2",
    )
    assert instance_v1 != instance_v2

    outcome = {
        "source_system": "farm-system",
        "external_logical_record_id": "logical-1",
        "revision_number": 1,
        "external_revision_id": "revision-1",
        "source_field": "season_code",
        "source_code": "2026",
        "registry_version": "registry-v1",
        "mapping_policy_version": "mapping-v1",
        "registry_entry_hash": "c" * 64,
        "target_type": "SEASON",
        "target_business_key": "2026",
        "target_parent_business_key": None,
        "resolved_master_business_key": "2026",
        "resolved_master_parent_business_key": None,
        "resolved_master_record_hash": "d" * 64,
        "resolution_mode": "REGISTRY_EXACT",
        "resolver_version": ACTUAL_HARVEST_SEASON_RESOLVER_VERSION,
        "outcome": "MAPPED",
    }
    assert compute_resolved_identity_snapshot_hash(
        [outcome]
    ) != compute_resolved_identity_snapshot_hash(
        [{**outcome, "resolver_version": "resolver-v2"}], season_resolver_version="resolver-v2"
    )
    snapshot_kwargs = {
        "registry_version": "registry-v1",
        "mapping_policy_version": "mapping-v1",
        "entries": [
            {"source_field": "season_code", "source_code": "2026", "target_type": "SEASON"}
        ],
    }
    assert compute_mapping_snapshot_hash(
        **snapshot_kwargs, season_resolver_version=ACTUAL_HARVEST_SEASON_RESOLVER_VERSION
    ) != compute_mapping_snapshot_hash(**snapshot_kwargs, season_resolver_version="resolver-v2")
    assert _validation_hash(
        [
            {
                "source_system": "farm-system",
                "external_logical_record_id": "logical-1",
                "revision_number": 1,
                "external_revision_id": "revision-1",
                "canonical_record_hash": "1" * 64,
            }
        ]
    ) != compute_validation_result_hash(
        seal_manifest_hash="a" * 64,
        mapping_snapshot_hash="b" * 64,
        mapping_policy_version="mapping-v1",
        validation_policy_version="validation-v1",
        season_resolver_version="resolver-v2",
        record_hashes=[
            {
                "source_system": "farm-system",
                "external_logical_record_id": "logical-1",
                "revision_number": 1,
                "external_revision_id": "revision-1",
                "canonical_record_hash": "1" * 64,
            }
        ],
        mapping_outcomes=[],
        nodes=[],
        edges=[],
        errors=[],
        warnings=[],
        counts={"valid": 1, "invalid": 0, "errors": 0, "warnings": 0},
        committed_lineage_basis_hash="c" * 64,
        lineage_graph_hash="d" * 64,
        resolved_identity_snapshot_hash="e" * 64,
    )
