"""Obtain accepted S2 TRAIN/VALIDATION content_bytes through the already-obtained live AsyncSession.

Uses the application AsyncSessionMaker already configured in ``backend.app.db.session``.
Does not use ``bound_source_002_row_level_read_session_provider``. Does not invent a
connection string or call create_engine, create_async_engine, or construct a new async
session maker. TRAIN/VAL content_bytes obtained through the already-obtained live
AsyncSession are not SOURCE_002_ROW_LEVEL_READ and are not official-hash attestation.
"""

from __future__ import annotations

import asyncio
from enum import StrEnum

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker as _AsyncSessionMakerCls

from backend.app.s2_materialized_dataset.lane_d.hashing import content_sha256
from backend.app.s2_materialized_dataset.lane_d.service import (
    S2MaterializedDatasetModel,
    S2MaterializedPartitionModel,
)
from backend.app.s2_materialized_dataset.shared.contracts import (
    PartitionName,
    QualityGateStatus,
)
from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read import (
    OFFICIAL_DATASET_ID,
    OFFICIAL_DATASET_VERSION,
    OFFICIAL_MATERIALIZED_DATASET_IDENTITY_SHA256,
    SEALED_TEST_BYTE_COUNT,
    SEALED_TEST_CONTENT_SHA256,
    SEALED_TEST_ROW_COUNT,
)


class LiveAsyncObtainReasonCode(StrEnum):
    OBTAINED = "OBTAINED"
    FAIL_CLOSED_NO_ASYNC_SESSION_MAKER = "FAIL_CLOSED_NO_ASYNC_SESSION_MAKER"
    FAIL_CLOSED_ASYNC_SESSION_NOT_OBTAINED_FROM_SESSION_MAKER = (
        "FAIL_CLOSED_ASYNC_SESSION_NOT_OBTAINED_FROM_SESSION_MAKER"
    )
    FAIL_CLOSED_ASYNC_SESSION_UNREADABLE = "FAIL_CLOSED_ASYNC_SESSION_UNREADABLE"


_NOT_OBTAINED_FROM_SESSION_MAKER = (
    LiveAsyncObtainReasonCode.FAIL_CLOSED_ASYNC_SESSION_NOT_OBTAINED_FROM_SESSION_MAKER
)


class AcceptedS2TrainValLiveAsyncObtainEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    obtained: bool
    source_002_row_level_read: bool
    official_hashes_attested_from_a_live_read: bool
    accepted_s2_train_val_content_bytes_obtained_from_bound_live_session: bool
    reason_code: LiveAsyncObtainReasonCode
    dataset_id: str | None = None
    dataset_version: str | None = None
    materialized_dataset_identity_sha256: str | None = None
    train_content_bytes: bytes | None = None
    validation_content_bytes: bytes | None = None
    train_row_count: int | None = None
    train_byte_count: int | None = None
    validation_row_count: int | None = None
    validation_byte_count: int | None = None
    test_row_count: int | None = None
    test_remains_sealed: bool = True


# fmt: off
def obtain_accepted_s2_train_val_content_bytes_from_the_already_obtained_live_async_session \
(
) -> AcceptedS2TrainValLiveAsyncObtainEnvelope:
# fmt: on
    try:
        from backend.app.db.session import AsyncSessionMaker as live_async_session_maker
    except Exception:
        return _fail(LiveAsyncObtainReasonCode.FAIL_CLOSED_NO_ASYNC_SESSION_MAKER)
    if live_async_session_maker is None or not isinstance(
        live_async_session_maker, _AsyncSessionMakerCls
    ):
        return _fail(LiveAsyncObtainReasonCode.FAIL_CLOSED_NO_ASYNC_SESSION_MAKER)
    try:
        return asyncio.run(_obtain_with_session_maker(live_async_session_maker))
    except _AsyncSessionNotObtained:
        return _fail(_NOT_OBTAINED_FROM_SESSION_MAKER)
    except Exception:
        return _fail(LiveAsyncObtainReasonCode.FAIL_CLOSED_ASYNC_SESSION_UNREADABLE)


