from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base

_JSON_VARIANT = JSONB(astext_type=Text()).with_variant(JSON(), "sqlite")
_BIGINT_VARIANT = BigInteger().with_variant(Integer(), "sqlite")


def _sha256_check_sql(column_name: str) -> str:
    stripped = column_name
    for char in "0123456789abcdef":
        stripped = f"replace({stripped}, '{char}', '')"
    return (
        f"length({column_name}) = 64 "
        f"and lower({column_name}) = {column_name} "
        f"and {stripped} = ''"
    )


class ResidualModelTrainingRun(Base):
    __tablename__ = "residual_model_training_run"
    __table_args__ = (
        CheckConstraint(
            "execution_status in ('running', 'completed', 'blocked', 'failed')",
            name="ck_residual_model_training_run_execution_status",
        ),
        CheckConstraint(
            "eligibility_status in ('not_evaluated', 'eligible', 'ineligible')",
            name="ck_residual_model_training_run_eligibility_status",
        ),
        CheckConstraint(
            _sha256_check_sql("training_signature"),
            name="ck_residual_model_training_run_signature",
        ),
        CheckConstraint(
            _sha256_check_sql("config_hash"),
            name="ck_residual_model_training_run_config_hash",
        ),
        CheckConstraint(
            _sha256_check_sql("manifest_hash"),
            name="ck_residual_model_training_run_manifest_hash",
        ),
        CheckConstraint(
            _sha256_check_sql("feature_schema_hash"),
            name="ck_residual_model_training_run_feature_schema_hash",
        ),
        CheckConstraint(
            _sha256_check_sql("canonical_payload_hash"),
            name="ck_residual_model_training_run_payload_hash",
        ),
        UniqueConstraint("training_signature", name="uq_residual_model_training_run_signature"),
        Index(
            "ix_residual_model_training_run_execution_status",
            "execution_status",
        ),
        Index(
            "ix_residual_model_training_run_eligibility_status",
            "eligibility_status",
        ),
    )

    id: Mapped[int] = mapped_column(_BIGINT_VARIANT, primary_key=True, autoincrement=True)
    execution_status: Mapped[str] = mapped_column(Text, nullable=False)
    eligibility_status: Mapped[str] = mapped_column(Text, nullable=False)
    model_family: Mapped[str] = mapped_column(Text, nullable=False)
    model_version: Mapped[str] = mapped_column(Text, nullable=False)
    feature_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    feature_schema_hash: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    training_signature: Mapped[str] = mapped_column(Text, nullable=False)
    config_hash: Mapped[str] = mapped_column(Text, nullable=False)
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)
    manifest_hash: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_snapshot: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)
    feature_audit_summary: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)
    category_encoding_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(
        _JSON_VARIANT,
        nullable=False,
    )
    training_metrics: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)
    validation_metrics: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)
    eligibility_reasons: Mapped[list[str]] = mapped_column(_JSON_VARIANT, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(_JSON_VARIANT, nullable=False)
    blockers: Mapped[list[str]] = mapped_column(_JSON_VARIANT, nullable=False)
    fallback_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)
    canonical_output: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)
    canonical_payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    sample_count: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False, server_default="0")
    distinct_season_count: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        nullable=False,
        server_default="0",
    )
    distinct_factory_count: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        nullable=False,
        server_default="0",
    )
    manifest_row_count: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        nullable=False,
        server_default="0",
    )
    expected_artifact_count: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        nullable=False,
        server_default="0",
    )
    python_version: Mapped[str] = mapped_column(Text, nullable=False)
    numpy_version: Mapped[str] = mapped_column(Text, nullable=False)
    sklearn_version: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    typed_attempt: Mapped[dict[str, Any] | None] = mapped_column(
        _JSON_VARIANT, nullable=True, default=None
    )


