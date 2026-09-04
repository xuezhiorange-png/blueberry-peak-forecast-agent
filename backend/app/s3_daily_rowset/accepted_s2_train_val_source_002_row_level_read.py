"""S3-A2 accepted S2 TRAIN/VALIDATION SOURCE_002 row-level-read attestation.

Hashes persisted TRAIN/VALIDATION `content_bytes` against the copied S2
acceptance-package official hashes. Does not trust the stored `content_sha256`
column. Does not return kilogram values, member rows, or partition bytes.
Default live session provider is bound by the live-session wiring module.

Official hash constants are a reference copy of the S2 acceptance package.
They are not recomputed here as new official values.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum

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
from backend.app.s3_daily_rowset.schemas import (
    EXPECTED_DATASET_ID,
    EXPECTED_DATASET_VERSION,
    EXPECTED_MATERIALIZED_DATASET_IDENTITY_SHA256,
)

OFFICIAL_DATASET_ID = EXPECTED_DATASET_ID
OFFICIAL_DATASET_VERSION = EXPECTED_DATASET_VERSION
OFFICIAL_MATERIALIZED_DATASET_IDENTITY_SHA256 = EXPECTED_MATERIALIZED_DATASET_IDENTITY_SHA256
OFFICIAL_TRAIN_ROW_COUNT = 16224
OFFICIAL_TRAIN_BYTE_COUNT = 9087071
OFFICIAL_TRAIN_CONTENT_SHA256 = "be2d4184434a0f389af21c315945322e9216cd17cc471b772e3fff389d3386d2"
OFFICIAL_VALIDATION_ROW_COUNT = 8006
OFFICIAL_VALIDATION_BYTE_COUNT = 4484905
OFFICIAL_VALIDATION_CONTENT_SHA256 = (
    "4cbf1119f83034464159210ebbbeea5ec87848f92ce044bb328949a8f5331d06"
)
SEALED_TEST_ROW_COUNT = 0
SEALED_TEST_BYTE_COUNT = 240
SEALED_TEST_CONTENT_SHA256 = "bd3d846a300c70a638bc169a095c3b02cb9e20c2c2aa6a96af0990d85a1fb1bd"

SessionProvider = Callable[[], Session | None]

_session_provider: SessionProvider | None = None


class Source002RowLevelReadReasonCode(StrEnum):
    ATTESTED = "ATTESTED"
    FAIL_CLOSED_NO_SESSION = "FAIL_CLOSED_NO_SESSION"
    FAIL_CLOSED_SESSION_UNREADABLE = "FAIL_CLOSED_SESSION_UNREADABLE"
    FAIL_CLOSED_NO_ACCEPTED_DATASET = "FAIL_CLOSED_NO_ACCEPTED_DATASET"
    FAIL_CLOSED_DATASET_IDENTITY_MISMATCH = "FAIL_CLOSED_DATASET_IDENTITY_MISMATCH"
    FAIL_CLOSED_MISSING_TRAIN_OR_VALIDATION_BYTES = "FAIL_CLOSED_MISSING_TRAIN_OR_VALIDATION_BYTES"
    FAIL_CLOSED_HASH_MISMATCH = "FAIL_CLOSED_HASH_MISMATCH"
    FAIL_CLOSED_COUNT_MISMATCH = "FAIL_CLOSED_COUNT_MISMATCH"
    FAIL_CLOSED_TEST_UNSEALED = "FAIL_CLOSED_TEST_UNSEALED"


class AcceptedS2TrainValSource002RowLevelReadAttestation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    attested: bool
    source_002_row_level_read: bool
    official_hashes_attested_from_a_live_read: bool
    reason_code: Source002RowLevelReadReasonCode
    dataset_id: str | None = None
    dataset_version: str | None = None
    materialized_dataset_identity_sha256: str | None = None
    train_row_count: int | None = None
    train_byte_count: int | None = None
    train_content_sha256: str | None = None
    validation_row_count: int | None = None
    validation_byte_count: int | None = None
    validation_content_sha256: str | None = None
    test_row_count: int | None = None
    test_remains_sealed: bool = True


def set_source_002_row_level_read_session_provider(
    provider: SessionProvider | None,
) -> None:
    global _session_provider
    _session_provider = provider


def clear_source_002_row_level_read_session_provider() -> None:
    set_source_002_row_level_read_session_provider(None)


def bound_source_002_row_level_read_session_provider() -> SessionProvider | None:
    return _session_provider


def attest_accepted_s2_train_val_source_002_row_level_read() -> (
    AcceptedS2TrainValSource002RowLevelReadAttestation
):
    if _session_provider is None:
        return _fail(Source002RowLevelReadReasonCode.FAIL_CLOSED_NO_SESSION)
    from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_session import (  # noqa: E501
        attest_source_002_via_async_session_run_sync,
        is_live_async_session_run_sync_provider,
    )

    if is_live_async_session_run_sync_provider(_session_provider):
        return attest_source_002_via_async_session_run_sync()
    try:
        session = _session_provider()
    except Exception:
        return _fail(Source002RowLevelReadReasonCode.FAIL_CLOSED_SESSION_UNREADABLE)
    if session is None:
        return _fail(Source002RowLevelReadReasonCode.FAIL_CLOSED_NO_SESSION)
    try:
        return _attest_from_session(session)
    except Exception:
        return _fail(Source002RowLevelReadReasonCode.FAIL_CLOSED_SESSION_UNREADABLE)


def _attestation(
    *,
    attested: bool,
    reason: Source002RowLevelReadReasonCode,
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
    test_row_count: int | None = None,
) -> AcceptedS2TrainValSource002RowLevelReadAttestation:
    return AcceptedS2TrainValSource002RowLevelReadAttestation(
        attested=attested,
        source_002_row_level_read=attested,
        official_hashes_attested_from_a_live_read=attested,
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
        test_row_count=test_row_count,
        test_remains_sealed=test_remains_sealed,
    )


def _fail(
    reason: Source002RowLevelReadReasonCode,
    *,
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
    test_row_count: int | None = None,
) -> AcceptedS2TrainValSource002RowLevelReadAttestation:
    return _attestation(
        attested=False,
        reason=reason,
        test_remains_sealed=test_remains_sealed,
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        materialized_dataset_identity_sha256=materialized_dataset_identity_sha256,
        train_row_count=train_row_count,
        train_byte_count=train_byte_count,
        train_content_sha256=train_content_sha256,
        validation_row_count=validation_row_count,
        validation_byte_count=validation_byte_count,
        validation_content_sha256=validation_content_sha256,
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


def _attest_from_session(
    session: Session,
) -> AcceptedS2TrainValSource002RowLevelReadAttestation:
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
            return _fail(Source002RowLevelReadReasonCode.FAIL_CLOSED_NO_ACCEPTED_DATASET)
        return _fail(
            Source002RowLevelReadReasonCode.FAIL_CLOSED_DATASET_IDENTITY_MISMATCH,
            dataset_id=any_source_002.dataset_id,
            dataset_version=any_source_002.dataset_version,
            materialized_dataset_identity_sha256=(
                any_source_002.materialized_dataset_identity_sha256
            ),
        )
    if accepted.quality_gate_status != QualityGateStatus.ACCEPTED.value:
        return _fail(
            Source002RowLevelReadReasonCode.FAIL_CLOSED_NO_ACCEPTED_DATASET,
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
            Source002RowLevelReadReasonCode.FAIL_CLOSED_DATASET_IDENTITY_MISMATCH,
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
            Source002RowLevelReadReasonCode.FAIL_CLOSED_MISSING_TRAIN_OR_VALIDATION_BYTES,
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
                Source002RowLevelReadReasonCode.FAIL_CLOSED_TEST_UNSEALED,
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
            Source002RowLevelReadReasonCode.FAIL_CLOSED_HASH_MISMATCH,
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
            Source002RowLevelReadReasonCode.FAIL_CLOSED_COUNT_MISMATCH,
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

    return _attestation(
        attested=True,
        reason=Source002RowLevelReadReasonCode.ATTESTED,
        dataset_id=accepted.dataset_id,
        dataset_version=accepted.dataset_version,
        materialized_dataset_identity_sha256=accepted.materialized_dataset_identity_sha256,
        train_row_count=train.row_count,
        train_byte_count=len(train_bytes),
        train_content_sha256=hashed_train,
        validation_row_count=validation.row_count,
        validation_byte_count=len(validation_bytes),
        validation_content_sha256=hashed_validation,
        test_row_count=test_row_count,
    )


def _bind_default_live_session_provider() -> None:
    module = __import__(
        "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_session",
        fromlist=("bind_default_source_002_row_level_read_live_session_provider",),
    )
    module.bind_default_source_002_row_level_read_live_session_provider()


_bind_default_live_session_provider()
