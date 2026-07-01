"""Infrastructure proof tests for PostgreSQL test infrastructure.

Requires PostgreSQL (RUN_POSTGRES_INTEGRATION=1). Tests:
1. Positive database identity verification
2. TRUNCATE cleanup works (data removed after test)
3. Consecutive tests have no residual state
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


class TestTruncateCleanup:
    """Verify TRUNCATE-based cleanup works correctly."""

    async def test_data_cleaned_between_tests(self) -> None:
        """Insert data, let autouse fixture clean it up."""
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
                text(
                    "SELECT COUNT(*) FROM dim_factory "
                    "WHERE code = '__test_cleanup_proof__'"
                )
            )
            assert result.scalar_one() == 1

    async def test_no_residual_from_previous_test(self) -> None:
        """This test runs after test_data_cleaned_between_tests.
        The autouse fixture should have cleaned up."""
        async with AsyncSessionMaker() as session:
            result = await session.execute(
                text(
                    "SELECT COUNT(*) FROM dim_factory "
                    "WHERE code = '__test_cleanup_proof__'"
                )
            )
            assert result.scalar_one() == 0, (
                "Residual data found — TRUNCATE cleanup not working"
            )
