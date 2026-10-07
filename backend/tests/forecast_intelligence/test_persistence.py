"""Real SQLite migration, atomic writes, reload, source integrity and immutability."""

from copy import deepcopy

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from backend.app.forecast_intelligence.application import execute_hierarchical_run
from backend.app.forecast_intelligence.errors import HierarchicalForecastError
from backend.app.forecast_intelligence.persistence import HierarchicalRunRepository
from backend.app.forecast_intelligence.schemas import HierarchicalHistoryQuery
from backend.app.forecast_quality.operational_peak_persistence import OperationalPeakRunRepository
from backend.app.models.hierarchical_forecast import HierarchicalForecastRun
from backend.tests.forecast_intelligence.conftest import MIGRATION
from backend.tests.forecast_intelligence.test_reconciliation import request


async def test_complete_incomplete_reload_order_and_authority_independence(
    hierarchy_factory, source_ids, monkeypatch
):
    async with hierarchy_factory() as session, session.begin():
        source_repository = OperationalPeakRunRepository(session)
        before = [(await source_repository.get(i)).model_dump(mode="json") for i in source_ids]
        first = await execute_hierarchical_run(session, request(source_ids))
        repeated = await execute_hierarchical_run(session, request(list(reversed(source_ids))))
        assert repeated.reused_existing_run and first.run.run_id == repeated.run.run_id
        incomplete = await execute_hierarchical_run(session, request(source_ids[:-1]))
        assert incomplete.result["daily_forecast"] == []
        assert incomplete.result["status"] == "INCOMPLETE_CHILD_COVERAGE"
        assert before == [
            (await source_repository.get(i)).model_dump(mode="json") for i in source_ids
        ]
    monkeypatch.setattr(
        "backend.app.forecast_intelligence.application.current_hierarchy",
        lambda: (_ for _ in ()).throw(RuntimeError("unavailable")),
    )
    async with hierarchy_factory() as session:
        repository = HierarchicalRunRepository(session)
        assert (await repository.get(first.run.run_id)).model_dump() == first.model_dump()
        assert (await repository.get(incomplete.run.run_id)).result == incomplete.result
        history = await repository.history(HierarchicalHistoryQuery(limit=1))
        assert history.next_cursor and len(history.items) == 1
        page2 = await repository.history(
            HierarchicalHistoryQuery(limit=1, cursor=history.next_cursor)
        )
        assert page2.items[0].run_id == first.run.run_id
        assert len((await repository.daily(first.run.run_id)).daily_forecast) == 15
        with pytest.raises(HierarchicalForecastError, match="RUN_NOT_FOUND"):
            await repository.get(99999)


@pytest.mark.parametrize(
    "table",
    ["hierarchical_forecast_run", "hierarchical_forecast_daily", "hierarchical_forecast_source"],
)
@pytest.mark.parametrize("action", ["UPDATE", "DELETE"])
async def test_all_tables_immutable(hierarchy_factory, source_ids, table, action):
    async with hierarchy_factory() as session, session.begin():
        await execute_hierarchical_run(session, request(source_ids))
    async with hierarchy_factory() as session:
        sql = f"UPDATE {table} SET id=id" if action == "UPDATE" else f"DELETE FROM {table}"
        with pytest.raises(DBAPIError, match="immutable"):
            await session.execute(text(sql))
        await session.rollback()


@pytest.mark.parametrize("kind", ["daily", "parent", "source", "hierarchy", "source_daily"])
async def test_corruption_detected(hierarchy_factory, source_ids, kind):
    async with hierarchy_factory() as session, session.begin():
        saved = await execute_hierarchical_run(session, request(source_ids))
    # Deliberate offline corruption fixture, never an application escape hatch.
    async with hierarchy_factory() as session, session.begin():
        table = {
            "daily": "hierarchical_forecast_daily",
            "parent": "hierarchical_forecast_run",
            "source": "hierarchical_forecast_source",
            "hierarchy": "hierarchical_forecast_run",
            "source_daily": "operational_peak_forecast_daily",
        }[kind]
        await session.execute(text(f"DROP TRIGGER {table}_update"))
        if kind == "hierarchy":
            model = await session.get(HierarchicalForecastRun, saved.run.run_id)
            payload = deepcopy(model.hierarchy_snapshot)
            payload["company"]["entity_label"] = "corrupted"
            model.hierarchy_snapshot = payload
        else:
            assignment = {
                "daily": "predicted_kg='999'",
                "parent": "child_expected_count=5",
                "source": "source_result_hash='bad'",
                "source_daily": "predicted_kg='999'",
            }[kind]
            # Parent count mutation must also preserve DB status constraint to reach reload.
            if kind == "parent":
                assignment = "target_entity_label='corrupted'"
            await session.execute(text(f"UPDATE {table} SET {assignment}"))
    async with hierarchy_factory() as session:
        with pytest.raises(HierarchicalForecastError, match="PERSISTENCE_INTEGRITY_FAILED"):
            await HierarchicalRunRepository(session).get(saved.run.run_id)


async def test_reload_failure_rolls_back_entire_attempt(hierarchy_factory, source_ids, monkeypatch):
    async def broken(*args):
        raise HierarchicalForecastError("HIERARCHICAL_FORECAST_PERSISTENCE_INTEGRITY_FAILED", 500)

    monkeypatch.setattr(HierarchicalRunRepository, "get", broken)
    async with hierarchy_factory() as session, session.begin():
        with pytest.raises(HierarchicalForecastError):
            await execute_hierarchical_run(session, request(source_ids))
        assert await session.scalar(select(func.count()).select_from(HierarchicalForecastRun)) == 0


def test_empty_downgrade_upgrade_and_populated_refusal():
    from sqlalchemy import create_engine

    from backend.tests.forecast_intelligence.conftest import create_tables

    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        create_tables(connection)
        with Operations.context(MigrationContext.configure(connection)):
            MIGRATION.downgrade()
            MIGRATION.upgrade()
    engine.dispose()


async def test_populated_downgrade_refusal(hierarchy_factory, source_ids):
    async with hierarchy_factory() as session, session.begin():
        await execute_hierarchical_run(session, request(source_ids))
    async with hierarchy_factory.kw["bind"].begin() as connection:

        def downgrade(sync):
            with Operations.context(MigrationContext.configure(sync)):
                MIGRATION.downgrade()

        with pytest.raises(RuntimeError, match="HIERARCHICAL_FORECAST_DATA_PREVENTS_DOWNGRADE"):
            await connection.run_sync(downgrade)
