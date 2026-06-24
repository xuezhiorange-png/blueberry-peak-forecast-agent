from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class MaturityModelRun(Base):
    __tablename__ = "maturity_model_run"
    __table_args__ = (
        CheckConstraint(
            "status in ('running', 'completed', 'failed', 'unavailable')",
            name="ck_maturity_model_run_status",
        ),
        UniqueConstraint("source_signature", "status", name="uq_maturity_model_run_sig_status"),
        Index(
            "ux_maturity_model_run_active_or_done",
            "source_signature",
            unique=True,
            postgresql_where=text("status in ('running', 'completed', 'unavailable')"),
            sqlite_where=text("status in ('running', 'completed', 'unavailable')"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    model_version: Mapped[str] = mapped_column(Text, nullable=False)
    config_hash: Mapped[str] = mapped_column(Text, nullable=False)
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    training_cutoff: Mapped[date] = mapped_column(Date, nullable=False)
    source_signature: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    random_seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    model_family: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    sample_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    distinct_season_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    distinct_farm_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    distinct_subfarm_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    training_metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    calibration_metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    blockers: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class MaturityModelArtifact(Base):
    __tablename__ = "maturity_model_artifact"
    __table_args__ = (
        UniqueConstraint("run_id", name="uq_maturity_model_artifact_run_id"),
        UniqueConstraint("artifact_hash", name="uq_maturity_model_artifact_hash"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "maturity_model_run.id",
            name="fk_maturity_artifact_run_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    artifact_hash: Mapped[str] = mapped_column(Text, nullable=False)
    support_min_day: Mapped[int] = mapped_column(BigInteger, nullable=False)
    support_max_day: Mapped[int] = mapped_column(BigInteger, nullable=False)
    artifact_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class MaturityForecastRun(Base):
    __tablename__ = "maturity_forecast_run"
    __table_args__ = (
        CheckConstraint(
            "status in ('running', 'completed', 'failed', 'unavailable')",
            name="ck_maturity_forecast_run_status",
        ),
        CheckConstraint(
            "axis_mode in ('observed_phenology_axis', 'calendar_proxy_axis')",
            name="ck_maturity_forecast_run_axis_mode",
        ),
        UniqueConstraint(
            "source_signature",
            "status",
            name="uq_maturity_forecast_run_sig_status",
        ),
        Index(
            "ux_maturity_forecast_run_active_or_done",
            "source_signature",
            unique=True,
            postgresql_where=text("status in ('running', 'completed', 'unavailable')"),
            sqlite_where=text("status in ('running', 'completed', 'unavailable')"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    model_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "maturity_model_run.id",
            name="fk_maturity_forecast_run_model_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    artifact_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "maturity_model_artifact.id",
            name="fk_maturity_forecast_run_artifact_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    plan_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "farm_season_variety_plan.id",
            name="fk_maturity_forecast_run_plan_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    location_reference_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "location_reference.id",
            name="fk_maturity_forecast_run_loc_ref_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    weather_mapping_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "location_weather_mapping.id",
            name="fk_maturity_forecast_run_mapping_id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    base_temperature_search_run_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "base_temperature_search_run.id",
            name="fk_maturity_forecast_run_base_temp_id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    prediction_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    prediction_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_marketable_total_kg: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    expected_total_source: Mapped[str] = mapped_column(Text, nullable=False)
    axis_mode: Mapped[str] = mapped_column(Text, nullable=False)
    source_signature: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    blockers: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class MaturityDailyPredictionModel(Base):
    __tablename__ = "maturity_daily_prediction"
    __table_args__ = (
        UniqueConstraint("forecast_run_id", "prediction_date", name="uq_maturity_daily_run_date"),
        Index("ix_maturity_daily_prediction_run_id", "forecast_run_id"),
        Index("ix_maturity_daily_prediction_date", "prediction_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    forecast_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "maturity_forecast_run.id",
            name="fk_maturity_daily_prediction_run_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
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
    quality_flags: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
