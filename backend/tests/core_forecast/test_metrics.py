from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path

import pytest

from backend.app.core_forecast.canonical import (
    DAILY_CURVE_SCHEMA_VERSION,
    METRICS_SCHEMA_VERSION,
    compute_daily_curve_hash,
)
from backend.app.core_forecast.metrics import compute_core_forecast_metrics
from backend.app.core_forecast.schemas import (
    QUANTILES,
    CompleteCoreForecastMetricsResult,
    CompleteDailyMarketableCurveResult,
    CompleteDailyMarketableCurveRow,
    CoreForecastBlocker,
)
from backend.app.rolling_backtest.canonical import canonical_json_dumps

FIXTURE_DIR = Path("backend/tests/fixtures/v0_1_complete_season_case_01")
EXPECTED_ROWS = json.loads((FIXTURE_DIR / "expected_daily.json").read_text(encoding="utf-8"))[
    "rows"
]
EXPECTED_METRICS = json.loads((FIXTURE_DIR / "expected_metrics.json").read_text(encoding="utf-8"))[
    "metrics"
]


def _curve(
    rows: tuple[CompleteDailyMarketableCurveRow, ...] | None = None,
) -> CompleteDailyMarketableCurveResult:
    raw_rows = EXPECTED_ROWS if rows is None else rows
    models = tuple(
        row
        if isinstance(row, CompleteDailyMarketableCurveRow)
        else CompleteDailyMarketableCurveRow(**row)
        for row in raw_rows
    )
    try:
        curve_hash = compute_daily_curve_hash(models)
    except (TypeError, ValueError):
        # Keep malformed model_construct() rows inside the service boundary.
        curve_hash = "0" * 64
    return CompleteDailyMarketableCurveResult(
        status="COMPLETED",
        rows=models,
        curve_hash=curve_hash,
        blockers=(),
    )


def _metric_fields(metric) -> dict[str, object]:
    return {
        "single_day_peak": metric.single_day_peak.model_dump(mode="json"),
        "sustained_7day_peak": metric.sustained_7day_peak.model_dump(mode="json"),
        "season_cumulative_effective_marketable_kg": (
            metric.season_cumulative_effective_marketable_kg
        ),
    }


def _row_with(row: dict[str, object], **updates: object) -> CompleteDailyMarketableCurveRow:
    payload = {key: value for key, value in row.items() if key != "row_hash"}
    payload.update(updates)
    row_hash = hashlib.sha256(canonical_json_dumps(payload).encode("utf-8")).hexdigest()
    return CompleteDailyMarketableCurveRow(**payload, row_hash=row_hash)


def _effective_totals(curve: CompleteDailyMarketableCurveResult) -> dict[tuple[date, str], Decimal]:
    totals: dict[tuple[date, str], Decimal] = {}
    for row in curve.rows:
        key = (row.date, row.forecast_quantile)
        totals[key] = totals.get(key, Decimal("0")) + Decimal(row.effective_marketable_quantity_kg)
    return totals


def _assert_blocked(result: CompleteCoreForecastMetricsResult, code: str) -> None:
    assert result.status == "BLOCKED"
    assert result.metrics == ()
    assert result.metrics_schema_version is None
    assert result.date_basis is None
    assert result.source_curve_hash is None
    assert result.metrics_hash is None
    assert result.blockers
    assert result.blockers[0].code == code


@pytest.mark.unit
@pytest.mark.contract
@pytest.mark.golden
def test_complete_season_fixture_metrics_match_expected_oracle_exactly() -> None:
    result = compute_core_forecast_metrics(daily_curve=_curve())
    assert result.status == "COMPLETED"
    assert result.metrics_schema_version == METRICS_SCHEMA_VERSION
    assert result.date_basis == "HARVEST_BUSINESS_DATE"
    actual = {metric.forecast_quantile: _metric_fields(metric) for metric in result.metrics}
    expected = {
        quantile: {
            "single_day_peak": oracle["single_day_peak"],
            "sustained_7day_peak": oracle["sustained_7day_peak"],
            "season_cumulative_effective_marketable_kg": oracle[
                "season_cumulative_effective_marketable_kg"
            ],
        }
        for quantile, oracle in EXPECTED_METRICS.items()
    }
    assert actual == expected


