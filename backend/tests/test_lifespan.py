import pytest

from backend.app.db import session as db_session
from backend.tests.support.legacy_test_app import create_legacy_test_app as create_app


@pytest.mark.asyncio
async def test_app_lifespan_disposes_database_engine_on_shutdown(monkeypatch):
    dispose_calls = 0

    async def fake_dispose_db_engine() -> None:
        nonlocal dispose_calls
        dispose_calls += 1

    monkeypatch.setattr(db_session, "dispose_db_engine", fake_dispose_db_engine)
    app = create_app(synthetic=True)

    async with app.router.lifespan_context(app):
        assert dispose_calls == 0

    assert dispose_calls == 1
