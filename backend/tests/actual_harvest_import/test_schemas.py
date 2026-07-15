from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.app.actual_harvest_import.enums import (
    ActualHarvestBatchSealStatus,
    ActualHarvestImportBatchStatus,
    ActualHarvestImportChannel,
    ActualHarvestMissingRecordSemantics,
    ActualHarvestPhysicalEvent,
    ActualHarvestQuantityBasis,
    ActualHarvestQuantityUnit,
    ActualHarvestRecordStatus,
    SourceRecordedAtAuthorityStatus,
)
from backend.app.actual_harvest_import.schemas import (
    ActualHarvestImportBatchInput,
    ActualHarvestImportRecordInput,
    ActualHarvestValidationIssue,
    CanonicalActualHarvestImportBatch,
    CanonicalActualHarvestImportRecord,
    sort_validation_issues,
)

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def _attestation() -> dict[str, str]:
    return {
        "attestation_version": "q2a-source-semantics-v1",
        "physical_event": ActualHarvestPhysicalEvent.FARM_PICK,
        "quantity_basis": ActualHarvestQuantityBasis.OBSERVED_WEIGHT,
        "quantity_unit": ActualHarvestQuantityUnit.KG,
        "missing_record_semantics": ActualHarvestMissingRecordSemantics.UNKNOWN_NOT_ZERO,
    }


def _record(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "external_logical_record_id": "logical-1",
        "external_revision_id": "revision-1",
        "source_system": "farm-ledger",
        "external_batch_id": "batch-1",
        "harvest_business_date": date(2026, 1, 2),
        "farm_code": "farm-1",
        "subfarm_or_plot_code": "plot-1",
        "variety_code": "variety-1",
        "actual_harvest_quantity_kg": Decimal("0"),
        "source_recorded_at": datetime(2026, 1, 2, 8, tzinfo=UTC),
        "source_recorded_at_authority_status": (
            SourceRecordedAtAuthorityStatus.TRUSTED_SOURCE_TIMESTAMP
        ),
        "source_recorded_at_authority_reference_or_null": "source-row-1",
        "revision_number": 1,
        "record_status": ActualHarvestRecordStatus.ACTIVE,
        "supersedes_external_revision_id": None,
        "season_code": "2026",
        "farm_timezone": "Asia/Shanghai",
        "revised_at": None,
        "finalized_at": None,
        "source_row_number": 1,
        "source_sheet_name": "Harvest",
        "source_note": None,
    }
    value.update(overrides)
    return value


def _batch(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "import_channel": ActualHarvestImportChannel.API,
        "source_system": "farm-ledger",
        "source_dataset": "daily-harvest",
        "source_version": "2026.1",
        "external_batch_id": "batch-1",
        "idempotency_key": "idem-1",
        "submitted_at": datetime(2026, 1, 3, 8, tzinfo=UTC),
        "submitted_by_identity": "operator-1",
        "expected_record_count_or_null": 1,
        "source_file_name_or_null": None,
        "source_file_hash_or_null": None,
        "raw_payload_hash": "a" * 64,
        "schema_version": "q2a-actual-harvest-v1",
        "mapping_policy_version": "q2a-mapping-v1",
        "validation_policy_version": "q2a-validation-v1",
        "source_semantics_attestation": _attestation(),
        "source_semantics_attestation_hash": "b" * 64,
    }
    value.update(overrides)
    return value


