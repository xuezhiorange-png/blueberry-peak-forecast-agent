"""Append-only aggregate forecasts, separate from their immutable Base sources."""

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

DOCUMENT = JSON().with_variant(JSONB(), "postgresql")


class HierarchicalForecastRun(Base):
    __tablename__ = "hierarchical_forecast_run"
    __table_args__ = (
        UniqueConstraint("execution_hash", name="uq_hierarchical_execution"),
        CheckConstraint(
            "child_included_count > 0 AND child_expected_count >= child_included_count",
            name="ck_hierarchical_counts",
        ),
        CheckConstraint(
            "(status = 'COMPLETE' AND child_expected_count = child_included_count "
            "AND daily_row_count >= 1) OR (status = 'INCOMPLETE_CHILD_COVERAGE' "
            "AND child_included_count < child_expected_count AND daily_row_count = 0)",
            name="ck_hierarchical_status",
        ),
        CheckConstraint(
            "target_entity_type IN ('REGION', 'COMPANY')", name="ck_hierarchical_target"
        ),
        CheckConstraint(
            "business_season_end >= business_season_start", name="ck_hierarchical_window"
        ),
        Index("ix_hierarchical_history", "created_at", "id"),
        Index("ix_hierarchical_target", "target_entity_type", "target_entity_id", "target_season"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    execution_hash: Mapped[str] = mapped_column(Text, nullable=False)
    reconciliation_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    hierarchy_contract_version: Mapped[str] = mapped_column(Text, nullable=False)
    hierarchy_authority_hash: Mapped[str] = mapped_column(Text, nullable=False)
    source_authority_hash: Mapped[str] = mapped_column(Text, nullable=False)
    hierarchy_snapshot: Mapped[dict[str, Any]] = mapped_column(DOCUMENT, nullable=False)
    request_snapshot: Mapped[dict[str, Any]] = mapped_column(DOCUMENT, nullable=False)
    target_entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_entity_id: Mapped[str] = mapped_column(Text, nullable=False)
    target_entity_label: Mapped[str] = mapped_column(Text, nullable=False)
    target_season: Mapped[str] = mapped_column(Text, nullable=False)
    origin_date: Mapped[date] = mapped_column(Date, nullable=False)
    business_season_start: Mapped[date] = mapped_column(Date, nullable=False)
    business_season_end: Mapped[date] = mapped_column(Date, nullable=False)
    baseline_id: Mapped[str] = mapped_column(Text, nullable=False)
    source_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    weather_used: Mapped[bool] = mapped_column(nullable=False)
    quantile_or_point_label: Mapped[str] = mapped_column(Text, nullable=False)
    scenario_id: Mapped[str] = mapped_column(Text, nullable=False)
    child_expected_count: Mapped[int] = mapped_column(Integer, nullable=False)
    child_included_count: Mapped[int] = mapped_column(Integer, nullable=False)
    child_base_ids_hash: Mapped[str] = mapped_column(Text, nullable=False)
    missing_base_ids_hash: Mapped[str] = mapped_column(Text, nullable=False)
    source_run_ids_hash: Mapped[str] = mapped_column(Text, nullable=False)
    source_result_hashes_hash: Mapped[str] = mapped_column(Text, nullable=False)
    daily_row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    result_metadata: Mapped[dict[str, Any]] = mapped_column(DOCUMENT, nullable=False)
    result_hash: Mapped[str] = mapped_column(Text, nullable=False)


class HierarchicalForecastDaily(Base):
    __tablename__ = "hierarchical_forecast_daily"
    __table_args__ = (
        UniqueConstraint("run_id", "row_index", name="uq_hierarchical_daily_index"),
        UniqueConstraint("run_id", "forecast_date", name="uq_hierarchical_daily_date"),
        CheckConstraint("row_index >= 0", name="ck_hierarchical_daily_index"),
        CheckConstraint(
            "CAST(predicted_kg AS NUMERIC) >= 0", name="ck_hierarchical_daily_quantity"
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("hierarchical_forecast_run.id"), nullable=False)
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    forecast_date: Mapped[date] = mapped_column(Date, nullable=False)
    predicted_kg: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)


class HierarchicalForecastSource(Base):
    __tablename__ = "hierarchical_forecast_source"
    __table_args__ = (
        UniqueConstraint("hierarchical_run_id", "base_id", name="uq_hierarchical_source_base"),
        UniqueConstraint(
            "hierarchical_run_id",
            "source_operational_peak_run_id",
            name="uq_hierarchical_source_run",
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hierarchical_run_id: Mapped[int] = mapped_column(
        ForeignKey("hierarchical_forecast_run.id"), nullable=False
    )
    source_operational_peak_run_id: Mapped[int] = mapped_column(
        ForeignKey("operational_peak_forecast_run.id"), nullable=False
    )
    base_id: Mapped[str] = mapped_column(Text, nullable=False)
    source_execution_hash: Mapped[str] = mapped_column(Text, nullable=False)
    source_result_hash: Mapped[str] = mapped_column(Text, nullable=False)
