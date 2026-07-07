"""Persist Task 9A harvest-state runs and audit artifacts.

Revision ID: 0010_harvest_state_persistence
Revises: 0009_natural_maturity_curve
Create Date: 2026-06-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_harvest_state_persistence"
down_revision: str | None = "0009_natural_maturity_curve"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _sha256_check_sql(column_name: str) -> str:
    stripped = column_name
    for char in "0123456789abcdef":
        stripped = f"replace({stripped}, '{char}', '')"
    return (
        f"length({column_name}) = 64 and lower({column_name}) = {column_name} and {stripped} = ''"
    )


_NON_NEGATIVE_CHECK_SUFFIXES = {
    "pool_row_count": "prc",
    "member_row_count": "mrc",
    "cohort_row_count": "crc",
    "future_arrival_row_count": "farc",
    "opening_mature_inventory_kg": "open_inv",
    "natural_maturity_supply_kg": "supply",
    "available_mature_quantity_kg": "avail",
    "mature_inventory_loss_quantity_kg": "loss",
    "harvestable_mature_quantity_kg": "harvestable",
    "nominal_harvest_capacity_kg_per_day": "nom_cap",
    "effective_harvest_capacity_kg_per_day": "eff_cap",
    "effective_capacity_for_day_kg": "day_cap",
    "harvested_quantity_kg": "harvested",
    "closing_mature_inventory_kg": "close_inv",
    "unharvested_backlog_kg": "backlog",
    "arrival_quantity_kg": "arrival",
    "opening_cohort_count": "open_coh",
    "closing_cohort_count": "close_coh",
    "member_count": "members",
    "allocated_harvest_capacity_kg": "alloc_cap",
    "opening_quantity_kg": "open_qty",
    "new_supply_quantity_kg": "new_supply",
    "quantity_before_loss_kg": "before_loss",
    "quantity_before_harvest_kg": "before_harvest",
    "closing_quantity_kg": "close_qty",
}


def _non_negative_check_sql(prefix: str, *columns: str) -> list[sa.CheckConstraint]:
    return [
        sa.CheckConstraint(
            f"{column} >= 0",
            name=f"ck_{prefix}_{_NON_NEGATIVE_CHECK_SUFFIXES[column]}_nn",
        )
        for column in columns
    ]


def upgrade() -> None:
    op.create_table(
        "harvest_state_run",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("output_schema_version", sa.Text(), nullable=False),
        sa.Column("result_hash_schema_version", sa.Text(), nullable=False),
        sa.Column(
            "resolved_parameter_snapshot_schema_version",
            sa.Text(),
            nullable=False,
        ),
        sa.Column("source_ref_schema_version", sa.Text(), nullable=False),
        sa.Column("stable_cohort_key_schema_version", sa.Text(), nullable=False),
        sa.Column(
            "input_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "resolved_parameter_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "source_ref_catalog",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("blockers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "mass_balance_result",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "continuity_result",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "canonical_output",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("config_hash", sa.Text(), nullable=False),
        sa.Column("result_hash", sa.Text(), nullable=False),
        sa.Column("canonical_payload_hash", sa.Text(), nullable=False),
        sa.Column("forecast_start_date", sa.Date(), nullable=False),
        sa.Column("forecast_end_date", sa.Date(), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("destination_factory_id", sa.BigInteger(), nullable=False),
        sa.Column("pool_row_count", sa.BigInteger(), nullable=False),
        sa.Column("member_row_count", sa.BigInteger(), nullable=False),
        sa.Column("cohort_row_count", sa.BigInteger(), nullable=False),
        sa.Column("future_arrival_row_count", sa.BigInteger(), nullable=False),
        sa.Column("maturity_model_run_id", sa.BigInteger(), nullable=True),
        sa.Column("maturity_model_version", sa.Text(), nullable=True),
        sa.Column("maturity_model_config_hash", sa.Text(), nullable=True),
        sa.Column("maturity_model_source_signature", sa.Text(), nullable=True),
        sa.Column("maturity_model_artifact_id", sa.BigInteger(), nullable=True),
        sa.Column("maturity_model_artifact_hash", sa.Text(), nullable=True),
        sa.Column("maturity_forecast_run_id", sa.BigInteger(), nullable=True),
        sa.Column("maturity_forecast_source_signature", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status in ('completed', 'blocked')",
            name="ck_harvest_state_run_status",
        ),
        sa.CheckConstraint(
            _sha256_check_sql("config_hash"),
            name="ck_harvest_state_run_config_hash",
        ),
        sa.CheckConstraint(
            _sha256_check_sql("result_hash"),
            name="ck_harvest_state_run_result_hash",
        ),
        sa.CheckConstraint(
            _sha256_check_sql("canonical_payload_hash"),
            name="ck_harvest_state_run_canonical_payload_hash",
        ),
        sa.CheckConstraint(
            "forecast_end_date >= forecast_start_date",
            name="ck_harvest_state_run_forecast_date_range",
        ),
        *_non_negative_check_sql(
            "hsr",
            "pool_row_count",
            "member_row_count",
            "cohort_row_count",
            "future_arrival_row_count",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("result_hash", name="uq_harvest_state_run_result_hash"),
    )
    op.create_index("ix_harvest_state_run_status", "harvest_state_run", ["status"])
    op.create_index("ix_harvest_state_run_as_of_date", "harvest_state_run", ["as_of_date"])
    op.create_index(
        "ix_harvest_state_run_maturity_forecast_run_id",
        "harvest_state_run",
        ["maturity_forecast_run_id"],
    )
    op.create_index(
        "ix_harvest_state_run_maturity_model_run_id",
        "harvest_state_run",
        ["maturity_model_run_id"],
    )

    op.create_table(
        "harvest_state_daily_pool_row",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("harvest_state_run_id", sa.BigInteger(), nullable=False),
        sa.Column("state_date", sa.Date(), nullable=False),
        sa.Column("forecast_quantile", sa.Text(), nullable=False),
        sa.Column("capacity_pool_id", sa.Text(), nullable=False),
        sa.Column("capacity_pool_grain", sa.Text(), nullable=False),
        sa.Column("capacity_pool_membership_hash", sa.Text(), nullable=False),
        sa.Column("capacity_input_mode", sa.Text(), nullable=False),
        sa.Column("opening_mature_inventory_kg", sa.Numeric(18, 3), nullable=False),
        sa.Column("natural_maturity_supply_kg", sa.Numeric(18, 3), nullable=False),
        sa.Column("available_mature_quantity_kg", sa.Numeric(18, 3), nullable=False),
        sa.Column("mature_inventory_loss_quantity_kg", sa.Numeric(18, 3), nullable=False),
        sa.Column("harvestable_mature_quantity_kg", sa.Numeric(18, 3), nullable=False),
        sa.Column("nominal_harvest_capacity_kg_per_day", sa.Numeric(18, 3), nullable=False),
        sa.Column("labor_availability_ratio", sa.Numeric(12, 6), nullable=False),
        sa.Column("weather_harvest_efficiency_ratio", sa.Numeric(12, 6), nullable=False),
        sa.Column("operational_efficiency_ratio", sa.Numeric(12, 6), nullable=False),
        sa.Column(
            "effective_harvest_capacity_kg_per_day",
            sa.Numeric(18, 3),
            nullable=False,
        ),
        sa.Column("effective_capacity_for_day_kg", sa.Numeric(18, 3), nullable=False),
        sa.Column("harvested_quantity_kg", sa.Numeric(18, 3), nullable=False),
        sa.Column("closing_mature_inventory_kg", sa.Numeric(18, 3), nullable=False),
        sa.Column("unharvested_backlog_kg", sa.Numeric(18, 3), nullable=False),
        sa.Column("arrival_quantity_kg", sa.Numeric(18, 3), nullable=False),
        sa.Column("opening_cohort_count", sa.BigInteger(), nullable=False),
        sa.Column("closing_cohort_count", sa.BigInteger(), nullable=False),
        sa.Column("member_count", sa.BigInteger(), nullable=False),
        sa.Column("mass_balance_passed", sa.Boolean(), nullable=False),
        sa.Column("capacity_constraint_passed", sa.Boolean(), nullable=False),
        sa.Column("continuity_passed", sa.Boolean(), nullable=False),
        sa.Column(
            "parameter_source_ref_hashes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "cohort_source_ref_hashes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.CheckConstraint(
            "forecast_quantile in ('P50', 'P80', 'P90')",
            name="ck_harvest_state_daily_pool_quantile",
        ),
        sa.CheckConstraint(
            "capacity_pool_grain in ('SUBFARM_VARIETY', 'SUBFARM', 'FARM')",
            name="ck_harvest_state_daily_pool_grain",
        ),
        sa.CheckConstraint(
            "capacity_input_mode in ('LABOR_DERIVED', 'DIRECT_CAPACITY')",
            name="ck_harvest_state_daily_pool_input_mode",
        ),
        sa.CheckConstraint(
            _sha256_check_sql("capacity_pool_membership_hash"),
            name="ck_harvest_state_daily_pool_membership_hash",
        ),
        sa.CheckConstraint(
            "labor_availability_ratio >= 0 and labor_availability_ratio <= 1",
            name="ck_harvest_state_daily_pool_labor_ratio",
        ),
        sa.CheckConstraint(
            "weather_harvest_efficiency_ratio >= 0 and weather_harvest_efficiency_ratio <= 1",
            name="ck_harvest_state_daily_pool_weather_ratio",
        ),
        sa.CheckConstraint(
            "operational_efficiency_ratio >= 0 and operational_efficiency_ratio <= 1",
            name="ck_harvest_state_daily_pool_operational_ratio",
        ),
        *_non_negative_check_sql(
            "hsdp",
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
        sa.ForeignKeyConstraint(
            ["harvest_state_run_id"],
            ["harvest_state_run.id"],
            name="fk_harvest_state_daily_pool_run_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "harvest_state_run_id",
            "state_date",
            "capacity_pool_id",
            "forecast_quantile",
            name="uq_harvest_state_daily_pool_business_key",
        ),
    )
    op.create_index(
        "ix_harvest_state_daily_pool_run_id",
        "harvest_state_daily_pool_row",
        ["harvest_state_run_id"],
    )

    op.create_table(
        "harvest_state_daily_member_row",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("harvest_state_run_id", sa.BigInteger(), nullable=False),
        sa.Column("state_date", sa.Date(), nullable=False),
        sa.Column("forecast_quantile", sa.Text(), nullable=False),
        sa.Column("capacity_pool_id", sa.Text(), nullable=False),
        sa.Column("capacity_pool_grain", sa.Text(), nullable=False),
        sa.Column("capacity_pool_membership_hash", sa.Text(), nullable=False),
        sa.Column("farm_id", sa.BigInteger(), nullable=False),
        sa.Column("subfarm_id", sa.BigInteger(), nullable=True),
        sa.Column("subfarm_identity_key", sa.Text(), nullable=False),
        sa.Column("variety_id", sa.BigInteger(), nullable=False),
        sa.Column("destination_factory_id", sa.BigInteger(), nullable=False),
        sa.Column("opening_mature_inventory_kg", sa.Numeric(18, 3), nullable=False),
        sa.Column("natural_maturity_supply_kg", sa.Numeric(18, 3), nullable=False),
        sa.Column("available_mature_quantity_kg", sa.Numeric(18, 3), nullable=False),
        sa.Column("mature_inventory_loss_quantity_kg", sa.Numeric(18, 3), nullable=False),
        sa.Column("harvestable_mature_quantity_kg", sa.Numeric(18, 3), nullable=False),
        sa.Column("allocated_harvest_capacity_kg", sa.Numeric(18, 3), nullable=False),
        sa.Column("harvested_quantity_kg", sa.Numeric(18, 3), nullable=False),
        sa.Column("closing_mature_inventory_kg", sa.Numeric(18, 3), nullable=False),
        sa.Column("unharvested_backlog_kg", sa.Numeric(18, 3), nullable=False),
        sa.Column("arrival_quantity_kg", sa.Numeric(18, 3), nullable=False),
        sa.Column("opening_cohort_count", sa.BigInteger(), nullable=False),
        sa.Column("closing_cohort_count", sa.BigInteger(), nullable=False),
        sa.Column(
            "cohort_source_ref_hashes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.CheckConstraint(
            "forecast_quantile in ('P50', 'P80', 'P90')",
            name="ck_harvest_state_daily_member_quantile",
        ),
        sa.CheckConstraint(
            "capacity_pool_grain in ('SUBFARM_VARIETY', 'SUBFARM', 'FARM')",
            name="ck_harvest_state_daily_member_grain",
        ),
        sa.CheckConstraint(
            _sha256_check_sql("capacity_pool_membership_hash"),
            name="ck_harvest_state_daily_member_membership_hash",
        ),
        sa.CheckConstraint(
            "subfarm_identity_key <> ''",
            name="ck_harvest_state_daily_member_subfarm_identity_key",
        ),
        *_non_negative_check_sql(
            "hsdm",
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
        sa.ForeignKeyConstraint(
            ["harvest_state_run_id"],
            ["harvest_state_run.id"],
            name="fk_harvest_state_daily_member_run_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "harvest_state_run_id",
            "state_date",
            "capacity_pool_id",
            "farm_id",
            "subfarm_identity_key",
            "variety_id",
            "forecast_quantile",
            name="uq_harvest_state_daily_member_business_key",
        ),
    )
    op.create_index(
        "ix_harvest_state_daily_member_run_id",
        "harvest_state_daily_member_row",
        ["harvest_state_run_id"],
    )

    op.create_table(
        "harvest_state_cohort_transition_row",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("harvest_state_run_id", sa.BigInteger(), nullable=False),
        sa.Column("state_date", sa.Date(), nullable=False),
        sa.Column("forecast_quantile", sa.Text(), nullable=False),
        sa.Column("capacity_pool_id", sa.Text(), nullable=False),
        sa.Column("farm_id", sa.BigInteger(), nullable=False),
        sa.Column("subfarm_id", sa.BigInteger(), nullable=True),
        sa.Column("variety_id", sa.BigInteger(), nullable=False),
        sa.Column("destination_factory_id", sa.BigInteger(), nullable=False),
        sa.Column("capacity_pool_membership_hash", sa.Text(), nullable=False),
        sa.Column("stable_cohort_key", sa.Text(), nullable=False),
        sa.Column("stable_cohort_key_schema_version", sa.Text(), nullable=False),
        sa.Column("source_ref_hash", sa.Text(), nullable=False),
        sa.Column(
            "source_ref",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("cohort_date", sa.Date(), nullable=False),
        sa.Column("opening_quantity_kg", sa.Numeric(18, 3), nullable=False),
        sa.Column("new_supply_quantity_kg", sa.Numeric(18, 3), nullable=False),
        sa.Column("quantity_before_loss_kg", sa.Numeric(18, 3), nullable=False),
        sa.Column("mature_inventory_loss_quantity_kg", sa.Numeric(18, 3), nullable=False),
        sa.Column("quantity_before_harvest_kg", sa.Numeric(18, 3), nullable=False),
        sa.Column("harvested_quantity_kg", sa.Numeric(18, 3), nullable=False),
        sa.Column("closing_quantity_kg", sa.Numeric(18, 3), nullable=False),
        sa.Column("harvest_anchor_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("arrival_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("arrival_local_date", sa.Date(), nullable=True),
        sa.Column("arrival_quantity_kg", sa.Numeric(18, 3), nullable=False),
        sa.CheckConstraint(
            "forecast_quantile in ('P50', 'P80', 'P90')",
            name="ck_harvest_state_cohort_transition_quantile",
        ),
        sa.CheckConstraint(
            _sha256_check_sql("stable_cohort_key"),
            name="ck_harvest_state_cohort_transition_stable_key",
        ),
        sa.CheckConstraint(
            _sha256_check_sql("source_ref_hash"),
            name="ck_harvest_state_cohort_transition_source_ref_hash",
        ),
        sa.CheckConstraint(
            _sha256_check_sql("capacity_pool_membership_hash"),
            name="ck_harvest_state_cohort_transition_membership_hash",
        ),
        *_non_negative_check_sql(
            "hsct",
            "opening_quantity_kg",
            "new_supply_quantity_kg",
            "quantity_before_loss_kg",
            "mature_inventory_loss_quantity_kg",
            "quantity_before_harvest_kg",
            "harvested_quantity_kg",
            "closing_quantity_kg",
            "arrival_quantity_kg",
        ),
        sa.ForeignKeyConstraint(
            ["harvest_state_run_id"],
            ["harvest_state_run.id"],
            name="fk_harvest_state_cohort_transition_run_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "harvest_state_run_id",
            "state_date",
            "capacity_pool_id",
            "forecast_quantile",
            "stable_cohort_key",
            name="uq_harvest_state_cohort_transition_business_key",
        ),
    )
    op.create_index(
        "ix_harvest_state_cohort_transition_run_id",
        "harvest_state_cohort_transition_row",
        ["harvest_state_run_id"],
    )

    op.create_table(
        "harvest_state_future_arrival_row",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("harvest_state_run_id", sa.BigInteger(), nullable=False),
        sa.Column("capacity_pool_id", sa.Text(), nullable=False),
        sa.Column("farm_id", sa.BigInteger(), nullable=False),
        sa.Column("subfarm_id", sa.BigInteger(), nullable=True),
        sa.Column("subfarm_identity_key", sa.Text(), nullable=False),
        sa.Column("destination_factory_id", sa.BigInteger(), nullable=False),
        sa.Column("arrival_local_date", sa.Date(), nullable=False),
        sa.Column("variety_id", sa.BigInteger(), nullable=False),
        sa.Column("forecast_quantile", sa.Text(), nullable=False),
        sa.Column("quantity_kg", sa.Numeric(18, 3), nullable=False),
        sa.Column("harvest_to_arrival_lag_days", sa.BigInteger(), nullable=False),
        sa.Column("farm_timezone", sa.Text(), nullable=False),
        sa.Column("destination_factory_timezone", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "forecast_quantile in ('P50', 'P80', 'P90')",
            name="ck_harvest_state_future_arrival_quantile",
        ),
        sa.CheckConstraint(
            "subfarm_identity_key <> ''",
            name="ck_harvest_state_future_arrival_subfarm_identity_key",
        ),
        sa.CheckConstraint(
            "harvest_to_arrival_lag_days >= 0",
            name="ck_harvest_state_future_arrival_lag_non_negative",
        ),
        sa.CheckConstraint(
            "quantity_kg >= 0",
            name="ck_harvest_state_future_arrival_quantity_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["harvest_state_run_id"],
            ["harvest_state_run.id"],
            name="fk_harvest_state_future_arrival_run_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "harvest_state_run_id",
            "arrival_local_date",
            "capacity_pool_id",
            "farm_id",
            "subfarm_identity_key",
            "variety_id",
            "forecast_quantile",
            name="uq_harvest_state_future_arrival_business_key",
        ),
    )
    op.create_index(
        "ix_harvest_state_future_arrival_run_id",
        "harvest_state_future_arrival_row",
        ["harvest_state_run_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_harvest_state_future_arrival_run_id",
        table_name="harvest_state_future_arrival_row",
    )
    op.drop_table("harvest_state_future_arrival_row")

    op.drop_index(
        "ix_harvest_state_cohort_transition_run_id",
        table_name="harvest_state_cohort_transition_row",
    )
    op.drop_table("harvest_state_cohort_transition_row")

    op.drop_index(
        "ix_harvest_state_daily_member_run_id",
        table_name="harvest_state_daily_member_row",
    )
    op.drop_table("harvest_state_daily_member_row")

    op.drop_index(
        "ix_harvest_state_daily_pool_run_id",
        table_name="harvest_state_daily_pool_row",
    )
    op.drop_table("harvest_state_daily_pool_row")

    op.drop_index("ix_harvest_state_run_maturity_model_run_id", table_name="harvest_state_run")
    op.drop_index(
        "ix_harvest_state_run_maturity_forecast_run_id",
        table_name="harvest_state_run",
    )
    op.drop_index("ix_harvest_state_run_as_of_date", table_name="harvest_state_run")
    op.drop_index("ix_harvest_state_run_status", table_name="harvest_state_run")
    op.drop_table("harvest_state_run")
