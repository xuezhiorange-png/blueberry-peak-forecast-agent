"""SYNTHETIC=true. Fail closed using real canonical records and real MCP SDK."""

# ruff: noqa: F811
import pytest

from backend.tests.e2e.test_v0_17_s6_cross_surface_parity import (
    environment,  # noqa: F401 -- shared isolated database fixture
    scenario,
)
from frontend.e2e.support import s6_api as harness

pytestmark = [pytest.mark.unit, pytest.mark.contract]


@pytest.mark.parametrize(
    "field,value",
    [
        ("forecast_family", "SYNTHETIC_WRONG_FAMILY"),
        ("baseline_id", "SYNTHETIC_WRONG_BASELINE"),
        ("policy_version", "SYNTHETIC_WRONG_POLICY"),
        ("target_season", "2024-2025"),
        ("origin_date", "2026-01-02"),
        ("expected_source_result_hash", "0" * 64),
    ],
)
async def test_drifted_identity_http_conflict_sdk_forbidden(environment, field, value):
    app, http = environment
    query = {**harness.seed.STATE["identities"][0], field: value}
    response = await http.get("/api/v1/forecast-intelligence/curve", params=query)
    assert response.status_code == 409
    async with harness.sdk_client(app) as sdk:
        result = await harness.sdk_call(sdk, "get_forecast_curve", query)
        assert result.is_error and result.structured_content["code"] == "FORBIDDEN"
    # A failed read must not poison the next valid read.
    valid = await http.get(
        "/api/v1/forecast-intelligence/curve", params=harness.seed.STATE["identities"][0]
    )
    assert valid.status_code == 200


@pytest.mark.parametrize(
    "failure", ["missing_cost", "unknown_cost", "cost_hash", "decimal", "dates", "extra_forecast"]
)
async def test_invalid_decision_never_returns_result(environment, failure):
    app, http = environment
    payload = scenario(harness.seed.STATE["canonical_curves"][0])
    expected = 422
    if failure == "missing_cost":
        del payload["cost_contract_id"]
    elif failure == "unknown_cost":
        payload["cost_contract_id"] = "SYNTHETIC_UNKNOWN_R1"
        expected = 404
    elif failure == "cost_hash":
        payload["expected_cost_contract_hash"] = "0" * 64
        expected = 409
    elif failure == "decimal":
        payload["capacity_rows"][0]["daily_handling_capacity_kg"] = "NaN"
    elif failure == "dates":
        payload["capacity_rows"][1]["date"] = payload["capacity_rows"][0]["date"]
    else:
        payload["forecast_curve"] = []
    response = await http.post("/api/v1/decision-support/simulate-capacity", json=payload)
    assert response.status_code == expected
    assert "engine_result_hash" not in response.json()
    async with harness.sdk_client(app) as sdk:
        result = await harness.sdk_call(sdk, "simulate_capacity", payload)
        assert result.is_error
        assert "engine_result_hash" not in result.structured_content
