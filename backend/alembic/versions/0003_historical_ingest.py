"""Create task 2 historical ingest tables.

Revision ID: 0003_historical_ingest
Revises: 0002_master_data
Create Date: 2026-06-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_historical_ingest"
down_revision: str | None = "0002_master_data"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ingest_file",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("file_sha256", sa.Text(), nullable=False),
        sa.Column("season_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("sheet_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("row_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("inserted_row_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("suspected_duplicate_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("config_hash", sa.Text(), nullable=False),
        sa.Column("config_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column(
            "quality_report",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status in ('running', 'completed', 'failed', 'skipped')",
            name="ck_ingest_file_status",
        ),
        sa.ForeignKeyConstraint(
            ["season_id"],
            ["dim_season.id"],
            name="fk_ingest_file_season_id_dim_season",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ingest_file"),
        sa.UniqueConstraint("file_sha256", name="uq_ingest_file_file_sha256"),
    )
    op.create_index("ix_ingest_file_season_id", "ingest_file", ["season_id"])
    op.create_index("ix_ingest_file_status", "ingest_file", ["status"])

    op.create_table(
        "fact_receipt_raw",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ingest_file_id", sa.BigInteger(), nullable=False),
        sa.Column("season_id", sa.BigInteger(), nullable=False),
        sa.Column("source_sheet", sa.Text(), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("receipt_date_raw", sa.Text(), nullable=True),
        sa.Column("link_name_raw", sa.Text(), nullable=True),
        sa.Column("farm_raw", sa.Text(), nullable=True),
        sa.Column("subfarm_raw", sa.Text(), nullable=True),
        sa.Column("variety_raw", sa.Text(), nullable=True),
        sa.Column("grade_raw", sa.Text(), nullable=True),
        sa.Column("weight_kg_raw", sa.Text(), nullable=True),
        sa.Column("factory_raw", sa.Text(), nullable=True),
        sa.Column("receipt_date", sa.Date(), nullable=True),
        sa.Column("weight_kg", sa.Numeric(18, 6), nullable=True),
        sa.Column("factory_normalized", sa.Text(), nullable=True),
        sa.Column("variety_normalized", sa.Text(), nullable=True),
        sa.Column("factory_id", sa.BigInteger(), nullable=True),
        sa.Column("variety_id", sa.BigInteger(), nullable=True),
        sa.Column("grade_id", sa.BigInteger(), nullable=True),
        sa.Column("is_date_valid", sa.Boolean(), nullable=False),
        sa.Column("is_weight_valid", sa.Boolean(), nullable=False),
        sa.Column("is_factory_known", sa.Boolean(), nullable=False),
        sa.Column("is_variety_known", sa.Boolean(), nullable=False),
        sa.Column("is_suspected_duplicate", sa.Boolean(), nullable=False),
        sa.Column("is_analysis_eligible", sa.Boolean(), nullable=False),
        sa.Column("exclusion_reasons", postgresql.JSONB(), nullable=False),
        sa.Column("parse_errors", postgresql.JSONB(), nullable=False),
        sa.Column("source_row_fingerprint", sa.Text(), nullable=False),
        sa.Column("business_fingerprint", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["factory_id"],
            ["dim_factory.id"],
            name="fk_fact_receipt_raw_factory_id_dim_factory",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["grade_id"],
            ["dim_grade.id"],
            name="fk_fact_receipt_raw_grade_id_dim_grade",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ingest_file_id"],
            ["ingest_file.id"],
            name="fk_fact_receipt_raw_ingest_file_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["season_id"],
            ["dim_season.id"],
            name="fk_fact_receipt_raw_season_id_dim_season",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["variety_id"],
            ["dim_variety.id"],
            name="fk_fact_receipt_raw_variety_id_dim_variety",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_fact_receipt_raw"),
        sa.UniqueConstraint("source_row_fingerprint", name="uq_fact_receipt_raw_source_row_fp"),
    )
    op.create_index("ix_fact_receipt_raw_ingest_file_id", "fact_receipt_raw", ["ingest_file_id"])
    op.create_index("ix_fact_receipt_raw_season_id", "fact_receipt_raw", ["season_id"])
    op.create_index("ix_fact_receipt_raw_business_fp", "fact_receipt_raw", ["business_fingerprint"])
    op.create_index("ix_fact_receipt_raw_receipt_date", "fact_receipt_raw", ["receipt_date"])
    op.create_index("ix_fact_receipt_raw_factory_id", "fact_receipt_raw", ["factory_id"])
    op.create_index("ix_fact_receipt_raw_variety_id", "fact_receipt_raw", ["variety_id"])


def downgrade() -> None:
    op.drop_index("ix_fact_receipt_raw_variety_id", table_name="fact_receipt_raw")
    op.drop_index("ix_fact_receipt_raw_factory_id", table_name="fact_receipt_raw")
    op.drop_index("ix_fact_receipt_raw_receipt_date", table_name="fact_receipt_raw")
    op.drop_index("ix_fact_receipt_raw_business_fp", table_name="fact_receipt_raw")
    op.drop_index("ix_fact_receipt_raw_season_id", table_name="fact_receipt_raw")
    op.drop_index("ix_fact_receipt_raw_ingest_file_id", table_name="fact_receipt_raw")
    op.drop_table("fact_receipt_raw")
    op.drop_index("ix_ingest_file_status", table_name="ingest_file")
    op.drop_index("ix_ingest_file_season_id", table_name="ingest_file")
    op.drop_table("ingest_file")
