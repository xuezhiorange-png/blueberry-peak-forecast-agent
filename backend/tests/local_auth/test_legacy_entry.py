"""Explicit synthetic legacy ingress never becomes a production auth fallback."""

import inspect
import os
import socket
from pathlib import Path

import pytest
import yaml
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from backend.app.core.config import AppSettings
from backend.app.main import app as production_app
from backend.app.main import create_app
from backend.tests.mcp.test_streamable_http import INITIALIZE, rpc
from backend.tests.mcp.test_streamable_http_postgres import running_backend
from backend.tests.support.legacy_test_app import (
    _reject_nonisolated_connection,
    create_legacy_test_app,
    create_live_legacy_test_app,
)


@pytest.mark.parametrize("factory", [create_app, lambda: production_app])
@pytest.mark.parametrize("path", ["/api/v1/trial/forecasts", "/api/v1/blueberry/v1/mcp"])
async def test_l01_l02_production_legacy_default_denial(factory, path):
    async with AsyncClient(transport=ASGITransport(app=factory()), base_url="https://test") as c:
        result = await c.post(path, json={})
        assert result.status_code == 403
        assert result.json()["data"] is None


async def test_l03_environment_cannot_bypass_production(monkeypatch):
    monkeypatch.setenv("BLUEBERRY_LEGACY_SYNTHETIC_TEST", "1")
    monkeypatch.setenv("LOCAL_AUTH_ENABLED", "false")
    assert "controlled" not in inspect.signature(create_app).parameters
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="https://test") as c:
        assert (await c.post("/api/v1/trial/forecasts", json={})).status_code == 403


async def test_l04_l05_real_legacy_sdk_discovery_and_credentials():
    app = create_legacy_test_app(
        AppSettings(blueberry_mcp_connector_shared_secret=SecretStr("SYNTHETIC_LEGACY_KEY")),
        synthetic=True,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        path = "/api/v1/blueberry/v1/mcp"
        assert (await c.post(path, json={})).status_code == 401
        c.headers["X-Blueberry-Connector-Key"] = "SYNTHETIC_LEGACY_KEY"
        initialized = await rpc(c, "initialize", INITIALIZE)
        assert initialized["serverInfo"]["name"] == "blueberry-area-forecast"
        tools = await rpc(c, "tools/list", {})
        assert tools["tools"]
        assert (await c.get("/health/live")).headers["X-Blueberry-Test-Entry"] == "SYNTHETIC_LEGACY"


def test_l07_production_does_not_mount_or_import_test_factory():
    source = Path(inspect.getfile(create_app)).read_text()
    assert "backend.tests" not in source and "legacy_test_app" not in source
    assert not hasattr(production_app.state, "legacy_test_only")


@pytest.mark.parametrize("synthetic", [False, None, "true"])
def test_l08_missing_explicit_synthetic_factory_configuration(synthetic):
    with pytest.raises(ValueError, match="synthetic"):
        create_legacy_test_app(synthetic=synthetic)


def test_l08_live_entry_and_database_fail_closed(monkeypatch):
    monkeypatch.delenv("BLUEBERRY_LEGACY_SYNTHETIC_TEST", raising=False)
    with pytest.raises(ValueError, match="configuration"):
        create_live_legacy_test_app()
    for params in (
        {"host": "remote.example", "database": "blueberry_test_fixture"},
        {"host": "localhost", "database": "blueberry_peak"},
    ):
        with pytest.raises(RuntimeError, match="nonisolated"):
            _reject_nonisolated_connection(None, None, [], params)


def test_ci_legacy_database_jobs_use_explicit_isolated_names():
    root = Path(__file__).resolve().parents[3]
    jobs = yaml.safe_load((root / ".github/workflows/ci.yml").read_text())["jobs"]
    for job, database in (
        ("postgres-task11", "blueberry_test_task11"),
        ("postgres-domain-2", "blueberry_test_domain2"),
    ):
        definition = jobs[job]
        service = definition["services"]["postgres"]
        assert service["env"]["POSTGRES_DB"] == database
        assert database in service["options"]
        for step in definition["steps"]:
            if "POSTGRES_DB" in step.get("env", {}):
                assert step["env"]["POSTGRES_DB"] == database
        _reject_nonisolated_connection(None, None, [], {"host": "localhost", "database": database})


async def test_l09_l10_live_entry_verified_and_owned_process_stops():
    async with running_backend(dict(os.environ)) as client:
        port = client.base_url.port
        response = await client.get("/health/live")
        assert response.status_code == 200
        assert response.headers["X-Blueberry-Test-Entry"] == "SYNTHETIC_LEGACY"
    with socket.socket() as connection:
        assert connection.connect_ex(("127.0.0.1", port)) != 0
