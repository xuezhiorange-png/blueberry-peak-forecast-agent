"""Probe whether the already-obtained live AsyncSession is synchronously queryable via run_sync.

Uses the application AsyncSessionMaker already configured in ``backend.app.db.session``.
Does not use ``bound_source_002_row_level_read_session_provider``. Does not invent a
connection string or call create_engine, create_async_engine, or construct a new async
session maker. A synchronously queryable already-obtained live AsyncSession via run_sync
is not TRAIN/VAL content_bytes obtained and is not SOURCE_002_ROW_LEVEL_READ.
"""

from __future__ import annotations

import asyncio
from enum import StrEnum

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import MissingGreenlet
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker as _AsyncSessionMakerCls
from sqlalchemy.orm import Session


class LiveAsyncSessionRunSyncQueryReasonCode(StrEnum):
    QUERYABLE = "QUERYABLE"
    FAIL_CLOSED_NO_ASYNC_SESSION_MAKER = "FAIL_CLOSED_NO_ASYNC_SESSION_MAKER"
    FAIL_CLOSED_ASYNC_SESSION_NOT_OBTAINED_FROM_SESSION_MAKER = (
        "FAIL_CLOSED_ASYNC_SESSION_NOT_OBTAINED_FROM_SESSION_MAKER"
    )
    FAIL_CLOSED_ASYNC_SESSION_NOT_SYNCHRONOUSLY_QUERYABLE_VIA_RUN_SYNC = (
        "FAIL_CLOSED_ASYNC_SESSION_NOT_SYNCHRONOUSLY_QUERYABLE_VIA_RUN_SYNC"
    )


_SESSION_RUN_SYNC_QUERY_REASON = LiveAsyncSessionRunSyncQueryReasonCode
_NOT_OBTAINED_FROM_SESSION_MAKER = (
    _SESSION_RUN_SYNC_QUERY_REASON.FAIL_CLOSED_ASYNC_SESSION_NOT_OBTAINED_FROM_SESSION_MAKER
)
_NOT_SYNCHRONOUSLY_QUERYABLE_VIA_RUN_SYNC = _SESSION_RUN_SYNC_QUERY_REASON.FAIL_CLOSED_ASYNC_SESSION_NOT_SYNCHRONOUSLY_QUERYABLE_VIA_RUN_SYNC  # noqa: E501


class AcceptedS2TrainValLiveAsyncSessionRunSyncQueryEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    queryable: bool
    source_002_row_level_read: bool
    official_hashes_attested_from_a_live_read: bool
    accepted_s2_train_val_content_bytes_obtained_from_bound_live_session: bool
    reason_code: LiveAsyncSessionRunSyncQueryReasonCode


def probe_accepted_s2_train_val_already_obtained_live_async_session_run_sync_queryability(  # noqa: E501
) -> AcceptedS2TrainValLiveAsyncSessionRunSyncQueryEnvelope:
    try:
        from backend.app.db.session import AsyncSessionMaker as live_async_session_maker
    except Exception:
        return _fail(LiveAsyncSessionRunSyncQueryReasonCode.FAIL_CLOSED_NO_ASYNC_SESSION_MAKER)
    if live_async_session_maker is None or not isinstance(
        live_async_session_maker, _AsyncSessionMakerCls
    ):
        return _fail(LiveAsyncSessionRunSyncQueryReasonCode.FAIL_CLOSED_NO_ASYNC_SESSION_MAKER)
    try:
        return asyncio.run(_probe_with_session_maker(live_async_session_maker))
    except _AsyncSessionNotObtained:
        return _fail(_NOT_OBTAINED_FROM_SESSION_MAKER)
    except Exception:
        return _fail(_NOT_SYNCHRONOUSLY_QUERYABLE_VIA_RUN_SYNC)


class _AsyncSessionNotObtained(RuntimeError):
    pass


def _envelope(
    *,
    queryable: bool,
    reason: LiveAsyncSessionRunSyncQueryReasonCode,
) -> AcceptedS2TrainValLiveAsyncSessionRunSyncQueryEnvelope:
    return AcceptedS2TrainValLiveAsyncSessionRunSyncQueryEnvelope(
        queryable=queryable,
        source_002_row_level_read=False,
        official_hashes_attested_from_a_live_read=False,
        accepted_s2_train_val_content_bytes_obtained_from_bound_live_session=False,
        reason_code=reason,
    )


def _fail(
    reason: LiveAsyncSessionRunSyncQueryReasonCode,
) -> AcceptedS2TrainValLiveAsyncSessionRunSyncQueryEnvelope:
    return _envelope(queryable=False, reason=reason)


async def _probe_with_session_maker(
    live_async_session_maker: _AsyncSessionMakerCls[AsyncSession],
) -> AcceptedS2TrainValLiveAsyncSessionRunSyncQueryEnvelope:
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


def _probe_sync_query(sync_session: Session) -> int | None:
    result = sync_session.execute(select(1))
    scalar_value = result.scalar()
    if isinstance(scalar_value, int):
        return scalar_value
    return None


async def _probe_from_async_session(
    session: AsyncSession,
) -> AcceptedS2TrainValLiveAsyncSessionRunSyncQueryEnvelope:
    try:
        probe_value = await session.run_sync(_probe_sync_query)
        if probe_value != 1:
            return _fail(_NOT_SYNCHRONOUSLY_QUERYABLE_VIA_RUN_SYNC)
        return _envelope(
            queryable=True,
            reason=LiveAsyncSessionRunSyncQueryReasonCode.QUERYABLE,
        )
    except MissingGreenlet:
        return _fail(_NOT_SYNCHRONOUSLY_QUERYABLE_VIA_RUN_SYNC)
    except Exception:
        return _fail(_NOT_SYNCHRONOUSLY_QUERYABLE_VIA_RUN_SYNC)
