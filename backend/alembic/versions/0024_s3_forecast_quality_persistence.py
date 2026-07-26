"""Create the V0.2-S3 Round B forecast-quality persistence schema."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.types import TypeEngine

revision = "0024_s3_forecast_quality_persistence"
down_revision = "0023_historical_backtest_binding"
branch_labels = None
depends_on = None

_SCHEMA_VERSION = "v0.2-s3-quality-persistence-v1"


def _json_type(is_sqlite: bool) -> TypeEngine[Any]:
    return sa.JSON() if is_sqlite else postgresql.JSONB(astext_type=sa.Text())


def _bigint_type(is_sqlite: bool) -> TypeEngine[Any]:
    return sa.Integer() if is_sqlite else sa.BigInteger()


def _sha256_check(column: str, name: str) -> sa.CheckConstraint:
    stripped = column
    for char in "0123456789abcdef":
        stripped = f"replace({stripped}, '{char}', '')"
    return sa.CheckConstraint(
        f"length({column}) = 64 AND lower({column}) = {column} AND {stripped} = ''",
        name=name,
    )


def _create_tables(is_sqlite: bool) -> None:
    json_type = _json_type(is_sqlite)
    bigint = _bigint_type(is_sqlite)

    op.create_table(
        "quality_evaluation_run",
        sa.Column("id", bigint, primary_key=True, autoincrement=True),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("evaluation_request_hash", sa.Text(), nullable=False),
        sa.Column("s2_run_identity", sa.Text(), nullable=False),
        sa.Column("s2_manifest_identity", sa.Text(), nullable=False),
        sa.Column("s2_binding_row_set_hash", sa.Text(), nullable=False),
        sa.Column("metric_policy_version", sa.Text(), nullable=False),
        sa.Column("baseline_policy_version", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("canonical_payload", json_type, nullable=False),
        sa.Column("canonical_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("evaluation_request_hash", name="uq_quality_evaluation_run_request"),
        sa.UniqueConstraint("canonical_hash", name="uq_quality_evaluation_run_canonical_hash"),
        _sha256_check("evaluation_request_hash", "ck_quality_evaluation_run_request_sha256"),
        _sha256_check("canonical_hash", "ck_quality_evaluation_run_canonical_sha256"),
        sa.CheckConstraint(
            f"schema_version = '{_SCHEMA_VERSION}'",
            name="ck_quality_evaluation_run_schema_version",
        ),
        sa.CheckConstraint("status = 'COMPLETE'", name="ck_quality_evaluation_run_status"),
    )

    op.create_table(
        "quality_metric_result",
        sa.Column("id", bigint, primary_key=True, autoincrement=True),
        sa.Column(
            "quality_evaluation_run_id",
            bigint,
            sa.ForeignKey(
                "quality_evaluation_run.id",
                name="fk_quality_metric_result_run",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("metric_result_key_hash", sa.Text(), nullable=False),
        sa.Column("metric_name", sa.Text(), nullable=False),
        sa.Column("metric_status", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.Text(), nullable=False),
        sa.Column("metric_value", sa.Numeric(20, 6), nullable=True),
        sa.Column("numerator", sa.Numeric(20, 6), nullable=True),
        sa.Column("denominator", sa.Numeric(20, 6), nullable=True),
        sa.Column("breakdown_identity", json_type, nullable=False),
        sa.Column("canonical_payload", json_type, nullable=False),
        sa.Column("canonical_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "quality_evaluation_run_id",
            "metric_result_key_hash",
            name="uq_quality_metric_result_run_key",
        ),
        sa.UniqueConstraint("canonical_hash", name="uq_quality_metric_result_canonical_hash"),
        _sha256_check("metric_result_key_hash", "ck_quality_metric_result_key_sha256"),
        _sha256_check("canonical_hash", "ck_quality_metric_result_canonical_sha256"),
        sa.CheckConstraint(
            "metric_status <> '' AND reason_code <> ''",
            name="ck_quality_metric_result_status_reason_nonempty",
        ),
    )
    op.create_index(
        "ix_quality_metric_result_run_id",
        "quality_metric_result",
        ["quality_evaluation_run_id"],
    )

    op.create_table(
        "quality_breakdown_result",
        sa.Column("id", bigint, primary_key=True, autoincrement=True),
        sa.Column(
            "quality_evaluation_run_id",
            bigint,
            sa.ForeignKey(
                "quality_evaluation_run.id",
                name="fk_quality_breakdown_result_run",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("breakdown_key_hash", sa.Text(), nullable=False),
        sa.Column("breakdown_identity", json_type, nullable=False),
        sa.Column("metric_status", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.Text(), nullable=False),
        sa.Column("s2_comparable_row_count", sa.BigInteger(), nullable=False),
        sa.Column("s2_excluded_row_count", sa.BigInteger(), nullable=False),
        sa.Column("s2_not_computable_row_count", sa.BigInteger(), nullable=False),
        sa.Column("coverage_ratio", sa.Numeric(20, 6), nullable=True),
        sa.Column("metric_values", json_type, nullable=False),
        sa.Column("canonical_payload", json_type, nullable=False),
        sa.Column("canonical_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "quality_evaluation_run_id",
            "breakdown_key_hash",
            name="uq_quality_breakdown_result_run_key",
        ),
        sa.UniqueConstraint("canonical_hash", name="uq_quality_breakdown_result_canonical_hash"),
        _sha256_check("breakdown_key_hash", "ck_quality_breakdown_result_key_sha256"),
        _sha256_check("canonical_hash", "ck_quality_breakdown_result_canonical_sha256"),
        sa.CheckConstraint(
            "s2_comparable_row_count >= 0 AND s2_excluded_row_count >= 0 "
            "AND s2_not_computable_row_count >= 0",
            name="ck_quality_breakdown_result_counts_nonnegative",
        ),
        sa.CheckConstraint(
            "coverage_ratio IS NULL OR (coverage_ratio >= 0 AND coverage_ratio <= 1)",
            name="ck_quality_breakdown_result_coverage_range",
        ),
    )
    op.create_index(
        "ix_quality_breakdown_result_run_id",
        "quality_breakdown_result",
        ["quality_evaluation_run_id"],
    )

    op.create_table(
        "naive_baseline_run",
        sa.Column("id", bigint, primary_key=True, autoincrement=True),
        sa.Column(
            "quality_evaluation_run_id",
            bigint,
            sa.ForeignKey(
                "quality_evaluation_run.id",
                name="fk_naive_baseline_run_run",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("baseline_request_hash", sa.Text(), nullable=False),
        sa.Column("baseline_result_hash", sa.Text(), nullable=False),
        sa.Column("baseline_source_snapshot_identity", sa.Text(), nullable=False),
        sa.Column("baseline_source_snapshot_hash", sa.Text(), nullable=False),
        sa.Column("baseline_source_row_set_hash", sa.Text(), nullable=False),
        sa.Column("visibility_manifest_hash", sa.Text(), nullable=False),
        sa.Column("baseline_policy_version", sa.Text(), nullable=False),
        sa.Column("metric_status", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.Text(), nullable=False),
        sa.Column("canonical_payload", json_type, nullable=False),
        sa.Column("canonical_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "quality_evaluation_run_id",
            "baseline_request_hash",
            name="uq_naive_baseline_run_request",
        ),
        sa.UniqueConstraint(
            "quality_evaluation_run_id",
            "baseline_result_hash",
            name="uq_naive_baseline_run_result",
        ),
        sa.UniqueConstraint("canonical_hash", name="uq_naive_baseline_canonical_hash"),
        _sha256_check("baseline_request_hash", "ck_naive_baseline_request_sha256"),
        _sha256_check("baseline_result_hash", "ck_naive_baseline_result_sha256"),
        _sha256_check("canonical_hash", "ck_naive_baseline_canonical_sha256"),
    )
    op.create_index(
        "ix_naive_baseline_run_run_id",
        "naive_baseline_run",
        ["quality_evaluation_run_id"],
    )

    op.create_table(
        "model_baseline_comparison",
        sa.Column("id", bigint, primary_key=True, autoincrement=True),
        sa.Column(
            "quality_evaluation_run_id",
            bigint,
            sa.ForeignKey(
                "quality_evaluation_run.id",
                name="fk_model_baseline_comparison_run",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column(
            "naive_baseline_run_id",
            bigint,
            sa.ForeignKey(
                "naive_baseline_run.id",
                name="fk_model_baseline_comparison_baseline",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("comparison_key_hash", sa.Text(), nullable=False),
        sa.Column("model_identity", json_type, nullable=False),
        sa.Column("comparison_policy_version", sa.Text(), nullable=False),
        sa.Column("comparison_status", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.Text(), nullable=False),
        sa.Column("canonical_payload", json_type, nullable=False),
        sa.Column("canonical_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "quality_evaluation_run_id",
            "comparison_key_hash",
            name="uq_model_baseline_comparison_run_key",
        ),
        sa.UniqueConstraint("canonical_hash", name="uq_model_baseline_comparison_canonical_hash"),
        _sha256_check("comparison_key_hash", "ck_model_baseline_comparison_key_sha256"),
        _sha256_check("canonical_hash", "ck_model_baseline_comparison_canonical_sha256"),
    )
    op.create_index(
        "ix_model_baseline_comparison_run_id",
        "model_baseline_comparison",
        ["quality_evaluation_run_id"],
    )

    op.create_table(
        "quality_evaluation_manifest",
        sa.Column("id", bigint, primary_key=True, autoincrement=True),
        sa.Column(
            "quality_evaluation_run_id",
            bigint,
            sa.ForeignKey(
                "quality_evaluation_run.id",
                name="fk_quality_manifest_run",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("evaluation_request_hash", sa.Text(), nullable=False),
        sa.Column("evaluation_instance_hash", sa.Text(), nullable=False),
        sa.Column("metric_result_set_hash", sa.Text(), nullable=False),
        sa.Column("breakdown_result_set_hash", sa.Text(), nullable=False),
        sa.Column("baseline_result_set_hash", sa.Text(), nullable=False),
        sa.Column("comparison_result_set_hash", sa.Text(), nullable=False),
        sa.Column("manifest_payload", json_type, nullable=False),
        sa.Column("manifest_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sealed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("quality_evaluation_run_id", name="uq_quality_manifest_run"),
        sa.UniqueConstraint("manifest_hash", name="uq_quality_manifest_hash"),
        _sha256_check("evaluation_request_hash", "ck_quality_manifest_request_sha256"),
        _sha256_check("evaluation_instance_hash", "ck_quality_manifest_instance_sha256"),
        _sha256_check("metric_result_set_hash", "ck_quality_manifest_metric_set_sha256"),
        _sha256_check("breakdown_result_set_hash", "ck_quality_manifest_breakdown_set_sha256"),
        _sha256_check("baseline_result_set_hash", "ck_quality_manifest_baseline_set_sha256"),
        _sha256_check("comparison_result_set_hash", "ck_quality_manifest_comparison_set_sha256"),
        _sha256_check("manifest_hash", "ck_quality_manifest_hash_sha256"),
    )
    op.create_index(
        "ix_quality_manifest_run_id",
        "quality_evaluation_manifest",
        ["quality_evaluation_run_id"],
    )


def _create_postgresql_enforcement() -> None:
    op.execute(
        """
        CREATE FUNCTION quality_evaluation_immutable_row() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'forecast-quality persistence row is immutable';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION quality_evaluation_child_insert_guard() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM quality_evaluation_manifest
                WHERE quality_evaluation_run_id = NEW.quality_evaluation_run_id
            ) THEN
                RAISE EXCEPTION 'forecast-quality child cannot be inserted after manifest seal';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    for table in (
        "quality_evaluation_run",
        "quality_metric_result",
        "quality_breakdown_result",
        "naive_baseline_run",
        "model_baseline_comparison",
        "quality_evaluation_manifest",
    ):
        op.execute(
            f"""
            CREATE TRIGGER trg_quality_{table}_immutable
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION quality_evaluation_immutable_row()
            """
        )
    for table in (
        "quality_metric_result",
        "quality_breakdown_result",
        "naive_baseline_run",
        "model_baseline_comparison",
    ):
        op.execute(
            f"""
            CREATE TRIGGER trg_quality_{table}_manifest_insert_guard
            BEFORE INSERT ON {table}
            FOR EACH ROW EXECUTE FUNCTION quality_evaluation_child_insert_guard()
            """
        )


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    _create_tables(is_sqlite)
    if not is_sqlite:
        _create_postgresql_enforcement()


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    if not is_sqlite:
        for table in (
            "quality_metric_result",
            "quality_breakdown_result",
            "naive_baseline_run",
            "model_baseline_comparison",
        ):
            op.execute(
                f"DROP TRIGGER IF EXISTS trg_quality_{table}_manifest_insert_guard ON {table}"
            )
        for table in (
            "quality_evaluation_run",
            "quality_metric_result",
            "quality_breakdown_result",
            "naive_baseline_run",
            "model_baseline_comparison",
            "quality_evaluation_manifest",
        ):
            op.execute(f"DROP TRIGGER IF EXISTS trg_quality_{table}_immutable ON {table}")
        op.execute("DROP FUNCTION IF EXISTS quality_evaluation_child_insert_guard()")
        op.execute("DROP FUNCTION IF EXISTS quality_evaluation_immutable_row()")
    for table in (
        "quality_evaluation_manifest",
        "model_baseline_comparison",
        "naive_baseline_run",
        "quality_breakdown_result",
        "quality_metric_result",
        "quality_evaluation_run",
    ):
        op.drop_table(table)
