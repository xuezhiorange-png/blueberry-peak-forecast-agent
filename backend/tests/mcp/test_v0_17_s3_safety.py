"""SYNTHETIC=true. Failure injection, cancellation and canonical integrity gates."""
# ruff: noqa: F811

import ast
import asyncio
from copy import deepcopy
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import event, text

from backend.app.forecast_intelligence.application import execute_hierarchical_run
from backend.app.forecast_intelligence.decision_service import COST_HASHES
from backend.app.forecast_intelligence.read_schemas import QualityReadQuery
from backend.app.forecast_intelligence.read_service import (
    PUBLIC_EVIDENCE_HASHES,
    ForecastIntelligenceReadService,
)
from backend.app.mcp.forecast_intelligence_http import (
    MCP_PATH,
    ForecastIntelligenceHTTP,
    create_forecast_intelligence_app,
)
from backend.tests.forecast_intelligence.conftest import (  # noqa: F401
    source_ids,
    synthetic_authority,
)
from backend.tests.mcp.test_v0_17_s3_productization import (
    HEADER,
    KEY,
    account,
    call,
    client,
    comparison_payload,
    config,
    dead_session,
    grant_for,
    hierarchy_factory,  # noqa: F401
    hierarchy_query,
    hierarchy_request,
    query,
    request_payload,
)

pytestmark = [pytest.mark.unit, pytest.mark.contract]


async def test_real_sdk_http_client_initialize_list_and_call():
    import httpx2
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    app = create_forecast_intelligence_app(config(), session_factory=dead_session)
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app),
        headers={HEADER: KEY},
    ) as http:
        async with streamable_http_client("https://test" + MCP_PATH, http_client=http) as streams:
            async with ClientSession(streams[0], streams[1]) as sdk:
                await sdk.initialize()
                assert len((await sdk.list_tools()).tools) == 8
                value = await sdk.call_tool("get_forecast_quality", {})
                assert not value.is_error
                expected = (
                    await ForecastIntelligenceReadService(None).quality(QualityReadQuery())
                ).model_dump(mode="json")
                assert value.structured_content == expected
                denied = await sdk.call_tool(
                    "get_forecast_curve", query(run_id=2).model_dump(mode="json")
                )
                assert denied.is_error and denied.structured_content["code"] == "FORBIDDEN"


@pytest.mark.parametrize("filename", list(PUBLIC_EVIDENCE_HASHES))
@pytest.mark.parametrize("missing", [True, False])
async def test_quality_missing_or_tampered_files_remain_fail_closed(monkeypatch, filename, missing):
    original = Path.read_bytes

    def altered(path):
        if path.as_posix().endswith(filename):
            if missing:
                raise FileNotFoundError
            return b"SYNTHETIC_TAMPER"
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", altered)
    app = create_forecast_intelligence_app(config(), session_factory=dead_session)
    async with client(app) as c:
        value = await call(c, "get_forecast_quality", {})
        if missing:
            assert not value["isError"]
            assert value["structuredContent"]["status"] == "NOT_AVAILABLE"
            assert value["structuredContent"]["data"] is None
        else:
            assert value["isError"]
            assert value["structuredContent"]["code"] == "PUBLIC_EVIDENCE_AUTHORITY_MISMATCH"


@pytest.mark.parametrize("kind", ["daily", "hash", "summary", "origin"])
async def test_damaged_canonical_saved_run(hierarchy_factory, source_ids, kind):
    async with hierarchy_factory() as session:
        source = await ForecastIntelligenceReadService(session).curve(query(source_ids[0]))
    # Only the isolated SYNTHETIC database is intentionally corrupted.
    async with hierarchy_factory() as session, session.begin():
        table = (
            "operational_peak_forecast_daily"
            if kind == "daily"
            else "operational_peak_forecast_run"
        )
        await session.execute(text(f"DROP TRIGGER {table}_update"))
        assignment = {
            "daily": "predicted_kg='999'",
            "hash": "result_hash='" + "b" * 64 + "'",
            "summary": "forecast_7d='{}'",
            "origin": "origin_date='2026-01-03'",
        }[kind]
        key = "run_id" if kind == "daily" else "id"
        await session.execute(
            text(f"UPDATE {table} SET {assignment} WHERE {key}=:id"), {"id": source_ids[0]}
        )
    app = create_forecast_intelligence_app(
        config(account(run_grants=(grant_for(source),))),
        session_factory=hierarchy_factory,
    )
    async with client(app) as c:
        value = await call(c, "get_forecast_curve", query(source_ids[0]).model_dump(mode="json"))
        assert value["isError"]
        assert value["structuredContent"]["code"] == "SAVED_RUN_INTEGRITY_FAILED"


