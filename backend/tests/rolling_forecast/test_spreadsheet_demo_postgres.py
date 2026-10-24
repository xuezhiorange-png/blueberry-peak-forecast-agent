"""Real application/auth/PG chain, only registered SYNTHETIC workbook identities."""

import hashlib

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import create_app
from backend.app.rolling_forecast import spreadsheet_demo as demo
from backend.tests.local_auth.conftest import login
from backend.tests.rolling_forecast.spreadsheet_demo_package import create_demo
from backend.tests.rolling_forecast.test_spreadsheet_demo import bound

pytestmark = [pytest.mark.postgres, pytest.mark.integration]
ROOT = "/api/v1/rolling-forecast-runs"


@pytest.mark.asyncio
async def test_bound_workbooks_issue_reload_compare_export_and_guards(
    pg_auth, tmp_path, record_property
):
    auth, _, _, account, _ = pg_auth
    _, catalog, manifest_path = create_demo(tmp_path / "SYNTHETIC", account.principal_id)
    auth.settings.app_env = "test"
    auth.settings.rolling_forecast_catalog_path = str(catalog)
    auth.settings.pre_data_demo_manifest_path = str(manifest_path)
    auth.settings.pre_data_demo_manifest_sha256 = hashlib.sha256(
        manifest_path.read_bytes()
    ).hexdigest()
    manifest = demo.Manifest.model_validate_json(manifest_path.read_bytes())
    app = create_app(auth.settings)
    app.state.local_auth = auth
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://synthetic.test"
    ) as client:
        assert (await client.get(ROOT + "/spreadsheet-demo")).status_code == 401
        assert (await login(client)).status_code == 200

        async def post(action, payload):
            token = (await client.get("/api/v1/auth/csrf")).json()["data"]["csrf_token"]
            return await client.post(
                ROOT + "/spreadsheet-demo/" + action,
                json=payload,
                headers={"Origin": "https://synthetic.test", "X-CSRF-Token": token},
            )

        asset = (await client.get(ROOT + "/spreadsheet-demo")).json()["data"]
        assert (
            "path" not in asset
            and asset["file_sha256"] == manifest.scenarios["complete"].assets["xlsx"].sha256
        )
        payload = bound(manifest.scenarios["complete"]).model_dump(mode="json")
        assert (await post("issue", {**payload, "file_sha256": "a" * 64})).status_code == 422
        assert (await post("issue", {**payload, "rows": [["123"]]})).status_code == 422
        assert (await post("verify", payload)).json()["data"]["readiness"][
            "m1_feature_readiness"
        ] == "COMPUTABLE"
        saved = []
        for origin in demo.ORIGINS:
            response = await post("issue", {**payload, "origin": origin})
            assert response.status_code == 200, response.text
            run = response.json()["data"]
            assert (await client.get(f"{ROOT}/{run['run_id']}")).json()["data"] == run
            saved.append(run)
        assert saved[0]["result"]["models"]["M1"]["H7"]["forecast_total_kg"] == "538.941049"
        assert saved[1]["result"]["models"]["M1"]["H15"]["forecast_total_kg"] == "1002.702182"
        comparison = (
            await client.get(
                ROOT + "/compare",
                params={"left_run_id": saved[0]["run_id"], "right_run_id": saved[1]["run_id"]},
            )
        ).json()["data"]
        assert len(comparison["models"]["M1"]["common_target_daily_delta_kg"]) == 14
        for format in ("html", "csv"):
            response = await client.get(
                f"{ROOT}/{saved[0]['run_id']}/report",
                params={"format": format, "comparison_run_id": saved[1]["run_id"]},
            )
            assert response.status_code == 200, response.text
            exported = response.json()["data"]
            assert exported["result_hash"] == saved[0]["result_hash"]
            assert (
                "538.941049" in exported["content"]
                and "SYNTHETIC-models.json" not in exported["content"]
            )
        for scenario in ("missing-day", "late-record", "basis-conflict"):
            bad = bound(manifest.scenarios[scenario], scenario=scenario).model_dump(mode="json")
            response = await post("verify", bad)
            assert response.status_code == 200, response.text
            assert response.json()["data"]["readiness"]["m1_feature_readiness"] != "COMPUTABLE"
            assert (await post("issue", bad)).json()["code"] == "SYNTHETIC_SOURCE_NOT_READY"
        example = tmp_path / "SYNTHETIC-demo-business.json"
        import json

        example.write_text(json.dumps(dict(runs=saved, comparison=comparison), indent=2))
        record_property("SYNTHETIC_BUSINESS_EXAMPLE", str(example))
        auth.settings.app_env = "production"
        assert (await post("issue", payload)).json()["code"] == "SYNTHETIC_DEMO_UNAVAILABLE"
