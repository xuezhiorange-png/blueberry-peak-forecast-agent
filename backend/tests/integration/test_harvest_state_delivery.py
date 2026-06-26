from __future__ import annotations

import io
import os
import zipfile
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import AsyncSessionMaker
from backend.app.harvest_state.persistence import HarvestStatePersistenceIntegrityError
from backend.app.harvest_state.schemas import Task9ARequest
from backend.app.main import create_app
from backend.app.models.harvest_state import (
    HarvestStateCohortTransitionRowModel,
    HarvestStateDailyMemberRowModel,
    HarvestStateDailyPoolRowModel,
    HarvestStateFutureArrivalRowModel,
    HarvestStateRun,
)
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


def _request_json() -> dict[str, object]:
    return Task9ARequest.model_validate(make_request()).model_dump(mode="json")


@pytest.mark.integration
async def test_harvest_state_api_compute_persist_load_completed(client: AsyncClient) -> None:
    response = await client.post("/api/v1/harvest-state/runs", json=_request_json())
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"

    fetched = await client.get(f"/api/v1/harvest-state/runs/{payload['run_id']}")
    assert fetched.status_code == 200
    assert fetched.json() == payload


@pytest.mark.integration
async def test_harvest_state_api_compute_persist_load_blocked(client: AsyncClient) -> None:
    payload = _request_json()
    payload["farm_timezone"] = "Bad/Timezone"

    response = await client.post("/api/v1/harvest-state/runs", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "blocked"


@pytest.mark.integration
async def test_harvest_state_idempotent_repeated_request(client: AsyncClient) -> None:
    first = await client.post("/api/v1/harvest-state/runs", json=_request_json())
    second = await client.post("/api/v1/harvest-state/runs", json=_request_json())

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["run_id"] == first.json()["run_id"]


@pytest.mark.integration
async def test_harvest_state_report_from_persisted_run(client: AsyncClient) -> None:
    created = await client.post("/api/v1/harvest-state/runs", json=_request_json())
    run_id = created.json()["run_id"]

    report = await client.get(f"/api/v1/harvest-state/runs/{run_id}/report.csv")
    assert report.status_code == 200
    with zipfile.ZipFile(io.BytesIO(report.content)) as archive:
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
        manifest = archive.read("manifest.json").decode("utf-8")
        pool_csv = archive.read("daily_pool_state_rows.csv").decode("utf-8")
        assert '"report_schema_version":"task9c-harvest-state-csv-report-v1"' in manifest
        assert '["' in pool_csv
        assert "['" not in pool_csv


@pytest.mark.integration
async def test_postgres_get_run_by_result_hash(client: AsyncClient) -> None:
    created = await client.post("/api/v1/harvest-state/runs", json=_request_json())
    payload = created.json()

    fetched = await client.get(
        f"/api/v1/harvest-state/runs/by-result-hash/{payload['result_hash']}"
    )

    assert fetched.status_code == 200
    assert fetched.json() == payload


@pytest.mark.integration
async def test_postgres_api_output_matches_persisted_reload(client: AsyncClient) -> None:
    created = await client.post("/api/v1/harvest-state/runs", json=_request_json())
    payload = created.json()

    by_id = await client.get(f"/api/v1/harvest-state/runs/{payload['run_id']}")
    by_hash = await client.get(
        f"/api/v1/harvest-state/runs/by-result-hash/{payload['result_hash']}"
    )
    report = await client.get(f"/api/v1/harvest-state/runs/{payload['run_id']}/report.json")

    assert by_id.status_code == 200
    assert by_hash.status_code == 200
    assert report.status_code == 200
    assert by_id.json() == payload
    assert by_hash.json() == payload
    assert report.json()["output"] == payload["output"]


@pytest.mark.integration
async def test_postgres_repeated_request_reuses_same_run_and_children(
    client: AsyncClient,
) -> None:
    first = await client.post("/api/v1/harvest-state/runs", json=_request_json())
    second = await client.post("/api/v1/harvest-state/runs", json=_request_json())

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["run_id"] == first.json()["run_id"]

    async with AsyncSessionMaker() as session:
        assert await session.scalar(select(func.count()).select_from(HarvestStateRun)) == 1
        assert (
            await session.scalar(select(func.count()).select_from(HarvestStateDailyPoolRowModel))
            == 9
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(HarvestStateDailyMemberRowModel)
            )
            == 18
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(HarvestStateCohortTransitionRowModel)
            )
            == 24
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(HarvestStateFutureArrivalRowModel)
            )
            == 6
        )


@pytest.mark.integration
async def test_postgres_failed_save_rolls_back_run_and_children(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_commit = AsyncSession.commit
    state = {"raised": False}

    async def _failing_commit(self: AsyncSession) -> None:
        if not state["raised"]:
            state["raised"] = True
            raise HarvestStatePersistenceIntegrityError("forced commit failure")
        await original_commit(self)

    monkeypatch.setattr(AsyncSession, "commit", _failing_commit)

    response = await client.post("/api/v1/harvest-state/runs", json=_request_json())

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "HARVEST_STATE_DELIVERY_INTEGRITY_ERROR",
            "message": "Harvest-state delivery failed an integrity check.",
        }
    }

    async with AsyncSessionMaker() as session:
        assert await session.scalar(select(func.count()).select_from(HarvestStateRun)) == 0
        assert (
            await session.scalar(select(func.count()).select_from(HarvestStateDailyPoolRowModel))
            == 0
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(HarvestStateDailyMemberRowModel)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(HarvestStateCohortTransitionRowModel)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(HarvestStateFutureArrivalRowModel)
            )
            == 0
        )
