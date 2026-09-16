"""Saved-run MCP adapters: discovery, transactions and persisted transport parity."""

import hashlib
import io
import json

import pytest
from httpx import ASGITransport, AsyncClient
from mcp import Client
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import SQLAlchemyError

from backend.app.cli import run_cli
from backend.app.db.session import get_db_session
from backend.app.main import create_app
from backend.app.mcp import persisted_runs
from backend.app.mcp.area_forecast import server
from backend.app.models.area_forecast import AreaForecastDailyRow, AreaForecastRun
from backend.tests.area_yield.test_run_persistence import authority, bounded  # noqa: F401
from backend.tests.area_yield.test_run_transport import factory as factory

pytestmark = pytest.mark.usefixtures("authority")

NAMES = [
    "forecast_blueberry_by_area",
    "create_blueberry_area_forecast_run",
    "get_blueberry_area_forecast_run",
    "list_blueberry_area_forecast_runs",
    "get_blueberry_area_forecast_daily",
]
OPERATIONAL_NAMES = [
    "create_blueberry_operational_peak_forecast_run",
    "get_blueberry_operational_peak_forecast_run",
    "list_blueberry_operational_peak_forecast_runs",
    "get_blueberry_operational_peak_forecast_daily",
]
ALL_NAMES = NAMES + OPERATIONAL_NAMES


async def test_all_tools_discovery():
    async with Client(server) as client:
        tools = (await client.list_tools()).tools
    assert [tool.name for tool in tools] == ALL_NAMES
    for tool in tools:
        assert tool.description and tool.input_schema and tool.output_schema
        assert tool.annotations.read_only_hint == (
            tool.name not in {NAMES[1], OPERATIONAL_NAMES[0]}
        )
        assert tool.annotations.destructive_hint is False
        assert tool.annotations.idempotent_hint is True
        assert tool.annotations.open_world_hint is False


@pytest.fixture
async def configured(factory, monkeypatch):
    monkeypatch.setattr(persisted_runs, "AsyncSessionMaker", factory)
    return factory


def args(**changes):
    return {**bounded().model_dump(mode="json", exclude={"forecast_method"}), **changes}


def cli(factory, words, body=""):
    out, err = io.StringIO(), io.StringIO()
    code = run_cli(
        ["area-forecast-run", *words],
        session_factory=factory,
        stdin=io.StringIO(body),
        stdout=out,
        stderr=err,
    )
    assert code == 0, err.getvalue()
    return json.loads(out.getvalue())


async def test_transport_parity_history_and_stateless_no_write(configured, monkeypatch):
    app = create_app()

    async def sessions():
        async with configured() as s:
            yield s

    app.dependency_overrides[get_db_session] = sessions
    async with (
        Client(server) as c,
        AsyncClient(transport=ASGITransport(app=app), base_url="http://local") as http,
    ):
        stateless = await c.call_tool(NAMES[0], args())
        assert not stateless.is_error
        async with configured() as s:
            assert await s.scalar(select(func.count()).select_from(AreaForecastRun)) == 0
        created = await c.call_tool(NAMES[1], args())
        assert not created.is_error
        saved = created.structured_content
        rid = saved["run"]["run_id"]
        assert saved["result"] == stateless.structured_content
        again = (await c.call_tool(NAMES[1], args())).structured_content
        via_http = (await http.post("/api/v1/area-forecast-runs", json=args())).json()
        via_cli = cli(configured, ["create", "--input", "-"], json.dumps(args()))
        assert again == via_http == via_cli
        assert again["reused_existing_run"] and again["run"]["run_id"] == rid
        async with configured() as s:
            assert await s.scalar(select(func.count()).select_from(AreaForecastDailyRow)) == 207
        for area in ("500", "1000"):
            assert not (await c.call_tool(NAMES[1], args(productive_area_mu=area))).is_error
        monkeypatch.delenv("AREA_YIELD_AUTHORITY_PATH")
        assert (await c.call_tool(NAMES[2], {"run_id": rid})).structured_content == saved
        assert (await http.get(f"/api/v1/area-forecast-runs/{rid}")).json() == saved
        assert cli(configured, ["get", "--run-id", str(rid)]) == saved
        daily = (await c.call_tool(NAMES[4], {"run_id": rid})).structured_content
        assert daily["run_id"] == rid
        assert daily["daily_forecast"] == saved["result"]["daily_forecast"]
        assert (await http.get(f"/api/v1/area-forecast-runs/{rid}/daily")).json() == daily[
            "daily_forecast"
        ]
        assert (
            cli(configured, ["daily", "--run-id", str(rid)])["daily_forecast"]
            == daily["daily_forecast"]
        )
        filters = {"canonical_farm": "known", "target_season": "2026-2027", "limit": 2}
        history = (await c.call_tool(NAMES[3], filters)).structured_content
        assert (await http.get("/api/v1/area-forecast-runs", params=filters)).json() == history
        assert (
            cli(
                configured,
                ["list", "--farm", "known", "--target-season", "2026-2027", "--limit", "2"],
            )
            == history
        )
        assert "daily_forecast" not in json.dumps(history)
        cursor = history["next_cursor"]
        last = (await c.call_tool(NAMES[3], {**filters, "cursor": cursor})).structured_content
        assert (
            await http.get("/api/v1/area-forecast-runs", params={**filters, "cursor": cursor})
        ).json() == last
        assert (
            cli(
                configured,
                [
                    "list",
                    "--farm",
                    "known",
                    "--target-season",
                    "2026-2027",
                    "--limit",
                    "2",
                    "--cursor",
                    cursor,
                ],
            )
            == last
        )
        assert len(last["items"]) == 1


