from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base

_BIGINT_VARIANT = BigInteger().with_variant(Integer(), "sqlite")
_JSON_VARIANT = JSONB(astext_type=Text()).with_variant(JSON(), "sqlite")


def _sha256_check_sql(column_name: str) -> str:
    stripped = column_name
    for char in "0123456789abcdef":
        stripped = f"replace({stripped}, '{char}', '')"
    return (
        f"length({column_name}) = 64 and lower({column_name}) = {column_name} and {stripped} = ''"
    )


def _lifecycle_status_check(column_name: str = "status") -> str:
    return f"{column_name} in ('draft', 'active', 'superseded', 'retired', 'cancelled')"


def _forecast_quantile_check(column_name: str = "forecast_quantile") -> str:
    return f"{column_name} in ('P50', 'P80', 'P90')"


class Task9CapacityPoolDefinition(Base):
    __tablename__ = "task9_capacity_pool_definition"
    __table_args__ = (
        UniqueConstraint(
            "season_id",
            "destination_factory_id",
            "capacity_pool_code",
            "capacity_pool_version",
            "revision",
            name="uq_task9_capacity_pool_definition_business_revision",
        ),
        CheckConstraint("revision > 0", name="ck_task9_capacity_pool_definition_revision"),
        CheckConstraint(
            "capacity_pool_grain in ('FARM', 'SUBFARM', 'SUBFARM_VARIETY')",
            name="ck_task9_capacity_pool_definition_grain",
        ),
        CheckConstraint(
            "capacity_input_mode in ('LABOR_DERIVED', 'DIRECT_CAPACITY')",
            name="ck_task9_capacity_pool_definition_mode",
        ),
        CheckConstraint(
            "effective_to is null or effective_to >= effective_from",
            name="ck_task9_capacity_pool_definition_effective_range",
        ),
        CheckConstraint(
            _lifecycle_status_check(),
            name="ck_task9_capacity_pool_definition_status",
        ),
        CheckConstraint(
            _sha256_check_sql("row_hash"),
            name="ck_task9_capacity_pool_definition_row_hash_sha256",
        ),
    )

    id: Mapped[int] = mapped_column(_BIGINT_VARIANT, primary_key=True, autoincrement=True)
    season_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey("dim_season.id", ondelete="RESTRICT"),
        nullable=False,
    )
    destination_factory_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey("dim_factory.id", ondelete="RESTRICT"),
        nullable=False,
    )
    capacity_pool_code: Mapped[str] = mapped_column(Text, nullable=False)
    capacity_pool_version: Mapped[str] = mapped_column(Text, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    capacity_pool_grain: Mapped[str] = mapped_column(Text, nullable=False)
    capacity_input_mode: Mapped[str] = mapped_column(Text, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    available_at_local_date: Mapped[date] = mapped_column(Date, nullable=False)
    consumable_from_local_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    consumable_to_local_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    status_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_system: Mapped[str] = mapped_column(Text, nullable=False)
    source_record_key: Mapped[str] = mapped_column(Text, nullable=False)
    source_version: Mapped[str] = mapped_column(Text, nullable=False)
    row_hash: Mapped[str] = mapped_column(Text, nullable=False)
    superseded_by_id: Mapped[int | None] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey("task9_capacity_pool_definition.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Task9CapacityPoolMember(Base):
    __tablename__ = "task9_capacity_pool_member"
    __table_args__ = (
        # P0-7B: UNIQUE NULLS NOT DISTINCT will be added in migration 0014.
        # Plain UniqueConstraint removed — it silently accepts (NULL, NULL) duplicates.
        CheckConstraint("farm_id > 0", name="ck_task9_capacity_pool_member_farm_positive"),
        CheckConstraint(
            "subfarm_id is null or subfarm_id > 0",
            name="ck_task9_capacity_pool_member_subfarm_positive",
        ),
        CheckConstraint("variety_id > 0", name="ck_task9_capacity_pool_member_variety_positive"),
        CheckConstraint(
            _lifecycle_status_check(),
            name="ck_task9_capacity_pool_member_status",
        ),
        CheckConstraint(
            "effective_to is null or effective_to >= effective_from",
            name="ck_task9_capacity_pool_member_effective_range",
        ),
        CheckConstraint(
            _sha256_check_sql("row_hash"),
            name="ck_task9_capacity_pool_member_row_hash_sha256",
        ),
    )

    id: Mapped[int] = mapped_column(_BIGINT_VARIANT, primary_key=True, autoincrement=True)
    capacity_pool_definition_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey("task9_capacity_pool_definition.id", ondelete="RESTRICT"),
        nullable=False,
    )
    season_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey("dim_season.id", ondelete="RESTRICT"),
        nullable=False,
    )
    destination_factory_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey("dim_factory.id", ondelete="RESTRICT"),
        nullable=False,
    )
    farm_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey("dim_farm.id", ondelete="RESTRICT"),
        nullable=False,
    )
    subfarm_id: Mapped[int | None] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey("dim_subfarm.id", ondelete="RESTRICT"),
        nullable=True,
    )
    variety_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey("dim_variety.id", ondelete="RESTRICT"),
        nullable=False,
    )
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    consumable_from_key: Mapped[date] = mapped_column(Date, nullable=False)
    consumable_to_key: Mapped[date] = mapped_column(Date, nullable=False)
    row_hash: Mapped[str] = mapped_column(Text, nullable=False)


