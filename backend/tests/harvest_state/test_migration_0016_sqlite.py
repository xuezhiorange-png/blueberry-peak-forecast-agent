from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration_module() -> ModuleType:
    path = Path("backend/alembic/versions/0016_task9_forecast_season_identity.py")
    spec = importlib.util.spec_from_file_location("task9_migration_0016", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _database() -> sa.Engine:
    engine = sa.create_engine("sqlite:///:memory:")
    metadata = sa.MetaData()
    sa.Table(
        "dim_season",
        metadata,
        sa.Column("id", sa.BigInteger(), primary_key=True),
    )
    sa.Table(
        "harvest_state_run",
        metadata,
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("result_hash_schema_version", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("destination_factory_id", sa.BigInteger(), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("forecast_end_date", sa.Date(), nullable=False),
    )
    metadata.create_all(engine)
    return engine


def _operations(connection: sa.Connection) -> Operations:
    return Operations(MigrationContext.configure(connection))


def test_sqlite_upgrade_and_safe_downgrade() -> None:
    module = _migration_module()
    engine = _database()
    with engine.begin() as connection:
        module.op = _operations(connection)
        module.upgrade()
        inspector = sa.inspect(connection)
        assert "forecast_season_id" in {
            column["name"] for column in inspector.get_columns("harvest_state_run")
        }
        assert "ix_harvest_state_run_forecast_season_scope" in {
            index["name"] for index in inspector.get_indexes("harvest_state_run")
        }
        module.downgrade()
        inspector = sa.inspect(connection)
        assert "forecast_season_id" not in {
            column["name"] for column in inspector.get_columns("harvest_state_run")
        }


def test_sqlite_downgrade_refuses_v2_authority_data() -> None:
    module = _migration_module()
    engine = _database()
    with engine.begin() as connection:
        module.op = _operations(connection)
        module.upgrade()
        connection.execute(
            sa.text(
                "INSERT INTO harvest_state_run "
                "(id, result_hash_schema_version, status, destination_factory_id, "
                "as_of_date, forecast_end_date, forecast_season_id) "
                "VALUES (1, 'task9a-result-hash-v2', 'blocked', 1, "
                "'2026-01-01', '2026-01-02', 123)"
            )
        )
        with pytest.raises(RuntimeError, match="refuse to downgrade"):
            module.downgrade()
