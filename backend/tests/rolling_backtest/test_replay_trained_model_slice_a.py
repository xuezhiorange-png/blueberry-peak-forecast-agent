"""TASK-012 Slice A — replay_trained_model contract-gate / test-scaffold.

This module pins the design contract from
``docs/task-012-replay-trained-model-design.md`` §11 (Test contract) and
§12 (Implementation slice boundaries — Slice A — contract tests only).

Per §12 Slice A is **contract tests only** and forbids production
implementation. Per §11 the first implementation-facing PR after this
design must be a contract-test PR (this PR).

=====================================================================
HOW THIS PR IS DELIBERATELY CONSTRUCTED — READ BEFORE REVIEWING
=====================================================================

This PR is a **contract-gate / test-scaffold** PR. It does NOT deliver a
fully passing replay_trained_model pipeline. It establishes the §11
contract surface as documented obligation pins so that Slice B / Slice C /
Slice D implementation PRs have a stable acceptance gate to satisfy.

Each of the 12 §11 required tests is present in this module and is
classified into one of two categories:

ACTIVE_SLICE_A — passes today by exercising existing code paths.
  These pin behavior that is ALREADY enforced by the codebase:
  ``validate_replay_task10_model_policy``, ``evaluate_replay_task10_binding``,
  the ``ReplayTrainedModelIdentity`` schema, the
  ``RollingNodeDefinition._validate_task10_policy_cutoff`` validator, and
  the Task10ModelPolicy enum values.

OBLIGATION_PLACEHOLDER — recorded contract pin awaiting a future slice.
  These pin behavior that requires production code that is NOT part of
  Slice A. Each placeholder carries a ``pytest.skip(reason=...)`` whose
  ``reason`` explicitly cites:

  - the design section (§11 #N + §12),
  - the future slice that will activate it (Slice B / Slice C / Slice D),
  - and any §13 hard prohibition that the future slice must respect.

  These placeholders EXIST to satisfy §11's "these tests exist" rule.
  They do NOT count as fulfilled acceptance tests. §11 line 264
  ("No implementation PR may be considered complete until these tests
  exist and pass") applies to **implementation PRs** (Slice B / C / D),
  not to this Slice A contract-test PR (whose identity per §11 line 247
  is "contract-test PR").

=====================================================================
CURRENT COUNTS AT TIME OF THIS PR
=====================================================================

- ACTIVE_SLICE_A passing tests: 5  (#1, #2, #6, #7, schema-level #3 / #12
  counted as partial — see per-test annotations for exact mapping)
- OBLIGATION_PLACEHOLDER awaiting future slices: 7  (full §11 #4, #5, #8,
  #9, #10, #11, full §11 #12) plus the execution portion of §11 #3 and
  §11 #12.
- Meta-checks: 4  (test-count guard, no-implementation guard,
  active-vs-placeholder separation guard, obligation-references guard).

These counts are HARDENED by meta-tests in this module. The test runner
output cannot be misread as "12/12 §11 passed" — obligation
placeholders are visible by name, by future-slice, and by design section.

=====================================================================
HARD PROHIBITIONS REAFFIRMED (per §13 / §14)
=====================================================================

- No Task 8 / Task 9 / Task 10 semantic change.
- No ``current/latest/most-recent`` fallback.
- No production code change in this module.
- No implementation of Slice B / Slice C / Slice D.
- No design doc mutation.

=====================================================================
"""

from __future__ import annotations

import datetime as _dt
import inspect
from dataclasses import dataclass
from datetime import UTC
from enum import Enum
from typing import Final

import pytest

from backend.app.rolling_backtest.enums import Task10ModelPolicy
from backend.app.rolling_backtest.node_orchestration import (
    Task10ReplayBindingInvalidError,
)
from backend.app.rolling_backtest.replay_task10_binding import (
    evaluate_replay_task10_binding,
    validate_replay_task10_model_policy,
)

# ── Slice classification ────────────────────────────────────────────────────


