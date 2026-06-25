from __future__ import annotations

import io
import os
import zipfile
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import create_app
from backend.tests.harvest_state.conftest import make_request

pytestmark = pytest.mark.integration


def _require_postgres() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("set RUN_POSTGRES_INTEGRATION=1 when PostgreSQL is available")


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    _require_postgres()
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client:
        yield test_client


@pytest.mark.integration
async def test_harvest_state_api_compute_persist_load_completed(client: AsyncClient) -> None:
    response = await client.post("/api/v1/harvest-state/runs", json=make_request())
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"

    fetched = await client.get(f"/api/v1/harvest-state/runs/{payload['run_id']}")
    assert fetched.status_code == 200
    assert fetched.json() == payload


@pytest.mark.integration
async def test_harvest_state_api_compute_persist_load_blocked(client: AsyncClient) -> None:
    payload = make_request()
    payload["farm_timezone"] = "Bad/Timezone"

    response = await client.post("/api/v1/harvest-state/runs", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "blocked"


@pytest.mark.integration
async def test_harvest_state_idempotent_repeated_request(client: AsyncClient) -> None:
    first = await client.post("/api/v1/harvest-state/runs", json=make_request())
    second = await client.post("/api/v1/harvest-state/runs", json=make_request())

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["run_id"] == first.json()["run_id"]


@pytest.mark.integration
async def test_harvest_state_report_from_persisted_run(client: AsyncClient) -> None:
    created = await client.post("/api/v1/harvest-state/runs", json=make_request())
    run_id = created.json()["run_id"]

    report = await client.get(f"/api/v1/harvest-state/runs/{run_id}/report.csv")
    assert report.status_code == 200
    with zipfile.ZipFile(io.BytesIO(report.content)) as archive:
        assert "manifest.json" in archive.namelist()
