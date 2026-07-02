import importlib
from pathlib import Path

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from backend.app.models.residual_model import (
    ResidualModelArtifact,
    ResidualModelExecutionAttempt,
    ResidualModelManifestRow,
    ResidualModelPredictionRow,
    ResidualModelPredictionRun,
    ResidualModelTrainingRun,
)


def _load_migration() -> object:
    spec = importlib.util.spec_from_file_location(
        "migration_0011_residual_model",
        Path("backend/alembic/versions/0011_residual_model.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_residual_model_migration_metadata() -> None:
    mod = _load_migration()
    assert mod.revision == "0011_residual_model"
    assert mod.down_revision == "0010_harvest_state_persistence"
    assert hasattr(mod, "upgrade")
    assert hasattr(mod, "downgrade")


def test_residual_model_migration_has_downgrade() -> None:
    mod = _load_migration()
    assert mod.downgrade is not None


def test_residual_model_schema_contains_tables() -> None:
    tables = (
        ResidualModelTrainingRun.__table__,
        ResidualModelManifestRow.__table__,
        ResidualModelArtifact.__table__,
        ResidualModelPredictionRun.__table__,
        ResidualModelPredictionRow.__table__,
        ResidualModelExecutionAttempt.__table__,
    )

    for table in tables:
        for constraint in table.constraints:
            if constraint.name:
                assert len(constraint.name) <= 63, constraint.name
        CreateTable(table).compile(dialect=postgresql.dialect())


def _assert_compiled_sql_contains(table, expected_fragments: list[str]) -> str:
    """Compile CREATE TABLE for PostgreSQL and assert all fragments appear."""
    compiled = str(CreateTable(table).compile(dialect=postgresql.dialect()))
    for frag in expected_fragments:
        assert frag in compiled, f"Expected '{frag}' in compiled DDL for {table.name}"
    return compiled


def test_residual_model_training_run_check_constraints() -> None:
    """Verify training_run CHECK constraints appear in compiled PostgreSQL DDL."""
    table = ResidualModelTrainingRun.__table__
    sql = _assert_compiled_sql_contains(
        table,
        [
            "execution_status",
            "eligibility_status",
            "sample_count >= 0",
            "distinct_season_count >= 0",
            "distinct_factory_count >= 0",
            "manifest_row_count >= 0",
            "expected_artifact_count >= 0",
            "execution_status != 'completed' OR eligibility_status != 'eligible' OR expected_artifact_count = 3",  # noqa: E501
            "execution_status != 'completed' OR eligibility_status != 'ineligible' OR expected_artifact_count = 0",  # noqa: E501
            "execution_status NOT IN ('blocked', 'failed') OR expected_artifact_count = 0",
            "eligibility_status != 'eligible' OR execution_status = 'completed'",
            "ck_residual_model_training_run_sample_count",
            "ck_residual_model_training_run_season_count",
            "ck_residual_model_training_run_factory_count",
            "ck_residual_model_training_run_manifest_row_count",
            "ck_residual_model_training_run_expected_artifact_count",
            "ck_residual_model_training_run_completed_eligible_artifacts",
            "ck_residual_model_training_run_completed_ineligible_artifacts",
            "ck_residual_model_training_run_blocked_failed_artifacts",
            "ck_residual_model_training_run_eligible_only_when_completed",
            "training_signature",
            "config_hash",
            "manifest_hash",
            "feature_schema_hash",
            "canonical_payload_hash",
            "uq_residual_model_training_run_signature",
        ],
    )
    # Verify all PostgreSQL-specific constructs compile
    assert "CREATE TABLE" in sql
    assert "BIGINT" in sql
    assert "JSONB" in sql
    assert "TIMESTAMP WITH TIME ZONE" in sql
    assert "feature_schema_hash" in sql
    assert "python_version" in sql
    assert "numpy_version" in sql
    assert "sklearn_version" in sql


def test_residual_model_manifest_row_check_constraints() -> None:
    """Verify manifest_row CHECK constraints appear in compiled PostgreSQL DDL."""
    table = ResidualModelManifestRow.__table__
    sql = _assert_compiled_sql_contains(
        table,
        [
            "split in ('train', 'validation', 'test')",
            "row_index > 0",
            "forecast_horizon_days >= 0",
            "sample_weight >= 0",
            "label_analytics_build_run_id",
            "label_actual_source_max_raw_id",
            "label_actual_aggregation_version",
            "label_actual_config_hash",
            "label_actual_source_cutoff",
            "feature_analytics_build_run_id",
            "feature_actual_source_max_raw_id",
            "feature_actual_aggregation_version",
            "feature_actual_config_hash",
            "feature_actual_source_cutoff",
            "sample_weight",
            "ck_residual_model_manifest_row_label_config_hash",
            "ck_residual_model_manifest_row_feature_config_hash",
            "ck_residual_model_manifest_row_sample_weight",
        ],
    )
    assert "CREATE TABLE" in sql


def test_residual_model_artifact_check_constraints() -> None:
    """Verify artifact CHECK constraints appear in compiled PostgreSQL DDL."""
    table = ResidualModelArtifact.__table__
    sql = _assert_compiled_sql_contains(
        table,
        [
            "quantile_label in ('P50', 'P80', 'P90')",
            "artifact_format in ('joblib_bundle')",
            "estimator_type in ('HistGradientBoostingRegressor')",
            "loss_name in ('quantile')",
            "trusted_internal_source = true",
            "quantile_label = 'P50' AND quantile_value = 0.5000",
            "quantile_label = 'P80' AND quantile_value = 0.8000",
            "quantile_label = 'P90' AND quantile_value = 0.9000",
            "ck_residual_model_artifact_format",
            "ck_residual_model_artifact_estimator_type",
            "ck_residual_model_artifact_loss_name",
            "ck_residual_model_artifact_trusted_source",
            "ck_residual_model_artifact_quantile_value",
        ],
    )
    assert "CREATE TABLE" in sql
    assert "trusted_internal_source" in sql
    assert "feature_schema_hash" in sql
    assert "config_hash" in sql
    assert "BYTEA" in sql


def test_residual_model_prediction_run_check_constraints() -> None:
    """Verify prediction_run CHECK constraints appear in compiled PostgreSQL DDL."""
    table = ResidualModelPredictionRun.__table__
    sql = _assert_compiled_sql_contains(
        table,
        [
            "execution_status in ('completed', 'blocked', 'failed')",
            "mode in ('residual_corrected', 'structural_only', 'blocked')",
            "expected_prediction_row_count >= 0",
            "execution_status != 'blocked' OR expected_prediction_row_count = 0",
            "execution_status != 'failed' OR expected_prediction_row_count = 0",
            "execution_status != 'completed' OR mode != 'structural_only' OR fallback_reason IS NOT NULL",  # noqa: E501
            "ck_residual_model_prediction_run_row_count",
            "ck_residual_model_prediction_run_blocked_zero",
            "ck_residual_model_prediction_run_failed_zero",
            "ck_residual_model_prediction_run_structural_fallback",
        ],
    )
    assert "CREATE TABLE" in sql
    assert "feature_schema_version" in sql
    assert "feature_schema_hash" in sql
    assert "artifact_hashes" in sql
    assert "prediction_input_signature" in sql
    assert "expected_prediction_row_count" in sql
    assert "typed_attempt" in sql


def test_residual_model_prediction_row_check_constraints() -> None:
    """Verify prediction_row CHECK constraints appear in compiled PostgreSQL DDL."""
    table = ResidualModelPredictionRow.__table__
    sql = _assert_compiled_sql_contains(
        table,
        [
            "prediction_row_hash",
            "mode in ('residual_corrected', 'structural_only', 'blocked')",
            "mode != 'structural_only' OR fallback_reason IS NOT NULL",
            "mode != 'residual_corrected' OR fallback_reason IS NULL",
            "corrected_p50_kg >= 0",
            "corrected_p80_kg >= 0",
            "corrected_p90_kg >= 0",
            "corrected_p50_kg <= corrected_p80_kg",
            "corrected_p80_kg <= corrected_p90_kg",
            "forecast_horizon_days >= 0",
            "mode != 'structural_only' or (raw_residual_p50_kg = 0",
            "ck_residual_model_prediction_row_mode",
            "ck_residual_model_prediction_row_structural_fallback",
            "ck_residual_model_prediction_row_corrected_no_fallback",
        ],
    )
    assert "CREATE TABLE" in sql
    assert "NUMERIC(18, 6)" in sql or "NUMERIC(18,6)" in sql
    assert "fallback_reason" in sql


def test_residual_model_execution_attempt_check_constraints() -> None:
    """Verify execution_attempt CHECK constraints appear in compiled PostgreSQL DDL."""
    table = ResidualModelExecutionAttempt.__table__
    sql = _assert_compiled_sql_contains(
        table,
        [
            "attempt_type in ('training', 'prediction')",
            "execution_status in ('running', 'completed', 'blocked', 'failed')",
            "ck_residual_model_attempt_type",
            "ck_residual_model_attempt_execution_status",
            "requested_inputs",
            "config_identity",
            "upstream_requested_ids",
            "sanitized_error",
            "linked_training_run_id",
            "linked_prediction_run_id",
            "started_at",
            "finished_at",
        ],
    )
    assert "CREATE TABLE" in sql
    assert "JSONB" in sql
    assert "TIMESTAMP WITH TIME ZONE" in sql