async def test_incomplete_hierarchy_keeps_partial_and_blocks_simulation(
    hierarchy_factory, source_ids
):
    async with hierarchy_factory() as session:
        saved = await execute_hierarchical_run(session, hierarchy_request(source_ids[:-1]))
        await session.commit()
        q = hierarchy_query(saved)
        reader = ForecastIntelligenceReadService(session)
        source = await reader.curve(q)
        expected = (await reader.hierarchy(q)).model_dump(mode="json")
    assert expected["status"] == "PARTIAL"
    app = create_forecast_intelligence_app(
        config(account(run_grants=(grant_for(source),))),
        session_factory=hierarchy_factory,
    )
    async with client(app) as c:
        value = await call(c, "get_hierarchical_forecast", q.model_dump(mode="json"))
        assert value["structuredContent"] == expected
        payload = request_payload(source)
        payload["capacity_rows"] = [
            {"date": "2026-01-02", "capacity_mode": "DIRECT", "daily_handling_capacity_kg": "140"}
        ]
        value = await call(c, "simulate_capacity", payload)
        assert not value["isError"]
        assert value["structuredContent"]["status"] == "NOT_AVAILABLE"
        assert value["structuredContent"]["data"] is None


async def test_explicit_rerun_grant_does_not_authorize_parent_or_latest(
    hierarchy_factory,
    source_ids,
    synthetic_authority,
):
    from backend.app.forecast_quality.operational_peak import (
        OperationalPeakForecastRequest,
        forecast_operational_peak,
    )
    from backend.app.forecast_quality.operational_peak_persistence import (
        OperationalPeakRunRepository,
        execution_hash,
    )

    async with hierarchy_factory() as session, session.begin():
        repo = OperationalPeakRunRepository(session)
        old = await repo.get(source_ids[0])
        fixture = forecast_operational_peak(
            OperationalPeakForecastRequest("A1", "2025-2026", date(2026, 1, 1)),
            synthetic_authority.registry,
            synthetic_authority.reference_profile,
        )
        new = await repo.save(
            snapshot=old.request_snapshot,
            result=fixture,
            execution_id=execution_hash(old.request_snapshot, "c" * 64, fixture.policy_version),
            authority_hash="c" * 64,
            rerun_of_run_id=source_ids[0],
        )
    async with hierarchy_factory() as session:
        source = await ForecastIntelligenceReadService(session).curve(query(new.run.run_id))
    app = create_forecast_intelligence_app(
        config(account(run_grants=(grant_for(source),))),
        session_factory=hierarchy_factory,
    )
    async with client(app) as c:
        value = await call(c, "get_forecast_curve", query(new.run.run_id).model_dump(mode="json"))
        assert value["structuredContent"] == source.model_dump(mode="json")
        assert value["structuredContent"]["source_rerun_of_run_id"] == source_ids[0]
        value = await call(c, "get_forecast_curve", query(source_ids[0]).model_dump(mode="json"))
        assert value["isError"] and value["structuredContent"]["code"] == "FORBIDDEN"


