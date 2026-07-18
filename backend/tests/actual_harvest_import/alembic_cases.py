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
        expected_tables = {
            "actual_harvest_import_batch",
            "actual_harvest_import_record",
            "actual_harvest_mapping_policy_registry",
            "actual_harvest_mapping_registry_entry",
            "actual_harvest_mapping_snapshot",
            "actual_harvest_validation_run",
            "actual_harvest_validation_attempt",
            "actual_harvest_validation_result",
            "actual_harvest_validation_record",
            "actual_harvest_validation_mapping_evidence",
            "actual_harvest_validation_error",
            "actual_harvest_validation_lineage_node",
            "actual_harvest_validation_lineage_edge",
            "actual_harvest_validation_lineage_basis",
            "actual_harvest_validation_lineage_basis_member",
        }
        assert set(inspector.get_table_names()) == expected_tables
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
        assert {
            index["name"] for index in inspector.get_indexes("actual_harvest_validation_run")
        } == {
            "ix_actual_harvest_validation_run_current",
            "uq_actual_harvest_validation_run_current",
        }
        assert {
            index["name"]
            for index in inspector.get_indexes("actual_harvest_validation_mapping_evidence")
        } == {"ix_actual_harvest_validation_mapping_evidence_record"}
        assert {
            constraint["name"]
            for constraint in inspector.get_check_constraints(
                "actual_harvest_validation_mapping_evidence"
            )
        } == {
            "ck_actual_harvest_validation_mapping_entry_hash",
            "ck_actual_harvest_validation_resolved_master_hash",
            "ck_actual_harvest_validation_mapping_target_type",
            "ck_actual_harvest_validation_mapping_target_fk",
        }
        for table_name in expected_tables:
            for foreign_key in inspector.get_foreign_keys(table_name):
                assert foreign_key["options"].get("ondelete") == "RESTRICT"

        expected_foreign_keys = {
            "actual_harvest_mapping_registry_entry": {"fk_actual_harvest_mapping_entry_registry"},
            "actual_harvest_validation_run": {"fk_actual_harvest_validation_run_batch"},
            "actual_harvest_validation_attempt": {"fk_actual_harvest_validation_attempt_run"},
            "actual_harvest_mapping_snapshot": {"fk_actual_harvest_mapping_snapshot_run"},
            "actual_harvest_validation_result": {"fk_actual_harvest_validation_result_run"},
            "actual_harvest_validation_record": {"fk_actual_harvest_validation_record_run"},
            "actual_harvest_validation_mapping_evidence": {
                "fk_actual_harvest_validation_mapping_evidence_run",
                "fk_actual_harvest_mapping_evidence_season",
                "fk_actual_harvest_mapping_evidence_farm",
                "fk_actual_harvest_mapping_evidence_subfarm",
                "fk_actual_harvest_mapping_evidence_variety",
            },
            "actual_harvest_validation_error": {"fk_actual_harvest_validation_error_run"},
            "actual_harvest_validation_lineage_node": {"fk_actual_harvest_validation_node_run"},
            "actual_harvest_validation_lineage_edge": {"fk_actual_harvest_validation_edge_run"},
            "actual_harvest_validation_lineage_basis": {"fk_actual_harvest_validation_basis_run"},
            "actual_harvest_validation_lineage_basis_member": {
                "fk_actual_harvest_validation_basis_member_basis"
            },
        }
        for table_name, expected_names in expected_foreign_keys.items():
            assert {
                foreign_key["name"] for foreign_key in inspector.get_foreign_keys(table_name)
            } == expected_names

        expected_unique_constraints = {
            "actual_harvest_mapping_policy_registry": {
                "uq_actual_harvest_mapping_registry_version",
                "uq_actual_harvest_mapping_policy_version",
            },
            "actual_harvest_mapping_registry_entry": {"uq_actual_harvest_mapping_entry_source"},
            "actual_harvest_validation_run": {"uq_actual_harvest_validation_run_instance"},
            "actual_harvest_validation_attempt": {
                "uq_actual_harvest_validation_attempt_id",
                "uq_actual_harvest_validation_attempt_generation",
            },
            "actual_harvest_mapping_snapshot": {"uq_actual_harvest_mapping_snapshot_run"},
            "actual_harvest_validation_result": {"uq_actual_harvest_validation_result_run"},
            "actual_harvest_validation_record": {"uq_actual_harvest_validation_record_key"},
            "actual_harvest_validation_mapping_evidence": {
                "uq_actual_harvest_validation_mapping_evidence_field"
            },
            "actual_harvest_validation_error": {"uq_actual_harvest_validation_error_hash"},
            "actual_harvest_validation_lineage_node": {"uq_actual_harvest_validation_node_key"},
            "actual_harvest_validation_lineage_edge": {"uq_actual_harvest_validation_edge_key"},
            "actual_harvest_validation_lineage_basis": {"uq_actual_harvest_validation_basis_run"},
            "actual_harvest_validation_lineage_basis_member": {
                "uq_actual_harvest_validation_basis_member_key"
            },
        }
        for table_name, expected_names in expected_unique_constraints.items():
            assert {
                constraint["name"] for constraint in inspector.get_unique_constraints(table_name)
            } == expected_names

        expected_checks = {
            "actual_harvest_mapping_policy_registry": {
                "ck_actual_harvest_mapping_registry_status",
                "ck_actual_harvest_mapping_entry_count",
                "ck_actual_harvest_mapping_registry_hash",
            },
            "actual_harvest_mapping_registry_entry": {
                "ck_actual_harvest_mapping_entry_target_type",
                "ck_actual_harvest_mapping_entry_hash",
            },
            "actual_harvest_validation_run": {
                "ck_actual_harvest_validation_run_status",
                "ck_actual_harvest_validation_request_hash",
                "ck_actual_harvest_validation_instance_hash",
                "ck_actual_harvest_validation_seal_hash",
                "ck_actual_harvest_validation_basis_hash",
                "ck_actual_harvest_validation_registry_hash",
                "ck_actual_harvest_validation_record_manifest_hash",
                "ck_actual_harvest_validation_lineage_hash",
                "ck_actual_harvest_validation_result_hash",
                "ck_actual_harvest_validation_snapshot_hash",
                "ck_actual_harvest_validation_resolved_identity_hash",
            },
            "actual_harvest_validation_attempt": {"ck_actual_harvest_validation_attempt_status"},
            "actual_harvest_mapping_snapshot": {
                "ck_actual_harvest_snapshot_registry_hash",
                "ck_actual_harvest_snapshot_hash",
                "ck_actual_harvest_snapshot_resolved_identity_hash",
            },
            "actual_harvest_validation_result": {
                "ck_actual_harvest_validation_result_hash_row",
                "ck_actual_harvest_validation_result_lineage_hash",
                "ck_actual_harvest_validation_result_basis_hash",
                "ck_actual_harvest_validation_result_snapshot_hash",
                "ck_actual_harvest_validation_result_resolved_identity_hash",
            },
            "actual_harvest_validation_record": {
                "ck_actual_harvest_validation_record_origin",
                "ck_actual_harvest_validation_record_hash",
            },
            "actual_harvest_validation_mapping_evidence": {
                "ck_actual_harvest_validation_mapping_entry_hash",
                "ck_actual_harvest_validation_resolved_master_hash",
                "ck_actual_harvest_validation_mapping_target_type",
                "ck_actual_harvest_validation_mapping_target_fk",
            },
            "actual_harvest_validation_lineage_node": {
                "ck_actual_harvest_validation_node_origin",
                "ck_actual_harvest_validation_node_record_hash",
                "ck_actual_harvest_validation_node_hash",
            },
            "actual_harvest_validation_lineage_edge": {"ck_actual_harvest_validation_edge_hash"},
            "actual_harvest_validation_lineage_basis": {
                "ck_actual_harvest_validation_basis_hash_row"
            },
            "actual_harvest_validation_lineage_basis_member": {
                "ck_actual_harvest_validation_basis_member_record_hash",
                "ck_actual_harvest_validation_basis_member_hash",
            },
        }
        for table_name, expected_names in expected_checks.items():
            assert {
                constraint["name"] for constraint in inspector.get_check_constraints(table_name)
            } == expected_names

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
        assert set(sa.inspect(connection).get_table_names()) == expected_tables


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
    assert module.RECORD_STATUS_VALUES == ("ACTIVE", "CORRECTED", "VOID", "FINALIZED")
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
    assert "actual_harvest_validation_lineage_basis" in source
    assert "actual_harvest_validation_lineage_basis_member" in source
    assert "actual_harvest_validation_aggregation" not in source
    assert "active_label" not in source
    assert "cutoff" not in source.lower()
