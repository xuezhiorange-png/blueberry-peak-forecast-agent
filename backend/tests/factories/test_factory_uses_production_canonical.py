"""Test that the typed factory contract composes production-canonical hashes.

Per the Batch 5 design freeze (PR #68 / Issue #53) §8, this test
verifies that ``backend.tests.factories.identity.build_test_identity``
delegates canonical hashing to ``backend.app.harvest_state.canonical``
and ``backend.app.rolling_backtest.canonical`` rather than
reimplementing it locally.

It is a small, focused contract test that exercises the typed
factory and asserts:

- ``identity.canonical_payload_hash`` equals what
  :func:`backend.app.harvest_state.canonical.sha256_hex` produces
  for the same payload.
- ``identity.audit_payload_hash`` equals what
  :func:`backend.app.rolling_backtest.canonical.sha256_payload`
  produces for the same audit payload.

If either test fails, the typed factory contract is broken — either
the factory is calling a non-canonical helper, or production canonical
helpers have drifted. Either way, the test must surface the
divergence immediately.
"""

from __future__ import annotations

from backend.app.harvest_state.canonical import sha256_hex
from backend.app.rolling_backtest.canonical import sha256_payload
from backend.tests.factories.identity import build_test_identity


def test_build_test_identity_canonical_payload_hash_matches_production() -> None:
    """``build_test_identity`` must delegate canonical hashing to backend.app.**"""
    payload = {"domain": "harvest_state", "version": 1, "items": [1, 2, 3]}
    audit_payload = {"audit_kind": "decision", "ts": "2026-07-08T00:00:00Z"}

    identity = build_test_identity(
        run_id=42,
        scope_id=1,
        payload=payload,
        audit_payload=audit_payload,
    )

    expected_canonical = sha256_hex(payload)
    expected_audit = sha256_payload(audit_payload)

    assert identity.canonical_payload_hash == expected_canonical, (
        f"identity.canonical_payload_hash={identity.canonical_payload_hash!r} "
        f"does not equal production sha256_hex(payload)={expected_canonical!r}"
    )
    assert identity.audit_payload_hash == expected_audit, (
        f"identity.audit_payload_hash={identity.audit_payload_hash!r} "
        f"does not equal production sha256_payload(audit_payload)={expected_audit!r}"
    )


def test_build_test_identity_passes_through_run_id_and_scope_id() -> None:
    """run_id / scope_id are forwarded as typed inputs verbatim."""
    identity = build_test_identity(
        run_id=12345,
        scope_id=2,
        payload={"x": 1},
        audit_payload={"y": 2},
    )
    assert identity.run_id == 12345
    assert identity.scope_id == 2


def test_build_test_identity_optional_extra_metadata() -> None:
    """extra_metadata is optional and does not affect canonical hashes."""
    payload = {"x": 1}
    audit_payload = {"y": 2}

    identity_no_extra = build_test_identity(
        run_id=1,
        scope_id=1,
        payload=payload,
        audit_payload=audit_payload,
    )
    identity_with_extra = build_test_identity(
        run_id=1,
        scope_id=1,
        payload=payload,
        audit_payload=audit_payload,
        extra_metadata={"scope_tag": "smoke"},
    )

    assert identity_no_extra.canonical_payload_hash == identity_with_extra.canonical_payload_hash
    assert identity_no_extra.audit_payload_hash == identity_with_extra.audit_payload_hash
    assert identity_with_extra.extra_metadata == {"scope_tag": "smoke"}
