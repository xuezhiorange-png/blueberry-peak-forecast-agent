from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

from backend.tests.actual_harvest_import.alembic_cases import (
    assert_actual_harvest_alembic_head_and_revision_contract,
    assert_actual_harvest_migration_architecture_contract,
    assert_actual_harvest_sqlite_upgrade_downgrade_upgrade,
)

MIGRATION_PATH = Path("backend/alembic/versions/0017_core_forecast_run_persistence.py")
MIGRATION_REVISION = "0017_core_forecast_run_persistence"

pytestmark = [pytest.mark.postgres, pytest.mark.migration]


def _migration_module():
    spec = importlib.util.spec_from_file_location("core_forecast_s4_migration", MIGRATION_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("S4 migration module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_alembic_head_and_revision_contract() -> None:
    migration = _migration_module()
    assert migration.revision == MIGRATION_REVISION
    assert migration.down_revision == "0016_task9_forecast_season_identity"
    assert not (MIGRATION_PATH.read_text(encoding="utf-8").find("actual_harvest") >= 0)


def test_sqlite_upgrade_downgrade_upgrade_creates_only_s4_tables() -> None:
    migration = _migration_module()
    engine = create_engine("sqlite:///:memory:")

    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration.upgrade()
        inspector = inspect(connection)
        assert set(inspector.get_table_names()) == {
            "core_forecast_run",
            "core_forecast_daily_row",
            "core_forecast_metric",
        }
        assert {index["name"] for index in inspector.get_indexes("core_forecast_daily_row")} == {
            "ix_core_forecast_daily_row_run_date",
            "ix_core_forecast_daily_row_run_quantile_date",
        }
        assert {index["name"] for index in inspector.get_indexes("core_forecast_metric")} == {
            "ix_core_forecast_metric_run_id"
        }

        with Operations.context(context):
            migration.downgrade()
        assert inspect(connection).get_table_names() == []

        with Operations.context(context):
            migration.upgrade()
        assert set(inspect(connection).get_table_names()) == {
            "core_forecast_run",
            "core_forecast_daily_row",
            "core_forecast_metric",
        }


def test_s4_tables_have_required_constraints_and_foreign_keys() -> None:
    migration = _migration_module()
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration.upgrade()
        inspector = inspect(connection)

        run_constraints = {
            constraint["name"]
            for constraint in inspector.get_check_constraints("core_forecast_run")
        }
        assert "ck_core_forecast_run_completed_only" in run_constraints
        assert "ck_core_forecast_run_metric_count_three" in run_constraints

        daily_constraints = {
            constraint["name"]
            for constraint in inspector.get_check_constraints("core_forecast_daily_row")
        }
        assert "ck_core_forecast_daily_row_quantile" in daily_constraints
        assert "ck_core_forecast_daily_row_quantities_nonnegative" in daily_constraints

        metric_constraints = {
            constraint["name"]
            for constraint in inspector.get_check_constraints("core_forecast_metric")
        }
        assert "ck_core_forecast_metric_window_days" in metric_constraints

        run_fks = inspector.get_foreign_keys("core_forecast_run")
        assert {foreign_key["name"] for foreign_key in run_fks} >= {
            "fk_core_forecast_run_season",
            "fk_core_forecast_run_task8",
            "fk_core_forecast_run_task9",
            "fk_core_forecast_run_rerun_parent",
        }
        for foreign_key in run_fks:
            if foreign_key["name"] in {
                "fk_core_forecast_run_season",
                "fk_core_forecast_run_task8",
                "fk_core_forecast_run_task9",
                "fk_core_forecast_run_rerun_parent",
            }:
                assert foreign_key["options"]["ondelete"] == "RESTRICT"


def test_actual_harvest_alembic_head_and_revision_contract() -> None:
    assert_actual_harvest_alembic_head_and_revision_contract()


def test_actual_harvest_sqlite_upgrade_downgrade_upgrade() -> None:
    assert_actual_harvest_sqlite_upgrade_downgrade_upgrade()


def test_actual_harvest_migration_architecture_contract() -> None:
    assert_actual_harvest_migration_architecture_contract()