@pytest.mark.unit
def test_single_day_peak_uses_effective_marketable_quantity() -> None:
    result = compute_core_forecast_metrics(daily_curve=_curve())
    p50 = result.metrics[0]
    assert p50.single_day_peak.date == date(2026, 3, 18)
    assert p50.single_day_peak.quantity_kg == "97.577520"
    assert p50.single_day_peak.tie_break == "EARLIEST_DATE"


@pytest.mark.unit
def test_single_day_equal_maxima_select_earliest_date() -> None:
    rows = []
    for raw_row in EXPECTED_ROWS:
        if raw_row["forecast_quantile"] == "P50":
            current_date = date.fromisoformat(raw_row["date"])
            quantity = (
                "10.000000" if current_date in {date(2026, 3, 2), date(2026, 3, 5)} else "1.000000"
            )
            rows.append(_row_with(raw_row, effective_marketable_quantity_kg=quantity))
        else:
            rows.append(CompleteDailyMarketableCurveRow(**raw_row))
    result = compute_core_forecast_metrics(daily_curve=_curve(tuple(rows)))
    assert result.status == "COMPLETED"
    assert result.metrics[0].single_day_peak.date == date(2026, 3, 2)


@pytest.mark.unit
def test_seven_day_peak_uses_rolling_cumulative_not_average() -> None:
    result = compute_core_forecast_metrics(daily_curve=_curve())
    peak = result.metrics[0].sustained_7day_peak
    assert peak.metric == "ROLLING_CUMULATIVE"
    assert peak.cumulative_quantity_kg == "585.465120"
    assert peak.daily_average_kg_per_day == "83.637874"


@pytest.mark.unit
def test_seven_day_window_requires_strict_consecutive_calendar_dates() -> None:
    rows = [row for row in EXPECTED_ROWS if row["date"] != "2026-03-04"]
    result = compute_core_forecast_metrics(
        daily_curve=_curve(tuple(CompleteDailyMarketableCurveRow(**row) for row in rows))
    )
    _assert_blocked(result, "DAILY_CURVE_INCOMPLETE_SERIES")


@pytest.mark.unit
def test_equal_seven_day_windows_select_earliest_start() -> None:
    result = compute_core_forecast_metrics(daily_curve=_curve())
    for metric in result.metrics:
        peak = metric.sustained_7day_peak
        assert peak.start_date == date(2026, 3, 15)
        assert peak.end_date == date(2026, 3, 21)


@pytest.mark.unit
def test_seven_day_daily_average_is_derived_from_selected_cumulative() -> None:
    result = compute_core_forecast_metrics(daily_curve=_curve())
    for metric in result.metrics:
        peak = metric.sustained_7day_peak
        expected = (Decimal(peak.cumulative_quantity_kg) / Decimal("7")).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_EVEN
        )
        assert peak.daily_average_kg_per_day == format(expected, "f")


@pytest.mark.unit
def test_seven_day_daily_average_uses_round_half_even_at_scale_six() -> None:
    cumulative = Decimal("585.465120")
    expected = (cumulative / Decimal("7")).quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)
    result = compute_core_forecast_metrics(daily_curve=_curve())
    assert result.metrics[0].sustained_7day_peak.daily_average_kg_per_day == format(expected, "f")


@pytest.mark.unit
def test_incomplete_tail_fragment_is_ignored() -> None:
    rows = [row for row in EXPECTED_ROWS if row["date"] <= "2026-05-28"]
    result = compute_core_forecast_metrics(
        daily_curve=_curve(tuple(CompleteDailyMarketableCurveRow(**row) for row in rows))
    )
    assert result.status == "COMPLETED"
    assert result.metrics[0].sustained_7day_peak.end_date == date(2026, 3, 21)


@pytest.mark.unit
def test_complete_range_shorter_than_seven_days_blocks() -> None:
    rows = [row for row in EXPECTED_ROWS if row["date"] <= "2026-03-06"]
    result = compute_core_forecast_metrics(
        daily_curve=_curve(tuple(CompleteDailyMarketableCurveRow(**row) for row in rows))
    )
    _assert_blocked(result, "NO_COMPLETE_7DAY_WINDOW")


