"""S3-A2 accepted S2 TRAIN/VALIDATION SOURCE_002 row-level-read live-async-connection tests."""

from __future__ import annotations

import importlib
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from backend.app.s2_materialized_dataset.shared.contracts import SOURCE_002_ROW_LEVEL_READ
from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read import (
    AcceptedS2TrainValSource002RowLevelReadAttestation,
    clear_source_002_row_level_read_session_provider,
)

_async_connection = importlib.import_module(
    "backend.app.s3_daily_rowset."
    "accepted_s2_train_val_source_002_row_level_read_live_async_connection"
)
_live_session = importlib.import_module(
    "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_session"
)
_query = importlib.import_module(
    "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_session_query"
)
_obtain = importlib.import_module(
    "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_obtain"
)
_live_connection = importlib.import_module(
    "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_connection"
)
AcceptedS2TrainValLiveAsyncConnectionEnvelope = (
    _async_connection.AcceptedS2TrainValLiveAsyncConnectionEnvelope
)
LiveAsyncConnectionReasonCode = _async_connection.LiveAsyncConnectionReasonCode
obtain_accepted_s2_train_val_async_connection_from_the_already_configured_live_async_engine = (
    _async_connection.obtain_accepted_s2_train_val_async_connection_from_the_already_configured_live_async_engine
)
bind_default_source_002_row_level_read_live_session_provider = (
    _live_session.bind_default_source_002_row_level_read_live_session_provider
)
probe_accepted_s2_train_val_bound_live_session_queryability = (
    _query.probe_accepted_s2_train_val_bound_live_session_queryability
)
LiveSessionQueryReasonCode = _query.LiveSessionQueryReasonCode
obtain_accepted_s2_train_val_content_bytes_from_bound_live_session = (
    _obtain.obtain_accepted_s2_train_val_content_bytes_from_bound_live_session
)
obtain_accepted_s2_train_val_sync_connection_from_bound_live_session_bind = (
    _live_connection.obtain_accepted_s2_train_val_sync_connection_from_bound_live_session_bind
)
LiveConnectionReasonCode = _live_connection.LiveConnectionReasonCode

TEST_CATALOG_ARTIFACT_PY_BLOB = "af59a9f1d291ab32eff23684aca477f0e4a852cd"
PARENT_READER_TEST_PY_BLOB = "bca600a15ebf3daa292050ab52ebcebfd953540a"
LIVE_SESSION_TEST_PY_BLOB = "c1ba24a1b87269d998b243002c231d654b08eb5a"
LIVE_OBTAIN_TEST_PY_BLOB = "0f54d1db37374bba4f5fcadc726baf0dff3c22b0"
LIVE_SESSION_QUERY_TEST_PY_BLOB = "00aabd3376c3f1a1fa41349627a7a7faa0352b69"
LIVE_CONNECTION_TEST_PY_BLOB = "2ebc0fa5ae9359f965964a8a70f2c5d65e7929e3"
PARENT_READER_PY_BLOB = "2a9232064179da89484d52dcf203c95a0fa71a68"
LIVE_SESSION_PY_BLOB = "28513a5b86659bed784e64d2060c53088149dc96"
LIVE_OBTAIN_PY_BLOB = "bf6e50cccf172f00c9be224d3d42bd2b1ef1bf8c"
LIVE_SESSION_QUERY_PY_BLOB = "d6a082dcabd7fbd1db324fd8ba6153ea2240fe39"
LIVE_CONNECTION_PY_BLOB = "f87bdf8b8add435298056f61614ee1d91c9dbbf0"
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
SESSION_MODULE = Path("backend/app/db/session.py")


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


def test_official_live_async_engine_path_fail_closed_or_connected() -> None:
    envelope = (
        obtain_accepted_s2_train_val_async_connection_from_the_already_configured_live_async_engine()
    )

    if envelope.connected:
        assert envelope.reason_code is LiveAsyncConnectionReasonCode.CONNECTED
    else:
        assert envelope.reason_code is not LiveAsyncConnectionReasonCode.CONNECTED
    _assert_not_source_002(envelope)


def test_synthetic_sqlite_aiosqlite_connected_is_not_official_live_async_connection() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    with patch("backend.app.db.session.engine", engine):
        envelope = (
            obtain_accepted_s2_train_val_async_connection_from_the_already_configured_live_async_engine()
        )

    assert envelope.connected is True
    assert envelope.reason_code is LiveAsyncConnectionReasonCode.CONNECTED
    _assert_not_source_002(envelope)


def test_missing_async_engine_fail_closes_no_async_engine() -> None:
    with patch("backend.app.db.session.engine", None):
        envelope = (
            obtain_accepted_s2_train_val_async_connection_from_the_already_configured_live_async_engine()
        )

    assert envelope.connected is False
    assert envelope.reason_code is LiveAsyncConnectionReasonCode.FAIL_CLOSED_NO_ASYNC_ENGINE
    _assert_not_source_002(envelope)


