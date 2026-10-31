"""Negative integrity tests; no authentication, network or business database."""

import hashlib
from pathlib import Path

import pytest

from backend.app.core.historical_code_identity import current_code_fixture
from backend.tests.historical_source import (
    AUTHORIZED_HISTORY_PATHS,
    HISTORICAL_COMMIT,
    historical_bytes,
    source_bytes,
    verified_source,
)


def test_reviewed_fixed_commit_exists_and_blobs_match() -> None:
    for path in AUTHORIZED_HISTORY_PATHS:
        assert historical_bytes(path, HISTORICAL_COMMIT)


def test_expected_digest_is_not_rewritten_or_ignored() -> None:
    with pytest.raises(AssertionError, match="SHA256 mismatch"):
        verified_source("backend/app/main.py", "0" * 64)
    original = historical_bytes("backend/app/main.py", HISTORICAL_COMMIT)
    assert verified_source("backend/app/main.py", hashlib.sha256(original).hexdigest()) == original


@pytest.mark.parametrize("commit", ["0" * 40, "HEAD", HISTORICAL_COMMIT + "~1"])
def test_absent_or_untrusted_revision_fails(commit: str) -> None:
    with pytest.raises(AssertionError):
        historical_bytes("backend/app/main.py", commit)


@pytest.mark.parametrize("path", ["../secret", "/secret", "a:b", "a\\b", "", "a/../b"])
def test_path_cannot_escape_or_inject_revision(path: str) -> None:
    with pytest.raises(AssertionError):
        historical_bytes(path, HISTORICAL_COMMIT)


def test_missing_blob_fails() -> None:
    with pytest.raises(AssertionError, match="source unavailable"):
        historical_bytes("backend/does-not-exist", HISTORICAL_COMMIT)


def test_current_runtime_edit_does_not_rewrite_historical_hash(tmp_path: Path) -> None:
    path = "backend/app/main.py"
    # Exact code and Commit/Tree metadata only; never fetch business history.
    with current_code_fixture(HISTORICAL_COMMIT, path) as tmp_path:
        original = historical_bytes(path, HISTORICAL_COMMIT)
        candidate = tmp_path / path
        candidate.parent.mkdir(parents=True)
        candidate.write_bytes(b"authorized future runtime content\n")
        assert source_bytes(path, root=tmp_path) == original
        assert hashlib.sha256(candidate.read_bytes()).digest() != hashlib.sha256(original).digest()


def test_frozen_document_tampering_still_fails(tmp_path: Path) -> None:
    path = "docs/frozen.json"
    candidate = tmp_path / path
    candidate.parent.mkdir()
    candidate.write_bytes(b"original")
    digest = hashlib.sha256(b"original").hexdigest()
    assert verified_source(path, digest, root=tmp_path) == b"original"
    candidate.write_bytes(b"tampered")
    with pytest.raises(AssertionError, match="SHA256 mismatch"):
        verified_source(path, digest, root=tmp_path)
