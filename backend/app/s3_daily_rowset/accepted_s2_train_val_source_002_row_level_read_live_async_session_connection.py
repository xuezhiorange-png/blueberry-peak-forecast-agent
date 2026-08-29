"""Obtain an async connection from the already-obtained live AsyncSession.

Uses the application AsyncSessionMaker already configured in ``backend.app.db.session``.
Does not use ``bound_source_002_row_level_read_session_provider``. Does not invent a
connection string or call create_engine, create_async_engine, or construct a new async
session maker. An async connection from session.connection() is not asynchronously
queryable, is not TRAIN/VAL content_bytes obtained, and is not SOURCE_002_ROW_LEVEL_READ.
"""

from __future__ import annotations

import asyncio
from enum import StrEnum

from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import MissingGreenlet
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker as _AsyncSessionMakerCls


class LiveAsyncSessionConnectionReasonCode(StrEnum):
    CONNECTED = "CONNECTED"
    FAIL_CLOSED_NO_ASYNC_SESSION_MAKER = "FAIL_CLOSED_NO_ASYNC_SESSION_MAKER"
    FAIL_CLOSED_ASYNC_SESSION_NOT_OBTAINED_FROM_SESSION_MAKER = (
        "FAIL_CLOSED_ASYNC_SESSION_NOT_OBTAINED_FROM_SESSION_MAKER"
    )
    FAIL_CLOSED_ASYNC_CONNECTION_NOT_OBTAINED_FROM_SESSION_CONNECTION = (
        "FAIL_CLOSED_ASYNC_CONNECTION_NOT_OBTAINED_FROM_SESSION_CONNECTION"
    )


_NOT_OBTAINED_FROM_SESSION_MAKER = (
    LiveAsyncSessionConnectionReasonCode.FAIL_CLOSED_ASYNC_SESSION_NOT_OBTAINED_FROM_SESSION_MAKER
)
_SESSION_CONNECTION_REASON = LiveAsyncSessionConnectionReasonCode
_NOT_OBTAINED_FROM_SESSION_CONNECTION = (
    _SESSION_CONNECTION_REASON.FAIL_CLOSED_ASYNC_CONNECTION_NOT_OBTAINED_FROM_SESSION_CONNECTION
)


class AcceptedS2TrainValLiveAsyncSessionConnectionEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connected: bool
    source_002_row_level_read: bool
    official_hashes_attested_from_a_live_read: bool
    accepted_s2_train_val_content_bytes_obtained_from_bound_live_session: bool
    reason_code: LiveAsyncSessionConnectionReasonCode


def obtain_accepted_s2_train_val_async_connection_from_the_already_obtained_live_async_session_connection() -> (  # noqa: E501
    AcceptedS2TrainValLiveAsyncSessionConnectionEnvelope
):
    try:
        from backend.app.db.session import AsyncSessionMaker as live_async_session_maker
    except Exception:
        return _fail(LiveAsyncSessionConnectionReasonCode.FAIL_CLOSED_NO_ASYNC_SESSION_MAKER)
    if live_async_session_maker is None or not isinstance(
        live_async_session_maker, _AsyncSessionMakerCls
    ):
        return _fail(LiveAsyncSessionConnectionReasonCode.FAIL_CLOSED_NO_ASYNC_SESSION_MAKER)
    try:
        return asyncio.run(_obtain_with_session_maker(live_async_session_maker))
    except _AsyncSessionNotObtained:
        return _fail(_NOT_OBTAINED_FROM_SESSION_MAKER)
    except Exception:
        return _fail(_NOT_OBTAINED_FROM_SESSION_CONNECTION)


class _AsyncSessionNotObtained(RuntimeError):
    pass


def _envelope(
    *,
    connected: bool,
    reason: LiveAsyncSessionConnectionReasonCode,
) -> AcceptedS2TrainValLiveAsyncSessionConnectionEnvelope:
    return AcceptedS2TrainValLiveAsyncSessionConnectionEnvelope(
        connected=connected,
        source_002_row_level_read=False,
        official_hashes_attested_from_a_live_read=False,
        accepted_s2_train_val_content_bytes_obtained_from_bound_live_session=False,
        reason_code=reason,
    )


def _fail(
    reason: LiveAsyncSessionConnectionReasonCode,
) -> AcceptedS2TrainValLiveAsyncSessionConnectionEnvelope:
    return _envelope(connected=False, reason=reason)


async def _obtain_with_session_maker(
    live_async_session_maker: _AsyncSessionMakerCls[AsyncSession],
) -> AcceptedS2TrainValLiveAsyncSessionConnectionEnvelope:
    session_cm = live_async_session_maker()
    try:
        session = await session_cm.__aenter__()
    except Exception as exc:
        raise _AsyncSessionNotObtained() from exc
    try:
        if session is None:
            raise _AsyncSessionNotObtained()
        return await _obtain_from_async_session(session)
    finally:
        await session_cm.__aexit__(None, None, None)


async def _obtain_from_async_session(
    session: AsyncSession,
) -> AcceptedS2TrainValLiveAsyncSessionConnectionEnvelope:
    try:
        try:
            connection = await session.connection()
        except MissingGreenlet:
            return _fail(_NOT_OBTAINED_FROM_SESSION_CONNECTION)
        if connection is None:
            return _fail(_NOT_OBTAINED_FROM_SESSION_CONNECTION)
        if not isinstance(connection, AsyncConnection):
            return _fail(_NOT_OBTAINED_FROM_SESSION_CONNECTION)
        return _envelope(connected=True, reason=LiveAsyncSessionConnectionReasonCode.CONNECTED)
    except Exception:
        return _fail(_NOT_OBTAINED_FROM_SESSION_CONNECTION)
