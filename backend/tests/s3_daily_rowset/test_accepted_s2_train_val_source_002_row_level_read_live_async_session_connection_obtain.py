"""S3-A2 accepted S2 TRAIN/VAL SOURCE_002 live-async-session-connection-obtain tests."""

from __future__ import annotations

import asyncio
import importlib
import subprocess
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.schema import Table

from backend.app.s2_materialized_dataset.lane_d.canonical import build_test_synthetic_bytes
from backend.app.s2_materialized_dataset.lane_d.hashing import content_sha256
from backend.app.s2_materialized_dataset.lane_d.partitions import TEST_END, TEST_START
from backend.app.s2_materialized_dataset.lane_d.service import (
    S2MaterializedDatasetModel,
    S2MaterializedPartitionModel,
)
from backend.app.s2_materialized_dataset.shared.contracts import (
    SOURCE_002_ROW_LEVEL_READ,
    SPLIT_POLICY_VERSION,
)
from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read import (
    OFFICIAL_DATASET_ID,
    OFFICIAL_DATASET_VERSION,
    OFFICIAL_MATERIALIZED_DATASET_IDENTITY_SHA256,
    AcceptedS2TrainValSource002RowLevelReadAttestation,
    clear_source_002_row_level_read_session_provider,
)

_connection_obtain = importlib.import_module(
    "backend.app.s3_daily_rowset."
    "accepted_s2_train_val_source_002_row_level_read_live_async_session_connection_obtain"
)
_connection_query = importlib.import_module(
    "backend.app.s3_daily_rowset."
    "accepted_s2_train_val_source_002_row_level_read_live_async_session_connection_query"
)
_async_session_connection = importlib.import_module(
    "backend.app.s3_daily_rowset."
    "accepted_s2_train_val_source_002_row_level_read_live_async_session_connection"
)
_async_session_query = importlib.import_module(
    "backend.app.s3_daily_rowset."
    "accepted_s2_train_val_source_002_row_level_read_live_async_session_query"
)
_async_session_bind = importlib.import_module(
    "backend.app.s3_daily_rowset."
    "accepted_s2_train_val_source_002_row_level_read_live_async_session_bind"
)
_async_obtain = importlib.import_module(
    "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_async_obtain"
)
AcceptedS2TrainValLiveAsyncSessionConnectionObtainEnvelope = (
    _connection_obtain.AcceptedS2TrainValLiveAsyncSessionConnectionObtainEnvelope
)
LiveAsyncSessionConnectionObtainReasonCode = (
    _connection_obtain.LiveAsyncSessionConnectionObtainReasonCode
)
obtain_accepted_s2_train_val_content_bytes_from_the_already_obtained_live_async_session_connection = _connection_obtain.obtain_accepted_s2_train_val_content_bytes_from_the_already_obtained_live_async_session_connection  # noqa: E501
probe_accepted_s2_train_val_already_obtained_live_async_session_connection_queryability = _connection_query.probe_accepted_s2_train_val_already_obtained_live_async_session_connection_queryability  # noqa: E501
obtain_accepted_s2_train_val_async_connection_from_the_already_obtained_live_async_session_connection = _async_session_connection.obtain_accepted_s2_train_val_async_connection_from_the_already_obtained_live_async_session_connection  # noqa: E501
probe_accepted_s2_train_val_already_obtained_live_async_session_queryability = _async_session_query.probe_accepted_s2_train_val_already_obtained_live_async_session_queryability  # noqa: E501
obtain_accepted_s2_train_val_async_connection_from_the_already_obtained_live_async_session_bind = _async_session_bind.obtain_accepted_s2_train_val_async_connection_from_the_already_obtained_live_async_session_bind  # noqa: E501
obtain_accepted_s2_train_val_content_bytes_from_the_already_obtained_live_async_session = _async_obtain.obtain_accepted_s2_train_val_content_bytes_from_the_already_obtained_live_async_session  # noqa: E501
LiveAsyncSessionConnectionQueryReasonCode = (
    _connection_query.LiveAsyncSessionConnectionQueryReasonCode
)
LiveAsyncSessionConnectionReasonCode = (
    _async_session_connection.LiveAsyncSessionConnectionReasonCode
)
LiveAsyncSessionQueryReasonCode = _async_session_query.LiveAsyncSessionQueryReasonCode
LiveAsyncSessionBindReasonCode = _async_session_bind.LiveAsyncSessionBindReasonCode
LiveAsyncObtainReasonCode = _async_obtain.LiveAsyncObtainReasonCode

