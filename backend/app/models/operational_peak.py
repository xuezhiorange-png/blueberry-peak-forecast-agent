"""Immutable persistence models for the V0.5-S6 operational peak product."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base
from backend.app.models.area_forecast import ExactDecimal

_JSON_VARIANT = JSON().with_variant(JSONB(), "postgresql")


class OperationalPeakForecastRun(Base):
    __tablename__ = "operational_peak_forecast_run"
    __table_args__ = (
        CheckConstraint("status = 'completed'", name="ck_operational_peak_run_completed"),
        CheckConstraint("daily_row_count >= 1", name="ck_operational_peak_run_count"),
        CheckConstraint(
            "business_season_end >= business_season_start", name="ck_operational_peak_run_window"
        ),
        CheckConstraint(
            "rerun_of_run_id IS NULL OR rerun_of_run_id < id",
            name="ck_operational_peak_run_lineage",
        ),
        UniqueConstraint("execution_hash", name="uq_operational_peak_execution"),
        Index("ix_operational_peak_result_hash", "result_hash"),
        Index("ix_operational_peak_history", "created_at", "id"),
        Index("ix_operational_peak_base_season", "base_id", "target_season"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    execution_hash: Mapped[str] = mapped_column(Text, nullable=False)
    request_hash: Mapped[str] = mapped_column(Text, nullable=False)
    request_snapshot: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)
    result_metadata: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)
    authority_hash: Mapped[str] = mapped_column(Text, nullable=False)
    policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    baseline_id: Mapped[str] = mapped_column(Text, nullable=False)
    base_id: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_base_name: Mapped[str] = mapped_column(Text, nullable=False)
    productive_area_mu: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    target_season: Mapped[str] = mapped_column(Text, nullable=False)
    origin_date: Mapped[date] = mapped_column(Date, nullable=False)
    business_season_start: Mapped[date] = mapped_column(Date, nullable=False)
    business_season_end: Mapped[date] = mapped_column(Date, nullable=False)
    weather_used: Mapped[bool] = mapped_column(nullable=False, default=False)
    result_hash: Mapped[str] = mapped_column(Text, nullable=False)
    daily_row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    forecast_7d: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)
    forecast_15d: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)
    remaining_business_window: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)
    rerun_of_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("operational_peak_forecast_run.id"), nullable=True
    )


class OperationalPeakForecastDaily(Base):
    __tablename__ = "operational_peak_forecast_daily"
    __table_args__ = (
        UniqueConstraint("run_id", "row_index", name="uq_operational_peak_daily_index"),
        UniqueConstraint("run_id", "forecast_date", name="uq_operational_peak_daily_date"),
        CheckConstraint("row_index >= 0", name="ck_operational_peak_daily_index"),
        CheckConstraint(
            "CAST(predicted_kg AS NUMERIC) >= 0",
            name="ck_operational_peak_daily_quantity",
        ),
        CheckConstraint(
            "CAST(kg_per_mu AS NUMERIC) >= 0",
            name="ck_operational_peak_daily_kg_per_mu",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("operational_peak_forecast_run.id"), nullable=False
    )
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    forecast_date: Mapped[date] = mapped_column(Date, nullable=False)
    predicted_kg: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    kg_per_mu: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    business_season_day_index: Mapped[int] = mapped_column(Integer, nullable=False)
    reference_bin: Mapped[int] = mapped_column(Integer, nullable=False)


__all__ = ["OperationalPeakForecastRun", "OperationalPeakForecastDaily"]
