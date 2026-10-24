"""Readiness -> real S8/S7 ASGI/auth/PG chain, only explicit SYNTHETIC events."""

import json
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import create_app
from backend.tests.local_auth.conftest import login
from backend.tests.rolling_forecast.inbound_fixture import body
from backend.tests.rolling_forecast.source_readiness_package import create_package
from backend.tests.rolling_forecast.test_postgres import post
from backend.tests.rolling_forecast.test_source_readiness import inspect

pytestmark = [pytest.mark.postgres, pytest.mark.integration]


@pytest.mark.asyncio
async def test_readiness_to_two_saved_origins_and_comparison(pg_auth, tmp_path, record_property):
    auth, factory, _, account, _ = pg_auth
    catalog, path = create_package(tmp_path / "package", principal_id=account.principal_id)
    ready = [inspect(catalog, "synthetic-full", offset=i) for i in (0, 1)]
    assert [r["m1_feature_readiness"] for r in ready] == ["COMPUTABLE", "COMPUTABLE"]
    auth.settings.rolling_forecast_catalog_path = str(path)
    app = create_app(auth.settings)
    app.state.local_auth = auth
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://synthetic.test"
    ) as client:
        assert (await login(client)).status_code == 200
        saved = []
        for i, totals in enumerate((("538.941049", "1031.362335"), ("526.137595", "1002.702182"))):
            response = await post(client, body(i))
            assert response.status_code == 200, response.text
            run = response.json()["data"]
            saved.append(run)
            assert (await client.get(f"/api/v1/rolling-forecast-runs/{run['run_id']}")).json()[
                "data"
            ] == run
            m1 = run["result"]["models"]["M1"]
            assert (m1["H7"]["forecast_total_kg"], m1["H15"]["forecast_total_kg"]) == totals
            for n, window in ((7, "H7"), (15, "H15")):
                assert sum(Decimal(d["kg"]) for d in m1["daily_forecast_kg"][:n]) == Decimal(
                    m1[window]["forecast_total_kg"]
                )
        comparison = (
            await client.get(
                "/api/v1/rolling-forecast-runs/compare",
                params={"left_run_id": saved[0]["run_id"], "right_run_id": saved[1]["run_id"]},
            )
        ).json()["data"]
        assert comparison["models"]["M1"]["status"] == "COMPARABLE"
        assert len(comparison["models"]["M1"]["common_target_daily_delta_kg"]) == 14
        assert (await post(client, body())).json()["data"] == saved[0]
    output = tmp_path / "SYNTHETIC-s9-business-example.json"
    output.write_text(
        json.dumps(dict(readiness=ready, runs=saved, comparison=comparison), indent=2)
    )
    output.chmod(0o600)
    record_property("SYNTHETIC_S9_EXAMPLE", str(output))


@pytest.mark.parametrize("scenario", ["missing-day", "late-record", "partial-member"])
@pytest.mark.asyncio
async def test_incomplete_readiness_agrees_with_runtime_m1_blocker(pg_auth, tmp_path, scenario):
    auth, factory, _, account, _ = pg_auth
    catalog, path = create_package(
        tmp_path / "package", scenario, principal_id=account.principal_id
    )
    assert inspect(catalog, "synthetic-full")["m1_feature_readiness"] == "NOT_COMPUTABLE"
    auth.settings.rolling_forecast_catalog_path = str(path)
    app = create_app(auth.settings)
    app.state.local_auth = auth
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://synthetic.test"
    ) as client:
        assert (await login(client)).status_code == 200
        response = await post(client, body())
        assert response.status_code == 200, response.text
        models = response.json()["data"]["result"]["models"]
        assert models["M0"]["status"] == "COMPUTED"
        assert models["M1"]["status"] == "NOT_COMPUTABLE"
        assert not models["M1"].get("daily_forecast_kg")