TEST_CATALOG_ARTIFACT_PY_BLOB = "af59a9f1d291ab32eff23684aca477f0e4a852cd"
PARENT_READER_TEST_PY_BLOB = "bca600a15ebf3daa292050ab52ebcebfd953540a"
LIVE_SESSION_TEST_PY_BLOB = "c1ba24a1b87269d998b243002c231d654b08eb5a"
LIVE_OBTAIN_TEST_PY_BLOB = "0f54d1db37374bba4f5fcadc726baf0dff3c22b0"
LIVE_SESSION_QUERY_TEST_PY_BLOB = "00aabd3376c3f1a1fa41349627a7a7faa0352b69"
LIVE_CONNECTION_TEST_PY_BLOB = "2ebc0fa5ae9359f965964a8a70f2c5d65e7929e3"
LIVE_ASYNC_CONNECTION_TEST_PY_BLOB = "542e5c86812a20824f32f2085186e8a422db71d7"
LIVE_ASYNC_SESSION_TEST_PY_BLOB = "1e56e51f94f986de9686a34df9be80d1f741ddb4"
LIVE_ASYNC_OBTAIN_TEST_PY_BLOB = "b40cba70f8947954d95557523f9573cf5bc6d357"
LIVE_ASYNC_SESSION_QUERY_TEST_PY_BLOB = "f1045649d9a38203e892656da8883753fa9ba9f7"
LIVE_ASYNC_SESSION_BIND_TEST_PY_BLOB = "db5fce3c1db0f6ce7bc4155ba47ec412295963ea"
LIVE_ASYNC_SESSION_CONNECTION_TEST_PY_BLOB = "f29c83c45ec8846386d01a2342397bf1cab539ea"
LIVE_ASYNC_SESSION_CONNECTION_QUERY_TEST_PY_BLOB = "15f5b018ab19e41942885a06dc74b0259934ce0b"
PARENT_READER_PY_BLOB = "2a9232064179da89484d52dcf203c95a0fa71a68"
LIVE_SESSION_PY_BLOB = "28513a5b86659bed784e64d2060c53088149dc96"
LIVE_OBTAIN_PY_BLOB = "bf6e50cccf172f00c9be224d3d42bd2b1ef1bf8c"
LIVE_SESSION_QUERY_PY_BLOB = "d6a082dcabd7fbd1db324fd8ba6153ea2240fe39"
LIVE_CONNECTION_PY_BLOB = "f87bdf8b8add435298056f61614ee1d91c9dbbf0"
LIVE_ASYNC_CONNECTION_PY_BLOB = "51672d5a159d0889a159d9c03e8191e7f8a6b344"
LIVE_ASYNC_SESSION_PY_BLOB = "40afc94dacb2208accd4903b12ae46152a750b41"
LIVE_ASYNC_OBTAIN_PY_BLOB = "01f0e6e75f527514c5a08208f91eaec99a0154d1"
LIVE_ASYNC_SESSION_QUERY_PY_BLOB = "4d946c02acff3a257817e714ad824f9b311d42ec"
LIVE_ASYNC_SESSION_BIND_PY_BLOB = "a955a2de32209e8cd0fa7a8609029336c7a6d4fc"
LIVE_ASYNC_SESSION_CONNECTION_PY_BLOB = "222166655ad4822a6ae943e132c0abcd3aa33dde"
LIVE_ASYNC_SESSION_CONNECTION_QUERY_PY_BLOB = "90415c54ce07a82ce4567084f01aaea75a7b7a9c"
SESSION_PY_BLOB = "49845a077d252af2a7a246fa25616d7595535037"
READER_MODULE = Path(
    "backend/app/s3_daily_rowset/accepted_s2_train_val_source_002_row_level_read.py"
)
LIVE_SESSION_MODULE = Path(
    "backend/app/s3_daily_rowset/accepted_s2_train_val_source_002_row_level_read_live_session.py"
)
LIVE_OBTAIN_MODULE = Path(
    "backend/app/s3_daily_rowset/accepted_s2_train_val_source_002_row_level_read_live_obtain.py"
)
LIVE_SESSION_QUERY_MODULE = Path(
    "backend/app/s3_daily_rowset/"
    "accepted_s2_train_val_source_002_row_level_read_live_session_query.py"
)
LIVE_CONNECTION_MODULE = Path(
    "backend/app/s3_daily_rowset/accepted_s2_train_val_source_002_row_level_read_live_connection.py"
)
LIVE_ASYNC_CONNECTION_MODULE = Path(
    "backend/app/s3_daily_rowset/"
    "accepted_s2_train_val_source_002_row_level_read_live_async_connection.py"
)
LIVE_ASYNC_SESSION_MODULE = Path(
    "backend/app/s3_daily_rowset/"
    "accepted_s2_train_val_source_002_row_level_read_live_async_session.py"
)
LIVE_ASYNC_OBTAIN_MODULE = Path(
    "backend/app/s3_daily_rowset/"
    "accepted_s2_train_val_source_002_row_level_read_live_async_obtain.py"
)
LIVE_ASYNC_SESSION_QUERY_MODULE = Path(
    "backend/app/s3_daily_rowset/"
    "accepted_s2_train_val_source_002_row_level_read_live_async_session_query.py"
)
LIVE_ASYNC_SESSION_BIND_MODULE = Path(
    "backend/app/s3_daily_rowset/"
    "accepted_s2_train_val_source_002_row_level_read_live_async_session_bind.py"
)
LIVE_ASYNC_SESSION_CONNECTION_MODULE = Path(
    "backend/app/s3_daily_rowset/"
    "accepted_s2_train_val_source_002_row_level_read_live_async_session_connection.py"
)
LIVE_ASYNC_SESSION_CONNECTION_QUERY_MODULE = Path(
    "backend/app/s3_daily_rowset/"
    "accepted_s2_train_val_source_002_row_level_read_live_async_session_connection_query.py"
)
CONNECTION_OBTAIN_MODULE = Path(
    "backend/app/s3_daily_rowset/"
    "accepted_s2_train_val_source_002_row_level_read_live_async_session_connection_obtain.py"
)
SESSION_MODULE = Path("backend/app/db/session.py")
SYNTHETIC_TRAIN_BYTES = b"synthetic-train-partition\n"
SYNTHETIC_VAL_BYTES = b"synthetic-validation-partition\n"


