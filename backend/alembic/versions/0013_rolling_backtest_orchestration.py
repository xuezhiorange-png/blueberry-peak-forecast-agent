"""Rolling backtest orchestration: attempt ownership, stage history, outcome snapshot.

Revision ID: 0013_rolling_backtest_orchestration
Revises: 0012_rolling_backtest
Create Date: 2026-06-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_rolling_backtest_orchestration"
down_revision: str | None = "0012_rolling_backtest"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON_VARIANT = postgresql.JSONB(astext_type=sa.Text())

_ORCHESTRATION_STAGES = (
    "resolve_historical_inputs",
    "validate_visibility",
    "validate_authority_chain",
    "resolve_or_replay_task8",
    "resolve_or_replay_task9",
    "resolve_or_train_task10",
    "execute_task10_prediction",
    "finalize_orchestration_snapshot",
)


def _sha256_check_sql(column_name: str) -> str:
    stripped = column_name
    for char in "0123456789abcdef":
        stripped = f"replace({stripped}, '{char}', '')"
    return (
        f"length({column_name}) = 64 and lower({column_name}) = {column_name} and {stripped} = ''"
    )


def upgrade() -> None:
    connection = op.get_bind()
    legacy_attempt_count = connection.execute(
        sa.text("SELECT COUNT(*) FROM rolling_backtest_attempt")
    ).scalar_one()
    if legacy_attempt_count:
        raise RuntimeError(
            "0013_rolling_backtest_orchestration requires an empty "
            "rolling_backtest_attempt table; legacy attempt rows cannot be "
            "deterministically backfilled to rolling_node_id"
        )

    # ── 1. Alter rolling_backtest_attempt: add rolling_node_id ──────────────
    op.add_column(
        "rolling_backtest_attempt",
        sa.Column("rolling_node_id", sa.BigInteger(), nullable=False),
    )

    # Drop old run-level unique constraint
    op.drop_constraint(
        "uq_rolling_backtest_attempt_number",
        "rolling_backtest_attempt",
        type_="unique",
    )
    # Drop old run-level index
    op.drop_index("ix_rolling_backtest_attempt_run_id", table_name="rolling_backtest_attempt")

    # Add new node-level unique constraint
    op.create_unique_constraint(
        "uq_rolling_backtest_attempt_number",
        "rolling_backtest_attempt",
        ["rolling_node_id", "attempt_number"],
    )
    # Add new indexes
    op.create_index(
        "ix_rolling_backtest_attempt_node_id",
        "rolling_backtest_attempt",
        ["rolling_node_id"],
    )
    op.create_index(
        "ix_rolling_backtest_attempt_run_id",
        "rolling_backtest_attempt",
        ["rolling_run_id"],
    )

    # FK from attempt to node
    op.create_foreign_key(
        "fk_rolling_backtest_attempt_node_id",
        "rolling_backtest_attempt",
        "rolling_backtest_node",
        ["rolling_node_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # ── 2. Create rolling_backtest_stage_event ─────────────────────────────
    op.create_table(
        "rolling_backtest_stage_event",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("attempt_id", sa.BigInteger(), nullable=False),
        sa.Column("rolling_node_id", sa.BigInteger(), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("structured_error_code", sa.Text(), nullable=True),
        sa.Column("sanitized_diagnostics", _JSON_VARIANT, nullable=True),
        sa.Column("entered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rolling_backtest_stage_event"),
        sa.UniqueConstraint(
            "attempt_id",
            "sequence_number",
            name="uq_rolling_backtest_stage_event_seq",
        ),
        sa.UniqueConstraint(
            "attempt_id",
            "stage",
            name="uq_rolling_backtest_stage_event_stage",
        ),
        sa.CheckConstraint(
            "sequence_number >= 1",
            name="ck_rolling_backtest_stage_event_seq_positive",
        ),
        sa.CheckConstraint(
            f"stage in ({', '.join(repr(s) for s in _ORCHESTRATION_STAGES)})",
            name="ck_rolling_backtest_stage_event_stage",
        ),
        sa.CheckConstraint(
            "status in ('running', 'completed', 'blocked', 'failed')",
            name="ck_rolling_backtest_stage_event_status",
        ),
        sa.CheckConstraint(
            "(status = 'running') = (finished_at IS NULL)",
            name="ck_rolling_backtest_stage_event_terminal_time",
        ),
        sa.CheckConstraint(
            "(status in ('blocked', 'failed')) = (structured_error_code IS NOT NULL)",
            name="ck_rolling_backtest_stage_event_error_code",
        ),
        sa.CheckConstraint(
            "status != 'running' OR structured_error_code IS NULL",
            name="ck_rolling_backtest_stage_event_running_no_error",
        ),
    )
    op.create_index(
        "ix_rolling_backtest_stage_event_attempt_id",
        "rolling_backtest_stage_event",
        ["attempt_id"],
    )
    op.create_index(
        "ix_rolling_backtest_stage_event_node_id",
        "rolling_backtest_stage_event",
        ["rolling_node_id"],
    )
    op.create_foreign_key(
        "fk_rolling_backtest_stage_event_attempt_id",
        "rolling_backtest_stage_event",
        "rolling_backtest_attempt",
        ["attempt_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_rolling_backtest_stage_event_node_id",
        "rolling_backtest_stage_event",
        "rolling_backtest_node",
        ["rolling_node_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # ── 3. Create rolling_backtest_orchestration_snapshot ──────────────────
    op.create_table(
        "rolling_backtest_orchestration_snapshot",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("attempt_id", sa.BigInteger(), nullable=False),
        sa.Column("rolling_node_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("terminal_stage", sa.Text(), nullable=False),
        sa.Column("fallback_mode", sa.Text(), nullable=True),
        sa.Column("blocker_code", sa.Text(), nullable=True),
        sa.Column("canonical_payload", _JSON_VARIANT, nullable=False),
        sa.Column("canonical_payload_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rolling_backtest_orchestration_snapshot"),
        sa.UniqueConstraint(
            "attempt_id",
            name="uq_rolling_backtest_orchestration_snapshot_attempt_id",
        ),
        sa.CheckConstraint(
            _sha256_check_sql("canonical_payload_hash"),
            name="ck_rolling_backtest_orch_snap_hash_sha256",
        ),
        sa.CheckConstraint(
            "status in ("
            "'forecast_completed', 'partially_completed', "
            "'completed', 'blocked', 'failed')",
            name="ck_rolling_backtest_orch_snap_status",
        ),
        sa.CheckConstraint(
            f"terminal_stage in ({', '.join(repr(s) for s in _ORCHESTRATION_STAGES)})",
            name="ck_rolling_backtest_orch_snap_terminal_stage",
        ),
        sa.CheckConstraint(
            "(status = 'blocked') = (blocker_code IS NOT NULL)",
            name="ck_rolling_backtest_orch_snap_blocker",
        ),
    )
    op.create_index(
        "ix_rolling_backtest_orch_snap_attempt_id",
        "rolling_backtest_orchestration_snapshot",
        ["attempt_id"],
    )
    op.create_index(
        "ix_rolling_backtest_orch_snap_node_id",
        "rolling_backtest_orchestration_snapshot",
        ["rolling_node_id"],
    )
    op.create_foreign_key(
        "fk_rolling_backtest_orch_snap_attempt_id",
        "rolling_backtest_orchestration_snapshot",
        "rolling_backtest_attempt",
        ["attempt_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_rolling_backtest_orch_snap_node_id",
        "rolling_backtest_orchestration_snapshot",
        "rolling_backtest_node",
        ["rolling_node_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    # ── 3. Drop rolling_backtest_orchestration_snapshot ────────────────────
    op.drop_table("rolling_backtest_orchestration_snapshot")

    # ── 2. Drop rolling_backtest_stage_event ───────────────────────────────
    op.drop_table("rolling_backtest_stage_event")

    # ── 1. Revert rolling_backtest_attempt changes ──────────────────────────
    op.drop_constraint(
        "fk_rolling_backtest_attempt_node_id",
        "rolling_backtest_attempt",
        type_="foreignkey",
    )
    op.drop_index("ix_rolling_backtest_attempt_node_id", table_name="rolling_backtest_attempt")
    op.drop_index("ix_rolling_backtest_attempt_run_id", table_name="rolling_backtest_attempt")
    op.drop_constraint(
        "uq_rolling_backtest_attempt_number",
        "rolling_backtest_attempt",
        type_="unique",
    )
    op.drop_column("rolling_backtest_attempt", "rolling_node_id")

    # Restore old run-level unique constraint
    op.create_unique_constraint(
        "uq_rolling_backtest_attempt_number",
        "rolling_backtest_attempt",
        ["rolling_run_id", "attempt_number"],
    )
    # Restore old index
    op.create_index(
        "ix_rolling_backtest_attempt_run_id",
        "rolling_backtest_attempt",
        ["rolling_run_id"],
    )
