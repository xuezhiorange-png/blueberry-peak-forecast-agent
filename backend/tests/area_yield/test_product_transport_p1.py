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