class Task9DailyCapacityAuthority(Base):
    __tablename__ = "task9_daily_capacity_authority"
    __table_args__ = (
        UniqueConstraint(
            "capacity_pool_definition_id",
            "capacity_date",
            "daily_capacity_revision",
            name="uq_task9_daily_capacity_authority_business_revision",
        ),
        CheckConstraint(
            "daily_capacity_revision > 0",
            name="ck_task9_daily_capacity_authority_revision",
        ),
        CheckConstraint(
            "(planned_picker_count is not null and kg_per_person_per_day is not null and "
            "direct_nominal_capacity_kg_per_day is null) or "
            "(direct_nominal_capacity_kg_per_day is not null and planned_picker_count is null "
            "and kg_per_person_per_day is null)",
            name="ck_task9_daily_capacity_authority_mode_fields",
        ),
        CheckConstraint(
            "labor_availability_ratio >= 0 and labor_availability_ratio <= 1",
            name="ck_task9_daily_capacity_authority_labor_ratio",
        ),
        CheckConstraint(
            "operational_efficiency_ratio >= 0 and operational_efficiency_ratio <= 1",
            name="ck_task9_daily_capacity_authority_operational_ratio",
        ),
        CheckConstraint(
            _lifecycle_status_check(),
            name="ck_task9_daily_capacity_authority_status",
        ),
        CheckConstraint(
            _sha256_check_sql("row_hash"),
            name="ck_task9_daily_capacity_authority_row_hash_sha256",
        ),
    )

    id: Mapped[int] = mapped_column(_BIGINT_VARIANT, primary_key=True, autoincrement=True)
    capacity_pool_definition_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey("task9_capacity_pool_definition.id", ondelete="RESTRICT"),
        nullable=False,
    )
    capacity_date: Mapped[date] = mapped_column(Date, nullable=False)
    daily_capacity_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    planned_picker_count: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    kg_per_person_per_day: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    direct_nominal_capacity_kg_per_day: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 3), nullable=True
    )
    labor_availability_ratio: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    operational_efficiency_ratio: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    available_at_local_date: Mapped[date] = mapped_column(Date, nullable=False)
    consumable_from_local_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    consumable_to_local_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    status_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    superseded_by_id: Mapped[int | None] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey("task9_daily_capacity_authority.id", ondelete="RESTRICT"),
        nullable=True,
    )
    source_system: Mapped[str] = mapped_column(Text, nullable=False)
    source_record_key: Mapped[str] = mapped_column(Text, nullable=False)
    source_version: Mapped[str] = mapped_column(Text, nullable=False)
    row_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    capacity_pool_definition: Mapped[Task9CapacityPoolDefinition] = relationship(
        "Task9CapacityPoolDefinition",
        lazy="selectin",
    )


