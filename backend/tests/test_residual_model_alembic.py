from pathlib import Path

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from backend.app.models.residual_model import (
    ResidualModelArtifact,
    ResidualModelManifestRow,
    ResidualModelMetric,
    ResidualModelPredictionRow,
    ResidualModelPredictionRun,
    ResidualModelTrainingRun,
)


def test_residual_model_migration_metadata() -> None:
    revision_path = Path("backend/alembic/versions/0011_residual_model.py")

    assert revision_path.exists()
    source = revision_path.read_text()
    assert 'revision: str = "0011_residual_model"' in source
    assert 'down_revision: str | None = "0010_harvest_state_persistence"' in source
    assert "def upgrade() -> None:" in source


def test_residual_model_migration_has_downgrade() -> None:
    revision_path = Path("backend/alembic/versions/0011_residual_model.py")

    source = revision_path.read_text()
    assert "def downgrade() -> None:" in source


def test_residual_model_schema_contains_tables() -> None:
    schema_path = Path("sql/schema.sql")
    source = schema_path.read_text()

    for table_name in (
        "residual_model_training_run",
        "residual_model_manifest_row",
        "residual_model_artifact",
        "residual_model_metric",
        "residual_model_prediction_run",
        "residual_model_prediction_row",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table_name} (" in source


def test_residual_model_postgres_constraint_names_fit_identifier_limit() -> None:
    tables = (
        ResidualModelTrainingRun.__table__,
        ResidualModelManifestRow.__table__,
        ResidualModelArtifact.__table__,
        ResidualModelMetric.__table__,
        ResidualModelPredictionRun.__table__,
        ResidualModelPredictionRow.__table__,
    )

    for table in tables:
        for constraint in table.constraints:
            if constraint.name:
                assert len(constraint.name) <= 63, constraint.name
        CreateTable(table).compile(dialect=postgresql.dialect())
