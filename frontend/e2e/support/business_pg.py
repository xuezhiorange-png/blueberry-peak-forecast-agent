"""Loopback-only HTTPS S4 browser harness; actual S1/S2 app and isolated PG.

Never imported by production. Literal SYNTHETIC saved curves, not inference.
The UUID database is created/migrated before serving and dropped on shutdown.
"""

import asyncio
import os
import subprocess
import sys
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from uuid import uuid4

import asyncpg
from fastapi import FastAPI
from fastapi.responses import FileResponse
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.staticfiles import StaticFiles

from backend.app.area_yield.data import digest
from backend.app.core.config import AppSettings
from backend.app.forecast_intelligence.hierarchy import COMPANY_ID, build_hierarchy
from backend.app.forecast_intelligence.persistence import HierarchicalRunRepository, source_mapping
from backend.app.forecast_intelligence.read_schemas import ForecastReadQuery
from backend.app.forecast_intelligence.reconciliation import reconcile
from backend.app.forecast_intelligence.schemas import CreateHierarchicalRun
from backend.app.forecast_quality.operational_peak_persistence import (
    OperationalPeakRunRepository,
    execution_hash,
)
from backend.app.local_auth.models import AuthAccount
from backend.app.local_auth.passwords import hash_password
from backend.app.local_auth.service import AuthService
from backend.app.local_auth.sessions import now
from backend.app.main import create_app
from backend.tests.business_access.test_discovery import grant
from backend.tests.mcp.test_v0_18_s3_postgres import quality_grant
from frontend.e2e.support.dashboard_api import saved_fixture

ROOT = Path(__file__).resolve().parents[3]
STATE = {"SYNTHETIC": True}


@asynccontextmanager
async def lifespan(outer):
    assert os.environ.get("S4_SYNTHETIC_ONLY") == "1"
    host = os.environ["POSTGRES_HOST"]
    assert host in {"127.0.0.1", "localhost"}
    origin = os.environ["S4_HTTPS_ORIGIN"]
    assert origin.startswith("https://127.0.0.1:")
    user, password, port = (
        os.environ[k] for k in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_PORT")
    )
    database = "blueberry_peak_test_s4_" + uuid4().hex
    admin = await asyncpg.connect(
        host=host, port=int(port), user=user, password=password, database="postgres"
    )
    await admin.execute(f'CREATE DATABASE "{database}"')
    engine = None
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, "-m", "alembic", "-c", "backend/alembic.ini", "upgrade", "head"],
            env=dict(os.environ, APP_ENV="test", POSTGRES_DB=database),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        engine = create_async_engine(
            f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}"
        )
        factory = async_sessionmaker(engine, expire_on_commit=False)
        settings = AppSettings(
            app_env="test",
            local_auth_origin=origin,
            local_auth_login_bucket_secret="SYNTHETIC_S4_NOT_PRODUCTION",
            local_auth_organization_ids_json='["SYNTHETIC_ORG"]',
            business_access_signing_key="SYNTHETIC_S4_SIGNING_ONLY_" * 3,
        )
        auth = AuthService(factory, settings)
        accounts = []
        async with factory() as db, db.begin():
            for username, role, forced in (
                ("synthetic-user", "BUSINESS_USER", False),
                ("synthetic-other", "BUSINESS_USER", False),
                ("synthetic-admin", "ADMIN", False),
                ("synthetic-first", "BUSINESS_USER", True),
            ):
                account = AuthAccount(
                    username_normalized=username,
                    password_hash=hash_password("SYNTHETIC-password-123"),
                    role=role,
                    status="ACTIVE",
                    must_change_password=forced,
                    created_at=now(),
                    updated_at=now(),
                )
                db.add(account)
                accounts.append(account)
            await db.flush()
            registry = {
                "bases": [
                    {
                        "base_id": f"SYNTHETIC_BASE_{i}",
                        "canonical_base_name": f"SYNTHETIC_BASE_{i}",
                        "region_scope": "SYNTHETIC_REGION",
                    }
                    for i in (1, 2)
                ]
            }
            authority = digest(registry)
            saved = []
            for base in registry["bases"]:
                result = saved_fixture(base["base_id"])
                snapshot = {
                    "base_id": result.base_id,
                    "target_season": result.target_season,
                    "origin_date": result.origin_date.isoformat(),
                }
                saved.append(
                    await OperationalPeakRunRepository(db).save(
                        snapshot,
                        result,
                        execution_hash(snapshot, authority, result.policy_version),
                        authority,
                        None,
                    )
                )
            queries = [
                ForecastReadQuery(
                    source_kind="OPERATIONAL_PEAK",
                    forecast_family="OPERATIONAL_PEAK_FORECAST_RUN_V1",
                    run_id=s.run.run_id,
                    hierarchy_level="BASE",
                    entity_id=s.run.base_id,
                    target_season="2025-2026",
                    origin_date=date(2026, 1, 1),
                    baseline_id=s.run.baseline_id,
                    policy_version=s.run.policy_version,
                    expected_source_result_hash=s.run.result_hash,
                )
                for s in saved
            ]
            hierarchy = build_hierarchy(registry, authority, digest(registry))
            sources = [source_mapping(s) for s in saved]
            for level, entity in (("REGION", "SYNTHETIC_REGION"), ("COMPANY", COMPANY_ID)):
                request = CreateHierarchicalRun(
                    target_entity_type=level,
                    target_entity_id=entity,
                    source_run_ids=[s.run.run_id for s in saved],
                )
                aggregate = await HierarchicalRunRepository(db).save(
                    hierarchy, request, reconcile(hierarchy, request, sources), sources
                )
                queries.append(
                    ForecastReadQuery(
                        source_kind="HIERARCHICAL",
                        forecast_family=queries[0].forecast_family,
                        run_id=aggregate.run.run_id,
                        hierarchy_level=level,
                        entity_id=entity,
                        target_season=queries[0].target_season,
                        origin_date=queries[0].origin_date,
                        baseline_id=queries[0].baseline_id,
                        policy_version=queries[0].policy_version,
                        expected_source_result_hash=aggregate.run.result_hash,
                    )
                )
        for query in queries:
            await grant(factory, accounts[0], query)
        await grant(factory, accounts[1], queries[1])
        await grant(factory, accounts[3], queries[0])
        await quality_grant(factory, accounts[0])
        STATE["post_seed_business_dml_count"] = 0

        @event.listens_for(engine.sync_engine, "before_cursor_execute")
        def guard_business_dml(connection, cursor, statement, parameters, context, many):
            del connection, cursor, parameters, context, many
            sql = statement.lower().lstrip()
            if sql.startswith(("insert", "update", "delete", "alter", "drop")) and (
                "operational_peak_forecast" in sql or "hierarchical_forecast" in sql
            ):
                STATE["post_seed_business_dml_count"] += 1
                raise AssertionError("SYNTHETIC_READ_PHASE_BUSINESS_DML_FORBIDDEN")

        production = create_app(settings)
        production.state.local_auth = auth
        outer.state.production = production
        outer.state.auth = auth
        outer.state.hold_next = None
        outer.state.held = None
        outer.state.hold_arrived = False
        STATE.update(database=database, identities=[q.model_dump(mode="json") for q in queries])
        yield
    finally:
        if engine is not None:
            await engine.dispose()
        await admin.execute(f'DROP DATABASE "{database}" WITH (FORCE)')
        await admin.close()