def test_same_record_contract_accepts_api_csv_and_xlsx_channel_context() -> None:
    record = ActualHarvestImportRecordInput.model_validate(_record())
    assert record.actual_harvest_quantity_kg == Decimal("0")
    for channel in ActualHarvestImportChannel:
        batch = ActualHarvestImportBatchInput.model_validate(_batch(import_channel=channel))
        assert batch.import_channel is channel


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("external_logical_record_id", " "),
        ("actual_harvest_quantity_kg", -1),
        ("actual_harvest_quantity_kg", float("nan")),
        ("actual_harvest_quantity_kg", float("inf")),
        ("harvest_business_date", datetime(2026, 1, 2, tzinfo=UTC)),
        ("farm_timezone", "Not/AZone"),
        ("source_recorded_at", datetime(2026, 1, 2)),
        ("source_recorded_at_authority_reference_or_null", " "),
    ],
)
def test_record_rejects_invalid_scalar_shapes(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        ActualHarvestImportRecordInput.model_validate(_record(**{field: value}))


def test_zero_quantity_is_explicitly_valid() -> None:
    record = ActualHarvestImportRecordInput.model_validate(_record(actual_harvest_quantity_kg="0"))
    assert record.actual_harvest_quantity_kg == Decimal("0")


def test_source_row_number_is_null_or_positive_and_hashes_are_lowercase() -> None:
    with pytest.raises(ValidationError):
        ActualHarvestImportRecordInput.model_validate(_record(source_row_number=0))
    with pytest.raises(ValidationError):
        ActualHarvestImportBatchInput.model_validate(_batch(raw_payload_hash="A" * 64))


def test_source_time_status_rules_are_cross_field_validated() -> None:
    with pytest.raises(ValidationError):
        ActualHarvestImportRecordInput.model_validate(
            _record(
                source_recorded_at=None,
                source_recorded_at_authority_reference_or_null=None,
            )
        )
    assert (
        ActualHarvestImportRecordInput.model_validate(
            _record(
                source_recorded_at=None,
                source_recorded_at_authority_status=SourceRecordedAtAuthorityStatus.MISSING,
                source_recorded_at_authority_reference_or_null=None,
            )
        ).source_recorded_at
        is None
    )


def test_server_owned_record_fields_are_forbidden_on_input_and_required_on_canonical() -> None:
    with pytest.raises(ValidationError):
        ActualHarvestImportRecordInput.model_validate(
            _record(import_received_at=datetime(2026, 1, 3, tzinfo=UTC))
        )
    canonical = CanonicalActualHarvestImportRecord.model_validate(
        _record(
            import_received_at=datetime(2026, 1, 3, tzinfo=UTC),
            ingested_at=datetime(2026, 1, 3, 8, tzinfo=UTC),
        )
    )
    with pytest.raises(ValidationError):
        canonical.__setattr__("source_note", "changed")
    assert canonical.import_received_at.tzinfo is not None


def test_record_is_immutable_and_revision_shape_is_local() -> None:
    record = ActualHarvestImportRecordInput.model_validate(_record())
    with pytest.raises(ValidationError):
        record.__setattr__("external_revision_id", "revision-2")
    with pytest.raises(ValidationError):
        ActualHarvestImportRecordInput.model_validate(
            _record(
                revision_number=2,
                external_revision_id="revision-2",
                supersedes_external_revision_id=None,
            )
        )


def test_batch_input_rejects_server_owned_fields_and_canonical_batch_enforces_seal_shape() -> None:
    with pytest.raises(ValidationError):
        ActualHarvestImportBatchInput.model_validate(_batch(import_id=1))
    common = _batch(
        import_id=1,
        import_received_at=datetime(2026, 1, 3, 8, tzinfo=UTC),
        ingested_at=datetime(2026, 1, 3, 8, 1, tzinfo=UTC),
        uploaded_record_count=1,
        sealed_record_count_or_null=1,
        sealed_at_or_null=datetime(2026, 1, 3, 9, tzinfo=UTC),
        sealed_by_identity_or_null="operator-1",
        seal_status=ActualHarvestBatchSealStatus.SEALED,
        server_raw_payload_hash_or_null="c" * 64,
        canonical_batch_hash_or_null="d" * 64,
        seal_manifest_hash_or_null="e" * 64,
        status=ActualHarvestImportBatchStatus.SEALED,
        record_count=1,
        valid_record_count=1,
        invalid_record_count=0,
        committed_record_count=0,
        created_at=datetime(2026, 1, 3, 8, tzinfo=UTC),
        validated_at_or_null=None,
        committed_at_or_null=None,
    )
    batch = CanonicalActualHarvestImportBatch.model_validate(common)
    assert batch.seal_status is ActualHarvestBatchSealStatus.SEALED
    with pytest.raises(ValidationError):
        CanonicalActualHarvestImportBatch.model_validate(
            {**common, "seal_status": ActualHarvestBatchSealStatus.UNSEALED}
        )


def test_validation_issue_sort_is_independent_of_input_order() -> None:
    base = {
        "error_code": "UNKNOWN_FIELD",
        "severity": "ERROR",
        "import_id": 1,
        "external_logical_record_id_or_null": None,
        "external_revision_id_or_null": None,
        "field_path_or_null": None,
        "message_template_id": "unknown-field",
        "details": {"field": "unexpected"},
    }
    first = ActualHarvestValidationIssue.model_validate({**base, "record_index_or_null": 2})
    second = ActualHarvestValidationIssue.model_validate(
        {**base, "record_index_or_null": None, "message_template_id": "required-field"}
    )
    assert sort_validation_issues([first, second]) == (second, first)


@pytest.mark.parametrize("details", [{"token": "secret"}, {"raw_row": {"value": 1}}])
def test_validation_issue_details_reject_sensitive_or_raw_payloads(
    details: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ActualHarvestValidationIssue.model_validate(
            {
                "error_code": "UNKNOWN_FIELD",
                "severity": "ERROR",
                "import_id": 1,
                "record_index_or_null": None,
                "external_logical_record_id_or_null": None,
                "external_revision_id_or_null": None,
                "field_path_or_null": None,
                "message_template_id": "unknown-field",
                "details": details,
            }
        )
