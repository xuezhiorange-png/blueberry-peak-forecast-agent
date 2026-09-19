"""SQLAlchemy models for the V0.6-S1 append-only PIT foundation."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
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

from backend.app.actual_harvest_import.models import UTCDateTime
from backend.app.db.base import Base
from backend.app.models.area_forecast import ExactDecimal


def _sqlite_bigint() -> Any:
    return BigInteger().with_variant(Integer(), "sqlite")


def _document() -> Any:
    return JSON().with_variant(JSONB(), "postgresql")


class AreaRevision(Base):
    __tablename__ = "area_revision"
    __table_args__ = (
        CheckConstraint("CAST(area_mu AS NUMERIC) > 0", name="ck_area_revision_positive"),
        CheckConstraint(
            "area_type IN ("
            "'REFERENCE_AREA', 'ACTUAL_PRODUCTIVE_AREA', 'PLANTED_AREA', 'PLANNED_AREA'"
            ")",
            name="ck_area_revision_type",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_area_revision_effective_range",
        ),
        UniqueConstraint("payload_hash", name="uq_area_revision_payload_hash"),
        Index("ix_area_revision_base_season_known", "base_id", "season", "known_at"),
    )

    area_revision_id: Mapped[str] = mapped_column(Text, primary_key=True)
    base_id: Mapped[str] = mapped_column(Text, nullable=False)
    season: Mapped[str] = mapped_column(Text, nullable=False)
    area_mu: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    area_type: Mapped[str] = mapped_column(Text, nullable=False)
    effective_from: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    known_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_reference: Mapped[str] = mapped_column(Text, nullable=False)
    basis: Mapped[str] = mapped_column(Text, nullable=False)
    supersedes_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("area_revision.area_revision_id", ondelete="RESTRICT"), nullable=True
    )
    payload_hash: Mapped[str] = mapped_column(Text, nullable=False)


class WeatherForecastSnapshot(Base):
    __tablename__ = "weather_forecast_snapshot"
    __table_args__ = (
        CheckConstraint(
            "forecast_horizon_hours >= 0",
            name="ck_weather_forecast_horizon_nonnegative",
        ),
        CheckConstraint("issued_at <= known_at", name="ck_weather_forecast_issued_known"),
        CheckConstraint(
            "base_id IS NOT NULL OR location_id IS NOT NULL",
            name="ck_weather_forecast_scope",
        ),
        UniqueConstraint(
            "raw_payload_hash",
            "normalized_payload_hash",
            name="uq_weather_forecast_payload",
        ),
        Index("ix_weather_forecast_scope_valid", "base_id", "valid_at"),
        Index("ix_weather_forecast_known", "known_at"),
    )

    weather_snapshot_id: Mapped[str] = mapped_column(Text, primary_key=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    base_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    issued_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    known_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    valid_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    forecast_horizon_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    temperature_min: Mapped[Decimal | None] = mapped_column(ExactDecimal(), nullable=True)
    temperature_max: Mapped[Decimal | None] = mapped_column(ExactDecimal(), nullable=True)
    temperature_mean: Mapped[Decimal | None] = mapped_column(ExactDecimal(), nullable=True)
    precipitation: Mapped[Decimal | None] = mapped_column(ExactDecimal(), nullable=True)
    relative_humidity: Mapped[Decimal | None] = mapped_column(ExactDecimal(), nullable=True)
    solar_radiation: Mapped[Decimal | None] = mapped_column(ExactDecimal(), nullable=True)
    wind_speed: Mapped[Decimal | None] = mapped_column(ExactDecimal(), nullable=True)
    raw_payload_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    payload_hash: Mapped[str] = mapped_column(Text, nullable=False)


class RealizedWeatherObservation(Base):
    __tablename__ = "realized_weather_observation"
    __table_args__ = (
        CheckConstraint(
            "base_id IS NOT NULL OR location_id IS NOT NULL",
            name="ck_realized_weather_scope",
        ),
        UniqueConstraint("payload_hash", name="uq_realized_weather_payload_hash"),
        Index("ix_realized_weather_scope_time", "base_id", "location_id", "observation_time"),
        Index("ix_realized_weather_known", "known_at"),
    )

    weather_observation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    base_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    observation_time: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    temperature: Mapped[Decimal | None] = mapped_column(ExactDecimal(), nullable=True)
    precipitation: Mapped[Decimal | None] = mapped_column(ExactDecimal(), nullable=True)
    humidity: Mapped[Decimal | None] = mapped_column(ExactDecimal(), nullable=True)
    solar_radiation: Mapped[Decimal | None] = mapped_column(ExactDecimal(), nullable=True)
    wind: Mapped[Decimal | None] = mapped_column(ExactDecimal(), nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_reference: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    known_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    payload_hash: Mapped[str] = mapped_column(Text, nullable=False)


class PhenologyObservation(Base):
    __tablename__ = "phenology_observation"
    __table_args__ = (
        UniqueConstraint("payload_hash", name="uq_phenology_observation_payload_hash"),
        Index("ix_phenology_base_season_known", "base_id", "season", "known_at"),
    )

    observation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    base_id: Mapped[str] = mapped_column(Text, nullable=False)
    farm_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    season: Mapped[str] = mapped_column(Text, nullable=False)
    phenology_stage: Mapped[str] = mapped_column(Text, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    known_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_reference: Mapped[str] = mapped_column(Text, nullable=False)
    quality_status: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_hash: Mapped[str] = mapped_column(Text, nullable=False)


class ForecastRunSnapshot(Base):
    __tablename__ = "forecast_run_snapshot"
    __table_args__ = (
        CheckConstraint(
            "forecast_end_date >= forecast_start_date",
            name="ck_forecast_snapshot_window",
        ),
        CheckConstraint("CAST(target_area_mu AS NUMERIC) > 0", name="ck_forecast_snapshot_area"),
        CheckConstraint("daily_row_count >= 1", name="ck_forecast_snapshot_daily_count"),
        CheckConstraint("model_status <> ''", name="ck_forecast_snapshot_model_status"),
        Index("ix_forecast_snapshot_base_season", "base_id", "target_season"),
        Index("ix_forecast_snapshot_created", "forecast_created_at", "forecast_run_id"),
    )

    forecast_run_id: Mapped[str] = mapped_column(Text, primary_key=True)
    forecast_created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    base_id: Mapped[str] = mapped_column(Text, nullable=False)
    target_season: Mapped[str] = mapped_column(Text, nullable=False)
    forecast_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    forecast_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    target_area_mu: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    forecast_mode: Mapped[str] = mapped_column(Text, nullable=False)
    model_status: Mapped[str] = mapped_column(Text, nullable=False)
    total_model_id: Mapped[str] = mapped_column(Text, nullable=False)
    temporal_model_id: Mapped[str] = mapped_column(Text, nullable=False)
    model_artifact_hashes: Mapped[dict[str, Any]] = mapped_column(_document(), nullable=False)
    prior_history_season: Mapped[str | None] = mapped_column(Text, nullable=True)
    prior_history_quantity_kg: Mapped[Decimal | None] = mapped_column(ExactDecimal(), nullable=True)
    prior_history_coverage_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    prior_history_source_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    prior_history_identity_mapping_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    area_revision_id: Mapped[str] = mapped_column(
        ForeignKey("area_revision.area_revision_id", ondelete="RESTRICT"), nullable=False
    )
    weather_snapshot_ids: Mapped[list[str]] = mapped_column(_document(), nullable=False)
    phenology_observation_ids: Mapped[list[str]] = mapped_column(_document(), nullable=False)
    input_snapshot_json: Mapped[dict[str, Any]] = mapped_column(_document(), nullable=False)
    input_snapshot_hash: Mapped[str] = mapped_column(Text, nullable=False)
    predicted_season_total_kg: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    single_day_peak: Mapped[dict[str, Any]] = mapped_column(_document(), nullable=False)
    rolling_7day_peak: Mapped[dict[str, Any]] = mapped_column(_document(), nullable=False)
    result_hash: Mapped[str] = mapped_column(Text, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(_document(), nullable=False)
    daily_row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class ForecastRunSnapshotDaily(Base):
    __tablename__ = "forecast_run_snapshot_daily"
    __table_args__ = (
        UniqueConstraint("forecast_run_id", "row_index", name="uq_forecast_snapshot_daily_index"),
        UniqueConstraint(
            "forecast_run_id", "forecast_date", name="uq_forecast_snapshot_daily_date"
        ),
        CheckConstraint("row_index >= 0", name="ck_forecast_snapshot_daily_index"),
        CheckConstraint(
            "CAST(predicted_quantity_kg AS NUMERIC) >= 0",
            name="ck_forecast_snapshot_daily_quantity",
        ),
        CheckConstraint(
            "CAST(normalized_share AS NUMERIC) >= 0",
            name="ck_forecast_snapshot_daily_share",
        ),
    )

    id: Mapped[int] = mapped_column(_sqlite_bigint(), primary_key=True, autoincrement=True)
    forecast_run_id: Mapped[str] = mapped_column(
        ForeignKey("forecast_run_snapshot.forecast_run_id", ondelete="RESTRICT"), nullable=False
    )
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    forecast_date: Mapped[date] = mapped_column(Date, nullable=False)
    predicted_quantity_kg: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)
    normalized_share: Mapped[Decimal] = mapped_column(ExactDecimal(), nullable=False)


__all__ = [
    "AreaRevision",
    "ForecastRunSnapshot",
    "ForecastRunSnapshotDaily",
    "PhenologyObservation",
    "RealizedWeatherObservation",
    "WeatherForecastSnapshot",
]