outer = FastAPI(lifespan=lifespan)


@outer.get("/__s4_test__/ready")
async def ready():
    return {**STATE, "hold_arrived": outer.state.hold_arrived}


@outer.post("/__s4_test__/hold-next-curve")
async def hold_next():
    outer.state.held = asyncio.Event()
    outer.state.hold_next = outer.state.held
    outer.state.hold_arrived = False
    return {"SYNTHETIC": True}


@outer.post("/__s4_test__/release-curve")
async def release_curve():
    if outer.state.held is not None:
        outer.state.held.set()
    return {"SYNTHETIC": True}


@outer.post("/__s4_test__/revoke-other")
async def revoke_other():
    # Fixed synthetic subject only, never an arbitrary SQL or management API.
    auth = outer.state.auth
    async with auth.factory() as db, db.begin():
        account = await db.scalar(
            select(AuthAccount)
            .where(AuthAccount.username_normalized == "synthetic-other")
            .with_for_update()
        )
        account.grant_revision += 1
        await auth.revoke_all(db, account, "SYNTHETIC_S4_REVOCATION")
    return {"SYNTHETIC": True, "revoked": True}


@outer.get("/dashboard/{path:path}")
async def frontend(path: str):
    del path
    return FileResponse(ROOT / "frontend/dist/index.html", headers={"Cache-Control": "no-store"})


outer.mount("/assets", StaticFiles(directory=ROOT / "frontend/dist/assets"))


async def app(scope, receive, send):
    if scope["type"] == "http" and scope["path"].startswith("/api/"):
        gate = (
            outer.state.hold_next
            if scope["path"] == "/api/v1/forecast-intelligence/curve"
            else None
        )
        if gate is not None:
            outer.state.hold_next = None

        async def held_send(message):
            if gate is not None and message["type"] == "http.response.start":
                outer.state.hold_arrived = True
                await gate.wait()
            await send(message)

        await outer.state.production(scope, receive, held_send)
    else:
        await outer(scope, receive, send)
