"""I7 label-snapshot request/response schema definitions.

These pydantic models are pure value objects. They do not touch the
database directly; service.py maps them to ORM rows inside the
caller-owned transaction.

Frozen contract:
- docs/forecast-quality/q2a-i7-label-snapshot-and-revision-winner-contract.md §7, §13
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.actual_harvest_labels.enums import (
    ActualHarvestLabelVisibilityMode,
)


class ActualHarvestLabelSnapshotRequest(BaseModel):
    """Canonical I7 snapshot request value object.

    Contract §13 mandates that all canonical lists be sorted and unique
    before hashing. The ``model_validator`` below enforces that invariant
    at the value-object boundary.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshot_idempotency_key: str = Field(min_length=1)
    source_system: str = Field(min_length=1)
    visibility_mode: ActualHarvestLabelVisibilityMode
    label_observation_cutoff_at_or_null: datetime | None
    harvest_date_start: date
    harvest_date_end: date
    season_business_keys: tuple[str, ...]
    farm_business_keys_or_empty_for_all: tuple[str, ...]
    variety_business_keys_or_empty_for_all: tuple[str, ...]
    snapshot_policy_version: str = Field(min_length=1)
    winner_policy_version: str = Field(min_length=1)
    aggregation_policy_version: str = Field(min_length=1)

    @field_validator("source_system", "snapshot_policy_version")
    @classmethod
    def _no_whitespace(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("string field must not be blank")
        return stripped

    @model_validator(mode="after")
    def _enforce_contract_invariants(self) -> Self:
        canonical_lists: list[tuple[str, ...]] = [
            self.season_business_keys,
            self.farm_business_keys_or_empty_for_all,
            self.variety_business_keys_or_empty_for_all,
        ]
        for items in canonical_lists:
            if any(not item.strip() for item in items):
                raise ValueError("business-key lists must not contain blank entries")
            if list(items) != sorted(set(items)):
                raise ValueError("business-key lists must be canonical sorted unique")
        if self.harvest_date_start > self.harvest_date_end:
            raise ValueError("harvest_date_start must be <= harvest_date_end")
        if (
            self.visibility_mode == ActualHarvestLabelVisibilityMode.AS_OF_EVALUATION
            and self.label_observation_cutoff_at_or_null is None
        ):
            raise ValueError("AS_OF_EVALUATION requires label_observation_cutoff_at_or_null")
        if (
            self.visibility_mode == ActualHarvestLabelVisibilityMode.FINAL_ADJUDICATED
            and self.label_observation_cutoff_at_or_null is not None
        ):
            raise ValueError(
                "FINAL_ADJUDICATED requires label_observation_cutoff_at_or_null = NULL"
            )
        return self


class ActualHarvestLabelSnapshotHeader(BaseModel):
    """Snapshot header value object returned to callers.

    Hashed fields are SHA-256 lowercase hex. All IDs are database
    identifiers and excluded from canonical hashes per contract §14.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshot_id: int
    snapshot_idempotency_key: str
    source_system: str
    visibility_mode: ActualHarvestLabelVisibilityMode
    label_observation_cutoff_at_or_null: datetime | None
    harvest_date_start: date
    harvest_date_end: date
    snapshot_policy_version: str
    winner_policy_version: str
    aggregation_policy_version: str
    snapshot_executed_at: datetime
    snapshot_request_identity_hash: str
    snapshot_instance_identity_hash: str
    source_commit_manifest_set_hash: str
    winner_manifest_hash: str
    label_row_set_hash: str
    exclusion_manifest_hash: str
    label_snapshot_hash: str
    source_manifest_count: int
    winner_count: int
    label_row_count: int
    exclusion_row_count: int
    created_by_identity: str


class ActualHarvestLabelSnapshotResult(BaseModel):
    """Wrapper that pairs a header with the in-memory list of rows."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    header: ActualHarvestLabelSnapshotHeader
    winners: tuple[dict[str, object], ...]
    label_rows: tuple[dict[str, object], ...]
    exclusion_rows: tuple[dict[str, object], ...]


class ActualHarvestWinnerRow(BaseModel):
    """In-memory normalized winner row value object.

    A winner is the unique visible terminal of a logical record whose
    record_status is eligible for the requested visibility mode.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_system: str
    external_logical_record_id: str
    external_revision_id: str
    revision_number: int
    canonical_record_hash: str
    record_status: str
    effective_status: str
    finalized_at_or_null: datetime | None
    source_recorded_at_or_null: datetime | None
    source_recorded_at_authority_status: str
    harvest_business_date: date
    actual_harvest_quantity_kg: Decimal
    commit_manifest_hash: str
    season_business_key: str
    farm_business_key: str
    subfarm_business_key: str
    variety_business_key: str
    mapping_registry_version: str
    mapping_policy_version: str
    season_resolver_version: str
    mapping_registry_entry_hash: str | None
    resolved_master_business_key: str
    resolved_master_parent_business_key: str | None
    resolved_master_record_hash: str
    mapping_snapshot_hash: str
    resolved_identity_snapshot_hash: str
    registry_content_hash: str
    winner_row_hash: str


class ActualHarvestLabelRow(BaseModel):
    """In-memory canonical-grain aggregation row.

    Multiple winners may share a canonical grain (contract §12: same
    grain is not a duplicate). Sums are exact Decimal.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    season_business_key: str
    farm_business_key: str
    subfarm_business_key: str
    variety_business_key: str
    harvest_business_date: date
    exact_decimal_quantity_sum_kg: Decimal
    contributing_winner_count: int
    contributing_winner_hashes: tuple[str, ...]
    label_row_hash: str


class ActualHarvestExclusionRow(BaseModel):
    """In-memory coverage-exclusion row value object.

    Exclusion rows are deterministically ordered by
    (exclusion_category, source_system, external_logical_record_id_or_null,
    external_revision_id_or_null) so that the manifest hash is stable.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    exclusion_category: str
    source_system: str
    external_logical_record_id_or_null: str | None
    external_revision_id_or_null: str | None
    harvest_business_date_or_null: date | None
    exclusion_row_hash: str
    exclusion_details: dict[str, object]


__all__ = [
    "ActualHarvestExclusionRow",
    "ActualHarvestLabelRow",
    "ActualHarvestLabelSnapshotHeader",
    "ActualHarvestLabelSnapshotRequest",
    "ActualHarvestLabelSnapshotResult",
    "ActualHarvestWinnerRow",
]
