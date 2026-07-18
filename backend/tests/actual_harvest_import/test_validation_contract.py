from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

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
from backend.app.actual_harvest_import.validation import (
    has_trusted_source_timestamp,
    validate_iana_timezone,
    validate_non_empty_identifier,
    validate_non_negative_finite_decimal,
    validate_revision_local_shape,
    validate_sha256_hex,
    validate_source_recorded_at_authority_shape,
    validate_timezone_aware_datetime,
)

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def test_scalar_helpers_are_strict_and_deterministic() -> None:
    assert validate_non_empty_identifier("  farm-1  ") == "farm-1"
    assert validate_non_negative_finite_decimal("0.00") == Decimal("0.00")
    assert validate_iana_timezone("Asia/Shanghai") == "Asia/Shanghai"
    aware = datetime(2026, 1, 1, tzinfo=UTC)
    assert validate_timezone_aware_datetime(aware) == aware
    assert validate_sha256_hex("a" * 64) == "a" * 64


@pytest.mark.parametrize(
    "value",
    [Decimal("0"), Decimal("0.000001"), Decimal("999999999999.999999")],
)
def test_decimal_helper_accepts_exact_numeric_18_6_values(value: Decimal) -> None:
    assert validate_non_negative_finite_decimal(value) == value


@pytest.mark.parametrize(
    "value",
    [Decimal("0.0000001"), Decimal("1000000000000"), Decimal("9999999999999999999")],
)
def test_decimal_helper_rejects_values_not_representable_as_numeric_18_6(
    value: Decimal,
) -> None:
    with pytest.raises(ValueError, match=r"NUMERIC\(18,6\)"):
        validate_non_negative_finite_decimal(value)


@pytest.mark.parametrize("value", [True, 1.0, float("nan"), float("inf"), Decimal("-1")])
def test_decimal_helper_rejects_non_contract_values(value: object) -> None:
    with pytest.raises(ValueError):
        validate_non_negative_finite_decimal(value)


@pytest.mark.parametrize(
    ("revision_number", "predecessor"),
    [(1, None), (2, "rev-1")],
)
def test_revision_shape_accepts_only_local_valid_forms(
    revision_number: int,
    predecessor: str | None,
) -> None:
    validate_revision_local_shape(
        revision_number=revision_number,
        external_revision_id="rev-2" if revision_number > 1 else "rev-1",
        supersedes_external_revision_id=predecessor,
    )


@pytest.mark.parametrize(
    ("revision_number", "predecessor"),
    [(1, "rev-0"), (2, None), (2, "rev-2")],
)
def test_revision_shape_rejects_invalid_local_forms(
    revision_number: int,
    predecessor: str | None,
) -> None:
    with pytest.raises(ValueError):
        validate_revision_local_shape(
            revision_number=revision_number,
            external_revision_id="rev-2",
            supersedes_external_revision_id=predecessor,
        )


def test_source_time_truth_table() -> None:
    aware = datetime(2026, 1, 1, tzinfo=UTC)
    validate_source_recorded_at_authority_shape(
        status=SourceRecordedAtAuthorityStatus.TRUSTED_SOURCE_TIMESTAMP,
        source_recorded_at=aware,
        authority_reference="source-row-1",
    )
    validate_source_recorded_at_authority_shape(
        status=SourceRecordedAtAuthorityStatus.USER_ASSERTED_UNVERIFIED,
        source_recorded_at=aware,
        authority_reference=None,
    )
    validate_source_recorded_at_authority_shape(
        status=SourceRecordedAtAuthorityStatus.MISSING,
        source_recorded_at=None,
        authority_reference=None,
    )
    validate_source_recorded_at_authority_shape(
        status=SourceRecordedAtAuthorityStatus.CONFLICTING,
        source_recorded_at=None,
        authority_reference="conflict-1",
    )
    assert has_trusted_source_timestamp(
        type(
            "Record",
            (),
            {
                "source_recorded_at": aware,
                "source_recorded_at_authority_status": (
                    SourceRecordedAtAuthorityStatus.TRUSTED_SOURCE_TIMESTAMP
                ),
            },
        )()
    )
    assert has_trusted_source_timestamp(
        type(
            "NaiveRecord",
            (),
            {
                "source_recorded_at": datetime(2026, 1, 1),
                "source_recorded_at_authority_status": (
                    SourceRecordedAtAuthorityStatus.TRUSTED_SOURCE_TIMESTAMP
                ),
            },
        )()
    )


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


