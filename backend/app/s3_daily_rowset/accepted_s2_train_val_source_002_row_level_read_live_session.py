"""Bind the landed SOURCE_002 row-level reader to the existing live AsyncSessionMaker.

Does not invent a connection string or call create_engine. Uses the application
``AsyncSessionMaker`` already configured in ``backend.app.db.session`` and executes
attestation/obtain through ``AsyncSession.run_sync``. Does not use
``async_engine.sync_engine`` as a production bridge.
"""

from __future__ import annotations

import asyncio

from sqlalchemy.exc import MissingGreenlet
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker as _AsyncSessionMakerCls
from sqlalchemy.orm import Session

from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read import (
    AcceptedS2TrainValSource002RowLevelReadAttestation,
    Source002RowLevelReadReasonCode,
    _attest_from_session,
)
from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_obtain import (  # noqa: E501
    AcceptedS2TrainValLiveObtainEnvelope,
    LiveObtainReasonCode,
    _obtain_from_session,
)


class _AsyncSessionNotObtained(RuntimeError):
    pass


def source_002_row_level_read_live_session_provider() -> Session | None:
    """Marker provider; attestation/obtain dispatch to AsyncSession.run_sync."""
    return None


def is_live_async_session_run_sync_provider(provider: object) -> bool:
    return provider is source_002_row_level_read_live_session_provider


def bind_default_source_002_row_level_read_live_session_provider() -> None:
    from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read import (
        set_source_002_row_level_read_session_provider,
    )

    set_source_002_row_level_read_session_provider(source_002_row_level_read_live_session_provider)


def _fail_attestation(
    reason: Source002RowLevelReadReasonCode,
) -> AcceptedS2TrainValSource002RowLevelReadAttestation:
    from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read import (
        _fail,
    )

    return _fail(reason)


def _fail_obtain(reason: LiveObtainReasonCode) -> AcceptedS2TrainValLiveObtainEnvelope:
    from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_obtain import (  # noqa: E501
        _fail,
    )

    return _fail(reason)


async def _attest_with_session_maker(
    live_async_session_maker: _AsyncSessionMakerCls[AsyncSession],
) -> AcceptedS2TrainValSource002RowLevelReadAttestation:
    session_cm = live_async_session_maker()
    try:
        session = await session_cm.__aenter__()
    except Exception as exc:
        raise _AsyncSessionNotObtained() from exc
    try:
        if session is None:
            raise _AsyncSessionNotObtained()
        return await session.run_sync(_attest_from_session)
    except Exception:
        return _fail_attestation(Source002RowLevelReadReasonCode.FAIL_CLOSED_SESSION_UNREADABLE)
    finally:
        await session_cm.__aexit__(None, None, None)


async def _obtain_with_session_maker(
    live_async_session_maker: _AsyncSessionMakerCls[AsyncSession],
) -> AcceptedS2TrainValLiveObtainEnvelope:
    session_cm = live_async_session_maker()
    try:
        session = await session_cm.__aenter__()
    except Exception as exc:
        raise _AsyncSessionNotObtained() from exc
    try:
        if session is None:
            raise _AsyncSessionNotObtained()
        return await session.run_sync(_obtain_from_session)
    except Exception:
        return _fail_obtain(LiveObtainReasonCode.FAIL_CLOSED_SESSION_UNREADABLE)
    finally:
        await session_cm.__aexit__(None, None, None)


def attest_source_002_via_async_session_run_sync() -> (
    AcceptedS2TrainValSource002RowLevelReadAttestation
):
    """Attest SOURCE_002 row-level read through AsyncSessionMaker.run_sync."""
    try:
        from backend.app.db.session import AsyncSessionMaker as live_async_session_maker
    except Exception:
        return _fail_attestation(Source002RowLevelReadReasonCode.FAIL_CLOSED_NO_SESSION)
    if live_async_session_maker is None or not isinstance(
        live_async_session_maker, _AsyncSessionMakerCls
    ):
        return _fail_attestation(Source002RowLevelReadReasonCode.FAIL_CLOSED_NO_SESSION)
    try:
        return asyncio.run(_attest_with_session_maker(live_async_session_maker))
    except (_AsyncSessionNotObtained, MissingGreenlet):
        return _fail_attestation(Source002RowLevelReadReasonCode.FAIL_CLOSED_SESSION_UNREADABLE)
    except Exception:
        return _fail_attestation(Source002RowLevelReadReasonCode.FAIL_CLOSED_SESSION_UNREADABLE)


def obtain_source_002_via_async_session_run_sync() -> AcceptedS2TrainValLiveObtainEnvelope:
    """Obtain SOURCE_002 TRAIN/VALIDATION bytes through AsyncSessionMaker.run_sync."""
    try:
        from backend.app.db.session import AsyncSessionMaker as live_async_session_maker
    except Exception:
        return _fail_obtain(LiveObtainReasonCode.FAIL_CLOSED_NO_SESSION)
    if live_async_session_maker is None or not isinstance(
        live_async_session_maker, _AsyncSessionMakerCls
    ):
        return _fail_obtain(LiveObtainReasonCode.FAIL_CLOSED_NO_SESSION)
    try:
        return asyncio.run(_obtain_with_session_maker(live_async_session_maker))
    except (_AsyncSessionNotObtained, MissingGreenlet):
        return _fail_obtain(LiveObtainReasonCode.FAIL_CLOSED_SESSION_UNREADABLE)
    except Exception:
        return _fail_obtain(LiveObtainReasonCode.FAIL_CLOSED_SESSION_UNREADABLE)
