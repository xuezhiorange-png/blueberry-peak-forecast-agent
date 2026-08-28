"""S3-A2 accepted S2 TRAIN/VALIDATION SOURCE_002 row-level-read live-async-session-query tests."""

from __future__ import annotations

import asyncio
import importlib
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.s2_materialized_dataset.shared.contracts import SOURCE_002_ROW_LEVEL_READ
from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read import (
    AcceptedS2TrainValSource002RowLevelReadAttestation,
    clear_source_002_row_level_read_session_provider,
)

_async_session_query = importlib.import_module(
    "backend.app.s3_daily_rowset."
    "accepted_s2_train_val_source_002_row_level_read_live_async_session_query"
)
_async_obtain = importlib.import_module(
    "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_async_obtain"
)
_session_query = importlib.import_module(
    "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_session_query"
)
_live_session = importlib.import_module(
    "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_session"
)
AcceptedS2TrainValLiveAsyncSessionQueryEnvelope = (
    _async_session_query.AcceptedS2TrainValLiveAsyncSessionQueryEnvelope
)
LiveAsyncSessionQueryReasonCode = _async_session_query.LiveAsyncSessionQueryReasonCode
probe_accepted_s2_train_val_already_obtained_live_async_session_queryability = _async_session_query.probe_accepted_s2_train_val_already_obtained_live_async_session_queryability  # noqa: E501
obtain_accepted_s2_train_val_content_bytes_from_the_already_obtained_live_async_session = _async_obtain.obtain_accepted_s2_train_val_content_bytes_from_the_already_obtained_live_async_session  # noqa: E501
LiveAsyncObtainReasonCode = _async_obtain.LiveAsyncObtainReasonCode
probe_accepted_s2_train_val_bound_live_session_queryability = (
    _session_query.probe_accepted_s2_train_val_bound_live_session_queryability
)
LiveSessionQueryReasonCode = _session_query.LiveSessionQueryReasonCode
bind_default_source_002_row_level_read_live_session_provider = (
    _live_session.bind_default_source_002_row_level_read_live_session_provider
)

TEST_CATALOG_ARTIFACT_PY_BLOB = "af59a9f1d291ab32eff23684aca477f0e4a852cd"
PARENT_READER_TEST_PY_BLOB = "bca600a15ebf3daa292050ab52ebcebfd953540a"
LIVE_SESSION_TEST_PY_BLOB = "c1ba24a1b87269d998b243002c231d654b08eb5a"
LIVE_OBTAIN_TEST_PY_BLOB = "0f54d1db37374bba4f5fcadc726baf0dff3c22b0"
LIVE_SESSION_QUERY_TEST_PY_BLOB = "00aabd3376c3f1a1fa41349627a7a7faa0352b69"
LIVE_CONNECTION_TEST_PY_BLOB = "2ebc0fa5ae9359f965964a8a70f2c5d65e7929e3"
LIVE_ASYNC_CONNECTION_TEST_PY_BLOB = "542e5c86812a20824f32f2085186e8a422db71d7"
LIVE_ASYNC_SESSION_TEST_PY_BLOB = "1e56e51f94f986de9686a34df9be80d1f741ddb4"
LIVE_ASYNC_OBTAIN_TEST_PY_BLOB = "b40cba70f8947954d95557523f9573cf5bc6d357"
PARENT_READER_PY_BLOB = "2a9232064179da89484d52dcf203c95a0fa71a68"
LIVE_SESSION_PY_BLOB = "28513a5b86659bed784e64d2060c53088149dc96"
LIVE_OBTAIN_PY_BLOB = "bf6e50cccf172f00c9be224d3d42bd2b1ef1bf8c"
LIVE_SESSION_QUERY_PY_BLOB = "d6a082dcabd7fbd1db324fd8ba6153ea2240fe39"
LIVE_CONNECTION_PY_BLOB = "f87bdf8b8add435298056f61614ee1d91c9dbbf0"
LIVE_ASYNC_CONNECTION_PY_BLOB = "51672d5a159d0889a159d9c03e8191e7f8a6b344"
LIVE_ASYNC_SESSION_PY_BLOB = "40afc94dacb2208accd4903b12ae46152a750b41"
LIVE_ASYNC_OBTAIN_PY_BLOB = "01f0e6e75f527514c5a08208f91eaec99a0154d1"
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
    assert SOURCE_002_ROW_LEVEL_READ is False


def test_official_live_async_session_query_path_fail_closed_or_queryable() -> None:
    envelope = probe_accepted_s2_train_val_already_obtained_live_async_session_queryability()

    if envelope.queryable:
        assert envelope.reason_code is LiveAsyncSessionQueryReasonCode.QUERYABLE
    else:
        assert envelope.reason_code is not LiveAsyncSessionQueryReasonCode.QUERYABLE
    _assert_not_source_002(envelope)


def test_synthetic_sqlite_aiosqlite_queryable_is_not_official_live_async_session_query() -> None:
    session_maker = _session_maker_sqlite()

    with patch("backend.app.db.session.AsyncSessionMaker", session_maker):
        envelope = probe_accepted_s2_train_val_already_obtained_live_async_session_queryability()

    assert envelope.queryable is True
    assert envelope.reason_code is LiveAsyncSessionQueryReasonCode.QUERYABLE
    _assert_not_source_002(envelope)


def test_missing_async_session_maker_fail_closes_no_async_session_maker() -> None:
    with patch("backend.app.db.session.AsyncSessionMaker", None):
        envelope = probe_accepted_s2_train_val_already_obtained_live_async_session_queryability()

    assert envelope.queryable is False
    assert (
        envelope.reason_code is LiveAsyncSessionQueryReasonCode.FAIL_CLOSED_NO_ASYNC_SESSION_MAKER
    )
    _assert_not_source_002(envelope)


