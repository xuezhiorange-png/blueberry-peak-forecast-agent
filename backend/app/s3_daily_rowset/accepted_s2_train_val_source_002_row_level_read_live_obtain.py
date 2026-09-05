"""Obtain accepted S2 TRAIN/VALIDATION content_bytes via the live production reader.

Default production execution uses AsyncSessionMaker.run_sync(_obtain_from_session).
Explicit sync-session injection remains supported for unit tests. Does not invent a
connection string or call create_engine. Obtaining content_bytes that then fail to
match official hashes is not SOURCE_002_ROW_LEVEL_READ and is not parent IMPLEMENTED.
TEST payload is never returned.
"""

from __future__ import annotations

from enum import StrEnum
from typing import cast

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

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
    bound_source_002_row_level_read_session_provider,
    uses_explicit_source_002_row_level_read_session_provider,
)


class LiveObtainReasonCode(StrEnum):
    OBTAINED = "OBTAINED"
    FAIL_CLOSED_NO_SESSION = "FAIL_CLOSED_NO_SESSION"
    FAIL_CLOSED_SESSION_UNREADABLE = "FAIL_CLOSED_SESSION_UNREADABLE"
    FAIL_CLOSED_NO_ASYNC_SESSION_MAKER = "FAIL_CLOSED_NO_ASYNC_SESSION_MAKER"
    FAIL_CLOSED_ASYNC_SESSION_NOT_OBTAINED = "FAIL_CLOSED_ASYNC_SESSION_NOT_OBTAINED"
    FAIL_CLOSED_ASYNC_SESSION_UNREADABLE = "FAIL_CLOSED_ASYNC_SESSION_UNREADABLE"
    FAIL_CLOSED_NO_ACCEPTED_DATASET = "FAIL_CLOSED_NO_ACCEPTED_DATASET"
    FAIL_CLOSED_DATASET_IDENTITY_MISMATCH = "FAIL_CLOSED_DATASET_IDENTITY_MISMATCH"
    FAIL_CLOSED_MISSING_TRAIN_OR_VALIDATION_BYTES = "FAIL_CLOSED_MISSING_TRAIN_OR_VALIDATION_BYTES"
    FAIL_CLOSED_TEST_UNSEALED = "FAIL_CLOSED_TEST_UNSEALED"


class AcceptedS2TrainValLiveObtainEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    obtained: bool
    source_002_row_level_read: bool
    official_hashes_attested_from_a_live_read: bool
    reason_code: LiveObtainReasonCode
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


def _obtain_via_explicit_sync_session_provider() -> AcceptedS2TrainValLiveObtainEnvelope:
    provider = bound_source_002_row_level_read_session_provider()
    if provider is None:
        return _fail(LiveObtainReasonCode.FAIL_CLOSED_NO_SESSION)
    try:
        session = provider()
    except Exception:
        return _fail(LiveObtainReasonCode.FAIL_CLOSED_SESSION_UNREADABLE)
    if session is None:
        return _fail(LiveObtainReasonCode.FAIL_CLOSED_NO_SESSION)
    try:
        return _obtain_from_session(session)
    except Exception:
        return _fail(LiveObtainReasonCode.FAIL_CLOSED_SESSION_UNREADABLE)


def _obtain_via_live_async_session_run_sync() -> AcceptedS2TrainValLiveObtainEnvelope:
    from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_run_sync import (  # noqa: E501
        AsyncSessionNotObtained,
        NoAsyncSessionMaker,
        run_live_source_002_sync_reader,
    )

    try:
        return cast(
            AcceptedS2TrainValLiveObtainEnvelope,
            run_live_source_002_sync_reader(_obtain_from_session),
        )
    except NoAsyncSessionMaker:
        return _fail(LiveObtainReasonCode.FAIL_CLOSED_NO_ASYNC_SESSION_MAKER)
    except AsyncSessionNotObtained:
        return _fail(LiveObtainReasonCode.FAIL_CLOSED_ASYNC_SESSION_NOT_OBTAINED)
    except Exception:
        return _fail(LiveObtainReasonCode.FAIL_CLOSED_ASYNC_SESSION_UNREADABLE)


def obtain_accepted_s2_train_val_content_bytes_from_bound_live_session() -> (
    AcceptedS2TrainValLiveObtainEnvelope
):
    if uses_explicit_source_002_row_level_read_session_provider():
        return _obtain_via_explicit_sync_session_provider()
    return _obtain_via_live_async_session_run_sync()


def _envelope(
    *,
    obtained: bool,
    reason: LiveObtainReasonCode,
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
) -> AcceptedS2TrainValLiveObtainEnvelope:
    return AcceptedS2TrainValLiveObtainEnvelope(
        obtained=obtained,
        source_002_row_level_read=False,
        official_hashes_attested_from_a_live_read=False,
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
    reason: LiveObtainReasonCode,
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
) -> AcceptedS2TrainValLiveObtainEnvelope:
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


def _obtain_from_session(session: Session) -> AcceptedS2TrainValLiveObtainEnvelope:
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
            return _fail(LiveObtainReasonCode.FAIL_CLOSED_NO_ACCEPTED_DATASET)
        return _fail(
            LiveObtainReasonCode.FAIL_CLOSED_DATASET_IDENTITY_MISMATCH,
            dataset_id=any_source_002.dataset_id,
            dataset_version=any_source_002.dataset_version,
            materialized_dataset_identity_sha256=(
                any_source_002.materialized_dataset_identity_sha256
            ),
        )
    if accepted.quality_gate_status != QualityGateStatus.ACCEPTED.value:
        return _fail(
            LiveObtainReasonCode.FAIL_CLOSED_NO_ACCEPTED_DATASET,
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
            LiveObtainReasonCode.FAIL_CLOSED_DATASET_IDENTITY_MISMATCH,
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
            LiveObtainReasonCode.FAIL_CLOSED_MISSING_TRAIN_OR_VALIDATION_BYTES,
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
                LiveObtainReasonCode.FAIL_CLOSED_TEST_UNSEALED,
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
        reason=LiveObtainReasonCode.OBTAINED,
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
