"""Test-only S5/S6 presentation harness adapter, NOT authentication acceptance.

The old SQLite parity suites keep their canonical services and payload checks.
S4 security acceptance instead uses business_pg and the real S1/S2 runtime.
"""

from fastapi import Request
from fastapi.responses import JSONResponse


def install(app, state):
    def envelope(data, kind="LOCAL_AUTH"):
        return {"schema_version": f"V0_18_{kind}_R1", "status": "READY", "data": data}

    @app.get("/api/v1/auth/me")
    async def me():
        return envelope(
            {
                "principal_id": "SYNTHETIC_COMPAT",
                "role": "BUSINESS_USER",
                "must_change_password": False,
                "auth_revision": 1,
                "grant_revision": 1,
            }
        )

    @app.get("/api/v1/auth/csrf")
    async def csrf():
        return envelope({"csrf_token": "SYNTHETIC_COMPAT_NOT_AUTHENTICATION", "expires_in": 300})

    @app.get("/api/v1/business-access/scope")
    async def scope():
        return envelope(
            {
                "entities": [
                    {
                        "hierarchy_level": q["hierarchy_level"],
                        "entity_id": q["entity_id"],
                        "entity_name": q["entity_id"],
                    }
                    for q in {
                        (q["hierarchy_level"], q["entity_id"]): q for q in state["identities"]
                    }.values()
                ],
                "data_types": ["FORECAST", "QUALITY"],
                "capabilities": ["may_read_forecast", "may_read_quality"],
                "organization_ids": ["SYNTHETIC"],
                "grant_revision": 1,
                "catalog_snapshot": "a" * 64,
            },
            "BUSINESS_ACCESS",
        )

    @app.get("/api/v1/business-access/saved-runs")
    async def listing():
        return envelope(
            {
                "items": [
                    {
                        "forecast_identity": {
                            k: v for k, v in q.items() if k != "expected_source_result_hash"
                        },
                        "expected_source_result_hash": q["expected_source_result_hash"],
                        "entity_name": q["entity_id"],
                        "forecast_family": q["forecast_family"],
                        "origin_date": q["origin_date"],
                        "completeness_status": "COMPLETE",
                        "canonical_verification_required": True,
                        "source_status": "completed",
                        "saved_at": "2026-01-01T00:00:00Z",
                        "rerun_of_run_id": None,
                    }
                    for q in state["identities"]
                ],
                "next_cursor": None,
                "grant_revision": 1,
                "catalog_snapshot": "a" * 64,
            },
            "BUSINESS_ACCESS",
        )

    @app.post("/api/v1/business-access/selection")
    async def selection(request: Request):
        value = await request.json()
        q = {
            **value["forecast_identity"],
            "expected_source_result_hash": value["expected_source_result_hash"],
        }
        if q not in state["identities"]:
            return JSONResponse({"status": "ERROR", "data": None}, status_code=409)
        # The existing canonical route performs all integrity/authority checks;
        # use its exact response projection, never synthesize business numbers.
        import httpx

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            source = await client.get("/api/v1/forecast-intelligence/curve", params=q)
        if source.status_code != 200:
            return JSONResponse(source.json(), status_code=source.status_code)
        return envelope(
            {
                "forecast_identity": value["forecast_identity"],
                "expected_source_result_hash": value["expected_source_result_hash"],
                "projection_hash": source.json()["projection_hash"],
                "handoff_token": "SYNTHETIC_COMPAT_ONLY",
                "expires_in": 300,
                "authorization_required_on_consumption": True,
            },
            "BUSINESS_ACCESS",
        )