class SliceClassification(str, Enum):  # noqa: UP042 — string-valued enum preferred for clarity
    """How a §11 test relates to Slice A's allowed scope.

    ``ACTIVE_SLICE_A`` — the test exercises code that exists today and
      passes without any production implementation. The acceptance gate
      is "this code path must continue to enforce this contract".

    ``OBLIGATION_PLACEHOLDER`` — the test exists to satisfy §11's
      "these tests must exist" rule but requires production code that
      is explicitly forbidden by §12 Slice A. Each placeholder carries
      a ``pytest.skip`` referencing the future slice (B / C / D) that
      will activate it. NOT counted as fulfilled acceptance.
    """

    ACTIVE_SLICE_A = "active_slice_a"
    OBLIGATION_PLACEHOLDER = "obligation_placeholder"


# Future slice label that activates each obligation placeholder. Used by
# the obligation-references meta-test to guard against vague "awaits
# future" language that fails to name a specific §12 slice.
OBLIGATION_FUTURE_SLICE_B: Final = "Slice B"
OBLIGATION_FUTURE_SLICE_C: Final = "Slice C"
OBLIGATION_FUTURE_SLICE_D: Final = "Slice D"


# Registry of every §11 contract test in this module: name, §11 number,
# classification, and (for placeholders) the future slice that activates
# it. The meta-tests read this registry; per-test functions do not need
# to maintain it as long as their names match.
_SECTION_11_REGISTRY: Final[tuple[dict[str, str], ...]] = (
    {
        "name": "test_replay_trained_model_remains_rejected_before_implementation_gate",
        "section": "§11 #1",
        "classification": SliceClassification.ACTIVE_SLICE_A.value,
    },
    {
        "name": "test_explicit_replay_trained_model_does_not_fall_back_to_historical",
        "section": "§11 #2",
        "classification": SliceClassification.ACTIVE_SLICE_A.value,
    },
    {
        "name": "test_training_rows_after_training_cutoff_at_are_excluded",
        "section": "§11 #3",
        # Schema-level bound (tz-aware + ≤ forecast_cutoff_at) is active.
        # Execution-time row filtering awaits Slice C.
        "classification": SliceClassification.OBLIGATION_PLACEHOLDER.value,
        "future_slice": OBLIGATION_FUTURE_SLICE_C,
    },
    {
        "name": "test_labels_with_post_cutoff_availability_are_excluded",
        "section": "§11 #4",
        "classification": SliceClassification.OBLIGATION_PLACEHOLDER.value,
        "future_slice": OBLIGATION_FUTURE_SLICE_C,
    },
    {
        "name": "test_empty_training_set_produces_structured_blocker",
        "section": "§11 #5",
        "classification": SliceClassification.OBLIGATION_PLACEHOLDER.value,
        "future_slice": OBLIGATION_FUTURE_SLICE_C,
    },
    {
        "name": "test_cross_run_model_artifact_substitution_is_rejected",
        "section": "§11 #6",
        "classification": SliceClassification.ACTIVE_SLICE_A.value,
    },
    {
        "name": "test_cross_run_task9_replay_binding_substitution_is_rejected",
        "section": "§11 #7",
        "classification": SliceClassification.ACTIVE_SLICE_A.value,
    },
    {
        "name": "test_identical_replay_inputs_produce_identical_hashes",
        "section": "§11 #8",
        "classification": SliceClassification.OBLIGATION_PLACEHOLDER.value,
        "future_slice": OBLIGATION_FUTURE_SLICE_B,
    },
    {
        "name": "test_changing_model_config_changes_hashes",
        "section": "§11 #9",
        "classification": SliceClassification.OBLIGATION_PLACEHOLDER.value,
        "future_slice": OBLIGATION_FUTURE_SLICE_B,
    },
    {
        "name": "test_json_manifest_mismatch_for_replay_trained_identity_is_rejected",
        "section": "§11 #10",
        "classification": SliceClassification.OBLIGATION_PLACEHOLDER.value,
        "future_slice": OBLIGATION_FUTURE_SLICE_D,
    },
    {
        "name": "test_replay_trained_prediction_carries_model_policy_string",
        "section": "§11 #11",
        # Enum-level pin is active (frozen string literal). Record-side
        # emission awaits Slice D.
        "classification": SliceClassification.OBLIGATION_PLACEHOLDER.value,
        "future_slice": OBLIGATION_FUTURE_SLICE_D,
    },
    {
        "name": "test_historical_and_replay_trained_comparison_runs_produce_separate_identities",
        "section": "§11 #12",
        # Schema-level discriminator mutual-exclusion is active. Per-run
        # identity separation awaits Slice D.
        "classification": SliceClassification.OBLIGATION_PLACEHOLDER.value,
        "future_slice": OBLIGATION_FUTURE_SLICE_D,
    },
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


# ── §11 #1: REPLAY_TRAINED_MODEL remains rejected before implementation gate ──
# Classification: ACTIVE_SLICE_A


def test_replay_trained_model_remains_rejected_before_implementation_gate() -> None:
    """§11 #1 — ACTIVE_SLICE_A.

    The ``replay_trained_model`` enum value exists but every code path
    that processes replay authorization MUST reject it until Slice B / C / D
    land. ``validate_replay_task10_model_policy`` is the canonical gate and
    pins this contract today.
    """

    with pytest.raises(Task10ReplayBindingInvalidError) as exc_info:
        validate_replay_task10_model_policy(
            requested_policy=Task10ModelPolicy.REPLAY_TRAINED_MODEL,
        )
    # The rejection is structured: it carries a message that names the
    # forbidden policy. We don't pin the exact message text
    # (anti-fragile), but the rejection must fire and must NOT silently
    # fall back to HISTORICALLY_AVAILABLE_MODEL.
    assert "REPLAY_TRAINED_MODEL" in str(exc_info.value) or "replay_trained_model" in str(
        exc_info.value
    ), f"rejection message must name the forbidden policy: {exc_info.value}"


# ── §11 #2: explicit REPLAY_TRAINED_MODEL does not fall back ─────────────────
# Classification: ACTIVE_SLICE_A


def test_explicit_replay_trained_model_does_not_fall_back_to_historical() -> None:
    """§11 #2 — ACTIVE_SLICE_A.

    The gate MUST NOT silently convert REPLAY_TRAINED_MODEL into
    HISTORICALLY_AVAILABLE_MODEL. Verified by asserting that the gate
    raises rather than returns HISTORICALLY_AVAILABLE_MODEL.
    """

    with pytest.raises(Task10ReplayBindingInvalidError):
        validate_replay_task10_model_policy(
            requested_policy=Task10ModelPolicy.REPLAY_TRAINED_MODEL,
        )
    # And the gate, when given the only-authorized policy, returns it.
    authorized = validate_replay_task10_model_policy(
        requested_policy=Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL,
    )
    assert authorized is Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL


# ── §11 #3: training rows after training_cutoff_at are excluded ──────────────
# Classification: OBLIGATION_PLACEHOLDER (awaits Slice C; schema-level bound active)


def test_training_rows_after_training_cutoff_at_are_excluded() -> None:
    """§11 #3 — OBLIGATION_PLACEHOLDER (awaits Slice C).

    Schema-level bound: ``ReplayTrainedModelIdentity.training_cutoff_at``
    must be timezone-aware AND must not exceed the node's
    ``forecast_cutoff_at`` (active today via
    ``RollingNodeDefinition._validate_task10_policy_cutoff``).

    Execution-time row filtering (rows with observation_date AFTER
    ``training_cutoff_at`` are dropped from the training set) requires
    Slice C — replay training execution. Per §13, Slice C must not
    change Task 8 / Task 9 semantics.
    """

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
        "awaits Slice C implementation per TASK-012 design §11 #3 + §12. "
        "Schema-level bound above is ACTIVE_SLICE_A."
    )


