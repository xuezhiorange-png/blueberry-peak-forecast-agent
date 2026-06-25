from __future__ import annotations

import io
import zipfile
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import get_db_session
from backend.app.harvest_state.schemas import Task9ARequest
from backend.app.main import create_app
from backend.tests.harvest_state.conftest import make_request


@pytest.fixture
async def harvest_state_client(sqlite_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def _override() -> AsyncIterator[AsyncSession]:
        yield sqlite_session

    app.dependency_overrides[get_db_session] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


def _request_json() -> dict[str, object]:
    return Task9ARequest.model_validate(make_request()).model_dump(mode="json")


@pytest.mark.asyncio
async def test_post_completed_run(harvest_state_client: AsyncClient) -> None:
    response = await harvest_state_client.post(
        "/api/v1/harvest-state/runs",
        json=_request_json(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["output"]["status"] == "completed"


@pytest.mark.asyncio
async def test_post_blocked_run(harvest_state_client: AsyncClient) -> None:
    payload = _request_json()
    payload["farm_timezone"] = "Bad/Timezone"

    response = await harvest_state_client.post("/api/v1/harvest-state/runs", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "blocked"
    assert body["output"]["blockers"] == ["INVALID_TIMEZONE"]


@pytest.mark.asyncio
async def test_post_repeated_request_returns_same_run_id(harvest_state_client: AsyncClient) -> None:
    first = await harvest_state_client.post("/api/v1/harvest-state/runs", json=_request_json())
    second = await harvest_state_client.post("/api/v1/harvest-state/runs", json=_request_json())

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["run_id"] == first.json()["run_id"]


@pytest.mark.asyncio
async def test_get_run_by_id_and_hash(harvest_state_client: AsyncClient) -> None:
    created = await harvest_state_client.post("/api/v1/harvest-state/runs", json=_request_json())
    run_id = created.json()["run_id"]
    result_hash = created.json()["result_hash"]

    by_id = await harvest_state_client.get(f"/api/v1/harvest-state/runs/{run_id}")
    by_hash = await harvest_state_client.get(
        f"/api/v1/harvest-state/runs/by-result-hash/{result_hash}"
    )

    assert by_id.status_code == 200
    assert by_hash.status_code == 200
    assert by_id.json() == created.json()
    assert by_hash.json() == created.json()


@pytest.mark.asyncio
async def test_get_missing_run_returns_404(harvest_state_client: AsyncClient) -> None:
    response = await harvest_state_client.get("/api/v1/harvest-state/runs/999")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "HARVEST_STATE_RUN_NOT_FOUND",
            "message": "Harvest-state run was not found.",
        }
    }


@pytest.mark.asyncio
async def test_invalid_result_hash_returns_422(harvest_state_client: AsyncClient) -> None:
    response = await harvest_state_client.get(
        "/api/v1/harvest-state/runs/by-result-hash/not-a-hash"
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_invalid_request_returns_422(harvest_state_client: AsyncClient) -> None:
    payload = _request_json()
    del payload["destination_factory_id"]

    response = await harvest_state_client.post("/api/v1/harvest-state/runs", json=payload)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_json_and_csv_reports(harvest_state_client: AsyncClient) -> None:
    created = await harvest_state_client.post("/api/v1/harvest-state/runs", json=_request_json())
    run_id = created.json()["run_id"]

    json_report = await harvest_state_client.get(f"/api/v1/harvest-state/runs/{run_id}/report.json")
    csv_report = await harvest_state_client.get(f"/api/v1/harvest-state/runs/{run_id}/report.csv")

    assert json_report.status_code == 200
    assert json_report.headers["content-type"].startswith("application/json")
    assert csv_report.status_code == 200
    assert csv_report.headers["content-type"].startswith("application/zip")

    with zipfile.ZipFile(io.BytesIO(csv_report.content)) as archive:
        assert archive.namelist() == [
            "manifest.json",
            "run.csv",
            "daily_pool_state_rows.csv",
            "daily_member_state_rows.csv",
            "cohort_transition_rows.csv",
            "future_arrival_schedule.csv",
            "source_ref_catalog.json",
            "warnings.csv",
            "blockers.csv",
        ]


def test_openapi_registers_harvest_state_routes() -> None:
    app = create_app()
    schema = app.openapi()

    assert "/api/v1/harvest-state/runs" in schema["paths"]
    assert "/api/v1/harvest-state/runs/{run_id}" in schema["paths"]
    assert "/api/v1/harvest-state/runs/by-result-hash/{result_hash}" in schema["paths"]