def _sealed_test_bytes() -> bytes:
    return build_test_synthetic_bytes(
        partition_name="TEST",
        partition_start_date=TEST_START.isoformat(),
        partition_end_date=TEST_END.isoformat(),
        split_policy_version=SPLIT_POLICY_VERSION,
    )


def _placeholder_sha(label: str) -> str:
    return content_sha256(label.encode("utf-8"))


def _create_tables(sync_conn: sa.Connection) -> None:
    cast(Table, S2MaterializedDatasetModel.__table__).create(sync_conn)
    cast(Table, S2MaterializedPartitionModel.__table__).create(sync_conn)


async def _persist_accepted_dataset_async(
    session: AsyncSession,
    *,
    dataset_id: str = OFFICIAL_DATASET_ID,
    dataset_version: str = OFFICIAL_DATASET_VERSION,
    identity: str = OFFICIAL_MATERIALIZED_DATASET_IDENTITY_SHA256,
    train_bytes: bytes = SYNTHETIC_TRAIN_BYTES,
    validation_bytes: bytes = SYNTHETIC_VAL_BYTES,
) -> None:
    now = datetime(2026, 4, 1, tzinfo=UTC)
    dataset = S2MaterializedDatasetModel(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        materialized_dataset_identity_sha256=identity,
        source_cohort_id="source-002-s1-cohort-v1",
        source_cohort_manifest_sha256=(
            "27ddb9a77d9ce7d4b0579d0648c23b5ade7d6a090626b695e5b41827e714fcca"
        ),
        raw_policy_version="v0-3-s2-raw-policy-v1",
        cleaning_policy_version="v0-3-s2-cleaning-policy-v1",
        correction_policy_version="v0-3-s2-correction-policy-v1",
        exclusion_policy_version="v0-3-s2-exclusion-policy-v1",
        visibility_policy_version="v0-3-s2-visibility-policy-v1",
        revision_winner_policy_version="v0-3-s2-revision-winner-policy-v1",
        cleaned_dataset_version_identity="cleaned-dataset-v1",
        builder_version="v0-3-s2-lane-d-builder-r1",
        dataset_schema_version="v0-3-s2-materialized-dataset-v1",
        lineage_complete=True,
        quality_gate_status="ACCEPTED",
        build_started_at=now,
        build_completed_at=now,
        upstream_snapshot_sha256=_placeholder_sha("upstream"),
    )
    session.add(dataset)
    await session.flush()
    for name, start, end, content_bytes, row_count in (
        ("TRAIN", date(2025, 8, 5), date(2026, 1, 30), train_bytes, 1),
        ("VALIDATION", date(2026, 1, 31), date(2026, 3, 9), validation_bytes, 1),
        ("TEST", TEST_START, TEST_END, _sealed_test_bytes(), 0),
    ):
        session.add(
            S2MaterializedPartitionModel(
                materialized_dataset_id=dataset.id,
                partition_name=name,
                partition_start_date=start,
                partition_end_date=end,
                partition_date_field="HARVEST_BUSINESS_DATE",
                target_decision="OBSERVED_FARM_PICK_QUANTITY",
                canonical_grain="SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE",
                split_policy_version=SPLIT_POLICY_VERSION,
                manifest_schema_version="v0-3-s2-materialized-dataset-manifest-v1",
                materialized_partition_schema_version="v0-3-s2-materialized-partition-v1",
                row_count=row_count,
                byte_count=len(content_bytes),
                content_sha256=content_sha256(content_bytes),
                partition_identity_sha256=_placeholder_sha(f"identity-{name}"),
                manifest_sha256=_placeholder_sha(f"manifest-{name}"),
                content_bytes=content_bytes,
                lineage_complete=True,
                quality_gate_status="ACCEPTED",
                rebuild_hash_replay_status="PASS",
            )
        )
    await session.commit()


