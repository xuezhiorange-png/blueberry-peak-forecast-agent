"""REST contract tests for the S6 operational peak product path."""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from backend.app.db.session import get_db_session
from backend.app.main import create_app


def _body() -> dict[str, str]:
    return {
        "base_id": "base-yangliu",
        "target_season": "2026-2027",
        "origin_date": "2027-03-31",
    }


def _app(factory):
    app = create_app()

    async def sessions():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = sessions
    return app


async def test_create_get_list_daily_and_idempotency(s6_factory, s6_authority, monkeypatch):
    monkeypatch.setenv("TRIAL_ACTOR_IDENTITY", "s6-api")
    monkeypatch.setenv("TRIAL_ACTOR_ALLOWED_SOURCE_SYSTEMS", "trial-api")
    monkeypatch.setenv("TRIAL_ACTOR_ALLOWED_CHANNELS", "api")
    monkeypatch.setenv("TRIAL_ACTOR_PERMISSIONS", "may_create_forecast,may_read_forecast")
    app = _app(s6_factory)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://local") as client:
        first = await client.post("/api/v1/operational-peak-forecast-runs", json=_body())
        assert first.status_code == 200, first.text
        first_body = first.json()
        run_id = first_body["run"]["run_id"]
        assert first_body["result"]["forecast_7d"]["total_kg"] == "2758.000000"
        assert first_body["result"]["forecast_15d"]["total_kg"] == "5910.000000"

        repeat = await client.post("/api/v1/operational-peak-forecast-runs", json=_body())
        assert repeat.status_code == 200
        assert repeat.json()["reused_existing_run"] is True
        assert repeat.json()["run"]["run_id"] == run_id

        got = await client.get(f"/api/v1/operational-peak-forecast-runs/{run_id}")
        daily = await client.get(f"/api/v1/operational-peak-forecast-runs/{run_id}/daily")
        history = await client.get("/api/v1/operational-peak-forecast-runs", params={"limit": 20})
        assert got.status_code == daily.status_code == history.status_code == 200
        assert got.json() == first_body
        assert len(daily.json()["daily_forecast"]) == 15
        assert history.json()["items"][0]["run_id"] == run_id
        assert "daily_forecast" not in history.text

        monkeypatch.delenv("OPERATIONAL_PEAK_AUTHORITY_PATH")
        assert (
            await client.get(f"/api/v1/operational-peak-forecast-runs/{run_id}")
        ).status_code == 200
        assert (
            await client.get(f"/api/v1/operational-peak-forecast-runs/{run_id}/daily")
        ).status_code == 200


async def test_request_and_authority_errors_are_distinct(s6_factory, s6_authority, monkeypatch):
    monkeypatch.setenv("TRIAL_ACTOR_IDENTITY", "s6-api")
    monkeypatch.setenv("TRIAL_ACTOR_ALLOWED_SOURCE_SYSTEMS", "trial-api")
    monkeypatch.setenv("TRIAL_ACTOR_ALLOWED_CHANNELS", "api")
    monkeypatch.setenv("TRIAL_ACTOR_PERMISSIONS", "may_create_forecast,may_read_forecast")
    app = _app(s6_factory)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://local") as client:
        unknown = await client.post(
            "/api/v1/operational-peak-forecast-runs",
            json={**_body(), "base_id": "unknown"},
        )
        assert unknown.status_code == 422 and unknown.json()["code"] == "UNREGISTERED_BASE"
        monkeypatch.delenv("OPERATIONAL_PEAK_AUTHORITY_SHA256")
        unavailable = await client.post("/api/v1/operational-peak-forecast-runs", json=_body())
        assert unavailable.status_code == 503
        assert unavailable.json()["code"] == "AUTHORITY_NOT_CONFIGURED"