class _AsyncSessionNotObtained(RuntimeError):
    pass


def _envelope(
    *,
    obtained: bool,
    reason: LiveAsyncObtainReasonCode,
    test_remains_sealed: bool = True,
    dataset_id: str | None = None,
    dataset_version: str | None = None,
    materialized_dataset_identity_sha256: str | None = None,
    train_content_bytes: bytes | None = None,
    validation_content_bytes: bytes | None = None,
    train_row_count: int | None = None,
    train_byte_count: int | None = None,
    validation_row_count: int | None = None,
    validation_byte_count: int | None = None,
    test_row_count: int | None = None,
) -> AcceptedS2TrainValLiveAsyncObtainEnvelope:
    return AcceptedS2TrainValLiveAsyncObtainEnvelope(
        obtained=obtained,
        source_002_row_level_read=False,
        official_hashes_attested_from_a_live_read=False,
        accepted_s2_train_val_content_bytes_obtained_from_bound_live_session=False,
        reason_code=reason,
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        materialized_dataset_identity_sha256=materialized_dataset_identity_sha256,
        train_content_bytes=train_content_bytes,
        validation_content_bytes=validation_content_bytes,
        train_row_count=train_row_count,
        train_byte_count=train_byte_count,
        validation_row_count=validation_row_count,
        validation_byte_count=validation_byte_count,
        test_row_count=test_row_count,
        test_remains_sealed=test_remains_sealed,
    )


def _fail(
    reason: LiveAsyncObtainReasonCode,
    *,
    test_remains_sealed: bool = True,
    dataset_id: str | None = None,
    dataset_version: str | None = None,
    materialized_dataset_identity_sha256: str | None = None,
    train_row_count: int | None = None,
    train_byte_count: int | None = None,
    validation_row_count: int | None = None,
    validation_byte_count: int | None = None,
    test_row_count: int | None = None,
) -> AcceptedS2TrainValLiveAsyncObtainEnvelope:
    return _envelope(
        obtained=False,
        reason=reason,
        test_remains_sealed=test_remains_sealed,
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        materialized_dataset_identity_sha256=materialized_dataset_identity_sha256,
        train_row_count=train_row_count,
        train_byte_count=train_byte_count,
        validation_row_count=validation_row_count,
        validation_byte_count=validation_byte_count,
        test_row_count=test_row_count,
    )


def _as_bytes(value: object) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, memoryview):
        return bytes(value)
    return b""


def _one_partition(
    partitions: list[S2MaterializedPartitionModel],
    name: str,
) -> S2MaterializedPartitionModel | None:
    matches = [partition for partition in partitions if partition.partition_name == name]
    if len(matches) != 1:
        return None
    return matches[0]


