from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

MIGRATION_PATH = Path("backend/alembic/versions/0018_actual_harvest_import_staging.py")
MIGRATION_REVISION = "0018_actual_harvest_import_staging"


def _migration_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("actual_harvest_migration_0018", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def assert_actual_harvest_alembic_head_and_revision_contract() -> None:
    config = Config("backend/alembic.ini")
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == [MIGRATION_REVISION]
    module = _migration_module()
    assert module.revision == MIGRATION_REVISION
    assert module.down_revision == "0017_core_forecast_run_persistence"


def assert_actual_harvest_sqlite_upgrade_downgrade_upgrade() -> None:
    module = _migration_module()
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade()
        inspector = sa.inspect(connection)
        assert set(inspector.get_table_names()) == {
            "actual_harvest_import_batch",
            "actual_harvest_import_record",
        }
        assert {
            column["name"] for column in inspector.get_columns("actual_harvest_import_record")
        } >= {
            "actual_harvest_quantity_kg",
            "source_system",
            "external_batch_id",
        }
        assert inspector.get_indexes("actual_harvest_import_record")
        assert inspector.get_foreign_keys("actual_harvest_import_record")[0]["options"] == {
            "ondelete": "RESTRICT"
        }

        module.downgrade()
        assert set(sa.inspect(connection).get_table_names()) == set()

        module.upgrade()
        assert set(sa.inspect(connection).get_table_names()) == {
            "actual_harvest_import_batch",
            "actual_harvest_import_record",
        }


def assert_actual_harvest_migration_architecture_contract() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    module = _migration_module()
    assert "JSON" not in source
    assert "parser" not in source.lower()
    assert "label_snapshot" not in source
    assert "commit_manifest" not in source
    assert "revision_graph" not in source
    assert "from backend.app" not in source
    assert "import backend.app" not in source
    assert module.IMPORT_CHANNEL_VALUES == ("api", "csv", "xlsx")
    assert module.PHYSICAL_EVENT_VALUES == ("FARM_PICK",)
    assert module.QUANTITY_BASIS_VALUES == ("OBSERVED_WEIGHT",)
    assert module.QUANTITY_UNIT_VALUES == ("KG",)
    assert module.MISSING_RECORD_SEMANTICS_VALUES == ("UNKNOWN_NOT_ZERO",)
    assert module.RECORD_STATUS_VALUES == (
        "ACTIVE",
        "CORRECTED",
        "VOID",
        "FINALIZED",
    )
    assert module.SOURCE_RECORDED_AT_AUTHORITY_VALUES == (
        "TRUSTED_SOURCE_TIMESTAMP",
        "USER_ASSERTED_UNVERIFIED",
        "MISSING",
        "CONFLICTING",
    )
    assert module.BATCH_STATUS_VALUES == (
        "RECEIVED",
        "UPLOADING",
        "SEALED",
        "PARSING",
        "PARSE_FAILED",
        "VALIDATING",
        "VALIDATION_FAILED",
        "VALIDATED",
        "COMMITTING",
        "COMMITTED",
        "COMMIT_FAILED",
        "CANCELLED",
    )
    assert module.BATCH_SEAL_STATUS_VALUES == ("UNSEALED", "SEALED")
