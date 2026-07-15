from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.app.rolling_backtest.canonical import canonical_json_dumps

FIXTURE_DIR = Path(__file__).parents[1] / "fixtures" / "v0_1_complete_season_case_01"
QUANTILES = ("P50", "P80", "P90")
DECIMAL_KEYS = {
    "planting_area_mu",
    "expected_yield_kg_per_mu",
    "marketable_rate",
    "expected_total_marketable_kg",
    "tree_age_years",
    "sorting_retention_rate",
    "postharvest_retention_rate",
    "planned_picker_count",
    "picker_productivity_kg_per_day",
    "labor_availability_ratio",
    "operational_efficiency_ratio",
    "weather_efficiency_ratio",
}


def _load(name: str) -> Any:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _decimal(value: str) -> Decimal:
    parsed = Decimal(value)
    assert parsed.is_finite()
    return parsed


def _walk_no_float(value: Any) -> None:
    if isinstance(value, float):
        raise AssertionError("fixture contains a native float")
    if isinstance(value, dict):
        for item in value.values():
            _walk_no_float(item)
    elif isinstance(value, list):
        for item in value:
            _walk_no_float(item)


def _assert_decimal_strings(value: Any, key: str | None = None) -> None:
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            _assert_decimal_strings(child_value, child_key)
    elif isinstance(value, list):
        for item in value:
            _assert_decimal_strings(item, key)
    elif key in DECIMAL_KEYS or (
        key is not None and (key.endswith("_kg") or key.endswith("_rate"))
    ):
        assert isinstance(value, str), f"{key} must be a Decimal string"
        assert _decimal(value) >= 0


def test_fixture_has_complete_calendar_and_frozen_scope() -> None:
    manifest = _load("manifest.json")
    expected = _load("expected_daily.json")["rows"]
    start = date.fromisoformat(manifest["date_range"]["start"])
    end = date.fromisoformat(manifest["date_range"]["end"])
    dates = sorted({date.fromisoformat(row["date"]) for row in expected})
    assert len(dates) == 90
    assert dates == [start + timedelta(days=i) for i in range(90)]
    assert start == date(2026, 3, 1)
    assert end == date(2026, 5, 29)
    assert manifest["scope"] == {
        "farm_count": 1,
        "subfarm_count": 2,
        "variety_count": 2,
        "destination_factory_count": 1,
        "quantiles": list(QUANTILES),
    }
    assert len(expected) == 90 * 2 * 2 * 3
    assert {row["farm_id"] for row in expected} == {101}
    assert {row["subfarm_id"] for row in expected} == {1101, 1102}
    assert {row["variety_id"] for row in expected} == {2101, 2102}
    assert {row["destination_factory_id"] for row in expected} == {9101}
    assert {row["forecast_quantile"] for row in expected} == set(QUANTILES)


def test_expected_rows_are_deterministically_sorted_and_have_all_fields() -> None:
    rows = _load("expected_daily.json")["rows"]
    quantile_rank = {quantile: index for index, quantile in enumerate(QUANTILES)}
    actual_keys = [
        (
            row["date"],
            row["farm_id"],
            row["subfarm_id"],
            row["variety_id"],
            quantile_rank[row["forecast_quantile"]],
        )
        for row in rows
    ]
    assert actual_keys == sorted(actual_keys)
    required = {
        "date",
        "forecast_quantile",
        "farm_id",
        "subfarm_id",
        "variety_id",
        "destination_factory_id",
        "natural_maturity_supply_kg",
        "opening_mature_inventory_kg",
        "available_mature_quantity_kg",
        "mature_inventory_loss_quantity_kg",
        "harvestable_mature_quantity_kg",
        "effective_harvest_capacity_kg",
        "model_harvested_marketable_quantity_kg",
        "closing_mature_inventory_kg",
        "unharvested_backlog_kg",
        "sorting_retention_rate",
        "postharvest_retention_rate",
        "effective_marketable_quantity_kg",
        "task8_forecast_run_id",
        "task9_harvest_state_run_id",
        "task8_artifact_hash",
        "task9_result_hash",
        "marketable_policy_version",
        "marketable_policy_hash",
        "row_hash",
    }
    assert all(set(row) == required for row in rows)
    assert all("marketable_rate" not in row for row in rows)


def test_fixture_uses_decimal_strings_and_no_non_finite_values() -> None:
    payloads = [
        _load(name)
        for name in (
            "input.json",
            "expected_daily.json",
            "expected_metrics.json",
            "rerun_input.json",
        )
    ]
    for payload in payloads:
        _walk_no_float(payload)
        _assert_decimal_strings(payload)
    expected = _load("expected_daily.json")["rows"]
    assert any(row["effective_marketable_quantity_kg"] == "0.000000" for row in expected)
    assert any(Decimal(row["sorting_retention_rate"]) < Decimal("1") for row in expected)
    for row in expected:
        for field in (
            "natural_maturity_supply_kg",
            "opening_mature_inventory_kg",
            "available_mature_quantity_kg",
            "mature_inventory_loss_quantity_kg",
            "harvestable_mature_quantity_kg",
            "effective_harvest_capacity_kg",
            "model_harvested_marketable_quantity_kg",
            "closing_mature_inventory_kg",
            "unharvested_backlog_kg",
            "effective_marketable_quantity_kg",
        ):
            assert _decimal(row[field]) >= 0


