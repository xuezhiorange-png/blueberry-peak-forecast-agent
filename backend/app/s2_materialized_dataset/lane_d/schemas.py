"""Pydantic schemas for Lane D materialized dataset manifests and build results."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.s2_materialized_dataset.shared.contracts import (
    BUILDER_VERSION,
    CANONICAL_GRAIN,
    DATASET_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    MATERIALIZED_PARTITION_SCHEMA_VERSION,
    SOURCE_COHORT_ID,
    SOURCE_COHORT_MANIFEST_SHA256,
    SPLIT_POLICY_VERSION,
    TARGET_DECISION,
    PartitionName,
    QualityGateStatus,
    RebuildHashReplayStatus,
)


class PartitionManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    dataset_id: str
    dataset_version: str
    partition_name: PartitionName
    source_cohort_id: str = SOURCE_COHORT_ID
    source_cohort_manifest_sha256: str = SOURCE_COHORT_MANIFEST_SHA256
    target_decision: str = TARGET_DECISION
    canonical_grain: str = CANONICAL_GRAIN
    partition_date_field: Literal["HARVEST_BUSINESS_DATE"] = "HARVEST_BUSINESS_DATE"
    partition_start_date: date
    partition_end_date: date

    raw_policy_version: str
    cleaning_policy_version: str
    correction_policy_version: str
    exclusion_policy_version: str
    visibility_policy_version: str
    revision_winner_policy_version: str
    split_policy_version: str = SPLIT_POLICY_VERSION
    builder_version: str = BUILDER_VERSION
    dataset_schema_version: str = DATASET_SCHEMA_VERSION
    manifest_schema_version: str = MANIFEST_SCHEMA_VERSION
    materialized_partition_schema_version: str = MATERIALIZED_PARTITION_SCHEMA_VERSION

    row_count: int = Field(ge=0)
    byte_count: int = Field(ge=0)
    content_sha256: str
    partition_identity_sha256: str
    manifest_sha256: str

    build_started_at: datetime
    build_completed_at: datetime

    lineage_complete: bool
    quality_gate_status: QualityGateStatus
    rebuild_hash_replay_status: RebuildHashReplayStatus


class MaterializedDatasetResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    dataset_id: str
    dataset_version: str
    materialized_dataset_identity_sha256: str
    lineage_complete: bool
    quality_gate_status: QualityGateStatus
    partitions: tuple[PartitionManifest, ...]


class MaterializedPartitionBytes(BaseModel):
    model_config = ConfigDict(frozen=True)

    partition_name: PartitionName
    content_bytes: bytes
    row_count: int
    byte_count: int
    content_sha256: str
