"""Lineage scope is mandatory even on the idempotent early-return path."""

import io
import json

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, update

from backend.app.area_yield.run_application import execute_area_forecast_run
from backend.app.area_yield.run_persistence import (
    AreaForecastPersistenceConflictError,
    AreaForecastPersistenceIntegrityError,
    AreaForecastRunNotFoundError,
    AreaForecastRunRepository,
)
from backend.app.cli import run_cli
from backend.app.db.session import get_db_session
from backend.app.main import create_app
from backend.app.models.area_forecast import AreaForecastRun
from backend.tests.area_yield.test_run_persistence import authority, bounded  # noqa: F401
from backend.tests.area_yield.test_run_persistence import session as session
from backend.tests.area_yield.test_run_transport import factory as factory

pytestmark = pytest.mark.usefixtures("authority")


@pytest.mark.parametrize(
    "changes",
    [
        {"farm": "other"},
        {
            "target_season": "2027-2028",
            "season_start": "2027-10-15",
            "season_end": "2028-05-09",
        },
        {"season_start": "2026-10-20"},
        {"season_end": "2027-05-08"},
    ],
)
async def test_scope_mismatch_rejected(session, changes):
    parent = await execute_area_forecast_run(session, bounded())
    with pytest.raises(AreaForecastPersistenceConflictError) as err:
        await execute_area_forecast_run(
            session, bounded(**changes), rerun_of_run_id=parent.run.run_id
        )
    assert err.value.code == "AREA_FORECAST_RERUN_SCOPE_MISMATCH"
    assert await session.scalar(select(func.count()).select_from(AreaForecastRun)) == 1


async def test_unrelated_parent_before_existing_return(session):
    a = await execute_area_forecast_run(session, bounded())
    b = await execute_area_forecast_run(session, bounded(farm="other"))
    with pytest.raises(AreaForecastPersistenceConflictError) as err:
        await execute_area_forecast_run(session, bounded(), rerun_of_run_id=b.run.run_id)
    assert err.value.code == "AREA_FORECAST_RERUN_SCOPE_MISMATCH"
    with pytest.raises(AreaForecastRunNotFoundError):
        await execute_area_forecast_run(session, bounded(), rerun_of_run_id=999999)
    assert (await AreaForecastRunRepository(session).get(a.run.run_id)).result == a.result


async def test_alias_and_as_of_change_allowed(session):
    a = await execute_area_forecast_run(session, bounded(as_of="2026-09-12"))
    b = await execute_area_forecast_run(
        session, bounded(farm="alias", as_of="2026-09-13"), rerun_of_run_id=a.run.run_id
    )
    assert b.run.rerun_of_run_id == a.run.run_id
    assert b.result.canonical_farm == a.result.canonical_farm


async def test_corrupt_parent_rejected_before_reuse(session):
    a = await execute_area_forecast_run(session, bounded())
    await session.execute(
        update(AreaForecastRun).where(AreaForecastRun.id == a.run.run_id).values(result_hash="bad")
    )
    with pytest.raises(AreaForecastPersistenceIntegrityError):
        await execute_area_forecast_run(session, bounded(), rerun_of_run_id=a.run.run_id)


async def test_default_window_resolves_to_same_scope(session):
    a = await execute_area_forecast_run(session, bounded(season_start=None, season_end=None))
    b = await execute_area_forecast_run(
        session,
        bounded(season_start=a.result.season_start, season_end=a.result.season_end),
        rerun_of_run_id=a.run.run_id,
    )
    assert b.run.rerun_of_run_id == a.run.run_id


async def test_tampered_parent_scope_reload(session):
    unrelated = await execute_area_forecast_run(session, bounded(farm="other"))
    parent = await execute_area_forecast_run(session, bounded())
    child = await execute_area_forecast_run(
        session, bounded(productive_area_mu="500"), rerun_of_run_id=parent.run.run_id
    )
    await session.execute(
        update(AreaForecastRun)
        .where(AreaForecastRun.id == child.run.run_id)
        .values(rerun_of_run_id=unrelated.run.run_id)
    )
    with pytest.raises(AreaForecastPersistenceIntegrityError):
        await AreaForecastRunRepository(session).get(child.run.run_id)


async def test_http_cli_scope_conflict_code(factory):
    async with factory() as s, s.begin():
        a = await execute_area_forecast_run(s, bounded())
        b = await execute_area_forecast_run(s, bounded(farm="other"))
    body = {**bounded().model_dump(mode="json"), "rerun_of_run_id": b.run.run_id}
    app = create_app()

    async def sessions():
        async with factory() as s:
            yield s

    app.dependency_overrides[get_db_session] = sessions
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://local") as c:
        response = await c.post("/api/v1/area-forecast-runs", json=body)
    assert response.status_code == 409
    assert response.json()["code"] == "AREA_FORECAST_RERUN_SCOPE_MISMATCH"
    out, err = io.StringIO(), io.StringIO()
    assert (
        run_cli(
            ["area-forecast-run", "create", "--input", "-"],
            session_factory=factory,
            stdin=io.StringIO(json.dumps(body)),
            stdout=out,
            stderr=err,
        )
        != 0
    )
    assert "AREA_FORECAST_RERUN_SCOPE_MISMATCH" in err.getvalue()
    assert not out.getvalue()
    async with factory() as s:
        assert (await AreaForecastRunRepository(s).get(a.run.run_id)).result == a.result
