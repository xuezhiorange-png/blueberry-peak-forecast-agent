from __future__ import annotations

import pytest

import backend.app.actual_harvest_import as actual_harvest_import
from backend.app.actual_harvest_import.enums import (
    ActualHarvestBatchSealStatus,
    ActualHarvestImportBatchStatus,
    ActualHarvestImportChannel,
    ActualHarvestMissingRecordSemantics,
    ActualHarvestPhysicalEvent,
    ActualHarvestQuantityBasis,
    ActualHarvestQuantityUnit,
    ActualHarvestRecordStatus,
    ActualHarvestValidationErrorCode,
    ActualHarvestValidationSeverity,
    SourceRecordedAtAuthorityStatus,
)

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def test_transport_and_source_enums_are_closed() -> None:
    assert {item.value for item in ActualHarvestImportChannel} == {"api", "csv", "xlsx"}
    assert {item.value for item in ActualHarvestPhysicalEvent} == {"FARM_PICK"}
    assert {item.value for item in ActualHarvestQuantityBasis} == {"OBSERVED_WEIGHT"}
    assert {item.value for item in ActualHarvestQuantityUnit} == {"KG"}
    assert {item.value for item in ActualHarvestMissingRecordSemantics} == {"UNKNOWN_NOT_ZERO"}
    assert {item.value for item in ActualHarvestRecordStatus} == {
        "ACTIVE",
        "CORRECTED",
        "VOID",
        "FINALIZED",
    }
    assert {item.value for item in SourceRecordedAtAuthorityStatus} == {
        "TRUSTED_SOURCE_TIMESTAMP",
        "USER_ASSERTED_UNVERIFIED",
        "MISSING",
        "CONFLICTING",
    }


def test_batch_and_validation_enums_are_closed() -> None:
    assert {item.value for item in ActualHarvestBatchSealStatus} == {"UNSEALED", "SEALED"}
    assert {item.value for item in ActualHarvestValidationSeverity} == {"ERROR", "WARNING"}
    assert {item.value for item in ActualHarvestImportBatchStatus} == {
        "RECEIVED",
        "UPLOADING",
        "SEALED",
        "PARSING",
        "PARSE_FAILED",
        "VALIDATING",
        "VALIDATION_FAILED",
        "VALIDATED",
        "COMMITTING",
        "COMMITTED",
        "COMMIT_FAILED",
        "CANCELLED",
    }


def test_validation_error_code_set_has_exactly_thirty_members() -> None:
    assert len(ActualHarvestValidationErrorCode) == 30
    assert "DELETED" not in ActualHarvestRecordStatus.__members__
    assert "SUPERSEDED" not in ActualHarvestRecordStatus.__members__


def test_public_contract_exports_are_exact() -> None:
    assert set(actual_harvest_import.__all__) == {
        "ActualHarvestBatchSealStatus",
        "ActualHarvestImportBatchInput",
        "ActualHarvestImportBatchStatus",
        "ActualHarvestImportChannel",
        "ActualHarvestImportRecordInput",
        "ActualHarvestMissingRecordSemantics",
        "ActualHarvestPhysicalEvent",
        "ActualHarvestQuantityBasis",
        "ActualHarvestQuantityUnit",
        "ActualHarvestRecordStatus",
        "ActualHarvestSourceSemanticsAttestation",
        "ActualHarvestValidationErrorCode",
        "ActualHarvestValidationIssue",
        "ActualHarvestValidationSeverity",
        "CanonicalActualHarvestImportBatch",
        "CanonicalActualHarvestImportRecord",
        "SourceRecordedAtAuthorityStatus",
        "has_trusted_source_timestamp",
        "sort_validation_issues",
        "validate_iana_timezone",
        "validate_non_empty_identifier",
        "validate_non_negative_finite_decimal",
        "validate_revision_local_shape",
        "validate_sha256_hex",
        "validate_source_recorded_at_authority_shape",
        "validate_timezone_aware_datetime",
    }