@pytest.mark.parametrize(
    "field,value",
    [
        ("daily_handling_capacity_kg", 140.0),
        ("daily_handling_capacity_kg", True),
        ("daily_handling_capacity_kg", "-1"),
        ("daily_handling_capacity_kg", "NaN"),
        ("daily_handling_capacity_kg", "Infinity"),
        ("daily_handling_capacity_kg", "1" * 65),
        ("workforce_count", True),
        ("workforce_count", 10.0),
        ("workforce_count", -1),
        ("workforce_count", 1000001),
        ("productivity_kg_per_person_day", "-1"),
    ],
)
async def test_numeric_schema_before_data_read(field, value):
    row = {"date": "2026-01-02", "capacity_mode": "DIRECT", "daily_handling_capacity_kg": "140"}
    if field in ("workforce_count", "productivity_kg_per_person_day"):
        row = {
            "date": "2026-01-02",
            "capacity_mode": "WORKFORCE_DERIVED",
            "workforce_count": 10,
            "productivity_kg_per_person_day": "12",
        }
    row[field] = value
    payload = {
        "forecast_selection": query().model_dump(
            mode="json", exclude={"expected_source_result_hash"}
        ),
        "expected_source_result_hash": "a" * 64,
        "planning_level": "POINT",
        "cost_contract_id": "SYNTHETIC_BALANCED_R1",
        "expected_cost_contract_hash": COST_HASHES["SYNTHETIC_BALANCED_R1"],
        "scenario_id": "A",
        "scenario_version": "R1",
        "capacity_rows": [row],
    }
    app = create_forecast_intelligence_app(config(), session_factory=dead_session)
    async with client(app) as c:
        value = await call(c, "simulate_capacity", payload)
        assert value["isError"] and value["structuredContent"]["code"] == "INVALID_REQUEST"


async def test_no_dml_and_bounded_scenario_ranking(hierarchy_factory, source_ids):
    async with hierarchy_factory() as session:
        source = await ForecastIntelligenceReadService(session).curve(query(source_ids[0]))
    app = create_forecast_intelligence_app(
        config(account(run_grants=(grant_for(source),))),
        session_factory=hierarchy_factory,
    )
    engine = hierarchy_factory.kw["bind"].sync_engine
    statements = []

    def audit(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.strip().split()[0].upper())

    event.listen(engine, "before_cursor_execute", audit)
    try:
        async with client(app) as c:
            for cost_id, cost_hash in COST_HASHES.items():
                payload = request_payload(source, capacity="0")
                payload.update(cost_contract_id=cost_id, expected_cost_contract_hash=cost_hash)
                compared = comparison_payload(payload, count=20)
                first = await call(c, "compare_capacity_scenarios", compared)
                assert not first["isError"]
                compared["scenarios"].reverse()
                second = await call(c, "compare_capacity_scenarios", compared)
                assert first == second
                data = first["structuredContent"]["data"]
                assert data["scenario_results"][0]["aggregate_capacity_utilization_decimal"] is None
                compared["scenarios"].append(deepcopy(compared["scenarios"][0]))
                assert (await call(c, "compare_capacity_scenarios", compared))["isError"]
    finally:
        event.remove(engine, "before_cursor_execute", audit)
    assert statements and set(statements) <= {"SELECT", "PRAGMA", "BEGIN"}


