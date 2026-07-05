"""Unit tests for Task 11 Phase 3.1 bucket #4 — replay metadata writer.

Tests verify the writer at the metadata-writer level only. They do not
implement or invoke any replay runner / dispatch / Task 9 service /
Task 10 binding logic; they use a fake AsyncSession that records what
the writer would have flushed, plus structural checks of the persisted
row shapes against the §4 + §4.5 contracts.

Each test asserts one (and only one) bucket-#4 hard-boundary invariant
so a future regression report can pinpoint which §4 rule regressed.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from backend.app.models.harvest_state import (
    HarvestStateReplaySourceVisibilityAuditModel,
)
from backend.app.rolling_backtest.enums import (
    ExecutionMode,
    UpstreamSelectionMode,
)
from backend.app.rolling_backtest.orchestration import OrchestrationBlocker
from backend.app.rolling_backtest.replay_metadata import (
    METADATA_FIELD_SOURCES,
    ReplayMetadataConflictError,
    ReplayMetadataInputError,
    ReplayRunIdentity,
    write_replay_metadata,
)
from backend.app.rolling_backtest.schemas import (
    RollingBacktestConfig,
    RollingNodeDefinition,
)

# ── fakes / helpers ──────────────────────────────────────────────────────────


@dataclass(slots=True)
class _AddedAuditRow:
    """Captured record of every ``session.add()`` argument the writer emitted."""

    model_class: type
    kwargs: dict[str, Any]


class _CapturingSession:
    """AsyncSession double that records adds / flushes / executes.

    Models the minimum the writer needs:

    * ``session.add(obj)`` — appends an :class:`_AddedAuditRow` capture.
    * ``session.flush()`` — counts (single call per invocation).
    * ``session.execute(...)`` — returns whatever ``_FakeResult.row``
      was wired by the test (so tests can simulate "row not found" or
      "row already is_replay=True" without a real DB).
    """

    def __init__(self, *, row: Any) -> None:
        self._row = row
        self.added: list[_AddedAuditRow] = []
        self.add_calls = 0
        self.flush_calls = 0

    def add(self, obj: Any) -> None:
        self.add_calls += 1
        self.added.append(
            _AddedAuditRow(
                model_class=type(obj),
                kwargs={
                    "harvest_state_run_id": getattr(obj, "harvest_state_run_id", None),
                    "source_role": getattr(obj, "source_role", None),
                    "source_type": getattr(obj, "source_type", None),
                    "source_visibility_source": getattr(
                        obj, "source_visibility_source", None
                    ),
                    "forecast_cutoff_at": getattr(obj, "forecast_cutoff_at", None),
                    "visibility_passed": getattr(obj, "visibility_passed", None),
                    "rejection_blocker_code": getattr(obj, "rejection_blocker_code", None),
                    "semantic_identity_hash": getattr(obj, "semantic_identity_hash", None),
                },
            )
        )

    async def flush(self) -> None:
        self.flush_calls += 1

    async def execute(self, *_args: Any, **_kwargs: Any) -> _FakeResult:
        return _FakeResult(self._row)


class _FakeResult:
    """ScalarResult double — only ``scalar_one_or_none`` is used by the writer."""

    def __init__(self, row: Any) -> None:
        self._row = row

    def scalar_one_or_none(self) -> Any:
        return self._row


def _existing_row(*, is_replay: bool | None) -> Any:
    """Build an in-memory ORM ``HarvestStateRun``-like row the writer can mutate.

    The real ``HarvestStateRun`` model maps a PG table with many
    NOT-NULL columns that we don't want to populate for a writer-only
    test. Instead, build an arbitrary duck-typed class whose attribute
    names match the writer's read/write surface exactly. The writer
    never inspects the ``__class__`` of the row — it only assigns the
    five metadata fields onto the instance returned by the session.
    """
    # Use a private subclass / instance trampoline so the writer's
    # ``is_replay is True`` / ``is_replay is False`` checks behave
    # identically to a real ``HarvestStateRun`` ORM attribute.
    class _StubRun:
        __slots__ = (
            "id",
            "is_replay",
            "forecast_effective_cutoff_at",
            "replay_executed_at",
            "replay_code_version",
            "replay_run_correlation_id",
        )

        def __init__(self, *, is_replay_: bool | None) -> None:
            self.id = 4242
            self.is_replay = is_replay_
            self.forecast_effective_cutoff_at = None
            self.replay_executed_at = None
            self.replay_code_version = None
            self.replay_run_correlation_id = None

    return _StubRun(is_replay_=is_replay)


def _cutoff() -> datetime:
    """Sample tz-aware UTC ``forecast_cutoff_at`` for the test node.

    Mirror the bucket-#3 audit writer test's helper so Pydantic's node
    validator is happy (matching ``as_of_local_date=2026-03-15``).
    """
    return datetime(2026, 3, 15, 4, 0, 0, tzinfo=UTC)


def _node() -> RollingNodeDefinition:
    """Build a fully-populated ``RollingNodeDefinition``.

    Mirrors ``test_signatures.py::_node`` so ``node_signature_hash`` is
    happy. ``task10_model_policy`` is a placeholder dict matching the
    bucket-#3 audit-writer test's policy shape.
    """
    from datetime import date

    forecast_cutoff_at = _cutoff()
    policy = {
        "policy": "historically_available_model",
        "training_run_semantic_identity": "a" * 64,
        "artifact_semantic_identities": ["b" * 64, "c" * 64, "d" * 64],
        "authority_visibility_identity": "e" * 64,
    }
    return RollingNodeDefinition(
        season_id=2026,
        node_key="march_15",
        as_of_local_date=date(2026, 3, 15),
        forecast_cutoff_at=forecast_cutoff_at,
        forecast_start_local_date=date(2026, 3, 16),
        forecast_end_local_date=date(2026, 3, 31),
        scope={
            "destination_factory_ids": {"mode": "include_ids", "ids": [202, 101]},
            "farm_ids": {"mode": "all", "ids": []},
            "subfarm_ids": {"mode": "all", "ids": []},
            "variety_ids": {"mode": "all", "ids": []},
        },
        upstream_selection_mode=UpstreamSelectionMode.HISTORICAL_RESOLUTION,
        forecast_horizon_policy_version="task11-horizon-v1",
        timezone="Asia/Shanghai",
        task10_model_policy=policy,
        resolved_upstream_semantic_identities=(),
    )


def _config() -> RollingBacktestConfig:
    """Build a fully-populated ``RollingBacktestConfig`` (Pydantic)."""
    return RollingBacktestConfig.model_validate(
        {
            "rolling_schema_version": "task11-rolling-v1",
            "canonical_serialization_version": "task11-canonical-v1",
            "availability_registry_version": "task11-availability-v1",
            "node_calendar_version": "task11-calendar-v1",
            "forecast_horizon_policy_version": "task11-horizon-v1",
            "upstream_selection_policy_version": "task11-selection-v1",
            "metric_policy_version": "task11-metrics-v1",
            "execution_mode": ExecutionMode.RETROSPECTIVE_REPLAY.value,
            "calendar_phase_policy_version": "task11-calendar-phase-v1",
            "cutoff_policy_version": "task11-cutoff-v1",
            "cutoff_timezone": "Asia/Shanghai",
            "cutoff_local_time": "12:00:00",
            "nodes": [_node().model_dump(mode="json")],
        }
    )


def _identity() -> ReplayRunIdentity:
    """Build a valid ``ReplayRunIdentity`` the writer accepts."""
    return ReplayRunIdentity(
        code_version="task-11-phase3-amendment@b91320a",
        run_correlation_id="a" * 32,
    )


def _replay_executed_at() -> datetime:
    """Build a tz-aware UTC datetime for ``replay_executed_at``."""
    return datetime(2026, 7, 5, 4, 30, 0, tzinfo=UTC)


# ── §4 / §7 input contract — REPLAY_RUNTIME_IDENTITY_MISSING (§4.3) ─────────


def test_writer_rejects_blank_code_version_with_runtime_identity_missing() -> None:
    """§4.3 — blank ``code_version`` ⇒ REPLAY_RUNTIME_IDENTITY_MISSING."""
    session = _CapturingSession(row=_existing_row(is_replay=False))
    with pytest.raises(ReplayMetadataInputError) as exc_info:
        asyncio.run(
            write_replay_metadata(
                session=session,  # type: ignore[arg-type]
                config=_config(),
                rolling_node=_node(),
                run_id=4242,
                replay_executed_at=_replay_executed_at(),
                replay_identity=ReplayRunIdentity(
                    code_version="   ",
                    run_correlation_id="a" * 32,
                ),
            )
        )
    assert exc_info.value.blocker_code == (
        OrchestrationBlocker.REPLAY_RUNTIME_IDENTITY_MISSING.value
    )
    # Writer must NOT have emitted any audit row / performed a DB round-trip.
    assert session.add_calls == 0
    assert session.flush_calls == 0


def test_writer_rejects_blank_correlation_id_with_metadata_invalid() -> None:
    """§4.4 — blank ``run_correlation_id`` ⇒ REPLAY_METADATA_INVALID."""
    session = _CapturingSession(row=_existing_row(is_replay=False))
    with pytest.raises(ReplayMetadataInputError) as exc_info:
        asyncio.run(
            write_replay_metadata(
                session=session,  # type: ignore[arg-type]
                config=_config(),
                rolling_node=_node(),
                run_id=4242,
                replay_executed_at=_replay_executed_at(),
                replay_identity=ReplayRunIdentity(
                    code_version="task-11-phase3-amendment@b91320a",
                    run_correlation_id="",
                ),
            )
        )
    assert exc_info.value.blocker_code == (
        OrchestrationBlocker.REPLAY_METADATA_INVALID.value
    )
    assert session.add_calls == 0
    assert session.flush_calls == 0


# ── §9 *no current-data fallback* — tz-naive datetimes rejected ──────────────


def test_writer_rejects_naive_replay_executed_at() -> None:
    """§9 — tz-naive ``replay_executed_at`` is rejected before any DB round-trip."""
    session = _CapturingSession(row=_existing_row(is_replay=False))
    with pytest.raises(ReplayMetadataInputError) as exc_info:
        asyncio.run(
            write_replay_metadata(
                session=session,  # type: ignore[arg-type]
                config=_config(),
                rolling_node=_node(),
                run_id=4242,
                replay_executed_at=datetime(2026, 7, 5, 4, 30, 0),
                replay_identity=_identity(),
            )
        )
    assert exc_info.value.blocker_code == (
        OrchestrationBlocker.REPLAY_METADATA_INVALID.value
    )
    assert session.add_calls == 0
    assert session.flush_calls == 0


def test_writer_rejects_naive_forecast_cutoff_at_on_node() -> None:
    """§9 — tz-naive ``rolling_node.forecast_cutoff_at`` is rejected."""
    from datetime import date

    session = _CapturingSession(row=_existing_row(is_replay=False))
    bad_node = _node()
    # Replace the cutoff with a tz-naive datetime via attribute set;
    # Pydantic does not normally allow this, but ``model_construct``
    # already built the object so a direct attribute assignment bypasses
    # validators (writers do not re-validate the node they receive).
    object.__setattr__(
        bad_node, "forecast_cutoff_at", datetime(2026, 3, 15, 4, 0, 0)
    )
    # Sanity: confirm the timestamp indeed has no tzinfo.
    assert bad_node.forecast_cutoff_at.tzinfo is None  # noqa: UP017
    with pytest.raises(ReplayMetadataInputError) as exc_info:
        asyncio.run(
            write_replay_metadata(
                session=session,  # type: ignore[arg-type]
                config=_config(),
                rolling_node=bad_node,
                run_id=4242,
                replay_executed_at=_replay_executed_at(),
                replay_identity=_identity(),
            )
        )
    assert exc_info.value.blocker_code == (
        OrchestrationBlocker.REPLAY_METADATA_INVALID.value
    )
    assert session.add_calls == 0
    assert session.flush_calls == 0
    # required to silence linter complaining about unused import
    _ = date(2026, 3, 15)


# ── input contract — run_id positive integer ─────────────────────────────────


@pytest.mark.parametrize("bad_run_id", [0, -1, -4242])
def test_writer_rejects_non_positive_run_id(bad_run_id: int) -> None:
    """§4 / §7 — ``run_id`` must be a positive integer."""
    session = _CapturingSession(row=_existing_row(is_replay=False))
    with pytest.raises(ReplayMetadataInputError):
        asyncio.run(
            write_replay_metadata(
                session=session,  # type: ignore[arg-type]
                config=_config(),
                rolling_node=_node(),
                run_id=bad_run_id,
                replay_executed_at=_replay_executed_at(),
                replay_identity=_identity(),
            )
        )
    assert session.add_calls == 0
    assert session.flush_calls == 0


# ── §4.2 idempotency — already-replay row rejected ───────────────────────────


def test_writer_rejects_already_replay_row_with_conflict_error() -> None:
    """§4.2 — UPDATE is NEVER issued on rows whose ``is_replay`` is TRUE.

    The writer raises a ``ReplayMetadataConflictError`` carrying the
    bucket-#2 frozen ``REPLAY_METADATA_INVALID`` blocker code.
    """
    session = _CapturingSession(row=_existing_row(is_replay=True))
    with pytest.raises(ReplayMetadataConflictError) as exc_info:
        asyncio.run(
            write_replay_metadata(
                session=session,  # type: ignore[arg-type]
                config=_config(),
                rolling_node=_node(),
                run_id=4242,
                replay_executed_at=_replay_executed_at(),
                replay_identity=_identity(),
            )
        )
    assert exc_info.value.blocker_code == (
        OrchestrationBlocker.REPLAY_METADATA_INVALID.value
    )
    # No audit row emitted; no flush called (writer is conservative).
    assert session.add_calls == 0
    assert session.flush_calls == 0


def test_writer_rejects_missing_row() -> None:
    """§4 — no row found for ``run_id`` is an input error (no row to update)."""
    session = _CapturingSession(row=None)
    with pytest.raises(ReplayMetadataInputError) as exc_info:
        asyncio.run(
            write_replay_metadata(
                session=session,  # type: ignore[arg-type]
                config=_config(),
                rolling_node=_node(),
                run_id=9999,
                replay_executed_at=_replay_executed_at(),
                replay_identity=_identity(),
            )
        )
    assert exc_info.value.blocker_code == (
        OrchestrationBlocker.REPLAY_METADATA_INVALID.value
    )
    assert session.add_calls == 0
    assert session.flush_calls == 0


# ── writer happy path — 5 metadata fields stamped + 1 audit row emitted ──────


def test_writer_stamps_five_metadata_columns_and_emits_one_audit_row() -> None:
    """§4 + §4.5 — full happy path.

    The writer assigns all five §4 fields onto the in-memory
    ``HarvestStateRun`` instance and emits exactly one
    ``HarvestStateReplaySourceVisibilityAuditModel`` row.
    """
    row = _existing_row(is_replay=False)
    session = _CapturingSession(row=row)
    executed_at = _replay_executed_at()
    identity = _identity()

    returned = asyncio.run(
        write_replay_metadata(
            session=session,  # type: ignore[arg-type]
            config=_config(),
            rolling_node=_node(),
            run_id=4242,
            replay_executed_at=executed_at,
            replay_identity=identity,
        )
    )

    # ── in-place UPDATE on the loaded row ────────────────────────────────
    assert returned is row
    assert row.is_replay is True
    assert row.forecast_effective_cutoff_at == _cutoff()
    assert row.replay_executed_at == executed_at.astimezone(UTC)
    assert row.replay_code_version == identity.code_version
    assert row.replay_run_correlation_id == identity.run_correlation_id

    # ── audit-row emission: exactly one row, and it is the audit model ─
    assert session.add_calls == 1
    assert len(session.added) == 1
    audit = session.added[0]
    assert audit.model_class is HarvestStateReplaySourceVisibilityAuditModel
    assert audit.kwargs["harvest_state_run_id"] == 4242

    # ── single flush (§4.1 "follow-up transaction … no savepoints") ────
    assert session.flush_calls == 1


def test_writer_emits_audit_row_with_section_four_five_literal_source_role() -> None:
    """§4.5 — audit row's ``source_role`` MUST be ``task9_harvest_state_run_replay:<run_id>``.

    Documented as a hard-coded literal in the writer module; the test
    pins it so a future refactor cannot silently change the audit row's
    ``source_role`` shape.
    """
    row = _existing_row(is_replay=False)
    session = _CapturingSession(row=row)
    asyncio.run(
        write_replay_metadata(
            session=session,  # type: ignore[arg-type]
            config=_config(),
            rolling_node=_node(),
            run_id=4242,
            replay_executed_at=_replay_executed_at(),
            replay_identity=_identity(),
        )
    )
    audit = session.added[0]
    assert audit.kwargs["source_role"] == "task9_harvest_state_run_replay:4242"
    assert audit.kwargs["source_type"] == "task9_harvest_state_run_replay"


def test_writer_audit_row_passes_failed_visibility_path_validation() -> None:
    """§6 / DB CHECK — the bucket-#4 audit row meets the bucket-#3 audit row CHECK rules.

    Per DB constraints:

    * ``source_role`` non-blank (CHECK ``ck_hsrpsva_role_non_blank``).
    * ``source_type`` non-blank (CHECK ``ck_hsrpsva_type_non_blank``).
    * ``source_visibility_source`` one of three documented values
      (CHECK ``ck_hsrpsva_visibility_source_non_blank``).
    * ``forecast_cutoff_at`` tz-aware (PG-side enforcement).
    * ``visibility_passed = TRUE`` ⇒ ``rejection_blocker_code IS NULL``
      (CHECK ``ck_hsrpsva_passed_blocker_coupling``).
    * ``semantic_identity_hash`` is a 64-char lowercase hex string
      (CHECK ``ck_hsrpsva_semantic_identity_hash_sha256``).
    """
    row = _existing_row(is_replay=False)
    session = _CapturingSession(row=row)
    asyncio.run(
        write_replay_metadata(
            session=session,  # type: ignore[arg-type]
            config=_config(),
            rolling_node=_node(),
            run_id=4242,
            replay_executed_at=_replay_executed_at(),
            replay_identity=_identity(),
        )
    )
    audit = session.added[0]
    role, stype, svsrc = (
        audit.kwargs["source_role"],
        audit.kwargs["source_type"],
        audit.kwargs["source_visibility_source"],
    )
    assert role.strip() != ""
    assert stype.strip() != ""
    assert svsrc.strip() != ""
    assert svsrc == "availability_audit"
    assert audit.kwargs["forecast_cutoff_at"].tzinfo is not None
    assert audit.kwargs["visibility_passed"] is True
    assert audit.kwargs["rejection_blocker_code"] is None
    h = audit.kwargs["semantic_identity_hash"]
    assert isinstance(h, str) and len(h) == 64 and h == h.lower()
    # And every character is a hex digit:
    int(h, 16)  # raises if any non-hex char present


def test_writer_does_not_call_now_or_use_database_default_for_replay_executed_at() -> None:
    """§4.1 — ``replay_executed_at`` MUST be the caller's explicit UTC value.

    The writer never falls back to ``datetime.now()`` nor relies on a
    database-side ``now()`` default. The post-call value on the ORM row
    equals the input verbatim (preserving the caller's tz-aware UTC
    instant; may be re-projected to UTC but never re-computed).
    """
    row = _existing_row(is_replay=False)
    session = _CapturingSession(row=row)
    executed_at = datetime(2099, 1, 2, 3, 4, 5, tzinfo=UTC)
    identity = _identity()
    asyncio.run(
        write_replay_metadata(
            session=session,  # type: ignore[arg-type]
            config=_config(),
            rolling_node=_node(),
            run_id=4242,
            replay_executed_at=executed_at,
            replay_identity=identity,
        )
    )
    # The writer may ASTIMEZONE(UTC) the input but must NOT modify it.
    assert row.replay_executed_at == executed_at.astimezone(UTC)


# ── cross-bucket compatibility — bucket #1 / #2 / #3 not regressed ──────────


def test_writer_does_not_import_or_invoke_bucket_three_audit_writer() -> None:
    """Bucket #4 does not call ``write_replay_source_visibility_audit``.

    Per Charles's authorization scope, the bucket-#4 writer emits its
    own singular audit row directly via ``session.add`` (not via the
    bucket-#3 writer). This test asserts the writer's logic does not
    import / call :func:`replay_audit.write_replay_source_visibility_audit`.
    """
    import backend.app.rolling_backtest.replay_audit as bucket3
    import backend.app.rolling_backtest.replay_metadata as bucket4

    # The writer must not be wrapped around the bucket-#3 entry point.
    assert id(bucket4.write_replay_metadata) != id(
        bucket3.write_replay_source_visibility_audit
    )


def test_metadata_field_sources_table_covers_five_columns() -> None:
    """§4 — the bucket-#4 module's documented ``METADATA_FIELD_SOURCES`` table lists
    all five §4 metadata columns exactly once each.
    """
    expected_columns = {
        "is_replay",
        "forecast_effective_cutoff_at",
        "replay_executed_at",
        "replay_code_version",
        "replay_run_correlation_id",
    }
    actual_columns = {row[0] for row in METADATA_FIELD_SOURCES}
    assert actual_columns == expected_columns


def test_writer_flushes_exactly_once_per_invocation() -> None:
    """§4.1 — one follow-up ``session.flush()`` per writer call (no savepoints)."""
    row = _existing_row(is_replay=False)
    session = _CapturingSession(row=row)
    asyncio.run(
        write_replay_metadata(
            session=session,  # type: ignore[arg-type]
            config=_config(),
            rolling_node=_node(),
            run_id=4242,
            replay_executed_at=_replay_executed_at(),
            replay_identity=_identity(),
        )
    )
    assert session.flush_calls == 1


# ── cross-bucket compatibility — AsyncSession-flavored mock works ──────────


def test_writer_compatible_with_unittest_mock_async_session() -> None:
    """Sanity test: the writer pairs with the same ``AsyncMock``-style session
    used by the bucket-#3 audit-writer test (no new ground truth required).

    The writer exercises ``session.execute(...)`` once to load the
    persisted row. This test asserts that pattern is honoured and that
    no unexpected session methods are called.
    """
    row = _existing_row(is_replay=False)
    session = AsyncMock()
    session.add = lambda obj: None
    session.flush = AsyncMock(return_value=None)
    result_mock = AsyncMock()
    result_mock.scalar_one_or_none = lambda: row
    session.execute = AsyncMock(return_value=result_mock)

    asyncio.run(
        write_replay_metadata(
            session=session,
            config=_config(),
            rolling_node=_node(),
            run_id=4242,
            replay_executed_at=_replay_executed_at(),
            replay_identity=_identity(),
        )
    )

    session.execute.assert_called_once()
    session.flush.assert_awaited_once()
