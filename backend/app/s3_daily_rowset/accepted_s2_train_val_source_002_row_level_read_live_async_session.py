"""Obtain an async session from the already-configured live AsyncSessionMaker.

Uses the application AsyncSessionMaker already configured in ``backend.app.db.session``.
Does not invent a connection string or call create_engine, create_async_engine,
or construct a new async session maker. An async session from session maker is not a sync connection
from bind, is not an async connection from engine, is not a queryable Session, is
not TRAIN/VAL content_bytes obtained, and is not SOURCE_002_ROW_LEVEL_READ.
"""

from __future__ import annotations

import asyncio
from enum import StrEnum

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import async_sessionmaker as _AsyncSessionMakerCls


class LiveAsyncSessionReasonCode(StrEnum):
    OBTAINED = "OBTAINED"
    FAIL_CLOSED_NO_ASYNC_SESSION_MAKER = "FAIL_CLOSED_NO_ASYNC_SESSION_MAKER"
    FAIL_CLOSED_ASYNC_SESSION_NOT_OBTAINED_FROM_SESSION_MAKER = (
        "FAIL_CLOSED_ASYNC_SESSION_NOT_OBTAINED_FROM_SESSION_MAKER"
    )


_NOT_OBTAINED_FROM_SESSION_MAKER = (
    LiveAsyncSessionReasonCode.FAIL_CLOSED_ASYNC_SESSION_NOT_OBTAINED_FROM_SESSION_MAKER
)


class AcceptedS2TrainValLiveAsyncSessionEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    obtained: bool
    source_002_row_level_read: bool
    official_hashes_attested_from_a_live_read: bool
    accepted_s2_train_val_content_bytes_obtained_from_bound_live_session: bool
    reason_code: LiveAsyncSessionReasonCode


# fmt: off
def obtain_accepted_s2_train_val_async_session_from_the_already_configured_live_async_sessionmaker \
(
) -> AcceptedS2TrainValLiveAsyncSessionEnvelope:
# fmt: on
    try:
        from backend.app.db.session import AsyncSessionMaker as live_async_session_maker
    except Exception:
        return _fail(LiveAsyncSessionReasonCode.FAIL_CLOSED_NO_ASYNC_SESSION_MAKER)
    if live_async_session_maker is None or not isinstance(
        live_async_session_maker, _AsyncSessionMakerCls
    ):
        return _fail(LiveAsyncSessionReasonCode.FAIL_CLOSED_NO_ASYNC_SESSION_MAKER)
    try:
        asyncio.run(_obtain_from_session_maker(live_async_session_maker))
    except Exception:
        return _fail(_NOT_OBTAINED_FROM_SESSION_MAKER)
    return _envelope(obtained=True, reason=LiveAsyncSessionReasonCode.OBTAINED)


def _envelope(
    *,
    obtained: bool,
    reason: LiveAsyncSessionReasonCode,
) -> AcceptedS2TrainValLiveAsyncSessionEnvelope:
    return AcceptedS2TrainValLiveAsyncSessionEnvelope(
        obtained=obtained,
        source_002_row_level_read=False,
        official_hashes_attested_from_a_live_read=False,
        accepted_s2_train_val_content_bytes_obtained_from_bound_live_session=False,
        reason_code=reason,
    )


def _fail(reason: LiveAsyncSessionReasonCode) -> AcceptedS2TrainValLiveAsyncSessionEnvelope:
    return _envelope(obtained=False, reason=reason)


async def _obtain_from_session_maker(live_async_session_maker: _AsyncSessionMakerCls) -> None:
    async with live_async_session_maker() as session:
        if session is None:
            raise RuntimeError("async session not obtained")
