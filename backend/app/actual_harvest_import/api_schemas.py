from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.actual_harvest_import.api_policy import API_POLICY
from backend.app.actual_harvest_import.enums import ActualHarvestImportChannel
from backend.app.actual_harvest_import.schemas import (
    ActualHarvestImportBatchInput,
    ActualHarvestImportRecordInput,
)


class ActualHarvestApiCreateImportRequest(ActualHarvestImportBatchInput):
    """API transport input; server-owned fields are intentionally absent."""

    @model_validator(mode="before")
    @classmethod
    def _reject_file_fields(cls, value: object) -> object:
        if isinstance(value, dict) and (
            "source_file_name_or_null" in value or "source_file_hash_or_null" in value
        ):
            raise ValueError("source file metadata is not accepted for API imports")
        return value

    @model_validator(mode="after")
    def _api_only(self) -> ActualHarvestApiCreateImportRequest:
        if self.import_channel != ActualHarvestImportChannel.API:
            raise ValueError("import_channel must be API")
        return self

    @field_validator(
        "source_system",
        "external_batch_id",
        "idempotency_key",
        "submitted_by_identity",
    )
    @classmethod
    def _bounded_identifiers(cls, value: str) -> str:
        if len(value) > API_POLICY.max_identifier_length:
            raise ValueError("identifier exceeds API policy limit")
        return value

    @field_validator("source_dataset")
    @classmethod
    def _bounded_dataset(cls, value: str) -> str:
        if len(value) > API_POLICY.max_dataset_length:
            raise ValueError("source dataset exceeds API policy limit")
        return value

    @field_validator("source_version")
    @classmethod
    def _bounded_version(cls, value: str) -> str:
        if len(value) > API_POLICY.max_version_length:
            raise ValueError("source version exceeds API policy limit")
        return value

    @field_validator("schema_version", "mapping_policy_version", "validation_policy_version")
    @classmethod
    def _bounded_policy_version(cls, value: str) -> str:
        if len(value) > API_POLICY.max_version_length:
            raise ValueError("policy version exceeds API policy limit")
        return value

    @model_validator(mode="after")
    def _bounded_attestation_version(self) -> ActualHarvestApiCreateImportRequest:
        if (
            len(self.source_semantics_attestation.attestation_version)
            > API_POLICY.max_version_length
        ):
            raise ValueError("attestation version exceeds API policy limit")
        return self


class ActualHarvestApiRecordInput(ActualHarvestImportRecordInput):
    @model_validator(mode="before")
    @classmethod
    def _reject_server_fields(cls, value: object) -> object:
        if isinstance(value, dict) and (
            "import_received_at" in value
            or "ingested_at" in value
            or "source_row_number" in value
            or "source_sheet_name" in value
        ):
            raise ValueError("server-generated API record field supplied")
        return value

    @field_validator(
        "external_logical_record_id",
        "external_revision_id",
        "source_system",
        "external_batch_id",
        "farm_code",
        "subfarm_or_plot_code",
        "variety_code",
        "source_recorded_at_authority_reference_or_null",
        "season_code",
        "farm_timezone",
    )
    @classmethod
    def _bounded_record_identifiers(cls, value: str | None) -> str | None:
        if value is not None and len(value) > API_POLICY.max_identifier_length:
            raise ValueError("record identifier exceeds API policy limit")
        return value

    @field_validator("source_note")
    @classmethod
    def _bounded_source_note(cls, value: str | None) -> str | None:
        if value is not None and len(value) > API_POLICY.max_source_note_length:
            raise ValueError("source note exceeds API policy limit")
        return value


class ActualHarvestApiAppendRecordsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    records: tuple[ActualHarvestApiRecordInput, ...] = Field(
        min_length=1,
        max_length=API_POLICY.max_records_per_append,
    )


class ActualHarvestApiSealRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ActualHarvestApiCancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ActualHarvestApiValidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


_HEX64 = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$", strict=True)


class ActualHarvestApiCommitRequest(BaseModel):
    """v0.2-S1 atomic commit request body.

    The single bound field is the validation_run_instance_identity_hash of
    the current VALIDATED validation run. The server reloads the batch,
    the current validation run, the validation result, and the mapping
    snapshot, and only commits when the bound identity matches. A drift
    of any evidence returns COMMIT_EVIDENCE_DRIFT or COMMIT_EVIDENCE_CONFLICT
    without writing anything.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    validation_run_instance_identity_hash: str = _HEX64


class ActualHarvestApiCommitResponse(BaseModel):
    """v0.2-S1 commit response body.

    `reused_existing_commit` is true when the batch was already COMMITTED
    and the request's validation_run_instance_identity_hash matches the
    one stored in the original manifest; in that case the server returned
    the original manifest without writing anything (zero-write exact replay).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    commit_policy_version: str
    commit_manifest_hash: str
    validation_run_instance_identity_hash: str
    committed_record_count: int
    committed_at: datetime
    committed_by_identity: str
    reused_existing_commit: bool


class ActualHarvestApiValidationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    validation_status: str
    validation_run_identity: str | None
    validation_result_hash: str | None
    lineage_graph_hash: str | None
    mapping_snapshot_hash: str | None
    resolved_identity_snapshot_hash: str | None
    committed_lineage_basis_hash: str | None
    season_resolver_version: str | None
    valid_count: int
    invalid_count: int
    error_count: int
    warning_count: int


class ActualHarvestApiPage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    page_size: int = Field(default=API_POLICY.default_page_size, strict=True)
    page_token: str | None = Field(default=None, max_length=2048, strict=True)


class ActualHarvestApiBatchSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    import_id: str
    status: str
    import_channel: str
    source_system: str
    source_dataset: str
    source_version: str
    external_batch_id: str
    idempotency_key: str
    submitted_by_identity: str
    expected_record_count_or_null: int | None
    uploaded_record_count: int
    record_count: int
    valid_record_count: int
    invalid_record_count: int
    committed_record_count: int
    seal_status: str
    sealed_record_count_or_null: int | None
    sealed_at_or_null: datetime | None
    sealed_by_identity_or_null: str | None
    server_raw_payload_hash_or_null: str | None
    canonical_batch_hash_or_null: str | None
    seal_manifest_hash_or_null: str | None
    created_at: datetime


class ActualHarvestApiRecordOutput(ActualHarvestImportRecordInput):
    model_config = ConfigDict(extra="forbid", frozen=True)

    import_received_at: datetime
    ingested_at: datetime


class ActualHarvestApiPagination(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    page_size: int
    next_page_token: str | None


class ActualHarvestApiEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str | None
    status: Literal["OK", "ERROR"]
    data_or_null: Any
    errors: tuple[dict[str, Any], ...] = ()
    warnings: tuple[dict[str, Any], ...] = ()
    pagination_or_null: ActualHarvestApiPagination | None = None
    canonical_hashes: dict[str, str] = {}
    provenance: dict[str, str] = {}


__all__ = [
    "ActualHarvestApiAppendRecordsRequest",
    "ActualHarvestApiBatchSummary",
    "ActualHarvestApiCommitRequest",
    "ActualHarvestApiCommitResponse",
    "ActualHarvestApiEnvelope",
    "ActualHarvestApiPage",
    "ActualHarvestApiRecordInput",
    "ActualHarvestApiRecordOutput",
    "ActualHarvestApiSealRequest",
    "ActualHarvestApiValidateRequest",
    "ActualHarvestApiValidationSummary",
]