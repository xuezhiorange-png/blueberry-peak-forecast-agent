"""Create task 1 master data tables.

Revision ID: 0002_master_data
Revises: 0001_task0_baseline
Create Date: 2026-06-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_master_data"
down_revision: str | None = "0001_task0_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dim_season",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.CheckConstraint("end_date >= start_date", name="ck_dim_season_date_range"),
        sa.PrimaryKeyConstraint("id", name="pk_dim_season"),
        sa.UniqueConstraint("code", name="uq_dim_season_code"),
    )
    op.create_table(
        "dim_factory",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.Text(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("region_name", sa.Text(), nullable=True),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("altitude_m", sa.Numeric(8, 2), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.CheckConstraint(
            "latitude is null or (latitude >= -90 and latitude <= 90)",
            name="ck_dim_factory_latitude_range",
        ),
        sa.CheckConstraint(
            "longitude is null or (longitude >= -180 and longitude <= 180)",
            name="ck_dim_factory_longitude_range",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_dim_factory"),
        sa.UniqueConstraint("code", name="uq_dim_factory_code"),
        sa.UniqueConstraint("name", name="uq_dim_factory_name"),
    )
    op.create_table(
        "dim_farm",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("altitude_m", sa.Numeric(8, 2), nullable=True),
        sa.CheckConstraint(
            "latitude is null or (latitude >= -90 and latitude <= 90)",
            name="ck_dim_farm_latitude_range",
        ),
        sa.CheckConstraint(
            "longitude is null or (longitude >= -180 and longitude <= 180)",
            name="ck_dim_farm_longitude_range",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_dim_farm"),
        sa.UniqueConstraint("name", name="uq_dim_farm_name"),
    )
    op.create_table(
        "dim_variety",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_dim_variety"),
        sa.UniqueConstraint("code", name="uq_dim_variety_code"),
    )
    op.create_table(
        "dim_grade",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column(
            "is_analysis_eligible_default",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_dim_grade"),
        sa.UniqueConstraint("code", name="uq_dim_grade_code"),
    )
    op.create_table(
        "dim_subfarm",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("farm_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("altitude_m", sa.Numeric(8, 2), nullable=True),
        sa.ForeignKeyConstraint(
            ["farm_id"],
            ["dim_farm.id"],
            name="fk_dim_subfarm_farm_id_dim_farm",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_dim_subfarm"),
        sa.UniqueConstraint("farm_id", "name", name="uq_dim_subfarm_farm_id_name"),
    )
    op.create_table(
        "dim_holiday",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("season_id", sa.BigInteger(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("region_name", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("end_date >= start_date", name="ck_dim_holiday_date_range"),
        sa.ForeignKeyConstraint(
            ["season_id"],
            ["dim_season.id"],
            name="fk_dim_holiday_season_id_dim_season",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_dim_holiday"),
        sa.UniqueConstraint("season_id", "code", name="uq_dim_holiday_season_id_code"),
    )


def downgrade() -> None:
    op.drop_table("dim_holiday")
    op.drop_table("dim_subfarm")
    op.drop_table("dim_grade")
    op.drop_table("dim_variety")
    op.drop_table("dim_farm")
    op.drop_table("dim_factory")
    op.drop_table("dim_season")
