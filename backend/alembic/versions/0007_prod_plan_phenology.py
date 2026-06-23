"""Create task 6 production plan and phenology tables.

Revision ID: 0007_prod_plan_phenology
Revises: 0006_minimal_input_parameters
Create Date: 2026-06-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_prod_plan_phenology"
down_revision: str | None = "0006_minimal_input_parameters"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "farm_season_variety_plan",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("farm_id", sa.BigInteger(), nullable=False),
        sa.Column("subfarm_id", sa.BigInteger(), nullable=True),
        sa.Column("season_id", sa.BigInteger(), nullable=False),
        sa.Column("variety_id", sa.BigInteger(), nullable=False),
        sa.Column("planted_area_mu", sa.Numeric(18, 6), nullable=False),
        sa.Column("expected_yield_kg_per_mu", sa.Numeric(18, 6), nullable=False),
        sa.Column("marketable_rate", sa.Numeric(12, 10), nullable=False),
        sa.Column("tree_age_years", sa.Numeric(8, 2), nullable=True),
        sa.Column("pruning_date", sa.Date(), nullable=True),
        sa.Column("flowering_start_date", sa.Date(), nullable=True),
        sa.Column("flowering_peak_date", sa.Date(), nullable=True),
        sa.Column("flowering_end_date", sa.Date(), nullable=True),
        sa.Column("first_pick_date", sa.Date(), nullable=True),
        sa.Column("expected_total_marketable_kg", sa.Numeric(18, 6), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("available_at", sa.Date(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_name", sa.Text(), nullable=True),
        sa.Column("source_version", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("row_hash", sa.Text(), nullable=False),
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
            "planted_area_mu >= 0",
            name="ck_farm_season_variety_plan_planted_area_non_negative",
        ),
        sa.CheckConstraint(
            "expected_yield_kg_per_mu >= 0",
            name="ck_farm_season_variety_plan_expected_yield_non_negative",
        ),
        sa.CheckConstraint(
            "marketable_rate >= 0 and marketable_rate <= 1",
            name="ck_farm_season_variety_plan_marketable_rate_range",
        ),
        sa.CheckConstraint(
            "expected_total_marketable_kg is null or expected_total_marketable_kg >= 0",
            name="ck_farm_season_variety_plan_expected_total_non_negative",
        ),
        sa.CheckConstraint(
            "tree_age_years is null or tree_age_years >= 0",
            name="ck_farm_season_variety_plan_tree_age_non_negative",
        ),
        sa.CheckConstraint(
            "version > 0",
            name="ck_farm_season_variety_plan_version_positive",
        ),
        sa.CheckConstraint(
            "effective_to is null or effective_to > effective_from",
            name="ck_farm_season_variety_plan_effective_range",
        ),
        sa.CheckConstraint(
            "flowering_start_date is null or flowering_peak_date is null "
            "or flowering_start_date <= flowering_peak_date",
            name="ck_farm_season_variety_plan_flowering_start_peak",
        ),
        sa.CheckConstraint(
            "flowering_peak_date is null or flowering_end_date is null "
            "or flowering_peak_date <= flowering_end_date",
            name="ck_farm_season_variety_plan_flowering_peak_end",
        ),
        sa.ForeignKeyConstraint(
            ["farm_id"],
            ["dim_farm.id"],
            name="fk_farm_plan_farm_id_dim_farm",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["subfarm_id"],
            ["dim_subfarm.id"],
            name="fk_farm_plan_subfarm_id_dim_subfarm",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["season_id"],
            ["dim_season.id"],
            name="fk_farm_plan_season_id_dim_season",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["variety_id"],
            ["dim_variety.id"],
            name="fk_farm_plan_variety_id_dim_variety",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_farm_season_variety_plan"),
        sa.UniqueConstraint("row_hash", name="uq_farm_season_variety_plan_row_hash"),
    )
    op.create_index(
        "uq_farm_season_variety_plan_version_null_subfarm",
        "farm_season_variety_plan",
        ["farm_id", "season_id", "variety_id", "version"],
        unique=True,
        postgresql_where=sa.text("subfarm_id is null"),
        sqlite_where=sa.text("subfarm_id is null"),
    )
    op.create_index(
        "uq_farm_season_variety_plan_version_with_subfarm",
        "farm_season_variety_plan",
        ["farm_id", "subfarm_id", "season_id", "variety_id", "version"],
        unique=True,
        postgresql_where=sa.text("subfarm_id is not null"),
        sqlite_where=sa.text("subfarm_id is not null"),
    )
    op.create_index(
        "ix_farm_season_variety_plan_business_key",
        "farm_season_variety_plan",
        ["farm_id", "season_id", "variety_id"],
    )
    op.create_index(
        "ix_farm_season_variety_plan_subfarm_id",
        "farm_season_variety_plan",
        ["subfarm_id"],
    )
    op.create_index(
        "ix_farm_season_variety_plan_effective_from",
        "farm_season_variety_plan",
        ["effective_from"],
    )
    op.create_index(
        "ix_farm_season_variety_plan_effective_to",
        "farm_season_variety_plan",
        ["effective_to"],
    )
    op.create_index(
        "ix_farm_season_variety_plan_available_at",
        "farm_season_variety_plan",
        ["available_at"],
    )
    op.create_index(
        "ix_farm_season_variety_plan_row_hash",
        "farm_season_variety_plan",
        ["row_hash"],
    )

    op.create_table(
        "production_plan_import_run",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("file_sha256", sa.Text(), nullable=False),
        sa.Column("source_version", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("row_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("inserted_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("skipped_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("rejected_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("duplicate_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("unknown_farm_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("unknown_subfarm_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("unknown_season_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("unknown_variety_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("invalid_date_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("invalid_numeric_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("overlap_conflict_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("version_conflict_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("report_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status in ('running', 'completed', 'failed')",
            name="ck_production_plan_import_run_status",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_production_plan_import_run"),
    )


def downgrade() -> None:
    op.drop_table("production_plan_import_run")

    op.drop_index(
        "ix_farm_season_variety_plan_row_hash",
        table_name="farm_season_variety_plan",
    )
    op.drop_index(
        "ix_farm_season_variety_plan_available_at",
        table_name="farm_season_variety_plan",
    )
    op.drop_index(
        "ix_farm_season_variety_plan_effective_to",
        table_name="farm_season_variety_plan",
    )
    op.drop_index(
        "ix_farm_season_variety_plan_effective_from",
        table_name="farm_season_variety_plan",
    )
    op.drop_index(
        "ix_farm_season_variety_plan_subfarm_id",
        table_name="farm_season_variety_plan",
    )
    op.drop_index(
        "ix_farm_season_variety_plan_business_key",
        table_name="farm_season_variety_plan",
    )
    op.drop_index(
        "uq_farm_season_variety_plan_version_with_subfarm",
        table_name="farm_season_variety_plan",
    )
    op.drop_index(
        "uq_farm_season_variety_plan_version_null_subfarm",
        table_name="farm_season_variety_plan",
    )
    op.drop_table("farm_season_variety_plan")
