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


class WeatherSourceLocation(Base):
    __tablename__ = "weather_source_location"
    __table_args__ = (
        UniqueConstraint(
            "provider_code",
            "external_location_id",
            "source_version",
            name="uq_weather_src_loc_provider_ext_ver",
        ),
        UniqueConstraint(
            "row_hash",
            name="uq_weather_src_loc_row_hash",
        ),
        CheckConstraint(
            "location_type in ('station', 'grid')",
            name="ck_weather_src_loc_type",
        ),
        CheckConstraint(
            "latitude >= -90 and latitude <= 90",
            name="ck_weather_src_loc_latitude",
        ),
        CheckConstraint(
            "longitude >= -180 and longitude <= 180",
            name="ck_weather_src_loc_longitude",
        ),
        CheckConstraint(
            "valid_to is null or valid_to >= valid_from",
            name="ck_weather_src_loc_valid_range",
        ),
        Index("ix_weather_src_loc_provider", "provider_code"),
        Index("ix_weather_src_loc_type", "location_type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider_code: Mapped[str] = mapped_column(Text, nullable=False)
    external_location_id: Mapped[str] = mapped_column(Text, nullable=False)
    location_type: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    altitude_m: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    timezone_name: Mapped[str] = mapped_column(Text, nullable=False)
    grid_resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_version: Mapped[str] = mapped_column(Text, nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    row_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class WeatherDailyObservation(Base):
    __tablename__ = "weather_daily_observation"
    __table_args__ = (
        UniqueConstraint(
            "row_hash",
            name="uq_weather_daily_obs_row_hash",
        ),
        CheckConstraint(
            "temperature_max_c >= temperature_min_c",
            name="ck_weather_daily_obs_temp_range",
        ),
        CheckConstraint(
            "temperature_mean_c is null "
            "or (temperature_mean_c >= temperature_min_c "
            "and temperature_mean_c <= temperature_max_c)",
            name="ck_weather_daily_obs_mean_range",
        ),
        CheckConstraint(
            "temperature_mean_source in ('provided', 'derived')",
            name="ck_weather_daily_obs_mean_source",
        ),
        CheckConstraint(
            "precipitation_mm >= 0",
            name="ck_weather_daily_obs_precip_non_negative",
        ),
        CheckConstraint(
            "solar_radiation_mj_m2 is null or solar_radiation_mj_m2 >= 0",
            name="ck_weather_daily_obs_solar_non_negative",
        ),
        Index("ix_weather_daily_obs_source_loc_id", "weather_source_location_id"),
        Index("ix_weather_daily_obs_obs_date", "observation_date"),
        Index("ix_weather_daily_obs_available_at", "available_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    weather_source_location_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "weather_source_location.id",
            name="fk_weather_daily_obs_src_loc_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    observation_date: Mapped[date] = mapped_column(Date, nullable=False)
    temperature_min_c: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    temperature_max_c: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    temperature_mean_c: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    temperature_mean_source: Mapped[str] = mapped_column(Text, nullable=False)
    precipitation_mm: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    solar_radiation_mj_m2: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6),
        nullable=True,
    )
    provider_code: Mapped[str] = mapped_column(Text, nullable=False)
    source_version: Mapped[str] = mapped_column(Text, nullable=False)
    available_at: Mapped[date] = mapped_column(Date, nullable=False)
    quality_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    quality_flags: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    source_file_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_row_number: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    row_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class WeatherImportRun(Base):
    __tablename__ = "weather_import_run"
    __table_args__ = (
        CheckConstraint(
            "import_type in ('location', 'observation', 'mapping')",
            name="ck_weather_import_run_type",
        ),
        CheckConstraint(
            "status in ('running', 'completed', 'failed')",
            name="ck_weather_import_run_status",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    import_type: Mapped[str] = mapped_column(Text, nullable=False)
    provider_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    file_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    source_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    dry_run: Mapped[bool] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    row_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    inserted_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    skipped_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    duplicate_count: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default="0",
    )
    rejected_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    invalid_date_count: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default="0",
    )
    invalid_numeric_count: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default="0",
    )
    unknown_location_count: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default="0",
    )
    conflict_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    report_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class LocationWeatherMapping(Base):
    __tablename__ = "location_weather_mapping"
    __table_args__ = (
        UniqueConstraint(
            "row_hash",
            name="uq_location_weather_mapping_row_hash",
        ),
        CheckConstraint(
            "mapping_method in ('explicit', 'nearest_station', 'nearest_grid')",
            name="ck_location_weather_mapping_method",
        ),
        CheckConstraint(
            "distance_km >= 0",
            name="ck_location_weather_mapping_distance",
        ),
        CheckConstraint(
            "mapping_score >= 0",
            name="ck_location_weather_mapping_score",
        ),
        CheckConstraint(
            "valid_to is null or valid_to >= valid_from",
            name="ck_location_weather_mapping_valid_range",
        ),
        Index("ix_loc_weather_mapping_loc_ref_id", "location_reference_id"),
        Index("ix_loc_weather_mapping_src_loc_id", "weather_source_location_id"),
        Index("ix_loc_weather_mapping_available_at", "available_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    location_reference_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "location_reference.id",
            name="fk_loc_weather_mapping_loc_ref_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    weather_source_location_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "weather_source_location.id",
            name="fk_loc_weather_mapping_src_loc_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    mapping_method: Mapped[str] = mapped_column(Text, nullable=False)
    distance_km: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    altitude_difference_m: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    mapping_score: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    confidence_level: Mapped[str] = mapped_column(Text, nullable=False)
    mapping_version: Mapped[str] = mapped_column(Text, nullable=False)
    config_hash: Mapped[str] = mapped_column(Text, nullable=False)
    available_at: Mapped[date] = mapped_column(Date, nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    row_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class BaseTemperatureSearchRun(Base):
    __tablename__ = "base_temperature_search_run"
    __table_args__ = (
        CheckConstraint(
            "status in ('running', 'completed', 'failed', 'unavailable')",
            name="ck_base_temp_search_run_status",
        ),
        Index(
            "ux_base_temp_search_run_active_or_done",
            "source_signature",
            unique=True,
            postgresql_where=text("status in ('running', 'completed', 'unavailable')"),
        ),
        Index("ix_base_temp_search_run_variety_id", "variety_id"),
        Index("ix_base_temp_search_run_zone_id", "climate_zone_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    scope_type: Mapped[str] = mapped_column(Text, nullable=False)
    variety_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "dim_variety.id",
            name="fk_base_temp_search_run_variety_id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    climate_zone_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "dim_agro_climate_zone.id",
            name="fk_base_temp_search_run_zone_id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    training_cutoff: Mapped[date] = mapped_column(Date, nullable=False)
    anchor_event: Mapped[str] = mapped_column(Text, nullable=False)
    target_event: Mapped[str] = mapped_column(Text, nullable=False)
    candidate_temperatures: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    selected_base_temperature: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6),
        nullable=True,
    )
    scoring_method: Mapped[str] = mapped_column(Text, nullable=False)
    selected_score: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    sample_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    distinct_season_count: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default="0",
    )
    training_sample_ids: Mapped[list[int]] = mapped_column(JSONB, nullable=False)
    candidate_scores: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    config_hash: Mapped[str] = mapped_column(Text, nullable=False)
    feature_version: Mapped[str] = mapped_column(Text, nullable=False)
    source_signature: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    blockers: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class WeatherFeatureRun(Base):
    __tablename__ = "weather_feature_run"
    __table_args__ = (
        CheckConstraint(
            "status in ('running', 'completed', 'failed', 'unavailable')",
            name="ck_weather_feature_run_status",
        ),
        Index(
            "ux_weather_feature_run_active_or_done",
            "source_signature",
            unique=True,
            postgresql_where=text("status in ('running', 'completed', 'unavailable')"),
        ),
        Index("ix_weather_feature_run_plan_id", "plan_id"),
        Index("ix_weather_feature_run_feature_date", "feature_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    feature_version: Mapped[str] = mapped_column(Text, nullable=False)
    config_hash: Mapped[str] = mapped_column(Text, nullable=False)
    mapping_version: Mapped[str] = mapped_column(Text, nullable=False)
    weather_source_version: Mapped[str] = mapped_column(Text, nullable=False)
    base_temperature_search_run_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "base_temperature_search_run.id",
            name="fk_weather_feature_run_base_temp_run_id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    plan_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "farm_season_variety_plan.id",
            name="fk_weather_feature_run_plan_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    location_reference_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "location_reference.id",
            name="fk_weather_feature_run_loc_ref_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    location_weather_mapping_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "location_weather_mapping.id",
            name="fk_weather_feature_run_mapping_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    weather_source_location_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "weather_source_location.id",
            name="fk_weather_feature_run_src_loc_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    feature_date: Mapped[date] = mapped_column(Date, nullable=False)
    source_signature: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    window_features: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    timeline_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    weather_observation_ids: Mapped[list[int]] = mapped_column(JSONB, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    blockers: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