async def _async_session_maker_with_dataset() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(_create_tables)
    session_maker: async_sessionmaker[AsyncSession] = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_maker() as session:
        await _persist_accepted_dataset_async(session)
    return session_maker


def _session_maker_with_dataset() -> async_sessionmaker[AsyncSession]:
    return asyncio.run(_async_session_maker_with_dataset())


@pytest.fixture(autouse=True)
def _restore_session_provider() -> Iterator[None]:
    clear_source_002_row_level_read_session_provider()
    yield
    clear_source_002_row_level_read_session_provider()


def _assert_not_source_002(envelope: Any) -> None:
    assert envelope.source_002_row_level_read is False
    assert envelope.official_hashes_attested_from_a_live_read is False
    if hasattr(envelope, "accepted_s2_train_val_content_bytes_obtained_from_bound_live_session"):
        assert (
            envelope.accepted_s2_train_val_content_bytes_obtained_from_bound_live_session is False
        )
    assert SOURCE_002_ROW_LEVEL_READ is False


def test_official_live_async_session_connection_obtain_path_fail_closed_or_obtained() -> None:
    envelope = obtain_accepted_s2_train_val_content_bytes_from_the_already_obtained_live_async_session_connection()  # noqa: E501

    if envelope.obtained:
        assert envelope.reason_code is LiveAsyncSessionConnectionObtainReasonCode.OBTAINED
        assert envelope.train_content_bytes is not None
        assert envelope.validation_content_bytes is not None
    else:
        assert envelope.reason_code is not LiveAsyncSessionConnectionObtainReasonCode.OBTAINED
        assert envelope.train_content_bytes is None
        assert envelope.validation_content_bytes is None
    _assert_not_source_002(envelope)


def test_synthetic_sqlite_aiosqlite_obtained_is_not_official_live_async_session_connection_obtain() -> (  # noqa: E501
    None
):
    session_maker = _session_maker_with_dataset()

    with patch("backend.app.db.session.AsyncSessionMaker", session_maker):
        envelope = obtain_accepted_s2_train_val_content_bytes_from_the_already_obtained_live_async_session_connection()  # noqa: E501

    assert envelope.obtained is True
    assert envelope.reason_code is LiveAsyncSessionConnectionObtainReasonCode.OBTAINED
    assert envelope.train_content_bytes == SYNTHETIC_TRAIN_BYTES
    assert envelope.validation_content_bytes == SYNTHETIC_VAL_BYTES
    assert envelope.test_remains_sealed is True
    _assert_not_source_002(envelope)
    assert content_sha256(envelope.train_content_bytes) != (
        "be2d4184434a0f389af21c315945322e9216cd17cc471b772e3fff389d3386d2"
    )


