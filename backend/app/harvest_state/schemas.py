from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from backend.app.harvest_state.canonical import parse_decimal
from backend.app.harvest_state.enums import (
    CANONICAL_FORECAST_QUANTILES,
    CapacityInputMode,
    CapacityPoolGrain,
    ForecastQuantile,
    ParameterCode,
    SourceRefType,
    WeatherCombinationMethod,
)

BusinessDecimal = Annotated[Decimal, BeforeValidator(parse_decimal)]
NonNegativeBusinessDecimal = Annotated[
    Decimal,
    BeforeValidator(parse_decimal),
    Field(ge=Decimal("0")),
]
RatioDecimal = Annotated[
    Decimal,
    BeforeValidator(parse_decimal),
    Field(ge=Decimal("0"), le=Decimal("1")),
]


class _BaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CapacityPoolMember(_BaseModel):
    farm_id: int
    subfarm_id: int | None
    variety_id: int


class CapacityPoolInput(_BaseModel):
    capacity_pool_id: str = Field(min_length=1)
    capacity_pool_grain: CapacityPoolGrain
    members: list[CapacityPoolMember]

    @field_validator("members")
    @classmethod
    def _members_not_empty(cls, value: list[CapacityPoolMember]) -> list[CapacityPoolMember]:
        if not value:
            raise ValueError("capacity pool members must not be empty")
        return value


class WeatherFeatureBand(_BaseModel):
    lower_bound: BusinessDecimal
    lower_inclusive: bool
    upper_bound: BusinessDecimal
    upper_inclusive: bool
    multiplier: RatioDecimal


class WeatherFeatureRule(_BaseModel):
    feature_id: str = Field(min_length=1)
    bands: list[WeatherFeatureBand]

    @field_validator("bands")
    @classmethod
    def _bands_not_empty(cls, value: list[WeatherFeatureBand]) -> list[WeatherFeatureBand]:
        if not value:
            raise ValueError("weather feature rule bands must not be empty")
        return value


class WeatherEfficiencyRuleConfig(_BaseModel):
    version: str = Field(min_length=1)
    required_feature_ids: list[str]
    feature_rules: list[WeatherFeatureRule]
    combination_method: WeatherCombinationMethod
    minimum_ratio: RatioDecimal
    maximum_ratio: RatioDecimal
    missing_feature_policy: Literal["BLOCK"]

    @model_validator(mode="after")
    def _validate_bounds(self) -> WeatherEfficiencyRuleConfig:
        if self.minimum_ratio > self.maximum_ratio:
            raise ValueError("minimum_ratio must be <= maximum_ratio")
        feature_ids = [item.feature_id for item in self.feature_rules]
        if sorted(feature_ids) != sorted(self.required_feature_ids):
            raise ValueError("feature_rules must exactly cover required_feature_ids")
        return self


class ParameterSourceRef(_BaseModel):
    source_ref_type: Literal["PARAMETER_SOURCE"] = "PARAMETER_SOURCE"
    source_ref_schema_version: Literal["task9a-source-ref-v1"] = "task9a-source-ref-v1"
    parameter_code: ParameterCode
    source_system: str = Field(min_length=1)
    source_record_key: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    source_row_hash: str = Field(min_length=1)
    available_at: date
    as_of_date: date


class Task8PredictionSourceRef(_BaseModel):
    source_ref_type: Literal["TASK8_DAILY_PREDICTION"] = "TASK8_DAILY_PREDICTION"
    source_ref_schema_version: Literal["task9a-source-ref-v1"] = "task9a-source-ref-v1"
    maturity_model_run_id: int
    maturity_model_version: str = Field(min_length=1)
    maturity_model_config_hash: str = Field(min_length=1)
    maturity_model_source_signature: str = Field(min_length=1)
    maturity_model_artifact_id: int
    maturity_model_artifact_hash: str = Field(min_length=1)
    maturity_forecast_run_id: int
    maturity_forecast_source_signature: str = Field(min_length=1)
    maturity_forecast_as_of_date: date
    maturity_forecast_prediction_start_date: date
    maturity_forecast_prediction_end_date: date
    maturity_daily_prediction_id: int
    prediction_date: date
    forecast_quantile: ForecastQuantile
    source_quantity_kg: NonNegativeBusinessDecimal
    plan_id: int
    location_reference_id: int
    weather_mapping_id: int | None
    base_temperature_search_run_id: int | None


