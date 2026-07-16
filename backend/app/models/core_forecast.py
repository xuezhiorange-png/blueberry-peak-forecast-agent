from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

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

from backend.app.db.base import Base

_BIGINT_VARIANT = BigInteger().with_variant(Integer(), "sqlite")
_JSON_VARIANT = JSON().with_variant(JSONB(), "postgresql")
_QUANTILES = "forecast_quantile in ('P50', 'P80', 'P90')"


def _hash_checks(column: str, name: str) -> tuple[CheckConstraint, CheckConstraint]:
    return (
        CheckConstraint(
            f"length({column}) = 64 AND {column} NOT GLOB '*[^0-9a-f]*'",
            name=name,
        ).ddl_if(dialect="sqlite"),
        CheckConstraint(
            f"{column} ~ '^[0-9a-f]{{64}}$'",
            name=name,
        ).ddl_if(dialect="postgresql"),
    )


class CoreForecastRunModel(Base):
    __tablename__ = "core_forecast_run"
    __table_args__ = (
        CheckConstraint("status = 'completed'", name="ck_core_forecast_run_completed_only"),
        CheckConstraint(
            "run_schema_version = 'v0.1-core-forecast-run-v1'",
            name="ck_core_forecast_run_schema_version",
        ),
        CheckConstraint(
            "request_schema_version = 'v0.1-core-forecast-request-v1'",
            name="ck_core_forecast_request_schema_version",
        ),
        CheckConstraint(
            "date_basis = 'HARVEST_BUSINESS_DATE'",
            name="ck_core_forecast_run_date_basis",
        ),
        CheckConstraint(
            "forecast_end_date >= forecast_start_date",
            name="ck_core_forecast_run_date_range",
        ),
        CheckConstraint("forecast_season_id > 0", name="ck_core_forecast_run_season_positive"),
        CheckConstraint(
            "destination_factory_id > 0",
            name="ck_core_forecast_run_factory_positive",
        ),
        CheckConstraint("task8_forecast_run_id > 0", name="ck_core_forecast_run_task8_positive"),
        CheckConstraint(
            "task9_harvest_state_run_id > 0",
            name="ck_core_forecast_run_task9_positive",
        ),
        CheckConstraint("daily_row_count > 0", name="ck_core_forecast_run_daily_count_positive"),
        CheckConstraint("metric_row_count = 3", name="ck_core_forecast_run_metric_count_three"),
        *_hash_checks("forecast_input_hash", "ck_core_forecast_run_forecast_input_hash"),
        *_hash_checks("request_hash", "ck_core_forecast_run_request_hash"),
        *_hash_checks("result_hash", "ck_core_forecast_run_result_hash"),
        *_hash_checks(
            "retention_policy_snapshot_hash",
            "ck_core_forecast_run_policy_snapshot_hash",
        ),
        *_hash_checks("curve_hash", "ck_core_forecast_run_curve_hash"),
        *_hash_checks("metrics_hash", "ck_core_forecast_run_metrics_hash"),
        *_hash_checks("task8_artifact_hash", "ck_core_forecast_run_task8_artifact_hash"),
        *_hash_checks("task9_result_hash", "ck_core_forecast_run_task9_result_hash"),
        UniqueConstraint("request_hash", name="uq_core_forecast_run_request_hash"),
        UniqueConstraint("result_hash", name="uq_core_forecast_run_result_hash"),
    )

    id: Mapped[int] = mapped_column(_BIGINT_VARIANT, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    run_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    request_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    date_basis: Mapped[str] = mapped_column(Text, nullable=False)

    forecast_input_hash: Mapped[str] = mapped_column(Text, nullable=False)
    request_hash: Mapped[str] = mapped_column(Text, nullable=False)
    result_hash: Mapped[str] = mapped_column(Text, nullable=False)
    retention_policy_snapshot_hash: Mapped[str] = mapped_column(Text, nullable=False)
    curve_hash: Mapped[str] = mapped_column(Text, nullable=False)
    metrics_hash: Mapped[str] = mapped_column(Text, nullable=False)

    request_snapshot: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)

    forecast_season_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey("dim_season.id", name="fk_core_forecast_run_season", ondelete="RESTRICT"),
        nullable=False,
    )
    forecast_season_code: Mapped[str] = mapped_column(Text, nullable=False)
    forecast_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    forecast_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    destination_factory_id: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)

    task8_forecast_run_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey(
            "maturity_forecast_run.id",
            name="fk_core_forecast_run_task8",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    task8_artifact_hash: Mapped[str] = mapped_column(Text, nullable=False)
    task9_harvest_state_run_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey(
            "harvest_state_run.id",
            name="fk_core_forecast_run_task9",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    task9_result_hash: Mapped[str] = mapped_column(Text, nullable=False)
    rerun_of_run_id: Mapped[int | None] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey(
            "core_forecast_run.id",
            name="fk_core_forecast_run_rerun_parent",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )

    daily_row_count: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    metric_row_count: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CoreForecastDailyRowModel(Base):
    __tablename__ = "core_forecast_daily_row"
    __table_args__ = (
        CheckConstraint(_QUANTILES, name="ck_core_forecast_daily_row_quantile"),
        CheckConstraint(
            "natural_maturity_supply_kg >= 0 AND opening_mature_inventory_kg >= 0 "
            "AND available_mature_quantity_kg >= 0 "
            "AND mature_inventory_loss_quantity_kg >= 0 "
            "AND harvestable_mature_quantity_kg >= 0 "
            "AND effective_harvest_capacity_kg >= 0 "
            "AND model_harvested_marketable_quantity_kg >= 0 "
            "AND closing_mature_inventory_kg >= 0 "
            "AND unharvested_backlog_kg >= 0 "
            "AND effective_marketable_quantity_kg >= 0",
            name="ck_core_forecast_daily_row_quantities_nonnegative",
        ),
        CheckConstraint(
            "sorting_retention_rate >= 0 AND sorting_retention_rate <= 1 "
            "AND postharvest_retention_rate >= 0 AND postharvest_retention_rate <= 1",
            name="ck_core_forecast_daily_row_retention_range",
        ),
        *_hash_checks("task8_artifact_hash", "ck_core_forecast_daily_row_task8_hash"),
        *_hash_checks("task9_result_hash", "ck_core_forecast_daily_row_task9_hash"),
        *_hash_checks("marketable_policy_hash", "ck_core_forecast_daily_row_policy_hash"),
        *_hash_checks("row_hash", "ck_core_forecast_daily_row_hash"),
        UniqueConstraint(
            "core_forecast_run_id",
            "date",
            "farm_id",
            "subfarm_id",
            "variety_id",
            "forecast_quantile",
            name="uq_core_forecast_daily_row_business_key",
        ),
        Index("ix_core_forecast_daily_row_run_date", "core_forecast_run_id", "date"),
        Index(
            "ix_core_forecast_daily_row_run_quantile_date",
            "core_forecast_run_id",
            "forecast_quantile",
            "date",
        ),
    )

    id: Mapped[int] = mapped_column(_BIGINT_VARIANT, primary_key=True, autoincrement=True)
    core_forecast_run_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey(
            "core_forecast_run.id",
            name="fk_core_forecast_daily_row_run",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    forecast_quantile: Mapped[str] = mapped_column(Text, nullable=False)
    farm_id: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    subfarm_id: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    variety_id: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    destination_factory_id: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)

    natural_maturity_supply_kg: Mapped[Decimal] = mapped_column(Numeric(24, 6), nullable=False)
    opening_mature_inventory_kg: Mapped[Decimal] = mapped_column(Numeric(24, 6), nullable=False)
    available_mature_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(24, 6), nullable=False)
    mature_inventory_loss_quantity_kg: Mapped[Decimal] = mapped_column(
        Numeric(24, 6), nullable=False
    )
    harvestable_mature_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(24, 6), nullable=False)
    effective_harvest_capacity_kg: Mapped[Decimal] = mapped_column(Numeric(24, 6), nullable=False)
    model_harvested_marketable_quantity_kg: Mapped[Decimal] = mapped_column(
        Numeric(24, 6), nullable=False
    )
    closing_mature_inventory_kg: Mapped[Decimal] = mapped_column(Numeric(24, 6), nullable=False)
    unharvested_backlog_kg: Mapped[Decimal] = mapped_column(Numeric(24, 6), nullable=False)
    sorting_retention_rate: Mapped[Decimal] = mapped_column(Numeric(24, 6), nullable=False)
    postharvest_retention_rate: Mapped[Decimal] = mapped_column(Numeric(24, 6), nullable=False)
    effective_marketable_quantity_kg: Mapped[Decimal] = mapped_column(
        Numeric(24, 6), nullable=False
    )

    task8_forecast_run_id: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    task9_harvest_state_run_id: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    task8_artifact_hash: Mapped[str] = mapped_column(Text, nullable=False)
    task9_result_hash: Mapped[str] = mapped_column(Text, nullable=False)
    marketable_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    marketable_policy_hash: Mapped[str] = mapped_column(Text, nullable=False)
    row_hash: Mapped[str] = mapped_column(Text, nullable=False)


