"""Obtain a synchronous connection from the bound live session's bind.

Uses the already-bound SOURCE_002 row-level-read session provider. Does not
invent a connection string or call create_engine. A synchronous connection from
bind is not a queryable Session, is not TRAIN/VAL content_bytes obtained, and
is not SOURCE_002_ROW_LEVEL_READ. Does not rewrite the live-session wiring module.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import MissingGreenlet
from sqlalchemy.orm import Session

from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read import (
    bound_source_002_row_level_read_session_provider,
)


class LiveConnectionReasonCode(StrEnum):
    CONNECTED = "CONNECTED"
    FAIL_CLOSED_NO_SESSION = "FAIL_CLOSED_NO_SESSION"
    FAIL_CLOSED_SESSION_UNREADABLE = "FAIL_CLOSED_SESSION_UNREADABLE"
    FAIL_CLOSED_NO_BIND = "FAIL_CLOSED_NO_BIND"
    FAIL_CLOSED_SYNC_CONNECTION_NOT_OBTAINED_FROM_BIND = (
        "FAIL_CLOSED_SYNC_CONNECTION_NOT_OBTAINED_FROM_BIND"
    )


_NOT_OBTAINED_FROM_BIND = (
    LiveConnectionReasonCode.FAIL_CLOSED_SYNC_CONNECTION_NOT_OBTAINED_FROM_BIND
)


class AcceptedS2TrainValLiveConnectionEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connected: bool
    source_002_row_level_read: bool
    official_hashes_attested_from_a_live_read: bool
    accepted_s2_train_val_content_bytes_obtained_from_bound_live_session: bool
    reason_code: LiveConnectionReasonCode


def obtain_accepted_s2_train_val_sync_connection_from_bound_live_session_bind() -> (
    AcceptedS2TrainValLiveConnectionEnvelope
):
    provider = bound_source_002_row_level_read_session_provider()
    if provider is None:
        return _fail(LiveConnectionReasonCode.FAIL_CLOSED_NO_SESSION)
    try:
        session = provider()
    except Exception:
        return _fail(LiveConnectionReasonCode.FAIL_CLOSED_SESSION_UNREADABLE)
    if session is None:
        return _fail(LiveConnectionReasonCode.FAIL_CLOSED_NO_SESSION)
    try:
        return _obtain_from_session(session)
    except MissingGreenlet:
        return _fail(_NOT_OBTAINED_FROM_BIND)
    except Exception:
        return _fail(LiveConnectionReasonCode.FAIL_CLOSED_SESSION_UNREADABLE)


def _envelope(
    *,
    connected: bool,
    reason: LiveConnectionReasonCode,
) -> AcceptedS2TrainValLiveConnectionEnvelope:
    return AcceptedS2TrainValLiveConnectionEnvelope(
        connected=connected,
        source_002_row_level_read=False,
        official_hashes_attested_from_a_live_read=False,
        accepted_s2_train_val_content_bytes_obtained_from_bound_live_session=False,
        reason_code=reason,
    )


def _fail(reason: LiveConnectionReasonCode) -> AcceptedS2TrainValLiveConnectionEnvelope:
    return _envelope(connected=False, reason=reason)


def _obtain_from_session(session: Session) -> AcceptedS2TrainValLiveConnectionEnvelope:
    try:
        bind = session.get_bind()
    except Exception:
        return _fail(LiveConnectionReasonCode.FAIL_CLOSED_NO_BIND)
    if bind is None:
        return _fail(LiveConnectionReasonCode.FAIL_CLOSED_NO_BIND)
    connection = None
    try:
        try:
            connection = bind.connect()
        except MissingGreenlet:
            return _fail(_NOT_OBTAINED_FROM_BIND)
        if connection is None:
            return _fail(_NOT_OBTAINED_FROM_BIND)
        return _envelope(connected=True, reason=LiveConnectionReasonCode.CONNECTED)
    except Exception:
        return _fail(_NOT_OBTAINED_FROM_BIND)
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass
