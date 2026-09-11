"""Read-only V2 authority audit for the remaining S4 candidates.

The audit deliberately has no validation loader, scorer callback, TEST reader,
database repository, or ledger write path.  Immutable registry selection
eligibility is reported separately from current historical-only execution
eligibility and from current V4 runnability.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final, Literal

from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read import (
    OFFICIAL_TRAIN_CONTENT_SHA256,
    OFFICIAL_TRAIN_ROW_COUNT,
    OFFICIAL_VALIDATION_CONTENT_SHA256,
    OFFICIAL_VALIDATION_ROW_COUNT,
)
from backend.app.s4_experiment import (
    EXPERIMENT_PLAN_V2_HASH,
    EXPERIMENT_PLAN_V2_VERSION,
    FROZEN_CANDIDATE_REGISTRY,
    V2_BUDGET_SNAPSHOT_CANONICAL_STARTED_COUNT,
    V2_BUDGET_SNAPSHOT_EFFECTIVE_CONSUMED,
    V2_BUDGET_SNAPSHOT_REMAINING_VALIDATION_EVALUATIONS,
    V2_CANDIDATE_01_RERUN_FORBIDDEN,
    V2_FORECAST_HORIZONS,
    V2_HISTORICAL_DATA_ONLY,
    V2_LEGACY_RECONCILED_VALIDATION_DEBIT,
    V2_PRODUCTION_PLAN_REQUIRED,
    V2_PROSPECTIVE_CAPTURE_REQUIRED,
    V2_TASK8_TASK9_REQUIRED,
    V2_TEST_REMAINS_SEALED,
    V2_WALL_CLOCK_WAIT_REQUIRED,
    V2_WEATHER_REQUIRED,
    V4_GUARDRAIL_POLICY_HASH,
    V4_GUARDRAIL_POLICY_VERSION,
    CandidateRegistration,
    MetricObservation,
    compare_primary_metric,
)
from backend.app.s4_local_engineering import (
    SOURCE_002_MATERIALIZED_DATASET_IDENTITY_SHA256,
)
from backend.app.s4_v2_historical_only_execution import (
    V2_C05_CANONICAL_EXECUTION_FUNCTIONS,
    V2_C05_CANONICAL_PARAMETER_PATH,
    V2_C05_CANONICAL_SOURCE_DOMAIN,
    V2_C07_CANONICAL_EXECUTION_FUNCTIONS,
    V2_C07_CANONICAL_PARAMETER_PATH,
    V2_C07_CANONICAL_SOURCE_DOMAIN,
    V2_CANDIDATE_01_ID,
    V2_CANDIDATE_02_ID,
    V2_CANDIDATE_04_ID,
    V2_CANDIDATE_05_ID,
    V2_CANDIDATE_06_ID,
    V2_CANDIDATE_07_ID,
    V2_CANDIDATE_08_ID,
    V2_CANDIDATE_AUDIT_ORDER,
    V2CandidateCompatibility,
    build_v2_candidate_compatibility_audit,
)

TASK_ID: Final[str] = "V0_3_S4_REMAINING_CANDIDATE_AUTHORITY_BINDING_CORRECTION_R2"
AUDIT_CANDIDATE_IDS: Final[tuple[str, ...]] = (
    V2_CANDIDATE_02_ID,
    V2_CANDIDATE_05_ID,
    V2_CANDIDATE_07_ID,
)

C02_ID: Final[str] = V2_CANDIDATE_02_ID
C05_ID: Final[str] = V2_CANDIDATE_05_ID
C07_ID: Final[str] = V2_CANDIDATE_07_ID

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
C04_EXHAUSTED_EVIDENCE: Final[str] = "C04_EXHAUSTED_EVIDENCE_INSUFFICIENT"
NO_REMAINING_CANDIDATE_BLOCKER: Final[str] = (
    "NO_REMAINING_CANDIDATE_HAS_A_LAWFUL_SOURCE002_ONLY_V4_SCORING_PATH"
)

V4_PRIMARY_METRIC: Final[str] = "daily_wape"
V4_PRIMARY_REQUIRED_RELATION: Final[str] = "CANDIDATE_STRICTLY_LESS_THAN_INCUMBENT"
V4_POINT_GUARDRAIL: Final[str] = "daily_mae"

# These values are not a live database read.  They are the last accepted
# durable snapshot recorded by the immutable C04 execution evidence.  Keeping
# the provenance explicit prevents this read-only audit from claiming a stale
# document counter is current PostgreSQL authority.
DURABLE_BUDGET_READBACK_AVAILABLE: Final[bool] = False
LAST_ACCEPTED_DURABLE_BUDGET_EVIDENCE_PATH: Final[str] = (
    "docs/v0-3/s4/evidence/s4-c04-controlled-real-validation-r1.json"
)
LAST_ACCEPTED_DURABLE_BUDGET_EVIDENCE_SHA256: Final[str] = (
    "78b1489b28fe0056e1c7fd88165f927c04d16bf1083926048ba4c36e3c1498b3"
)
LAST_ACCEPTED_CANONICAL_STARTED_COUNT: Final[int] = 4
LAST_ACCEPTED_EFFECTIVE_CONSUMED: Final[int] = 8
LAST_ACCEPTED_REMAINING: Final[int] = 24
LAST_ACCEPTED_BUDGET_DELTA: Final[int] = 0

CandidateStatus = Literal["COMPATIBLE", "INCOMPATIBLE"]


@dataclass(frozen=True, slots=True)
class RemainingCandidateViability:
    """Code-level facts for one candidate; construction performs no execution."""

    candidate_id: str
    candidate_family: str
    parent_model_id: str
    hypothesis: str
    planned_run_count: int
    frozen_registry_selection_eligibility: str
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
    current_historical_only_execution_eligibility: bool
    currently_runnable_under_v4: bool
    structurally_selectable_under_v4: bool
    status: CandidateStatus
    reason_code: str
    secondary_reason_codes: tuple[str, ...]
    code_evidence_paths: tuple[str, ...]
    required_future_authority: tuple[str, ...]
    implementation_blocker: str | None = None
    structural_selection_blocker: str | None = None
    requires_policy_amendment: bool = False
    canonical_parameter_path: tuple[str, ...] = ()
    canonical_execution_functions: tuple[str, ...] = ()
    canonical_source_domain: tuple[str, ...] = ()
    explicit_total_override_exists: bool | None = None

    @property
    def frozen_registry_selection_eligible(self) -> bool:
        return self.frozen_registry_selection_eligibility == ("REGISTERED_AND_GUARDRAIL_ELIGIBLE")

    @property
    def current_v0_3_execution_eligible(self) -> bool:
        """Compatibility alias whose value is sourced from the V2 audit row."""

        return self.current_historical_only_execution_eligibility

    def payload(self) -> dict[str, object]:
        """Return a JSON-safe, deterministic representation of this audit row."""

        return {
            "candidate_id": self.candidate_id,
            "candidate_family": self.candidate_family,
            "parent_model_id": self.parent_model_id,
            "hypothesis": self.hypothesis,
            "planned_run_count": self.planned_run_count,
            "frozen_registry_selection_eligibility": self.frozen_registry_selection_eligibility,
            "frozen_registry_selection_eligible": self.frozen_registry_selection_eligible,
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
            "current_historical_only_execution_eligibility": (
                self.current_historical_only_execution_eligibility
            ),
            "current_v0_3_execution_eligible": self.current_v0_3_execution_eligible,
            "currently_runnable_under_v4": self.currently_runnable_under_v4,
            "structurally_selectable_under_v4": self.structurally_selectable_under_v4,
            "status": self.status,
            "reason_code": self.reason_code,
            "secondary_reason_codes": list(self.secondary_reason_codes),
            "code_evidence_paths": list(self.code_evidence_paths),
            "required_future_authority": list(self.required_future_authority),
            "implementation_blocker": self.implementation_blocker,
            "structural_selection_blocker": self.structural_selection_blocker,
            "requires_policy_amendment": self.requires_policy_amendment,
            "canonical_parameter_path": list(self.canonical_parameter_path),
            "canonical_execution_functions": list(self.canonical_execution_functions),
            "canonical_source_domain": list(self.canonical_source_domain),
            "explicit_total_override_exists": self.explicit_total_override_exists,
        }


@dataclass(frozen=True, slots=True)
class FrozenS4Closure:
    """Current all-candidate closure, derived from canonical audit facts."""

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


def _registry_registration(candidate_id: str) -> CandidateRegistration:
    """Return registry identity from the canonical S4-A registry only."""

    for registration in FROZEN_CANDIDATE_REGISTRY:
        if registration.candidate_id == candidate_id:
            return registration
    raise ValueError(f"candidate is missing from frozen registry: {candidate_id}")


def _v2_audit_by_id() -> dict[str, V2CandidateCompatibility]:
    rows = build_v2_candidate_compatibility_audit()
    if tuple(row.candidate_id for row in rows) != V2_CANDIDATE_AUDIT_ORDER:
        raise AssertionError("V2 candidate compatibility audit order drifted")
    return {row.candidate_id: row for row in rows}


def _remaining_from_v2(
    candidate_id: str,
    *,
    canonical_control_fields: tuple[str, ...],
    structurally_selectable_under_v4: bool,
    reason_code: str,
    secondary_reason_codes: tuple[str, ...],
    code_evidence_paths: tuple[str, ...],
    required_future_authority: tuple[str, ...],
    implementation_blocker: str | None = None,
    structural_selection_blocker: str | None = None,
    requires_policy_amendment: bool = False,
) -> RemainingCandidateViability:
    row = _v2_audit_by_id()[candidate_id]
    registration = _registry_registration(candidate_id)
    return RemainingCandidateViability(
        candidate_id=registration.candidate_id,
        candidate_family=registration.candidate_family,
        parent_model_id=registration.parent_model_id,
        hypothesis=registration.hypothesis,
        planned_run_count=registration.planned_run_count,
        frozen_registry_selection_eligibility=registration.selection_eligibility,
        parameter_or_feature_path=row.parameter_or_feature_path,
        canonical_control_fields=canonical_control_fields,
        actual_execution_function=row.actual_execution_function,
        actual_data_sources_read=row.actual_data_sources_read,
        uses_source_002_train=row.uses_source_002_train,
        uses_source_002_validation=row.uses_source_002_validation,
        uses_weather=row.uses_weather,
        uses_production_plan=row.uses_production_plan,
        uses_task8=row.uses_task8,
        uses_task9=row.uses_task9,
        uses_other_forward_looking_authority=row.uses_other_forward_looking_authority,
        parameter_reaches_prediction_math=row.parameter_reaches_prediction_math,
        parameter_change_can_change_prediction=row.parameter_change_can_change_prediction,
        source_002_only_candidate_path_exists=row.historical_only_execution_compatible,
        historical_only_input_compatible=row.historical_only_input_compatible,
        historical_only_execution_compatible=row.historical_only_execution_compatible,
        current_historical_only_execution_eligibility=row.current_v0_3_execution_eligible,
        currently_runnable_under_v4=False,
        structurally_selectable_under_v4=structurally_selectable_under_v4,
        status=row.status,
        reason_code=reason_code,
        secondary_reason_codes=secondary_reason_codes,
        code_evidence_paths=code_evidence_paths,
        required_future_authority=required_future_authority,
        implementation_blocker=implementation_blocker,
        structural_selection_blocker=structural_selection_blocker,
        requires_policy_amendment=requires_policy_amendment,
        canonical_parameter_path=row.canonical_parameter_path,
        canonical_execution_functions=row.canonical_execution_functions,
        canonical_source_domain=row.canonical_source_domain,
        explicit_total_override_exists=row.explicit_total_override_exists,
    )


def _build_c02() -> RemainingCandidateViability:
    return _remaining_from_v2(
        C02_ID,
        canonical_control_fields=("P50", "P80", "P90", "daily_wape", "daily_mae"),
        structurally_selectable_under_v4=False,
        reason_code=C02_STRUCTURAL_BLOCKER,
        secondary_reason_codes=(C02_PATH_BLOCKER,),
        implementation_blocker=C02_PATH_BLOCKER,
        structural_selection_blocker=C02_STRUCTURAL_BLOCKER,
        requires_policy_amendment=True,
        code_evidence_paths=(
            "backend/app/forecast_quality/quantile_coverage.py:192-266",
            "backend/app/s4_v2_historical_only_execution.py:252-291",
            "backend/app/s4_experiment.py:986-1023",
        ),
        required_future_authority=(
            "V2-bound candidate prediction path that applies p80/p90 controls",
            "P50 prediction identity that can be compared under daily_wape",
            "Separate policy amendment if a quantile-only candidate remains in scope",
        ),
    )


def _build_c05() -> RemainingCandidateViability:
    return _remaining_from_v2(
        C05_ID,
        canonical_control_fields=(
            "marketable_rate",
            "sorting_retention_rate",
            "postharvest_retention_rate",
            "expected_total_marketable_kg",
        ),
        structurally_selectable_under_v4=False,
        reason_code=C05_BLOCKER,
        secondary_reason_codes=(
            "C05_MARKETABLE_RATE_IS_NOT_CORE_CURVE_RETENTION",
            "NO_SOURCE002_MARKETABLE_RATE_AUTHORITY",
        ),
        code_evidence_paths=(
            "backend/app/planning/plan_service.py:119-125",
            "backend/app/planning/plan_service.py:369-410",
            "backend/app/maturity/service.py:682-742",
            "backend/app/maturity/service.py:920-922",
            "backend/app/maturity/service.py:2508-2604",
            "backend/app/core_forecast/service.py:433-510",
        ),
        required_future_authority=(
            "Unambiguous SOURCE-002 historical planted-area/yield/marketable-rate authority",
            "A V2-bound candidate scorer that applies marketable_rate on the canonical upstream "
            "path",
        ),
    )


def _build_c07() -> RemainingCandidateViability:
    return _remaining_from_v2(
        C07_ID,
        canonical_control_fields=(
            "labor_availability_ratio",
            "weather_harvest_efficiency_ratio",
            "operational_efficiency_ratio",
            "resolved_effective_capacity_kg_per_day",
        ),
        structurally_selectable_under_v4=False,
        reason_code=C07_BLOCKER,
        secondary_reason_codes=(
            "NO_SOURCE002_HARVEST_EFFICIENCY_INPUT_AUTHORITY",
            "EFFECTIVE_CAPACITY_REQUIRES_WEATHER_AND_TASK9_STATE",
        ),
        code_evidence_paths=(
            "backend/app/harvest_state/service.py:631-886",
            "backend/app/harvest_state/weather.py:49-68",
            "backend/app/harvest_state/authority_schemas.py:163-204",
            "backend/app/models/task9_authority.py:230-234",
        ),
        required_future_authority=(
            "Frozen historical labels for labor, weather, and operational efficiency",
            "SOURCE-002 derivation of every canonical effective-capacity input",
            "A V2-bound candidate scorer that applies the calibrated efficiency",
        ),
    )


def build_remaining_candidate_viability_audit() -> tuple[RemainingCandidateViability, ...]:
    """Return C02/C05/C07 in the frozen optimization order."""

    rows = (_build_c02(), _build_c05(), _build_c07())
    if tuple(row.candidate_id for row in rows) != AUDIT_CANDIDATE_IDS:
        raise AssertionError("remaining candidate audit order drifted")
    return rows


def _derive_current_v4_runnability() -> dict[str, tuple[bool, str]]:
    """Compose current runnability from canonical facts, never a static map."""

    rows = _v2_audit_by_id()
    result: dict[str, tuple[bool, str]] = {}
    for candidate_id in V2_CANDIDATE_AUDIT_ORDER:
        row = rows[candidate_id]
        if candidate_id == V2_CANDIDATE_01_ID and V2_CANDIDATE_01_RERUN_FORBIDDEN:
            result[candidate_id] = (False, "CANDIDATE_01_RERUN_FORBIDDEN")
        elif candidate_id == C02_ID:
            result[candidate_id] = (False, C02_STRUCTURAL_BLOCKER)
        elif candidate_id == V2_CANDIDATE_04_ID and row.reason_code == C04_EXHAUSTED_EVIDENCE:
            result[candidate_id] = (False, C04_EXHAUSTED_EVIDENCE)
        elif (
            candidate_id in (V2_CANDIDATE_06_ID, V2_CANDIDATE_08_ID)
            and not row.current_v0_3_execution_eligible
        ):
            result[candidate_id] = (False, row.reason_code)
        elif candidate_id == C05_ID:
            result[candidate_id] = (False, C05_BLOCKER)
        elif candidate_id == C07_ID:
            result[candidate_id] = (False, C07_BLOCKER)
        else:
            runnable = (
                row.current_v0_3_execution_eligible and row.historical_only_execution_compatible
            )
            result[candidate_id] = (runnable, row.reason_code if not runnable else "NONE")
    return result


def build_frozen_s4_closure() -> FrozenS4Closure:
    """Reconcile all eight current V4 runnability facts without execution."""

    current = _derive_current_v4_runnability()
    runnability = tuple(
        (candidate_id, current[candidate_id][0], current[candidate_id][1])
        for candidate_id in V2_CANDIDATE_AUDIT_ORDER
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


def c02_quantile_effect_proof() -> dict[str, object]:
    """Prove that p80/p90-only mutation leaves the V4 primary P50 metric unchanged."""

    base_prediction = {
        "P50": Decimal("100.000000"),
        "P80": Decimal("120.000000"),
        "P90": Decimal("140.000000"),
    }
    changed_intervals = {
        "P50": Decimal("100.000000"),
        "P80": Decimal("130.000000"),
        "P90": Decimal("150.000000"),
    }
    equal_wape = compare_primary_metric(
        MetricObservation.computed("daily_wape", Decimal("1.000000")),
        MetricObservation.computed("daily_wape", Decimal("1.000000")),
    )
    return {
        "p50_unchanged": base_prediction["P50"] == changed_intervals["P50"],
        "p80_changed": base_prediction["P80"] != changed_intervals["P80"],
        "p90_changed": base_prediction["P90"] != changed_intervals["P90"],
        "base_prediction": {key: format(value, "f") for key, value in base_prediction.items()},
        "changed_intervals": {key: format(value, "f") for key, value in changed_intervals.items()},
        "equal_daily_wape_status": equal_wape.status,
        "equal_daily_wape_reason_code": equal_wape.reason_code,
        "equal_wape_is_not_improved": (
            equal_wape.status == "FAIL" and equal_wape.reason_code == "NOT_IMPROVED"
        ),
    }


def _registry_selection_payload() -> dict[str, dict[str, object]]:
    return {
        registration.candidate_id: {
            "candidate_family": registration.candidate_family,
            "parent_model_id": registration.parent_model_id,
            "hypothesis": registration.hypothesis,
            "planned_run_count": registration.planned_run_count,
            "selection_eligibility": registration.selection_eligibility,
        }
        for registration in FROZEN_CANDIDATE_REGISTRY
    }


def _current_execution_eligibility_payload(
    rows: dict[str, V2CandidateCompatibility],
) -> dict[str, bool]:
    return {
        candidate_id: rows[candidate_id].current_v0_3_execution_eligible
        for candidate_id in V2_CANDIDATE_AUDIT_ORDER
    }


def _budget_snapshot_payload() -> dict[str, object]:
    return {
        "state_class": "LAST_ACCEPTED_DURABLE_BUDGET_SNAPSHOT",
        "durable_budget_readback_available": DURABLE_BUDGET_READBACK_AVAILABLE,
        "current_durable_state_readback_performed": False,
        "values_are_current_database_readback": False,
        "provenance": {
            "evidence_path": LAST_ACCEPTED_DURABLE_BUDGET_EVIDENCE_PATH,
            "evidence_sha256": LAST_ACCEPTED_DURABLE_BUDGET_EVIDENCE_SHA256,
        },
        "legacy_reconciled_validation_debit": V2_LEGACY_RECONCILED_VALIDATION_DEBIT,
        "canonical_started_count": LAST_ACCEPTED_CANONICAL_STARTED_COUNT,
        "effective_consumed": LAST_ACCEPTED_EFFECTIVE_CONSUMED,
        "remaining": LAST_ACCEPTED_REMAINING,
        "budget_delta": LAST_ACCEPTED_BUDGET_DELTA,
        "v2_freeze_snapshot": {
            "canonical_started_count": V2_BUDGET_SNAPSHOT_CANONICAL_STARTED_COUNT,
            "effective_consumed": V2_BUDGET_SNAPSHOT_EFFECTIVE_CONSUMED,
            "remaining": V2_BUDGET_SNAPSHOT_REMAINING_VALIDATION_EVALUATIONS,
        },
    }


def build_remaining_candidate_audit_payload() -> dict[str, object]:
    """Return the machine-derived read-only payload used by docs and tests."""

    v2_rows = _v2_audit_by_id()
    closure = build_frozen_s4_closure()
    candidate_rows = build_remaining_candidate_viability_audit()
    closure_rows = closure.payload()["candidate_runnability"]
    assert isinstance(closure_rows, list)
    c05_closure = closure_rows[4]
    c07_closure = closure_rows[6]
    assert isinstance(c05_closure, dict)
    assert isinstance(c07_closure, dict)
    return {
        "task_id": TASK_ID,
        "experiment_plan_version": EXPERIMENT_PLAN_V2_VERSION,
        "experiment_plan_hash": EXPERIMENT_PLAN_V2_HASH,
        "guardrail_policy_version": V4_GUARDRAIL_POLICY_VERSION,
        "guardrail_policy_hash": V4_GUARDRAIL_POLICY_HASH,
        "historical_data_only": V2_HISTORICAL_DATA_ONLY,
        "source_002_materialized_dataset_identity": SOURCE_002_MATERIALIZED_DATASET_IDENTITY_SHA256,
        "source_002_train_rows": OFFICIAL_TRAIN_ROW_COUNT,
        "source_002_train_sha256": OFFICIAL_TRAIN_CONTENT_SHA256,
        "source_002_validation_rows": OFFICIAL_VALIDATION_ROW_COUNT,
        "source_002_validation_sha256": OFFICIAL_VALIDATION_CONTENT_SHA256,
        "forecast_horizons": list(V2_FORECAST_HORIZONS),
        "weather_required": V2_WEATHER_REQUIRED,
        "production_plan_required": V2_PRODUCTION_PLAN_REQUIRED,
        "task8_task9_required": V2_TASK8_TASK9_REQUIRED,
        "prospective_capture_required": V2_PROSPECTIVE_CAPTURE_REQUIRED,
        "wall_clock_wait_required": V2_WALL_CLOCK_WAIT_REQUIRED,
        "test_remains_sealed": V2_TEST_REMAINS_SEALED,
        "frozen_registry_selection_eligibility": _registry_selection_payload(),
        "frozen_plan_eligibility": _current_execution_eligibility_payload(v2_rows),
        "v2_current_execution_eligibility": _current_execution_eligibility_payload(v2_rows),
        "candidate_compatibility_audit": [row.payload() for row in candidate_rows],
        "frozen_s4_closure": closure.payload(),
        "budget": _budget_snapshot_payload(),
        "execution_boundary": {
            "validation_execution_authorized": False,
            "validation_scoring_performed": False,
            "evaluation_started_created": False,
            "evaluation_terminal_created": False,
            "test_access_requested": False,
            "test_bytes_read": False,
            "candidate_execution_performed": False,
            "durable_budget_readback_available": DURABLE_BUDGET_READBACK_AVAILABLE,
        },
        "selection_policy": {
            "primary_metric": V4_PRIMARY_METRIC,
            "primary_required_relation": V4_PRIMARY_REQUIRED_RELATION,
            "point_guardrail": V4_POINT_GUARDRAIL,
            "no_proxy_parameter_invention": True,
            "no_source002_field_reinterpretation": True,
            "c02_implementation_blocker": C02_PATH_BLOCKER,
            "c02_structural_selection_blocker": C02_STRUCTURAL_BLOCKER,
            "c02_requires_policy_amendment": True,
            "c02_quantile_effect_proof": c02_quantile_effect_proof(),
        },
        "c05_canonical_path_audit": {
            "canonical_parameter_path": list(V2_C05_CANONICAL_PARAMETER_PATH),
            "canonical_execution_functions": list(V2_C05_CANONICAL_EXECUTION_FUNCTIONS),
            "canonical_source_domain": list(V2_C05_CANONICAL_SOURCE_DOMAIN),
            "explicit_total_override_exists": True,
            "marketable_rate_formula": (
                "planted_area_mu * expected_yield_kg_per_mu * marketable_rate"
            ),
            "core_curve_does_not_reapply_marketable_rate": True,
            "sorting_and_postharvest_retention_are_distinct": True,
            "currently_runnable_under_v4": c05_closure["currently_runnable_under_v4"],
            "blocker": C05_BLOCKER,
        },
        "c07_canonical_path_audit": {
            "canonical_parameter_path": list(V2_C07_CANONICAL_PARAMETER_PATH),
            "canonical_execution_functions": list(V2_C07_CANONICAL_EXECUTION_FUNCTIONS),
            "canonical_source_domain": list(V2_C07_CANONICAL_SOURCE_DOMAIN),
            "effective_capacity_formula": (
                "resolved_nominal_capacity * labor_availability_ratio * "
                "weather_harvest_efficiency_ratio * operational_efficiency_ratio"
            ),
            "currently_runnable_under_v4": c07_closure["currently_runnable_under_v4"],
            "blocker": C07_BLOCKER,
        },
        "candidate_01_rerun_forbidden": V2_CANDIDATE_01_RERUN_FORBIDDEN,
        "candidate_06_execution_eligible": v2_rows[
            V2_CANDIDATE_06_ID
        ].current_v0_3_execution_eligible,
        "candidate_08_execution_eligible": v2_rows[
            V2_CANDIDATE_08_ID
        ].current_v0_3_execution_eligible,
        "next_executable_candidate": closure.next_executable_candidate,
        "no_remaining_candidate_blocker": NO_REMAINING_CANDIDATE_BLOCKER,
    }


def build_machine_derived_audit_payload() -> dict[str, object]:
    """Return the exact projection checked into the machine-readable evidence."""

    payload = build_remaining_candidate_audit_payload()
    closure = payload["frozen_s4_closure"]
    assert isinstance(closure, dict)
    selection_policy = payload["selection_policy"]
    assert isinstance(selection_policy, dict)
    candidate_rows = payload["candidate_compatibility_audit"]
    assert isinstance(candidate_rows, list)
    compact_candidate_rows = []
    for row in candidate_rows:
        assert isinstance(row, dict)
        compact_candidate_rows.append(
            {
                "candidate_id": row["candidate_id"],
                "frozen_registry_selection_eligibility": row[
                    "frozen_registry_selection_eligibility"
                ],
                "current_historical_only_execution_eligibility": row[
                    "current_historical_only_execution_eligibility"
                ],
                "historical_only_input_compatible": row["historical_only_input_compatible"],
                "historical_only_execution_compatible": row["historical_only_execution_compatible"],
                "currently_runnable_under_v4": row["currently_runnable_under_v4"],
                "structurally_selectable_under_v4": row["structurally_selectable_under_v4"],
                "parameter_reaches_prediction_math": row["parameter_reaches_prediction_math"],
                "parameter_change_can_change_prediction": row[
                    "parameter_change_can_change_prediction"
                ],
                "reason_code": row["reason_code"],
                "secondary_reason_codes": row["secondary_reason_codes"],
                "implementation_blocker": row["implementation_blocker"],
                "structural_selection_blocker": row["structural_selection_blocker"],
                "requires_policy_amendment": row["requires_policy_amendment"],
            }
        )
    return {
        "task_id": payload["task_id"],
        "experiment_plan": {
            "version": payload["experiment_plan_version"],
            "hash": payload["experiment_plan_hash"],
        },
        "guardrail_policy": {
            "version": payload["guardrail_policy_version"],
            "hash": payload["guardrail_policy_hash"],
        },
        "v2_current_execution_eligibility": payload["v2_current_execution_eligibility"],
        "frozen_registry_selection_eligibility": payload["frozen_registry_selection_eligibility"],
        "candidate_compatibility_audit": compact_candidate_rows,
        "current_v4_runnability": closure["candidate_runnability"],
        "next_executable_candidate": payload["next_executable_candidate"],
        "current_frozen_plan_has_no_remaining_executable_candidate": closure[
            "current_frozen_plan_has_no_remaining_executable_candidate"
        ],
        "c02_quantile_effect_proof": selection_policy["c02_quantile_effect_proof"],
        "c05_canonical_path_audit": payload["c05_canonical_path_audit"],
        "c07_canonical_path_audit": payload["c07_canonical_path_audit"],
        "budget": payload["budget"],
    }


__all__ = [
    "AUDIT_CANDIDATE_IDS",
    "C02_ID",
    "C02_PATH_BLOCKER",
    "C02_STRUCTURAL_BLOCKER",
    "C04_EXHAUSTED_EVIDENCE",
    "C05_BLOCKER",
    "C05_ID",
    "C07_BLOCKER",
    "C07_ID",
    "DURABLE_BUDGET_READBACK_AVAILABLE",
    "FrozenS4Closure",
    "LAST_ACCEPTED_BUDGET_DELTA",
    "LAST_ACCEPTED_CANONICAL_STARTED_COUNT",
    "LAST_ACCEPTED_DURABLE_BUDGET_EVIDENCE_PATH",
    "LAST_ACCEPTED_DURABLE_BUDGET_EVIDENCE_SHA256",
    "LAST_ACCEPTED_EFFECTIVE_CONSUMED",
    "LAST_ACCEPTED_REMAINING",
    "LEGACY_RECONCILED_VALIDATION_DEBIT",
    "NO_REMAINING_CANDIDATE_BLOCKER",
    "RemainingCandidateViability",
    "SOURCE_002_IDENTITY",
    "SOURCE_002_TRAIN_ROWS",
    "SOURCE_002_TRAIN_SHA256",
    "SOURCE_002_VALIDATION_ROWS",
    "SOURCE_002_VALIDATION_SHA256",
    "TASK_ID",
    "V4_GUARDRAIL_POLICY_HASH",
    "V4_GUARDRAIL_POLICY_VERSION",
    "build_frozen_s4_closure",
    "build_machine_derived_audit_payload",
    "build_remaining_candidate_audit_payload",
    "build_remaining_candidate_viability_audit",
    "c02_quantile_effect_proof",
]


# Immutable SOURCE-002 aliases are imported from the canonical historical
# dataset module rather than duplicated here.
SOURCE_002_IDENTITY = SOURCE_002_MATERIALIZED_DATASET_IDENTITY_SHA256
SOURCE_002_TRAIN_ROWS = OFFICIAL_TRAIN_ROW_COUNT
SOURCE_002_TRAIN_SHA256 = OFFICIAL_TRAIN_CONTENT_SHA256
SOURCE_002_VALIDATION_ROWS = OFFICIAL_VALIDATION_ROW_COUNT
SOURCE_002_VALIDATION_SHA256 = OFFICIAL_VALIDATION_CONTENT_SHA256
LEGACY_RECONCILED_VALIDATION_DEBIT = V2_LEGACY_RECONCILED_VALIDATION_DEBIT
