from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from math import isfinite
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
    validate_iana_timezone,
    validate_json_pointer,
    validate_non_negative_finite_decimal,
    validate_revision_local_shape,
    validate_source_recorded_at_authority_shape,
    validate_timezone_aware_datetime,
)

type JsonScalar = None | bool | int | float | str
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]

NonEmptyString = Annotated[str, Field(strict=True, min_length=1)]
SHA256Hex = Annotated[
    str,
    Field(strict=True, min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"),
]
PositiveStrictInt = Annotated[int, Field(strict=True, ge=1)]
NonNegativeStrictInt = Annotated[int, Field(strict=True, ge=0)]


class _BaseContractModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )


def _reject_datetime_for_date(value: object) -> object:
    if isinstance(value, datetime):
        raise ValueError("a datetime is not a harvest business date")
    return value


class ActualHarvestSourceSemanticsAttestation(_BaseContractModel):
    attestation_version: NonEmptyString
    physical_event: ActualHarvestPhysicalEvent
    quantity_basis: ActualHarvestQuantityBasis
    quantity_unit: ActualHarvestQuantityUnit
    missing_record_semantics: ActualHarvestMissingRecordSemantics


class ActualHarvestImportRecordInput(_BaseContractModel):
    external_logical_record_id: NonEmptyString
    external_revision_id: NonEmptyString
    source_system: NonEmptyString
    external_batch_id: NonEmptyString
    harvest_business_date: date
    farm_code: NonEmptyString
    subfarm_or_plot_code: NonEmptyString
    variety_code: NonEmptyString
    actual_harvest_quantity_kg: Decimal
    source_recorded_at: datetime | None
    source_recorded_at_authority_status: SourceRecordedAtAuthorityStatus
    source_recorded_at_authority_reference_or_null: NonEmptyString | None
    revision_number: PositiveStrictInt
    record_status: ActualHarvestRecordStatus
    supersedes_external_revision_id: NonEmptyString | None
    season_code: NonEmptyString
    farm_timezone: NonEmptyString | None
    revised_at: datetime | None
    finalized_at: datetime | None
    source_row_number: PositiveStrictInt | None
    source_sheet_name: NonEmptyString | None
    source_note: NonEmptyString | None

    @field_validator("harvest_business_date", mode="before")
    @classmethod
    def _validate_business_date(cls, value: object) -> object:
        return _reject_datetime_for_date(value)

    @field_validator("actual_harvest_quantity_kg", mode="before")
    @classmethod
    def _validate_quantity(cls, value: object) -> Decimal:
        return validate_non_negative_finite_decimal(
            value,
            field_name="actual_harvest_quantity_kg",
        )

    @field_validator("source_recorded_at", "revised_at", "finalized_at")
    @classmethod
    def _validate_aware_datetimes(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return validate_timezone_aware_datetime(value, field_name="datetime")

    @field_validator("farm_timezone")
    @classmethod
    def _validate_farm_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_iana_timezone(value, field_name="farm_timezone")

    @model_validator(mode="after")
    def _validate_local_contract(self) -> ActualHarvestImportRecordInput:
        validate_revision_local_shape(
            revision_number=self.revision_number,
            external_revision_id=self.external_revision_id,
            supersedes_external_revision_id=self.supersedes_external_revision_id,
        )
        validate_source_recorded_at_authority_shape(
            status=self.source_recorded_at_authority_status,
            source_recorded_at=self.source_recorded_at,
            authority_reference=self.source_recorded_at_authority_reference_or_null,
        )
        return self


class CanonicalActualHarvestImportRecord(ActualHarvestImportRecordInput):
    import_received_at: datetime
    ingested_at: datetime

    @field_validator("import_received_at", "ingested_at")
    @classmethod
    def _validate_server_datetimes(cls, value: datetime) -> datetime:
        return validate_timezone_aware_datetime(value, field_name="server timestamp")


class ActualHarvestImportBatchInput(_BaseContractModel):
    import_channel: ActualHarvestImportChannel
    source_system: NonEmptyString
    source_dataset: NonEmptyString
    source_version: NonEmptyString
    external_batch_id: NonEmptyString
    idempotency_key: NonEmptyString
    submitted_at: datetime
    submitted_by_identity: NonEmptyString
    expected_record_count_or_null: NonNegativeStrictInt | None
    source_file_name_or_null: NonEmptyString | None
    source_file_hash_or_null: SHA256Hex | None
    raw_payload_hash: SHA256Hex
    schema_version: NonEmptyString
    mapping_policy_version: NonEmptyString
    validation_policy_version: NonEmptyString
    source_semantics_attestation: ActualHarvestSourceSemanticsAttestation
    source_semantics_attestation_hash: SHA256Hex

    @field_validator("submitted_at")
    @classmethod
    def _validate_submitted_at(cls, value: datetime) -> datetime:
        return validate_timezone_aware_datetime(value, field_name="submitted_at")


class CanonicalActualHarvestImportBatch(_BaseContractModel):
    import_id: PositiveStrictInt
    import_channel: ActualHarvestImportChannel
    source_system: NonEmptyString
    source_dataset: NonEmptyString
    source_version: NonEmptyString
    external_batch_id: NonEmptyString
    idempotency_key: NonEmptyString
    submitted_at: datetime
    import_received_at: datetime
    ingested_at: datetime
    submitted_by_identity: NonEmptyString
    expected_record_count_or_null: NonNegativeStrictInt | None
    uploaded_record_count: NonNegativeStrictInt
    sealed_record_count_or_null: NonNegativeStrictInt | None
    sealed_at_or_null: datetime | None
    sealed_by_identity_or_null: NonEmptyString | None
    seal_status: ActualHarvestBatchSealStatus
    server_raw_payload_hash_or_null: SHA256Hex | None
    canonical_batch_hash_or_null: SHA256Hex | None
    seal_manifest_hash_or_null: SHA256Hex | None
    source_file_name_or_null: NonEmptyString | None
    source_file_hash_or_null: SHA256Hex | None
    raw_payload_hash: SHA256Hex
    schema_version: NonEmptyString
    mapping_policy_version: NonEmptyString
    validation_policy_version: NonEmptyString
    source_semantics_attestation: ActualHarvestSourceSemanticsAttestation
    source_semantics_attestation_hash: SHA256Hex
    status: ActualHarvestImportBatchStatus
    record_count: NonNegativeStrictInt
    valid_record_count: NonNegativeStrictInt
    invalid_record_count: NonNegativeStrictInt
    committed_record_count: NonNegativeStrictInt
    created_at: datetime
    validated_at_or_null: datetime | None
    committed_at_or_null: datetime | None

    @field_validator(
        "submitted_at",
        "import_received_at",
        "ingested_at",
        "sealed_at_or_null",
        "created_at",
        "validated_at_or_null",
        "committed_at_or_null",
    )
    @classmethod
    def _validate_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return validate_timezone_aware_datetime(value, field_name="batch timestamp")

    @model_validator(mode="after")
    def _validate_seal_shape(self) -> CanonicalActualHarvestImportBatch:
        sealed_values = (
            self.sealed_record_count_or_null,
            self.sealed_at_or_null,
            self.sealed_by_identity_or_null,
            self.canonical_batch_hash_or_null,
            self.seal_manifest_hash_or_null,
        )
        if self.seal_status == ActualHarvestBatchSealStatus.SEALED:
            if any(value is None for value in sealed_values):
                raise ValueError("a sealed batch requires complete seal metadata")
        elif any(value is not None for value in sealed_values):
            raise ValueError("an unsealed batch must not carry seal metadata")
        return self


class ActualHarvestValidationIssue(_BaseContractModel):
    error_code: ActualHarvestValidationErrorCode
    severity: ActualHarvestValidationSeverity
    import_id: PositiveStrictInt
    record_index_or_null: NonNegativeStrictInt | None
    external_logical_record_id_or_null: NonEmptyString | None
    external_revision_id_or_null: NonEmptyString | None
    field_path_or_null: NonEmptyString | None
    message_template_id: NonEmptyString
    details: dict[str, JsonValue]

    @field_validator("field_path_or_null")
    @classmethod
    def _validate_field_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_json_pointer(value)

    @field_validator("details", mode="before")
    @classmethod
    def _validate_safe_details(cls, value: object) -> object:
        forbidden_key_fragments = (
            "authorization",
            "cookie",
            "credential",
            "password",
            "private_url",
            "raw_row",
            "secret",
            "stacktrace",
            "token",
            "traceback",
        )

        def walk(node: object) -> None:
            if isinstance(node, dict):
                for key, child in node.items():
                    if isinstance(key, str) and any(
                        fragment in key.lower() for fragment in forbidden_key_fragments
                    ):
                        raise ValueError("validation issue details contain sensitive or raw data")
                    walk(child)
            elif isinstance(node, list):
                for child in node:
                    walk(child)
            elif isinstance(node, float) and not isfinite(node):
                raise ValueError("validation issue details must contain finite JSON values")
            elif isinstance(node, str) and node.startswith(("http://", "https://")):
                raise ValueError("validation issue details must not contain private URLs")

        walk(value)
        return value


def sort_validation_issues(
    issues: Iterable[ActualHarvestValidationIssue],
) -> tuple[ActualHarvestValidationIssue, ...]:
    def sort_key(issue: ActualHarvestValidationIssue) -> tuple[object, ...]:
        return (
            issue.record_index_or_null is not None,
            issue.record_index_or_null if issue.record_index_or_null is not None else -1,
            issue.external_logical_record_id_or_null is not None,
            issue.external_logical_record_id_or_null or "",
            issue.external_revision_id_or_null is not None,
            issue.external_revision_id_or_null or "",
            issue.field_path_or_null is not None,
            issue.field_path_or_null or "",
            issue.error_code.value,
            issue.message_template_id,
        )

    return tuple(sorted(issues, key=sort_key))
