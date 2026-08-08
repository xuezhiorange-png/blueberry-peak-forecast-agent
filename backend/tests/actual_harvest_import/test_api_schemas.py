from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from backend.app.actual_harvest_import.api_schemas import (
    ActualHarvestApiAppendRecordsRequest,
    ActualHarvestApiCreateImportRequest,
    ActualHarvestApiRecordInput,
)
from backend.app.actual_harvest_import.enums import (
    ActualHarvestImportChannel,
    ActualHarvestMissingRecordSemantics,
    ActualHarvestPhysicalEvent,
    ActualHarvestQuantityBasis,
    ActualHarvestQuantityUnit,
    ActualHarvestRecordStatus,
    SourceRecordedAtAuthorityStatus,
)
from backend.app.actual_harvest_import.schemas import ActualHarvestSourceSemanticsAttestation


def _create_payload() -> dict[str, object]:
    return {
        "import_channel": "api",
        "source_system": "farm-system",
        "source_dataset": "actual-harvest",
        "source_version": "2026-07",
        "external_batch_id": "batch-1",
        "idempotency_key": "key-1",
        "submitted_at": "2026-07-18T08:00:00Z",
        "submitted_by_identity": "operator-1",
        "expected_record_count_or_null": 1,
        "raw_payload_hash": "a" * 64,
        "schema_version": "actual-harvest-v1",
        "mapping_policy_version": "mapping-v1",
        "validation_policy_version": "validation-v1",
        "source_semantics_attestation": {
            "attestation_version": "v1",
            "physical_event": "FARM_PICK",
            "quantity_basis": "OBSERVED_WEIGHT",
            "quantity_unit": "KG",
            "missing_record_semantics": "UNKNOWN_NOT_ZERO",
        },
        "source_semantics_attestation_hash": "b" * 64,
    }


def _record_payload() -> dict[str, object]:
    return {
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
        "source_recorded_at_authority_status": "TRUSTED_SOURCE_TIMESTAMP",
        "source_recorded_at_authority_reference_or_null": "source-1",
        "revision_number": 1,
        "record_status": "ACTIVE",
        "supersedes_external_revision_id": None,
        "season_code": "2026",
        "farm_timezone": "Asia/Shanghai",
        "revised_at": "2026-07-17T08:00:00Z",
        "finalized_at": None,
        "source_note": "observed",
    }


def test_api_create_and_record_are_strict_transport_models() -> None:
    request = ActualHarvestApiCreateImportRequest.model_validate(_create_payload())
    assert request.import_channel == ActualHarvestImportChannel.API
    record = ActualHarvestApiRecordInput.model_validate(_record_payload())
    assert str(record.actual_harvest_quantity_kg) == "1.250000"
    assert request.submitted_at.tzinfo is not None
    assert datetime.now(UTC).tzinfo is not None


@pytest.mark.parametrize(
    "field",
    ["import_received_at", "ingested_at", "source_row_number", "source_sheet_name"],
)
def test_api_record_rejects_server_owned_fields(field: str) -> None:
    payload = _record_payload()
    payload[field] = 1
    with pytest.raises(ValidationError):
        ActualHarvestApiRecordInput.model_validate(payload)


def test_api_create_rejects_spreadsheet_file_metadata() -> None:
    payload = _create_payload()
    payload["source_file_name_or_null"] = "records.csv"
    with pytest.raises(ValidationError):
        ActualHarvestApiCreateImportRequest.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_schema_sha256_or_null", "a" * 64),
        ("schema_compatibility_policy_id_or_null", "synthetic-schema-policy-v1"),
        ("schema_compatibility_status_or_null", "SUPPORTED"),
    ],
)
def test_api_create_rejects_inactive_batch_a_schema_metadata(
    field: str,
    value: object,
) -> None:
    payload = _create_payload()
    payload[field] = value
    with pytest.raises(ValidationError):
        ActualHarvestApiCreateImportRequest.model_validate(payload)


def test_append_page_is_bounded() -> None:
    with pytest.raises(ValidationError):
        ActualHarvestApiAppendRecordsRequest(records=tuple(_record_payload() for _ in range(501)))


def test_attestation_types_remain_contract_values() -> None:
    attestation = ActualHarvestSourceSemanticsAttestation(
        attestation_version="v1",
        physical_event=ActualHarvestPhysicalEvent.FARM_PICK,
        quantity_basis=ActualHarvestQuantityBasis.OBSERVED_WEIGHT,
        quantity_unit=ActualHarvestQuantityUnit.KG,
        missing_record_semantics=ActualHarvestMissingRecordSemantics.UNKNOWN_NOT_ZERO,
    )
    assert attestation.quantity_unit == ActualHarvestQuantityUnit.KG
    assert ActualHarvestRecordStatus.ACTIVE.value == "ACTIVE"
    assert SourceRecordedAtAuthorityStatus.MISSING.value == "MISSING"
