"""Real isolated PostgreSQL only. No production database fallback."""

import asyncio
import os
import subprocess
from uuid import uuid4

import asyncpg
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.api.local_auth import router
from backend.app.api.local_auth_admin import router as admin_router
from backend.app.core.config import AppSettings
from backend.app.local_auth.models import AuthAccount
from backend.app.local_auth.passwords import hash_password
from backend.app.local_auth.service import AuthService
from backend.app.local_auth.sessions import now
from backend.tests.forecast_intelligence.conftest import synthetic_authority  # noqa: F401


@pytest_asyncio.fixture
async def pg_auth():
    host = os.environ.get("POSTGRES_HOST", "")
    assert host in {"localhost", "127.0.0.1"}, "Isolated loopback PostgreSQL required"
    port = int(os.environ["POSTGRES_PORT"])
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASSWORD"]
    database = "blueberry_test_auth_" + uuid4().hex
    admin = await asyncpg.connect(
        host=host, port=port, user=user, password=password, database="postgres"
    )
    await admin.execute(f'CREATE DATABASE "{database}"')
    environment = dict(os.environ, APP_ENV="test", POSTGRES_DB=database)
    result = await asyncio.to_thread(
        subprocess.run,
        ["uv", "run", "alembic", "-c", "backend/alembic.ini", "upgrade", "head"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    engine = create_async_engine(f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = AppSettings(
        app_env="test",
        local_auth_origin="https://synthetic.test",
        local_auth_login_bucket_secret="SYNTHETIC_TEST_ONLY_NOT_PRODUCTION",
        local_auth_organization_ids_json='["SYNTHETIC_ORG"]',
    )
    auth = AuthService(factory, settings)
    app = FastAPI()
    app.state.local_auth = auth
    app.include_router(router, prefix="/api/v1/auth")
    app.include_router(admin_router, prefix="/api/v1/admin")
    async with factory() as db, db.begin():
        account = AuthAccount(
            username_normalized="synthetic-user",
            password_hash=hash_password("SYNTHETIC-password-123"),
            role="BUSINESS_USER",
            status="ACTIVE",
            must_change_password=False,
            created_at=now(),
            updated_at=now(),
        )
        db.add(account)
        await db.flush()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://synthetic.test"
    ) as client:
        yield auth, factory, client, account, database
    await engine.dispose()
    # Only the freshly generated, explicitly isolated database is removed.
    await admin.execute(f'DROP DATABASE "{database}" WITH (FORCE)')
    await admin.close()


async def login(client, password="SYNTHETIC-password-123"):
    csrf = await client.get("/api/v1/auth/csrf")
    assert csrf.status_code == 200
    return await client.post(
        "/api/v1/auth/login",
        json={"username": "synthetic-user", "password": password},
        headers={
            "Origin": "https://synthetic.test",
            "X-CSRF-Token": csrf.json()["data"]["csrf_token"],
        },
    )
