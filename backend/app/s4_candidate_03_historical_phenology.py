"""C03 manifest/audit surface with a fail-closed canonical scorer boundary.

The first readiness attempt contained a SOURCE-002-only group-peak-delta
prototype.  That prototype is retained below for isolated mathematical tests
and historical auditability, but it is *not* the production C03 execution
authority.  The production phenology shift model is trained by
``backend.app.maturity.service.train_maturity_curve`` from resolved maturity
samples whose plan/weather/location/base-temperature authorities are not
present in ``MaterializableRow``.  Until that equivalence and input authority
are established, C03 execution must fail closed.
"""

from __future__ import annotations

import copy
import hashlib
import re
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, replace
from dataclasses import fields as dataclass_fields
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, cast

import numpy as np

from backend.app.maturity.config import MaturityCurveConfig, load_maturity_curve_config
from backend.app.maturity.schemas import ShiftModelArtifact
from backend.app.rolling_backtest.canonical import canonical_json_dumps, sha256_payload
from backend.app.s2_materialized_dataset.shared.contracts import MaterializableRow
from backend.app.s4_experiment import (
    EXPERIMENT_PLAN_V2_HASH,
    EXPERIMENT_PLAN_V2_VERSION,
    FROZEN_CANDIDATE_REGISTRY,
    INCUMBENT_MODEL_ID,
    METRIC_CONTRACT_IDENTITY,
    METRIC_CONTRACT_VERSION,
    V3_COMPLETE_DAILY_ROWSET_AUTHORITY,
    V3_EVALUATION_SURFACE_ID,
    V3_FORECAST_HORIZONS,
    V3_MISSING_DAY_ZERO_FILL,
    V4_GUARDRAIL_POLICY_HASH,
    V4_GUARDRAIL_POLICY_VERSION,
    CandidateExecutionGateRequest,
    CandidateExecutionGateResult,
    CandidateRegistration,
    check_candidate_execution_gate,
)

if TYPE_CHECKING:
    from backend.app.s4_local_engineering import V2HistoricalEvaluationAuthority

