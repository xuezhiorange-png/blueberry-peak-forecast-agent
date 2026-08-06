from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, datetime
from decimal import Decimal
from math import isfinite
from typing import Annotated, NoReturn

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.actual_harvest_import.batch_a_contracts import (
    BatchASourceIdentity,
    validate_batch_a_identifier,
)
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
    validate_non_negative_finite_decimal,
    validate_revision_local_shape,
    validate_source_recorded_at_authority_shape,
    validate_timezone_aware_datetime,
)

type JsonScalar = None | bool | int | float | str
type JsonValue = JsonScalar | tuple[JsonValue, ...] | Mapping[str, JsonValue]

NonEmptyString = Annotated[str, Field(strict=True, min_length=1)]
SHA256Hex = Annotated[
    str,
    Field(strict=True, min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"),
]
PositiveStrictInt = Annotated[int, Field(strict=True, ge=1)]
NonNegativeStrictInt = Annotated[int, Field(strict=True, ge=0)]
ImportId = NonEmptyString


class _BaseContractModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )


class _FrozenDict(dict[str, object]):
    __slots__ = ("_initialized",)

    def __init__(self, value: Mapping[str, object] | None = None) -> None:
        if getattr(self, "_initialized", False):
            raise TypeError("frozen mapping cannot be reinitialized")
        dict.__init__(self)
        for key, child in (value or {}).items():
            if not isinstance(key, str):
                raise TypeError("frozen mapping keys must be strings")
            dict.__setitem__(self, key, _freeze_json_value(child))
        object.__setattr__(self, "_initialized", True)

    def _reject_mutation(self, *args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        raise TypeError("frozen mapping is immutable")

    __setitem__ = _reject_mutation
    __delitem__ = _reject_mutation
    clear = _reject_mutation
    pop = _reject_mutation
    setdefault = _reject_mutation
    update = _reject_mutation

    def popitem(self) -> tuple[str, object]:
        return self._reject_mutation()

    def __ior__(self, value: Mapping[str, object]) -> _FrozenDict:  # type: ignore[override, misc]
        return self._reject_mutation(value)


def _freeze_json_value(value: object) -> object:
    if isinstance(value, Mapping):
        return _FrozenDict(value)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json_value(child) for child in value)
    return value


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
    external_logical_record_id: NonEmptyString = Field(
        json_schema_extra={"spreadsheet_importable": True, "spreadsheet_order": 10}
    )
    external_revision_id: NonEmptyString = Field(
        json_schema_extra={"spreadsheet_importable": True, "spreadsheet_order": 20}
    )
    source_system: NonEmptyString = Field(
        json_schema_extra={"spreadsheet_importable": True, "spreadsheet_order": 30}
    )
    external_batch_id: NonEmptyString = Field(
        json_schema_extra={"spreadsheet_importable": True, "spreadsheet_order": 40}
    )
    harvest_business_date: date = Field(
        json_schema_extra={"spreadsheet_importable": True, "spreadsheet_order": 50}
    )
    farm_code: NonEmptyString = Field(
        json_schema_extra={"spreadsheet_importable": True, "spreadsheet_order": 60}
    )
    subfarm_or_plot_code: NonEmptyString = Field(
        json_schema_extra={"spreadsheet_importable": True, "spreadsheet_order": 70}
    )
    variety_code: NonEmptyString = Field(
        json_schema_extra={"spreadsheet_importable": True, "spreadsheet_order": 80}
    )
    actual_harvest_quantity_kg: Decimal = Field(
        json_schema_extra={"spreadsheet_importable": True, "spreadsheet_order": 90}
    )
    source_recorded_at: datetime | None = Field(
        default=None,
        json_schema_extra={"spreadsheet_importable": True, "spreadsheet_order": 100},
    )
    source_recorded_at_authority_status: SourceRecordedAtAuthorityStatus = Field(
        json_schema_extra={"spreadsheet_importable": True, "spreadsheet_order": 110}
    )
    source_recorded_at_authority_reference_or_null: NonEmptyString | None = Field(
        default=None,
        json_schema_extra={"spreadsheet_importable": True, "spreadsheet_order": 120},
    )
    revision_number: PositiveStrictInt = Field(
        json_schema_extra={"spreadsheet_importable": True, "spreadsheet_order": 130}
    )
    record_status: ActualHarvestRecordStatus = Field(
        json_schema_extra={"spreadsheet_importable": True, "spreadsheet_order": 140}
    )
    supersedes_external_revision_id: NonEmptyString | None = Field(
        default=None,
        json_schema_extra={"spreadsheet_importable": True, "spreadsheet_order": 150},
    )
    season_code: NonEmptyString | None = Field(
        default=None,
        json_schema_extra={"spreadsheet_importable": True, "spreadsheet_order": 160},
    )
    farm_timezone: NonEmptyString | None = Field(
        default=None,
        json_schema_extra={"spreadsheet_importable": True, "spreadsheet_order": 170},
    )
    revised_at: datetime | None = Field(
        default=None,
        json_schema_extra={"spreadsheet_importable": True, "spreadsheet_order": 180},
    )
    finalized_at: datetime | None = Field(
        default=None,
        json_schema_extra={"spreadsheet_importable": True, "spreadsheet_order": 190},
    )
    source_note: NonEmptyString | None = Field(
        default=None,
        json_schema_extra={"spreadsheet_importable": True, "spreadsheet_order": 200},
    )
    source_row_number: PositiveStrictInt | None = Field(
        default=None, json_schema_extra={"spreadsheet_importable": False}
    )
    source_sheet_name: NonEmptyString | None = Field(
        default=None, json_schema_extra={"spreadsheet_importable": False}
    )

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

    @field_validator("source_system", mode="before")
    @classmethod
    def _validate_batch_a_source_system(cls, value: object) -> str:
        return validate_batch_a_identifier(value, field_name="source_system")

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
    expected_record_count_or_null: NonNegativeStrictInt | None = None
    source_file_name_or_null: NonEmptyString | None = None
    source_file_hash_or_null: SHA256Hex | None = None
    raw_payload_hash: SHA256Hex
    schema_version: NonEmptyString
    mapping_policy_version: NonEmptyString
    validation_policy_version: NonEmptyString
    source_semantics_attestation: ActualHarvestSourceSemanticsAttestation
    source_semantics_attestation_hash: SHA256Hex

    @field_validator(
        "source_system",
        "source_dataset",
        "source_version",
        "schema_version",
        mode="before",
    )
    @classmethod
    def _validate_batch_a_source_identity_fields(cls, value: object, info: object) -> str:
        field_name = getattr(info, "field_name", "source_identity")
        return validate_batch_a_identifier(value, field_name=field_name)

    @field_validator("submitted_at")
    @classmethod
    def _validate_submitted_at(cls, value: datetime) -> datetime:
        return validate_timezone_aware_datetime(value, field_name="submitted_at")

    @model_validator(mode="after")
    def _validate_batch_a_source_identity(self) -> ActualHarvestImportBatchInput:
        BatchASourceIdentity(
            source_system=self.source_system,
            source_dataset=self.source_dataset,
            source_version=self.source_version,
            schema_version=self.schema_version,
        )
        return self


