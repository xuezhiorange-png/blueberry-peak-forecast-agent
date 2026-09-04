"""S3-B final-target quantile prediction lane schema remediation.

Revision ID: f3a9b2c8d1e4
Revises: e8b2c4d6f1a3
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "f3a9b2c8d1e4"
down_revision = "e8b2c4d6f1a3"
branch_labels = None
depends_on = None

PREDICTION_RUN_TABLE = "residual_model_prediction_run"
TRAINING_RUN_TABLE = "residual_model_training_run"

MODE_CONSTRAINT = "ck_residual_model_prediction_run_mode"
TASK9_HASH_CONSTRAINT = "ck_residual_model_prediction_run_task9_hash"
LANE_CONSTRAINT = "ck_residual_model_prediction_run_lane_consistency"
GRAIN_COUNT_CONSTRAINT = "ck_residual_model_training_run_grain_count"
TARGET_KIND_CONSTRAINT = "ck_residual_model_prediction_run_target_kind"


def _sha256_check_sql(column_name: str) -> str:
    stripped = column_name
    for char in "0123456789abcdef":
        stripped = f"replace({stripped}, '{char}', '')"
    return (
        f"(task9_result_hash IS NULL OR "
        f"(length({column_name}) = 64 and lower({column_name}) = {column_name} "
        f"and {stripped} = ''))"
    )


def _lane_consistency_sql() -> str:
    return (
        "("
        "prediction_target_kind = 'LEGACY_RESIDUAL_CORRECTION' AND "
        "task9_run_id IS NOT NULL AND "
        "task9_result_hash IS NOT NULL AND "
        "mode IN ('residual_corrected', 'structural_only', 'blocked')"
        ") OR ("
        "prediction_target_kind = 'FINAL_TARGET_QUANTILE' AND "
        "task9_run_id IS NULL AND "
        "task9_result_hash IS NULL AND "
        "training_run_id IS NOT NULL AND "
        "expected_prediction_row_count = 0 AND "
        "("
        "(execution_status = 'completed' AND mode = 'final_target_quantile') OR "
        "(execution_status IN ('blocked', 'failed') AND mode = 'blocked')"
        ")"
        ")"
    )


def upgrade() -> None:
    op.add_column(
        PREDICTION_RUN_TABLE,
        sa.Column(
            "prediction_target_kind",
            sa.Text(),
            nullable=False,
            server_default="LEGACY_RESIDUAL_CORRECTION",
        ),
    )
    op.execute(
        text(
            f"UPDATE {PREDICTION_RUN_TABLE} "
            "SET prediction_target_kind = 'LEGACY_RESIDUAL_CORRECTION'"
        )
    )
    op.create_check_constraint(
        TARGET_KIND_CONSTRAINT,
        PREDICTION_RUN_TABLE,
        "prediction_target_kind in ('LEGACY_RESIDUAL_CORRECTION', 'FINAL_TARGET_QUANTILE')",
    )

    op.add_column(
        TRAINING_RUN_TABLE,
        sa.Column(
            "distinct_grain_count",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
    )
    op.execute(text(f"UPDATE {TRAINING_RUN_TABLE} SET distinct_grain_count = 0"))
    op.create_check_constraint(
        GRAIN_COUNT_CONSTRAINT,
        TRAINING_RUN_TABLE,
        "distinct_grain_count >= 0",
    )

    op.drop_constraint(MODE_CONSTRAINT, PREDICTION_RUN_TABLE, type_="check")
    op.create_check_constraint(
        MODE_CONSTRAINT,
        PREDICTION_RUN_TABLE,
        "mode in ('residual_corrected', 'structural_only', 'blocked', 'final_target_quantile')",
    )

    op.drop_constraint(TASK9_HASH_CONSTRAINT, PREDICTION_RUN_TABLE, type_="check")
    op.create_check_constraint(
        TASK9_HASH_CONSTRAINT,
        PREDICTION_RUN_TABLE,
        _sha256_check_sql("task9_result_hash"),
    )

    op.alter_column(
        PREDICTION_RUN_TABLE,
        "task9_run_id",
        existing_type=sa.BigInteger(),
        nullable=True,
    )
    op.alter_column(
        PREDICTION_RUN_TABLE,
        "task9_result_hash",
        existing_type=sa.Text(),
        nullable=True,
    )

    op.create_check_constraint(
        LANE_CONSTRAINT,
        PREDICTION_RUN_TABLE,
        _lane_consistency_sql(),
    )


def downgrade() -> None:
    bind = op.get_bind()
    final_target_count = bind.execute(
        text(
            f"SELECT COUNT(*) FROM {PREDICTION_RUN_TABLE} "
            "WHERE prediction_target_kind = 'FINAL_TARGET_QUANTILE'"
        )
    ).scalar_one()
    if final_target_count > 0:
        raise RuntimeError("Downgrade forbidden: FINAL_TARGET_QUANTILE prediction rows exist")

    op.drop_constraint(LANE_CONSTRAINT, PREDICTION_RUN_TABLE, type_="check")

    op.alter_column(
        PREDICTION_RUN_TABLE,
        "task9_result_hash",
        existing_type=sa.Text(),
        nullable=False,
    )
    op.alter_column(
        PREDICTION_RUN_TABLE,
        "task9_run_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )

    op.drop_constraint(TASK9_HASH_CONSTRAINT, PREDICTION_RUN_TABLE, type_="check")
    op.create_check_constraint(
        TASK9_HASH_CONSTRAINT,
        PREDICTION_RUN_TABLE,
        (
            "length(task9_result_hash) = 64 and lower(task9_result_hash) = task9_result_hash "
            "and replace(replace(replace(replace(replace(replace(replace(replace("
            "replace(replace(replace(replace(replace(replace(replace(replace("
            "task9_result_hash, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), "
            "'5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), "
            "'c', ''), 'd', ''), 'e', ''), 'f', '') = ''"
        ),
    )

    op.drop_constraint(MODE_CONSTRAINT, PREDICTION_RUN_TABLE, type_="check")
    op.create_check_constraint(
        MODE_CONSTRAINT,
        PREDICTION_RUN_TABLE,
        "mode in ('residual_corrected', 'structural_only', 'blocked')",
    )

    op.drop_constraint(GRAIN_COUNT_CONSTRAINT, TRAINING_RUN_TABLE, type_="check")
    op.drop_column(TRAINING_RUN_TABLE, "distinct_grain_count")

    op.drop_constraint(TARGET_KIND_CONSTRAINT, PREDICTION_RUN_TABLE, type_="check")
    op.drop_column(PREDICTION_RUN_TABLE, "prediction_target_kind")
