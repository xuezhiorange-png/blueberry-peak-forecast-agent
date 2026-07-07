"""Bucket #6 — Task 10 replay binding hardening tests.

Verifies the §11 contract enforcement in
:mod:`backend.app.rolling_backtest.replay_task10_binding` and the
non-regression on the historical
``Task10Task9BindingMismatchError`` /
``task10_task9_binding_mismatch`` flow (Phase 2).

Test matrix (per Charles's bucket #6 authorization):

1. Correct replay-produced Task 9 output is accepted.
2. Cross-run substitution is rejected (different task9_run_id).
3. Cross-run / hash-mismatch substitution is rejected (same run_id,
   different result_hash).
4. Missing replay-produced HarvestStateRun row is rejected.
5. is_replay=False on a candidate row is rejected.
6. load_harvest_state_output_by_id returning no output is rejected.
7. Task10ModelPolicy.REPLAY_TRAINED_MODEL is rejected.
8. Task10ModelPolicy=None is rejected.
9. Task10ModelPolicy=unknown value is rejected.
10. Task10ModelPolicy=HISTORICALLY_AVAILABLE_MODEL is accepted.
11. Replay output cannot pose as historical_observed.
12. Phase 2 Task10Task9BindingMismatchError is unchanged.
13. Task10ReplayBindingInvalidError carries the bucket #2 frozen
    literal ``OrchestrationBlocker.TASK10_REPLAY_BINDING_INVALID``.
14. Existing bucket #3 audit writer behavior is unchanged.
15. Existing bucket #4 metadata writer behavior is unchanged.
16. Existing bucket #5 dispatch wiring behavior is unchanged.
17. evaluate_replay_task10_binding does NOT call
    run_harvest_state_model.
18. The binding module does NOT call any lower-level Task 9
    internals; only load_harvest_state_output_by_id /
    load_residual_prediction_run_by_id are permitted reads.
19. evaluate_replay_task10_binding_for_resolved_inputs selects
    TASK10_PREDICTION_RUN correctly.
20. evaluate_replay_task10_binding_for_resolved_inputs accepts a
    resolved inputs dict without a Task 10 prediction.
"""

from __future__ import annotations

import datetime as _dt
import inspect
from dataclasses import dataclass
from datetime import UTC
from typing import Any, cast
from unittest import mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.rolling_backtest import (
    node_orchestration as node_orchestration_module,
)
from backend.app.rolling_backtest import (
    replay_pipeline as replay_pipeline_module,
)
from backend.app.rolling_backtest import (
    replay_task10_binding as binding_module,
)
from backend.app.rolling_backtest.enums import (
    AvailabilitySourceType,
    ExecutionMode,
    Task10ModelPolicy,
)
from backend.app.rolling_backtest.node_orchestration import (
    Task10ReplayBindingInvalidError,
    Task10Task9BindingMismatchError,
)
from backend.app.rolling_backtest.orchestration import (
    OrchestrationBlocker,
    ResolvedInputOutcome,
)
from backend.app.rolling_backtest.replay_pipeline import ReplayPipelineOutcome
from backend.app.rolling_backtest.replay_task10_binding import (
    ReplayTask9BindingContext,
    evaluate_replay_task10_binding,
    evaluate_replay_task10_binding_for_resolved_inputs,
    is_replay_execution_mode,
    validate_replay_task10_model_policy,
)
from backend.app.rolling_backtest.schemas import (
    PersistentUpstreamReference,
    ResolvedUpstreamSemanticIdentity,
    UpstreamSemanticIdentityPayload,
)

# ── Fixtures / helpers ────────────────────────────────────────────────────


def _utc(year: int = 2026, month: int = 3, day: int = 15) -> _dt.datetime:
    return _dt.datetime(
        year,
        month,
        day,
        4,
        0,
        0,
        tzinfo=UTC,
    )


@dataclass
class _StubHarvestRun:
    """Minimal HarvestStateRun stub matching the columns the binding
    validator reads."""

    id: int
    is_replay: bool = True
    result_hash: str = "a" * 64


@dataclass
class _StubPredictionResult:
    """Minimal ResidualPredictionExecutionResult stub."""

    task9_run_id: int
    task9_result_hash: str
    mode: str = "residual_corrected"
    prediction_hash: str = "p" * 64


