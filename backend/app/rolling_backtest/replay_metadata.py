"""Task 11 Phase 3.1 bucket #4 — replay metadata writer.

Per ``docs/task-11-phase3-retrospective-replay-amendment.md`` §4
(Decision 2 — Replay metadata write boundary):

After ``execute_harvest_state_run`` returns successfully with a
``HarvestStateRunEnvelope`` whose ``run_id`` identifies a freshly-persisted
``harvest_state_run`` row, the replay metadata writer updates *that* row
in the same ``AsyncSession`` to mark it as a replay run and stamps the
five replay metadata fields onto it. The writer additionally emits a
single ``harvest_state_replay_source_visibility_audit`` row (per §4.5)
that downstream readers use to reconstruct which upstream sources the
replay run was bound to.

This module is imported only by the bucket #5 dispatch path described in
§5 of the amendment; Phase 2 callers must continue to bypass it.

Hard boundaries (per Charles's bucket #4 authorization):

* No new Alembic migration is created.
* No schema changes are made.
* No ORM model is altered; the five columns ``is_replay`` /
  ``forecast_effective_cutoff_at`` / ``replay_executed_at`` /
  ``replay_code_version`` / ``replay_run_correlation_id`` and the audit
  table ``harvest_state_replay_source_visibility_audit`` already exist
  on ``harvest_state_run`` (PR #31 schema gap).
* The replay runner, dispatch lift, Task 9 service invocation, Task 10
  binding, and availability / resolution logic are out of scope.
* The Phase 2 / bucket-#1 / bucket-#3 code path is *not* modified.
* The frozen amendment doc, PR #30 body, Issue #29 body, and the
  Frozen Amendment Content SHA are *not* updated.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import TYPE_CHECKING, Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.harvest_state import (
    HarvestStateReplaySourceVisibilityAuditModel,
    HarvestStateRun,
)
from backend.app.rolling_backtest.orchestration import OrchestrationBlocker
from backend.app.rolling_backtest.signatures import node_signature_hash

if TYPE_CHECKING:
    from backend.app.rolling_backtest.schemas import (
        RollingBacktestConfig,
        RollingNodeDefinition,
    )


# ── §4 field-of-value contract (read-only reference table) ────────────────────
# Each tuple pins the §4 column-to-source mapping. The writer raises an
# explicit error if any input value would force it to invent a value.
METADATA_FIELD_SOURCES: Final[tuple[tuple[str, str], ...]] = (
    ("is_replay", "literal True (per §4.1 UPDATE block)"),
    (
        "forecast_effective_cutoff_at",
        "RollingNodeDefinition.forecast_cutoff_at (tz-aware)",
    ),
    (
        "replay_executed_at",
        "caller-supplied UTC datetime (writer does NOT fall back to now())",
    ),
    (
        "replay_code_version",
        "ReplayRunIdentity.code_version (non-blank, from §4.3)",
    ),
    (
        "replay_run_correlation_id",
        "ReplayRunIdentity.run_correlation_id (non-blank, per-replay, from §4.4)",
    ),
)


# ── Frozen §4 / §7 error blocker codes (read-only literal handles) ────────────
# Both blockers are owned by bucket #2 and re-used here verbatim.
_RUNTIME_IDENTITY_MISSING_BLOCKER: Final[str] = (
    OrchestrationBlocker.REPLAY_RUNTIME_IDENTITY_MISSING.value
)
_METADATA_INVALID_BLOCKER: Final[str] = OrchestrationBlocker.REPLAY_METADATA_INVALID.value


# ── §4.5 audit row format (literal handles) ──────────────────────────────────
# Per §4.5, the bucket-#4 audit row's ``source_role`` MUST be
# ``task9_harvest_state_run_replay:<run_id>`` so downstream readers can
# reconstruct the replay. The audit table's CHECK constraint
# ``ck_hsrpsva_type_non_blank`` only rejects blank ``source_type`` strings;
# using the ``task9_harvest_state_run_replay`` literal here is therefore
# legal at the DB CHECK level. ``source_type`` does not have to be a
# member of ``AvailabilitySourceType`` — bucket-#3's typed contract is
# strictly an upstream-source writer; bucket-#4 writes its own singular
# audit row tagged with the replay-run identity (§4.5).
_REPLAY_AUDIT_SOURCE_TYPE: Final[str] = "task9_harvest_state_run_replay"


def _replay_audit_source_role(run_id: int) -> str:
    """§4.5 — return the literal ``source_role`` for the bucket-#4 audit row."""
    return f"{_REPLAY_AUDIT_SOURCE_TYPE}:{run_id}"


