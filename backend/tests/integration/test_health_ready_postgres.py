"""Slice 2 migrated representative test.

This test originally lived in
``backend/tests/integration/test_health_ready_postgres.py`` and
asserted the ``/health/ready`` HTTP endpoint contract. The original
test is preserved as ``test_health_ready_uses_real_postgresql_connection``.

This file ADDS one new test,
``test_health_ready_under_transactional_isolation``, that exercises
the same endpoint under the new ``transactional_pg_session`` opt-in
fixture. The new test performs a minimal direct-database round-trip
(insert into a tiny lookup table, read it back) before issuing the
HTTP request, so the fixture is exercised end-to-end.

The original test is NOT modified in this slice; the migration is
implemented by ADDING a sibling test rather than rewriting the
existing one, so reviewers can diff the change in isolation. The
``pytest.mark.skipif`` gate is preserved on both tests.
"""

import os

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from backend.app.main import create_app

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
    reason="set RUN_POSTGRES_INTEGRATION=1 when PostgreSQL is available",
)
@pytest.mark.asyncio
async def test_health_ready_uses_real_postgresql_connection() -> None:
    """Original representative test (unchanged)."""
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"


@pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
    reason="set RUN_POSTGRES_INTEGRATION=1 when PostgreSQL is available",
)
@pytest.mark.asyncio
async def test_health_ready_under_transactional_isolation(
    transactional_pg_session,
) -> None:
    """Slice 2 representative migration.

    Exercises the new ``transactional_pg_session`` opt-in fixture
    alongside the original ``/health/ready`` HTTP contract. The
    direct-database round-trip (insert into ``dim_season``) runs
    inside the fixture's outer transaction; the fixture rolls the
    outer transaction back at teardown so the row never escapes to
    the shared PG database.
    """
    app = create_app()

    # Direct-DB round-trip under the new fixture.
    probe_code = "S2-HEALTH-READY-PROBE"
    await transactional_pg_session.execute(
        text(
            "INSERT INTO dim_season (season_code, display_name) "
            "VALUES (:code, :name) "
            "ON CONFLICT (season_code) DO NOTHING"
        ),
        {"code": probe_code, "name": "slice2 health probe"},
    )
    result = await transactional_pg_session.execute(
        text("SELECT display_name FROM dim_season WHERE season_code = :code"),
        {"code": probe_code},
    )
    assert result.scalar_one() == "slice2 health probe"

    # Original HTTP contract still asserted.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
