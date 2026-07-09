"""TASK-012 Slice B — replay_trained_model identity plumbing + hash helpers.

Per ``docs/task-012-replay-trained-model-design.md`` §12 Slice B (verbatim):
    Allowed: manifest schema, identity projection, deterministic hash helpers,
    structured blockers.
    Forbidden: live training algorithm changes unless contract tests already
    exist.

This module provides:

1. ``TrainingManifestPayload`` and ``ModelConfigPayload`` — minimal,
   frozen-design-compliant payload projections for §7 (training manifest
   contract) and §6 (identity model).
2. ``compute_training_manifest_hash`` / ``compute_model_config_hash`` —
   deterministic SHA-256 hashes over canonical JSON serialization.
3. ``compute_model_artifact_hash`` — derived hash combining
   ``training_manifest_hash`` + ``model_config_hash`` + ``model_code_version``
   (so the artifact hash changes whenever any of those three change).
4. ``project_replay_trained_identity`` — identity projection helper that
   builds the canonical §6 identity tuple from raw inputs.

Determinism discipline (per design §14 stop conditions + §13 no-fallback):

- No wall-clock ``now()`` participates in any canonical hash.
- All canonical payloads are sorted-keys + ``separators=(",", ":")``
  UTF-8 JSON via the existing ``canonical_json_dumps`` helper.
- Decimal / datetime / Enum serialization rules are inherited from
  :mod:`backend.app.rolling_backtest.canonical` (no floats in canonical
  payloads).

This module is **pure functions** + **frozen dataclasses**. It performs
NO database writes, NO wall-clock reads, NO env / settings reads, NO
training algorithm calls. Slice C is the slice that invokes live
training; Slice B is the slice that establishes identity plumbing.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Final

from backend.app.rolling_backtest.canonical import canonical_json_dumps

# ── Frozen payload projections (§7 training manifest contract) ───────────────


@dataclass(frozen=True)
class TrainingManifestPayload:
    """§7 frozen-design subset required by Slice B hash helpers.

    The full §7 manifest includes 9 categories (replay identity,
    cutoff identity, dataset identity, feature identity, label identity,
    model config, artifact identity, blocker inventory, provenance).
    Slice B establishes the **canonical payload projection** used for
    deterministic hash computation; the live manifest writer is added
    in Slice C.
    """

    replay_attempt_id: str
    replay_node_id: str
    scenario_id: str
    forecast_cutoff_at: datetime
    training_cutoff_at: datetime
    allowed_training_season_ids: tuple[int, ...]
    feature_visibility_policy_version: str
    label_visibility_policy_version: str
    artifact_visibility_policy_version: str
    validation_policy_version: str
    training_dataset_hash: str
    task8_curve_identity: str | None
    task9_replay_binding_identity: str | None
    row_count: int
    excluded_row_count: int

    def __post_init__(self) -> None:
        # Enforce tz-aware cutoffs per design §5.1.
        for name in ("forecast_cutoff_at", "training_cutoff_at"):
            value = getattr(self, name)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
        # Enforce hash-field non-emptiness per design §6 line 141
        # (canonical payload projection cannot have empty hash).
        if not self.training_dataset_hash or len(self.training_dataset_hash) != 64:
            raise ValueError(
                "training_dataset_hash must be a 64-char hex string "
                "(design §6 line 141: hash fields must be non-empty)"
            )
        if not all(c in "0123456789abcdef" for c in self.training_dataset_hash):
            raise ValueError("training_dataset_hash must be lowercase hex")
        # Enforce training_cutoff_at <= forecast_cutoff_at per §5.1.
        if self.training_cutoff_at.astimezone(UTC) > self.forecast_cutoff_at.astimezone(UTC):
            raise ValueError("training_cutoff_at must be <= forecast_cutoff_at (design §5.1)")
        # Enforce non-empty identity strings per §6.
        for name in (
            "replay_attempt_id",
            "replay_node_id",
            "scenario_id",
        ):
            if not getattr(self, name):
                raise ValueError(f"{name} must be non-empty (design §6)")


@dataclass(frozen=True)
class ModelConfigPayload:
    """§6 line 122-139 frozen-design subset for ``model_config_hash``.

    Captures the model-side identity fields whose change MUST cause
    ``model_config_hash`` and (by extension) ``model_artifact_hash``
    to change per §11 #9.

    Runtime seed participates in the hash IF it is explicitly provided;
    a deterministic seed derivation rule (design §6 line 135) is
    expected to populate ``random_seed`` before projection, so the
    hash is always reproducible from canonical inputs.
    """

    algorithm_family: str
    hyperparameters: dict[str, str | int | bool]
    random_seed: int
    deterministic_serialization_version: str

    def __post_init__(self) -> None:
        if not self.algorithm_family:
            raise ValueError("algorithm_family must be non-empty")
        if not self.deterministic_serialization_version:
            raise ValueError("deterministic_serialization_version must be non-empty")


# ── Deterministic hash helpers ──────────────────────────────────────────────


_HASH_ALGORITHM: Final[str] = "sha256"
_HASH_HEX_LEN: Final[int] = 64


def _hash_bytes(payload: bytes) -> str:
    return hashlib.new(_HASH_ALGORITHM, payload).hexdigest()


def compute_training_manifest_hash(manifest: TrainingManifestPayload) -> str:
    """§7 + §6: deterministic SHA-256 over the canonical §7 manifest.

    The manifest is serialized via :func:`canonical_json_dumps` so:

    - dict keys are sorted,
    - tuple / list items are ordered,
    - datetimes are serialized as ISO-8601 with timezone ``Z``,
    - Decimals use the existing canonical decimal string,
    - no native floats (raises if any leak in).

    Re-encoding the same logical manifest produces the same hash byte-
    for-byte. Runtime timestamps that are NOT part of historical
    authority (per §7 line 161) MUST NOT be passed in; this helper
    trusts that the caller has already excluded them.
    """
    return _hash_bytes(canonical_json_dumps(asdict(manifest)).encode("utf-8"))


def compute_model_config_hash(config: ModelConfigPayload) -> str:
    """§6 line 134: deterministic SHA-256 over the canonical model config.

    Changing any field (algorithm family, hyperparameters, random_seed,
    deterministic_serialization_version) MUST change this hash. The
    canonical JSON projection sorts dict keys, so reordering
    ``hyperparameters`` does NOT change the hash (which is correct:
    a hyperparameter is the same regardless of insertion order).
    """
    return _hash_bytes(canonical_json_dumps(asdict(config)).encode("utf-8"))


def compute_model_artifact_hash(
    *,
    training_manifest_hash: str,
    model_config_hash: str,
    model_code_version: str,
) -> str:
    """§6 line 132: deterministic SHA-256 combining manifest + config + code.

    Per §11 #9: changing only the model config MUST change this hash.
    Per §6: the artifact is canonical only when all three inputs are
    non-empty 64-hex (or non-empty ``model_code_version``).

    The combination is a sorted-key JSON projection so the output is
    stable across Python versions / dict insertion order.
    """
    if not training_manifest_hash or len(training_manifest_hash) != _HASH_HEX_LEN:
        raise ValueError("training_manifest_hash must be a 64-char hex string (design §6 line 141)")
    if not model_config_hash or len(model_config_hash) != _HASH_HEX_LEN:
        raise ValueError("model_config_hash must be a 64-char hex string (design §6 line 141)")
    if not model_code_version:
        raise ValueError("model_code_version must be non-empty (design §6)")
    payload = json.dumps(
        {
            "model_code_version": model_code_version,
            "model_config_hash": model_config_hash,
            "training_manifest_hash": training_manifest_hash,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return _hash_bytes(payload.encode("utf-8"))


# ── Identity projection helper ──────────────────────────────────────────────


@dataclass(frozen=True)
class ReplayTrainedIdentityProjection:
    """§6 identity projection: a frozen, hash-ready identity bundle.

    The projection carries:

    - the canonical payload projections that feed the hash helpers;
    - the resulting 64-hex hashes (so callers can compare without
      recomputation);
    - the canonical §6 identity fields.

    Use :func:`project_replay_trained_identity` to construct one from
    raw inputs; the dataclass is ``frozen=True`` so once projected the
    identity is immutable.
    """

    manifest: TrainingManifestPayload
    config: ModelConfigPayload
    model_code_version: str
    task12_policy_version: str
    training_manifest_hash: str
    model_config_hash: str
    model_artifact_hash: str


def project_replay_trained_identity(
    *,
    manifest: TrainingManifestPayload,
    config: ModelConfigPayload,
    model_code_version: str,
    task12_policy_version: str,
) -> ReplayTrainedIdentityProjection:
    """Identity projection (§6 + §7 + §11 #8).

    Combines the manifest payload, model config payload, code version,
    and TASK-012 policy version into a single frozen identity bundle
    with the three 64-hex hashes pre-computed.

    Callers MUST NOT mutate the resulting projection; the dataclass
    is ``frozen=True`` to enforce that contract.
    """
    if not task12_policy_version:
        raise ValueError("task12_policy_version must be non-empty (design §6)")
    if not model_code_version:
        raise ValueError("model_code_version must be non-empty (design §6)")
    training_manifest_hash = compute_training_manifest_hash(manifest)
    model_config_hash = compute_model_config_hash(config)
    model_artifact_hash = compute_model_artifact_hash(
        training_manifest_hash=training_manifest_hash,
        model_config_hash=model_config_hash,
        model_code_version=model_code_version,
    )
    return ReplayTrainedIdentityProjection(
        manifest=manifest,
        config=config,
        model_code_version=model_code_version,
        task12_policy_version=task12_policy_version,
        training_manifest_hash=training_manifest_hash,
        model_config_hash=model_config_hash,
        model_artifact_hash=model_artifact_hash,
    )


# ── Helper: build default config payload (Slice B helper, NOT production) ──


def make_default_model_config(
    *,
    algorithm_family: str = "slice_b_stub_residual_v1",
    random_seed: int = 20260709,
    deterministic_serialization_version: str = "slice-b-v1",
) -> ModelConfigPayload:
    """Convenience constructor used by Slice B contract tests.

    Production callers (Slice C / Slice D) MUST supply real config
    payloads; this helper exists so the contract tests can exercise
    hash determinism + config-sensitivity without coupling to a real
    training algorithm.
    """
    return ModelConfigPayload(
        algorithm_family=algorithm_family,
        hyperparameters={"learning_rate": "0.01", "max_depth": 6, "shuffle": False},
        random_seed=random_seed,
        deterministic_serialization_version=deterministic_serialization_version,
    )


__all__ = [
    "TrainingManifestPayload",
    "ModelConfigPayload",
    "ReplayTrainedIdentityProjection",
    "compute_training_manifest_hash",
    "compute_model_config_hash",
    "compute_model_artifact_hash",
    "project_replay_trained_identity",
    "make_default_model_config",
]