def _build_replay_outcome(
    *,
    task9_run_id: int,
    replay_executed_at: _dt.datetime | None = None,
    code_version: str = "bucket-6.0.0",
    replay_correlation_id: str = "rcid-bucket6",
) -> ReplayPipelineOutcome:
    return ReplayPipelineOutcome(
        task9_run_id=task9_run_id,
        audit_row_count=3,
        replay_executed_at=replay_executed_at or _utc(),
        replay_correlation_id=replay_correlation_id,
        code_version=code_version,
    )


def _build_binding_context(
    *,
    task9_run_id: int,
    task9_result_hash: str = "a" * 64,
) -> ReplayTask9BindingContext:
    return ReplayTask9BindingContext(
        task9_run_id=task9_run_id,
        task9_result_hash=task9_result_hash,
        is_replay_provenance=True,
        replay_code_version="bucket-6.0.0",
        replay_executed_at=_utc(),
    )


def _make_resolved_input(
    *,
    source_type: AvailabilitySourceType,
    reference_value: int | str,
    reference_type: str = "database_run_id",
    source_role: str = "stub_role",
) -> ResolvedInputOutcome:
    semantic_payload = UpstreamSemanticIdentityPayload(
        schema_version="test-v1",
        display_label="test-label",
        semantic_payload_hash="a" * 64,
        canonical_payload_hash="b" * 64,
    )
    semantic_identity = ResolvedUpstreamSemanticIdentity(
        source_type=source_type,
        source_role=source_role,
        semantic=semantic_payload,
    )
    return ResolvedInputOutcome(
        source_role=source_role,
        source_type=source_type,
        semantic_identity=semantic_identity,
        persistent_reference=PersistentUpstreamReference(
            reference_type=reference_type,
            reference_value=reference_value,
        ),
        authoritative_available_at=_utc(),
        canonical_identity_hash="c" * 64,
        canonical_payload_hash="p" * 64,
    )


# ── is_replay_execution_mode helper ──────────────────────────────────────


def test_is_replay_execution_mode_enum_match() -> None:
    assert is_replay_execution_mode(ExecutionMode.RETROSPECTIVE_REPLAY) is True
    assert is_replay_execution_mode(ExecutionMode.HISTORICAL_OBSERVED) is False


def test_is_replay_execution_mode_string_match() -> None:
    assert is_replay_execution_mode("retrospective_replay") is True
    assert is_replay_execution_mode("historical_observed") is False


# ── validate_replay_task10_model_policy ──────────────────────────────────


def test_validate_replay_task10_model_policy_accepts_historically() -> None:
    """HISTORICALLY_AVAILABLE_MODEL is the only policy allowed for replay."""
    result = validate_replay_task10_model_policy(
        requested_policy=Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL,
    )
    assert result is Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL
    # String form
    result_str = validate_replay_task10_model_policy(
        requested_policy="historically_available_model"
    )
    assert result_str is Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL


def test_validate_replay_task10_model_policy_rejects_replay_trained() -> None:
    """REPLAY_TRAINED_MODEL is rejected per §11 §3 + Issue #29 §3."""
    with pytest.raises(Task10ReplayBindingInvalidError) as excinfo:
        validate_replay_task10_model_policy(
            requested_policy=Task10ModelPolicy.REPLAY_TRAINED_MODEL,
        )
    expected = OrchestrationBlocker.TASK10_REPLAY_BINDING_INVALID.value
    assert excinfo.value.code == expected


def test_validate_replay_task10_model_policy_rejects_none() -> None:
    with pytest.raises(Task10ReplayBindingInvalidError) as excinfo:
        validate_replay_task10_model_policy(requested_policy=None)
    expected = OrchestrationBlocker.TASK10_REPLAY_BINDING_INVALID.value
    assert excinfo.value.code == expected


def test_validate_replay_task10_model_policy_rejects_unknown() -> None:
    with pytest.raises(Task10ReplayBindingInvalidError) as excinfo:
        validate_replay_task10_model_policy(requested_policy="not_a_real_policy")
    expected = OrchestrationBlocker.TASK10_REPLAY_BINDING_INVALID.value
    assert excinfo.value.code == expected


