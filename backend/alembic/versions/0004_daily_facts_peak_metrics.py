"""Create task 3 daily facts and peak metric tables.

Revision ID: 0004_daily_facts_peak_metrics
Revises: 0003_historical_ingest
Create Date: 2026-06-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_daily_facts_peak_metrics"
down_revision: str | None = "0003_historical_ingest"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analytics_build_run",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("season_id", sa.BigInteger(), nullable=False),
        sa.Column("aggregation_version", sa.Text(), nullable=False),
        sa.Column("source_max_raw_id", sa.BigInteger(), nullable=False),
        sa.Column("config_hash", sa.Text(), nullable=False),
        sa.Column("config_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("source_eligible_row_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "source_eligible_weight_kg",
            sa.Numeric(18, 6),
            server_default="0",
            nullable=False,
        ),
        sa.Column("daily_fact_row_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status in ('running', 'completed', 'failed')",
            name="ck_analytics_build_run_status",
        ),
        sa.ForeignKeyConstraint(
            ["season_id"],
            ["dim_season.id"],
            name="fk_analytics_build_run_season_id_dim_season",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_analytics_build_run"),
    )
    op.create_index(
        "ix_analytics_build_run_season_id",
        "analytics_build_run",
        ["season_id"],
    )
    op.create_index(
        "ix_analytics_build_run_status",
        "analytics_build_run",
        ["status"],
    )
    op.create_index(
        "ix_analytics_build_run_source_max_raw_id",
        "analytics_build_run",
        ["source_max_raw_id"],
    )
    op.create_index(
        "ux_analytics_build_run_active_or_completed",
        "analytics_build_run",
        ["season_id", "aggregation_version", "source_max_raw_id", "config_hash"],
        unique=True,
        postgresql_where=sa.text("status in ('running', 'completed')"),
    )

    op.create_table(
        "fact_receipt_daily",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("build_run_id", sa.BigInteger(), nullable=False),
        sa.Column("season_id", sa.BigInteger(), nullable=False),
        sa.Column("receipt_date", sa.Date(), nullable=False),
        sa.Column("factory_id", sa.BigInteger(), nullable=False),
        sa.Column("farm_key", sa.Text(), nullable=False),
        sa.Column("subfarm_key", sa.Text(), nullable=False),
        sa.Column("variety_id", sa.BigInteger(), nullable=False),
        sa.Column("weight_kg", sa.Numeric(18, 6), nullable=False),
        sa.Column("source_row_count", sa.Integer(), nullable=False),
        sa.Column(
            "holiday_codes",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("is_spring_festival", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("weight_kg > 0", name="ck_fact_receipt_daily_weight_positive"),
        sa.CheckConstraint(
            "source_row_count > 0",
            name="ck_fact_receipt_daily_source_row_count_positive",
        ),
        sa.ForeignKeyConstraint(
            ["build_run_id"],
            ["analytics_build_run.id"],
            name="fk_fact_receipt_daily_build_run_id_analytics_build_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["season_id"],
            ["dim_season.id"],
            name="fk_fact_receipt_daily_season_id_dim_season",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["factory_id"],
            ["dim_factory.id"],
            name="fk_fact_receipt_daily_factory_id_dim_factory",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["variety_id"],
            ["dim_variety.id"],
            name="fk_fact_receipt_daily_variety_id_dim_variety",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_fact_receipt_daily"),
        sa.UniqueConstraint(
            "build_run_id",
            "season_id",
            "receipt_date",
            "factory_id",
            "farm_key",
            "subfarm_key",
            "variety_id",
            name="uq_fact_receipt_daily_build_grain",
        ),
    )
    op.create_index("ix_fact_receipt_daily_build_run_id", "fact_receipt_daily", ["build_run_id"])
    op.create_index("ix_fact_receipt_daily_season_id", "fact_receipt_daily", ["season_id"])
    op.create_index("ix_fact_receipt_daily_factory_id", "fact_receipt_daily", ["factory_id"])
    op.create_index("ix_fact_receipt_daily_receipt_date", "fact_receipt_daily", ["receipt_date"])
    op.create_index(
        "ix_fact_receipt_daily_season_factory_date",
        "fact_receipt_daily",
        ["season_id", "factory_id", "receipt_date"],
    )

    op.create_table(
        "factory_season_peak_metric",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("build_run_id", sa.BigInteger(), nullable=False),
        sa.Column("season_id", sa.BigInteger(), nullable=False),
        sa.Column("factory_id", sa.BigInteger(), nullable=False),
        sa.Column("analysis_start_date", sa.Date(), nullable=False),
        sa.Column("analysis_end_date", sa.Date(), nullable=False),
        sa.Column("calendar_day_count", sa.Integer(), nullable=False),
        sa.Column("observed_day_count", sa.Integer(), nullable=False),
        sa.Column("total_weight_kg", sa.Numeric(18, 6), nullable=False),
        sa.Column("single_day_peak_kg", sa.Numeric(18, 6), nullable=False),
        sa.Column("single_day_peak_date", sa.Date(), nullable=False),
        sa.Column("stable_median_3d_peak_kg", sa.Numeric(18, 6), nullable=False),
        sa.Column("stable_median_3d_peak_date", sa.Date(), nullable=True),
        sa.Column("mean_3d_peak_kg", sa.Numeric(18, 6), nullable=False),
        sa.Column("mean_3d_peak_date", sa.Date(), nullable=True),
        sa.Column("peak_concentration", sa.Numeric(12, 10), nullable=False),
        sa.Column("variety_hhi", sa.Numeric(12, 10), nullable=False),
        sa.Column("farm_hhi", sa.Numeric(12, 10), nullable=False),
        sa.Column("subfarm_hhi", sa.Numeric(12, 10), nullable=False),
        sa.Column("unknown_farm_weight_share", sa.Numeric(12, 10), nullable=False),
        sa.Column("unknown_subfarm_weight_share", sa.Numeric(12, 10), nullable=False),
        sa.Column("spring_festival_day_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "computed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "total_weight_kg > 0",
            name="ck_factory_peak_total_weight_positive",
        ),
        sa.CheckConstraint(
            "calendar_day_count >= observed_day_count and observed_day_count >= 0",
            name="ck_factory_peak_observed_day_count",
        ),
        sa.CheckConstraint(
            "peak_concentration >= 0 and peak_concentration <= 1",
            name="ck_factory_peak_peak_concentration_range",
        ),
        sa.CheckConstraint(
            "variety_hhi >= 0 and variety_hhi <= 1",
            name="ck_factory_peak_variety_hhi_range",
        ),
        sa.CheckConstraint(
            "farm_hhi >= 0 and farm_hhi <= 1",
            name="ck_factory_peak_farm_hhi_range",
        ),
        sa.CheckConstraint(
            "subfarm_hhi >= 0 and subfarm_hhi <= 1",
            name="ck_factory_peak_subfarm_hhi_range",
        ),
        sa.CheckConstraint(
            "unknown_farm_weight_share >= 0 and unknown_farm_weight_share <= 1",
            name="ck_factory_peak_unknown_farm_share_range",
        ),
        sa.CheckConstraint(
            "unknown_subfarm_weight_share >= 0 and unknown_subfarm_weight_share <= 1",
            name="ck_factory_peak_unknown_subfarm_share_range",
        ),
        sa.ForeignKeyConstraint(
            ["build_run_id"],
            ["analytics_build_run.id"],
            name="fk_factory_season_peak_metric_build_run_id_analytics_build_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["season_id"],
            ["dim_season.id"],
            name="fk_factory_season_peak_metric_season_id_dim_season",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["factory_id"],
            ["dim_factory.id"],
            name="fk_factory_season_peak_metric_factory_id_dim_factory",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_factory_season_peak_metric"),
        sa.UniqueConstraint(
            "build_run_id",
            "factory_id",
            name="uq_factory_season_peak_metric_build_run_id_factory_id",
        ),
    )
    op.create_index(
        "ix_factory_season_peak_metric_build_run_id",
        "factory_season_peak_metric",
        ["build_run_id"],
    )
    op.create_index(
        "ix_factory_season_peak_metric_season_id",
        "factory_season_peak_metric",
        ["season_id"],
    )
    op.create_index(
        "ix_factory_season_peak_metric_factory_id",
        "factory_season_peak_metric",
        ["factory_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_factory_season_peak_metric_factory_id",
        table_name="factory_season_peak_metric",
    )
    op.drop_index(
        "ix_factory_season_peak_metric_season_id",
        table_name="factory_season_peak_metric",
    )
    op.drop_index(
        "ix_factory_season_peak_metric_build_run_id",
        table_name="factory_season_peak_metric",
    )
    op.drop_table("factory_season_peak_metric")

    op.drop_index("ix_fact_receipt_daily_season_factory_date", table_name="fact_receipt_daily")
    op.drop_index("ix_fact_receipt_daily_receipt_date", table_name="fact_receipt_daily")
    op.drop_index("ix_fact_receipt_daily_factory_id", table_name="fact_receipt_daily")
    op.drop_index("ix_fact_receipt_daily_season_id", table_name="fact_receipt_daily")
    op.drop_index("ix_fact_receipt_daily_build_run_id", table_name="fact_receipt_daily")
    op.drop_table("fact_receipt_daily")

    op.drop_index(
        "ux_analytics_build_run_active_or_completed",
        table_name="analytics_build_run",
    )
    op.drop_index("ix_analytics_build_run_source_max_raw_id", table_name="analytics_build_run")
    op.drop_index("ix_analytics_build_run_status", table_name="analytics_build_run")
    op.drop_index("ix_analytics_build_run_season_id", table_name="analytics_build_run")
    op.drop_table("analytics_build_run")
