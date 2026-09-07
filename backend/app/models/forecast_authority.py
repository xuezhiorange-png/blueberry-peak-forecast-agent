"""Immutable prospective forecast-authority retention models.

The existing Task 8, Task 9, Core Forecast, and Task 10 tables remain the
owners of their respective business results.  These two tables are an
append-only, cross-owner retention envelope: it records the exact identities
and the Task 8 daily values that were visible for one completed production
forecast so a later point-in-time reader does not need to reconstruct the
forecast from mutable current inputs.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Date,
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

_BIGINT_VARIANT = BigInteger().with_variant(Integer(), "sqlite")
_JSON_VARIANT = JSON().with_variant(JSONB(), "postgresql")

FORECAST_AUTHORITY_SCHEMA_VERSION = "v0.3-s3-prospective-forecast-authority-v1"
FORECAST_AUTHORITY_SCOPE_PRODUCTION = "PRODUCTION"
FORECAST_AUTHORITY_STATUS_CAPTURED = "CAPTURED"


def _sha256_checks(column: str, name: str) -> tuple[CheckConstraint, CheckConstraint]:
    return (
        CheckConstraint(
            f"length({column}) = 64 AND {column} NOT GLOB '*[^0-9a-f]*'",
            name=name,
        ).ddl_if(dialect="sqlite"),
        CheckConstraint(
            f"{column} ~ '^[0-9a-f]{{64}}$'",
            name=name,
        ).ddl_if(dialect="postgresql"),
    )


class ForecastAuthorityCaptureModel(Base):
    """One immutable, complete production forecast authority envelope."""

    __tablename__ = "forecast_authority_capture"
    __table_args__ = (
        CheckConstraint(
            "authority_schema_version = 'v0.3-s3-prospective-forecast-authority-v1'",
            name="ck_forecast_authority_capture_schema_version",
        ),
        CheckConstraint(
            "authority_scope = 'PRODUCTION'",
            name="ck_forecast_authority_capture_production_scope",
        ),
        CheckConstraint(
            "status = 'CAPTURED'",
            name="ck_forecast_authority_capture_status",
        ),
        CheckConstraint("daily_row_count > 0", name="ck_forecast_authority_capture_daily_count"),
        CheckConstraint(
            "task8_forecast_run_id > 0 AND task8_model_run_id > 0 AND task8_artifact_id > 0",
            name="ck_forecast_authority_capture_task8_ids",
        ),
        CheckConstraint(
            "task9_run_id > 0 AND task10_training_run_id > 0 "
            "AND task10_prediction_run_id > 0 AND task10_binding_id > 0",
            name="ck_forecast_authority_capture_downstream_ids",
        ),
        CheckConstraint("plan_id > 0", name="ck_forecast_authority_capture_plan_id"),
        *_sha256_checks(
            "forecast_identity",
            "ck_forecast_authority_capture_forecast_identity",
        ),
        *_sha256_checks(
            "authority_identity_hash",
            "ck_forecast_authority_capture_authority_identity_hash",
        ),
        *_sha256_checks(
            "business_grain_hash",
            "ck_forecast_authority_capture_business_grain_hash",
        ),
        *_sha256_checks(
            "plan_authority_hash",
            "ck_forecast_authority_capture_plan_authority_hash",
        ),
        *_sha256_checks("plan_row_hash", "ck_forecast_authority_capture_plan_row_hash"),
        *_sha256_checks(
            "weather_authority_hash",
            "ck_forecast_authority_capture_weather_authority_hash",
        ),
        *_sha256_checks("code_authority_hash", "ck_forecast_authority_capture_code_authority_hash"),
        *_sha256_checks(
            "task8_authority_hash",
            "ck_forecast_authority_capture_task8_authority_hash",
        ),
        *_sha256_checks("task8_config_hash", "ck_forecast_authority_capture_task8_config_hash"),
        *_sha256_checks("task8_artifact_hash", "ck_forecast_authority_capture_task8_artifact_hash"),
        *_sha256_checks(
            "task9_authority_hash",
            "ck_forecast_authority_capture_task9_authority_hash",
        ),
        *_sha256_checks("task9_result_hash", "ck_forecast_authority_capture_task9_result_hash"),
        *_sha256_checks(
            "task10_authority_hash",
            "ck_forecast_authority_capture_task10_authority_hash",
        ),
        *_sha256_checks(
            "task10_training_signature",
            "ck_forecast_authority_capture_task10_training_signature",
        ),
        *_sha256_checks(
            "task10_prediction_input_signature",
            "ck_forecast_authority_capture_task10_input_hash",
        ),
        *_sha256_checks(
            "task10_prediction_hash",
            "ck_forecast_authority_capture_task10_prediction_hash",
        ),
        *_sha256_checks("task10_binding_hash", "ck_forecast_authority_capture_task10_binding_hash"),
        *_sha256_checks(
            "core_authority_hash",
            "ck_forecast_authority_capture_core_authority_hash",
        ),
        *_sha256_checks(
            "source_lineage_hash",
            "ck_forecast_authority_capture_source_lineage_hash",
        ),
        *_sha256_checks(
            "task8_daily_artifact_hash",
            "ck_forecast_authority_capture_task8_daily_artifact_hash",
        ),
        *_sha256_checks("authority_hash", "ck_forecast_authority_capture_hash"),
        UniqueConstraint(
            "forecast_identity",
            name="uq_forecast_authority_capture_forecast_identity",
        ),
        UniqueConstraint(
            "core_forecast_run_id",
            name="uq_forecast_authority_capture_core_run",
        ),
        UniqueConstraint("authority_hash", name="uq_forecast_authority_capture_authority_hash"),
        Index("ix_forecast_authority_capture_cutoff", "forecast_cutoff_at"),
        Index("ix_forecast_authority_capture_task8_run", "task8_forecast_run_id"),
        Index("ix_forecast_authority_capture_task10_prediction", "task10_prediction_run_id"),
    )

    id: Mapped[int] = mapped_column(_BIGINT_VARIANT, primary_key=True, autoincrement=True)
    authority_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    authority_scope: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    forecast_identity: Mapped[str] = mapped_column(Text, nullable=False)
    forecast_cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    forecast_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    forecast_available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    core_forecast_run_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey("core_forecast_run.id", name="fk_forecast_authority_capture_core_run_id"),
        nullable=False,
    )
    code_authority_id: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    code_authority_hash: Mapped[str] = mapped_column(Text, nullable=False)
    code_authority_available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    forecast_season_id: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    destination_factory_id: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)

    business_grain_hash: Mapped[str] = mapped_column(Text, nullable=False)
    business_grain_snapshot: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)

    plan_id: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    plan_version: Mapped[int] = mapped_column(Integer, nullable=False)
    plan_row_hash: Mapped[str] = mapped_column(Text, nullable=False)
    plan_authority_hash: Mapped[str] = mapped_column(Text, nullable=False)
    plan_snapshot: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)

    location_reference_id: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    weather_mapping_id: Mapped[int | None] = mapped_column(_BIGINT_VARIANT, nullable=True)
    base_temperature_search_run_id: Mapped[int | None] = mapped_column(
        _BIGINT_VARIANT, nullable=True
    )
    weather_authority_hash: Mapped[str] = mapped_column(Text, nullable=False)
    weather_snapshot: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)

    task8_forecast_run_id: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    task8_model_run_id: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    task8_artifact_id: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    task8_model_version: Mapped[str] = mapped_column(Text, nullable=False)
    task8_config_hash: Mapped[str] = mapped_column(Text, nullable=False)
    task8_artifact_hash: Mapped[str] = mapped_column(Text, nullable=False)
    task8_authority_hash: Mapped[str] = mapped_column(Text, nullable=False)
    task8_snapshot: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)

    task9_run_id: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    task9_result_hash: Mapped[str] = mapped_column(Text, nullable=False)
    task9_authority_hash: Mapped[str] = mapped_column(Text, nullable=False)
    task9_snapshot: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)

    task10_training_run_id: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    task10_training_signature: Mapped[str] = mapped_column(Text, nullable=False)
    task10_prediction_run_id: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    task10_prediction_input_signature: Mapped[str] = mapped_column(Text, nullable=False)
    task10_prediction_hash: Mapped[str] = mapped_column(Text, nullable=False)
    task10_binding_id: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    task10_binding_hash: Mapped[str] = mapped_column(Text, nullable=False)
    task10_authority_hash: Mapped[str] = mapped_column(Text, nullable=False)
    task10_snapshot: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)

    core_authority_hash: Mapped[str] = mapped_column(Text, nullable=False)
    core_snapshot: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)
    governance_snapshot: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)
    source_lineage_hash: Mapped[str] = mapped_column(Text, nullable=False)
    task8_daily_artifact_hash: Mapped[str] = mapped_column(Text, nullable=False)
    daily_row_count: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    canonical_payload: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)
    authority_identity_hash: Mapped[str] = mapped_column(Text, nullable=False)
    authority_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ForecastAuthorityDailyModel(Base):
    """Immutable retained Task 8 daily curve row for one capture."""

    __tablename__ = "forecast_authority_daily"
    __table_args__ = (
        UniqueConstraint(
            "forecast_authority_capture_id",
            "prediction_date",
            name="uq_forecast_authority_daily_capture_date",
        ),
        *_sha256_checks("row_hash", "ck_forecast_authority_daily_row_hash"),
        CheckConstraint(
            "p50_kg >= 0 AND p80_kg >= 0 AND p90_kg >= 0",
            name="ck_forecast_authority_daily_quantities_nonnegative",
        ),
        CheckConstraint(
            "p50_kg <= p80_kg AND p80_kg <= p90_kg",
            name="ck_forecast_authority_daily_quantile_order",
        ),
        CheckConstraint(
            "forecast_authority_capture_id > 0",
            name="ck_forecast_authority_daily_capture_positive",
        ),
        Index(
            "ix_forecast_authority_daily_capture_date",
            "forecast_authority_capture_id",
            "prediction_date",
        ),
    )

    id: Mapped[int] = mapped_column(_BIGINT_VARIANT, primary_key=True, autoincrement=True)
    forecast_authority_capture_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey(
            "forecast_authority_capture.id",
            name="fk_forecast_authority_daily_capture_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    source_daily_prediction_id: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    forecast_run_id: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    prediction_date: Mapped[date] = mapped_column(Date, nullable=False)
    phenology_coordinate_day: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    p50_kg: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    p80_kg: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    p90_kg: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    cumulative_p50_kg: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    cumulative_p80_kg: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    cumulative_p90_kg: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    curve_share: Mapped[Decimal] = mapped_column(Numeric(12, 10), nullable=False)
    confidence_level: Mapped[str] = mapped_column(Text, nullable=False)
    quality_flags: Mapped[list[str]] = mapped_column(_JSON_VARIANT, nullable=False)
    source_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    canonical_payload: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)
    row_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
