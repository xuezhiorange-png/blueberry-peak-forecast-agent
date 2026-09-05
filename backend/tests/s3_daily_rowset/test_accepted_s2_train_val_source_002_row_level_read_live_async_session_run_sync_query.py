"""S3-A2 accepted S2 TRAIN/VAL SOURCE_002 live-async-session-run-sync-query tests."""

from __future__ import annotations

import asyncio
import importlib
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.app.s2_materialized_dataset.shared.contracts import SOURCE_002_ROW_LEVEL_READ
from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read import (
    AcceptedS2TrainValSource002RowLevelReadAttestation,
    clear_source_002_row_level_read_session_provider,
)

_run_sync_query = importlib.import_module(
    "backend.app.s3_daily_rowset."
    "accepted_s2_train_val_source_002_row_level_read_live_async_session_run_sync_query"
)
_bind_query = importlib.import_module(
    "backend.app.s3_daily_rowset."
    "accepted_s2_train_val_source_002_row_level_read_live_async_session_bind_query"
)
_bind_obtain = importlib.import_module(
    "backend.app.s3_daily_rowset."
    "accepted_s2_train_val_source_002_row_level_read_live_async_session_bind_obtain"
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
_connection_obtain = importlib.import_module(
    "backend.app.s3_daily_rowset."
    "accepted_s2_train_val_source_002_row_level_read_live_async_session_connection_obtain"
)
_async_obtain = importlib.import_module(
    "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_async_obtain"
)
AcceptedS2TrainValLiveAsyncSessionRunSyncQueryEnvelope = (
    _run_sync_query.AcceptedS2TrainValLiveAsyncSessionRunSyncQueryEnvelope
)
LiveAsyncSessionRunSyncQueryReasonCode = _run_sync_query.LiveAsyncSessionRunSyncQueryReasonCode
probe_accepted_s2_train_val_already_obtained_live_async_session_run_sync_queryability = _run_sync_query.probe_accepted_s2_train_val_already_obtained_live_async_session_run_sync_queryability  # noqa: E501
probe_accepted_s2_train_val_already_obtained_live_async_session_bind_connection_queryability = _bind_query.probe_accepted_s2_train_val_already_obtained_live_async_session_bind_connection_queryability  # noqa: E501
obtain_accepted_s2_train_val_content_bytes_from_the_already_obtained_live_async_session_bind_connection = _bind_obtain.obtain_accepted_s2_train_val_content_bytes_from_the_already_obtained_live_async_session_bind_connection  # noqa: E501
probe_accepted_s2_train_val_already_obtained_live_async_session_connection_queryability = _connection_query.probe_accepted_s2_train_val_already_obtained_live_async_session_connection_queryability  # noqa: E501
obtain_accepted_s2_train_val_async_connection_from_the_already_obtained_live_async_session_connection = _async_session_connection.obtain_accepted_s2_train_val_async_connection_from_the_already_obtained_live_async_session_connection  # noqa: E501
probe_accepted_s2_train_val_already_obtained_live_async_session_queryability = _async_session_query.probe_accepted_s2_train_val_already_obtained_live_async_session_queryability  # noqa: E501
obtain_accepted_s2_train_val_async_connection_from_the_already_obtained_live_async_session_bind = _async_session_bind.obtain_accepted_s2_train_val_async_connection_from_the_already_obtained_live_async_session_bind  # noqa: E501
obtain_accepted_s2_train_val_content_bytes_from_the_already_obtained_live_async_session_connection = _connection_obtain.obtain_accepted_s2_train_val_content_bytes_from_the_already_obtained_live_async_session_connection  # noqa: E501
obtain_accepted_s2_train_val_content_bytes_from_the_already_obtained_live_async_session = _async_obtain.obtain_accepted_s2_train_val_content_bytes_from_the_already_obtained_live_async_session  # noqa: E501
LiveAsyncSessionBindQueryReasonCode = _bind_query.LiveAsyncSessionBindQueryReasonCode
LiveAsyncSessionBindObtainReasonCode = _bind_obtain.LiveAsyncSessionBindObtainReasonCode
LiveAsyncSessionConnectionQueryReasonCode = (
    _connection_query.LiveAsyncSessionConnectionQueryReasonCode
)
LiveAsyncSessionConnectionReasonCode = (
    _async_session_connection.LiveAsyncSessionConnectionReasonCode
)
LiveAsyncSessionQueryReasonCode = _async_session_query.LiveAsyncSessionQueryReasonCode
LiveAsyncSessionBindReasonCode = _async_session_bind.LiveAsyncSessionBindReasonCode
LiveAsyncSessionConnectionObtainReasonCode = (
    _connection_obtain.LiveAsyncSessionConnectionObtainReasonCode
)
LiveAsyncObtainReasonCode = _async_obtain.LiveAsyncObtainReasonCode

TEST_CATALOG_ARTIFACT_PY_BLOB = "af59a9f1d291ab32eff23684aca477f0e4a852cd"
PARENT_READER_TEST_PY_BLOB = "0e21ccc316eb828e52353f9b01adc7cc7743141d"
LIVE_SESSION_TEST_PY_BLOB = "94c54c117ad92a191e2aac00e8314f398e971125"
LIVE_OBTAIN_TEST_PY_BLOB = "d45f8d8d644b02d8bc4ca5fe091610e956fc1c91"
LIVE_SESSION_QUERY_TEST_PY_BLOB = "775b45df7c5c1ccbf97bde417da2637cbf1972c3"
LIVE_CONNECTION_TEST_PY_BLOB = "b7692f1af6bf4ce04a3e9f9a05ce2a82630e908e"
LIVE_ASYNC_CONNECTION_TEST_PY_BLOB = "d3e68be59c3511ad3592ef5b0cffdaea572023e6"
LIVE_ASYNC_SESSION_TEST_PY_BLOB = "b5f55aaecf584f144d5e45e851c45344c893d512"
LIVE_ASYNC_OBTAIN_TEST_PY_BLOB = "36e7cadecc45922e0319fc8a2d7649a55f4e05db"
LIVE_ASYNC_SESSION_QUERY_TEST_PY_BLOB = "dd015b0876d8a0c6100b38fa1b9ee4c0961c2e8b"
LIVE_ASYNC_SESSION_BIND_TEST_PY_BLOB = "a03ce4503f3d34f564e49df69780be65333f188f"
LIVE_ASYNC_SESSION_CONNECTION_TEST_PY_BLOB = "bc670011541bef60447648924dfe4305dc7fff62"
LIVE_ASYNC_SESSION_CONNECTION_QUERY_TEST_PY_BLOB = "c5429df22e90cfbb1f90d20e81f8dbb60146655e"
LIVE_ASYNC_SESSION_CONNECTION_OBTAIN_TEST_PY_BLOB = "b8be184ceb8087ebd12d2c575e7a03c98b344af0"
LIVE_ASYNC_SESSION_BIND_QUERY_TEST_PY_BLOB = "db646fe0753864c2b0c779e04d453cb2952aa647"
LIVE_ASYNC_SESSION_BIND_OBTAIN_TEST_PY_BLOB = "84958e0d281a74d7cf53e473ac6851f440eaba7f"
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
LIVE_ASYNC_SESSION_CONNECTION_OBTAIN_PY_BLOB = "726d934415952ea5705d53c5b2b4311888e7c4c0"
LIVE_ASYNC_SESSION_BIND_QUERY_PY_BLOB = "c95efcbdc7b4ef2f95eb1a90550b9aff3500bf22"
LIVE_ASYNC_SESSION_BIND_OBTAIN_PY_BLOB = "5b8a343ae3889111c5032cb22083beb19de20e7a"
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
LIVE_ASYNC_SESSION_CONNECTION_OBTAIN_MODULE = Path(
    "backend/app/s3_daily_rowset/"
    "accepted_s2_train_val_source_002_row_level_read_live_async_session_connection_obtain.py"
)
LIVE_ASYNC_SESSION_BIND_QUERY_MODULE = Path(
    "backend/app/s3_daily_rowset/"
    "accepted_s2_train_val_source_002_row_level_read_live_async_session_bind_query.py"
)
LIVE_ASYNC_SESSION_BIND_OBTAIN_MODULE = Path(
    "backend/app/s3_daily_rowset/"
    "accepted_s2_train_val_source_002_row_level_read_live_async_session_bind_obtain.py"
)
SESSION_MODULE = Path("backend/app/db/session.py")


async def _async_session_maker_sqlite() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


def _session_maker_sqlite() -> async_sessionmaker[AsyncSession]:
    return asyncio.run(_async_session_maker_sqlite())


@pytest.fixture(autouse=True)
def _restore_session_provider() -> Iterator[None]:
    clear_source_002_row_level_read_session_provider()
    yield
    clear_source_002_row_level_read_session_provider()


def _assert_not_source_002(envelope: Any) -> None:
    assert envelope.source_002_row_level_read is False
    assert envelope.official_hashes_attested_from_a_live_read is False
    assert envelope.accepted_s2_train_val_content_bytes_obtained_from_bound_live_session is False
    assert SOURCE_002_ROW_LEVEL_READ is True


def test_official_live_async_session_run_sync_query_path_fail_closed_or_queryable() -> None:
    envelope = (
        probe_accepted_s2_train_val_already_obtained_live_async_session_run_sync_queryability()
    )  # noqa: E501

    if envelope.queryable:
        assert envelope.reason_code is LiveAsyncSessionRunSyncQueryReasonCode.QUERYABLE
    else:
        assert envelope.reason_code is not LiveAsyncSessionRunSyncQueryReasonCode.QUERYABLE
    _assert_not_source_002(envelope)


def test_synthetic_sqlite_aiosqlite_queryable_is_not_official_live_async_session_run_sync_query() -> (  # noqa: E501
    None
):
    session_maker = _session_maker_sqlite()

    with patch("backend.app.db.session.AsyncSessionMaker", session_maker):
        envelope = (
            probe_accepted_s2_train_val_already_obtained_live_async_session_run_sync_queryability()
        )  # noqa: E501

    assert envelope.queryable is True
    assert envelope.reason_code is LiveAsyncSessionRunSyncQueryReasonCode.QUERYABLE
    _assert_not_source_002(envelope)


def test_missing_async_session_maker_fail_closes_no_async_session_maker() -> None:
    with patch("backend.app.db.session.AsyncSessionMaker", None):
        envelope = (
            probe_accepted_s2_train_val_already_obtained_live_async_session_run_sync_queryability()
        )  # noqa: E501

    assert envelope.queryable is False
    assert (
        envelope.reason_code
        is LiveAsyncSessionRunSyncQueryReasonCode.FAIL_CLOSED_NO_ASYNC_SESSION_MAKER
    )
    _assert_not_source_002(envelope)


def test_session_maker_that_raises_on_enter_fail_closes_not_obtained() -> None:
    failing_ctx = AsyncMock()
    failing_ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("session refused"))
    failing_ctx.__aexit__ = AsyncMock(return_value=None)
    failing_maker = MagicMock(return_value=failing_ctx)
    failing_maker.__class__ = async_sessionmaker

    with patch("backend.app.db.session.AsyncSessionMaker", failing_maker):
        envelope = (
            probe_accepted_s2_train_val_already_obtained_live_async_session_run_sync_queryability()
        )  # noqa: E501

    assert envelope.queryable is False
    assert envelope.reason_code is (
        LiveAsyncSessionRunSyncQueryReasonCode.FAIL_CLOSED_ASYNC_SESSION_NOT_OBTAINED_FROM_SESSION_MAKER
    )
    _assert_not_source_002(envelope)


