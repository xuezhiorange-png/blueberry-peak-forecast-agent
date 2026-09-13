"""All transports use the same hash-bound service and normal actor dependency."""

import hashlib
import json
import subprocess
import sys

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.agent.orchestration import AgentOrchestrator
from backend.app.area_yield.product_authority import forecast_area_product
from backend.app.main import create_app
from backend.tests.area_yield.test_product_p1 import bundle, request


@pytest.fixture
def configured(tmp_path, monkeypatch):
    raw = json.dumps(bundle()).encode()
    path = tmp_path / "authority.json"
    path.write_bytes(raw)
    monkeypatch.setenv("AREA_YIELD_AUTHORITY_PATH", str(path))
    monkeypatch.setenv("AREA_YIELD_AUTHORITY_SHA256", hashlib.sha256(raw).hexdigest())
    monkeypatch.setenv("TRIAL_ACTOR_IDENTITY", "local-product-fixture")
    monkeypatch.setenv("TRIAL_ACTOR_ALLOWED_SOURCE_SYSTEMS", "trial-api")
    monkeypatch.setenv("TRIAL_ACTOR_ALLOWED_CHANNELS", "api")
    monkeypatch.setenv("TRIAL_ACTOR_PERMISSIONS", "may_create_forecast")
    return path


def test_agent_core_and_fresh_cli_identical(configured):
    expected = forecast_area_product(request()).model_dump(mode="json")
    assert AgentOrchestrator.forecast_by_area(request()).model_dump(mode="json") == expected
    run = subprocess.run(
        [sys.executable, "-m", "backend.app.cli", "area-forecast", "--input", "-"],
        input=request().model_dump_json(),
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(run.stdout) == expected


@pytest.mark.asyncio
async def test_http_same_service_no_dependency_override(configured):
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://local") as c:
        response = await c.post("/api/v1/trial/forecasts", json=request().model_dump(mode="json"))
    assert response.status_code == 200, response.text
    assert response.json() == forecast_area_product(request()).model_dump(mode="json")


@pytest.mark.asyncio
async def test_http_permission_and_invalid_area(configured, monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://local") as c:
        body = request().model_dump(mode="json")
        body["productive_area_mu"] = "NaN"
        assert (await c.post("/api/v1/trial/forecasts", json=body)).status_code == 422
        monkeypatch.setenv("TRIAL_ACTOR_PERMISSIONS", "may_read_forecast")
        assert (
            await c.post("/api/v1/trial/forecasts", json=request().model_dump(mode="json"))
        ).status_code == 404  # Existing trial contract hides unauthorized resources.


def test_missing_or_corrupt_private_authority(configured, monkeypatch):
    monkeypatch.setenv("AREA_YIELD_AUTHORITY_SHA256", "0" * 64)
    with pytest.raises(ValueError, match="HASH"):
        forecast_area_product(request())


def cli(body):
    return subprocess.run(
        [sys.executable, "-m", "backend.app.cli", "area-forecast", "--input", "-"],
        input=json.dumps(body),
        text=True,
        capture_output=True,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    ["path_missing", "hash_missing", "unreadable", "outer_hash", "payload_hash", "invalid_json"],
)
async def test_server_authority_is_503_and_cli_configuration_error(
    configured, monkeypatch, failure
):
    if failure == "path_missing":
        monkeypatch.delenv("AREA_YIELD_AUTHORITY_PATH")
    elif failure == "hash_missing":
        monkeypatch.delenv("AREA_YIELD_AUTHORITY_SHA256")
    elif failure == "unreadable":
        monkeypatch.setenv("AREA_YIELD_AUTHORITY_PATH", str(configured / "missing"))
    elif failure == "outer_hash":
        monkeypatch.setenv("AREA_YIELD_AUTHORITY_SHA256", "0" * 64)
    else:
        b = bundle()
        b["hash"] = "0" * 64
        raw = json.dumps(b).encode() if failure == "payload_hash" else b"not-json"
        configured.write_bytes(raw)
        monkeypatch.setenv("AREA_YIELD_AUTHORITY_SHA256", hashlib.sha256(raw).hexdigest())
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://local") as c:
        r = await c.post("/api/v1/trial/forecasts", json=request().model_dump(mode="json"))
    assert r.status_code == 503, r.text
    assert r.json()["code"] == "AREA_FORECAST_AUTHORITY_UNAVAILABLE"
    run = cli(request().model_dump(mode="json"))
    assert run.returncode == 3
    assert "AREA_FORECAST_AUTHORITY_UNAVAILABLE:" in run.stderr


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "farm,season,reason",
    [
        ("new", "2026-2027", "UNSUPPORTED_CANONICAL_FARM"),
        ("known", "2027-2028", "PRIOR_SEASON_HISTORY_MISSING"),
    ],
)
async def test_business_failure_has_same_reason_http_cli_python(configured, farm, season, reason):
    body = request(farm).model_dump(mode="json")
    body["target_season"] = season
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://local") as c:
        r = await c.post("/api/v1/trial/forecasts", json=body)
    assert r.status_code == 422
    assert r.json()["code"] == "AREA_FORECAST_UNSUPPORTED_FARM_HISTORY"
    assert r.json()["details"]["reason"] == reason
    run = cli(body)
    assert run.returncode == 2 and reason in run.stderr
    from backend.app.area_yield.product import AreaDrivenForecastRequest

    with pytest.raises(ValueError, match=reason):
        AgentOrchestrator.forecast_by_area(AreaDrivenForecastRequest(**body))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"productive_area_mu": "0"},
        {"target_season": "2026-2028"},
        {"season_start": "2026-10-01", "season_end": "2026-10-05"},
        {"as_of": "2026-07-01"},
    ],
)
async def test_bad_request_is_422_not_authority_failure(configured, changes):
    body = {**request().model_dump(mode="json"), **changes}
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://local") as c:
        r = await c.post("/api/v1/trial/forecasts", json=body)
    assert r.status_code == 422
    run = cli(body)
    assert run.returncode == 2
    assert "AREA_FORECAST_REQUEST_INVALID:" in run.stderr
