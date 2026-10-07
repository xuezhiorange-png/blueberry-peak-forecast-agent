"""HTTP/CLI/MCP parity and privacy over the same synthetic saved sources."""

import io
import json

import pytest
from httpx import ASGITransport, AsyncClient
from mcp.types import CallToolRequestParams

from backend.app.cli import run_cli
from backend.app.db.session import get_db_session
from backend.app.main import create_app
from backend.app.mcp import area_forecast, hierarchical_forecast_runs
from backend.tests.forecast_intelligence.test_reconciliation import request


def _app(factory):
    app = create_app()

    async def sessions():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = sessions
    return app


@pytest.fixture
def actor(monkeypatch):
    monkeypatch.setenv("TRIAL_ACTOR_IDENTITY", "s1-synthetic")
    monkeypatch.setenv("TRIAL_ACTOR_ALLOWED_SOURCE_SYSTEMS", "trial-api")
    monkeypatch.setenv("TRIAL_ACTOR_ALLOWED_CHANNELS", "api")
    monkeypatch.setenv("TRIAL_ACTOR_PERMISSIONS", "may_create_forecast,may_read_forecast")


async def test_api_complete_incomplete_history_discovery(hierarchy_factory, source_ids, actor):
    async with AsyncClient(
        transport=ASGITransport(app=_app(hierarchy_factory)), base_url="http://local"
    ) as client:
        response = await client.post(
            "/api/v1/hierarchical-forecast-runs", json=request(source_ids).model_dump()
        )
        assert response.status_code == 200, response.text
        saved = response.json()
        run_id = saved["run"]["run_id"]
        assert (await client.get(f"/api/v1/hierarchical-forecast-runs/{run_id}")).json() == saved
        assert (
            len(
                (await client.get(f"/api/v1/hierarchical-forecast-runs/{run_id}/daily")).json()[
                    "daily_forecast"
                ]
            )
            == 15
        )
        history = await client.get(
            "/api/v1/hierarchical-forecast-runs",
            params={"target_entity_type": "COMPANY", "limit": 1},
        )
        assert history.status_code == 200, history.text
        assert history.json()["items"][0]["run_id"] == run_id
        assert "daily_forecast" not in history.text
        incomplete = await client.post(
            "/api/v1/hierarchical-forecast-runs", json=request(source_ids[:-1]).model_dump()
        )
        assert incomplete.status_code == 200
        assert incomplete.json()["result"]["official_aggregate_kg"] is None
        discovery = await client.get("/api/v1/hierarchical-forecast-hierarchy")
        assert discovery.status_code == 200
        assert "productive_area_mu" not in discovery.text
        assert "source_file" not in discovery.text
        assert (await client.get("/api/v1/hierarchical-forecast-runs/999999")).status_code == 404


async def test_api_permission_validation_domain_and_privacy(
    hierarchy_factory, source_ids, actor, monkeypatch
):
    async with AsyncClient(
        transport=ASGITransport(app=_app(hierarchy_factory)), base_url="http://local"
    ) as client:
        body = request(source_ids).model_dump()
        monkeypatch.setenv("TRIAL_ACTOR_PERMISSIONS", "may_read_forecast")
        assert (
            await client.post("/api/v1/hierarchical-forecast-runs", json=body)
        ).status_code == 404
        monkeypatch.setenv("TRIAL_ACTOR_PERMISSIONS", "may_create_forecast,may_read_forecast")
        for mutation in (
            {"override": "secret"},
            {"source_run_ids": [1, 1]},
            {"target_entity_id": "unknown"},
        ):
            response = await client.post(
                "/api/v1/hierarchical-forecast-runs", json={**body, **mutation}
            )
            assert response.status_code == 422

        async def broken(*args):
            raise RuntimeError("postgresql://secret@private/server")

        monkeypatch.setattr(
            "backend.app.api.hierarchical_forecast_runs.execute_hierarchical_run", broken
        )
        response = await client.post("/api/v1/hierarchical-forecast-runs", json=body)
        assert response.json() == {"code": "HIERARCHICAL_FORECAST_WRITE_FAILURE"}
        assert "secret" not in response.text


