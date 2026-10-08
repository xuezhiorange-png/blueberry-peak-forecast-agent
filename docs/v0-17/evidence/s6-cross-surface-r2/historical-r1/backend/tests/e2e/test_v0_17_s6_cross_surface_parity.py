"""SYNTHETIC=true. Real canonical SQLite / HTTP / SDK acceptance, no inference."""

import json
from decimal import Decimal

import httpx
import jsonschema
import pytest

from backend.app.forecast_intelligence.decision_service import COST_HASHES, DecisionSupportService
from backend.app.forecast_intelligence.read_schemas import ForecastReadQuery, QualityReadQuery
from backend.app.forecast_intelligence.read_service import ForecastIntelligenceReadService
from backend.app.mcp.forecast_intelligence_tools import TOOLS
from frontend.e2e.support import s6_api as harness

pytestmark = [pytest.mark.unit, pytest.mark.contract]


@pytest.fixture
async def environment():
    async with harness.lifespan(harness.app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=harness.app), base_url="http://s6.test"
        ) as http:
            yield harness.app, http
        assert harness.seed.STATE["read_dml_count"] == 0


def scenario(source, scenario_id="B", mode="DIRECT", buffer="0", capacity="140"):
    identity = source["forecast_identity"]
    rows = []
    for day in source["data"]["daily_rows"]:
        row = {"date": day["target_date"], "capacity_mode": mode}
        if mode == "DIRECT":
            row["daily_handling_capacity_kg"] = capacity
        else:
            row.update(workforce_count=10, productivity_kg_per_person_day="12")
        if buffer is not None:
            row["buffer_handling_capacity_kg"] = buffer
        rows.append(row)
    return {
        "forecast_selection": identity,
        "expected_source_result_hash": source["source_result_hash"],
        "planning_level": "POINT",
        "cost_contract_id": "SYNTHETIC_UNDER_4X_R1",
        "expected_cost_contract_hash": COST_HASHES["SYNTHETIC_UNDER_4X_R1"],
        "scenario_id": scenario_id,
        "scenario_version": "R1",
        "capacity_rows": rows,
    }


async def assert_sdk(sdk, name, arguments, expected, schemas):
    result = await harness.sdk_call(sdk, name, arguments)
    assert not result.is_error
    assert result.structured_content == expected
    jsonschema.validate(result.structured_content, schemas[name])


@pytest.mark.parametrize("scope", [0, 2, 3], ids=["BASE", "REGION", "COMPANY"])
async def test_all_eight_capabilities_same_database(environment, scope):
    app, http = environment
    query = ForecastReadQuery.model_validate(harness.seed.STATE["identities"][scope])
    async with harness.sdk_client(app) as sdk, app.state.sessions() as session:
        discovered = (await sdk.list_tools()).tools
        assert {tool.name for tool in discovered} == set(TOOLS)
        assert len(discovered) == 8
        schemas = {tool.name: tool.output_schema for tool in discovered}
        reader = ForecastIntelligenceReadService(session)
        for name, tool in TOOLS.items():
            if tool.method in ("simulate", "compare"):
                continue
            arguments = {} if tool.method == "quality" else query.model_dump(mode="json")
            request = QualityReadQuery() if tool.method == "quality" else query
            expected = (await getattr(reader, tool.method)(request)).model_dump(mode="json")
            response = await http.get(
                "/api/v1/forecast-intelligence/" + tool.method, params=arguments
            )
            assert response.status_code == 200
            assert response.json() == expected
            await assert_sdk(sdk, name, arguments, expected, schemas)
            if tool.method in ("uncertainty", "attribution"):
                assert expected["status"] == "NOT_AVAILABLE" and expected["data"] is None
        source = (await reader.curve(query)).model_dump(mode="json")
        decision = DecisionSupportService(reader)
        payload = scenario(source)
        for method, name, path, arguments in (
            ("simulate", "simulate_capacity", "simulate-capacity", payload),
            (
                "compare",
                "compare_capacity_scenarios",
                "compare-capacity-scenarios",
                {
                    **{
                        k: v
                        for k, v in payload.items()
                        if k not in ("scenario_id", "scenario_version", "capacity_rows")
                    },
                    "scenarios": [
                        {
                            k: v
                            for k, v in scenario(source, sid, mode, buf, cap).items()
                            if k in ("scenario_id", "scenario_version", "capacity_rows")
                        }
                        for sid, mode, buf, cap in (
                            ("A", "DIRECT", "0", "120"),
                            ("B", "DIRECT", "0", "140"),
                            ("C", "WORKFORCE_DERIVED", "20", "140"),
                        )
                    ],
                },
            ),
        ):
            expected = (await getattr(decision, method)(arguments)).model_dump(mode="json")
            response = await http.post("/api/v1/decision-support/" + path, json=arguments)
            assert response.status_code == 200 and response.json() == expected
            await assert_sdk(sdk, name, arguments, expected, schemas)
            if method == "compare":
                reversed_input = {**arguments, "scenarios": arguments["scenarios"][::-1]}
                assert (await decision.compare(reversed_input)).model_dump(mode="json") == expected
                if scope == 0:
                    values = {r["scenario_id"]: r for r in expected["data"]["scenario_results"]}
                    a, b, c = (values[sid] for sid in "ABC")
                    assert a["total_business_loss"] == "1280"
                    assert b["total_business_loss"] == c["total_business_loss"] == "980"
                    assert b["overload_day_count"] == 4
                    assert b["cumulative_shortfall_kg"] == "140"
                    assert b["max_backlog_kg"] == "120"
                    assert b["ending_backlog_kg"] == "0"
                    for key in (
                        "total_processed_kg",
                        "aggregate_capacity_utilization_decimal",
                        "aggregate_capacity_utilization_numerator_kg",
                        "aggregate_capacity_utilization_denominator_kg",
                    ):
                        assert b[key] == c[key]
                    assert [
                        r["scenario_id"] for r in expected["data"]["comparison"]["rankings"]
                    ] == ["B", "C", "A"]


