"""Probe whether the already-obtained live AsyncSession is asynchronously queryable.

Uses the application AsyncSessionMaker already configured in ``backend.app.db.session``.
Does not use ``bound_source_002_row_level_read_session_provider``. Does not invent a
connection string or call create_engine, create_async_engine, or construct a new async
session maker. An asynchronously queryable already-obtained live AsyncSession is not
TRAIN/VAL content_bytes obtained and is not SOURCE_002_ROW_LEVEL_READ.
"""

from __future__ import annotations

import asyncio
from enum import StrEnum

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import MissingGreenlet
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker as _AsyncSessionMakerCls


class LiveAsyncSessionQueryReasonCode(StrEnum):
    QUERYABLE = "QUERYABLE"
    FAIL_CLOSED_NO_ASYNC_SESSION_MAKER = "FAIL_CLOSED_NO_ASYNC_SESSION_MAKER"
    FAIL_CLOSED_ASYNC_SESSION_NOT_OBTAINED_FROM_SESSION_MAKER = (
        "FAIL_CLOSED_ASYNC_SESSION_NOT_OBTAINED_FROM_SESSION_MAKER"
    )
    FAIL_CLOSED_ASYNC_SESSION_NOT_ASYNCHRONOUSLY_QUERYABLE = (
        "FAIL_CLOSED_ASYNC_SESSION_NOT_ASYNCHRONOUSLY_QUERYABLE"
    )


_NOT_OBTAINED_FROM_SESSION_MAKER = (
    LiveAsyncSessionQueryReasonCode.FAIL_CLOSED_ASYNC_SESSION_NOT_OBTAINED_FROM_SESSION_MAKER
)


class AcceptedS2TrainValLiveAsyncSessionQueryEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    queryable: bool
    source_002_row_level_read: bool
    official_hashes_attested_from_a_live_read: bool
    accepted_s2_train_val_content_bytes_obtained_from_bound_live_session: bool
    reason_code: LiveAsyncSessionQueryReasonCode


# fmt: off
def probe_accepted_s2_train_val_already_obtained_live_async_session_queryability \
(
) -> AcceptedS2TrainValLiveAsyncSessionQueryEnvelope:
# fmt: on
    try:
        from backend.app.db.session import AsyncSessionMaker as live_async_session_maker
    except Exception:
        return _fail(LiveAsyncSessionQueryReasonCode.FAIL_CLOSED_NO_ASYNC_SESSION_MAKER)
    if live_async_session_maker is None or not isinstance(
        live_async_session_maker, _AsyncSessionMakerCls
    ):
        return _fail(LiveAsyncSessionQueryReasonCode.FAIL_CLOSED_NO_ASYNC_SESSION_MAKER)
    try:
        return asyncio.run(_probe_with_session_maker(live_async_session_maker))
    except _AsyncSessionNotObtained:
        return _fail(_NOT_OBTAINED_FROM_SESSION_MAKER)
    except Exception:
        return _fail(
            LiveAsyncSessionQueryReasonCode.FAIL_CLOSED_ASYNC_SESSION_NOT_ASYNCHRONOUSLY_QUERYABLE
        )


class _AsyncSessionNotObtained(RuntimeError):
    pass


def _envelope(
    *,
    queryable: bool,
    reason: LiveAsyncSessionQueryReasonCode,
) -> AcceptedS2TrainValLiveAsyncSessionQueryEnvelope:
    return AcceptedS2TrainValLiveAsyncSessionQueryEnvelope(
        queryable=queryable,
        source_002_row_level_read=False,
        official_hashes_attested_from_a_live_read=False,
        accepted_s2_train_val_content_bytes_obtained_from_bound_live_session=False,
        reason_code=reason,
    )


def _fail(
    reason: LiveAsyncSessionQueryReasonCode,
) -> AcceptedS2TrainValLiveAsyncSessionQueryEnvelope:
    return _envelope(queryable=False, reason=reason)


async def _probe_with_session_maker(
    live_async_session_maker: _AsyncSessionMakerCls[AsyncSession],
) -> AcceptedS2TrainValLiveAsyncSessionQueryEnvelope:
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
) -> AcceptedS2TrainValLiveAsyncSessionQueryEnvelope:
    try:
        probe_value = await session.scalar(select(1))
        if probe_value != 1:
            return _fail(
                LiveAsyncSessionQueryReasonCode.FAIL_CLOSED_ASYNC_SESSION_NOT_ASYNCHRONOUSLY_QUERYABLE
            )
        return _envelope(queryable=True, reason=LiveAsyncSessionQueryReasonCode.QUERYABLE)
    except MissingGreenlet:
        return _fail(
            LiveAsyncSessionQueryReasonCode.FAIL_CLOSED_ASYNC_SESSION_NOT_ASYNCHRONOUSLY_QUERYABLE
        )
    except Exception:
        return _fail(
            LiveAsyncSessionQueryReasonCode.FAIL_CLOSED_ASYNC_SESSION_NOT_ASYNCHRONOUSLY_QUERYABLE
        )
