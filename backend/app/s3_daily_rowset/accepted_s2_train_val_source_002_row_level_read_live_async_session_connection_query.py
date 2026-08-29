"""Probe whether the AsyncConnection from the already-obtained live AsyncSession is queryable.

Uses the application AsyncSessionMaker already configured in ``backend.app.db.session``.
Does not use ``bound_source_002_row_level_read_session_provider``. Does not invent a
connection string or call create_engine, create_async_engine, or construct a new async
session maker. A queryable async connection from session.connection() is not TRAIN/VAL
content_bytes obtained and is not SOURCE_002_ROW_LEVEL_READ.
"""

from __future__ import annotations

import asyncio
from enum import StrEnum

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import MissingGreenlet
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker as _AsyncSessionMakerCls


class LiveAsyncSessionConnectionQueryReasonCode(StrEnum):
    QUERYABLE = "QUERYABLE"
    FAIL_CLOSED_NO_ASYNC_SESSION_MAKER = "FAIL_CLOSED_NO_ASYNC_SESSION_MAKER"
    FAIL_CLOSED_ASYNC_SESSION_NOT_OBTAINED_FROM_SESSION_MAKER = (
        "FAIL_CLOSED_ASYNC_SESSION_NOT_OBTAINED_FROM_SESSION_MAKER"
    )
    FAIL_CLOSED_ASYNC_CONNECTION_NOT_OBTAINED_FROM_SESSION_CONNECTION = (
        "FAIL_CLOSED_ASYNC_CONNECTION_NOT_OBTAINED_FROM_SESSION_CONNECTION"
    )
    FAIL_CLOSED_ASYNC_CONNECTION_NOT_ASYNCHRONOUSLY_QUERYABLE = (
        "FAIL_CLOSED_ASYNC_CONNECTION_NOT_ASYNCHRONOUSLY_QUERYABLE"
    )


_SESSION_CONNECTION_QUERY_REASON = LiveAsyncSessionConnectionQueryReasonCode
_NOT_OBTAINED_FROM_SESSION_MAKER = (
    _SESSION_CONNECTION_QUERY_REASON.FAIL_CLOSED_ASYNC_SESSION_NOT_OBTAINED_FROM_SESSION_MAKER
)
# fmt: off
_NOT_OBTAINED_FROM_SESSION_CONNECTION = (
    _SESSION_CONNECTION_QUERY_REASON.FAIL_CLOSED_ASYNC_CONNECTION_NOT_OBTAINED_FROM_SESSION_CONNECTION
)
# fmt: on
_NOT_ASYNCHRONOUSLY_QUERYABLE = (
    _SESSION_CONNECTION_QUERY_REASON.FAIL_CLOSED_ASYNC_CONNECTION_NOT_ASYNCHRONOUSLY_QUERYABLE
)


class AcceptedS2TrainValLiveAsyncSessionConnectionQueryEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    queryable: bool
    source_002_row_level_read: bool
    official_hashes_attested_from_a_live_read: bool
    accepted_s2_train_val_content_bytes_obtained_from_bound_live_session: bool
    reason_code: LiveAsyncSessionConnectionQueryReasonCode


def probe_accepted_s2_train_val_already_obtained_live_async_session_connection_queryability(  # noqa: E501
) -> AcceptedS2TrainValLiveAsyncSessionConnectionQueryEnvelope:
    try:
        from backend.app.db.session import AsyncSessionMaker as live_async_session_maker
    except Exception:
        return _fail(LiveAsyncSessionConnectionQueryReasonCode.FAIL_CLOSED_NO_ASYNC_SESSION_MAKER)
    if live_async_session_maker is None or not isinstance(
        live_async_session_maker, _AsyncSessionMakerCls
    ):
        return _fail(LiveAsyncSessionConnectionQueryReasonCode.FAIL_CLOSED_NO_ASYNC_SESSION_MAKER)
    try:
        return asyncio.run(_probe_with_session_maker(live_async_session_maker))
    except _AsyncSessionNotObtained:
        return _fail(_NOT_OBTAINED_FROM_SESSION_MAKER)
    except Exception:
        return _fail(_NOT_OBTAINED_FROM_SESSION_CONNECTION)


class _AsyncSessionNotObtained(RuntimeError):
    pass


def _envelope(
    *,
    queryable: bool,
    reason: LiveAsyncSessionConnectionQueryReasonCode,
) -> AcceptedS2TrainValLiveAsyncSessionConnectionQueryEnvelope:
    return AcceptedS2TrainValLiveAsyncSessionConnectionQueryEnvelope(
        queryable=queryable,
        source_002_row_level_read=False,
        official_hashes_attested_from_a_live_read=False,
        accepted_s2_train_val_content_bytes_obtained_from_bound_live_session=False,
        reason_code=reason,
    )


def _fail(
    reason: LiveAsyncSessionConnectionQueryReasonCode,
) -> AcceptedS2TrainValLiveAsyncSessionConnectionQueryEnvelope:
    return _envelope(queryable=False, reason=reason)


async def _probe_with_session_maker(
    live_async_session_maker: _AsyncSessionMakerCls[AsyncSession],
) -> AcceptedS2TrainValLiveAsyncSessionConnectionQueryEnvelope:
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
) -> AcceptedS2TrainValLiveAsyncSessionConnectionQueryEnvelope:
    try:
        try:
            connection = await session.connection()
        except MissingGreenlet:
            return _fail(_NOT_OBTAINED_FROM_SESSION_CONNECTION)
        if connection is None:
            return _fail(_NOT_OBTAINED_FROM_SESSION_CONNECTION)
        if not isinstance(connection, AsyncConnection):
            return _fail(_NOT_OBTAINED_FROM_SESSION_CONNECTION)
        return await _probe_from_async_connection(connection)
    except Exception:
        return _fail(_NOT_OBTAINED_FROM_SESSION_CONNECTION)


async def _probe_from_async_connection(
    connection: AsyncConnection,
) -> AcceptedS2TrainValLiveAsyncSessionConnectionQueryEnvelope:
    try:
        probe_value = await connection.scalar(select(1))
        if probe_value != 1:
            return _fail(_NOT_ASYNCHRONOUSLY_QUERYABLE)
        return _envelope(
            queryable=True,
            reason=LiveAsyncSessionConnectionQueryReasonCode.QUERYABLE,
        )
    except MissingGreenlet:
        return _fail(_NOT_ASYNCHRONOUSLY_QUERYABLE)
    except Exception:
        return _fail(_NOT_ASYNCHRONOUSLY_QUERYABLE)
