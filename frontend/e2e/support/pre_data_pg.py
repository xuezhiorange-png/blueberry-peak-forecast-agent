"""S9-bound workbook demo on the existing owned HTTPS/ASGI/PostgreSQL fixture."""

import hashlib
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import FastAPI
from fastapi.responses import FileResponse
from sqlalchemy import select
from starlette.staticfiles import StaticFiles

from backend.app.local_auth.models import AuthAccount
from backend.tests.rolling_forecast.spreadsheet_demo_package import create_demo
from frontend.e2e.support import business_pg


@asynccontextmanager
async def lifespan(outer):
    async with business_pg.lifespan(outer):
        with TemporaryDirectory(prefix="SYNTHETIC-pre-data-browser-") as directory:
            auth = outer.state.auth
            async with auth.factory() as db:
                account = await db.scalar(
                    select(AuthAccount).where(AuthAccount.username_normalized == "synthetic-user")
                )
            _, catalog, manifest = create_demo(
                Path(directory) / "SYNTHETIC-package", account.principal_id
            )
            auth.settings.app_env = "test"
            auth.settings.rolling_forecast_catalog_path = str(catalog)
            auth.settings.pre_data_demo_manifest_path = str(manifest)
            auth.settings.pre_data_demo_manifest_sha256 = hashlib.sha256(
                manifest.read_bytes()
            ).hexdigest()
            yield


outer = FastAPI(lifespan=lifespan)


@outer.get("/__s4_test__/ready")
async def ready():
    return business_pg.STATE


@outer.get("/dashboard/{path:path}")
async def frontend(path: str):
    return FileResponse(business_pg.ROOT / "frontend/dist/index.html")


outer.mount("/assets", StaticFiles(directory=business_pg.ROOT / "frontend/dist/assets"))


async def app(scope, receive, send):
    if scope["type"] == "http" and scope["path"].startswith("/api/"):
        await outer.state.production(scope, receive, send)
    else:
        await outer(scope, receive, send)