# ── Public typed input contracts ──────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ReplayRunIdentity:
    """Caller-supplied replay runtime identity (per §4.3 + §4.4).

    Both fields are non-blank at the writer boundary so the DB CHECK
    ``ck_harvest_state_run_replay_metadata_coupling`` never sees an
    invalid value. Blank values raise :class:`ReplayMetadataInputError`
    with the bucket-#2 frozen ``REPLAY_RUNTIME_IDENTITY_MISSING`` blocker
    (per §4.3).
    """

    code_version: str
    run_correlation_id: str


# ── Module-local errors (kept local per existing module-local pattern) ────────


class ReplayMetadataInputError(ValueError):
    """§4.3 + §4 / §7 — caller passed a payload that violates §4 field rules.

    Examples:

    * ``replay_executed_at`` tz-naive (writer rejects before any DB
      round-trip per §9 *no current-data fallback* defence).
    * ``rolling_node.forecast_cutoff_at`` tz-naive.
    * ``replay_identity.code_version`` blank or empty (REPLAY_RUNTIME_IDENTITY_MISSING).
    * ``replay_identity.run_correlation_id`` blank or empty.
    * ``run_id`` not a positive integer.
    * Persisted ``harvest_state_run`` row not found for ``run_id``.
    * Caller passed an ORM ``HarvestStateRun`` whose ``is_replay`` was
      already ``True`` *and* the supplied payload disagrees with the
      pre-existing metadata — raised as
      :class:`ReplayMetadataConflictError` (not this exception).

    The accompanying :attr:`blocker_code` is one of the bucket-#2 frozen
    ``OrchestrationBlocker`` literals; for runtime-identity holes it is
    ``REPLAY_RUNTIME_IDENTITY_MISSING``; for all other §4 field-rule
    violations it is ``REPLAY_METADATA_INVALID``.
    """

    def __init__(self, message: str, *, blocker_code: str) -> None:
        super().__init__(message)
        self.blocker_code = blocker_code


class ReplayMetadataConflictError(RuntimeError):
    """§4.2 — UPDATE rejected because the target row is already ``is_replay=TRUE``.

    The bucket-#4 writer MUST NOT issue an UPDATE on a row whose
    ``is_replay`` is already ``TRUE`` (per §4.2 — *idempotent replay
    re-runs produce new rows*). If the dispatch caller accidentally
    targets such a row, the writer raises this error rather than
    silently overwriting the prior replay's metadata. The accompanying
    :attr:`blocker_code` carries the §7 frozen
    ``OrchestrationBlocker.REPLAY_METADATA_INVALID`` literal value.
    """

    def __init__(self, message: str, *, blocker_code: str) -> None:
        super().__init__(message)
        self.blocker_code = blocker_code


# ── Internal helpers ──────────────────────────────────────────────────────────


def _ensure_utc(value: datetime, *, field_name: str) -> datetime:
    """Reject tz-naive ``datetime`` (per §9 *no current-data fallback*)."""
    if not isinstance(value, datetime):  # defensive typing
        raise ReplayMetadataInputError(
            f"{field_name} must be a datetime, got {type(value).__name__}",
            blocker_code=_METADATA_INVALID_BLOCKER,
        )
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ReplayMetadataInputError(
            f"{field_name} must be timezone-aware (got tz-naive datetime)",
            blocker_code=_METADATA_INVALID_BLOCKER,
        )
    return value.astimezone(UTC)


