"""Synthetic session fixtures own an engine for exactly one session context.

The public probes create their own asyncio.run loop. Preparing the database in
that session's __aenter__ and disposing it from close keeps connect/use/dispose
in that loop, including failed setup and failed query paths. No application
engine, pool policy, source authority or real dataset is involved.
"""

from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Self
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

_TEST_STORAGE: ContextVar[tuple[Path, list[Path]] | None] = ContextVar(
    "synthetic_sqlite_test_storage", default=None
)


@contextmanager
def sqlite_test_storage(directory: Path) -> Iterator[None]:
    """Explicit pytest ownership of synthetic files shared by successive sessions."""
    paths: list[Path] = []
    token = _TEST_STORAGE.set((directory, paths))
    try:
        yield
    finally:
        try:
            for path in paths:
                path.unlink()
        finally:
            _TEST_STORAGE.reset(token)


def owned_sqlite_session_maker(
    prepare: Callable[[AsyncEngine], Awaitable[None]] | None = None,
    *,
    retain_test_data: bool = False,
) -> async_sessionmaker[AsyncSession]:
    url = "sqlite+aiosqlite:///:memory:"
    if retain_test_data:
        storage = _TEST_STORAGE.get()
        if storage is None:
            raise ValueError("retained synthetic data requires a test-scoped storage owner")
        directory, paths = storage
        path = directory / f"synthetic-{uuid4().hex}.sqlite"
        path.touch(exist_ok=False)
        paths.append(path)
        url = f"sqlite+aiosqlite:///{path}"
    prepared = False

    class OwnedSQLiteSession(AsyncSession):
        def __init__(self, **kwargs: Any) -> None:
            if kwargs.pop("bind", None) is not None:
                raise ValueError("synthetic session owns its engine; external bind is forbidden")
            self._owned_sqlite_engine = create_async_engine(url, poolclass=StaticPool)
            super().__init__(bind=self._owned_sqlite_engine, **kwargs)

        async def __aenter__(self) -> Self:
            nonlocal prepared
            try:
                if prepare is not None and (not retain_test_data or not prepared):
                    await prepare(self._owned_sqlite_engine)
                    prepared = True
                return await super().__aenter__()
            except BaseException:
                await self.close()
                raise

        async def close(self) -> None:
            try:
                await super().close()
            finally:
                await self._owned_sqlite_engine.dispose()

    return async_sessionmaker(class_=OwnedSQLiteSession, expire_on_commit=False)


def owned_sqlite_connection_engine() -> AsyncEngine:
    """One synthetic connection owns its pool and disposes it before loop exit."""

    class OwnedSQLiteConnection(AsyncConnection):
        async def close(self) -> None:
            try:
                await super().close()
            finally:
                await self.engine.dispose()

    class OwnedSQLiteEngine(AsyncEngine):
        def connect(self) -> AsyncConnection:
            return OwnedSQLiteConnection(self)

    # AsyncEngine's public constructor wraps the normal SQLite async dialect;
    # the pool policy remains StaticPool. No synchronous connection is opened.
    return OwnedSQLiteEngine(create_engine("sqlite+aiosqlite:///:memory:"))
