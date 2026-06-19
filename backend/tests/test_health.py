import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.db.session import get_db_session
from backend.app.main import create_app


class _ReadyResult:
    def scalar_one(self) -> int:
        return 1


class _ReadySession:
    async def execute(self, statement):
        assert "SELECT 1" in str(statement)
        return _ReadyResult()


class _BrokenSession:
    async def execute(self, statement):
        raise OSError("database unavailable")


async def _ready_session_override():
    yield _ReadySession()


async def _broken_session_override():
    yield _BrokenSession()


@pytest.mark.asyncio
async def test_health_live_succeeds_without_database():
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "live",
        "service": "Blueberry Peak Forecast Agent",
        "version": "0.1.0",
    }


@pytest.mark.asyncio
async def test_unit_health_ready_succeeds_when_database_query_succeeds():
    app = create_app()
    app.dependency_overrides[get_db_session] = _ready_session_override

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "service": "Blueberry Peak Forecast Agent",
        "version": "0.1.0",
    }


@pytest.mark.asyncio
async def test_health_ready_returns_503_when_database_query_fails():
    app = create_app()
    app.dependency_overrides[get_db_session] = _broken_session_override

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "database is not ready"}


def test_create_app_registers_health_routes():
    app = create_app()

    assert app.title == "Blueberry Peak Forecast Agent"
    assert app.version == "0.1.0"
    assert app.state.settings.app_name == "Blueberry Peak Forecast Agent"
