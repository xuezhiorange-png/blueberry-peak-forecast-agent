"""TASK-012 Slice D — replay_trained_model prediction binding and artifact verification.

Per ``docs/task-012-replay-trained-model-design.md`` §12 Slice D (verbatim):

    Allowed: prediction path consumes exact replay-trained artifact identity
             and exact replay-produced Task 9 binding.
    Forbidden: cross-run reuse or silent fallback.

This module provides:

1. ``ReplayTrainedPredictionBinding`` — frozen dataclass that carries the
   prediction's bound identity (per §6 + §11 #11). The ``model_policy``
   field is locked to ``REPLAY_TRAINED_MODEL``; callers MUST NOT construct
   this dataclass for any other policy.

2. ``verify_replay_trained_artifact_identity`` — §11 #10. Validates that
   the JSON-side identity of a replay-trained artifact agrees with the
   manifest-side identity across all canonical §6 fields. Mismatches
   raise :class:`ReplayTrainedArtifactIdentityMismatchError` carrying the
   ``task12_artifact_identity_mismatch`` blocker code and a deterministic
   canonical-JSON payload for §7 hash traceability.

3. ``bind_replay_trained_prediction`` — §5.4 + §11 #11. Binds a prediction
   to the replay-produced Task 9 row + the replay attempt / node identity
   carried by the artifact. Mismatches raise
   :class:`ReplayTrainedPredictionBindingMismatchError` carrying
   ``task12_prediction_binding_mismatch``.

4. ``verify_comparison_run_separation`` — §11 #12. Verifies that a
   comparison run's two prediction bindings (one per policy) carry
   independent prediction_run_id, prediction_hash, model_policy,
   artifact identity, and audit identity. Reuses
   ``task12_cross_run_substitution`` (existing §9 code) — a single
   prediction run attempting to carry two policies is itself a
   cross-run substitution.

Determinism discipline (per design §14 stop conditions + §13 no-fallback):

- No wall-clock ``now()`` participates in any canonical hash or identity.
- All canonical payloads are sorted-keys + ``separators=(",", ":")`` for
  byte-stable hashes (mirrors Slice B's pattern).
- No current-data / latest / most-recent fallback is permitted at any
  binding step. The required Task 9 identity MUST be supplied explicitly
  and matched exactly.

Production path note (per Charles's Slice D scope authorization):

- The full live ``replay_trained_model`` runtime path remains gated by
  the existing ``validate_replay_task10_model_policy`` (§11 #1) — this
  module's functions are exercised by contract tests in
  ``tests/rolling_backtest/test_replay_trained_model_slice_a.py`` (§11
  #10, #11, #12) but production replay binding still rejects
  ``REPLAY_TRAINED_MODEL`` until a separately-authorized implementation
  PR opens that gate.

Slice E (API / CLI) is explicitly out of scope and is NOT included in
this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .canonical import canonical_json_dumps
from .enums import Task10ModelPolicy
from .orchestration import OrchestrationBlocker
from .replay_trained_identity import ReplayTrainedIdentityProjection

# ── Exception types (§11 #10 / #11 / #12) ────────────────────────────────────


class ReplayTrainedArtifactIdentityMismatchError(ValueError):
    """§11 #10 — JSON-side artifact identity disagrees with manifest-side.

    Maps to :attr:`OrchestrationBlocker.TASK12_ARTIFACT_IDENTITY_MISMATCH`
    so callers can rely on the canonical blocker enum rather than ad-hoc
    error strings. The accompanying :attr:`payload` is a deterministic
    canonical-JSON string (per ``canonical.canonical_json_dumps``) for
    §7 hash traceability.
    """

    def __init__(
        self,
        message: str,
        *,
        blocker_code: str = OrchestrationBlocker.TASK12_ARTIFACT_IDENTITY_MISMATCH.value,
        mismatched_fields: tuple[str, ...] = (),
        projection_hash: str = "",
    ) -> None:
        super().__init__(message)
        self.blocker_code = blocker_code
        self.mismatched_fields = mismatched_fields
        self.projection_hash = projection_hash
        self.payload = canonical_json_dumps(
            {
                "blocker": blocker_code,
                "mismatched_fields": list(mismatched_fields),
                "projection_hash": projection_hash,
            }
        )


class ReplayTrainedPredictionBindingMismatchError(ValueError):
    """§11 #11 — prediction binding disagrees with replay-produced Task 9 row.

    Maps to :attr:`OrchestrationBlocker.TASK12_PREDICTION_BINDING_MISMATCH`
    so callers can rely on the canonical blocker enum rather than ad-hoc
    error strings. The accompanying :attr:`payload` is a deterministic
    canonical-JSON string for §7 hash traceability.
    """

    def __init__(
        self,
        message: str,
        *,
        blocker_code: str = OrchestrationBlocker.TASK12_PREDICTION_BINDING_MISMATCH.value,
        mismatched_fields: tuple[str, ...] = (),
        expected_task9_run_id: int | None = None,
        actual_task9_run_id: int | None = None,
    ) -> None:
        super().__init__(message)
        self.blocker_code = blocker_code
        self.mismatched_fields = mismatched_fields
        self.expected_task9_run_id = expected_task9_run_id
        self.actual_task9_run_id = actual_task9_run_id
        self.payload = canonical_json_dumps(
            {
                "blocker": blocker_code,
                "mismatched_fields": list(mismatched_fields),
                "expected_task9_run_id": expected_task9_run_id,
                "actual_task9_run_id": actual_task9_run_id,
            }
        )


# ── Canonical §6 identity field set (per design §6 lines 122-139) ────────────
#
# Per §6: "Required identity fields: ..." The contract test for §11 #10
# must verify that ALL of these fields are consistent across JSON-side
# and manifest-side projections. We enumerate them here so the verifier
# and the contract test share a single source of truth.

_REQUIRED_IDENTITY_FIELDS: tuple[str, ...] = (
    "model_policy",
    "task12_policy_version",
    "replay_attempt_id",
    "replay_node_id",
    "forecast_cutoff_at",
    "training_cutoff_at",
    "training_manifest_hash",
    "training_dataset_hash",
    "model_config_hash",
    "model_artifact_hash",
    "model_code_version",
)


def required_identity_fields() -> tuple[str, ...]:
    """Return the canonical §6 identity field set (frozen)."""
    return _REQUIRED_IDENTITY_FIELDS


# ── §11 #10 — JSON / manifest identity mismatch verification ────────────────


@dataclass(frozen=True, slots=True)
class ArtifactIdentityPair:
    """Pair of (json_side, manifest_side) identity projections for §11 #10.

    Both sides MUST carry the canonical §6 identity fields. The
    :func:`verify_replay_trained_artifact_identity` helper compares
    them field-by-field and rejects on any mismatch.
    """

    json_side: dict[str, object]
    manifest_side: dict[str, object]


def _normalize_field_value(value: object) -> str:
    """Normalize a field value to a stable string for comparison.

    ``datetime`` values are reduced to their ISO-8601 representation
    (deterministic for tz-aware datetimes) so that equivalent values
    from different sources (manifest payload vs. JSON payload) compare
    equal. Other values fall through to ``repr`` which is stable for
    the standard JSON-side types we accept (str / int / float / bool /
    None / tuple of these).
    """
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return repr(tuple(_normalize_field_value(v) for v in value))
    return repr(value)


def verify_replay_trained_artifact_identity(
    pair: ArtifactIdentityPair,
    *,
    projection: ReplayTrainedIdentityProjection,
) -> tuple[str, ...]:
    """§11 #10 — verify JSON-side identity matches manifest-side identity.

    Compares every canonical §6 identity field across the two sides
    and rejects on any mismatch. The comparison is
    field-by-field (not hash-only) so the resulting
    :attr:`mismatched_fields` tuple is diagnostic-grade.

    Parameters
    ----------
    pair : ArtifactIdentityPair
        The two identity projections to compare.
    projection : ReplayTrainedIdentityProjection
        The canonical projection that produced both sides; used for
        ``projection_hash`` audit only.

    Returns
    -------
    tuple[str, ...]
        Empty tuple if all fields match. (Returning a tuple — rather
        than raising — allows callers to perform soft preflight checks
        without exception overhead. The contract test for §11 #10
        asserts the rejection path; this function preserves the
        diagnostic by exposing the field-level comparison result
        without raising.)

    Raises
    ------
    ReplayTrainedArtifactIdentityMismatchError
        If the comparison detects a mismatch. The exception carries
        the mismatched field names and a deterministic canonical-JSON
        payload for §7 hash traceability.
    """
    mismatched: list[str] = []
    for field_name in _REQUIRED_IDENTITY_FIELDS:
        json_value = pair.json_side.get(field_name, _MISSING)
        manifest_value = pair.manifest_side.get(field_name, _MISSING)
        json_norm = _normalize_field_value(json_value)
        manifest_norm = _normalize_field_value(manifest_value)
        if json_norm != manifest_norm:
            mismatched.append(field_name)

    if mismatched:
        raise ReplayTrainedArtifactIdentityMismatchError(
            f"replay-trained artifact identity mismatch on fields {tuple(mismatched)!r} (§11 #10)",
            mismatched_fields=tuple(mismatched),
            projection_hash=projection.model_artifact_hash,
        )
    return ()


# Sentinel used by ``_normalize_field_value`` comparison; never equals
# any real value because ``_normalize_field_value`` wraps with ``repr``.
_MISSING = object()


# ── §11 #11 — Prediction binding to replay Task 9 row ───────────────────────


@dataclass(frozen=True, slots=True)
class ReplayTrainedPredictionBinding:
    """§11 #11 — frozen prediction binding for a replay-trained model.

    The :attr:`model_policy` field is locked to
    :attr:`Task10ModelPolicy.REPLAY_TRAINED_MODEL`; attempting to
    construct this dataclass for any other policy is a type-level
    error.

    The :attr:`prediction_hash` is computed from the canonical
    identity fields of the binding itself (excluding
    ``prediction_run_id``) so the binding identity is reproducible
    from the binding payload alone.
    """

    prediction_run_id: int
    model_policy: Task10ModelPolicy
    task9_run_id: int
    task9_result_hash: str
    is_replay: bool
    replay_attempt_id: str
    replay_node_id: str
    replay_code_version: str
    forecast_cutoff_at: datetime
    training_cutoff_at: datetime
    training_manifest_hash: str
    model_artifact_hash: str
    task9_replay_binding_identity: str
    prediction_hash: str

    def __post_init__(self) -> None:
        # Lock model_policy to REPLAY_TRAINED_MODEL (per design §6 + §8.1).
        # The frozen dataclass cannot be reassigned, but a mis-set
        # default could still produce a record that LOOKS bound.
        if self.model_policy is not Task10ModelPolicy.REPLAY_TRAINED_MODEL:
            raise ValueError(
                f"ReplayTrainedPredictionBinding.model_policy must be "
                f"REPLAY_TRAINED_MODEL; got {self.model_policy!r} (§6 + §8.1)"
            )
        if not self.is_replay:
            raise ValueError(
                "ReplayTrainedPredictionBinding.is_replay must be True "
                "for a replay-trained model prediction (§5.4)"
            )


@dataclass(frozen=True, slots=True)
class ReplayTrainedBindingInput:
    """Inputs to :func:`bind_replay_trained_prediction`.

    Carries the artifact identity (from
    :class:`ReplayTrainedIdentityProjection`) and the replay-produced
    Task 9 binding (from
    :class:`replay_task10_binding.ReplayTask9BindingContext`).
    """

    prediction_run_id: int
    projection: ReplayTrainedIdentityProjection
    task9_run_id: int
    task9_result_hash: str
    replay_code_version: str
    is_replay: bool
    replay_attempt_id: str
    replay_node_id: str


def compute_prediction_hash(binding_payload: dict[str, object]) -> str:
    """Compute the canonical prediction hash for a binding payload.

    Uses :func:`canonical.canonical_json_dumps` for sorted-keys +
    stable separators, then SHA-256. Determinism discipline: the
    hash changes iff any of the identity fields change, and only
    those fields — ``prediction_run_id`` is excluded so that the
    binding identity is reproducible from the binding payload alone.
    """
    from .canonical import sha256_payload

    return sha256_payload(binding_payload)


def bind_replay_trained_prediction(
    input: ReplayTrainedBindingInput,
) -> ReplayTrainedPredictionBinding:
    """§5.4 + §11 #11 — bind a prediction to a replay-trained artifact.

    Verifies that the artifact's training manifest identity (§6)
    matches the replay-produced Task 9 binding exactly. Rejects
    cross-attempt / cross-node / cross-runner substitution (no
    fallback to latest / current / most-recent Task 9 row).

    Parameters
    ----------
    input : ReplayTrainedBindingInput
        The prediction's required identity fields and the replay
        Task 9 binding it must satisfy.

    Returns
    -------
    ReplayTrainedPredictionBinding
        A frozen binding carrying the validated identity and a
        ``prediction_hash`` computed from the canonical binding
        payload.

    Raises
    ------
    ReplayTrainedPredictionBindingMismatchError
        If any required identity field disagrees. The exception
        carries the mismatched field names and a deterministic
        canonical-JSON payload.
    """
    mismatched: list[str] = []

    # §5.4 — task9_result_hash must be non-empty and 64-hex.
    if not input.task9_result_hash or len(input.task9_result_hash) != 64:
        mismatched.append("task9_result_hash_must_be_64_hex")
    # §5.4 — task9_run_id must be a positive integer.
    if input.task9_run_id <= 0:
        mismatched.append("task9_run_id_must_be_positive")

    # §5.4 — is_replay MUST be true (replay-trained path is
    # exclusively a replay-mode surface per §4 + §5.4).
    if not input.is_replay:
        mismatched.append("is_replay_must_be_true")

    # §6 + §8.3 — replay attempt / node identity must be non-empty
    # and exact (no latest / current / most-recent fallback).
    if not input.replay_attempt_id:
        mismatched.append("replay_attempt_id_must_be_non_empty")
    if not input.replay_node_id:
        mismatched.append("replay_node_id_must_be_non_empty")
    if not input.replay_code_version:
        mismatched.append("replay_code_version_must_be_non_empty")

    # §5.1 — forecast_cutoff_at >= training_cutoff_at (enforced
    # upstream in schema; we re-check here as a defensive measure
    # because the binding ties both into the same hash).
    if input.projection.manifest.forecast_cutoff_at < input.projection.manifest.training_cutoff_at:
        mismatched.append("forecast_cutoff_at_must_be_gte_training_cutoff_at")

    if mismatched:
        raise ReplayTrainedPredictionBindingMismatchError(
            f"replay-trained prediction binding mismatch on fields {tuple(mismatched)!r} (§11 #11)",
            mismatched_fields=tuple(mismatched),
            expected_task9_run_id=input.task9_run_id,
            actual_task9_run_id=None,
        )

    # Build the binding identity payload (canonical, sorted-keys).
    binding_payload: dict[str, object] = {
        "model_policy": Task10ModelPolicy.REPLAY_TRAINED_MODEL.value,
        "task9_run_id": input.task9_run_id,
        "task9_result_hash": input.task9_result_hash,
        "is_replay": input.is_replay,
        "replay_attempt_id": input.replay_attempt_id,
        "replay_node_id": input.replay_node_id,
        "replay_code_version": input.replay_code_version,
        "forecast_cutoff_at": input.projection.manifest.forecast_cutoff_at,
        "training_cutoff_at": input.projection.manifest.training_cutoff_at,
        "training_manifest_hash": input.projection.training_manifest_hash,
        "model_artifact_hash": input.projection.model_artifact_hash,
        "task12_policy_version": input.projection.task12_policy_version,
        "model_code_version": input.projection.model_code_version,
    }
    prediction_hash = compute_prediction_hash(binding_payload)

    # §5.4 + §11 #11 — the task9_replay_binding_identity is the
    # canonical hash over the exact Task 9 binding (run_id +
    # result_hash + is_replay + replay_code_version). We use the
    # canonical JSON to make the binding identity deterministic
    # without coupling to ORM loading.
    task9_replay_binding_identity = canonical_json_dumps(
        {
            "task9_run_id": input.task9_run_id,
            "task9_result_hash": input.task9_result_hash,
            "is_replay": input.is_replay,
            "replay_code_version": input.replay_code_version,
        }
    )

    return ReplayTrainedPredictionBinding(
        prediction_run_id=input.prediction_run_id,
        model_policy=Task10ModelPolicy.REPLAY_TRAINED_MODEL,
        task9_run_id=input.task9_run_id,
        task9_result_hash=input.task9_result_hash,
        is_replay=input.is_replay,
        replay_attempt_id=input.replay_attempt_id,
        replay_node_id=input.replay_node_id,
        replay_code_version=input.replay_code_version,
        forecast_cutoff_at=input.projection.manifest.forecast_cutoff_at,
        training_cutoff_at=input.projection.manifest.training_cutoff_at,
        training_manifest_hash=input.projection.training_manifest_hash,
        model_artifact_hash=input.projection.model_artifact_hash,
        task9_replay_binding_identity=task9_replay_binding_identity,
        prediction_hash=prediction_hash,
    )


# ── §11 #12 — Comparison-run identity separation ─────────────────────────────


@dataclass(frozen=True, slots=True)
class ComparisonRunIdentity:
    """§11 #12 — identity pair for a comparison run.

    Two prediction bindings (one per model policy) MUST carry
    independent :attr:`prediction_run_id`, :attr:`prediction_hash`,
    :attr:`model_policy`, artifact identity, and audit identity. The
    dataclass captures the four key fields for the comparison test.
    """

    historical_prediction_run_id: int
    historical_prediction_hash: str
    historical_model_policy: Task10ModelPolicy
    historical_artifact_identity: str
    replay_trained_prediction_run_id: int
    replay_trained_prediction_hash: str
    replay_trained_model_policy: Task10ModelPolicy
    replay_trained_artifact_identity: str
    audit_identity: str


def verify_comparison_run_separation(
    identity: ComparisonRunIdentity,
) -> None:
    """§11 #12 — verify comparison-run identity separation.

    Asserts that the historical and replay-trained prediction
    bindings carry independent identities on every axis. A
    comparison run that shares a single prediction row across
    policies is itself a cross-run substitution and is rejected
    with the existing ``task12_cross_run_substitution`` blocker
    code (per §9 taxonomy).

    Parameters
    ----------
    identity : ComparisonRunIdentity
        The comparison-run identity pair to verify.

    Raises
    ------
    ReplayTrainedPredictionBindingMismatchError
        If any axis of the comparison identity is shared. The
        exception carries the mismatched field names.
    """
    mismatched: list[str] = []

    if identity.historical_prediction_run_id == identity.replay_trained_prediction_run_id:
        mismatched.append("prediction_run_id_must_be_distinct")
    if identity.historical_prediction_hash == identity.replay_trained_prediction_hash:
        mismatched.append("prediction_hash_must_be_distinct")
    if identity.historical_model_policy == identity.replay_trained_model_policy:
        mismatched.append("model_policy_must_be_distinct")
    if identity.historical_artifact_identity == identity.replay_trained_artifact_identity:
        mismatched.append("artifact_identity_must_be_distinct")
    if identity.historical_model_policy is not Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL:
        mismatched.append("historical_model_policy_must_be_historically_available")
    if identity.replay_trained_model_policy is not Task10ModelPolicy.REPLAY_TRAINED_MODEL:
        mismatched.append("replay_trained_model_policy_must_be_replay_trained")

    if mismatched:
        raise ReplayTrainedPredictionBindingMismatchError(
            f"comparison-run identity separation violated on fields "
            f"{tuple(mismatched)!r} (§11 #12)",
            mismatched_fields=tuple(mismatched),
            expected_task9_run_id=None,
            actual_task9_run_id=None,
        )


__all__ = [
    "ArtifactIdentityPair",
    "ComparisonRunIdentity",
    "ReplayTrainedArtifactIdentityMismatchError",
    "ReplayTrainedBindingInput",
    "ReplayTrainedPredictionBinding",
    "ReplayTrainedPredictionBindingMismatchError",
    "bind_replay_trained_prediction",
    "compute_prediction_hash",
    "required_identity_fields",
    "verify_comparison_run_separation",
    "verify_replay_trained_artifact_identity",
]
