"""The two-table SQLite migration cycle complements actual PostgreSQL E2E."""

import importlib

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError


def test_two_table_migration_cycle_and_append_only_guard():
    revision = importlib.import_module("backend.alembic.versions.0041_rolling_shadow_forecast")
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as db:
        context = MigrationContext.configure(db)
        for _ in range(2):
            with Operations.context(context):
                revision.upgrade()
            assert set(inspect(db).get_table_names()) == {
                "rolling_forecast_run",
                "rolling_forecast_daily",
            }
            db.execute(
                text("""INSERT INTO rolling_forecast_run
              (id,principal_id,context_reference,base_id,target_season,origin_date,
               origin_cutoff_at,input_hash,result_hash,status,snapshot,created_at)
              VALUES (1,'A','SYNTHETIC','SYNTHETIC','2026-2027','2026-11-05',
                      '2026-11-05','INPUT','RESULT','BLOCKED','{}','2026-11-05')""")
            )
            for sql in (
                "UPDATE rolling_forecast_run SET id=id",
                "DELETE FROM rolling_forecast_run",
            ):
                with pytest.raises(DBAPIError, match="immutable"):
                    db.execute(text(sql))
            with Operations.context(context):
                revision.downgrade()
            assert inspect(db).get_table_names() == []
