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
            "schema_version = 'v0.2-s3-quality-persistence-v1'",
            name="ck_quality_evaluation_run_schema_version",
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
        UniqueConstraint("canonical_hash", name="uq_quality_metric_result_canonical_hash"),
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
        UniqueConstraint("canonical_hash", name="uq_quality_breakdown_result_canonical_hash"),
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
        UniqueConstraint("canonical_hash", name="uq_naive_baseline_canonical_hash"),
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
        UniqueConstraint("canonical_hash", name="uq_model_baseline_comparison_canonical_hash"),
        _sha256_check("comparison_key_hash", "ck_model_baseline_comparison_key_sha256"),
        _sha256_check("canonical_hash", "ck_model_baseline_comparison_canonical_sha256"),
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
    naive_baseline_run_id: Mapped[int] = mapped_column(
        _BIGINT,
        ForeignKey(
            "naive_baseline_run.id",
            name="fk_model_baseline_comparison_baseline",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    comparison_key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    model_identity: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    comparison_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    comparison_status: Mapped[str] = mapped_column(Text, nullable=False)
    reason_code: Mapped[str] = mapped_column(Text, nullable=False)
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
    manifest_payload: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    manifest_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sealed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


__all__ = [
    "ModelBaselineComparisonModel",
    "NaiveBaselineRunModel",
    "PERSISTENCE_SCHEMA_VERSION",
    "QualityBreakdownResultModel",
    "QualityEvaluationManifestModel",
    "QualityEvaluationRunModel",
    "QualityMetricResultModel",
]
