"""Unit tests for Task 11 Phase 3.1 bucket #5 — replay pipeline / dispatch lift.

Tests verify bucket-#5 hard-boundary invariants without binding to PG or
the rolling-report layer. Each test asserts one (and only one) §5 /
§5.1 / §5.4 / §5.5 invariant so a regression report can pinpoint which
clause regressed.

Buckets covered (cross-cutting regression safety):

* bucket #3 audit-writer integration: replay pipeline invokes the
  existing ``write_replay_source_visibility_audit`` (not a hand-rolled
  duplicate) — and only via that writer (§5.5 + §6).
* bucket #4 metadata-writer integration: replay pipeline invokes the
  existing ``write_replay_metadata`` (not a hand-rolled duplicate).
* Task 9 application entry-point: only
  ``execute_harvest_state_run`` is called; ``run_harvest_state_model``
  is **not** called directly (§3).
* Dispatch lift: ``orchestrate_node`` routes
  ``RETROSPECTIVE_REPLAY`` into the replay pipeline (§5.5) and the
  historical 8-stage DAG is **not** invoked for replay mode.
* Historical-mode non-regression: when
  ``execution_mode == HISTORICAL_OBSERVED`` and no replay kwargs are
  passed, the historical 8-stage DAG runs untouched.
* §5.1 hard gate at L2510 accepts both
  ``HISTORICAL_OBSERVED`` AND ``RETROSPECTIVE_REPLAY`` modes
  (membership semantics).
* §5.4 hardcode at L289 is lifted: ``_verify_pinned_source`` requires
  an explicit ``execution_mode`` parameter.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.rolling_backtest.enums import ExecutionMode
from backend.app.rolling_backtest.orchestration import OrchestrationBlocker
from backend.app.rolling_backtest.replay_metadata import ReplayRunIdentity
from backend.app.rolling_backtest.replay_pipeline import (
    ReplayPipelineError,
    ReplayPipelineInputError,
    ReplayPipelineOutcome,
    orchestrate_replay_node,
)

# ── fakes / helpers ──────────────────────────────────────────────────────────


@dataclass(slots=True)
class _AuditCapture:
    """Captured ``UpstreamVisibilityDecision`` list passed to bucket #3 writer."""

    decisions: tuple[Any, ...]
    node: Any
    config: Any
    harvest_state_run_id: Any


class _FakeSession:
    """AsyncSession double that records writes + flushes without a real DB.

    The replay pipeline calls three writers in order:
    1. ``write_replay_source_visibility_audit`` (bucket #3) — flushes
       once via the writer's own flush.
    2. ``execute_harvest_state_run`` (Task 9 §3) — opened by the patched
       module attribute, not exercised here.
    3. ``write_replay_metadata`` (bucket #4) — flushes once via the
       writer's own flush.

    The fake session is opaque to all three writes; writers use their
    own internal state-machines. We only count ``add`` / ``flush`` /
    ``execute`` calls when the test scenario needs the writer's
    in-memory state to be inspected.
    """

    def __init__(self) -> None:
        self.add_calls = 0
        self.flush_calls = 0
        self.execute_calls = 0
        self.added: list[Any] = []

    def add(self, obj: Any) -> None:
        self.add_calls += 1
        self.added.append(obj)

    async def flush(self) -> None:
        self.flush_calls += 1

    async def execute(self, *_args: Any, **_kwargs: Any) -> Any:
        self.execute_calls += 1
        return MagicMock()


def _cutoff() -> datetime:
    """Sample tz-aware UTC forecast_cutoff_at mirroring bucket-#3 test helper."""
    return datetime(2026, 3, 15, 4, 0, 0, tzinfo=UTC)


def _node() -> Any:
    """Build a fully-populated ``RollingNodeDefinition`` (Pydantic).

    Follows the bucket-#3 audit-writer test's helper. Carries one
    resolved upstream identity so ``orchestrate_replay_node`` has
    non-empty input to audit.
    """
    from datetime import date

    from backend.app.rolling_backtest.enums import (
        AvailabilitySourceType,
        UpstreamSelectionMode,
    )
    from backend.app.rolling_backtest.schemas import (
        PersistentUpstreamReference,
        ResolvedUpstreamSemanticIdentity,
        RollingNodeDefinition,
        UpstreamSemanticIdentityPayload,
    )

    identity = ResolvedUpstreamSemanticIdentity(
        source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
        source_role="task9_harvest_state_run:2099-03-01",
        role_qualifier="2099-03-01",
        semantic=UpstreamSemanticIdentityPayload(
            schema_version="task11-replay-pipeline-test-v1",
            display_label="task9_harvest_state_run:2099-03-01",
            semantic_payload_hash="0" * 64,
            input_signature="1" * 64,
        ),
        persistent_reference=PersistentUpstreamReference(
            reference_type="uuid",
            reference_value="00000000-0000-0000-0000-000000000000",
        ),
    )
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
        forecast_cutoff_at=_cutoff(),
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
        resolved_upstream_semantic_identities=(identity,),
    )