@pytest.mark.parametrize(
    "mode,buffer,capacity",
    [
        ("DIRECT", None, "140"),
        ("DIRECT", "0", "140"),
        ("DIRECT", "20", "120"),
        ("WORKFORCE_DERIVED", "20", "140"),
        ("DIRECT", "0", "0"),
    ],
)
@pytest.mark.parametrize(
    "planning", ["POINT", "UPPER_PLANNING_BOUND_80", "UPPER_PLANNING_BOUND_90"]
)
async def test_capacity_and_planning_parity(environment, mode, buffer, capacity, planning):
    app, http = environment
    source = harness.seed.STATE["canonical_curves"][0]
    payload = scenario(source, mode=mode, buffer=buffer, capacity=capacity)
    payload["planning_level"] = planning
    async with harness.sdk_client(app) as sdk, app.state.sessions() as session:
        expected = (
            await DecisionSupportService(ForecastIntelligenceReadService(session)).simulate(payload)
        ).model_dump(mode="json")
        response = await http.post("/api/v1/decision-support/simulate-capacity", json=payload)
        assert response.status_code == 200 and response.json() == expected
        result = await harness.sdk_call(sdk, "simulate_capacity", payload)
        assert not result.is_error and result.structured_content == expected
        if planning != "POINT":
            assert expected["status"] == "NOT_AVAILABLE" and expected["data"] is None
        else:
            data = expected["data"]
            assert data["initial_backlog_kg"] == "0"
            opening = Decimal(0)
            for row in data["daily_rows"]:
                assert Decimal(row["opening_backlog_kg"]) == opening
                assert opening + Decimal(row["planning_demand_kg"]) == (
                    Decimal(row["processed_kg"]) + Decimal(row["closing_backlog_kg"])
                )
                opening = Decimal(row["closing_backlog_kg"])
            if capacity == "0":
                assert data["aggregate_capacity_utilization_decimal"] is None


async def test_current_quality_and_historical_scope_are_independent(environment):
    app, http = environment
    async with harness.sdk_client(app) as sdk:
        for mode in ("HISTORICAL_VALIDATION", "CURRENT_PRODUCTION_ACCURACY"):
            response = await http.get(
                "/api/v1/forecast-intelligence/quality", params={"mode": mode}
            )
            result = await harness.sdk_call(sdk, "get_forecast_quality", {"mode": mode})
            assert response.json() == result.structured_content
            value = response.json()
            if mode == "CURRENT_PRODUCTION_ACCURACY":
                assert value["status"] == "NO_CURRENT_ACTUAL" and value["data"] is None
            else:
                assert value["data"]["model_id"] == "V0_15_S5_M1_RIDGE"
                assert [h["horizon"] for h in value["data"]["horizons"]] == [
                    "H1",
                    "H3",
                    "H7",
                    "H15",
                ]
                assert all(
                    h["interval_status"] == "NOT_AVAILABLE" for h in value["data"]["horizons"][:2]
                )
                assert not value["data"]["strict_pit"]
                assert "SYNTHETIC_S6_SERVER_ONLY_CREDENTIAL" not in json.dumps(value)
