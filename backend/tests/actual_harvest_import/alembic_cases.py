from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_VERSIONS_DIR = _BACKEND_ROOT / "alembic" / "versions"

MIGRATION_PATH = _ALEMBIC_VERSIONS_DIR / "0021_actual_harvest_label_snapshot.py"
MIGRATION_REVISION = "0021_actual_harvest_label_snapshot"
MIGRATION_0022_PATH = _ALEMBIC_VERSIONS_DIR / "0022_finalized_at_lineage_basis_member.py"
MIGRATION_0022_REVISION = "0022_finalized_at_lineage_basis_member"
MIGRATION_0023_PATH = _ALEMBIC_VERSIONS_DIR / "0023_historical_backtest_binding.py"
MIGRATION_0023_REVISION = "0023_historical_backtest_binding"
MIGRATION_0024_PATH = _ALEMBIC_VERSIONS_DIR / "0024_s3_forecast_quality_persistence.py"
MIGRATION_0024_REVISION = "0024_s3_forecast_quality_persistence"


def _migration_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("actual_harvest_migration_0020", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _previous_migration_module() -> ModuleType:
    path = _ALEMBIC_VERSIONS_DIR / "0020_actual_harvest_commit_manifest.py"
    spec = importlib.util.spec_from_file_location("actual_harvest_migration_0020", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _validation_migration_module() -> ModuleType:
    path = _ALEMBIC_VERSIONS_DIR / "0019_actual_harvest_validation_evidence.py"
    spec = importlib.util.spec_from_file_location("actual_harvest_migration_0019", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _staging_migration_module() -> ModuleType:
    path = _ALEMBIC_VERSIONS_DIR / "0018_actual_harvest_import_staging.py"
    spec = importlib.util.spec_from_file_location("actual_harvest_migration_0018", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def assert_actual_harvest_alembic_head_and_revision_contract() -> None:
    config = Config(str(_BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND_ROOT / "alembic"))
    script = ScriptDirectory.from_config(config)
    # 0022 remains the I7 lineage parent for finalized_at, 0023 remains the
    # S2 historical binding extension, and 0024 is the current unique head.
    heads = script.get_heads()
    assert len(heads) == 1, f"alembic heads must be exactly one, got {heads!r}"
    assert heads == [MIGRATION_0024_REVISION], (
        f"alembic heads must be [{MIGRATION_0024_REVISION!r}], got {heads!r}"
    )
    module = _migration_module()
    assert module.revision == MIGRATION_REVISION
    assert module.down_revision == "0020_actual_harvest_commit_manifest"
    spec = importlib.util.spec_from_file_location(
        "actual_harvest_migration_0022", MIGRATION_0022_PATH
    )
    assert spec is not None and spec.loader is not None
    migration_0022 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration_0022)
    assert migration_0022.revision == MIGRATION_0022_REVISION
    assert migration_0022.down_revision == MIGRATION_REVISION
    spec_0023 = importlib.util.spec_from_file_location(
        "actual_harvest_migration_0023", MIGRATION_0023_PATH
    )
    assert spec_0023 is not None and spec_0023.loader is not None
    migration_0023 = importlib.util.module_from_spec(spec_0023)
    spec_0023.loader.exec_module(migration_0023)
    assert migration_0023.revision == MIGRATION_0023_REVISION
    assert migration_0023.down_revision == MIGRATION_0022_REVISION
    spec_0024 = importlib.util.spec_from_file_location(
        "actual_harvest_migration_0024", MIGRATION_0024_PATH
    )
    assert spec_0024 is not None and spec_0024.loader is not None
    migration_0024 = importlib.util.module_from_spec(spec_0024)
    spec_0024.loader.exec_module(migration_0024)
    assert migration_0024.revision == MIGRATION_0024_REVISION
    assert migration_0024.down_revision == MIGRATION_0023_REVISION


def assert_actual_harvest_sqlite_upgrade_downgrade_upgrade() -> None:
    module = _migration_module()
    previous = _previous_migration_module()
    spec_0022 = importlib.util.spec_from_file_location(
        "actual_harvest_migration_0022", MIGRATION_0022_PATH
    )
    assert spec_0022 is not None and spec_0022.loader is not None
    migration_0022 = importlib.util.module_from_spec(spec_0022)
    spec_0022.loader.exec_module(migration_0022)
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        module.op = Operations(MigrationContext.configure(connection))
        staging = _staging_migration_module()
        staging.op = module.op
        staging.upgrade()
        validation = _validation_migration_module()
        validation.op = module.op
        validation.upgrade()
        previous.op = module.op
        previous.upgrade()
        module.upgrade()
        migration_0022.op = module.op
        migration_0022.upgrade()
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
            "actual_harvest_commit_manifest",
            "actual_harvest_label_snapshot",
            "actual_harvest_label_snapshot_winner",
            "actual_harvest_label_snapshot_label",
            "actual_harvest_label_snapshot_exclusion",
        }
        assert set(inspector.get_table_names()) == expected_tables
        assert {
            column["name"] for column in inspector.get_columns("actual_harvest_import_record")
        } >= {
            "actual_harvest_quantity_kg",
            "source_system",
            "external_batch_id",
        }
        assert {
            column["name"] for column in inspector.get_columns("actual_harvest_mapping_snapshot")
        } >= {"season_resolver_version"}
        assert {
            column["name"] for column in inspector.get_columns("actual_harvest_validation_run")
        } >= {"season_resolver_version"}
        assert {
            column["name"] for column in inspector.get_columns("actual_harvest_validation_result")
        } >= {"season_resolver_version"}
        assert {
            column["name"]
            for column in inspector.get_columns("actual_harvest_validation_mapping_evidence")
        } >= {"resolver_version"}
        # I7 follow-up contract: the lineage basis member table must
        # carry the committed FINALIZED predecessor's finalized_at as a
        # nullable timezone-aware timestamp so subsequent validations
        # (and contract tests) can read it back. See migration 0022.
        assert {
            column["name"]
            for column in inspector.get_columns("actual_harvest_validation_lineage_basis_member")
        } >= {
            "source_system",
            "source_recorded_at",
            "source_recorded_at_authority_status",
            "finalized_at",
            "member_sort_key",
            "member_hash",
        }
        # S1 commit_manifest column contract.
        commit_manifest_columns = {
            column["name"] for column in inspector.get_columns("actual_harvest_commit_manifest")
        }
        expected_commit_manifest_columns = {
            "id",
            "batch_id",
            "validation_run_id",
            "commit_policy_version",
            "validation_run_instance_identity_hash",
            "commit_manifest_hash",
            "seal_manifest_hash",
            "canonical_batch_hash",
            "record_manifest_hash",
            "validation_result_hash",
            "mapping_snapshot_hash",
            "resolved_identity_snapshot_hash",
            "lineage_graph_hash",
            "committed_lineage_basis_hash",
            "registry_content_hash",
            "source_semantics_attestation_hash",
            "committed_record_count",
            "committed_by_identity",
            "committed_at",
        }
        assert commit_manifest_columns == expected_commit_manifest_columns
        # S1 commit_manifest unique constraint contract.
        commit_manifest_unique = {
            constraint["name"]
            for constraint in inspector.get_unique_constraints("actual_harvest_commit_manifest")
        }
        assert commit_manifest_unique == {
            "uq_actual_harvest_commit_manifest_batch",
            "uq_actual_harvest_commit_manifest_validation_run",
            "uq_actual_harvest_commit_manifest_hash",
        }
        # S1 commit_manifest foreign key contract.
        commit_manifest_fks = {
            fk["name"] for fk in inspector.get_foreign_keys("actual_harvest_commit_manifest")
        }
        assert commit_manifest_fks == {
            "fk_actual_harvest_commit_manifest_batch",
            "fk_actual_harvest_commit_manifest_validation_run",
        }
        # S1 commit_manifest check constraint contract.
        commit_manifest_checks = {
            check["name"]
            for check in inspector.get_check_constraints("actual_harvest_commit_manifest")
        }
        for required_check in (
            "ck_actual_harvest_commit_manifest_count_nonneg",
            "ck_actual_harvest_commit_manifest_instance_hash",
            "ck_actual_harvest_commit_manifest_hash",
            "ck_actual_harvest_commit_manifest_seal_hash",
            "ck_actual_harvest_commit_manifest_canonical_batch_hash",
            "ck_actual_harvest_commit_manifest_record_manifest_hash",
            "ck_actual_harvest_commit_manifest_validation_result_hash",
            "ck_actual_harvest_commit_manifest_mapping_snapshot_hash",
            "ck_actual_harvest_commit_manifest_resolved_identity_hash",
            "ck_actual_harvest_commit_manifest_lineage_graph_hash",
            "ck_actual_harvest_commit_manifest_lineage_basis_hash",
            "ck_actual_harvest_commit_manifest_registry_hash",
            "ck_actual_harvest_commit_manifest_attestation_hash",
        ):
            assert required_check in commit_manifest_checks, required_check
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
        expected_indexes = {
            "actual_harvest_mapping_registry_entry": {
                "ix_actual_harvest_mapping_entry_lookup": (
                    False,
                    ["registry_id", "source_field", "source_code"],
                ),
            },
            "actual_harvest_validation_run": {
                "ix_actual_harvest_validation_run_current": (False, ["batch_id", "is_current"]),
                "uq_actual_harvest_validation_run_current": (True, ["batch_id"]),
            },
            "actual_harvest_validation_record": {
                "ix_actual_harvest_validation_record_page": (
                    False,
                    ["validation_run_id", "record_index"],
                ),
            },
            "actual_harvest_validation_mapping_evidence": {
                "ix_actual_harvest_validation_mapping_evidence_record": (
                    False,
                    ["validation_run_id", "record_index"],
                ),
            },
            "actual_harvest_validation_error": {
                "ix_actual_harvest_validation_error_page": (
                    False,
                    ["validation_run_id", "sort_key"],
                ),
            },
            "actual_harvest_validation_lineage_basis_member": {
                "ix_actual_harvest_validation_basis_member_sort": (
                    False,
                    ["basis_id", "member_sort_key"],
                ),
            },
            "actual_harvest_commit_manifest": {},
        }
        for table_name, expected_table_indexes in expected_indexes.items():
            actual_table_indexes = {
                index["name"]: index for index in inspector.get_indexes(table_name)
            }
            assert set(actual_table_indexes) == set(expected_table_indexes)
            for index_name, (unique, columns) in expected_table_indexes.items():
                actual = actual_table_indexes[index_name]
                assert bool(actual["unique"]) is unique
                assert actual["column_names"] == columns
                if index_name == "uq_actual_harvest_validation_run_current":
                    where = actual.get("dialect_options", {}).get("sqlite_where")
                    assert str(where).replace(" ", "") == "is_current=1"
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
            "actual_harvest_commit_manifest": {
                "fk_actual_harvest_commit_manifest_batch",
                "fk_actual_harvest_commit_manifest_validation_run",
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
            "actual_harvest_commit_manifest": {
                "uq_actual_harvest_commit_manifest_batch",
                "uq_actual_harvest_commit_manifest_validation_run",
                "uq_actual_harvest_commit_manifest_hash",
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
            "actual_harvest_commit_manifest": {
                "ck_actual_harvest_commit_manifest_count_nonneg",
                "ck_actual_harvest_commit_manifest_instance_hash",
                "ck_actual_harvest_commit_manifest_hash",
                "ck_actual_harvest_commit_manifest_seal_hash",
                "ck_actual_harvest_commit_manifest_canonical_batch_hash",
                "ck_actual_harvest_commit_manifest_record_manifest_hash",
                "ck_actual_harvest_commit_manifest_validation_result_hash",
                "ck_actual_harvest_commit_manifest_mapping_snapshot_hash",
                "ck_actual_harvest_commit_manifest_resolved_identity_hash",
                "ck_actual_harvest_commit_manifest_lineage_graph_hash",
                "ck_actual_harvest_commit_manifest_lineage_basis_hash",
                "ck_actual_harvest_commit_manifest_registry_hash",
                "ck_actual_harvest_commit_manifest_attestation_hash",
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

        # S1 commit_manifest immutability is enforced by the
        # `trg_actual_harvest_commit_manifest_immutable` SQLite trigger
        # (and the PostgreSQL equivalent) created in 0020 upgrade. Trigger
        # existence is verified by the SQLite upgrade path above; runtime
        # UPDATE/DELETE rejection is covered by the unit/contract tests in
        # `tests/actual_harvest_import/test_commit_contract.py`.

        # B5 contract: the import-record immutability guard must reject
        # UPDATE/DELETE on a record whose parent batch is sealed. The
        # SQLite upgrade path installs the BEFORE UPDATE/DELETE triggers
        # that the PostgreSQL DDL emits; this part proves the SQLite
        # branch produces the same observable contract: any UPDATE or
        # DELETE on a row whose parent batch is in {SEALED, VALIDATING,
        # VALIDATED, COMMITTED} must raise, while UPLOADING rows are
        # still mutable.
        # First, plant a UPLOADING batch + record so the WHEN clause
        # has something to inspect.
        connection.execute(
            sa.text(
                """
                INSERT INTO actual_harvest_import_batch
                    (id, import_id, import_channel, source_system, source_dataset,
                     source_version, external_batch_id, idempotency_key, submitted_at,
                     import_received_at, ingested_at, submitted_by_identity,
                     record_count, valid_record_count, invalid_record_count,
                     committed_record_count, raw_payload_hash, schema_version,
                     mapping_policy_version, validation_policy_version,
                     source_semantics_attestation_version,
                     source_semantics_physical_event,
                     source_semantics_quantity_basis,
                     source_semantics_quantity_unit,
                     source_semantics_missing_record_semantics,
                     source_semantics_attestation_hash, status, seal_status,
                     uploaded_record_count)
                VALUES (1, 'upload-test', 'api', 'source-test', 'ds', 'v1',
                        'ext-upload-1', 'idem-upload-1', '2024-01-01 00:00:00',
                        '2024-01-01 00:00:00', '2024-01-01 00:00:00',
                        'op-1', 1, 0, 0, 0, '"""
                + "a" * 64
                + """',
                        'schema-v1', 'mapping-v1', 'validation-v1',
                        'att-v1', 'FARM_PICK', 'OBSERVED_WEIGHT', 'KG',
                        'UNKNOWN_NOT_ZERO', '"""
                + "a" * 64
                + """',
                        'UPLOADING', 'UNSEALED', 1)
                """
            )
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO actual_harvest_import_record
                    (id, batch_id, external_logical_record_id, external_revision_id,
                     source_system, external_batch_id, harvest_business_date,
                     farm_code, subfarm_or_plot_code, variety_code,
                     actual_harvest_quantity_kg, source_recorded_at,
                     source_recorded_at_authority_status,
                     import_received_at, ingested_at, revision_number,
                     record_status)
                VALUES (1, 1, 'log-1', 'rev-1', 'source-test',
                        'ext-upload-1', '2024-01-01', 'farm-1', 'sub-1', 'var-1',
                        1.0, '2024-01-01 00:00:00', 'TRUSTED_SOURCE_TIMESTAMP',
                        '2024-01-01 00:00:00', '2024-01-01 00:00:00', 1,
                        'ACTIVE')
                """
            )
        )
        # UPLOADING allows mutation (B5 must not block the legitimate
        # append/cancel/append-again path).
        connection.execute(
            sa.text(
                "UPDATE actual_harvest_import_record "
                "SET actual_harvest_quantity_kg = 2.0 WHERE id = 1"
            )
        )
        # Now promote the batch to VALIDATED and assert the guard fires.
        connection.execute(
            sa.text("UPDATE actual_harvest_import_batch SET status = 'VALIDATED' WHERE id = 1")
        )
        sealed_record_mutations = (
            (
                "UPDATE actual_harvest_import_record "
                "SET actual_harvest_quantity_kg = 3.0 WHERE id = 1"
            ),
            "DELETE FROM actual_harvest_import_record WHERE id = 1",
        )
        for statement in sealed_record_mutations:
            try:
                connection.execute(sa.text(statement))
            except sa.exc.IntegrityError:
                pass
            else:
                raise AssertionError("sealed import-record mutation was accepted by the B5 trigger")

        module.downgrade()
        migration_0022.op = module.op
        migration_0022.downgrade()
        previous.op = module.op
        previous.downgrade()
        validation.op = module.op
        validation.downgrade()
        staging.op = module.op
        staging.downgrade()
        assert set(sa.inspect(connection).get_table_names()) == set()

        staging.op = module.op
        staging.upgrade()
        validation.op = module.op
        validation.upgrade()
        previous.op = module.op
        previous.upgrade()
        module.upgrade()
        migration_0022.op = module.op
        migration_0022.upgrade()
        assert set(sa.inspect(connection).get_table_names()) == expected_tables


def assert_actual_harvest_migration_architecture_contract() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    module = _migration_module()
    # Forbidden content (must not bleed into the I7 migration).
    assert "JSON" not in source
    assert "parser" not in source.lower()
    assert "label_snapshot" in source
    assert "commit_manifest" in source
    assert "revision_graph" not in source
    assert "from backend.app" not in source
    assert "import backend.app" not in source
    # I7 contract: header / winner / label / exclusion policy versions
    # must be the fixed constants so on-disk hashes are reproducible.
    assert module.SNAPSHOT_POLICY_VERSION == "actual-harvest-label-snapshot-policy-v1"
    assert module.WINNER_POLICY_VERSION == "actual-harvest-label-winner-policy-v1"
    assert module.AGGREGATION_POLICY_VERSION == "actual-harvest-label-aggregation-policy-v1"
    assert module.REQUEST_HASH_POLICY_VERSION == "actual-harvest-label-request-hash-v1"
    assert module.INSTANCE_HASH_POLICY_VERSION == "actual-harvest-label-instance-hash-v1"
    assert module.SNAPSHOT_HASH_POLICY_VERSION == "actual-harvest-label-snapshot-hash-v1"
    # I7 contract: no background-worker / lease / heartbeat / fencing /
    # attempt-ledger forbidden tokens. The S1 commit layer established
    # the same rules; 0021 must not re-introduce them.
    assert "COMMITTING" not in source
    assert "COMMIT_FAILED" not in source
    assert "ATTEMPT_LEDGER" not in source
    assert "LEASE" not in source
    assert "HEARTBEAT" not in source
    assert "FENCING" not in source
    # Architecture string rules.
    assert "actual_harvest_validation_lineage_basis" not in source
    assert "actual_harvest_validation_lineage_basis_member" not in source
    assert "actual_harvest_validation_aggregation" not in source
    assert "active_label" not in source
    # I7 contract: ``cutoff`` is a legal identifier for the I7 snapshot
    # header; do not assert it is absent.