async def _obtain_with_session_maker(
    live_async_session_maker: _AsyncSessionMakerCls[AsyncSession],
) -> AcceptedS2TrainValLiveAsyncObtainEnvelope:
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
) -> AcceptedS2TrainValLiveAsyncObtainEnvelope:
    try:
        accepted = await session.scalar(
            select(S2MaterializedDatasetModel).where(
                S2MaterializedDatasetModel.dataset_id == OFFICIAL_DATASET_ID,
                S2MaterializedDatasetModel.dataset_version == OFFICIAL_DATASET_VERSION,
            )
        )
        if accepted is None:
            any_source_002 = await session.scalar(
                select(S2MaterializedDatasetModel).where(
                    S2MaterializedDatasetModel.dataset_id == OFFICIAL_DATASET_ID
                )
            )
            if any_source_002 is None:
                return _fail(LiveAsyncObtainReasonCode.FAIL_CLOSED_ASYNC_SESSION_UNREADABLE)
            return _fail(
                LiveAsyncObtainReasonCode.FAIL_CLOSED_ASYNC_SESSION_UNREADABLE,
                dataset_id=any_source_002.dataset_id,
                dataset_version=any_source_002.dataset_version,
                materialized_dataset_identity_sha256=(
                    any_source_002.materialized_dataset_identity_sha256
                ),
            )
        if accepted.quality_gate_status != QualityGateStatus.ACCEPTED.value:
            return _fail(
                LiveAsyncObtainReasonCode.FAIL_CLOSED_ASYNC_SESSION_UNREADABLE,
                dataset_id=accepted.dataset_id,
                dataset_version=accepted.dataset_version,
                materialized_dataset_identity_sha256=(accepted.materialized_dataset_identity_sha256),
            )
        if (
            accepted.dataset_id != OFFICIAL_DATASET_ID
            or accepted.dataset_version != OFFICIAL_DATASET_VERSION
            or accepted.materialized_dataset_identity_sha256
            != OFFICIAL_MATERIALIZED_DATASET_IDENTITY_SHA256
        ):
            return _fail(
                LiveAsyncObtainReasonCode.FAIL_CLOSED_ASYNC_SESSION_UNREADABLE,
                dataset_id=accepted.dataset_id,
                dataset_version=accepted.dataset_version,
                materialized_dataset_identity_sha256=(accepted.materialized_dataset_identity_sha256),
            )

        partitions = list(
            (
                await session.scalars(
                    select(S2MaterializedPartitionModel).where(
                        S2MaterializedPartitionModel.materialized_dataset_id == accepted.id
                    )
                )
            ).all()
        )
        train = _one_partition(partitions, PartitionName.TRAIN.value)
        validation = _one_partition(partitions, PartitionName.VALIDATION.value)
        train_bytes = _as_bytes(train.content_bytes) if train is not None else b""
        validation_bytes = _as_bytes(validation.content_bytes) if validation is not None else b""
        if train is None or validation is None or not train_bytes or not validation_bytes:
            return _fail(
                LiveAsyncObtainReasonCode.FAIL_CLOSED_ASYNC_SESSION_UNREADABLE,
                dataset_id=accepted.dataset_id,
                dataset_version=accepted.dataset_version,
                materialized_dataset_identity_sha256=(accepted.materialized_dataset_identity_sha256),
            )

        test = _one_partition(partitions, PartitionName.TEST.value)
        test_row_count = test.row_count if test is not None else None
        test_bytes = _as_bytes(test.content_bytes) if test is not None else b""
        if test is not None:
            test_hash = content_sha256(test_bytes) if test_bytes else ""
            if (
                test.row_count != SEALED_TEST_ROW_COUNT
                or len(test_bytes) != SEALED_TEST_BYTE_COUNT
                or test_hash != SEALED_TEST_CONTENT_SHA256
            ):
                return _fail(
                    LiveAsyncObtainReasonCode.FAIL_CLOSED_ASYNC_SESSION_UNREADABLE,
                    test_remains_sealed=False,
                    dataset_id=accepted.dataset_id,
                    dataset_version=accepted.dataset_version,
                    materialized_dataset_identity_sha256=(
                        accepted.materialized_dataset_identity_sha256
                    ),
                    train_row_count=train.row_count,
                    train_byte_count=len(train_bytes),
                    validation_row_count=validation.row_count,
                    validation_byte_count=len(validation_bytes),
                    test_row_count=test_row_count,
                )

        return _envelope(
            obtained=True,
            reason=LiveAsyncObtainReasonCode.OBTAINED,
            dataset_id=accepted.dataset_id,
            dataset_version=accepted.dataset_version,
            materialized_dataset_identity_sha256=accepted.materialized_dataset_identity_sha256,
            train_content_bytes=train_bytes,
            validation_content_bytes=validation_bytes,
            train_row_count=train.row_count,
            train_byte_count=len(train_bytes),
            validation_row_count=validation.row_count,
            validation_byte_count=len(validation_bytes),
            test_row_count=test_row_count,
        )
    except Exception:
        return _fail(LiveAsyncObtainReasonCode.FAIL_CLOSED_ASYNC_SESSION_UNREADABLE)