async def test_cancellation_cleans_request_and_next_request_recovers(monkeypatch):
    started = asyncio.Event()

    async def waiting(self, query):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(ForecastIntelligenceReadService, "quality", waiting)
    app = create_forecast_intelligence_app(config(), session_factory=dead_session)
    async with client(app) as c:
        task = asyncio.create_task(call(c, "get_forecast_quality", {}))
        await asyncio.wait_for(started.wait(), 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        monkeypatch.undo()
        value = await call(c, "get_forecast_quality", {})
        assert not value["isError"]


async def test_disconnect_before_complete_body_is_not_success():
    sent = []

    async def receive():
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    await ForecastIntelligenceHTTP(config(), dead_session)(
        {
            "type": "http",
            "scheme": "https",
            "method": "POST",
            "path": MCP_PATH,
            "headers": [(b"host", b"test"), (HEADER.lower().encode(), KEY.encode())],
        },
        receive,
        send,
    )
    assert sent == []


def test_no_algorithm_or_legacy_dependency_in_adapter():
    root = Path(__file__).resolve().parents[3]
    for path in (root / "backend/app/mcp").glob("forecast_intelligence_*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not any(
                    word in (node.module or "")
                    for word in (
                        "area_forecast",
                        "operational_peak_runs",
                        "persisted_runs",
                        "label_zone",
                        "actual_harvest_import",
                        "sklearn",
                        "lightgbm",
                        "catboost",
                    )
                )
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {"fit", "predict", "commit", "flush", "execute"}


async def test_arguments_limit_before_validation_or_read():
    app = create_forecast_intelligence_app(config(), session_factory=dead_session)
    async with client(app) as c:
        value = await call(c, "get_forecast_curve", {"extra": "x" * 131072})
        assert value["isError"]
        assert value["structuredContent"]["code"] == "RESOURCE_LIMIT_EXCEEDED"


async def test_response_limit_is_diagnostic_not_truncated(monkeypatch):
    from backend.app.mcp import forecast_intelligence_server as server_module

    original = ForecastIntelligenceReadService.quality

    async def large(self, query):
        value = await original(self, query)
        return value.model_copy(update={"unavailable_reason": "x" * 10000})

    monkeypatch.setattr(ForecastIntelligenceReadService, "quality", large)
    monkeypatch.setattr(server_module, "RESPONSE_LIMIT", 1000)
    app = create_forecast_intelligence_app(config(), session_factory=dead_session)
    async with client(app) as c:
        value = await call(c, "get_forecast_quality", {})
        assert value["isError"]
        assert value["structuredContent"] == {
            "status": "ERROR",
            "code": "RESOURCE_LIMIT_EXCEEDED",
            "data": None,
        }


async def test_timeout_recovers_and_never_returns_partial_business_result(monkeypatch):
    from backend.app.mcp import forecast_intelligence_http as transport_module

    async def slow(self, query):
        await asyncio.Event().wait()

    monkeypatch.setattr(ForecastIntelligenceReadService, "quality", slow)
    monkeypatch.setattr(transport_module, "EXECUTION_SECONDS", 0.05)
    app = create_forecast_intelligence_app(config(), session_factory=dead_session)
    async with client(app) as c:
        response = await c.post(
            MCP_PATH,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "get_forecast_quality", "arguments": {}},
            },
        )
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "EXECUTION_TIMEOUT"
        monkeypatch.undo()
        assert not (await call(c, "get_forecast_quality", {}))["isError"]


@pytest.mark.parametrize("mode", ["HISTORICAL_VALIDATION", "CURRENT_PRODUCTION_ACCURACY"])
async def test_quality_grant_required_before_file_access(mode, monkeypatch):
    def blocked(*args):
        pytest.fail("QUALITY_FILE_READ_EXECUTED")

    monkeypatch.setattr("backend.app.forecast_intelligence.read_service.public_evidence", blocked)
    app = create_forecast_intelligence_app(
        config(account(quality_grants=())),
        session_factory=dead_session,
    )
    async with client(app) as c:
        value = await call(c, "get_forecast_quality", {"mode": mode})
        assert value["isError"] and value["structuredContent"]["code"] == "FORBIDDEN"


@pytest.mark.parametrize("broken", ["SQL", "INTERNAL"])
async def test_failure_then_next_request_recovers(monkeypatch, broken):
    from sqlalchemy.exc import SQLAlchemyError

    async def failing(self, query):
        if broken == "SQL":
            raise SQLAlchemyError("SYNTHETIC_PRIVATE_EXCEPTION")
        raise RuntimeError("SYNTHETIC_PRIVATE_EXCEPTION")

    monkeypatch.setattr(ForecastIntelligenceReadService, "quality", failing)
    app = create_forecast_intelligence_app(config(), session_factory=dead_session)
    async with client(app) as c:
        value = await call(c, "get_forecast_quality", {})
        assert value["isError"]
        assert "SYNTHETIC_PRIVATE_EXCEPTION" not in str(value)
        monkeypatch.undo()
        assert not (await call(c, "get_forecast_quality", {}))["isError"]


