"""Read-only viability audit for the remaining V0.3 S4 candidates.

This module records what the current code actually proves for candidates 02,
05, and 07.  It is deliberately an audit boundary, not an execution adapter:
it has no dataset loader, scorer callback, TEST reader, database repository, or
validation-ledger write path.

The frozen registry's plan eligibility is kept separate from current V4
runnability.  A candidate can remain registered and eligible in the immutable
experiment plan while still lacking a lawful SOURCE-002-only scoring path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

TASK_ID: Final[str] = "V0_3_S4_REMAINING_CANDIDATE_VIABILITY_AND_CLOSURE_AUDIT_R1"
AUDIT_CANDIDATE_IDS: Final[tuple[str, ...]] = (
    "02_quantile_calibration",
    "05_marketable_rate",
    "07_harvest_efficiency",
)

SOURCE_002_IDENTITY: Final[str] = "f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785"
SOURCE_002_TRAIN_ROWS: Final[int] = 16_224
SOURCE_002_TRAIN_SHA256: Final[str] = (
    "be2d4184434a0f389af21c315945322e9216cd17cc471b772e3fff389d3386d2"
)
SOURCE_002_VALIDATION_ROWS: Final[int] = 8_006
SOURCE_002_VALIDATION_SHA256: Final[str] = (
    "4cbf1119f83034464159210ebbbeea5ec87848f92ce044bb328949a8f5331d06"
)

EXPERIMENT_PLAN_V2_VERSION: Final[str] = "v0.3-experiment-plan-v2"
EXPERIMENT_PLAN_V2_HASH: Final[str] = (
    "c2bfab4ec38b4ca640f62d061494961c5b49afe5b52fa675326aa80fdf5f8ad9"
)
V4_GUARDRAIL_POLICY_VERSION: Final[str] = "v0.3-s4-guardrail-policy-v4-breakdown-reporting-floor"
V4_GUARDRAIL_POLICY_HASH: Final[str] = (
    "f2b5c808d5a72170f055f891422f4253834a977cd5c74b450c8e4546653f46d2"
)
V2_FORECAST_HORIZONS: Final[tuple[int, ...]] = (7, 14, 21)
V2_HISTORICAL_DATA_ONLY: Final[bool] = True
V2_WEATHER_REQUIRED: Final[bool] = False
V2_PRODUCTION_PLAN_REQUIRED: Final[bool] = False
V2_TASK8_TASK9_REQUIRED: Final[bool] = False
V2_PROSPECTIVE_CAPTURE_REQUIRED: Final[bool] = False
V2_WALL_CLOCK_WAIT_REQUIRED: Final[bool] = False
V2_TEST_REMAINS_SEALED: Final[bool] = True
V2_CANDIDATE_01_RERUN_FORBIDDEN: Final[bool] = True
V2_CANDIDATE_06_EXECUTION_ELIGIBLE: Final[bool] = False
V2_CANDIDATE_08_EXECUTION_ELIGIBLE: Final[bool] = False

LEGACY_RECONCILED_VALIDATION_DEBIT: Final[int] = 4
CANONICAL_STARTED_COUNT: Final[int] = 4
EFFECTIVE_CONSUMED: Final[int] = 8
REMAINING_VALIDATION_BUDGET: Final[int] = 24

C02_ID: Final[str] = "02_quantile_calibration"
C05_ID: Final[str] = "05_marketable_rate"
C07_ID: Final[str] = "07_harvest_efficiency"

C02_STRUCTURAL_BLOCKER: Final[str] = (
    "C02_QUANTILE_ONLY_CANDIDATE_CANNOT_STRICTLY_IMPROVE_V4_PRIMARY_POINT_METRIC"
)
C02_PATH_BLOCKER: Final[str] = "NO_V2_BOUND_PREDICTION_QUANTILE_PATH"
C05_BLOCKER: Final[str] = (
    "C05_CANONICAL_MARKETABLE_RATE_AUTHORITY_UNAVAILABLE_IN_SOURCE002_HISTORICAL_LANE"
)
C07_BLOCKER: Final[str] = (
    "C07_CANONICAL_HARVEST_EFFICIENCY_AUTHORITY_UNAVAILABLE_IN_SOURCE002_HISTORICAL_LANE"
)
NO_REMAINING_CANDIDATE_BLOCKER: Final[str] = (
    "NO_REMAINING_CANDIDATE_HAS_A_LAWFUL_SOURCE002_ONLY_V4_SCORING_PATH"
)

V4_PRIMARY_METRIC: Final[str] = "daily_wape"
V4_PRIMARY_REQUIRED_RELATION: Final[str] = "CANDIDATE_STRICTLY_LESS_THAN_INCUMBENT"
V4_POINT_GUARDRAIL: Final[str] = "daily_mae"

CandidateStatus = Literal["COMPATIBLE", "INCOMPATIBLE"]


@dataclass(frozen=True, slots=True)
class RemainingCandidateViability:
    """Code-level facts for one candidate; construction performs no execution."""

    candidate_id: str
    candidate_family: str
    parent_model_id: str
    hypothesis: str
    planned_run_count: int
    parameter_or_feature_path: tuple[str, ...]
    canonical_control_fields: tuple[str, ...]
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
    source_002_only_candidate_path_exists: bool
    historical_only_input_compatible: bool
    historical_only_execution_compatible: bool
    plan_eligible: bool
    currently_runnable_under_v4: bool
    structurally_selectable_under_v4: bool
    status: CandidateStatus
    reason_code: str
    secondary_reason_codes: tuple[str, ...]
    code_evidence_paths: tuple[str, ...]
    required_future_authority: tuple[str, ...]

    def payload(self) -> dict[str, object]:
        """Return a JSON-safe, deterministic representation of this audit row."""

        return {
            "candidate_id": self.candidate_id,
            "candidate_family": self.candidate_family,
            "parent_model_id": self.parent_model_id,
            "hypothesis": self.hypothesis,
            "planned_run_count": self.planned_run_count,
            "parameter_or_feature_path": list(self.parameter_or_feature_path),
            "canonical_control_fields": list(self.canonical_control_fields),
            "actual_execution_function": list(self.actual_execution_function),
            "actual_data_sources_read": list(self.actual_data_sources_read),
            "uses_SOURCE_002_TRAIN": self.uses_source_002_train,
            "uses_SOURCE_002_VALIDATION": self.uses_source_002_validation,
            "uses_weather": self.uses_weather,
            "uses_production_plan": self.uses_production_plan,
            "uses_Task8": self.uses_task8,
            "uses_Task9": self.uses_task9,
            "uses_other_forward_looking_authority": self.uses_other_forward_looking_authority,
            "parameter_reaches_prediction_math": self.parameter_reaches_prediction_math,
            "parameter_change_can_change_prediction": self.parameter_change_can_change_prediction,
            "source_002_only_candidate_path_exists": self.source_002_only_candidate_path_exists,
            "historical_only_input_compatible": self.historical_only_input_compatible,
            "historical_only_execution_compatible": self.historical_only_execution_compatible,
            "plan_eligible": self.plan_eligible,
            "currently_runnable_under_v4": self.currently_runnable_under_v4,
            "structurally_selectable_under_v4": self.structurally_selectable_under_v4,
            "status": self.status,
            "reason_code": self.reason_code,
            "secondary_reason_codes": list(self.secondary_reason_codes),
            "code_evidence_paths": list(self.code_evidence_paths),
            "required_future_authority": list(self.required_future_authority),
        }


@dataclass(frozen=True, slots=True)
class FrozenS4Closure:
    """Current all-candidate closure, including the non-audited candidates."""

    candidate_runnability: tuple[tuple[str, bool, str], ...]
    next_executable_candidate: str
    current_frozen_plan_has_no_remaining_executable_candidate: bool
    s4_next_decision_required: str

    def payload(self) -> dict[str, object]:
        return {
            "candidate_runnability": [
                {
                    "candidate_id": candidate_id,
                    "currently_runnable_under_v4": runnable,
                    "reason_code": reason_code,
                }
                for candidate_id, runnable, reason_code in self.candidate_runnability
            ],
            "next_executable_candidate": self.next_executable_candidate,
            "current_frozen_plan_has_no_remaining_executable_candidate": (
                self.current_frozen_plan_has_no_remaining_executable_candidate
            ),
            "s4_next_decision_required": self.s4_next_decision_required,
        }


_FROZEN_REGISTRY_BINDINGS: Final[dict[str, tuple[str, str, str, int, bool]]] = {
    "01_parameter_calibration": (
        "PARAMETER_CALIBRATION",
        "V0_2_CURRENT_MODEL",
        "parameter_calibration_reduces_primary_metric_without_guardrail_regression",
        4,
        True,
    ),
    C02_ID: (
        "QUANTILE_CALIBRATION",
        "V0_2_CURRENT_MODEL",
        "quantile_calibration_improves_p80_p90_coverage_without_point_metric_regression",
        4,
        True,
    ),
    "03_phenology_offset": (
        "PARAMETER_CALIBRATION",
        "V0_2_CURRENT_MODEL",
        "versioned_phenology_offset_reduces_timing_error",
        4,
        True,
    ),
    "04_yield_parameter": (
        "PARAMETER_CALIBRATION",
        "V0_2_CURRENT_MODEL",
        "versioned_yield_parameter_calibration_reduces_quantity_error",
        4,
        True,
    ),
    C05_ID: (
        "PARAMETER_CALIBRATION",
        "V0_2_CURRENT_MODEL",
        "versioned_marketable_rate_calibration_reduces_marketable_quantity_error",
        4,
        True,
    ),
    "06_weather_response": (
        "STRUCTURAL_MODEL_CANDIDATE",
        "V0_2_CURRENT_MODEL",
        "authorized_weather_response_features_reduce_residual_error",
        4,
        True,
    ),
    C07_ID: (
        "PARAMETER_CALIBRATION",
        "V0_2_CURRENT_MODEL",
        "versioned_harvest_efficiency_calibration_reduces_peak_error",
        4,
        True,
    ),
    "08_residual_feature": (
        "STRUCTURAL_MODEL_CANDIDATE",
        "V0_2_CURRENT_MODEL",
        "authorized_residual_features_reduce_unexplained_residual",
        4,
        True,
    ),
}


def _registry_binding(candidate_id: str) -> tuple[str, str, str, int, bool]:
    try:
        return _FROZEN_REGISTRY_BINDINGS[candidate_id]
    except KeyError as exc:
        raise ValueError(f"candidate is missing from frozen registry: {candidate_id}") from exc


_CURRENT_V4_RUNNABILITY: Final[tuple[tuple[str, bool, str], ...]] = (
    ("01_parameter_calibration", False, "CANDIDATE_01_RERUN_FORBIDDEN"),
    (C02_ID, False, C02_STRUCTURAL_BLOCKER),
    (
        "03_phenology_offset",
        False,
        "C03_CANONICAL_TRAINING_SHIFT_MODEL_NOT_SEPARABLE_FROM_FORWARD_LOOKING_AUTHORITY",
    ),
    ("04_yield_parameter", False, "C04_EXHAUSTED_EVIDENCE_INSUFFICIENT"),
    (C05_ID, False, C05_BLOCKER),
    ("06_weather_response", False, "C06_WEATHER_OUTSIDE_V2_HISTORICAL_POLICY"),
    (C07_ID, False, C07_BLOCKER),
    ("08_residual_feature", False, "V2_HISTORICAL_ONLY_FEATURE_MANIFEST_REQUIRED"),
)


def _current_v4_runnability() -> dict[str, tuple[bool, str]]:
    return {
        candidate_id: (runnable, reason)
        for candidate_id, runnable, reason in _CURRENT_V4_RUNNABILITY
    }


def _build_c02() -> RemainingCandidateViability:
    family, parent, hypothesis, planned, plan_eligible = _registry_binding(C02_ID)
    return RemainingCandidateViability(
        candidate_id=C02_ID,
        candidate_family=family,
        parent_model_id=parent,
        hypothesis=hypothesis,
        planned_run_count=planned,
        parameter_or_feature_path=("intervals.p80_quantile", "intervals.p90_quantile"),
        canonical_control_fields=("P50", "P80", "P90", "daily_wape", "daily_mae"),
        actual_execution_function=(
            "backend.app.forecast_quality.quantile_coverage.compute_upper_quantile_coverage",
        ),
        actual_data_sources_read=(
            "S3_BINDING_FORECAST_ROWS",
            "S3_BINDING_ACTUAL_ROWS",
            "S3_TRAIN_VALIDATION_PAIRING_AUTHORITY",
        ),
        uses_source_002_train=False,
        uses_source_002_validation=False,
        uses_weather=False,
        uses_production_plan=False,
        uses_task8=False,
        uses_task9=False,
        uses_other_forward_looking_authority=False,
        parameter_reaches_prediction_math=False,
        parameter_change_can_change_prediction=False,
        source_002_only_candidate_path_exists=False,
        historical_only_input_compatible=True,
        historical_only_execution_compatible=False,
        plan_eligible=plan_eligible,
        currently_runnable_under_v4=False,
        structurally_selectable_under_v4=False,
        status="INCOMPATIBLE",
        reason_code=C02_STRUCTURAL_BLOCKER,
        secondary_reason_codes=(C02_PATH_BLOCKER,),
        code_evidence_paths=(
            "backend/app/forecast_quality/quantile_coverage.py:192-266",
            "backend/app/s4_v2_historical_only_execution.py:224-240",
            "backend/app/s4_experiment.py:55-62",
        ),
        required_future_authority=(
            "V2-bound candidate prediction path that applies p80/p90 controls",
            "P50 prediction identity that can be compared under daily_wape",
        ),
    )


def _build_c05() -> RemainingCandidateViability:
    family, parent, hypothesis, planned, plan_eligible = _registry_binding(C05_ID)
    return RemainingCandidateViability(
        candidate_id=C05_ID,
        candidate_family=family,
        parent_model_id=parent,
        hypothesis=hypothesis,
        planned_run_count=planned,
        parameter_or_feature_path=("marketable_rate",),
        canonical_control_fields=(
            "marketable_rate",
            "sorting_retention_rate",
            "postharvest_retention_rate",
        ),
        actual_execution_function=(
            "backend.app.core_forecast.application.execute_core_forecast_run",
            "backend.app.core_forecast.service.compose_complete_daily_marketable_curve",
        ),
        actual_data_sources_read=(
            "Task8 forecast authority",
            "Task9 harvest-state authority",
            "MarketableRetentionPolicySnapshot",
            "backend.app.models.planning.parameter_observation",
        ),
        uses_source_002_train=False,
        uses_source_002_validation=False,
        uses_weather=False,
        uses_production_plan=True,
        uses_task8=True,
        uses_task9=True,
        uses_other_forward_looking_authority=True,
        parameter_reaches_prediction_math=False,
        parameter_change_can_change_prediction=False,
        source_002_only_candidate_path_exists=False,
        historical_only_input_compatible=False,
        historical_only_execution_compatible=False,
        plan_eligible=plan_eligible,
        currently_runnable_under_v4=False,
        structurally_selectable_under_v4=False,
        status="INCOMPATIBLE",
        reason_code=C05_BLOCKER,
        secondary_reason_codes=("NO_BOUND_CANDIDATE_05_SCORING_PATH",),
        code_evidence_paths=(
            "backend/app/core_forecast/application.py:86-190",
            "backend/app/core_forecast/service.py:395-525",
            "backend/app/core_forecast/service.py:533-590",
            "backend/app/models/planning.py:236-250",
            "docs/11_production_plan_and_phenology.md:71-93",
        ),
        required_future_authority=(
            "Unambiguous SOURCE-002 historical marketable-rate authority",
            "A V2-bound candidate scorer that applies the rate to the prediction path",
        ),
    )


def _build_c07() -> RemainingCandidateViability:
    family, parent, hypothesis, planned, plan_eligible = _registry_binding(C07_ID)
    return RemainingCandidateViability(
        candidate_id=C07_ID,
        candidate_family=family,
        parent_model_id=parent,
        hypothesis=hypothesis,
        planned_run_count=planned,
        parameter_or_feature_path=("harvest_efficiency",),
        canonical_control_fields=(
            "labor_availability_ratio",
            "weather_harvest_efficiency_ratio",
            "operational_efficiency_ratio",
        ),
        actual_execution_function=("backend.app.harvest_state.service.run_harvest_state_model",),
        actual_data_sources_read=(
            "task9_daily_capacity_authority",
            "labor_availability_ratio",
            "weather_harvest_efficiency_ratio",
            "operational_efficiency_ratio",
            "weather feature authority",
            "holiday calendar authority",
        ),
        uses_source_002_train=False,
        uses_source_002_validation=False,
        uses_weather=True,
        uses_production_plan=False,
        uses_task8=False,
        uses_task9=True,
        uses_other_forward_looking_authority=True,
        parameter_reaches_prediction_math=False,
        parameter_change_can_change_prediction=False,
        source_002_only_candidate_path_exists=False,
        historical_only_input_compatible=False,
        historical_only_execution_compatible=False,
        plan_eligible=plan_eligible,
        currently_runnable_under_v4=False,
        structurally_selectable_under_v4=False,
        status="INCOMPATIBLE",
        reason_code=C07_BLOCKER,
        secondary_reason_codes=("NO_BOUND_CANDIDATE_07_SCORING_PATH",),
        code_evidence_paths=(
            "backend/app/harvest_state/service.py:780-885",
            "backend/app/harvest_state/weather.py:49-68",
            "backend/app/harvest_state/authority_schemas.py:163-204",
            "backend/app/models/task9_authority.py:230-234",
        ),
        required_future_authority=(
            "Frozen historical definition and labels for harvest efficiency",
            "SOURCE-002 derivation of all canonical efficiency inputs",
            "A V2-bound candidate scorer that applies the calibrated efficiency",
        ),
    )


def build_remaining_candidate_viability_audit() -> tuple[RemainingCandidateViability, ...]:
    """Return the C02/C05/C07 audit in the frozen optimization order."""

    rows = (_build_c02(), _build_c05(), _build_c07())
    if tuple(row.candidate_id for row in rows) != AUDIT_CANDIDATE_IDS:
        raise AssertionError("remaining candidate audit order drifted")
    return rows


def build_frozen_s4_closure() -> FrozenS4Closure:
    """Reconcile all eight current V4 runnability facts without executing them."""

    current = _current_v4_runnability()
    required_ids = (
        "01_parameter_calibration",
        "02_quantile_calibration",
        "03_phenology_offset",
        "04_yield_parameter",
        "05_marketable_rate",
        "06_weather_response",
        "07_harvest_efficiency",
        "08_residual_feature",
    )
    missing = [candidate_id for candidate_id in required_ids if candidate_id not in current]
    if missing:
        raise ValueError(f"current V4 audit is missing candidates: {missing}")
    runnability = tuple(
        (candidate_id, current[candidate_id][0], current[candidate_id][1])
        for candidate_id in required_ids
    )
    runnable = tuple(candidate_id for candidate_id, is_runnable, _ in runnability if is_runnable)
    return FrozenS4Closure(
        candidate_runnability=runnability,
        next_executable_candidate=runnable[0] if runnable else "NONE",
        current_frozen_plan_has_no_remaining_executable_candidate=not runnable,
        s4_next_decision_required=(
            "COORDINATOR_CHOICE_BETWEEN_INCUMBENT_CLOSURE_OR_NEW_EXPERIMENT_PLAN_AUTHORIZATION"
            if not runnable
            else "NONE"
        ),
    )


def build_remaining_candidate_audit_payload() -> dict[str, object]:
    """Return the complete read-only evidence payload used by docs and tests."""

    registry = _FROZEN_REGISTRY_BINDINGS
    plan_eligibility = {
        candidate_id: registry[candidate_id][4]
        for candidate_id in (
            "01_parameter_calibration",
            "02_quantile_calibration",
            "03_phenology_offset",
            "04_yield_parameter",
            "05_marketable_rate",
            "06_weather_response",
            "07_harvest_efficiency",
            "08_residual_feature",
        )
    }
    return {
        "task_id": TASK_ID,
        "experiment_plan_version": EXPERIMENT_PLAN_V2_VERSION,
        "experiment_plan_hash": EXPERIMENT_PLAN_V2_HASH,
        "guardrail_policy_version": V4_GUARDRAIL_POLICY_VERSION,
        "guardrail_policy_hash": V4_GUARDRAIL_POLICY_HASH,
        "historical_data_only": V2_HISTORICAL_DATA_ONLY,
        "source_002_materialized_dataset_identity": SOURCE_002_IDENTITY,
        "source_002_train_rows": SOURCE_002_TRAIN_ROWS,
        "source_002_train_sha256": SOURCE_002_TRAIN_SHA256,
        "source_002_validation_rows": SOURCE_002_VALIDATION_ROWS,
        "source_002_validation_sha256": SOURCE_002_VALIDATION_SHA256,
        "forecast_horizons": list(V2_FORECAST_HORIZONS),
        "weather_required": V2_WEATHER_REQUIRED,
        "production_plan_required": V2_PRODUCTION_PLAN_REQUIRED,
        "task8_task9_required": V2_TASK8_TASK9_REQUIRED,
        "prospective_capture_required": V2_PROSPECTIVE_CAPTURE_REQUIRED,
        "wall_clock_wait_required": V2_WALL_CLOCK_WAIT_REQUIRED,
        "test_remains_sealed": V2_TEST_REMAINS_SEALED,
        "frozen_plan_eligibility": plan_eligibility,
        "candidate_compatibility_audit": [
            row.payload() for row in build_remaining_candidate_viability_audit()
        ],
        "frozen_s4_closure": build_frozen_s4_closure().payload(),
        "budget": {
            "legacy_reconciled_validation_debit": LEGACY_RECONCILED_VALIDATION_DEBIT,
            "canonical_started_count": CANONICAL_STARTED_COUNT,
            "effective_consumed": EFFECTIVE_CONSUMED,
            "remaining": REMAINING_VALIDATION_BUDGET,
            "budget_delta": 0,
        },
        "execution_boundary": {
            "validation_execution_authorized": False,
            "validation_scoring_performed": False,
            "evaluation_started_created": False,
            "evaluation_terminal_created": False,
            "test_access_requested": False,
            "test_bytes_read": False,
            "candidate_execution_performed": False,
        },
        "selection_policy": {
            "primary_metric": V4_PRIMARY_METRIC,
            "primary_required_relation": V4_PRIMARY_REQUIRED_RELATION,
            "point_guardrail": V4_POINT_GUARDRAIL,
            "no_proxy_parameter_invention": True,
            "no_source002_field_reinterpretation": True,
        },
        "candidate_01_rerun_forbidden": V2_CANDIDATE_01_RERUN_FORBIDDEN,
        "candidate_06_execution_eligible": V2_CANDIDATE_06_EXECUTION_ELIGIBLE,
        "candidate_08_execution_eligible": V2_CANDIDATE_08_EXECUTION_ELIGIBLE,
        "next_executable_candidate": build_frozen_s4_closure().next_executable_candidate,
        "no_remaining_candidate_blocker": NO_REMAINING_CANDIDATE_BLOCKER,
    }


__all__ = [
    "AUDIT_CANDIDATE_IDS",
    "CANONICAL_STARTED_COUNT",
    "C02_ID",
    "C02_PATH_BLOCKER",
    "C02_STRUCTURAL_BLOCKER",
    "C05_BLOCKER",
    "C05_ID",
    "C07_BLOCKER",
    "C07_ID",
    "EFFECTIVE_CONSUMED",
    "FrozenS4Closure",
    "LEGACY_RECONCILED_VALIDATION_DEBIT",
    "REMAINING_VALIDATION_BUDGET",
    "RemainingCandidateViability",
    "SOURCE_002_IDENTITY",
    "SOURCE_002_TRAIN_ROWS",
    "SOURCE_002_TRAIN_SHA256",
    "SOURCE_002_VALIDATION_ROWS",
    "SOURCE_002_VALIDATION_SHA256",
    "TASK_ID",
    "build_frozen_s4_closure",
    "build_remaining_candidate_audit_payload",
    "build_remaining_candidate_viability_audit",
]
