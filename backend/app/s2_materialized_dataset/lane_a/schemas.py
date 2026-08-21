"""V0.3-S2 Lane A semantic identity schemas and errors."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.actual_harvest_import.batch_a_contracts import (
    validate_batch_a_identifier,
    validate_policy_identity,
    validate_sha256,
)

SHA256Hex = Annotated[
    str,
    Field(strict=True, min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"),
]
NonEmptyString = Annotated[str, Field(strict=True, min_length=1)]


class LaneALineageError(ValueError):
    """Base error for deterministic Lane A lineage rejection."""


class SourceArtifactIntegrityConflict(LaneALineageError):
    """Duplicate source artifact identity with different immutable bytes."""


class ImportBatchIdempotencyConflict(LaneALineageError):
    """Same external batch identity with different payload or policy versions."""


class SourceRowRevisionConflict(LaneALineageError):
    """Same source row identity with different canonical content."""


class MissingExternalLogicalRecordIdError(LaneALineageError):
    """Ingestion cannot synthesize a logical record identity from row position."""


class LaneALineageNotFoundError(LaneALineageError):
    """A requested lineage reference does not exist."""


class SourceArtifactRegistrationResult(StrEnum):
    FIRST_SEEN = "FIRST_SEEN"
    EXACT_REPLAY = "EXACT_REPLAY"


class ImportBatchRegistrationResult(StrEnum):
    FIRST_SEEN = "FIRST_SEEN"
    EXACT_REPLAY = "EXACT_REPLAY"


class SourceRowRegistrationResult(StrEnum):
    FIRST_SEEN = "FIRST_SEEN"
    EXACT_REPLAY = "EXACT_REPLAY"
    CONTENT_CONFLICT_CANDIDATE = "CONTENT_CONFLICT_CANDIDATE"


class _LaneABaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class RawSourceArtifactIdentityInput(_LaneABaseModel):
    source_system: NonEmptyString
    source_dataset: NonEmptyString
    source_version: NonEmptyString
    source_snapshot_reference: NonEmptyString
    source_object_identity: NonEmptyString
    source_artifact_sequence: Annotated[int, Field(strict=True, ge=1)]
    schema_version: NonEmptyString
    mapping_policy_version: NonEmptyString
    source_artifact_identity_version: NonEmptyString
    source_owner_attestation: NonEmptyString
    cohort_manifest_reference: NonEmptyString
    custody_record_reference: NonEmptyString
    storage_locator_hash: SHA256Hex

    @field_validator(
        "source_system",
        "source_dataset",
        "source_version",
        "source_snapshot_reference",
        "source_object_identity",
        "schema_version",
        "source_owner_attestation",
        "cohort_manifest_reference",
        "custody_record_reference",
    )
    @classmethod
    def _validate_identifiers(cls, value: object, info: object) -> str:
        field_name = getattr(info, "field_name", "identifier")
        return validate_batch_a_identifier(value, field_name=field_name)

    @field_validator("mapping_policy_version", "source_artifact_identity_version")
    @classmethod
    def _validate_policy_versions(cls, value: object, info: object) -> str:
        field_name = getattr(info, "field_name", "policy_version")
        return validate_policy_identity(value, field_name=field_name)

    @field_validator("storage_locator_hash")
    @classmethod
    def _validate_storage_locator_hash(cls, value: object) -> str:
        return validate_sha256(value, field_name="storage_locator_hash")


class RawSourceArtifactIdentity(_LaneABaseModel):
    source_artifact_identity_hash: SHA256Hex
    source_artifact_sha256: SHA256Hex
    source_system: NonEmptyString
    source_dataset: NonEmptyString
    source_version: NonEmptyString
    source_snapshot_reference: NonEmptyString
    source_object_identity: NonEmptyString
    source_artifact_sequence: Annotated[int, Field(strict=True, ge=1)]
    schema_version: NonEmptyString
    mapping_policy_version: NonEmptyString
    source_artifact_identity_version: NonEmptyString
    source_owner_attestation: NonEmptyString
    cohort_manifest_reference: NonEmptyString
    custody_record_reference: NonEmptyString
    storage_locator_hash: SHA256Hex


class RawImportBatchIdentityInput(_LaneABaseModel):
    external_batch_id: NonEmptyString
    source_system: NonEmptyString
    source_dataset: NonEmptyString
    raw_payload_hash: SHA256Hex
    import_policy_version: NonEmptyString
    schema_version: NonEmptyString
    mapping_policy_version: NonEmptyString
    validation_policy_version: NonEmptyString
    source_cohort_id: NonEmptyString
    import_request_identity: NonEmptyString

    @field_validator("external_batch_id", "source_system", "source_dataset", "source_cohort_id")
    @classmethod
    def _validate_identifiers(cls, value: object, info: object) -> str:
        field_name = getattr(info, "field_name", "identifier")
        return validate_batch_a_identifier(value, field_name=field_name)

    @field_validator("import_request_identity")
    @classmethod
    def _validate_import_request_identity(cls, value: object) -> str:
        return validate_batch_a_identifier(value, field_name="import_request_identity")

    @field_validator(
        "import_policy_version",
        "schema_version",
        "mapping_policy_version",
        "validation_policy_version",
    )
    @classmethod
    def _validate_policy_versions(cls, value: object, info: object) -> str:
        field_name = getattr(info, "field_name", "policy_version")
        return validate_policy_identity(value, field_name=field_name)

    @field_validator("raw_payload_hash")
    @classmethod
    def _validate_raw_payload_hash(cls, value: object) -> str:
        return validate_sha256(value, field_name="raw_payload_hash")


class RawImportBatchIdentity(_LaneABaseModel):
    raw_import_batch_identity_hash: SHA256Hex
    content_sha256: SHA256Hex
    raw_source_artifact_identity_hash: SHA256Hex
    external_batch_id: NonEmptyString
    source_system: NonEmptyString
    source_dataset: NonEmptyString
    raw_payload_hash: SHA256Hex
    import_policy_version: NonEmptyString
    schema_version: NonEmptyString
    mapping_policy_version: NonEmptyString
    validation_policy_version: NonEmptyString
    source_cohort_id: NonEmptyString
    import_request_identity: NonEmptyString
    source_row_identity_hashes: tuple[SHA256Hex, ...]


class SourceRowBusinessContent(_LaneABaseModel):
    harvest_business_date: date
    farm_code: NonEmptyString
    subfarm_or_plot_code: NonEmptyString
    variety_code: NonEmptyString
    actual_harvest_quantity_kg: Decimal

    @field_validator("actual_harvest_quantity_kg")
    @classmethod
    def _validate_quantity(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("actual_harvest_quantity_kg must be finite")
        return value


class SourceRowLineageInput(_LaneABaseModel):
    external_logical_record_id: NonEmptyString
    external_revision_id: NonEmptyString
    revision_number: Annotated[int, Field(strict=True, ge=1)]
    source_system: NonEmptyString
    source_version: NonEmptyString
    schema_version: NonEmptyString
    source_row_identity_version: NonEmptyString
    source_sheet_name: NonEmptyString | None = None
    source_row_number: Annotated[int, Field(strict=True, ge=1)] | None = None
    source_column_mapping_snapshot_hash: SHA256Hex
    business_content: SourceRowBusinessContent

    @field_validator("external_logical_record_id", "external_revision_id", "source_system")
    @classmethod
    def _validate_identifiers(cls, value: object, info: object) -> str:
        field_name = getattr(info, "field_name", "identifier")
        return validate_batch_a_identifier(value, field_name=field_name)

    @field_validator("source_version", "schema_version")
    @classmethod
    def _validate_versions(cls, value: object, info: object) -> str:
        field_name = getattr(info, "field_name", "version")
        return validate_batch_a_identifier(value, field_name=field_name)

    @field_validator("source_row_identity_version")
    @classmethod
    def _validate_row_identity_version(cls, value: object) -> str:
        return validate_policy_identity(value, field_name="source_row_identity_version")

    @field_validator("source_column_mapping_snapshot_hash")
    @classmethod
    def _validate_mapping_snapshot_hash(cls, value: object) -> str:
        return validate_sha256(value, field_name="source_column_mapping_snapshot_hash")


class SourceRowIdentity(_LaneABaseModel):
    source_row_identity_hash: SHA256Hex
    content_sha256: SHA256Hex
    raw_source_artifact_identity_hash: SHA256Hex
    raw_import_batch_identity_hash: SHA256Hex
    external_logical_record_id: NonEmptyString
    external_revision_id: NonEmptyString
    revision_number: Annotated[int, Field(strict=True, ge=1)]
    source_system: NonEmptyString
    source_version: NonEmptyString
    schema_version: NonEmptyString
    source_row_identity_version: NonEmptyString
    source_sheet_name: NonEmptyString | None = None
    source_row_number: Annotated[int, Field(strict=True, ge=1)] | None = None
    source_column_mapping_snapshot_hash: SHA256Hex
    winner_selection_blocked: bool = False


class SourceArtifactRegistration(_LaneABaseModel):
    result: SourceArtifactRegistrationResult
    identity: RawSourceArtifactIdentity


class ImportBatchRegistration(_LaneABaseModel):
    result: ImportBatchRegistrationResult
    identity: RawImportBatchIdentity


class SourceRowRegistration(_LaneABaseModel):
    result: SourceRowRegistrationResult
    identity: SourceRowIdentity


class SourceRowLineageChain(_LaneABaseModel):
    source_artifact: RawSourceArtifactIdentity
    import_batch: RawImportBatchIdentity
    source_row: SourceRowIdentity


class SourceArtifactRegistrationRecord(_LaneABaseModel):
    identity: RawSourceArtifactIdentity
    registered_at: datetime


class ImportBatchRegistrationRecord(_LaneABaseModel):
    identity: RawImportBatchIdentity
    registered_at: datetime


class SourceRowRegistrationRecord(_LaneABaseModel):
    identity: SourceRowIdentity
    registered_at: datetime
