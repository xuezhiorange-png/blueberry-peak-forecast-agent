"""Loop-owned pool leases from an existing, unchanged asyncpg Engine.

No Engine, URL or session factory is constructed here. Pool.recreate retains
the configured creator/options/events. Its leases are attached to Connections
of the exact supplied Engine, then returned/disposed before the loop exits.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import PoolProxiedConnection
from sqlalchemy.util.concurrency import greenlet_spawn


class _LoopOwnedConnection(AsyncConnection):
    """A real Connection whose private pool is owned by the surrounding scope."""


class LoopResourceUnavailable(RuntimeError):
    """Source connection acquisition failed, rather than factory construction."""


async def _finish_cleanup[T](operation: Awaitable[T]) -> T:
    """Run cleanup once; defer caller cancellation, then propagate it."""
    completion = asyncio.ensure_future(operation)
    cancellation: asyncio.CancelledError | None = None
    while not completion.done():
        try:
            # wait never cancels completion when its caller is cancelled.
            await asyncio.wait({completion})
        except asyncio.CancelledError as exc:
            cancellation = exc
    try:
        result = completion.result()
    except BaseException as exc:
        if cancellation is not None:
            raise cancellation from exc
        raise
    if cancellation is not None:
        raise cancellation
    return result


@asynccontextmanager
async def _connection_scope(source: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    owned_pool = source.pool.recreate()
    leases: list[PoolProxiedConnection] = []

    @event.listens_for(owned_pool, "checkout")
    def track_checkout(_dbapi: object, _record: object, proxy: PoolProxiedConnection) -> None:
        leases.append(proxy)

    try:
        try:
            lease = await greenlet_spawn(owned_pool.connect)
            sync_connection = await greenlet_spawn(
                source.sync_engine._connection_cls,
                source.sync_engine,
                connection=lease,
                _allow_revalidate=False,
            )
        except Exception as exc:
            raise LoopResourceUnavailable("Configured source connection unavailable") from exc
        connection = _LoopOwnedConnection(source, sync_connection=sync_connection)
        try:
            yield connection
        finally:
            await _finish_cleanup(connection.close())
    finally:

        async def release_pool() -> None:
            try:
                # engine_connect may fail after checkout, before Session owns it.
                for lease in leases:
                    if lease.is_valid:
                        await greenlet_spawn(lease.close)
            finally:
                await greenlet_spawn(owned_pool.dispose)

        await _finish_cleanup(release_pool())


@asynccontextmanager
async def _owned_session(session: AsyncSession, source: AsyncEngine) -> AsyncIterator[AsyncSession]:
    ready = False
    try:
        async with _connection_scope(source) as connection:
            ready = True
            session.bind = connection
            session.sync_session.bind = connection.sync_connection
            async with _session_scope(session) as entered:
                yield entered
    finally:
        if not ready:
            await _finish_cleanup(session.close())


@asynccontextmanager
async def _session_scope(session: AsyncSession) -> AsyncIterator[AsyncSession]:
    entered = False
    try:
        value = await session.__aenter__()
        entered = True
        yield value
    finally:
        if entered:
            await _finish_cleanup(session.__aexit__(None, None, None))
        else:
            await _finish_cleanup(session.close())


@asynccontextmanager
async def _borrowed_connection_session(
    session: AsyncSession, connection: AsyncConnection
) -> AsyncIterator[AsyncSession]:
    ready = False
    try:
        if connection.closed or connection.invalidated:
            raise LoopResourceUnavailable("Borrowed async connection is unavailable")
        raw = await connection.get_raw_connection()
        driver = raw.driver_connection
        if driver is None or getattr(driver, "_loop", None) is not asyncio.get_running_loop():
            raise LoopResourceUnavailable("Borrowed async connection belongs to a different loop")
        ready = True
        async with _session_scope(session) as entered:
            yield entered
    finally:
        if not ready:
            await _finish_cleanup(session.close())


def loop_owned_session(
    factory: async_sessionmaker[AsyncSession],
) -> AbstractAsyncContextManager[AsyncSession]:
    configuration = getattr(factory, "kw", None)
    if isinstance(configuration, dict):
        bind = configuration.get("bind")
        if isinstance(bind, (AsyncEngine, AsyncConnection)) and bind.dialect.driver == "asyncpg":
            if configuration.get("binds"):
                raise RuntimeError("Multiple configured binds have no single resource owner")
            # Keep construction synchronous, at the original factory call site.
            session = factory()
            if isinstance(bind, AsyncEngine):
                return _owned_session(session, bind)
            return _borrowed_connection_session(session, bind)
    return factory()


def loop_bound_connection(session: AsyncSession) -> AsyncConnection | None:
    """Only our held resource, never a JSON/info flag or an arbitrary bind."""
    bind = getattr(session, "bind", None)
    return bind if isinstance(bind, _LoopOwnedConnection) else None


@asynccontextmanager
async def loop_owned_connection(source: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    if source.dialect.driver == "asyncpg":
        async with _connection_scope(source) as connection:
            yield connection
    else:
        connection = await source.connect()
        if connection is None:
            raise RuntimeError("async connection not obtained")
        try:
            yield connection
        finally:
            await connection.close()
