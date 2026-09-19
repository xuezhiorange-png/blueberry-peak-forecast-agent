"""ORM models for the immutable V0.6-S3 evaluation authority."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from backend.app.actual_harvest_import.models import UTCDateTime
from backend.app.db.base import Base
from backend.app.db.types import ExactDecimal


def _document() -> Any:
    return JSON().with_variant(JSONB(), "postgresql")


def _sqlite_bigint() -> Any:
    from sqlalchemy import BigInteger

    return BigInteger().with_variant(Integer(), "sqlite")


class ForecastEvaluation(Base):
    """One append-only evaluation of one immutable forecast snapshot."""

    __tablename__ = "forecast_evaluation"
    __table_args__ = (
        UniqueConstraint("evaluation_identity_hash", name="uq_forecast_evaluation_identity"),
        CheckConstraint(
            "evaluation_mode IN ('FULL_AVAILABLE_RANGE', 'AS_OF_DATE')",
            name="ck_forecast_evaluation_mode",
        ),
        CheckConstraint(
            "actual_coverage_status IN ('COMPLETE', 'PARTIAL', 'EMPTY')",
            name="ck_forecast_evaluation_coverage",
        ),
        CheckConstraint("daily_row_count >= 1", name="ck_forecast_evaluation_daily_count"),
        Index("ix_forecast_evaluation_forecast", "forecast_run_id", "evaluation_created_at"),
        Index("ix_forecast_evaluation_base_season", "base_id", "target_season"),
    )

    evaluation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    forecast_run_id: Mapped[str] = mapped_column(
        ForeignKey("forecast_run_snapshot.forecast_run_id", ondelete="RESTRICT"),
        nullable=False,
    )
    base_id: Mapped[str] = mapped_column(Text, nullable=False)
    target_season: Mapped[str] = mapped_column(Text, nullable=False)
    evaluation_mode: Mapped[str] = mapped_column(Text, nullable=False)
    as_of_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    evaluation_created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    forecast_input_hash: Mapped[str] = mapped_column(Text, nullable=False)
    forecast_result_hash: Mapped[str] = mapped_column(Text, nullable=False)
    actual_authority_ids: Mapped[list[str]] = mapped_column(_document(), nullable=False)
    actual_authority_hashes: Mapped[list[str]] = mapped_column(_document(), nullable=False)
    realized_weather_authority_ids: Mapped[list[str]] = mapped_column(_document(), nullable=False)
    realized_weather_authority_hashes: Mapped[list[str]] = mapped_column(
        _document(), nullable=False
    )
    evaluated_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    evaluated_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    actual_coverage_status: Mapped[str] = mapped_column(Text, nullable=False)
    season_total_metrics: Mapped[dict[str, Any]] = mapped_column(_document(), nullable=False)
    daily_metrics: Mapped[dict[str, Any]] = mapped_column(_document(), nullable=False)
    single_day_peak_metrics: Mapped[dict[str, Any]] = mapped_column(_document(), nullable=False)
    rolling_7day_peak_metrics: Mapped[dict[str, Any]] = mapped_column(_document(), nullable=False)
    weather_metrics: Mapped[dict[str, Any]] = mapped_column(_document(), nullable=False)
    warnings: Mapped[list[str]] = mapped_column(_document(), nullable=False)
    evaluation_payload_json: Mapped[dict[str, Any]] = mapped_column(_document(), nullable=False)
    evaluation_identity_hash: Mapped[str] = mapped_column(Text, nullable=False)
    evaluation_payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    evaluation_result_hash: Mapped[str] = mapped_column(Text, nullable=False)
    daily_row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class ForecastEvaluationDaily(Base):
    """Canonical aligned forecast/actual rows for one evaluation."""

    __tablename__ = "forecast_evaluation_daily"
    __table_args__ = (
        UniqueConstraint("evaluation_id", "row_index", name="uq_forecast_evaluation_daily_index"),
        UniqueConstraint(
            "evaluation_id", "evaluation_date", name="uq_forecast_evaluation_daily_date"
        ),
        CheckConstraint("row_index >= 0", name="ck_forecast_evaluation_daily_index"),
        CheckConstraint(
            "actual_status IN ('CONFIRMED_QUANTITY', 'CONFIRMED_ZERO', 'MISSING')",
            name="ck_forecast_evaluation_daily_status",
        ),
        CheckConstraint(
            "CAST(predicted_quantity_kg AS NUMERIC) >= 0",
            name="ck_forecast_evaluation_daily_prediction",
        ),
        CheckConstraint(
            "actual_quantity_kg IS NULL OR CAST(actual_quantity_kg AS NUMERIC) >= 0",
            name="ck_forecast_evaluation_daily_actual",
        ),
        Index("ix_forecast_evaluation_daily_date", "evaluation_id", "evaluation_date"),
    )

    id: Mapped[int] = mapped_column(_sqlite_bigint(), primary_key=True, autoincrement=True)
    evaluation_id: Mapped[str] = mapped_column(
        ForeignKey("forecast_evaluation.evaluation_id", ondelete="RESTRICT"), nullable=False
    )
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    evaluation_date: Mapped[date] = mapped_column(Date, nullable=False)
    predicted_quantity_kg: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    actual_quantity_kg: Mapped[Decimal | None] = mapped_column(ExactDecimal(), nullable=True)
    actual_status: Mapped[str] = mapped_column(Text, nullable=False)
    actual_revision_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual_source_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_kg: Mapped[Decimal | None] = mapped_column(ExactDecimal(), nullable=True)
    absolute_error_kg: Mapped[Decimal | None] = mapped_column(ExactDecimal(), nullable=True)
    evaluation_as_of: Mapped[date | None] = mapped_column(Date, nullable=True)
    row_hash: Mapped[str] = mapped_column(Text, nullable=False)


__all__ = ["ForecastEvaluation", "ForecastEvaluationDaily"]
