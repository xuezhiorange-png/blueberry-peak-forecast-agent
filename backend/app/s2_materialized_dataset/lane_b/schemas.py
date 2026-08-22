"""V0.3-S2 Lane B cleaned-dataset value objects and synthetic upstream fixtures."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SOURCE_COHORT_ID = "source-002-s1-cohort-v1"
CANONICAL_GRAIN = "SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE"

SOURCE_002_MAPPED_SEASON_BUSINESS_KEY = "2025~2026"
SOURCE_002_UNMAPPED_SEASON_BUSINESS_KEY = "UNMAPPED_NOT_IN_S1_COHORT"
SOURCE_002_JULY_COHORT_EXCLUSION_REASON = "source-002-s1-cohort-unmapped-july-2025-07-22-option-a"
SOURCE_002_CLEANING_DECISION_AUTHORITY = "source-002-final-source-cohort-manifest-v1"
SOURCE_002_JULY_COHORT_EXCLUDED_ROW_COUNT = 2
SOURCE_002_CANONICAL_GRAIN_KG_SUM_LEDGER_POLICY_VERSION = "s2-source-002-canonical-grain-kg-sum-v1"


class QuantityPresenceStatus(StrEnum):
    KNOWN = "KNOWN"
    UNKNOWN_NOT_ZERO = "UNKNOWN_NOT_ZERO"


class QualityFindingCode(StrEnum):
    MISSING_QUANTITY_UNKNOWN_NOT_ZERO = "MISSING_QUANTITY_UNKNOWN_NOT_ZERO"
    DUPLICATE_CANONICAL_GRAIN = "DUPLICATE_CANONICAL_GRAIN"


class QualityFindingSeverity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"


class ExclusionCode(StrEnum):
    BUSINESS_EXCLUSION = "BUSINESS_EXCLUSION"
    QUALITY_BLOCKED = "QUALITY_BLOCKED"


class _FrozenContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class SyntheticRawSourceArtifactIdentity(_FrozenContractModel):
    source_system: str
    source_dataset: str
    source_version: str
    source_snapshot_reference: str
    source_object_identity: str
    source_artifact_sequence: int = Field(ge=1)
    schema_version: str
    mapping_policy_version: str
    source_artifact_identity_version: str


class SyntheticRawImportBatchIdentity(_FrozenContractModel):
    raw_source_artifact_identity_hash: str = Field(min_length=64, max_length=64)
    external_batch_id: str
    source_system: str
    source_dataset: str
    raw_payload_hash: str = Field(min_length=64, max_length=64)
    import_policy_version: str
    schema_version: str
    mapping_policy_version: str
    validation_policy_version: str
    source_cohort_id: str = SOURCE_COHORT_ID


class SyntheticSourceRowIdentity(_FrozenContractModel):
    raw_source_artifact_identity_hash: str = Field(min_length=64, max_length=64)
    raw_import_batch_identity_hash: str = Field(min_length=64, max_length=64)
    external_logical_record_id: str
    external_revision_id: str
    revision_number: int = Field(ge=1)
    source_system: str
    source_row_identity_version: str
    schema_version: str
    source_version: str
    source_sheet_name: str | None = None
    source_row_number: int | None = Field(default=None, ge=1)


class CanonicalGrainKey(_FrozenContractModel):
    season_business_key: str
    farm_business_key: str
    subfarm_business_key: str
    variety_business_key: str
    harvest_business_date: date

    @property
    def canonical_grain_key(self) -> str:
        return (
            f"{self.season_business_key}|{self.farm_business_key}|"
            f"{self.subfarm_business_key}|{self.variety_business_key}|"
            f"{self.harvest_business_date.isoformat()}"
        )


class SyntheticSourceRowInput(_FrozenContractModel):
    identity: SyntheticSourceRowIdentity
    season_business_key: str
    farm_business_key: str
    subfarm_business_key: str
    variety_business_key: str
    harvest_business_date: date
    actual_harvest_quantity_kg: Decimal | None
    missing_record_semantics: str = "UNKNOWN_NOT_ZERO"
    record_status: str = "FINALIZED"
    source_recorded_at: datetime | None = None
    persisted_source_row_identity_hash: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
    )

    @model_validator(mode="after")
    def _reject_zero_imputation_for_unknown(self) -> Self:
        if self.actual_harvest_quantity_kg is None:
            if self.missing_record_semantics != "UNKNOWN_NOT_ZERO":
                raise ValueError("missing quantity must use UNKNOWN_NOT_ZERO semantics")
        elif (
            self.actual_harvest_quantity_kg == 0
            and self.missing_record_semantics == "UNKNOWN_NOT_ZERO"
        ):
            raise ValueError("zero must not be substituted for unknown missing-day quantity")
        return self


class ManualCorrectionRequest(_FrozenContractModel):
    correction_event_id: str
    source_row_identity_hash: str = Field(min_length=64, max_length=64)
    field_name: str
    corrected_value: Decimal
    reason: str
    quality_finding_identity_hash: str | None = Field(default=None, min_length=64, max_length=64)
    manual_actor_or_authority_reference: str


class ManualExclusionRequest(_FrozenContractModel):
    exclusion_event_id: str
    source_row_identity_hash: str = Field(min_length=64, max_length=64)
    exclusion_code: ExclusionCode
    exclusion_reason_reference: str
    decision_authority_reference: str
    quality_finding_identity_hash: str | None = Field(default=None, min_length=64, max_length=64)


class LaneASourceRowsNotMaterializedError(ValueError):
    """Lane A SOURCE_002 facts are not persisted and E3 cleaning must stop."""


class Source002CleaningBlockedError(ValueError):
    """SOURCE_002 cleaning cannot proceed under governed policy."""


class Source002GrainKgSumBlockedError(Source002CleaningBlockedError):
    """Canonical-grain kilogram sum collapse cannot proceed under ledger policy."""


class Source002E3CollisionGroupSample(_FrozenContractModel):
    farm_business_key: str
    subfarm_business_key: str
    variety_business_key: str
    harvest_business_date: date
    row_count: int
    chain_distinct_count: int
    fruit_size_distinct_count: int
    kg_values: tuple[str, ...]


class Source002E3DiagnosticReport(_FrozenContractModel):
    source_rows_in_scope: int
    unique_canonical_grains: int
    singleton_grain_count: int
    collision_grain_count: int
    rows_in_singleton_grains: int
    rows_in_collision_grains: int
    kg_in_singleton_grains: Decimal
    kg_in_collision_grains: Decimal
    kg_total_in_scope: Decimal
    collision_group_size_min: int
    collision_group_size_p50: int
    collision_group_size_p90: int
    collision_group_size_max: int
    collision_group_samples: tuple[Source002E3CollisionGroupSample, ...] = ()


class CanonicalGrainCollisionBlockedError(Source002CleaningBlockedError):
    """Unresolved canonical-grain collisions require Lane C winner selection."""

    def __init__(
        self,
        message: str,
        *,
        conflict_group_count: int,
        conflict_group_row_counts: tuple[tuple[str, int], ...],
        diagnostics: Source002E3DiagnosticReport | None = None,
    ) -> None:
        super().__init__(message)
        self.conflict_group_count = conflict_group_count
        self.conflict_group_row_counts = conflict_group_row_counts
        self.diagnostics = diagnostics


class CleaningBuildRequest(_FrozenContractModel):
    source_cohort_id: str = SOURCE_COHORT_ID
    raw_source_artifacts: tuple[SyntheticRawSourceArtifactIdentity, ...] = ()
    raw_import_batches: tuple[SyntheticRawImportBatchIdentity, ...] = ()
    persisted_raw_source_artifact_identity_hashes: tuple[str, ...] = ()
    persisted_raw_import_batch_identity_hashes: tuple[str, ...] = ()
    source_rows: tuple[SyntheticSourceRowInput, ...]
    mapping_registry_hash: str = Field(min_length=64, max_length=64)
    cleaning_policy_version: str
    quality_policy_version: str
    correction_policy_version: str
    exclusion_policy_version: str
    cleaned_schema_version: str
    cleaning_projection_version: str
    quality_schema_version: str
    correction_schema_version: str
    exclusion_schema_version: str
    quality_rule_version: str
    manual_corrections: tuple[ManualCorrectionRequest, ...] = ()
    manual_exclusions: tuple[ManualExclusionRequest, ...] = ()
    canonical_grain_kg_sum_ledger_policy_version: str | None = None

    @field_validator(
        "raw_source_artifacts",
        "raw_import_batches",
        "source_rows",
        "persisted_raw_source_artifact_identity_hashes",
        "persisted_raw_import_batch_identity_hashes",
        mode="before",
    )
    @classmethod
    def _coerce_sequences(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="after")
    def _require_non_empty_rows(self) -> Self:
        if not self.source_rows:
            raise ValueError("cleaning build requires at least one source row")
        return self

    @model_validator(mode="after")
    def _require_lineage_binding(self) -> Self:
        has_synthetic = bool(self.raw_source_artifacts or self.raw_import_batches)
        has_persisted = bool(
            self.persisted_raw_source_artifact_identity_hashes
            or self.persisted_raw_import_batch_identity_hashes
        )
        if has_synthetic and has_persisted:
            raise ValueError("cleaning build cannot mix synthetic and persisted lineage")
        if not has_synthetic and not has_persisted:
            raise ValueError("cleaning build requires synthetic or persisted lineage")
        if has_synthetic and (not self.raw_source_artifacts or not self.raw_import_batches):
            raise ValueError("synthetic cleaning build requires artifact and batch identities")
        if has_persisted and (
            not self.persisted_raw_source_artifact_identity_hashes
            or not self.persisted_raw_import_batch_identity_hashes
        ):
            raise ValueError("persisted cleaning build requires artifact and batch hashes")
        return self


class QualityFindingRecord(_FrozenContractModel):
    quality_finding_identity_hash: str
    cleaned_dataset_version_identity_hash: str
    source_row_identity_hash: str
    cleaned_row_identity_hash: str | None
    quality_rule_id: str
    quality_rule_version: str
    observed_field: str
    finding_code: QualityFindingCode
    severity: QualityFindingSeverity
    normalized_observed_value_identity: str
    rule_definition_hash: str
    validation_run_identity: str


class CorrectionLedgerEntryRecord(_FrozenContractModel):
    correction_ledger_entry_identity_hash: str
    cleaned_dataset_version_identity_hash: str
    source_row_identity_hash: str
    correction_event_id: str
    field_name: str
    correction_policy_version: str
    correction_schema_version: str
    quality_finding_identity_hash: str | None
    original_value_digest: str
    corrected_value_digest: str
    reason: str
    manual_actor_or_authority_reference: str


class ExclusionLedgerEntryRecord(_FrozenContractModel):
    exclusion_ledger_entry_identity_hash: str
    cleaned_dataset_version_identity_hash: str
    source_row_identity_hash: str
    exclusion_event_id: str
    exclusion_code: ExclusionCode
    exclusion_policy_version: str
    exclusion_schema_version: str
    quality_finding_identity_hash: str | None
    exclusion_reason_reference: str
    decision_authority_reference: str


class CleanedRowRecord(_FrozenContractModel):
    cleaned_row_identity_hash: str
    cleaned_row_content_hash: str
    cleaned_dataset_version_identity_hash: str
    source_row_identity_hash: str
    canonical_grain_key: CanonicalGrainKey
    cleaning_projection_version: str
    cleaned_row_schema_version: str
    cleaning_policy_version: str
    correction_policy_version: str
    exclusion_policy_version: str
    source_actual_harvest_quantity_kg: Decimal | None
    effective_actual_harvest_quantity_kg: Decimal | None
    quantity_presence_status: QuantityPresenceStatus
    is_excluded: bool
    quality_finding_identity_hashes: tuple[str, ...]
    correction_ledger_entry_identity_hashes: tuple[str, ...]
    exclusion_ledger_entry_identity_hashes: tuple[str, ...]


class CleanedDatasetVersionRecord(_FrozenContractModel):
    cleaned_dataset_version_identity_hash: str
    cleaned_dataset_version_content_hash: str
    source_cohort_id: str
    mapping_registry_hash: str
    cleaning_policy_version: str
    quality_policy_version: str
    correction_policy_version: str
    exclusion_policy_version: str
    cleaned_schema_version: str
    raw_source_artifact_identity_hashes: tuple[str, ...]
    raw_import_batch_identity_hashes: tuple[str, ...]
    source_row_identity_hashes: tuple[str, ...]
    quality_report_identity_hash: str
    correction_ledger_identity_hashes: tuple[str, ...]
    exclusion_ledger_identity_hashes: tuple[str, ...]
    cleaned_row_identity_hashes: tuple[str, ...]
    cleaned_row_content_hashes: tuple[str, ...]
    row_count: int
    excluded_row_count: int
    unknown_quantity_row_count: int


class CleaningBuildResult(_FrozenContractModel):
    version: CleanedDatasetVersionRecord
    cleaned_rows: tuple[CleanedRowRecord, ...]
    quality_findings: tuple[QualityFindingRecord, ...]
    correction_ledger_entries: tuple[CorrectionLedgerEntryRecord, ...]
    exclusion_ledger_entries: tuple[ExclusionLedgerEntryRecord, ...]


class Source002CleaningResult(_FrozenContractModel):
    ingest_source_row_count: int
    ingest_first_seen_row_count: int
    ingest_replay_row_count: int
    raw_source_row_count: int
    canonical_source_row_count: int
    july_excluded_row_count: int
    grain_conflict_group_count: int
    diagnostics: Source002E3DiagnosticReport | None = None
    cleaning: CleaningBuildResult
