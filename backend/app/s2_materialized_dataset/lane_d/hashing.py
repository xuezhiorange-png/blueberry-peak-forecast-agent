"""Hash helpers for Lane D materialized partitions and manifests."""

from __future__ import annotations

import hashlib

from backend.app.rolling_backtest.canonical import canonical_json_dumps, sha256_payload


def content_sha256(content_bytes: bytes) -> str:
    return hashlib.sha256(content_bytes).hexdigest()


def manifest_sha256(manifest_payload: dict[str, object]) -> str:
    excluded = {
        "manifest_sha256",
        "build_started_at",
        "build_completed_at",
    }
    control_payload = {key: value for key, value in manifest_payload.items() if key not in excluded}
    return sha256_payload(control_payload)


def manifest_control_payload(manifest_payload: dict[str, object]) -> str:
    excluded = {
        "manifest_sha256",
        "build_started_at",
        "build_completed_at",
    }
    control_payload = {key: value for key, value in manifest_payload.items() if key not in excluded}
    return canonical_json_dumps(control_payload)