class Task9HolidayCalendarVersion(Base):
    __tablename__ = "task9_holiday_calendar_version"
    __table_args__ = (
        UniqueConstraint(
            "season_id",
            "calendar_code",
            "lifecycle_timezone_name",
            "calendar_version",
            "revision",
            name="uq_task9_holiday_calendar_version_business_revision",
        ),
        CheckConstraint("revision > 0", name="ck_task9_holiday_calendar_version_revision"),
        CheckConstraint(
            "btrim(lifecycle_timezone_name) <> ''",
            name="ck_task9_holiday_calendar_version_timezone_non_blank",
        ),
        CheckConstraint(
            _lifecycle_status_check(),
            name="ck_task9_holiday_calendar_version_status",
        ),
        CheckConstraint(
            _sha256_check_sql("calendar_hash"),
            name="ck_task9_holiday_calendar_version_calendar_hash_sha256",
        ),
        CheckConstraint(
            _sha256_check_sql("row_hash"),
            name="ck_task9_holiday_calendar_version_row_hash_sha256",
        ),
    )

    id: Mapped[int] = mapped_column(_BIGINT_VARIANT, primary_key=True, autoincrement=True)
    season_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey("dim_season.id", ondelete="RESTRICT"),
        nullable=False,
    )
    calendar_code: Mapped[str] = mapped_column(Text, nullable=False)
    lifecycle_timezone_name: Mapped[str] = mapped_column(Text, nullable=False)
    calendar_version: Mapped[str] = mapped_column(Text, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    region_scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    calendar_hash: Mapped[str] = mapped_column(Text, nullable=False)
    available_at_local_date: Mapped[date] = mapped_column(Date, nullable=False)
    consumable_from_local_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    consumable_to_local_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    status_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    superseded_by_id: Mapped[int | None] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey("task9_holiday_calendar_version.id", ondelete="RESTRICT"),
        nullable=True,
    )
    source_system: Mapped[str] = mapped_column(Text, nullable=False)
    source_record_key: Mapped[str] = mapped_column(Text, nullable=False)
    source_version: Mapped[str] = mapped_column(Text, nullable=False)
    row_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Task9HolidayCalendarDate(Base):
    __tablename__ = "task9_holiday_calendar_date"
    __table_args__ = (
        UniqueConstraint(
            "holiday_calendar_version_id",
            "holiday_date",
            "holiday_code",
            name="uq_task9_holiday_calendar_date_business_key",
        ),
    )

    id: Mapped[int] = mapped_column(_BIGINT_VARIANT, primary_key=True, autoincrement=True)
    holiday_calendar_version_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey("task9_holiday_calendar_version.id", ondelete="RESTRICT"),
        nullable=False,
    )
    holiday_date: Mapped[date] = mapped_column(Date, nullable=False)
    holiday_code: Mapped[str] = mapped_column(Text, nullable=False)
    holiday_name: Mapped[str] = mapped_column(Text, nullable=False)


