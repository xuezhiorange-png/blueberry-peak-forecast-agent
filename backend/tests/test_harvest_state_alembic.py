from pathlib import Path

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from backend.app.models.harvest_state import (
    HarvestStateCohortTransitionRowModel,
    HarvestStateDailyMemberRowModel,
    HarvestStateDailyPoolRowModel,
    HarvestStateFutureArrivalRowModel,
    HarvestStateRun,
)

# Slice 1 Batch 4 marker annotation: this file is owned by the
# `postgres-migration` shard per ci-shard-manifest.yml.
pytestmark = [pytest.mark.postgres, pytest.mark.migration]


def test_harvest_state_migration_metadata() -> None:
    revision_path = Path("backend/alembic/versions/0010_harvest_state_persistence.py")

    assert revision_path.exists()
    source = revision_path.read_text()
    assert 'revision: str = "0010_harvest_state_persistence"' in source
    assert 'down_revision: str | None = "0009_natural_maturity_curve"' in source
    assert "def upgrade() -> None:" in source


def test_harvest_state_migration_has_downgrade() -> None:
    revision_path = Path("backend/alembic/versions/0010_harvest_state_persistence.py")

    source = revision_path.read_text()
    assert "def downgrade() -> None:" in source


def test_task9_v2_forecast_season_migration_contract() -> None:
    revision_path = Path("backend/alembic/versions/0016_task9_forecast_season_identity.py")
    source = revision_path.read_text()

    assert 'revision: str = "0016_task9_forecast_season_identity"' in source
    assert 'down_revision: str | None = "0015_task11_phase3_schema_gap"' in source
    assert '"forecast_season_id", sa.BigInteger(), nullable=True' in source
    assert '"dim_season"' in source
    assert 'ondelete="RESTRICT"' in source
    assert '"ix_harvest_state_run_forecast_season_scope"' in source
    assert "task9a-result-hash-v2" in source
    assert "refuse to downgrade" in source
    assert "UPDATE harvest_state_run" not in source


def test_harvest_state_schema_contains_tables() -> None:
    schema_path = Path("sql/schema.sql")
    source = schema_path.read_text()

    for table_name in (
        "harvest_state_run",
        "harvest_state_daily_pool_row",
        "harvest_state_daily_member_row",
        "harvest_state_cohort_transition_row",
        "harvest_state_future_arrival_row",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table_name} (" in source


def test_harvest_state_postgres_constraint_names_fit_identifier_limit() -> None:
    tables = (
        HarvestStateRun.__table__,
        HarvestStateDailyPoolRowModel.__table__,
        HarvestStateDailyMemberRowModel.__table__,
        HarvestStateCohortTransitionRowModel.__table__,
        HarvestStateFutureArrivalRowModel.__table__,
    )

    for table in tables:
        for constraint in table.constraints:
            if constraint.name:
                assert len(constraint.name) <= 63, constraint.name
        CreateTable(table).compile(dialect=postgresql.dialect())


def test_task9_v2_forecast_season_orm_contract() -> None:
    column = HarvestStateRun.__table__.c.forecast_season_id
    assert column.nullable is True
    assert {foreign_key.target_fullname for foreign_key in column.foreign_keys} == {"dim_season.id"}
    assert {foreign_key.ondelete for foreign_key in column.foreign_keys} == {"RESTRICT"}
    index = next(
        item
        for item in HarvestStateRun.__table__.indexes
        if item.name == "ix_harvest_state_run_forecast_season_scope"
    )
    assert tuple(column.name for column in index.columns) == (
        "forecast_season_id",
        "status",
        "destination_factory_id",
        "as_of_date",
        "forecast_end_date",
    )
