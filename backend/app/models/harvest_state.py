from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, cast

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
from sqlalchemy.types import TypeDecorator

from backend.app.db.base import Base

_JSON_VARIANT = JSONB(astext_type=Text()).with_variant(JSON(), "sqlite")
_BIGINT_VARIANT = BigInteger().with_variant(Integer(), "sqlite")


class _AwareDateTimeType(TypeDecorator[datetime]):
    impl = DateTime(timezone=True)
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "sqlite":
            return dialect.type_descriptor(Text())
        return dialect.type_descriptor(DateTime(timezone=True))

    def process_bind_param(self, value: datetime | None, dialect: Any) -> Any:
        if value is None:
            return None
        if dialect.name == "sqlite":
            return value.isoformat()
        return value

    def process_result_value(self, value: Any, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if dialect.name == "sqlite":
            return datetime.fromisoformat(value)
        return cast(datetime, value)


_AWARE_DATETIME_VARIANT = _AwareDateTimeType()


def _sha256_check_sql(column_name: str) -> str:
    stripped = column_name
    for char in "0123456789abcdef":
        stripped = f"replace({stripped}, '{char}', '')"
    return (
        f"length({column_name}) = 64 "
        f"and lower({column_name}) = {column_name} "
        f"and {stripped} = ''"
    )


def _non_negative_check_sql(prefix: str, *columns: str) -> list[CheckConstraint]:
    return [
        CheckConstraint(f"{column} >= 0", name=f"ck_{prefix}_{column}_non_negative")
        for column in columns
    ]


class HarvestStateRun(Base):
    __tablename__ = "harvest_state_run"
    __table_args__ = (
        CheckConstraint(
            "status in ('completed', 'blocked')",
            name="ck_harvest_state_run_status",
        ),
        CheckConstraint(
            _sha256_check_sql("config_hash"),
            name="ck_harvest_state_run_config_hash",
        ),
        CheckConstraint(
            _sha256_check_sql("result_hash"),
            name="ck_harvest_state_run_result_hash",
        ),
        CheckConstraint(
            _sha256_check_sql("canonical_payload_hash"),
            name="ck_harvest_state_run_canonical_payload_hash",
        ),
        CheckConstraint(
            "forecast_end_date >= forecast_start_date",
            name="ck_harvest_state_run_forecast_date_range",
        ),
        *_non_negative_check_sql(
            "harvest_state_run",
            "pool_row_count",
            "member_row_count",
            "cohort_row_count",
            "future_arrival_row_count",
        ),
        UniqueConstraint("result_hash", name="uq_harvest_state_run_result_hash"),
        Index("ix_harvest_state_run_status", "status"),
        Index("ix_harvest_state_run_as_of_date", "as_of_date"),
        Index(
            "ix_harvest_state_run_maturity_forecast_run_id",
            "maturity_forecast_run_id",
        ),
        Index(
            "ix_harvest_state_run_maturity_model_run_id",
            "maturity_model_run_id",
        ),
    )

    id: Mapped[int] = mapped_column(_BIGINT_VARIANT, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    output_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    result_hash_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    resolved_parameter_snapshot_schema_version: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    source_ref_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    stable_cohort_key_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)
    resolved_parameter_snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        _JSON_VARIANT,
        nullable=True,
    )
    source_ref_catalog: Mapped[list[dict[str, Any]]] = mapped_column(_JSON_VARIANT, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(_JSON_VARIANT, nullable=False)
    blockers: Mapped[list[str]] = mapped_column(_JSON_VARIANT, nullable=False)
    mass_balance_result: Mapped[dict[str, Any] | None] = mapped_column(
        _JSON_VARIANT,
        nullable=True,
    )
    continuity_result: Mapped[dict[str, Any] | None] = mapped_column(
        _JSON_VARIANT,
        nullable=True,
    )
    canonical_output: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)
    config_hash: Mapped[str] = mapped_column(Text, nullable=False)
    result_hash: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    forecast_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    forecast_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    destination_factory_id: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    pool_row_count: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    member_row_count: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    cohort_row_count: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    future_arrival_row_count: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    maturity_model_run_id: Mapped[int | None] = mapped_column(_BIGINT_VARIANT, nullable=True)
    maturity_model_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    maturity_model_config_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    maturity_model_source_signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    maturity_model_artifact_id: Mapped[int | None] = mapped_column(_BIGINT_VARIANT, nullable=True)
    maturity_model_artifact_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    maturity_forecast_run_id: Mapped[int | None] = mapped_column(_BIGINT_VARIANT, nullable=True)
    maturity_forecast_source_signature: Mapped[str | None] = mapped_column(Text, nullable=True)
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