def test_session_run_sync_raises_fail_closes_not_synchronously_queryable_via_run_sync() -> None:
    non_queryable_session = AsyncMock(spec=AsyncSession)
    non_queryable_session.run_sync = AsyncMock(side_effect=RuntimeError("not queryable"))
    readable_ctx = AsyncMock()
    readable_ctx.__aenter__ = AsyncMock(return_value=non_queryable_session)
    readable_ctx.__aexit__ = AsyncMock(return_value=None)
    readable_maker = MagicMock(return_value=readable_ctx)
    readable_maker.__class__ = async_sessionmaker

    with patch("backend.app.db.session.AsyncSessionMaker", readable_maker):
        envelope = (
            probe_accepted_s2_train_val_already_obtained_live_async_session_run_sync_queryability()
        )  # noqa: E501

    assert envelope.queryable is False
    assert envelope.reason_code is (
        LiveAsyncSessionRunSyncQueryReasonCode.FAIL_CLOSED_ASYNC_SESSION_NOT_SYNCHRONOUSLY_QUERYABLE_VIA_RUN_SYNC
    )
    _assert_not_source_002(envelope)


def test_async_session_run_sync_query_envelope_has_queryable_not_connected_or_content_bytes() -> (
    None
):
    field_names = set(AcceptedS2TrainValLiveAsyncSessionRunSyncQueryEnvelope.model_fields)
    assert "queryable" in field_names
    assert "connected" not in field_names
    assert "obtained" not in field_names
    assert "train_content_bytes" not in field_names
    assert "validation_content_bytes" not in field_names
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


