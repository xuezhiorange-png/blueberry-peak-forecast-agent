"""S4-C03 phenology-offset execution control plane.

This module freezes the owner-selected C03 parameter neighborhood and binds a
future execution to the shared S4-B gate and PostgreSQL budget authority.  It
does not score a model, read TEST, or authorize an execution by itself.
"""

from __future__ import annotations

import copy
import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, Literal, cast

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.maturity.config import (
    CurveRules,
    ForecastRules,
    HolidayRules,
    IntervalRules,
    MaturityCurveConfig,
    MaturityCurveRules,
    OffsetRules,
    PoolingRules,
    load_maturity_curve_config,
)
from backend.app.rolling_backtest.canonical import canonical_json_dumps, sha256_payload
from backend.app.s4_candidate_execution_authority import (
    DurableCandidateExecutionResult,
    DurableCandidatePreflight,
    S4CandidateExecutionAuthority,
)
from backend.app.s4_experiment import (
    EXPERIMENT_PLAN_VERSION,
    FROZEN_CANDIDATE_REGISTRY,
    GUARDRAIL_POLICY_HASH,
    GUARDRAIL_POLICY_VERSION,
    INCUMBENT_MODEL_ID,
    METRIC_CONTRACT_IDENTITY,
    METRIC_CONTRACT_VERSION,
    S4_A_EXPERIMENT_PLAN_HASH_BOUND,
    CandidateExecutionGateRequest,
    CandidateRegistration,
)

CANDIDATE_03_ID: Final[str] = "03_phenology_offset"
CANDIDATE_03_FAMILY: Final[str] = "PARAMETER_CALIBRATION"
CANDIDATE_03_PARENT_MODEL_ID: Final[str] = INCUMBENT_MODEL_ID
CANDIDATE_03_HYPOTHESIS: Final[str] = "versioned_phenology_offset_reduces_timing_error"
C03_ID: Final[str] = CANDIDATE_03_ID
C03_FAMILY: Final[str] = CANDIDATE_03_FAMILY
C03_PARENT_MODEL_ID: Final[str] = CANDIDATE_03_PARENT_MODEL_ID
C03_HYPOTHESIS: Final[str] = CANDIDATE_03_HYPOTHESIS
C03_PARAMETER_MANIFEST_VERSION: Final[str] = "v0.3-s4-c03-phenology-offset-manifest-v1"
C03_OWNER_DECISION_ID: Final[str] = "V0_3_S4_C03_PHENOLOGY_OFFSET_SEMANTIC_DECISION_R1"
C03_SEMANTIC_AUTHORITY: Final[str] = "TRAINING_TIME_LEARNED_SHIFT_MODEL_BOUND"
C03_ALLOWED_PARAMETER_PATHS: Final[tuple[str, ...]] = ("offset.maximum_abs_shift_days",)
C03_EXCLUDED_PARAMETER_PATHS: Final[tuple[str, ...]] = (
    "forecast.observed_phase_adjustment_max_days",
)
C03_RANDOM_SEED_POLICY: Final[str] = "FIXED_AND_RECORDED_PER_RUN"
C03_RANDOM_SEED: Final[int] = 20260624
C03_PLANNED_RUN_COUNT: Final[int] = 4
C03_RUN_VALUES: Final[tuple[Decimal, ...]] = (
    Decimal("14"),
    Decimal("18"),
    Decimal("24"),
    Decimal("28"),
)
C03_INCUMBENT_OFFSET_MAXIMUM_ABS_SHIFT_DAYS: Final[Decimal] = Decimal("21")
C03_INCUMBENT_OFFSET_MINIMUM_TRAINING_SAMPLES: Final[int] = 3
C03_INCUMBENT_FORECAST_OBSERVED_PHASE_ADJUSTMENT_MAX_DAYS: Final[Decimal] = Decimal("14")
C03_INCUMBENT_CONFIG_PATH: Final[str] = "configs/maturity_curve.yaml"
C03_INCUMBENT_CONFIG_FILE_SHA256: Final[str] = (
    "fc023976a228c36556ed5f7ababe722a3dd8a558ed11e0473eb415b52dd69ace"
)
C03_INCUMBENT_CONFIG_HASH: Final[str] = (
    "3571477d5822f57cd2c424620915560e22481f48983b397a1f1b8934e1a7612c"
)
C03_USES_GENERAL_S4_B_GUARDRAILS: Final[bool] = True
C03_SPECIAL_GUARDRAIL_THRESHOLD_OVERRIDE: Final[bool] = False
C03_ADAPTIVE_SEARCH_ALLOWED: Final[bool] = False
C03_POST_VALIDATION_PARAMETER_SUBSTITUTION_ALLOWED: Final[bool] = False
C03_FORECAST_PHASE_PARAMETER_AUTHORIZED: Final[bool] = False

_SHA256_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")


