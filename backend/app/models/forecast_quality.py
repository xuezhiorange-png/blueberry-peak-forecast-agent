"""Round B forecast-quality persistence models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base

_BIGINT = BigInteger().with_variant(Integer(), "sqlite")
_JSON = JSON().with_variant(JSONB(astext_type=Text()), "postgresql")
PERSISTENCE_SCHEMA_VERSION = "v0.2-s3-quality-persistence-v1"
ROUND_C_PERSISTENCE_SCHEMA_VERSION = "v0.2-s3-quality-persistence-v2"
COMPARISON_POLICY_VERSION = "v0.2-s3-comparison-policy-v1"
COMPARISON_RESULT_SCHEMA_VERSION = "v0.2-s3-comparison-result-v1"
COMPARISON_RESULT_SET_SCHEMA_VERSION = "v0.2-s3-comparison-result-set-v2"
LEGACY_COMPARISON_RESULT_SET_SCHEMA_VERSION = "v0.2-s3-comparison-result-set-v1"


def _sha256_check(column: str, name: str) -> CheckConstraint:
    stripped = column
    for char in "0123456789abcdef":
        stripped = f"replace({stripped}, '{char}', '')"
    return CheckConstraint(
        f"length({column}) = 64 AND lower({column}) = {column} AND {stripped} = ''",
        name=name,
    )


class QualityEvaluationRunModel(Base):
    __tablename__ = "quality_evaluation_run"
    __table_args__ = (
        UniqueConstraint("evaluation_request_hash", name="uq_quality_evaluation_run_request"),
        UniqueConstraint("canonical_hash", name="uq_quality_evaluation_run_canonical_hash"),
        _sha256_check("evaluation_request_hash", "ck_quality_evaluation_run_request_sha256"),
        _sha256_check("canonical_hash", "ck_quality_evaluation_run_canonical_sha256"),
        CheckConstraint(
            "schema_version IN ('v0.2-s3-quality-persistence-v1', "
            "'v0.2-s3-quality-persistence-v2')",
            name="ck_quality_evaluation_run_schema_version",
        ),
        CheckConstraint(
            "(schema_version = 'v0.2-s3-quality-persistence-v1' AND "
            "comparison_policy_version IS NULL) OR "
            "(schema_version = 'v0.2-s3-quality-persistence-v2' AND "
            "comparison_policy_version = 'v0.2-s3-comparison-policy-v1')",
            name="ck_quality_evaluation_run_comparison_policy_version",
        ),
        CheckConstraint("status = 'COMPLETE'", name="ck_quality_evaluation_run_status"),
    )

    id: Mapped[int] = mapped_column(_BIGINT, primary_key=True, autoincrement=True)
    schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    evaluation_request_hash: Mapped[str] = mapped_column(Text, nullable=False)
    s2_run_identity: Mapped[str] = mapped_column(Text, nullable=False)
    s2_manifest_identity: Mapped[str] = mapped_column(Text, nullable=False)
    s2_binding_row_set_hash: Mapped[str] = mapped_column(Text, nullable=False)
    metric_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    baseline_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    comparison_policy_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_payload: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    canonical_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class QualityMetricResultModel(Base):
    __tablename__ = "quality_metric_result"
    __table_args__ = (
        UniqueConstraint(
            "quality_evaluation_run_id",
            "metric_result_key_hash",
            name="uq_quality_metric_result_run_key",
        ),
        UniqueConstraint(
            "quality_evaluation_run_id",
            "canonical_hash",
            name="uq_quality_metric_result_run_canonical_hash",
        ),
        _sha256_check("metric_result_key_hash", "ck_quality_metric_result_key_sha256"),
        _sha256_check("canonical_hash", "ck_quality_metric_result_canonical_sha256"),
        CheckConstraint(
            "metric_status <> '' AND reason_code <> ''",
            name="ck_quality_metric_result_status_reason_nonempty",
        ),
        Index("ix_quality_metric_result_run_id", "quality_evaluation_run_id"),
    )

    id: Mapped[int] = mapped_column(_BIGINT, primary_key=True, autoincrement=True)
    quality_evaluation_run_id: Mapped[int] = mapped_column(
        _BIGINT,
        ForeignKey(
            "quality_evaluation_run.id",
            name="fk_quality_metric_result_run",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    metric_result_key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    metric_name: Mapped[str] = mapped_column(Text, nullable=False)
    metric_status: Mapped[str] = mapped_column(Text, nullable=False)
    reason_code: Mapped[str] = mapped_column(Text, nullable=False)
    metric_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    numerator: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    denominator: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    breakdown_identity: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    canonical_payload: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    canonical_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class QualityBreakdownResultModel(Base):
    __tablename__ = "quality_breakdown_result"
    __table_args__ = (
        UniqueConstraint(
            "quality_evaluation_run_id",
            "breakdown_key_hash",
            name="uq_quality_breakdown_result_run_key",
        ),
        UniqueConstraint(
            "quality_evaluation_run_id",
            "canonical_hash",
            name="uq_quality_breakdown_result_run_canonical_hash",
        ),
        _sha256_check("breakdown_key_hash", "ck_quality_breakdown_result_key_sha256"),
        _sha256_check("canonical_hash", "ck_quality_breakdown_result_canonical_sha256"),
        CheckConstraint(
            "s2_comparable_row_count >= 0 AND s2_excluded_row_count >= 0 "
            "AND s2_not_computable_row_count >= 0",
            name="ck_quality_breakdown_result_counts_nonnegative",
        ),
        CheckConstraint(
            "coverage_ratio IS NULL OR (coverage_ratio >= 0 AND coverage_ratio <= 1)",
            name="ck_quality_breakdown_result_coverage_range",
        ),
        Index("ix_quality_breakdown_result_run_id", "quality_evaluation_run_id"),
    )

    id: Mapped[int] = mapped_column(_BIGINT, primary_key=True, autoincrement=True)
    quality_evaluation_run_id: Mapped[int] = mapped_column(
        _BIGINT,
        ForeignKey(
            "quality_evaluation_run.id",
            name="fk_quality_breakdown_result_run",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    breakdown_key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    breakdown_identity: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    metric_status: Mapped[str] = mapped_column(Text, nullable=False)
    reason_code: Mapped[str] = mapped_column(Text, nullable=False)
    s2_comparable_row_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    s2_excluded_row_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    s2_not_computable_row_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    coverage_ratio: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    metric_values: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    canonical_payload: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    canonical_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class NaiveBaselineRunModel(Base):
    __tablename__ = "naive_baseline_run"
    __table_args__ = (
        UniqueConstraint(
            "quality_evaluation_run_id",
            "baseline_request_hash",
            name="uq_naive_baseline_run_request",
        ),
        UniqueConstraint(
            "quality_evaluation_run_id",
            "baseline_result_hash",
            name="uq_naive_baseline_run_result",
        ),
        _sha256_check("baseline_request_hash", "ck_naive_baseline_request_sha256"),
        _sha256_check("baseline_result_hash", "ck_naive_baseline_result_sha256"),
        _sha256_check("canonical_hash", "ck_naive_baseline_canonical_sha256"),
        Index("ix_naive_baseline_run_run_id", "quality_evaluation_run_id"),
    )

    id: Mapped[int] = mapped_column(_BIGINT, primary_key=True, autoincrement=True)
    quality_evaluation_run_id: Mapped[int] = mapped_column(
        _BIGINT,
        ForeignKey(
            "quality_evaluation_run.id",
            name="fk_naive_baseline_run_run",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    baseline_request_hash: Mapped[str] = mapped_column(Text, nullable=False)
    baseline_result_hash: Mapped[str] = mapped_column(Text, nullable=False)
    baseline_source_snapshot_identity: Mapped[str] = mapped_column(Text, nullable=False)
    baseline_source_snapshot_hash: Mapped[str] = mapped_column(Text, nullable=False)
    baseline_source_row_set_hash: Mapped[str] = mapped_column(Text, nullable=False)
    visibility_manifest_hash: Mapped[str] = mapped_column(Text, nullable=False)
    baseline_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    metric_status: Mapped[str] = mapped_column(Text, nullable=False)
    reason_code: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_payload: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    canonical_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ModelBaselineComparisonModel(Base):
    __tablename__ = "model_baseline_comparison"
    __table_args__ = (
        UniqueConstraint(
            "quality_evaluation_run_id",
            "comparison_key_hash",
            name="uq_model_baseline_comparison_run_key",
        ),
        UniqueConstraint(
            "quality_evaluation_run_id",
            "canonical_hash",
            name="uq_model_baseline_comparison_run_canonical_hash",
        ),
        _sha256_check("comparison_key_hash", "ck_model_baseline_comparison_key_sha256"),
        _sha256_check("canonical_hash", "ck_model_baseline_comparison_canonical_sha256"),
        CheckConstraint(
            "schema_version = 'v0.2-s3-quality-persistence-v2'",
            name="ck_model_baseline_comparison_schema_version_v2",
        ),
        CheckConstraint(
            "comparison_policy_version = 'v0.2-s3-comparison-policy-v1'",
            name="ck_model_baseline_comparison_policy_version_v2",
        ),
        CheckConstraint(
            "comparison_name IN ('daily_mae_delta', 'daily_wape_delta', "
            "'daily_smape_delta', 'daily_mape_delta', "
            "'absolute_bias_magnitude_delta', 'signed_bias_delta', "
            "'p80_coverage_delta', 'p90_coverage_delta', "
            "'baseline_p80_p90_peak_comparison', 'interval_width_delta')",
            name="ck_model_baseline_comparison_name_vocabulary",
        ),
        CheckConstraint(
            "comparison_availability IN ('AVAILABLE', 'BLOCKED')",
            name="ck_model_baseline_comparison_availability_vocabulary",
        ),
        CheckConstraint(
            "metric_status IN ('COMPUTED', 'COMPARED', 'NOT_COMPUTABLE', "
            "'NOT_VERIFIED', 'INSUFFICIENT_SAMPLE')",
            name="ck_model_baseline_comparison_metric_status_vocabulary",
        ),
        CheckConstraint(
            "reason_code IN ('NONE', 'NO_MAPE_ELIGIBLE_ROWS', 'MAPE_DENOMINATOR_ZERO', "
            "'WAPE_DENOMINATOR_ZERO', 'RELATIVE_BIAS_DENOMINATOR_ZERO', "
            "'NO_COMPLETE_7DAY_WINDOW', 'QUANTILE_SEMANTICS_NOT_VERIFIED', "
            "'BELOW_MINIMUM', 'BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED', "
            "'COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING', "
            "'SIGNED_DIRECTION_ONLY', 'PREDICTION_INTERVAL_LOWER_BOUND_UNAVAILABLE', "
            "'NO_PRIOR_SEASON_ANALOG_DAY', 'NO_PRIOR_SEASON_ANALOG_ACTUAL', "
            "'BASELINE_SOURCE_NOT_VISIBLE_AT_CURRENT_FORECAST_CUTOFF', 'NO_S2_BINDING_ROWS')",
            name="ck_model_baseline_comparison_reason_code_vocabulary",
        ),
        CheckConstraint(
            "external_blocker IS NULL",
            name="ck_model_baseline_comparison_external_blocker_vocabulary",
        ),
        CheckConstraint(
            "frozen_limitation IS NULL OR frozen_limitation IN "
            "('BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED', "
            "'PREDICTION_INTERVAL_LOWER_BOUND_UNAVAILABLE')",
            name="ck_model_baseline_comparison_frozen_limitation_vocabulary",
        ),
        CheckConstraint(
            "(comparison_availability = 'AVAILABLE' AND frozen_limitation IS NULL) OR "
            "(comparison_availability = 'BLOCKED' AND frozen_limitation = reason_code)",
            name="ck_model_baseline_comparison_blocker_limitation_consistency",
        ),
        CheckConstraint(
            "(metric_status = 'NOT_COMPUTABLE' AND model_value IS NULL AND "
            "baseline_value IS NULL AND delta_value IS NULL) OR "
            "(metric_status <> 'NOT_COMPUTABLE' AND model_value IS NOT NULL AND "
            "baseline_value IS NOT NULL AND delta_value IS NOT NULL)",
            name="ck_model_baseline_comparison_conditional_values",
        ),
        Index("ix_model_baseline_comparison_run_id", "quality_evaluation_run_id"),
    )

    id: Mapped[int] = mapped_column(_BIGINT, primary_key=True, autoincrement=True)
    quality_evaluation_run_id: Mapped[int] = mapped_column(
        _BIGINT,
        ForeignKey(
            "quality_evaluation_run.id",
            name="fk_model_baseline_comparison_run",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    comparison_key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    comparison_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    comparison_name: Mapped[str] = mapped_column(Text, nullable=False)
    comparison_availability: Mapped[str] = mapped_column(Text, nullable=False)
    metric_status: Mapped[str] = mapped_column(Text, nullable=False)
    reason_code: Mapped[str] = mapped_column(Text, nullable=False)
    external_blocker: Mapped[str | None] = mapped_column(Text, nullable=True)
    frozen_limitation: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_identity: Mapped[str] = mapped_column(Text, nullable=False)
    baseline_member_identity_set: Mapped[list[dict[str, Any]]] = mapped_column(
        _JSON, nullable=False
    )
    baseline_member_set_hash: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_breakdown_identity: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    forecast_horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    model_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    baseline_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    delta_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    model_input_row_count: Mapped[int] = mapped_column(_BIGINT, nullable=False)
    baseline_input_row_count: Mapped[int] = mapped_column(_BIGINT, nullable=False)
    common_comparable_row_count: Mapped[int] = mapped_column(_BIGINT, nullable=False)
    model_only_row_count: Mapped[int] = mapped_column(_BIGINT, nullable=False)
    baseline_only_row_count: Mapped[int] = mapped_column(_BIGINT, nullable=False)
    excluded_row_count: Mapped[int] = mapped_column(_BIGINT, nullable=False)
    not_computable_row_count: Mapped[int] = mapped_column(_BIGINT, nullable=False)
    canonical_payload: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    canonical_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class QualityEvaluationManifestModel(Base):
    __tablename__ = "quality_evaluation_manifest"
    __table_args__ = (
        UniqueConstraint("quality_evaluation_run_id", name="uq_quality_manifest_run"),
        UniqueConstraint("manifest_hash", name="uq_quality_manifest_hash"),
        _sha256_check("evaluation_request_hash", "ck_quality_manifest_request_sha256"),
        _sha256_check("evaluation_instance_hash", "ck_quality_manifest_instance_sha256"),
        _sha256_check("metric_result_set_hash", "ck_quality_manifest_metric_set_sha256"),
        _sha256_check("breakdown_result_set_hash", "ck_quality_manifest_breakdown_set_sha256"),
        _sha256_check("baseline_result_set_hash", "ck_quality_manifest_baseline_set_sha256"),
        _sha256_check("comparison_result_set_hash", "ck_quality_manifest_comparison_set_sha256"),
        _sha256_check("manifest_hash", "ck_quality_manifest_hash_sha256"),
        CheckConstraint(
            "(schema_version = 'v0.2-s3-quality-persistence-v1' AND "
            "comparison_policy_version IS NULL AND comparison_result_schema_version IS NULL "
            "AND comparison_result_set_schema_version = 'v0.2-s3-comparison-result-set-v1') OR "
            "(schema_version = 'v0.2-s3-quality-persistence-v2' AND "
            "comparison_policy_version = 'v0.2-s3-comparison-policy-v1' AND "
            "comparison_result_schema_version = 'v0.2-s3-comparison-result-v1' AND "
            "comparison_result_set_schema_version = 'v0.2-s3-comparison-result-set-v2')",
            name="ck_quality_manifest_comparison_versions",
        ),
        CheckConstraint(
            "comparison_cell_count >= 0 AND comparison_result_count >= 0",
            name="ck_quality_manifest_comparison_counts_nonnegative",
        ),
        CheckConstraint(
            "(schema_version = 'v0.2-s3-quality-persistence-v1' AND "
            "comparison_cell_count = 0 AND comparison_result_count = 0) OR "
            "(schema_version = 'v0.2-s3-quality-persistence-v2' AND "
            "comparison_result_count = comparison_cell_count * 10)",
            name="ck_quality_manifest_comparison_count_closure",
        ),
        CheckConstraint(
            "schema_version <> 'v0.2-s3-quality-persistence-v1' OR "
            "(comparison_policy_version IS NULL AND comparison_result_schema_version IS NULL "
            "AND comparison_result_set_schema_version = 'v0.2-s3-comparison-result-set-v1' "
            "AND comparison_cell_count = 0 AND comparison_result_count = 0)",
            name="ck_quality_manifest_v1_comparison_projection",
        ),
        CheckConstraint(
            "schema_version <> 'v0.2-s3-quality-persistence-v2' OR "
            "(comparison_policy_version = 'v0.2-s3-comparison-policy-v1' AND "
            "comparison_result_schema_version = 'v0.2-s3-comparison-result-v1' AND "
            "comparison_result_set_schema_version = 'v0.2-s3-comparison-result-set-v2')",
            name="ck_quality_manifest_v2_comparison_projection",
        ),
        Index("ix_quality_manifest_run_id", "quality_evaluation_run_id"),
    )

    id: Mapped[int] = mapped_column(_BIGINT, primary_key=True, autoincrement=True)
    quality_evaluation_run_id: Mapped[int] = mapped_column(
        _BIGINT,
        ForeignKey(
            "quality_evaluation_run.id",
            name="fk_quality_manifest_run",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    evaluation_request_hash: Mapped[str] = mapped_column(Text, nullable=False)
    evaluation_instance_hash: Mapped[str] = mapped_column(Text, nullable=False)
    metric_result_set_hash: Mapped[str] = mapped_column(Text, nullable=False)
    breakdown_result_set_hash: Mapped[str] = mapped_column(Text, nullable=False)
    baseline_result_set_hash: Mapped[str] = mapped_column(Text, nullable=False)
    comparison_result_set_hash: Mapped[str] = mapped_column(Text, nullable=False)
    comparison_policy_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    comparison_result_schema_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    comparison_result_set_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    comparison_cell_count: Mapped[int] = mapped_column(_BIGINT, nullable=False)
    comparison_result_count: Mapped[int] = mapped_column(_BIGINT, nullable=False)
    manifest_payload: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    manifest_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sealed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


__all__ = [
    "COMPARISON_POLICY_VERSION",
    "COMPARISON_RESULT_SCHEMA_VERSION",
    "COMPARISON_RESULT_SET_SCHEMA_VERSION",
    "LEGACY_COMPARISON_RESULT_SET_SCHEMA_VERSION",
    "ModelBaselineComparisonModel",
    "NaiveBaselineRunModel",
    "PERSISTENCE_SCHEMA_VERSION",
    "ROUND_C_PERSISTENCE_SCHEMA_VERSION",
    "QualityBreakdownResultModel",
    "QualityEvaluationManifestModel",
    "QualityEvaluationRunModel",
    "QualityMetricResultModel",
]