class InitialInventorySourceRef(_BaseModel):
    source_ref_type: Literal["INITIAL_INVENTORY_SNAPSHOT"] = "INITIAL_INVENTORY_SNAPSHOT"
    source_ref_schema_version: Literal["task9a-source-ref-v1"] = "task9a-source-ref-v1"
    source_system: str = Field(min_length=1)
    source_record_key: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    source_row_hash: str = Field(min_length=1)
    available_at: date
    as_of_date: date


SourceRef = Annotated[
    Task8PredictionSourceRef | InitialInventorySourceRef | ParameterSourceRef,
    Field(discriminator="source_ref_type"),
]


class Task8DailyPredictionInput(_BaseModel):
    prediction_date: date
    farm_id: int
    subfarm_id: int | None
    variety_id: int
    source_ref: Task8PredictionSourceRef


class InitialInventoryCohortInput(_BaseModel):
    cohort_date: date
    farm_id: int
    subfarm_id: int | None
    variety_id: int
    remaining_quantity_kg: NonNegativeBusinessDecimal
    source_ref: InitialInventorySourceRef
    forecast_quantile: ForecastQuantile
    stable_cohort_key: str
    stable_cohort_key_schema_version: Literal["task9a-cohort-key-v1"] = "task9a-cohort-key-v1"


class MatureInventoryLossInput(_BaseModel):
    state_date: date
    capacity_pool_id: str = Field(min_length=1)
    forecast_quantile: ForecastQuantile
    mature_inventory_loss_quantity_kg: NonNegativeBusinessDecimal
    source_ref: ParameterSourceRef


class DailyWeatherFeatureInput(_BaseModel):
    capacity_date: date
    capacity_pool_id: str = Field(min_length=1)
    feature_id: str = Field(min_length=1)
    value: BusinessDecimal
    source_ref: ParameterSourceRef


class DailyCapacityInput(_BaseModel):
    capacity_date: date
    capacity_pool_id: str = Field(min_length=1)
    capacity_input_mode: CapacityInputMode
    planned_picker_count: NonNegativeBusinessDecimal | None = None
    kg_per_person_per_day: NonNegativeBusinessDecimal | None = None
    direct_nominal_capacity_kg_per_day: NonNegativeBusinessDecimal | None = None
    labor_availability_ratio: RatioDecimal
    operational_efficiency_ratio: RatioDecimal
    capacity_parameter_source_refs: list[ParameterSourceRef]


class RunResolvedParameters(_BaseModel):
    forecast_start_date: date
    forecast_end_date: date
    forecast_quantiles: list[ForecastQuantile]
    destination_factory_id: int
    farm_timezone: str
    destination_factory_timezone: str
    harvest_bucket_anchor_local_time: time
    harvest_to_arrival_lag_days: int
    holiday_calendar_version: str
    holiday_calendar_hash: str
    weather_rule_version: str
    weather_rule_config_hash: str
    decimal_precision: int
    quantity_scale: str
    ratio_scale: str
    rounding_mode: str
    source_ref_schema_version: str
    stable_cohort_key_schema_version: str
    result_hash_schema_version: str


class DailyPoolResolvedParameters(_BaseModel):
    capacity_date: date
    capacity_pool_id: str
    capacity_pool_grain: CapacityPoolGrain
    capacity_pool_membership_hash: str
    capacity_input_mode: CapacityInputMode
    planned_picker_count: NonNegativeBusinessDecimal | None = None
    kg_per_person_per_day: NonNegativeBusinessDecimal | None = None
    direct_nominal_capacity_kg_per_day: NonNegativeBusinessDecimal | None = None
    resolved_nominal_capacity_kg_per_day: NonNegativeBusinessDecimal
    labor_availability_ratio: RatioDecimal
    weather_harvest_efficiency_ratio: RatioDecimal
    operational_efficiency_ratio: RatioDecimal
    resolved_effective_capacity_kg_per_day: NonNegativeBusinessDecimal
    holiday_applied: bool
    capacity_parameter_source_refs: list[ParameterSourceRef]
    weather_feature_source_refs: list[ParameterSourceRef]


