from __future__ import annotations

import importlib

import pytest

FOUNDATION_MIGRATION = importlib.import_module(
    "backend.alembic.versions.0036_v06_pit_data_foundation"
)
MIGRATION = importlib.import_module("backend.alembic.versions.0037_v06_pit_scope_time_integrity")


@pytest.mark.migration
def test_v06_s1_scope_time_migration_is_the_single_next_revision() -> None:
    assert MIGRATION.revision == "0037_v06_pit_scope_time_integrity"
    assert MIGRATION.down_revision == "0036_v06_pit_data_foundation"
    assert MIGRATION.branch_labels is None
    assert MIGRATION.depends_on is None


@pytest.mark.migration
def test_v06_s1_foundation_migration_declares_immutable_pit_tables() -> None:
    assert FOUNDATION_MIGRATION._IMMUTABLE_TABLES == (
        "area_revision",
        "weather_forecast_snapshot",
        "realized_weather_observation",
        "phenology_observation",
        "forecast_run_snapshot",
        "forecast_run_snapshot_daily",
    )


@pytest.mark.migration
def test_v06_s1_scope_time_migration_declares_timestamp_constraints() -> None:
    assert MIGRATION._CHECK_CONSTRAINTS == (
        ("area_revision", "ck_area_revision_recorded_known", "recorded_at <= known_at"),
        (
            "weather_forecast_snapshot",
            "ck_weather_forecast_issued_fetched",
            "issued_at <= fetched_at",
        ),
        (
            "weather_forecast_snapshot",
            "ck_weather_forecast_fetched_known",
            "fetched_at <= known_at",
        ),
        (
            "realized_weather_observation",
            "ck_realized_weather_observation_known",
            "observation_time <= known_at",
        ),
        (
            "realized_weather_observation",
            "ck_realized_weather_recorded_known",
            "recorded_at <= known_at",
        ),
        ("phenology_observation", "ck_phenology_observed_known", "observed_at <= known_at"),
        ("phenology_observation", "ck_phenology_recorded_known", "recorded_at <= known_at"),
        (
            "forecast_run_snapshot",
            "ck_forecast_snapshot_created_order",
            "forecast_created_at <= created_at",
        ),
    )
