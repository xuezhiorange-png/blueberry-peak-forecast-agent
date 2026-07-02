"""Infrastructure proof tests for PostgreSQL test isolation.

Requires PostgreSQL (RUN_POSTGRES_INTEGRATION=1). Tests:
1. Positive database identity verification
2. Application session commit visible to second session (savepoint)
3. Outer rollback removes all data
4. Maker configuration restored after context
5. Exception path restores maker
6. Consecutive isolation contexts work
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from backend.tests.postgres_test_support import postgres_transactional_isolation

pytestmark = [pytest.mark.integration, pytest.mark.postgres_real_commit]


class TestDatabaseIdentity:
    """Positive PostgreSQL identity verification."""

    async def test_current_database_is_blueberry_peak_test(self) -> None:
        from backend.tests.postgres_test_support import assert_connected_to_safe_test_database

        await assert_connected_to_safe_test_database()


class TestTransactionIsolation:
    """Prove that postgres_transactional_isolation() provides real transaction isolation."""

    async def test_app_session_commit_visible(self) -> None:
        """App session commit creates savepoint, visible to second session."""
        async with postgres_transactional_isolation():
            from backend.app.db.session import AsyncSessionMaker

            async with AsyncSessionMaker() as session:
                await session.execute(
                    text(
                        "INSERT INTO dim_factory (code, name, active) "
                        "VALUES ('__iso_proof_1__', '__iso_test__', true)"
                    )
                )
                await session.commit()

            # Verify visible via another session within same isolation context
            async with AsyncSessionMaker() as second_session:
                result = await second_session.execute(
                    text("SELECT COUNT(*) FROM dim_factory WHERE code = '__iso_proof_1__'")
                )
                assert result.scalar_one() == 1, "Committed data not visible to second session"

    async def test_outer_rollback_removes_data(self) -> None:
        """After isolation context exits, data is gone."""
        async with postgres_transactional_isolation():
            from backend.app.db.session import AsyncSessionMaker

            async with AsyncSessionMaker() as session:
                await session.execute(
                    text(
                        "INSERT INTO dim_factory (code, name, active) "
                        "VALUES ('__iso_proof_2__', '__iso_test__', true)"
                    )
                )
                await session.commit()

        # After context exit, verify data is gone via fresh engine connection
        from backend.app.db.session import engine

        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT COUNT(*) FROM dim_factory WHERE code = '__iso_proof_2__'")
            )
            assert result.scalar_one() == 0, "Data survived outer rollback — isolation broken"

    async def test_maker_bind_restored(self) -> None:
        """After isolation context, maker bind points to engine, not connection."""
        from backend.app.db.session import AsyncSessionMaker, engine

        original_bind = AsyncSessionMaker.kw.get("bind")

        async with postgres_transactional_isolation():
            # Inside context: bind should be the connection
            inner_bind = AsyncSessionMaker.kw.get("bind")
            assert inner_bind is not engine, (
                "Inside isolation context, bind should be connection, not engine"
            )

        # After context: bind should be restored
        restored_bind = AsyncSessionMaker.kw.get("bind")
        assert restored_bind is original_bind, (
            f"Maker bind not restored: expected {original_bind}, got {restored_bind}"
        )

    async def test_maker_join_mode_restored(self) -> None:
        """After isolation context, join_transaction_mode is restored."""
        from backend.app.db.session import AsyncSessionMaker

        original_mode = AsyncSessionMaker.kw.get("join_transaction_mode", "conditional_savepoint")

        async with postgres_transactional_isolation():
            inner_mode = AsyncSessionMaker.kw.get("join_transaction_mode")
            assert inner_mode == "create_savepoint", (
                f"Inside context, join_transaction_mode should be create_savepoint, "
                f"got {inner_mode}"
            )

        restored_mode = AsyncSessionMaker.kw.get("join_transaction_mode", "conditional_savepoint")
        assert restored_mode == original_mode, (
            f"Maker join_transaction_mode not restored: "
            f"expected {original_mode}, got {restored_mode}"
        )

    async def test_exception_path_restores_maker(self) -> None:
        """Maker is restored even when exception occurs inside context."""
        from backend.app.db.session import AsyncSessionMaker

        original_bind = AsyncSessionMaker.kw.get("bind")
        original_mode = AsyncSessionMaker.kw.get("join_transaction_mode", "conditional_savepoint")

        class TestError(Exception):
            pass

        with pytest.raises(TestError):
            async with postgres_transactional_isolation():
                raise TestError("test exception")

        restored_bind = AsyncSessionMaker.kw.get("bind")
        restored_mode = AsyncSessionMaker.kw.get("join_transaction_mode", "conditional_savepoint")
        assert restored_bind is original_bind, "Maker bind not restored after exception"
        assert restored_mode == original_mode, (
            "Maker join_transaction_mode not restored after exception"
        )

    async def test_consecutive_isolation_contexts(self) -> None:
        """Two consecutive isolation contexts work without residual state."""
        # First context
        async with postgres_transactional_isolation():
            from backend.app.db.session import AsyncSessionMaker

            async with AsyncSessionMaker() as session:
                await session.execute(
                    text(
                        "INSERT INTO dim_factory (code, name, active) "
                        "VALUES ('__iso_consec_1__', '__iso_test__', true)"
                    )
                )
                await session.commit()

        # Second context — same key should work (first was rolled back)
        async with postgres_transactional_isolation():
            from backend.app.db.session import AsyncSessionMaker

            async with AsyncSessionMaker() as session:
                await session.execute(
                    text(
                        "INSERT INTO dim_factory (code, name, active) "
                        "VALUES ('__iso_consec_1__', '__iso_test__', true)"
                    )
                )
                await session.commit()

            # Verify data exists within second context
            async with AsyncSessionMaker() as verify_session:
                result = await verify_session.execute(
                    text("SELECT COUNT(*) FROM dim_factory WHERE code = '__iso_consec_1__'")
                )
                assert result.scalar_one() == 1


class TestTruncateCleanup:
    """Verify TRUNCATE-based cleanup works for special tests."""

    async def test_data_cleaned_between_tests(self) -> None:
        """Insert data, let autouse fixture clean it up."""
        from backend.app.db.session import AsyncSessionMaker

        async with AsyncSessionMaker() as session:
            await session.execute(
                text(
                    "INSERT INTO dim_factory (code, name, active) "
                    "VALUES ('__test_cleanup_proof__', '__test__', true) "
                    "ON CONFLICT DO NOTHING"
                )
            )
            await session.commit()

        # Verify data exists within this test
        async with AsyncSessionMaker() as session:
            result = await session.execute(
                text("SELECT COUNT(*) FROM dim_factory WHERE code = '__test_cleanup_proof__'")
            )
            assert result.scalar_one() == 1

    async def test_no_residual_from_previous_test(self) -> None:
        """This test runs after test_data_cleaned_between_tests.
        The autouse fixture should have cleaned up."""
        from backend.app.db.session import AsyncSessionMaker

        async with AsyncSessionMaker() as session:
            result = await session.execute(
                text("SELECT COUNT(*) FROM dim_factory WHERE code = '__test_cleanup_proof__'")
            )
            assert result.scalar_one() == 0, "Residual data found — TRUNCATE cleanup not working"
