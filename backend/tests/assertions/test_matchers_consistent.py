"""Test that assertions module composes production-canonical expected values.

Per the Batch 5 design freeze (PR #68 / Issue #53) §8, this test
verifies that ``backend.tests.assertions.canonical.assert_canonical_payload_hash``
recomputes the hash via ``backend.app.harvest_state.canonical.sha256_hex``
and asserts equality. It also verifies that
``assert_canonical_serialization`` recomputes via ``canonical_json_dumps``.

If either test fails, the assertion helper is broken — either it is
calling a non-canonical helper or the canonical serialization has
drifted. Either way, the test must surface the divergence.
"""

from __future__ import annotations

import pytest

from backend.app.harvest_state.canonical import canonical_json_dumps, sha256_hex
from backend.tests.assertions.canonical import (
    assert_canonical_payload_hash,
    assert_canonical_serialization,
)


def test_assert_canonical_payload_hash_passes_when_hashes_match() -> None:
    """Same payload hashed by production canonical must match."""
    payload = {"k": "v", "n": 1}
    expected = sha256_hex(payload)
    # Should not raise.
    assert_canonical_payload_hash(payload, expected)


def test_assert_canonical_payload_hash_fails_when_hashes_differ() -> None:
    """If the hash does not match, the assertion must raise."""
    payload = {"k": "v"}
    bogus = "0" * 64
    with pytest.raises(AssertionError):
        assert_canonical_payload_hash(payload, bogus)


def test_assert_canonical_payload_hash_rejects_non_sha256_hex_string() -> None:
    """A non-SHA-256-hex expected string is rejected upfront."""
    with pytest.raises(AssertionError):
        assert_canonical_payload_hash({"k": "v"}, "not-a-hash")


def test_assert_canonical_serialization_passes_when_canonical_json_matches() -> None:
    """Production canonical serialization must round-trip exactly."""
    payload = {"b": 2, "a": 1}  # intentionally unsorted; canonical sorts.
    expected = canonical_json_dumps(payload)
    # Should not raise.
    assert_canonical_serialization(payload, expected)


def test_assert_canonical_serialization_fails_on_drifted_canonical() -> None:
    """If the expected canonical JSON is from a different serialization path, fail."""
    payload = {"a": 1, "b": 2}
    bogus = '{"a": 1, "b": 2}'  # not canonical (no sort_keys, different separators).
    with pytest.raises(AssertionError):
        assert_canonical_serialization(payload, bogus)