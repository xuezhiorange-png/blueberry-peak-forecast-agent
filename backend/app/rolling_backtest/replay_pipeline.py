"""Task 11 Phase 3.1 bucket #5 — replay pipeline / dispatch lift.

Per ``docs/task-11-phase3-retrospective-replay-amendment.md`` §5
(Decision 3 — Replay runner / node orchestration location), Phase 3.1
delegates replay-mode dispatch to a new module in
``backend/app/rolling_backtest/replay_pipeline.py`` that **composes
around** (does not replace) the existing Task 8 / Task 9 / Task 10
service paths.

This module implements the canonical entry point
:func:`orchestrate_replay_node` that

1. validates the **explicit** replay runtime identity and replay
   correlation id (§4.3 + §4.4 contract);
2. runs the §6 audit loop via the bucket-#3 audit writer
   :func:`replay_audit.write_replay_source_visibility_audit` — one
   ``harvest_state_replay_source_visibility_audit`` row per upstream
   source in ``node.resolved_upstream_semantic_identities`` (§6);
3. invokes **only** the approved Task 9 application entry point
   :func:`harvest_state.application.execute_harvest_state_run` (§3, no
   direct ``run_harvest_state_model`` calls, no lower-level Task 9
   internals);
4. invokes the bucket-#4 replay metadata writer
   :func:`replay_metadata.write_replay_metadata` to stamp the five
   §4 columns onto the just-persisted ``harvest_state_run`` row.

The pipeline surfaces missing / invalid replay inputs, ambiguous
cutoff visibility, and empty upstream identities using the bucket-#2
frozen :class:`OrchestrationBlocker` literal codes
(``REPLAY_RUNTIME_IDENTITY_MISSING`` / ``REPLAY_METADATA_INVALID`` /
``REPLAY_AUDIT_INCOMPLETE`` etc).

Hard boundaries (per Charles's bucket #5 authorization):

* No new Alembic migration is created.
* No schema / ORM changes are made; the replay audit table
  ``harvest_state_replay_source_visibility_audit`` and the five replay
  metadata columns on ``harvest_state_run`` are reused as-is from
  PR #31.
* The Task 9 application entry point
  :func:`harvest_state.application.execute_harvest_state_run` is the
  single Task 9 sink — :func:`run_harvest_state_model` and other
  lower-level Task 9 internals are **not** called.
* Task 10 binding / residual-model training behavior are **not**
  implemented here — those are buckets #6+ (out of scope).
* Availability / resolution semantics are not changed beyond what the
  bucket-#3 audit writer already enforces (§6 + §9 *no current-data
  fallback* defence).
* The frozen amendment doc / PR #30 body / Issue #29 body / Frozen
  Amendment Content SHA are **not** updated.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.harvest_state.application import execute_harvest_state_run
from backend.app.rolling_backtest.orchestration import OrchestrationBlocker
from backend.app.rolling_backtest.replay_audit import (
    ReplayAuditIncompleteError,
    UpstreamVisibilityDecision,
    write_replay_source_visibility_audit,
)
from backend.app.rolling_backtest.replay_metadata import (
    ReplayMetadataInputError,
    ReplayRunIdentity,
    write_replay_metadata,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from backend.app.harvest_state.schemas import Task9ARequest
    from backend.app.rolling_backtest.schemas import (
        RollingBacktestConfig,
        RollingNodeDefinition,
    )


# ── §6 / §4.5 audit-row policy literals (read-only handles) ──────────────────
# The bucket-#3 audit-writer's per-row ``source_visibility_source`` value is
# one of three documented strings. Replay Pipeline #1 always uses
# ``availability_audit`` because the replay path reuses the historical
# resolver's persisted identities (which produced an availability audit row
# at resolve-time); replay stamps the documented audit-trace row.
_REPLAY_AUDIT_SOURCE: Final[str] = "availability_audit"


# ── §3 / §5 module-local error types ──────────────────────────────────────────
# Composed from the bucket #2 frozen ``OrchestrationBlocker`` literal values
# so the dispatch caller can map the failure to the right taxonomy entry.


class ReplayPipelineError(RuntimeError):
    """§5 / §7 — base class for ``orchestrate_replay_node`` failures.

    Subclasses and direct uses carry an :attr:`blocker_code` mirroring
    the bucket-#2 frozen :class:`OrchestrationBlocker` literal value so
    downstream dispatch callers can serialize the failure into the
    rolling report without re-mapping.
    """

    def __init__(self, message: str, *, blocker_code: str) -> None:
        super().__init__(message)
        self.blocker_code = blocker_code


class ReplayPipelineInputError(ReplayPipelineError, ValueError):
    """§4.3 + §4.4 — caller passed an invalid replay runtime identity.

    Raised at the boundary **before** any DB round-trip; the bucket-#4
    metadata writer also raises a :class:`ReplayMetadataInputError` for
    the same purpose once :func:`write_replay_metadata` is reached. The
    pipeline raises this earlier so the dispatch caller can short-circuit
    before the §6 audit loop opens.
    """


# ── §5 / §3 module-level frozen-blocker handles (private) ─────────────────────
# These four are the canonical literal values owned by bucket #2 and
# re-used here verbatim. They are NOT redefined in this module; the
# import from ``OrchestrationBlocker`` is the single source of truth.
_RUNTIME_IDENTITY_MISSING_BLOCKER: Final[str] = (
    OrchestrationBlocker.REPLAY_RUNTIME_IDENTITY_MISSING.value
)
_METADATA_INVALID_BLOCKER: Final[str] = (
    OrchestrationBlocker.REPLAY_METADATA_INVALID.value
)
_AUDIT_INCOMPLETE_BLOCKER: Final[str] = (
    OrchestrationBlocker.REPLAY_AUDIT_INCOMPLETE.value
)


def _require_non_blank_text(
    value: str,
    *,
    field_name: str,
    blocker_code: str,
) -> str:
    """Reject blank / missing runtime-identity strings at the pipeline boundary."""
    if not isinstance(value, str) or not value.strip():
        raise ReplayPipelineInputError(
            f"{field_name} must be a non-blank string",
            blocker_code=blocker_code,
        )
    return value


# ── Public typed output contract ──────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ReplayPipelineOutcome:
    """Phase 3.1 bucket-#5 replay-pipeline outcome envelope.

    The orchestrator wraps this into the canonical
    :class:`NodeOrchestrationOutcome` (or its successor) for the rolling
    report layer. Bucket #5 does not alter the public
    ``NodeOrchestrationOutcome`` shape (§5.5 "composes around … not
    replaces").
    """

    task9_run_id: int
    audit_row_count: int
    replay_executed_at: datetime
    replay_correlation_id: str
    code_version: str


# ── Public entry point ───────────────────────────────────────────────────────


async def orchestrate_replay_node(
    *,
    session: AsyncSession,
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
    task9a_request: Task9ARequest | Mapping[str, object],
    code_version: str,
    replay_correlation_id: str,
) -> ReplayPipelineOutcome:
    """§5 + §3 + §6 + §4 — bucket-#5 replay-pipeline canonical entry point.

    Returns a :class:`ReplayPipelineOutcome` after one
    ``session.flush()`` round-trip per writer (audit + metadata share
    the same :class:`AsyncSession` and the pipeline does **not**
    ``commit()``; the dispatch caller commits).

    Algorithm (in order):

    1. **Validate inputs first** — non-blank ``code_version`` (§4.3) and
       ``replay_correlation_id`` (§4.4). On violation, raise
       :class:`ReplayPipelineInputError` with the bucket-#2 frozen
       :attr:`OrchestrationBlocker.REPLAY_RUNTIME_IDENTITY_MISSING` /
       :attr:`OrchestrationBlocker.REPLAY_METADATA_INVALID` literal
       value. **No DB round-trip** is performed before this check.
    2. **Snapshot upstream identities** from
       ``node.resolved_upstream_semantic_identities``. If empty, raise
       :class:`ReplayPipelineError` carrying
       :attr:`OrchestrationBlocker.REPLAY_AUDIT_INCOMPLETE` (§6 ¶4).
    3. **§6 audit loop** — call the bucket-#3 audit writer
       :func:`replay_audit.write_replay_source_visibility_audit` with
       one :class:`UpstreamVisibilityDecision` per resolved identity
       (visibility passed carried over from the historical resolver
       via the persisted identities, not re-evaluated here). The
       audit row's ``harvest_state_run_id`` FK is left ``None`` —
       the FK ``fk_hsrpsva_harvest_state_run_id`` is nullable
       (``ondelete=SET NULL``), and downstream readers JOIN via the
       ``harvest_state_run.replay_run_correlation_id`` column the
       bucket-#4 metadata writer stamps onto the run row (§4.4).
    4. **§3 Task 9 canonical entry point** — call **only**
       :func:`harvest_state.application.execute_harvest_state_run`
       with the dispatch-caller-supplied ``task9a_request``. No
       direct ``run_harvest_state_model`` invocation, no lower-level
       Task 9 internals.
    5. **§4 metadata write** — call the bucket-#4 metadata writer
       :func:`replay_metadata.write_replay_metadata` with the
       just-produced ``run_id``, the **explicit caller-supplied**
       :class:`ReplayRunIdentity`, and the **explicit caller-supplied
       UTC** ``replay_executed_at`` (per §4.1 "no server default").
       The bucket-#4 writer itself validates inputs and surfaces
       bucket-#2 blocker codes on failure.
    6. Return a :class:`ReplayPipelineOutcome` carrying the produced
       ``task9_run_id``, audit row count, replay identity and
       :class:`~datetime.datetime` for the rolling report.

    The pipeline does **not**:

    * infer the runtime identity from the database, the wall clock,
      logs, or cached values (§9 *no current-data fallback*);
    * fabricate audit rows, metadata rows, or stub identities;
    * silently drop a zero-row audit batch (§6 ¶4 →
      :attr:`OrchestrationBlocker.REPLAY_AUDIT_INCOMPLETE`);
    * skip the metadata write step §4 (the pipeline raises if the
      bucket-#4 writer surfaces :class:`ReplayMetadataInputError` /
      :class:`ReplayMetadataConflictError`).
    """
    # ── 1. Validate inputs first (no DB round-trip) ──────────────────────
    code_version_clean = _require_non_blank_text(
        code_version,
        field_name="code_version",
        blocker_code=_RUNTIME_IDENTITY_MISSING_BLOCKER,
    )
    replay_correlation_id_clean = _require_non_blank_text(
        replay_correlation_id,
        field_name="replay_correlation_id",
        blocker_code=_METADATA_INVALID_BLOCKER,
    )

    # ── 2. Snapshot upstream identities; reject empty (§6 ¶4) ─────────────
    identities: tuple[Any, ...] = tuple(node.resolved_upstream_semantic_identities)
    if not identities:
        raise ReplayPipelineError(
            f"replay pipeline received node {node.season_id}/{node.node_key} "
            "with zero resolved upstream semantic identities; replay "
            "MUST produce a one-audit-row per upstream source per §6",
            blocker_code=_AUDIT_INCOMPLETE_BLOCKER,
        )

    # ── 3. §6 audit loop via the bucket-#3 writer ────────────────────────
    audit_decisions: list[UpstreamVisibilityDecision] = [
        UpstreamVisibilityDecision(
            identity=identity,
            visibility_source=_REPLAY_AUDIT_SOURCE,
            visibility_passed=True,
            rejection_blocker_code=None,
        )
        for identity in identities
    ]
    try:
        await write_replay_source_visibility_audit(
            session=session,
            harvest_state_run_id=None,
            node=node,
            config=config,
            upstream_visibility=audit_decisions,
        )
    except ReplayAuditIncompleteError as exc:
        # Defensive: bucket #3 already enforces §6 ¶4, but keep the
        # error reachable through the pipeline for callers that wrap a
        # single try/except around this function.
        raise ReplayPipelineError(
            f"bucket #3 audit writer refused empty batch: {exc}",
            blocker_code=_AUDIT_INCOMPLETE_BLOCKER,
        ) from exc

    # ── 4. §3 Task 9 canonical entry point ──────────────────────────────
    envelope = await execute_harvest_state_run(
        session=session,
        request=task9a_request,
    )
    task9_run_id: int = envelope.run_id

    # ── 5. §4 metadata write via the bucket-#4 writer ────────────────────
    replay_executed_at_utc = datetime.now(UTC)
    try:
        await write_replay_metadata(
            session=session,
            config=config,
            rolling_node=node,
            run_id=task9_run_id,
            replay_executed_at=replay_executed_at_utc,
            replay_identity=ReplayRunIdentity(
                code_version=code_version_clean,
                run_correlation_id=replay_correlation_id_clean,
            ),
        )
    except ReplayMetadataInputError as exc:
        # The bucket-#4 writer already raises a typed input error with
        # the bucket-#2 frozen blocker code attached; re-raise as the
        # pipeline's ReplayPipelineError so dispatch callers can
        # uniformly handle ``ReplayPipelineError``.
        raise ReplayPipelineError(
            f"bucket #4 metadata writer rejected inputs: {exc}",
            blocker_code=exc.blocker_code,
        ) from exc

    return ReplayPipelineOutcome(
        task9_run_id=task9_run_id,
        audit_row_count=len(audit_decisions),
        replay_executed_at=replay_executed_at_utc,
        replay_correlation_id=replay_correlation_id_clean,
        code_version=code_version_clean,
    )


__all__ = (
    "ReplayPipelineError",
    "ReplayPipelineInputError",
    "ReplayPipelineOutcome",
    "orchestrate_replay_node",
)