@pytest.mark.unit
def test_calendar_gap_blocks_complete_metrics() -> None:
    rows = [row for row in EXPECTED_ROWS if row["date"] not in {"2026-04-01"}]
    result = compute_core_forecast_metrics(
        daily_curve=_curve(tuple(CompleteDailyMarketableCurveRow(**row) for row in rows))
    )
    _assert_blocked(result, "DAILY_CURVE_INCOMPLETE_SERIES")


@pytest.mark.unit
def test_quantiles_are_computed_independently() -> None:
    result = compute_core_forecast_metrics(daily_curve=_curve())
    assert tuple(metric.forecast_quantile for metric in result.metrics) == QUANTILES
    assert [metric.single_day_peak.quantity_kg for metric in result.metrics] == [
        "97.577520",
        "117.093024",
        "136.608528",
    ]


@pytest.mark.unit
def test_all_scopes_are_aggregated_by_date_and_quantile() -> None:
    result = compute_core_forecast_metrics(daily_curve=_curve())
    totals = _effective_totals(_curve())
    assert len({key[0] for key in totals}) == 90
    assert all(len([key for key in totals if key[1] == quantile]) == 90 for quantile in QUANTILES)
    assert result.metrics[0].single_day_peak.quantity_kg == format(
        max(total for (current_date, quantile), total in totals.items() if quantile == "P50"),
        "f",
    )


@pytest.mark.unit
def test_season_cumulative_includes_every_date() -> None:
    result = compute_core_forecast_metrics(daily_curve=_curve())
    totals = _effective_totals(_curve())
    expected = sum(
        (total for (current_date, quantile), total in totals.items() if quantile == "P50"),
        Decimal("0"),
    )
    assert result.metrics[0].season_cumulative_effective_marketable_kg == format(expected, "f")


@pytest.mark.unit
def test_metrics_order_is_p50_p80_p90() -> None:
    result = compute_core_forecast_metrics(daily_curve=_curve())
    assert tuple(metric.forecast_quantile for metric in result.metrics) == ("P50", "P80", "P90")


@pytest.mark.unit
def test_same_input_produces_same_metrics_hash() -> None:
    first = compute_core_forecast_metrics(daily_curve=_curve())
    second = compute_core_forecast_metrics(daily_curve=_curve())
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


@pytest.mark.unit
def test_input_row_order_does_not_change_metrics_or_hash() -> None:
    curve = _curve()
    shuffled = _curve(tuple(reversed(tuple(curve.rows))))
    first = compute_core_forecast_metrics(daily_curve=curve)
    second = compute_core_forecast_metrics(daily_curve=shuffled)
    assert second.status == "COMPLETED"
    assert second.model_dump(mode="json") == first.model_dump(mode="json")


@pytest.mark.unit
def test_row_hash_tampering_blocks() -> None:
    rows = list(EXPECTED_ROWS)
    rows[0] = {**rows[0], "effective_marketable_quantity_kg": "999.000000"}
    tampered = tuple(CompleteDailyMarketableCurveRow.model_construct(**row) for row in rows)
    result = compute_core_forecast_metrics(daily_curve=_curve(tampered))
    _assert_blocked(result, "DAILY_CURVE_ROW_HASH_MISMATCH")


@pytest.mark.unit
def test_curve_hash_tampering_blocks() -> None:
    curve = _curve()
    tampered = CompleteDailyMarketableCurveResult(
        status="COMPLETED",
        rows=curve.rows,
        curve_hash="a" * 64,
        blockers=(),
    )
    result = compute_core_forecast_metrics(daily_curve=tampered)
    _assert_blocked(result, "DAILY_CURVE_HASH_MISMATCH")


@pytest.mark.unit
def test_native_float_quantity_blocks() -> None:
    row = CompleteDailyMarketableCurveRow.model_construct(
        **{**EXPECTED_ROWS[0], "effective_marketable_quantity_kg": 1.25}
    )
    result = compute_core_forecast_metrics(daily_curve=_curve((row,)))
    _assert_blocked(result, "DAILY_CURVE_DECIMAL_INVALID")


