from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

MIGRATION_PATH = Path("backend/alembic/versions/0019_actual_harvest_validation_evidence.py")
MIGRATION_REVISION = "0019_actual_harvest_validation_evidence"


def _migration_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("actual_harvest_migration_0019", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _staging_migration_module() -> ModuleType:
    path = Path("backend/alembic/versions/0018_actual_harvest_import_staging.py")
    spec = importlib.util.spec_from_file_location("actual_harvest_migration_0018", path)
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
    assert module.down_revision == "0018_actual_harvest_import_staging"


def assert_actual_harvest_sqlite_upgrade_downgrade_upgrade() -> None:
    module = _migration_module()
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        module.op = Operations(MigrationContext.configure(connection))
        staging = _staging_migration_module()
        staging.op = module.op
        staging.upgrade()
        module.upgrade()
        inspector = sa.inspect(connection)
        assert set(inspector.get_table_names()) >= {
            "actual_harvest_import_batch",
            "actual_harvest_import_record",
            "actual_harvest_mapping_policy_registry",
            "actual_harvest_mapping_registry_entry",
            "actual_harvest_mapping_snapshot",
            "actual_harvest_validation_run",
            "actual_harvest_validation_attempt",
            "actual_harvest_validation_result",
            "actual_harvest_validation_record",
            "actual_harvest_validation_error",
            "actual_harvest_validation_lineage_node",
            "actual_harvest_validation_lineage_edge",
            "actual_harvest_validation_lineage_basis",
            "actual_harvest_validation_lineage_basis_member",
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

        connection.execute(
            sa.text(
                """
                INSERT INTO actual_harvest_mapping_policy_registry
                    (id, registry_version, source_system, mapping_policy_version,
                     status, entry_count, registry_content_hash)
                VALUES (1, 'registry-test-v1', 'source-test', 'mapping-test-v1',
                        'DRAFT', 1, NULL)
                """
            )
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO actual_harvest_mapping_registry_entry
                    (id, registry_id, source_field, source_code, target_type,
                     target_business_key, entry_hash)
                VALUES (1, 1, 'farm_code', 'farm-1', 'FARM', 'farm-business-key', :entry_hash)
                """
            ),
            {"entry_hash": "b" * 64},
        )
        connection.execute(
            sa.text(
                """
                UPDATE actual_harvest_mapping_policy_registry
                SET status = 'SEALED', entry_count = 1, registry_content_hash = :registry_hash
                WHERE id = 1
                """
            ),
            {"registry_hash": "a" * 64},
        )

        sealed_mutations = (
            "INSERT INTO actual_harvest_mapping_registry_entry "
            "(id, registry_id, source_field, source_code, target_type, "
            "target_business_key, entry_hash) "
            "VALUES (2, 1, 'farm_code', 'farm-2', 'FARM', 'farm-business-key-2', "
            "'" + "c" * 64 + "')",
            "UPDATE actual_harvest_mapping_registry_entry SET source_code = 'farm-2' WHERE id = 1",
            "DELETE FROM actual_harvest_mapping_registry_entry WHERE id = 1",
            "UPDATE actual_harvest_mapping_policy_registry SET status = 'DRAFT' WHERE id = 1",
            "DELETE FROM actual_harvest_mapping_policy_registry WHERE id = 1",
        )
        for statement in sealed_mutations:
            try:
                connection.execute(sa.text(statement))
            except sa.exc.IntegrityError:
                pass
            else:
                raise AssertionError("sealed mapping registry mutation was accepted")

        module.downgrade()
        staging.op = module.op
        staging.downgrade()
        assert set(sa.inspect(connection).get_table_names()) == set()

        staging.op = module.op
        staging.upgrade()
        module.upgrade()
        assert set(sa.inspect(connection).get_table_names()) >= {
            "actual_harvest_import_batch",
            "actual_harvest_import_record",
            "actual_harvest_validation_run",
        }


def assert_actual_harvest_migration_architecture_contract() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "JSON" not in source
    assert "parser" not in source.lower()
    assert "label_snapshot" not in source
    assert "commit_manifest" not in source
    assert "revision_graph" not in source
    assert "from backend.app" not in source
    assert "import backend.app" not in source
    assert "actual_harvest_validation_lineage_basis" in source
    assert "actual_harvest_validation_lineage_basis_member" in source
    assert "actual_harvest_validation_aggregation" not in source
    assert "active_label" not in source
    assert "cutoff" not in source.lower()
