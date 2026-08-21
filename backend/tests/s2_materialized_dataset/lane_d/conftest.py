"""Shared fixtures for Lane D materialized dataset tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from backend.app.s2_materialized_dataset.shared.contracts import (
    SOURCE_COHORT_ID,
    SOURCE_COHORT_MANIFEST_SHA256,
    MaterializableRow,
)


@dataclass(frozen=True, slots=True)
class FakeLaneA:
    source_cohort_id: str = SOURCE_COHORT_ID
    source_cohort_manifest_sha256: str = SOURCE_COHORT_MANIFEST_SHA256
    raw_policy_version: str = "v0-3-s2-raw-policy-v1"
    lineage_present: bool = True

    def lineage_identity_present(self) -> bool:
        return self.lineage_present


@dataclass(frozen=True, slots=True)
class FakeLaneB:
    cleaned_dataset_version_identity: str = "cleaned-dataset-v1"
    cleaning_policy_version: str = "v0-3-s2-cleaning-policy-v1"
    correction_policy_version: str = "v0-3-s2-correction-policy-v1"
    exclusion_policy_version: str = "v0-3-s2-exclusion-policy-v1"
    rows: tuple[MaterializableRow, ...] = ()
    lineage_present: bool = True

    def iter_materializable_rows(self) -> tuple[MaterializableRow, ...]:
        return self.rows

    def lineage_identity_present(self) -> bool:
        return self.lineage_present


@dataclass(frozen=True, slots=True)
class FakeLaneC:
    visibility_policy_version: str = "v0-3-s2-visibility-policy-v1"
    revision_winner_policy_version: str = "v0-3-s2-revision-winner-policy-v1"
    lineage_present: bool = True

    def lineage_identity_present(self) -> bool:
        return self.lineage_present


@dataclass(frozen=True, slots=True)
class FakeUpstream:
    lane_a: FakeLaneA
    lane_b: FakeLaneB
    lane_c: FakeLaneC


def make_row(
    *,
    season: str = "2025-26",
    farm: str = "farm-a",
    subfarm: str = "subfarm-1",
    variety: str = "variety-x",
    harvest_business_date: date = date(2025, 9, 1),
    quantity: str = "100.0",
    source_row_identity: str = "source-row-1",
    cleaned_row_identity: str = "cleaned-row-1",
    pit_visibility_identity: str = "pit-vis-1",
    revision_winner_identity: str = "rev-win-1",
) -> MaterializableRow:
    return MaterializableRow(
        season=season,
        farm=farm,
        subfarm=subfarm,
        variety=variety,
        harvest_business_date=harvest_business_date,
        actual_harvest_quantity_kg=Decimal(quantity),
        source_row_identity=source_row_identity,
        cleaned_row_identity=cleaned_row_identity,
        pit_visibility_identity=pit_visibility_identity,
        revision_winner_identity=revision_winner_identity,
    )


def complete_upstream(rows: tuple[MaterializableRow, ...] | None = None) -> FakeUpstream:
    sample_rows = rows or (
        make_row(harvest_business_date=date(2025, 9, 1)),
        make_row(
            harvest_business_date=date(2026, 2, 15),
            source_row_identity="source-row-2",
            cleaned_row_identity="cleaned-row-2",
            pit_visibility_identity="pit-vis-2",
            revision_winner_identity="rev-win-2",
        ),
    )
    return FakeUpstream(
        lane_a=FakeLaneA(),
        lane_b=FakeLaneB(rows=sample_rows),
        lane_c=FakeLaneC(),
    )
