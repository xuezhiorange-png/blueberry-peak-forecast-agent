"""Persist immutable Core forecast to Task 10 authority binding.

Revision ID: c1d4e8f2a9b3
Revises: f3a9b2c8d1e4
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c1d4e8f2a9b3"
down_revision = "f3a9b2c8d1e4"
branch_labels = None
depends_on = None

TABLE = "core_forecast_task10_authority_binding"


def _sha256_check(column_name: str) -> str:
    stripped = column_name
    for char in "0123456789abcdef":
        stripped = f"replace({stripped}, '{char}', '')"
    return (
        f"(length({column_name}) = 64 and lower({column_name}) = {column_name} "
        f"and {stripped} = '')"
    )


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("core_forecast_run_id", sa.BigInteger(), nullable=False),
        sa.Column("task9_run_id", sa.BigInteger(), nullable=False),
        sa.Column("task9_result_hash", sa.Text(), nullable=False),
        sa.Column("task10_prediction_run_id", sa.BigInteger(), nullable=False),
        sa.Column("binding_identity_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["core_forecast_run_id"],
            ["core_forecast_run.id"],
            name="fk_core_forecast_task10_authority_binding_core_run_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["task9_run_id"],
            ["harvest_state_run.id"],
            name="fk_core_forecast_task10_authority_binding_task9_run_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["task10_prediction_run_id"],
            ["residual_model_prediction_run.id"],
            name="fk_core_forecast_task10_authority_binding_task10_run_id",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "core_forecast_run_id",
            name="uq_core_forecast_task10_authority_binding_core_run",
        ),
        sa.CheckConstraint("core_forecast_run_id > 0", name="ck_core_forecast_task10_binding_core"),
        sa.CheckConstraint("task9_run_id > 0", name="ck_core_forecast_task10_binding_task9"),
        sa.CheckConstraint(
            "task10_prediction_run_id > 0",
            name="ck_core_forecast_task10_binding_task10",
        ),
        sa.CheckConstraint(
            _sha256_check("task9_result_hash"),
            name="ck_core_forecast_task10_authority_binding_task9_result_hash",
        ),
        sa.CheckConstraint(
            _sha256_check("binding_identity_hash"),
            name="ck_core_forecast_task10_authority_binding_identity_hash",
        ),
    )
    op.create_index(
        "ix_core_forecast_task10_authority_binding_task10_prediction_run_id",
        TABLE,
        ["task10_prediction_run_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_core_forecast_task10_authority_binding_task10_prediction_run_id",
        table_name=TABLE,
    )
    op.drop_table(TABLE)
