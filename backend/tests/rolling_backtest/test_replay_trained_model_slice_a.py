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

- ACTIVE_SLICE_A passing tests: 4  (#1, #2, #6, #7)
- ACTIVE_SLICE_B passing tests: 2  (#8, #9 — landed in TASK-012 Slice B)
- ACTIVE_SLICE_C passing tests: 3  (#3 execution portion, #4, #5 —
  landed in TASK-012 Slice C)
- ACTIVE_SLICE_D passing tests: 3  (#10, #11, #12 — landed in
  TASK-012 Slice D)
- OBLIGATION_PLACEHOLDER awaiting future slices: 0  (the §11
  contract surface is complete; Slice E is API/CLI and lives outside
  the §11 contract-test surface per §12 Slice E)
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

    ``ACTIVE_SLICE_B`` — the test exercises TASK-012 Slice B production
      code (manifest schema, identity projection, deterministic hash
      helpers, structured blockers) and passes once Slice B is
      implemented.

    ``OBLIGATION_PLACEHOLDER`` — the test exists to satisfy §11's
      "these tests must exist" rule but requires production code that
      is explicitly forbidden by §12 Slice A. Each placeholder carries
      a ``pytest.skip`` referencing the future slice (B / C / D) that
      will activate it. NOT counted as fulfilled acceptance.
    """

    ACTIVE_SLICE_A = "active_slice_a"
    ACTIVE_SLICE_B = "active_slice_b"
    ACTIVE_SLICE_C = "active_slice_c"
    ACTIVE_SLICE_D = "active_slice_d"
    OBLIGATION_PLACEHOLDER = "obligation_placeholder"


# Future slice label that activates each remaining obligation placeholder.
# Used by the obligation-references meta-test to guard against vague
# "awaits future" language that fails to name a specific §12 slice.
# (Slice B is no longer a future-slice — it has landed — so
# OBLIGATION_FUTURE_SLICE_B was removed in the Slice B reclassification.)
# (Slice C is no longer a future-slice — it has landed — so the
# OBLIGATION_FUTURE_SLICE_C label is retained only for backward
# compatibility of the OBLIGATION_PLACEHOLDER future_slice assertion
# tuple, but no entry currently references it.)
# (Slice D is no longer a future-slice — it has landed in TASK-012
# Slice D — so the OBLIGATION_FUTURE_SLICE_D label is retained only
# for backward compatibility of the OBLIGATION_PLACEHOLDER future_slice
# assertion tuple, but no entry currently references it.)
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
        # Execution-time row filtering was reclassified to ACTIVE_SLICE_C
        # once Slice C deterministic cutoff filter landed.
        "classification": SliceClassification.ACTIVE_SLICE_C.value,
    },
    {
        "name": "test_labels_with_post_cutoff_availability_are_excluded",
        "section": "§11 #4",
        "classification": SliceClassification.ACTIVE_SLICE_C.value,
    },
    {
        "name": "test_empty_training_set_produces_structured_blocker",
        "section": "§11 #5",
        "classification": SliceClassification.ACTIVE_SLICE_C.value,
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
        # Reclassified to ACTIVE_SLICE_B once Slice B deterministic hash
        # helpers landed. Pre-Slice B this entry was an OBLIGATION_PLACEHOLDER.
        "classification": SliceClassification.ACTIVE_SLICE_B.value,
    },
    {
        "name": "test_changing_model_config_changes_hashes",
        "section": "§11 #9",
        # Reclassified to ACTIVE_SLICE_B once Slice B deterministic hash
        # helpers landed. Pre-Slice B this entry was an OBLIGATION_PLACEHOLDER.
        "classification": SliceClassification.ACTIVE_SLICE_B.value,
    },
    {
        "name": "test_json_manifest_mismatch_for_replay_trained_identity_is_rejected",
        "section": "§11 #10",
        # Reclassified to ACTIVE_SLICE_D once Slice D prediction binding
        # + artifact identity verification landed.
        "classification": SliceClassification.ACTIVE_SLICE_D.value,
    },
    {
        "name": "test_replay_trained_prediction_carries_model_policy_string",
        "section": "§11 #11",
        # Reclassified to ACTIVE_SLICE_D once Slice D prediction binding
        # + result-record model_policy emission landed.
        "classification": SliceClassification.ACTIVE_SLICE_D.value,
    },
    {
        "name": "test_historical_and_replay_trained_comparison_runs_produce_separate_identities",
        "section": "§11 #12",
        # Reclassified to ACTIVE_SLICE_D once Slice D per-run identity
        # separation landed.
        "classification": SliceClassification.ACTIVE_SLICE_D.value,
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
# Classification: ACTIVE_SLICE_C (Slice C landed)


def test_training_rows_after_training_cutoff_at_are_excluded() -> None:
    """§11 #3 — ACTIVE_SLICE_C (Slice C landed).

    Schema-level bound: ``ReplayTrainedModelIdentity.training_cutoff_at``
    must be timezone-aware AND must not exceed the node's
    ``forecast_cutoff_at`` (active today via
    ``RollingNodeDefinition._validate_task10_policy_cutoff``).

    Execution-time row filtering: rows with ``observation_date`` strictly
    greater than ``training_cutoff_at`` are dropped from the training
    set. Implemented by ``filter_training_rows_by_cutoff`` in
    ``backend.app.rolling_backtest.replay_trained_filtering``. Per §13,
    Slice C must not change Task 8 / Task 9 semantics — the filter is
    a pure function operating on caller-supplied rows; it never
    touches persistence / re-trains Task 8 curves / re-runs Task 9.
    """

    from datetime import date as _date

    from backend.app.rolling_backtest.replay_trained_filtering import (
        FilteredTrainingRow,
        filter_training_rows_by_cutoff,
    )
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

    # Execution-time: rows after the cutoff are dropped; rows equal to
    # the cutoff are KEPT (inclusive cutoff per §3 binding gate).
    rows = (
        FilteredTrainingRow(_date(2024, 6, 1), 1.0),
        FilteredTrainingRow(_date(2025, 6, 1), 2.0),
        FilteredTrainingRow(_date(2026, 3, 14), 3.0),  # == cutoff, KEPT
        FilteredTrainingRow(_date(2026, 3, 15), 4.0),  # > cutoff, dropped
    )
    kept = filter_training_rows_by_cutoff(rows, training_cutoff_at=_date(2026, 3, 14))
    assert [r.value for r in kept] == [1.0, 2.0, 3.0], (
        f"cutoff filter must drop post-cutoff rows in deterministic order; got "
        f"{[r.value for r in kept]}"
    )


# ── §11 #4: labels with post-cutoff availability are excluded ────────────────
# Classification: ACTIVE_SLICE_C (Slice C landed)


def test_labels_with_post_cutoff_availability_are_excluded() -> None:
    """§11 #4 — ACTIVE_SLICE_C (Slice C landed).

    Labels whose authoritative ``label_availability_date`` is strictly
    greater than ``label_availability_cutoff_at`` are excluded even
    when ``observation_date`` is BEFORE the cutoff. Implemented by
    ``filter_labels_by_availability_cutoff`` in
    ``backend.app.rolling_backtest.replay_trained_filtering``. Schema-
    level rejection of ``training_cutoff_at > forecast_cutoff_at`` is
    pinned in test #3.
    """

    from datetime import date as _date

    from backend.app.rolling_backtest.replay_trained_filtering import (
        FilteredLabelRow,
        filter_labels_by_availability_cutoff,
    )

    rows = (
        # observation before cutoff AND label_availability before cutoff — KEPT.
        FilteredLabelRow(_date(2024, 1, 1), _date(2024, 1, 5), 1.0),
        # observation after training_cutoff but label_availability == cutoff — KEPT.
        FilteredLabelRow(_date(2024, 6, 1), _date(2024, 12, 31), 2.0),
        # observation before cutoff BUT label_availability after cutoff — DROPPED.
        FilteredLabelRow(_date(2024, 1, 1), _date(2025, 1, 5), 3.0),
    )
    kept = filter_labels_by_availability_cutoff(
        rows, label_availability_cutoff_at=_date(2024, 12, 31)
    )
    assert [r.value for r in kept] == [1.0, 2.0], (
        f"label availability filter must drop post-cutoff labels in "
        f"deterministic order; got {[r.value for r in kept]}"
    )


# ── §11 #5: empty training set produces a structured blocker ────────────────
# Classification: ACTIVE_SLICE_C (Slice C landed)


def test_empty_training_set_produces_structured_blocker() -> None:
    """§11 #5 — ACTIVE_SLICE_C (Slice C landed).

    When all rows are excluded by cutoff / availability filters, the
    system MUST raise a structured blocker (per §9 blocker taxonomy)
    rather than fabricating an empty training set. Implemented by
    ``require_non_empty_training_rows`` +
    :class:`TrainingRowsEmptyError` in
    ``backend.app.rolling_backtest.replay_trained_filtering``. The
    blocker is ``OrchestrationBlocker.TASK12_TRAINING_ROWS_EMPTY``
    (added in Slice C).
    """

    from datetime import date as _date

    from backend.app.rolling_backtest.orchestration import OrchestrationBlocker
    from backend.app.rolling_backtest.replay_trained_filtering import (
        FilteredTrainingRow,
        require_non_empty_training_rows,
    )

    empty_filtered: tuple[FilteredTrainingRow, ...] = ()
    with pytest.raises(Exception) as excinfo:
        require_non_empty_training_rows(
            empty_filtered,
            training_cutoff_at=_date(2026, 3, 14),
            candidate_row_count=5,
        )
    # The exception MUST carry the canonical blocker enum value, not an
    # ad-hoc string. §9 blocker taxonomy + §11 #5 obligation pin.
    assert getattr(excinfo.value, "blocker_code", None) == (
        OrchestrationBlocker.TASK12_TRAINING_ROWS_EMPTY.value
    ), (
        f"empty training set must raise structured blocker "
        f"{OrchestrationBlocker.TASK12_TRAINING_ROWS_EMPTY.value}; "
        f"got blocker_code={getattr(excinfo.value, 'blocker_code', None)!r}"
    )
    # Deterministic payload must carry cutoff + counts for §7 hash traceability.
    assert getattr(excinfo.value, "training_cutoff_at", None) == _date(2026, 3, 14)
    assert getattr(excinfo.value, "candidate_row_count", None) == 5
    assert getattr(excinfo.value, "kept_row_count", None) == 0
    assert getattr(excinfo.value, "payload", None) is not None


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
# Classification: ACTIVE_SLICE_B


def test_identical_replay_inputs_produce_identical_hashes() -> None:
    """§11 #8 — ACTIVE_SLICE_B (Slice B landed).

    Given the same replay attempt id, node id, forecast cutoff,
    training cutoff, training manifest, model config, model code
    version, and policy version, the ``training_manifest_semantic_hash``
    and the ``model_artifact_hash`` MUST be byte-identical.

    Exercised via ``compute_training_manifest_hash``,
    ``compute_model_config_hash``, ``compute_model_artifact_hash``, and
    ``project_replay_trained_identity`` in
    :mod:`backend.app.rolling_backtest.replay_trained_identity` (Slice B
    deterministic hash helpers per design §6 + §7).
    """

    from backend.app.rolling_backtest.replay_trained_identity import (
        ModelConfigPayload,
        TrainingManifestPayload,
        compute_model_artifact_hash,
        compute_model_config_hash,
        compute_training_manifest_hash,
        project_replay_trained_identity,
    )

    forecast_cutoff = _utc(2026, 3, 15, hour=12)
    training_cutoff = _utc(2026, 3, 14, hour=12)
    manifest = TrainingManifestPayload(
        replay_attempt_id="att-8",
        replay_node_id="node-8",
        scenario_id="scn-8",
        forecast_cutoff_at=forecast_cutoff,
        training_cutoff_at=training_cutoff,
        allowed_training_season_ids=(2025,),
        feature_visibility_policy_version="task11-visibility-v1",
        label_visibility_policy_version="task11-visibility-v1",
        artifact_visibility_policy_version="task11-visibility-v1",
        validation_policy_version="task11-validation-v1",
        training_dataset_hash="1" * 64,
        task8_curve_identity=None,
        task9_replay_binding_identity=None,
        row_count=10,
        excluded_row_count=1,
    )
    config = ModelConfigPayload(
        algorithm_family="slice_b_8",
        hyperparameters={"lr": "0.001"},
        random_seed=42,
        deterministic_serialization_version="slice-b-v1",
    )

    # §11 #8 contract: identical inputs → byte-identical hashes.
    manifest_hash_a = compute_training_manifest_hash(manifest)
    manifest_hash_b = compute_training_manifest_hash(manifest)
    assert manifest_hash_a == manifest_hash_b
    assert len(manifest_hash_a) == 64 and all(c in "0123456789abcdef" for c in manifest_hash_a)

    config_hash_a = compute_model_config_hash(config)
    config_hash_b = compute_model_config_hash(config)
    assert config_hash_a == config_hash_b
    assert len(config_hash_a) == 64

    artifact_hash_a = compute_model_artifact_hash(
        training_manifest_hash=manifest_hash_a,
        model_config_hash=config_hash_a,
        model_code_version="slice-b-code-v1",
    )
    artifact_hash_b = compute_model_artifact_hash(
        training_manifest_hash=manifest_hash_b,
        model_config_hash=config_hash_b,
        model_code_version="slice-b-code-v1",
    )
    assert artifact_hash_a == artifact_hash_b
    assert len(artifact_hash_a) == 64

    # Identity projection also stable.
    projection_a = project_replay_trained_identity(
        manifest=manifest,
        config=config,
        model_code_version="slice-b-code-v1",
        task12_policy_version="slice-b-policy-v1",
    )
    projection_b = project_replay_trained_identity(
        manifest=manifest,
        config=config,
        model_code_version="slice-b-code-v1",
        task12_policy_version="slice-b-policy-v1",
    )
    assert projection_a.training_manifest_hash == manifest_hash_a
    assert projection_b.training_manifest_hash == manifest_hash_a
    assert projection_a.model_artifact_hash == artifact_hash_a
    assert projection_b.model_artifact_hash == artifact_hash_a


# ── §11 #9: changing model config changes the hashes ─────────────────────────
# Classification: ACTIVE_SLICE_B


def test_changing_model_config_changes_hashes() -> None:
    """§11 #9 — ACTIVE_SLICE_B (Slice B landed).

    Changing only the model config (algorithm, hyperparameters, seed)
    MUST change both the ``model_config_hash`` AND the
    ``model_artifact_hash``. Other identity fields held constant.

    Exercised via ``compute_model_config_hash`` and
    ``compute_model_artifact_hash`` (Slice B deterministic hash
    helpers per design §6).
    """

    from backend.app.rolling_backtest.replay_trained_identity import (
        ModelConfigPayload,
        TrainingManifestPayload,
        compute_model_artifact_hash,
        compute_model_config_hash,
        compute_training_manifest_hash,
    )

    forecast_cutoff = _utc(2026, 3, 15, hour=12)
    training_cutoff = _utc(2026, 3, 14, hour=12)
    manifest = TrainingManifestPayload(
        replay_attempt_id="att-9",
        replay_node_id="node-9",
        scenario_id="scn-9",
        forecast_cutoff_at=forecast_cutoff,
        training_cutoff_at=training_cutoff,
        allowed_training_season_ids=(2025,),
        feature_visibility_policy_version="task11-visibility-v1",
        label_visibility_policy_version="task11-visibility-v1",
        artifact_visibility_policy_version="task11-visibility-v1",
        validation_policy_version="task11-validation-v1",
        training_dataset_hash="2" * 64,
        task8_curve_identity=None,
        task9_replay_binding_identity=None,
        row_count=20,
        excluded_row_count=2,
    )

    manifest_hash = compute_training_manifest_hash(manifest)

    # Baseline config.
    config_a = ModelConfigPayload(
        algorithm_family="slice_b_9",
        hyperparameters={"lr": "0.001"},
        random_seed=42,
        deterministic_serialization_version="slice-b-v1",
    )
    config_hash_a = compute_model_config_hash(config_a)
    artifact_hash_a = compute_model_artifact_hash(
        training_manifest_hash=manifest_hash,
        model_config_hash=config_hash_a,
        model_code_version="slice-b-code-v1",
    )

    # Variant 1: change algorithm_family only.
    config_b = ModelConfigPayload(
        algorithm_family="slice_b_9_alt",  # changed
        hyperparameters={"lr": "0.001"},
        random_seed=42,
        deterministic_serialization_version="slice-b-v1",
    )
    config_hash_b = compute_model_config_hash(config_b)
    artifact_hash_b = compute_model_artifact_hash(
        training_manifest_hash=manifest_hash,
        model_config_hash=config_hash_b,
        model_code_version="slice-b-code-v1",
    )
    assert config_hash_a != config_hash_b, "changing algorithm_family must change model_config_hash"
    assert artifact_hash_a != artifact_hash_b, (
        "changing algorithm_family must change model_artifact_hash"
    )

    # Variant 2: change random_seed only.
    config_c = ModelConfigPayload(
        algorithm_family="slice_b_9",
        hyperparameters={"lr": "0.001"},
        random_seed=43,  # changed
        deterministic_serialization_version="slice-b-v1",
    )
    config_hash_c = compute_model_config_hash(config_c)
    artifact_hash_c = compute_model_artifact_hash(
        training_manifest_hash=manifest_hash,
        model_config_hash=config_hash_c,
        model_code_version="slice-b-code-v1",
    )
    assert config_hash_a != config_hash_c, "changing random_seed must change model_config_hash"
    assert artifact_hash_a != artifact_hash_c, (
        "changing random_seed must change model_artifact_hash"
    )

    # Variant 3: change hyperparameters only.
    config_d = ModelConfigPayload(
        algorithm_family="slice_b_9",
        hyperparameters={"lr": "0.01"},  # changed
        random_seed=42,
        deterministic_serialization_version="slice-b-v1",
    )
    config_hash_d = compute_model_config_hash(config_d)
    artifact_hash_d = compute_model_artifact_hash(
        training_manifest_hash=manifest_hash,
        model_config_hash=config_hash_d,
        model_code_version="slice-b-code-v1",
    )
    assert config_hash_a != config_hash_d, "changing hyperparameters must change model_config_hash"
    assert artifact_hash_a != artifact_hash_d, (
        "changing hyperparameters must change model_artifact_hash"
    )

    # Manifest hash MUST remain constant (only config varied).
    assert compute_training_manifest_hash(manifest) == manifest_hash, (
        "manifest hash must not change when only model config varies (§9 #9 contract)"
    )


# ── §11 #10: JSON / manifest mismatch for replay-trained identity rejected ──
# Classification: ACTIVE_SLICE_D


def test_json_manifest_mismatch_for_replay_trained_identity_is_rejected() -> None:
    """§11 #10 — ACTIVE_SLICE_D.

    A replay-trained artifact whose JSON-side identity fields disagree
    with the manifest-side identity fields MUST be rejected with a
    structured blocker (per §9 ``task12_manifest_mismatch`` /
    ``task12_artifact_identity_mismatch`` taxonomy + §7 deterministic
    payload contract).

    The Slice D ``verify_replay_trained_artifact_identity`` helper
    compares every canonical §6 identity field across the two sides
    and rejects on any mismatch.
    """
    from backend.app.rolling_backtest.replay_trained_identity import (
        ModelConfigPayload,
        TrainingManifestPayload,
        project_replay_trained_identity,
    )
    from backend.app.rolling_backtest.replay_trained_prediction import (
        ArtifactIdentityPair,
        ReplayTrainedArtifactIdentityMismatchError,
        verify_replay_trained_artifact_identity,
    )

    # Build a canonical projection whose JSON-side and manifest-side
    # agree.
    manifest = TrainingManifestPayload(
        replay_attempt_id="attempt-slice-d-1",
        replay_node_id="node-slice-d-1",
        scenario_id="scenario-slice-d-1",
        forecast_cutoff_at=_utc(2026, 3, 15),
        training_cutoff_at=_utc(2026, 3, 10),
        allowed_training_season_ids=(2026,),
        feature_visibility_policy_version="task11-feature-visibility-v1",
        label_visibility_policy_version="task11-label-visibility-v1",
        artifact_visibility_policy_version="task11-artifact-visibility-v1",
        validation_policy_version="task11-validation-v1",
        training_dataset_hash="a" * 64,
        task8_curve_identity=None,
        task9_replay_binding_identity=None,
        row_count=100,
        excluded_row_count=0,
    )
    config = ModelConfigPayload(
        algorithm_family="slice_d_artifact_v1",
        hyperparameters={"lr": "0.01"},
        random_seed=42,
        deterministic_serialization_version="slice-d-v1",
    )
    projection = project_replay_trained_identity(
        manifest=manifest,
        config=config,
        model_code_version="slice-d-code-v1",
        task12_policy_version="task-012-slice-d-v1",
    )

    # Construct a JSON-side payload that intentionally disagrees on
    # ``model_artifact_hash`` (one of the canonical §6 hash fields).
    json_side = {
        "model_policy": "replay_trained_model",
        "task12_policy_version": "task-012-slice-d-v1",
        "replay_attempt_id": "attempt-slice-d-1",
        "replay_node_id": "node-slice-d-1",
        "forecast_cutoff_at": _utc(2026, 3, 15),
        "training_cutoff_at": _utc(2026, 3, 10),
        "training_manifest_hash": projection.training_manifest_hash,
        "training_dataset_hash": "a" * 64,
        "model_config_hash": projection.model_config_hash,
        "model_artifact_hash": "f" * 64,  # mismatched!
        "model_code_version": "slice-d-code-v1",
    }
    manifest_side = {
        "model_policy": "replay_trained_model",
        "task12_policy_version": "task-012-slice-d-v1",
        "replay_attempt_id": "attempt-slice-d-1",
        "replay_node_id": "node-slice-d-1",
        "forecast_cutoff_at": _utc(2026, 3, 15),
        "training_cutoff_at": _utc(2026, 3, 10),
        "training_manifest_hash": projection.training_manifest_hash,
        "training_dataset_hash": "a" * 64,
        "model_config_hash": projection.model_config_hash,
        "model_artifact_hash": projection.model_artifact_hash,
        "model_code_version": "slice-d-code-v1",
    }

    # Mismatch MUST raise the structured error.
    with pytest.raises(ReplayTrainedArtifactIdentityMismatchError) as exc_info:
        verify_replay_trained_artifact_identity(
            ArtifactIdentityPair(json_side=json_side, manifest_side=manifest_side),
            projection=projection,
        )
    assert exc_info.value.mismatched_fields == ("model_artifact_hash",)
    assert exc_info.value.blocker_code == "task12_artifact_identity_mismatch"
    # §7: payload must be deterministic canonical-JSON.
    assert '"blocker":"task12_artifact_identity_mismatch"' in exc_info.value.payload
    assert '"projection_hash"' in exc_info.value.payload

    # Sanity: when both sides agree, the helper returns an empty
    # mismatched-fields tuple (no exception).
    agree = dict(manifest_side)
    assert (
        verify_replay_trained_artifact_identity(
            ArtifactIdentityPair(json_side=agree, manifest_side=manifest_side),
            projection=projection,
        )
        == ()
    )


# ── §11 #11: replay-trained prediction carries model_policy string ───────────
# Classification: ACTIVE_SLICE_D


def _binding_payload_for(binding: object) -> dict[str, object]:
    """Project the canonical binding payload used by the prediction hash.

    Mirrors the field set assembled inside
    ``bind_replay_trained_prediction`` so the contract test can
    recompute the hash without coupling to the private helper.
    Private (leading underscore) so Slice A's no-implementation
    meta-check does not reject it as a top-level non-test definition.
    """
    from backend.app.rolling_backtest.replay_trained_prediction import (
        ReplayTrainedPredictionBinding,
    )

    assert isinstance(binding, ReplayTrainedPredictionBinding)
    return {
        "model_policy": "replay_trained_model",
        "task9_run_id": binding.task9_run_id,
        "task9_result_hash": binding.task9_result_hash,
        "is_replay": binding.is_replay,
        "replay_attempt_id": binding.replay_attempt_id,
        "replay_node_id": binding.replay_node_id,
        "replay_code_version": binding.replay_code_version,
        "forecast_cutoff_at": binding.forecast_cutoff_at,
        "training_cutoff_at": binding.training_cutoff_at,
        "training_manifest_hash": binding.training_manifest_hash,
        "model_artifact_hash": binding.model_artifact_hash,
        "task12_policy_version": "task-012-slice-d-v1",
        "model_code_version": binding.replay_code_version,
    }


def test_replay_trained_prediction_carries_model_policy_string() -> None:
    """§11 #11 — ACTIVE_SLICE_D.

    Every prediction emitted by a ``replay_trained_model`` path MUST
    carry ``model_policy = "replay_trained_model"`` on the result
    record. The ``model_policy`` field MUST be a first-class field on
    the bound record (not just a request parameter or transient
    in-memory flag).
    """
    from backend.app.rolling_backtest.replay_trained_identity import (
        ModelConfigPayload,
        TrainingManifestPayload,
        project_replay_trained_identity,
    )
    from backend.app.rolling_backtest.replay_trained_prediction import (
        ReplayTrainedBindingInput,
        ReplayTrainedPredictionBinding,
        bind_replay_trained_prediction,
    )

    # Enum-level pin (active since Slice A).
    assert Task10ModelPolicy.REPLAY_TRAINED_MODEL.value == "replay_trained_model"

    # Build a canonical projection to drive the binding.
    manifest = TrainingManifestPayload(
        replay_attempt_id="attempt-slice-d-2",
        replay_node_id="node-slice-d-2",
        scenario_id="scenario-slice-d-2",
        forecast_cutoff_at=_utc(2026, 4, 20),
        training_cutoff_at=_utc(2026, 4, 15),
        allowed_training_season_ids=(2026,),
        feature_visibility_policy_version="task11-feature-visibility-v1",
        label_visibility_policy_version="task11-label-visibility-v1",
        artifact_visibility_policy_version="task11-artifact-visibility-v1",
        validation_policy_version="task11-validation-v1",
        training_dataset_hash="b" * 64,
        task8_curve_identity=None,
        task9_replay_binding_identity=None,
        row_count=120,
        excluded_row_count=0,
    )
    config = ModelConfigPayload(
        algorithm_family="slice_d_policy_v1",
        hyperparameters={"lr": "0.02"},
        random_seed=99,
        deterministic_serialization_version="slice-d-v1",
    )
    projection = project_replay_trained_identity(
        manifest=manifest,
        config=config,
        model_code_version="slice-d-code-v1",
        task12_policy_version="task-012-slice-d-v1",
    )

    binding_input = ReplayTrainedBindingInput(
        prediction_run_id=42,
        projection=projection,
        task9_run_id=7,
        task9_result_hash="c" * 64,
        replay_code_version="slice-d-code-v1",
        is_replay=True,
        replay_attempt_id="attempt-slice-d-2",
        replay_node_id="node-slice-d-2",
    )
    binding = bind_replay_trained_prediction(binding_input)

    # Type-level: the returned record is a ReplayTrainedPredictionBinding.
    assert isinstance(binding, ReplayTrainedPredictionBinding)

    # The model_policy field is locked to REPLAY_TRAINED_MODEL.
    assert binding.model_policy is Task10ModelPolicy.REPLAY_TRAINED_MODEL
    assert binding.model_policy.value == "replay_trained_model"

    # The model_policy string participates in the prediction_hash
    # identity (so swapping the policy would change the binding hash).
    payload_with_replay = dict(_binding_payload_for(binding))
    payload_with_historical = dict(_binding_payload_for(binding))
    payload_with_historical["model_policy"] = "historically_available_model"
    from backend.app.rolling_backtest.replay_trained_prediction import (
        compute_prediction_hash,
    )

    assert compute_prediction_hash(payload_with_replay) == binding.prediction_hash
    assert compute_prediction_hash(payload_with_replay) != compute_prediction_hash(
        payload_with_historical
    )

    # Lock guard: construction with a different policy MUST raise.
    with pytest.raises(ValueError, match="REPLAY_TRAINED_MODEL"):
        ReplayTrainedPredictionBinding(
            prediction_run_id=43,
            model_policy=Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL,
            task9_run_id=7,
            task9_result_hash="c" * 64,
            is_replay=True,
            replay_attempt_id="attempt-slice-d-2",
            replay_node_id="node-slice-d-2",
            replay_code_version="slice-d-code-v1",
            forecast_cutoff_at=_utc(2026, 4, 20),
            training_cutoff_at=_utc(2026, 4, 15),
            training_manifest_hash=projection.training_manifest_hash,
            model_artifact_hash=projection.model_artifact_hash,
            task9_replay_binding_identity="d" * 64,
            prediction_hash="e" * 64,
        )


# ── §11 #12: comparison runs produce separate prediction identities ─────────
# Classification: ACTIVE_SLICE_D


def test_historical_and_replay_trained_comparison_runs_produce_separate_identities() -> None:
    """§11 #12 — ACTIVE_SLICE_D.

    When a comparison run evaluates both ``HISTORICALLY_AVAILABLE_MODEL``
    and ``REPLAY_TRAINED_MODEL`` on the same scenario, the two
    prediction runs MUST carry separate prediction identities
    (separate ``prediction_run_id``, separate ``prediction_hash``,
    separate ``model_policy``, separate artifact identity, separate
    audit identity). Sharing a single prediction row across policies
    is itself a cross-run substitution and is rejected.
    """
    from pydantic import ValidationError

    from backend.app.rolling_backtest.enums import Task10ModelPolicy
    from backend.app.rolling_backtest.replay_trained_prediction import (
        ComparisonRunIdentity,
        verify_comparison_run_separation,
    )
    from backend.app.rolling_backtest.schemas import (
        HistoricalAvailableModelIdentity,
        ReplayTrainedModelIdentity,
    )

    # §8.4 schema-level mutual-exclusion pin: a single RollingNodeDefinition
    # MUST NOT carry both policy types — they are different policy tags
    # on the discriminated union ResolvedTask10ModelPolicy. The historical
    # branch uses HistoricalAvailableModelIdentity; the replay-trained
    # branch uses ReplayTrainedModelIdentity. Pydantic enforces the
    # discriminator at construction time.
    with pytest.raises(ValidationError):
        HistoricalAvailableModelIdentity(
            policy=Task10ModelPolicy.REPLAY_TRAINED_MODEL,
            training_run_semantic_identity="c" * 64,
            artifact_semantic_identities=("d" * 64,),
            authority_visibility_identity="e" * 64,
        )
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

    # §11 #12 — per-comparison-run identity separation. The two
    # prediction bindings MUST differ on every axis.
    from backend.app.rolling_backtest.replay_trained_prediction import (
        ReplayTrainedPredictionBindingMismatchError,
    )

    identity = ComparisonRunIdentity(
        historical_prediction_run_id=1,
        historical_prediction_hash="h" * 64,
        historical_model_policy=Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL,
        historical_artifact_identity="hist-artifact-identity-1",
        replay_trained_prediction_run_id=2,
        replay_trained_prediction_hash="r" * 64,
        replay_trained_model_policy=Task10ModelPolicy.REPLAY_TRAINED_MODEL,
        replay_trained_artifact_identity="replay-artifact-identity-2",
        audit_identity="audit-identity-1",
    )
    # Independent identities: no exception.
    verify_comparison_run_separation(identity)

    # Sharing the prediction_run_id MUST be rejected.
    with pytest.raises(ReplayTrainedPredictionBindingMismatchError) as exc_info:
        verify_comparison_run_separation(
            ComparisonRunIdentity(
                historical_prediction_run_id=1,
                historical_prediction_hash="h" * 64,
                historical_model_policy=Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL,
                historical_artifact_identity="hist-artifact-identity-1",
                replay_trained_prediction_run_id=1,  # shared!
                replay_trained_prediction_hash="r" * 64,
                replay_trained_model_policy=Task10ModelPolicy.REPLAY_TRAINED_MODEL,
                replay_trained_artifact_identity="replay-artifact-identity-2",
                audit_identity="audit-identity-1",
            )
        )
    assert "prediction_run_id_must_be_distinct" in exc_info.value.mismatched_fields

    # Sharing the prediction_hash MUST also be rejected.
    with pytest.raises(ReplayTrainedPredictionBindingMismatchError) as exc_info:
        verify_comparison_run_separation(
            ComparisonRunIdentity(
                historical_prediction_run_id=1,
                historical_prediction_hash="shared" * 13,  # 64 hex chars
                historical_model_policy=Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL,
                historical_artifact_identity="hist-artifact-identity-1",
                replay_trained_prediction_run_id=2,
                replay_trained_prediction_hash="shared" * 13,  # shared!
                replay_trained_model_policy=Task10ModelPolicy.REPLAY_TRAINED_MODEL,
                replay_trained_artifact_identity="replay-artifact-identity-2",
                audit_identity="audit-identity-1",
            )
        )
    assert "prediction_hash_must_be_distinct" in exc_info.value.mismatched_fields


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
    as one of ``ACTIVE_SLICE_A`` / ``ACTIVE_SLICE_B`` / ``ACTIVE_SLICE_C`` /
    ``OBLIGATION_PLACEHOLDER``, and the obligation placeholders MUST
    reference a specific future slice label.

    This guards against two failure modes:

    1. A test being added with classification=None / missing / a typo.
    2. An obligation placeholder being added without naming the future
       slice (so future readers cannot tell whether it awaits Slice B /
       C / D / E).

    Pre-Slice B (PR #83): ACTIVE_SLICE_A=4, OBLIGATION_PLACEHOLDER=8.
    Post-Slice B: ACTIVE_SLICE_A=4, ACTIVE_SLICE_B=2,
    OBLIGATION_PLACEHOLDER=6 (tests #8 + #9 reclassified to
    ACTIVE_SLICE_B once Slice B deterministic hash helpers landed).
    Post-Slice C: ACTIVE_SLICE_A=4, ACTIVE_SLICE_B=2,
    ACTIVE_SLICE_C=3 (#3 execution portion + #4 + #5), and
    OBLIGATION_PLACEHOLDER=3 (Slice D: #10, #11, #12).
    """

    active_a_count = 0
    active_b_count = 0
    active_c_count = 0
    active_d_count = 0
    obligation_count = 0
    for entry in _SECTION_11_REGISTRY:
        classification = entry["classification"]
        assert classification in (
            SliceClassification.ACTIVE_SLICE_A.value,
            SliceClassification.ACTIVE_SLICE_B.value,
            SliceClassification.ACTIVE_SLICE_C.value,
            SliceClassification.ACTIVE_SLICE_D.value,
            SliceClassification.OBLIGATION_PLACEHOLDER.value,
        ), f"§11 registry entry {entry['name']!r} has invalid classification"
        if classification == SliceClassification.ACTIVE_SLICE_A.value:
            active_a_count += 1
            # ACTIVE_SLICE_A entries MUST NOT carry a future_slice label
            # (they don't await one).
            assert "future_slice" not in entry, (
                f"ACTIVE_SLICE_A entry {entry['name']!r} should not carry future_slice"
            )
        elif classification == SliceClassification.ACTIVE_SLICE_B.value:
            active_b_count += 1
            # ACTIVE_SLICE_B entries were originally OBLIGATION_PLACEHOLDER
            # entries tagged with future_slice="Slice B". After Slice B
            # lands, those entries should drop the future_slice label.
            assert "future_slice" not in entry, (
                f"ACTIVE_SLICE_B entry {entry['name']!r} should not carry "
                f"future_slice (Slice B has landed; the obligation is now active)"
            )
        elif classification == SliceClassification.ACTIVE_SLICE_C.value:
            active_c_count += 1
            # ACTIVE_SLICE_C entries were originally OBLIGATION_PLACEHOLDER
            # entries tagged with future_slice="Slice C". After Slice C
            # lands, those entries should drop the future_slice label.
            assert "future_slice" not in entry, (
                f"ACTIVE_SLICE_C entry {entry['name']!r} should not carry "
                f"future_slice (Slice C has landed; the obligation is now active)"
            )
        elif classification == SliceClassification.ACTIVE_SLICE_D.value:
            active_d_count += 1
            # ACTIVE_SLICE_D entries were originally OBLIGATION_PLACEHOLDER
            # entries tagged with future_slice="Slice D". After Slice D
            # lands, those entries should drop the future_slice label.
            assert "future_slice" not in entry, (
                f"ACTIVE_SLICE_D entry {entry['name']!r} should not carry "
                f"future_slice (Slice D has landed; the obligation is now active)"
            )
        else:
            obligation_count += 1
            assert "future_slice" in entry, (
                f"OBLIGATION_PLACEHOLDER entry {entry['name']!r} must name "
                f"the future slice (Slice C / Slice D / Slice E)"
            )
            assert entry["future_slice"] in (
                OBLIGATION_FUTURE_SLICE_C,
                OBLIGATION_FUTURE_SLICE_D,
            ), (
                f"OBLIGATION_PLACEHOLDER entry {entry['name']!r} has "
                f"non-canonical future_slice label {entry['future_slice']!r}; "
                f"future_slice='Slice B' is no longer valid (Slice B landed); "
                f"future_slice='Slice C' is no longer valid (Slice C landed); "
                f"future_slice='Slice D' is no longer valid (Slice D landed)"
            )

    # Slice A is contract-tests-only per §12; the count of
    # ACTIVE_SLICE_A + ACTIVE_SLICE_B + ACTIVE_SLICE_C +
    # ACTIVE_SLICE_D + OBLIGATION_PLACEHOLDER must total exactly 12
    # (the §11 contract surface).
    total = active_a_count + active_b_count + active_c_count + active_d_count + obligation_count
    assert total == 12, (
        f"§11 registry must total 12 tests (got {total}: "
        f"{active_a_count} ACTIVE_SLICE_A + {active_b_count} ACTIVE_SLICE_B "
        f"+ {active_c_count} ACTIVE_SLICE_C + {active_d_count} ACTIVE_SLICE_D "
        f"+ {obligation_count} OBLIGATION_PLACEHOLDER)"
    )

    # Hardened visibility assertion: the obligation_count lower bound
    # tracks the count of remaining future slices that the §11 contract
    # surface has not yet activated. Once Slice B landed, the bound
    # moved from >= 6 to >= 3. Once Slice C landed, the bound stayed
    # at >= 3 (the three Slice D placeholders remained). Once Slice D
    # landed, the bound moved to >= 0 — the §11 contract surface is
    # complete; Slice E is API/CLI exposure and lives outside the
    # §11 test-contract surface (per §12 Slice E: "Allowed only
    # after Slices A-D are green and a separate API / CLI amendment
    # opens that surface"). The `>= 0` lower bound remains valid
    # as a guard against negative-count miscount, and the
    # `total == 12` guard above continues to enforce the §11
    # contract surface size.
    assert obligation_count >= 0, (
        f"Expected ≥0 obligation placeholders awaiting future slices "
        f"(got {obligation_count}). §11 contract surface is complete "
        f"after TASK-012 Slices A-D landed; Slice E is out of §11 scope."
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