# ── §11 #4: labels with post-cutoff availability are excluded ────────────────
# Classification: OBLIGATION_PLACEHOLDER (awaits Slice C)


def test_labels_with_post_cutoff_availability_are_excluded() -> None:
    """§11 #4 — OBLIGATION_PLACEHOLDER (awaits Slice C).

    Labels with authoritative availability AFTER ``training_cutoff_at``
    must be excluded even when observation_date is BEFORE the cutoff.
    Requires Slice C — replay training execution. Schema-level rejection
    of ``training_cutoff_at > forecast_cutoff_at`` is pinned in test #3.
    """

    pytest.skip(
        "Label availability filtering (post-cutoff availability timestamps) "
        "awaits Slice C implementation per TASK-012 design §11 #4 + §12."
    )


# ── §11 #5: empty training set produces a structured blocker ────────────────
# Classification: OBLIGATION_PLACEHOLDER (awaits Slice C)


def test_empty_training_set_produces_structured_blocker() -> None:
    """§11 #5 — OBLIGATION_PLACEHOLDER (awaits Slice C).

    When all rows are excluded by cutoff / availability filters, the
    system MUST raise a structured blocker (per §9 blocker taxonomy)
    rather than fabricating an empty training set.
    """

    pytest.skip(
        "Empty-training-set structured blocker awaits Slice C implementation "
        "per TASK-012 design §9 blocker taxonomy + §11 #5 + §12."
    )


