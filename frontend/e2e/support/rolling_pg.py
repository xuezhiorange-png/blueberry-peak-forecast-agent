"""Reuse owned S4 HTTPS/PG lifecycle and S7 synthetic I5/I7 test seed."""

from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import FastAPI
from fastapi.responses import FileResponse
from sqlalchemy import select
from starlette.staticfiles import StaticFiles

from backend.app.local_auth.models import AuthAccount
from backend.app.rolling_forecast.policy import Catalog
from backend.tests.rolling_forecast.inbound_fixture import fixture
from backend.tests.rolling_forecast.seed import seed
from frontend.e2e.support import business_pg


@asynccontextmanager
async def lifespan(outer):
    # No second PostgreSQL runner or fixture lifecycle implementation.
    async with business_pg.lifespan(outer):
        with TemporaryDirectory(prefix="SYNTHETIC-s7-browser-") as directory:
            auth = outer.state.auth
            async with auth.factory() as db:
                account = await db.scalar(
                    select(AuthAccount).where(AuthAccount.username_normalized == "synthetic-user")
                )
            old, policy = await seed(auth.factory, account.principal_id, Path(directory))
            inbound = fixture(Path(directory) / "inbound", account.principal_id)
            combined = Catalog.model_validate(
                {
                    **old.model_dump(mode="json"),
                    "contexts": [*old.contexts, *inbound.contexts],
                    "capabilities": [*old.capabilities, *inbound.capabilities],
                }
            )
            policy.write_text(combined.model_dump_json())
            auth.settings.rolling_forecast_catalog_path = str(policy)
            yield


outer = FastAPI(lifespan=lifespan)


@outer.get("/__s4_test__/ready")
async def ready():
    return business_pg.STATE


@outer.get("/dashboard/{path:path}")
async def frontend(path: str):
    del path
    return FileResponse(business_pg.ROOT / "frontend/dist/index.html")


outer.mount("/assets", StaticFiles(directory=business_pg.ROOT / "frontend/dist/assets"))


async def app(scope, receive, send):
    if scope["type"] == "http" and scope["path"].startswith("/api/"):
        await outer.state.production(scope, receive, send)
    else:
        await outer(scope, receive, send)