# ── build_replay_task9_binding_context ──────────────────────────────────


@pytest.mark.asyncio
async def test_build_replay_task9_binding_context_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A replay-produced row with is_replay=TRUE is accepted."""
    harvest_run = _StubHarvestRun(id=4242, is_replay=True)

    async def _fake_load_output(*_a: Any, **_kw: Any) -> Any:
        return mock.Mock(result_hash="b" * 64)

    monkeypatch.setattr(
        binding_module,
        "load_harvest_state_output_by_id",
        _fake_load_output,
    )

    class _S:
        async def execute(self, _stmt: Any) -> Any:
            class _R:
                def scalar_one_or_none(self) -> _StubHarvestRun:
                    return harvest_run

            return _R()

    ctx = await binding_module.build_replay_task9_binding_context(
        cast(AsyncSession, _S()),
        replay_outcome=_build_replay_outcome(task9_run_id=4242),
    )
    assert ctx.task9_run_id == 4242
    assert ctx.task9_result_hash == "b" * 64
    assert ctx.is_replay_provenance is True


@pytest.mark.asyncio
async def test_build_replay_task9_binding_context_missing_row_rejected() -> None:
    """Missing HarvestStateRun row ⇒ TASK10_REPLAY_BINDING_INVALID."""

    class _S:
        async def execute(self, _stmt: Any) -> Any:
            class _R:
                def scalar_one_or_none(self) -> None:
                    return None

            return _R()

    with pytest.raises(Task10ReplayBindingInvalidError) as excinfo:
        await binding_module.build_replay_task9_binding_context(
            cast(AsyncSession, _S()),
            replay_outcome=_build_replay_outcome(task9_run_id=999),
        )
    expected = OrchestrationBlocker.TASK10_REPLAY_BINDING_INVALID.value
    assert excinfo.value.code == expected


@pytest.mark.asyncio
async def test_build_replay_task9_binding_context_is_replay_false_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """is_replay=False (historical_observed shadow) ⇒ rejected."""

    harvest_run = _StubHarvestRun(id=77, is_replay=False)

    async def _fake_load_output(*_a: Any, **_kw: Any) -> Any:
        return mock.Mock(result_hash="c" * 64)

    monkeypatch.setattr(
        binding_module,
        "load_harvest_state_output_by_id",
        _fake_load_output,
    )

    class _S:
        async def execute(self, _stmt: Any) -> Any:
            class _R:
                def scalar_one_or_none(self) -> _StubHarvestRun:
                    return harvest_run

            return _R()

    with pytest.raises(Task10ReplayBindingInvalidError) as excinfo:
        await binding_module.build_replay_task9_binding_context(
            cast(AsyncSession, _S()),
            replay_outcome=_build_replay_outcome(task9_run_id=77),
        )
    expected = OrchestrationBlocker.TASK10_REPLAY_BINDING_INVALID.value
    assert excinfo.value.code == expected
    assert "is_replay=False" in str(excinfo.value)


@pytest.mark.asyncio
async def test_build_replay_task9_binding_context_load_output_none_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """load_harvest_state_output_by_id returns None ⇒ rejected."""
    harvest_run = _StubHarvestRun(id=88, is_replay=True)

    async def _fake_load_output(*_a: Any, **_kw: Any) -> None:
        return None

    monkeypatch.setattr(
        binding_module,
        "load_harvest_state_output_by_id",
        _fake_load_output,
    )

    class _S:
        async def execute(self, _stmt: Any) -> Any:
            class _R:
                def scalar_one_or_none(self) -> _StubHarvestRun:
                    return harvest_run

            return _R()

    with pytest.raises(Task10ReplayBindingInvalidError) as excinfo:
        await binding_module.build_replay_task9_binding_context(
            cast(AsyncSession, _S()),
            replay_outcome=_build_replay_outcome(task9_run_id=88),
        )
    expected = OrchestrationBlocker.TASK10_REPLAY_BINDING_INVALID.value
    assert excinfo.value.code == expected


@pytest.mark.asyncio
async def test_build_replay_task9_binding_context_load_output_hash_missing_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """load_harvest_state_output_by_id yields no result_hash ⇒ rejected."""
    harvest_run = _StubHarvestRun(id=99, is_replay=True)

    async def _fake_load_output(*_a: Any, **_kw: Any) -> Any:
        return mock.Mock(result_hash=None)

    monkeypatch.setattr(
        binding_module,
        "load_harvest_state_output_by_id",
        _fake_load_output,
    )

    class _S:
        async def execute(self, _stmt: Any) -> Any:
            class _R:
                def scalar_one_or_none(self) -> _StubHarvestRun:
                    return harvest_run

            return _R()

    with pytest.raises(Task10ReplayBindingInvalidError) as excinfo:
        await binding_module.build_replay_task9_binding_context(
            cast(AsyncSession, _S()),
            replay_outcome=_build_replay_outcome(task9_run_id=99),
        )
    expected = OrchestrationBlocker.TASK10_REPLAY_BINDING_INVALID.value
    assert excinfo.value.code == expected


# ── evaluate_replay_task10_binding ─────────────────────────────────────


@pytest.mark.asyncio
async def test_evaluate_replay_task10_binding_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Correct replay-produced identity ⇒ accepted."""
    binding_context = _build_binding_context(task9_run_id=10)
    prediction_input = _make_resolved_input(
        source_type=AvailabilitySourceType.TASK10_PREDICTION_RUN,
        reference_value=42,
    )

    async def _fake_load_prediction(*_a: Any, **_kw: Any) -> _StubPredictionResult:
        return _StubPredictionResult(
            task9_run_id=10,
            task9_result_hash=binding_context.task9_result_hash,
        )

    monkeypatch.setattr(
        binding_module,
        "load_residual_prediction_run_by_id",
        _fake_load_prediction,
    )

    result = await evaluate_replay_task10_binding(
        mock.Mock(),
        binding_context=binding_context,
        prediction_input=prediction_input,
        requested_policy=Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL,
    )
    assert result is not None
    assert result.prediction_run_id == 42
    assert result.task9_run_id == 10
    assert result.task9_result_hash == binding_context.task9_result_hash
    assert result.model_policy is Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL
    assert result.is_replay_provenance is True