def test_missing_async_session_maker_fail_closes_no_async_session_maker() -> None:
    with patch("backend.app.db.session.AsyncSessionMaker", None):
        envelope = obtain_accepted_s2_train_val_content_bytes_from_the_already_obtained_live_async_session_connection()  # noqa: E501

    assert envelope.obtained is False
    assert (
        envelope.reason_code
        is LiveAsyncSessionConnectionObtainReasonCode.FAIL_CLOSED_NO_ASYNC_SESSION_MAKER
    )
    _assert_not_source_002(envelope)


def test_session_maker_that_raises_on_enter_fail_closes_not_obtained() -> None:
    failing_ctx = AsyncMock()
    failing_ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("session refused"))
    failing_ctx.__aexit__ = AsyncMock(return_value=None)
    failing_maker = MagicMock(return_value=failing_ctx)
    failing_maker.__class__ = async_sessionmaker

    with patch("backend.app.db.session.AsyncSessionMaker", failing_maker):
        envelope = obtain_accepted_s2_train_val_content_bytes_from_the_already_obtained_live_async_session_connection()  # noqa: E501

    assert envelope.obtained is False
    assert envelope.reason_code is (
        LiveAsyncSessionConnectionObtainReasonCode.FAIL_CLOSED_ASYNC_SESSION_NOT_OBTAINED_FROM_SESSION_MAKER
    )
    _assert_not_source_002(envelope)


def test_session_connection_returns_none_fail_closes_not_obtained_from_session_connection() -> None:
    no_connection_session = AsyncMock(spec=AsyncSession)
    no_connection_session.connection = AsyncMock(return_value=None)
    readable_ctx = AsyncMock()
    readable_ctx.__aenter__ = AsyncMock(return_value=no_connection_session)
    readable_ctx.__aexit__ = AsyncMock(return_value=None)
    readable_maker = MagicMock(return_value=readable_ctx)
    readable_maker.__class__ = async_sessionmaker

    with patch("backend.app.db.session.AsyncSessionMaker", readable_maker):
        envelope = obtain_accepted_s2_train_val_content_bytes_from_the_already_obtained_live_async_session_connection()  # noqa: E501

    assert envelope.obtained is False
    assert envelope.reason_code is (
        LiveAsyncSessionConnectionObtainReasonCode.FAIL_CLOSED_ASYNC_CONNECTION_NOT_OBTAINED_FROM_SESSION_CONNECTION
    )
    _assert_not_source_002(envelope)


def test_session_connection_raises_fail_closes_not_obtained_from_session_connection() -> None:
    failing_session = AsyncMock(spec=AsyncSession)
    failing_session.connection = AsyncMock(side_effect=RuntimeError("connection refused"))
    readable_ctx = AsyncMock()
    readable_ctx.__aenter__ = AsyncMock(return_value=failing_session)
    readable_ctx.__aexit__ = AsyncMock(return_value=None)
    readable_maker = MagicMock(return_value=readable_ctx)
    readable_maker.__class__ = async_sessionmaker

    with patch("backend.app.db.session.AsyncSessionMaker", readable_maker):
        envelope = obtain_accepted_s2_train_val_content_bytes_from_the_already_obtained_live_async_session_connection()  # noqa: E501

    assert envelope.obtained is False
    assert envelope.reason_code is (
        LiveAsyncSessionConnectionObtainReasonCode.FAIL_CLOSED_ASYNC_CONNECTION_NOT_OBTAINED_FROM_SESSION_CONNECTION
    )
    _assert_not_source_002(envelope)


def test_unreadable_async_connection_fail_closes_session_connection_unreadable() -> None:
    unreadable_connection = AsyncMock(spec=AsyncConnection)
    unreadable_connection.scalar = AsyncMock(side_effect=RuntimeError("unreadable"))
    unreadable_connection.scalars = AsyncMock(side_effect=RuntimeError("unreadable"))
    readable_session = AsyncMock(spec=AsyncSession)
    readable_session.connection = AsyncMock(return_value=unreadable_connection)
    readable_ctx = AsyncMock()
    readable_ctx.__aenter__ = AsyncMock(return_value=readable_session)
    readable_ctx.__aexit__ = AsyncMock(return_value=None)
    readable_maker = MagicMock(return_value=readable_ctx)
    readable_maker.__class__ = async_sessionmaker

    with patch("backend.app.db.session.AsyncSessionMaker", readable_maker):
        envelope = obtain_accepted_s2_train_val_content_bytes_from_the_already_obtained_live_async_session_connection()  # noqa: E501

    assert envelope.obtained is False
    assert envelope.reason_code is (
        LiveAsyncSessionConnectionObtainReasonCode.FAIL_CLOSED_ASYNC_SESSION_CONNECTION_UNREADABLE
    )
    assert envelope.train_content_bytes is None
    assert envelope.validation_content_bytes is None
    _assert_not_source_002(envelope)


