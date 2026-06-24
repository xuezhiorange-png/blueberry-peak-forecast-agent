"""Create task 8 natural maturity curve tables.

Revision ID: 0009_natural_maturity_curve
Revises: 0008_weather_timeline
Create Date: 2026-06-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_natural_maturity_curve"
down_revision: str | None = "0008_weather_timeline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "maturity_model_run",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("model_version", sa.Text(), nullable=False),
        sa.Column("config_hash", sa.Text(), nullable=False),
        sa.Column(
            "config_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("training_cutoff", sa.Date(), nullable=False),
        sa.Column("source_signature", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("random_seed", sa.BigInteger(), nullable=False),
        sa.Column("model_family", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("sample_count", sa.BigInteger(), nullable=False),
        sa.Column("distinct_season_count", sa.BigInteger(), nullable=False),
        sa.Column("distinct_farm_count", sa.BigInteger(), nullable=False),
        sa.Column("distinct_subfarm_count", sa.BigInteger(), nullable=False),
        sa.Column(
            "training_metrics",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "calibration_metrics",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("blockers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "input_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status in ('running', 'completed', 'failed', 'unavailable')",
            name="ck_maturity_model_run_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_signature",
            "status",
            name="uq_maturity_model_run_sig_status",
        ),
    )
    op.create_index(
        "ux_maturity_model_run_active_or_done",
        "maturity_model_run",
        ["source_signature"],
        unique=True,
        postgresql_where=sa.text("status in ('running', 'completed', 'unavailable')"),
    )

    op.create_table(
        "maturity_model_artifact",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("artifact_hash", sa.Text(), nullable=False),
        sa.Column("support_min_day", sa.BigInteger(), nullable=False),
        sa.Column("support_max_day", sa.BigInteger(), nullable=False),
        sa.Column(
            "artifact_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["maturity_model_run.id"],
            name="fk_maturity_artifact_run_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", name="uq_maturity_model_artifact_run_id"),
        sa.UniqueConstraint("artifact_hash", name="uq_maturity_model_artifact_hash"),
    )

    op.create_table(
        "maturity_forecast_run",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("model_run_id", sa.BigInteger(), nullable=False),
        sa.Column("artifact_id", sa.BigInteger(), nullable=False),
        sa.Column("plan_id", sa.BigInteger(), nullable=False),
        sa.Column("location_reference_id", sa.BigInteger(), nullable=False),
        sa.Column("weather_mapping_id", sa.BigInteger(), nullable=True),
        sa.Column("base_temperature_search_run_id", sa.BigInteger(), nullable=True),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("prediction_start_date", sa.Date(), nullable=False),
        sa.Column("prediction_end_date", sa.Date(), nullable=False),
        sa.Column(
            "expected_marketable_total_kg",
            sa.Numeric(18, 6),
            nullable=False,
        ),
        sa.Column("expected_total_source", sa.Text(), nullable=False),
        sa.Column("axis_mode", sa.Text(), nullable=False),
        sa.Column("source_signature", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("blockers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "input_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status in ('running', 'completed', 'failed', 'unavailable')",
            name="ck_maturity_forecast_run_status",
        ),
        sa.CheckConstraint(
            "axis_mode in ('observed_phenology_axis', 'calendar_proxy_axis')",
            name="ck_maturity_forecast_run_axis_mode",
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id"],
            ["maturity_model_artifact.id"],
            name="fk_maturity_forecast_run_artifact_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["base_temperature_search_run_id"],
            ["base_temperature_search_run.id"],
            name="fk_maturity_forecast_run_base_temp_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["location_reference_id"],
            ["location_reference.id"],
            name="fk_maturity_forecast_run_loc_ref_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["model_run_id"],
            ["maturity_model_run.id"],
            name="fk_maturity_forecast_run_model_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["farm_season_variety_plan.id"],
            name="fk_maturity_forecast_run_plan_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["weather_mapping_id"],
            ["location_weather_mapping.id"],
            name="fk_maturity_forecast_run_mapping_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_signature",
            "status",
            name="uq_maturity_forecast_run_sig_status",
        ),
    )
    op.create_index(
        "ux_maturity_forecast_run_active_or_done",
        "maturity_forecast_run",
        ["source_signature"],
        unique=True,
        postgresql_where=sa.text("status in ('running', 'completed', 'unavailable')"),
    )

    op.create_table(
        "maturity_daily_prediction",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("forecast_run_id", sa.BigInteger(), nullable=False),
        sa.Column("prediction_date", sa.Date(), nullable=False),
        sa.Column("phenology_coordinate_day", sa.Numeric(12, 6), nullable=False),
        sa.Column("p50_kg", sa.Numeric(18, 6), nullable=False),
        sa.Column("p80_kg", sa.Numeric(18, 6), nullable=False),
        sa.Column("p90_kg", sa.Numeric(18, 6), nullable=False),
        sa.Column("cumulative_p50_kg", sa.Numeric(18, 6), nullable=False),
        sa.Column("cumulative_p80_kg", sa.Numeric(18, 6), nullable=False),
        sa.Column("cumulative_p90_kg", sa.Numeric(18, 6), nullable=False),
        sa.Column("curve_share", sa.Numeric(12, 10), nullable=False),
        sa.Column("confidence_level", sa.Text(), nullable=False),
        sa.Column(
            "quality_flags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["forecast_run_id"],
            ["maturity_forecast_run.id"],
            name="fk_maturity_daily_prediction_run_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "forecast_run_id",
            "prediction_date",
            name="uq_maturity_daily_run_date",
        ),
    )
    op.create_index(
        "ix_maturity_daily_prediction_run_id",
        "maturity_daily_prediction",
        ["forecast_run_id"],
    )
    op.create_index(
        "ix_maturity_daily_prediction_date",
        "maturity_daily_prediction",
        ["prediction_date"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_maturity_daily_prediction_date",
        table_name="maturity_daily_prediction",
    )
    op.drop_index(
        "ix_maturity_daily_prediction_run_id",
        table_name="maturity_daily_prediction",
    )
    op.drop_table("maturity_daily_prediction")

    op.drop_index(
        "ux_maturity_forecast_run_active_or_done",
        table_name="maturity_forecast_run",
    )
    op.drop_table("maturity_forecast_run")

    op.drop_table("maturity_model_artifact")

    op.drop_index(
        "ux_maturity_model_run_active_or_done",
        table_name="maturity_model_run",
    )
    op.drop_table("maturity_model_run")