class HarvestStateDailyPoolRowModel(Base):
    __tablename__ = "harvest_state_daily_pool_row"
    __table_args__ = (
        CheckConstraint(
            "forecast_quantile in ('P50', 'P80', 'P90')",
            name="ck_harvest_state_daily_pool_quantile",
        ),
        CheckConstraint(
            "capacity_pool_grain in ('SUBFARM_VARIETY', 'SUBFARM', 'FARM')",
            name="ck_harvest_state_daily_pool_grain",
        ),
        CheckConstraint(
            "capacity_input_mode in ('LABOR_DERIVED', 'DIRECT_CAPACITY')",
            name="ck_harvest_state_daily_pool_input_mode",
        ),
        CheckConstraint(
            _sha256_check_sql("capacity_pool_membership_hash"),
            name="ck_harvest_state_daily_pool_membership_hash",
        ),
        CheckConstraint(
            "labor_availability_ratio >= 0 and labor_availability_ratio <= 1",
            name="ck_harvest_state_daily_pool_labor_ratio",
        ),
        CheckConstraint(
            "weather_harvest_efficiency_ratio >= 0 and weather_harvest_efficiency_ratio <= 1",
            name="ck_harvest_state_daily_pool_weather_ratio",
        ),
        CheckConstraint(
            "operational_efficiency_ratio >= 0 and operational_efficiency_ratio <= 1",
            name="ck_harvest_state_daily_pool_operational_ratio",
        ),
        *_non_negative_check_sql(
            "harvest_state_daily_pool",
            "opening_mature_inventory_kg",
            "natural_maturity_supply_kg",
            "available_mature_quantity_kg",
            "mature_inventory_loss_quantity_kg",
            "harvestable_mature_quantity_kg",
            "nominal_harvest_capacity_kg_per_day",
            "effective_harvest_capacity_kg_per_day",
            "effective_capacity_for_day_kg",
            "harvested_quantity_kg",
            "closing_mature_inventory_kg",
            "unharvested_backlog_kg",
            "arrival_quantity_kg",
            "opening_cohort_count",
            "closing_cohort_count",
            "member_count",
        ),
        UniqueConstraint(
            "harvest_state_run_id",
            "state_date",
            "capacity_pool_id",
            "forecast_quantile",
            name="uq_harvest_state_daily_pool_business_key",
        ),
        Index("ix_harvest_state_daily_pool_run_id", "harvest_state_run_id"),
    )

    id: Mapped[int] = mapped_column(_BIGINT_VARIANT, primary_key=True, autoincrement=True)
    harvest_state_run_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey(
            "harvest_state_run.id",
            name="fk_harvest_state_daily_pool_run_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    state_date: Mapped[date] = mapped_column(Date, nullable=False)
    forecast_quantile: Mapped[str] = mapped_column(Text, nullable=False)
    capacity_pool_id: Mapped[str] = mapped_column(Text, nullable=False)
    capacity_pool_grain: Mapped[str] = mapped_column(Text, nullable=False)
    capacity_pool_membership_hash: Mapped[str] = mapped_column(Text, nullable=False)
    capacity_input_mode: Mapped[str] = mapped_column(Text, nullable=False)
    opening_mature_inventory_kg: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    natural_maturity_supply_kg: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    available_mature_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    mature_inventory_loss_quantity_kg: Mapped[Decimal] = mapped_column(
        Numeric(18, 3),
        nullable=False,
    )
    harvestable_mature_quantity_kg: Mapped[Decimal] = mapped_column(
        Numeric(18, 3),
        nullable=False,
    )
    nominal_harvest_capacity_kg_per_day: Mapped[Decimal] = mapped_column(
        Numeric(18, 3),
        nullable=False,
    )
    labor_availability_ratio: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    weather_harvest_efficiency_ratio: Mapped[Decimal] = mapped_column(
        Numeric(12, 6),
        nullable=False,
    )
    operational_efficiency_ratio: Mapped[Decimal] = mapped_column(
        Numeric(12, 6),
        nullable=False,
    )
    effective_harvest_capacity_kg_per_day: Mapped[Decimal] = mapped_column(
        Numeric(18, 3),
        nullable=False,
    )
    effective_capacity_for_day_kg: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    harvested_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    closing_mature_inventory_kg: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unharvested_backlog_kg: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    arrival_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    opening_cohort_count: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    closing_cohort_count: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    member_count: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    mass_balance_passed: Mapped[bool] = mapped_column(nullable=False)
    capacity_constraint_passed: Mapped[bool] = mapped_column(nullable=False)
    continuity_passed: Mapped[bool] = mapped_column(nullable=False)
    parameter_source_ref_hashes: Mapped[list[str]] = mapped_column(_JSON_VARIANT, nullable=False)
    cohort_source_ref_hashes: Mapped[list[str]] = mapped_column(_JSON_VARIANT, nullable=False)


class HarvestStateDailyMemberRowModel(Base):
    __tablename__ = "harvest_state_daily_member_row"
    __table_args__ = (
        CheckConstraint(
            "forecast_quantile in ('P50', 'P80', 'P90')",
            name="ck_harvest_state_daily_member_quantile",
        ),
        CheckConstraint(
            "capacity_pool_grain in ('SUBFARM_VARIETY', 'SUBFARM', 'FARM')",
            name="ck_harvest_state_daily_member_grain",
        ),
        CheckConstraint(
            _sha256_check_sql("capacity_pool_membership_hash"),
            name="ck_harvest_state_daily_member_membership_hash",
        ),
        CheckConstraint(
            "subfarm_identity_key <> ''",
            name="ck_harvest_state_daily_member_subfarm_identity_key",
        ),
        *_non_negative_check_sql(
            "harvest_state_daily_member",
            "opening_mature_inventory_kg",
            "natural_maturity_supply_kg",
            "available_mature_quantity_kg",
            "mature_inventory_loss_quantity_kg",
            "harvestable_mature_quantity_kg",
            "allocated_harvest_capacity_kg",
            "harvested_quantity_kg",
            "closing_mature_inventory_kg",
            "unharvested_backlog_kg",
            "arrival_quantity_kg",
            "opening_cohort_count",
            "closing_cohort_count",
        ),
        UniqueConstraint(
            "harvest_state_run_id",
            "state_date",
            "capacity_pool_id",
            "farm_id",
            "subfarm_identity_key",
            "variety_id",
            "forecast_quantile",
            name="uq_harvest_state_daily_member_business_key",
        ),
        Index("ix_harvest_state_daily_member_run_id", "harvest_state_run_id"),
    )

    id: Mapped[int] = mapped_column(_BIGINT_VARIANT, primary_key=True, autoincrement=True)
    harvest_state_run_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey(
            "harvest_state_run.id",
            name="fk_harvest_state_daily_member_run_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    state_date: Mapped[date] = mapped_column(Date, nullable=False)
    forecast_quantile: Mapped[str] = mapped_column(Text, nullable=False)
    capacity_pool_id: Mapped[str] = mapped_column(Text, nullable=False)
    capacity_pool_grain: Mapped[str] = mapped_column(Text, nullable=False)
    capacity_pool_membership_hash: Mapped[str] = mapped_column(Text, nullable=False)
    farm_id: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    subfarm_id: Mapped[int | None] = mapped_column(_BIGINT_VARIANT, nullable=True)
    subfarm_identity_key: Mapped[str] = mapped_column(Text, nullable=False)
    variety_id: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    destination_factory_id: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    opening_mature_inventory_kg: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    natural_maturity_supply_kg: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    available_mature_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    mature_inventory_loss_quantity_kg: Mapped[Decimal] = mapped_column(
        Numeric(18, 3),
        nullable=False,
    )
    harvestable_mature_quantity_kg: Mapped[Decimal] = mapped_column(
        Numeric(18, 3),
        nullable=False,
    )
    allocated_harvest_capacity_kg: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    harvested_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    closing_mature_inventory_kg: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unharvested_backlog_kg: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    arrival_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    opening_cohort_count: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    closing_cohort_count: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    cohort_source_ref_hashes: Mapped[list[str]] = mapped_column(_JSON_VARIANT, nullable=False)


class HarvestStateCohortTransitionRowModel(Base):
    __tablename__ = "harvest_state_cohort_transition_row"
    __table_args__ = (
        CheckConstraint(
            "forecast_quantile in ('P50', 'P80', 'P90')",
            name="ck_harvest_state_cohort_transition_quantile",
        ),
        CheckConstraint(
            _sha256_check_sql("stable_cohort_key"),
            name="ck_harvest_state_cohort_transition_stable_key",
        ),
        CheckConstraint(
            _sha256_check_sql("source_ref_hash"),
            name="ck_harvest_state_cohort_transition_source_ref_hash",
        ),
        CheckConstraint(
            _sha256_check_sql("capacity_pool_membership_hash"),
            name="ck_harvest_state_cohort_transition_membership_hash",
        ),
        *_non_negative_check_sql(
            "harvest_state_cohort_transition",
            "opening_quantity_kg",
            "new_supply_quantity_kg",
            "quantity_before_loss_kg",
            "mature_inventory_loss_quantity_kg",
            "quantity_before_harvest_kg",
            "harvested_quantity_kg",
            "closing_quantity_kg",
            "arrival_quantity_kg",
        ),
        UniqueConstraint(
            "harvest_state_run_id",
            "state_date",
            "capacity_pool_id",
            "forecast_quantile",
            "stable_cohort_key",
            name="uq_harvest_state_cohort_transition_business_key",
        ),
        Index("ix_harvest_state_cohort_transition_run_id", "harvest_state_run_id"),
    )

    id: Mapped[int] = mapped_column(_BIGINT_VARIANT, primary_key=True, autoincrement=True)
    harvest_state_run_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey(
            "harvest_state_run.id",
            name="fk_harvest_state_cohort_transition_run_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    state_date: Mapped[date] = mapped_column(Date, nullable=False)
    forecast_quantile: Mapped[str] = mapped_column(Text, nullable=False)
    capacity_pool_id: Mapped[str] = mapped_column(Text, nullable=False)
    farm_id: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    subfarm_id: Mapped[int | None] = mapped_column(_BIGINT_VARIANT, nullable=True)
    variety_id: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    destination_factory_id: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    capacity_pool_membership_hash: Mapped[str] = mapped_column(Text, nullable=False)
    stable_cohort_key: Mapped[str] = mapped_column(Text, nullable=False)
    stable_cohort_key_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    source_ref_hash: Mapped[str] = mapped_column(Text, nullable=False)
    source_ref: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)
    cohort_date: Mapped[date] = mapped_column(Date, nullable=False)
    opening_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    new_supply_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    quantity_before_loss_kg: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    mature_inventory_loss_quantity_kg: Mapped[Decimal] = mapped_column(
        Numeric(18, 3),
        nullable=False,
    )
    quantity_before_harvest_kg: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    harvested_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    closing_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    harvest_anchor_at: Mapped[datetime | None] = mapped_column(
        _AWARE_DATETIME_VARIANT,
        nullable=True,
    )
    arrival_at: Mapped[datetime | None] = mapped_column(
        _AWARE_DATETIME_VARIANT,
        nullable=True,
    )
    arrival_local_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    arrival_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)


class HarvestStateFutureArrivalRowModel(Base):
    __tablename__ = "harvest_state_future_arrival_row"
    __table_args__ = (
        CheckConstraint(
            "forecast_quantile in ('P50', 'P80', 'P90')",
            name="ck_harvest_state_future_arrival_quantile",
        ),
        CheckConstraint(
            "subfarm_identity_key <> ''",
            name="ck_harvest_state_future_arrival_subfarm_identity_key",
        ),
        CheckConstraint(
            "harvest_to_arrival_lag_days >= 0",
            name="ck_harvest_state_future_arrival_lag_non_negative",
        ),
        CheckConstraint(
            "quantity_kg >= 0",
            name="ck_harvest_state_future_arrival_quantity_non_negative",
        ),
        UniqueConstraint(
            "harvest_state_run_id",
            "arrival_local_date",
            "capacity_pool_id",
            "farm_id",
            "subfarm_identity_key",
            "variety_id",
            "forecast_quantile",
            name="uq_harvest_state_future_arrival_business_key",
        ),
        Index("ix_harvest_state_future_arrival_run_id", "harvest_state_run_id"),
    )

    id: Mapped[int] = mapped_column(_BIGINT_VARIANT, primary_key=True, autoincrement=True)
    harvest_state_run_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey(
            "harvest_state_run.id",
            name="fk_harvest_state_future_arrival_run_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    capacity_pool_id: Mapped[str] = mapped_column(Text, nullable=False)
    farm_id: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    subfarm_id: Mapped[int | None] = mapped_column(_BIGINT_VARIANT, nullable=True)
    subfarm_identity_key: Mapped[str] = mapped_column(Text, nullable=False)
    destination_factory_id: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    arrival_local_date: Mapped[date] = mapped_column(Date, nullable=False)
    variety_id: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    forecast_quantile: Mapped[str] = mapped_column(Text, nullable=False)
    quantity_kg: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    harvest_to_arrival_lag_days: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    farm_timezone: Mapped[str] = mapped_column(Text, nullable=False)
    destination_factory_timezone: Mapped[str] = mapped_column(Text, nullable=False)
