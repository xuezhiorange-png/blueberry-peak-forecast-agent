from __future__ import annotations

import io
import json
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.cli import run_cli
from backend.app.db.session import get_db_session
from backend.app.harvest_state.application import execute_harvest_state_run
from backend.app.harvest_state.schemas import Task9ARequest
from backend.app.main import create_app
from backend.tests.harvest_state.conftest import make_request


@pytest.fixture
async def parity_client(sqlite_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def _override() -> AsyncIterator[AsyncSession]:
        yield sqlite_session

    app.dependency_overrides[get_db_session] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


def _session_factory(sqlite_session: AsyncSession) -> async_sessionmaker[AsyncSession]:
    assert sqlite_session.bind is not None
    return async_sessionmaker(sqlite_session.bind, expire_on_commit=False, class_=AsyncSession)


def _request_json() -> dict[str, object]:
    return Task9ARequest.model_validate(make_request()).model_dump(mode="json")


@pytest.mark.asyncio
async def test_application_api_cli_outputs_are_canonically_equal(
    sqlite_session: AsyncSession,
    parity_client: AsyncClient,
) -> None:
    request = make_request()
    application = await execute_harvest_state_run(sqlite_session, request=request)

    api_response = await parity_client.post("/api/v1/harvest-state/runs", json=_request_json())
    assert api_response.status_code == 200

    cli_stdout = io.StringIO()
    cli_code = run_cli(
        ["harvest-state", "run", "--input", "-"],
        session_factory=_session_factory(sqlite_session),
        stdout=cli_stdout,
        stderr=io.StringIO(),
        stdin=io.StringIO(json.dumps(_request_json())),
    )
    assert cli_code == 0

    api_payload = api_response.json()
    cli_payload = json.loads(cli_stdout.getvalue())
    app_payload = application.model_dump(mode="json")
    assert api_payload == app_payload
    assert cli_payload == app_payload


@pytest.mark.asyncio
async def test_api_and_cli_reuse_same_persisted_run(
    sqlite_session: AsyncSession,
    parity_client: AsyncClient,
) -> None:
    request_json = _request_json()
    created = await parity_client.post("/api/v1/harvest-state/runs", json=request_json)
    assert created.status_code == 200
    run_id = created.json()["run_id"]

    cli_stdout = io.StringIO()
    cli_code = run_cli(
        ["harvest-state", "run", "--input", "-"],
        session_factory=_session_factory(sqlite_session),
        stdout=cli_stdout,
        stderr=io.StringIO(),
        stdin=io.StringIO(json.dumps(request_json)),
    )
    assert cli_code == 0
    assert json.loads(cli_stdout.getvalue())["run_id"] == run_id