def test_mass_balance_and_marketable_retention_are_conserved() -> None:
    rows = _load("expected_daily.json")["rows"]
    for row in rows:
        opening = _decimal(row["opening_mature_inventory_kg"])
        natural = _decimal(row["natural_maturity_supply_kg"])
        loss = _decimal(row["mature_inventory_loss_quantity_kg"])
        harvested = _decimal(row["model_harvested_marketable_quantity_kg"])
        closing = _decimal(row["closing_mature_inventory_kg"])
        available = _decimal(row["available_mature_quantity_kg"])
        assert opening + natural == available
        assert opening + natural == loss + harvested + closing
        effective = _decimal(row["effective_marketable_quantity_kg"])
        expected_effective = (
            harvested
            * _decimal(row["sorting_retention_rate"])
            * _decimal(row["postharvest_retention_rate"])
        ).quantize(Decimal("0.000001"))
        assert effective == expected_effective


def test_seven_day_peak_is_independently_rolling_cumulative_with_earliest_tie_break() -> None:
    rows = _load("expected_daily.json")["rows"]
    metrics = _load("expected_metrics.json")["metrics"]
    for quantile in QUANTILES:
        aggregate: dict[date, Decimal] = {}
        for row in rows:
            if row["forecast_quantile"] == quantile:
                day = date.fromisoformat(row["date"])
                aggregate[day] = aggregate.get(day, Decimal("0")) + _decimal(
                    row["effective_marketable_quantity_kg"]
                )
        dates = sorted(aggregate)
        windows = [
            (
                dates[index],
                sum(
                    (aggregate[dates[index + offset]] for offset in range(7)),
                    Decimal("0"),
                ),
            )
            for index in range(len(dates) - 6)
            if all(
                dates[index + offset] == dates[index] + timedelta(days=offset)
                for offset in range(7)
            )
        ]
        best_total = max(total for _, total in windows)
        best_starts = [start for start, total in windows if total == best_total]
        expected = metrics[quantile]["sustained_7day_peak"]
        assert expected["window_days"] == 7
        assert expected["metric"] == "ROLLING_CUMULATIVE"
        assert expected["date_continuity"] == "STRICT_CALENDAR_DAYS"
        assert expected["tie_break"] == "EARLIEST_START_DATE"
        assert date.fromisoformat(expected["start_date"]) == min(best_starts)
        assert date.fromisoformat(expected["end_date"]) == min(best_starts) + timedelta(days=6)
        assert _decimal(expected["cumulative_quantity_kg"]) == best_total
        assert len(metrics[quantile]["tied_windows"]) >= 2
        assert metrics[quantile]["tied_windows"][0]["start_date"] == min(
            item["start_date"] for item in metrics[quantile]["tied_windows"]
        )


def test_single_day_and_season_cumulative_metrics_are_recomputed() -> None:
    rows = _load("expected_daily.json")["rows"]
    metrics = _load("expected_metrics.json")["metrics"]
    for quantile in QUANTILES:
        by_date: dict[date, Decimal] = {}
        for row in rows:
            if row["forecast_quantile"] == quantile:
                day = date.fromisoformat(row["date"])
                by_date[day] = by_date.get(day, Decimal("0")) + _decimal(
                    row["effective_marketable_quantity_kg"]
                )
        peak = max(by_date.values())
        assert _decimal(metrics[quantile]["single_day_peak"]["quantity_kg"]) == peak
        assert (
            metrics[quantile]["single_day_peak"]["date"]
            == min(day for day, value in by_date.items() if value == peak).isoformat()
        )
        assert _decimal(metrics[quantile]["season_cumulative_effective_marketable_kg"]) == sum(
            by_date.values(), Decimal("0")
        )


def test_fixture_events_and_one_parameter_rerun_are_explicit() -> None:
    input_payload = _load("input.json")
    rows = input_payload["daily_inputs"]
    assert any("CAPACITY_DIP" in row["event_tags"] for row in rows)
    assert any("BACKLOG_BUILD" in row["event_tags"] for row in rows)
    assert any("CAPACITY_RECOVERY" in row["event_tags"] for row in rows)
    assert any(_decimal(row["mature_inventory_loss_quantity_kg"]) > 0 for row in rows)
    rerun = _load("rerun_input.json")["single_parameter_adjustment"]
    assert set(rerun) == {"parameter", "scope", "dates", "from", "to"}
    assert rerun["parameter"] == "labor_availability_ratio"
    assert rerun["from"] != rerun["to"]


def test_fixture_checksums_match_canonical_json() -> None:
    checksums = _load("checksums.json")["files"]
    for filename, expected_hash in checksums.items():
        payload = _load(filename)
        actual_hash = hashlib.sha256(canonical_json_dumps(payload).encode("utf-8")).hexdigest()
        assert actual_hash == expected_hash, filename
