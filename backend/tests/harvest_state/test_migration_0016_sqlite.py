from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from backend.app.harvest_state.canonical import canonical_json_dumps, sha256_hex


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
        sa.Column("canonical_output", sa.JSON(), nullable=True),
        sa.Column("result_hash", sa.Text(), nullable=True),
        sa.Column("canonical_payload_hash", sa.Text(), nullable=True),
    )
    sa.Table(
        "harvest_state_daily_pool_row",
        metadata,
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("harvest_state_run_id", sa.BigInteger(), nullable=False),
        sa.Column("row_payload", sa.JSON(), nullable=False),
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


def test_sqlite_migration_round_trip_preserves_completed_v1_bytes_and_rows() -> None:
    module = _migration_module()
    engine = _database()
    golden_path = Path("backend/tests/harvest_state/golden/task9a_completed_v1_canonical.json")
    payload = json.loads(golden_path.read_text())
    canonical = canonical_json_dumps(payload)
    payload_hash = sha256_hex(payload)

    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO harvest_state_run "
                "(id, result_hash_schema_version, status, destination_factory_id, "
                "as_of_date, forecast_end_date, canonical_output, result_hash, "
                "canonical_payload_hash) VALUES "
                "(1, 'task9a-result-hash-v1', 'completed', 701, '2026-02-28', "
                "'2026-03-01', :canonical_output, :result_hash, :payload_hash)"
            ),
            {
                "canonical_output": canonical,
                "result_hash": payload["result_hash"],
                "payload_hash": payload_hash,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO harvest_state_daily_pool_row "
                "(id, harvest_state_run_id, row_payload) VALUES (1, 1, :row_payload)"
            ),
            {"row_payload": canonical_json_dumps(payload["daily_pool_state_rows"][0])},
        )

        module.op = _operations(connection)
        module.upgrade()
        upgraded = (
            connection.execute(
                sa.text(
                    "SELECT forecast_season_id, canonical_output, result_hash, "
                    "canonical_payload_hash FROM harvest_state_run WHERE id = 1"
                )
            )
            .mappings()
            .one()
        )
        assert upgraded["forecast_season_id"] is None
        assert canonical_json_dumps(json.loads(upgraded["canonical_output"])) == canonical
        assert upgraded["result_hash"] == payload["result_hash"]
        assert upgraded["canonical_payload_hash"] == payload_hash
        assert connection.scalar(sa.text("SELECT count(*) FROM harvest_state_daily_pool_row")) == 1

        module.downgrade()
        downgraded = (
            connection.execute(
                sa.text(
                    "SELECT canonical_output, result_hash, canonical_payload_hash "
                    "FROM harvest_state_run WHERE id = 1"
                )
            )
            .mappings()
            .one()
        )
        assert canonical_json_dumps(json.loads(downgraded["canonical_output"])) == canonical
        assert downgraded["result_hash"] == payload["result_hash"]
        assert downgraded["canonical_payload_hash"] == payload_hash
        assert connection.scalar(sa.text("SELECT count(*) FROM harvest_state_daily_pool_row")) == 1
