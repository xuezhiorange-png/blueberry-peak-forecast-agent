"""Real ASGI, auth, PostgreSQL, immutable rows and independent SYNTHETIC review."""

import json
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import create_app
from backend.tests.local_auth.conftest import login
from backend.tests.rolling_forecast.inbound_fixture import body, fixture
from backend.tests.rolling_forecast.test_postgres import post

pytestmark = [pytest.mark.postgres, pytest.mark.integration]


@pytest.mark.asyncio
async def test_inbound_issue_persist_compare_and_separate_review(
    pg_auth, tmp_path, record_property
):
    auth, factory, _, account, _ = pg_auth
    catalog = fixture(tmp_path, account.principal_id)
    path = tmp_path / "catalog.json"
    path.write_text(catalog.model_dump_json())
    path.chmod(0o600)
    auth.settings.rolling_forecast_catalog_path = str(path)
    app = create_app(auth.settings)
    app.state.local_auth = auth
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://synthetic.test"
    ) as client:
        assert (await login(client)).status_code == 200
        a = await post(client, body())
        assert a.status_code == 200, a.text
        saved = a.json()["data"]
        assert "manifest_path" not in saved["input"]["observation_snapshot"]
        assert (await post(client, body())).json()["data"] == saved
        b = await post(client, body(1))
        assert b.status_code == 200, b.text
        newer = b.json()["data"]
        assert (await client.get(f"/api/v1/rolling-forecast-runs/{saved['run_id']}")).json()[
            "data"
        ] == saved
        compared = (
            await client.get(
                "/api/v1/rolling-forecast-runs/compare",
                params={"left_run_id": saved["run_id"], "right_run_id": newer["run_id"]},
            )
        ).json()["data"]
        assert len(compared["models"]["M1"]["common_target_daily_delta_kg"]) == 14
        url = f"/api/v1/rolling-forecast-runs/{saved['run_id']}/review"
        options = await client.get(url)
        assert options.status_code == 200, options.text
        assert options.json()["data"]["options"][0]["status"] == "PREFLIGHT_ELIGIBLE"
        token = (await client.get("/api/v1/auth/csrf")).json()["data"]["csrf_token"]
        response = await client.post(
            url,
            json={"label_snapshot_reference": "SYNTHETIC-INBOUND-LABELS"},
            headers={"Origin": "https://synthetic.test", "X-CSRF-Token": token},
        )
        assert response.status_code == 200, response.text
        review = response.json()["data"]
        assert review["status"] == "SCORED"
        assert review["evaluation_label_quantity_basis"] == "RECORDED_INBOUND_WEIGHT"
        assert len(review["actual_daily"]) == 15
        for window, n in (("H7_PREFIX", 7), ("H15_LOCAL", 15)):
            metrics = review["groups"][window]["metrics"]
            assert len(metrics) == 10
            for model, name in (("M0", "baseline"), ("M1", "candidate")):
                predicted = saved["result"]["models"][model]["daily_forecast_kg"][:n]
                actual = review["actual_daily"][:n]
                numerator = sum(
                    abs(Decimal(p["kg"]) - Decimal(a["quantity_kg"]))
                    for p, a in zip(predicted, actual, strict=True)
                )
                denominator = sum(Decimal(a["quantity_kg"]) for a in actual)
                assert Decimal(metrics["DAILY_WAPE"][name]["numerator"]) == numerator
                assert Decimal(metrics["DAILY_WAPE"][name]["denominator"]) == denominator
        example = tmp_path / "SYNTHETIC-s8-business-example.json"
        example.write_text(
            json.dumps(dict(run_1=saved, run_2=newer, comparison=compared, review=review), indent=2)
        )
        example.chmod(0o600)
        record_property("SYNTHETIC_S8_EXAMPLE", str(example))
        # A read/issue capability does not imply access to labels or review metadata.
        policy = catalog.model_dump(mode="json")
        policy["capabilities"][0]["operations"] = ["read", "issue", "compare"]
        path.write_text(json.dumps(policy))
        assert (await client.get(url)).status_code == 403
        assert (
            await client.post(
                url,
                json={"label_snapshot_reference": "SYNTHETIC-INBOUND-LABELS"},
                headers={"Origin": "https://synthetic.test", "X-CSRF-Token": token},
            )
        ).status_code == 403


@pytest.mark.parametrize("problem", ["source_binding", "immature_labels", "label_binding"])
@pytest.mark.asyncio
async def test_admission_rejects_before_quantity_reads(pg_auth, tmp_path, monkeypatch, problem):
    from backend.app.rolling_forecast import observations

    auth, factory, _, account, _ = pg_auth
    catalog = fixture(tmp_path, account.principal_id)
    policy = catalog.model_dump(mode="json")
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(policy))
    path.chmod(0o600)
    auth.settings.rolling_forecast_catalog_path = str(path)
    app = create_app(auth.settings)
    app.state.local_auth = auth
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://synthetic.test"
    ) as client:
        assert (await login(client)).status_code == 200
        saved = (await post(client, body())).json()["data"]
        context = policy["contexts"][0]
        if problem == "source_binding":
            context["snapshots"][0]["target_binding"] = None
        elif problem == "immature_labels":
            context["review_snapshots"][0]["mature_through"] = "2026-11-19"
        else:
            context["review_snapshots"][0]["target_binding"] = None
        path.write_text(json.dumps(policy))
        reads = []

        async def forbidden(*args, **kwargs):
            reads.append(True)
            raise AssertionError("UNAUTHORIZED_QUANTITY_READ")

        monkeypatch.setattr(observations, "load", forbidden)
        if problem == "source_binding":
            response = await post(client, body())
            assert response.json()["code"] == "SOURCE_BASIS_UNVERIFIED"
        else:
            url = f"/api/v1/rolling-forecast-runs/{saved['run_id']}/review"
            options = await client.get(url)
            assert options.json()["data"]["options"][0]["status"] == "NOT_SCORABLE"
            token = (await client.get("/api/v1/auth/csrf")).json()["data"]["csrf_token"]
            response = await client.post(
                url,
                json={"label_snapshot_reference": "SYNTHETIC-INBOUND-LABELS"},
                headers={"Origin": "https://synthetic.test", "X-CSRF-Token": token},
            )
            assert response.json()["code"] == (
                "LABELS_NOT_MATURE"
                if problem == "immature_labels"
                else "CROSS_SOURCE_TARGET_BASIS_UNVERIFIED"
            )
        assert response.status_code == 422, response.text
        assert not reads
