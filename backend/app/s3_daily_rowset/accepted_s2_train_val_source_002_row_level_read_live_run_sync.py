"""Execute synchronous SOURCE-002 readers through the configured AsyncSessionMaker.

Uses ``backend.app.db.session.AsyncSessionMaker`` already configured by the
application. Does not invent a connection string or call create_engine or
create_async_engine.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker as _AsyncSessionMakerCls
from sqlalchemy.orm import Session


class NoAsyncSessionMaker(RuntimeError):
    """Configured AsyncSessionMaker is unavailable."""


class AsyncSessionNotObtained(RuntimeError):
    """AsyncSessionMaker did not yield a usable AsyncSession."""


def resolve_live_async_session_maker() -> _AsyncSessionMakerCls[AsyncSession] | None:
    try:
        from backend.app.db.session import AsyncSessionMaker as live_async_session_maker
    except Exception:
        return None
    if live_async_session_maker is None or not isinstance(
        live_async_session_maker, _AsyncSessionMakerCls
    ):
        return None
    return live_async_session_maker


async def _run_sync_with_session_maker(
    live_async_session_maker: _AsyncSessionMakerCls[AsyncSession],
    sync_fn: Callable[[Session], object],
) -> object:
    session_cm = live_async_session_maker()
    try:
        session = await session_cm.__aenter__()
    except Exception as exc:
        raise AsyncSessionNotObtained() from exc
    try:
        if session is None:
            raise AsyncSessionNotObtained()
        return await session.run_sync(sync_fn)
    finally:
        await session_cm.__aexit__(None, None, None)


def run_live_source_002_sync_reader(sync_fn: Callable[[Session], object]) -> object:
    """Run a synchronous SOURCE-002 reader via AsyncSession.run_sync."""
    live_async_session_maker = resolve_live_async_session_maker()
    if live_async_session_maker is None:
        raise NoAsyncSessionMaker()
    return asyncio.run(_run_sync_with_session_maker(live_async_session_maker, sync_fn))
