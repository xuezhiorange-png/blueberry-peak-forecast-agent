"""Persist Task 10 residual model execution attempt table.

Revision ID: 0012_residual_model_execution_attempt
Revises: 0011_residual_model
Create Date: 2026-06-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_residual_model_execution_attempt"
down_revision: str | None = "0011_residual_model"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "residual_model_execution_attempt",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("attempt_type", sa.Text(), nullable=False),
        sa.Column("execution_status", sa.Text(), nullable=False),
        sa.Column("current_stage", sa.Text(), nullable=False),
        sa.Column(
            "requested_inputs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "config_identity",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "upstream_requested_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "blockers",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("sanitized_error", sa.Text(), nullable=True),
        sa.Column("linked_training_run_id", sa.BigInteger(), nullable=True),
        sa.Column("linked_prediction_run_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "attempt_type in ('training', 'prediction')",
            name="ck_residual_model_attempt_type",
        ),
        sa.CheckConstraint(
            "execution_status in ('running', 'completed', 'blocked', 'failed')",
            name="ck_residual_model_attempt_execution_status",
        ),
        sa.ForeignKeyConstraint(
            ["linked_training_run_id"],
            ["residual_model_training_run.id"],
            name="fk_residual_model_attempt_training_run_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["linked_prediction_run_id"],
            ["residual_model_prediction_run.id"],
            name="fk_residual_model_attempt_prediction_run_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_residual_model_attempt_execution_status",
        "residual_model_execution_attempt",
        ["execution_status"],
    )
    op.create_index(
        "ix_residual_model_attempt_type",
        "residual_model_execution_attempt",
        ["attempt_type"],
    )
    op.create_index(
        "ix_residual_model_attempt_linked_training_run_id",
        "residual_model_execution_attempt",
        ["linked_training_run_id"],
    )
    op.create_index(
        "ix_residual_model_attempt_linked_prediction_run_id",
        "residual_model_execution_attempt",
        ["linked_prediction_run_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_residual_model_attempt_linked_prediction_run_id",
        table_name="residual_model_execution_attempt",
    )
    op.drop_index(
        "ix_residual_model_attempt_linked_training_run_id",
        table_name="residual_model_execution_attempt",
    )
    op.drop_index(
        "ix_residual_model_attempt_type",
        table_name="residual_model_execution_attempt",
    )
    op.drop_index(
        "ix_residual_model_attempt_execution_status",
        table_name="residual_model_execution_attempt",
    )
    op.drop_constraint(
        "fk_residual_model_attempt_prediction_run_id",
        "residual_model_execution_attempt",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_residual_model_attempt_training_run_id",
        "residual_model_execution_attempt",
        type_="foreignkey",
    )
    op.drop_table("residual_model_execution_attempt")