class Task9WeatherRuleConfigVersion(Base):
    __tablename__ = "task9_weather_rule_config_version"
    __table_args__ = (
        UniqueConstraint(
            "rule_code",
            "lifecycle_timezone_name",
            "rule_version",
            "revision",
            name="uq_task9_weather_rule_config_version_business_revision",
        ),
        CheckConstraint("revision > 0", name="ck_task9_weather_rule_config_version_revision"),
        CheckConstraint(
            "btrim(lifecycle_timezone_name) <> ''",
            name="ck_task9_weather_rule_config_version_timezone_non_blank",
        ),
        CheckConstraint(
            "maximum_ratio >= minimum_ratio",
            name="ck_task9_weather_rule_config_version_ratio_bounds",
        ),
        CheckConstraint(
            "missing_feature_policy = 'BLOCK'",
            name="ck_task9_weather_rule_config_version_missing_feature_policy",
        ),
        CheckConstraint(
            _lifecycle_status_check(),
            name="ck_task9_weather_rule_config_version_status",
        ),
        CheckConstraint(
            _sha256_check_sql("config_hash"),
            name="ck_task9_weather_rule_config_version_config_hash_sha256",
        ),
        CheckConstraint(
            _sha256_check_sql("row_hash"),
            name="ck_task9_weather_rule_config_version_row_hash_sha256",
        ),
    )

    id: Mapped[int] = mapped_column(_BIGINT_VARIANT, primary_key=True, autoincrement=True)
    rule_code: Mapped[str] = mapped_column(Text, nullable=False)
    lifecycle_timezone_name: Mapped[str] = mapped_column(Text, nullable=False)
    rule_version: Mapped[str] = mapped_column(Text, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    combination_method: Mapped[str] = mapped_column(Text, nullable=False)
    minimum_ratio: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    maximum_ratio: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    required_feature_ids: Mapped[list[str]] = mapped_column(_JSON_VARIANT, nullable=False)
    feature_rules_json: Mapped[list[dict[str, Any]]] = mapped_column(_JSON_VARIANT, nullable=False)
    missing_feature_policy: Mapped[str] = mapped_column(Text, nullable=False)
    config_hash: Mapped[str] = mapped_column(Text, nullable=False)
    available_at_local_date: Mapped[date] = mapped_column(Date, nullable=False)
    consumable_from_local_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    consumable_to_local_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    status_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    superseded_by_id: Mapped[int | None] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey("task9_weather_rule_config_version.id", ondelete="RESTRICT"),
        nullable=True,
    )
    source_system: Mapped[str] = mapped_column(Text, nullable=False)
    source_record_key: Mapped[str] = mapped_column(Text, nullable=False)
    source_version: Mapped[str] = mapped_column(Text, nullable=False)
    row_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Task9RunParameterPackage(Base):
    __tablename__ = "task9_run_parameter_package"
    __table_args__ = (
        UniqueConstraint(
            "season_id",
            "destination_factory_id",
            "farm_scope_key",
            "package_version",
            "revision",
            name="uq_task9_run_parameter_package_business_revision",
        ),
        CheckConstraint("revision > 0", name="ck_task9_run_parameter_package_revision"),
        CheckConstraint(
            "btrim(farm_timezone) <> ''",
            name="ck_task9_run_parameter_package_farm_timezone_non_blank",
        ),
        CheckConstraint(
            "btrim(destination_factory_timezone) <> ''",
            name="ck_task9_run_parameter_package_factory_timezone_non_blank",
        ),
        CheckConstraint(
            "harvest_to_arrival_lag_days >= 0",
            name="ck_task9_run_parameter_package_arrival_lag_non_negative",
        ),
        CheckConstraint(
            "effective_to is null or effective_to >= effective_from",
            name="ck_task9_run_parameter_package_effective_range",
        ),
        CheckConstraint(
            _lifecycle_status_check(),
            name="ck_task9_run_parameter_package_status",
        ),
        CheckConstraint(
            _sha256_check_sql("row_hash"),
            name="ck_task9_run_parameter_package_row_hash_sha256",
        ),
    )

    id: Mapped[int] = mapped_column(_BIGINT_VARIANT, primary_key=True, autoincrement=True)
    season_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey("dim_season.id", ondelete="RESTRICT"),
        nullable=False,
    )
    destination_factory_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey("dim_factory.id", ondelete="RESTRICT"),
        nullable=False,
    )
    farm_scope_key: Mapped[str] = mapped_column(Text, nullable=False)
    package_version: Mapped[str] = mapped_column(Text, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    farm_timezone: Mapped[str] = mapped_column(Text, nullable=False)
    destination_factory_timezone: Mapped[str] = mapped_column(Text, nullable=False)
    harvest_bucket_anchor_local_time: Mapped[time] = mapped_column(Time, nullable=False)
    harvest_to_arrival_lag_days: Mapped[int] = mapped_column(Integer, nullable=False)
    holiday_calendar_version_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey("task9_holiday_calendar_version.id", ondelete="RESTRICT"),
        nullable=False,
    )
    weather_rule_config_version_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey("task9_weather_rule_config_version.id", ondelete="RESTRICT"),
        nullable=False,
    )
    available_at_local_date: Mapped[date] = mapped_column(Date, nullable=False)
    consumable_from_local_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    consumable_to_local_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    status_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    superseded_by_id: Mapped[int | None] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey("task9_run_parameter_package.id", ondelete="RESTRICT"),
        nullable=True,
    )
    source_system: Mapped[str] = mapped_column(Text, nullable=False)
    source_record_key: Mapped[str] = mapped_column(Text, nullable=False)
    source_version: Mapped[str] = mapped_column(Text, nullable=False)
    row_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Task9InitialInventorySnapshot(Base):
    __tablename__ = "task9_initial_inventory_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "season_id",
            "destination_factory_id",
            "opening_state_date",
            "snapshot_version",
            "revision",
            name="uq_task9_initial_inventory_snapshot_business_revision",
        ),
        CheckConstraint(
            "revision > 0",
            name="ck_task9_initial_inventory_snapshot_revision",
        ),
        CheckConstraint(
            "initial_opening_mature_inventory_kg >= 0",
            name="ck_task9_initial_inventory_snapshot_opening_non_negative",
        ),
        CheckConstraint(
            _lifecycle_status_check(),
            name="ck_task9_initial_inventory_snapshot_status",
        ),
        CheckConstraint(
            _sha256_check_sql("row_hash"),
            name="ck_task9_initial_inventory_snapshot_row_hash_sha256",
        ),
    )

    id: Mapped[int] = mapped_column(_BIGINT_VARIANT, primary_key=True, autoincrement=True)
    season_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey("dim_season.id", ondelete="RESTRICT"),
        nullable=False,
    )
    destination_factory_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey("dim_factory.id", ondelete="RESTRICT"),
        nullable=False,
    )
    opening_state_date: Mapped[date] = mapped_column(Date, nullable=False)
    snapshot_version: Mapped[str] = mapped_column(Text, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    initial_opening_mature_inventory_kg: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False
    )
    available_at_local_date: Mapped[date] = mapped_column(Date, nullable=False)
    consumable_from_local_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    consumable_to_local_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    status_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    superseded_by_id: Mapped[int | None] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey("task9_initial_inventory_snapshot.id", ondelete="RESTRICT"),
        nullable=True,
    )
    source_system: Mapped[str] = mapped_column(Text, nullable=False)
    source_record_key: Mapped[str] = mapped_column(Text, nullable=False)
    source_version: Mapped[str] = mapped_column(Text, nullable=False)
    row_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Task9InitialInventoryCohort(Base):
    __tablename__ = "task9_initial_inventory_cohort"
    __table_args__ = (
        UniqueConstraint(
            "initial_inventory_snapshot_id",
            "stable_cohort_key",
            name="uq_task9_initial_inventory_cohort_stable_key",
        ),
        CheckConstraint(
            _forecast_quantile_check(),
            name="ck_task9_initial_inventory_cohort_quantile",
        ),
        CheckConstraint(
            "remaining_quantity_kg >= 0",
            name="ck_task9_initial_inventory_cohort_remaining_non_negative",
        ),
        CheckConstraint(
            _sha256_check_sql("row_hash"),
            name="ck_task9_initial_inventory_cohort_row_hash_sha256",
        ),
    )

    id: Mapped[int] = mapped_column(_BIGINT_VARIANT, primary_key=True, autoincrement=True)
    initial_inventory_snapshot_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey("task9_initial_inventory_snapshot.id", ondelete="RESTRICT"),
        nullable=False,
    )
    stable_cohort_key: Mapped[str] = mapped_column(Text, nullable=False)
    forecast_quantile: Mapped[str] = mapped_column(Text, nullable=False)
    cohort_date: Mapped[date] = mapped_column(Date, nullable=False)
    farm_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey("dim_farm.id", ondelete="RESTRICT"),
        nullable=False,
    )
    subfarm_id: Mapped[int | None] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey("dim_subfarm.id", ondelete="RESTRICT"),
        nullable=True,
    )
    variety_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey("dim_variety.id", ondelete="RESTRICT"),
        nullable=False,
    )
    remaining_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    row_hash: Mapped[str] = mapped_column(Text, nullable=False)


