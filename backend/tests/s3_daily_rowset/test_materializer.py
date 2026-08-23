"""S3-A daily rowset materializer contract tests."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from backend.app.s2_materialized_dataset.lane_d.partitions import TEST_START
from backend.app.s2_materialized_dataset.shared.contracts import MaterializableRow
from backend.app.s3_daily_rowset.actuals import InMemoryS2ActualsSource
from backend.app.s3_daily_rowset.forecast_port import FakeIncumbentDailyCurveProvider
from backend.app.s3_daily_rowset.schemas import (
    DailyRowStatus,
    DatasetIdentity,
    DatasetIdentityMismatchError,
    EvaluationInstanceCell,
    HorizonWindowRequest,
    MaterializationOutcome,
    ReasonCode,
)
from backend.app.s3_daily_rowset.service import DailyRowsetMaterializerService
from backend.app.s3_daily_rowset.window import (
    complete_season_window_dates,
    derive_season_year,
    horizon_window_dates,
    sustained_peak_completeness_predicate,
)
from backend.tests.s3_daily_rowset.conftest import (
    DATASET_IDENTITY,
    horizon_dates,
    make_cell,
    make_row,
)


def _service(
    rows: tuple[MaterializableRow, ...],
    *,
    forecasts: dict[date, Decimal] | None = None,
    forecast_unavailable: bool = False,
    dataset_identity: DatasetIdentity = DATASET_IDENTITY,
    day_exclusions: frozenset[date] | None = None,
) -> DailyRowsetMaterializerService:
    if forecasts is None and not forecast_unavailable:
        forecasts = {row.harvest_business_date: Decimal("1.0") for row in rows}
    return DailyRowsetMaterializerService(
        dataset_identity=dataset_identity,
        actuals_source=InMemoryS2ActualsSource(rows, day_exclusions=day_exclusions),
        forecast_provider=FakeIncumbentDailyCurveProvider(
            forecasts=forecasts,
            unavailable=forecast_unavailable,
        ),
    )


def _request(
    cutoff: datetime,
    *,
    horizon_days: int = 7,
    target_date: date | None = None,
) -> HorizonWindowRequest:
    cutoff_date = cutoff.astimezone(ZoneInfo("Asia/Shanghai")).date()
    if target_date is None:
        target_date = cutoff_date.fromordinal(cutoff_date.toordinal() + horizon_days)
    return HorizonWindowRequest(
        evaluation_window_days=horizon_days,
        forecast_target_date=target_date,
    )


def _materialize(
    service: DailyRowsetMaterializerService,
    cutoff: datetime,
    *,
    variety: str = "variety-x",
    farm: str = "farm-a",
    horizon_days: int = 7,
    target_date: date | None = None,
):
    cell = make_cell(forecast_cutoff_at=cutoff, variety=variety, farm=farm)
    return service.materialize_horizon_window(
        cell,
        _request(cutoff, horizon_days=horizon_days, target_date=target_date),
    )


@pytest.mark.parametrize("horizon_days", [7, 14, 21])
def test_horizon_window_has_exactly_h_calendar_days(horizon_days: int) -> None:
    cutoff = datetime(2026, 2, 28, 16, 0, tzinfo=UTC)
    window = horizon_window_dates(cutoff, horizon_days)
    assert len(window) == horizon_days
    cutoff_date = cutoff.astimezone(ZoneInfo("Asia/Shanghai")).date()
    assert window[0] == cutoff_date.fromordinal(cutoff_date.toordinal() + 1)
    assert window[-1] == cutoff_date.fromordinal(cutoff_date.toordinal() + horizon_days)


def test_target_date_mismatch_rejects_without_realigning_window() -> None:
    cutoff = datetime(2026, 2, 28, 16, 0, tzinfo=UTC)
    dates = horizon_dates(cutoff, 7)
    rows = tuple(make_row(harvest_business_date=day, quantity="1.0") for day in dates)
    service = _service(rows)
    cell = make_cell(forecast_cutoff_at=cutoff)
    wrong_target = dates[-1].fromordinal(dates[-1].toordinal() + 1)
    result = service.materialize_horizon_window(
        cell,
        _request(cutoff, target_date=wrong_target),
    )
    assert result.outcome == MaterializationOutcome.NOT_COMPUTABLE
    assert result.reason_code == ReasonCode.TARGET_DATE_CUTOFF_HORIZON_MISMATCH
    assert result.daily_rows == ()


def test_missing_day_is_unknown_not_zero_and_rejects_window() -> None:
    cutoff = datetime(2026, 2, 28, 16, 0, tzinfo=UTC)
    dates = horizon_dates(cutoff, 7)
    rows = tuple(
        make_row(harvest_business_date=day, quantity="2.0") for day in dates if day != dates[3]
    )
    service = _service(rows)
    result = _materialize(service, cutoff)
    assert result.outcome == MaterializationOutcome.REJECTED
    assert result.reason_code == ReasonCode.WINDOW_REJECTED_UNKNOWN_OR_EXCLUDED_DAY
    missing_row = next(row for row in result.daily_rows if row.business_date == dates[3])
    assert missing_row.daily_row_status == DailyRowStatus.UNKNOWN
    assert missing_row.actual_harvest_quantity_kg is None


@pytest.mark.parametrize(
    ("variety", "farm"),
    [
        ("普鲜", "farm-a"),
        ("variety-x", "巴松加工厂"),
    ],
)
def test_cell_level_exclusion_does_not_generate_window(variety: str, farm: str) -> None:
    cutoff = datetime(2026, 2, 28, 16, 0, tzinfo=UTC)
    dates = horizon_dates(cutoff, 7)
    rows = tuple(
        make_row(harvest_business_date=day, quantity="1.0", variety=variety, farm=farm)
        for day in dates
    )
    service = _service(rows)
    result = _materialize(service, cutoff, variety=variety, farm=farm)
    assert result.outcome == MaterializationOutcome.CELL_EXCLUDED
    assert result.daily_rows == ()


def test_day_level_excluded_in_window_rejects_entire_window() -> None:
    cutoff = datetime(2026, 2, 28, 16, 0, tzinfo=UTC)
    dates = horizon_dates(cutoff, 7)
    rows = tuple(make_row(harvest_business_date=day, quantity="3.0") for day in dates)
    service = _service(rows, day_exclusions=frozenset({dates[2]}))
    result = _materialize(service, cutoff)
    assert result.outcome == MaterializationOutcome.REJECTED
    assert result.reason_code == ReasonCode.WINDOW_REJECTED_UNKNOWN_OR_EXCLUDED_DAY
    excluded_row = next(row for row in result.daily_rows if row.business_date == dates[2])
    assert excluded_row.daily_row_status == DailyRowStatus.EXCLUDED


def test_test_partition_rows_are_rejected() -> None:
    test_day = TEST_START
    rows = (make_row(harvest_business_date=test_day, quantity="5.0"),)
    service = _service(rows)
    cutoff = datetime(2026, 3, 9, 16, 0, tzinfo=UTC)
    result = _materialize(service, cutoff)
    assert result.outcome == MaterializationOutcome.REJECTED
    assert result.reason_code == ReasonCode.TEST_PARTITION_NOT_ALLOWED


def test_dataset_identity_mismatch_fails_closed() -> None:
    cutoff = datetime(2026, 2, 28, 16, 0, tzinfo=UTC)
    dates = horizon_dates(cutoff, 7)
    rows = tuple(make_row(harvest_business_date=day, quantity="1.0") for day in dates)
    bad_identity = DatasetIdentity(
        dataset_id="source-002",
        dataset_version="e5-live-v1",
        materialized_dataset_identity_sha256="0" * 64,
    )
    with pytest.raises(DatasetIdentityMismatchError):
        _service(rows, dataset_identity=bad_identity)


def test_missing_forecast_daily_curve_rejects_window() -> None:
    cutoff = datetime(2026, 2, 28, 16, 0, tzinfo=UTC)
    dates = horizon_dates(cutoff, 7)
    rows = tuple(make_row(harvest_business_date=day, quantity="4.0") for day in dates)
    service = _service(rows, forecast_unavailable=True)
    result = _materialize(service, cutoff)
    assert result.outcome == MaterializationOutcome.REJECTED
    assert result.reason_code == ReasonCode.FORECAST_UNAVAILABLE


def test_identity_hash_is_reproducible_and_changes_when_kg_changes(
    materializer: DailyRowsetMaterializerService,
    cell: EvaluationInstanceCell,
    horizon_request: HorizonWindowRequest,
    complete_window_rows: tuple[MaterializableRow, ...],
    cutoff: datetime,
) -> None:
    first = materializer.materialize_horizon_window(cell, horizon_request)
    second = materializer.materialize_horizon_window(cell, horizon_request)
    assert first.outcome == MaterializationOutcome.SUCCESS
    assert first.rowset_identity_sha256 == second.rowset_identity_sha256
    assert first.rowset_identity_sha256 is not None

    tampered_rows = list(complete_window_rows)
    tampered = tampered_rows[0]
    tampered_rows[0] = make_row(
        harvest_business_date=tampered.harvest_business_date,
        quantity="99.9",
    )
    tampered_service = _service(tuple(tampered_rows))
    tampered_result = tampered_service.materialize_horizon_window(cell, horizon_request)
    assert tampered_result.rowset_identity_sha256 != first.rowset_identity_sha256


def test_complete_season_year_derivation_failure_is_not_computable() -> None:
    assert derive_season_year("NOT_A_SEASON") is None
    cell = make_cell(season="NOT_A_SEASON")
    service = _service(())
    result = service.materialize_complete_season_window(cell)
    assert result.outcome == MaterializationOutcome.NOT_COMPUTABLE
    assert result.reason_code == ReasonCode.SEASON_YEAR_DERIVATION_FAILURE


def test_sustained_peak_predicates_constructable_without_pass(
    materializer: DailyRowsetMaterializerService,
    cell: EvaluationInstanceCell,
    horizon_request: HorizonWindowRequest,
) -> None:
    predicate_3 = sustained_peak_completeness_predicate(3)
    predicate_7 = sustained_peak_completeness_predicate(7)
    assert predicate_3.window_days == 3
    assert predicate_7.window_days == 7
    result = materializer.materialize_horizon_window(cell, horizon_request)
    assert result.outcome == MaterializationOutcome.SUCCESS
    assert result.sustained_peak_pass_allowed is False
    assert predicate_3.evaluate(result.daily_rows).pass_allowed is False
    assert predicate_7.evaluate(result.daily_rows).pass_allowed is False


def test_non_jan_apr_horizon_is_cell_excluded() -> None:
    cutoff = datetime(2025, 8, 4, 16, 0, tzinfo=UTC)
    dates = horizon_dates(cutoff, 7)
    rows = tuple(make_row(harvest_business_date=day, quantity="1.0") for day in dates)
    service = _service(rows)
    result = _materialize(service, cutoff)
    assert result.outcome == MaterializationOutcome.CELL_EXCLUDED
    assert all(day.month in {1, 2, 3, 4} for day in complete_season_window_dates("2025~2026"))


def test_complete_season_window_spans_jan_to_apr() -> None:
    window = complete_season_window_dates("2025~2026")
    assert window[0] == date(2026, 1, 1)
    assert window[-1] == date(2026, 4, 30)
    assert len(window) == 120