C03_CANDIDATE_ID: Final[str] = "03_phenology_offset"
C03_CANDIDATE_FAMILY: Final[str] = "PARAMETER_CALIBRATION"
C03_PARENT_MODEL_ID: Final[str] = INCUMBENT_MODEL_ID
C03_HYPOTHESIS: Final[str] = "versioned_phenology_offset_reduces_timing_error"
C03_OWNER_DECISION_ID: Final[str] = "V0_3_S4_C03_PHENOLOGY_OFFSET_SEMANTIC_DECISION_R1"
C03_SEMANTIC: Final[str] = "TRAINING_TIME_LEARNED_SHIFT_MODEL_BOUND"
C03_ALLOWED_PARAMETER_PATH: Final[str] = "offset.maximum_abs_shift_days"
C03_EXCLUDED_PARAMETER_PATH: Final[str] = "forecast.observed_phase_adjustment_max_days"
C03_ALLOWED_PARAMETER_PATHS: Final[tuple[str, ...]] = (C03_ALLOWED_PARAMETER_PATH,)
C03_EXCLUDED_PARAMETER_PATHS: Final[tuple[str, ...]] = (C03_EXCLUDED_PARAMETER_PATH,)
C03_PARAMETER_MANIFEST_VERSION: Final[str] = (
    "v0.3-s4-c03-phenology-offset-manifest-v2-historical-only"
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
C03_INCUMBENT_VALUE: Final[Decimal] = Decimal("21")
C03_INCUMBENT_CONFIG_PATH: Final[str] = "configs/maturity_curve.yaml"
C03_INCUMBENT_CONFIG_FILE_SHA256: Final[str] = (
    "fc023976a228c36556ed5f7ababe722a3dd8a558ed11e0473eb415b52dd69ace"
)
C03_INCUMBENT_CONFIG_HASH: Final[str] = (
    "3571477d5822f57cd2c424620915560e22481f48983b397a1f1b8934e1a7612c"
)
C03_INCUMBENT_OFFSET_MINIMUM_TRAINING_SAMPLES: Final[int] = 3
C03_INCUMBENT_FORECAST_PHASE_ADJUSTMENT_MAX_DAYS: Final[Decimal] = Decimal("14")
C03_SOURCE_ID: Final[str] = "SOURCE_002"
C03_MATERIALIZED_DATASET_IDENTITY: Final[str] = (
    "f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785"
)
C03_TRAIN_ROWS: Final[int] = 16_224
C03_VALIDATION_ROWS: Final[int] = 8_006
C03_TRAIN_DATASET_IDENTITY: Final[str] = (
    "be2d4184434a0f389af21c315945322e9216cd17cc471b772e3fff389d3386d2"
)
C03_VALIDATION_DATASET_IDENTITY: Final[str] = (
    "4cbf1119f83034464159210ebbbeea5ec87848f92ce044bb328949a8f5331d06"
)
C03_FORECAST_HORIZONS: Final[tuple[int, ...]] = V3_FORECAST_HORIZONS
C03_EVALUATION_SURFACE_ID: Final[str] = V3_EVALUATION_SURFACE_ID
C03_COMPLETE_DAILY_ROWSET_AUTHORITY: Final[bool] = V3_COMPLETE_DAILY_ROWSET_AUTHORITY
C03_MISSING_DAY_ZERO_FILL: Final[bool] = V3_MISSING_DAY_ZERO_FILL
C03_TEST_REMAINS_SEALED: Final[bool] = True
C03_CANONICAL_SHIFT_MODEL_BLOCKER: Final[str] = (
    "C03_CANONICAL_TRAINING_SHIFT_MODEL_NOT_SEPARABLE_FROM_FORWARD_LOOKING_AUTHORITY"
)
C03_HISTORICAL_ONLY_SCORING_PATH_EXISTS: Final[bool] = False
C03_PARAMETER_REACHES_PREDICTION_MATH: Final[bool] = False
C03_PARAMETER_CHANGE_CAN_CHANGE_PREDICTION: Final[bool] = False
C03_CANONICAL_PARAMETER_CHANGE_STATUS: Final[str] = "NOT_PROVEN"
C03_USES_WEATHER: Final[bool] = False
C03_USES_PRODUCTION_PLAN: Final[bool] = False
C03_USES_TASK8: Final[bool] = False
C03_USES_TASK9: Final[bool] = False
C03_USES_CURRENT_SEASON_INPUT: Final[bool] = False
C03_USES_PROSPECTIVE_CAPTURE: Final[bool] = False
C03_USES_WALL_CLOCK_WAIT: Final[bool] = False
C03_CANONICAL_PRODUCTION_TRAINING_PATH: Final[str] = (
    "backend.app.maturity.service.train_maturity_curve"
)
C03_CANONICAL_SHIFT_BUILDER_PATH: Final[str] = "backend.app.maturity.service._build_shift_model"
C03_CANONICAL_SHIFT_PREDICTOR_PATH: Final[str] = "backend.app.maturity.service._predict_shift_days"
C03_CANONICAL_FORECAST_PATH: Final[str] = "backend.app.maturity.service.forecast_natural_maturity"
C03_CANONICAL_PRODUCTION_SHIFT_PATHS: Final[tuple[str, ...]] = (
    C03_CANONICAL_PRODUCTION_TRAINING_PATH,
    C03_CANONICAL_SHIFT_BUILDER_PATH,
    C03_CANONICAL_SHIFT_PREDICTOR_PATH,
    C03_CANONICAL_FORECAST_PATH,
)
C03_NON_CANONICAL_PROTOTYPE_PATH: Final[str] = (
    "backend.app.s4_candidate_03_historical_phenology.C03HistoricalPhenologyScorer.predict_rows"
)
# No SOURCE-002-only canonical scorer is currently bound to C03.
C03_HISTORICAL_SCORER_PATH: Final[str] = "NONE_C03_CANONICAL_SOURCE_002_SCORER"
C03_HISTORICAL_ONLY_SCORER_PATH: Final[str] = C03_HISTORICAL_SCORER_PATH
C03_NON_CANONICAL_PROTOTYPE_STATUS: Final[str] = "NON_CANONICAL_EXPERIMENTAL_PROTOTYPE"
C03_NON_CANONICAL_PROTOTYPE_IS_EXECUTION_AUTHORITY: Final[bool] = False
C03_CANONICAL_SHIFT_TARGET_DEFINITION: Final[str] = (
    "observed_peak_day - parent_curve_artifact.peak_day"
)
C03_CANONICAL_TRAINING_FEATURES: Final[tuple[str, ...]] = (
    "altitude_m",
    "tree_age_years",
    "pruning_offset_days",
    "flowering_peak_offset_days",
    "first_pick_offset_days",
    "facility_type",
)
C03_CANONICAL_TRAINING_REQUIRED_INPUTS: Final[tuple[str, ...]] = (
    "training_sample.training_points",
    "parent_curve_artifact.peak_day",
    *(f"training_sample.feature_values.{name}" for name in C03_CANONICAL_TRAINING_FEATURES),
)
C03_CANONICAL_FORWARD_LOOKING_AUTHORITY_DOMAINS: Final[tuple[str, ...]] = (
    "analytics_build_run",
    "production_plan",
    "location_reference",
    "base_temperature_search",
    "weather_mapping_and_observations",
)
C03_SOURCE002_MATERIALIZABLE_FIELDS: Final[tuple[str, ...]] = tuple(
    field.name for field in dataclass_fields(MaterializableRow)
)
C03_AUTHORITY_CLASS: Final[str] = "S4_V4_SPARSE_HORIZON_HISTORICAL_ONLY_CANDIDATE_03"
C03_EXCLUSION_POLICY_IDENTITY: Final[str] = sha256_payload(
    {
        "policy": "V0_3_S4_HISTORICAL_ONLY_EXCLUSION_POLICY_V1",
        "allowed_sources": ["SOURCE_002_TRAIN", "SOURCE_002_VALIDATION_TARGET_IDENTITIES"],
        "excluded_sources": ["TEST", "WEATHER", "PRODUCTION_PLAN", "TASK8", "TASK9"],
        "test_remains_sealed": True,
    }
)
_SHA256_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")
_DECIMAL_QUANTUM: Final[Decimal] = Decimal("0.000001")
_MIN_CURVE_POINTS: Final[int] = 4

GroupKey = tuple[str, str, str, str]


class C03HistoricalPhenologyError(ValueError):
    """Sanitized C03 historical-only contract failure."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


@dataclass(frozen=True, slots=True)
class C03CanonicalTrainingInputAudit:
    """Read-only audit of the production shift-model input boundary.

    This object intentionally describes availability, not a replacement
    trainer.  ``MaterializableRow`` is the only SOURCE-002 object admitted to
    the V2 historical lane, so missing canonical inputs are a hard boundary.
    """

    production_training_path: str
    production_shift_builder_path: str
    production_shift_predictor_path: str
    production_forecast_path: str
    shift_target_definition: str
    required_training_features: tuple[str, ...]
    required_training_inputs: tuple[str, ...]
    source002_materializable_fields: tuple[str, ...]
    missing_source002_inputs: tuple[str, ...]
    forward_looking_authority_domains: tuple[str, ...]
    source002_can_supply_canonical_inputs: bool
    separable_from_forward_looking_authority: bool
    reason_code: str | None

    def payload(self) -> dict[str, object]:
        return {
            "production_training_path": self.production_training_path,
            "production_shift_builder_path": self.production_shift_builder_path,
            "production_shift_predictor_path": self.production_shift_predictor_path,
            "production_forecast_path": self.production_forecast_path,
            "shift_target_definition": self.shift_target_definition,
            "required_training_features": list(self.required_training_features),
            "required_training_inputs": list(self.required_training_inputs),
            "source002_materializable_fields": list(self.source002_materializable_fields),
            "missing_source002_inputs": list(self.missing_source002_inputs),
            "forward_looking_authority_domains": list(self.forward_looking_authority_domains),
            "source002_can_supply_canonical_inputs": self.source002_can_supply_canonical_inputs,
            "separable_from_forward_looking_authority": (
                self.separable_from_forward_looking_authority
            ),
            "reason_code": self.reason_code,
        }


def audit_c03_canonical_training_inputs() -> C03CanonicalTrainingInputAudit:
    """Audit canonical production inputs without loading data or running a model."""

    available_fields = set(C03_SOURCE002_MATERIALIZABLE_FIELDS)
    # These are resolved-sample/artifact paths, not aliases that may be
    # inferred from a row's date, quantity, or business identity.
    missing_inputs = tuple(
        path for path in C03_CANONICAL_TRAINING_REQUIRED_INPUTS if path not in available_fields
    )
    return C03CanonicalTrainingInputAudit(
        production_training_path=C03_CANONICAL_PRODUCTION_TRAINING_PATH,
        production_shift_builder_path=C03_CANONICAL_SHIFT_BUILDER_PATH,
        production_shift_predictor_path=C03_CANONICAL_SHIFT_PREDICTOR_PATH,
        production_forecast_path=C03_CANONICAL_FORECAST_PATH,
        shift_target_definition=C03_CANONICAL_SHIFT_TARGET_DEFINITION,
        required_training_features=C03_CANONICAL_TRAINING_FEATURES,
        required_training_inputs=C03_CANONICAL_TRAINING_REQUIRED_INPUTS,
        source002_materializable_fields=C03_SOURCE002_MATERIALIZABLE_FIELDS,
        missing_source002_inputs=missing_inputs,
        forward_looking_authority_domains=C03_CANONICAL_FORWARD_LOOKING_AUTHORITY_DOMAINS,
        source002_can_supply_canonical_inputs=not missing_inputs,
        separable_from_forward_looking_authority=False,
        reason_code=(C03_CANONICAL_SHIFT_MODEL_BLOCKER if missing_inputs else None),
    )


def _q(value: Decimal) -> Decimal:
    if type(value) is not Decimal or not value.is_finite():
        raise C03HistoricalPhenologyError("C03_NONFINITE_DECIMAL")
    return value.quantize(_DECIMAL_QUANTUM, rounding=ROUND_HALF_EVEN)


def _decimalize(value: object) -> object:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise C03HistoricalPhenologyError("C03_NONFINITE_DECIMAL")
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


def _path_value(snapshot: Mapping[str, Any], dotted_path: str) -> object:
    current: object = snapshot
    for segment in dotted_path.split("."):
        if not isinstance(current, Mapping) or segment not in current:
            raise C03HistoricalPhenologyError("C03_PARAMETER_PATH_MISSING")
        current = current[segment]
    return current


def _set_path(snapshot: dict[str, Any], dotted_path: str, value: object) -> None:
    segments = dotted_path.split(".")
    current = snapshot
    for segment in segments[:-1]:
        child = current.get(segment)
        if not isinstance(child, dict):
            raise C03HistoricalPhenologyError("C03_PARAMETER_PATH_NOT_OBJECT")
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
    """Full-snapshot diff used by the V2-bound allowlist."""

    changed_paths: tuple[str, ...]
    unauthorized_paths: tuple[str, ...]
    native_float_present: bool

    @property
    def unauthorized_parameter_diff_count(self) -> int:
        return len(self.unauthorized_paths)


def verify_c03_historical_parameter_allowlist(
    *, incumbent_snapshot: Mapping[str, object], candidate_snapshot: Mapping[str, object]
) -> C03ParameterDiff:
    """Verify the sole C03 mutation against complete snapshots."""

    incumbent = _decimalize(incumbent_snapshot)
    candidate = _decimalize(candidate_snapshot)
    if not isinstance(incumbent, Mapping) or not isinstance(candidate, Mapping):
        raise C03HistoricalPhenologyError("C03_PARAMETER_SNAPSHOT_INVALID")
    incumbent_flat = _flatten_paths(incumbent)
    candidate_flat = _flatten_paths(candidate)
    all_paths = sorted(set(incumbent_flat) | set(candidate_flat))
    changed_paths = tuple(
        path for path in all_paths if incumbent_flat.get(path) != candidate_flat.get(path)
    )
    unauthorized_paths = tuple(
        path for path in changed_paths if path not in C03_ALLOWED_PARAMETER_PATHS
    )
    return C03ParameterDiff(
        changed_paths=changed_paths,
        unauthorized_paths=unauthorized_paths,
        native_float_present=(
            _contains_native_float(incumbent_snapshot) or _contains_native_float(candidate_snapshot)
        ),
    )


def _config_file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_incumbent_config(path: Path | None, config: MaturityCurveConfig) -> None:
    if path is not None and path.as_posix().endswith(C03_INCUMBENT_CONFIG_PATH) is False:
        raise C03HistoricalPhenologyError("C03_INCUMBENT_CONFIG_PATH_MISMATCH")
    if path is not None and _config_file_sha256(path) != C03_INCUMBENT_CONFIG_FILE_SHA256:
        raise C03HistoricalPhenologyError("C03_INCUMBENT_CONFIG_FILE_IDENTITY_MISMATCH")
    snapshot = _decimalize(config.snapshot)
    if not isinstance(snapshot, Mapping) or _contains_native_float(snapshot):
        raise C03HistoricalPhenologyError("C03_INCUMBENT_CONFIG_SNAPSHOT_INVALID")
    expected = (
        ("model_family", "shared_spline_partial_pooling"),
        ("random_seed", C03_RANDOM_SEED),
        ("offset.maximum_abs_shift_days", C03_INCUMBENT_VALUE),
        ("offset.minimum_training_samples", C03_INCUMBENT_OFFSET_MINIMUM_TRAINING_SAMPLES),
        (
            "forecast.observed_phase_adjustment_max_days",
            C03_INCUMBENT_FORECAST_PHASE_ADJUSTMENT_MAX_DAYS,
        ),
    )
    for field, expected_value in expected:
        if _path_value(snapshot, field) != expected_value:
            raise C03HistoricalPhenologyError("C03_INCUMBENT_CONFIG_SEMANTIC_MISMATCH")
    if config.config_hash != C03_INCUMBENT_CONFIG_HASH:
        raise C03HistoricalPhenologyError("C03_INCUMBENT_CONFIG_HASH_MISMATCH")


def _validate_authority(authority: V2HistoricalEvaluationAuthority) -> None:
    if authority.source_id != C03_SOURCE_ID:
        raise C03HistoricalPhenologyError("C03_SOURCE_002_IDENTITY_MISMATCH")
    if authority.materialized_dataset_identity_sha256 != C03_MATERIALIZED_DATASET_IDENTITY:
        raise C03HistoricalPhenologyError("C03_MATERIALIZED_DATASET_IDENTITY_MISMATCH")
    if (
        authority.train_row_count != C03_TRAIN_ROWS
        or authority.validation_row_count != C03_VALIDATION_ROWS
        or authority.train_dataset_identity != C03_TRAIN_DATASET_IDENTITY
        or authority.validation_dataset_identity != C03_VALIDATION_DATASET_IDENTITY
    ):
        raise C03HistoricalPhenologyError("C03_PARTITION_IDENTITY_MISMATCH")
    if authority.evaluation_row_count != 688:
        raise C03HistoricalPhenologyError("C03_EVALUATION_TARGET_ROW_COUNT_MISMATCH")
    if authority.requested_forecast_horizons != C03_FORECAST_HORIZONS:
        raise C03HistoricalPhenologyError("C03_HORIZON_SET_MISMATCH")
    if authority.observed_forecast_horizons != C03_FORECAST_HORIZONS:
        raise C03HistoricalPhenologyError("C03_HORIZON_SET_INCOMPLETE")
    if authority.test_remains_sealed is not True:
        raise C03HistoricalPhenologyError("C03_TEST_MUST_REMAIN_SEALED")


@dataclass(frozen=True, slots=True)
class C03HistoricalRunDefinition:
    """One immutable V4-bound C03 run definition."""

    candidate_run_ordinal: int
    parameter_value: Decimal
    authorized_parameter_delta: Mapping[str, object]
    full_parameter_snapshot: Mapping[str, object]
    parameter_manifest_hash: str
    candidate_config_hash: str
    incumbent_config_hash: str
    random_seed: int
    unauthorized_parameter_diff_count: int

    def payload(self) -> dict[str, object]:
        return {
            "candidate_id": C03_CANDIDATE_ID,
            "candidate_run_ordinal": self.candidate_run_ordinal,
            "parameter_value": self.parameter_value,
            "authorized_parameter_delta": copy.deepcopy(dict(self.authorized_parameter_delta)),
            "full_parameter_snapshot": copy.deepcopy(dict(self.full_parameter_snapshot)),
            "parameter_manifest_hash": self.parameter_manifest_hash,
            "candidate_config_hash": self.candidate_config_hash,
            "incumbent_config_hash": self.incumbent_config_hash,
            "random_seed": self.random_seed,
            "unauthorized_parameter_diff_count": self.unauthorized_parameter_diff_count,
        }


@dataclass(frozen=True, slots=True)
class C03HistoricalParameterManifest:
    """Current execution manifest; the old V1 manifest is never reused."""

    version: str
    candidate_id: str
    candidate_family: str
    parent_model_id: str
    hypothesis: str
    semantic_authority_decision_id: str
    semantic_authority: str
    allowed_parameter_paths: tuple[str, ...]
    explicitly_excluded_parameter_paths: tuple[str, ...]
    experiment_plan_version: str
    experiment_plan_hash: str
    guardrail_policy_version: str
    guardrail_policy_hash: str
    evaluation_surface_identity: str
    forecast_horizons: tuple[int, ...]
    complete_daily_rowset_authority: bool
    missing_day_zero_fill: bool
    source_id: str
    materialized_dataset_identity: str
    train_dataset_identity: str
    validation_dataset_identity: str
    actual_label_set_identity: str
    exclusion_policy_identity: str
    cutoff_policy_identity: str
    forecast_horizon_set_identity: str
    business_grain_set_identity: str
    common_comparable_set_identity: str
    forecast_cutoff_at: date
    evaluation_target_row_count: int
    incumbent_config_path: str
    incumbent_config_file_sha256: str
    incumbent_config_hash: str
    incumbent_parameter_snapshot: Mapping[str, object]
    random_seed_policy: str
    random_seed: int
    planned_run_count: int
    adaptive_search_allowed: bool
    post_validation_parameter_substitution_allowed: bool
    code_commit_binding: str
    runs: tuple[C03HistoricalRunDefinition, ...]

    def payload(self) -> dict[str, object]:
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
            "experiment_plan_version": self.experiment_plan_version,
            "experiment_plan_hash": self.experiment_plan_hash,
            "guardrail_policy_version": self.guardrail_policy_version,
            "guardrail_policy_hash": self.guardrail_policy_hash,
            "evaluation_surface_identity": self.evaluation_surface_identity,
            "forecast_horizons": list(self.forecast_horizons),
            "complete_daily_rowset_authority": self.complete_daily_rowset_authority,
            "missing_day_zero_fill": self.missing_day_zero_fill,
            "source_id": self.source_id,
            "materialized_dataset_identity": self.materialized_dataset_identity,
            "train_dataset_identity": self.train_dataset_identity,
            "validation_dataset_identity": self.validation_dataset_identity,
            "actual_label_set_identity": self.actual_label_set_identity,
            "exclusion_policy_identity": self.exclusion_policy_identity,
            "cutoff_policy_identity": self.cutoff_policy_identity,
            "forecast_horizon_set_identity": self.forecast_horizon_set_identity,
            "business_grain_set_identity": self.business_grain_set_identity,
            "common_comparable_set_identity": self.common_comparable_set_identity,
            "forecast_cutoff_at": self.forecast_cutoff_at,
            "evaluation_target_row_count": self.evaluation_target_row_count,
            "incumbent_config_path": self.incumbent_config_path,
            "incumbent_config_file_sha256": self.incumbent_config_file_sha256,
            "incumbent_config_hash": self.incumbent_config_hash,
            "incumbent_parameter_snapshot": copy.deepcopy(dict(self.incumbent_parameter_snapshot)),
            "random_seed_policy": self.random_seed_policy,
            "random_seed": self.random_seed,
            "planned_run_count": self.planned_run_count,
            "adaptive_search_allowed": self.adaptive_search_allowed,
            "post_validation_parameter_substitution_allowed": (
                self.post_validation_parameter_substitution_allowed
            ),
            "native_float_allowed": False,
            "code_commit_binding": self.code_commit_binding,
            "runs": [run.payload() for run in self.runs],
        }

    @property
    def manifest_hash(self) -> str:
        return sha256_payload(self.payload())

    def run(self, ordinal: int) -> C03HistoricalRunDefinition:
        for run in self.runs:
            if run.candidate_run_ordinal == ordinal:
                return run
        raise C03HistoricalPhenologyError("C03_RUN_ORDINAL_NOT_IN_MANIFEST")


def _candidate_config_hash(snapshot: Mapping[str, object]) -> str:
    return sha256_payload(_decimalize(snapshot))


def _run_manifest_hash(
    *,
    manifest_version: str,
    ordinal: int,
    value: Decimal,
    parameter_delta: Mapping[str, object],
    full_snapshot: Mapping[str, object],
    incumbent_config_hash: str,
    code_commit_binding: str,
) -> str:
    return sha256_payload(
        {
            "manifest_version": manifest_version,
            "candidate_id": C03_CANDIDATE_ID,
            "candidate_run_ordinal": ordinal,
            "parameter_value": value,
            "authorized_parameter_delta": parameter_delta,
            "full_parameter_snapshot": full_snapshot,
            "incumbent_config_hash": incumbent_config_hash,
            "random_seed": C03_RANDOM_SEED,
            "code_commit_binding": code_commit_binding,
        }
    )


def build_c03_historical_only_manifest(
    *, authority: V2HistoricalEvaluationAuthority, config_path: Path, code_commit_binding: str
) -> C03HistoricalParameterManifest:
    """Build the V2/V4 C03 manifest without reading TEST or scoring."""

    _validate_authority(authority)
    if _COMMIT_PATTERN.fullmatch(code_commit_binding) is None:
        raise C03HistoricalPhenologyError("C03_CODE_COMMIT_BINDING_INVALID")
    if not config_path.is_file():
        raise C03HistoricalPhenologyError("C03_INCUMBENT_CONFIG_UNAVAILABLE")
    config = load_maturity_curve_config(config_path)
    _validate_incumbent_config(config_path, config)
    snapshot = _decimalize(config.snapshot)
    if not isinstance(snapshot, Mapping) or _contains_native_float(snapshot):
        raise C03HistoricalPhenologyError("C03_INCUMBENT_CONFIG_SNAPSHOT_INVALID")
    incumbent_snapshot = cast(dict[str, object], copy.deepcopy(dict(snapshot)))
    runs: list[C03HistoricalRunDefinition] = []
    for ordinal, value in enumerate(C03_RUN_VALUES, start=1):
        candidate_snapshot = copy.deepcopy(incumbent_snapshot)
        _set_path(candidate_snapshot, C03_ALLOWED_PARAMETER_PATH, value)
        diff = verify_c03_historical_parameter_allowlist(
            incumbent_snapshot=incumbent_snapshot,
            candidate_snapshot=candidate_snapshot,
        )
        if diff.native_float_present or diff.changed_paths != C03_ALLOWED_PARAMETER_PATHS:
            raise C03HistoricalPhenologyError("C03_UNAUTHORIZED_PARAMETER_PATH")
        candidate_hash = _candidate_config_hash(candidate_snapshot)
        delta = {C03_ALLOWED_PARAMETER_PATH: value}
        runs.append(
            C03HistoricalRunDefinition(
                candidate_run_ordinal=ordinal,
                parameter_value=value,
                authorized_parameter_delta=delta,
                full_parameter_snapshot=candidate_snapshot,
                parameter_manifest_hash=_run_manifest_hash(
                    manifest_version=C03_PARAMETER_MANIFEST_VERSION,
                    ordinal=ordinal,
                    value=value,
                    parameter_delta=delta,
                    full_snapshot=candidate_snapshot,
                    incumbent_config_hash=config.config_hash,
                    code_commit_binding=code_commit_binding,
                ),
                candidate_config_hash=candidate_hash,
                incumbent_config_hash=config.config_hash,
                random_seed=C03_RANDOM_SEED,
                unauthorized_parameter_diff_count=diff.unauthorized_parameter_diff_count,
            )
        )
    manifest = C03HistoricalParameterManifest(
        version=C03_PARAMETER_MANIFEST_VERSION,
        candidate_id=C03_CANDIDATE_ID,
        candidate_family=C03_CANDIDATE_FAMILY,
        parent_model_id=C03_PARENT_MODEL_ID,
        hypothesis=C03_HYPOTHESIS,
        semantic_authority_decision_id=C03_OWNER_DECISION_ID,
        semantic_authority=C03_SEMANTIC,
        allowed_parameter_paths=C03_ALLOWED_PARAMETER_PATHS,
        explicitly_excluded_parameter_paths=C03_EXCLUDED_PARAMETER_PATHS,
        experiment_plan_version=EXPERIMENT_PLAN_V2_VERSION,
        experiment_plan_hash=EXPERIMENT_PLAN_V2_HASH,
        guardrail_policy_version=V4_GUARDRAIL_POLICY_VERSION,
        guardrail_policy_hash=V4_GUARDRAIL_POLICY_HASH,
        evaluation_surface_identity=C03_EVALUATION_SURFACE_ID,
        forecast_horizons=C03_FORECAST_HORIZONS,
        complete_daily_rowset_authority=C03_COMPLETE_DAILY_ROWSET_AUTHORITY,
        missing_day_zero_fill=C03_MISSING_DAY_ZERO_FILL,
        source_id=authority.source_id,
        materialized_dataset_identity=authority.materialized_dataset_identity_sha256,
        train_dataset_identity=authority.train_dataset_identity,
        validation_dataset_identity=authority.validation_dataset_identity,
        actual_label_set_identity=authority.actual_label_set_identity,
        exclusion_policy_identity=C03_EXCLUSION_POLICY_IDENTITY,
        cutoff_policy_identity=authority.cutoff_policy_identity,
        forecast_horizon_set_identity=authority.forecast_horizon_set_identity,
        business_grain_set_identity=authority.business_grain_set_identity,
        common_comparable_set_identity=authority.common_comparable_set_identity,
        forecast_cutoff_at=authority.forecast_cutoff_at,
        evaluation_target_row_count=authority.evaluation_row_count,
        incumbent_config_path=C03_INCUMBENT_CONFIG_PATH,
        incumbent_config_file_sha256=_config_file_sha256(config_path),
        incumbent_config_hash=config.config_hash,
        incumbent_parameter_snapshot=incumbent_snapshot,
        random_seed_policy=C03_RANDOM_SEED_POLICY,
        random_seed=C03_RANDOM_SEED,
        planned_run_count=C03_PLANNED_RUN_COUNT,
        adaptive_search_allowed=False,
        post_validation_parameter_substitution_allowed=False,
        code_commit_binding=code_commit_binding,
        runs=tuple(runs),
    )
    validate_c03_historical_only_manifest(manifest)
    return manifest


def _registered_c03() -> CandidateRegistration:
    registration = next(
        (item for item in FROZEN_CANDIDATE_REGISTRY if item.candidate_id == C03_CANDIDATE_ID),
        None,
    )
    if registration is None:
        raise C03HistoricalPhenologyError("C03_CANDIDATE_REGISTRY_MISMATCH")
    return registration


def _require_sha(name: str, value: str) -> None:
    if _SHA256_PATTERN.fullmatch(value) is None:
        raise C03HistoricalPhenologyError(f"C03_{name.upper()}_IDENTITY_INVALID")


def validate_c03_historical_only_manifest(manifest: C03HistoricalParameterManifest) -> None:
    """Fail closed on registry, policy, snapshot, and run-hash drift."""

    expected_registration = CandidateRegistration(
        C03_CANDIDATE_ID,
        C03_CANDIDATE_FAMILY,
        C03_PARENT_MODEL_ID,
        C03_HYPOTHESIS,
        "NOT_AUTHORIZED_UNTIL_S4_SUBTASK_AUTHORIZATION",
        C03_PLANNED_RUN_COUNT,
        C03_RANDOM_SEED_POLICY,
        "REGISTERED_AND_GUARDRAIL_ELIGIBLE",
    )
    if _registered_c03() != expected_registration:
        raise C03HistoricalPhenologyError("C03_CANDIDATE_REGISTRY_MISMATCH")
    if manifest.version != C03_PARAMETER_MANIFEST_VERSION:
        raise C03HistoricalPhenologyError("C03_V1_MANIFEST_NOT_ALLOWED_FOR_V4_EXECUTION")
    if (
        manifest.candidate_id,
        manifest.candidate_family,
        manifest.parent_model_id,
        manifest.hypothesis,
    ) != (C03_CANDIDATE_ID, C03_CANDIDATE_FAMILY, C03_PARENT_MODEL_ID, C03_HYPOTHESIS):
        raise C03HistoricalPhenologyError("C03_CANDIDATE_REGISTRY_MISMATCH")
    if manifest.semantic_authority_decision_id != C03_OWNER_DECISION_ID:
        raise C03HistoricalPhenologyError("C03_OWNER_DECISION_MISMATCH")
    if manifest.semantic_authority != C03_SEMANTIC:
        raise C03HistoricalPhenologyError("C03_SEMANTIC_AUTHORITY_MISMATCH")
    if manifest.allowed_parameter_paths != C03_ALLOWED_PARAMETER_PATHS:
        raise C03HistoricalPhenologyError("C03_PARAMETER_ALLOWLIST_MISMATCH")
    if manifest.explicitly_excluded_parameter_paths != C03_EXCLUDED_PARAMETER_PATHS:
        raise C03HistoricalPhenologyError("C03_EXCLUDED_PARAMETER_PATH_MISMATCH")
    if (
        manifest.experiment_plan_version != EXPERIMENT_PLAN_V2_VERSION
        or manifest.experiment_plan_hash != EXPERIMENT_PLAN_V2_HASH
    ):
        raise C03HistoricalPhenologyError("C03_EXPERIMENT_PLAN_V2_BINDING_MISMATCH")
    if (
        manifest.guardrail_policy_version != V4_GUARDRAIL_POLICY_VERSION
        or manifest.guardrail_policy_hash != V4_GUARDRAIL_POLICY_HASH
    ):
        raise C03HistoricalPhenologyError("C03_V4_GUARDRAIL_POLICY_BINDING_MISMATCH")
    if (
        manifest.evaluation_surface_identity != C03_EVALUATION_SURFACE_ID
        or manifest.forecast_horizons != C03_FORECAST_HORIZONS
        or manifest.complete_daily_rowset_authority is not False
        or manifest.missing_day_zero_fill is not False
    ):
        raise C03HistoricalPhenologyError("C03_SPARSE_SURFACE_BINDING_MISMATCH")
    if (
        manifest.source_id != C03_SOURCE_ID
        or manifest.materialized_dataset_identity != C03_MATERIALIZED_DATASET_IDENTITY
        or manifest.train_dataset_identity != C03_TRAIN_DATASET_IDENTITY
        or manifest.validation_dataset_identity != C03_VALIDATION_DATASET_IDENTITY
        or manifest.evaluation_target_row_count != 688
    ):
        raise C03HistoricalPhenologyError("C03_SOURCE_002_IDENTITY_MISMATCH")
    for name, value in (
        ("actual_label_set", manifest.actual_label_set_identity),
        ("exclusion_policy", manifest.exclusion_policy_identity),
        ("cutoff_policy", manifest.cutoff_policy_identity),
        ("forecast_horizon_set", manifest.forecast_horizon_set_identity),
        ("business_grain_set", manifest.business_grain_set_identity),
        ("common_comparable_set", manifest.common_comparable_set_identity),
    ):
        _require_sha(name, value)
    if manifest.exclusion_policy_identity != C03_EXCLUSION_POLICY_IDENTITY:
        raise C03HistoricalPhenologyError("C03_EXCLUSION_POLICY_IDENTITY_MISMATCH")
    if (
        manifest.random_seed_policy != C03_RANDOM_SEED_POLICY
        or manifest.random_seed != C03_RANDOM_SEED
    ):
        raise C03HistoricalPhenologyError("C03_RANDOM_SEED_POLICY_MISMATCH")
    if manifest.planned_run_count != C03_PLANNED_RUN_COUNT:
        raise C03HistoricalPhenologyError("C03_PLANNED_RUN_COUNT_MISMATCH")
    if manifest.adaptive_search_allowed or manifest.post_validation_parameter_substitution_allowed:
        raise C03HistoricalPhenologyError("C03_ADAPTIVE_SEARCH_FORBIDDEN")
    if _COMMIT_PATTERN.fullmatch(manifest.code_commit_binding) is None:
        raise C03HistoricalPhenologyError("C03_CODE_COMMIT_BINDING_INVALID")
    if tuple(run.candidate_run_ordinal for run in manifest.runs) != (1, 2, 3, 4):
        raise C03HistoricalPhenologyError("C03_RUN_ORDER_NOT_FROZEN")
    if manifest.manifest_hash != sha256_payload(manifest.payload()):
        raise C03HistoricalPhenologyError("C03_MANIFEST_HASH_REPLAY_FAILURE")
    for run, expected_value in zip(manifest.runs, C03_RUN_VALUES, strict=True):
        if run.parameter_value != expected_value:
            raise C03HistoricalPhenologyError("C03_RUN_VALUE_MISMATCH")
        if expected_value == C03_INCUMBENT_VALUE:
            raise C03HistoricalPhenologyError("C03_RUN_INCLUDES_INCUMBENT_VALUE")
        diff = verify_c03_historical_parameter_allowlist(
            incumbent_snapshot=manifest.incumbent_parameter_snapshot,
            candidate_snapshot=run.full_parameter_snapshot,
        )
        if (
            diff.native_float_present
            or diff.changed_paths != C03_ALLOWED_PARAMETER_PATHS
            or diff.unauthorized_parameter_diff_count != 0
            or run.unauthorized_parameter_diff_count != 0
        ):
            raise C03HistoricalPhenologyError("C03_UNAUTHORIZED_PARAMETER_PATH")
        stored_delta = _decimalize(run.authorized_parameter_delta)
        if stored_delta != {C03_ALLOWED_PARAMETER_PATH: expected_value}:
            raise C03HistoricalPhenologyError("C03_PARAMETER_DELTA_MISMATCH")
        if _decimalize(_path_value(run.full_parameter_snapshot, C03_ALLOWED_PARAMETER_PATH)) != (
            expected_value
        ):
            raise C03HistoricalPhenologyError("C03_RUN_VALUE_MISMATCH")
        if run.candidate_config_hash != _candidate_config_hash(run.full_parameter_snapshot):
            raise C03HistoricalPhenologyError("C03_CANDIDATE_CONFIG_HASH_MISMATCH")
        if run.incumbent_config_hash != C03_INCUMBENT_CONFIG_HASH:
            raise C03HistoricalPhenologyError("C03_INCUMBENT_CONFIG_HASH_MISMATCH")
        if run.random_seed != C03_RANDOM_SEED:
            raise C03HistoricalPhenologyError("C03_RANDOM_SEED_MISMATCH")
        expected_hash = _run_manifest_hash(
            manifest_version=manifest.version,
            ordinal=run.candidate_run_ordinal,
            value=expected_value,
            parameter_delta={C03_ALLOWED_PARAMETER_PATH: expected_value},
            full_snapshot=run.full_parameter_snapshot,
            incumbent_config_hash=manifest.incumbent_config_hash,
            code_commit_binding=manifest.code_commit_binding,
        )
        if run.parameter_manifest_hash != expected_hash:
            raise C03HistoricalPhenologyError("C03_RUN_MANIFEST_HASH_MISMATCH")


@dataclass(frozen=True, slots=True)
class C03DerivedConfig:
    """Immutable candidate snapshot projection; YAML is never modified."""

    candidate_run_ordinal: int
    parameter_value: Decimal
    candidate_config_hash: str
    snapshot: Mapping[str, object]


def build_c03_historical_derived_config(
    manifest: C03HistoricalParameterManifest, candidate_run_ordinal: int
) -> tuple[C03HistoricalRunDefinition, C03DerivedConfig]:
    validate_c03_historical_only_manifest(manifest)
    run = manifest.run(candidate_run_ordinal)
    return run, C03DerivedConfig(
        candidate_run_ordinal=run.candidate_run_ordinal,
        parameter_value=run.parameter_value,
        candidate_config_hash=run.candidate_config_hash,
        snapshot=copy.deepcopy(dict(run.full_parameter_snapshot)),
    )


def build_c03_historical_only_config(
    manifest: C03HistoricalParameterManifest, candidate_run_ordinal: int, config_path: Path
) -> tuple[C03HistoricalRunDefinition, MaturityCurveConfig]:
    """Return a typed in-memory config for future execution wiring tests."""

    run, derived = build_c03_historical_derived_config(manifest, candidate_run_ordinal)
    config = load_maturity_curve_config(config_path)
    _validate_incumbent_config(config_path, config)
    candidate_rules = replace(
        config.rules,
        offset=replace(
            config.rules.offset,
            maximum_abs_shift_days=run.parameter_value,
        ),
    )
    return run, MaturityCurveConfig(
        rules=candidate_rules,
        config_hash=derived.candidate_config_hash,
        snapshot=copy.deepcopy(dict(derived.snapshot)),
    )


@dataclass(frozen=True, slots=True)
class C03HistoricalShiftModel:
    """TRAIN-learned group peak-delta model with immutable bound projection."""

    artifact: ShiftModelArtifact
    group_shift_days: Mapping[GroupKey, Decimal]
    variety_shift_days: Mapping[str, Decimal]
    default_shift_days: Decimal

    def with_maximum_abs_shift_days(
        self, maximum_abs_shift_days: Decimal
    ) -> C03HistoricalShiftModel:
        if type(maximum_abs_shift_days) is not Decimal or not maximum_abs_shift_days.is_finite():
            raise C03HistoricalPhenologyError("C03_PARAMETER_VALUE_INVALID")
        if maximum_abs_shift_days <= 0:
            raise C03HistoricalPhenologyError("C03_PARAMETER_VALUE_INVALID")
        return replace(
            self,
            artifact=replace(
                self.artifact,
                bounds=(-maximum_abs_shift_days, maximum_abs_shift_days),
            ),
        )

    def predict_shift_days(
        self, *, group_key: GroupKey, variety: str, maximum_abs_shift_days: Decimal
    ) -> Decimal:
        bounded = self.with_maximum_abs_shift_days(maximum_abs_shift_days)
        raw = bounded.group_shift_days.get(
            group_key,
            bounded.variety_shift_days.get(variety, bounded.default_shift_days),
        )
        return min(max(raw, bounded.artifact.bounds[0]), bounded.artifact.bounds[1]).quantize(
            _DECIMAL_QUANTUM,
            rounding=ROUND_HALF_EVEN,
        )


@dataclass(frozen=True, slots=True)
class _C03TrainingModel:
    support_days: tuple[int, ...]
    group_anchors: Mapping[GroupKey, date]
    variety_anchors: Mapping[str, date]
    group_totals: Mapping[GroupKey, Decimal]
    variety_total_medians: Mapping[str, Decimal]
    group_curves: Mapping[GroupKey, tuple[Decimal, ...] | None]
    variety_curves: Mapping[str, tuple[Decimal, ...] | None]
    shift_model: C03HistoricalShiftModel


def _group_key(row: MaterializableRow) -> GroupKey:
    return (row.season, row.farm, row.subfarm, row.variety)


def _row_key(row: MaterializableRow) -> tuple[str, str, str, str, date]:
    return (*_group_key(row), row.harvest_business_date)


def _median(values: list[Decimal]) -> Decimal:
    if not values:
        raise C03HistoricalPhenologyError("C03_SHIFT_TRAINING_INSUFFICIENT")
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return _q(ordered[middle])
    return _q((ordered[middle - 1] + ordered[middle]) / Decimal("2"))


def _fit_curve(
    samples: tuple[tuple[int, Decimal], ...],
    *,
    config: MaturityCurveConfig,
    support_days: tuple[int, ...],
) -> tuple[Decimal, ...] | None:
    samples_by_day: dict[int, list[Decimal]] = defaultdict(list)
    for relative_day, quantity in samples:
        if type(quantity) is not Decimal or not quantity.is_finite() or quantity < 0:
            raise C03HistoricalPhenologyError("C03_TRAIN_QUANTITY_INVALID")
        samples_by_day[relative_day].append(quantity)
    total = sum((quantity for _, quantity in samples), Decimal("0"))
    if total <= 0 or len(samples_by_day) < max(
        config.rules.curve.spline_degree + 1, _MIN_CURVE_POINTS
    ):
        return None
    relative_days = tuple(sorted(samples_by_day))
    shares = tuple(_q(sum(samples_by_day[day], Decimal("0")) / total) for day in relative_days)
    weights = tuple(_q(Decimal(len(samples_by_day[day]))) for day in relative_days)
    try:
        # This is the same shared maturity curve primitive used by the other
        # historical scorer.  It is imported lazily so manifest/gate tooling
        # remains free of model execution side effects.
        from backend.app.maturity.model import fit_shared_curve

        return fit_shared_curve(
            relative_days=relative_days,
            shares=shares,
            sample_weights=weights,
            support_days=support_days,
            spline_degree=config.rules.curve.spline_degree,
            spline_knot_count=config.rules.curve.spline_knot_count,
            ridge_alpha=config.rules.curve.ridge_alpha,
        )
    except (ValueError, RuntimeError) as exc:
        raise C03HistoricalPhenologyError("C03_TRAIN_CURVE_FIT_FAILED") from exc


def _curve_peak(curve: tuple[Decimal, ...], support_days: tuple[int, ...]) -> Decimal:
    index = max(range(len(curve)), key=lambda item: (curve[item], -abs(support_days[item])))
    return _q(Decimal(support_days[index]))


def _build_shift_model(
    *,
    group_curves: Mapping[GroupKey, tuple[Decimal, ...] | None],
    variety_curves: Mapping[str, tuple[Decimal, ...] | None],
    support_days: tuple[int, ...],
    config: MaturityCurveConfig,
) -> C03HistoricalShiftModel:
    group_shifts: dict[GroupKey, Decimal] = {}
    variety_values: dict[str, list[Decimal]] = defaultdict(list)
    for group_key in sorted(group_curves):
        local = group_curves[group_key]
        parent = variety_curves.get(group_key[3])
        if local is None or parent is None:
            continue
        shift = _q(_curve_peak(local, support_days) - _curve_peak(parent, support_days))
        group_shifts[group_key] = shift
        variety_values[group_key[3]].append(shift)
    if len(group_shifts) < config.rules.offset.minimum_training_samples:
        raise C03HistoricalPhenologyError("C03_SHIFT_TRAINING_INSUFFICIENT")
    variety_shifts = {variety: _median(values) for variety, values in variety_values.items()}
    default_shift = _median(list(group_shifts.values()))
    artifact = ShiftModelArtifact(
        enabled=True,
        intercept_days=default_shift,
        coefficients={
            "group=" + "|".join(group): _q(shift - default_shift)
            for group, shift in sorted(group_shifts.items())
        },
        category_vocabulary={
            "group": tuple("|".join(group) for group in sorted(group_shifts)),
        },
        reference_categories={"group": "unknown"},
        unknown_categories={"group": "unknown"},
        unknown_handling_rules={"group": "map_unseen_to_variety_or_intercept"},
        feature_order=tuple("group=" + "|".join(group) for group in sorted(group_shifts)),
        scaler_center={},
        scaler_scale={},
        feature_units={"group": "canonical_business_grain"},
        missing_value_rules={"group": "variety_parent_then_intercept"},
        bounds=(
            -config.rules.offset.maximum_abs_shift_days,
            config.rules.offset.maximum_abs_shift_days,
        ),
        warnings=(),
    )
    return C03HistoricalShiftModel(
        artifact=artifact,
        group_shift_days=group_shifts,
        variety_shift_days=variety_shifts,
        default_shift_days=default_shift,
    )


def _build_training_model(
    train_rows: tuple[MaterializableRow, ...],
    projection_rows: tuple[MaterializableRow, ...],
    config: MaturityCurveConfig,
) -> _C03TrainingModel:
    if not train_rows:
        raise C03HistoricalPhenologyError("C03_TRAIN_ROWS_EMPTY")
    by_group: dict[GroupKey, list[MaterializableRow]] = defaultdict(list)
    by_variety: dict[str, list[MaterializableRow]] = defaultdict(list)
    for row in train_rows:
        if type(row.actual_harvest_quantity_kg) is not Decimal:
            raise C03HistoricalPhenologyError("C03_TRAIN_QUANTITY_INVALID")
        by_group[_group_key(row)].append(row)
        by_variety[row.variety].append(row)
    group_anchors = {
        key: min(row.harvest_business_date for row in rows) for key, rows in by_group.items()
    }
    variety_anchors = {
        variety: min(row.harvest_business_date for row in rows)
        for variety, rows in by_variety.items()
    }
    group_totals = {
        key: sum((row.actual_harvest_quantity_kg for row in rows), Decimal("0"))
        for key, rows in by_group.items()
    }
    variety_total_medians = {
        variety: _median([group_totals[key] for key in sorted(group_totals) if key[3] == variety])
        for variety in sorted(by_variety)
    }
    relative_max = config.rules.curve.support_max_day
    for row in projection_rows:
        anchor = group_anchors.get(_group_key(row)) or variety_anchors.get(row.variety)
        if anchor is not None:
            relative_max = max(relative_max, (row.harvest_business_date - anchor).days)
    support_days = tuple(range(config.rules.curve.support_min_day, relative_max + 1))
    group_curves: dict[GroupKey, tuple[Decimal, ...] | None] = {}
    for key, rows in sorted(by_group.items()):
        samples = tuple(
            (
                (row.harvest_business_date - group_anchors[key]).days,
                row.actual_harvest_quantity_kg,
            )
            for row in sorted(rows, key=_row_key)
        )
        group_curves[key] = _fit_curve(
            samples,
            config=config,
            support_days=support_days,
        )
    variety_curves: dict[str, tuple[Decimal, ...] | None] = {}
    for variety in sorted(by_variety):
        normalized: list[tuple[int, Decimal]] = []
        for group_key in sorted(by_group):
            if group_key[3] != variety or group_totals[group_key] <= 0:
                continue
            anchor = group_anchors[group_key]
            normalized.extend(
                (
                    (row.harvest_business_date - anchor).days,
                    row.actual_harvest_quantity_kg / group_totals[group_key],
                )
                for row in sorted(by_group[group_key], key=_row_key)
            )
        variety_curves[variety] = _fit_curve(
            tuple(normalized), config=config, support_days=support_days
        )
    shift_model = _build_shift_model(
        group_curves=group_curves,
        variety_curves=variety_curves,
        support_days=support_days,
        config=config,
    )
    return _C03TrainingModel(
        support_days=support_days,
        group_anchors=group_anchors,
        variety_anchors=variety_anchors,
        group_totals=group_totals,
        variety_total_medians=variety_total_medians,
        group_curves=group_curves,
        variety_curves=variety_curves,
        shift_model=shift_model,
    )


def _shift_curve(
    *, density: tuple[Decimal, ...], support_days: tuple[int, ...], shift_days: Decimal
) -> tuple[Decimal, ...]:
    """Apply the production maturity shift/interpolation/normalization semantics."""

    x = np.asarray(support_days, dtype=float)
    y = np.asarray([float(item) for item in density], dtype=float)
    shifted = np.interp(x - float(shift_days), x, y, left=0.0, right=0.0)
    shifted = np.clip(shifted, 0.0, None)
    total = float(shifted.sum())
    if total <= 0:
        return tuple(Decimal("0") for _ in support_days)
    normalized = shifted / total
    result = [Decimal(f"{value:.6f}") for value in normalized.tolist()]
    difference = Decimal("1.000000") - sum(result, Decimal("0"))
    result[-1] += difference
    return tuple(result)


def _validate_projection_rows(
    target_rows: tuple[MaterializableRow, ...], forecast_cutoff_at: date
) -> None:
    if not target_rows:
        raise C03HistoricalPhenologyError("C03_TARGET_ROWS_EMPTY")
    seen: set[tuple[GroupKey, int]] = set()
    for row in target_rows:
        horizon = (row.harvest_business_date - forecast_cutoff_at).days
        try:
            from backend.app.s4_local_engineering import validate_v2_forecast_horizon

            validate_v2_forecast_horizon(horizon)
        except ValueError as exc:
            raise C03HistoricalPhenologyError("C03_HORIZON_NOT_IN_FROZEN_SET") from exc
        key = (_group_key(row), horizon)
        if key in seen:
            raise C03HistoricalPhenologyError("C03_DUPLICATE_TARGET_GROUP_HORIZON")
        seen.add(key)


@dataclass(frozen=True, slots=True)
class C03Prediction:
    """Prediction payload intentionally excludes target actual quantities."""

    season: str
    farm: str
    subfarm: str
    variety: str
    harvest_business_date: date
    forecast_cutoff_at: date
    horizon_days: int
    maximum_abs_shift_days: Decimal
    learned_shift_days: Decimal
    applied_shift_days: Decimal
    base_prediction_total_kg: Decimal
    curve_share: Decimal
    candidate_p50_kg: Decimal
    candidate_p80_kg: Decimal
    candidate_p90_kg: Decimal
    model_identity: str = INCUMBENT_MODEL_ID

    def payload(self) -> dict[str, object]:
        return {
            "season": self.season,
            "farm": self.farm,
            "subfarm": self.subfarm,
            "variety": self.variety,
            "harvest_business_date": self.harvest_business_date,
            "forecast_cutoff_at": self.forecast_cutoff_at,
            "horizon_days": self.horizon_days,
            "maximum_abs_shift_days": self.maximum_abs_shift_days,
            "learned_shift_days": self.learned_shift_days,
            "applied_shift_days": self.applied_shift_days,
            "base_prediction_total_kg": self.base_prediction_total_kg,
            "curve_share": self.curve_share,
            "candidate_p50_kg": self.candidate_p50_kg,
            "candidate_p80_kg": self.candidate_p80_kg,
            "candidate_p90_kg": self.candidate_p90_kg,
            "model_identity": self.model_identity,
        }


@dataclass(frozen=True, slots=True)
class C03ParameterEffectProof:
    baseline_bound: Decimal
    alternate_bound: Decimal
    baseline_prediction_identity: str
    alternate_prediction_identity: str
    changed_prediction_count: int


@dataclass(frozen=True, slots=True)
class C03HistoricalPhenologyScorer:
    """Non-canonical prototype retained for isolated audit fixtures only.

    It must never be constructed from SOURCE-002 authority or used as the S4
    C03 execution scorer.  The public class remains temporarily available so
    old fixture-level experiments remain inspectable, but the authority-bound
    constructor below fails closed.
    """

    train_rows: tuple[MaterializableRow, ...]
    forecast_cutoff_at: date
    train_dataset_identity: str
    config: MaturityCurveConfig
    _model: _C03TrainingModel

    @classmethod
    def from_v2_authority(
        cls,
        authority: V2HistoricalEvaluationAuthority,
        config: MaturityCurveConfig,
    ) -> C03HistoricalPhenologyScorer:
        del authority, config
        raise C03HistoricalPhenologyError(C03_CANONICAL_SHIFT_MODEL_BLOCKER)

    def predict_rows(
        self, target_rows: tuple[MaterializableRow, ...], maximum_abs_shift_days: Decimal
    ) -> tuple[C03Prediction, ...]:
        """Project target identities without reading their actual quantities."""

        if (
            type(maximum_abs_shift_days) is not Decimal
            or not maximum_abs_shift_days.is_finite()
            or maximum_abs_shift_days <= 0
        ):
            raise C03HistoricalPhenologyError("C03_PARAMETER_VALUE_INVALID")
        _validate_projection_rows(target_rows, self.forecast_cutoff_at)
        model = self._model
        p80_multiplier = Decimal("1") + self.config.rules.intervals.p80_quantile / Decimal("2")
        p90_multiplier = Decimal("1") + self.config.rules.intervals.p90_quantile
        predictions: list[C03Prediction] = []
        for row in sorted(target_rows, key=_row_key):
            group = _group_key(row)
            anchor = model.group_anchors.get(group) or model.variety_anchors.get(row.variety)
            curve = model.group_curves.get(group) or model.variety_curves.get(row.variety)
            base_total = model.group_totals.get(group) or model.variety_total_medians.get(
                row.variety
            )
            if anchor is None or curve is None or base_total is None:
                raise C03HistoricalPhenologyError("C03_TRAIN_SUPPORT_UNAVAILABLE")
            relative_day = (row.harvest_business_date - anchor).days
            if relative_day < model.support_days[0] or relative_day > model.support_days[-1]:
                raise C03HistoricalPhenologyError("C03_TRAIN_SUPPORT_UNAVAILABLE")
            learned_shift = model.shift_model.group_shift_days.get(
                group,
                model.shift_model.variety_shift_days.get(
                    row.variety, model.shift_model.default_shift_days
                ),
            )
            applied_shift = model.shift_model.predict_shift_days(
                group_key=group,
                variety=row.variety,
                maximum_abs_shift_days=maximum_abs_shift_days,
            )
            shifted_curve = _shift_curve(
                density=curve,
                support_days=model.support_days,
                shift_days=applied_shift,
            )
            curve_share = _q(shifted_curve[relative_day - model.support_days[0]])
            base_total = _q(base_total)
            p50 = _q(base_total * curve_share)
            p80 = max(_q(p50 * p80_multiplier), p50)
            p90 = max(_q(p50 * p90_multiplier), p80, p50)
            predictions.append(
                C03Prediction(
                    season=row.season,
                    farm=row.farm,
                    subfarm=row.subfarm,
                    variety=row.variety,
                    harvest_business_date=row.harvest_business_date,
                    forecast_cutoff_at=self.forecast_cutoff_at,
                    horizon_days=(row.harvest_business_date - self.forecast_cutoff_at).days,
                    maximum_abs_shift_days=maximum_abs_shift_days,
                    learned_shift_days=_q(learned_shift),
                    applied_shift_days=applied_shift,
                    base_prediction_total_kg=base_total,
                    curve_share=curve_share,
                    candidate_p50_kg=p50,
                    candidate_p80_kg=p80,
                    candidate_p90_kg=p90,
                )
            )
        return tuple(predictions)

    @staticmethod
    def prediction_identity(predictions: tuple[C03Prediction, ...]) -> str:
        return sha256_payload([prediction.payload() for prediction in predictions])

    def prove_parameter_effect(
        self,
        target_rows: tuple[MaterializableRow, ...],
        *,
        baseline_bound: Decimal = C03_INCUMBENT_VALUE,
        alternate_bound: Decimal = Decimal("14"),
    ) -> C03ParameterEffectProof:
        baseline = self.predict_rows(target_rows, baseline_bound)
        alternate = self.predict_rows(target_rows, alternate_bound)
        changed = sum(
            left.candidate_p50_kg != right.candidate_p50_kg
            or left.applied_shift_days != right.applied_shift_days
            for left, right in zip(baseline, alternate, strict=True)
        )
        return C03ParameterEffectProof(
            baseline_bound=baseline_bound,
            alternate_bound=alternate_bound,
            baseline_prediction_identity=self.prediction_identity(baseline),
            alternate_prediction_identity=self.prediction_identity(alternate),
            changed_prediction_count=changed,
        )

    def prove_frozen_parameter_effects(
        self, target_rows: tuple[MaterializableRow, ...]
    ) -> dict[Decimal, bool]:
        """Return effect checks for the four frozen values without scoring."""

        incumbent = self.predict_rows(target_rows, C03_INCUMBENT_VALUE)
        incumbent_identity = self.prediction_identity(incumbent)
        return {
            value: self.prediction_identity(self.predict_rows(target_rows, value))
            != incumbent_identity
            for value in C03_RUN_VALUES
        }


def build_c03_historical_phenology_scorer(
    *, authority: V2HistoricalEvaluationAuthority, config_path: Path
) -> C03HistoricalPhenologyScorer:
    """Reject the non-canonical prototype at the authority boundary."""

    del authority, config_path
    raise C03HistoricalPhenologyError(C03_CANONICAL_SHIFT_MODEL_BLOCKER)


def _manifest_pairing_payload(manifest: C03HistoricalParameterManifest) -> dict[str, object]:
    return {
        "train_dataset_identity": manifest.train_dataset_identity,
        "validation_dataset_identity": manifest.validation_dataset_identity,
        "actual_label_set_identity": manifest.actual_label_set_identity,
        "exclusion_policy_identity": manifest.exclusion_policy_identity,
        "cutoff_policy_identity": manifest.cutoff_policy_identity,
        "forecast_horizon_set_identity": manifest.forecast_horizon_set_identity,
        "metric_contract_identity": METRIC_CONTRACT_IDENTITY,
        "business_grain_set_identity": manifest.business_grain_set_identity,
        "common_comparable_set_identity": manifest.common_comparable_set_identity,
    }


def build_c03_v4_gate_request(
    *,
    manifest: C03HistoricalParameterManifest,
    candidate_run_ordinal: int,
    code_commit_sha: str,
    evaluation_id: str,
    candidate_actual_run_count: int = 0,
    global_actual_evaluation_count: int = 8,
) -> CandidateExecutionGateRequest:
    """Build a pure V4 request; this function never calls durable execution."""

    validate_c03_historical_only_manifest(manifest)
    if _COMMIT_PATTERN.fullmatch(code_commit_sha) is None or not evaluation_id:
        raise C03HistoricalPhenologyError("C03_EXECUTION_IDENTITY_MISSING")
    run = manifest.run(candidate_run_ordinal)
    pairing = _manifest_pairing_payload(manifest)
    policy_payload = {
        "candidate_id": C03_CANDIDATE_ID,
        "manifest_version": manifest.version,
        "manifest_hash": manifest.manifest_hash,
        "parameter_manifest_hash": run.parameter_manifest_hash,
        "candidate_config_hash": run.candidate_config_hash,
        "owner_decision_id": C03_OWNER_DECISION_ID,
        "semantic_authority": C03_SEMANTIC,
        "allowed_parameter_paths": list(C03_ALLOWED_PARAMETER_PATHS),
        "historical_data_only": True,
        "source_id": C03_SOURCE_ID,
        "test_access_requested": False,
        "test_sealed": True,
        "evaluation_surface_identity": C03_EVALUATION_SURFACE_ID,
        "forecast_horizons": list(C03_FORECAST_HORIZONS),
        "pairing_identities": pairing,
    }
    canonical_json_dumps(policy_payload)
    return CandidateExecutionGateRequest(
        experiment_plan_version=EXPERIMENT_PLAN_V2_VERSION,
        experiment_plan_hash=EXPERIMENT_PLAN_V2_HASH,
        guardrail_policy_version=V4_GUARDRAIL_POLICY_VERSION,
        guardrail_policy_hash=V4_GUARDRAIL_POLICY_HASH,
        candidate_id=C03_CANDIDATE_ID,
        candidate_run_ordinal=candidate_run_ordinal,
        candidate_planned_run_count=C03_PLANNED_RUN_COUNT,
        candidate_actual_run_count=candidate_actual_run_count,
        global_actual_evaluation_count=global_actual_evaluation_count,
        train_dataset_identity=manifest.train_dataset_identity,
        validation_dataset_identity=manifest.validation_dataset_identity,
        metric_contract_version=METRIC_CONTRACT_VERSION,
        test_access_requested=False,
        test_sealed=True,
        parameter_manifest_hash=run.parameter_manifest_hash,
        code_commit_sha=code_commit_sha,
        random_seed=run.random_seed,
        evaluation_id=evaluation_id,
        candidate_execution_manifest_frozen=True,
        candidate_registry=FROZEN_CANDIDATE_REGISTRY,
        policy_payload=policy_payload,
        actual_label_set_identity=manifest.actual_label_set_identity,
        exclusion_policy_identity=manifest.exclusion_policy_identity,
        cutoff_policy_identity=manifest.cutoff_policy_identity,
        forecast_horizon_set_identity=manifest.forecast_horizon_set_identity,
        metric_contract_identity=METRIC_CONTRACT_IDENTITY,
        business_grain_set_identity=manifest.business_grain_set_identity,
        common_comparable_set_identity=manifest.common_comparable_set_identity,
        invocation_type="NORMAL_RUN",
        evaluation_surface_identity=C03_EVALUATION_SURFACE_ID,
        forecast_horizons=C03_FORECAST_HORIZONS,
        complete_daily_rowset_authority=C03_COMPLETE_DAILY_ROWSET_AUTHORITY,
        missing_day_zero_fill=C03_MISSING_DAY_ZERO_FILL,
    )


def check_c03_v4_gate(request: CandidateExecutionGateRequest) -> CandidateExecutionGateResult:
    """Expose V4 identity checks, then fail closed without a canonical scorer."""

    result = check_candidate_execution_gate(request)
    if not result.allowed:
        return result
    return CandidateExecutionGateResult(
        status="BLOCKED",
        allowed=False,
        reason_codes=(C03_CANONICAL_SHIFT_MODEL_BLOCKER,),
    )


# Candidate-control-plane-style aliases make the versioned surface discoverable.
build_candidate_03_historical_only_manifest = build_c03_historical_only_manifest
validate_candidate_03_historical_only_manifest = validate_c03_historical_only_manifest
build_candidate_03_v4_gate_request = build_c03_v4_gate_request

__all__ = [
    "C03_ALLOWED_PARAMETER_PATH",
    "C03_ALLOWED_PARAMETER_PATHS",
    "C03_AUTHORITY_CLASS",
    "C03_CANDIDATE_FAMILY",
    "C03_CANDIDATE_ID",
    "C03_CANONICAL_FORWARD_LOOKING_AUTHORITY_DOMAINS",
    "C03_CANONICAL_PARAMETER_CHANGE_STATUS",
    "C03_CANONICAL_FORECAST_PATH",
    "C03_CANONICAL_PRODUCTION_SHIFT_PATHS",
    "C03_CANONICAL_PRODUCTION_TRAINING_PATH",
    "C03_CANONICAL_SHIFT_BUILDER_PATH",
    "C03_CANONICAL_SHIFT_MODEL_BLOCKER",
    "C03_CANONICAL_SHIFT_PREDICTOR_PATH",
    "C03_CANONICAL_SHIFT_TARGET_DEFINITION",
    "C03_CANONICAL_TRAINING_FEATURES",
    "C03_CANONICAL_TRAINING_REQUIRED_INPUTS",
    "C03_COMPLETE_DAILY_ROWSET_AUTHORITY",
    "C03_EVALUATION_SURFACE_ID",
    "C03_EXCLUDED_PARAMETER_PATH",
    "C03_EXCLUDED_PARAMETER_PATHS",
    "C03_FORECAST_HORIZONS",
    "C03_HISTORICAL_SCORER_PATH",
    "C03_HISTORICAL_ONLY_SCORER_PATH",
    "C03_HISTORICAL_ONLY_SCORING_PATH_EXISTS",
    "C03_HYPOTHESIS",
    "C03_INCUMBENT_CONFIG_FILE_SHA256",
    "C03_INCUMBENT_CONFIG_HASH",
    "C03_INCUMBENT_CONFIG_PATH",
    "C03_INCUMBENT_VALUE",
    "C03_MATERIALIZED_DATASET_IDENTITY",
    "C03_PARAMETER_CHANGE_CAN_CHANGE_PREDICTION",
    "C03_PARAMETER_MANIFEST_VERSION",
    "C03_PARAMETER_REACHES_PREDICTION_MATH",
    "C03_PARENT_MODEL_ID",
    "C03_PLANNED_RUN_COUNT",
    "C03_RANDOM_SEED",
    "C03_RANDOM_SEED_POLICY",
    "C03_RUN_VALUES",
    "C03_SEMANTIC",
    "C03_SOURCE_ID",
    "C03_SOURCE002_MATERIALIZABLE_FIELDS",
    "C03_NON_CANONICAL_PROTOTYPE_IS_EXECUTION_AUTHORITY",
    "C03_NON_CANONICAL_PROTOTYPE_PATH",
    "C03_NON_CANONICAL_PROTOTYPE_STATUS",
    "C03CanonicalTrainingInputAudit",
    "C03HistoricalParameterManifest",
    "C03HistoricalPhenologyError",
    "C03HistoricalPhenologyScorer",
    "C03HistoricalRunDefinition",
    "C03HistoricalShiftModel",
    "C03ParameterDiff",
    "C03Prediction",
    "C03ParameterEffectProof",
    "build_c03_historical_only_config",
    "build_c03_historical_only_manifest",
    "build_c03_historical_phenology_scorer",
    "build_c03_historical_derived_config",
    "build_c03_v4_gate_request",
    "audit_c03_canonical_training_inputs",
    "build_candidate_03_historical_only_manifest",
    "build_candidate_03_v4_gate_request",
    "check_c03_v4_gate",
    "validate_c03_historical_only_manifest",
    "validate_candidate_03_historical_only_manifest",
    "verify_c03_historical_parameter_allowlist",
]