class ResidualModelManifestRow(Base):
    __tablename__ = "residual_model_manifest_row"
    __table_args__ = (
        CheckConstraint(
            "split in ('train', 'validation', 'test')",
            name="ck_residual_model_manifest_row_split",
        ),
        CheckConstraint(
            _sha256_check_sql("task9_result_hash"),
            name="ck_residual_model_manifest_row_task9_hash",
        ),
        CheckConstraint(
            _sha256_check_sql("feature_vector_hash"),
            name="ck_residual_model_manifest_row_vector_hash",
        ),
        CheckConstraint(
            _sha256_check_sql("feature_visibility_audit_hash"),
            name="ck_residual_model_manifest_row_audit_hash",
        ),
        CheckConstraint(
            _sha256_check_sql("label_actual_config_hash"),
            name="ck_residual_model_manifest_row_label_config_hash",
        ),
        CheckConstraint(
            _sha256_check_sql("feature_actual_config_hash"),
            name="ck_residual_model_manifest_row_feature_config_hash",
        ),
        CheckConstraint(
            "row_index > 0",
            name="ck_residual_model_manifest_row_row_index",
        ),
        CheckConstraint(
            "forecast_horizon_days >= 0",
            name="ck_residual_model_manifest_row_forecast_horizon",
        ),
        CheckConstraint(
            "sample_weight >= 0",
            name="ck_residual_model_manifest_row_sample_weight",
        ),
        UniqueConstraint(
            "training_run_id",
            "row_index",
            name="uq_residual_model_manifest_row_run_index",
        ),
        Index("ix_residual_model_manifest_row_run_id", "training_run_id"),
    )

    id: Mapped[int] = mapped_column(_BIGINT_VARIANT, primary_key=True, autoincrement=True)
    training_run_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey(
            "residual_model_training_run.id",
            name="fk_residual_model_manifest_row_training_run_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    row_index: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    split: Mapped[str] = mapped_column(Text, nullable=False)
    include: Mapped[bool] = mapped_column(nullable=False)
    season_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey(
            "dim_season.id",
            name="fk_residual_model_manifest_row_season_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    destination_factory_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey(
            "dim_factory.id",
            name="fk_residual_model_manifest_row_factory_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    task9_run_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey(
            "harvest_state_run.id",
            name="fk_residual_model_manifest_row_task9_run_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    task9_result_hash: Mapped[str] = mapped_column(Text, nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    target_arrival_local_date: Mapped[date] = mapped_column(Date, nullable=False)
    forecast_horizon_days: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    label_analytics_build_run_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey(
            "analytics_build_run.id",
            name="fk_residual_model_manifest_row_label_analytics_build_run_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    label_actual_source_max_raw_id: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    label_actual_aggregation_version: Mapped[str] = mapped_column(Text, nullable=False)
    label_actual_config_hash: Mapped[str] = mapped_column(Text, nullable=False)
    label_actual_source_cutoff: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    feature_analytics_build_run_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey(
            "analytics_build_run.id",
            name="fk_residual_model_manifest_row_feature_analytics_build_run_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    feature_actual_source_max_raw_id: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    feature_actual_aggregation_version: Mapped[str] = mapped_column(Text, nullable=False)
    feature_actual_config_hash: Mapped[str] = mapped_column(Text, nullable=False)
    feature_actual_source_cutoff: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    observed_effective_receipt_kg: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    structural_p50_kg: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    structural_p80_kg: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    structural_p90_kg: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    residual_label_kg: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    sample_weight: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    feature_vector_hash: Mapped[str] = mapped_column(Text, nullable=False)
    feature_visibility_audit_hash: Mapped[str] = mapped_column(Text, nullable=False)
    exclusion_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_refs: Mapped[list[str]] = mapped_column(_JSON_VARIANT, nullable=False)
    row_payload: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)


class ResidualModelArtifact(Base):
    __tablename__ = "residual_model_artifact"
    __table_args__ = (
        CheckConstraint(
            "quantile_label in ('P50', 'P80', 'P90')",
            name="ck_residual_model_artifact_quantile_label",
        ),
        CheckConstraint(
            _sha256_check_sql("artifact_sha256"),
            name="ck_residual_model_artifact_sha256",
        ),
        CheckConstraint(
            _sha256_check_sql("feature_schema_hash"),
            name="ck_residual_model_artifact_feature_schema_hash",
        ),
        CheckConstraint(
            _sha256_check_sql("config_hash"),
            name="ck_residual_model_artifact_config_hash",
        ),
        UniqueConstraint(
            "training_run_id",
            "quantile_label",
            name="uq_residual_model_artifact_run_quantile",
        ),
        UniqueConstraint("artifact_sha256", name="uq_residual_model_artifact_sha256"),
        Index("ix_residual_model_artifact_training_run_id", "training_run_id"),
    )

    id: Mapped[int] = mapped_column(_BIGINT_VARIANT, primary_key=True, autoincrement=True)
    training_run_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey(
            "residual_model_training_run.id",
            name="fk_residual_model_artifact_training_run_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    quantile_label: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_format: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    estimator_type: Mapped[str] = mapped_column(Text, nullable=False)
    loss_name: Mapped[str] = mapped_column(Text, nullable=False)
    quantile_value: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    artifact_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    feature_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    feature_schema_hash: Mapped[str] = mapped_column(Text, nullable=False)
    config_hash: Mapped[str] = mapped_column(Text, nullable=False)
    trusted_internal_source: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="true",
    )
    artifact_metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        _JSON_VARIANT,
        nullable=False,
    )
    python_version: Mapped[str] = mapped_column(Text, nullable=False)
    numpy_version: Mapped[str] = mapped_column(Text, nullable=False)
    sklearn_version: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ResidualModelPredictionRun(Base):
    __tablename__ = "residual_model_prediction_run"
    __table_args__ = (
        CheckConstraint(
            "execution_status in ('completed', 'blocked', 'failed')",
            name="ck_residual_model_prediction_run_execution_status",
        ),
        CheckConstraint(
            "mode in ('residual_corrected', 'structural_only', 'blocked')",
            name="ck_residual_model_prediction_run_mode",
        ),
        CheckConstraint(
            _sha256_check_sql("task9_result_hash"),
            name="ck_residual_model_prediction_run_task9_hash",
        ),
        CheckConstraint(
            _sha256_check_sql("config_hash"),
            name="ck_residual_model_prediction_run_config_hash",
        ),
        CheckConstraint(
            _sha256_check_sql("feature_schema_hash"),
            name="ck_residual_model_prediction_run_feature_schema_hash",
        ),
        CheckConstraint(
            _sha256_check_sql("prediction_input_signature"),
            name="ck_residual_model_prediction_run_input_signature",
        ),
        CheckConstraint(
            _sha256_check_sql("prediction_hash"),
            name="ck_residual_model_prediction_run_prediction_hash",
        ),
        CheckConstraint(
            _sha256_check_sql("canonical_payload_hash"),
            name="ck_residual_model_prediction_run_payload_hash",
        ),
        UniqueConstraint(
            "prediction_input_signature",
            name="uq_residual_model_prediction_run_input_signature",
        ),
        Index("ix_residual_model_prediction_run_execution_status", "execution_status"),
        Index("ix_residual_model_prediction_run_task9_run_id", "task9_run_id"),
    )

    id: Mapped[int] = mapped_column(_BIGINT_VARIANT, primary_key=True, autoincrement=True)
    training_run_id: Mapped[int | None] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey(
            "residual_model_training_run.id",
            name="fk_residual_model_prediction_run_training_run_id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    task9_run_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey(
            "harvest_state_run.id",
            name="fk_residual_model_prediction_run_task9_run_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    task9_result_hash: Mapped[str] = mapped_column(Text, nullable=False)
    execution_status: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    config_hash: Mapped[str] = mapped_column(Text, nullable=False)
    feature_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    feature_schema_hash: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_hashes: Mapped[list[str]] = mapped_column(_JSON_VARIANT, nullable=False)
    prediction_input_signature: Mapped[str] = mapped_column(Text, nullable=False)
    prediction_hash: Mapped[str] = mapped_column(Text, nullable=False)
    feature_audit: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(_JSON_VARIANT, nullable=False)
    blockers: Mapped[list[str]] = mapped_column(_JSON_VARIANT, nullable=False)
    fallback_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_prediction_row_count: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        nullable=False,
        server_default="0",
    )
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)
    canonical_output: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)
    canonical_payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    typed_attempt: Mapped[dict[str, Any] | None] = mapped_column(
        _JSON_VARIANT, nullable=True, default=None
    )