class CoreForecastMetricModel(Base):
    __tablename__ = "core_forecast_metric"
    __table_args__ = (
        CheckConstraint(_QUANTILES, name="ck_core_forecast_metric_quantile"),
        CheckConstraint(
            "single_day_peak_quantity_kg >= 0 "
            "AND sustained_7day_cumulative_quantity_kg >= 0 "
            "AND sustained_7day_daily_average_kg_per_day >= 0 "
            "AND season_cumulative_effective_marketable_kg >= 0",
            name="ck_core_forecast_metric_quantities_nonnegative",
        ),
        CheckConstraint(
            "single_day_tie_break = 'EARLIEST_DATE'",
            name="ck_core_forecast_metric_single_day_tie_break",
        ),
        CheckConstraint(
            "sustained_window_days = 7",
            name="ck_core_forecast_metric_window_days",
        ),
        CheckConstraint(
            "sustained_metric = 'ROLLING_CUMULATIVE'",
            name="ck_core_forecast_metric_metric",
        ),
        CheckConstraint(
            "sustained_date_continuity = 'STRICT_CALENDAR_DAYS'",
            name="ck_core_forecast_metric_date_continuity",
        ),
        CheckConstraint(
            "sustained_tie_break = 'EARLIEST_START_DATE'",
            name="ck_core_forecast_metric_tie_break",
        ),
        UniqueConstraint(
            "core_forecast_run_id",
            "forecast_quantile",
            name="uq_core_forecast_metric_run_quantile",
        ),
        Index("ix_core_forecast_metric_run_id", "core_forecast_run_id"),
    )

    id: Mapped[int] = mapped_column(_BIGINT_VARIANT, primary_key=True, autoincrement=True)
    core_forecast_run_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey(
            "core_forecast_run.id",
            name="fk_core_forecast_metric_run",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    forecast_quantile: Mapped[str] = mapped_column(Text, nullable=False)
    single_day_peak_date: Mapped[date] = mapped_column(Date, nullable=False)
    single_day_peak_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(24, 6), nullable=False)
    single_day_tie_break: Mapped[str] = mapped_column(Text, nullable=False)
    sustained_7day_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    sustained_7day_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    sustained_7day_cumulative_quantity_kg: Mapped[Decimal] = mapped_column(
        Numeric(24, 6), nullable=False
    )
    sustained_7day_daily_average_kg_per_day: Mapped[Decimal] = mapped_column(
        Numeric(24, 6), nullable=False
    )
    sustained_window_days: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    sustained_metric: Mapped[str] = mapped_column(Text, nullable=False)
    sustained_date_continuity: Mapped[str] = mapped_column(Text, nullable=False)
    sustained_tie_break: Mapped[str] = mapped_column(Text, nullable=False)
    season_cumulative_effective_marketable_kg: Mapped[Decimal] = mapped_column(
        Numeric(24, 6), nullable=False
    )