@pytest.mark.unit
def test_non_finite_quantity_blocks() -> None:
    row = CompleteDailyMarketableCurveRow.model_construct(
        **{**EXPECTED_ROWS[0], "effective_marketable_quantity_kg": "NaN"}
    )
    result = compute_core_forecast_metrics(daily_curve=_curve((row,)))
    _assert_blocked(result, "DAILY_CURVE_DECIMAL_INVALID")


@pytest.mark.unit
def test_negative_zero_quantity_blocks() -> None:
    row = CompleteDailyMarketableCurveRow.model_construct(
        **{**EXPECTED_ROWS[0], "effective_marketable_quantity_kg": "-0.000000"}
    )
    result = compute_core_forecast_metrics(daily_curve=_curve((row,)))
    _assert_blocked(result, "DAILY_CURVE_DECIMAL_INVALID")


@pytest.mark.unit
def test_duplicate_business_key_blocks() -> None:
    curve = _curve()
    rows = curve.rows + (curve.rows[0],)
    tampered = CompleteDailyMarketableCurveResult(
        status="COMPLETED",
        rows=rows,
        curve_hash=compute_daily_curve_hash(rows),
        blockers=(),
    )
    result = compute_core_forecast_metrics(daily_curve=tampered)
    _assert_blocked(result, "DAILY_CURVE_DUPLICATE_KEY")


@pytest.mark.unit
def test_missing_quantile_blocks() -> None:
    rows = tuple(row for row in EXPECTED_ROWS if row["forecast_quantile"] != "P90")
    result = compute_core_forecast_metrics(
        daily_curve=_curve(tuple(CompleteDailyMarketableCurveRow(**row) for row in rows))
    )
    _assert_blocked(result, "DAILY_CURVE_INCOMPLETE_SERIES")


@pytest.mark.unit
def test_mismatched_scope_set_blocks() -> None:
    rows = [
        row
        for row in EXPECTED_ROWS
        if not (
            row["date"] == "2026-03-01"
            and row["forecast_quantile"] == "P80"
            and row["subfarm_id"] == 1102
            and row["variety_id"] == 2102
        )
    ]
    result = compute_core_forecast_metrics(
        daily_curve=_curve(tuple(CompleteDailyMarketableCurveRow(**row) for row in rows))
    )
    _assert_blocked(result, "DAILY_CURVE_INCOMPLETE_SERIES")


@pytest.mark.unit
def test_blocked_daily_curve_returns_blocked_metrics() -> None:
    daily_curve = CompleteDailyMarketableCurveResult(
        status="BLOCKED",
        rows=(),
        curve_hash=None,
        blockers=(
            CoreForecastBlocker(
                code="TASK8_AUTHORITY_NOT_FOUND",
                message="Task 8 forecast authority was not found",
            ),
        ),
    )
    result = compute_core_forecast_metrics(daily_curve=daily_curve)
    _assert_blocked(result, "DAILY_CURVE_NOT_COMPLETED")


@pytest.mark.unit
def test_no_failure_returns_partial_quantile_metrics() -> None:
    row = CompleteDailyMarketableCurveRow.model_construct(
        **{**EXPECTED_ROWS[0], "effective_marketable_quantity_kg": "NaN"}
    )
    result = compute_core_forecast_metrics(daily_curve=_curve((row,)))
    assert result.metrics == ()
    assert result.metrics_hash is None
    assert result.source_curve_hash is None


@pytest.mark.unit
def test_s2_curve_hash_helper_uses_frozen_schema_version() -> None:
    curve = _curve()
    assert curve.curve_hash == compute_daily_curve_hash(curve.rows)
    payload = {
        "schema_version": DAILY_CURVE_SCHEMA_VERSION,
        "rows": [row.model_dump(mode="json") for row in curve.rows],
    }
    expected = hashlib.sha256(canonical_json_dumps(payload).encode("utf-8")).hexdigest()
    assert curve.curve_hash == expected
