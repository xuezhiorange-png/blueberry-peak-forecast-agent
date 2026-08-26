"""Create empty S3 incumbent forecast replay identity table.

Revision ID: e8b2c4d6f1a3
Revises: a7c3e9f1b2d4
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e8b2c4d6f1a3"
down_revision = "a7c3e9f1b2d4"
branch_labels = None
depends_on = None

TABLE_NAME = "s3_incumbent_forecast_replay_identity"


def _sqlite_bigint() -> sa.types.TypeEngine[int]:
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        TABLE_NAME,
        sa.Column("id", _sqlite_bigint(), primary_key=True, autoincrement=True),
        sa.Column("forecast_cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("forecast_quantile", sa.Text(), nullable=False),
        sa.UniqueConstraint(
            "forecast_cutoff_at",
            "model_id",
            "forecast_quantile",
            name="uq_s3_incumbent_forecast_replay_identity_grain",
        ),
        sa.CheckConstraint(
            "length(model_id) > 0",
            name="ck_s3_replay_identity_model_id_nonempty",
        ),
        sa.CheckConstraint(
            "length(forecast_quantile) > 0",
            name="ck_s3_replay_identity_quantile_nonempty",
        ),
    )


def downgrade() -> None:
    op.drop_table(TABLE_NAME)
