import importlib

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError


def test_sqlite_migration_up_down_up():
    module = importlib.import_module("backend.alembic.versions.0034_area_forecast_runs")
    assert module.down_revision == "0033_empirical_maturity_authority"
    engine = create_engine("sqlite://")
    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        module.upgrade()
        triggers = (
            conn.execute(text("SELECT name FROM sqlite_master WHERE type='trigger'"))
            .scalars()
            .all()
        )
        assert "area_forecast_run_update" in triggers and "area_daily_insert_guard" in triggers
        # A completed parent's legal slots cannot be extended.
        with pytest.raises(DBAPIError):
            conn.execute(
                text(
                    "INSERT INTO area_forecast_daily_row"
                    "(run_id,row_index,date,predicted_kg,share,share_text) "
                    "VALUES(999,0,'2026-01-01','1','1','1')"
                )
            )
        module.downgrade()
        assert (
            conn.execute(
                text("SELECT name FROM sqlite_master WHERE name='area_forecast_run'")
            ).first()
            is None
        )
        module.upgrade()
    engine.dispose()
