"""SQLite migration round trip for the S6 tables and immutable guards."""

import importlib

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text


def test_operational_peak_migration_upgrade_downgrade_upgrade():
    previous = importlib.import_module("backend.alembic.versions.0034_area_forecast_runs")
    current = importlib.import_module(
        "backend.alembic.versions.0035_operational_peak_forecast_runs"
    )
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            previous.upgrade()
            current.upgrade()
        tables = {
            row[0]
            for row in connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        }
        assert {
            "operational_peak_forecast_run",
            "operational_peak_forecast_daily",
        } <= tables
        with Operations.context(MigrationContext.configure(connection)):
            current.downgrade()
            current.upgrade()
    engine.dispose()
