"""S3-A2 accepted S2 TRAIN/VALIDATION SOURCE_002 row-level-read live-session tests."""

from __future__ import annotations

import importlib
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from backend.app.s2_materialized_dataset.shared.contracts import SOURCE_002_ROW_LEVEL_READ
from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read import (
    Source002RowLevelReadReasonCode,
    attest_accepted_s2_train_val_source_002_row_level_read,
    bound_source_002_row_level_read_session_provider,
    clear_source_002_row_level_read_session_provider,
    set_source_002_row_level_read_session_provider,
)

_live_session = importlib.import_module(
    "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_session"
)
bind_default_live_session = (
    _live_session.bind_default_source_002_row_level_read_live_session_provider
)
live_session_provider = _live_session.source_002_row_level_read_live_session_provider

TEST_CATALOG_ARTIFACT_PY_BLOB = "af59a9f1d291ab32eff23684aca477f0e4a852cd"
READER_MODULE = Path(
    "backend/app/s3_daily_rowset/accepted_s2_train_val_source_002_row_level_read.py"
)
LIVE_SESSION_MODULE = Path(
    "backend/app/s3_daily_rowset/accepted_s2_train_val_source_002_row_level_read_live_session.py"
)


@pytest.fixture(autouse=True)
def _restore_live_session_provider() -> Iterator[None]:
    bind_default_live_session()
    yield
    clear_source_002_row_level_read_session_provider()


def test_default_bind_fills_unbound_provider_gap() -> None:
    assert bound_source_002_row_level_read_session_provider() is live_session_provider


def test_live_session_provider_returns_session_or_none_without_inventing_url() -> None:
    session = live_session_provider()
    assert session is None or isinstance(session, Session)
    if session is not None:
        session.close()


def test_bound_live_session_then_fail_closed_is_not_source_002_row_level_read() -> None:
    result = attest_accepted_s2_train_val_source_002_row_level_read()

    assert result.attested is False
    assert result.source_002_row_level_read is False
    assert result.official_hashes_attested_from_a_live_read is False
    assert result.reason_code is not Source002RowLevelReadReasonCode.ATTESTED
    assert SOURCE_002_ROW_LEVEL_READ is False


def test_explicit_override_still_wins_over_default_live_provider() -> None:
    set_source_002_row_level_read_session_provider(lambda: None)

    result = attest_accepted_s2_train_val_source_002_row_level_read()

    assert result.reason_code is Source002RowLevelReadReasonCode.FAIL_CLOSED_NO_SESSION
    assert result.attested is False
    assert result.source_002_row_level_read is False


def test_s2_source_002_row_level_read_constant_remains_false() -> None:
    assert SOURCE_002_ROW_LEVEL_READ is False


def test_reader_and_live_session_modules_contain_no_connection_string() -> None:
    reader_source = READER_MODULE.read_text(encoding="utf-8").lower()
    live_source = LIVE_SESSION_MODULE.read_text(encoding="utf-8").lower()
    for source in (reader_source, live_source):
        assert "postgresql://" not in source
        assert "create_engine(" not in source


def test_frozen_test_catalog_artifact_blob_unchanged() -> None:
    blob = subprocess.check_output(
        ["git", "hash-object", "backend/tests/s3_daily_rowset/test_catalog_artifact.py"],
        text=True,
    ).strip()
    assert blob == TEST_CATALOG_ARTIFACT_PY_BLOB


def test_s3_daily_rowset_has_no_production_init_py() -> None:
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()
