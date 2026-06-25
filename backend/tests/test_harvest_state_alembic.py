from pathlib import Path

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from backend.app.models.harvest_state import (
    HarvestStateCohortTransitionRowModel,
    HarvestStateDailyMemberRowModel,
    HarvestStateDailyPoolRowModel,
    HarvestStateFutureArrivalRowModel,
    HarvestStateRun,
)


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
