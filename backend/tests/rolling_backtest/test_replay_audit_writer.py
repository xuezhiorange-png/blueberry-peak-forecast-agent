"""Unit tests for Task 11 Phase 3.1 bucket #3 — replay source visibility audit writer.

Tests verify the writer at the audit-writer level only. They do not
implement or invoke any replay runner / dispatch / Task 9 service /
Task 10 binding logic; they use a fake AsyncSession that records what
the writer would have flushed, plus structural checks of the persisted
row shapes against the §6 contract.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from backend.app.rolling_backtest.enums import (
    AvailabilityBlockerCode,
    AvailabilitySourceType,
    ExecutionMode,
    UpstreamSelectionMode,
)
from backend.app.rolling_backtest.orchestration import OrchestrationBlocker
from backend.app.rolling_backtest.replay_audit import (
    _AUDIT_FIELD_SOURCES,
    ReplayAuditIncompleteError,
    ReplayAuditInputError,
    UpstreamVisibilityDecision,
    write_replay_source_visibility_audit,
)
from backend.app.rolling_backtest.schemas import (
    PersistentUpstreamReference,
    ResolvedUpstreamSemanticIdentity,
    RollingBacktestConfig,
    RollingNodeDefinition,
    UpstreamSemanticIdentityPayload,
)

# ── typed-input contract tests ────────────────────────────────────────────────


class _NoOpIdentity:
    """Stand-in for ResolvedUpstreamSemanticIdentity used by writer-only tests."""

    def __init__(self, source_type: AvailabilitySourceType, source_role: str) -> None:
        self.source_type = source_type
        self.source_role = source_role


def _identity(
    *,
    source_type: AvailabilitySourceType,
    source_role: str,
    role_qualifier: str | None = None,
) -> ResolvedUpstreamSemanticIdentity:
    """Build the smallest valid ResolvedUpstreamSemanticIdentity the writer accepts.

    The writer only consumes ``source_type`` and ``source_role`` from the
    identity (per §6 column sources). All other schema-required fields
    are populated with stable sentinel values sufficient to keep the
    Pydantic validator happy; they are not used by the writer.
    """
    return ResolvedUpstreamSemanticIdentity(
        source_type=source_type,
        source_role=source_role,
        role_qualifier=(
            role_qualifier
            if role_qualifier is not None
            else (source_role.split(":", 1)[1] if ":" in source_role else None)
        ),
        semantic=UpstreamSemanticIdentityPayload(
            schema_version="task11-replay-audit-test-v1",
            display_label=source_role,
            semantic_payload_hash="0" * 64,
            input_signature="1" * 64,
        ),
        persistent_reference=PersistentUpstreamReference(
            reference_type="uuid",
            reference_value="00000000-0000-0000-0000-000000000000",
        ),
    )


def _cutoff() -> Any:
    """§6 expects tz-aware datetime; sample value the audit writer accepts.

    Pick ``2026-03-15 04:00 UTC`` so local in Asia/Shanghai is
    ``2026-03-15 12:00 +08:00`` — which matches the test node's
    ``as_of_local_date=2026-03-15`` and the test config's
    ``cutoff_local_time=12:00:00`` (per the
    ``RollingBacktestConfig._validate_nodes_against_run_policy``
    cross-field check).
    """
    from datetime import UTC, datetime

    return datetime(2026, 3, 15, 4, 0, 0, tzinfo=UTC)


def _node(
    *,
    identities: tuple[ResolvedUpstreamSemanticIdentity, ...] = (),
) -> RollingNodeDefinition:
    """Build a fully-populated RollingNodeDefinition the writer accepts.

    Follows the construction pattern in
    ``backend/tests/rolling_backtest/test_signatures.py`` so
    :func:`node_signature_hash` works without touching real production
    data.
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
        resolved_upstream_semantic_identities=identities,
    )


def _config(nodes: tuple[RollingNodeDefinition, ...]) -> RollingBacktestConfig:
    """Build a fully-populated RollingBacktestConfig the writer accepts.

    Uses ``RollingBacktestConfig.model_validate`` so Pydantic constructs
    the typed config object; follows the pattern in
    ``test_signatures.py::_config``.
    """
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
            "nodes": [node.model_dump(mode="json") for node in nodes],
        }
    )


def _session_spy() -> AsyncMock:
    """AsyncSession double that records adds + flushes without a real DB."""
    session = AsyncMock()
    session.add = lambda obj: None  # type: ignore[method-assign]
    session.flush = AsyncMock(return_value=None)  # type: ignore[method-assign]
    return session


