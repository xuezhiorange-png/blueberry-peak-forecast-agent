"""The shared V1 arithmetic must preserve the fixed pre-S7 historical bytes."""

import subprocess
import types
from datetime import timedelta
from decimal import Decimal

import pytest

from backend.app.area_yield import v015_harvest_state as current
from backend.app.area_yield.formal_multi_season_validation import business_boundary
from backend.app.rolling_forecast.harvest_state import window_values

HISTORICAL_MAIN = "82682ac364e492b8cd29cd80014002c991238f42"


@pytest.mark.parametrize("season", ["2023-2024", "2024-2025", "2025-2026"])
@pytest.mark.parametrize("missing", [False, True])
def test_shared_arithmetic_preserves_original_historical_row_bytes(season, missing):
    old = types.ModuleType("s7_frozen_v015_comparator")
    raw = subprocess.check_output(
        ["git", "show", HISTORICAL_MAIN + ":backend/app/area_yield/v015_harvest_state.py"]
    )
    exec(compile(raw, "fixed-historical-v015.py", "exec"), old.__dict__)
    start = business_boundary(season).start
    days = [
        {
            "base_id": "SYNTHETIC",
            "season": season,
            "date": str(start + timedelta(days=i)),
            "record_state": "VALID_OBSERVED",
            "quantity_kg": str(i),
            "logical_record_id": str(i),
            "source_hashes": ["a" * 64],
            "conflict_status": ["NONE"],
        }
        for i in range(50)
    ]
    if missing:
        days.pop(5)
    row = {
        "base_id": "SYNTHETIC",
        "season": season,
        "row_key": "SYNTHETIC",
        "forecast_origin": str(start + timedelta(days=35)) + "T17:00:00+08:00",
        "split": current.SPLITS[season],
    }
    expected = old.build_row(row, old.history_index(days))
    assert current.build_row(row, current.history_index(days)) == expected
    prior = {start + timedelta(days=i): Decimal(i) for i in range(35)}
    if missing:
        prior.pop(start + timedelta(days=5))
    vector, audit, reasons = window_values(prior, start, start + timedelta(days=35))
    assert vector == expected["harvest_state_v1"]
    assert audit == expected["audit"]
    assert reasons <= set(expected["exclusion_reasons"])
