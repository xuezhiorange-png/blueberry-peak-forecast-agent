"""Shared PostgreSQL test support: identity validation and transactional isolation.

This module provides:
- validate_postgres_test_identity(): pure, testable validation logic
- assert_connected_to_safe_test_database(): async DB identity check
- postgres_transactional_isolation(): async context manager for transaction isolation
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# ── Safety constants ─────────────────────────────────────────────────────────

ALLOWED_TEST_DATABASES = frozenset({"blueberry_peak_test"})
FORBIDDEN_DATABASES = frozenset({"blueberry_peak", "postgres", "template0", "template1"})


# ── Pure validator (no DB connection) ────────────────────────────────────────


def validate_postgres_test_identity(
    *,
    app_env: str | None,
    environment_database: str | None,
    configured_database: str,
    actual_database: str,
) -> None:
    """Validate that all three sources of database identity agree.

    This is a pure function — no DB connection, no side effects.
    Raises ValueError with clear messages. Never includes passwords.
    """
    if app_env != "test":
        raise ValueError(f"APP_ENV must be 'test', got {app_env!r}")

    if not environment_database:
        raise ValueError("POSTGRES_DB environment variable is not set")

    if environment_database in FORBIDDEN_DATABASES:
        raise ValueError(f"POSTGRES_DB={environment_database!r} is a protected database name")

    if environment_database not in ALLOWED_TEST_DATABASES:
        raise ValueError(f"POSTGRES_DB={environment_database!r} is not in allowed test databases")

    if configured_database != environment_database:
        raise ValueError(
            f"Database mismatch: configured {configured_database!r} != "
            f"environment {environment_database!r}"
        )

    if configured_database != actual_database:
        raise ValueError(
            f"Database mismatch: configured {configured_database!r} != "
            f"actual connected {actual_database!r}"
        )

    if actual_database not in ALLOWED_TEST_DATABASES:
        raise ValueError(f"Connected to {actual_database!r} which is not an allowed test database")


# ── Async DB identity check ──────────────────────────────────────────────────


async def assert_connected_to_safe_test_database() -> None:
    """Connect to the database and verify identity matches all sources.

    Checks: APP_ENV, POSTGRES_DB env, settings.postgres_db, current_database().
    """
    from backend.app.core.config import get_settings

    settings = get_settings()

    engine = create_async_engine(settings.async_database_url)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT current_database()"))
            actual_db = result.scalar_one()
    finally:
        await engine.dispose()

    validate_postgres_test_identity(
        app_env=os.getenv("APP_ENV"),
        environment_database=os.getenv("POSTGRES_DB"),
        configured_database=settings.postgres_db,
        actual_database=actual_db,
    )


# ── Transactional isolation context manager ──────────────────────────────────


@asynccontextmanager
async def postgres_transactional_isolation() -> AsyncIterator[None]:
    """Reconfigure the global AsyncSessionMaker for transaction isolation.

    Usage:
        async with postgres_transactional_isolation():
            # All sessions created via AsyncSessionMaker() participate
            # in the outer transaction. session.commit() creates savepoints.
            ...

    On exit: rolls back outer transaction, restores original maker config.
    """
    from backend.app.db.session import AsyncSessionMaker, engine

    # Save original configuration
    original_bind: Any = AsyncSessionMaker.kw.get("bind")
    original_join_mode: Any = AsyncSessionMaker.kw.get(
        "join_transaction_mode", "conditional_savepoint"
    )

    async with engine.connect() as connection:
        outer_transaction = await connection.begin()

        # Reconfigure the global maker to use this connection
        AsyncSessionMaker.configure(
            bind=connection,
            join_transaction_mode="create_savepoint",
        )

        try:
            yield
        finally:
            # Ensure any lingering sessions are closed
            # Restore original configuration
            AsyncSessionMaker.configure(
                bind=original_bind,
                join_transaction_mode=original_join_mode,
            )
            await outer_transaction.rollback()
