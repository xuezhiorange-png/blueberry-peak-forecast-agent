"""Persist Task 10 leakage-safe residual correction models and predictions.

Revision ID: 0011_residual_model
Revises: 0010_harvest_state_persistence
Create Date: 2026-06-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_residual_model"
down_revision: str | None = "0010_harvest_state_persistence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _sha256_check_sql(column_name: str) -> str:
    stripped = column_name
    for char in "0123456789abcdef":
        stripped = f"replace({stripped}, '{char}', '')"
    return (
        f"length({column_name}) = 64 "
        f"and lower({column_name}) = {column_name} "
        f"and {stripped} = ''"
    )


def upgrade() -> None:
    op.create_table(
        "residual_model_training_run",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("execution_status", sa.Text(), nullable=False),
        sa.Column("eligibility_status", sa.Text(), nullable=False),
        sa.Column("model_family", sa.Text(), nullable=False),
        sa.Column("model_version", sa.Text(), nullable=False),
        sa.Column("feature_schema_version", sa.Text(), nullable=False),
        sa.Column("feature_schema_hash", sa.Text(), nullable=False),
        sa.Column("artifact_schema_version", sa.Text(), nullable=False),
        sa.Column("training_signature", sa.Text(), nullable=False),
        sa.Column("config_hash", sa.Text(), nullable=False),
        sa.Column("config_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("manifest_hash", sa.Text(), nullable=False),
        sa.Column("manifest_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("feature_audit_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "category_encoding_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("training_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("validation_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("eligibility_reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("blockers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fallback_reason", sa.Text(), nullable=True),
        sa.Column("input_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("canonical_output", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("canonical_payload_hash", sa.Text(), nullable=False),
        sa.Column("sample_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("distinct_season_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("distinct_factory_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("manifest_row_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("expected_artifact_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("python_version", sa.Text(), nullable=False),
        sa.Column("numpy_version", sa.Text(), nullable=False),
        sa.Column("sklearn_version", sa.Text(), nullable=False),
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
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("typed_attempt", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint(
            "execution_status in ('running', 'completed', 'blocked', 'failed')",
            name="ck_residual_model_training_run_execution_status",
        ),
        sa.CheckConstraint(
            "eligibility_status in ('not_evaluated', 'eligible', 'ineligible')",
            name="ck_residual_model_training_run_eligibility_status",
        ),
        sa.CheckConstraint(
            "sample_count >= 0",
            name="ck_residual_model_training_run_sample_count",
        ),
        sa.CheckConstraint(
            "distinct_season_count >= 0",
            name="ck_residual_model_training_run_season_count",
        ),
        sa.CheckConstraint(
            "distinct_factory_count >= 0",
            name="ck_residual_model_training_run_factory_count",
        ),
        sa.CheckConstraint(
            "manifest_row_count >= 0",
            name="ck_residual_model_training_run_manifest_row_count",
        ),
        sa.CheckConstraint(
            "expected_artifact_count >= 0",
            name="ck_residual_model_training_run_expected_artifact_count",
        ),
        sa.CheckConstraint(
            # ruff: noqa: E501
            "(execution_status != 'completed' OR eligibility_status != 'eligible' OR expected_artifact_count = 3)",
            name="ck_residual_model_training_run_completed_eligible_artifacts",
        ),
        sa.CheckConstraint(
            # ruff: noqa: E501
            "(execution_status != 'completed' OR eligibility_status != 'ineligible' OR expected_artifact_count = 0)",
            name="ck_residual_model_training_run_completed_ineligible_artifacts",
        ),
        sa.CheckConstraint(
            "(execution_status NOT IN ('blocked', 'failed') OR expected_artifact_count = 0)",
            name="ck_residual_model_training_run_blocked_failed_artifacts",
        ),
        sa.CheckConstraint(
            "(eligibility_status != 'eligible' OR execution_status = 'completed')",
            name="ck_residual_model_training_run_eligible_only_when_completed",
        ),
        sa.CheckConstraint(
            _sha256_check_sql("training_signature"),
            name="ck_residual_model_training_run_signature",
        ),
        sa.CheckConstraint(
            _sha256_check_sql("config_hash"),
            name="ck_residual_model_training_run_config_hash",
        ),
        sa.CheckConstraint(
            _sha256_check_sql("manifest_hash"),
            name="ck_residual_model_training_run_manifest_hash",
        ),
        sa.CheckConstraint(
            _sha256_check_sql("feature_schema_hash"),
            name="ck_residual_model_training_run_feature_schema_hash",
        ),
        sa.CheckConstraint(
            _sha256_check_sql("canonical_payload_hash"),
            name="ck_residual_model_training_run_payload_hash",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "training_signature",
            name="uq_residual_model_training_run_signature",
        ),
    )
    op.create_index(
        "ix_residual_model_training_run_execution_status",
        "residual_model_training_run",
        ["execution_status"],
    )
    op.create_index(
        "ix_residual_model_training_run_eligibility_status",
        "residual_model_training_run",
        ["eligibility_status"],
    )

    op.create_table(
        "residual_model_manifest_row",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("training_run_id", sa.BigInteger(), nullable=False),
        sa.Column("row_index", sa.BigInteger(), nullable=False),
        sa.Column("split", sa.Text(), nullable=False),
        sa.Column("include", sa.Boolean(), nullable=False),
        sa.Column("season_id", sa.BigInteger(), nullable=False),
        sa.Column("destination_factory_id", sa.BigInteger(), nullable=False),
        sa.Column("task9_run_id", sa.BigInteger(), nullable=False),
        sa.Column("task9_result_hash", sa.Text(), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("target_arrival_local_date", sa.Date(), nullable=False),
        sa.Column("forecast_horizon_days", sa.BigInteger(), nullable=False),
        sa.Column("label_analytics_build_run_id", sa.BigInteger(), nullable=False),
        sa.Column("label_actual_source_max_raw_id", sa.BigInteger(), nullable=False),
        sa.Column("label_actual_aggregation_version", sa.Text(), nullable=False),
        sa.Column("label_actual_config_hash", sa.Text(), nullable=False),
        sa.Column("label_actual_source_cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("feature_analytics_build_run_id", sa.BigInteger(), nullable=False),
        sa.Column("feature_actual_source_max_raw_id", sa.BigInteger(), nullable=False),
        sa.Column("feature_actual_aggregation_version", sa.Text(), nullable=False),
        sa.Column("feature_actual_config_hash", sa.Text(), nullable=False),
        sa.Column("feature_actual_source_cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_effective_receipt_kg", sa.Numeric(18, 6), nullable=False),
        sa.Column("structural_p50_kg", sa.Numeric(18, 6), nullable=False),
        sa.Column("structural_p80_kg", sa.Numeric(18, 6), nullable=False),
        sa.Column("structural_p90_kg", sa.Numeric(18, 6), nullable=False),
        sa.Column("residual_label_kg", sa.Numeric(18, 6), nullable=False),
        sa.Column("sample_weight", sa.Numeric(18, 6), nullable=False),
        sa.Column("feature_vector_hash", sa.Text(), nullable=False),
        sa.Column("feature_visibility_audit_hash", sa.Text(), nullable=False),
        sa.Column("exclusion_reason", sa.Text(), nullable=True),
        sa.Column("source_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("row_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "split in ('train', 'validation', 'test')",
            name="ck_residual_model_manifest_row_split",
        ),
        sa.CheckConstraint(
            _sha256_check_sql("task9_result_hash"),
            name="ck_residual_model_manifest_row_task9_hash",
        ),
        sa.CheckConstraint(
            _sha256_check_sql("feature_vector_hash"),
            name="ck_residual_model_manifest_row_vector_hash",
        ),
        sa.CheckConstraint(
            _sha256_check_sql("feature_visibility_audit_hash"),
            name="ck_residual_model_manifest_row_audit_hash",
        ),
        sa.CheckConstraint(
            _sha256_check_sql("label_actual_config_hash"),
            name="ck_residual_model_manifest_row_label_config_hash",
        ),
        sa.CheckConstraint(
            _sha256_check_sql("feature_actual_config_hash"),
            name="ck_residual_model_manifest_row_feature_config_hash",
        ),
        sa.CheckConstraint(
            "row_index > 0",
            name="ck_residual_model_manifest_row_row_index",
        ),
        sa.CheckConstraint(
            "forecast_horizon_days >= 0",
            name="ck_residual_model_manifest_row_forecast_horizon",
        ),
        sa.CheckConstraint(
            "sample_weight >= 0",
            name="ck_residual_model_manifest_row_sample_weight",
        ),
        sa.ForeignKeyConstraint(
            ["training_run_id"],
            ["residual_model_training_run.id"],
            name="fk_residual_model_manifest_row_training_run_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["season_id"],
            ["dim_season.id"],
            name="fk_residual_model_manifest_row_season_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["destination_factory_id"],
            ["dim_factory.id"],
            name="fk_residual_model_manifest_row_factory_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["task9_run_id"],
            ["harvest_state_run.id"],
            name="fk_residual_model_manifest_row_task9_run_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["label_analytics_build_run_id"],
            ["analytics_build_run.id"],
            name="fk_residual_model_manifest_row_label_analytics_build_run_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["feature_analytics_build_run_id"],
            ["analytics_build_run.id"],
            name="fk_residual_model_manifest_row_feature_analytics_build_run_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "training_run_id",
            "row_index",
            name="uq_residual_model_manifest_row_run_index",
        ),
    )
    op.create_index(
        "ix_residual_model_manifest_row_run_id",
        "residual_model_manifest_row",
        ["training_run_id"],
    )

    op.create_table(
        "residual_model_artifact",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("training_run_id", sa.BigInteger(), nullable=False),
        sa.Column("quantile_label", sa.Text(), nullable=False),
        sa.Column("artifact_format", sa.Text(), nullable=False),
        sa.Column("artifact_schema_version", sa.Text(), nullable=False),
        sa.Column("estimator_type", sa.Text(), nullable=False),
        sa.Column("loss_name", sa.Text(), nullable=False),
        sa.Column("quantile_value", sa.Numeric(6, 4), nullable=False),
        sa.Column("artifact_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("artifact_sha256", sa.Text(), nullable=False),
        sa.Column("feature_schema_version", sa.Text(), nullable=False),
        sa.Column("feature_schema_hash", sa.Text(), nullable=False),
        sa.Column("config_hash", sa.Text(), nullable=False),
        sa.Column("trusted_internal_source", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("python_version", sa.Text(), nullable=False),
        sa.Column("numpy_version", sa.Text(), nullable=False),
        sa.Column("sklearn_version", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "quantile_label in ('P50', 'P80', 'P90')",
            name="ck_residual_model_artifact_quantile_label",
        ),
        sa.CheckConstraint(
            "artifact_format in ('joblib_bundle')",
            name="ck_residual_model_artifact_format",
        ),
        sa.CheckConstraint(
            "estimator_type in ('HistGradientBoostingRegressor')",
            name="ck_residual_model_artifact_estimator_type",
        ),
        sa.CheckConstraint(
            "loss_name in ('quantile')",
            name="ck_residual_model_artifact_loss_name",
        ),
        sa.CheckConstraint(
            "trusted_internal_source = true",
            name="ck_residual_model_artifact_trusted_source",
        ),
        sa.CheckConstraint(
            sa.text(
                "(quantile_label = 'P50' AND quantile_value = 0.5000) OR "
                "(quantile_label = 'P80' AND quantile_value = 0.8000) OR "
                "(quantile_label = 'P90' AND quantile_value = 0.9000)"
            ),
            name="ck_residual_model_artifact_quantile_value",
        ),
        sa.CheckConstraint(
            _sha256_check_sql("artifact_sha256"),
            name="ck_residual_model_artifact_sha256",
        ),
        sa.CheckConstraint(
            _sha256_check_sql("feature_schema_hash"),
            name="ck_residual_model_artifact_feature_schema_hash",
        ),
        sa.CheckConstraint(
            _sha256_check_sql("config_hash"),
            name="ck_residual_model_artifact_config_hash",
        ),
        sa.ForeignKeyConstraint(
            ["training_run_id"],
            ["residual_model_training_run.id"],
            name="fk_residual_model_artifact_training_run_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "training_run_id",
            "quantile_label",
            name="uq_residual_model_artifact_run_quantile",
        ),
        sa.UniqueConstraint("artifact_sha256", name="uq_residual_model_artifact_sha256"),
    )
    op.create_index(
        "ix_residual_model_artifact_training_run_id",
        "residual_model_artifact",
        ["training_run_id"],
    )

    op.create_table(
        "residual_model_prediction_run",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("training_run_id", sa.BigInteger(), nullable=True),
        sa.Column("task9_run_id", sa.BigInteger(), nullable=False),
        sa.Column("task9_result_hash", sa.Text(), nullable=False),
        sa.Column("execution_status", sa.Text(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("config_hash", sa.Text(), nullable=False),
        sa.Column("feature_schema_version", sa.Text(), nullable=False),
        sa.Column("feature_schema_hash", sa.Text(), nullable=False),
        sa.Column("artifact_hashes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("prediction_input_signature", sa.Text(), nullable=False),
        sa.Column("prediction_hash", sa.Text(), nullable=False),
        sa.Column("feature_audit", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("blockers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fallback_reason", sa.Text(), nullable=True),
        sa.Column(
            "expected_prediction_row_count",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("input_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("canonical_output", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("canonical_payload_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("typed_attempt", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint(
            "execution_status in ('completed', 'blocked', 'failed')",
            name="ck_residual_model_prediction_run_execution_status",
        ),
        sa.CheckConstraint(
            "mode in ('residual_corrected', 'structural_only', 'blocked')",
            name="ck_residual_model_prediction_run_mode",
        ),
        sa.CheckConstraint(
            "expected_prediction_row_count >= 0",
            name="ck_residual_model_prediction_run_row_count",
        ),
        sa.CheckConstraint(
            "(execution_status != 'blocked' OR expected_prediction_row_count = 0)",
            name="ck_residual_model_prediction_run_blocked_zero",
        ),
        sa.CheckConstraint(
            "(execution_status != 'failed' OR expected_prediction_row_count = 0)",
            name="ck_residual_model_prediction_run_failed_zero",
        ),
        sa.CheckConstraint(
            sa.text(
                "(execution_status != 'completed' OR "
                "mode != 'structural_only' OR "
                "fallback_reason IS NOT NULL)"
            ),
            name="ck_residual_model_prediction_run_structural_fallback",
        ),
        sa.CheckConstraint(
            _sha256_check_sql("task9_result_hash"),
            name="ck_residual_model_prediction_run_task9_hash",
        ),
        sa.CheckConstraint(
            _sha256_check_sql("config_hash"),
            name="ck_residual_model_prediction_run_config_hash",
        ),
        sa.CheckConstraint(
            _sha256_check_sql("feature_schema_hash"),
            name="ck_residual_model_prediction_run_feature_schema_hash",
        ),
        sa.CheckConstraint(
            _sha256_check_sql("prediction_input_signature"),
            name="ck_residual_model_prediction_run_input_signature",
        ),
        sa.CheckConstraint(
            _sha256_check_sql("prediction_hash"),
            name="ck_residual_model_prediction_run_prediction_hash",
        ),
        sa.CheckConstraint(
            _sha256_check_sql("canonical_payload_hash"),
            name="ck_residual_model_prediction_run_payload_hash",
        ),
        sa.ForeignKeyConstraint(
            ["training_run_id"],
            ["residual_model_training_run.id"],
            name="fk_residual_model_prediction_run_training_run_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["task9_run_id"],
            ["harvest_state_run.id"],
            name="fk_residual_model_prediction_run_task9_run_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "prediction_input_signature",
            name="uq_residual_model_prediction_run_input_signature",
        ),
    )
    op.create_index(
        "ix_residual_model_prediction_run_execution_status",
        "residual_model_prediction_run",
        ["execution_status"],
    )
    op.create_index(
        "ix_residual_model_prediction_run_task9_run_id",
        "residual_model_prediction_run",
        ["task9_run_id"],
    )

    op.create_table(
        "residual_model_prediction_row",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("prediction_run_id", sa.BigInteger(), nullable=False),
        sa.Column("model_run_id", sa.BigInteger(), nullable=True),
        sa.Column("task9_run_id", sa.BigInteger(), nullable=False),
        sa.Column("task9_result_hash", sa.Text(), nullable=False),
        sa.Column("destination_factory_id", sa.BigInteger(), nullable=False),
        sa.Column("arrival_local_date", sa.Date(), nullable=False),
        sa.Column("forecast_horizon_days", sa.BigInteger(), nullable=False),
        sa.Column("structural_p50_kg", sa.Numeric(18, 6), nullable=False),
        sa.Column("structural_p80_kg", sa.Numeric(18, 6), nullable=False),
        sa.Column("structural_p90_kg", sa.Numeric(18, 6), nullable=False),
        sa.Column("raw_residual_p50_kg", sa.Numeric(18, 6), nullable=False),
        sa.Column("raw_residual_p80_kg", sa.Numeric(18, 6), nullable=False),
        sa.Column("raw_residual_p90_kg", sa.Numeric(18, 6), nullable=False),
        sa.Column("corrected_raw_p50_kg", sa.Numeric(18, 6), nullable=False),
        sa.Column("corrected_raw_p80_kg", sa.Numeric(18, 6), nullable=False),
        sa.Column("corrected_raw_p90_kg", sa.Numeric(18, 6), nullable=False),
        sa.Column("corrected_p50_kg", sa.Numeric(18, 6), nullable=False),
        sa.Column("corrected_p80_kg", sa.Numeric(18, 6), nullable=False),
        sa.Column("corrected_p90_kg", sa.Numeric(18, 6), nullable=False),
        sa.Column("nonnegative_projection_applied", sa.Boolean(), nullable=False),
        sa.Column("quantile_projection_applied", sa.Boolean(), nullable=False),
        sa.Column("projection_reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("feature_vector_hash", sa.Text(), nullable=False),
        sa.Column("feature_audit_hash", sa.Text(), nullable=False),
        sa.Column("prediction_row_hash", sa.Text(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("fallback_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            _sha256_check_sql("task9_result_hash"),
            name="ck_residual_model_prediction_row_task9_hash",
        ),
        sa.CheckConstraint(
            _sha256_check_sql("feature_vector_hash"),
            name="ck_residual_model_prediction_row_vector_hash",
        ),
        sa.CheckConstraint(
            _sha256_check_sql("feature_audit_hash"),
            name="ck_residual_model_prediction_row_audit_hash",
        ),
        sa.CheckConstraint(
            _sha256_check_sql("prediction_row_hash"),
            name="ck_residual_model_prediction_row_hash",
        ),
        sa.CheckConstraint(
            "mode in ('residual_corrected', 'structural_only', 'blocked')",
            name="ck_residual_model_prediction_row_mode",
        ),
        sa.CheckConstraint(
            "(mode != 'structural_only' OR fallback_reason IS NOT NULL)",
            name="ck_residual_model_prediction_row_structural_fallback",
        ),
        sa.CheckConstraint(
            "(mode != 'residual_corrected' OR fallback_reason IS NULL)",
            name="ck_residual_model_prediction_row_corrected_no_fallback",
        ),
        sa.CheckConstraint(
            "corrected_p50_kg >= 0 and corrected_p80_kg >= 0 and corrected_p90_kg >= 0",
            name="ck_residual_model_prediction_row_nonnegative",
        ),
        sa.CheckConstraint(
            "corrected_p50_kg <= corrected_p80_kg and corrected_p80_kg <= corrected_p90_kg",
            name="ck_residual_model_prediction_row_monotonic",
        ),
        sa.CheckConstraint(
            "forecast_horizon_days >= 0",
            name="ck_residual_model_prediction_row_forecast_horizon",
        ),
        sa.CheckConstraint(
            sa.text(
                "mode != 'structural_only' or "
                "(raw_residual_p50_kg = 0 and "
                "raw_residual_p80_kg = 0 and "
                "raw_residual_p90_kg = 0)"
            ),
            name="ck_residual_model_prediction_row_structural_only",
        ),
        sa.ForeignKeyConstraint(
            ["prediction_run_id"],
            ["residual_model_prediction_run.id"],
            name="fk_residual_model_prediction_row_prediction_run_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["model_run_id"],
            ["residual_model_training_run.id"],
            name="fk_residual_model_prediction_row_model_run_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["task9_run_id"],
            ["harvest_state_run.id"],
            name="fk_residual_model_prediction_row_task9_run_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["destination_factory_id"],
            ["dim_factory.id"],
            name="fk_residual_model_prediction_row_factory_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "prediction_run_id",
            "destination_factory_id",
            "arrival_local_date",
            name="uq_residual_model_prediction_row_run_factory_date",
        ),
    )
    op.create_index(
        "ix_residual_model_prediction_row_prediction_run_id",
        "residual_model_prediction_row",
        ["prediction_run_id"],
    )

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

    op.drop_index(
        "ix_residual_model_prediction_row_prediction_run_id",
        table_name="residual_model_prediction_row",
    )
    op.drop_table("residual_model_prediction_row")
    op.drop_index(
        "ix_residual_model_prediction_run_task9_run_id",
        table_name="residual_model_prediction_run",
    )
    op.drop_index(
        "ix_residual_model_prediction_run_execution_status",
        table_name="residual_model_prediction_run",
    )
    op.drop_table("residual_model_prediction_run")
    op.drop_index(
        "ix_residual_model_artifact_training_run_id",
        table_name="residual_model_artifact",
    )
    op.drop_table("residual_model_artifact")
    op.drop_index(
        "ix_residual_model_manifest_row_run_id",
        table_name="residual_model_manifest_row",
    )
    op.drop_table("residual_model_manifest_row")
    op.drop_index(
        "ix_residual_model_training_run_eligibility_status",
        table_name="residual_model_training_run",
    )
    op.drop_index(
        "ix_residual_model_training_run_execution_status",
        table_name="residual_model_training_run",
    )
    op.drop_table("residual_model_training_run")
