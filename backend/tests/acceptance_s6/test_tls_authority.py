"""Fresh S6: one canonical PG authority, real HTTP/TLS and MCP SDK, no mock payloads."""

import json
import ssl
from decimal import Decimal

import httpx
import httpx2
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pydantic import SecretStr
from sqlalchemy import select

from backend.app.db import session as database_session
from backend.app.forecast_intelligence.decision_schemas import CostSelection
from backend.app.forecast_intelligence.decision_service import COST_HASHES, DecisionSupportService
from backend.app.forecast_intelligence.persistence import HierarchicalRunRepository
from backend.app.forecast_intelligence.read_schemas import ForecastReadQuery, QualityReadQuery
from backend.app.forecast_intelligence.read_service import ForecastIntelligenceReadService
from backend.app.forecast_quality.operational_peak_persistence import OperationalPeakRunRepository
from backend.app.mcp.forecast_intelligence_http import MCP_PATH, create_service_account_app
from backend.app.mcp.forecast_intelligence_tools import TOOLS, tools
from backend.app.models.hierarchical_forecast import HierarchicalForecastRun
from backend.tests.business_access.test_discovery import grant
from backend.tests.mcp.test_v0_17_s3_productization import (
    HEADER,
    KEY,
    account,
    comparison_payload,
    grant_for,
    request_payload,
)
from backend.tests.mcp.test_v0_18_s3_policy import document, policy
from backend.tests.mcp.test_v0_18_s3_postgres import quality_grant
from backend.tests.safe_pilot.operations import assert_redacted, tls_server
from backend.tests.safe_pilot.test_restore_and_ingress import application, seed, sign_in

pytestmark = pytest.mark.postgres


async def write(http, origin, path, payload):
    csrf = (await http.get("/api/v1/auth/csrf")).json()["data"]["csrf_token"]
    return await http.post(path, json=payload, headers={"Origin": origin, "X-CSRF-Token": csrf})


async def prepared(pg_auth, level):
    auth, factory, _, user, _ = pg_auth
    selected, binding = await seed(factory, user)
    if level != "BASE":
        async with factory() as db:
            row = await db.scalar(
                select(HierarchicalForecastRun).where(
                    HierarchicalForecastRun.target_entity_type == level
                )
            )
            selected = ForecastReadQuery(
                **{
                    **selected.model_dump(),
                    "source_kind": "HIERARCHICAL",
                    "run_id": row.id,
                    "hierarchy_level": level,
                    "entity_id": row.target_entity_id,
                    "expected_source_result_hash": row.result_hash,
                }
            )
        binding = await grant(factory, user, selected)
    await quality_grant(factory, user)
    auth.settings.business_access_signing_key = SecretStr("SYNTHETIC_S6_SIGNING_" * 4)
    auth.settings.local_auth_simple_admin_catalog_json = SecretStr(
        json.dumps(
            {
                "organization_ids": ["SYNTHETIC_ORG"],
                "resources": [
                    {
                        "organization_id": "SYNTHETIC_ORG",
                        "resource_kind": "FORECAST",
                        "capability": "may_read_forecast",
                        "binding": binding.forecast_binding,
                    }
                ],
            }
        )
    )
    return auth, factory, selected