# ── §6 ¶4: empty input raises with REPLAY_AUDIT_INCOMPLETE ────────────────────


def test_writer_raises_replay_audit_incomplete_on_empty_input() -> None:
    """§6 ¶4 — zero rows ⇒ REPLAY_AUDIT_INCOMPLETE."""
    session = _session_spy()
    with pytest.raises(ReplayAuditIncompleteError) as exc_info:
        asyncio.run(
            write_replay_source_visibility_audit(
                session=session,
                harvest_state_run_id=42,
                node=_node(),
                config=_config((_node(),)),
                upstream_visibility=[],
            )
        )
    assert exc_info.value.blocker_code == OrchestrationBlocker.REPLAY_AUDIT_INCOMPLETE.value
    # session.flush() must NOT be called when input is empty (atomicity).
    session.flush.assert_not_called()


# ── §6 input contract — visibility_source enum ───────────────────────────────


def test_writer_rejects_blank_visibility_source() -> None:
    """§6 — visibility_source must be one of three documented strings."""
    with pytest.raises(ReplayAuditInputError):
        UpstreamVisibilityDecision(
            identity=_identity(
                source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
                source_role="task8_forecast_run:2099-03-01",
            ),
            visibility_source="",
            visibility_passed=True,
        )


def test_writer_rejects_unknown_visibility_source() -> None:
    """§6 — visibility_source must be one of three documented strings."""
    with pytest.raises(ReplayAuditInputError):
        UpstreamVisibilityDecision(
            identity=_identity(
                source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
                source_role="task8_forecast_run:2099-03-01",
            ),
            visibility_source="not_a_real_source",
            visibility_passed=True,
        )


def test_writer_accepts_each_documented_visibility_source() -> None:
    """§6 — all three documented visibility_source values are accepted."""
    for src in (
        "availability_audit",
        "task8_visibility_manifest",
        "task9_verification_snapshot",
    ):
        d = UpstreamVisibilityDecision(
            identity=_identity(
                source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
                source_role="task8_forecast_run:2099-03-01",
            ),
            visibility_source=src,
            visibility_passed=True,
        )
        assert d.visibility_source == src


# ── §6 input contract — passed-blocker coupling ───────────────────────────────


def test_writer_rejects_passed_true_with_blocker_code() -> None:
    """§6 — passed=True ⇒ blocker_code must be None."""
    with pytest.raises(ReplayAuditInputError):
        UpstreamVisibilityDecision(
            identity=_identity(
                source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
                source_role="task8_forecast_run:2099-03-01",
            ),
            visibility_source="availability_audit",
            visibility_passed=True,
            rejection_blocker_code=AvailabilityBlockerCode.MISSING_SOURCE_CUTOFF.value,
        )


def test_writer_rejects_passed_false_with_blank_blocker_code() -> None:
    """§6 — passed=False ⇒ blocker_code must be non-blank."""
    with pytest.raises(ReplayAuditInputError):
        UpstreamVisibilityDecision(
            identity=_identity(
                source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
                source_role="task8_forecast_run:2099-03-01",
            ),
            visibility_source="availability_audit",
            visibility_passed=False,
            rejection_blocker_code="",
        )


def test_writer_rejects_passed_false_with_unknown_blocker_code() -> None:
    """§6 — rejection_blocker_code must be one of AvailabilityBlockerCode values."""
    with pytest.raises(ReplayAuditInputError):
        UpstreamVisibilityDecision(
            identity=_identity(
                source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
                source_role="task8_forecast_run:2099-03-01",
            ),
            visibility_source="availability_audit",
            visibility_passed=False,
            rejection_blocker_code="not_a_known_code",
        )


def test_writer_accepts_each_known_availability_blocker_code() -> None:
    """§6 — every AvailabilityBlockerCode value is acceptable."""
    for blocker in AvailabilityBlockerCode:
        d = UpstreamVisibilityDecision(
            identity=_identity(
                source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
                source_role="task8_forecast_run:2099-03-01",
            ),
            visibility_source="availability_audit",
            visibility_passed=False,
            rejection_blocker_code=blocker.value,
        )
        assert d.rejection_blocker_code == blocker.value


# ── §6 ¶3: deterministic ordering ────────────────────────────────────────────