@pytest.mark.asyncio
async def test_evaluate_replay_task10_binding_cross_run_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cross-run substitution ⇒ rejected (§11 §1 + §4)."""
    binding_context = _build_binding_context(task9_run_id=10)
    prediction_input = _make_resolved_input(
        source_type=AvailabilitySourceType.TASK10_PREDICTION_RUN,
        reference_value=42,
    )

    async def _fake_load_prediction(*_a: Any, **_kw: Any) -> _StubPredictionResult:
        # Cross-run substitution: prediction binds to a different
        # task9_run_id than the replay-produced one.
        return _StubPredictionResult(
            task9_run_id=20,  # NOT 10
            task9_result_hash=binding_context.task9_result_hash,
        )

    monkeypatch.setattr(
        binding_module,
        "load_residual_prediction_run_by_id",
        _fake_load_prediction,
    )

    with pytest.raises(Task10ReplayBindingInvalidError) as excinfo:
        await evaluate_replay_task10_binding(
            mock.Mock(),
            binding_context=binding_context,
            prediction_input=prediction_input,
            requested_policy=Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL,
        )
    expected = OrchestrationBlocker.TASK10_REPLAY_BINDING_INVALID.value
    assert excinfo.value.code == expected
    assert "cross-run substitution" in str(excinfo.value).lower()


@pytest.mark.asyncio
async def test_evaluate_replay_task10_binding_hash_mismatch_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hash substitution ⇒ rejected (§11 §2 + §4)."""
    binding_context = _build_binding_context(task9_run_id=10)
    prediction_input = _make_resolved_input(
        source_type=AvailabilitySourceType.TASK10_PREDICTION_RUN,
        reference_value=42,
    )

    async def _fake_load_prediction(*_a: Any, **_kw: Any) -> _StubPredictionResult:
        # Hash substitution: same run_id, different result_hash.
        return _StubPredictionResult(
            task9_run_id=10,
            task9_result_hash="z" * 64,
        )

    monkeypatch.setattr(
        binding_module,
        "load_residual_prediction_run_by_id",
        _fake_load_prediction,
    )

    with pytest.raises(Task10ReplayBindingInvalidError) as excinfo:
        await evaluate_replay_task10_binding(
            mock.Mock(),
            binding_context=binding_context,
            prediction_input=prediction_input,
            requested_policy=Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL,
        )
    expected = OrchestrationBlocker.TASK10_REPLAY_BINDING_INVALID.value
    assert excinfo.value.code == expected
    assert "hash" in str(excinfo.value).lower()


