"""V0.3-S2 shared contracts for materialized dataset lanes.

Lane A/B/C upstream ports are Protocol stubs bound to contract identity
fields. Lane D consumes them without redefining upstream semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Protocol, runtime_checkable

# --- Inherited S1 authority (read-only references) --------------------------------

SOURCE_COHORT_ID = "source-002-s1-cohort-v1"
SOURCE_COHORT_MANIFEST_SHA256 = "27ddb9a77d9ce7d4b0579d0648c23b5ade7d6a090626b695e5b41827e714fcca"
TARGET_DECISION = "OBSERVED_FARM_PICK_QUANTITY"
ACTUAL_LABEL = "actual_harvest_quantity_kg"
CANONICAL_GRAIN = "SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE"
PARTITION_DATE_FIELD = "HARVEST_BUSINESS_DATE"
SPLIT_POLICY_VERSION = "v0-3-s1-time-ordered-split-policy-v1"

BUILDER_VERSION = "v0-3-s2-lane-d-builder-r1"
DATASET_SCHEMA_VERSION = "v0-3-s2-materialized-dataset-v1"
MANIFEST_SCHEMA_VERSION = "v0-3-s2-materialized-dataset-manifest-v1"
MATERIALIZED_PARTITION_SCHEMA_VERSION = "v0-3-s2-materialized-partition-v1"

SOURCE_002_ROW_LEVEL_READ = False
MATERIALIZED_DATASET_API_POLICY_VERSION = "v0-3-s2-lane-d-api-r1"


class PartitionName(StrEnum):
    TRAIN = "TRAIN"
    VALIDATION = "VALIDATION"
    TEST = "TEST"


class QualityGateStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class RebuildHashReplayStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_RUN = "NOT_RUN"


@dataclass(frozen=True, slots=True)
class MaterializableRow:
    """One cleaned row eligible for TRAIN/VALIDATION partition membership."""

    season: str
    farm: str
    subfarm: str
    variety: str
    harvest_business_date: date
    actual_harvest_quantity_kg: Decimal
    source_row_identity: str
    cleaned_row_identity: str
    pit_visibility_identity: str
    revision_winner_identity: str


@runtime_checkable
class LaneAUpstreamPort(Protocol):
    """Lane A raw ingestion and lineage foundation (contract §4.1–4.3)."""

    @property
    def source_cohort_id(self) -> str: ...

    @property
    def source_cohort_manifest_sha256(self) -> str: ...

    @property
    def raw_policy_version(self) -> str: ...

    def lineage_identity_present(self) -> bool: ...


@runtime_checkable
class LaneBUpstreamPort(Protocol):
    """Lane B cleaning, quality, and correction (contract §4.4–4.7)."""

    @property
    def cleaned_dataset_version_identity(self) -> str: ...

    @property
    def cleaning_policy_version(self) -> str: ...

    @property
    def correction_policy_version(self) -> str: ...

    @property
    def exclusion_policy_version(self) -> str: ...

    def iter_materializable_rows(self) -> tuple[MaterializableRow, ...]: ...

    def lineage_identity_present(self) -> bool: ...


@runtime_checkable
class LaneCUpstreamPort(Protocol):
    """Lane C PIT visibility and revision winner (contract §4.8–4.10)."""

    @property
    def visibility_policy_version(self) -> str: ...

    @property
    def revision_winner_policy_version(self) -> str: ...

    def lineage_identity_present(self) -> bool: ...


@runtime_checkable
class UpstreamBundlePort(Protocol):
    """Complete upstream dependency surface for Lane D materialization."""

    @property
    def lane_a(self) -> LaneAUpstreamPort: ...

    @property
    def lane_b(self) -> LaneBUpstreamPort: ...

    @property
    def lane_c(self) -> LaneCUpstreamPort: ...
