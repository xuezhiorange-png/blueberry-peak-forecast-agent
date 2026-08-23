"""S3-A daily rowset completeness verifier contract tests."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from backend.app.s2_materialized_dataset.lane_d.partitions import TEST_START
from backend.app.s2_materialized_dataset.shared.contracts import MaterializableRow
from backend.app.s3_daily_rowset.actuals import InMemoryS2ActualsSource
from backend.app.s3_daily_rowset.completeness import (
    COMPLETENESS_PREDICATE_IDS,
    CompletenessPredicateId,
    CompletenessVerifier,
    PredicateStatus,
)
from backend.app.s3_daily_rowset.forecast_port import (
    FakeIncumbentDailyCurveProvider,
    SparseHorizonBindingForecastProvider,
)
from backend.app.s3_daily_rowset.schemas import (
    DailyRow,
    DailyRowsetResult,
    DailyRowStatus,
    DatasetIdentity,
    DatasetIdentityMismatchError,
    EvaluationInstanceCell,
    HorizonWindowRequest,
    MaterializationOutcome,
    ReasonCode,
    WindowKind,
)
from backend.app.s3_daily_rowset.service import DailyRowsetMaterializerService
from backend.tests.s3_daily_rowset.conftest import (
    DATASET_IDENTITY,
    HORIZON_H7_SUCCESS_FIXTURE_HASH,
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
    forecast_provider: FakeIncumbentDailyCurveProvider
    | SparseHorizonBindingForecastProvider
    | None = None,
) -> DailyRowsetMaterializerService:
    if forecast_provider is None:
        if forecasts is None and not forecast_unavailable:
            forecasts = {row.harvest_business_date: Decimal("1.0") for row in rows}
        forecast_provider = FakeIncumbentDailyCurveProvider(
            forecasts=forecasts,
            unavailable=forecast_unavailable,
        )
    return DailyRowsetMaterializerService(
        dataset_identity=dataset_identity,
        actuals_source=InMemoryS2ActualsSource(rows, day_exclusions=day_exclusions),
        forecast_provider=forecast_provider,
    )


def _request(cutoff: datetime, *, horizon_days: int = 7) -> HorizonWindowRequest:
    cutoff_date = cutoff.astimezone(__import__("zoneinfo").ZoneInfo("Asia/Shanghai")).date()
    return HorizonWindowRequest(
        evaluation_window_days=horizon_days,
        forecast_target_date=cutoff_date.fromordinal(cutoff_date.toordinal() + horizon_days),
    )


def _materialize(service: DailyRowsetMaterializerService, cutoff: datetime):
    cell = make_cell(forecast_cutoff_at=cutoff)
    return service.materialize_horizon_window(cell, _request(cutoff))


def _predicate_statuses(result) -> dict[CompletenessPredicateId, PredicateStatus]:
    return {item.predicate_id: item.status for item in result.predicates}


def test_h7_success_window_all_predicates_pass_dataset_flag_stays_false(
    materializer: DailyRowsetMaterializerService,
    cell: EvaluationInstanceCell,
    horizon_request: HorizonWindowRequest,
) -> None:
    rowset = materializer.materialize_horizon_window(cell, horizon_request)
    assert rowset.outcome == MaterializationOutcome.SUCCESS
    assert rowset.rowset_identity_sha256 == HORIZON_H7_SUCCESS_FIXTURE_HASH

    verification = CompletenessVerifier().verify_window(rowset)
    assert verification.window_predicates_all_pass is True
    assert all(item.status == PredicateStatus.PASS for item in verification.predicates)
    assert set(_predicate_statuses(verification)) == set(COMPLETENESS_PREDICATE_IDS)
    assert verification.dataset_completeness_verified is False
    assert verification.current_s3_daily_rowset_completeness_verified is False
    assert verification.evaluation_instance_registry_available is False


def test_unknown_day_fails_completeness_predicates() -> None:
    cutoff = datetime(2026, 2, 28, 16, 0, tzinfo=UTC)
    dates = horizon_dates(cutoff, 7)
    rows = tuple(
        make_row(harvest_business_date=day, quantity="2.0") for day in dates if day != dates[3]
    )
    service = _service(rows)
    rowset = _materialize(service, cutoff)
    verification = CompletenessVerifier().verify_window(rowset)
    assert verification.window_predicates_all_pass is False
    assert verification.dataset_completeness_verified is False


def test_excluded_day_fails_completeness_predicates() -> None:
    cutoff = datetime(2026, 2, 28, 16, 0, tzinfo=UTC)
    dates = horizon_dates(cutoff, 7)
    rows = tuple(make_row(harvest_business_date=day, quantity="3.0") for day in dates)
    service = _service(rows, day_exclusions=frozenset({dates[2]}))
    rowset = _materialize(service, cutoff)
    verification = CompletenessVerifier().verify_window(rowset)
    assert verification.window_predicates_all_pass is False
    assert verification.dataset_completeness_verified is False


def test_forecast_unavailable_fails_completeness_predicates() -> None:
    cutoff = datetime(2026, 2, 28, 16, 0, tzinfo=UTC)
    dates = horizon_dates(cutoff, 7)
    rows = tuple(make_row(harvest_business_date=day, quantity="4.0") for day in dates)
    service = _service(rows, forecast_unavailable=True)
    rowset = _materialize(service, cutoff)
    verification = CompletenessVerifier().verify_window(rowset)
    assert verification.window_predicates_all_pass is False
    statuses = _predicate_statuses(verification)
    forecast_id = CompletenessPredicateId.FORECAST_DAILY_CURVE_VISIBLE_AT_CUTOFF
    assert statuses[forecast_id] == PredicateStatus.FAIL
    assert verification.dataset_completeness_verified is False


def test_sparse_horizon_binding_fails_completeness_predicates() -> None:
    cutoff = datetime(2026, 2, 28, 16, 0, tzinfo=UTC)
    dates = horizon_dates(cutoff, 7)
    rows = tuple(make_row(harvest_business_date=day, quantity="1.0") for day in dates)
    service = _service(rows, forecast_provider=SparseHorizonBindingForecastProvider())
    rowset = _materialize(service, cutoff)
    verification = CompletenessVerifier().verify_window(rowset)
    assert rowset.reason_code == ReasonCode.FORECAST_UNAVAILABLE
    assert verification.window_predicates_all_pass is False
    assert verification.dataset_completeness_verified is False


def test_test_partition_horizon_fails_completeness_predicates() -> None:
    cutoff = datetime(2026, 3, 9, 16, 0, tzinfo=UTC)
    rows = (make_row(harvest_business_date=TEST_START, quantity="5.0"),)
    service = _service(rows)
    rowset = _materialize(service, cutoff)
    verification = CompletenessVerifier().verify_window(rowset)
    assert rowset.reason_code == ReasonCode.TEST_PARTITION_NOT_ALLOWED
    assert verification.window_predicates_all_pass is False
    assert verification.dataset_completeness_verified is False


def test_complete_season_intersecting_test_partition_fails_predicates() -> None:
    rows = (
        make_row(harvest_business_date=date(2026, 1, 15), quantity="1.0"),
        make_row(harvest_business_date=date(2026, 2, 10), quantity="1.0"),
    )
    service = _service(
        rows,
        forecasts={date(2026, 1, 15): Decimal("1.0"), date(2026, 2, 10): Decimal("1.0")},
    )
    rowset = service.materialize_complete_season_window(make_cell())
    verification = CompletenessVerifier().verify_window(rowset)
    assert rowset.reason_code == ReasonCode.TEST_PARTITION_NOT_ALLOWED
    assert verification.window_predicates_all_pass is False
    assert verification.dataset_completeness_verified is False


@pytest.mark.parametrize(
    ("variety", "farm"),
    [
        ("普鲜", "farm-a"),
        ("variety-x", "巴松加工厂"),
    ],
)
def test_cell_level_excluded_fails_completeness_predicates(variety: str, farm: str) -> None:
    cutoff = datetime(2026, 2, 28, 16, 0, tzinfo=UTC)
    dates = horizon_dates(cutoff, 7)
    rows = tuple(
        make_row(harvest_business_date=day, quantity="1.0", variety=variety, farm=farm)
        for day in dates
    )
    service = _service(rows)
    rowset = service.materialize_horizon_window(
        make_cell(forecast_cutoff_at=cutoff, variety=variety, farm=farm),
        _request(cutoff),
    )
    verification = CompletenessVerifier().verify_window(rowset)
    assert rowset.outcome == MaterializationOutcome.CELL_EXCLUDED
    assert verification.window_predicates_all_pass is False
    assert verification.dataset_completeness_verified is False


def test_dataset_identity_mismatch_blocks_materializer() -> None:
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


def test_missing_rowset_identity_hash_fails_traceability_predicate() -> None:
    cutoff = datetime(2026, 2, 28, 16, 0, tzinfo=UTC)
    dates = horizon_dates(cutoff, 7)
    tampered = DailyRowsetResult(
        outcome=MaterializationOutcome.SUCCESS,
        window_kind=WindowKind.HORIZON,
        evaluation_window_days=7,
        window_start_date=dates[0],
        window_end_date=dates[-1],
        daily_rows=tuple(
            DailyRow(
                business_date=day,
                daily_row_status=DailyRowStatus.OBSERVED,
                actual_harvest_quantity_kg=Decimal("1.0"),
                forecast_harvest_quantity_kg=Decimal("1.0"),
            )
            for day in dates
        ),
        rowset_identity_sha256=None,
    )
    verification = CompletenessVerifier().verify_window(tampered)
    statuses = _predicate_statuses(verification)
    trace_id = CompletenessPredicateId.OBSERVED_KG_TRACEABLE_TO_SOURCE_002_GRAIN
    assert statuses[trace_id] == PredicateStatus.FAIL
    assert verification.dataset_completeness_verified is False


def test_tampered_success_with_unknown_row_fails_predicates_two_and_three() -> None:
    cutoff = datetime(2026, 2, 28, 16, 0, tzinfo=UTC)
    dates = horizon_dates(cutoff, 7)
    daily_rows = []
    for index, day in enumerate(dates):
        if index == 3:
            daily_rows.append(
                DailyRow(
                    business_date=day,
                    daily_row_status=DailyRowStatus.UNKNOWN,
                    actual_harvest_quantity_kg=None,
                    forecast_harvest_quantity_kg=Decimal("1.0"),
                )
            )
        else:
            daily_rows.append(
                DailyRow(
                    business_date=day,
                    daily_row_status=DailyRowStatus.OBSERVED,
                    actual_harvest_quantity_kg=Decimal("1.0"),
                    forecast_harvest_quantity_kg=Decimal("1.0"),
                )
            )
    tampered = DailyRowsetResult(
        outcome=MaterializationOutcome.SUCCESS,
        window_kind=WindowKind.HORIZON,
        evaluation_window_days=7,
        window_start_date=dates[0],
        window_end_date=dates[-1],
        daily_rows=tuple(daily_rows),
        rowset_identity_sha256=HORIZON_H7_SUCCESS_FIXTURE_HASH,
    )
    verification = CompletenessVerifier().verify_window(tampered)
    statuses = _predicate_statuses(verification)
    assert statuses[CompletenessPredicateId.NO_SILENT_MISSING_DAYS] == PredicateStatus.FAIL
    assert statuses[CompletenessPredicateId.NO_ZERO_FILL_FOR_UNKNOWN] == PredicateStatus.FAIL
    assert verification.window_predicates_all_pass is False
    assert verification.dataset_completeness_verified is False
    assert verification.current_s3_daily_rowset_completeness_verified is False
