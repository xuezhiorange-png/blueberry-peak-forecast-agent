"""Obtain an asynchronous connection from the already-configured live AsyncEngine.

Uses the application AsyncEngine already configured in ``backend.app.db.session``.
Does not invent a connection string or call create_engine / create_async_engine.
An async connection from engine is not a sync connection from bind, is not a
queryable Session, is not TRAIN/VAL content_bytes obtained, and is not
SOURCE_002_ROW_LEVEL_READ.
"""

from __future__ import annotations

import asyncio
from enum import StrEnum

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine


class LiveAsyncConnectionReasonCode(StrEnum):
    CONNECTED = "CONNECTED"
    FAIL_CLOSED_NO_ASYNC_ENGINE = "FAIL_CLOSED_NO_ASYNC_ENGINE"
    FAIL_CLOSED_ASYNC_CONNECTION_NOT_OBTAINED_FROM_ENGINE = (
        "FAIL_CLOSED_ASYNC_CONNECTION_NOT_OBTAINED_FROM_ENGINE"
    )


_NOT_OBTAINED_FROM_ENGINE = (
    LiveAsyncConnectionReasonCode.FAIL_CLOSED_ASYNC_CONNECTION_NOT_OBTAINED_FROM_ENGINE
)


class AcceptedS2TrainValLiveAsyncConnectionEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connected: bool
    source_002_row_level_read: bool
    official_hashes_attested_from_a_live_read: bool
    accepted_s2_train_val_content_bytes_obtained_from_bound_live_session: bool
    reason_code: LiveAsyncConnectionReasonCode


def obtain_accepted_s2_train_val_async_connection_from_the_already_configured_live_async_engine() -> (  # noqa: E501
    AcceptedS2TrainValLiveAsyncConnectionEnvelope
):
    try:
        from backend.app.db.session import engine as live_async_engine
    except Exception:
        return _fail(LiveAsyncConnectionReasonCode.FAIL_CLOSED_NO_ASYNC_ENGINE)
    if live_async_engine is None or not isinstance(live_async_engine, AsyncEngine):
        return _fail(LiveAsyncConnectionReasonCode.FAIL_CLOSED_NO_ASYNC_ENGINE)
    try:
        asyncio.run(_obtain_from_engine(live_async_engine))
    except Exception:
        return _fail(_NOT_OBTAINED_FROM_ENGINE)
    return _envelope(connected=True, reason=LiveAsyncConnectionReasonCode.CONNECTED)


def _envelope(
    *,
    connected: bool,
    reason: LiveAsyncConnectionReasonCode,
) -> AcceptedS2TrainValLiveAsyncConnectionEnvelope:
    return AcceptedS2TrainValLiveAsyncConnectionEnvelope(
        connected=connected,
        source_002_row_level_read=False,
        official_hashes_attested_from_a_live_read=False,
        accepted_s2_train_val_content_bytes_obtained_from_bound_live_session=False,
        reason_code=reason,
    )


def _fail(reason: LiveAsyncConnectionReasonCode) -> AcceptedS2TrainValLiveAsyncConnectionEnvelope:
    return _envelope(connected=False, reason=reason)


async def _obtain_from_engine(live_async_engine: AsyncEngine) -> None:
    connection: AsyncConnection | None = None
    try:
        connection = await live_async_engine.connect()
        if connection is None:
            raise RuntimeError("async connection not obtained")
    finally:
        if connection is not None:
            try:
                await connection.close()
            except Exception:
                pass