def _require_non_blank_text(value: str, *, field_name: str, blocker_code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReplayMetadataInputError(
            f"{field_name} must be a non-blank string",
            blocker_code=blocker_code,
        )
    return value


def _compute_replay_audit_hash(
    *,
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
    source_role: str,
) -> str:
    """§6 — ``sha256_hex(node_signature_hash(config, node) || source_role)``.

    Mirrors :func:`replay_audit.write_replay_source_visibility_audit`'s
    per-row hash policy. ``||`` here is byte-string concatenation with
    no separator (matching the §6 contract literal).
    """
    node_hash = node_signature_hash(config, node)
    return sha256((node_hash + source_role).encode("utf-8")).hexdigest()


# ── Public writer entry point ────────────────────────────────────────────────


async def write_replay_metadata(
    *,
    session: AsyncSession,
    config: RollingBacktestConfig,
    rolling_node: RollingNodeDefinition,
    run_id: int,
    replay_executed_at: datetime,
    replay_identity: ReplayRunIdentity,
) -> HarvestStateRun:
    """§4 — write the five replay metadata columns onto the persisted run.

    Returns the same ORM ``HarvestStateRun`` instance after the in-place
    UPDATE has been staged on the session (via a single
    ``session.flush()``). The caller is responsible for committing the
    surrounding transaction; the writer's :class:`AsyncSession` flush
    call lets DB-side CHECK constraints surface immediately while the
    caller's commit boundary remains theirs.

    Algorithm (per §4):

    1. Validate *all* inputs at the writer boundary (no DB round-trip).
       Reject blank ``code_version`` with the
       ``REPLAY_RUNTIME_IDENTITY_MISSING`` blocker (§4.3).
       Reject blank ``run_correlation_id`` with the
       ``REPLAY_METADATA_INVALID`` blocker (§4.4).
       Reject tz-naive ``replay_executed_at`` /
       ``rolling_node.forecast_cutoff_at`` with
       ``REPLAY_METADATA_INVALID`` (§9 *no current-data fallback*).
    2. SELECT the ``harvest_state_run`` row by ``run_id``. If the row
       is missing, raise ``ReplayMetadataInputError`` with
       ``REPLAY_METADATA_INVALID`` — there is no row to update.
    3. If the row's ``is_replay`` is already ``TRUE``, raise
       :class:`ReplayMetadataConflictError` with the
       ``REPLAY_METADATA_INVALID`` blocker (§4.2 — UPDATE is *never*
       issued on rows whose ``is_replay`` is already ``TRUE``;
       idempotent replay re-runs produce *new* rows via a fresh
       ``execute_harvest_state_run`` call).
    4. Stamp the five metadata fields on the row.
    5. Emit one ``harvest_state_replay_source_visibility_audit`` row
       tagged with ``source_role = "task9_harvest_state_run_replay:
       <run_id>"`` (§4.5). The audit row's ``harvest_state_run_id``
       is set to ``run_id`` so readers can JOIN audit rows to the
       updated ``harvest_state_run`` via the FK already established by
       bucket #3.
    6. ``session.flush()`` once. Both rows are atomic with respect to
       the caller's transaction.

    The writer does not infer / default / fall-back any value: every
    per-row field is taken from a caller-supplied input or a column
    already populated on the ORM row.
    """
    # ── 1. Validate inputs FIRST (no DB round-trip) ──────────────────────
    if not isinstance(run_id, int) or run_id <= 0:
        raise ReplayMetadataInputError(
            f"run_id must be a positive integer (got {run_id!r})",
            blocker_code=_METADATA_INVALID_BLOCKER,
        )
    replay_executed_at_utc = _ensure_utc(replay_executed_at, field_name="replay_executed_at")
    forecast_effective_cutoff_at = _ensure_utc(
        rolling_node.forecast_cutoff_at,
        field_name="rolling_node.forecast_cutoff_at",
    )
    code_version = _require_non_blank_text(
        replay_identity.code_version,
        field_name="replay_identity.code_version",
        blocker_code=_RUNTIME_IDENTITY_MISSING_BLOCKER,
    )
    run_correlation_id = _require_non_blank_text(
        replay_identity.run_correlation_id,
        field_name="replay_identity.run_correlation_id",
        blocker_code=_METADATA_INVALID_BLOCKER,
    )

    # ── 2. Read the persisted run row ────────────────────────────────────
    result = await session.execute(select(HarvestStateRun).where(HarvestStateRun.id == run_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise ReplayMetadataInputError(
            f"no harvest_state_run row found for run_id={run_id}",
            blocker_code=_METADATA_INVALID_BLOCKER,
        )

    # ── 3. Enforce §4.2 — never UPDATE an already-replay row ─────────────
    if row.is_replay is True:
        raise ReplayMetadataConflictError(
            f"harvest_state_run id={run_id} has is_replay=TRUE; "
            "UPDATE is rejected per §4.2 (idempotent replay re-runs "
            "produce new rows via a fresh execute_harvest_state_run).",
            blocker_code=_METADATA_INVALID_BLOCKER,
        )

    # ── 4. Stamp the five fields onto the in-memory ORM row ──────────────
    row.is_replay = True
    row.forecast_effective_cutoff_at = forecast_effective_cutoff_at
    row.replay_executed_at = replay_executed_at_utc
    row.replay_code_version = code_version
    row.replay_run_correlation_id = run_correlation_id

    # ── 5. Emit the §4.5 audit row ────────────────────────────────────────
    source_role = _replay_audit_source_role(run_id)
    semantic_identity_hash = _compute_replay_audit_hash(
        config=config,
        node=rolling_node,
        source_role=source_role,
    )
    audit_row = HarvestStateReplaySourceVisibilityAuditModel(
        harvest_state_run_id=run_id,
        source_role=source_role,
        source_type=_REPLAY_AUDIT_SOURCE_TYPE,
        source_visibility_source="availability_audit",
        forecast_cutoff_at=forecast_effective_cutoff_at,
        visibility_passed=True,
        rejection_blocker_code=None,
        semantic_identity_hash=semantic_identity_hash,
    )
    session.add(audit_row)

    # ── 6. Single flush (per §4.1 — "follow-up transaction, no savepoint") ─
    await session.flush()

    return row


# ── Module exports ────────────────────────────────────────────────────────────

__all__ = (
    "METADATA_FIELD_SOURCES",
    "ReplayMetadataConflictError",
    "ReplayMetadataInputError",
    "ReplayRunIdentity",
    "write_replay_metadata",
)