async def test_cli_and_mcp_canonical_parity(hierarchy_factory, source_ids, tmp_path, monkeypatch):
    body = request(source_ids).model_dump()

    def cli(words, payload=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        code = run_cli(
            ["hierarchical-forecast-run", *words],
            session_factory=hierarchy_factory,
            stdin=io.StringIO(json.dumps(payload) if payload else ""),
            stdout=stdout,
            stderr=stderr,
        )
        assert code == 0, stderr.getvalue()
        return json.loads(stdout.getvalue()) if stdout.getvalue() else None

    created = cli(["create", "--input", "-"], body)
    run_id = created["run"]["run_id"]
    assert cli(["get", "--run-id", str(run_id)]) == created
    assert cli(["list"])["items"][0]["run_id"] == run_id
    assert len(cli(["daily", "--run-id", str(run_id)])["daily_forecast"]) == 15
    path = tmp_path / "request.json"
    path.write_text(json.dumps(body))
    output = tmp_path / "result.json"
    cli(["create", "--input", str(path), "--output", str(output)])
    assert json.loads(output.read_text())["reused_existing_run"]
    monkeypatch.setattr(hierarchical_forecast_runs, "AsyncSessionMaker", hierarchy_factory)
    mcp_created = await hierarchical_forecast_runs.call_tool(
        hierarchical_forecast_runs.CREATE, body
    )
    assert mcp_created["result"] == created["result"]
    assert (
        await hierarchical_forecast_runs.call_tool(
            hierarchical_forecast_runs.GET, {"run_id": run_id}
        )
        == created
    )
    assert (
        len(
            (
                await hierarchical_forecast_runs.call_tool(
                    hierarchical_forecast_runs.DAILY, {"run_id": run_id}
                )
            )["daily_forecast"]
        )
        == 15
    )
    assert (await hierarchical_forecast_runs.call_tool(hierarchical_forecast_runs.LIST, {}))[
        "items"
    ][0]["run_id"] == run_id


async def test_mcp_schema_unknown_fields_incomplete_and_privacy(
    hierarchy_factory, source_ids, monkeypatch
):
    monkeypatch.setattr(hierarchical_forecast_runs, "AsyncSessionMaker", hierarchy_factory)
    tools = hierarchical_forecast_runs.run_tools()
    assert len(tools) == 4
    import hashlib

    payload = [
        {
            "name": t.name,
            "input": t.input_schema,
            "output": t.output_schema,
            "annotations": t.annotations.model_dump(),
        }
        for t in tools
    ]
    assert hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest() == ("44fed595b1f7aeee359210682b6f615513b1f54bc9460d555203e50f26b52b42")
    assert all(t.input_schema.get("additionalProperties") is False for t in tools)
    assert tools[0].annotations.read_only_hint is False
    assert all(t.annotations.read_only_hint for t in tools[1:])
    for body in (
        {**request(source_ids).model_dump(), "override": 1},
        {**request(source_ids).model_dump(), "source_run_ids": [1, 1]},
    ):
        response = await area_forecast._call_tool(
            None, CallToolRequestParams(name=hierarchical_forecast_runs.CREATE, arguments=body)
        )
        assert response.is_error
    value = await hierarchical_forecast_runs.call_tool(
        hierarchical_forecast_runs.CREATE, request(source_ids[:-1]).model_dump()
    )
    assert value["result"]["status"] == "INCOMPLETE_CHILD_COVERAGE"

    async def broken(*args):
        raise RuntimeError("secret database address")

    monkeypatch.setattr(hierarchical_forecast_runs, "call_tool", broken)
    response = await area_forecast._call_tool(
        None, CallToolRequestParams(name=hierarchical_forecast_runs.GET, arguments={"run_id": 1})
    )
    assert response.is_error and "secret" not in response.content[0].text


@pytest.mark.parametrize(
    "words",
    [["create", "--input", "-"], ["get", "--run-id", "999999"], ["list", "--cursor", "bad"]],
)
async def test_cli_errors_sanitized(hierarchy_factory, words):
    stdout, stderr = io.StringIO(), io.StringIO()
    code = run_cli(
        ["hierarchical-forecast-run", *words],
        session_factory=hierarchy_factory,
        stdin=io.StringIO("{}"),
        stdout=stdout,
        stderr=stderr,
    )
    assert code != 0
    assert "Traceback" not in stderr.getvalue()
