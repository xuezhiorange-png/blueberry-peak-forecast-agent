from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from backend.app.harvest_state.canonical import parse_decimal
from backend.app.residual_model.enums import (
    AvailabilityRule,
    EncodingPolicy,
    FeatureDType,
    FeatureSourceDomain,
    LeakageBlockerCode,
    MissingPolicy,
    PredictionTargetKind,
    ProjectionReason,
    ResidualEligibilityStatus,
    ResidualExecutionStatus,
    ResidualPredictionMode,
    ResidualSplit,
)

BusinessDecimal = Annotated[Decimal, BeforeValidator(parse_decimal)]
NonNegativeBusinessDecimal = Annotated[
    Decimal,
    BeforeValidator(parse_decimal),
    Field(ge=Decimal("0")),
]


class _BaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FeatureDefinition(_BaseModel):
    feature_name: str = Field(min_length=1)
    dtype: FeatureDType
    source_domain: FeatureSourceDomain
    source_field: str = Field(min_length=1)
    availability_rule: AvailabilityRule
    missing_policy: MissingPolicy
    encoding_policy: EncodingPolicy
    allow_for_training: bool
    allow_for_prediction: bool
    provenance_requirement: str = Field(min_length=1)


class FeatureValue(_BaseModel):
    feature_name: str = Field(min_length=1)
    value: Decimal | int | str | bool | None
    known_at: datetime
    source_ref: dict[str, Any]
    source_version: str = Field(min_length=1)
    source_available_at: datetime
    observation_date: date | None = None


class FeatureVisibilityIssue(_BaseModel):
    code: LeakageBlockerCode
    feature_name: str = Field(min_length=1)
    detail: str = Field(min_length=1)


class FeatureVisibilityAudit(_BaseModel):
    status: ResidualExecutionStatus
    feature_count: int
    visible_feature_count: int
    blocked_feature_count: int
    missing_feature_count: int
    unknown_feature_count: int
    blockers: list[FeatureVisibilityIssue]
    warnings: list[str]
    audit_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class ProjectionResult(_BaseModel):
    raw_p50_kg: BusinessDecimal
    raw_p80_kg: BusinessDecimal
    raw_p90_kg: BusinessDecimal
    corrected_p50_kg: NonNegativeBusinessDecimal
    corrected_p80_kg: NonNegativeBusinessDecimal
    corrected_p90_kg: NonNegativeBusinessDecimal
    nonnegative_projection_applied: bool
    quantile_projection_applied: bool
    projection_reasons: list[ProjectionReason]
    raw_crossing_count: int = 0
    final_crossing_count: int = 0
    nonnegative_projection_count: int = 0


class AnalyticsActualSnapshot(_BaseModel):
    build_run_id: int
    source_max_raw_id: int
    aggregation_version: str = Field(min_length=1)
    config_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_cutoff: datetime


class ResidualTrainingManifestRow(_BaseModel):
    season_id: int
    destination_factory_id: int
    task9_run_id: int
    task9_result_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    as_of_date: date
    target_arrival_local_date: date
    forecast_horizon_days: int
    label_actual_snapshot: AnalyticsActualSnapshot
    feature_actual_snapshot: AnalyticsActualSnapshot
    observed_effective_receipt_kg: NonNegativeBusinessDecimal
    structural_p50_kg: NonNegativeBusinessDecimal
    structural_p80_kg: NonNegativeBusinessDecimal
    structural_p90_kg: NonNegativeBusinessDecimal
    residual_label_kg: BusinessDecimal
    feature_values: tuple[FeatureValue, ...]
    feature_visibility_audit: FeatureVisibilityAudit | None = None
    feature_vector_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    feature_visibility_audit_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    split: ResidualSplit
    include: bool
    sample_weight: NonNegativeBusinessDecimal
    exclusion_reason: str | None = None
    source_refs: tuple[str, ...]


class FinalTargetActualsAuthoritySnapshot(_BaseModel):
    authority: str = Field(min_length=1)
    partition_identity: str = Field(min_length=1)
    source_row_identity: str = Field(min_length=1)
    lineage_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class FinalTargetTrainingManifestRow(_BaseModel):
    """Farm-harvest grain training row for direct final-target quantile modeling."""

    season_id: int
    farm_id: int
    subfarm_id: int
    variety_id: int
    harvest_business_date: date
    forecast_cutoff_at: datetime
    forecast_horizon_days: int
    actual_harvest_quantity_kg: NonNegativeBusinessDecimal
    actuals_authority: FinalTargetActualsAuthoritySnapshot
    feature_values: tuple[FeatureValue, ...]
    feature_visibility_audit: FeatureVisibilityAudit | None = None
    feature_vector_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    feature_visibility_audit_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    split: ResidualSplit
    include: bool
    sample_weight: NonNegativeBusinessDecimal
    exclusion_reason: str | None = None
    source_refs: tuple[str, ...]


