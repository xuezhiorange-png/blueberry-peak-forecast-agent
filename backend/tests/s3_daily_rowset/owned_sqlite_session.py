"""Synthetic session fixtures own an engine for exactly one session context.

The public probes create their own asyncio.run loop. Preparing the database in
that session's __aenter__ and disposing it from close keeps connect/use/dispose
in that loop, including failed setup and failed query paths. No application
engine, pool policy, source authority or real dataset is involved.
"""

from collections.abc import Awaitable, Callable
from typing import Any, Self

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def owned_sqlite_session_maker(
    prepare: Callable[[AsyncEngine], Awaitable[None]] | None = None,
) -> async_sessionmaker[AsyncSession]:
    class OwnedSQLiteSession(AsyncSession):
        def __init__(self, **kwargs: Any) -> None:
            if kwargs.pop("bind", None) is not None:
                raise ValueError("synthetic session owns its engine; external bind is forbidden")
            self._owned_sqlite_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
            super().__init__(bind=self._owned_sqlite_engine, **kwargs)

        async def __aenter__(self) -> Self:
            try:
                if prepare is not None:
                    await prepare(self._owned_sqlite_engine)
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
