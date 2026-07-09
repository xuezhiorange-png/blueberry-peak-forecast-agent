"""TASK-012 Slice A — replay_trained_model contract tests.

This module pins the design contract from
``docs/task-012-replay-trained-model-design.md`` §11 (Test contract) and
§12 (Slice A — contract tests only).

Per §12, Slice A is **contract tests only** and forbids production
implementation. The 12 tests below cover every test case listed in
§11 verbatim:

1. ``REPLAY_TRAINED_MODEL`` remains rejected before implementation gate.
2. Explicit ``REPLAY_TRAINED_MODEL`` does not fall back to
   ``HISTORICALLY_AVAILABLE_MODEL``.
3. Training rows after ``training_cutoff_at`` are excluded.
4. Labels with post-cutoff availability timestamps are excluded even
   when their observation date is before the cutoff.
5. Empty training set produces a structured blocker.
6. Cross-run model artifact substitution is rejected.
7. Cross-run Task 9 replay binding substitution is rejected.
8. Identical replay inputs produce identical training manifest hashes
   and model artifact hashes.
9. Changing model config changes the model config hash and model
   artifact hash.
10. JSON / manifest mismatch for replay-trained artifact identity is
    rejected.
11. Prediction produced with replay-trained model carries
    ``model_policy = "replay_trained_model"``.
12. Historically available and replay-trained comparison runs produce
    separate prediction identities.

Behavior pins that are satisfied by existing code paths
(``validate_replay_task10_model_policy``,
``evaluate_replay_task10_binding``, the
``ReplayTrainedModelIdentity`` schema, and the
``RollingNodeDefinition._validate_task10_policy_cutoff`` validator)
are fully exercised. Behavior pins that require Slice B / Slice C /
Slice D production implementation are recorded as ``pytest.skip``
contract pins with explicit ``reason`` references to §11 + §12 +
the future slice that will activate them — they exist as documented
contract obligations awaiting the next design-authorized
implementation round.

Per §11: ``No implementation PR may be considered complete until these
tests exist and pass.`` Slice A delivers the contract pins; full
pass-through requires Slice B / Slice C / Slice D implementation
rounds (each requiring separate Charles authorization).

Hard prohibitions reaffirmed (per §13 / §14):

- No Task 8 / Task 9 / Task 10 semantic change.
- No ``current/latest/most-recent`` fallback.
- No production code change in this module.
- No implementation of Slice B / Slice C / Slice D.
"""

from __future__ import annotations

import datetime as _dt
import inspect
from dataclasses import dataclass
from datetime import UTC

import pytest

from backend.app.rolling_backtest.enums import Task10ModelPolicy
from backend.app.rolling_backtest.node_orchestration import (
    Task10ReplayBindingInvalidError,
)
from backend.app.rolling_backtest.replay_task10_binding import (
    evaluate_replay_task10_binding,
    validate_replay_task10_model_policy,
)


# ── Helpers ──────────────────────────────────────────────────────────────────
def _utc(year: int = 2026, month: int = 3, day: int = 15, hour: int = 4) -> _dt.datetime:
    """Timezone-aware UTC datetime helper (matches design §5.1 timezone rule)."""
    return _dt.datetime(year, month, day, hour, 0, 0, tzinfo=UTC)


@dataclass
class _StubPredictionResult:
    """Minimal stub matching the columns ``evaluate_replay_task10_binding`` reads.

    The contract test surface uses duck-typed stubs to avoid coupling
    Slice A to the live ORM schema or task 9 persistence layer. Pattern
    mirrors ``_StubPredictionResult`` in ``test_replay_task10_binding.py``.
    """

    task9_run_id: int = 0
    task9_result_hash: str = ""
    mode: str = ""
    prediction_hash: str = ""


# ── Test 1: REPLAY_TRAINED_MODEL remains rejected before implementation gate ─