class FinalTargetPredictionRow(_BaseModel):
    model_run_id: int
    prediction_run_id: int
    season_id: int
    farm_id: int
    subfarm_id: int
    variety_id: int
    harvest_business_date: date
    forecast_cutoff_at: datetime
    forecast_horizon_days: int
    forecast_quantile: str = Field(pattern=r"^P(50|80|90)$")
    prediction_target_kind: PredictionTargetKind
    raw_p50_kg: BusinessDecimal
    raw_p80_kg: BusinessDecimal
    raw_p90_kg: BusinessDecimal
    corrected_p50_kg: NonNegativeBusinessDecimal
    corrected_p80_kg: NonNegativeBusinessDecimal
    corrected_p90_kg: NonNegativeBusinessDecimal
    model_harvested_marketable_quantity_kg: NonNegativeBusinessDecimal
    nonnegative_projection_applied: bool
    quantile_projection_applied: bool
    projection_reasons: list[ProjectionReason]
    raw_crossing_count: int = 0
    final_crossing_count: int = 0
    feature_vector_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    feature_audit_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    prediction_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    fallback_reason: str | None = None


class ResidualTrainingSampleSpec(_BaseModel):
    task9_run_id: int
    label_analytics_build_run_id: int
    feature_analytics_build_run_id: int
    split: ResidualSplit
    include: bool = True
    sample_weight: NonNegativeBusinessDecimal = Decimal("1")
    exclusion_reason: str | None = None
    supplemental_feature_values: tuple[FeatureValue, ...] = ()


class ResidualPredictionRequest(_BaseModel):
    model_run_id: int
    task9_run_id: int
    feature_analytics_build_run_id: int | None = None
    supplemental_feature_values: tuple[FeatureValue, ...] = ()


class ResidualTrainingSummary(_BaseModel):
    execution_status: ResidualExecutionStatus
    eligibility_status: ResidualEligibilityStatus
    model_family: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    feature_schema_version: str = Field(min_length=1)
    artifact_schema_version: str = Field(min_length=1)
    config_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class CategoryEncoding(_BaseModel):
    feature_name: str = Field(min_length=1)
    ordered_known_categories: list[str]
    unknown_bucket_code: int
    missing_bucket_code: int
    encoding_version: str = Field(min_length=1)


class ResidualArtifactMetadata(_BaseModel):
    quantile_label: str = Field(pattern=r"^P(50|80|90)$")
    artifact_schema_version: str = Field(min_length=1)
    model_family: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    feature_schema_version: str = Field(min_length=1)
    feature_schema_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    category_encoding_version: str = Field(min_length=1)
    projection_version: str = Field(min_length=1)
    config_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    training_signature: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    quantiles: list[float]
    prediction_target_kind: PredictionTargetKind = PredictionTargetKind.LEGACY_RESIDUAL_CORRECTION
    python_version: str = Field(min_length=1)
    numpy_version: str = Field(min_length=1)
    sklearn_version: str = Field(min_length=1)
    created_by_service_version: str = Field(min_length=1)
    binary_format: str = Field(min_length=1)
    binary_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    estimator_parameters: dict[str, Any]
    category_encodings: list[CategoryEncoding] = Field(default_factory=list)


class PersistableResidualArtifact(_BaseModel):
    quantile_label: str = Field(pattern=r"^P(50|80|90)$")
    artifact_bytes: bytes
    metadata: ResidualArtifactMetadata


class ResidualTrainingExecutionResult(_BaseModel):
    execution_status: ResidualExecutionStatus
    eligibility_status: ResidualEligibilityStatus
    model_family: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    feature_schema_version: str = Field(min_length=1)
    artifact_schema_version: str = Field(min_length=1)
    training_signature: str = Field(pattern=r"^[0-9a-f]{64}$")
    config_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    sample_count: int
    distinct_season_count: int
    distinct_factory_count: int
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    feature_audit_summary: dict[str, Any]
    metrics: dict[str, Any]
    eligibility_reasons: tuple[str, ...]
    input_snapshot: dict[str, Any]
    artifacts: tuple[PersistableResidualArtifact, ...] = ()


class ResidualPredictionExecutionResult(_BaseModel):
    execution_status: ResidualExecutionStatus
    mode: ResidualPredictionMode
    model_run_id: int | None = None
    task9_run_id: int | None = None
    task9_result_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    config_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    prediction_input_signature: str = Field(pattern=r"^[0-9a-f]{64}$")
    prediction_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    fallback_reason: str | None = None
    rows: tuple[ResidualPredictionRow, ...]
    final_target_rows: tuple[FinalTargetPredictionRow, ...] = ()
    input_snapshot: dict[str, Any]


class ResidualPredictionRow(_BaseModel):
    model_run_id: int
    prediction_run_id: int
    task9_run_id: int
    task9_result_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    destination_factory_id: int
    arrival_local_date: date
    forecast_horizon_days: int
    structural_p50_kg: NonNegativeBusinessDecimal
    structural_p80_kg: NonNegativeBusinessDecimal
    structural_p90_kg: NonNegativeBusinessDecimal
    raw_residual_p50_kg: BusinessDecimal
    raw_residual_p80_kg: BusinessDecimal
    raw_residual_p90_kg: BusinessDecimal
    corrected_raw_p50_kg: BusinessDecimal
    corrected_raw_p80_kg: BusinessDecimal
    corrected_raw_p90_kg: BusinessDecimal
    corrected_p50_kg: NonNegativeBusinessDecimal
    corrected_p80_kg: NonNegativeBusinessDecimal
    corrected_p90_kg: NonNegativeBusinessDecimal
    nonnegative_projection_applied: bool
    quantile_projection_applied: bool
    projection_reasons: list[ProjectionReason]
    feature_vector_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    feature_audit_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    prediction_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    mode: ResidualPredictionMode
    fallback_reason: str | None = None
