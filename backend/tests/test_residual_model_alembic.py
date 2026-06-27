import importlib
from pathlib import Path

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from backend.app.models.residual_model import (
    ResidualModelArtifact,
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
    )

    for table in tables:
        for constraint in table.constraints:
            if constraint.name:
                assert len(constraint.name) <= 63, constraint.name
        CreateTable(table).compile(dialect=postgresql.dialect())