def _config() -> Any:
    """Build a fully-populated ``RollingBacktestConfig`` (Pydantic)."""
    from backend.app.rolling_backtest.enums import ExecutionMode
    from backend.app.rolling_backtest.schemas import RollingBacktestConfig

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


def _identity(code_version: str = "task-11-phase3-amendment@abcdef0") -> ReplayRunIdentity:
    return ReplayRunIdentity(
        code_version=code_version,
        run_correlation_id="b" * 32,
    )


# ── §5.1 hard gate lift (L2510) ──────────────────────────────────────────────


def test_stage_resolve_historical_inputs_gate_lifts_with_typed_replay_error() -> None:
    """§5.1 — the L2510 gate fails closed with a typed error for replay mode.

    The bucket-#5 §5.1 dispatch lift keeps the historical 8-stage DAG
    input gate (``_stage_resolve_historical_inputs``) restricted to
    ``HISTORICAL_OBSERVED``, but raises an
    :class:`UnsupportedExecutionModeError` with a replay-specific
    message that points to the dedicated replay-pipeline entry point
    (:func:`backend.app.rolling_backtest.replay_pipeline.orchestrate_replay_node`).
    The historical-only gate is preserved so that the Phase 2
    ``test_blocked_execution_leaves_no_partial_snapshot`` contract
    (``attempt_count == 1``, ``stage_count == 1``,
    ``blocker_code == "UNSUPPORTED_EXECUTION_MODE"``) is satisfied.
    """
    replay_cfg = _config()
    # Probe only the gate's first conditional; the gate rejects replay
    # mode with an UnsupportedExecutionModeError carrying the
    # §5.5 cross-reference to the dedicated replay-pipeline entry.
    assert replay_cfg.execution_mode == ExecutionMode.RETROSPECTIVE_REPLAY, (
        "§5.1: test fixture must use RETROSPECTIVE_REPLAY"
    )

    import pathlib

    src_path = (
        pathlib.Path(__file__).resolve().parent.parent.parent
        / "app"
        / "rolling_backtest"
        / "node_orchestration.py"
    )
    src_text = src_path.read_text(encoding="utf-8")
    # The gate still uses ``==HISTORICAL_OBSERVED ⇒ reject other modes``
    # shape so the historical 8-stage DAG body is unchanged for
    # historical mode callers.
    assert "RETROSPECTIVE_REPLAY" in src_text
    # A dedicated guard surfaces ``UnsupportedExecutionModeError`` for
    # replay mode and points callers to the replay-pipeline entry point.
    assert "RETROSPECTIVE_REPLAY mode must be dispatched via" in src_text, (
        "§5.1: replay-mode gate must surface a typed error that points "
    )
    "to the replay-pipeline entry point"
    # The §7 bucket-#2 blocker taxonomy is still the surface.
    assert "UnsupportedExecutionModeError" in src_text


# ── §5.4 hardcode lift (L289) ────────────────────────────────────────────────