@pytest.mark.parametrize(
    "tool,body",
    [
        (NAMES[1], args(productive_area_mu=393.4)),
        (NAMES[1], args(authority_path="/private/secret")),
        (NAMES[1], args(forecast_method="AREA_DRIVEN_B1")),
        (NAMES[2], {"run_id": 0}),
        (NAMES[2], {"run_id": 1.2}),
        (NAMES[3], {"limit": 101}),
        (NAMES[3], {"database_url": "secret"}),
        (NAMES[3], {"cursor": "invalid cursor"}),
    ],
)
async def test_invalid_inputs(configured, tool, body):
    async with Client(server) as c:
        result = await c.call_tool(tool, body)
    assert result.is_error and result.structured_content["code"] == "AREA_FORECAST_REQUEST_INVALID"
    assert "/private/secret" not in result.model_dump_json()


async def test_errors_and_rerun_scope(configured, monkeypatch):
    async with Client(server) as c:
        a = (await c.call_tool(NAMES[1], args())).structured_content
        b = (await c.call_tool(NAMES[1], args(farm="other"))).structured_content
        bad = await c.call_tool(NAMES[1], args(rerun_of_run_id=b["run"]["run_id"]))
        assert (
            bad.is_error and bad.structured_content["code"] == "AREA_FORECAST_RERUN_SCOPE_MISMATCH"
        )
        good = await c.call_tool(NAMES[1], args(rerun_of_run_id=a["run"]["run_id"]))
        assert good.structured_content["reused_existing_run"]
        for changed in [
            {"farm": "unknown"},
            {"target_season": "2027-2028", "season_start": None, "season_end": None},
        ]:
            r = await c.call_tool(NAMES[1], args(**changed))
            assert r.structured_content["code"] == "AREA_FORECAST_UNSUPPORTED_FARM_HISTORY"
        missing = await c.call_tool(NAMES[2], {"run_id": 999999})
        assert missing.structured_content["code"] == "AREA_FORECAST_RUN_NOT_FOUND"
        monkeypatch.delenv("AREA_YIELD_AUTHORITY_PATH")
        failed = await c.call_tool(NAMES[1], args())
        assert failed.structured_content["code"] == "AREA_FORECAST_AUTHORITY_UNAVAILABLE"


@pytest.mark.parametrize("fault", ["missing", "quantity", "hash", "lineage"])
async def test_integrity_failure(configured, fault):
    async with Client(server) as c:
        other = (await c.call_tool(NAMES[1], args(farm="other"))).structured_content
        parent = (await c.call_tool(NAMES[1], args())).structured_content
        child = (
            await c.call_tool(
                NAMES[1], args(productive_area_mu="500", rerun_of_run_id=parent["run"]["run_id"])
            )
        ).structured_content
        rid = child["run"]["run_id"]
        async with configured() as s, s.begin():
            if fault == "missing":
                await s.execute(
                    delete(AreaForecastDailyRow).where(
                        AreaForecastDailyRow.run_id == rid, AreaForecastDailyRow.row_index == 3
                    )
                )
            elif fault == "quantity":
                await s.execute(
                    update(AreaForecastDailyRow)
                    .where(AreaForecastDailyRow.run_id == rid, AreaForecastDailyRow.row_index == 3)
                    .values(predicted_kg=999)
                )
            else:
                values = (
                    {"result_hash": "bad"}
                    if fault == "hash"
                    else {"rerun_of_run_id": other["run"]["run_id"]}
                )
                await s.execute(
                    update(AreaForecastRun).where(AreaForecastRun.id == rid).values(**values)
                )
        for name in (NAMES[2], NAMES[4]):
            result = await c.call_tool(name, {"run_id": rid})
            assert (
                result.is_error
                and result.structured_content["code"]
                == "AREA_FORECAST_PERSISTENCE_INTEGRITY_FAILED"
            )


@pytest.mark.parametrize(
    "name,body",
    [(NAMES[1], args()), (NAMES[2], {"run_id": 1}), (NAMES[3], {}), (NAMES[4], {"run_id": 1})],
)
async def test_database_failure_redacted(configured, monkeypatch, name, body):
    def broken():
        raise SQLAlchemyError("postgresql://private:credential@host/db SELECT secret /private/path")

    monkeypatch.setattr(persisted_runs, "AsyncSessionMaker", broken)
    async with Client(server) as c:
        result = await c.call_tool(name, body)
    assert result.is_error and result.structured_content["code"] == "AREA_FORECAST_WRITE_FAILURE"
    assert all(s not in result.model_dump_json() for s in ("credential", "SELECT", "/private/path"))


async def test_saved_tool_schema_hash():
    async with Client(server) as c:
        tools = (await c.list_tools()).tools
    payload = [
        {
            "name": t.name,
            "input": t.input_schema,
            "output": t.output_schema,
            "annotations": t.annotations.model_dump(),
        }
        for t in tools[1:]
    ]
    value = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert value == "2deef74fbe79823e5005f37ca44d5581ab1efc1a95cc9c4c6a00a5eafe0cba48"


async def test_failed_create_rolls_back_outer_transaction(configured, monkeypatch):
    original = persisted_runs.execute_area_forecast_run

    async def fail_after_flush(*args, **kwargs):
        await original(*args, **kwargs)
        raise SQLAlchemyError("private commit boundary failure")

    monkeypatch.setattr(persisted_runs, "execute_area_forecast_run", fail_after_flush)
    async with Client(server) as c:
        result = await c.call_tool(NAMES[1], args())
    assert result.is_error and result.structured_content["code"] == "AREA_FORECAST_WRITE_FAILURE"
    async with configured() as s:
        assert await s.scalar(select(func.count()).select_from(AreaForecastRun)) == 0
        assert await s.scalar(select(func.count()).select_from(AreaForecastDailyRow)) == 0