class Candidate03ContractError(ValueError):
    """Sanitized, machine-readable C03 contract failure."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _decimalize(value: object) -> object:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise Candidate03ContractError("C03_NONFINITE_DECIMAL")
        return value
    if isinstance(value, Mapping):
        return {str(key): _decimalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decimalize(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_decimalize(item) for item in value)
    return value


def _contains_native_float(value: object) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, Mapping):
        return any(_contains_native_float(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_native_float(item) for item in value)
    return False


def _path_value(payload: Mapping[str, Any], dotted_path: str) -> object:
    current: object = payload
    for segment in dotted_path.split("."):
        if not isinstance(current, Mapping) or segment not in current:
            raise Candidate03ContractError("C03_PARAMETER_PATH_MISSING")
        current = current[segment]
    return current


def _set_path(payload: dict[str, Any], dotted_path: str, value: object) -> None:
    segments = dotted_path.split(".")
    current = payload
    for segment in segments[:-1]:
        child = current.get(segment)
        if not isinstance(child, dict):
            raise Candidate03ContractError("C03_PARAMETER_PATH_NOT_OBJECT")
        current = child
    current[segments[-1]] = value


def _flatten_paths(value: object, prefix: str = "") -> dict[str, object]:
    if isinstance(value, Mapping):
        flattened: dict[str, object] = {}
        for key in sorted(value):
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            flattened.update(_flatten_paths(value[key], child_prefix))
        return flattened
    return {prefix: value}


@dataclass(frozen=True, slots=True)
class C03ParameterDiff:
    changed_paths: tuple[str, ...]
    unauthorized_paths: tuple[str, ...]
    native_float_present: bool

    @property
    def unauthorized_parameter_diff_count(self) -> int:
        return len(self.unauthorized_paths)


def verify_c03_parameter_allowlist(
    *,
    incumbent_snapshot: Mapping[str, Any],
    candidate_snapshot: Mapping[str, Any],
) -> C03ParameterDiff:
    """Compare full snapshots and permit exactly the owner-selected path."""

    incumbent = _decimalize(incumbent_snapshot)
    candidate = _decimalize(candidate_snapshot)
    if not isinstance(incumbent, Mapping) or not isinstance(candidate, Mapping):
        raise Candidate03ContractError("C03_PARAMETER_SNAPSHOT_INVALID")
    incumbent_flat = _flatten_paths(incumbent)
    candidate_flat = _flatten_paths(candidate)
    all_paths = sorted(set(incumbent_flat) | set(candidate_flat))
    changed = tuple(
        path for path in all_paths if incumbent_flat.get(path) != candidate_flat.get(path)
    )
    allowed = set(C03_ALLOWED_PARAMETER_PATHS)
    unauthorized = tuple(path for path in changed if path not in allowed)
    return C03ParameterDiff(
        changed_paths=changed,
        unauthorized_paths=unauthorized,
        native_float_present=_contains_native_float(incumbent_snapshot)
        or _contains_native_float(candidate_snapshot),
    )


@dataclass(frozen=True, slots=True)
class Candidate03RunDefinition:
    candidate_run_ordinal: int
    authorized_parameter_delta: Mapping[str, Any]
    full_parameter_snapshot: Mapping[str, Any]
    parameter_manifest_hash: str
    candidate_config_hash: str
    incumbent_config_hash: str
    random_seed: int
    unauthorized_parameter_diff_count: int

    def payload(self) -> dict[str, Any]:
        return {
            "candidate_id": CANDIDATE_03_ID,
            "candidate_run_ordinal": self.candidate_run_ordinal,
            "authorized_parameter_delta": copy.deepcopy(dict(self.authorized_parameter_delta)),
            "full_parameter_snapshot": copy.deepcopy(dict(self.full_parameter_snapshot)),
            "parameter_manifest_hash": self.parameter_manifest_hash,
            "candidate_config_hash": self.candidate_config_hash,
            "incumbent_config_hash": self.incumbent_config_hash,
            "random_seed": self.random_seed,
            "unauthorized_parameter_diff_count": self.unauthorized_parameter_diff_count,
        }


@dataclass(frozen=True, slots=True)
class Candidate03ParameterManifest:
    version: str
    candidate_id: str
    candidate_family: str
    parent_model_id: str
    hypothesis: str
    semantic_authority_decision_id: str
    semantic_authority: str
    allowed_parameter_paths: tuple[str, ...]
    explicitly_excluded_parameter_paths: tuple[str, ...]
    incumbent_config_path: str
    incumbent_config_file_sha256: str
    incumbent_config_hash: str
    incumbent_parameter_snapshot: Mapping[str, Any]
    random_seed_policy: str
    planned_run_count: int
    adaptive_search_allowed: bool
    post_validation_parameter_substitution_allowed: bool
    runs: tuple[Candidate03RunDefinition, ...]

    def payload(self) -> dict[str, Any]:
        return {
            "c03_parameter_manifest_version": self.version,
            "candidate_id": self.candidate_id,
            "candidate_family": self.candidate_family,
            "parent_model_id": self.parent_model_id,
            "hypothesis": self.hypothesis,
            "semantic_authority_decision_id": self.semantic_authority_decision_id,
            "semantic_authority": self.semantic_authority,
            "allowed_parameter_paths": list(self.allowed_parameter_paths),
            "explicitly_excluded_parameter_paths": list(self.explicitly_excluded_parameter_paths),
            "incumbent_config_path": self.incumbent_config_path,
            "incumbent_config_file_sha256": self.incumbent_config_file_sha256,
            "incumbent_config_hash": self.incumbent_config_hash,
            "incumbent_parameter_snapshot": copy.deepcopy(dict(self.incumbent_parameter_snapshot)),
            "random_seed_policy": self.random_seed_policy,
            "planned_run_count": self.planned_run_count,
            "runs": [run.payload() for run in self.runs],
            "native_float_allowed": False,
            "adaptive_search_allowed": self.adaptive_search_allowed,
            "post_validation_parameter_substitution_allowed": (
                self.post_validation_parameter_substitution_allowed
            ),
            "c03_uses_general_s4_b_guardrails": C03_USES_GENERAL_S4_B_GUARDRAILS,
            "c03_special_guardrail_threshold_override": C03_SPECIAL_GUARDRAIL_THRESHOLD_OVERRIDE,
        }

    @property
    def manifest_hash(self) -> str:
        return sha256_payload(self.payload())

    def run(self, ordinal: int) -> Candidate03RunDefinition:
        for run in self.runs:
            if run.candidate_run_ordinal == ordinal:
                return run
        raise Candidate03ContractError("C03_RUN_ORDINAL_NOT_IN_MANIFEST")


def _candidate_config_hash(snapshot: Mapping[str, Any]) -> str:
    return sha256_payload(_decimalize(snapshot))


def _run_manifest_hash(
    *,
    ordinal: int,
    parameter_delta: Mapping[str, Any],
    full_snapshot: Mapping[str, Any],
    incumbent_config_hash: str,
) -> str:
    return sha256_payload(
        {
            "manifest_version": C03_PARAMETER_MANIFEST_VERSION,
            "candidate_id": CANDIDATE_03_ID,
            "candidate_run_ordinal": ordinal,
            "parent_model_id": CANDIDATE_03_PARENT_MODEL_ID,
            "semantic_authority_decision_id": C03_OWNER_DECISION_ID,
            "semantic_authority": C03_SEMANTIC_AUTHORITY,
            "authorized_parameter_delta": parameter_delta,
            "full_parameter_snapshot": full_snapshot,
            "incumbent_config_hash": incumbent_config_hash,
            "random_seed": C03_RANDOM_SEED,
        }
    )


def _validate_incumbent_config(config: MaturityCurveConfig) -> None:
    snapshot = _decimalize(config.snapshot)
    if not isinstance(snapshot, Mapping):
        raise Candidate03ContractError("C03_INCUMBENT_CONFIG_SNAPSHOT_INVALID")
    expected: tuple[tuple[str, object], ...] = (
        ("model_family", "shared_spline_partial_pooling"),
        ("random_seed", C03_RANDOM_SEED),
        ("offset.maximum_abs_shift_days", C03_INCUMBENT_OFFSET_MAXIMUM_ABS_SHIFT_DAYS),
        ("offset.minimum_training_samples", C03_INCUMBENT_OFFSET_MINIMUM_TRAINING_SAMPLES),
        (
            "forecast.observed_phase_adjustment_max_days",
            C03_INCUMBENT_FORECAST_OBSERVED_PHASE_ADJUSTMENT_MAX_DAYS,
        ),
    )
    for path, expected_value in expected:
        if _path_value(snapshot, path) != expected_value:
            raise Candidate03ContractError("C03_INCUMBENT_CONFIG_AUTHORITY_MISMATCH")
    if config.config_hash != C03_INCUMBENT_CONFIG_HASH:
        raise Candidate03ContractError("C03_INCUMBENT_CONFIG_HASH_MISMATCH")


def build_candidate_03_manifest(config_path: Path) -> Candidate03ParameterManifest:
    """Build the owner-frozen C03 manifest from the current incumbent config."""

    if not config_path.is_file():
        raise Candidate03ContractError("C03_INCUMBENT_CONFIG_UNAVAILABLE")
    if _file_sha256(config_path) != C03_INCUMBENT_CONFIG_FILE_SHA256:
        raise Candidate03ContractError("C03_INCUMBENT_CONFIG_FILE_IDENTITY_MISMATCH")
    config = load_maturity_curve_config(config_path)
    _validate_incumbent_config(config)
    snapshot = _decimalize(config.snapshot)
    if not isinstance(snapshot, Mapping) or _contains_native_float(snapshot):
        raise Candidate03ContractError("C03_INCUMBENT_CONFIG_SNAPSHOT_INVALID")
    incumbent_snapshot = cast(dict[str, Any], copy.deepcopy(dict(snapshot)))
    runs: list[Candidate03RunDefinition] = []
    for ordinal, value in enumerate(C03_RUN_VALUES, start=1):
        candidate_snapshot = copy.deepcopy(incumbent_snapshot)
        delta = {C03_ALLOWED_PARAMETER_PATHS[0]: value}
        _set_path(candidate_snapshot, C03_ALLOWED_PARAMETER_PATHS[0], value)
        diff = verify_c03_parameter_allowlist(
            incumbent_snapshot=incumbent_snapshot,
            candidate_snapshot=candidate_snapshot,
        )
        if diff.native_float_present or diff.changed_paths != C03_ALLOWED_PARAMETER_PATHS:
            raise Candidate03ContractError("C03_UNAUTHORIZED_PARAMETER_PATH")
        candidate_hash = _candidate_config_hash(candidate_snapshot)
        run_hash = _run_manifest_hash(
            ordinal=ordinal,
            parameter_delta=delta,
            full_snapshot=candidate_snapshot,
            incumbent_config_hash=config.config_hash,
        )
        runs.append(
            Candidate03RunDefinition(
                candidate_run_ordinal=ordinal,
                authorized_parameter_delta=delta,
                full_parameter_snapshot=candidate_snapshot,
                parameter_manifest_hash=run_hash,
                candidate_config_hash=candidate_hash,
                incumbent_config_hash=config.config_hash,
                random_seed=C03_RANDOM_SEED,
                unauthorized_parameter_diff_count=diff.unauthorized_parameter_diff_count,
            )
        )
    manifest = Candidate03ParameterManifest(
        version=C03_PARAMETER_MANIFEST_VERSION,
        candidate_id=CANDIDATE_03_ID,
        candidate_family=C03_FAMILY,
        parent_model_id=C03_PARENT_MODEL_ID,
        hypothesis=C03_HYPOTHESIS,
        semantic_authority_decision_id=C03_OWNER_DECISION_ID,
        semantic_authority=C03_SEMANTIC_AUTHORITY,
        allowed_parameter_paths=C03_ALLOWED_PARAMETER_PATHS,
        explicitly_excluded_parameter_paths=C03_EXCLUDED_PARAMETER_PATHS,
        incumbent_config_path=C03_INCUMBENT_CONFIG_PATH,
        incumbent_config_file_sha256=_file_sha256(config_path),
        incumbent_config_hash=config.config_hash,
        incumbent_parameter_snapshot=incumbent_snapshot,
        random_seed_policy=C03_RANDOM_SEED_POLICY,
        planned_run_count=C03_PLANNED_RUN_COUNT,
        adaptive_search_allowed=C03_ADAPTIVE_SEARCH_ALLOWED,
        post_validation_parameter_substitution_allowed=(
            C03_POST_VALIDATION_PARAMETER_SUBSTITUTION_ALLOWED
        ),
        runs=tuple(runs),
    )
    validate_candidate_03_manifest(manifest, config_path=config_path)
    return manifest


def _registered_c03() -> CandidateRegistration:
    registration = next(
        (item for item in FROZEN_CANDIDATE_REGISTRY if item.candidate_id == CANDIDATE_03_ID),
        None,
    )
    if registration is None:
        raise Candidate03ContractError("C03_CANDIDATE_REGISTRY_MISMATCH")
    return registration


def validate_candidate_03_manifest(
    manifest: Candidate03ParameterManifest,
    *,
    config_path: Path | None = None,
) -> None:
    """Validate the complete C03 contract, not just its declared metadata."""

    registration = _registered_c03()
    expected_registration = CandidateRegistration(
        CANDIDATE_03_ID,
        C03_FAMILY,
        C03_PARENT_MODEL_ID,
        C03_HYPOTHESIS,
        "NOT_AUTHORIZED_UNTIL_S4_SUBTASK_AUTHORIZATION",
        C03_PLANNED_RUN_COUNT,
        C03_RANDOM_SEED_POLICY,
        "REGISTERED_AND_GUARDRAIL_ELIGIBLE",
    )
    if registration != expected_registration:
        raise Candidate03ContractError("C03_CANDIDATE_REGISTRY_MISMATCH")
    if manifest.version != C03_PARAMETER_MANIFEST_VERSION:
        raise Candidate03ContractError("C03_PARAMETER_MANIFEST_VERSION_MISMATCH")
    if (
        manifest.candidate_id,
        manifest.candidate_family,
        manifest.parent_model_id,
        manifest.hypothesis,
    ) != (CANDIDATE_03_ID, C03_FAMILY, C03_PARENT_MODEL_ID, C03_HYPOTHESIS):
        raise Candidate03ContractError("C03_CANDIDATE_REGISTRY_MISMATCH")
    if manifest.semantic_authority_decision_id != C03_OWNER_DECISION_ID:
        raise Candidate03ContractError("C03_OWNER_DECISION_MISMATCH")
    if manifest.semantic_authority != C03_SEMANTIC_AUTHORITY:
        raise Candidate03ContractError("C03_SEMANTIC_AUTHORITY_MISMATCH")
    if manifest.allowed_parameter_paths != C03_ALLOWED_PARAMETER_PATHS:
        raise Candidate03ContractError("C03_PARAMETER_ALLOWLIST_MISMATCH")
    if manifest.explicitly_excluded_parameter_paths != C03_EXCLUDED_PARAMETER_PATHS:
        raise Candidate03ContractError("C03_EXCLUDED_PARAMETER_PATH_MISMATCH")
    if manifest.incumbent_config_path != C03_INCUMBENT_CONFIG_PATH:
        raise Candidate03ContractError("C03_INCUMBENT_CONFIG_PATH_MISMATCH")
    if manifest.incumbent_config_file_sha256 != C03_INCUMBENT_CONFIG_FILE_SHA256:
        raise Candidate03ContractError("C03_INCUMBENT_CONFIG_FILE_IDENTITY_MISMATCH")
    if manifest.incumbent_config_hash != C03_INCUMBENT_CONFIG_HASH:
        raise Candidate03ContractError("C03_INCUMBENT_CONFIG_HASH_MISMATCH")
    if manifest.random_seed_policy != C03_RANDOM_SEED_POLICY:
        raise Candidate03ContractError("C03_RANDOM_SEED_POLICY_MISMATCH")
    if manifest.planned_run_count != C03_PLANNED_RUN_COUNT:
        raise Candidate03ContractError("C03_PLANNED_RUN_COUNT_MISMATCH")
    if manifest.adaptive_search_allowed or manifest.post_validation_parameter_substitution_allowed:
        raise Candidate03ContractError("C03_ADAPTIVE_SEARCH_FORBIDDEN")
    if _contains_native_float(manifest.incumbent_parameter_snapshot):
        raise Candidate03ContractError("C03_NATIVE_FLOAT_FORBIDDEN")
    if tuple(run.candidate_run_ordinal for run in manifest.runs) != (1, 2, 3, 4):
        raise Candidate03ContractError("C03_RUN_ORDER_NOT_FROZEN")
    for run, expected_value in zip(manifest.runs, C03_RUN_VALUES, strict=True):
        expected_delta = {C03_ALLOWED_PARAMETER_PATHS[0]: expected_value}
        diff = verify_c03_parameter_allowlist(
            incumbent_snapshot=manifest.incumbent_parameter_snapshot,
            candidate_snapshot=run.full_parameter_snapshot,
        )
        if diff.native_float_present:
            raise Candidate03ContractError("C03_NATIVE_FLOAT_FORBIDDEN")
        if diff.changed_paths != C03_ALLOWED_PARAMETER_PATHS:
            raise Candidate03ContractError("C03_UNAUTHORIZED_PARAMETER_PATH")
        if diff.unauthorized_parameter_diff_count != 0:
            raise Candidate03ContractError("C03_UNAUTHORIZED_PARAMETER_PATH")
        stored_delta = _decimalize(run.authorized_parameter_delta)
        if not isinstance(stored_delta, Mapping) or dict(stored_delta) != expected_delta:
            raise Candidate03ContractError("C03_PARAMETER_DELTA_MISMATCH")
        if (
            _decimalize(_path_value(run.full_parameter_snapshot, C03_ALLOWED_PARAMETER_PATHS[0]))
            != expected_value
        ):
            raise Candidate03ContractError("C03_RUN_VALUE_MISMATCH")
        if expected_value == C03_INCUMBENT_OFFSET_MAXIMUM_ABS_SHIFT_DAYS:
            raise Candidate03ContractError("C03_RUN_INCLUDES_INCUMBENT_VALUE")
        if run.unauthorized_parameter_diff_count != 0:
            raise Candidate03ContractError("C03_UNAUTHORIZED_PARAMETER_PATH")
        candidate_hash = _candidate_config_hash(run.full_parameter_snapshot)
        if run.candidate_config_hash != candidate_hash:
            raise Candidate03ContractError("C03_CANDIDATE_CONFIG_HASH_MISMATCH")
        if run.incumbent_config_hash != C03_INCUMBENT_CONFIG_HASH:
            raise Candidate03ContractError("C03_INCUMBENT_CONFIG_HASH_MISMATCH")
        if run.random_seed != C03_RANDOM_SEED:
            raise Candidate03ContractError("C03_RANDOM_SEED_MISMATCH")
        expected_run_hash = _run_manifest_hash(
            ordinal=run.candidate_run_ordinal,
            parameter_delta=expected_delta,
            full_snapshot=run.full_parameter_snapshot,
            incumbent_config_hash=C03_INCUMBENT_CONFIG_HASH,
        )
        if run.parameter_manifest_hash != expected_run_hash:
            raise Candidate03ContractError("C03_RUN_MANIFEST_HASH_MISMATCH")
    if config_path is not None:
        if (
            not config_path.is_file()
            or _file_sha256(config_path) != C03_INCUMBENT_CONFIG_FILE_SHA256
        ):
            raise Candidate03ContractError("C03_INCUMBENT_CONFIG_FILE_IDENTITY_MISMATCH")
        config = load_maturity_curve_config(config_path)
        _validate_incumbent_config(config)
        if _decimalize(config.snapshot) != dict(manifest.incumbent_parameter_snapshot):
            raise Candidate03ContractError("C03_INCUMBENT_CONFIG_SNAPSHOT_MISMATCH")


def _config_from_snapshot(
    snapshot: Mapping[str, Any],
    *,
    config_hash: str,
) -> MaturityCurveConfig:
    def value(path: str) -> object:
        return _path_value(snapshot, path)

    def integer(path: str) -> int:
        raw = value(path)
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise Candidate03ContractError("C03_CONFIG_INTEGER_INVALID")
        return raw

    return MaturityCurveConfig(
        rules=MaturityCurveRules(
            curve=CurveRules(
                version=cast(str, value("curve.version")),
                support_min_day=integer("curve.support_min_day"),
                support_max_day=integer("curve.support_max_day"),
                spline_degree=integer("curve.spline_degree"),
                spline_knot_count=integer("curve.spline_knot_count"),
                ridge_alpha=cast(Decimal, value("curve.ridge_alpha")),
            ),
            pooling=PoolingRules(
                minimum_samples=integer("pooling.minimum_samples"),
                minimum_seasons=integer("pooling.minimum_seasons"),
                minimum_farms=integer("pooling.minimum_farms"),
                minimum_subfarms=integer("pooling.minimum_subfarms"),
                full_pooling_sample_target=integer("pooling.full_pooling_sample_target"),
            ),
            offset=OffsetRules(
                maximum_abs_shift_days=cast(Decimal, value("offset.maximum_abs_shift_days")),
                minimum_training_samples=integer("offset.minimum_training_samples"),
            ),
            holidays=HolidayRules(
                spring_festival_codes=tuple(
                    cast(list[str], value("holidays.spring_festival_codes"))
                ),
                disturbance_weight=cast(Decimal, value("holidays.disturbance_weight")),
                exclude_from_loss=bool(value("holidays.exclude_from_loss")),
            ),
            intervals=IntervalRules(
                p80_quantile=cast(Decimal, value("intervals.p80_quantile")),
                p90_quantile=cast(Decimal, value("intervals.p90_quantile")),
                calendar_proxy_widening_factor=cast(
                    Decimal, value("intervals.calendar_proxy_widening_factor")
                ),
                uncalibrated_widening_factor=cast(
                    Decimal, value("intervals.uncalibrated_widening_factor")
                ),
            ),
            forecast=ForecastRules(
                p50_mass_tolerance_kg=cast(Decimal, value("forecast.p50_mass_tolerance_kg")),
                observed_phase_adjustment_max_days=cast(
                    Decimal, value("forecast.observed_phase_adjustment_max_days")
                ),
                minimum_observed_axis_coverage_ratio=cast(
                    Decimal, value("forecast.minimum_observed_axis_coverage_ratio")
                ),
            ),
            random_seed=integer("random_seed"),
            model_family=cast(Literal["shared_spline_partial_pooling"], value("model_family")),
        ),
        config_hash=config_hash,
        snapshot=copy.deepcopy(dict(snapshot)),
    )


def build_candidate_03_derived_config(
    manifest: Candidate03ParameterManifest,
    candidate_run_ordinal: int,
) -> tuple[Candidate03RunDefinition, MaturityCurveConfig]:
    """Build an immutable in-memory candidate config without changing YAML."""

    validate_candidate_03_manifest(manifest)
    run = manifest.run(candidate_run_ordinal)
    diff = verify_c03_parameter_allowlist(
        incumbent_snapshot=manifest.incumbent_parameter_snapshot,
        candidate_snapshot=run.full_parameter_snapshot,
    )
    if diff.native_float_present or diff.unauthorized_parameter_diff_count:
        raise Candidate03ContractError("C03_UNAUTHORIZED_PARAMETER_PATH")
    return run, _config_from_snapshot(
        run.full_parameter_snapshot,
        config_hash=run.candidate_config_hash,
    )


@dataclass(frozen=True, slots=True)
class C03PairingIdentities:
    train_dataset_identity: str
    validation_dataset_identity: str
    actual_label_set_identity: str
    exclusion_policy_identity: str
    cutoff_policy_identity: str
    forecast_horizon_set_identity: str
    business_grain_set_identity: str
    common_comparable_set_identity: str
    metric_contract_identity: str = METRIC_CONTRACT_IDENTITY

    def values(self) -> tuple[tuple[str, str], ...]:
        return (
            ("train_dataset_identity", self.train_dataset_identity),
            ("validation_dataset_identity", self.validation_dataset_identity),
            ("actual_label_set_identity", self.actual_label_set_identity),
            ("exclusion_policy_identity", self.exclusion_policy_identity),
            ("cutoff_policy_identity", self.cutoff_policy_identity),
            ("forecast_horizon_set_identity", self.forecast_horizon_set_identity),
            ("business_grain_set_identity", self.business_grain_set_identity),
            ("common_comparable_set_identity", self.common_comparable_set_identity),
            ("metric_contract_identity", self.metric_contract_identity),
        )


def _validate_pairing_identities(pairing_identities: C03PairingIdentities) -> None:
    for name, value in pairing_identities.values():
        if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
            raise Candidate03ContractError(f"C03_{name.upper()}_IDENTITY_INVALID")
        if value in {"0" * 64, "a" * 64, "b" * 64, "PENDING", "UNKNOWN"}:
            raise Candidate03ContractError(f"C03_{name.upper()}_IDENTITY_PLACEHOLDER")
    if pairing_identities.metric_contract_identity != METRIC_CONTRACT_IDENTITY:
        raise Candidate03ContractError("C03_METRIC_CONTRACT_IDENTITY_MISMATCH")


@dataclass(frozen=True, slots=True)
class Candidate03ExecutionContext:
    """Immutable binding released to the shared durable execution adapter."""

    manifest_hash: str
    candidate_id: str
    candidate_run_ordinal: int
    parameter_manifest_hash: str
    candidate_config_hash: str
    code_commit_sha: str
    evaluation_id: str
    pairing_identities: C03PairingIdentities


def build_candidate_03_execution_context(
    *,
    manifest: Candidate03ParameterManifest,
    run: Candidate03RunDefinition,
    pairing_identities: C03PairingIdentities,
    code_commit_sha: str,
    evaluation_id: str,
) -> Candidate03ExecutionContext:
    """Bind the frozen run and authoritative pairing identities immutably."""

    validate_candidate_03_manifest(manifest)
    if run != manifest.run(run.candidate_run_ordinal):
        raise Candidate03ContractError("C03_RUN_NOT_BOUND_TO_MANIFEST")
    _validate_pairing_identities(pairing_identities)
    if not code_commit_sha or not evaluation_id:
        raise Candidate03ContractError("C03_EXECUTION_IDENTITY_MISSING")
    return Candidate03ExecutionContext(
        manifest_hash=manifest.manifest_hash,
        candidate_id=CANDIDATE_03_ID,
        candidate_run_ordinal=run.candidate_run_ordinal,
        parameter_manifest_hash=run.parameter_manifest_hash,
        candidate_config_hash=run.candidate_config_hash,
        code_commit_sha=code_commit_sha,
        evaluation_id=evaluation_id,
        pairing_identities=pairing_identities,
    )


def build_candidate_03_gate_request(
    *,
    manifest: Candidate03ParameterManifest,
    run: Candidate03RunDefinition,
    pairing_identities: C03PairingIdentities,
    code_commit_sha: str,
    evaluation_id: str,
    candidate_actual_run_count: int = 0,
    global_actual_evaluation_count: int = 4,
    invocation_type: str = "NORMAL_RUN",
    retry_of_evaluation_id: str | None = None,
) -> CandidateExecutionGateRequest:
    """Construct the exact S4-B request for a C03 run.

    The PostgreSQL adapter rebinds the two count fields and retry history from
    verified state immediately before admission.  The defaults describe the
    current 4-of-32 bootstrap only; they are not a second budget authority.
    """

    context = build_candidate_03_execution_context(
        manifest=manifest,
        run=run,
        pairing_identities=pairing_identities,
        code_commit_sha=code_commit_sha,
        evaluation_id=evaluation_id,
    )
    policy_payload = {
        "candidate_id": context.candidate_id,
        "manifest_hash": context.manifest_hash,
        "parameter_manifest_hash": context.parameter_manifest_hash,
        "candidate_config_hash": context.candidate_config_hash,
        "owner_decision_id": C03_OWNER_DECISION_ID,
        "semantic_authority": C03_SEMANTIC_AUTHORITY,
        "allowed_parameter_paths": list(C03_ALLOWED_PARAMETER_PATHS),
        "excluded_parameter_paths": list(C03_EXCLUDED_PARAMETER_PATHS),
        "adaptive_search_allowed": False,
    }
    try:
        canonical_json_dumps(policy_payload)
    except (TypeError, ValueError) as exc:
        raise Candidate03ContractError("C03_POLICY_PAYLOAD_NOT_CANONICAL") from exc
    return CandidateExecutionGateRequest(
        experiment_plan_version=EXPERIMENT_PLAN_VERSION,
        experiment_plan_hash=S4_A_EXPERIMENT_PLAN_HASH_BOUND,
        guardrail_policy_version=GUARDRAIL_POLICY_VERSION,
        guardrail_policy_hash=GUARDRAIL_POLICY_HASH,
        candidate_id=context.candidate_id,
        candidate_run_ordinal=context.candidate_run_ordinal,
        candidate_planned_run_count=C03_PLANNED_RUN_COUNT,
        candidate_actual_run_count=candidate_actual_run_count,
        global_actual_evaluation_count=global_actual_evaluation_count,
        train_dataset_identity=context.pairing_identities.train_dataset_identity,
        validation_dataset_identity=context.pairing_identities.validation_dataset_identity,
        metric_contract_version=METRIC_CONTRACT_VERSION,
        test_access_requested=False,
        test_sealed=True,
        parameter_manifest_hash=context.parameter_manifest_hash,
        code_commit_sha=context.code_commit_sha,
        random_seed=run.random_seed,
        evaluation_id=context.evaluation_id,
        retry_of_evaluation_id=retry_of_evaluation_id,
        candidate_execution_manifest_frozen=True,
        candidate_registry=FROZEN_CANDIDATE_REGISTRY,
        policy_payload=policy_payload,
        actual_label_set_identity=context.pairing_identities.actual_label_set_identity,
        exclusion_policy_identity=context.pairing_identities.exclusion_policy_identity,
        cutoff_policy_identity=context.pairing_identities.cutoff_policy_identity,
        forecast_horizon_set_identity=context.pairing_identities.forecast_horizon_set_identity,
        metric_contract_identity=context.pairing_identities.metric_contract_identity,
        business_grain_set_identity=context.pairing_identities.business_grain_set_identity,
        common_comparable_set_identity=context.pairing_identities.common_comparable_set_identity,
        invocation_type=invocation_type,
    )


async def preflight_candidate_03(
    session: AsyncSession,
    *,
    manifest: Candidate03ParameterManifest,
    candidate_run_ordinal: int,
    pairing_identities: C03PairingIdentities,
    code_commit_sha: str,
    evaluation_id: str,
    invocation_type: str = "NORMAL_RUN",
    retry_of_evaluation_id: str | None = None,
) -> DurableCandidatePreflight:
    """Bind C03 to verified PostgreSQL state without starting an event."""

    validate_candidate_03_manifest(manifest)
    run = manifest.run(candidate_run_ordinal)
    request = build_candidate_03_gate_request(
        manifest=manifest,
        run=run,
        pairing_identities=pairing_identities,
        code_commit_sha=code_commit_sha,
        evaluation_id=evaluation_id,
        invocation_type=invocation_type,
        retry_of_evaluation_id=retry_of_evaluation_id,
    )
    preflight = await S4CandidateExecutionAuthority(session).preflight(request)
    if preflight.allowed and preflight.gate_request is not None:
        if preflight.gate_request.candidate_run_ordinal != candidate_run_ordinal:
            raise Candidate03ContractError("C03_RUN_ORDINAL_NOT_NEXT")
        if preflight.gate_request.global_actual_evaluation_count != (
            preflight.state.effective_consumed if preflight.state is not None else -1
        ):
            raise Candidate03ContractError("C03_EFFECTIVE_COUNT_NOT_BOUND_TO_POSTGRES")
    return preflight


async def execute_authorized_candidate_03(
    session: AsyncSession,
    *,
    manifest: Candidate03ParameterManifest,
    candidate_run_ordinal: int,
    pairing_identities: C03PairingIdentities,
    code_commit_sha: str,
    evaluation_id: str,
    scorer: Any,
    execution_authorized: bool,
    trigger_source: str,
    invocation_type: str = "NORMAL_RUN",
    retry_of_evaluation_id: str | None = None,
) -> DurableCandidateExecutionResult:
    """Execute only through the shared durable boundary.

    Tests may pass a synthetic scorer and explicit authorization.  The normal
    C03 CLI never supplies that authorization in this task.
    """

    preflight = await preflight_candidate_03(
        session,
        manifest=manifest,
        candidate_run_ordinal=candidate_run_ordinal,
        pairing_identities=pairing_identities,
        code_commit_sha=code_commit_sha,
        evaluation_id=evaluation_id,
        invocation_type=invocation_type,
        retry_of_evaluation_id=retry_of_evaluation_id,
    )
    return await S4CandidateExecutionAuthority(session).execute_preflight(
        preflight,
        scorer=scorer,
        execution_authorized=execution_authorized,
        trigger_source=trigger_source,
    )


__all__ = [
    "CANDIDATE_03_FAMILY",
    "CANDIDATE_03_HYPOTHESIS",
    "CANDIDATE_03_ID",
    "CANDIDATE_03_PARENT_MODEL_ID",
    "C03_ADAPTIVE_SEARCH_ALLOWED",
    "C03_ALLOWED_PARAMETER_PATHS",
    "C03_EXCLUDED_PARAMETER_PATHS",
    "C03_FAMILY",
    "C03_HYPOTHESIS",
    "C03_INCUMBENT_CONFIG_FILE_SHA256",
    "C03_INCUMBENT_CONFIG_HASH",
    "C03_OWNER_DECISION_ID",
    "C03_PARAMETER_MANIFEST_VERSION",
    "C03_PARENT_MODEL_ID",
    "C03_PLANNED_RUN_COUNT",
    "C03_RANDOM_SEED",
    "C03_RUN_VALUES",
    "C03_SEMANTIC_AUTHORITY",
    "C03PairingIdentities",
    "Candidate03ExecutionContext",
    "Candidate03ContractError",
    "Candidate03ParameterManifest",
    "Candidate03RunDefinition",
    "build_candidate_03_derived_config",
    "build_candidate_03_execution_context",
    "build_candidate_03_gate_request",
    "build_candidate_03_manifest",
    "execute_authorized_candidate_03",
    "preflight_candidate_03",
    "validate_candidate_03_manifest",
    "verify_c03_parameter_allowlist",
]
