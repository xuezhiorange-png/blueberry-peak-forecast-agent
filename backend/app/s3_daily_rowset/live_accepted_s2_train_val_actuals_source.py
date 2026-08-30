"""Bind accepted S2 TRAIN/VALIDATION actuals into the S3-A daily rowset materializer.

Loads accepted TRAIN+VALIDATION partition bytes from the already-configured live
database via ``AsyncSessionMaker.run_sync``, hashes bytes with ``content_sha256``,
parses NDJSON into ``MaterializableRow``, and exposes an ``InMemoryS2ActualsSource``.
Does not return, log, or commit ``content_bytes``, kilogram values, or member lists.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker as _AsyncSessionMakerCls
from sqlalchemy.orm import Session

from backend.app.s2_materialized_dataset.lane_d.canonical import (
    MalformedPartitionBytesError,
    parse_partition_bytes,
)
from backend.app.s2_materialized_dataset.lane_d.hashing import content_sha256
from backend.app.s2_materialized_dataset.lane_d.service import (
    S2MaterializedDatasetModel,
    S2MaterializedPartitionModel,
)
from backend.app.s2_materialized_dataset.shared.contracts import (
    MaterializableRow,
    PartitionName,
    QualityGateStatus,
)
from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read import (
    OFFICIAL_DATASET_ID,
    OFFICIAL_DATASET_VERSION,
    OFFICIAL_MATERIALIZED_DATASET_IDENTITY_SHA256,
    OFFICIAL_TRAIN_BYTE_COUNT,
    OFFICIAL_TRAIN_CONTENT_SHA256,
    OFFICIAL_TRAIN_ROW_COUNT,
    OFFICIAL_VALIDATION_BYTE_COUNT,
    OFFICIAL_VALIDATION_CONTENT_SHA256,
    OFFICIAL_VALIDATION_ROW_COUNT,
    SEALED_TEST_BYTE_COUNT,
    SEALED_TEST_CONTENT_SHA256,
    SEALED_TEST_ROW_COUNT,
)
from backend.app.s3_daily_rowset.actuals import InMemoryS2ActualsSource, S2ActualsSourcePort


class LiveAcceptedS2TrainValActualsSourceReasonCode(StrEnum):
    BOUND = "BOUND"
    FAIL_CLOSED_NO_ASYNC_SESSION_MAKER = "FAIL_CLOSED_NO_ASYNC_SESSION_MAKER"
    FAIL_CLOSED_ASYNC_SESSION_NOT_OBTAINED_FROM_SESSION_MAKER = (
        "FAIL_CLOSED_ASYNC_SESSION_NOT_OBTAINED_FROM_SESSION_MAKER"
    )
    FAIL_CLOSED_ASYNC_SESSION_UNREADABLE = "FAIL_CLOSED_ASYNC_SESSION_UNREADABLE"
    FAIL_CLOSED_NO_ACCEPTED_DATASET = "FAIL_CLOSED_NO_ACCEPTED_DATASET"
    FAIL_CLOSED_DATASET_IDENTITY_MISMATCH = "FAIL_CLOSED_DATASET_IDENTITY_MISMATCH"
    FAIL_CLOSED_MISSING_TRAIN_OR_VALIDATION_BYTES = "FAIL_CLOSED_MISSING_TRAIN_OR_VALIDATION_BYTES"
    FAIL_CLOSED_HASH_MISMATCH = "FAIL_CLOSED_HASH_MISMATCH"
    FAIL_CLOSED_COUNT_MISMATCH = "FAIL_CLOSED_COUNT_MISMATCH"
    FAIL_CLOSED_TEST_UNSEALED = "FAIL_CLOSED_TEST_UNSEALED"
    FAIL_CLOSED_MALFORMED_PARTITION_BYTES = "FAIL_CLOSED_MALFORMED_PARTITION_BYTES"
    FAIL_CLOSED_PARSE_ROW_COUNT_MISMATCH = "FAIL_CLOSED_PARSE_ROW_COUNT_MISMATCH"


_REASON_NO_ASYNC_SESSION_MAKER = (
    LiveAcceptedS2TrainValActualsSourceReasonCode.FAIL_CLOSED_NO_ASYNC_SESSION_MAKER
)
_REASON_SESSION_UNREADABLE = (
    LiveAcceptedS2TrainValActualsSourceReasonCode.FAIL_CLOSED_ASYNC_SESSION_UNREADABLE
)
_REASON_NO_ACCEPTED_DATASET = (
    LiveAcceptedS2TrainValActualsSourceReasonCode.FAIL_CLOSED_NO_ACCEPTED_DATASET
)


class LiveAcceptedS2TrainValActualsBindingEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    bound: bool
    live_accepted_s2_train_val_actuals_source_bound: bool
    reason_code: LiveAcceptedS2TrainValActualsSourceReasonCode
    dataset_id: str | None = None
    dataset_version: str | None = None
    materialized_dataset_identity_sha256: str | None = None
    train_row_count: int | None = None
    train_byte_count: int | None = None
    train_content_sha256: str | None = None
    validation_row_count: int | None = None
    validation_byte_count: int | None = None
    validation_content_sha256: str | None = None
    parsed_train_row_count: int | None = None
    parsed_validation_row_count: int | None = None
    parsed_total_row_count: int | None = None
    test_row_count: int | None = None
    test_remains_sealed: bool = True


@dataclass(frozen=True, slots=True)
class LiveAcceptedS2TrainValActualsBindOutcome:
    envelope: LiveAcceptedS2TrainValActualsBindingEnvelope
    actuals_source: S2ActualsSourcePort | None = None


class _AsyncSessionNotObtained(RuntimeError):
    pass


def bind_live_accepted_s2_train_val_actuals_source() -> LiveAcceptedS2TrainValActualsBindOutcome:
    try:
        from backend.app.db.session import AsyncSessionMaker as live_async_session_maker
    except Exception:
        return _fail(_REASON_NO_ASYNC_SESSION_MAKER)
    if live_async_session_maker is None or not isinstance(
        live_async_session_maker, _AsyncSessionMakerCls
    ):
        return _fail(_REASON_NO_ASYNC_SESSION_MAKER)
    try:
        return asyncio.run(_bind_with_session_maker(live_async_session_maker))
    except _AsyncSessionNotObtained:
        return _fail(
            LiveAcceptedS2TrainValActualsSourceReasonCode.FAIL_CLOSED_ASYNC_SESSION_NOT_OBTAINED_FROM_SESSION_MAKER
        )
    except Exception:
        return _fail(_REASON_SESSION_UNREADABLE)


def _envelope(
    *,
    bound: bool,
    reason: LiveAcceptedS2TrainValActualsSourceReasonCode,
    test_remains_sealed: bool = True,
    dataset_id: str | None = None,
    dataset_version: str | None = None,
    materialized_dataset_identity_sha256: str | None = None,
    train_row_count: int | None = None,
    train_byte_count: int | None = None,
    train_content_sha256: str | None = None,
    validation_row_count: int | None = None,
    validation_byte_count: int | None = None,
    validation_content_sha256: str | None = None,
    parsed_train_row_count: int | None = None,
    parsed_validation_row_count: int | None = None,
    parsed_total_row_count: int | None = None,
    test_row_count: int | None = None,
) -> LiveAcceptedS2TrainValActualsBindingEnvelope:
    return LiveAcceptedS2TrainValActualsBindingEnvelope(
        bound=bound,
        live_accepted_s2_train_val_actuals_source_bound=bound,
        reason_code=reason,
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        materialized_dataset_identity_sha256=materialized_dataset_identity_sha256,
        train_row_count=train_row_count,
        train_byte_count=train_byte_count,
        train_content_sha256=train_content_sha256,
        validation_row_count=validation_row_count,
        validation_byte_count=validation_byte_count,
        validation_content_sha256=validation_content_sha256,
        parsed_train_row_count=parsed_train_row_count,
        parsed_validation_row_count=parsed_validation_row_count,
        parsed_total_row_count=parsed_total_row_count,
        test_row_count=test_row_count,
        test_remains_sealed=test_remains_sealed,
    )


def _fail(
    reason: LiveAcceptedS2TrainValActualsSourceReasonCode,
    **kwargs: object,
) -> LiveAcceptedS2TrainValActualsBindOutcome:
    return LiveAcceptedS2TrainValActualsBindOutcome(
        envelope=_envelope(bound=False, reason=reason, **kwargs),
        actuals_source=None,
    )


def _success(
    *,
    actuals_source: InMemoryS2ActualsSource,
    dataset_id: str,
    dataset_version: str,
    materialized_dataset_identity_sha256: str,
    train_row_count: int,
    train_byte_count: int,
    train_content_sha256: str,
    validation_row_count: int,
    validation_byte_count: int,
    validation_content_sha256: str,
    parsed_train_row_count: int,
    parsed_validation_row_count: int,
    test_row_count: int | None,
) -> LiveAcceptedS2TrainValActualsBindOutcome:
    return LiveAcceptedS2TrainValActualsBindOutcome(
        envelope=_envelope(
            bound=True,
            reason=LiveAcceptedS2TrainValActualsSourceReasonCode.BOUND,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            materialized_dataset_identity_sha256=materialized_dataset_identity_sha256,
            train_row_count=train_row_count,
            train_byte_count=train_byte_count,
            train_content_sha256=train_content_sha256,
            validation_row_count=validation_row_count,
            validation_byte_count=validation_byte_count,
            validation_content_sha256=validation_content_sha256,
            parsed_train_row_count=parsed_train_row_count,
            parsed_validation_row_count=parsed_validation_row_count,
            parsed_total_row_count=parsed_train_row_count + parsed_validation_row_count,
            test_row_count=test_row_count,
        ),
        actuals_source=actuals_source,
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


def _bind_from_sync_session(session: Session) -> LiveAcceptedS2TrainValActualsBindOutcome:
    accepted = session.scalar(
        select(S2MaterializedDatasetModel).where(
            S2MaterializedDatasetModel.dataset_id == OFFICIAL_DATASET_ID,
            S2MaterializedDatasetModel.dataset_version == OFFICIAL_DATASET_VERSION,
        )
    )
    if accepted is None:
        any_source_002 = session.scalar(
            select(S2MaterializedDatasetModel).where(
                S2MaterializedDatasetModel.dataset_id == OFFICIAL_DATASET_ID
            )
        )
        if any_source_002 is None:
            return _fail(_REASON_NO_ACCEPTED_DATASET)
        return _fail(
            LiveAcceptedS2TrainValActualsSourceReasonCode.FAIL_CLOSED_DATASET_IDENTITY_MISMATCH,
            dataset_id=any_source_002.dataset_id,
            dataset_version=any_source_002.dataset_version,
            materialized_dataset_identity_sha256=(
                any_source_002.materialized_dataset_identity_sha256
            ),
        )
    if accepted.quality_gate_status != QualityGateStatus.ACCEPTED.value:
        return _fail(
            LiveAcceptedS2TrainValActualsSourceReasonCode.FAIL_CLOSED_NO_ACCEPTED_DATASET,
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
            LiveAcceptedS2TrainValActualsSourceReasonCode.FAIL_CLOSED_DATASET_IDENTITY_MISMATCH,
            dataset_id=accepted.dataset_id,
            dataset_version=accepted.dataset_version,
            materialized_dataset_identity_sha256=(accepted.materialized_dataset_identity_sha256),
        )

    partitions = list(
        session.scalars(
            select(S2MaterializedPartitionModel).where(
                S2MaterializedPartitionModel.materialized_dataset_id == accepted.id
            )
        ).all()
    )
    train = _one_partition(partitions, PartitionName.TRAIN.value)
    validation = _one_partition(partitions, PartitionName.VALIDATION.value)
    train_bytes = _as_bytes(train.content_bytes) if train is not None else b""
    validation_bytes = _as_bytes(validation.content_bytes) if validation is not None else b""
    if train is None or validation is None or not train_bytes or not validation_bytes:
        return _fail(
            LiveAcceptedS2TrainValActualsSourceReasonCode.FAIL_CLOSED_MISSING_TRAIN_OR_VALIDATION_BYTES,
            dataset_id=accepted.dataset_id,
            dataset_version=accepted.dataset_version,
            materialized_dataset_identity_sha256=(accepted.materialized_dataset_identity_sha256),
        )

    test = _one_partition(partitions, PartitionName.TEST.value)
    test_row_count = test.row_count if test is not None else None
    test_bytes = _as_bytes(test.content_bytes) if test is not None else b""
    hashed_train = content_sha256(train_bytes)
    hashed_validation = content_sha256(validation_bytes)

    if test is not None:
        test_hash = content_sha256(test_bytes) if test_bytes else ""
        if (
            test.row_count != SEALED_TEST_ROW_COUNT
            or len(test_bytes) != SEALED_TEST_BYTE_COUNT
            or test_hash != SEALED_TEST_CONTENT_SHA256
        ):
            return _fail(
                LiveAcceptedS2TrainValActualsSourceReasonCode.FAIL_CLOSED_TEST_UNSEALED,
                test_remains_sealed=False,
                dataset_id=accepted.dataset_id,
                dataset_version=accepted.dataset_version,
                materialized_dataset_identity_sha256=(
                    accepted.materialized_dataset_identity_sha256
                ),
                train_row_count=train.row_count,
                train_byte_count=len(train_bytes),
                train_content_sha256=hashed_train,
                validation_row_count=validation.row_count,
                validation_byte_count=len(validation_bytes),
                validation_content_sha256=hashed_validation,
                test_row_count=test_row_count,
            )

    if (
        hashed_train != OFFICIAL_TRAIN_CONTENT_SHA256
        or hashed_validation != OFFICIAL_VALIDATION_CONTENT_SHA256
    ):
        return _fail(
            LiveAcceptedS2TrainValActualsSourceReasonCode.FAIL_CLOSED_HASH_MISMATCH,
            dataset_id=accepted.dataset_id,
            dataset_version=accepted.dataset_version,
            materialized_dataset_identity_sha256=(accepted.materialized_dataset_identity_sha256),
            train_row_count=train.row_count,
            train_byte_count=len(train_bytes),
            train_content_sha256=hashed_train,
            validation_row_count=validation.row_count,
            validation_byte_count=len(validation_bytes),
            validation_content_sha256=hashed_validation,
            test_row_count=test_row_count,
        )

    if (
        train.row_count != OFFICIAL_TRAIN_ROW_COUNT
        or len(train_bytes) != OFFICIAL_TRAIN_BYTE_COUNT
        or validation.row_count != OFFICIAL_VALIDATION_ROW_COUNT
        or len(validation_bytes) != OFFICIAL_VALIDATION_BYTE_COUNT
    ):
        return _fail(
            LiveAcceptedS2TrainValActualsSourceReasonCode.FAIL_CLOSED_COUNT_MISMATCH,
            dataset_id=accepted.dataset_id,
            dataset_version=accepted.dataset_version,
            materialized_dataset_identity_sha256=(accepted.materialized_dataset_identity_sha256),
            train_row_count=train.row_count,
            train_byte_count=len(train_bytes),
            train_content_sha256=hashed_train,
            validation_row_count=validation.row_count,
            validation_byte_count=len(validation_bytes),
            validation_content_sha256=hashed_validation,
            test_row_count=test_row_count,
        )

    try:
        parsed_train = parse_partition_bytes(train_bytes)
        parsed_validation = parse_partition_bytes(validation_bytes)
    except MalformedPartitionBytesError:
        return _fail(
            LiveAcceptedS2TrainValActualsSourceReasonCode.FAIL_CLOSED_MALFORMED_PARTITION_BYTES,
            dataset_id=accepted.dataset_id,
            dataset_version=accepted.dataset_version,
            materialized_dataset_identity_sha256=(accepted.materialized_dataset_identity_sha256),
            train_row_count=train.row_count,
            train_byte_count=len(train_bytes),
            train_content_sha256=hashed_train,
            validation_row_count=validation.row_count,
            validation_byte_count=len(validation_bytes),
            validation_content_sha256=hashed_validation,
            test_row_count=test_row_count,
        )

    if (
        len(parsed_train) != OFFICIAL_TRAIN_ROW_COUNT
        or len(parsed_validation) != OFFICIAL_VALIDATION_ROW_COUNT
    ):
        return _fail(
            LiveAcceptedS2TrainValActualsSourceReasonCode.FAIL_CLOSED_PARSE_ROW_COUNT_MISMATCH,
            dataset_id=accepted.dataset_id,
            dataset_version=accepted.dataset_version,
            materialized_dataset_identity_sha256=(accepted.materialized_dataset_identity_sha256),
            train_row_count=train.row_count,
            train_byte_count=len(train_bytes),
            train_content_sha256=hashed_train,
            validation_row_count=validation.row_count,
            validation_byte_count=len(validation_bytes),
            validation_content_sha256=hashed_validation,
            parsed_train_row_count=len(parsed_train),
            parsed_validation_row_count=len(parsed_validation),
            test_row_count=test_row_count,
        )

    combined_rows: tuple[MaterializableRow, ...] = parsed_train + parsed_validation
    actuals_source = InMemoryS2ActualsSource(combined_rows)
    return _success(
        actuals_source=actuals_source,
        dataset_id=accepted.dataset_id,
        dataset_version=accepted.dataset_version,
        materialized_dataset_identity_sha256=accepted.materialized_dataset_identity_sha256,
        train_row_count=train.row_count,
        train_byte_count=len(train_bytes),
        train_content_sha256=hashed_train,
        validation_row_count=validation.row_count,
        validation_byte_count=len(validation_bytes),
        validation_content_sha256=hashed_validation,
        parsed_train_row_count=len(parsed_train),
        parsed_validation_row_count=len(parsed_validation),
        test_row_count=test_row_count,
    )


async def _bind_with_session_maker(
    live_async_session_maker: _AsyncSessionMakerCls[AsyncSession],
) -> LiveAcceptedS2TrainValActualsBindOutcome:
    session_cm = live_async_session_maker()
    try:
        session = await session_cm.__aenter__()
    except Exception as exc:
        raise _AsyncSessionNotObtained() from exc
    try:
        if session is None:
            raise _AsyncSessionNotObtained()
        return await session.run_sync(_bind_from_sync_session)
    finally:
        await session_cm.__aexit__(None, None, None)
