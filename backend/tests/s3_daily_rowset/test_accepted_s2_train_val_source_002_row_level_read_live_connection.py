"""S3-A2 accepted S2 TRAIN/VALIDATION SOURCE_002 row-level-read live-connection tests."""

from __future__ import annotations

import importlib
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

from backend.app.s2_materialized_dataset.shared.contracts import SOURCE_002_ROW_LEVEL_READ
from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read import (
    AcceptedS2TrainValSource002RowLevelReadAttestation,
    clear_source_002_row_level_read_session_provider,
    set_source_002_row_level_read_session_provider,
)

_connection = importlib.import_module(
    "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_connection"
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
AcceptedS2TrainValLiveConnectionEnvelope = _connection.AcceptedS2TrainValLiveConnectionEnvelope
LiveConnectionReasonCode = _connection.LiveConnectionReasonCode
obtain_accepted_s2_train_val_sync_connection_from_bound_live_session_bind = (
    _connection.obtain_accepted_s2_train_val_sync_connection_from_bound_live_session_bind
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

TEST_CATALOG_ARTIFACT_PY_BLOB = "af59a9f1d291ab32eff23684aca477f0e4a852cd"
PARENT_READER_TEST_PY_BLOB = "0e21ccc316eb828e52353f9b01adc7cc7743141d"
LIVE_SESSION_TEST_PY_BLOB = "94c54c117ad92a191e2aac00e8314f398e971125"
LIVE_OBTAIN_TEST_PY_BLOB = "d45f8d8d644b02d8bc4ca5fe091610e956fc1c91"
LIVE_SESSION_QUERY_TEST_PY_BLOB = "775b45df7c5c1ccbf97bde417da2637cbf1972c3"
PARENT_READER_PY_BLOB = "2a9232064179da89484d52dcf203c95a0fa71a68"
LIVE_SESSION_PY_BLOB = "28513a5b86659bed784e64d2060c53088149dc96"
LIVE_OBTAIN_PY_BLOB = "bf6e50cccf172f00c9be224d3d42bd2b1ef1bf8c"
LIVE_SESSION_QUERY_PY_BLOB = "d6a082dcabd7fbd1db324fd8ba6153ea2240fe39"
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


def _sqlite_session() -> Session:
    engine = sa.create_engine("sqlite:///:memory:")
    return sessionmaker(bind=engine, expire_on_commit=False)()


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


def test_no_session_fail_closes_as_not_connected() -> None:
    envelope = obtain_accepted_s2_train_val_sync_connection_from_bound_live_session_bind()

    assert envelope.connected is False
    assert envelope.reason_code is LiveConnectionReasonCode.FAIL_CLOSED_NO_SESSION
    _assert_not_source_002(envelope)


def test_provider_returning_none_fail_closes() -> None:
    set_source_002_row_level_read_session_provider(lambda: None)

    envelope = obtain_accepted_s2_train_val_sync_connection_from_bound_live_session_bind()

    assert envelope.connected is False
    assert envelope.reason_code is LiveConnectionReasonCode.FAIL_CLOSED_NO_SESSION
    _assert_not_source_002(envelope)


def test_unreadable_session_provider_fail_closes() -> None:
    def _raise() -> Session:
        raise RuntimeError("session unavailable")

    set_source_002_row_level_read_session_provider(_raise)

    envelope = obtain_accepted_s2_train_val_sync_connection_from_bound_live_session_bind()

    assert envelope.connected is False
    assert envelope.reason_code is LiveConnectionReasonCode.FAIL_CLOSED_SESSION_UNREADABLE
    _assert_not_source_002(envelope)


def test_synthetic_sqlite_connected_is_not_official_live_connection() -> None:
    session = _sqlite_session()
    set_source_002_row_level_read_session_provider(lambda: session)

    envelope = obtain_accepted_s2_train_val_sync_connection_from_bound_live_session_bind()

    assert envelope.connected is True
    assert envelope.reason_code is LiveConnectionReasonCode.CONNECTED
    _assert_not_source_002(envelope)


def test_connection_envelope_does_not_expose_content_bytes_or_kg() -> None:
    field_names = set(AcceptedS2TrainValLiveConnectionEnvelope.model_fields)
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


def test_bound_live_session_connection_fail_closed_is_not_source_002_row_level_read() -> None:
    bind_default_source_002_row_level_read_live_session_provider()

    envelope = obtain_accepted_s2_train_val_sync_connection_from_bound_live_session_bind()

    if envelope.connected:
        assert envelope.reason_code is LiveConnectionReasonCode.CONNECTED
    else:
        assert envelope.reason_code is not LiveConnectionReasonCode.CONNECTED
    _assert_not_source_002(envelope)


def test_bound_live_session_query_still_fail_closes_and_not_source_002_row_level_read() -> None:
    bind_default_source_002_row_level_read_live_session_provider()

    envelope = probe_accepted_s2_train_val_bound_live_session_queryability()

    assert envelope.queryable is False
    assert (
        envelope.reason_code
        is LiveSessionQueryReasonCode.FAIL_CLOSED_SESSION_NOT_SYNCHRONOUSLY_QUERYABLE
    )
    _assert_not_source_002(envelope)


def test_bound_live_session_obtain_still_does_not_flip_source_002_row_level_read() -> None:
    bind_default_source_002_row_level_read_live_session_provider()

    envelope = obtain_accepted_s2_train_val_content_bytes_from_bound_live_session()

    assert envelope.source_002_row_level_read is False
    assert envelope.official_hashes_attested_from_a_live_read is False
    assert SOURCE_002_ROW_LEVEL_READ is True


def test_s2_source_002_row_level_read_constant_is_true_parent_family_live_attestation() -> None:
    assert SOURCE_002_ROW_LEVEL_READ is True


def test_connection_and_parent_modules_contain_no_connection_string() -> None:
    for module in (
        READER_MODULE,
        LIVE_SESSION_MODULE,
        LIVE_OBTAIN_MODULE,
        LIVE_SESSION_QUERY_MODULE,
        LIVE_CONNECTION_MODULE,
    ):
        source = module.read_text(encoding="utf-8").lower()
        assert "postgresql://" not in source
        assert "create_engine(" not in source
    connection_source = LIVE_CONNECTION_MODULE.read_text(encoding="utf-8").lower()
    assert "session.connection(" not in connection_source


def test_parent_reader_live_session_obtain_and_query_blobs_unchanged() -> None:
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
    assert reader_blob == PARENT_READER_PY_BLOB
    assert live_session_blob == LIVE_SESSION_PY_BLOB
    assert obtain_blob == LIVE_OBTAIN_PY_BLOB
    assert query_blob == LIVE_SESSION_QUERY_PY_BLOB
    assert reader_tests == PARENT_READER_TEST_PY_BLOB
    assert live_session_tests == LIVE_SESSION_TEST_PY_BLOB
    assert obtain_tests == LIVE_OBTAIN_TEST_PY_BLOB
    assert query_tests == LIVE_SESSION_QUERY_TEST_PY_BLOB


def test_frozen_test_catalog_artifact_blob_unchanged() -> None:
    blob = subprocess.check_output(
        ["git", "hash-object", "backend/tests/s3_daily_rowset/test_catalog_artifact.py"],
        text=True,
    ).strip()
    assert blob == TEST_CATALOG_ARTIFACT_PY_BLOB


def test_s3_daily_rowset_has_no_production_init_py() -> None:
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()


def test_session_with_no_bind_fail_closes() -> None:
    session = Session()
    set_source_002_row_level_read_session_provider(lambda: session)

    envelope = obtain_accepted_s2_train_val_sync_connection_from_bound_live_session_bind()

    assert envelope.connected is False
    assert envelope.reason_code is LiveConnectionReasonCode.FAIL_CLOSED_NO_BIND
    _assert_not_source_002(envelope)
