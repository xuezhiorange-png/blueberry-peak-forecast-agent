"""Lane D hashing tests."""

from __future__ import annotations

from datetime import UTC, datetime

from backend.app.s2_materialized_dataset.lane_d.hashing import (
    content_sha256,
    manifest_control_payload,
    manifest_sha256,
)


def test_content_sha256_matches_bytes() -> None:
    payload = b'{"a":1}\n'
    assert content_sha256(payload) == content_sha256(payload)
    assert len(content_sha256(payload)) == 64


def test_manifest_sha256_excludes_self_and_build_timestamps() -> None:
    payload = {
        "dataset_id": "ds-1",
        "dataset_version": "v1",
        "manifest_sha256": "should-be-ignored",
        "build_started_at": datetime(2026, 1, 1, tzinfo=UTC),
        "build_completed_at": datetime(2026, 1, 2, tzinfo=UTC),
        "row_count": 1,
    }
    digest_a = manifest_sha256(payload)
    payload["manifest_sha256"] = "different"
    digest_b = manifest_sha256(payload)
    assert digest_a == digest_b
    assert "manifest_sha256" not in manifest_control_payload(payload)
