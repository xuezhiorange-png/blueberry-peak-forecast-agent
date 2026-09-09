"""V0.3 S4 V2 historical-only execution readiness adapter.

The adapter binds the frozen V2 plan to the accepted SOURCE-002
TRAIN/VALIDATION surface and audits candidate execution paths without starting
an evaluation.  It deliberately has no database dependency, scorer callback,
TEST reader, or budget mutation path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from backend.app.s4_candidate_execution_authority import CANDIDATE_01_RERUN_FORBIDDEN
from backend.app.s4_experiment import (
    EXPERIMENT_PLAN_V2_HASH,
    EXPERIMENT_PLAN_V2_VERSION,
    V2_CANDIDATE_01_RERUN_FORBIDDEN,
    V2_CANDIDATE_06_EXECUTION_ELIGIBLE,
    V2_CANDIDATE_08_EXECUTION_ELIGIBLE,
    V2_CANONICAL_STARTED_COUNT,
    V2_EFFECTIVE_CONSUMED,
    V2_FORECAST_HORIZONS,
    V2_GUARDRAIL_POLICY_HASH,
    V2_GUARDRAIL_POLICY_VERSION,
    V2_HISTORICAL_DATA_ONLY,
    V2_LEGACY_RECONCILED_VALIDATION_DEBIT,
    V2_PRODUCTION_PLAN_REQUIRED,
    V2_PROSPECTIVE_CAPTURE_REQUIRED,
    V2_REMAINING_VALIDATION_EVALUATIONS,
    V2_TASK8_TASK9_REQUIRED,
    V2_TEST_REMAINS_SEALED,
    V2_WALL_CLOCK_WAIT_REQUIRED,
    V2_WEATHER_REQUIRED,
    canonical_guardrail_policy_v2,
)
from backend.app.s4_local_engineering import (
    V2HistoricalEvaluationAuthority,
    build_v2_historical_evaluation_authority,
    load_frozen_engineering_dataset,
    v2_metric_availability,
    v2_training_rows,
)

V2_CANDIDATE_AUDIT_ORDER: Final[tuple[str, ...]] = (
    "01_parameter_calibration",
    "02_quantile_calibration",
    "03_phenology_offset",
    "04_yield_parameter",
    "05_marketable_rate",
    "07_harvest_efficiency",
)

V2_CANDIDATE_06_ID: Final[str] = "06_weather_response"
V2_CANDIDATE_08_ID: Final[str] = "08_residual_feature"
V2_CANDIDATE_03_ID: Final[str] = "03_phenology_offset"
V2_CANDIDATE_02_ID: Final[str] = "02_quantile_calibration"
V2_CANDIDATE_01_ID: Final[str] = "01_parameter_calibration"
V2_CANDIDATE_04_ID: Final[str] = "04_yield_parameter"
V2_CANDIDATE_05_ID: Final[str] = "05_marketable_rate"
V2_CANDIDATE_07_ID: Final[str] = "07_harvest_efficiency"

V2_NO_EXECUTION_PATH: Final[str] = "NONE_BOUND_TO_V2_HISTORICAL_ONLY_EXECUTION"
V2_C01_LOCAL_SCORER_PATH: Final[str] = "backend.app.s4_local_engineering.run_local_replay"
V2_C02_METRIC_ONLY_PATH: Final[str] = (
    "backend.app.forecast_quality.quantile_coverage.compute_upper_quantile_coverage"
)
V2_C03_LEGACY_PATH: Final[str] = "backend.app.maturity.service.forecast_natural_maturity"
V2_C03_LOCAL_PATH: Final[str] = V2_NO_EXECUTION_PATH

CompatibilityStatus = Literal["COMPATIBLE", "INCOMPATIBLE"]


@dataclass(frozen=True, slots=True)
class V2CandidateCompatibility:
    """Code-level candidate compatibility facts, not an execution grant."""

    candidate_id: str
    parameter_or_feature_path: tuple[str, ...]
    actual_execution_function: tuple[str, ...]
    actual_data_sources_read: tuple[str, ...]
    uses_source_002_train: bool
    uses_source_002_validation: bool
    uses_weather: bool
    uses_production_plan: bool
    uses_task8: bool
    uses_task9: bool
    uses_other_forward_looking_authority: bool
    parameter_reaches_prediction_math: bool
    parameter_change_can_change_prediction: bool
    v2_historical_only_scoring_path_exists: bool
    historical_only_input_compatible: bool
    historical_only_execution_compatible: bool
    current_v0_3_execution_eligible: bool
    status: CompatibilityStatus
    reason_code: str

    def payload(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "parameter_or_feature_path": self.parameter_or_feature_path,
            "actual_execution_function": self.actual_execution_function,
            "actual_data_sources_read": self.actual_data_sources_read,
            "uses_SOURCE_002_TRAIN": self.uses_source_002_train,
            "uses_SOURCE_002_VALIDATION": self.uses_source_002_validation,
            "uses_weather": self.uses_weather,
            "uses_production_plan": self.uses_production_plan,
            "uses_Task8": self.uses_task8,
            "uses_Task9": self.uses_task9,
            "uses_other_forward_looking_authority": self.uses_other_forward_looking_authority,
            "parameter_reaches_prediction_math": self.parameter_reaches_prediction_math,
            "parameter_change_can_change_prediction": self.parameter_change_can_change_prediction,
            "v2_historical_only_scoring_path_exists": self.v2_historical_only_scoring_path_exists,
            "historical_only_input_compatible": self.historical_only_input_compatible,
            "historical_only_execution_compatible": self.historical_only_execution_compatible,
            "current_v0_3_execution_eligible": self.current_v0_3_execution_eligible,
            "status": self.status,
            "reason_code": self.reason_code,
        }


def _audit(
    *,
    candidate_id: str,
    parameter_or_feature_path: tuple[str, ...],
    actual_execution_function: tuple[str, ...],
    actual_data_sources_read: tuple[str, ...],
    uses_source_002_train: bool,
    uses_source_002_validation: bool,
    uses_weather: bool = False,
    uses_production_plan: bool = False,
    uses_task8: bool = False,
    uses_task9: bool = False,
    uses_other_forward_looking_authority: bool = False,
    parameter_reaches_prediction_math: bool,
    parameter_change_can_change_prediction: bool,
    v2_historical_only_scoring_path_exists: bool,
    historical_only_input_compatible: bool,
    current_v0_3_execution_eligible: bool = False,
    reason_code: str,
) -> V2CandidateCompatibility:
    historical_only_execution_compatible = (
        historical_only_input_compatible
        and parameter_reaches_prediction_math
        and parameter_change_can_change_prediction
        and v2_historical_only_scoring_path_exists
        and not uses_weather
        and not uses_production_plan
        and not uses_task8
        and not uses_task9
        and not uses_other_forward_looking_authority
    )
    return V2CandidateCompatibility(
        candidate_id=candidate_id,
        parameter_or_feature_path=parameter_or_feature_path,
        actual_execution_function=actual_execution_function,
        actual_data_sources_read=actual_data_sources_read,
        uses_source_002_train=uses_source_002_train,
        uses_source_002_validation=uses_source_002_validation,
        uses_weather=uses_weather,
        uses_production_plan=uses_production_plan,
        uses_task8=uses_task8,
        uses_task9=uses_task9,
        uses_other_forward_looking_authority=uses_other_forward_looking_authority,
        parameter_reaches_prediction_math=parameter_reaches_prediction_math,
        parameter_change_can_change_prediction=parameter_change_can_change_prediction,
        v2_historical_only_scoring_path_exists=v2_historical_only_scoring_path_exists,
        historical_only_input_compatible=historical_only_input_compatible,
        historical_only_execution_compatible=historical_only_execution_compatible,
        current_v0_3_execution_eligible=(
            current_v0_3_execution_eligible and historical_only_execution_compatible
        ),
        status=("COMPATIBLE" if historical_only_execution_compatible else "INCOMPATIBLE"),
        reason_code=reason_code,
    )


def build_v2_candidate_compatibility_audit() -> tuple[V2CandidateCompatibility, ...]:
    """Return the fixed six-candidate audit in declared candidate order."""

    return (
        _audit(
            candidate_id=V2_CANDIDATE_01_ID,
            parameter_or_feature_path=(
                "curve.spline_knot_count",
                "curve.ridge_alpha",
            ),
            actual_execution_function=(V2_C01_LOCAL_SCORER_PATH,),
            actual_data_sources_read=(
                "SOURCE_002_TRAIN",
                "SOURCE_002_VALIDATION",
                "configs/maturity_curve.yaml",
            ),
            uses_source_002_train=True,
            uses_source_002_validation=True,
            parameter_reaches_prediction_math=True,
            parameter_change_can_change_prediction=True,
            v2_historical_only_scoring_path_exists=False,
            historical_only_input_compatible=True,
            reason_code=CANDIDATE_01_RERUN_FORBIDDEN,
        ),
        _audit(
            candidate_id=V2_CANDIDATE_02_ID,
            parameter_or_feature_path=(
                "intervals.p80_quantile",
                "intervals.p90_quantile",
            ),
            actual_execution_function=(V2_C02_METRIC_ONLY_PATH,),
            actual_data_sources_read=(
                "S3_BINDING_FORECAST_ROWS",
                "S3_BINDING_ACTUAL_ROWS",
                "S3_TRAIN_VALIDATION_PAIRING_AUTHORITY",
            ),
            uses_source_002_train=False,
            uses_source_002_validation=False,
            parameter_reaches_prediction_math=False,
            parameter_change_can_change_prediction=False,
            v2_historical_only_scoring_path_exists=False,
            historical_only_input_compatible=False,
            reason_code="NO_V2_BOUND_PREDICTION_QUANTILE_PATH",
        ),
        _audit(
            candidate_id=V2_CANDIDATE_03_ID,
            parameter_or_feature_path=("offset.maximum_abs_shift_days",),
            actual_execution_function=(
                "backend.app.s4_candidate_03_execution.build_candidate_03_derived_config",
                V2_C03_LEGACY_PATH,
                V2_C03_LOCAL_PATH,
            ),
            actual_data_sources_read=(
                "configs/maturity_curve.yaml",
                "production_plan",
                "weather_observations",
                "Task8/Task9_runtime_authority",
            ),
            uses_source_002_train=False,
            uses_source_002_validation=False,
            uses_weather=True,
            uses_production_plan=True,
            uses_task8=True,
            uses_task9=True,
            parameter_reaches_prediction_math=True,
            parameter_change_can_change_prediction=True,
            v2_historical_only_scoring_path_exists=False,
            historical_only_input_compatible=False,
            reason_code="C03_NO_SOURCE_002_ONLY_SCORING_PATH",
        ),
        _audit(
            candidate_id=V2_CANDIDATE_04_ID,
            parameter_or_feature_path=("yield_parameter",),
            actual_execution_function=(),
            actual_data_sources_read=("NO_BOUND_CANDIDATE_SCORER",),
            uses_source_002_train=False,
            uses_source_002_validation=False,
            parameter_reaches_prediction_math=False,
            parameter_change_can_change_prediction=False,
            v2_historical_only_scoring_path_exists=False,
            historical_only_input_compatible=True,
            reason_code="NO_BOUND_CANDIDATE_04_SCORING_PATH",
        ),
        _audit(
            candidate_id=V2_CANDIDATE_05_ID,
            parameter_or_feature_path=("marketable_rate",),
            actual_execution_function=(),
            actual_data_sources_read=("NO_BOUND_CANDIDATE_SCORER",),
            uses_source_002_train=False,
            uses_source_002_validation=False,
            parameter_reaches_prediction_math=False,
            parameter_change_can_change_prediction=False,
            v2_historical_only_scoring_path_exists=False,
            historical_only_input_compatible=True,
            reason_code="NO_BOUND_CANDIDATE_05_SCORING_PATH",
        ),
        _audit(
            candidate_id=V2_CANDIDATE_07_ID,
            parameter_or_feature_path=("harvest_efficiency",),
            actual_execution_function=(),
            actual_data_sources_read=("NO_BOUND_CANDIDATE_SCORER",),
            uses_source_002_train=False,
            uses_source_002_validation=False,
            parameter_reaches_prediction_math=False,
            parameter_change_can_change_prediction=False,
            v2_historical_only_scoring_path_exists=False,
            historical_only_input_compatible=True,
            reason_code="NO_BOUND_CANDIDATE_07_SCORING_PATH",
        ),
    )


@dataclass(frozen=True, slots=True)
class V2HistoricalOnlyReadiness:
    """Pure readiness state; it cannot create a STARTED event."""

    experiment_plan_version: str
    experiment_plan_hash: str
    guardrail_policy_version: str
    guardrail_policy_hash: str
    historical_data_only: bool
    weather_required: bool
    production_plan_required: bool
    task8_task9_required: bool
    prospective_capture_required: bool
    wall_clock_wait_required: bool
    test_remains_sealed: bool
    forecast_horizons: tuple[int, ...]
    candidate_06_execution_eligible: bool
    candidate_08_execution_eligible: bool
    candidate_01_rerun_forbidden: bool
    legacy_reconciled_validation_debit: int
    canonical_started_count: int
    effective_consumed: int
    remaining: int
    candidate_audit: tuple[V2CandidateCompatibility, ...]
    next_executable_candidate: str
    started_event_created: bool
    validation_scoring_performed: bool
    test_accessed: bool

    def payload(self) -> dict[str, object]:
        return {
            "experiment_plan_version": self.experiment_plan_version,
            "experiment_plan_hash": self.experiment_plan_hash,
            "guardrail_policy_version": self.guardrail_policy_version,
            "guardrail_policy_hash": self.guardrail_policy_hash,
            "historical_data_only": self.historical_data_only,
            "weather_required": self.weather_required,
            "production_plan_required": self.production_plan_required,
            "task8_task9_required": self.task8_task9_required,
            "prospective_capture_required": self.prospective_capture_required,
            "wall_clock_wait_required": self.wall_clock_wait_required,
            "test_remains_sealed": self.test_remains_sealed,
            "forecast_horizons": self.forecast_horizons,
            "candidate_06_execution_eligible": self.candidate_06_execution_eligible,
            "candidate_08_execution_eligible": self.candidate_08_execution_eligible,
            "candidate_01_rerun_forbidden": self.candidate_01_rerun_forbidden,
            "legacy_reconciled_validation_debit": self.legacy_reconciled_validation_debit,
            "canonical_started_count": self.canonical_started_count,
            "effective_consumed": self.effective_consumed,
            "remaining": self.remaining,
            "candidate_audit": [item.payload() for item in self.candidate_audit],
            "next_executable_candidate": self.next_executable_candidate,
            "started_event_created": self.started_event_created,
            "validation_scoring_performed": self.validation_scoring_performed,
            "test_accessed": self.test_accessed,
        }


def build_v2_historical_only_readiness() -> V2HistoricalOnlyReadiness:
    """Build the V2 policy snapshot without reading budget persistence."""

    audit = build_v2_candidate_compatibility_audit()
    next_candidate = next(
        (item.candidate_id for item in audit if item.current_v0_3_execution_eligible),
        "NONE",
    )
    return V2HistoricalOnlyReadiness(
        experiment_plan_version=EXPERIMENT_PLAN_V2_VERSION,
        experiment_plan_hash=EXPERIMENT_PLAN_V2_HASH,
        guardrail_policy_version=V2_GUARDRAIL_POLICY_VERSION,
        guardrail_policy_hash=V2_GUARDRAIL_POLICY_HASH,
        historical_data_only=V2_HISTORICAL_DATA_ONLY,
        weather_required=V2_WEATHER_REQUIRED,
        production_plan_required=V2_PRODUCTION_PLAN_REQUIRED,
        task8_task9_required=V2_TASK8_TASK9_REQUIRED,
        prospective_capture_required=V2_PROSPECTIVE_CAPTURE_REQUIRED,
        wall_clock_wait_required=V2_WALL_CLOCK_WAIT_REQUIRED,
        test_remains_sealed=V2_TEST_REMAINS_SEALED,
        forecast_horizons=V2_FORECAST_HORIZONS,
        candidate_06_execution_eligible=V2_CANDIDATE_06_EXECUTION_ELIGIBLE,
        candidate_08_execution_eligible=V2_CANDIDATE_08_EXECUTION_ELIGIBLE,
        candidate_01_rerun_forbidden=V2_CANDIDATE_01_RERUN_FORBIDDEN,
        legacy_reconciled_validation_debit=V2_LEGACY_RECONCILED_VALIDATION_DEBIT,
        canonical_started_count=V2_CANONICAL_STARTED_COUNT,
        effective_consumed=V2_EFFECTIVE_CONSUMED,
        remaining=V2_REMAINING_VALIDATION_EVALUATIONS,
        candidate_audit=audit,
        next_executable_candidate=next_candidate,
        started_event_created=False,
        validation_scoring_performed=False,
        test_accessed=False,
    )


def build_v2_historical_only_authority(repo_root: Path) -> V2HistoricalEvaluationAuthority:
    """Load and bind SOURCE-002 partitions for readiness checks only."""

    dataset = load_frozen_engineering_dataset(repo_root)
    authority = build_v2_historical_evaluation_authority(dataset)
    _ = v2_training_rows(authority)
    return authority


def v2_policy_is_self_consistent() -> bool:
    """Replay the V2 policy hash without changing the V1 policy identity."""

    from backend.app.rolling_backtest.canonical import sha256_payload

    return sha256_payload(canonical_guardrail_policy_v2()) == V2_GUARDRAIL_POLICY_HASH


def v2_guardrail_metric_availability() -> dict[str, str]:
    """Return current metric availability, including deliberate blockers."""

    return v2_metric_availability()


__all__ = [
    "V2_CANDIDATE_01_ID",
    "V2_CANDIDATE_02_ID",
    "V2_CANDIDATE_03_ID",
    "V2_CANDIDATE_04_ID",
    "V2_CANDIDATE_05_ID",
    "V2_CANDIDATE_06_ID",
    "V2_CANDIDATE_07_ID",
    "V2_CANDIDATE_08_ID",
    "V2_CANDIDATE_AUDIT_ORDER",
    "V2HistoricalEvaluationAuthority",
    "V2CandidateCompatibility",
    "V2HistoricalOnlyReadiness",
    "build_v2_candidate_compatibility_audit",
    "build_v2_historical_only_authority",
    "build_v2_historical_only_readiness",
    "v2_guardrail_metric_availability",
    "v2_policy_is_self_consistent",
]