def test_writer_inserts_rows_in_lexicographic_source_role_order() -> None:
    """§6 ¶3 — rows written in lex order of source_role regardless of input order."""
    seen: list[Any] = []
    session = _session_spy()

    def _capture_add(obj: Any) -> None:
        seen.append(obj)

    session.add = _capture_add  # type: ignore[method-assign]

    # Input order is NOT lex sorted.
    decision1 = UpstreamVisibilityDecision(
        identity=_identity(
            source_type=AvailabilitySourceType.TASK10_MODEL_ARTIFACT,
            source_role="task10_model_artifact:99",
        ),
        visibility_source="availability_audit",
        visibility_passed=True,
    )
    decision2 = UpstreamVisibilityDecision(
        identity=_identity(
            source_type=AvailabilitySourceType.TASK8_DAILY_PREDICTION,
            source_role="task8_daily_prediction:2099-03-05",
        ),
        visibility_source="availability_audit",
        visibility_passed=True,
    )
    decision3 = UpstreamVisibilityDecision(
        identity=_identity(
            source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
            source_role="task8_forecast_run:2099-03-01",
        ),
        visibility_source="task8_visibility_manifest",
        visibility_passed=False,
        rejection_blocker_code=AvailabilityBlockerCode.OBSERVATION_DATE_AFTER_CUTOFF.value,
    )

    asyncio.run(
        write_replay_source_visibility_audit(
            session=session,
            harvest_state_run_id=101,
            node=_node(),
            config=_config((_node(),)),
            upstream_visibility=[decision1, decision2, decision3],
        )
    )

    # Expected lex order (ascending ASCII):
    # "task10_model_artifact:99"
    # "task8_daily_prediction:2099-03-05"
    # "task8_forecast_run:2099-03-01"
    actual_order = [r.source_role for r in seen]
    assert actual_order == sorted(
        [
            "task10_model_artifact:99",
            "task8_daily_prediction:2099-03-05",
            "task8_forecast_run:2099-03-01",
        ]
    )


# ── §6 column-source mapping ────────────────────────────────────────────────


def test_writer_does_not_set_captured_at_field() -> None:
    """§6 — captured_at is the DB server default; writer MUST NOT set it."""
    seen: list[Any] = []
    session = _session_spy()

    def _capture(obj: Any) -> None:
        seen.append(obj)

    session.add = _capture  # type: ignore[method-assign]

    node = _node()
    asyncio.run(
        write_replay_source_visibility_audit(
            session=session,
            harvest_state_run_id=202,
            node=node,
            config=_config((node,)),
            upstream_visibility=[
                UpstreamVisibilityDecision(
                    identity=_identity(
                        source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
                        source_role="task8_forecast_run:2099-03-01",
                    ),
                    visibility_source="availability_audit",
                    visibility_passed=True,
                )
            ],
        )
    )

    assert len(seen) == 1
    # Writer must NOT have populated captured_at — DB default fills it.
    # On the in-memory ORM object, an unset Column field is ``None``
    # (SQLAlchemy resolves it to the server default at INSERT time).
    captured_at_via_writer = getattr(seen[0], "captured_at", "WRITER-SET-THIS-VALUE")
    assert captured_at_via_writer is None, (
        f"writer must not set captured_at; got {captured_at_via_writer!r}"
    )


def test_writer_maps_every_section_six_field_to_correct_source() -> None:
    """§6 column-source mapping must be present and contain all expected columns."""
    expected_columns = {
        "harvest_state_run_id",
        "source_role",
        "source_type",
        "source_visibility_source",
        "forecast_cutoff_at",
        "visibility_passed",
        "rejection_blocker_code",
        "semantic_identity_hash",
        "captured_at",
    }
    seen_columns = {col for col, _src in _AUDIT_FIELD_SOURCES}
    assert seen_columns == expected_columns, (
        f"§6 column coverage mismatch: missing={expected_columns - seen_columns}, "
        f"extra={seen_columns - expected_columns}"
    )