def test_validation_error_code_set_and_public_exports_are_exact() -> None:
    expected_error_codes = {
        "CSV_ENCODING_INVALID",
        "CSV_STRUCTURE_INVALID",
        "CSV_LIMIT_EXCEEDED",
        "CSV_EMPTY_ROW_IGNORED",
        "CANONICAL_HEADER_DUPLICATE",
        "CANONICAL_HEADER_COLLISION",
        "XLSX_CANONICAL_SHEET_MISSING",
        "XLSX_CANONICAL_SHEET_DUPLICATE",
        "XLSX_EXTRA_SHEET_FORBIDDEN",
        "XLSX_FORMULA_CELL_FORBIDDEN",
        "XLSX_MERGED_CELL_FORBIDDEN",
        "XLSX_HIDDEN_ROW_FORBIDDEN",
        "XLSX_HIDDEN_COLUMN_FORBIDDEN",
        "XLSX_EXECUTABLE_CONTENT_FORBIDDEN",
        "XLSX_EXTERNAL_LINK_FORBIDDEN",
        "XLSX_ARCHIVE_INVALID",
        "XLSX_LIMIT_EXCEEDED",
        "SERVER_GENERATED_FIELD_SUPPLIED",
        "TEMPLATE_POLICY_INCOMPATIBLE",
        "REQUIRED_FIELD_MISSING",
        "UNKNOWN_FIELD",
        "INVALID_DATE",
        "INVALID_DATETIME",
        "INVALID_TIMEZONE",
        "INVALID_DECIMAL",
        "NEGATIVE_QUANTITY",
        "IDENTITY_MAPPING_NOT_FOUND",
        "IDENTITY_MAPPING_AMBIGUOUS",
        "DUPLICATE_RECORD",
        "IDEMPOTENCY_KEY_CONFLICT",
        "REVISION_NUMBER_CONFLICT",
        "REVISION_IDENTITY_CONFLICT",
        "REVISION_PREDECESSOR_MISSING",
        "REVISION_MULTIPLE_SUCCESSORS",
        "REVISION_LINEAGE_CYCLE",
        "REVISION_LOGICAL_RECORD_MISMATCH",
        "MULTIPLE_TERMINAL_REVISIONS",
        "INVALID_RECORD_STATUS",
        "SOURCE_SEMANTICS_ATTESTATION_MISSING",
        "SOURCE_SEMANTICS_NOT_FARM_PICK",
        "BATCH_NOT_VALIDATED",
        "BATCH_ALREADY_COMMITTED",
        "CANONICAL_HASH_MISMATCH",
        "BATCH_NOT_SEALED",
        "BATCH_ALREADY_SEALED",
        "BATCH_SEAL_HASH_CONFLICT",
        "BATCH_RECORD_COUNT_MISMATCH",
        "BATCH_MUTATION_AFTER_SEAL",
        "BATCH_SEAL_CHANGED",
        "IDENTITY_MAPPING_POLICY_VERSION_MISSING",
        "IDENTITY_MAPPING_REGISTRY_NOT_SEALED",
        "IDENTITY_MAPPING_REGISTRY_HASH_CHANGED",
        "IDENTITY_MAPPING_TARGET_TYPE_UNSUPPORTED",
        "SEASON_RESOLUTION_NOT_FOUND",
        "SEASON_RESOLUTION_AMBIGUOUS",
        "SEASON_BUSINESS_DATE_MISMATCH",
        "VALIDATION_IN_PROGRESS",
        "VALIDATION_EVIDENCE_STALE",
        "COMMITTED_LINEAGE_BASIS_CHANGED",
    }
    assert {item.name for item in ActualHarvestValidationErrorCode} == expected_error_codes
    assert {item.value for item in ActualHarvestValidationErrorCode} == expected_error_codes
    assert "DELETED" not in ActualHarvestRecordStatus.__members__
    assert "SUPERSEDED" not in ActualHarvestRecordStatus.__members__
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
