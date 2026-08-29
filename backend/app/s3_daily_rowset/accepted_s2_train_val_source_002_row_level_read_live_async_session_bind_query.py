"""Probe whether the AsyncConnection from the already-obtained live AsyncSession bind is queryable.

Uses the application AsyncSessionMaker already configured in ``backend.app.db.session``.
Does not use ``bound_source_002_row_level_read_session_provider``. Does not invent a
connection string or call create_engine, create_async_engine, or construct a new async
session maker. A queryable async connection from session bind is not TRAIN/VAL
content_bytes obtained and is not SOURCE_002_ROW_LEVEL_READ.
"""

from __future__ import annotations

import asyncio
from enum import StrEnum

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import MissingGreenlet
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker as _AsyncSessionMakerCls


class LiveAsyncSessionBindQueryReasonCode(StrEnum):
    QUERYABLE = "QUERYABLE"
    FAIL_CLOSED_NO_ASYNC_SESSION_MAKER = "FAIL_CLOSED_NO_ASYNC_SESSION_MAKER"
    FAIL_CLOSED_ASYNC_SESSION_NOT_OBTAINED_FROM_SESSION_MAKER = (
        "FAIL_CLOSED_ASYNC_SESSION_NOT_OBTAINED_FROM_SESSION_MAKER"
    )
    FAIL_CLOSED_NO_BIND = "FAIL_CLOSED_NO_BIND"
    FAIL_CLOSED_ASYNC_CONNECTION_NOT_OBTAINED_FROM_SESSION_BIND = (
        "FAIL_CLOSED_ASYNC_CONNECTION_NOT_OBTAINED_FROM_SESSION_BIND"
    )
    FAIL_CLOSED_ASYNC_SESSION_BIND_CONNECTION_NOT_ASYNCHRONOUSLY_QUERYABLE = (
        "FAIL_CLOSED_ASYNC_SESSION_BIND_CONNECTION_NOT_ASYNCHRONOUSLY_QUERYABLE"
    )


_SESSION_BIND_QUERY_REASON = LiveAsyncSessionBindQueryReasonCode
_NOT_OBTAINED_FROM_SESSION_MAKER = (
    _SESSION_BIND_QUERY_REASON.FAIL_CLOSED_ASYNC_SESSION_NOT_OBTAINED_FROM_SESSION_MAKER
)
_NOT_OBTAINED_FROM_SESSION_BIND = (
    _SESSION_BIND_QUERY_REASON.FAIL_CLOSED_ASYNC_CONNECTION_NOT_OBTAINED_FROM_SESSION_BIND
)
_NOT_ASYNCHRONOUSLY_QUERYABLE = (
    _SESSION_BIND_QUERY_REASON.FAIL_CLOSED_ASYNC_SESSION_BIND_CONNECTION_NOT_ASYNCHRONOUSLY_QUERYABLE
)


class AcceptedS2TrainValLiveAsyncSessionBindQueryEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    queryable: bool
    source_002_row_level_read: bool
    official_hashes_attested_from_a_live_read: bool
    accepted_s2_train_val_content_bytes_obtained_from_bound_live_session: bool
    reason_code: LiveAsyncSessionBindQueryReasonCode


def probe_accepted_s2_train_val_already_obtained_live_async_session_bind_connection_queryability(  # noqa: E501
) -> AcceptedS2TrainValLiveAsyncSessionBindQueryEnvelope:
    try:
        from backend.app.db.session import AsyncSessionMaker as live_async_session_maker
    except Exception:
        return _fail(LiveAsyncSessionBindQueryReasonCode.FAIL_CLOSED_NO_ASYNC_SESSION_MAKER)
    if live_async_session_maker is None or not isinstance(
        live_async_session_maker, _AsyncSessionMakerCls
    ):
        return _fail(LiveAsyncSessionBindQueryReasonCode.FAIL_CLOSED_NO_ASYNC_SESSION_MAKER)
    try:
        return asyncio.run(_probe_with_session_maker(live_async_session_maker))
    except _AsyncSessionNotObtained:
        return _fail(_NOT_OBTAINED_FROM_SESSION_MAKER)
    except Exception:
        return _fail(_NOT_OBTAINED_FROM_SESSION_BIND)


class _AsyncSessionNotObtained(RuntimeError):
    pass


def _envelope(
    *,
    queryable: bool,
    reason: LiveAsyncSessionBindQueryReasonCode,
) -> AcceptedS2TrainValLiveAsyncSessionBindQueryEnvelope:
    return AcceptedS2TrainValLiveAsyncSessionBindQueryEnvelope(
        queryable=queryable,
        source_002_row_level_read=False,
        official_hashes_attested_from_a_live_read=False,
        accepted_s2_train_val_content_bytes_obtained_from_bound_live_session=False,
        reason_code=reason,
    )


def _fail(
    reason: LiveAsyncSessionBindQueryReasonCode,
) -> AcceptedS2TrainValLiveAsyncSessionBindQueryEnvelope:
    return _envelope(queryable=False, reason=reason)


async def _probe_with_session_maker(
    live_async_session_maker: _AsyncSessionMakerCls[AsyncSession],
) -> AcceptedS2TrainValLiveAsyncSessionBindQueryEnvelope:
    session_cm = live_async_session_maker()
    try:
        session = await session_cm.__aenter__()
    except Exception as exc:
        raise _AsyncSessionNotObtained() from exc
    try:
        if session is None:
            raise _AsyncSessionNotObtained()
        return await _probe_from_async_session(session)
    finally:
        await session_cm.__aexit__(None, None, None)


async def _probe_from_async_session(
    session: AsyncSession,
) -> AcceptedS2TrainValLiveAsyncSessionBindQueryEnvelope:
    try:
        retrieved = session.get_bind()
    except Exception:
        return _fail(LiveAsyncSessionBindQueryReasonCode.FAIL_CLOSED_NO_BIND)
    bind: AsyncEngine | None = retrieved if isinstance(retrieved, AsyncEngine) else None
    if bind is None:
        attached = session.bind
        bind = attached if isinstance(attached, AsyncEngine) else None
    if bind is None:
        return _fail(LiveAsyncSessionBindQueryReasonCode.FAIL_CLOSED_NO_BIND)
    connection: AsyncConnection | None = None
    try:
        try:
            connection = await bind.connect()
        except MissingGreenlet:
            return _fail(_NOT_OBTAINED_FROM_SESSION_BIND)
        if connection is None:
            return _fail(_NOT_OBTAINED_FROM_SESSION_BIND)
        if not isinstance(connection, AsyncConnection):
            return _fail(_NOT_OBTAINED_FROM_SESSION_BIND)
        return await _probe_from_async_connection(connection)
    except Exception:
        return _fail(_NOT_OBTAINED_FROM_SESSION_BIND)
    finally:
        if connection is not None:
            try:
                await connection.close()
            except Exception:
                pass


async def _probe_from_async_connection(
    connection: AsyncConnection,
) -> AcceptedS2TrainValLiveAsyncSessionBindQueryEnvelope:
    try:
        probe_value = await connection.scalar(select(1))
        if probe_value != 1:
            return _fail(_NOT_ASYNCHRONOUSLY_QUERYABLE)
        return _envelope(
            queryable=True,
            reason=LiveAsyncSessionBindQueryReasonCode.QUERYABLE,
        )
    except MissingGreenlet:
        return _fail(_NOT_ASYNCHRONOUSLY_QUERYABLE)
    except Exception:
        return _fail(_NOT_ASYNCHRONOUSLY_QUERYABLE)