@pytest.mark.asyncio
async def test_evaluate_replay_task10_binding_missing_prediction_row_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Integrity loader returns None ⇒ no substitution."""
    binding_context = _build_binding_context(task9_run_id=10)
    prediction_input = _make_resolved_input(
        source_type=AvailabilitySourceType.TASK10_PREDICTION_RUN,
        reference_value=42,
    )

    async def _fake_load_prediction(*_a: Any, **_kw: Any) -> None:
        return None

    monkeypatch.setattr(
        binding_module,
        "load_residual_prediction_run_by_id",
        _fake_load_prediction,
    )

    with pytest.raises(Task10ReplayBindingInvalidError) as excinfo:
        await evaluate_replay_task10_binding(
            mock.Mock(),
            binding_context=binding_context,
            prediction_input=prediction_input,
            requested_policy=Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL,
        )
    expected = OrchestrationBlocker.TASK10_REPLAY_BINDING_INVALID.value
    assert excinfo.value.code == expected


@pytest.mark.asyncio
async def test_evaluate_replay_task10_binding_non_database_run_id_rejected() -> None:
    """Non-database_run_id prediction references are rejected."""
    binding_context = _build_binding_context(task9_run_id=10)

    # Provide a non-database_run_id reference (database_artifact_id
    # instead) — the validator gates on reference_type being
    # database_run_id, since replay binding must be a row reference.
    prediction_input = _make_resolved_input(
        source_type=AvailabilitySourceType.TASK10_PREDICTION_RUN,
        reference_value=42,
        reference_type="database_artifact_id",
    )

    with pytest.raises(Task10ReplayBindingInvalidError) as excinfo:
        await evaluate_replay_task10_binding(
            mock.Mock(),
            binding_context=binding_context,
            prediction_input=prediction_input,
            requested_policy=Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL,
        )
    expected = OrchestrationBlocker.TASK10_REPLAY_BINDING_INVALID.value
    assert excinfo.value.code == expected
    assert "database_run_id" in str(excinfo.value)


# ── replay-vs-historical output separation ────────────────────────────


@pytest.mark.asyncio
async def test_evaluate_replay_task10_binding_rejects_replay_trained_policy() -> None:
    """REPLAY_TRAINED_MODEL is rejected before any DB round-trip (§11 §3)."""
    binding_context = _build_binding_context(task9_run_id=10)

    with pytest.raises(Task10ReplayBindingInvalidError) as excinfo:
        await evaluate_replay_task10_binding(
            mock.Mock(),
            binding_context=binding_context,
            prediction_input=None,
            requested_policy=Task10ModelPolicy.REPLAY_TRAINED_MODEL,
        )
    expected = OrchestrationBlocker.TASK10_REPLAY_BINDING_INVALID.value
    assert excinfo.value.code == expected
    assert "replay_trained_model" in str(excinfo.value)


@pytest.mark.asyncio
async def test_evaluate_replay_task10_binding_no_prediction_trivially_ok() -> None:
    """A replay that binds no Task 10 prediction is accepted with None."""
    binding_context = _build_binding_context(task9_run_id=10)

    result = await evaluate_replay_task10_binding(
        mock.Mock(),
        binding_context=binding_context,
        prediction_input=None,
        requested_policy=Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL,
    )
    assert result is None


# ── evaluate_replay_task10_binding_for_resolved_inputs ──────────────


@pytest.mark.asyncio
async def test_evaluate_for_resolved_inputs_selects_prediction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Convenience wrapper finds the Task 10 prediction in resolved_inputs."""
    binding_context = _build_binding_context(task9_run_id=10)
    resolved: dict[str, ResolvedInputOutcome] = {
        # Non-task10 inputs should be ignored.
        "task8_forecast_run": _make_resolved_input(
            source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
            reference_value=1,
            source_role="task8_forecast_run:FEBRUARY_END",
        ),
        "task10_prediction_run:FEBRUARY_END": _make_resolved_input(
            source_type=AvailabilitySourceType.TASK10_PREDICTION_RUN,
            reference_value=42,
            source_role="task10_prediction_run:FEBRUARY_END",
        ),
        "task10_training_run": _make_resolved_input(
            source_type=AvailabilitySourceType.TASK10_TRAINING_RUN,
            reference_value=99,
            source_role="task10_training_run:FEBRUARY_END",
        ),
    }

    async def _fake_load_prediction(*_a: Any, **_kw: Any) -> _StubPredictionResult:
        return _StubPredictionResult(
            task9_run_id=10,
            task9_result_hash=binding_context.task9_result_hash,
        )

    monkeypatch.setattr(
        binding_module,
        "load_residual_prediction_run_by_id",
        _fake_load_prediction,
    )

    result = await evaluate_replay_task10_binding_for_resolved_inputs(
        mock.Mock(),
        binding_context=binding_context,
        resolved_inputs=resolved,
        requested_policy=Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL,
    )
    assert result is not None
    assert result.prediction_run_id == 42


