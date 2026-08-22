"""V0.3-S2 Lane A semantic identity schemas and errors."""

from __future__ import annotations

import re
import unicodedata
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

_UNRESOLVED_SENTINELS = frozenset({"NOT_PROVIDED", "NOT_ISSUED", "PENDING"})
_LANE_A_URL_PATH_RE = re.compile(
    r"(?:https?://|ftp://|//|\\\\|[a-zA-Z]:[\\/]|docs\.google\.com|drive\.google)",
    re.IGNORECASE,
)
_LANE_A_VERSION_REFERENCE_PATTERN = re.compile(
    r"^[a-z0-9](?:[a-z0-9._:-]{0,126}[a-z0-9])?$"
)


def validate_lane_a_governed_business_identity(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    text = unicodedata.normalize("NFC", value).strip()
    if not text or len(text) > 256:
        raise ValueError(f"{field_name} must be a non-empty governed business identity")
    if text.upper() in _UNRESOLVED_SENTINELS:
        raise ValueError(f"{field_name} must not use an unresolved status sentinel")
    if _LANE_A_URL_PATH_RE.search(text):
        raise ValueError(f"{field_name} must not contain a URL or path")
    return text


def validate_lane_a_governed_version_reference(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    text = value.strip()
    if not text or len(text) > 128:
        raise ValueError(f"{field_name} must be a non-empty version reference")
    if text.upper() in _UNRESOLVED_SENTINELS:
        raise ValueError(f"{field_name} must not use an unresolved status sentinel")
    if _LANE_A_URL_PATH_RE.search(text):
        raise ValueError(f"{field_name} must not contain a URL or path")
    if _LANE_A_VERSION_REFERENCE_PATTERN.fullmatch(text) is None:
        raise ValueError(f"{field_name} must be a governed version reference")
    return text


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


class Source002IdentityVerificationError(LaneALineageError):
    """SOURCE_002 frozen object identity verification failed."""


class Source002ControlledIngestBlocked(Source002IdentityVerificationError):
    """Controlled ingest is blocked because E1 identity verification did not pass."""


class Source002ParseError(LaneALineageError):
    """SOURCE_002 workbook parsing failed."""


SOURCE_002_SOURCE_SYSTEM = "扫码称重系统"
SOURCE_002_SOURCE_DATASET = "田间商品果每日采摘净重汇总"
SOURCE_002_SOURCE_VERSION = "scan-weight-export:v0_3_s1:002"
SOURCE_002_SNAPSHOT_REFERENCE = "snapshot:v0_3_s1:002"
SOURCE_002_OBJECT_SHA256 = "fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a"
SOURCE_002_BYTE_COUNT = 28668416
SOURCE_002_DECLARED_ROW_COUNT = 233171
SOURCE_002_SCHEMA_VERSION = "observed-source-schema-v1"
SOURCE_002_OBSERVED_SCHEMA_SHA256 = (
    "919e63c4d3b4d00b304a045f63bfb050d4eb9abec3b0a318186b7ca2e7276867"
)
SOURCE_002_COHORT_ID = "source-002-s1-cohort-v1"
SOURCE_002_COHORT_MANIFEST_SHA256 = (
    "27ddb9a77d9ce7d4b0579d0648c23b5ade7d6a090626b695e5b41827e714fcca"
)
SOURCE_002_EXPECTED_HEADERS: tuple[str, ...] = (
    "时间",
    "链路",
    "农场",
    "分场",
    "品种",
    "果径",
    "入库公斤数",
)
SOURCE_002_EXPECTED_FIELD_COUNT = len(SOURCE_002_EXPECTED_HEADERS)
SOURCE_002_ACTUAL_HEADER_SCHEMA = ",".join(SOURCE_002_EXPECTED_HEADERS)
SOURCE_002_FORBIDDEN_BASENAMES: frozenset[str] = frozenset(
    {"2024_2025_receipts.xls", "2025_2026_receipts.xls"}
)
SOURCE_002_MAPPING_POLICY_VERSION = "source-002-mapping-policy-v1"
SOURCE_002_MAPPING_SNAPSHOT_HASH = (
    "6f07bc878935060f57a2ef24318d6d3b17e27c7f096885f813ac80bed6ac9d10"
)
SOURCE_002_STORAGE_LOCATOR_HASH = (
    "df39369fde69dd0f573952dcc84f8c0f8c3376541c7447e104bb7869400afb5a"
)
SOURCE_002_FORBIDDEN_STORAGE_LOCATOR_HASH = (
    "b8808e32eec032060894b9839dae7969bccad50ba4bf0c399fe19c5b16958eb9"
)
SOURCE_002_IMPORT_POLICY_VERSION = "v0-3-s2-source-002-controlled-import-policy-v1"
SOURCE_002_VALIDATION_POLICY_VERSION = "v0-3-s2-source-002-controlled-validation-policy-v1"
SOURCE_002_OWNER_ATTESTATION = "source-002-final-source-owner-attestation-v1"
SOURCE_002_CUSTODY_RECORD = "source-002-custody-record-v1"
SOURCE_002_OBJECT_IDENTITY = "snapshot:v0_3_s1:002"
SOURCE_002_IDFL_REVISION_ID = "source-002-idfl-immutable-final-revision-v1"
SOURCE_002_CONTROLLED_IMPORT_REQUEST_IDENTITY = "source-002-controlled-materialization-import-v1"
SOURCE_002_CONTROLLED_EXTERNAL_BATCH_ID = "source-002-controlled-materialization-batch-v1"
SOURCE_002_ROW_EVIDENCE_IDENTITY_POLICY_VERSION = "v0-3-s2-source-002-row-evidence-identity-v1"
SOURCE_002_FROZEN_OBJECT_PATH_ENV = "SOURCE_002_FROZEN_OBJECT_PATH"


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

    @field_validator("source_system", "source_dataset")
    @classmethod
    def _validate_business_identities(cls, value: object, info: object) -> str:
        field_name = getattr(info, "field_name", "identifier")
        return validate_lane_a_governed_business_identity(value, field_name=field_name)

    @field_validator(
        "source_version",
        "source_snapshot_reference",
        "source_object_identity",
        "schema_version",
    )
    @classmethod
    def _validate_version_references(cls, value: object, info: object) -> str:
        field_name = getattr(info, "field_name", "version_reference")
        return validate_lane_a_governed_version_reference(value, field_name=field_name)

    @field_validator(
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

    @field_validator("source_system", "source_dataset")
    @classmethod
    def _validate_business_identities(cls, value: object, info: object) -> str:
        field_name = getattr(info, "field_name", "identifier")
        return validate_lane_a_governed_business_identity(value, field_name=field_name)

    @field_validator("external_batch_id", "source_cohort_id")
    @classmethod
    def _validate_identifiers(cls, value: object, info: object) -> str:
        field_name = getattr(info, "field_name", "identifier")
        return validate_batch_a_identifier(value, field_name=field_name)

    @field_validator("import_request_identity")
    @classmethod
    def _validate_import_request_identity(cls, value: object) -> str:
        return validate_batch_a_identifier(value, field_name="import_request_identity")

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, value: object) -> str:
        return validate_lane_a_governed_version_reference(value, field_name="schema_version")

    @field_validator(
        "import_policy_version",
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

    @field_validator("external_logical_record_id", "external_revision_id")
    @classmethod
    def _validate_identifiers(cls, value: object, info: object) -> str:
        field_name = getattr(info, "field_name", "identifier")
        return validate_batch_a_identifier(value, field_name=field_name)

    @field_validator("source_system")
    @classmethod
    def _validate_source_system(cls, value: object) -> str:
        return validate_lane_a_governed_business_identity(value, field_name="source_system")

    @field_validator("source_version", "schema_version")
    @classmethod
    def _validate_versions(cls, value: object, info: object) -> str:
        field_name = getattr(info, "field_name", "version")
        return validate_lane_a_governed_version_reference(value, field_name=field_name)

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


class Source002IdentityVerificationStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"


class Source002IdentityFailureCode(StrEnum):
    OBJECT_NOT_FOUND = "OBJECT_NOT_FOUND"
    FORBIDDEN_OBJECT = "FORBIDDEN_OBJECT"
    BYTE_COUNT_MISMATCH = "BYTE_COUNT_MISMATCH"
    OBJECT_SHA256_MISMATCH = "OBJECT_SHA256_MISMATCH"
    ROW_COUNT_MISMATCH = "ROW_COUNT_MISMATCH"
    HEADER_MISMATCH = "HEADER_MISMATCH"
    OBSERVED_SCHEMA_SHA256_MISMATCH = "OBSERVED_SCHEMA_SHA256_MISMATCH"
    COHORT_MANIFEST_SHA256_MISMATCH = "COHORT_MANIFEST_SHA256_MISMATCH"
    METADATA_MISMATCH = "METADATA_MISMATCH"


class Source002IdentityVerificationRecord(_LaneABaseModel):
    status: Source002IdentityVerificationStatus
    failure_code: Source002IdentityFailureCode | None = None
    source_system: str = SOURCE_002_SOURCE_SYSTEM
    source_dataset: str = SOURCE_002_SOURCE_DATASET
    source_version: str = SOURCE_002_SOURCE_VERSION
    source_snapshot_reference: str = SOURCE_002_SNAPSHOT_REFERENCE
    source_object_sha256: str | None = None
    byte_count: int | None = None
    declared_source_row_count: int | None = None
    observed_schema_version: str = SOURCE_002_SCHEMA_VERSION
    observed_schema_sha256: str | None = None
    source_cohort_id: str = SOURCE_002_COHORT_ID
    source_cohort_manifest_sha256: str = SOURCE_002_COHORT_MANIFEST_SHA256
    object_present: bool = False
    ingest_authorized: bool = False


class Source002ControlledIngestResult(_LaneABaseModel):
    verification: Source002IdentityVerificationRecord
    artifact_registration: SourceArtifactRegistration
    batch_registration: ImportBatchRegistration
    source_row_count: int
    first_seen_row_count: int
    replay_row_count: int
