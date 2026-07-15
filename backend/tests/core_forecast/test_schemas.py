from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.core_forecast.schemas import CompleteDailyMarketableCurveRow

FIXTURE_DIR = Path("backend/tests/fixtures/v0_1_complete_season_case_01")
ROW = json.loads((FIXTURE_DIR / "expected_daily.json").read_text(encoding="utf-8"))["rows"][0]


def _reject(field: str, value: object) -> None:
    payload = dict(ROW)
    payload[field] = value
    with pytest.raises(ValidationError):
        CompleteDailyMarketableCurveRow(**payload)


def test_row_accepts_exact_six_decimal_strings() -> None:
    row = CompleteDailyMarketableCurveRow(**ROW)
    assert row.natural_maturity_supply_kg == ROW["natural_maturity_supply_kg"]


def test_row_rejects_integer_lexical_quantity() -> None:
    _reject("natural_maturity_supply_kg", "1")


def test_row_rejects_short_scale_quantity() -> None:
    _reject("natural_maturity_supply_kg", "1.000")


def test_row_rejects_long_scale_quantity() -> None:
    _reject("natural_maturity_supply_kg", "1.0000000")


def test_row_rejects_scientific_notation() -> None:
    _reject("natural_maturity_supply_kg", "1e0")


def test_row_rejects_negative_zero() -> None:
    _reject("natural_maturity_supply_kg", "-0.000000")


def test_row_rejects_native_float() -> None:
    _reject("natural_maturity_supply_kg", 1.0)


def test_row_rejects_non_finite_string() -> None:
    _reject("natural_maturity_supply_kg", "NaN")
