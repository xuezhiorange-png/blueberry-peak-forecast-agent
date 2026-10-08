"""SYNTHETIC=true HTTP parity, resource limits, authorization and isolation."""

from datetime import date

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from backend.app.actual_harvest_import.api_auth import get_actual_harvest_actor
from backend.app.forecast_intelligence import what_if
from backend.app.forecast_intelligence.decision_schemas import BODY_LIMIT, SimulationRequest
from backend.app.forecast_intelligence.decision_service import (
    COST_HASHES,
    adapt_saved_curve,
    cost_contract,
    make_scenario,
)
from backend.app.forecast_intelligence.read_service import ForecastIntelligenceReadService
from backend.tests.forecast_intelligence.test_v0_17_s1_service_read_api import configured_app, query
from backend.tests.forecast_intelligence.test_v0_17_s2_decision_service import (
    comparison_payload,
    request_payload,
    selection,
)

PREFIX = "/api/v1/decision-support"


async def source_and_payload(factory, ids):
    async with factory() as session:
        source = await ForecastIntelligenceReadService(session).curve(query(ids[0]))
    return source, request_payload(source)


@pytest.mark.parametrize("cost_id", COST_HASHES)
async def test_business_loss_exposure_no_amount(hierarchy_factory, monkeypatch, cost_id):
    app = configured_app(hierarchy_factory, monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(
            PREFIX + "/business-loss",
            params={
                "cost_contract_id": cost_id,
                "expected_cost_contract_hash": COST_HASHES[cost_id],
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["data"]["total_business_loss"] is None
        assert r.json()["loss_unit"] == "SYNTHETIC_LOSS_UNIT"
        assert r.json()["data"]["cost_contract"]["synthetic"] is True


async def test_http_complete_result_engine_parity(hierarchy_factory, source_ids, monkeypatch):
    source, payload = await source_and_payload(hierarchy_factory, source_ids)
    app = configured_app(hierarchy_factory, monkeypatch)
    curve, _ = adapt_saved_curve(source, selection(payload))
    expected = what_if.simulate(
        make_scenario(
            curve,
            selection(payload),
            cost_contract(selection(payload)),
            SimulationRequest.model_validate(payload),
        )
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(PREFIX + "/simulate-capacity", json=payload)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["data"] == expected
        assert result["engine_result_hash"] == expected["result_hash"]
        assert result["source_result_hash"] == source.source_result_hash
        assert result["source_read_projection_hash"] == source.projection_hash
        assert (
            len(
                {
                    result["source_result_hash"],
                    result["adapter_authority_hash"],
                    result["engine_result_hash"],
                    result["projection_hash"],
                }
            )
            == 4
        )
        compared = await client.post(
            PREFIX + "/compare-capacity-scenarios", json=comparison_payload(payload)
        )
        assert compared.status_code == 200, compared.text
        assert compared.json()["data"]["comparison"]["scenario_comparison_status"] == "COMPARABLE"


@pytest.mark.parametrize("endpoint", ["simulate-capacity", "compare-capacity-scenarios"])
@pytest.mark.parametrize("level", ["UPPER_PLANNING_BOUND_80", "UPPER_PLANNING_BOUND_90"])
async def test_http_upper_unavailable(hierarchy_factory, source_ids, monkeypatch, endpoint, level):
    _, payload = await source_and_payload(hierarchy_factory, source_ids)
    payload["planning_level"] = level
    if endpoint.startswith("compare"):
        payload = comparison_payload(payload)
    app = configured_app(hierarchy_factory, monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(PREFIX + "/" + endpoint, json=payload)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "NOT_AVAILABLE"
        assert r.json()["data"] is None


@pytest.mark.parametrize(
    "field,value,status",
    [
        ("expected_source_result_hash", "a" * 64, 409),
        ("expected_source_result_hash", None, 422),
        ("expected_cost_contract_hash", "a" * 64, 409),
        ("cost_contract_id", "UNKNOWN", 404),
        ("planning_level", "P80", 422),
        ("planning_level", "P50", 422),
        ("forecast_values", ["1"], 422),
        ("actual_values", ["1"], 422),
        ("c_under", "1", 422),
        ("initial_backlog_kg", "1", 422),
    ],
)
async def test_authority_input_fail_closed(
    hierarchy_factory, source_ids, monkeypatch, field, value, status
):
    _, payload = await source_and_payload(hierarchy_factory, source_ids)
    payload[field] = value
    app = configured_app(hierarchy_factory, monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(PREFIX + "/simulate-capacity", json=payload)
        assert r.status_code == status, r.text
        assert r.json()["data"] is None


@pytest.mark.parametrize(
    "field,value,status",
    [
        ("run_id", 999999, 404),
        ("run_id", 0, 422),
        ("forecast_family", "OTHER", 409),
        ("baseline_id", "OTHER", 409),
        ("policy_version", "OTHER", 409),
        ("entity_id", "OTHER", 409),
        ("origin_date", "2026-01-02", 409),
        ("target_season", "2024-2025", 409),
        ("hierarchy_level", "FACTORY", 422),
        ("cursor", "x", 422),
    ],
)
async def test_full_source_selection_enforced(
    hierarchy_factory, source_ids, monkeypatch, field, value, status
):
    _, payload = await source_and_payload(hierarchy_factory, source_ids)
    payload["forecast_selection"][field] = value
    app = configured_app(hierarchy_factory, monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(PREFIX + "/simulate-capacity", json=payload)
        assert r.status_code == status, r.text


@pytest.mark.parametrize(
    "endpoint", ["business-loss", "simulate-capacity", "compare-capacity-scenarios"]
)
async def test_permission_precedes_source_read(
    hierarchy_factory, source_ids, monkeypatch, endpoint
):
    _, payload = await source_and_payload(hierarchy_factory, source_ids)
    app = configured_app(hierarchy_factory, monkeypatch, "may_read_quality")

    async def forbidden(*args, **kwargs):
        raise AssertionError("SOURCE_READ_BEFORE_PERMISSION")

    monkeypatch.setattr(ForecastIntelligenceReadService, "curve", forbidden)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        if endpoint == "business-loss":
            r = await client.get(
                PREFIX + "/" + endpoint,
                params={
                    "cost_contract_id": payload["cost_contract_id"],
                    "expected_cost_contract_hash": payload["expected_cost_contract_hash"],
                },
            )
        else:
            r = await client.post(
                PREFIX + "/" + endpoint,
                json=comparison_payload(payload) if endpoint.startswith("compare") else payload,
            )
        assert r.status_code == 403, r.text


@pytest.mark.parametrize("status", [401, 503])
async def test_auth_failure_sanitized(hierarchy_factory, source_ids, monkeypatch, status):
    _, payload = await source_and_payload(hierarchy_factory, source_ids)
    app = configured_app(hierarchy_factory, monkeypatch)

    def failure():
        raise HTTPException(status, detail="token=SECRET /private/path SQL")

    app.dependency_overrides[get_actual_harvest_actor] = failure
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(PREFIX + "/simulate-capacity", json=payload)
        assert r.status_code == status, r.text
        assert "SECRET" not in r.text and "/private/" not in r.text


@pytest.mark.parametrize("database", [False, True])
async def test_internal_failure_sanitized(hierarchy_factory, source_ids, monkeypatch, database):
    _, payload = await source_and_payload(hierarchy_factory, source_ids)
    app = configured_app(hierarchy_factory, monkeypatch)

    async def failure(*args, **kwargs):
        if database:
            raise OperationalError("SQL secret", {}, Exception("token=SECRET /private/path"))
        raise RuntimeError("token=SECRET /private/path")

    monkeypatch.setattr(ForecastIntelligenceReadService, "curve", failure)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(PREFIX + "/simulate-capacity", json=payload)
        assert r.status_code == 503, r.text
        assert "SECRET" not in r.text and "SQL" not in r.text and "/private/" not in r.text


async def test_request_body_limit_counts_actual_bytes(hierarchy_factory, monkeypatch):
    app = configured_app(hierarchy_factory, monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:

        async def chunks():
            yield b" " * (BODY_LIMIT // 2)
            yield b" " * (BODY_LIMIT // 2 + 1)

        r = await client.post(
            PREFIX + "/simulate-capacity",
            content=chunks(),
            headers={"Content-Type": "application/json", "Content-Length": "1"},
        )
        assert r.status_code == 413
        r = await client.post(
            PREFIX + "/simulate-capacity",
            content=b" " * BODY_LIMIT,
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 422


@pytest.mark.parametrize("count,status", [(1, 422), (2, 200), (20, 200), (21, 422)])
async def test_bounded_comparison(hierarchy_factory, source_ids, monkeypatch, count, status):
    _, payload = await source_and_payload(hierarchy_factory, source_ids)
    app = configured_app(hierarchy_factory, monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            PREFIX + "/compare-capacity-scenarios", json=comparison_payload(payload, count)
        )
        assert r.status_code == status, r.text


async def test_duplicate_scenarios_not_ranked(hierarchy_factory, source_ids, monkeypatch):
    _, payload = await source_and_payload(hierarchy_factory, source_ids)
    payload = comparison_payload(payload)
    payload["scenarios"][1]["scenario_id"] = payload["scenarios"][0]["scenario_id"]
    app = configured_app(hierarchy_factory, monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(PREFIX + "/compare-capacity-scenarios", json=payload)
        assert r.status_code == 422, r.text
        assert r.json()["data"] is None


async def test_damaged_saved_rows_fail_closed(hierarchy_factory, source_ids, monkeypatch):
    _, payload = await source_and_payload(hierarchy_factory, source_ids)
    async with hierarchy_factory() as session, session.begin():
        # Isolated SYNTHETIC corruption injection, matching the existing S1 custody test.
        await session.execute(text("DROP TRIGGER operational_peak_forecast_daily_update"))
        await session.execute(
            text("UPDATE operational_peak_forecast_daily SET predicted_kg='999' WHERE run_id=:id"),
            {"id": source_ids[0]},
        )
    app = configured_app(hierarchy_factory, monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(PREFIX + "/simulate-capacity", json=payload)
        assert r.status_code == 409, r.text


async def test_partial_saved_window_only_computes_available_dates(
    hierarchy_factory, synthetic_authority, monkeypatch
):
    from backend.app.forecast_quality.operational_peak import (
        OperationalPeakForecastRequest,
        forecast_operational_peak,
    )
    from backend.app.forecast_quality.operational_peak_persistence import (
        OperationalPeakRunRepository,
        execution_hash,
        request_snapshot,
    )

    request = OperationalPeakForecastRequest("A1", "2025-2026", date(2026, 4, 14))
    value = forecast_operational_peak(
        request, synthetic_authority.registry, synthetic_authority.reference_profile
    )
    snapshot = request_snapshot(request)
    async with hierarchy_factory() as session, session.begin():
        saved = await OperationalPeakRunRepository(session).save(
            snapshot=snapshot,
            result=value,
            execution_id=execution_hash(
                snapshot, synthetic_authority.authority_hash, synthetic_authority.policy_version
            ),
            authority_hash=synthetic_authority.authority_hash,
            rerun_of_run_id=None,
        )
    async with hierarchy_factory() as session:
        source = await ForecastIntelligenceReadService(session).curve(
            query(saved.run.run_id, origin_date=date(2026, 4, 14))
        )
    payload = request_payload(source)
    app = configured_app(hierarchy_factory, monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(PREFIX + "/simulate-capacity", json=payload)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "PARTIAL"
        assert r.json()["available_day_count"] == r.json()["data"]["day_count"] == 1
        assert r.json()["data"]["forecast_end_date"] == "2026-04-15"


def test_openapi_only_three_s2_capabilities_and_bounded_inputs(hierarchy_factory, monkeypatch):
    app = configured_app(hierarchy_factory, monkeypatch)
    paths = {k: v for k, v in app.openapi()["paths"].items() if k.startswith(PREFIX)}
    assert {k: set(v) for k, v in paths.items()} == {
        PREFIX + "/business-loss": {"get"},
        PREFIX + "/simulate-capacity": {"post"},
        PREFIX + "/compare-capacity-scenarios": {"post"},
    }
    body = paths[PREFIX + "/compare-capacity-scenarios"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    assert body["properties"]["scenarios"]["maxItems"] == 20
    assert body["properties"]["scenarios"]["items"]["properties"]["capacity_rows"]["maxItems"] == 15


@pytest.mark.parametrize("cost_id", COST_HASHES)
async def test_all_synthetic_weights_http_engine_parity(
    hierarchy_factory, source_ids, monkeypatch, cost_id
):
    source, payload = await source_and_payload(hierarchy_factory, source_ids)
    payload["cost_contract_id"] = cost_id
    payload["expected_cost_contract_hash"] = COST_HASHES[cost_id]
    curve, _ = adapt_saved_curve(source, selection(payload))
    expected = what_if.simulate(
        make_scenario(
            curve,
            selection(payload),
            cost_contract(selection(payload)),
            SimulationRequest.model_validate(payload),
        )
    )
    app = configured_app(hierarchy_factory, monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(PREFIX + "/simulate-capacity", json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["data"] == expected


@pytest.mark.parametrize("capacity,status", [("0", 200), ("9" * 50 + ".1", 422)])
async def test_zero_capacity_and_exact_precision_failure(
    hierarchy_factory, source_ids, monkeypatch, capacity, status
):
    _, payload = await source_and_payload(hierarchy_factory, source_ids)
    for row in payload["capacity_rows"]:
        row["daily_handling_capacity_kg"] = capacity
        row["buffer_handling_capacity_kg"] = "0" if capacity == "0" else "0.1"
    app = configured_app(hierarchy_factory, monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(PREFIX + "/simulate-capacity", json=payload)
    assert response.status_code == status, response.text
    if status == 200:
        result = response.json()["data"]
        assert result["aggregate_capacity_utilization_decimal"] is None
        assert result["aggregate_capacity_utilization_denominator_kg"] == "0"
        assert result["daily_rows"][0]["opening_backlog_kg"] == "0"
        assert all(r["capacity_utilization_decimal"] is None for r in result["daily_rows"])
    else:
        assert response.json()["code"] == "AUTHORITATIVE_PRECISION_EXCEEDED"


async def test_no_actor_configuration_is_service_unavailable(hierarchy_factory, monkeypatch):
    app = configured_app(hierarchy_factory, monkeypatch)
    monkeypatch.delenv("TRIAL_ACTOR_IDENTITY")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            PREFIX + "/business-loss",
            params={
                "cost_contract_id": "SYNTHETIC_BALANCED_R1",
                "expected_cost_contract_hash": COST_HASHES["SYNTHETIC_BALANCED_R1"],
            },
        )
        assert response.status_code == 503, response.text
        response = await client.get(PREFIX + "/business-loss?x=" + "x" * 8193)
        assert response.status_code == 422


async def test_canonical_source_read_precedes_capacity_validation(
    hierarchy_factory, source_ids, monkeypatch
):
    _, payload = await source_and_payload(hierarchy_factory, source_ids)
    payload["capacity_rows"][0]["daily_handling_capacity_kg"] = "NaN"
    calls = []
    original = ForecastIntelligenceReadService.curve

    async def tracked(self, query):
        calls.append(query.run_id)
        return await original(self, query)

    monkeypatch.setattr(ForecastIntelligenceReadService, "curve", tracked)
    app = configured_app(hierarchy_factory, monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(PREFIX + "/simulate-capacity", json=payload)
    assert response.status_code == 422
    assert calls == [source_ids[0]]