def test_engine_connect_that_raises_fail_closes_not_obtained() -> None:
    failing_engine = AsyncMock(spec=AsyncEngine)
    failing_engine.connect = AsyncMock(side_effect=RuntimeError("connection refused"))

    with patch("backend.app.db.session.engine", failing_engine):
        envelope = (
            obtain_accepted_s2_train_val_async_connection_from_the_already_configured_live_async_engine()
        )

    assert envelope.connected is False
    assert (
        envelope.reason_code
        is LiveAsyncConnectionReasonCode.FAIL_CLOSED_ASYNC_CONNECTION_NOT_OBTAINED_FROM_ENGINE
    )
    _assert_not_source_002(envelope)


def test_connection_envelope_does_not_expose_content_bytes_or_kg() -> None:
    field_names = set(AcceptedS2TrainValLiveAsyncConnectionEnvelope.model_fields)
    assert "connected" in field_names
    assert "queryable" not in field_names
    assert "content_bytes" not in field_names
    assert "train_content_bytes" not in field_names
    assert "validation_content_bytes" not in field_names
    assert "test_content_bytes" not in field_names
    assert "actual_harvest_quantity_kg" not in field_names
    assert "farm" not in field_names
    assert "members" not in field_names


def test_parent_attestation_model_still_does_not_expose_content_bytes() -> None:
    field_names = set(AcceptedS2TrainValSource002RowLevelReadAttestation.model_fields)
    assert "content_bytes" not in field_names
    assert "train_content_bytes" not in field_names
    assert "validation_content_bytes" not in field_names


def test_sibling_query_obtain_and_live_connection_still_fail_closed_not_source_002() -> None:
    bind_default_source_002_row_level_read_live_session_provider()

    query_envelope = probe_accepted_s2_train_val_bound_live_session_queryability()
    obtain_envelope = obtain_accepted_s2_train_val_content_bytes_from_bound_live_session()
    connection_envelope = (
        obtain_accepted_s2_train_val_sync_connection_from_bound_live_session_bind()
    )

    assert query_envelope.queryable is False
    assert (
        query_envelope.reason_code
        is LiveSessionQueryReasonCode.FAIL_CLOSED_SESSION_NOT_SYNCHRONOUSLY_QUERYABLE
    )
    assert obtain_envelope.source_002_row_level_read is False
    assert obtain_envelope.official_hashes_attested_from_a_live_read is False
    if connection_envelope.connected:
        assert connection_envelope.reason_code is LiveConnectionReasonCode.CONNECTED
    else:
        assert (
            connection_envelope.reason_code
            is LiveConnectionReasonCode.FAIL_CLOSED_SYNC_CONNECTION_NOT_OBTAINED_FROM_BIND
        )
    assert query_envelope.source_002_row_level_read is False
    assert query_envelope.official_hashes_attested_from_a_live_read is False
    _assert_not_source_002(connection_envelope)


def test_s2_source_002_row_level_read_constant_remains_false() -> None:
    assert SOURCE_002_ROW_LEVEL_READ is False


def test_async_connection_module_contains_no_forbidden_patterns() -> None:
    source = LIVE_ASYNC_CONNECTION_MODULE.read_text(encoding="utf-8").lower()
    assert "postgresql://" not in source
    assert "create_engine(" not in source
    assert "create_async_engine(" not in source
    assert "session.connection(" not in source
    assert "bind.connect(" not in source
    assert "get_bind(" not in source


def test_parent_reader_live_session_obtain_query_live_connection_and_session_blobs_unchanged() -> (
    None
):
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
    assert reader_blob == PARENT_READER_PY_BLOB
    assert live_session_blob == LIVE_SESSION_PY_BLOB
    assert obtain_blob == LIVE_OBTAIN_PY_BLOB
    assert query_blob == LIVE_SESSION_QUERY_PY_BLOB
    assert live_connection_blob == LIVE_CONNECTION_PY_BLOB
    assert session_blob == SESSION_PY_BLOB
    assert reader_tests == PARENT_READER_TEST_PY_BLOB
    assert live_session_tests == LIVE_SESSION_TEST_PY_BLOB
    assert obtain_tests == LIVE_OBTAIN_TEST_PY_BLOB
    assert query_tests == LIVE_SESSION_QUERY_TEST_PY_BLOB
    assert live_connection_tests == LIVE_CONNECTION_TEST_PY_BLOB


def test_frozen_test_catalog_artifact_blob_unchanged() -> None:
    blob = subprocess.check_output(
        ["git", "hash-object", "backend/tests/s3_daily_rowset/test_catalog_artifact.py"],
        text=True,
    ).strip()
    assert blob == TEST_CATALOG_ARTIFACT_PY_BLOB


def test_s3_daily_rowset_has_no_production_init_py() -> None:
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()
