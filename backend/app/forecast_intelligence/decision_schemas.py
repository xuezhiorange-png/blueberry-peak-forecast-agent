"""S2 transport contracts: strict strings at input, typed frozen-engine output."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, StrictInt, StrictStr, field_validator

from backend.app.forecast_intelligence.read_schemas import (
    AuthorityIdentity,
    ForecastIdentity,
    Hash,
    HierarchyIdentity,
    Identifier,
    ReadModel,
)

BODY_LIMIT = 131072
SCENARIO_LIMIT = 20
DAY_LIMIT = 15
PlanningLevel = Literal["POINT", "UPPER_PLANNING_BOUND_80", "UPPER_PLANNING_BOUND_90"]
Quantity = Annotated[StrictStr, Field(max_length=64, pattern=r"^[0-9]+(?:\.[0-9]+)?$")]


class CostSelection(ReadModel):
    cost_contract_id: Identifier
    expected_cost_contract_hash: Hash


class DecisionSelection(CostSelection):
    forecast_selection: ForecastIdentity
    expected_source_result_hash: Hash
    planning_level: PlanningLevel


class DirectCapacity(ReadModel):
    date: date
    capacity_mode: Literal["DIRECT"]
    daily_handling_capacity_kg: Quantity
    buffer_handling_capacity_kg: Quantity | None = None


class WorkforceCapacity(ReadModel):
    date: date
    capacity_mode: Literal["WORKFORCE_DERIVED"]
    workforce_count: Annotated[StrictInt, Field(ge=0, le=1000000)]
    productivity_kg_per_person_day: Quantity
    buffer_handling_capacity_kg: Quantity | None = None


CapacityInput = Annotated[DirectCapacity | WorkforceCapacity, Field(discriminator="capacity_mode")]


class ScenarioInput(ReadModel):
    scenario_id: Identifier
    scenario_version: Identifier
    capacity_rows: Annotated[list[CapacityInput], Field(min_length=1, max_length=DAY_LIMIT)]

    @field_validator("scenario_id", "scenario_version")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("SCENARIO_SCHEMA_INVALID")
        return value


class SimulationRequest(DecisionSelection, ScenarioInput):
    pass


class ComparisonRequest(DecisionSelection):
    scenarios: Annotated[list[ScenarioInput], Field(min_length=2, max_length=SCENARIO_LIMIT)]


class CostContractView(ReadModel):
    contract_id: str
    policy_version: str
    contract_version: str
    authority_type: Literal["EXPLICIT_SYNTHETIC_SCENARIO"]
    authority_reference: str
    c_under_per_kg: str
    c_over_per_kg: str
    loss_unit: Literal["SYNTHETIC_LOSS_UNIT"]
    synthetic: Literal[True]
    canonical_company_cost: Literal[False]
    contract_hash: Hash


class BusinessLossExposure(ReadModel):
    cost_contract: CostContractView
    formula: str
    s5_semantics: Literal["ACTUAL_VS_FORECAST_LOSS"] = "ACTUAL_VS_FORECAST_LOSS"
    simulation_semantics: Literal["ASYMMETRIC_PLANNING_GAP_LOSS"] = "ASYMMETRIC_PLANNING_GAP_LOSS"
    total_business_loss: None = None
    loss_amount_status: Literal["NOT_COMPUTED_NO_SCENARIO"] = "NOT_COMPUTED_NO_SCENARIO"


class DailySimulationResult(ReadModel):
    date: date
    capacity_mode: Literal["DIRECT", "WORKFORCE_DERIVED"]
    workforce_count: int | None
    productivity_kg_per_person_day: str | None
    buffer_supplied: bool
    buffer_handling_capacity_kg: str
    daily_handling_capacity_kg: str
    planning_level: PlanningLevel
    planning_demand_kg: str
    effective_capacity_kg: str
    opening_backlog_kg: str
    workload_kg: str
    processed_kg: str
    closing_backlog_kg: str
    daily_overload_kg: str
    daily_over_capacity_kg: str
    under_capacity_kg: str
    over_capacity_kg: str
    under_capacity_loss: str
    over_capacity_loss: str
    scenario_business_loss: str
    capacity_utilization_numerator_kg: str
    capacity_utilization_denominator_kg: str
    capacity_utilization_decimal: str | None
    capacity_utilization_precision: Literal[50]
    capacity_utilization_rounding_mode: Literal["ROUND_HALF_EVEN"]
    capacity_utilization_rounding_applied: bool
    capacity_utilization_status: Literal["COMPUTABLE", "NOT_COMPUTABLE_ZERO_CAPACITY"]
    row_hash: Hash


class SimulationResult(ReadModel):
    saved_forecast_hash: Hash
    forecast_curve_hash: Hash
    forecast_source_hash: Hash
    forecast_origin: str
    hierarchy_level: Literal["BASE", "REGION", "COMPANY"]
    hierarchy_entity_id: str
    hierarchy_authority_hash: Hash
    planning_level: PlanningLevel
    cost_contract_hash: Hash
    loss_unit: Literal["SYNTHETIC_LOSS_UNIT"]
    dates: list[date]
    initial_backlog_kg: Literal["0"]
    backlog_policy_version: str
    scenario_id: str
    scenario_hash: Hash
    scenario_status: Literal["COMPLETE"]
    loss_semantics: Literal["ASYMMETRIC_PLANNING_GAP_LOSS"]
    decision_evidence_class: Literal["SYNTHETIC_DECISION_LOSS"]
    forecast_start_date: date
    forecast_end_date: date
    day_count: int
    overload_dates: list[date]
    backlog_dates: list[date]
    overload_day_count: int
    backlog_day_count: int
    cumulative_shortfall_kg: str
    max_backlog_kg: str
    ending_backlog_kg: str
    total_planning_demand_kg: str
    total_base_handling_capacity_kg: str
    total_buffer_capacity_kg: str
    total_effective_capacity_kg: str
    total_processed_kg: str
    under_capacity_kg: str
    over_capacity_kg: str
    under_capacity_loss: str
    over_capacity_loss: str
    total_business_loss: str
    daily_rows: list[DailySimulationResult]
    aggregate_capacity_utilization_numerator_kg: str
    aggregate_capacity_utilization_denominator_kg: str
    aggregate_capacity_utilization_decimal: str | None
    aggregate_capacity_utilization_precision: Literal[50]
    aggregate_capacity_utilization_rounding_mode: Literal["ROUND_HALF_EVEN"]
    aggregate_capacity_utilization_rounding_applied: bool
    aggregate_capacity_utilization_status: Literal["COMPUTABLE", "NOT_COMPUTABLE_ZERO_CAPACITY"]
    result_hash: Hash


class ScenarioRank(ReadModel):
    scenario_id: str
    scenario_hash: Hash
    result_hash: Hash
    scenario_rank: int


class ComparisonResult(ReadModel):
    scenario_comparison_status: Literal["COMPARABLE"]
    comparison_authority_hash: Hash
    ranking_semantics: Literal["DESCRIPTIVE_ORDER_UNDER_GIVEN_INPUTS_AND_COST_CONTRACT"]
    rankings: list[ScenarioRank]
    comparison_hash: Hash


class ComparisonData(ReadModel):
    comparison: ComparisonResult
    scenario_results: list[SimulationResult]


class DecisionResponse[T: ReadModel](ReadModel):
    schema_version: Literal["V0_17_S2_DECISION_SUPPORT_API_R1"] = "V0_17_S2_DECISION_SUPPORT_API_R1"
    capability: Literal["BUSINESS_LOSS_EXPOSURE", "SIMULATE_CAPACITY", "COMPARE_CAPACITY_SCENARIOS"]
    status: Literal["READY", "PARTIAL", "NOT_AVAILABLE"]
    forecast_identity: ForecastIdentity | None = None
    hierarchy_identity: HierarchyIdentity | None = None
    authority_identity: AuthorityIdentity | None = None
    source_result_hash: Hash | None = None
    source_rerun_of_run_id: int | None = None
    source_read_projection_hash: Hash | None = None
    adapter_policy_version: Literal["V0_17_S2_SAVED_FORECAST_DECISION_ADAPTER_R1"] = (
        "V0_17_S2_SAVED_FORECAST_DECISION_ADAPTER_R1"
    )
    adapter_authority_hash: Hash | None = None
    adapter_authority_kind: str | None = None
    adapter_authority_binding: dict[str, str | int] | None = None
    adapter_saved_forecast_hash: Hash | None = None
    origin_date: date | None = None
    origin_anchor: str | None = None
    origin_anchor_policy: Literal["V0_17_S2_SHANGHAI_DATE_ANCHOR_R1"] = (
        "V0_17_S2_SHANGHAI_DATE_ANCHOR_R1"
    )
    date_anchor_not_issuance_timestamp: Literal[True] = True
    data_completeness: str | None = None
    available_day_count: int | None = None
    planning_level: PlanningLevel | None = None
    cost_contract_id: str
    cost_contract_hash: Hash
    loss_unit: Literal["SYNTHETIC_LOSS_UNIT"] = "SYNTHETIC_LOSS_UNIT"
    synthetic: Literal[True] = True
    canonical_company_cost: Literal[False] = False
    real_roi_validated: Literal[False] = False
    point_forecast_is_proven_p50: Literal[False] = False
    upper_planning_bound_is_quantile: Literal[False] = False
    fine_grained_entity_authorization_established: Literal[False] = False
    engine_policy_versions: dict[str, str]
    engine_result_hash: Hash | None = None
    data: T | None = None
    unavailable_reason: str | None = None
    projection_hash: Hash


def decimal_input(value: str) -> Decimal:
    # Schema admits only bounded fixed-point strings, never native floats/exponents.
    return Decimal(value)
