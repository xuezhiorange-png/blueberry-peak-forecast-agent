"""Typed test identity dataclass and builders for the Batch 5 ``factories/`` package.

Per the Batch 5 design freeze (PR #68 / Issue #53) §4.3, the typed
factory contract explicitly carries two typed inputs:

1. **DB identifier**: ``database_url`` / ``port`` / ``role`` /
   ``profile_name``. Factories refuse to construct if the effective
   DB identifier does not match ``APP_ENV=test`` profile rules.

2. **Test identity**: a typed tuple of
   ``(run_id, scope_id, canonical_payload_hash, audit_payload_hash)``
   where the two hashes are computed via **production canonical
   implementations** under ``backend.app.harvest_state.canonical``
   and ``backend.app.rolling_backtest.canonical``. Test-only helpers
   MUST NOT reimplement these hashes.

The ``TestIdentity`` dataclass is the typed input; factories accept
``TestIdentity`` and return composed fixture objects. No factory
re-implements canonical logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.app.harvest_state.canonical import sha256_hex
from backend.app.rolling_backtest.canonical import sha256_payload


@dataclass(frozen=True)
class TestIdentity:
    """Typed test identity (per design §4.3).

    Attributes
    ----------
    run_id:
        The numeric GitHub Actions ``GITHUB_RUN_ID`` for the
        invocation, or a test-suite-stable integer for unit tests.
    scope_id:
        The numeric ``GITHUB_RUN_ATTEMPT`` for the invocation, or a
        test-suite-stable integer for unit tests.
    canonical_payload_hash:
        SHA-256 hex digest of the canonical payload, computed via
        :func:`backend.app.harvest_state.canonical.sha256_hex`. This
        is the **production canonical** hash and MUST NOT be
        reimplemented locally.
    audit_payload_hash:
        SHA-256 hex digest of the canonical audit payload, computed
        via :func:`backend.app.rolling_backtest.canonical.sha256_payload`
        over :func:`backend.app.rolling_backtest.availability.availability_snapshot_audit_payload`
        (or any other domain-specific audit payload). This is the
        **production canonical** audit hash and MUST NOT be
        reimplemented locally.
    extra_metadata:
        Domain-specific auxiliary metadata that downstream factories
        may attach (e.g. scope tags). MUST NOT affect the canonical
        hashes.
    """

    run_id: int
    scope_id: int
    canonical_payload_hash: str
    audit_payload_hash: str
    extra_metadata: dict[str, Any] = field(default_factory=dict)


def build_test_identity(
    run_id: int,
    scope_id: int,
    *,
    payload: Any,
    audit_payload: Any,
    extra_metadata: dict[str, Any] | None = None,
) -> TestIdentity:
    """Build a typed test identity by computing the two canonical hashes.

    The two hash functions called here are the **production canonical**
    implementations. Test-only helpers MUST NOT replace them with
    in-test reimplementations. Per design §6, the
    ``test_no_canonical_reimplementation`` scope-guard test enforces
    this rule by AST-grepping the ``factories/`` and ``assertions/``
    packages for forbidden hash / hmac / sign patterns.
    """
    return TestIdentity(
        run_id=run_id,
        scope_id=scope_id,
        canonical_payload_hash=sha256_hex(payload),
        audit_payload_hash=sha256_payload(audit_payload),
        extra_metadata=dict(extra_metadata or {}),
    )


__all__ = ["TestIdentity", "build_test_identity"]