class ResolvedParameterSnapshot(_BaseModel):
    schema_version: Literal["task9a-resolved-parameters-v1"] = "task9a-resolved-parameters-v1"
    run_parameters: RunResolvedParameters
    daily_pool_parameters: list[DailyPoolResolvedParameters]


class DailyPoolStateRow(_BaseModel):
    state_date: date
    forecast_quantile: ForecastQuantile
    capacity_pool_id: str
    capacity_pool_grain: CapacityPoolGrain
    capacity_pool_membership_hash: str
    capacity_input_mode: CapacityInputMode
    opening_mature_inventory_kg: NonNegativeBusinessDecimal
    natural_maturity_supply_kg: NonNegativeBusinessDecimal
    available_mature_quantity_kg: NonNegativeBusinessDecimal
    mature_inventory_loss_quantity_kg: NonNegativeBusinessDecimal
    harvestable_mature_quantity_kg: NonNegativeBusinessDecimal
    nominal_harvest_capacity_kg_per_day: NonNegativeBusinessDecimal
    labor_availability_ratio: RatioDecimal
    weather_harvest_efficiency_ratio: RatioDecimal
    operational_efficiency_ratio: RatioDecimal
    effective_harvest_capacity_kg_per_day: NonNegativeBusinessDecimal
    effective_capacity_for_day_kg: NonNegativeBusinessDecimal
    harvested_quantity_kg: NonNegativeBusinessDecimal
    closing_mature_inventory_kg: NonNegativeBusinessDecimal
    unharvested_backlog_kg: NonNegativeBusinessDecimal
    arrival_quantity_kg: NonNegativeBusinessDecimal
    opening_cohort_count: int
    closing_cohort_count: int
    member_count: int
    mass_balance_passed: bool
    capacity_constraint_passed: bool
    continuity_passed: bool
    parameter_source_ref_hashes: list[str]
    cohort_source_ref_hashes: list[str]


class DailyMemberStateRow(_BaseModel):
    state_date: date
    forecast_quantile: ForecastQuantile
    capacity_pool_id: str
    capacity_pool_grain: CapacityPoolGrain
    capacity_pool_membership_hash: str
    farm_id: int
    subfarm_id: int | None
    variety_id: int
    destination_factory_id: int
    opening_mature_inventory_kg: NonNegativeBusinessDecimal
    natural_maturity_supply_kg: NonNegativeBusinessDecimal
    available_mature_quantity_kg: NonNegativeBusinessDecimal
    mature_inventory_loss_quantity_kg: NonNegativeBusinessDecimal
    harvestable_mature_quantity_kg: NonNegativeBusinessDecimal
    allocated_harvest_capacity_kg: NonNegativeBusinessDecimal
    harvested_quantity_kg: NonNegativeBusinessDecimal
    closing_mature_inventory_kg: NonNegativeBusinessDecimal
    unharvested_backlog_kg: NonNegativeBusinessDecimal
    arrival_quantity_kg: NonNegativeBusinessDecimal
    opening_cohort_count: int
    closing_cohort_count: int
    cohort_source_ref_hashes: list[str]


class CohortTransitionRow(_BaseModel):
    state_date: date
    forecast_quantile: ForecastQuantile
    capacity_pool_id: str
    farm_id: int
    subfarm_id: int | None
    variety_id: int
    destination_factory_id: int
    stable_cohort_key: str
    stable_cohort_key_schema_version: Literal["task9a-cohort-key-v1"] = "task9a-cohort-key-v1"
    source_ref_hash: str
    cohort_date: date
    opening_quantity_kg: NonNegativeBusinessDecimal
    new_supply_quantity_kg: NonNegativeBusinessDecimal
    quantity_before_loss_kg: NonNegativeBusinessDecimal
    mature_inventory_loss_quantity_kg: NonNegativeBusinessDecimal
    quantity_before_harvest_kg: NonNegativeBusinessDecimal
    harvested_quantity_kg: NonNegativeBusinessDecimal
    closing_quantity_kg: NonNegativeBusinessDecimal
    harvest_anchor_at: datetime | None = None
    arrival_at: datetime | None = None
    arrival_local_date: date | None = None
    arrival_quantity_kg: NonNegativeBusinessDecimal


