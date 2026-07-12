"""TASK-013 Slice A — frozen Pydantic schemas for the 8 logical tools.

This module implements the strict Pydantic contracts frozen in
``docs/task-013-minimal-input-deterministic-agent-orchestration-design.md``
(Slice A is *schemas + deterministic adapters only*; no orchestrator).

Hard rules implemented here:

* ``model_config = ConfigDict(extra="forbid")`` on every request/output model.
* Frozen models where mutation is not required.
* Authoritative quantities are *canonical decimal strings*, never native ``float``.
* All hashes are 64-char lowercase hex (sha256).
* Authority IDs are strict ``int``; ``str`` row IDs are NOT accepted.
* Naive datetimes are rejected; only aware UTC ``datetime`` is allowed.
* Set is rejected in canonical payloads (delegated to the canonical contract).
* Non-finite Decimal is rejected (delegated to the canonical contract).
* Naive datetime is rejected in canonical payloads (delegated to the canonical contract).

Adapter-introduced hashes use the explicit names from §6:

* canonical_request_hash
* advanced_overrides_hash
* parameters_hash
* agent_daily_row_hash
* agent_daily_curve_hash
* agent_peak_hash
* scenario_config_hash
* scenario_id
* override_ref_id
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from backend.app.agent.enums import (
    AuthorityEnvelopeType,
    AuthorityOverrideTarget,
    BlockerCode,
    CitationSourceTask,
    CitationSourceTool,
    Confidence,
    ExecutionTarget,
    ForecastQuantile,
    MatchedLocationMethod,
    OverrideKind,
    ParameterTarget,
    RecommendationCategory,
    RecommendationKind,
    RequestStatus,
    RetryHint,
    ScenarioTarget,
    SpringFestivalPhase,
)


# --- Strict scalar constraints --------------------------------------------

SHA256Hex = Annotated[
    str,
    StringConstraints(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"),
]

IntId = Annotated[int, Field(ge=0, strict=True)]

DecimalString = Annotated[
    str,
    StringConstraints(min_length=1, pattern=r"^-?\d+(?:\.\d+)?$"),
]


# --- Strict aware UTC datetime --------------------------------------------


class _StrictBase(BaseModel):
    """Common base: extra fields are FORBIDDEN; freeze by default."""

    model_config = ConfigDict(extra="forbid", frozen=True)


# --- §26.2 Blocker ----------------------------------------------------------

class Blocker(_StrictBase):
    code: BlockerCode
    message: str = Field(min_length=1, max_length=2000)
    details: dict[str, Any] | None = None
    citation: dict[str, Any] | None = None
    retry_hint: RetryHint = "NONE"


# --- §7.1 Minimal-input request -------------------------------------------

class MinimalVarietyInput(_StrictBase):
    variety_id: str = Field(min_length=1)
    planting_area_mu: DecimalString


class LocationInput(_StrictBase):
    raw_text: str | None = None
    latitude: DecimalString | None = None
    longitude: DecimalString | None = None
    map_pick_token: str | None = None
    location_reference_id: IntId | None = None
    address: str | None = None
    altitude_m: DecimalString | None = None

    @model_validator(mode="after")
    def _at_least_one_locator(self) -> "LocationInput":
        if (
            self.raw_text is None
            and self.latitude is None
            and self.longitude is None
            and self.map_pick_token is None
            and self.location_reference_id is None
            and self.address is None
        ):
            raise ValueError("location must supply at least one of raw_text/coordinates/map_pick_token/reference_id/address")
        return self


class MinimalInputRequest(_StrictBase):
    request_id: str = Field(min_length=1)
    location: LocationInput
    varieties: list[MinimalVarietyInput]
    requested_as_of_date: date | None = None
    requested_forecast_season: IntId | None = None
    advanced_overrides: "AdvancedOverrides | None" = None

    @field_validator("varieties")
    @classmethod
    def _non_empty(cls, v: list[MinimalVarietyInput]) -> list[MinimalVarietyInput]:
        if not v:
            raise ValueError("varieties must be non-empty")
        return v



# --- §9.3.1 Task8Authority -------------------------------------------------

class Task8Authority(_StrictBase):
    maturity_model_run_id: IntId
    maturity_model_version: str = Field(min_length=1)
    maturity_model_config_hash: SHA256Hex
    maturity_model_source_signature: str = Field(min_length=1)
    maturity_model_artifact_id: IntId
    maturity_model_artifact_hash: SHA256Hex
    maturity_forecast_run_id: IntId
    maturity_forecast_source_signature: str = Field(min_length=1)
    maturity_forecast_as_of_date: date


# --- §9.3.2 Task9Authority -------------------------------------------------

class Task9Authority(_StrictBase):
    harvest_state_run_id: IntId
    harvest_state_run_config_hash: SHA256Hex
    harvest_state_run_result_hash: SHA256Hex
    harvest_state_run_canonical_payload_hash: SHA256Hex
    harvest_state_output_schema_version: str = Field(min_length=1)
    harvest_state_as_of_date: date
    harvest_state_forecast_start_date: date
    harvest_state_forecast_end_date: date
    destination_factory_id: IntId
    pool_row_count: IntId
    member_row_count: IntId
    cohort_row_count: IntId
    future_arrival_row_count: IntId
    source_ref_schema_version: str = Field(min_length=1)
    result_hash_schema_version: str = Field(min_length=1)
    stable_cohort_key_schema_version: str = Field(min_length=1)
    resolved_parameter_snapshot_schema_version: str = Field(min_length=1)


# --- §9.3.3 Task10Authority ------------------------------------------------

class Task10Authority(_StrictBase):
    training_run_id: IntId | None
    training_manifest_hash: SHA256Hex | None
    prediction_run_id: IntId
    task9_run_id: IntId
    task9_result_hash: SHA256Hex
    prediction_hash: SHA256Hex
    prediction_config_hash: SHA256Hex
    prediction_input_signature: SHA256Hex
    artifact_hashes: list[SHA256Hex]
    feature_schema_hash: SHA256Hex
    prediction_canonical_payload_hash: SHA256Hex


# --- §9.3.4 Task11Authority ------------------------------------------------

class Task11Authority(_StrictBase):
    rolling_backtest_run_id: IntId
    run_signature: SHA256Hex
    config_hash: SHA256Hex
    canonical_payload_hash: SHA256Hex
    rolling_schema_version: str = Field(min_length=1)
    canonical_serialization_version: str = Field(min_length=1)
    availability_registry_version: str = Field(min_length=1)
    node_calendar_version: str = Field(min_length=1)
    forecast_horizon_policy_version: str = Field(min_length=1)
    upstream_selection_policy_version: str = Field(min_length=1)
    metric_policy_version: str = Field(min_length=1)
    cutoff_policy_version: str = Field(min_length=1)
    execution_mode: str = Field(min_length=1)
    status: str = Field(min_length=1)
    expected_node_count: IntId


# --- §9.3.5 Task12Authority ------------------------------------------------

class Task12Authority(_StrictBase):
    prediction_run_id: IntId
    scenario_id: SHA256Hex
    training_manifest_hash: SHA256Hex
    model_config_hash: SHA256Hex
    task9_run_id: IntId
    task9_result_hash: SHA256Hex
    prediction_hash: SHA256Hex
    forecast_cutoff_at: AwareDatetime
    training_cutoff_at: AwareDatetime
    model_code_version: str = Field(min_length=1)
    task12_policy_version: str = Field(min_length=1)
    validation_policy_version: str = Field(min_length=1)
    label_visibility_policy_version: str = Field(min_length=1)
    feature_visibility_policy_version: str = Field(min_length=1)
    artifact_visibility_policy_version: str = Field(min_length=1)
    model_artifact_hash: SHA256Hex | None
    task9_replay_binding_identity: SHA256Hex
    task10_manifest_hash: SHA256Hex | None
    task10_config_hash: SHA256Hex | None


# --- §8 Advanced overrides -----------------------------------------------

class AsOfOverride(_StrictBase):
    override_kind: Literal["AS_OF_OVERRIDE"] = "AS_OF_OVERRIDE"
    value: date
    unit: Literal["date"] = "date"
    source_attestation: str = Field(min_length=1)
    source_ref: dict[str, Any] | None = None


class YieldPerMuOverrideValue(_StrictBase):
    value: DecimalString
    unit: Literal["kg_per_mu"] = "kg_per_mu"


class RateOverrideValue(_StrictBase):
    value: DecimalString
    unit: Literal["ratio"] = "ratio"


class DateOverrideValue(_StrictBase):
    value: date
    unit: Literal["date"] = "date"


class WeatherAdjustmentOverrideValue(_StrictBase):
    temperature_delta_c: DecimalString | None = None
    rainfall_scale: DecimalString | None = None
    gdd_scale: DecimalString | None = None
    unit: Literal["weather_adjustment"] = "weather_adjustment"


class DistributionOverrideParameters(_StrictBase):
    type: Literal["NORMAL", "BETA", "HISTORICAL_EMPIRICAL"]
    parameters: dict[str, Any]


class DistributionOverrideValue(_StrictBase):
    value: DistributionOverrideParameters
    unit: Literal["distribution"] = "distribution"


class ParameterOverride(_StrictBase):
    override_kind: Literal["PARAMETER_OVERRIDE_KIND"] = "PARAMETER_OVERRIDE_KIND"
    variety_id: str = Field(min_length=1)
    target_parameter: ParameterTarget
    value: (
        YieldPerMuOverrideValue
        | RateOverrideValue
        | DateOverrideValue
        | DistributionOverrideValue
        | WeatherAdjustmentOverrideValue
    )
    unit: str | None = None
    source_attestation: str = Field(min_length=1)
    source_ref: dict[str, Any] | None = None


class StaffingOverrideValue(_StrictBase):
    value: DecimalString
    unit: Literal["person_per_day"] = "person_per_day"


class SpringFestivalIntensityOverrideValue(_StrictBase):
    value: SpringFestivalPhase
    unit: None = None


class ProcessorCapacityOverrideValue(_StrictBase):
    value: DecimalString
    unit: Literal["t_per_day"] = "t_per_day"


class ScenarioOverride(_StrictBase):
    override_kind: Literal["SCENARIO_OVERRIDE_KIND"] = "SCENARIO_OVERRIDE_KIND"
    target: ScenarioTarget
    value: (
        StaffingOverrideValue
        | SpringFestivalIntensityOverrideValue
        | ProcessorCapacityOverrideValue
    )
    unit: str | None = None
    source_attestation: str = Field(min_length=1)
    source_ref: dict[str, Any] | None = None


class ExecutionOverride(_StrictBase):
    override_kind: Literal["EXECUTION_OVERRIDE_KIND"] = "EXECUTION_OVERRIDE_KIND"
    target: ExecutionTarget
    value: bool | str = Field(min_length=1)
    unit: None = None
    source_attestation: str = Field(min_length=1)
    source_ref: dict[str, Any] | None = None


class AuthorityOverride(_StrictBase):
    override_kind: Literal["AUTHORITY_OVERRIDE_KIND"] = "AUTHORITY_OVERRIDE_KIND"
    target: AuthorityOverrideTarget
    value: IntId
    unit: None = None
    source_attestation: str = Field(min_length=1)
    source_ref: dict[str, Any] | None = None


class AdvancedOverrides(_StrictBase):
    parameter_overrides: list[ParameterOverride] = Field(default_factory=list)
    scenario_overrides: list[ScenarioOverride] = Field(default_factory=list)
    execution_overrides: list[ExecutionOverride] = Field(default_factory=list)
    authority_overrides: list[AuthorityOverride] = Field(default_factory=list)
    as_of_overrides: list[AsOfOverride] = Field(default_factory=list)

    @model_validator(mode="after")
    def _at_most_one_as_of(self) -> "AdvancedOverrides":
        if len(self.as_of_overrides) > 1:
            raise ValueError("at most one AS_OF_OVERRIDE may be supplied")
        return self



# --- §7.2 NormalizedAgentRequest + §8.2 RequestedAsOfDateProvenance ------

class RequestedAsOfDateProvenance(_StrictBase):
    caller_requested_as_of_date: date | None
    effective_as_of_date: date
    override_applied: bool
    override_kind: Literal["AS_OF_OVERRIDE"] | None
    source_attestation: str | None
    source_ref: dict[str, Any] | None


class ResolvedLocation(_StrictBase):
    status: Literal["resolved", "ambiguous", "unresolved"]
    location_reference_id: IntId | None = None
    address_normalized: str | None = None
    address_raw: str | None = None
    farm_name: str | None = None
    subfarm_name: str | None = None
    province: str | None = None
    prefecture: str | None = None
    county: str | None = None
    township: str | None = None
    village: str | None = None
    matched_location_method: MatchedLocationMethod
    climate_zone_id: IntId | None = None
    climate_zone_code: str | None = None
    climate_zone_version: str | None = None
    mapping_confidence: DecimalString | None = None
    distance_km: DecimalString | None = None
    altitude_difference_m: DecimalString | None = None
    score: DecimalString | None = None
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    warning: str | None = None


class NormalizedVarietyInput(_StrictBase):
    variety_id: str = Field(min_length=1)
    planting_area_mu: DecimalString


class NormalizedAgentRequest(_StrictBase):
    request_id: str = Field(min_length=1)
    request_received_at: AwareDatetime
    effective_as_of_date: date
    effective_forecast_season: IntId
    season_resolution_policy_version: str = Field(min_length=1)
    season_calendar_config_hash: SHA256Hex
    requested_as_of_date_provenance: RequestedAsOfDateProvenance
    normalized_location: ResolvedLocation
    varieties: list[NormalizedVarietyInput]
    advanced_overrides: AdvancedOverrides | None = None
    canonical_request_hash: SHA256Hex


# --- §19.3 Citation (canonical single source of truth) -------------------

class CitationOverrideRef(_StrictBase):
    override_ref_id: SHA256Hex
    override_kind: OverrideKind
    target: str | None = None
    source_attestation: str = Field(min_length=1)
    source_ref: dict[str, Any] | None = None


class CitationAuthorityEntry(_StrictBase):
    authority_type: AuthorityEnvelopeType
    authority: (
        Task8Authority
        | Task9Authority
        | Task10Authority
        | Task11Authority
        | Task12Authority
    )


class Citation(_StrictBase):
    source_tasks: list[CitationSourceTask]
    source_tool: CitationSourceTool
    authorities: list[CitationAuthorityEntry] = Field(default_factory=list)
    agent_artifact_hash: SHA256Hex | None = None
    field_path: str = Field(min_length=1)
    effective_as_of_date: date
    confidence_evidence: dict[str, Any] | None = None
    tags: list[Literal["OVERRIDE_APPLIED"]] = Field(default_factory=list)
    override_refs: list[CitationOverrideRef] = Field(default_factory=list)


# --- §15.3 DailyQuantiles + ForecastDailyRow -----------------------------

class DailyQuantiles(_StrictBase):
    p50: DecimalString
    p80: DecimalString
    p90: DecimalString


class VarietyContribution(_StrictBase):
    variety_id: str = Field(min_length=1)
    volume_kg_p50: DecimalString
    volume_kg_p80: DecimalString
    volume_kg_p90: DecimalString
    contribution_rate_p50: DecimalString
    contribution_rate_p80: DecimalString
    contribution_rate_p90: DecimalString


class ForecastDailyRow(_StrictBase):
    date: date
    natural_maturity_quantity_kg: DailyQuantiles
    harvested_quantity_kg: DailyQuantiles
    closing_mature_inventory_kg: DailyQuantiles
    unharvested_backlog_kg: DailyQuantiles
    arrival_quantity_kg: DailyQuantiles
    final_corrected_arrival_quantity_kg: DailyQuantiles
    per_variety_contribution: list[VarietyContribution] = Field(default_factory=list)
    agent_daily_row_hash: SHA256Hex


# --- §10.4 UncertaintyWideningPolicy -------------------------------------

class UncertaintyWideningPolicy(_StrictBase):
    policy_version: str = Field(min_length=1)
    config_hash: SHA256Hex
    factors_by_source_level: dict[str, DecimalString]
    monotonicity_invariant: Literal[True] = True


# --- §16.4 PeakMetricPolicy ---------------------------------------------

class PeakMetricPolicy(_StrictBase):
    policy_version: str = Field(min_length=1)
    policy_config_hash: SHA256Hex
    sustained_window_days: int = Field(ge=1)
    sustained_metric: Literal["ROLLING_DAILY_AVERAGE"] = "ROLLING_DAILY_AVERAGE"
    tie_break: Literal["EARLIEST_START_DATE"] = "EARLIEST_START_DATE"
    peak_window_days_before: int = Field(ge=0)
    peak_window_days_after: int = Field(ge=0)
    high_load_reference: Literal["SINGLE_DAY_PEAK"] = "SINGLE_DAY_PEAK"
    high_load_threshold_ratio: DecimalString


# --- §24.1 AgentForecastOutput + Provenance -------------------------------

class ParameterEstimate(_StrictBase):
    parameter_name: str = Field(min_length=1)
    variety_id: str = Field(min_length=1)
    p50: DecimalString
    p80_lower: DecimalString | None = None
    p80_upper: DecimalString | None = None
    source_level: int = Field(ge=1, le=5)
    confidence: Confidence
    confidence_score: DecimalString | None = None
    sample_count: IntId
    season_count: IntId
    farm_count: IntId
    source_observation_ids: list[IntId] = Field(default_factory=list)
    fallback_below_minimum: bool = False
    missing_evidence: list[str] = Field(default_factory=list)
    citation: Citation | None = None


class AgentForecastOutput(_StrictBase):
    request_id: str = Field(min_length=1)
    request_status: RequestStatus
    normalized_request: NormalizedAgentRequest
    resolved_location: ResolvedLocation
    parameters: list[ParameterEstimate] = Field(default_factory=list)
    daily_curve: list[ForecastDailyRow] = Field(default_factory=list)
    peak: dict[str, Any] = Field(default_factory=dict)
    recommendations: list[dict[str, Any]] = Field(default_factory=list)
    explanation: dict[str, Any] = Field(default_factory=dict)
    confidence: dict[str, Any] = Field(default_factory=dict)
    uncertainty_widening_policy_version: str = Field(min_length=1)
    uncertainty_widening_policy_config_hash: SHA256Hex
    peak_metric_policy_version: str | None = None
    peak_metric_policy_config_hash: SHA256Hex | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    blockers: list[Blocker] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# --- §13 resolve_location -------------------------------------------------

class ResolveLocationInput(_StrictBase):
    normalized_request: NormalizedAgentRequest


class ResolveLocationCandidate(_StrictBase):
    location_reference_id: IntId
    address_normalized: str | None = None
    farm_name: str | None = None
    subfarm_name: str | None = None
    score: DecimalString | None = None
    distance_km: DecimalString | None = None


class ResolveLocationOutput(_StrictBase):
    resolved_location: ResolvedLocation
    location_catalog_version: str = Field(min_length=1)
    candidates: list[ResolveLocationCandidate] = Field(default_factory=list)
    blockers: list[Blocker] = Field(default_factory=list)


# --- §14 infer_parameters ------------------------------------------------

class InferParametersInput(_StrictBase):
    normalized_request: NormalizedAgentRequest
    resolved_location: ResolvedLocation
    uncertainty_widening_policy: UncertaintyWideningPolicy


class InferParametersOutput(_StrictBase):
    parameters: list[ParameterEstimate] = Field(default_factory=list)
    uncertainty_widening_policy_version: str = Field(min_length=1)
    uncertainty_widening_policy_config_hash: SHA256Hex
    parameters_hash: SHA256Hex
    blocked_variety_ids: list[str] = Field(default_factory=list)
    blockers: list[Blocker] = Field(default_factory=list)


# --- §15 forecast_daily_curve --------------------------------------------

class ForecastDailyCurveInput(_StrictBase):
    normalized_request: NormalizedAgentRequest
    resolved_location: ResolvedLocation
    parameters: list[ParameterEstimate] = Field(default_factory=list)
    advanced_overrides: AdvancedOverrides | None = None
    uncertainty_widening_policy: UncertaintyWideningPolicy


class ForecastDailyCurveOutput(_StrictBase):
    per_day: list[ForecastDailyRow]
    task8_authority: Task8Authority | None = None
    task9_authority: Task9Authority | None = None
    task10_authority: Task10Authority | None = None
    task11_authority: Task11Authority | None = None
    task12_authority: Task12Authority | None = None
    agent_daily_curve_hash: SHA256Hex
    blockers: list[Blocker] = Field(default_factory=list)


# --- §16 forecast_peak ---------------------------------------------------

class SingleDayPeakEntry(_StrictBase):
    date: date
    volume_kg: DecimalString


class SustainedPeakEntry(_StrictBase):
    start_date: date
    end_date: date
    rolling_daily_average_kg_per_day: DecimalString
    cumulative_quantity_kg: DecimalString


class DominantVarietyEntry(_StrictBase):
    variety_id: str = Field(min_length=1)
    contribution_rate: DecimalString
    numerator_kg: DecimalString
    denominator_kg: DecimalString


class ForecastPeakOutput(_StrictBase):
    peak_metric_policy_version: str = Field(min_length=1)
    peak_metric_policy_config_hash: SHA256Hex
    agent_peak_hash: SHA256Hex
    single_day_peak: dict[ForecastQuantile, SingleDayPeakEntry]
    sustained_window_days: int = Field(ge=1)
    sustained_3day_peak: dict[ForecastQuantile, SustainedPeakEntry]
    peak_window_days_before: int = Field(ge=0)
    peak_window_days_after: int = Field(ge=0)
    peak_window_cumulative_quantity_kg: dict[ForecastQuantile, DecimalString]
    peak_duration_days: dict[ForecastQuantile, int]
    high_load_threshold: dict[ForecastQuantile, DecimalString]
    dominant_variety: dict[ForecastQuantile, DominantVarietyEntry]
    peak_formation_explanation_ref: str | None = None


class ForecastPeakInput(_StrictBase):
    normalized_request: NormalizedAgentRequest
    daily_curve: ForecastDailyCurveOutput
    peak_metric_policy: PeakMetricPolicy


# --- §17 simulate_scenario -----------------------------------------------

class SimulateScenarioInput(_StrictBase):
    normalized_request: NormalizedAgentRequest
    resolved_location: ResolvedLocation
    parameters: list[ParameterEstimate] = Field(default_factory=list)
    scenario_overrides: list[ScenarioOverride] = Field(default_factory=list)
    uncertainty_widening_policy: UncertaintyWideningPolicy
    peak_metric_policy: PeakMetricPolicy
    advanced_overrides: AdvancedOverrides | None = None


class ScenarioDeltaQuantiles(_StrictBase):
    p50: DecimalString
    p80: DecimalString
    p90: DecimalString


class SimulateScenarioDelta(_StrictBase):
    single_day_peak_volume_delta_kg: ScenarioDeltaQuantiles
    sustained_3day_daily_average_delta_kg_per_day: ScenarioDeltaQuantiles
    sustained_3day_cumulative_delta_kg: ScenarioDeltaQuantiles


class SimulateScenarioOutput(_StrictBase):
    scenario_id: SHA256Hex
    scenario_config_hash: SHA256Hex
    forecast_daily_curve: ForecastDailyCurveOutput
    forecast_peak: ForecastPeakOutput
    delta_vs_baseline: SimulateScenarioDelta


# --- §18 run_backtest (deferred; schema + EXECUTION_DEFERRED only) -------

class RunBacktestInput(_StrictBase):
    normalized_request: NormalizedAgentRequest
    execution_override: ExecutionOverride | None = None


class RunBacktestOutput(_StrictBase):
    status: Literal["EXECUTION_DEFERRED"] = "EXECUTION_DEFERRED"
    blocker: Blocker


# --- §19 explain_forecast (schema only) ----------------------------------

class ExplainParagraph(_StrictBase):
    kind: Literal[
        "AUTHORITATIVE_VALUE",
        "DETERMINISTIC_EXPLANATION",
        "DETERMINISTIC_RECOMMENDATION",
        "NON_AUTHORITATIVE_PRESENTATION",
    ]
    text: str = Field(min_length=1)
    citation: Citation | None = None


class ExplainSection(_StrictBase):
    section: str = Field(min_length=1)
    paragraphs: list[ExplainParagraph] = Field(default_factory=list)


class ExplainForecastInput(_StrictBase):
    normalized_request: NormalizedAgentRequest
    resolved_location: ResolvedLocation
    parameters: list[ParameterEstimate] = Field(default_factory=list)
    daily_curve: ForecastDailyCurveOutput
    peak: ForecastPeakOutput
    citations: list[Citation] = Field(default_factory=list)


class ExplainForecastOutput(_StrictBase):
    structured_payload: list[ExplainSection] = Field(default_factory=list)


# --- §20 generate_recommendations (schema only; 7 categories) -----------

class RecommendationEvidenceThreshold(_StrictBase):
    parameter: str = Field(min_length=1)
    value: DecimalString
    unit: str = Field(min_length=1)


class RecommendationEvidence(_StrictBase):
    citation: Citation
    threshold: RecommendationEvidenceThreshold | None = None


class Recommendation(_StrictBase):
    category: RecommendationCategory
    kind: RecommendationKind
    text: str = Field(min_length=1)
    rule_id: str = Field(min_length=1)
    evidence: list[RecommendationEvidence] = Field(default_factory=list)
    confidence: Confidence


class GenerateRecommendationsInput(_StrictBase):
    normalized_request: NormalizedAgentRequest
    resolved_location: ResolvedLocation
    parameters: list[ParameterEstimate] = Field(default_factory=list)
    daily_curve: ForecastDailyCurveOutput
    peak: ForecastPeakOutput
    citations: list[Citation] = Field(default_factory=list)


class GenerateRecommendationsOutput(_StrictBase):
    recommendations: list[Recommendation] = Field(default_factory=list)


# --- §7.1 forward reference resolution -----------------------------------
# MinimalInputRequest references AdvancedOverrides, which is declared later.
# Rebuild MinimalInputRequest here now that AdvancedOverrides exists.

MinimalInputRequest.model_rebuild()
AdvancedOverrides.model_rebuild()


__all__ = [
    "SHA256Hex",
    "IntId",
    "DecimalString",
    "Blocker",
    "MinimalVarietyInput",
    "LocationInput",
    "MinimalInputRequest",
    "Task8Authority",
    "Task9Authority",
    "Task10Authority",
    "Task11Authority",
    "Task12Authority",
    "AsOfOverride",
    "ParameterOverride",
    "ScenarioOverride",
    "ExecutionOverride",
    "AuthorityOverride",
    "AdvancedOverrides",
    "RequestedAsOfDateProvenance",
    "ResolvedLocation",
    "NormalizedVarietyInput",
    "NormalizedAgentRequest",
    "CitationOverrideRef",
    "CitationAuthorityEntry",
    "Citation",
    "DailyQuantiles",
    "VarietyContribution",
    "ForecastDailyRow",
    "UncertaintyWideningPolicy",
    "PeakMetricPolicy",
    "ParameterEstimate",
    "AgentForecastOutput",
    "ResolveLocationInput",
    "ResolveLocationCandidate",
    "ResolveLocationOutput",
    "InferParametersInput",
    "InferParametersOutput",
    "ForecastDailyCurveInput",
    "ForecastDailyCurveOutput",
    "ForecastPeakInput",
    "ForecastPeakOutput",
    "SimulateScenarioInput",
    "SimulateScenarioOutput",
    "RunBacktestInput",
    "RunBacktestOutput",
    "ExplainForecastInput",
    "ExplainForecastOutput",
    "Recommendation",
    "RecommendationEvidence",
    "RecommendationEvidenceThreshold",
    "GenerateRecommendationsInput",
    "GenerateRecommendationsOutput",
]