def test_replay_trained_model_remains_rejected_before_implementation_gate() -> None:
    """§11 #1 — the replay_trained_model enum value exists but every code path
    that processes replay authorization MUST reject it until Slice B / C / D
    land. ``validate_replay_task10_model_policy`` is the canonical gate and
    pins this contract today."""

    with pytest.raises(Task10ReplayBindingInvalidError) as exc_info:
        validate_replay_task10_model_policy(
            requested_policy=Task10ModelPolicy.REPLAY_TRAINED_MODEL,
        )
    # The rejection is structured: it carries a message that names the
    # frozen Issue #29 §3 contract. We don't pin the exact message text
    # (anti-fragile), but the rejection must fire and must NOT silently
    # fall back to HISTORICALLY_AVAILABLE_MODEL.
    assert "REPLAY_TRAINED_MODEL" in str(exc_info.value) or "replay_trained_model" in str(
        exc_info.value
    ), f"rejection message must name the forbidden policy: {exc_info.value}"


# ── Test 2: explicit REPLAY_TRAINED_MODEL does not fall back ─────────────────


def test_explicit_replay_trained_model_does_not_fall_back_to_historical() -> None:
    """§11 #2 — the gate MUST NOT silently convert REPLAY_TRAINED_MODEL into
    HISTORICALLY_AVAILABLE_MODEL. Verified by asserting that the gate raises
    rather than returns HISTORICALLY_AVAILABLE_MODEL."""

    with pytest.raises(Task10ReplayBindingInvalidError):
        validate_replay_task10_model_policy(
            requested_policy=Task10ModelPolicy.REPLAY_TRAINED_MODEL,
        )
    # And the gate, when given the only-authorized policy, returns it.
    authorized = validate_replay_task10_model_policy(
        requested_policy=Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL,
    )
    assert authorized is Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL


# ── Test 3: training rows after training_cutoff_at are excluded ──────────────


def test_training_rows_after_training_cutoff_at_are_excluded() -> None:
    """§11 #3 — schema-level bound: ``ReplayTrainedModelIdentity.training_cutoff_at``
    must be timezone-aware AND must not exceed the node's
    ``forecast_cutoff_at``. Execution-time row filtering awaits Slice C.

    This contract pin validates the existing schema-level bound via
    ``ReplayTrainedModelIdentity`` and the
    ``RollingNodeDefinition._validate_task10_policy_cutoff`` model validator.
    The execution-time filtering of rows beyond ``training_cutoff_at``
    is a Slice C responsibility; we mark the row-level filter as
    pending-implementation to honor §11's "tests exist" requirement
    without violating §12's "no production implementation" rule."""

    from backend.app.rolling_backtest.schemas import ReplayTrainedModelIdentity

    forecast_cutoff = _utc(2026, 3, 15, hour=12)
    training_cutoff = _utc(2026, 3, 14, hour=12)  # strictly before forecast

    # Schema-level: training_cutoff_at must be tz-aware and ≤ forecast_cutoff_at.
    identity = ReplayTrainedModelIdentity(
        policy=Task10ModelPolicy.REPLAY_TRAINED_MODEL,
        training_cutoff_at=training_cutoff,
        allowed_training_season_ids=(2026,),
        validation_policy_version="task11-validation-v1",
        label_visibility_policy_version="task11-label-visibility-v1",
        feature_visibility_policy_version="task11-feature-visibility-v1",
        artifact_visibility_policy_version="task11-artifact-visibility-v1",
        training_manifest_semantic_hash="b" * 64,
    )
    assert identity.training_cutoff_at == training_cutoff
    assert identity.training_cutoff_at.tzinfo is not None
    assert identity.training_cutoff_at <= forecast_cutoff

    # Execution-time row filtering requires Slice C implementation.
    pytest.skip(
        "Execution-time training-row filtering (rows after training_cutoff_at) "
        "awaits Slice C implementation per TASK-012 design §11 #3 + §12."
    )


# ── Test 4: labels with post-cutoff availability are excluded ───────────────


