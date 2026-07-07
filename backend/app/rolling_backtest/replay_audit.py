"""Task 11 Phase 3.1 bucket #3 — replay source visibility audit writer.

This module implements the writer for the replay source visibility audit
required by frozen amendment §6 (Decision 4).

Schema authority
----------------
The target table ``harvest_state_replay_source_visibility_audit`` and the
five replay metadata columns on ``harvest_state_run`` were added by
``backend/alembic/versions/0015_task11_phase3_schema_gap.py`` (Phase 3.0
schema prerequisite, merged at ``c0377521``). This module NEVER creates
or modifies migrations — it only writes rows into the table that PR #31
already established.

Frozen contract pointers
------------------------
- §6 (Decision 4 — Source visibility audit): one row per item in
  ``RollingNodeDefinition.resolved_upstream_semantic_identities``;
  exact column sources documented in :data:`_AUDIT_FIELD_SOURCES`;
  determinstic ordering by lexicographic ``source_role``.
- §6 ¶3 (Ordering policy): rows are written in the same order as
  ``node.resolved_upstream_semantic_identities`` sorted by
  ``source_role`` lexicographically.
- §6 ¶4 (Failure mode): a replay run that produces zero audit rows is
  rejected with code :attr:`OrchestrationBlocker.REPLAY_AUDIT_INCOMPLETE`
  (§7 blocker taxonomy, frozen in bucket #2).
- §3 (Decision 3 — Replay runner location): the audit loop runs
  BEFORE ``execute_harvest_state_run`` and writes one row per upstream
  source. Bucket #3 implements only the WRITER; the dispatcher that
  calls it lands in bucket #5 (out of scope here).

Scope boundaries (per Charles's bucket #3 authorization)
-------------------------------------------------------
- No migration is created or modified (schema is frozen at ``0015``).
- ORM models are unchanged (the existing
  ``HarvestStateReplaySourceVisibilityAuditModel`` is sufficient).
- No replay metadata writer logic (bucket #4, out of scope).
- No replay runner / dispatch lift (bucket #5, out of scope).
- No Task 9 service call (forbidden).
- No Task 10 binding hardening (bucket #6, out of scope).
- No availability / resolution selection logic (forbidden).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from typing import TYPE_CHECKING, Final

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.harvest_state import (
    HarvestStateReplaySourceVisibilityAuditModel,
)
from backend.app.rolling_backtest.enums import AvailabilityBlockerCode
from backend.app.rolling_backtest.orchestration import OrchestrationBlocker

if TYPE_CHECKING:
    from datetime import datetime

    from backend.app.rolling_backtest.schemas import (
        ResolvedUpstreamSemanticIdentity,
        RollingBacktestConfig,
        RollingNodeDefinition,
    )


# ── §6 field-of-value contract (read-only reference table) ────────────────────
# Each tuple pins the §6 column-to-source mapping. The writer raises an
# explicit error if any per-row input would force it to invent a value.
_AUDIT_FIELD_SOURCES: Final[tuple[tuple[str, str], ...]] = (
    ("harvest_state_run_id", "caller-supplied (id of replay-produced HarvestStateRun)"),
    ("source_role", "ResolvedUpstreamSemanticIdentity.source_role"),
    ("source_type", "ResolvedUpstreamSemanticIdentity.source_type.value"),
    ("source_visibility_source", "UpstreamVisibilityDecision.visibility_source"),
    ("forecast_cutoff_at", "RollingNodeDefinition.forecast_cutoff_at"),
    ("visibility_passed", "UpstreamVisibilityDecision.visibility_passed"),
    (
        "rejection_blocker_code",
        "UpstreamVisibilityDecision.rejection_blocker_code (NULL iff passed=True)",
    ),
    (
        "semantic_identity_hash",
        "sha256_hex(node_signature_hash(config, node) || source_role)",
    ),
    ("captured_at", "DB server default now() — writer does NOT set"),
)


# Frozen §6 ¶3 lexicographic ordering key.
_ORDER_BY_SOURCE_ROLE: Final[str] = "source_role"


# Frozen §7 / §6 ¶4 audit-incomplete blocker code.
_AUDIT_INCOMPLETE_BLOCKER: Final[str] = OrchestrationBlocker.REPLAY_AUDIT_INCOMPLETE.value


# ── Module-local errors (kept local per existing module-local pattern) ────────


class ReplayAuditIncompleteError(RuntimeError):
    """§6 ¶4 — replay produced zero audit rows; rejected with ``REPLAY_AUDIT_INCOMPLETE``.

    No source / ORM / migration is touched; this is a module-local
    exception type used by :func:`write_replay_source_visibility_audit`.
    The accompanying :attr:`blocker_code` is the bucket #2 frozen
    :attr:`OrchestrationBlocker.REPLAY_AUDIT_INCOMPLETE` literal value.
    """

    def __init__(self, message: str, *, blocker_code: str) -> None:
        super().__init__(message)
        # Bucket #2 added OrchestrationBlocker; carry its literal value.
        self.blocker_code = blocker_code


class ReplayAuditInputError(ValueError):
    """§6 — caller passed a decision payload that violates the frozen field-of-value rules.

    Examples:
    - ``visibility_passed=False`` but ``rejection_blocker_code`` is ``None`` or blank.
    - ``visibility_passed=True`` but ``rejection_blocker_code`` is non-None.
    - ``rejection_blocker_code`` is non-None and not a known
      :class:`AvailabilityBlockerCode` enum value.
    - ``visibility_source`` is blank.
    - Per-row ``source_role`` / ``source_type`` is blank.
    """


# ── Typed input contract (per-row) ────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class UpstreamVisibilityDecision:
    """Per-upstream-source replay visibility audit decision.

    The writer stamps exactly one row per ``identity`` matching the
    fields below. Required fields are enforced at the writer boundary
    so the DB-side CHECK constraints are never relied on as the sole
    gate (per §6 deterministic semantics).
    """

    identity: ResolvedUpstreamSemanticIdentity
    visibility_source: str
    visibility_passed: bool
    rejection_blocker_code: str | None = None

    def __post_init__(self) -> None:
        # Per §6, visibility_source is one of three documented strings.
        # The DB CHECK allows ANY non-blank string; the writer tightens
        # this to the §6 enumerated values so the writer itself never
        # emits a value §6 doesn't permit.
        if not self.visibility_source or not self.visibility_source.strip():
            raise ReplayAuditInputError("visibility_source must be a non-blank string")
        allowed_visibility_sources = (
            "availability_audit",
            "task8_visibility_manifest",
            "task9_verification_snapshot",
        )
        if self.visibility_source not in allowed_visibility_sources:
            raise ReplayAuditInputError(
                "visibility_source must be one of "
                f"{allowed_visibility_sources}, got {self.visibility_source!r}"
            )

        # §6 passed-blocker coupling: enforcement at the writer level so
        # DB CHECK violations never surface to the caller as opaque
        # IntegrityErrors.
        if self.visibility_passed:
            if self.rejection_blocker_code is not None:
                raise ReplayAuditInputError(
                    "rejection_blocker_code must be None when visibility_passed=True"
                )
        else:
            if not self.rejection_blocker_code or not self.rejection_blocker_code.strip():
                raise ReplayAuditInputError(
                    "rejection_blocker_code must be a non-blank string when visibility_passed=False"
                )
            # §6 says rejection_blocker_code is one of AvailabilityBlockerCode
            # enum values when visibility_passed=False. Validate the literal
            # against the enum so the writer never silently accepts arbitrary
            # strings.
            try:
                AvailabilityBlockerCode(self.rejection_blocker_code)
            except ValueError as exc:
                raise ReplayAuditInputError(
                    "rejection_blocker_code is not an AvailabilityBlockerCode "
                    f"value: {self.rejection_blocker_code!r}"
                ) from exc


# ── Writer ────────────────────────────────────────────────────────────────────


async def write_replay_source_visibility_audit(
    *,
    session: AsyncSession,
    harvest_state_run_id: int | None,
    node: RollingNodeDefinition,
    config: RollingBacktestConfig,
    upstream_visibility: Sequence[UpstreamVisibilityDecision],
) -> list[HarvestStateReplaySourceVisibilityAuditModel]:
    """§6 — persist one replay-audit row per upstream source, lex-ordered.

    Bucket #3-only writer; obeys frozen §6 exactly:

    - One row per item in
      ``RollingNodeDefinition.resolved_upstream_semantic_identities``.
      The caller passes these via the ``upstream_visibility`` sequence
      (one entry per resolved identity, in any order).
    - Row ordering: rows are inserted in lexicographic order of
      ``source_role`` so audit row order is identical across re-runs
      (modulo FK id allocation, which §6 explicitly allows).
    - Per-row field sources: ``_AUDIT_FIELD_SOURCES`` (and the §6 table
      in the amendment doc).
    - ``captured_at`` is filled by the DB ``now()`` default; the writer
      NEVER sets it.
    - Empty input is a §6 ¶4 contract violation and raises
      :class:`ReplayAuditIncompleteError` carrying the
      ``REPLAY_AUDIT_INCOMPLETE`` blocker code (§7).

    Transaction boundary: the writer inserts N rows in one
    ``session.flush()`` call (atomically per-call). The caller controls
    the surrounding transaction; per §4.2, idempotent replay re-runs
    produce new rows, so the writer is non-idempotent at this layer
    (caller's responsibility to gate re-runs).

    Idempotency / atomicity: PG FK + CHECK constraints enforce shape;
    the writer's pre-insert validation enforces the §6 §7 contracts
    so the caller never sees a DB-side IntegrityError for a field
    the contract already constrains.
    """
    if not upstream_visibility:
        # §6 ¶4: zero rows → REPLAY_AUDIT_INCOMPLETE. Use bucket #2
        # frozen literal carried in OrchestrationBlocker.REPLAY_AUDIT_INCOMPLETE.
        raise ReplayAuditIncompleteError(
            "replay produced zero audit rows; rejected per §6 ¶4",
            blocker_code=_AUDIT_INCOMPLETE_BLOCKER,
        )

    forecast_cutoff_at: datetime = node.forecast_cutoff_at
    if forecast_cutoff_at.tzinfo is None:
        raise ReplayAuditInputError("node.forecast_cutoff_at must be timezone-aware per §6")

    # §6 ¶3: deterministic ordering = sort by source_role lexicographically
    # BEFORE computing per-row semantic_identity_hash so the hash inputs
    # are stable across re-runs.
    ordered = sorted(
        upstream_visibility,
        key=lambda d: d.identity.source_role,
    )

    # §6 semantic_identity_hash row policy:
    # sha256_hex(node_signature_hash(config, node) || source_role)
    # where || is string concatenation (no separator per the contract's
    # literal form; collision risk on the hash output is bounded by
    # SHA-256 pre-image resistance).
    base_signature_hash = _compute_node_signature_hash(config=config, node=node)
    rows: list[HarvestStateReplaySourceVisibilityAuditModel] = []
    for decision in ordered:
        sem_hash_input = base_signature_hash + decision.identity.source_role
        sem_hash = sha256(sem_hash_input.encode("utf-8")).hexdigest()
        row = HarvestStateReplaySourceVisibilityAuditModel(
            harvest_state_run_id=harvest_state_run_id,
            source_role=decision.identity.source_role,
            source_type=decision.identity.source_type.value,
            source_visibility_source=decision.visibility_source,
            forecast_cutoff_at=forecast_cutoff_at,
            visibility_passed=decision.visibility_passed,
            rejection_blocker_code=decision.rejection_blocker_code,
            semantic_identity_hash=sem_hash,
            # captured_at: deliberately NOT set; DB defaults to now().
        )
        rows.append(row)
        session.add(row)

    # Atomic per-call: flush once so DB CHECK / FK / NOT NULL constraints
    # surface here as a clear writer-level error instead of at commit time.
    await session.flush()
    return rows


def _compute_node_signature_hash(
    *,
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
) -> str:
    """Local wrapper around ``node_signature_hash`` to avoid an import cycle.

    :func:`node_signature_hash` lives in
    :mod:`backend.app.rolling_backtest.signatures`, which itself
    imports several writer-adjacent modules. Importing it lazily here
    keeps :mod:`replay_audit` module-loadable without requiring
    ``RollingBacktestConfig`` / ``RollingNodeDefinition`` to be fully
    resolved at writer import time. TYPE_CHECKING import above covers
    the static-typing side.
    """
    from backend.app.rolling_backtest.signatures import node_signature_hash

    return node_signature_hash(config, node)


__all__ = [
    "UpstreamVisibilityDecision",
    "ReplayAuditIncompleteError",
    "ReplayAuditInputError",
    "write_replay_source_visibility_audit",
    "_AUDIT_FIELD_SOURCES",
]