class CanonicalActualHarvestImportBatch(_BaseContractModel):
    import_id: ImportId
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
        "source_system",
        "source_dataset",
        "source_version",
        "schema_version",
        mode="before",
    )
    @classmethod
    def _validate_batch_a_source_identity_fields(cls, value: object, info: object) -> str:
        field_name = getattr(info, "field_name", "source_identity")
        return validate_batch_a_identifier(value, field_name=field_name)

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
    def _validate_batch_a_source_identity(self) -> CanonicalActualHarvestImportBatch:
        BatchASourceIdentity(
            source_system=self.source_system,
            source_dataset=self.source_dataset,
            source_version=self.source_version,
            schema_version=self.schema_version,
        )
        return self

    @model_validator(mode="after")
    def _validate_seal_shape(self) -> CanonicalActualHarvestImportBatch:
        sealed_values = (
            self.sealed_record_count_or_null,
            self.sealed_at_or_null,
            self.sealed_by_identity_or_null,
            self.server_raw_payload_hash_or_null,
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
    import_id: ImportId
    record_index_or_null: NonNegativeStrictInt | None
    external_logical_record_id_or_null: NonEmptyString | None
    external_revision_id_or_null: NonEmptyString | None
    field_path_or_null: NonEmptyString | None
    message_template_id: NonEmptyString
    details: Mapping[str, JsonValue]

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
            if isinstance(node, Mapping):
                for key, child in node.items():
                    if isinstance(key, str) and any(
                        fragment in key.lower() for fragment in forbidden_key_fragments
                    ):
                        raise ValueError("validation issue details contain sensitive or raw data")
                    walk(child)
            elif isinstance(node, (list, tuple)):
                for child in node:
                    walk(child)
            elif isinstance(node, float) and not isfinite(node):
                raise ValueError("validation issue details must contain finite JSON values")
            elif isinstance(node, str) and node.startswith(("http://", "https://")):
                raise ValueError("validation issue details must not contain private URLs")

        walk(value)
        return value

    @field_validator("details", mode="after")
    @classmethod
    def _freeze_details(cls, value: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
        return _FrozenDict(value)  # type: ignore[return-value]


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
