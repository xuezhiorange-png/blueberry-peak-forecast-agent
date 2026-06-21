"""Create task 4 baseline backtest tables.

Revision ID: 0005_baseline_backtest
Revises: 0004_daily_facts_peak_metrics
Create Date: 2026-06-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_baseline_backtest"
down_revision: str | None = "0004_daily_facts_peak_metrics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "baseline_backtest_run",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("model_version", sa.Text(), nullable=False),
        sa.Column("config_hash", sa.Text(), nullable=False),
        sa.Column("config_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("source_signature", sa.Text(), nullable=False),
        sa.Column("source_build_runs", postgresql.JSONB(), nullable=False),
        sa.Column("evaluation_scheme", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("random_seed", sa.BigInteger(), nullable=False),
        sa.Column("result_row_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status in ('running', 'completed', 'failed')",
            name="ck_baseline_backtest_run_status",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_baseline_backtest_run"),
    )
    op.create_index(
        "ix_baseline_backtest_run_status",
        "baseline_backtest_run",
        ["status"],
    )
    op.create_index(
        "ix_baseline_backtest_run_evaluation_scheme",
        "baseline_backtest_run",
        ["evaluation_scheme"],
    )
    op.create_index(
        "ux_baseline_backtest_run_active_or_completed",
        "baseline_backtest_run",
        ["model_version", "config_hash", "source_signature", "evaluation_scheme"],
        unique=True,
        postgresql_where=sa.text("status in ('running', 'completed')"),
    )

    op.create_table(
        "baseline_backtest_result",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("baseline_name", sa.Text(), nullable=False),
        sa.Column("target_season_id", sa.BigInteger(), nullable=False),
        sa.Column("factory_id", sa.BigInteger(), nullable=False),
        sa.Column("previous_season_id", sa.BigInteger(), nullable=True),
        sa.Column("fold_key", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("actual_stable_peak_kg", sa.Numeric(18, 6), nullable=True),
        sa.Column("predicted_stable_peak_kg", sa.Numeric(18, 6), nullable=True),
        sa.Column("absolute_error_kg", sa.Numeric(18, 6), nullable=True),
        sa.Column("signed_error_kg", sa.Numeric(18, 6), nullable=True),
        sa.Column("ape", sa.Numeric(12, 10), nullable=True),
        sa.Column("input_features", postgresql.JSONB(), nullable=False),
        sa.Column("training_season_codes", postgresql.JSONB(), nullable=False),
        sa.Column("model_metadata", postgresql.JSONB(), nullable=False),
        sa.Column("exclusion_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "baseline_name in ("
            "'previous_season_peak',"
            "'volume_previous_concentration',"
            "'ridge_structure',"
            "'ridge_structure_factory_holdout'"
            ")",
            name="ck_baseline_backtest_result_baseline_name",
        ),
        sa.CheckConstraint(
            "status in ('evaluated', 'excluded')",
            name="ck_baseline_backtest_result_status",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["baseline_backtest_run.id"],
            name="fk_baseline_backtest_result_run_id_baseline_backtest_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_season_id"],
            ["dim_season.id"],
            name="fk_baseline_backtest_result_target_season_id_dim_season",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["factory_id"],
            ["dim_factory.id"],
            name="fk_baseline_backtest_result_factory_id_dim_factory",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["previous_season_id"],
            ["dim_season.id"],
            name="fk_baseline_backtest_result_previous_season_id_dim_season",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_baseline_backtest_result"),
        sa.UniqueConstraint(
            "run_id",
            "baseline_name",
            "target_season_id",
            "factory_id",
            "fold_key",
            name="uq_baseline_backtest_result_run_model_target_factory_fold",
        ),
    )
    op.create_index(
        "ix_baseline_backtest_result_run_id",
        "baseline_backtest_result",
        ["run_id"],
    )
    op.create_index(
        "ix_baseline_backtest_result_baseline_name",
        "baseline_backtest_result",
        ["baseline_name"],
    )
    op.create_index(
        "ix_baseline_backtest_result_target_season_id",
        "baseline_backtest_result",
        ["target_season_id"],
    )
    op.create_index(
        "ix_baseline_backtest_result_factory_id",
        "baseline_backtest_result",
        ["factory_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_baseline_backtest_result_factory_id", table_name="baseline_backtest_result")
    op.drop_index(
        "ix_baseline_backtest_result_target_season_id",
        table_name="baseline_backtest_result",
    )
    op.drop_index(
        "ix_baseline_backtest_result_baseline_name",
        table_name="baseline_backtest_result",
    )
    op.drop_index("ix_baseline_backtest_result_run_id", table_name="baseline_backtest_result")
    op.drop_table("baseline_backtest_result")

    op.drop_index(
        "ux_baseline_backtest_run_active_or_completed",
        table_name="baseline_backtest_run",
    )
    op.drop_index(
        "ix_baseline_backtest_run_evaluation_scheme",
        table_name="baseline_backtest_run",
    )
    op.drop_index("ix_baseline_backtest_run_status", table_name="baseline_backtest_run")
    op.drop_table("baseline_backtest_run")
