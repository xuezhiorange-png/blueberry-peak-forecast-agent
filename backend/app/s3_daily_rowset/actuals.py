"""Read-only S2 actuals port for S3-A daily rowset materialization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from backend.app.s2_materialized_dataset.lane_d.partitions import (
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    VALIDATION_END,
    VALIDATION_START,
)
from backend.app.s2_materialized_dataset.shared.contracts import MaterializableRow
from backend.app.s3_daily_rowset.schemas import DailyRowStatus, EvaluationInstanceCell


def partition_for_harvest_date(harvest_business_date: date) -> str | None:
    if TRAIN_START <= harvest_business_date <= TRAIN_END:
        return "TRAIN"
    if VALIDATION_START <= harvest_business_date <= VALIDATION_END:
        return "VALIDATION"
    if TEST_START <= harvest_business_date <= TEST_END:
        return "TEST"
    return None


def is_evaluation_partition_allowed(harvest_business_date: date) -> bool:
    partition = partition_for_harvest_date(harvest_business_date)
    return partition in {"TRAIN", "VALIDATION"}


def window_contains_test_partition(window_dates: tuple[date, ...]) -> bool:
    return any(not is_evaluation_partition_allowed(day) for day in window_dates)


@dataclass(frozen=True, slots=True)
class ActualLookup:
    daily_row_status: DailyRowStatus
    actual_harvest_quantity_kg: Decimal | None = None


class S2ActualsSourcePort:
    """Lookup accepted S2 grains at canonical harvest-date grain."""

    def lookup_actual(
        self,
        cell: EvaluationInstanceCell,
        business_date: date,
    ) -> ActualLookup:
        raise NotImplementedError


@dataclass
class InMemoryS2ActualsSource(S2ActualsSourcePort):
    rows: tuple[MaterializableRow, ...]
    day_exclusions: frozenset[date] | None = None

    def __post_init__(self) -> None:
        self._index: dict[tuple[str, str, str, str, date], MaterializableRow] = {}
        for row in self.rows:
            key = (row.season, row.farm, row.subfarm, row.variety, row.harvest_business_date)
            self._index[key] = row

    def lookup_actual(
        self,
        cell: EvaluationInstanceCell,
        business_date: date,
    ) -> ActualLookup:
        if self.day_exclusions and business_date in self.day_exclusions:
            return ActualLookup(daily_row_status=DailyRowStatus.EXCLUDED)
        key = (cell.season, cell.farm, cell.subfarm, cell.variety, business_date)
        row = self._index.get(key)
        if row is None:
            return ActualLookup(daily_row_status=DailyRowStatus.UNKNOWN)
        return ActualLookup(
            daily_row_status=DailyRowStatus.OBSERVED,
            actual_harvest_quantity_kg=row.actual_harvest_quantity_kg,
        )