def test_writer_passes_through_caller_supplied_fields_verbatim() -> None:
    """§6 — caller-provided fields flow through 1:1 to the ORM row."""
    seen: list[Any] = []
    session = _session_spy()

    def _capture(obj: Any) -> None:
        seen.append(obj)

    session.add = _capture  # type: ignore[method-assign]

    decision = UpstreamVisibilityDecision(
        identity=_identity(
            source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
            source_role="task8_forecast_run:2099-03-01",
        ),
        visibility_source="task9_verification_snapshot",
        visibility_passed=False,
        rejection_blocker_code=AvailabilityBlockerCode.SOURCE_VISIBILITY_MISSING.value,
    )

    asyncio.run(
        write_replay_source_visibility_audit(
            session=session,
            harvest_state_run_id=999,
            node=_node(),
            config=_config((_node(),)),
            upstream_visibility=[decision],
        )
    )

    assert len(seen) == 1
    row = seen[0]
    assert row.harvest_state_run_id == 999
    assert row.source_role == "task8_forecast_run:2099-03-01"
    assert row.source_type == AvailabilitySourceType.TASK8_FORECAST_RUN.value
    assert row.source_visibility_source == "task9_verification_snapshot"
    assert row.visibility_passed is False
    assert row.rejection_blocker_code == AvailabilityBlockerCode.SOURCE_VISIBILITY_MISSING.value
    assert row.forecast_cutoff_at == _node().forecast_cutoff_at


def test_writer_emits_semantic_identity_hash_per_row() -> None:
    """§6 — semantic_identity_hash is sha256(node_hash || source_role) per row."""
    seen: list[Any] = []
    session = _session_spy()

    def _capture(obj: Any) -> None:
        seen.append(obj)

    session.add = _capture  # type: ignore[method-assign]

    decisions = [
        UpstreamVisibilityDecision(
            identity=_identity(
                source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
                source_role=f"task8_forecast_run:2099-03-{day:02d}",
            ),
            visibility_source="availability_audit",
            visibility_passed=True,
        )
        for day in (1, 2)
    ]

    asyncio.run(
        write_replay_source_visibility_audit(
            session=session,
            harvest_state_run_id=1,
            node=_node(),
            config=_config((_node(),)),
            upstream_visibility=decisions,
        )
    )

    assert len(seen) == 2
    # Each row's hash is 64-char hex (SHA-256) and rows differ because source_role differs.
    hashes = [r.semantic_identity_hash for r in seen]
    assert all(len(h) == 64 and all(c in "0123456789abcdef" for c in h) for h in hashes)
    # Different source_role → different hash (lex ordering notwithstanding).
    assert hashes[0] != hashes[1]


def test_writer_rejects_naive_forecast_cutoff_at() -> None:
    """§6 — forecast_cutoff_at must be tz-aware."""
    from datetime import datetime

    # Build a fully-typed node, then bypass Pydantic's @field_validator
    # by using ``model_construct`` so the naive datetime is observable
    # at the writer layer. The writer itself is the unit under test; it
    # must reject naive cutoffs before any DB code runs.
    tz_node = _node()
    node = RollingNodeDefinition.model_construct(
        season_id=tz_node.season_id,
        node_key=tz_node.node_key,
        as_of_local_date=tz_node.as_of_local_date,
        forecast_cutoff_at=datetime(2026, 3, 15, 4, 0, 0),  # naive
        forecast_start_local_date=tz_node.forecast_start_local_date,
        forecast_end_local_date=tz_node.forecast_end_local_date,
        scope=tz_node.scope,
        upstream_selection_mode=tz_node.upstream_selection_mode,
        forecast_horizon_policy_version=tz_node.forecast_horizon_policy_version,
        timezone=tz_node.timezone,
        task10_model_policy=tz_node.task10_model_policy,
        resolved_upstream_semantic_identities=tz_node.resolved_upstream_semantic_identities,
    )
    session = _session_spy()

    with pytest.raises(ReplayAuditInputError):
        asyncio.run(
            write_replay_source_visibility_audit(
                session=session,
                harvest_state_run_id=1,
                node=node,
                config=_config((tz_node,)),
                upstream_visibility=[
                    UpstreamVisibilityDecision(
                        identity=_identity(
                            source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
                            source_role="task8_forecast_run:2099-03-01",
                        ),
                        visibility_source="availability_audit",
                        visibility_passed=True,
                    )
                ],
            )
        )


def test_writer_calls_session_flush_exactly_once_for_n_decisions() -> None:
    """Atomic per-call semantics: a single flush() regardless of N."""
    session = _session_spy()
    decisions = [
        UpstreamVisibilityDecision(
            identity=_identity(
                source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
                source_role=f"task8_forecast_run:2099-03-{day:02d}",
            ),
            visibility_source="availability_audit",
            visibility_passed=True,
        )
        for day in range(1, 11)
    ]
    asyncio.run(
        write_replay_source_visibility_audit(
            session=session,
            harvest_state_run_id=1,
            node=_node(),
            config=_config((_node(),)),
            upstream_visibility=decisions,
        )
    )
    # Per-writer contract: one flush for N rows (atomic).
    assert session.flush.await_count == 1
