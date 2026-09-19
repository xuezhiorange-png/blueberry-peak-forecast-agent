"""Normalized immutable product runs, distinct from Core Forecast business runs."""

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
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base
from backend.app.db.types import ExactDecimal


class AreaForecastRun(Base):
    __tablename__ = "area_forecast_run"
    __table_args__ = (
        CheckConstraint("status = 'completed'", name="ck_area_run_completed"),
        CheckConstraint("daily_row_count >= 7", name="ck_area_run_count"),
        CheckConstraint("season_end >= season_start", name="ck_area_run_window"),
        CheckConstraint(
            "rerun_of_run_id IS NULL OR rerun_of_run_id < id", name="ck_area_run_lineage"
        ),
        UniqueConstraint("request_hash", name="uq_area_run_execution"),
        Index("ix_area_run_result_hash", "result_hash"),
        Index("ix_area_run_history", "created_at", "id"),
        Index("ix_area_run_farm_season", "canonical_farm", "target_season"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    forecast_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    model_version: Mapped[str] = mapped_column(Text, nullable=False)
    request_hash: Mapped[str] = mapped_column(Text, nullable=False)
    result_hash: Mapped[str] = mapped_column(Text, nullable=False)
    request_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql")
    )
    result_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql")
    )
    canonical_farm: Mapped[str] = mapped_column(Text, nullable=False)
    requested_productive_area_mu: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    target_season: Mapped[str] = mapped_column(Text, nullable=False)
    season_start: Mapped[date] = mapped_column(Date, nullable=False)
    season_end: Mapped[date] = mapped_column(Date, nullable=False)
    history_cutoff: Mapped[date] = mapped_column(Date, nullable=False)
    predicted_yield_kg_per_mu: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    predicted_total_kg: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    total_model: Mapped[str] = mapped_column(Text, nullable=False)
    total_model_source_season: Mapped[str] = mapped_column(Text, nullable=False)
    authority_hash: Mapped[str] = mapped_column(Text, nullable=False)
    shape_hash: Mapped[str] = mapped_column(Text, nullable=False)
    daily_row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    rerun_of_run_id: Mapped[int | None] = mapped_column(ForeignKey("area_forecast_run.id"))


class AreaForecastDailyRow(Base):
    __tablename__ = "area_forecast_daily_row"
    __table_args__ = (
        UniqueConstraint("run_id", "row_index", name="uq_area_daily_index"),
        UniqueConstraint("run_id", "date", name="uq_area_daily_date"),
        CheckConstraint("row_index >= 0", name="ck_area_daily_index"),
        CheckConstraint("CAST(predicted_kg AS NUMERIC) >= 0", name="ck_area_daily_quantity"),
        CheckConstraint("CAST(share AS NUMERIC) >= 0", name="ck_area_daily_share"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("area_forecast_run.id"), nullable=False)
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    predicted_kg: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    share: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    share_text: Mapped[str] = mapped_column(Text, nullable=False)
