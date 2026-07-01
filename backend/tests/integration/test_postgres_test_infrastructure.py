"""Infrastructure proof tests for PostgreSQL transaction isolation.

Requires PostgreSQL (RUN_POSTGRES_INTEGRATION=1). Tests:
1. Application session commit contained by outer transaction
2. Outer rollback removes rows
3. Maker configuration restored after isolation
4. Exception path restores maker
5. Two consecutive isolation contexts work
6. Positive database identity verification
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from backend.app.db.session import AsyncSessionMaker

RUN_PG = os.getenv("RUN_POSTGRES_INTEGRATION") == "1"

pytestmark = [pytest.mark.integration, pytest.mark.postgres_real_commit]


@pytest.fixture(autouse=True)
def _requires_postgres() -> None:
    if not RUN_PG:
        pytest.skip("RUN_POSTGRES_INTEGRATION not set")


class TestDatabaseIdentity:
    """Positive PostgreSQL identity verification."""

    async def test_current_database_is_blueberry_peak_test(self) -> None:
        from backend.tests.postgres_test_support import assert_connected_to_safe_test_database

        await assert_connected_to_safe_test_database()


class TestTransactionIsolation:
    """Prove that transaction isolation works correctly.

    These tests use the postgres_transactional_isolation context manager
    directly and create sessions via the global AsyncSessionMaker.
    """

    async def test_application_session_commit_contained(self) -> None:
        """Insert + commit in one session, visible in second session within context."""
        from backend.tests.postgres_test_support import postgres_transactional_isolation

        async with postgres_transactional_isolation():
            # Write via first application session
            async with AsyncSessionMaker() as session:
                await session.execute(
                    text(
                        "INSERT INTO dim_factory (code, name, active) "
                        "VALUES ('__test_factory_iso__', '__test__', true) "
                        "ON CONFLICT DO NOTHING"
                    )
                )
                await session.commit()

            # Read via second application session — must be visible
            async with AsyncSessionMaker() as session:
                result = await session.execute(
                    text(
                        "SELECT COUNT(*) FROM dim_factory "
                        "WHERE code = '__test_factory_iso__'"
                    )
                )
                count = result.scalar_one()
                assert count == 1, f"Expected 1, got {count}"

    async def test_outer_rollback_removes_row(self) -> None:
        """After context exit, fresh connection sees no data."""
        from backend.tests.postgres_test_support import postgres_transactional_isolation

        async with postgres_transactional_isolation():
            async with AsyncSessionMaker() as session:
                await session.execute(
                    text(
                        "INSERT INTO dim_factory (code, name, active) "
                        "VALUES ('__test_rollback__', '__test__', true) "
                        "ON CONFLICT DO NOTHING"
                    )
                )
                await session.commit()

        # After exit: fresh connection must NOT see the row
        from backend.app.db.session import engine

        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT COUNT(*) FROM dim_factory "
                    "WHERE code = '__test_rollback__'"
                )
            )
            count = result.scalar_one()
            assert count == 0, f"Expected 0 after rollback, got {count}"

    async def test_maker_bind_restored(self) -> None:
        """After context exit, maker bind is restored to original engine."""
        from backend.app.db.session import engine
        from backend.tests.postgres_test_support import postgres_transactional_isolation

        original_bind = AsyncSessionMaker.kw.get("bind")

        async with postgres_transactional_isolation():
            # Inside: bind should be the connection, not the engine
            inner_bind = AsyncSessionMaker.kw.get("bind")
            assert inner_bind is not engine, "Bind should be connection during isolation"

        # After: bind should be restored
        restored_bind = AsyncSessionMaker.kw.get("bind")
        assert restored_bind == original_bind, (
            f"Bind not restored: expected {original_bind}, got {restored_bind}"
        )

    async def test_exception_path_restores_maker(self) -> None:
        """Even if the context body raises, maker is restored."""
        from backend.tests.postgres_test_support import postgres_transactional_isolation

        original_bind = AsyncSessionMaker.kw.get("bind")

        with pytest.raises(RuntimeError, match="test error"):
            async with postgres_transactional_isolation():
                raise RuntimeError("test error")

        restored_bind = AsyncSessionMaker.kw.get("bind")
        assert restored_bind == original_bind, "Maker bind not restored after exception"

    async def test_two_consecutive_contexts(self) -> None:
        """Two consecutive isolation contexts with same business key both succeed."""
        from backend.tests.postgres_test_support import postgres_transactional_isolation

        for _ in range(2):
            async with postgres_transactional_isolation():
                async with AsyncSessionMaker() as session:
                    await session.execute(
                        text(
                            "INSERT INTO dim_factory (code, name, active) "
                            "VALUES ('__test_consecutive__', '__test__', true) "
                            "ON CONFLICT DO NOTHING"
                        )
                    )
                    await session.commit()

        # After both: no data should remain
        from backend.app.db.session import engine

        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT COUNT(*) FROM dim_factory "
                    "WHERE code = '__test_consecutive__'"
                )
            )
            count = result.scalar_one()
            assert count == 0, f"Expected 0 after two contexts, got {count}"