@pytest.mark.parametrize("level", ["BASE", "REGION", "COMPANY"])
async def test_s6_canonical_http_sdk_complete_payloads(
    pg_auth, tmp_path, monkeypatch, record_property, caplog, level
):
    auth, factory, selected = await prepared(pg_auth, level)
    async with factory() as db:
        source = await ForecastIntelligenceReadService(db).curve(selected)
        repository = (
            OperationalPeakRunRepository(db) if level == "BASE" else HierarchicalRunRepository(db)
        )
        saved = await repository.get(selected.run_id)
        assert saved.result["result_hash"] == source.source_result_hash
        assert [r["predicted_kg"] for r in saved.result["daily_forecast"]] == [
            r.point_forecast_kg for r in source.data.daily_rows
        ]
        assert [r["date"] for r in saved.result["daily_forecast"]] == [
            r.target_date.isoformat() for r in source.data.daily_rows
        ]
    record_property(
        "S6_CANONICAL_REPOSITORY_PROOF",
        json.dumps(
            {
                "level": level,
                "source_result_hash": source.source_result_hash,
                "run_id": selected.run_id,
                "raw_decimal_and_dates_equal": True,
            },
            sort_keys=True,
        ),
    )
    provider = policy(tmp_path)
    monkeypatch.setenv("FORECAST_INTELLIGENCE_MCP_POLICY_FILE", str(provider.path))
    monkeypatch.setattr(database_session, "AsyncSessionMaker", factory)
    http_dir, mcp_dir = tmp_path / "http", tmp_path / "mcp"
    http_dir.mkdir()
    mcp_dir.mkdir()
    matrix = []
    async with (
        tls_server(application(auth), http_dir) as (origin, cert, _),
        tls_server(create_service_account_app(), mcp_dir) as (machine_origin, machine_cert, _),
    ):
        auth.settings.local_auth_origin = origin
        provider.publish(
            document(
                2,
                accounts=(account(run_grants=(grant_for(source),)),),
                allowed_hosts=(machine_origin.removeprefix("https://"),),
            )
        )
        async with (
            httpx.AsyncClient(
                base_url=origin, verify=ssl.create_default_context(cafile=str(cert))
            ) as http,
            httpx2.AsyncClient(
                verify=ssl.create_default_context(cafile=str(machine_cert)), headers={HEADER: KEY}
            ) as machine,
        ):
            cookie = await sign_in(http)
            scope = await http.get("/api/v1/business-access/scope")
            assert scope.status_code == 200
            listed = await http.get(
                "/api/v1/business-access/saved-runs",
                params={"hierarchy_level": level, "entity_id": selected.entity_id, "page_size": 1},
            )
            assert listed.status_code == 200
            data = listed.json()["data"]
            assert len(data["items"]) == 1 and data["next_cursor"] is None
            item = data["items"][0]
            assert item["forecast_identity"] == source.forecast_identity.model_dump(mode="json")
            handoff = await write(
                http,
                origin,
                "/api/v1/business-access/selection",
                {key: data[key] for key in ("grant_revision", "catalog_snapshot")}
                | {key: item[key] for key in ("forecast_identity", "expected_source_result_hash")},
            )
            assert handoff.status_code == 200 and handoff.json()["data"]["expires_in"] == 300
            async with streamable_http_client(
                machine_origin + MCP_PATH, http_client=machine
            ) as streams:
                async with ClientSession(streams[0], streams[1]) as sdk:
                    await sdk.initialize()
                    listing = (await sdk.list_tools()).tools
                    assert len(listing) == 8
                    assert [t.model_dump() for t in listing] == [t.model_dump() for t in tools()]

                    async def compare(name, payload, canonical, response):
                        assert response.status_code == 200, response.text
                        actual = await sdk.call_tool(name, payload)
                        assert not actual.is_error
                        expected = canonical.model_dump(mode="json")
                        assert actual.structured_content == response.json() == expected
                        assert json.loads(actual.content[0].text) == expected
                        matrix.append(
                            {
                                "tool": name,
                                "planning_level": payload.get("planning_level"),
                                "capacity_mode": payload.get("capacity_rows", [{}])[0].get(
                                    "capacity_mode"
                                ),
                                "forecast_identity": expected.get("forecast_identity"),
                                "source_result_hash": expected.get("source_result_hash"),
                                "projection_hash": expected["projection_hash"],
                                "engine_result_hash": expected.get("engine_result_hash"),
                                "status": expected["status"],
                                "numeric_hash_semantic_parity": "PASS",
                            }
                        )

                    for name, tool in list(TOOLS.items())[:6]:
                        query = QualityReadQuery() if tool.method == "quality" else selected
                        payload = query.model_dump(mode="json")
                        async with factory() as db:
                            canonical = await getattr(
                                ForecastIntelligenceReadService(db), tool.method
                            )(query)
                        response = await http.get(
                            "/api/v1/forecast-intelligence/" + tool.method,
                            params={k: v for k, v in payload.items() if v is not None},
                        )
                        await compare(name, payload, canonical, response)
                        if tool.method in {"uncertainty", "attribution"}:
                            assert canonical.status == "NOT_AVAILABLE"
                        if tool.method == "overview":
                            assert Decimal(canonical.data.forecast_7d_total_kg) == Decimal(
                                "980" if level == "BASE" else "1960"
                            )
                            assert Decimal(canonical.data.forecast_15d_total_kg) == Decimal(
                                "1820" if level == "BASE" else "3640"
                            )
                    cost = CostSelection(
                        cost_contract_id="SYNTHETIC_UNDER_4X_R1",
                        expected_cost_contract_hash=COST_HASHES["SYNTHETIC_UNDER_4X_R1"],
                    )
                    exposure = await http.get(
                        "/api/v1/decision-support/business-loss", params=cost.model_dump()
                    )
                    assert exposure.status_code == 200
                    assert exposure.json() == DecisionSupportService(None).business_loss(
                        cost
                    ).model_dump(mode="json")
                    for mode in ("DIRECT", "WORKFORCE_DERIVED"):
                        for planning in (
                            "POINT",
                            "UPPER_PLANNING_BOUND_80",
                            "UPPER_PLANNING_BOUND_90",
                        ):
                            payload = request_payload(source, sid=mode, mode=mode)
                            payload.update(cost.model_dump(), planning_level=planning)
                            for comparison in (False, True):
                                values = comparison_payload(payload) if comparison else payload
                                method = "compare" if comparison else "simulate"
                                path = (
                                    "compare-capacity-scenarios"
                                    if comparison
                                    else "simulate-capacity"
                                )
                                async with factory() as db:
                                    canonical = await getattr(
                                        DecisionSupportService(ForecastIntelligenceReadService(db)),
                                        method,
                                    )(values)
                                response = await write(
                                    http, origin, "/api/v1/decision-support/" + path, values
                                )
                                await compare(
                                    "compare_capacity_scenarios"
                                    if comparison
                                    else "simulate_capacity",
                                    values,
                                    canonical,
                                    response,
                                )
                                if planning != "POINT":
                                    assert canonical.status == "NOT_AVAILABLE"
                                elif not comparison:
                                    assert canonical.data.initial_backlog_kg == "0"
                                    assert all(
                                        isinstance(r.planning_demand_kg, str)
                                        for r in canonical.data.daily_rows
                                    )
                                    if level == "BASE":
                                        assert canonical.data.total_business_loss == "980"
                                        assert canonical.data.overload_day_count == 4
                    assert_redacted(
                        caplog.text, [KEY, cookie, handoff.json()["data"]["handoff_token"]]
                    )
    record_property("S6_PARITY_MATRIX", json.dumps(matrix, sort_keys=True))