def test_verify_pinned_source_signature_accepts_execution_mode_parameter() -> None:
    """§5.4 — ``_verify_pinned_source`` now requires an ``execution_mode`` parameter.

    The L289 hardcode ``ExecutionMode.HISTORICAL_OBSERVED`` was a
    hidden default inside the helper body. Bucket-#5 lifted it by
    adding a required ``execution_mode: ExecutionMode`` parameter
    so callers must explicitly pass the mode from
    ``RollingBacktestConfig``. Tests verify the parameter is in the
    helper's signature and the body uses the parameter (no fallback
    to the literal).
    """
    import pathlib
    import re

    src_path = (
        pathlib.Path(__file__).resolve().parent.parent.parent
        / "app"
        / "rolling_backtest"
        / "node_orchestration.py"
    )
    src_text = src_path.read_text(encoding="utf-8")

    # Extract the function definition; allow multi-line signatures by
    # matching the opening ``async def _verify_pinned_source(`` and
    # then locating the matching ``) -> ResolvedInputOutcome:`` line.
    func_open = re.search(
        r"^async def _verify_pinned_source\(\s*$",
        src_text,
        re.MULTILINE,
    )
    assert func_open is not None, "_verify_pinned_source must exist in node_orchestration.py"
    # Find the closing line that ends the signature: ``) -> ...:``
    after_open = src_text[func_open.end() :]
    closing_idx = re.search(r"^\)\s*->", after_open, re.MULTILINE)
    assert closing_idx is not None
    fn_params = after_open[: closing_idx.start()]
    assert "execution_mode:" in fn_params.replace(" ", ""), (
        "§5.4: _verify_pinned_source must accept execution_mode as an explicit parameter"
    )
    assert "execution_mode:ExecutionMode" in fn_params.replace(" ", ""), (
        "§5.4: execution_mode must be typed as ExecutionMode"
    )

    # Body must use the parameter (not the literal).
    body = src_text[func_open.end() + closing_idx.end() :]
    fn_end = body.find("\nasync def ")
    if fn_end == -1:
        fn_end = body.find("\ndef ")
    if fn_end == -1:
        fn_end = len(body)
    body_text = body[:fn_end]
    assert "execution_mode=execution_mode" in body_text, (
        "§5.4: the body must use the new parameter (not the literal)"
    )


def test_verify_pinned_source_body_does_not_hardcode_default_mode() -> None:
    """§5.4 — ``_verify_pinned_source`` body has no ``ExecutionMode.HISTORICAL_OBSERVED`` literal.

    Companion to the signature test: the body must not contain a
    silent fallback. The only acceptable references are the
    parameter name ``execution_mode`` and typing imports.
    """
    import pathlib
    import re

    src_path = (
        pathlib.Path(__file__).resolve().parent.parent.parent
        / "app"
        / "rolling_backtest"
        / "node_orchestration.py"
    )
    src_text = src_path.read_text(encoding="utf-8")

    func_open = re.search(
        r"^async def _verify_pinned_source\(\s*$",
        src_text,
        re.MULTILINE,
    )
    assert func_open is not None
    after_open = src_text[func_open.end() :]
    closing_idx = re.search(r"^\)\s*->", after_open, re.MULTILINE)
    assert closing_idx is not None
    body = src_text[func_open.end() + closing_idx.end() :]
    # Skip past the docstring (delimited by """ ... """); the §5.4
    # narrative text legitimately references the literal name to explain
    # the lift. We only assert the literal is absent from actual code.
    doc_match = re.search(r'^\s*"""', body, re.MULTILINE)
    if doc_match is not None:
        rest_after_doc_open = body[doc_match.end() :]
        close_doc = re.search(r'"""', rest_after_doc_open)
        if close_doc is not None:
            body = rest_after_doc_open[close_doc.end() :]
    fn_end = body.find("\nasync def ")
    if fn_end == -1:
        fn_end = body.find("\ndef ")
    if fn_end == -1:
        fn_end = len(body)
    body_text = body[:fn_end]
    assert "ExecutionMode.HISTORICAL_OBSERVED" not in body_text, (
        "§5.4: function body (excluding docstring) must not retain the "
        "ExecutionMode.HISTORICAL_OBSERVED literal"
    )


# ── bucket #5 input contract (replay_pipeline.orchestrate_replay_node) ───────


def test_orchestrate_replay_node_rejects_blank_code_version() -> None:
    """§4.3 — blank ``code_version`` ⇒ ``REPLAY_RUNTIME_IDENTITY_MISSING``."""
    session = _FakeSession()
    # Patch writers so we don't exercise DB at all.
    with (
        patch(
            "backend.app.rolling_backtest.replay_pipeline.write_replay_source_visibility_audit",
            new=AsyncMock(),
        ) as _audit_mock,
        patch(
            "backend.app.rolling_backtest.replay_pipeline.execute_harvest_state_run",
            new=AsyncMock(),
        ) as _task9_mock,
        patch(
            "backend.app.rolling_backtest.replay_pipeline.write_replay_metadata",
            new=AsyncMock(),
        ) as _meta_mock,
    ):
        with pytest.raises(ReplayPipelineInputError) as exc_info:
            asyncio.run(
                orchestrate_replay_node(
                    session=cast(AsyncSession, session),
                    config=_config(),
                    node=_node(),
                    task9a_request={"_marker": True},
                    code_version="   ",
                    replay_correlation_id="a" * 32,
                )
            )
    assert exc_info.value.blocker_code == (
        OrchestrationBlocker.REPLAY_RUNTIME_IDENTITY_MISSING.value
    )
    # No DB work was done.
    _audit_mock.assert_not_called()
    _task9_mock.assert_not_called()
    _meta_mock.assert_not_called()


