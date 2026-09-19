"""ORM models for the immutable V0.6-S4 prospective assessment authority."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from backend.app.actual_harvest_import.models import UTCDateTime
from backend.app.db.base import Base


def _document() -> Any:
    return JSON().with_variant(JSONB(), "postgresql")


class ProspectiveValidationRun(Base):
    """One immutable S4 eligibility registry and evidence summary."""

    __tablename__ = "prospective_validation_run"
    __table_args__ = (
        UniqueConstraint("payload_hash", name="uq_prospective_validation_payload"),
        CheckConstraint(
            "weather_incremental_value_conclusion IN "
            "('INCONCLUSIVE', 'NOT_DEMONSTRATED', 'SUPPORTED_BY_CURRENT_EVIDENCE')",
            name="ck_prospective_validation_conclusion",
        ),
        CheckConstraint(
            "v0_7_recommendation IN "
            "('PROCEED_TO_CONTROLLED_EXPERIMENT', 'DO_NOT_PROCEED_YET', 'INSUFFICIENT_EVIDENCE')",
            name="ck_prospective_validation_recommendation",
        ),
        Index("ix_prospective_validation_created", "created_at", "validation_run_id"),
    )

    validation_run_id: Mapped[str] = mapped_column(Text, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    model_a_identity: Mapped[str] = mapped_column(Text, nullable=False)
    model_a_hash: Mapped[str] = mapped_column(Text, nullable=False)
    eligible_forecast_run_ids: Mapped[list[str]] = mapped_column(_document(), nullable=False)
    s3_evaluation_ids: Mapped[list[str]] = mapped_column(_document(), nullable=False)
    eligibility_registry_json: Mapped[list[dict[str, Any]]] = mapped_column(
        _document(), nullable=False
    )
    sample_scope: Mapped[dict[str, Any]] = mapped_column(_document(), nullable=False)
    coverage_summary: Mapped[dict[str, Any]] = mapped_column(_document(), nullable=False)
    baseline_metrics: Mapped[dict[str, Any]] = mapped_column(_document(), nullable=False)
    weather_quality_metrics: Mapped[dict[str, Any]] = mapped_column(_document(), nullable=False)
    weather_incremental_metrics: Mapped[dict[str, Any]] = mapped_column(_document(), nullable=False)
    evidence_sufficiency: Mapped[dict[str, Any]] = mapped_column(_document(), nullable=False)
    weather_snapshot_authority_hashes: Mapped[list[str]] = mapped_column(
        _document(), nullable=False
    )
    weather_incremental_value_conclusion: Mapped[str] = mapped_column(Text, nullable=False)
    v0_7_recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(_document(), nullable=False)
    payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    result_hash: Mapped[str] = mapped_column(Text, nullable=False)


class WeatherIncrementalValueAssessment(Base):
    """Immutable persisted projection of S4 weather-value diagnostics."""

    __tablename__ = "weather_incremental_value_assessment"
    __table_args__ = (
        UniqueConstraint("payload_hash", name="uq_weather_incremental_payload"),
        CheckConstraint(
            "weather_incremental_value_conclusion IN "
            "('INCONCLUSIVE', 'NOT_DEMONSTRATED', 'SUPPORTED_BY_CURRENT_EVIDENCE')",
            name="ck_weather_incremental_conclusion",
        ),
        CheckConstraint(
            "v0_7_recommendation IN "
            "('PROCEED_TO_CONTROLLED_EXPERIMENT', 'DO_NOT_PROCEED_YET', 'INSUFFICIENT_EVIDENCE')",
            name="ck_weather_incremental_recommendation",
        ),
        Index("ix_weather_incremental_validation", "validation_run_id", "created_at"),
    )

    assessment_id: Mapped[str] = mapped_column(Text, primary_key=True)
    validation_run_id: Mapped[str] = mapped_column(
        ForeignKey("prospective_validation_run.validation_run_id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    model_a_identity: Mapped[str] = mapped_column(Text, nullable=False)
    model_a_hash: Mapped[str] = mapped_column(Text, nullable=False)
    weather_snapshot_authority_hashes: Mapped[list[str]] = mapped_column(
        _document(), nullable=False
    )
    sample_scope: Mapped[dict[str, Any]] = mapped_column(_document(), nullable=False)
    coverage_summary: Mapped[dict[str, Any]] = mapped_column(_document(), nullable=False)
    baseline_metrics: Mapped[dict[str, Any]] = mapped_column(_document(), nullable=False)
    weather_quality_metrics: Mapped[dict[str, Any]] = mapped_column(_document(), nullable=False)
    weather_incremental_metrics: Mapped[dict[str, Any]] = mapped_column(_document(), nullable=False)
    evidence_sufficiency: Mapped[dict[str, Any]] = mapped_column(_document(), nullable=False)
    weather_incremental_value_conclusion: Mapped[str] = mapped_column(Text, nullable=False)
    v0_7_recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(_document(), nullable=False)
    payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    result_hash: Mapped[str] = mapped_column(Text, nullable=False)


__all__ = ["ProspectiveValidationRun", "WeatherIncrementalValueAssessment"]