class ResidualModelPredictionRow(Base):
    __tablename__ = "residual_model_prediction_row"
    __table_args__ = (
        CheckConstraint(
            _sha256_check_sql("task9_result_hash"),
            name="ck_residual_model_prediction_row_task9_hash",
        ),
        CheckConstraint(
            _sha256_check_sql("feature_vector_hash"),
            name="ck_residual_model_prediction_row_vector_hash",
        ),
        CheckConstraint(
            _sha256_check_sql("feature_audit_hash"),
            name="ck_residual_model_prediction_row_audit_hash",
        ),
        CheckConstraint(
            _sha256_check_sql("prediction_row_hash"),
            name="ck_residual_model_prediction_row_hash",
        ),
        CheckConstraint(
            "corrected_p50_kg >= 0 and corrected_p80_kg >= 0 and corrected_p90_kg >= 0",
            name="ck_residual_model_prediction_row_nonnegative",
        ),
        CheckConstraint(
            "corrected_p50_kg <= corrected_p80_kg and corrected_p80_kg <= corrected_p90_kg",
            name="ck_residual_model_prediction_row_monotonic",
        ),
        CheckConstraint(
            "forecast_horizon_days >= 0",
            name="ck_residual_model_prediction_row_forecast_horizon",
        ),
        CheckConstraint(
            (
                "mode != 'structural_only' or "
                "(raw_residual_p50_kg = 0 and "
                "raw_residual_p80_kg = 0 and "
                "raw_residual_p90_kg = 0)"
            ),
            name="ck_residual_model_prediction_row_structural_only",
        ),
        UniqueConstraint(
            "prediction_run_id",
            "destination_factory_id",
            "arrival_local_date",
            name="uq_residual_model_prediction_row_run_factory_date",
        ),
        Index("ix_residual_model_prediction_row_prediction_run_id", "prediction_run_id"),
    )

    id: Mapped[int] = mapped_column(_BIGINT_VARIANT, primary_key=True, autoincrement=True)
    prediction_run_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey(
            "residual_model_prediction_run.id",
            name="fk_residual_model_prediction_row_prediction_run_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    model_run_id: Mapped[int | None] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey(
            "residual_model_training_run.id",
            name="fk_residual_model_prediction_row_model_run_id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    task9_run_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey(
            "harvest_state_run.id",
            name="fk_residual_model_prediction_row_task9_run_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    task9_result_hash: Mapped[str] = mapped_column(Text, nullable=False)
    destination_factory_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey(
            "dim_factory.id",
            name="fk_residual_model_prediction_row_factory_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    arrival_local_date: Mapped[date] = mapped_column(Date, nullable=False)
    forecast_horizon_days: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    structural_p50_kg: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    structural_p80_kg: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    structural_p90_kg: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    raw_residual_p50_kg: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    raw_residual_p80_kg: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    raw_residual_p90_kg: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    corrected_raw_p50_kg: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    corrected_raw_p80_kg: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    corrected_raw_p90_kg: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    corrected_p50_kg: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    corrected_p80_kg: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    corrected_p90_kg: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    nonnegative_projection_applied: Mapped[bool] = mapped_column(nullable=False)
    quantile_projection_applied: Mapped[bool] = mapped_column(nullable=False)
    projection_reasons: Mapped[list[str]] = mapped_column(_JSON_VARIANT, nullable=False)
    feature_vector_hash: Mapped[str] = mapped_column(Text, nullable=False)
    feature_audit_hash: Mapped[str] = mapped_column(Text, nullable=False)
    prediction_row_hash: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    fallback_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
