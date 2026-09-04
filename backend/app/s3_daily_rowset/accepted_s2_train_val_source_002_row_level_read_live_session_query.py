"""Probe whether the bound live session is synchronously queryable.

Uses the already-bound SOURCE_002 row-level-read session provider. Does not
invent a connection string or call create_engine. A queryable bound session
is not TRAIN/VAL content_bytes obtained and is not SOURCE_002_ROW_LEVEL_READ.
Does not rewrite the live-session wiring module.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import MissingGreenlet
from sqlalchemy.orm import Session

from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read import (
    bound_source_002_row_level_read_session_provider,
)


class LiveSessionQueryReasonCode(StrEnum):
    QUERYABLE = "QUERYABLE"
    FAIL_CLOSED_NO_SESSION = "FAIL_CLOSED_NO_SESSION"
    FAIL_CLOSED_SESSION_UNREADABLE = "FAIL_CLOSED_SESSION_UNREADABLE"
    FAIL_CLOSED_SESSION_NOT_SYNCHRONOUSLY_QUERYABLE = (
        "FAIL_CLOSED_SESSION_NOT_SYNCHRONOUSLY_QUERYABLE"
    )


class AcceptedS2TrainValLiveSessionQueryEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    queryable: bool
    source_002_row_level_read: bool
    official_hashes_attested_from_a_live_read: bool
    accepted_s2_train_val_content_bytes_obtained_from_bound_live_session: bool
    reason_code: LiveSessionQueryReasonCode


def probe_accepted_s2_train_val_bound_live_session_queryability() -> (
    AcceptedS2TrainValLiveSessionQueryEnvelope
):
    provider = bound_source_002_row_level_read_session_provider()
    if provider is None:
        return _fail(LiveSessionQueryReasonCode.FAIL_CLOSED_NO_SESSION)
    from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_session import (  # noqa: E501
        is_live_async_session_run_sync_provider,
    )

    if is_live_async_session_run_sync_provider(provider):
        return _fail(LiveSessionQueryReasonCode.FAIL_CLOSED_SESSION_NOT_SYNCHRONOUSLY_QUERYABLE)
    try:
        session = provider()
    except Exception:
        return _fail(LiveSessionQueryReasonCode.FAIL_CLOSED_SESSION_UNREADABLE)
    if session is None:
        return _fail(LiveSessionQueryReasonCode.FAIL_CLOSED_NO_SESSION)
    try:
        return _probe_from_session(session)
    except MissingGreenlet:
        return _fail(LiveSessionQueryReasonCode.FAIL_CLOSED_SESSION_NOT_SYNCHRONOUSLY_QUERYABLE)
    except Exception:
        return _fail(LiveSessionQueryReasonCode.FAIL_CLOSED_SESSION_UNREADABLE)


def _envelope(
    *,
    queryable: bool,
    reason: LiveSessionQueryReasonCode,
) -> AcceptedS2TrainValLiveSessionQueryEnvelope:
    return AcceptedS2TrainValLiveSessionQueryEnvelope(
        queryable=queryable,
        source_002_row_level_read=False,
        official_hashes_attested_from_a_live_read=False,
        accepted_s2_train_val_content_bytes_obtained_from_bound_live_session=False,
        reason_code=reason,
    )


def _fail(reason: LiveSessionQueryReasonCode) -> AcceptedS2TrainValLiveSessionQueryEnvelope:
    return _envelope(queryable=False, reason=reason)


def _probe_from_session(session: Session) -> AcceptedS2TrainValLiveSessionQueryEnvelope:
    try:
        connection = session.connection()
    except MissingGreenlet:
        return _fail(LiveSessionQueryReasonCode.FAIL_CLOSED_SESSION_NOT_SYNCHRONOUSLY_QUERYABLE)
    if connection is None:
        return _fail(LiveSessionQueryReasonCode.FAIL_CLOSED_SESSION_UNREADABLE)
    return _envelope(queryable=True, reason=LiveSessionQueryReasonCode.QUERYABLE)
