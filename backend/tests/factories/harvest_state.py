"""Harvest-state factory composing fixture objects via production canonical.

Per the Batch 5 design freeze (PR #68 / Issue #53), this factory
composes harvest-state fixture data by **calling** production
canonical / hash / key / ID implementations under
``backend.app.harvest_state.canonical`` rather than reimplementing
them. The factory returns a ``HarvestStateFactoryOutput`` dataclass
that downstream test code passes to assertions.

Scope (per design §4.2):

- Factory composition (test data + identities).
- Allowed imports: ``backend.app.**`` (production canonical),
  ``backend.tests.db`` (DB profile / session), standard library,
  pytest, sqlalchemy.
- Forbidden imports: ``backend.tests.assertions``,
  ``backend.tests.factories`` self-circular (no cross-importing),
  and ``backend.tests.db`` for asserting invariants.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.harvest_state.canonical import (
    canonical_json_dumps,
    make_result_hash,
)
from backend.tests.factories.identity import TestIdentity, build_test_identity


@dataclass(frozen=True)
class HarvestStateFactoryOutput:
    """Composed fixture output for harvest-state tests.

    Attributes
    ----------
    identity:
        The typed test identity (per design §4.3).
    canonical_output_json:
        The canonical JSON string of the composed output, computed via
        :func:`backend.app.harvest_state.canonical.canonical_json_dumps`.
        This is the production canonical serialization; test code
        MUST NOT re-serialize the fixture through a different path
        or the result_hash comparison will fail.
    result_hash:
        The production canonical result hash, computed via
        :func:`backend.app.harvest_state.canonical.make_result_hash`.
    """

    identity: TestIdentity
    canonical_output_json: str
    result_hash: str


def harvest_state_factory(
    run_id: int,
    scope_id: int,
    *,
    output_payload: Any,
    audit_payload: Any | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> HarvestStateFactoryOutput:
    """Compose a harvest-state fixture using production canonical.

    Parameters
    ----------
    run_id:
        Test-identity ``run_id``.
    scope_id:
        Test-identity ``scope_id``.
    output_payload:
        Domain payload (e.g. Task9ACompletedOutput). Serialized via
        :func:`backend.app.harvest_state.canonical.canonical_json_dumps`.
    audit_payload:
        Optional audit payload. If absent, ``audit_payload_hash`` is
        computed from the canonical output JSON.
    extra_metadata:
        Optional auxiliary metadata forwarded into the test identity.

    Returns
    -------
    HarvestStateFactoryOutput
        The composed fixture with the typed identity, canonical JSON,
        and production canonical result hash.
    """
    canonical_output = canonical_json_dumps(output_payload)
    audit_input = audit_payload if audit_payload is not None else canonical_output
    identity = build_test_identity(
        run_id=run_id,
        scope_id=scope_id,
        payload=output_payload,
        audit_payload=audit_input,
        extra_metadata=extra_metadata,
    )
    result_hash = make_result_hash({"output": output_payload})
    return HarvestStateFactoryOutput(
        identity=identity,
        canonical_output_json=canonical_output,
        result_hash=result_hash,
    )


__all__ = ["HarvestStateFactoryOutput", "harvest_state_factory"]
