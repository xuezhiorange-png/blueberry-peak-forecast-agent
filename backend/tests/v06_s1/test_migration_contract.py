from __future__ import annotations

import importlib

import pytest

MIGRATION = importlib.import_module("backend.alembic.versions.0036_v06_pit_data_foundation")


@pytest.mark.migration
def test_v06_s1_migration_is_the_single_next_revision() -> None:
    assert MIGRATION.revision == "0036_v06_pit_data_foundation"
    assert MIGRATION.down_revision == "0035_operational_peak_forecast_runs"
    assert MIGRATION.branch_labels is None
    assert MIGRATION.depends_on is None


@pytest.mark.migration
def test_v06_s1_migration_declares_immutable_pit_tables() -> None:
    assert MIGRATION._IMMUTABLE_TABLES == (
        "area_revision",
        "weather_forecast_snapshot",
        "realized_weather_observation",
        "phenology_observation",
        "forecast_run_snapshot",
        "forecast_run_snapshot_daily",
    )
