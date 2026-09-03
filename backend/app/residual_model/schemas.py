from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, cast

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from backend.app.harvest_state.canonical import parse_decimal
from backend.app.residual_model.config import PredictionTargetKind
from backend.app.residual_model.enums import (
    AvailabilityRule,
    EncodingPolicy,
    FeatureDType,
    FeatureSourceDomain,
    LeakageBlockerCode,
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


class FinalTargetPredictionRequest(_BaseModel):
    model_run_id: int
    forecast_cutoff_at: datetime
    prediction_rows: tuple[FinalTargetTrainingManifestRow, ...]


class GovernedGrainIdentityBinding(_BaseModel):
    """Maps governed numeric IDs to S2 physical grain strings."""

    season_id: int
    season: str = Field(min_length=1)
    farm_id: int
    farm: str = Field(min_length=1)
    subfarm_id: int
    subfarm: str = Field(min_length=1)
    variety_id: int
    variety: str = Field(min_length=1)

    def matches_materializable_row(self, row: object) -> bool:
        from backend.app.s2_materialized_dataset.shared.contracts import MaterializableRow

        if not isinstance(row, MaterializableRow):
            return False
        return (
            row.season == self.season
            and row.farm == self.farm
            and row.subfarm == self.subfarm
            and row.variety == self.variety
        )


class FinalTargetPredictionAuthority(_BaseModel):
    prediction_target_kind: PredictionTargetKind
    model_run_id: int
    prediction_run_id: int
    model_family: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    artifact_schema_version: str = Field(min_length=1)
    config_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    training_signature: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    prediction_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    forecast_cutoff_at: datetime
    final_target_rows: tuple[FinalTargetPredictionRow, ...]

    def predictions_by_business_key(self) -> dict[tuple[int, int, int, date, str], str]:
        if self.prediction_target_kind != PredictionTargetKind.FINAL_TARGET_QUANTILE:
            raise ValueError("prediction_target_kind must be FINAL_TARGET_QUANTILE")
        keyed: dict[tuple[int, int, int, date, str], str] = {}
        for row in self.final_target_rows:
            if row.model_run_id != self.model_run_id:
                raise ValueError("mixed model_run_id in final-target prediction authority")
            if row.prediction_run_id != self.prediction_run_id:
                raise ValueError("mixed prediction_run_id in final-target prediction authority")
            if row.prediction_target_kind != PredictionTargetKind.FINAL_TARGET_QUANTILE:
                raise ValueError("legacy prediction row in final-target authority")
            key = (
                row.farm_id,
                row.subfarm_id,
                row.variety_id,
                row.harvest_business_date,
                row.forecast_quantile,
            )
            if key in keyed:
                raise ValueError(f"duplicate final-target prediction business key {key}")
            keyed[key] = str(row.model_harvested_marketable_quantity_kg)
        return keyed


def build_final_target_prediction_authority(
    *,
    training_result: ResidualTrainingExecutionResult,
    prediction_result: ResidualPredictionExecutionResult,
    prediction_run_id: int,
) -> FinalTargetPredictionAuthority:
    """Bind a persisted final-target prediction to its training-run authority."""

    if prediction_result.input_snapshot.get("prediction_target_kind") != (
        PredictionTargetKind.FINAL_TARGET_QUANTILE.value
    ):
        raise ValueError("prediction_result is not a final-target lane result")
    if training_result.input_snapshot.get("prediction_target_kind") != (
        PredictionTargetKind.FINAL_TARGET_QUANTILE.value
    ):
        raise ValueError("training_result is not a final-target lane result")
    model_run_id = cast(int, prediction_result.model_run_id)
    if model_run_id <= 0:
        raise ValueError("final-target prediction authority requires persisted model_run_id")
    if prediction_run_id <= 0:
        raise ValueError("final-target prediction authority requires persisted prediction_run_id")
    forecast_cutoff_raw = prediction_result.input_snapshot.get("forecast_cutoff_at")
    if not isinstance(forecast_cutoff_raw, str):
        raise ValueError("final-target prediction missing forecast_cutoff_at authority")
    forecast_cutoff_at = datetime.fromisoformat(forecast_cutoff_raw)
    stamped_rows = tuple(
        row.model_copy(
            update={
                "model_run_id": model_run_id,
                "prediction_run_id": prediction_run_id,
            }
        )
        for row in prediction_result.final_target_rows
    )
    return FinalTargetPredictionAuthority(
        prediction_target_kind=PredictionTargetKind.FINAL_TARGET_QUANTILE,
        model_run_id=model_run_id,
        prediction_run_id=prediction_run_id,
        model_family=training_result.model_family,
        model_version=training_result.model_version,
        artifact_schema_version=training_result.artifact_schema_version,
        config_hash=training_result.config_hash,
        training_signature=training_result.training_signature,
        manifest_hash=training_result.manifest_hash,
        prediction_hash=prediction_result.prediction_hash,
        forecast_cutoff_at=forecast_cutoff_at,
        final_target_rows=stamped_rows,
    )


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
