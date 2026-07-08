"""Canonical payload assertion helpers.

Per the Batch 5 design freeze (PR #68 / Issue #53), assertions are
**pure helpers** that compare observed values against production-
computed expected values. Assertions MUST NOT construct fixtures or
open DB sessions (per design §5.2 forbidden imports).

The helpers here all take values as arguments; they do not pull
fixtures from a global state.
"""

from __future__ import annotations

from backend.app.harvest_state.canonical import (
    is_sha256_hex,
    sha256_hex,
)


def assert_canonical_payload_hash(payload: object, expected_hash: str) -> None:
    """Assert that ``sha256_hex(payload) == expected_hash``.

    The expected hash MUST have been computed via the **production
    canonical** :func:`backend.app.harvest_state.canonical.sha256_hex`.
    Re-hashing via a different in-test implementation will fail
    because canonical JSON serialization (sort_keys, separators) is
    production-controlled.

    Raises
    ------
    AssertionError
        If the recomputed hash does not match ``expected_hash`` or if
        ``expected_hash`` is not a canonical SHA-256 hex string.
    """
    assert is_sha256_hex(expected_hash), (
        f"expected_hash is not a canonical SHA-256 hex string: {expected_hash!r}"
    )
    actual_hash = sha256_hex(payload)
    assert actual_hash == expected_hash, (
        f"canonical_payload_hash mismatch: expected={expected_hash!r} actual={actual_hash!r}"
    )


def assert_canonical_serialization(
    payload: object,
    expected_canonical_json: str,
) -> None:
    """Assert that ``canonical_json_dumps(payload) == expected_canonical_json``.

    ``expected_canonical_json`` MUST have been produced by the
    production canonical serialization. This helper is symmetric with
    :func:`assert_canonical_payload_hash` and exists so call sites
    can pick the most readable assertion.
    """
    # Local import to keep this module import-side-effect free when
    # only the hash helpers are needed.
    from backend.app.harvest_state.canonical import canonical_json_dumps  # noqa: PLC0415

    actual = canonical_json_dumps(payload)
    assert actual == expected_canonical_json, (
        f"canonical JSON mismatch: expected={expected_canonical_json!r} actual={actual!r}"
    )


__all__ = [
    "assert_canonical_payload_hash",
    "assert_canonical_serialization",
]