def test_session_maker_that_raises_on_enter_fail_closes_not_obtained() -> None:
    failing_ctx = AsyncMock()
    failing_ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("session refused"))
    failing_ctx.__aexit__ = AsyncMock(return_value=None)
    failing_maker = MagicMock(return_value=failing_ctx)
    failing_maker.__class__ = async_sessionmaker

    with patch("backend.app.db.session.AsyncSessionMaker", failing_maker):
        envelope = probe_accepted_s2_train_val_already_obtained_live_async_session_queryability()

    assert envelope.queryable is False
    assert (
        envelope.reason_code
        is LiveAsyncSessionQueryReasonCode.FAIL_CLOSED_ASYNC_SESSION_NOT_OBTAINED_FROM_SESSION_MAKER
    )
    _assert_not_source_002(envelope)


def test_non_queryable_async_session_fail_closes_not_asynchronously_queryable() -> None:
    non_queryable_session = AsyncMock(spec=AsyncSession)
    non_queryable_session.scalar = AsyncMock(side_effect=RuntimeError("not queryable"))
    readable_ctx = AsyncMock()
    readable_ctx.__aenter__ = AsyncMock(return_value=non_queryable_session)
    readable_ctx.__aexit__ = AsyncMock(return_value=None)
    readable_maker = MagicMock(return_value=readable_ctx)
    readable_maker.__class__ = async_sessionmaker

    with patch("backend.app.db.session.AsyncSessionMaker", readable_maker):
        envelope = probe_accepted_s2_train_val_already_obtained_live_async_session_queryability()

    assert envelope.queryable is False
    assert (
        envelope.reason_code
        is LiveAsyncSessionQueryReasonCode.FAIL_CLOSED_ASYNC_SESSION_NOT_ASYNCHRONOUSLY_QUERYABLE
    )
    _assert_not_source_002(envelope)


def test_async_session_query_envelope_has_queryable_not_obtained_or_content_bytes() -> None:
    field_names = set(AcceptedS2TrainValLiveAsyncSessionQueryEnvelope.model_fields)
    assert "queryable" in field_names
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


def test_sibling_live_async_obtain_and_live_session_query_still_not_source_002() -> None:
    bind_default_source_002_row_level_read_live_session_provider()

    async_obtain_envelope = (
        obtain_accepted_s2_train_val_content_bytes_from_the_already_obtained_live_async_session()
    )
    session_query_envelope = probe_accepted_s2_train_val_bound_live_session_queryability()

    if async_obtain_envelope.obtained:
        assert async_obtain_envelope.reason_code is LiveAsyncObtainReasonCode.OBTAINED
    else:
        assert async_obtain_envelope.reason_code is not LiveAsyncObtainReasonCode.OBTAINED
    if session_query_envelope.queryable:
        assert session_query_envelope.reason_code is LiveSessionQueryReasonCode.QUERYABLE
    else:
        assert session_query_envelope.reason_code is not LiveSessionQueryReasonCode.QUERYABLE
    _assert_not_source_002(async_obtain_envelope)
    _assert_not_source_002(session_query_envelope)


def test_s2_source_002_row_level_read_constant_remains_false() -> None:
    assert SOURCE_002_ROW_LEVEL_READ is False


def test_async_session_query_module_contains_no_forbidden_patterns() -> None:
    module = Path(
        "backend/app/s3_daily_rowset/"
        "accepted_s2_train_val_source_002_row_level_read_live_async_session_query.py"
    )
    source = module.read_text(encoding="utf-8").lower()
    assert "postgresql://" not in source
    assert "create_engine(" not in source
    assert "create_async_engine(" not in source
    assert "async_sessionmaker(" not in source
    assert "session.connection(" not in source
    assert "bind.connect(" not in source
    assert "get_bind(" not in source
    assert "engine.connect(" not in source
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
    assert reader_blob == PARENT_READER_PY_BLOB
    assert live_session_blob == LIVE_SESSION_PY_BLOB
    assert obtain_blob == LIVE_OBTAIN_PY_BLOB
    assert query_blob == LIVE_SESSION_QUERY_PY_BLOB
    assert live_connection_blob == LIVE_CONNECTION_PY_BLOB
    assert live_async_connection_blob == LIVE_ASYNC_CONNECTION_PY_BLOB
    assert live_async_session_blob == LIVE_ASYNC_SESSION_PY_BLOB
    assert live_async_obtain_blob == LIVE_ASYNC_OBTAIN_PY_BLOB
    assert session_blob == SESSION_PY_BLOB
    assert reader_tests == PARENT_READER_TEST_PY_BLOB
    assert live_session_tests == LIVE_SESSION_TEST_PY_BLOB
    assert obtain_tests == LIVE_OBTAIN_TEST_PY_BLOB
    assert query_tests == LIVE_SESSION_QUERY_TEST_PY_BLOB
    assert live_connection_tests == LIVE_CONNECTION_TEST_PY_BLOB
    assert live_async_connection_tests == LIVE_ASYNC_CONNECTION_TEST_PY_BLOB
    assert live_async_session_tests == LIVE_ASYNC_SESSION_TEST_PY_BLOB
    assert live_async_obtain_tests == LIVE_ASYNC_OBTAIN_TEST_PY_BLOB


def test_frozen_test_catalog_artifact_blob_unchanged() -> None:
    blob = subprocess.check_output(
        ["git", "hash-object", "backend/tests/s3_daily_rowset/test_catalog_artifact.py"],
        text=True,
    ).strip()
    assert blob == TEST_CATALOG_ARTIFACT_PY_BLOB


def test_s3_daily_rowset_has_no_production_init_py() -> None:
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()