def test_async_session_connection_obtain_envelope_has_obtained_not_queryable_or_connected() -> None:
    field_names = set(AcceptedS2TrainValLiveAsyncSessionConnectionObtainEnvelope.model_fields)
    assert "obtained" in field_names
    assert "queryable" not in field_names
    assert "connected" not in field_names
    assert "train_content_bytes" in field_names
    assert "validation_content_bytes" in field_names
    assert "test_content_bytes" not in field_names
    assert "content_bytes" not in field_names
    assert "actual_harvest_quantity_kg" not in field_names
    assert "farm" not in field_names
    assert "members" not in field_names


def test_parent_attestation_model_still_does_not_expose_content_bytes() -> None:
    field_names = set(AcceptedS2TrainValSource002RowLevelReadAttestation.model_fields)
    assert "content_bytes" not in field_names
    assert "train_content_bytes" not in field_names
    assert "validation_content_bytes" not in field_names


def test_sibling_connection_query_connection_bind_and_async_obtain_still_not_source_002() -> None:
    connection_query_envelope = (
        probe_accepted_s2_train_val_already_obtained_live_async_session_connection_queryability()
    )
    connection_envelope = obtain_accepted_s2_train_val_async_connection_from_the_already_obtained_live_async_session_connection()  # noqa: E501
    query_envelope = probe_accepted_s2_train_val_already_obtained_live_async_session_queryability()
    bind_envelope = obtain_accepted_s2_train_val_async_connection_from_the_already_obtained_live_async_session_bind()  # noqa: E501
    async_obtain_envelope = (
        obtain_accepted_s2_train_val_content_bytes_from_the_already_obtained_live_async_session()
    )

    if connection_query_envelope.queryable:
        assert (
            connection_query_envelope.reason_code
            is LiveAsyncSessionConnectionQueryReasonCode.QUERYABLE
        )
    else:
        assert (
            connection_query_envelope.reason_code
            is not LiveAsyncSessionConnectionQueryReasonCode.QUERYABLE
        )
    if connection_envelope.connected:
        assert connection_envelope.reason_code is LiveAsyncSessionConnectionReasonCode.CONNECTED
    else:
        assert connection_envelope.reason_code is not LiveAsyncSessionConnectionReasonCode.CONNECTED
    if query_envelope.queryable:
        assert query_envelope.reason_code is LiveAsyncSessionQueryReasonCode.QUERYABLE
    else:
        assert query_envelope.reason_code is not LiveAsyncSessionQueryReasonCode.QUERYABLE
    if bind_envelope.connected:
        assert bind_envelope.reason_code is LiveAsyncSessionBindReasonCode.CONNECTED
    else:
        assert bind_envelope.reason_code is not LiveAsyncSessionBindReasonCode.CONNECTED
    if async_obtain_envelope.obtained:
        assert async_obtain_envelope.reason_code is LiveAsyncObtainReasonCode.OBTAINED
    else:
        assert async_obtain_envelope.reason_code is not LiveAsyncObtainReasonCode.OBTAINED
    _assert_not_source_002(connection_query_envelope)
    _assert_not_source_002(connection_envelope)
    _assert_not_source_002(query_envelope)
    _assert_not_source_002(bind_envelope)
    _assert_not_source_002(async_obtain_envelope)


def test_s2_source_002_row_level_read_constant_remains_false() -> None:
    assert SOURCE_002_ROW_LEVEL_READ is False


def test_async_session_connection_obtain_module_contains_session_connection_not_session_scalar() -> (
    None
):  # noqa: E501
    source = CONNECTION_OBTAIN_MODULE.read_text(encoding="utf-8").lower()
    assert "session.connection(" in source
    assert "session.scalar(" not in source
    assert "connection.scalar(" in source