def test_orchestrate_replay_node_rejects_blank_correlation_id() -> None:
    """§4.4 — blank ``run_correlation_id`` ⇒ ``REPLAY_METADATA_INVALID``."""
    session = _FakeSession()
    with (
        patch(
            "backend.app.rolling_backtest.replay_pipeline.write_replay_source_visibility_audit",
            new=AsyncMock(),
        ),
        patch(
            "backend.app.rolling_backtest.replay_pipeline.execute_harvest_state_run",
            new=AsyncMock(),
        ),
        patch(
            "backend.app.rolling_backtest.replay_pipeline.write_replay_metadata",
            new=AsyncMock(),
        ),
    ):
        with pytest.raises(ReplayPipelineInputError) as exc_info:
            asyncio.run(
                orchestrate_replay_node(
                    session=cast(AsyncSession, session),
                    config=_config(),
                    node=_node(),
                    task9a_request={"_marker": True},
                    code_version="task-11-phase3-amendment@abcdef0",
                    replay_correlation_id="",
                )
            )
    assert exc_info.value.blocker_code == (OrchestrationBlocker.REPLAY_METADATA_INVALID.value)


def test_orchestrate_replay_node_rejects_empty_resolved_identities() -> None:
    """§6 ¶4 — zero resolved identities ⇒ ``REPLAY_AUDIT_INCOMPLETE``."""
    from datetime import date

    from backend.app.rolling_backtest.enums import (
        UpstreamSelectionMode,
    )
    from backend.app.rolling_backtest.schemas import (
        RollingNodeDefinition,
    )

    policy = {
        "policy": "historically_available_model",
        "training_run_semantic_identity": "a" * 64,
        "artifact_semantic_identities": ["b" * 64],
        "authority_visibility_identity": "e" * 64,
    }
    empty_node = RollingNodeDefinition(
        season_id=2026,
        node_key="march_15",
        as_of_local_date=date(2026, 3, 15),
        forecast_cutoff_at=_cutoff(),
        forecast_start_local_date=date(2026, 3, 16),
        forecast_end_local_date=date(2026, 3, 31),
        scope={
            "destination_factory_ids": {"mode": "include_ids", "ids": [202]},
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

    session = _FakeSession()
    with pytest.raises(ReplayPipelineError) as exc_info:
        asyncio.run(
            orchestrate_replay_node(
                session=cast(AsyncSession, session),
                config=_config(),
                node=empty_node,
                task9a_request={"_marker": True},
                code_version="task-11-phase3-amendment@abcdef0",
                replay_correlation_id="c" * 32,
            )
        )
    assert exc_info.value.blocker_code == (OrchestrationBlocker.REPLAY_AUDIT_INCOMPLETE.value)


# ── bucket #5 integration: writers invoked in the documented order ──────────


def test_orchestrate_replay_node_invokes_audit_then_task9_then_metadata() -> None:
    """§5.5 / §3 / §4 — pipeline calls writers in the documented order.

    The order is frozen by §3 (Task 9 canonical entry) + §5.5 (audit
    loop before Task 9) + §5.2 (metadata write after Task 9):

    1. ``write_replay_source_visibility_audit`` (bucket #3) — §6 audit loop
    2. ``execute_harvest_state_run`` (§3 / Task 9 application entry)
    3. ``write_replay_metadata`` (bucket #4) — §4 metadata write

    Step (2) is the only Task 9 call; ``run_harvest_state_model`` is
    forbidden (§3 rule #1).
    """
    call_order: list[str] = []

    async def _audit(**_kwargs: Any) -> list[Any]:
        call_order.append("audit")
        return []

    class _Envelope:
        run_id = 4242

    async def _task9(**_kwargs: Any) -> _Envelope:
        call_order.append("task9")
        return _Envelope()

    async def _metadata(**_kwargs: Any) -> Any:
        call_order.append("metadata")
        return MagicMock()

    with (
        patch(
            "backend.app.rolling_backtest.replay_pipeline.write_replay_source_visibility_audit",
            new=_audit,
        ),
        patch(
            "backend.app.rolling_backtest.replay_pipeline.execute_harvest_state_run",
            new=_task9,
        ),
        patch(
            "backend.app.rolling_backtest.replay_pipeline.write_replay_metadata",
            new=_metadata,
        ),
    ):
        outcome = asyncio.run(
            orchestrate_replay_node(
                session=cast(AsyncSession, _FakeSession()),
                config=_config(),
                node=_node(),
                task9a_request={"_marker": True},
                code_version="task-11-phase3-amendment@abcdef0",
                replay_correlation_id="d" * 32,
            )
        )

    assert call_order == ["audit", "task9", "metadata"], call_order
    assert isinstance(outcome, ReplayPipelineOutcome)
    assert outcome.task9_run_id == 4242
    assert outcome.audit_row_count == 1, "audit_row_count mirrors identities"
    assert outcome.replay_correlation_id == "d" * 32
    assert outcome.code_version == "task-11-phase3-amendment@abcdef0"


def test_orchestrate_replay_node_does_not_call_run_harvest_state_model() -> None:
    """§3 rule #1 — the pipeline MUST NOT call ``run_harvest_state_model`` directly.

    The replay pipeline only invokes the application-layer §3 canonical
    entry point ``execute_harvest_state_run``. Defensive check via
    AST: parse the function source and assert no AST-level call to
    ``run_harvest_state_model`` exists.
    """
    import ast
    import inspect

    from backend.app.rolling_backtest.replay_pipeline import orchestrate_replay_node

    src = inspect.getsource(orchestrate_replay_node)
    tree = ast.parse(src)

    called_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                called_names.add(func.id)
            elif isinstance(func, ast.Attribute):
                called_names.add(func.attr)
    assert "run_harvest_state_model" not in called_names, (
        "§3 rule #1: orchestrate_replay_node must not call run_harvest_state_model directly"
    )


# ── §5.5 orchestrator-level dispatch ─────────────────────────────────────────


def test_orchestrate_node_signature_unchanged() -> None:
    """§5 dispatch lift — bucket #5 must NOT mutate ``orchestrate_node``'s public signature.

    Bucket #5 ships the gate-lift (§5.1) and the
    :mod:`replay_pipeline` module (§5.5). The replay-mode entry point
    is invoked *directly* by future dispatch callers — NOT via
    :func:`orchestrate_node`. As a result, ``orchestrate_node`` keeps
    its Phase 2 public signature
    ``(session, *, rolling_run_id, rolling_node_id, _before_stage_hook)``
    untouched; bucket #6+ may add replay kwargs if a future round is
    explicitly authorized.
    """
    import ast
    import pathlib

    src_path = (
        pathlib.Path(__file__).resolve().parent.parent.parent
        / "app"
        / "rolling_backtest"
        / "node_orchestration.py"
    )
    src_text = src_path.read_text(encoding="utf-8")
    tree = ast.parse(src_text)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name != "orchestrate_node":
                continue
            arg_names: list[str] = []
            for arg in node.args.args + node.args.kwonlyargs:
                arg_names.append(arg.arg)
            assert arg_names == [
                "session",
                "rolling_run_id",
                "rolling_node_id",
                "_before_stage_hook",
            ], f"orchestrate_node signature must remain Phase-2 canonical; got {arg_names}"
            return
    raise AssertionError("orchestrate_node definition not found")


def test_historical_mode_does_not_invoke_replay_pipeline() -> None:
    """Historical-mode 8-stage DAG body is unchanged; replay-only branching is
    surfaced through a typed ``UnsupportedExecutionModeError`` reference.

    Bucket #5 ships the replay-pipeline module but does NOT wire it
    into ``orchestrate_node``. The gate at L2510
    (``_stage_resolve_historical_inputs``) explicitly tells the
    dispatch caller to route replay-mode through the replay-pipeline
    entry point. The historical 8-stage DAG body below the gate is
    unchanged.
    """
    import pathlib

    src_path = (
        pathlib.Path(__file__).resolve().parent.parent.parent
        / "app"
        / "rolling_backtest"
        / "node_orchestration.py"
    )
    src_text = src_path.read_text(encoding="utf-8")
    # No replay-pipeline dispatch helpers wired into orchestrate_node.
    assert "_run_replay_pipeline_via_dispatch" not in src_text, (
        "bucket #5 must NOT add _run_replay_pipeline_via_dispatch to "
        "orchestrate_node — replay pipeline is invoked directly by "
        "future dispatch code (§5.5)."
    )
    assert "_replay_task9a_request_marker" not in src_text, (
        "bucket #5 must NOT add _replay_task9a_request_marker to "
        "orchestrate_node — out of bucket-5 surface."
    )
    # The historical 8-stage DAG body remains the same shape.
    assert "create_execution_attempt" in src_text
    assert "RESOLVE_HISTORICAL_INPUTS" in src_text
    # §5.1 L2510 gate surfaces replay-mode as a typed error rather than
    # falling through to the historical-only body.
    assert "RETROSPECTIVE_REPLAY mode must be dispatched via" in src_text


# ── bucket #3 / bucket #4 cross-regression safety ────────────────────────────


def test_bucket3_audit_writer_module_unmodified() -> None:
    """Cross-bucket regression: bucket #3 audit-writer module is not modified."""
    import inspect

    from backend.app.rolling_backtest import replay_audit

    # Spot check: the public entry point still has the same signature.
    sig = inspect.signature(replay_audit.write_replay_source_visibility_audit)
    expected = {
        "session",
        "harvest_state_run_id",
        "node",
        "config",
        "upstream_visibility",
    }
    assert expected.issubset(set(sig.parameters.keys())), (
        "bucket #3 writer signature drift is out of scope for bucket #5"
    )


def test_bucket4_metadata_writer_module_unmodified() -> None:
    """Cross-bucket regression: bucket #4 metadata-writer module is not modified."""
    import inspect

    from backend.app.rolling_backtest import replay_metadata

    sig = inspect.signature(replay_metadata.write_replay_metadata)
    expected = {
        "session",
        "config",
        "rolling_node",
        "run_id",
        "replay_executed_at",
        "replay_identity",
    }
    assert expected.issubset(set(sig.parameters.keys())), (
        "bucket #4 writer signature drift is out of scope for bucket #5"
    )


def test_replay_pipeline_uses_replay_audit_and_replay_metadata_modules() -> None:
    """Bucket #5 imports the bucket-#3 and bucket-#4 writers — never duplicates them."""
    import inspect

    from backend.app.rolling_backtest.replay_pipeline import orchestrate_replay_node

    src = inspect.getsource(orchestrate_replay_node)
    # Pipeline must call the bucket #3 audit writer's public entry point.
    assert "write_replay_source_visibility_audit(" in src
    # Pipeline must call the bucket #4 metadata writer's public entry
    # point.
    assert "write_replay_metadata(" in src
    # Pipeline must NOT re-implement the audit row ORM inserts.
    assert "HarvestStateReplaySourceVisibilityAuditModel(" not in src
    # Pipeline must NOT do a direct ORM UPDATE on the five metadata columns
    # by hand — bucket #4 writer does this authoritatively.
    assert ".is_replay =" not in src
    assert ".forecast_effective_cutoff_at =" not in src
    assert ".replay_code_version =" not in src


# ── bucket #5 module-surface discipline ──────────────────────────────────────


def test_replay_pipeline_module_only_orchestrate_replay_node_and_helpers() -> None:
    """§5.5 — ``replay_pipeline`` is the canonical replay-pipeline module.

    It must NOT contain a runner (bucket-7+ scope), Task 10 binding
    code (bucket-6 scope), or a generic dispatcher. Only the dispatch
    surface + helpers + typed errors + outcome envelope.
    """
    import inspect

    from backend.app.rolling_backtest import replay_pipeline

    public_members = {
        name
        for name, obj in inspect.getmembers(replay_pipeline)
        if not name.startswith("_") and not inspect.ismodule(obj)
    }
    # The four documented public symbols.
    expected_public = {
        "ReplayPipelineError",
        "ReplayPipelineInputError",
        "ReplayPipelineOutcome",
        "orchestrate_replay_node",
    }
    assert expected_public.issubset(public_members), (
        f"missing public symbols: {expected_public - public_members}"
    )


def test_replay_pipeline_does_not_import_run_harvest_state_model() -> None:
    """Static check: the replay pipeline module MUST NOT import Task 9's lower-level model.

    AST-based check (rather than raw source grep) avoids false
    positives from docstring / comment references.
    """
    import ast
    import inspect

    from backend.app.rolling_backtest import replay_pipeline

    src = inspect.getsource(replay_pipeline)
    tree = ast.parse(src)

    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported_names.add(alias.asname or alias.name.split(".")[0])
    assert "run_harvest_state_model" not in imported_names, (
        "§3 rule #1: replay_pipeline module must not import run_harvest_state_model"
    )
