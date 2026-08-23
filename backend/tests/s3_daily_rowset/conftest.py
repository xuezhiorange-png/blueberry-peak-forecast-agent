"""Shared fixtures for S3-A daily rowset materializer tests."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from backend.app.s2_materialized_dataset.shared.contracts import MaterializableRow
from backend.app.s3_daily_rowset.actuals import InMemoryS2ActualsSource
from backend.app.s3_daily_rowset.forecast_port import FakeIncumbentDailyCurveProvider
from backend.app.s3_daily_rowset.schemas import (
    DatasetIdentity,
    EvaluationInstanceCell,
    HorizonWindowRequest,
)
from backend.app.s3_daily_rowset.service import DailyRowsetMaterializerService

SHANGHAI = ZoneInfo("Asia/Shanghai")

DATASET_IDENTITY = DatasetIdentity(
    dataset_id="source-002",
    dataset_version="e5-live-v1",
    materialized_dataset_identity_sha256=(
        "f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785"
    ),
)
HORIZON_H7_SUCCESS_FIXTURE_HASH = "8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18"


def make_row(
    *,
    season: str = "2025~2026",
    farm: str = "farm-a",
    subfarm: str = "subfarm-1",
    variety: str = "variety-x",
    harvest_business_date: date,
    quantity: str,
) -> MaterializableRow:
    return MaterializableRow(
        season=season,
        farm=farm,
        subfarm=subfarm,
        variety=variety,
        harvest_business_date=harvest_business_date,
        actual_harvest_quantity_kg=Decimal(quantity),
        source_row_identity=f"src-{harvest_business_date.isoformat()}",
        cleaned_row_identity=f"cln-{harvest_business_date.isoformat()}",
        pit_visibility_identity=f"pit-{harvest_business_date.isoformat()}",
        revision_winner_identity=f"rev-{harvest_business_date.isoformat()}",
    )


def make_cell(
    *,
    season: str = "2025~2026",
    farm: str = "farm-a",
    subfarm: str = "subfarm-1",
    variety: str = "variety-x",
    model_id: str = "incumbent-v0.2",
    forecast_cutoff_at: datetime | None = None,
    quantile: str = "P50",
) -> EvaluationInstanceCell:
    if forecast_cutoff_at is None:
        forecast_cutoff_at = datetime(2026, 2, 28, 16, 0, tzinfo=UTC)
    return EvaluationInstanceCell(
        season=season,
        farm=farm,
        subfarm=subfarm,
        variety=variety,
        model_id=model_id,
        forecast_cutoff_at=forecast_cutoff_at,
        forecast_quantile=quantile,
    )


def horizon_dates(
    cutoff_at: datetime,
    horizon_days: int,
) -> tuple[date, ...]:
    cutoff_business_date = cutoff_at.astimezone(SHANGHAI).date()
    start = cutoff_business_date.fromordinal(cutoff_business_date.toordinal() + 1)
    end = cutoff_business_date.fromordinal(cutoff_business_date.toordinal() + horizon_days)
    dates: list[date] = []
    current = start
    while current <= end:
        dates.append(current)
        current = current.fromordinal(current.toordinal() + 1)
    return tuple(dates)


@pytest.fixture
def cutoff() -> datetime:
    return datetime(2026, 2, 28, 16, 0, tzinfo=UTC)


@pytest.fixture
def cell(cutoff: datetime) -> EvaluationInstanceCell:
    return make_cell(forecast_cutoff_at=cutoff)


@pytest.fixture
def complete_window_rows(
    cell: EvaluationInstanceCell,
    cutoff: datetime,
) -> tuple[MaterializableRow, ...]:
    dates = horizon_dates(cutoff, 7)
    return tuple(
        make_row(harvest_business_date=day, quantity=f"{index + 1}.5")
        for index, day in enumerate(dates)
    )


@pytest.fixture
def materializer(
    complete_window_rows: tuple[MaterializableRow, ...],
    cutoff: datetime,
) -> DailyRowsetMaterializerService:
    dates = horizon_dates(cutoff, 7)
    forecasts = {day: Decimal("10.0") for day in dates}
    return DailyRowsetMaterializerService(
        dataset_identity=DATASET_IDENTITY,
        actuals_source=InMemoryS2ActualsSource(complete_window_rows),
        forecast_provider=FakeIncumbentDailyCurveProvider(forecasts=forecasts),
    )


@pytest.fixture
def horizon_request(cutoff: datetime) -> HorizonWindowRequest:
    return HorizonWindowRequest(
        evaluation_window_days=7,
        forecast_target_date=cutoff.astimezone(SHANGHAI)
        .date()
        .fromordinal(cutoff.astimezone(SHANGHAI).date().toordinal() + 7),
    )