def test_sibling_probes_still_not_source_002() -> None:
    bind_query_envelope = probe_accepted_s2_train_val_already_obtained_live_async_session_bind_connection_queryability()  # noqa: E501
    bind_obtain_envelope = obtain_accepted_s2_train_val_content_bytes_from_the_already_obtained_live_async_session_bind_connection()  # noqa: E501
    connection_query_envelope = (
        probe_accepted_s2_train_val_already_obtained_live_async_session_connection_queryability()
    )
    connection_envelope = obtain_accepted_s2_train_val_async_connection_from_the_already_obtained_live_async_session_connection()  # noqa: E501
    query_envelope = probe_accepted_s2_train_val_already_obtained_live_async_session_queryability()
    bind_envelope = obtain_accepted_s2_train_val_async_connection_from_the_already_obtained_live_async_session_bind()  # noqa: E501
    connection_obtain_envelope = obtain_accepted_s2_train_val_content_bytes_from_the_already_obtained_live_async_session_connection()  # noqa: E501
    async_obtain_envelope = (
        obtain_accepted_s2_train_val_content_bytes_from_the_already_obtained_live_async_session()
    )

    if bind_query_envelope.queryable:
        assert bind_query_envelope.reason_code is LiveAsyncSessionBindQueryReasonCode.QUERYABLE
    else:
        assert bind_query_envelope.reason_code is not LiveAsyncSessionBindQueryReasonCode.QUERYABLE
    if bind_obtain_envelope.obtained:
        assert bind_obtain_envelope.reason_code is LiveAsyncSessionBindObtainReasonCode.OBTAINED
    else:
        assert bind_obtain_envelope.reason_code is not LiveAsyncSessionBindObtainReasonCode.OBTAINED
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
    if connection_obtain_envelope.obtained:
        assert (
            connection_obtain_envelope.reason_code
            is LiveAsyncSessionConnectionObtainReasonCode.OBTAINED
        )
    else:
        assert (
            connection_obtain_envelope.reason_code
            is not LiveAsyncSessionConnectionObtainReasonCode.OBTAINED
        )
    if async_obtain_envelope.obtained:
        assert async_obtain_envelope.reason_code is LiveAsyncObtainReasonCode.OBTAINED
    else:
        assert async_obtain_envelope.reason_code is not LiveAsyncObtainReasonCode.OBTAINED
    _assert_not_source_002(bind_query_envelope)
    _assert_not_source_002(bind_obtain_envelope)
    _assert_not_source_002(connection_query_envelope)
    _assert_not_source_002(connection_envelope)
    _assert_not_source_002(query_envelope)
    _assert_not_source_002(bind_envelope)
    _assert_not_source_002(connection_obtain_envelope)
    _assert_not_source_002(async_obtain_envelope)