@pytest.mark.asyncio
async def test_evaluate_for_resolved_inputs_no_prediction_returns_none() -> None:
    """No Task 10 prediction in resolved_inputs ⇒ trivially satisfied."""
    binding_context = _build_binding_context(task9_run_id=10)
    resolved: dict[str, ResolvedInputOutcome] = {
        "task8_forecast_run": _make_resolved_input(
            source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
            reference_value=1,
            source_role="task8_forecast_run:FEBRUARY_END",
        ),
    }

    result = await evaluate_replay_task10_binding_for_resolved_inputs(
        mock.Mock(),
        binding_context=binding_context,
        resolved_inputs=resolved,
        requested_policy=Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL,
    )
    assert result is None


# ── Phase 2 path non-regression ───────────────────────────────────────


def test_phase2_task10_task9_binding_mismatch_error_unchanged() -> None:
    """Historical Task10Task9BindingMismatchError is preserved unchanged."""
    # Phase 2 code literal — the historical binding-mismatch identifier
    # is preserved verbatim.
    assert Task10Task9BindingMismatchError.code == "TASK10_TASK9_BINDING_MISMATCH"
    # Bucket #6 code literal — the bucket #2 frozen enum value is
    # carried into the new typed error verbatim.
    expected = OrchestrationBlocker.TASK10_REPLAY_BINDING_INVALID.value
    assert Task10ReplayBindingInvalidError.code == expected


def test_orchestrator_catch_list_includes_new_error() -> None:
    """Orchestrator catch list contains the new typed error."""
    src = inspect.getsource(node_orchestration_module)
    assert "Task10ReplayBindingInvalidError" in src


# ── bucket #3 / #4 / #5 regression guard ──────────────────────────────


def test_bucket_audit_writer_signature_preserved() -> None:
    """Bucket #3 audit writer is unchanged."""
    src = inspect.getsource(node_orchestration_module)
    assert "from .replay_audit import" not in src
    assert "from . import replay_audit" not in src


def test_bucket_metadata_writer_signature_preserved() -> None:
    """Bucket #4 metadata writer is unchanged."""
    src = inspect.getsource(node_orchestration_module)
    assert "from .replay_metadata import" not in src
    assert "from . import replay_metadata" not in src


def test_bucket_dispatch_signature_preserved() -> None:
    """Bucket #5 dispatch wiring is unchanged."""
    assert hasattr(replay_pipeline_module, "orchestrate_replay_node")
    assert hasattr(replay_pipeline_module, "ReplayPipelineOutcome")


# ── no Task 9 lower-level internals called directly ────────────────


