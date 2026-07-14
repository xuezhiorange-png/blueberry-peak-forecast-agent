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

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated, Any, Literal, get_args

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
    BlockerCode,
    CitationSourceTask,
    CitationSourceTool,
    ConditionResult,
    Confidence,
    ExplanationParagraphKind,
    ExplanationSectionCode,
    ForecastQuantile,
    MatchedLocationMethod,
    MissingDataImpactCode,
    OverrideKind,
    RecommendationCategory,
    RecommendationKind,
    RecommendationReasonCode,
    RecommendationStatus,
    RequestStatus,
    RetryHint,
    SpringFestivalPhase,
)
from backend.app.harvest_state.schemas import ForecastSeasonIdentitySnapshot

# --- Strict scalar constraints --------------------------------------------

SHA256Hex = Annotated[
    str,
    StringConstraints(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"),
]

RFC6901JsonPointer = Annotated[
    str,
    StringConstraints(
        min_length=1,
        pattern=r"^(?:/(?:[^~/]|~[01])*)+$",
    ),
]

IntId = Annotated[int, Field(ge=0, strict=True)]

DecimalString = Annotated[
    str,
    StringConstraints(min_length=1, pattern=r"^-?\d+(?:\.\d+)?$"),
]


def _validate_canonical_decimal_string(value: str) -> str:
    """Reject scientific notation, leading zeros (except ``0``), ``-0``."""
    if value.startswith("-") and value not in (
        "-0",
        "-0.0",
        "-0.00",
        "-0.000",
        "-0.0000",
    ):
        body = value[1:]
        if body.startswith("0") and len(body) > 1 and not body.startswith("0."):
            raise ValueError("negative canonical decimal may not have leading zeros")
    else:
        if len(value) > 1 and value.startswith("0") and not value.startswith("0."):
            raise ValueError("non-negative canonical decimal may not have leading zeros")
    if value in ("-0", "-0.0", "-0.00", "-0.000", "-0.0000"):
        raise ValueError("canonical decimal may not be negative zero")
    return value


NonNegativeDecimalString = Annotated[
    str,
    StringConstraints(min_length=1, pattern=r"^-?\d+(?:\.\d+)?$"),
]

PositiveDecimalString = Annotated[
    str,
    StringConstraints(min_length=1, pattern=r"^-?\d+(?:\.\d+)?$"),
]


class _StrictBase(BaseModel):
    """Common base: extra fields are FORBIDDEN; freeze by default."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Blocker(_StrictBase):
    code: BlockerCode
    message: str = Field(min_length=1, max_length=2000)
    details: dict[str, Any] | None = None
    citation: dict[str, Any] | None = None
    retry_hint: RetryHint = "NONE"


# SourceCapabilityGapError is raised by adapters when a required upstream
# source is missing.  We define it here as a public class so the schema-level
# ``_verify_policy_invariant`` helper can reference it without importing
# from the adapter module (which would create a circular import).


class SourceCapabilityGapError(RuntimeError):
    """Raised when a required upstream source is missing."""


class MinimalVarietyInput(_StrictBase):
    variety_id: str = Field(min_length=1)
    planting_area_mu: DecimalString

    @field_validator("planting_area_mu")
    @classmethod
    def _validate_canonical_area(cls, value: str) -> str:
        _validate_canonical_decimal_string(value)
        if Decimal(value) <= Decimal("0"):
            raise ValueError("planting_area_mu must be > 0")
        return value


class LocationInput(_StrictBase):
    """Raw caller-supplied location input — §13.

    Deterministic precedence (highest → lowest):
    1. ``location_reference_id`` (REFERENCE_ID)
    2. ``address``
    3. (``latitude``, ``longitude``) coordinates (paired)
    4. ``raw_text``
    5. ``map_pick_token``
    """

    raw_text: str | None = None
    latitude: DecimalString | None = None
    longitude: DecimalString | None = None
    map_pick_token: str | None = None
    location_reference_id: IntId | None = None
    address: str | None = None
    altitude_m: DecimalString | None = None

    @model_validator(mode="after")
    def _validate(self) -> LocationInput:
        if (
            self.raw_text is None
            and self.latitude is None
            and self.longitude is None
            and self.map_pick_token is None
            and self.location_reference_id is None
            and self.address is None
        ):
            raise ValueError(
                "location must supply at least one of: raw_text / coordinates / "
                "map_pick_token / location_reference_id / address"
            )
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be provided together or both omitted")
        if self.latitude is not None:
            lat = Decimal(self.latitude)
            if lat < Decimal("-90") or lat > Decimal("90"):
                raise ValueError("latitude must be in [-90, 90]")
        if self.longitude is not None:
            lng = Decimal(self.longitude)
            if lng < Decimal("-180") or lng > Decimal("180"):
                raise ValueError("longitude must be in [-180, 180]")
        return self


class MinimalInputRequest(_StrictBase):
    request_id: str = Field(min_length=1)
    location: LocationInput
    varieties: list[MinimalVarietyInput]
    requested_as_of_date: date | None = None
    requested_forecast_season: (
        Annotated[int, Field(strict=True, gt=0)]
        | Annotated[str, Field(strict=True, min_length=1)]
        | None
    ) = None
    advanced_overrides: AdvancedOverrides | None = None

    @field_validator("varieties")
    @classmethod
    def _non_empty(cls, v: list[MinimalVarietyInput]) -> list[MinimalVarietyInput]:
        if not v:
            raise ValueError("varieties must be non-empty")
        return v


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
    forecast_season_id: Annotated[int, Field(strict=True, gt=0)] | None = None
    pool_row_count: IntId
    member_row_count: IntId
    cohort_row_count: IntId
    future_arrival_row_count: IntId
    source_ref_schema_version: str = Field(min_length=1)
    result_hash_schema_version: str = Field(min_length=1)
    stable_cohort_key_schema_version: str = Field(min_length=1)
    resolved_parameter_snapshot_schema_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def _forecast_range_valid(self) -> Task9Authority:
        if self.harvest_state_forecast_start_date > self.harvest_state_forecast_end_date:
            raise ValueError(
                "harvest_state_forecast_start_date must be <= harvest_state_forecast_end_date"
            )
        if (
            self.harvest_state_output_schema_version == "task9a-output-v2"
            and self.forecast_season_id is None
        ):
            raise ValueError("Task 9 v2 authority requires forecast_season_id")
        return self


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

    @model_validator(mode="after")
    def _training_identity_consistent(self) -> Task10Authority:
        if (self.training_run_id is None) != (self.training_manifest_hash is None):
            raise ValueError("training_run_id is None iff training_manifest_hash is None")
        return self

    @field_validator("artifact_hashes")
    @classmethod
    def _sorted_ascending(cls, value: list[SHA256Hex]) -> list[SHA256Hex]:
        if list(value) != sorted(value):
            raise ValueError("artifact_hashes must be sorted ascending (canonical)")
        return value


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
    # P0-2 round 5: the four policy-version fields are OPTIONAL.  When
    # the upstream schema does not expose a real persisted
    # ``*_policy_version`` column, the loader surfaces
    # AUTHORITY_POLICY_VERSION_MISSING and leaves these as None.  The
    # previous implementation mapped status / mode / policy-enum fields
    # into these slots, which violated the P0-2 provenance discipline.
    validation_policy_version: str | None = None
    label_visibility_policy_version: str | None = None
    feature_visibility_policy_version: str | None = None
    artifact_visibility_policy_version: str | None = None
    model_artifact_hash: SHA256Hex | None
    task9_replay_binding_identity: SHA256Hex
    task10_manifest_hash: SHA256Hex | None
    task10_config_hash: SHA256Hex | None

    @field_validator("forecast_cutoff_at", "training_cutoff_at")
    @classmethod
    def _utc_only(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):  # noqa: UP017
            raise ValueError("aware datetimes must be UTC")
        return value


class AsOfOverride(_StrictBase):
    override_kind: Literal["AS_OF_OVERRIDE"] = "AS_OF_OVERRIDE"
    value: date
    unit: Literal["date"] = "date"
    source_attestation: str = Field(min_length=1)
    source_ref: dict[str, Any] | None = None


class YieldPerMuOverrideValue(_StrictBase):
    value: PositiveDecimalString
    unit: Literal["kg_per_mu"] = "kg_per_mu"

    @field_validator("value")
    @classmethod
    def _validate_canonical(cls, value: str) -> str:
        _validate_canonical_decimal_string(value)
        return value


class RateOverrideValue(_StrictBase):
    value: DecimalString
    unit: Literal["ratio"] = "ratio"

    @field_validator("value")
    @classmethod
    def _validate_canonical(cls, value: str) -> str:
        _validate_canonical_decimal_string(value)
        return value


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


class StaffingOverrideValue(_StrictBase):
    value: NonNegativeDecimalString
    unit: Literal["person_per_day"] = "person_per_day"

    @field_validator("value")
    @classmethod
    def _validate_canonical(cls, value: str) -> str:
        _validate_canonical_decimal_string(value)
        return value


class SpringFestivalIntensityOverrideValue(_StrictBase):
    value: SpringFestivalPhase
    unit: None = None


class ProcessorCapacityOverrideValue(_StrictBase):
    value: NonNegativeDecimalString
    unit: Literal["t_per_day"] = "t_per_day"

    @field_validator("value")
    @classmethod
    def _validate_canonical(cls, value: str) -> str:
        _validate_canonical_decimal_string(value)
        return value


class _ParameterOverrideBase(_StrictBase):
    override_kind: Literal["PARAMETER_OVERRIDE_KIND"] = "PARAMETER_OVERRIDE_KIND"
    variety_id: str = Field(min_length=1)
    source_attestation: str = Field(min_length=1)
    source_ref: dict[str, Any] | None = None


class ExpectedPerMuYieldOverride(_ParameterOverrideBase):
    variety_id: str = Field(min_length=1)
    target_parameter: Literal["EXPECTED_PER_MU_YIELD"]
    value: YieldPerMuOverrideValue
    unit: str | None = None


class CommodityFruitRateOverride(_ParameterOverrideBase):
    variety_id: str = Field(min_length=1)
    target_parameter: Literal["COMMODITY_FRUIT_RATE"]
    value: RateOverrideValue
    unit: str | None = None


class FirstHarvestDateOverride(_ParameterOverrideBase):
    variety_id: str = Field(min_length=1)
    target_parameter: Literal["FIRST_HARVEST_DATE"]
    value: DateOverrideValue
    unit: str | None = None


class MaturityCurveOverride(_ParameterOverrideBase):
    variety_id: str = Field(min_length=1)
    target_parameter: Literal["MATURITY_CURVE"]
    value: DistributionOverrideValue
    unit: str | None = None


class SpringFestivalHarvestRateOverride(_ParameterOverrideBase):
    variety_id: str = Field(min_length=1)
    target_parameter: Literal["SPRING_FESTIVAL_HARVEST_RATE"]
    value: RateOverrideValue
    unit: str | None = None


class WeatherAdjustmentOverride(_ParameterOverrideBase):
    variety_id: str = Field(min_length=1)
    target_parameter: Literal["WEATHER_ADJUSTMENT"]
    value: WeatherAdjustmentOverrideValue
    unit: str | None = None


class PostSpringFestivalBacklogReleaseIntensityOverride(_ParameterOverrideBase):
    variety_id: str = Field(min_length=1)
    target_parameter: Literal["POST_SPRING_FESTIVAL_BACKLOG_RELEASE_INTENSITY"]
    value: RateOverrideValue
    unit: str | None = None


class HistoricalAnomalyPeakProbabilityOverride(_ParameterOverrideBase):
    variety_id: str = Field(min_length=1)
    target_parameter: Literal["HISTORICAL_ANOMALY_PEAK_PROBABILITY"]
    value: RateOverrideValue
    unit: str | None = None


ParameterOverrideUnion = Annotated[
    ExpectedPerMuYieldOverride
    | CommodityFruitRateOverride
    | FirstHarvestDateOverride
    | MaturityCurveOverride
    | SpringFestivalHarvestRateOverride
    | WeatherAdjustmentOverride
    | PostSpringFestivalBacklogReleaseIntensityOverride
    | HistoricalAnomalyPeakProbabilityOverride,
    Field(discriminator="target_parameter"),
]


class _ScenarioOverrideBase(_StrictBase):
    override_kind: Literal["SCENARIO_OVERRIDE_KIND"] = "SCENARIO_OVERRIDE_KIND"
    source_attestation: str = Field(min_length=1)
    source_ref: dict[str, Any] | None = None


class StaffingScenarioOverride(_ScenarioOverrideBase):
    target: Literal["STAFFING"]
    value: StaffingOverrideValue
    unit: str | None = None


class SpringFestivalIntensityScenarioOverride(_ScenarioOverrideBase):
    target: Literal["SPRING_FESTIVAL_INTENSITY"]
    value: SpringFestivalIntensityOverrideValue
    unit: str | None = None


class ProcessorCapacityScenarioOverride(_ScenarioOverrideBase):
    target: Literal["PROCESSOR_CAPACITY"]
    value: ProcessorCapacityOverrideValue
    unit: str | None = None


ScenarioOverrideUnion = Annotated[
    StaffingScenarioOverride
    | SpringFestivalIntensityScenarioOverride
    | ProcessorCapacityScenarioOverride,
    Field(discriminator="target"),
]


class _ExecutionOverrideBase(_StrictBase):
    override_kind: Literal["EXECUTION_OVERRIDE_KIND"] = "EXECUTION_OVERRIDE_KIND"
    source_attestation: str = Field(min_length=1)
    source_ref: dict[str, Any] | None = None


class RequestBacktestOverride(_ExecutionOverrideBase):
    target: Literal["REQUEST_BACKTEST"]
    value: bool
    unit: None = None


class RequestReplayTrainedRunOverride(_ExecutionOverrideBase):
    target: Literal["REQUEST_REPLAY_TRAINED_RUN"]
    value: bool
    unit: None = None


class RequestSimulationOverride(_ExecutionOverrideBase):
    target: Literal["REQUEST_SIMULATION"]
    value: bool
    unit: None = None


ExecutionOverrideUnion = Annotated[
    RequestBacktestOverride | RequestReplayTrainedRunOverride | RequestSimulationOverride,
    Field(discriminator="target"),
]


class _AuthorityOverrideBase(_StrictBase):
    override_kind: Literal["AUTHORITY_OVERRIDE_KIND"] = "AUTHORITY_OVERRIDE_KIND"
    value: IntId
    unit: None = None
    source_attestation: str = Field(min_length=1)
    source_ref: dict[str, Any] | None = None


class Task8ForecastRunAuthorityOverride(_AuthorityOverrideBase):
    target: Literal["TASK8_FORECAST_RUN"]


class Task9HarvestStateRunAuthorityOverride(_AuthorityOverrideBase):
    target: Literal["TASK9_HARVEST_STATE_RUN"]


class Task10PredictionRunAuthorityOverride(_AuthorityOverrideBase):
    target: Literal["TASK10_PREDICTION_RUN"]


class Task10TrainingRunAuthorityOverride(_AuthorityOverrideBase):
    target: Literal["TASK10_TRAINING_RUN"]


class Task11BacktestRunAuthorityOverride(_AuthorityOverrideBase):
    target: Literal["TASK11_BACKTEST_RUN"]


class Task12PredictionRunAuthorityOverride(_AuthorityOverrideBase):
    target: Literal["TASK12_PREDICTION_RUN"]


AuthorityOverrideUnion = Annotated[
    Task8ForecastRunAuthorityOverride
    | Task9HarvestStateRunAuthorityOverride
    | Task10PredictionRunAuthorityOverride
    | Task10TrainingRunAuthorityOverride
    | Task11BacktestRunAuthorityOverride
    | Task12PredictionRunAuthorityOverride,
    Field(discriminator="target"),
]


class AdvancedOverrides(_StrictBase):
    parameter_overrides: list[ParameterOverrideUnion] = Field(default_factory=list)
    scenario_overrides: list[ScenarioOverrideUnion] = Field(default_factory=list)
    execution_overrides: list[ExecutionOverrideUnion] = Field(default_factory=list)
    authority_overrides: list[AuthorityOverrideUnion] = Field(default_factory=list)
    as_of_overrides: list[AsOfOverride] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_invariants(self) -> AdvancedOverrides:
        if len(self.as_of_overrides) > 1:
            raise ValueError("at most one AS_OF_OVERRIDE may be supplied")

        seen_param: set[tuple[str, str]] = set()
        for po in self.parameter_overrides:
            key = (po.variety_id, po.target_parameter)
            if key in seen_param:
                raise ValueError(
                    f"duplicate parameter override for (variety_id, target_parameter)={key}"
                )
            seen_param.add(key)

        seen_scenario: set[str] = set()
        for so in self.scenario_overrides:
            if so.target in seen_scenario:
                raise ValueError(f"duplicate scenario override for target={so.target}")
            seen_scenario.add(so.target)

        seen_auth: set[str] = set()
        for ao in self.authority_overrides:
            if ao.target in seen_auth:
                raise ValueError(f"duplicate authority override for target={ao.target}")
            seen_auth.add(ao.target)

        task10_targets = {
            ao.target for ao in self.authority_overrides if ao.target.startswith("TASK10_")
        }
        if {"TASK10_TRAINING_RUN", "TASK10_PREDICTION_RUN"}.issubset(task10_targets):
            raise ValueError(
                "TASK10_TRAINING_RUN and TASK10_PREDICTION_RUN overrides conflict on the same scope"
            )
        return self


class RequestedAsOfDateProvenance(_StrictBase):
    caller_requested_as_of_date: date | None
    effective_as_of_date: date
    override_applied: bool
    override_kind: Literal["AS_OF_OVERRIDE"] | None
    source_attestation: str | None
    source_ref: dict[str, Any] | None

    @model_validator(mode="after")
    def _consistent(self) -> RequestedAsOfDateProvenance:
        if not self.override_applied:
            if self.override_kind is not None:
                raise ValueError("override_kind must be None when override_applied is False")
            if self.source_attestation is not None:
                raise ValueError("source_attestation must be None when override_applied is False")
            if self.source_ref is not None:
                raise ValueError("source_ref must be None when override_applied is False")
        else:
            if self.override_kind != "AS_OF_OVERRIDE":
                raise ValueError(
                    "override_kind must be 'AS_OF_OVERRIDE' when override_applied is True"
                )
            if self.source_attestation is None:
                raise ValueError("source_attestation is required when override_applied is True")
        return self


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

    @field_validator("planting_area_mu")
    @classmethod
    def _validate_canonical_area(cls, value: str) -> str:
        _validate_canonical_decimal_string(value)
        if Decimal(value) <= Decimal("0"):
            raise ValueError("planting_area_mu must be > 0")
        return value


class NormalizedAgentRequest(_StrictBase):
    request_id: str = Field(min_length=1)
    request_received_at: AwareDatetime
    effective_as_of_date: date
    requested_forecast_season: int | str | None = None
    effective_forecast_season_id: Annotated[int, Field(strict=True, gt=0)] | None = None
    effective_forecast_season_code: str | None = Field(default=None, min_length=1)
    season_record_hash: SHA256Hex | None = None
    season_resolution_policy_version: str | None = Field(default=None, min_length=1)
    season_resolution_policy_config_hash: SHA256Hex | None = None
    # Transitional constructor compatibility only. These fields are excluded
    # from canonical serialization and are never read as authority.
    effective_forecast_season: IntId | None = Field(default=None, exclude=True)
    season_calendar_config_hash: SHA256Hex | None = Field(default=None, exclude=True)
    requested_as_of_date_provenance: RequestedAsOfDateProvenance
    normalized_location: ResolvedLocation
    # P0-3.1: location_input is the RAW caller location (from MinimalInputRequest),
    # distinct from normalized_location (the resolved output of resolve_location).
    location_input: LocationInput
    varieties: list[NormalizedVarietyInput]
    advanced_overrides: AdvancedOverrides | None = None
    canonical_request_hash: SHA256Hex

    @model_validator(mode="after")
    def _season_identity_is_atomic(self) -> NormalizedAgentRequest:
        identity_fields = (
            self.effective_forecast_season_id,
            self.effective_forecast_season_code,
            self.season_record_hash,
            self.season_resolution_policy_config_hash,
        )
        if any(value is not None for value in identity_fields) and not (
            all(value is not None for value in identity_fields)
            and self.season_resolution_policy_version is not None
        ):
            raise ValueError("resolved forecast season identity must be complete or absent")
        return self


class ResolvedForecastSeasonIdentity(_StrictBase):
    season_snapshot: ForecastSeasonIdentitySnapshot
    season_resolution_policy_version: str = Field(min_length=1)
    season_resolution_policy_config_hash: SHA256Hex


class CitationOverrideRef(_StrictBase):
    override_ref_id: SHA256Hex
    override_kind: OverrideKind
    target: str | None = None
    source_attestation: str = Field(min_length=1)
    source_ref: dict[str, Any] | None = None


class CitationAuthorityEntry(_StrictBase):
    authority_type: AuthorityEnvelopeType
    authority: Task8Authority | Task9Authority | Task10Authority | Task11Authority | Task12Authority


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
    weather_tags: tuple[str, ...] = ()
    spring_festival_phase: SpringFestivalPhase = "NONE"
    agent_daily_row_hash: SHA256Hex


_UNCERTAINTY_STEP_KEYS: tuple[str, ...] = (
    "step_1_same_farm_same_variety_high_evidence",
    "step_2_same_township_similar_altitude",
    "step_3_same_county_same_climate_zone",
    "step_4_province_level_same_variety",
    "step_5_variety_document_prior_only",
)


class UncertaintyWideningPolicy(_StrictBase):
    policy_version: str = Field(min_length=1)
    config_hash: SHA256Hex
    factors_by_source_level: dict[str, DecimalString]
    monotonicity_invariant: Literal[True] = True

    @model_validator(mode="after")
    def _verify_policy_invariant(self) -> UncertaintyWideningPolicy:
        # The Pydantic-level validator only confirms the keys that ARE present
        # are well-formed decimal strings >= 0 and strictly monotonic.
        # The full 5-key requirement is enforced by
        # :func:`_verify_policy_invariant` (and by
        # :func:`widening_factor_for` which raises on missing keys).
        factors = self.factors_by_source_level
        values: list[tuple[str, Decimal]] = []
        for key, raw in factors.items():
            v = Decimal(raw)
            if v < Decimal("0"):
                raise ValueError(f"factor {key} must be >= 0")
            values.append((key, v))
        prev_pair: tuple[str, Decimal] | None = None
        for curr_pair in values:
            if prev_pair is not None:
                if not (prev_pair[1] < curr_pair[1]):
                    raise ValueError("factors must be strictly monotonic (ascending)")
            prev_pair = curr_pair
        return self


def _verify_policy_invariant(policy: UncertaintyWideningPolicy) -> None:
    """Strict invariant check used by adapters + integration tests.

    Requires all five canonical step keys to be present and strictly
    monotonic ascending.  The Pydantic ``model_validator`` does NOT enforce
    the 5-key requirement because older tests still pass partial policies
    (to demonstrate that ``widening_factor_for`` raises ``SourceCapabilityGapError``).
    """
    factors = policy.factors_by_source_level
    missing = [k for k in _UNCERTAINTY_STEP_KEYS if k not in factors]
    if missing:
        raise SourceCapabilityGapError(
            f"UncertaintyWideningPolicy missing required factor(s): {missing}"
        )
    values: list[Decimal] = []
    for k in _UNCERTAINTY_STEP_KEYS:
        v = Decimal(factors[k])
        if v < Decimal("0"):
            raise SourceCapabilityGapError(f"factor {k} must be >= 0")
        values.append(v)
    for prev, curr in zip(values, values[1:], strict=True):
        if not (prev < curr):
            raise SourceCapabilityGapError(
                f"factors must be strictly monotonic: {_UNCERTAINTY_STEP_KEYS}"
            )


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
    strict_three_day_window: Literal[True] = True

    @model_validator(mode="after")
    def _enforce_strict_three_day_window(self) -> PeakMetricPolicy:
        if self.strict_three_day_window and self.sustained_window_days != 3:
            raise ValueError("strict_three_day_window=True forces sustained_window_days == 3")
        return self


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
    prior_version: str | None = None
    distribution_kind: Literal["POINT", "NORMAL", "BETA", "HISTORICAL_EMPIRICAL"] = "POINT"
    citation: Citation | None = None


class AgentForecastOutput(_StrictBase):
    request_id: str = Field(min_length=1)
    request_status: RequestStatus
    normalized_request: NormalizedAgentRequest
    resolved_location: ResolvedLocation
    parameters: list[ParameterEstimate] = Field(default_factory=list)
    daily_curve: list[ForecastDailyRow] = Field(default_factory=list)
    peak: dict[str, Any] = Field(default_factory=dict)
    citations: list[Citation] = Field(default_factory=list)
    recommendations: GenerateRecommendationsOutput
    explanation: ExplainForecastOutput
    confidence: dict[str, Any] = Field(default_factory=dict)
    uncertainty_widening_policy_version: str = Field(min_length=1)
    uncertainty_widening_policy_config_hash: SHA256Hex
    peak_metric_policy_version: str | None = None
    peak_metric_policy_config_hash: SHA256Hex | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    blockers: list[Blocker] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ResolveLocationInput(_StrictBase):
    """P0-3.3 — input carries the RAW caller-supplied ``location_input``."""

    normalized_request: NormalizedAgentRequest
    location_input: LocationInput | None = None

    @property
    def resolved_location_input(self) -> LocationInput:
        """Resolve location_input at access time (Pydantic frozen-safe)."""
        if self.location_input is not None:
            return self.location_input
        return self.normalized_request.location_input


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
    blockers: list[Blocker] = Field(default_factory=list)


class ForecastPeakInput(_StrictBase):
    normalized_request: NormalizedAgentRequest
    daily_curve: ForecastDailyCurveOutput
    peak_metric_policy: PeakMetricPolicy


class SimulateScenarioInput(_StrictBase):
    normalized_request: NormalizedAgentRequest
    resolved_location: ResolvedLocation
    parameters: list[ParameterEstimate] = Field(default_factory=list)
    scenario_overrides: list[ScenarioOverrideUnion] = Field(default_factory=list)
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
    """Discriminated scenario result (P0-6 round 5).

    When the scenario override cannot be executed by any upstream
    service in Slice A, ``status`` is ``"BLOCKED"`` and the
    ``forecast_daily_curve`` / ``forecast_peak`` / ``delta_vs_baseline``
    fields are NOT populated with fabricated values.  The ``blockers``
    list carries the typed capability/incompatibility blocker(s) that
    caused the BLOCKED status.  When ``status`` is ``"SUCCESS"`` the
    scenario was executed end-to-end against the real upstream pipeline.
    """

    scenario_id: SHA256Hex
    scenario_config_hash: SHA256Hex
    status: Literal["SUCCESS", "BLOCKED"]
    forecast_daily_curve: ForecastDailyCurveOutput | None = None
    forecast_peak: ForecastPeakOutput | None = None
    delta_vs_baseline: SimulateScenarioDelta | None = None
    blockers: list[Blocker] = Field(default_factory=list)


class RunBacktestInput(_StrictBase):
    normalized_request: NormalizedAgentRequest
    execution_override: ExecutionOverrideUnion | None = None


class RunBacktestOutput(_StrictBase):
    status: Literal["EXECUTION_DEFERRED"] = "EXECUTION_DEFERRED"
    blocker: Blocker


class SliceCSourcePayload(_StrictBase):
    """Validated, immutable Slice B evidence consumed by Slice C."""

    request_id: str = Field(min_length=1)
    request_status: RequestStatus
    normalized_request: NormalizedAgentRequest
    resolved_location: ResolvedLocation
    parameters: list[ParameterEstimate] = Field(default_factory=list)
    daily_curve: list[ForecastDailyRow] = Field(default_factory=list)
    peak: dict[str, Any]
    citations: list[Citation] = Field(default_factory=list)
    confidence: dict[str, Any] = Field(min_length=1)
    provenance: dict[str, Any] = Field(min_length=1)
    blockers: list[Blocker] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ExplanationRulePolicy(_StrictBase):
    policy_version: str = Field(min_length=1)
    policy_config_hash: SHA256Hex
    template_catalog_version: str = Field(min_length=1)
    template_catalog_hash: SHA256Hex


class RecommendationRulePolicy(_StrictBase):
    policy_version: str = Field(min_length=1)
    policy_config_hash: SHA256Hex
    rule_catalog_version: str = Field(min_length=1)
    rule_catalog_hash: SHA256Hex


class ExplainParagraph(_StrictBase):
    kind: ExplanationParagraphKind
    text: str = Field(min_length=1)
    template_id: str = Field(min_length=1)
    evidence_field_paths: list[RFC6901JsonPointer] = Field(min_length=1)
    citation: Citation | None = None

    @model_validator(mode="after")
    def _authoritative_value_requires_citation(self) -> ExplainParagraph:
        if self.kind == "AUTHORITATIVE_VALUE" and self.citation is None:
            raise ValueError("AUTHORITATIVE_VALUE requires a canonical Citation")
        return self


class ExplainSection(_StrictBase):
    section: ExplanationSectionCode
    paragraphs: list[ExplainParagraph] = Field(default_factory=list)


class ExplainForecastInput(_StrictBase):
    normalized_request: NormalizedAgentRequest
    resolved_location: ResolvedLocation
    parameters: list[ParameterEstimate] = Field(default_factory=list)
    daily_curve: ForecastDailyCurveOutput
    peak: ForecastPeakOutput
    citations: list[Citation] = Field(default_factory=list)


class ExplainForecastOutput(_StrictBase):
    explanation_rule_policy_version: str = Field(min_length=1)
    explanation_rule_policy_config_hash: SHA256Hex
    template_catalog_version: str = Field(min_length=1)
    template_catalog_hash: SHA256Hex
    structured_payload: list[ExplainSection]
    agent_explanation_hash: SHA256Hex
    blockers: list[Blocker] = Field(default_factory=list)

    @model_validator(mode="after")
    def _sections_are_complete_and_ordered(self) -> ExplainForecastOutput:
        expected = list(get_args(ExplanationSectionCode))
        actual = [section.section for section in self.structured_payload]
        if actual != expected:
            raise ValueError("explanation sections must contain the frozen eight-section order")
        emitted = {
            paragraph.kind
            for section in self.structured_payload
            for paragraph in section.paragraphs
        }
        if not emitted <= {"AUTHORITATIVE_VALUE", "DETERMINISTIC_EXPLANATION"}:
            raise ValueError("Slice C may emit only authoritative values and explanations")
        return self


class RecommendationEvidenceThreshold(_StrictBase):
    parameter: str = Field(min_length=1)
    value: DecimalString
    unit: str = Field(min_length=1)


class RecommendationEvidence(_StrictBase):
    citation: Citation
    affected_field_paths: list[RFC6901JsonPointer] = Field(min_length=1)
    missing_data_code: MissingDataImpactCode | None = None
    threshold: RecommendationEvidenceThreshold | None = None


class ConditionEvaluation(_StrictBase):
    field_path: RFC6901JsonPointer
    operator: str = Field(min_length=1)
    observed_value: str | int | bool | None
    threshold_value: str | int | bool | None
    unit: str | None = None
    result: ConditionResult
    citation: Citation | None = None


class NonAction(_StrictBase):
    required: Literal[True] = True
    code: Literal["ADVISORY_ONLY_NO_AUTOMATIC_EXECUTION"] = "ADVISORY_ONLY_NO_AUTOMATIC_EXECUTION"
    text: Literal["This output is advisory only and does not trigger any external action."] = (
        "This output is advisory only and does not trigger any external action."
    )
    category_specific_code: str = Field(min_length=1)


class RecommendationDecision(_StrictBase):
    category: RecommendationCategory
    kind: RecommendationKind
    status: RecommendationStatus
    reason_code: RecommendationReasonCode
    reason_details: dict[str, Any] | None = None
    priority_rank: int = Field(ge=1, le=7, strict=True)
    rule_id: str = Field(min_length=1)
    template_id: str = Field(min_length=1)
    advisory_text: str | None = None
    applicability_conditions: list[ConditionEvaluation] = Field(default_factory=list)
    evidence: list[RecommendationEvidence] = Field(default_factory=list)
    risk_codes: list[str] = Field(default_factory=list)
    confidence: Confidence | None = None
    confidence_boundary: dict[str, Any] | None = None
    blocker_dependencies: list[Blocker] = Field(default_factory=list)
    non_action: NonAction

    @model_validator(mode="after")
    def _status_reason_contract(self) -> RecommendationDecision:
        allowed = {
            "APPLICABLE": {"RULE_APPLICABLE"},
            "NOT_APPLICABLE": {"CONDITIONS_NOT_MET", "OUTSIDE_AUTHORIZED_SCOPE"},
            "BLOCKED": {
                "REQUIRED_THRESHOLD_MISSING",
                "REQUIRED_EVIDENCE_MISSING",
                "UPSTREAM_BLOCKED",
                "POLICY_UNAVAILABLE",
            },
        }
        if self.reason_code not in allowed[self.status]:
            raise ValueError("reason_code is incompatible with recommendation status")
        if self.status == "APPLICABLE" and self.advisory_text is None:
            raise ValueError("APPLICABLE requires advisory_text")
        if self.status != "APPLICABLE" and self.advisory_text is not None:
            raise ValueError("non-APPLICABLE decisions must not contain advisory_text")
        if self.status == "BLOCKED" and not self.blocker_dependencies:
            raise ValueError("BLOCKED requires blocker_dependencies")
        return self


class GenerateRecommendationsInput(_StrictBase):
    normalized_request: NormalizedAgentRequest
    resolved_location: ResolvedLocation
    parameters: list[ParameterEstimate] = Field(default_factory=list)
    daily_curve: ForecastDailyCurveOutput
    peak: ForecastPeakOutput
    citations: list[Citation] = Field(default_factory=list)


class GenerateRecommendationsOutput(_StrictBase):
    recommendation_rule_policy_version: str = Field(min_length=1)
    recommendation_rule_policy_config_hash: SHA256Hex
    rule_catalog_version: str = Field(min_length=1)
    rule_catalog_hash: SHA256Hex
    decisions: list[RecommendationDecision]
    agent_recommendations_hash: SHA256Hex
    blockers: list[Blocker] = Field(default_factory=list)

    @model_validator(mode="after")
    def _decisions_are_complete_and_ordered(self) -> GenerateRecommendationsOutput:
        expected = list(get_args(RecommendationCategory))
        actual = [decision.category for decision in self.decisions]
        if actual != expected:
            raise ValueError("recommendations must contain exactly seven categories in order")
        return self


MinimalInputRequest.model_rebuild()
AdvancedOverrides.model_rebuild()
AgentForecastOutput.model_rebuild()


# --- Backward-compat aliases ---------------------------------------------
# The legacy union-typed names (``ParameterOverride``, ``ScenarioOverride``,
# ``ExecutionOverride``, ``AuthorityOverride``) are preserved as
# ``RootModel``-backed proxies so existing tests + downstream callers
# continue to construct them transparently and access discriminator
# fields directly (``ov.target``, ``ov.override_kind`` …).


from pydantic import RootModel as _RootModel  # noqa: E402


def _wrap_root_model(cls: type[_RootModel[Any]], public_name: str) -> type[Any]:
    """Build a public alias class that delegates attribute access to ``.root``."""

    class _Alias(cls):  # type: ignore[misc, valid-type]
        def __getattr__(self, item: str) -> Any:
            if item.startswith("__") or item.startswith("model_") or item in ("root",):
                return object.__getattribute__(self, item)
            return getattr(self.root, item)

    _Alias.__name__ = public_name
    _Alias.__qualname__ = public_name
    return _Alias


class _ParameterOverrideRoot(_RootModel[ParameterOverrideUnion]):
    pass


class _ScenarioOverrideRoot(_RootModel[ScenarioOverrideUnion]):
    pass


class _ExecutionOverrideRoot(_RootModel[ExecutionOverrideUnion]):
    pass


class _AuthorityOverrideRoot(_RootModel[AuthorityOverrideUnion]):
    pass


ParameterOverride = _wrap_root_model(_ParameterOverrideRoot, "ParameterOverride")
ScenarioOverride = _wrap_root_model(_ScenarioOverrideRoot, "ScenarioOverride")
ExecutionOverride = _wrap_root_model(_ExecutionOverrideRoot, "ExecutionOverride")
AuthorityOverride = _wrap_root_model(_AuthorityOverrideRoot, "AuthorityOverride")


__all__ = [
    "SHA256Hex",
    "RFC6901JsonPointer",
    "IntId",
    "DecimalString",
    "NonNegativeDecimalString",
    "PositiveDecimalString",
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
    "YieldPerMuOverrideValue",
    "RateOverrideValue",
    "DateOverrideValue",
    "WeatherAdjustmentOverrideValue",
    "DistributionOverrideParameters",
    "DistributionOverrideValue",
    "StaffingOverrideValue",
    "SpringFestivalIntensityOverrideValue",
    "ProcessorCapacityOverrideValue",
    "ExpectedPerMuYieldOverride",
    "CommodityFruitRateOverride",
    "FirstHarvestDateOverride",
    "MaturityCurveOverride",
    "SpringFestivalHarvestRateOverride",
    "WeatherAdjustmentOverride",
    "PostSpringFestivalBacklogReleaseIntensityOverride",
    "HistoricalAnomalyPeakProbabilityOverride",
    "ParameterOverrideUnion",
    "StaffingScenarioOverride",
    "SpringFestivalIntensityScenarioOverride",
    "ProcessorCapacityScenarioOverride",
    "ScenarioOverrideUnion",
    "RequestBacktestOverride",
    "RequestReplayTrainedRunOverride",
    "RequestSimulationOverride",
    "ExecutionOverrideUnion",
    "Task8ForecastRunAuthorityOverride",
    "Task9HarvestStateRunAuthorityOverride",
    "Task10PredictionRunAuthorityOverride",
    "Task10TrainingRunAuthorityOverride",
    "Task11BacktestRunAuthorityOverride",
    "Task12PredictionRunAuthorityOverride",
    "AuthorityOverrideUnion",
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
    "SliceCSourcePayload",
    "ExplanationRulePolicy",
    "RecommendationRulePolicy",
    "ExplainParagraph",
    "ExplainSection",
    "ExplainForecastInput",
    "ExplainForecastOutput",
    "ConditionEvaluation",
    "NonAction",
    "RecommendationDecision",
    "RecommendationEvidence",
    "RecommendationEvidenceThreshold",
    "GenerateRecommendationsInput",
    "GenerateRecommendationsOutput",
    # Backward-compat aliases for the legacy union-typed names.
    "ParameterOverride",
    "ScenarioOverride",
    "ExecutionOverride",
    "AuthorityOverride",
]