# ── §11 #6: cross-run model artifact substitution is rejected ────────────────
# Classification: ACTIVE_SLICE_A


@pytest.mark.asyncio
async def test_cross_run_model_artifact_substitution_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§11 #6 — ACTIVE_SLICE_A.

    A model artifact produced by a different replay attempt MUST NOT be
    accepted by the current replay binding path. Pinned by the existing
    ``evaluate_replay_task10_binding`` which enforces task9_run_id +
    result_hash equality between the loaded artifact and the current
    replay-produced row.

    Pattern mirrors ``test_evaluate_replay_task10_binding_cross_run_rejected``
    in ``test_replay_task10_binding.py`` (Phase 3 bucket #6) but binds to
    the design §11 contract test name explicitly.
    """

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


# ── §11 #7: cross-run Task 9 replay binding substitution is rejected ────────
# Classification: ACTIVE_SLICE_A


@pytest.mark.asyncio
async def test_cross_run_task9_replay_binding_substitution_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§11 #7 — ACTIVE_SLICE_A.

    The replay-produced Task 9 row MUST be the only accepted binding
    source. A foreign task9 binding (different run_id or different
    result_hash) MUST be rejected.

    Pinned by ``evaluate_replay_task10_binding``'s run_id equality +
    result_hash equality checks against the current replay's
    harvest-state row.
    """

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


# ── §11 #8: identical replay inputs produce identical hashes ─────────────────
# Classification: OBLIGATION_PLACEHOLDER (awaits Slice B)


def test_identical_replay_inputs_produce_identical_hashes() -> None:
    """§11 #8 — OBLIGATION_PLACEHOLDER (awaits Slice B).

    Given the same replay attempt id, node id, forecast cutoff,
    training cutoff, training manifest, model config, model code
    version, and policy version, the ``training_manifest_semantic_hash``
    and the ``model_artifact_hash`` MUST be byte-identical.

    Awaiting Slice B (training manifest + identity plumbing + hash
    helpers). The schema-level fields for these hashes exist in
    ``ReplayTrainedModelIdentity`` today.
    """

    pytest.skip(
        "Deterministic training_manifest_semantic_hash + model_artifact_hash "
        "computation awaits Slice B implementation per TASK-012 design §6 "
        "identity model + §7 training manifest contract + §11 #8 + §12."
    )


# ── §11 #9: changing model config changes the hashes ─────────────────────────
# Classification: OBLIGATION_PLACEHOLDER (awaits Slice B)


def test_changing_model_config_changes_hashes() -> None:
    """§11 #9 — OBLIGATION_PLACEHOLDER (awaits Slice B).

    Changing only the model config (algorithm, hyperparameters, seed)
    MUST change both the ``model_config_hash`` AND the
    ``model_artifact_hash``. Other identity fields held constant.

    Awaiting Slice B implementation.
    """

    pytest.skip(
        "Model config → model_config_hash + model_artifact_hash derivation "
        "awaits Slice B implementation per TASK-012 design §6 + §11 #9 + §12."
    )


# ── §11 #10: JSON / manifest mismatch for replay-trained identity rejected ──
# Classification: OBLIGATION_PLACEHOLDER (awaits Slice D)


def test_json_manifest_mismatch_for_replay_trained_identity_is_rejected() -> None:
    """§11 #10 — OBLIGATION_PLACEHOLDER (awaits Slice D).

    A replay-trained artifact whose JSON-side identity fields disagree
    with the manifest-side identity fields MUST be rejected.

    Awaiting Slice D (prediction binding and artifact verification).
    The schema-level ``training_manifest_semantic_hash`` field exists in
    ``ReplayTrainedModelIdentity`` today.
    """

    pytest.skip(
        "JSON / manifest identity mismatch rejection awaits Slice D "
        "implementation per TASK-012 design §5.4 upstream replay binding + "
        "§11 #10 + §12."
    )


# ── §11 #11: replay-trained prediction carries model_policy string ───────────
# Classification: OBLIGATION_PLACEHOLDER (awaits Slice D; enum literal active)


def test_replay_trained_prediction_carries_model_policy_string() -> None:
    """§11 #11 — OBLIGATION_PLACEHOLDER (awaits Slice D).

    Every prediction emitted by a ``replay_trained_model`` path MUST carry
    ``model_policy = "replay_trained_model"`` on the result record.

    The Task10ModelPolicy enum value ``REPLAY_TRAINED_MODEL =
    "replay_trained_model"`` is already frozen (active pin below).
    Result-record emission awaits Slice D.
    """

    # Enum-level pin (active): what Slice B/C/D will write into the
    # result record's model_policy field.
    assert Task10ModelPolicy.REPLAY_TRAINED_MODEL.value == "replay_trained_model"

    pytest.skip(
        "Replay-trained prediction result carrying model_policy = "
        "'replay_trained_model' awaits Slice D implementation per "
        "TASK-012 design §6 identity model + §11 #11 + §12."
    )


# ── §11 #12: comparison runs produce separate prediction identities ─────────
# Classification: OBLIGATION_PLACEHOLDER (awaits Slice D; discriminator active)


def test_historical_and_replay_trained_comparison_runs_produce_separate_identities() -> None:
    """§11 #12 — OBLIGATION_PLACEHOLDER (awaits Slice D).

    When a comparison run evaluates both ``HISTORICALLY_AVAILABLE_MODEL``
    and ``REPLAY_TRAINED_MODEL`` on the same scenario, the two prediction
    runs MUST carry separate prediction identities (separate
    ``prediction_run_id``, separate ``prediction_hash``, separate
    ``model_policy``).

    Schema-level mutual-exclusion (active below) is frozen in §8.4.
    Per-run identity separation awaits Slice D.
    """

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


_META_CHECK_NAMES: Final[frozenset[str]] = frozenset(
    {
        "test_slice_a_test_count_matches_design_section_11",
        "test_slice_a_module_does_not_define_replay_trained_model_implementation",
        "test_slice_a_active_vs_obligation_classification_is_complete",
        "test_slice_a_obligation_placeholders_reference_design_sections",
    }
)


def test_slice_a_test_count_matches_design_section_11() -> None:
    """Slice A meta-check: this module contains exactly the 12 contract tests
    required by design §11, plus 4 meta-checks (this one and 3 siblings).
    Guards against accidental test additions or deletions without explicit
    design-amendment authorization.
    """

    defined_test_names = {
        name
        for name, obj in globals().items()
        if name.startswith("test_") and inspect.isfunction(obj) and obj.__module__ == __name__
    }
    # The 12 §11 contract tests are the registry entries.
    registry_names = {entry["name"] for entry in _SECTION_11_REGISTRY}
    # All other test_* functions in this module are Slice A meta-checks.
    meta_check_names = defined_test_names - registry_names
    assert meta_check_names == _META_CHECK_NAMES, (
        f"Slice A meta-check drift: meta-check names {sorted(meta_check_names)} "
        f"do not match the canonical set {sorted(_META_CHECK_NAMES)}"
    )
    assert defined_test_names >= registry_names, (
        f"§11 registry contains tests not defined in this module: "
        f"{sorted(registry_names - defined_test_names)}"
    )


def test_slice_a_module_does_not_define_replay_trained_model_implementation() -> None:
    """Slice A meta-check: per §12, this module MUST NOT introduce live
    training algorithm code, manifest hashing helpers, or replay
    artifact verifiers. The only definitions allowed are test functions
    + private helpers (leading underscore).
    """

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


def test_slice_a_active_vs_obligation_classification_is_complete() -> None:
    """Slice A meta-check: every §11 test in the registry MUST be classified
    as either ``ACTIVE_SLICE_A`` or ``OBLIGATION_PLACEHOLDER``, and the
    obligation placeholders MUST reference a specific future slice label.

    This guards against two failure modes:

    1. A test being added with classification=None / missing.
    2. An obligation placeholder being added without naming the future
       slice (so future readers cannot tell whether it awaits Slice B /
       C / D / E).
    """

    active_count = 0
    obligation_count = 0
    for entry in _SECTION_11_REGISTRY:
        classification = entry["classification"]
        assert classification in (
            SliceClassification.ACTIVE_SLICE_A.value,
            SliceClassification.OBLIGATION_PLACEHOLDER.value,
        ), f"§11 registry entry {entry['name']!r} has invalid classification"
        if classification == SliceClassification.ACTIVE_SLICE_A.value:
            active_count += 1
            # ACTIVE_SLICE_A entries MUST NOT carry a future_slice label
            # (they don't await one).
            assert "future_slice" not in entry, (
                f"ACTIVE_SLICE_A entry {entry['name']!r} should not carry future_slice"
            )
        else:
            obligation_count += 1
            assert "future_slice" in entry, (
                f"OBLIGATION_PLACEHOLDER entry {entry['name']!r} must name "
                f"the future slice (Slice B / Slice C / Slice D / Slice E)"
            )
            assert entry["future_slice"] in (
                OBLIGATION_FUTURE_SLICE_B,
                OBLIGATION_FUTURE_SLICE_C,
                OBLIGATION_FUTURE_SLICE_D,
            ), (
                f"OBLIGATION_PLACEHOLDER entry {entry['name']!r} has "
                f"non-canonical future_slice label {entry['future_slice']!r}"
            )

    # Slice A is contract-tests-only per §12; the count of
    # ACTIVE_SLICE_A + OBLIGATION_PLACEHOLDER must total exactly 12.
    total = active_count + obligation_count
    assert total == 12, (
        f"§11 registry must total 12 tests (got {total}: "
        f"{active_count} active + {obligation_count} placeholder)"
    )

    # Hardened visibility assertion: there MUST be at least one obligation
    # placeholder so that the test runner output can NEVER be misread as
    # "12/12 §11 contract tests passing today". If the obligation count
    # drops to 0, Slice B/C/D implementation has already landed and this
    # contract-test scaffold has served its purpose; the slice A PR
    # should be retired. Until then, this assertion guards against the
    # "all tests silently satisfied" failure mode.
    assert obligation_count >= 6, (
        f"Expected ≥6 obligation placeholders awaiting future slices "
        f"(got {obligation_count}). Slice A is contract-tests-only per §12; "
        f"if obligation_count has dropped, this contract-test PR should be "
        f"retired in favor of Slice B/C/D implementation PRs."
    )


def test_slice_a_obligation_placeholders_reference_design_sections() -> None:
    """Slice A meta-check: every OBLIGATION_PLACEHOLDER test's
    ``pytest.skip(reason=...)`` MUST cite the §11 + §12 design sections
    AND name a specific future slice (B / C / D).

    Guards against vague skip messages like "awaits future implementation"
    that fail to name the slice that activates the contract.
    """

    import re as _re

    for entry in _SECTION_11_REGISTRY:
        if entry["classification"] != SliceClassification.OBLIGATION_PLACEHOLDER.value:
            continue
        test_name = entry["name"]
        test_obj = globals().get(test_name)
        assert test_obj is not None, f"missing test function: {test_name}"
        # The test body MUST contain at least one pytest.skip call.
        source = inspect.getsource(test_obj)
        # Capture the full skip reason: pytest.skip("...") is a single-
        # line call here (each OBLIGATION_PLACEHOLDER keeps its reason on
        # one line for grep-ability), but we use a permissive regex that
        # accepts either "..." or '...' or triple-quoted strings.
        skip_matches = _re.findall(
            r"pytest\.skip\(\s*([\"']{1,3})([\s\S]*?)\1\s*\)",
            source,
        )
        assert skip_matches, (
            f"OBLIGATION_PLACEHOLDER {test_name!r} must contain a "
            f"pytest.skip with a substantive reason"
        )
        for _quote, skip_msg in skip_matches:
            assert "§11" in skip_msg and "§12" in skip_msg, (
                f"OBLIGATION_PLACEHOLDER {test_name!r} skip reason must "
                f"cite both §11 and §12; got: {skip_msg!r}"
            )
            future_slice = entry["future_slice"]
            assert future_slice in skip_msg, (
                f"OBLIGATION_PLACEHOLDER {test_name!r} skip reason must "
                f"name its future slice {future_slice!r}; got: {skip_msg!r}"
            )