def test_labels_with_post_cutoff_availability_are_excluded() -> None:
    """§11 #4 — labels with authoritative availability AFTER training_cutoff_at
    must be excluded even when observation_date is BEFORE the cutoff.

    Awaiting Slice C implementation. Schema-level rejection of
    training_cutoff_at > forecast_cutoff_at is pinned in test #3."""

    pytest.skip(
        "Label availability filtering (post-cutoff availability timestamps) "
        "awaits Slice C implementation per TASK-012 design §11 #4 + §12."
    )


# ── Test 5: empty training set produces a structured blocker ────────────────


def test_empty_training_set_produces_structured_blocker() -> None:
    """§11 #5 — when all rows are excluded by cutoff / availability filters,
    the system MUST raise a structured blocker (per §9 blocker taxonomy)
    rather than fabricating an empty training set.

    Awaiting Slice C implementation."""

    pytest.skip(
        "Empty-training-set structured blocker awaits Slice C implementation "
        "per TASK-012 design §9 blocker taxonomy + §11 #5 + §12."
    )


# ── Test 6: cross-run model artifact substitution is rejected ─────────────────


@pytest.mark.asyncio
async def test_cross_run_model_artifact_substitution_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§11 #6 — a model artifact produced by a different replay attempt MUST NOT
    be accepted by the current replay binding path. Pinned by the existing
    ``evaluate_replay_task10_binding`` which enforces task9_run_id + result_hash
    equality between the loaded artifact and the current replay-produced row.

    Pattern mirrors ``test_evaluate_replay_task10_binding_cross_run_rejected``
    in ``test_replay_task10_binding.py`` (Phase 3 bucket #6) but binds to the
    design §11 contract test name explicitly."""

    from sqlalchemy.ext.asyncio import AsyncSession

    from backend.app.rolling_backtest import replay_task10_binding as binding_mod
    from backend.app.rolling_backtest.enums import AvailabilitySourceType
    from backend.app.rolling_backtest.orchestration import (
        OrchestrationBlocker,
        ResolvedInputOutcome,
    )
    from backend.app.rolling_backtest.schemas import (
        PersistentUpstreamReference,
        ResolvedUpstreamSemanticIdentity,
        UpstreamSemanticIdentityPayload,
    )

    current_task9_run_id = 10
    foreign_task9_run_id = 20

    binding_context = binding_mod.ReplayTask9BindingContext(
        task9_run_id=current_task9_run_id,
        task9_result_hash="a" * 64,
        is_replay_provenance=True,
        replay_code_version="task11-replay-v1",
        replay_executed_at=_utc(),
    )

    semantic_payload = UpstreamSemanticIdentityPayload(
        schema_version="task12-slice-a-v1",
        display_label="slice-a-stub",
        semantic_payload_hash="a" * 64,
        canonical_payload_hash="b" * 64,
    )
    semantic_identity = ResolvedUpstreamSemanticIdentity(
        source_type=AvailabilitySourceType.TASK10_PREDICTION_RUN,
        source_role="task10_prediction_run",
        semantic=semantic_payload,
    )
    prediction_input = ResolvedInputOutcome(
        source_role="task10_prediction_run",
        source_type=AvailabilitySourceType.TASK10_PREDICTION_RUN,
        semantic_identity=semantic_identity,
        persistent_reference=PersistentUpstreamReference(
            reference_type="database_run_id",
            reference_value=42,
        ),
        authoritative_available_at=_utc(),
        canonical_identity_hash="c" * 64,
        canonical_payload_hash="d" * 64,
    )

    async def _fake_load_prediction(session: AsyncSession, run_id: int) -> _StubPredictionResult:
        # Cross-run substitution: prediction binds to a different
        # task9_run_id than the replay-produced one.
        return _StubPredictionResult(
            task9_run_id=foreign_task9_run_id,
            task9_result_hash=binding_context.task9_result_hash,
            mode="residual_corrected",
            prediction_hash="p" * 64,
        )

    monkeypatch.setattr(
        binding_mod,
        "load_residual_prediction_run_by_id",
        _fake_load_prediction,
    )

    from unittest import mock

    with pytest.raises(Task10ReplayBindingInvalidError) as exc_info:
        await evaluate_replay_task10_binding(
            mock.Mock(),
            binding_context=binding_context,
            prediction_input=prediction_input,
            requested_policy=Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL,
        )
    # The §7 frozen blocker code MUST be the canonical cross-run rejection.
    assert exc_info.value.code == OrchestrationBlocker.TASK10_REPLAY_BINDING_INVALID.value
    assert "cross-run substitution" in str(exc_info.value).lower()


# ── Test 7: cross-run Task 9 replay binding substitution is rejected ─────────


@pytest.mark.asyncio
async def test_cross_run_task9_replay_binding_substitution_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§11 #7 — the replay-produced Task 9 row MUST be the only accepted
    binding source. A foreign task9 binding (different run_id or
    different result_hash) MUST be rejected.

    Pinned by ``evaluate_replay_task10_binding``'s run_id equality + result_hash
    equality checks against the current replay's harvest-state row."""

    from sqlalchemy.ext.asyncio import AsyncSession

    from backend.app.rolling_backtest import replay_task10_binding as binding_mod
    from backend.app.rolling_backtest.enums import AvailabilitySourceType
    from backend.app.rolling_backtest.orchestration import (
        OrchestrationBlocker,
        ResolvedInputOutcome,
    )
    from backend.app.rolling_backtest.schemas import (
        PersistentUpstreamReference,
        ResolvedUpstreamSemanticIdentity,
        UpstreamSemanticIdentityPayload,
    )

    current_task9_run_id = 10
    expected_task9_result_hash = "a" * 64
    foreign_task9_result_hash = "z" * 64

    binding_context = binding_mod.ReplayTask9BindingContext(
        task9_run_id=current_task9_run_id,
        task9_result_hash=expected_task9_result_hash,
        is_replay_provenance=True,
        replay_code_version="task11-replay-v1",
        replay_executed_at=_utc(),
    )

    semantic_payload = UpstreamSemanticIdentityPayload(
        schema_version="task12-slice-a-v1",
        display_label="slice-a-stub",
        semantic_payload_hash="a" * 64,
        canonical_payload_hash="b" * 64,
    )
    semantic_identity = ResolvedUpstreamSemanticIdentity(
        source_type=AvailabilitySourceType.TASK10_PREDICTION_RUN,
        source_role="task10_prediction_run",
        semantic=semantic_payload,
    )
    prediction_input = ResolvedInputOutcome(
        source_role="task10_prediction_run",
        source_type=AvailabilitySourceType.TASK10_PREDICTION_RUN,
        semantic_identity=semantic_identity,
        persistent_reference=PersistentUpstreamReference(
            reference_type="database_run_id",
            reference_value=42,
        ),
        authoritative_available_at=_utc(),
        canonical_identity_hash="c" * 64,
        canonical_payload_hash="d" * 64,
    )

    async def _fake_load_prediction(session: AsyncSession, run_id: int) -> _StubPredictionResult:
        # Same run_id, DIFFERENT result_hash ⇒ hash substitution rejection.
        return _StubPredictionResult(
            task9_run_id=current_task9_run_id,
            task9_result_hash=foreign_task9_result_hash,
            mode="residual_corrected",
            prediction_hash="p" * 64,
        )

    monkeypatch.setattr(
        binding_mod,
        "load_residual_prediction_run_by_id",
        _fake_load_prediction,
    )

    from unittest import mock

    with pytest.raises(Task10ReplayBindingInvalidError) as exc_info:
        await evaluate_replay_task10_binding(
            mock.Mock(),
            binding_context=binding_context,
            prediction_input=prediction_input,
            requested_policy=Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL,
        )
    assert exc_info.value.code == OrchestrationBlocker.TASK10_REPLAY_BINDING_INVALID.value
    assert "hash" in str(exc_info.value).lower()


# ── Test 8: identical replay inputs produce identical hashes ─────────────────


def test_identical_replay_inputs_produce_identical_hashes() -> None:
    """§11 #8 — given the same replay attempt id, node id, forecast cutoff,
    training cutoff, training manifest, model config, model code version,
    and policy version, the training_manifest_semantic_hash and the
    model_artifact_hash MUST be byte-identical.

    Awaiting Slice B (training manifest + identity plumbing + hash helpers)
    implementation. The schema-level fields for these hashes exist in
    ``ReplayTrainedModelIdentity`` today."""

    pytest.skip(
        "Deterministic training_manifest_semantic_hash + model_artifact_hash "
        "computation awaits Slice B implementation per TASK-012 design §6 "
        "identity model + §7 training manifest contract + §11 #8 + §12."
    )


# ── Test 9: changing model config changes the hashes ──────────────────────────


def test_changing_model_config_changes_hashes() -> None:
    """§11 #9 — changing only the model config (algorithm, hyperparameters,
    seed) MUST change both the model_config_hash AND the model_artifact_hash.
    Other identity fields held constant.

    Awaiting Slice B implementation."""

    pytest.skip(
        "Model config → model_config_hash + model_artifact_hash derivation "
        "awaits Slice B implementation per TASK-012 design §6 + §11 #9 + §12."
    )


# ── Test 10: JSON / manifest mismatch for replay-trained identity rejected ───


def test_json_manifest_mismatch_for_replay_trained_identity_is_rejected() -> None:
    """§11 #10 — a replay-trained artifact whose JSON-side identity fields
    disagree with the manifest-side identity fields MUST be rejected.

    Awaiting Slice D (prediction binding and artifact verification)
    implementation. The schema-level ``training_manifest_semantic_hash``
    field exists in ``ReplayTrainedModelIdentity`` today."""

    pytest.skip(
        "JSON / manifest identity mismatch rejection awaits Slice D "
        "implementation per TASK-012 design §5.4 upstream replay binding + "
        "§11 #10 + §12."
    )


# ── Test 11: replay-trained prediction carries model_policy string ───────────


def test_replay_trained_prediction_carries_model_policy_string() -> None:
    """§11 #11 — every prediction emitted by a replay_trained_model path MUST
    carry ``model_policy = "replay_trained_model"`` on the result record.

    Awaiting Slice D implementation. The Task10ModelPolicy enum value
    ``REPLAY_TRAINED_MODEL = "replay_trained_model"`` is already frozen."""

    # Enum-level pin (this is what Slice B/C/D will write into the
    # result record's model_policy field).
    assert Task10ModelPolicy.REPLAY_TRAINED_MODEL.value == "replay_trained_model"

    pytest.skip(
        "Replay-trained prediction result carrying model_policy = "
        "'replay_trained_model' awaits Slice D implementation per "
        "TASK-012 design §6 identity model + §11 #11 + §12."
    )


# ── Test 12: comparison runs produce separate prediction identities ─────────


def test_historical_and_replay_trained_comparison_runs_produce_separate_identities() -> None:
    """§11 #12 — when a comparison run evaluates both HISTORICALLY_AVAILABLE_MODEL
    and REPLAY_TRAINED_MODEL on the same scenario, the two prediction runs
    MUST carry separate prediction identities (separate prediction_run_id,
    separate prediction_hash, separate model_policy).

    Awaiting Slice D implementation. The mutual-exclusion rule is already
    frozen in §8.4 (no implicit coexistence in a single prediction run)."""

    # §8.4 schema-level mutual-exclusion pin: a single RollingNodeDefinition
    # MUST NOT carry both policy types — they are different policy tags
    # on the discriminated union ResolvedTask10ModelPolicy. The historical
    # branch uses HistoricalAvailableModelIdentity; the replay-trained
    # branch uses ReplayTrainedModelIdentity. Pydantic enforces the
    # discriminator at construction time.
    from pydantic import ValidationError

    from backend.app.rolling_backtest.schemas import (
        HistoricalAvailableModelIdentity,
        ReplayTrainedModelIdentity,
    )

    # HistoricalAvailableModelIdentity rejects the replay_trained_model
    # discriminator literal.
    with pytest.raises(ValidationError):
        HistoricalAvailableModelIdentity(
            policy=Task10ModelPolicy.REPLAY_TRAINED_MODEL,
            training_run_semantic_identity="c" * 64,
            artifact_semantic_identities=("d" * 64,),
            authority_visibility_identity="e" * 64,
        )

    # ReplayTrainedModelIdentity rejects the historical discriminator literal.
    with pytest.raises(ValidationError):
        ReplayTrainedModelIdentity(
            policy=Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL,
            training_cutoff_at=_utc(),
            allowed_training_season_ids=(2026,),
            validation_policy_version="task11-validation-v1",
            label_visibility_policy_version="task11-label-visibility-v1",
            feature_visibility_policy_version="task11-feature-visibility-v1",
            artifact_visibility_policy_version="task11-artifact-visibility-v1",
            training_manifest_semantic_hash="f" * 64,
        )

    # Per-run identity separation awaits Slice D.
    pytest.skip(
        "Per-comparison-run prediction identity separation awaits Slice D "
        "implementation per TASK-012 design §8.4 mutual-exclusion + §11 #12 + §12."
    )


# ── Slice A meta-checks ──────────────────────────────────────────────────────


# Explicit list of the 12 contract test names required by design §11,
# in order. Guards against accidental test additions or deletions without
# an explicit design-amendment round.
_DESIGN_SECTION_11_TEST_NAMES: tuple[str, ...] = (
    "test_replay_trained_model_remains_rejected_before_implementation_gate",
    "test_explicit_replay_trained_model_does_not_fall_back_to_historical",
    "test_training_rows_after_training_cutoff_at_are_excluded",
    "test_labels_with_post_cutoff_availability_are_excluded",
    "test_empty_training_set_produces_structured_blocker",
    "test_cross_run_model_artifact_substitution_is_rejected",
    "test_cross_run_task9_replay_binding_substitution_is_rejected",
    "test_identical_replay_inputs_produce_identical_hashes",
    "test_changing_model_config_changes_hashes",
    "test_json_manifest_mismatch_for_replay_trained_identity_is_rejected",
    "test_replay_trained_prediction_carries_model_policy_string",
    "test_historical_and_replay_trained_comparison_runs_produce_separate_identities",
)


def test_slice_a_test_count_matches_design_section_11() -> None:
    """Slice A meta-check: this module contains exactly the 12 contract tests
    required by design §11. Guards against accidental test additions or
    deletions without explicit design-amendment authorization."""

    defined_test_names = {
        name
        for name, obj in globals().items()
        if name.startswith("test_") and inspect.isfunction(obj) and obj.__module__ == __name__
    }
    missing = set(_DESIGN_SECTION_11_TEST_NAMES) - defined_test_names
    assert not missing, (
        f"Slice A contract test surface missing tests required by §11: {sorted(missing)}"
    )
    # Allow additional meta-check tests beyond the 12, but the 12 §11
    # tests MUST be present by name. Per §12, no production implementation
    # functions are allowed (covered by separate meta-check below).


def test_slice_a_module_does_not_define_replay_trained_model_implementation() -> None:
    """Slice A meta-check: per §12, this module MUST NOT introduce live
    training algorithm code, manifest hashing helpers, or replay
    artifact verifiers. The only definitions allowed are test functions
    + private helpers (leading underscore)."""

    # Reject any function defined in this module that is NOT a test or
    # a private helper (leading underscore).
    for name, obj in list(globals().items()):
        if not inspect.isfunction(obj):
            continue
        if obj.__module__ != __name__:
            continue
        if name.startswith("test_"):
            continue
        if name.startswith("_") and not name.startswith("__"):
            continue
        pytest.fail(
            f"Slice A contract tests must not introduce top-level "
            f"non-test definitions; found {name!r}. Per design §12."
        )