class Task9MatureInventoryLossAuthority(Base):
    __tablename__ = "task9_mature_inventory_loss_authority"
    __table_args__ = (
        UniqueConstraint(
            "season_id",
            "destination_factory_id",
            "state_date",
            "capacity_pool_code",
            "forecast_quantile",
            "loss_version",
            "revision",
            name="uq_task9_mature_inventory_loss_authority_business_revision",
        ),
        CheckConstraint(
            "revision > 0",
            name="ck_task9_mature_inventory_loss_authority_revision",
        ),
        CheckConstraint(
            _forecast_quantile_check(),
            name="ck_task9_mature_inventory_loss_authority_quantile",
        ),
        CheckConstraint(
            "mature_inventory_loss_quantity_kg >= 0",
            name="ck_task9_mature_inventory_loss_authority_quantity_non_negative",
        ),
        CheckConstraint(
            _lifecycle_status_check(),
            name="ck_task9_mature_inventory_loss_authority_status",
        ),
        CheckConstraint(
            _sha256_check_sql("row_hash"),
            name="ck_task9_mature_inventory_loss_authority_row_hash_sha256",
        ),
    )

    id: Mapped[int] = mapped_column(_BIGINT_VARIANT, primary_key=True, autoincrement=True)
    season_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey("dim_season.id", ondelete="RESTRICT"),
        nullable=False,
    )
    destination_factory_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey("dim_factory.id", ondelete="RESTRICT"),
        nullable=False,
    )
    state_date: Mapped[date] = mapped_column(Date, nullable=False)
    capacity_pool_code: Mapped[str] = mapped_column(Text, nullable=False)
    forecast_quantile: Mapped[str] = mapped_column(Text, nullable=False)
    loss_version: Mapped[str] = mapped_column(Text, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    mature_inventory_loss_quantity_kg: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False
    )
    available_at_local_date: Mapped[date] = mapped_column(Date, nullable=False)
    consumable_from_local_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    consumable_to_local_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    status_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    superseded_by_id: Mapped[int | None] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey("task9_mature_inventory_loss_authority.id", ondelete="RESTRICT"),
        nullable=True,
    )
    source_system: Mapped[str] = mapped_column(Text, nullable=False)
    source_record_key: Mapped[str] = mapped_column(Text, nullable=False)
    source_version: Mapped[str] = mapped_column(Text, nullable=False)
    row_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Task9AuthorityLifecycleEvent(Base):
    __tablename__ = "task9_authority_lifecycle_event"
    __table_args__ = (
        UniqueConstraint(
            "authority_family",
            "authority_stable_key",
            "authority_business_version",
            "authority_revision",
            "transition_sequence",
            name="uq_task9_authority_lifecycle_event_identity_sequence",
        ),
        UniqueConstraint(
            "authority_family",
            "authority_stable_key",
            "authority_business_version",
            "authority_revision",
            "lifecycle_event_hash",
            name="uq_task9_authority_lifecycle_event_identity_hash",
        ),
        CheckConstraint(
            "authority_revision > 0",
            name="ck_task9_authority_lifecycle_event_revision_positive",
        ),
        CheckConstraint(
            "transition_sequence >= 1",
            name="ck_task9_authority_lifecycle_event_transition_sequence_positive",
        ),
        CheckConstraint(
            "superseded_by_authority_revision is null or superseded_by_authority_revision > 0",
            name="ck_task9_lifecycle_event_repl_rev_positive",
        ),
        CheckConstraint(
            "old_status is null or "
            "old_status in ('draft', 'active', 'superseded', 'retired', 'cancelled')",
            name="ck_task9_authority_lifecycle_event_old_status",
        ),
        CheckConstraint(
            "new_status in ('draft', 'active', 'superseded', 'retired', 'cancelled')",
            name="ck_task9_authority_lifecycle_event_new_status",
        ),
        CheckConstraint(
            "((superseded_by_authority_stable_key is null and "
            "superseded_by_authority_business_version is null and "
            "superseded_by_authority_revision is null) or "
            "(superseded_by_authority_stable_key is not null and "
            "superseded_by_authority_business_version is not null and "
            "superseded_by_authority_revision is not null))",
            name="ck_task9_authority_lifecycle_event_replacement_all_or_none",
        ),
        CheckConstraint(
            "((new_status = 'superseded' and superseded_by_authority_stable_key is not null) "
            "or (new_status <> 'superseded' and superseded_by_authority_stable_key is null))",
            name="ck_task9_lifecycle_event_superseded_repl",
        ),
        CheckConstraint(
            _sha256_check_sql("business_row_hash"),
            name="ck_task9_authority_lifecycle_event_business_row_hash_sha256",
        ),
        CheckConstraint(
            _sha256_check_sql("lifecycle_event_hash"),
            name="ck_task9_authority_lifecycle_event_hash_sha256",
        ),
    )

    id: Mapped[int] = mapped_column(_BIGINT_VARIANT, primary_key=True, autoincrement=True)
    authority_family: Mapped[str] = mapped_column(Text, nullable=False)
    authority_stable_key: Mapped[str] = mapped_column(Text, nullable=False)
    authority_business_version: Mapped[str] = mapped_column(Text, nullable=False)
    authority_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    business_row_hash: Mapped[str] = mapped_column(Text, nullable=False)
    transition_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    old_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_status: Mapped[str] = mapped_column(Text, nullable=False)
    old_consumable_from_local_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    old_consumable_to_local_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    new_consumable_from_local_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    new_consumable_to_local_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    superseded_by_authority_stable_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    superseded_by_authority_business_version: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    superseded_by_authority_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transitioned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_system: Mapped[str] = mapped_column(Text, nullable=False)
    source_record_key: Mapped[str] = mapped_column(Text, nullable=False)
    lifecycle_event_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