async def test_short_saved_window_is_partial_not_full_h15(hierarchy_factory, synthetic_authority):
    from backend.app.forecast_quality.operational_peak import (
        OperationalPeakForecastRequest,
        forecast_operational_peak,
    )
    from backend.app.forecast_quality.operational_peak_persistence import (
        OperationalPeakRunRepository,
        execution_hash,
        request_snapshot,
    )

    origin = date(2026, 4, 14)
    request = OperationalPeakForecastRequest("A1", "2025-2026", origin)
    fixture = forecast_operational_peak(
        request,
        synthetic_authority.registry,
        synthetic_authority.reference_profile,
    )
    snapshot = request_snapshot(request)
    async with hierarchy_factory() as session, session.begin():
        saved = await OperationalPeakRunRepository(session).save(
            snapshot=snapshot,
            result=fixture,
            execution_id=execution_hash(
                snapshot,
                synthetic_authority.authority_hash,
                synthetic_authority.policy_version,
            ),
            authority_hash=synthetic_authority.authority_hash,
            rerun_of_run_id=None,
        )
    q = query(saved.run.run_id, origin_date=origin)
    async with hierarchy_factory() as session:
        source = await ForecastIntelligenceReadService(session).curve(q)
    app = create_forecast_intelligence_app(
        config(account(run_grants=(grant_for(source),))),
        session_factory=hierarchy_factory,
    )
    async with client(app) as c:
        overview = (await call(c, "get_forecast_overview", q.model_dump(mode="json")))[
            "structuredContent"
        ]
        assert overview["status"] == "PARTIAL"
        assert overview["data"]["forecast_15d_total_kg"] is None
        simulated = (await call(c, "simulate_capacity", request_payload(source)))[
            "structuredContent"
        ]
        assert simulated["status"] == "PARTIAL"
        assert simulated["data"]["day_count"] == 1


async def test_granted_nonexistent_run_is_not_found_not_fallback(hierarchy_factory):
    app = create_forecast_intelligence_app(config(), session_factory=hierarchy_factory)
    async with client(app) as c:
        value = await call(c, "get_forecast_curve", query().model_dump(mode="json"))
        assert value["isError"] and value["structuredContent"]["code"] == "SAVED_RUN_NOT_FOUND"


@pytest.mark.parametrize("method", ["simulate_capacity", "compare_capacity_scenarios"])
async def test_decision_grant_denied_before_source_or_engine(method):
    payload = {
        "forecast_selection": query(run_id=999).model_dump(
            mode="json", exclude={"expected_source_result_hash"}
        ),
        "expected_source_result_hash": "a" * 64,
        "planning_level": "POINT",
        "cost_contract_id": "SYNTHETIC_BALANCED_R1",
        "expected_cost_contract_hash": COST_HASHES["SYNTHETIC_BALANCED_R1"],
        "scenario_id": "A",
        "scenario_version": "R1",
        "capacity_rows": [
            {"date": "2026-01-02", "capacity_mode": "DIRECT", "daily_handling_capacity_kg": "140"}
        ],
    }
    if method == "compare_capacity_scenarios":
        payload = comparison_payload(payload)
    app = create_forecast_intelligence_app(config(), session_factory=dead_session)
    async with client(app) as c:
        value = await call(c, method, payload)
        assert value["isError"] and value["structuredContent"]["code"] == "FORBIDDEN"


async def test_sdk_http_saved_curve_and_decision_service_parity(hierarchy_factory, source_ids):
    import httpx2
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    from backend.app.forecast_intelligence.decision_service import DecisionSupportService

    async with hierarchy_factory() as session:
        reader = ForecastIntelligenceReadService(session)
        source = await reader.curve(query(source_ids[0]))
        requests = {"simulate_capacity": request_payload(source)}
        requests["compare_capacity_scenarios"] = comparison_payload(requests["simulate_capacity"])
        expected = {
            "get_forecast_curve": source.model_dump(mode="json"),
            "simulate_capacity": (
                await DecisionSupportService(reader).simulate(requests["simulate_capacity"])
            ).model_dump(mode="json"),
            "compare_capacity_scenarios": (
                await DecisionSupportService(reader).compare(requests["compare_capacity_scenarios"])
            ).model_dump(mode="json"),
        }
    requests["get_forecast_curve"] = query(source_ids[0]).model_dump(mode="json")
    app = create_forecast_intelligence_app(
        config(account(run_grants=(grant_for(source),))),
        session_factory=hierarchy_factory,
    )
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app),
        headers={HEADER: KEY},
    ) as http:
        async with streamable_http_client("https://test" + MCP_PATH, http_client=http) as streams:
            async with ClientSession(streams[0], streams[1]) as sdk:
                await sdk.initialize()
                for name, request in requests.items():
                    value = await sdk.call_tool(name, request)
                    assert not value.is_error
                    assert value.structured_content == expected[name]
