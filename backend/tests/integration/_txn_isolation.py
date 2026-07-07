"""Slice 2 — opt-in transactional PostgreSQL test isolation helper.

This module provides :func:`transactional_async_session`, a
:func:`@asynccontextmanager` that opens a single outer transaction on
a dedicated :class:`AsyncConnection`, yields an :class:`AsyncSession`
bound to that connection with
``join_transaction_mode="create_savepoint"``, and rolls the outer
transaction back on exit regardless of test outcome.

Design contract
---------------

1. The outer transaction is **never** committed; it is only rolled
   back. The connection is returned to the engine pool at teardown.
2. ``await session.commit()`` inside the test body only releases the
   current savepoint. A subsequent ORM write re-opens a fresh
   savepoint automatically (SQLAlchemy 2.0 default behavior with
   ``join_transaction_mode="create_savepoint"``).
3. All writes — including those that passed through ``commit()`` —
   are reverted at teardown because the outer transaction is rolled
   back, not committed.
4. Cleanup is unconditional: the session is closed, the outer
   transaction is rolled back (if still active), the connection is
   closed, and any exception from the test body is re-raised after
   cleanup. Failures during cleanup are logged at WARNING level but
   never swallowed.

This module deliberately accepts any :class:`AsyncEngine` rather than
importing the application's :mod:`backend.app.db.session` so it can be
unit-tested without depending on the FastAPI app's full module
graph. The caller is responsible for ensuring the engine is connected
to a database the test is permitted to use.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Final

from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    AsyncTransaction,
    async_sessionmaker,
)

_LOGGER: Final = logging.getLogger(__name__)


@asynccontextmanager
async def transactional_async_session(
    engine: AsyncEngine,
    *,
    expire_on_commit: bool = False,
) -> AsyncIterator[AsyncSession]:
    """Yield an :class:`AsyncSession` wrapped in an outer transaction.

    Parameters
    ----------
    engine:
        The :class:`AsyncEngine` to bind the test session to. A
        dedicated :class:`AsyncConnection` is acquired from the
        engine's pool; the connection is returned to the pool on
        teardown.
    expire_on_commit:
        Forwarded to the :class:`AsyncSession`. Defaults to
        ``False`` so that attribute access after ``commit()`` does
        not trigger a refresh ``SELECT``.

    Yields
    ------
    AsyncSession
        A session bound to the dedicated connection with
        ``join_transaction_mode="create_savepoint"``. The initial
        savepoint is opened eagerly by the first ORM write, so test
        code can call ``session.add()`` /
        ``session.execute(insert_stmt)`` /
        ``session.flush()`` without manually starting a savepoint.

        ``await session.commit()`` releases the current savepoint;
        the outer transaction is not committed. A subsequent ORM
        write re-opens a fresh savepoint automatically.

    Raises
    ------
    Re-raises any exception from the test body after cleanup. Cleanup
    failures are logged at WARNING level and do not mask the original
    exception.
    """
    connection: AsyncConnection | None = None
    outer_txn: AsyncTransaction | None = None
    session: AsyncSession | None = None
    try:
        # Step 1 — acquire a dedicated connection from the engine pool.
        connection = await engine.connect()

        # Step 2 — open the outer transaction on that connection.
        # This transaction will be rolled back at teardown; it is
        # never committed.
        outer_txn = await connection.begin()

        # Step 3 — build a sessionmaker that binds every new session
        # to the same connection. ``join_transaction_mode="create_savepoint"``
        # instructs SQLAlchemy 2.x to start a nested savepoint
        # automatically before each ORM operation, so the test can
        # call ``commit()`` without losing its transaction context.
        session_factory = async_sessionmaker(
            bind=connection,
            class_=AsyncSession,
            expire_on_commit=expire_on_commit,
            join_transaction_mode="create_savepoint",
        )
        session = session_factory()

        # Step 4 — eagerly start the initial savepoint so the session
        # is immediately usable for writes. We do NOT enter the
        # returned transaction's context manager because we want the
        # savepoint to persist for the entire test body and to
        # re-open lazily on the next ``commit()``.
        await session.begin_nested()

        yield session
    finally:
        # Cleanup order matters: close the session first (which closes
        # any pending savepoint), then roll back the outer transaction
        # (which reverts every committed savepoint), then close the
        # connection (which returns it to the engine pool).
        if session is not None:
            try:
                await session.close()
            except Exception:  # pragma: no cover - defensive cleanup
                _LOGGER.warning(
                    "transactional_async_session: session.close() failed",
                    exc_info=True,
                )
        if outer_txn is not None and outer_txn.is_active:
            try:
                await outer_txn.rollback()
            except Exception:  # pragma: no cover - defensive cleanup
                _LOGGER.warning(
                    "transactional_async_session: outer rollback failed",
                    exc_info=True,
                )
        if connection is not None:
            try:
                await connection.close()
            except Exception:  # pragma: no cover - defensive cleanup
                _LOGGER.warning(
                    "transactional_async_session: connection.close() failed",
                    exc_info=True,
                )
