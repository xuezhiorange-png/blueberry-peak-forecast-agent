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


class AgroClimateZone(Base):
    __tablename__ = "dim_agro_climate_zone"
    __table_args__ = (
        UniqueConstraint(
            "code",
            "zone_version",
            name="uq_dim_agro_climate_zone_code_version",
        ),
        CheckConstraint(
            "centroid_latitude >= -90 and centroid_latitude <= 90",
            name="ck_dim_agro_climate_zone_latitude_range",
        ),
        CheckConstraint(
            "centroid_longitude >= -180 and centroid_longitude <= 180",
            name="ck_dim_agro_climate_zone_longitude_range",
        ),
        CheckConstraint(
            "min_altitude_m is null or max_altitude_m is null or min_altitude_m <= max_altitude_m",
            name="ck_dim_agro_climate_zone_altitude_range",
        ),
        CheckConstraint(
            "valid_to is null or valid_to >= valid_from",
            name="ck_dim_agro_climate_zone_valid_range",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    country: Mapped[str] = mapped_column(Text, nullable=False)
    province: Mapped[str] = mapped_column(Text, nullable=False)
    prefecture: Mapped[str | None] = mapped_column(Text, nullable=True)
    county: Mapped[str | None] = mapped_column(Text, nullable=True)
    centroid_latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    centroid_longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    min_altitude_m: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    max_altitude_m: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    zone_version: Mapped[str] = mapped_column(Text, nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_version: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ClimateZoneImportRun(Base):
    __tablename__ = "climate_zone_import_run"
    __table_args__ = (
        CheckConstraint(
            "status in ('running', 'completed', 'failed')",
            name="ck_climate_zone_import_run_status",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    file_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    zone_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    row_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    valid_row_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    invalid_row_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    inserted_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    skipped_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
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


class LocationReference(Base):
    __tablename__ = "location_reference"
    __table_args__ = (
        UniqueConstraint(
            "source_version",
            "source_row_hash",
            name="uq_location_reference_source_version_row_hash",
        ),
        CheckConstraint(
            "latitude >= -90 and latitude <= 90",
            name="ck_location_reference_latitude_range",
        ),
        CheckConstraint(
            "longitude >= -180 and longitude <= 180",
            name="ck_location_reference_longitude_range",
        ),
        CheckConstraint(
            "valid_to is null or valid_to >= valid_from",
            name="ck_location_reference_valid_range",
        ),
        Index("ix_location_reference_address_normalized", "address_normalized"),
        Index("ix_location_reference_climate_zone_id", "climate_zone_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    farm_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "dim_farm.id",
            name="fk_location_reference_farm_id_dim_farm",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    subfarm_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "dim_subfarm.id",
            name="fk_location_reference_subfarm_id_dim_subfarm",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    farm_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    farm_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    subfarm_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    province: Mapped[str | None] = mapped_column(Text, nullable=True)
    prefecture: Mapped[str | None] = mapped_column(Text, nullable=True)
    county: Mapped[str | None] = mapped_column(Text, nullable=True)
    township: Mapped[str | None] = mapped_column(Text, nullable=True)
    village: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    altitude_m: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    climate_zone_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "dim_agro_climate_zone.id",
            name="fk_location_reference_climate_zone_id_dim_agro_climate_zone",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    location_source: Mapped[str] = mapped_column(Text, nullable=False)
    source_version: Mapped[str] = mapped_column(Text, nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_row_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ParameterLibraryVersion(Base):
    __tablename__ = "parameter_library_version"
    __table_args__ = (
        UniqueConstraint(
            "version_code",
            name="uq_parameter_library_version_version_code",
        ),
        CheckConstraint(
            "status in ('draft', 'active', 'retired', 'failed')",
            name="ck_parameter_library_version_status",
        ),
        Index(
            "ux_parameter_library_version_active",
            "status",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    version_code: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_file_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_hash: Mapped[str] = mapped_column(Text, nullable=False)
    record_count: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default="0",
    )
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ParameterObservation(Base):
    __tablename__ = "parameter_observation"
    __table_args__ = (
        UniqueConstraint(
            "library_version_id",
            "source_row_hash",
            name="uq_parameter_observation_library_row_hash",
        ),
        CheckConstraint(
            "parameter_type in ("
            "'yield_kg_per_mu',"
            "'marketable_rate',"
            "'first_harvest_offset_days',"
            "'maturity_peak_offset_days',"
            "'maturity_width_days',"
            "'maturity_skewness',"
            "'harvest_realization_rate'"
            ")",
            name="ck_parameter_observation_parameter_type",
        ),
        CheckConstraint(
            "parameter_type != 'yield_kg_per_mu' or scalar_value > 0",
            name="ck_parameter_observation_yield_positive",
        ),
        CheckConstraint(
            "parameter_type != 'marketable_rate' or (scalar_value >= 0 and scalar_value <= 1)",
            name="ck_parameter_observation_marketable_rate_range",
        ),
        CheckConstraint(
            "parameter_type != 'harvest_realization_rate' "
            "or (scalar_value >= 0 and scalar_value <= 1)",
            name="ck_parameter_observation_harvest_realization_rate_range",
        ),
        CheckConstraint(
            "parameter_type != 'maturity_width_days' or scalar_value > 0",
            name="ck_parameter_observation_width_positive",
        ),
        CheckConstraint(
            "sample_weight > 0",
            name="ck_parameter_observation_sample_weight_positive",
        ),
        CheckConstraint(
            "valid_to is null or valid_to >= valid_from",
            name="ck_parameter_observation_valid_range",
        ),
        Index("ix_parameter_observation_variety_id", "variety_id"),
        Index("ix_parameter_observation_parameter_type", "parameter_type"),
        Index("ix_parameter_observation_climate_zone_id", "climate_zone_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    library_version_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "parameter_library_version.id",
            name="fk_param_obs_lib_ver_id_param_lib_ver",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    parameter_type: Mapped[str] = mapped_column(Text, nullable=False)
    variety_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "dim_variety.id",
            name="fk_parameter_observation_variety_id_dim_variety",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    farm_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "dim_farm.id",
            name="fk_parameter_observation_farm_id_dim_farm",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    subfarm_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "dim_subfarm.id",
            name="fk_parameter_observation_subfarm_id_dim_subfarm",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    location_reference_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "location_reference.id",
            name="fk_param_obs_loc_ref_id_location_ref",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    climate_zone_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "dim_agro_climate_zone.id",
            name="fk_parameter_observation_climate_zone_id_dim_agro_climate_zone",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    season_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "dim_season.id",
            name="fk_parameter_observation_season_id_dim_season",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    province: Mapped[str | None] = mapped_column(Text, nullable=True)
    prefecture: Mapped[str | None] = mapped_column(Text, nullable=True)
    county: Mapped[str | None] = mapped_column(Text, nullable=True)
    township: Mapped[str | None] = mapped_column(Text, nullable=True)
    altitude_m: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    scalar_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    sample_weight: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    source_level: Mapped[str] = mapped_column(Text, nullable=False)
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_version: Mapped[str] = mapped_column(Text, nullable=False)
    historical_mape: Mapped[Decimal | None] = mapped_column(Numeric(12, 10), nullable=True)
    date_mae_days: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    p90_coverage: Mapped[Decimal | None] = mapped_column(Numeric(12, 10), nullable=True)
    available_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_row_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class MinimalForecastTask(Base):
    __tablename__ = "minimal_forecast_task"
    __table_args__ = (
        CheckConstraint(
            "status in ('created', 'resolving_location', 'inferring_parameters', "
            "'parameters_ready', 'failed')",
            name="ck_minimal_forecast_task_status",
        ),
        UniqueConstraint(
            "input_hash",
            "as_of_date",
            name="uq_minimal_forecast_task_input_hash_as_of",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    input_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    normalized_input: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    input_hash: Mapped[str] = mapped_column(Text, nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class ParameterInferenceRun(Base):
    __tablename__ = "parameter_inference_run"
    __table_args__ = (
        CheckConstraint(
            "status in ('running', 'completed', 'failed')",
            name="ck_parameter_inference_run_status",
        ),
        Index(
            "ux_parameter_inference_run_active_or_completed",
            "input_hash",
            "as_of_date",
            "resolver_version",
            "library_version_id",
            "config_hash",
            unique=True,
            postgresql_where=text("status in ('running', 'completed')"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "minimal_forecast_task.id",
            name="fk_parameter_inference_run_task_id_minimal_forecast_task",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    input_hash: Mapped[str] = mapped_column(Text, nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    resolver_version: Mapped[str] = mapped_column(Text, nullable=False)
    library_version_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "parameter_library_version.id",
            name="fk_param_infer_run_lib_ver_id_param_lib_ver",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    config_hash: Mapped[str] = mapped_column(Text, nullable=False)
    source_signature: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
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


class ParameterInferenceResult(Base):
    __tablename__ = "parameter_inference_result"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "variety_id",
            "parameter_type",
            name="uq_parameter_inference_result_run_variety_parameter",
        ),
        CheckConstraint(
            "status in ('available', 'unavailable')",
            name="ck_parameter_inference_result_status",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "parameter_inference_run.id",
            name="fk_parameter_inference_result_run_id_parameter_inference_run",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    variety_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "dim_variety.id",
            name="fk_parameter_inference_result_variety_id_dim_variety",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    parameter_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    p50_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    p80_lower: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    p80_upper: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    source_level: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_level: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(12, 10), nullable=True)
    sample_count: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default="0",
    )
    season_count: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default="0",
    )
    farm_count: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default="0",
    )
    source_observation_ids: Mapped[list[int]] = mapped_column(JSONB, nullable=False)
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    uncertainty_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
