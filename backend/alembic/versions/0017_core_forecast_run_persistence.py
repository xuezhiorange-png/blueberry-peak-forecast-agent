"""Persist completed V0.1 core forecast runs, daily rows, and metrics."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017_core_forecast_run_persistence"
down_revision: str | None = "0016_task9_forecast_season_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BIGINT = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
_NUMERIC = sa.Numeric(24, 6)


def _hash_check(column: str) -> str:
    return f"length({column}) = 64 AND {column} NOT GLOB '*[^0-9a-f]*'"


def upgrade() -> None:
    op.create_table(
        "core_forecast_run",
        sa.Column("id", _BIGINT, primary_key=True, autoincrement=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("run_schema_version", sa.Text(), nullable=False),
        sa.Column("request_schema_version", sa.Text(), nullable=False),
        sa.Column("date_basis", sa.Text(), nullable=False),
        sa.Column("forecast_input_hash", sa.Text(), nullable=False),
        sa.Column("request_hash", sa.Text(), nullable=False),
        sa.Column("result_hash", sa.Text(), nullable=False),
        sa.Column("retention_policy_snapshot_hash", sa.Text(), nullable=False),
        sa.Column("curve_hash", sa.Text(), nullable=False),
        sa.Column("metrics_hash", sa.Text(), nullable=False),
        sa.Column("request_snapshot", _JSON, nullable=False),
        sa.Column(
            "forecast_season_id",
            _BIGINT,
            sa.ForeignKey("dim_season.id", name="fk_core_forecast_run_season", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("forecast_season_code", sa.Text(), nullable=False),
        sa.Column("forecast_start_date", sa.Date(), nullable=False),
        sa.Column("forecast_end_date", sa.Date(), nullable=False),
        sa.Column("destination_factory_id", _BIGINT, nullable=False),
        sa.Column(
            "task8_forecast_run_id",
            _BIGINT,
            sa.ForeignKey(
                "maturity_forecast_run.id",
                name="fk_core_forecast_run_task8",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("task8_artifact_hash", sa.Text(), nullable=False),
        sa.Column(
            "task9_harvest_state_run_id",
            _BIGINT,
            sa.ForeignKey(
                "harvest_state_run.id",
                name="fk_core_forecast_run_task9",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("task9_result_hash", sa.Text(), nullable=False),
        sa.Column(
            "rerun_of_run_id",
            _BIGINT,
            sa.ForeignKey(
                "core_forecast_run.id",
                name="fk_core_forecast_run_rerun_parent",
                ondelete="RESTRICT",
            ),
            nullable=True,
        ),
        sa.Column("daily_row_count", _BIGINT, nullable=False),
        sa.Column("metric_row_count", _BIGINT, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status = 'completed'", name="ck_core_forecast_run_completed_only"),
        sa.CheckConstraint(
            "run_schema_version = 'v0.1-core-forecast-run-v1'",
            name="ck_core_forecast_run_schema_version",
        ),
        sa.CheckConstraint(
            "request_schema_version = 'v0.1-core-forecast-request-v1'",
            name="ck_core_forecast_request_schema_version",
        ),
        sa.CheckConstraint(
            "date_basis = 'HARVEST_BUSINESS_DATE'",
            name="ck_core_forecast_run_date_basis",
        ),
        sa.CheckConstraint(
            "forecast_end_date >= forecast_start_date",
            name="ck_core_forecast_run_date_range",
        ),
        sa.CheckConstraint("forecast_season_id > 0", name="ck_core_forecast_run_season_positive"),
        sa.CheckConstraint(
            "destination_factory_id > 0",
            name="ck_core_forecast_run_factory_positive",
        ),
        sa.CheckConstraint("task8_forecast_run_id > 0", name="ck_core_forecast_run_task8_positive"),
        sa.CheckConstraint(
            "task9_harvest_state_run_id > 0",
            name="ck_core_forecast_run_task9_positive",
        ),
        sa.CheckConstraint("daily_row_count > 0", name="ck_core_forecast_run_daily_count_positive"),
        sa.CheckConstraint("metric_row_count = 3", name="ck_core_forecast_run_metric_count_three"),
        *[
            sa.CheckConstraint(_hash_check(column), name=f"ck_core_forecast_run_{column}")
            for column in (
                "forecast_input_hash",
                "request_hash",
                "result_hash",
                "retention_policy_snapshot_hash",
                "curve_hash",
                "metrics_hash",
                "task8_artifact_hash",
                "task9_result_hash",
            )
        ],
        sa.UniqueConstraint("request_hash", name="uq_core_forecast_run_request_hash"),
        sa.UniqueConstraint("result_hash", name="uq_core_forecast_run_result_hash"),
    )

    op.create_table(
        "core_forecast_daily_row",
        sa.Column("id", _BIGINT, primary_key=True, autoincrement=True),
        sa.Column(
            "core_forecast_run_id",
            _BIGINT,
            sa.ForeignKey(
                "core_forecast_run.id",
                name="fk_core_forecast_daily_row_run",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("forecast_quantile", sa.Text(), nullable=False),
        sa.Column("farm_id", _BIGINT, nullable=False),
        sa.Column("subfarm_id", _BIGINT, nullable=False),
        sa.Column("variety_id", _BIGINT, nullable=False),
        sa.Column("destination_factory_id", _BIGINT, nullable=False),
        *[
            sa.Column(column, _NUMERIC, nullable=False)
            for column in (
                "natural_maturity_supply_kg",
                "opening_mature_inventory_kg",
                "available_mature_quantity_kg",
                "mature_inventory_loss_quantity_kg",
                "harvestable_mature_quantity_kg",
                "effective_harvest_capacity_kg",
                "model_harvested_marketable_quantity_kg",
                "closing_mature_inventory_kg",
                "unharvested_backlog_kg",
                "sorting_retention_rate",
                "postharvest_retention_rate",
                "effective_marketable_quantity_kg",
            )
        ],
        sa.Column("task8_forecast_run_id", _BIGINT, nullable=False),
        sa.Column("task9_harvest_state_run_id", _BIGINT, nullable=False),
        sa.Column("task8_artifact_hash", sa.Text(), nullable=False),
        sa.Column("task9_result_hash", sa.Text(), nullable=False),
        sa.Column("marketable_policy_version", sa.Text(), nullable=False),
        sa.Column("marketable_policy_hash", sa.Text(), nullable=False),
        sa.Column("row_hash", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "forecast_quantile in ('P50', 'P80', 'P90')",
            name="ck_core_forecast_daily_row_quantile",
        ),
        sa.CheckConstraint(
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
        sa.CheckConstraint(
            "sorting_retention_rate >= 0 AND sorting_retention_rate <= 1 "
            "AND postharvest_retention_rate >= 0 AND postharvest_retention_rate <= 1",
            name="ck_core_forecast_daily_row_retention_range",
        ),
        *[
            sa.CheckConstraint(_hash_check(column), name=f"ck_core_forecast_daily_row_{column}")
            for column in (
                "task8_artifact_hash",
                "task9_result_hash",
                "marketable_policy_hash",
                "row_hash",
            )
        ],
        sa.UniqueConstraint(
            "core_forecast_run_id",
            "date",
            "farm_id",
            "subfarm_id",
            "variety_id",
            "forecast_quantile",
            name="uq_core_forecast_daily_row_business_key",
        ),
    )
    op.create_index(
        "ix_core_forecast_daily_row_run_date",
        "core_forecast_daily_row",
        ["core_forecast_run_id", "date"],
    )
    op.create_index(
        "ix_core_forecast_daily_row_run_quantile_date",
        "core_forecast_daily_row",
        ["core_forecast_run_id", "forecast_quantile", "date"],
    )

    op.create_table(
        "core_forecast_metric",
        sa.Column("id", _BIGINT, primary_key=True, autoincrement=True),
        sa.Column(
            "core_forecast_run_id",
            _BIGINT,
            sa.ForeignKey(
                "core_forecast_run.id",
                name="fk_core_forecast_metric_run",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("forecast_quantile", sa.Text(), nullable=False),
        sa.Column("single_day_peak_date", sa.Date(), nullable=False),
        sa.Column("single_day_peak_quantity_kg", _NUMERIC, nullable=False),
        sa.Column("single_day_tie_break", sa.Text(), nullable=False),
        sa.Column("sustained_7day_start_date", sa.Date(), nullable=False),
        sa.Column("sustained_7day_end_date", sa.Date(), nullable=False),
        sa.Column("sustained_7day_cumulative_quantity_kg", _NUMERIC, nullable=False),
        sa.Column("sustained_7day_daily_average_kg_per_day", _NUMERIC, nullable=False),
        sa.Column("sustained_window_days", _BIGINT, nullable=False),
        sa.Column("sustained_metric", sa.Text(), nullable=False),
        sa.Column("sustained_date_continuity", sa.Text(), nullable=False),
        sa.Column("sustained_tie_break", sa.Text(), nullable=False),
        sa.Column("season_cumulative_effective_marketable_kg", _NUMERIC, nullable=False),
        sa.CheckConstraint(
            "forecast_quantile in ('P50', 'P80', 'P90')",
            name="ck_core_forecast_metric_quantile",
        ),
        sa.CheckConstraint(
            "single_day_peak_quantity_kg >= 0 "
            "AND sustained_7day_cumulative_quantity_kg >= 0 "
            "AND sustained_7day_daily_average_kg_per_day >= 0 "
            "AND season_cumulative_effective_marketable_kg >= 0",
            name="ck_core_forecast_metric_quantities_nonnegative",
        ),
        sa.CheckConstraint(
            "single_day_tie_break = 'EARLIEST_DATE'",
            name="ck_core_forecast_metric_single_day_tie_break",
        ),
        sa.CheckConstraint("sustained_window_days = 7", name="ck_core_forecast_metric_window_days"),
        sa.CheckConstraint(
            "sustained_metric = 'ROLLING_CUMULATIVE'",
            name="ck_core_forecast_metric_metric",
        ),
        sa.CheckConstraint(
            "sustained_date_continuity = 'STRICT_CALENDAR_DAYS'",
            name="ck_core_forecast_metric_date_continuity",
        ),
        sa.CheckConstraint(
            "sustained_tie_break = 'EARLIEST_START_DATE'",
            name="ck_core_forecast_metric_tie_break",
        ),
        sa.UniqueConstraint(
            "core_forecast_run_id",
            "forecast_quantile",
            name="uq_core_forecast_metric_run_quantile",
        ),
    )
    op.create_index(
        "ix_core_forecast_metric_run_id",
        "core_forecast_metric",
        ["core_forecast_run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_core_forecast_metric_run_id", table_name="core_forecast_metric")
    op.drop_table("core_forecast_metric")
    op.drop_index(
        "ix_core_forecast_daily_row_run_quantile_date",
        table_name="core_forecast_daily_row",
    )
    op.drop_index("ix_core_forecast_daily_row_run_date", table_name="core_forecast_daily_row")
    op.drop_table("core_forecast_daily_row")
    op.drop_table("core_forecast_run")