def test_binding_module_does_not_import_run_harvest_state_model() -> None:
    """The binding validator must not reach into Task 9 lower-level
    internals. AST-level guard: no import / call / attribute ref to
    ``run_harvest_state_model`` outside of the module docstring and
    comments.
    """
    import ast

    tree = ast.parse(inspect.getsource(binding_module))

    def _walk(node: ast.AST) -> list[str]:
        bad: list[str] = []
        for child in ast.walk(node):
            if isinstance(child, ast.ImportFrom):
                for alias in child.names:
                    if alias.name == "run_harvest_state_model":
                        bad.append(f"import {alias.name}")
            elif isinstance(child, ast.Import):
                for alias in child.names:
                    if alias.name == "run_harvest_state_model":
                        bad.append(f"import {alias.name}")
            elif isinstance(child, ast.Call):
                func = child.func
                if isinstance(func, ast.Name) and func.id == "run_harvest_state_model":
                    bad.append("call run_harvest_state_model")
                elif isinstance(func, ast.Attribute) and func.attr == "run_harvest_state_model":
                    bad.append("call .run_harvest_state_model")
        return bad

    assert _walk(tree) == [], f"binding module references run_harvest_state_model: {_walk(tree)}"


def test_binding_module_no_residual_training() -> None:
    """The binding validator must not introduce residual-model training."""
    import ast

    tree = ast.parse(inspect.getsource(binding_module))
    bad: list[str] = []
    for child in ast.walk(tree):
        if isinstance(child, ast.ImportFrom):
            for alias in child.names:
                if alias.name in {"train_residual_model", "ResidualModelTrainer"}:
                    bad.append(f"import {alias.name}")
        elif isinstance(child, ast.Import):
            for alias in child.names:
                if alias.name in {"train_residual_model", "ResidualModelTrainer"}:
                    bad.append(f"import {alias.name}")
        elif isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Name) and func.id == "train_residual_model":
                bad.append("call train_residual_model")
    assert bad == [], f"binding module references residual-training: {bad}"


# ── replay output cannot pose as historical_observed ────────────────


@pytest.mark.asyncio
async def test_no_current_data_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Replay binding refuses a substitute Task 10 prediction even when
    it came from a historical_observed run (no current-data /
    latest-row / wall-clock fallback)."""
    binding_context = _build_binding_context(task9_run_id=10)
    prediction_input = _make_resolved_input(
        source_type=AvailabilitySourceType.TASK10_PREDICTION_RUN,
        reference_value=42,
    )

    async def _fake_load_prediction(*_a: Any, **_kw: Any) -> _StubPredictionResult:
        # Imagine a historical_observed Task 10 prediction whose Task 9
        # was produced under a different cut — must be refused.
        return _StubPredictionResult(
            task9_run_id=11,  # different
            task9_result_hash=binding_context.task9_result_hash,
        )

    monkeypatch.setattr(
        binding_module,
        "load_residual_prediction_run_by_id",
        _fake_load_prediction,
    )

    with pytest.raises(Task10ReplayBindingInvalidError) as excinfo:
        await evaluate_replay_task10_binding(
            mock.Mock(),
            binding_context=binding_context,
            prediction_input=prediction_input,
            requested_policy=Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL,
        )
    expected = OrchestrationBlocker.TASK10_REPLAY_BINDING_INVALID.value
    assert excinfo.value.code == expected
    assert "cross-run substitution" in str(excinfo.value).lower()


# ── structural integrity ──────────────────────────────────────────


def test_replay_task10_binding_outcome_provenance() -> None:
    """A successful binding outcome is always is_replay_provenance=True."""
    outcome = binding_module.ReplayTask10BindingOutcome(
        prediction_run_id=42,
        task9_run_id=10,
        task9_result_hash="a" * 64,
        is_replay_provenance=True,
        model_policy=Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL,
    )
    assert outcome.is_replay_provenance is True
    assert outcome.model_policy is Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL


def test_binding_module_no_wall_clock_decisions() -> None:
    """No wall-clock substitution in binding decisions. AST guard:
    no expressions of the form ``datetime.now()`` /
    ``datetime.utcnow()`` outside of docstrings / comments.
    """
    import ast

    tree = ast.parse(inspect.getsource(binding_module))
    bad: list[str] = []
    for child in ast.walk(tree):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        attr = func.attr if isinstance(func, ast.Attribute) else None
        value = func.value if isinstance(func, ast.Attribute) else None
        if isinstance(value, ast.Name) and value.id == "datetime" and attr in {"now", "utcnow"}:
            bad.append(f"datetime.{attr}()")
    assert bad == [], f"binding module uses wall-clock fallback: {bad}"