def test_s2_source_002_row_level_read_constant_is_true_parent_family_live_attestation() -> None:
    assert SOURCE_002_ROW_LEVEL_READ is True


def test_async_session_run_sync_query_module_contains_required_and_forbidden_patterns() -> None:
    module = Path(
        "backend/app/s3_daily_rowset/"
        "accepted_s2_train_val_source_002_row_level_read_live_async_session_run_sync_query.py"
    )
    source = module.read_text(encoding="utf-8")
    lowered = source.lower()
    assert "run_sync(" in source
    assert "get_bind(" not in source
    assert "bind.connect(" not in lowered
    assert "postgresql://" not in lowered
    assert "create_engine(" not in lowered
    assert "create_async_engine(" not in lowered
    assert "async_sessionmaker(" not in lowered
    assert "session.connection(" not in lowered
    assert "engine.connect(" not in lowered
    assert "session.scalar(" not in lowered
    assert "bound_source_002_row_level_read_session_provider(" not in lowered


def test_production_modules_contain_no_sync_engine_session_bridge() -> None:
    modules = [
        READER_MODULE,
        LIVE_SESSION_MODULE,
        LIVE_OBTAIN_MODULE,
        LIVE_SESSION_QUERY_MODULE,
        LIVE_CONNECTION_MODULE,
        LIVE_ASYNC_SESSION_MODULE,
        LIVE_ASYNC_CONNECTION_MODULE,
        LIVE_ASYNC_OBTAIN_MODULE,
    ]
    for module in modules:
        source = module.read_text(encoding="utf-8").lower()
        assert ".sync_engine" not in source
        assert "session(bind" not in source


def test_frozen_test_catalog_artifact_blob_unchanged() -> None:
    blob = subprocess.check_output(
        ["git", "hash-object", "backend/tests/s3_daily_rowset/test_catalog_artifact.py"],
        text=True,
    ).strip()
    assert blob == TEST_CATALOG_ARTIFACT_PY_BLOB


def test_s3_daily_rowset_has_no_production_init_py() -> None:
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()
