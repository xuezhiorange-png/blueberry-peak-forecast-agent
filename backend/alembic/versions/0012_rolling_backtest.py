"""Rolling backtest persistence schema.

Revision ID: 0012_rolling_backtest
Revises: 0011_residual_model
Create Date: 2026-06-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_rolling_backtest"
down_revision: str | None = "0011_residual_model"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _sha256_check_sql(column_name: str) -> str:
    stripped = column_name
    for char in "0123456789abcdef":
        stripped = f"replace({stripped}, '{char}', '')"
    return (
        f"length({column_name}) = 64 and lower({column_name}) = {column_name} and {stripped} = ''"
    )


def _nullable_sha256_check_sql(column_name: str) -> str:
    """SHA-256 check for nullable columns: only validated when non-null."""
    stripped = column_name
    for char in "0123456789abcdef":
        stripped = f"replace({stripped}, '{char}', '')"
    return (
        f"({column_name} IS NULL) OR "
        f"(length({column_name}) = 64 "
        f"and lower({column_name}) = {column_name} "
        f"and {stripped} = '')"
    )


def upgrade() -> None:
    # ── rolling_backtest_run ─────────────────────────────────────────────
    op.create_table(
        "rolling_backtest_run",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_signature", sa.Text(), nullable=False),
        sa.Column("config_hash", sa.Text(), nullable=False),
        sa.Column("execution_mode", sa.Text(), nullable=False),
        sa.Column("rolling_schema_version", sa.Text(), nullable=False),
        sa.Column("canonical_serialization_version", sa.Text(), nullable=False),
        sa.Column("availability_registry_version", sa.Text(), nullable=False),
        sa.Column("node_calendar_version", sa.Text(), nullable=False),
        sa.Column("forecast_horizon_policy_version", sa.Text(), nullable=False),
        sa.Column("upstream_selection_policy_version", sa.Text(), nullable=False),
        sa.Column("metric_policy_version", sa.Text(), nullable=False),
        sa.Column("calendar_phase_policy_version", sa.Text(), nullable=False),
        sa.Column("cutoff_policy_version", sa.Text(), nullable=False),
        sa.Column("cutoff_timezone", sa.Text(), nullable=False),
        sa.Column("cutoff_local_time", sa.Time(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("expected_node_count", sa.BigInteger(), nullable=False),
        sa.Column("canonical_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("canonical_payload_hash", sa.Text(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="pk_rolling_backtest_run"),
        sa.UniqueConstraint("run_signature", name="uq_rolling_backtest_run_signature"),
        sa.CheckConstraint(
            _sha256_check_sql("run_signature"),
            name="ck_rolling_backtest_run_signature_sha256",
        ),
        sa.CheckConstraint(
            _sha256_check_sql("config_hash"),
            name="ck_rolling_backtest_run_config_hash_sha256",
        ),
        sa.CheckConstraint(
            _sha256_check_sql("canonical_payload_hash"),
            name="ck_rolling_backtest_run_canonical_payload_hash_sha256",
        ),
        sa.CheckConstraint(
            "execution_mode in ('historical_observed', 'retrospective_replay')",
            name="ck_rolling_backtest_run_execution_mode",
        ),
        sa.CheckConstraint(
            "status in ('pending', 'running', 'forecast_completed', "
            "'partially_completed', 'completed', 'blocked', 'failed')",
            name="ck_rolling_backtest_run_status",
        ),
        sa.CheckConstraint(
            "expected_node_count >= 1",
            name="ck_rolling_backtest_run_expected_node_count",
        ),
    )

    # ── rolling_backtest_node ────────────────────────────────────────────
    op.create_table(
        "rolling_backtest_node",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "rolling_run_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "rolling_backtest_run.id",
                name="fk_rolling_backtest_node_run_id",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("season_id", sa.BigInteger(), nullable=False),
        sa.Column("node_key", sa.Text(), nullable=False),
        sa.Column("node_signature", sa.Text(), nullable=False),
        sa.Column("as_of_local_date", sa.Date(), nullable=False),
        sa.Column("forecast_cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("forecast_start_local_date", sa.Date(), nullable=False),
        sa.Column("forecast_end_local_date", sa.Date(), nullable=False),
        sa.Column("execution_mode", sa.Text(), nullable=False),
        sa.Column("upstream_selection_mode", sa.Text(), nullable=False),
        sa.Column("scope", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("forecast_horizon_policy_version", sa.Text(), nullable=False),
        sa.Column("task10_model_policy", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("cutoff_policy_version", sa.Text(), nullable=False),
        sa.Column("timezone", sa.Text(), nullable=False),
        sa.Column("canonical_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("canonical_payload_hash", sa.Text(), nullable=False),
        sa.Column("expected_resolved_input_count", sa.BigInteger(), nullable=False),
        sa.Column("expected_availability_audit_count", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rolling_backtest_node"),
        sa.UniqueConstraint(
            "rolling_run_id",
            "season_id",
            "node_key",
            name="uq_rolling_backtest_node_business_key",
        ),
        sa.UniqueConstraint(
            "rolling_run_id",
            "node_signature",
            name="uq_rolling_backtest_node_signature",
        ),
        sa.CheckConstraint(
            _sha256_check_sql("node_signature"),
            name="ck_rolling_backtest_node_signature_sha256",
        ),
        sa.CheckConstraint(
            _sha256_check_sql("canonical_payload_hash"),
            name="ck_rolling_backtest_node_canonical_payload_hash_sha256",
        ),
        sa.CheckConstraint(
            "execution_mode in ('historical_observed', 'retrospective_replay')",
            name="ck_rolling_backtest_node_execution_mode",
        ),
        sa.CheckConstraint(
            "upstream_selection_mode in ('pinned', 'historical_resolution')",
            name="ck_rolling_backtest_node_upstream_selection_mode",
        ),
        sa.CheckConstraint(
            "forecast_end_local_date >= forecast_start_local_date",
            name="ck_rolling_backtest_node_forecast_date_range",
        ),
        sa.CheckConstraint(
            "season_id > 0",
            name="ck_rolling_backtest_node_season_positive",
        ),
        sa.CheckConstraint(
            "expected_resolved_input_count >= 0",
            name="ck_rolling_backtest_node_expected_input_count_non_negative",
        ),
        sa.CheckConstraint(
            "expected_availability_audit_count >= 0",
            name="ck_rolling_backtest_node_expected_audit_count_non_negative",
        ),
    )
    op.create_index(
        "ix_rolling_backtest_node_run_id",
        "rolling_backtest_node",
        ["rolling_run_id"],
    )

    # ── rolling_backtest_attempt ─────────────────────────────────────────
    op.create_table(
        "rolling_backtest_attempt",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "rolling_run_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "rolling_backtest_run.id",
                name="fk_rolling_backtest_attempt_run_id",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column(
            "prior_attempt_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "rolling_backtest_attempt.id",
                name="fk_rolling_backtest_attempt_prior_id",
                ondelete="RESTRICT",
            ),
            nullable=True,
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("current_stage", sa.Text(), nullable=False),
        sa.Column("structured_error_code", sa.Text(), nullable=True),
        sa.Column("sanitized_diagnostics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("runtime_environment_identity", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rolling_backtest_attempt"),
        sa.UniqueConstraint(
            "rolling_run_id",
            "attempt_number",
            name="uq_rolling_backtest_attempt_number",
        ),
        sa.CheckConstraint(
            "status in ('pending', 'running', 'forecast_completed', "
            "'partially_completed', 'completed', 'blocked', 'failed')",
            name="ck_rolling_backtest_attempt_status",
        ),
        sa.CheckConstraint(
            "attempt_number >= 1",
            name="ck_rolling_backtest_attempt_number_positive",
        ),
        sa.CheckConstraint(
            "(status in ('pending', 'running')) = (finished_at IS NULL)",
            name="ck_rolling_backtest_attempt_terminal_time",
        ),
    )
    op.create_index(
        "ix_rolling_backtest_attempt_run_id",
        "rolling_backtest_attempt",
        ["rolling_run_id"],
    )

    # ── rolling_backtest_resolved_input ──────────────────────────────────
    op.create_table(
        "rolling_backtest_resolved_input",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "rolling_node_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "rolling_backtest_node.id",
                name="fk_rolling_backtest_resolved_input_node_id",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("source_role", sa.Text(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("role_qualifier", sa.Text(), nullable=True),
        sa.Column("semantic_input_signature", sa.Text(), nullable=True),
        sa.Column("result_hash", sa.Text(), nullable=True),
        sa.Column("canonical_payload_hash", sa.Text(), nullable=True),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("policy_version", sa.Text(), nullable=True),
        sa.Column("persistent_reference_type", sa.Text(), nullable=True),
        sa.Column("persistent_reference_value", sa.Text(), nullable=True),
        sa.Column("canonical_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("audit_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rolling_backtest_resolved_input"),
        sa.UniqueConstraint(
            "rolling_node_id",
            "source_role",
            name="uq_rolling_backtest_resolved_input_source_role",
        ),
        sa.CheckConstraint(
            _sha256_check_sql("audit_hash"),
            name="ck_rolling_backtest_resolved_input_audit_hash_sha256",
        ),
        sa.CheckConstraint(
            _nullable_sha256_check_sql("semantic_input_signature"),
            name="ck_rolling_backtest_resolved_input_semantic_sig_sha256",
        ),
        sa.CheckConstraint(
            _nullable_sha256_check_sql("result_hash"),
            name="ck_rolling_backtest_resolved_input_result_hash_sha256",
        ),
        sa.CheckConstraint(
            _nullable_sha256_check_sql("canonical_payload_hash"),
            name="ck_rolling_backtest_resolved_input_canonical_hash_sha256",
        ),
        sa.CheckConstraint(
            "(persistent_reference_type IS NULL) = (persistent_reference_value IS NULL)",
            name="ck_rolling_backtest_resolved_input_persistent_ref_pairing",
        ),
    )
    op.create_index(
        "ix_rolling_backtest_resolved_input_node_id",
        "rolling_backtest_resolved_input",
        ["rolling_node_id"],
    )

    # ── rolling_backtest_availability_audit ──────────────────────────────
    op.create_table(
        "rolling_backtest_availability_audit",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "rolling_node_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "rolling_backtest_node.id",
                name="fk_rolling_backtest_availability_audit_node_id",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("source_role", sa.Text(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("allowed", sa.Boolean(), nullable=False),
        sa.Column("blocker_code", sa.Text(), nullable=True),
        sa.Column("canonical_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("audit_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rolling_backtest_availability_audit"),
        sa.UniqueConstraint(
            "rolling_node_id",
            "source_role",
            name="uq_rolling_backtest_availability_audit_source_role",
        ),
        sa.CheckConstraint(
            _sha256_check_sql("audit_hash"),
            name="ck_rolling_backtest_availability_audit_hash_sha256",
        ),
        sa.CheckConstraint(
            "(allowed = true AND blocker_code IS NULL) OR "
            "(allowed = false AND blocker_code IS NOT NULL)",
            name="ck_rolling_backtest_audit_consistency",
        ),
    )
    op.create_index(
        "ix_rolling_backtest_availability_audit_node_id",
        "rolling_backtest_availability_audit",
        ["rolling_node_id"],
    )

    # ── rolling_backtest_dag_snapshot ────────────────────────────────────
    op.create_table(
        "rolling_backtest_dag_snapshot",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "rolling_node_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "rolling_backtest_node.id",
                name="fk_rolling_backtest_dag_snapshot_node_id",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("dag_schema_version", sa.Text(), nullable=False),
        sa.Column("dag_policy_version", sa.Text(), nullable=False),
        sa.Column("canonical_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("canonical_payload_hash", sa.Text(), nullable=False),
        sa.Column("expected_node_count", sa.BigInteger(), nullable=False),
        sa.Column("expected_edge_count", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rolling_backtest_dag_snapshot"),
        sa.UniqueConstraint(
            "rolling_node_id",
            name="uq_rolling_backtest_dag_snapshot_node_id",
        ),
        sa.CheckConstraint(
            _sha256_check_sql("canonical_payload_hash"),
            name="ck_rolling_backtest_dag_snapshot_payload_hash_sha256",
        ),
        sa.CheckConstraint(
            "expected_node_count >= 0",
            name="ck_rolling_backtest_dag_snapshot_node_count_non_negative",
        ),
        sa.CheckConstraint(
            "expected_edge_count >= 0",
            name="ck_rolling_backtest_dag_snapshot_edge_count_non_negative",
        ),
    )
    op.create_index(
        "ix_rolling_backtest_dag_snapshot_node_id",
        "rolling_backtest_dag_snapshot",
        ["rolling_node_id"],
    )


def downgrade() -> None:
    op.drop_table("rolling_backtest_dag_snapshot")
    op.drop_table("rolling_backtest_availability_audit")
    op.drop_table("rolling_backtest_resolved_input")
    op.drop_table("rolling_backtest_attempt")
    op.drop_table("rolling_backtest_node")
    op.drop_table("rolling_backtest_run")