def test_async_session_connection_obtain_module_contains_no_forbidden_patterns() -> None:
    source = CONNECTION_OBTAIN_MODULE.read_text(encoding="utf-8").lower()
    assert "postgresql://" not in source
    assert "create_engine(" not in source
    assert "create_async_engine(" not in source
    assert "async_sessionmaker(" not in source
    assert "engine.connect(" not in source
    assert "get_bind(" not in source
    assert "bind.connect(" not in source
    assert "run_sync(" not in source
    assert "bound_source_002_row_level_read_session_provider(" not in source


def test_parent_reader_live_session_obtain_and_async_siblings_blobs_unchanged() -> None:
    reader_blob = subprocess.check_output(
        ["git", "hash-object", str(READER_MODULE)],
        text=True,
    ).strip()
    live_session_blob = subprocess.check_output(
        ["git", "hash-object", str(LIVE_SESSION_MODULE)],
        text=True,
    ).strip()
    obtain_blob = subprocess.check_output(
        ["git", "hash-object", str(LIVE_OBTAIN_MODULE)],
        text=True,
    ).strip()
    query_blob = subprocess.check_output(
        ["git", "hash-object", str(LIVE_SESSION_QUERY_MODULE)],
        text=True,
    ).strip()
    live_connection_blob = subprocess.check_output(
        ["git", "hash-object", str(LIVE_CONNECTION_MODULE)],
        text=True,
    ).strip()
    live_async_connection_blob = subprocess.check_output(
        ["git", "hash-object", str(LIVE_ASYNC_CONNECTION_MODULE)],
        text=True,
    ).strip()
    live_async_session_blob = subprocess.check_output(
        ["git", "hash-object", str(LIVE_ASYNC_SESSION_MODULE)],
        text=True,
    ).strip()
    live_async_obtain_blob = subprocess.check_output(
        ["git", "hash-object", str(LIVE_ASYNC_OBTAIN_MODULE)],
        text=True,
    ).strip()
    live_async_session_query_blob = subprocess.check_output(
        ["git", "hash-object", str(LIVE_ASYNC_SESSION_QUERY_MODULE)],
        text=True,
    ).strip()
    live_async_session_bind_blob = subprocess.check_output(
        ["git", "hash-object", str(LIVE_ASYNC_SESSION_BIND_MODULE)],
        text=True,
    ).strip()
    live_async_session_connection_blob = subprocess.check_output(
        ["git", "hash-object", str(LIVE_ASYNC_SESSION_CONNECTION_MODULE)],
        text=True,
    ).strip()
    live_async_session_connection_query_blob = subprocess.check_output(
        ["git", "hash-object", str(LIVE_ASYNC_SESSION_CONNECTION_QUERY_MODULE)],
        text=True,
    ).strip()
    session_blob = subprocess.check_output(
        ["git", "hash-object", str(SESSION_MODULE)],
        text=True,
    ).strip()
    reader_tests = subprocess.check_output(
        [
            "git",
            "hash-object",
            "backend/tests/s3_daily_rowset/test_accepted_s2_train_val_source_002_row_level_read.py",
        ],
        text=True,
    ).strip()
    live_session_tests = subprocess.check_output(
        [
            "git",
            "hash-object",
            "backend/tests/s3_daily_rowset/"
            "test_accepted_s2_train_val_source_002_row_level_read_live_session.py",
        ],
        text=True,
    ).strip()
    obtain_tests = subprocess.check_output(
        [
            "git",
            "hash-object",
            "backend/tests/s3_daily_rowset/"
            "test_accepted_s2_train_val_source_002_row_level_read_live_obtain.py",
        ],
        text=True,
    ).strip()
    query_tests = subprocess.check_output(
        [
            "git",
            "hash-object",
            "backend/tests/s3_daily_rowset/"
            "test_accepted_s2_train_val_source_002_row_level_read_live_session_query.py",
        ],
        text=True,
    ).strip()
    live_connection_tests = subprocess.check_output(
        [
            "git",
            "hash-object",
            "backend/tests/s3_daily_rowset/"
            "test_accepted_s2_train_val_source_002_row_level_read_live_connection.py",
        ],
        text=True,
    ).strip()
    live_async_connection_tests = subprocess.check_output(
        [
            "git",
            "hash-object",
            "backend/tests/s3_daily_rowset/"
            "test_accepted_s2_train_val_source_002_row_level_read_live_async_connection.py",
        ],
        text=True,
    ).strip()
    live_async_session_tests = subprocess.check_output(
        [
            "git",
            "hash-object",
            "backend/tests/s3_daily_rowset/"
            "test_accepted_s2_train_val_source_002_row_level_read_live_async_session.py",
        ],
        text=True,
    ).strip()
    live_async_obtain_tests = subprocess.check_output(
        [
            "git",
            "hash-object",
            "backend/tests/s3_daily_rowset/"
            "test_accepted_s2_train_val_source_002_row_level_read_live_async_obtain.py",
        ],
        text=True,
    ).strip()
    live_async_session_query_tests = subprocess.check_output(
        [
            "git",
            "hash-object",
            "backend/tests/s3_daily_rowset/"
            "test_accepted_s2_train_val_source_002_row_level_read_live_async_session_query.py",
        ],
        text=True,
    ).strip()
    live_async_session_bind_tests = subprocess.check_output(
        [
            "git",
            "hash-object",
            "backend/tests/s3_daily_rowset/"
            "test_accepted_s2_train_val_source_002_row_level_read_live_async_session_bind.py",
        ],
        text=True,
    ).strip()
    live_async_session_connection_tests = subprocess.check_output(
        [
            "git",
            "hash-object",
            "backend/tests/s3_daily_rowset/"
            "test_accepted_s2_train_val_source_002_row_level_read_live_async_session_connection.py",
        ],
        text=True,
    ).strip()
    live_async_session_connection_query_tests = subprocess.check_output(
        [
            "git",
            "hash-object",
            "backend/tests/s3_daily_rowset/"
            "test_accepted_s2_train_val_source_002_row_level_read_live_async_session_connection_query.py",
        ],
        text=True,
    ).strip()
    assert reader_blob == PARENT_READER_PY_BLOB
    assert live_session_blob == LIVE_SESSION_PY_BLOB
    assert obtain_blob == LIVE_OBTAIN_PY_BLOB
    assert query_blob == LIVE_SESSION_QUERY_PY_BLOB
    assert live_connection_blob == LIVE_CONNECTION_PY_BLOB
    assert live_async_connection_blob == LIVE_ASYNC_CONNECTION_PY_BLOB
    assert live_async_session_blob == LIVE_ASYNC_SESSION_PY_BLOB
    assert live_async_obtain_blob == LIVE_ASYNC_OBTAIN_PY_BLOB
    assert live_async_session_query_blob == LIVE_ASYNC_SESSION_QUERY_PY_BLOB
    assert live_async_session_bind_blob == LIVE_ASYNC_SESSION_BIND_PY_BLOB
    assert live_async_session_connection_blob == LIVE_ASYNC_SESSION_CONNECTION_PY_BLOB
    assert live_async_session_connection_query_blob == LIVE_ASYNC_SESSION_CONNECTION_QUERY_PY_BLOB
    assert session_blob == SESSION_PY_BLOB
    assert reader_tests == PARENT_READER_TEST_PY_BLOB
    assert live_session_tests == LIVE_SESSION_TEST_PY_BLOB
    assert obtain_tests == LIVE_OBTAIN_TEST_PY_BLOB
    assert query_tests == LIVE_SESSION_QUERY_TEST_PY_BLOB
    assert live_connection_tests == LIVE_CONNECTION_TEST_PY_BLOB
    assert live_async_connection_tests == LIVE_ASYNC_CONNECTION_TEST_PY_BLOB
    assert live_async_session_tests == LIVE_ASYNC_SESSION_TEST_PY_BLOB
    assert live_async_obtain_tests == LIVE_ASYNC_OBTAIN_TEST_PY_BLOB
    assert live_async_session_query_tests == LIVE_ASYNC_SESSION_QUERY_TEST_PY_BLOB
    assert live_async_session_bind_tests == LIVE_ASYNC_SESSION_BIND_TEST_PY_BLOB
    assert live_async_session_connection_tests == LIVE_ASYNC_SESSION_CONNECTION_TEST_PY_BLOB
    assert (
        live_async_session_connection_query_tests
        == LIVE_ASYNC_SESSION_CONNECTION_QUERY_TEST_PY_BLOB
    )


def test_frozen_test_catalog_artifact_blob_unchanged() -> None:
    blob = subprocess.check_output(
        ["git", "hash-object", "backend/tests/s3_daily_rowset/test_catalog_artifact.py"],
        text=True,
    ).strip()
    assert blob == TEST_CATALOG_ARTIFACT_PY_BLOB


def test_s3_daily_rowset_has_no_production_init_py() -> None:
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()