class FutureArrivalScheduleRow(_BaseModel):
    destination_factory_id: int
    arrival_local_date: date
    variety_id: int
    forecast_quantile: ForecastQuantile
    quantity_kg: NonNegativeBusinessDecimal


class SourceRefCatalogEntry(_BaseModel):
    source_ref_hash: str
    source_ref_type: SourceRefType
    source_ref_schema_version: str
    source_ref_payload: dict[str, Any]


class Task9ARequest(_BaseModel):
    as_of_date: date
    forecast_start_date: date
    forecast_end_date: date
    forecast_quantiles: list[ForecastQuantile]
    destination_factory_id: int
    farm_timezone: str
    destination_factory_timezone: str
    harvest_bucket_anchor_local_time: time
    harvest_to_arrival_lag_days: int
    holiday_calendar_version: str
    holiday_calendar_hash: str
    holiday_dates: list[date]
    weather_rule_config: WeatherEfficiencyRuleConfig
    run_parameter_source_refs: list[ParameterSourceRef]
    capacity_pools: list[CapacityPoolInput]
    daily_capacity_inputs: list[DailyCapacityInput]
    daily_weather_features: list[DailyWeatherFeatureInput]
    task8_daily_predictions: list[Task8DailyPredictionInput]
    initial_inventory_cohorts: list[InitialInventoryCohortInput] | None = None
    initial_opening_mature_inventory_kg: NonNegativeBusinessDecimal | None = None
    mature_inventory_loss_inputs: list[MatureInventoryLossInput]

    @field_validator("forecast_quantiles")
    @classmethod
    def _validate_quantiles(
        cls,
        value: list[ForecastQuantile],
    ) -> list[ForecastQuantile]:
        if tuple(value) != CANONICAL_FORECAST_QUANTILES:
            raise ValueError("forecast_quantiles must be [P50, P80, P90]")
        return value

    @model_validator(mode="after")
    def _validate_dates(self) -> Task9ARequest:
        if self.forecast_end_date < self.forecast_start_date:
            raise ValueError("forecast_end_date must be >= forecast_start_date")
        if self.harvest_to_arrival_lag_days < 0:
            raise ValueError("harvest_to_arrival_lag_days must be >= 0")
        return self


class Task9ACompletedOutput(_BaseModel):
    output_schema_version: Literal["task9a-output-v1"] = "task9a-output-v1"
    status: Literal["completed"] = "completed"
    forecast_start_date: date
    forecast_end_date: date
    forecast_quantiles: list[ForecastQuantile]
    input_snapshot: dict[str, Any]
    resolved_parameter_snapshot: ResolvedParameterSnapshot
    daily_pool_state_rows: list[DailyPoolStateRow]
    daily_member_state_rows: list[DailyMemberStateRow]
    cohort_transition_rows: list[CohortTransitionRow]
    future_arrival_schedule: list[FutureArrivalScheduleRow]
    source_ref_catalog: list[SourceRefCatalogEntry]
    warnings: list[str]
    blockers: list[str]
    mass_balance_result: dict[str, Any]
    continuity_result: dict[str, Any]
    config_hash: str
    result_hash: str


class Task9ABlockedOutput(_BaseModel):
    output_schema_version: Literal["task9a-output-v1"] = "task9a-output-v1"
    status: Literal["blocked"] = "blocked"
    input_snapshot: dict[str, Any]
    resolved_parameter_snapshot: ResolvedParameterSnapshot | None = None
    daily_pool_state_rows: list[DailyPoolStateRow] = Field(default_factory=list)
    daily_member_state_rows: list[DailyMemberStateRow] = Field(default_factory=list)
    cohort_transition_rows: list[CohortTransitionRow] = Field(default_factory=list)
    future_arrival_schedule: list[FutureArrivalScheduleRow] = Field(default_factory=list)
    source_ref_catalog: list[SourceRefCatalogEntry] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    blockers: list[str]
    config_hash: str
    result_hash: str
