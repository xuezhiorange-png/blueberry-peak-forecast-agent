import os

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import create_app

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
    reason="set RUN_POSTGRES_INTEGRATION=1 when PostgreSQL is available",
)
@pytest.mark.asyncio
async def test_health_ready_uses_real_postgresql_connection():
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
