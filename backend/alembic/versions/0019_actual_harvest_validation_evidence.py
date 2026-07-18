"""Add immutable actual-harvest validation and lineage evidence.

Revision ID: 0019_actual_harvest_validation_evidence
Revises: 0018_actual_harvest_import_staging
"""

from __future__ import annotations

from collections.abc import Iterable

import sqlalchemy as sa
from alembic import op

revision = "0019_actual_harvest_validation_evidence"
down_revision = "0018_actual_harvest_import_staging"
branch_labels = None
depends_on = None


def _bigint() -> sa.types.TypeEngine:
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def _enum_check(column: str, values: Iterable[str]) -> str:
    quoted = ", ".join("'" + value + "'" for value in values)
    return f"{column} IN ({quoted})"


def _sha_check(column: str, *, nullable: bool = False) -> str:
    expression = column
    for character in "0123456789abcdef":
        expression = f"replace({expression}, '{character}', '')"
    valid = f"length({column}) = 64 AND lower({column}) = {column} AND length({expression}) = 0"
    return f"{column} IS NULL OR ({valid})" if nullable else valid


def _create_mapping_registry_immutability_guards() -> None:
    """Prevent direct writes to a sealed registry and its entries."""
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            sa.text(
                """
                CREATE FUNCTION actual_harvest_reject_sealed_registry_mutation()
                RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    IF OLD.status = 'SEALED' THEN
                        RAISE EXCEPTION 'sealed mapping registry is immutable'
                            USING ERRCODE = 'check_violation';
                    END IF;
                    IF TG_OP = 'DELETE' THEN
                        RETURN OLD;
                    END IF;
                    RETURN NEW;
                END;
                $$;
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_actual_harvest_sealed_registry_immutable
                BEFORE UPDATE OR DELETE
                ON actual_harvest_mapping_policy_registry
                FOR EACH ROW
                EXECUTE FUNCTION actual_harvest_reject_sealed_registry_mutation()
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE FUNCTION actual_harvest_reject_sealed_registry_entry_mutation()
                RETURNS trigger LANGUAGE plpgsql AS $$
                DECLARE
                    sealed_count integer;
                BEGIN
                    IF TG_OP = 'INSERT' THEN
                        SELECT count(*) INTO sealed_count
                        FROM actual_harvest_mapping_policy_registry
                        WHERE id = NEW.registry_id AND status = 'SEALED';
                    ELSIF TG_OP = 'UPDATE' THEN
                        SELECT count(*) INTO sealed_count
                        FROM actual_harvest_mapping_policy_registry
                        WHERE id IN (OLD.registry_id, NEW.registry_id)
                        AND status = 'SEALED';
                    ELSE
                        SELECT count(*) INTO sealed_count
                        FROM actual_harvest_mapping_policy_registry
                        WHERE id = OLD.registry_id AND status = 'SEALED';
                    END IF;
                    IF sealed_count > 0 THEN
                        RAISE EXCEPTION 'sealed mapping registry entries are immutable'
                            USING ERRCODE = 'check_violation';
                    END IF;
                    IF TG_OP = 'DELETE' THEN
                        RETURN OLD;
                    END IF;
                    RETURN NEW;
                END;
                $$
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_actual_harvest_sealed_registry_entry_immutable
                BEFORE INSERT OR UPDATE OR DELETE
                ON actual_harvest_mapping_registry_entry
                FOR EACH ROW
                EXECUTE FUNCTION actual_harvest_reject_sealed_registry_entry_mutation()
                """
            )
        )
        return

    if dialect == "sqlite":
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_actual_harvest_sealed_registry_immutable_update
                BEFORE UPDATE ON actual_harvest_mapping_policy_registry
                WHEN OLD.status = 'SEALED'
                BEGIN
                    SELECT RAISE(ABORT, 'sealed mapping registry is immutable');
                END;
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_actual_harvest_sealed_registry_immutable_delete
                BEFORE DELETE ON actual_harvest_mapping_policy_registry
                WHEN OLD.status = 'SEALED'
                BEGIN
                    SELECT RAISE(ABORT, 'sealed mapping registry is immutable');
                END;
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_actual_harvest_sealed_registry_entry_immutable_insert
                BEFORE INSERT ON actual_harvest_mapping_registry_entry
                WHEN EXISTS (
                    SELECT 1
                    FROM actual_harvest_mapping_policy_registry
                    WHERE id = NEW.registry_id AND status = 'SEALED'
                )
                BEGIN
                    SELECT RAISE(ABORT, 'sealed mapping registry entries are immutable');
                END;
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_actual_harvest_sealed_registry_entry_immutable_update
                BEFORE UPDATE ON actual_harvest_mapping_registry_entry
                WHEN EXISTS (
                    SELECT 1
                    FROM actual_harvest_mapping_policy_registry
                    WHERE id IN (OLD.registry_id, NEW.registry_id) AND status = 'SEALED'
                )
                BEGIN
                    SELECT RAISE(ABORT, 'sealed mapping registry entries are immutable');
                END;
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_actual_harvest_sealed_registry_entry_immutable_delete
                BEFORE DELETE ON actual_harvest_mapping_registry_entry
                WHEN EXISTS (
                    SELECT 1
                    FROM actual_harvest_mapping_policy_registry
                    WHERE id = OLD.registry_id AND status = 'SEALED'
                )
                BEGIN
                    SELECT RAISE(ABORT, 'sealed mapping registry entries are immutable');
                END;
                """
            )
        )


def _drop_mapping_registry_immutability_guards() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            sa.text(
                """
                DROP TRIGGER IF EXISTS trg_actual_harvest_sealed_registry_entry_immutable
                    ON actual_harvest_mapping_registry_entry
                """
            )
        )
        op.execute(
            sa.text(
                """
                DROP TRIGGER IF EXISTS trg_actual_harvest_sealed_registry_immutable
                    ON actual_harvest_mapping_policy_registry
                """
            )
        )
        op.execute(
            sa.text(
                "DROP FUNCTION IF EXISTS actual_harvest_reject_sealed_registry_entry_mutation()"
            )
        )
        op.execute(
            sa.text("DROP FUNCTION IF EXISTS actual_harvest_reject_sealed_registry_mutation()")
        )
    elif dialect == "sqlite":
        for trigger in (
            "trg_actual_harvest_sealed_registry_immutable_update",
            "trg_actual_harvest_sealed_registry_immutable_delete",
            "trg_actual_harvest_sealed_registry_entry_immutable_insert",
            "trg_actual_harvest_sealed_registry_entry_immutable_update",
            "trg_actual_harvest_sealed_registry_entry_immutable_delete",
        ):
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger}"))


def upgrade() -> None:
    op.create_table(
        "actual_harvest_mapping_policy_registry",
        sa.Column("id", _bigint(), primary_key=True, autoincrement=True),
        sa.Column("registry_version", sa.Text(), nullable=False),
        sa.Column("source_system", sa.Text(), nullable=False),
        sa.Column("mapping_policy_version", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("entry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("registry_content_hash", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("sealed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("registry_version", name="uq_actual_harvest_mapping_registry_version"),
        sa.UniqueConstraint(
            "mapping_policy_version", name="uq_actual_harvest_mapping_policy_version"
        ),
        sa.CheckConstraint(
            _enum_check("status", ("DRAFT", "SEALED")),
            name="ck_actual_harvest_mapping_registry_status",
        ),
        sa.CheckConstraint("entry_count >= 0", name="ck_actual_harvest_mapping_entry_count"),
        sa.CheckConstraint(
            _sha_check("registry_content_hash", nullable=True),
            name="ck_actual_harvest_mapping_registry_hash",
        ),
    )
    op.create_table(
        "actual_harvest_mapping_registry_entry",
        sa.Column("id", _bigint(), primary_key=True, autoincrement=True),
        sa.Column("registry_id", _bigint(), nullable=False),
        sa.Column("source_field", sa.Text(), nullable=False),
        sa.Column("source_code", sa.Text(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("target_business_key", sa.Text(), nullable=False),
        sa.Column("target_parent_business_key", sa.Text(), nullable=True),
        sa.Column("farm_timezone", sa.Text(), nullable=True),
        sa.Column("entry_hash", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["registry_id"],
            ["actual_harvest_mapping_policy_registry.id"],
            name="fk_actual_harvest_mapping_entry_registry",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "registry_id",
            "source_field",
            "source_code",
            name="uq_actual_harvest_mapping_entry_source",
        ),
        sa.CheckConstraint(
            _enum_check("target_type", ("SEASON", "FARM", "SUBFARM", "VARIETY")),
            name="ck_actual_harvest_mapping_entry_target_type",
        ),
        sa.CheckConstraint(_sha_check("entry_hash"), name="ck_actual_harvest_mapping_entry_hash"),
    )
    op.create_index(
        "ix_actual_harvest_mapping_entry_lookup",
        "actual_harvest_mapping_registry_entry",
        ["registry_id", "source_field", "source_code"],
    )
    op.create_table(
        "actual_harvest_validation_run",
        sa.Column("id", _bigint(), primary_key=True, autoincrement=True),
        sa.Column("batch_id", _bigint(), nullable=False),
        sa.Column("request_identity_hash", sa.Text(), nullable=False),
        sa.Column("instance_identity_hash", sa.Text(), nullable=False),
        sa.Column("seal_manifest_hash", sa.Text(), nullable=False),
        sa.Column("mapping_policy_version", sa.Text(), nullable=False),
        sa.Column("validation_policy_version", sa.Text(), nullable=False),
        sa.Column("committed_lineage_basis_hash", sa.Text(), nullable=False),
        sa.Column("registry_content_hash", sa.Text(), nullable=False),
        sa.Column("record_manifest_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active_attempt_id", sa.Text(), nullable=True),
        sa.Column("active_attempt_generation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lineage_graph_hash", sa.Text(), nullable=True),
        sa.Column("validation_result_hash", sa.Text(), nullable=True),
        sa.Column("mapping_snapshot_hash", sa.Text(), nullable=True),
        sa.Column("valid_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("invalid_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warning_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["actual_harvest_import_batch.id"],
            name="fk_actual_harvest_validation_run_batch",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "batch_id", "instance_identity_hash", name="uq_actual_harvest_validation_run_instance"
        ),
        sa.CheckConstraint(
            _enum_check("status", ("VALIDATING", "VALIDATED", "VALIDATION_FAILED")),
            name="ck_actual_harvest_validation_run_status",
        ),
        sa.CheckConstraint(
            _sha_check("request_identity_hash"), name="ck_actual_harvest_validation_request_hash"
        ),
        sa.CheckConstraint(
            _sha_check("instance_identity_hash"), name="ck_actual_harvest_validation_instance_hash"
        ),
        sa.CheckConstraint(
            _sha_check("seal_manifest_hash"), name="ck_actual_harvest_validation_seal_hash"
        ),
        sa.CheckConstraint(
            _sha_check("committed_lineage_basis_hash"),
            name="ck_actual_harvest_validation_basis_hash",
        ),
        sa.CheckConstraint(
            _sha_check("registry_content_hash"), name="ck_actual_harvest_validation_registry_hash"
        ),
        sa.CheckConstraint(
            _sha_check("record_manifest_hash"),
            name="ck_actual_harvest_validation_record_manifest_hash",
        ),
        sa.CheckConstraint(
            _sha_check("lineage_graph_hash", nullable=True),
            name="ck_actual_harvest_validation_lineage_hash",
        ),
        sa.CheckConstraint(
            _sha_check("validation_result_hash", nullable=True),
            name="ck_actual_harvest_validation_result_hash",
        ),
        sa.CheckConstraint(
            _sha_check("mapping_snapshot_hash", nullable=True),
            name="ck_actual_harvest_validation_snapshot_hash",
        ),
    )
    op.create_index(
        "ix_actual_harvest_validation_run_current",
        "actual_harvest_validation_run",
        ["batch_id", "is_current"],
    )
    op.create_index(
        "uq_actual_harvest_validation_run_current",
        "actual_harvest_validation_run",
        ["batch_id"],
        unique=True,
        postgresql_where=sa.text("is_current = true"),
        sqlite_where=sa.text("is_current = 1"),
    )
    op.create_table(
        "actual_harvest_validation_attempt",
        sa.Column("id", _bigint(), primary_key=True, autoincrement=True),
        sa.Column("validation_run_id", _bigint(), nullable=False),
        sa.Column("attempt_id", sa.Text(), nullable=False),
        sa.Column("attempt_generation", sa.Integer(), nullable=False),
        sa.Column("fencing_token", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("abandoned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["validation_run_id"],
            ["actual_harvest_validation_run.id"],
            name="fk_actual_harvest_validation_attempt_run",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("attempt_id", name="uq_actual_harvest_validation_attempt_id"),
        sa.UniqueConstraint(
            "validation_run_id",
            "attempt_generation",
            name="uq_actual_harvest_validation_attempt_generation",
        ),
        sa.CheckConstraint(
            _enum_check("status", ("ACTIVE", "ABANDONED", "STALE", "COMPLETED")),
            name="ck_actual_harvest_validation_attempt_status",
        ),
    )
    op.create_table(
        "actual_harvest_mapping_snapshot",
        sa.Column("id", _bigint(), primary_key=True, autoincrement=True),
        sa.Column("validation_run_id", _bigint(), nullable=False),
        sa.Column("registry_version", sa.Text(), nullable=False),
        sa.Column("mapping_policy_version", sa.Text(), nullable=False),
        sa.Column("registry_content_hash", sa.Text(), nullable=False),
        sa.Column("mapping_snapshot_hash", sa.Text(), nullable=False),
        sa.Column("entry_count", sa.Integer(), nullable=False),
        sa.Column("snapshot_payload", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["validation_run_id"],
            ["actual_harvest_validation_run.id"],
            name="fk_actual_harvest_mapping_snapshot_run",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("validation_run_id", name="uq_actual_harvest_mapping_snapshot_run"),
        sa.CheckConstraint(
            _sha_check("registry_content_hash"), name="ck_actual_harvest_snapshot_registry_hash"
        ),
        sa.CheckConstraint(
            _sha_check("mapping_snapshot_hash"), name="ck_actual_harvest_snapshot_hash"
        ),
    )
    op.create_table(
        "actual_harvest_validation_result",
        sa.Column("id", _bigint(), primary_key=True, autoincrement=True),
        sa.Column("validation_run_id", _bigint(), nullable=False),
        sa.Column("validation_result_hash", sa.Text(), nullable=False),
        sa.Column("lineage_graph_hash", sa.Text(), nullable=False),
        sa.Column("committed_lineage_basis_hash", sa.Text(), nullable=False),
        sa.Column("mapping_snapshot_hash", sa.Text(), nullable=False),
        sa.Column("valid_count", sa.Integer(), nullable=False),
        sa.Column("invalid_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("warning_count", sa.Integer(), nullable=False),
        sa.Column("result_payload", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["validation_run_id"],
            ["actual_harvest_validation_run.id"],
            name="fk_actual_harvest_validation_result_run",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("validation_run_id", name="uq_actual_harvest_validation_result_run"),
        sa.CheckConstraint(
            _sha_check("validation_result_hash"),
            name="ck_actual_harvest_validation_result_hash_row",
        ),
        sa.CheckConstraint(
            _sha_check("lineage_graph_hash"),
            name="ck_actual_harvest_validation_result_lineage_hash",
        ),
        sa.CheckConstraint(
            _sha_check("committed_lineage_basis_hash"),
            name="ck_actual_harvest_validation_result_basis_hash",
        ),
        sa.CheckConstraint(
            _sha_check("mapping_snapshot_hash"),
            name="ck_actual_harvest_validation_result_snapshot_hash",
        ),
    )
    common_run_fk = sa.ForeignKeyConstraint(
        ["validation_run_id"], ["actual_harvest_validation_run.id"], ondelete="RESTRICT"
    )
    op.create_table(
        "actual_harvest_validation_record",
        sa.Column("id", _bigint(), primary_key=True, autoincrement=True),
        sa.Column("validation_run_id", _bigint(), nullable=False),
        sa.Column("origin", sa.Text(), nullable=False),
        sa.Column("record_index", sa.Integer(), nullable=False),
        sa.Column("source_system", sa.Text(), nullable=False),
        sa.Column("external_logical_record_id", sa.Text(), nullable=False),
        sa.Column("external_revision_id", sa.Text(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("canonical_record_hash", sa.Text(), nullable=False),
        sa.Column("mapping_outcome", sa.Text(), nullable=False),
        sa.Column("is_valid", sa.Boolean(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        common_run_fk,
        sa.UniqueConstraint(
            "validation_run_id",
            "origin",
            "source_system",
            "external_revision_id",
            name="uq_actual_harvest_validation_record_key",
        ),
        sa.CheckConstraint(
            _enum_check("origin", ("CURRENT_BATCH_REVISION", "COMMITTED_HISTORY_REVISION")),
            name="ck_actual_harvest_validation_record_origin",
        ),
        sa.CheckConstraint(
            _sha_check("canonical_record_hash"), name="ck_actual_harvest_validation_record_hash"
        ),
    )
    op.create_index(
        "ix_actual_harvest_validation_record_page",
        "actual_harvest_validation_record",
        ["validation_run_id", "record_index"],
    )
    op.create_table(
        "actual_harvest_validation_error",
        sa.Column("id", _bigint(), primary_key=True, autoincrement=True),
        sa.Column("validation_run_id", _bigint(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("error_code", sa.Text(), nullable=False),
        sa.Column("record_index", sa.Integer(), nullable=True),
        sa.Column("external_logical_record_id", sa.Text(), nullable=True),
        sa.Column("external_revision_id", sa.Text(), nullable=True),
        sa.Column("field_path", sa.Text(), nullable=True),
        sa.Column("message_template_id", sa.Text(), nullable=False),
        sa.Column("sanitized_details", sa.Text(), nullable=False),
        sa.Column("sort_key", sa.Text(), nullable=False),
        sa.Column("error_hash", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["validation_run_id"],
            ["actual_harvest_validation_run.id"],
            name="fk_actual_harvest_validation_error_run",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "validation_run_id", "error_hash", name="uq_actual_harvest_validation_error_hash"
        ),
    )
    op.create_index(
        "ix_actual_harvest_validation_error_page",
        "actual_harvest_validation_error",
        ["validation_run_id", "sort_key"],
    )
    op.create_table(
        "actual_harvest_validation_lineage_node",
        sa.Column("id", _bigint(), primary_key=True, autoincrement=True),
        sa.Column("validation_run_id", _bigint(), nullable=False),
        sa.Column("origin", sa.Text(), nullable=False),
        sa.Column("source_system", sa.Text(), nullable=False),
        sa.Column("external_logical_record_id", sa.Text(), nullable=False),
        sa.Column("external_revision_id", sa.Text(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("record_status", sa.Text(), nullable=False),
        sa.Column("supersedes_external_revision_id", sa.Text(), nullable=True),
        sa.Column("canonical_record_hash", sa.Text(), nullable=False),
        sa.Column("source_recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_recorded_at_authority_status", sa.Text(), nullable=False),
        sa.Column("node_hash", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["validation_run_id"],
            ["actual_harvest_validation_run.id"],
            name="fk_actual_harvest_validation_node_run",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "validation_run_id",
            "source_system",
            "external_revision_id",
            name="uq_actual_harvest_validation_node_key",
        ),
        sa.CheckConstraint(
            _enum_check("origin", ("CURRENT_BATCH_REVISION", "COMMITTED_HISTORY_REVISION")),
            name="ck_actual_harvest_validation_node_origin",
        ),
        sa.CheckConstraint(
            _sha_check("canonical_record_hash"),
            name="ck_actual_harvest_validation_node_record_hash",
        ),
        sa.CheckConstraint(_sha_check("node_hash"), name="ck_actual_harvest_validation_node_hash"),
    )
    op.create_table(
        "actual_harvest_validation_lineage_edge",
        sa.Column("id", _bigint(), primary_key=True, autoincrement=True),
        sa.Column("validation_run_id", _bigint(), nullable=False),
        sa.Column("source_system", sa.Text(), nullable=False),
        sa.Column("predecessor_revision_id", sa.Text(), nullable=False),
        sa.Column("successor_revision_id", sa.Text(), nullable=False),
        sa.Column("edge_type", sa.Text(), nullable=False),
        sa.Column("edge_hash", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["validation_run_id"],
            ["actual_harvest_validation_run.id"],
            name="fk_actual_harvest_validation_edge_run",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "validation_run_id",
            "source_system",
            "predecessor_revision_id",
            "successor_revision_id",
            name="uq_actual_harvest_validation_edge_key",
        ),
        sa.CheckConstraint(_sha_check("edge_hash"), name="ck_actual_harvest_validation_edge_hash"),
    )
    op.create_table(
        "actual_harvest_validation_lineage_basis",
        sa.Column("id", _bigint(), primary_key=True, autoincrement=True),
        sa.Column("validation_run_id", _bigint(), nullable=False),
        sa.Column("source_system", sa.Text(), nullable=False),
        sa.Column("authority_policy_version", sa.Text(), nullable=False),
        sa.Column("committed_lineage_basis_hash", sa.Text(), nullable=False),
        sa.Column("member_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["validation_run_id"],
            ["actual_harvest_validation_run.id"],
            name="fk_actual_harvest_validation_basis_run",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("validation_run_id", name="uq_actual_harvest_validation_basis_run"),
        sa.CheckConstraint(
            _sha_check("committed_lineage_basis_hash"),
            name="ck_actual_harvest_validation_basis_hash_row",
        ),
    )
    op.create_table(
        "actual_harvest_validation_lineage_basis_member",
        sa.Column("id", _bigint(), primary_key=True, autoincrement=True),
        sa.Column("basis_id", _bigint(), nullable=False),
        sa.Column("source_system", sa.Text(), nullable=False),
        sa.Column("committed_batch_ref", sa.Text(), nullable=False),
        sa.Column("external_logical_record_id", sa.Text(), nullable=False),
        sa.Column("external_revision_id", sa.Text(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("canonical_record_hash", sa.Text(), nullable=False),
        sa.Column("predecessor_revision_id", sa.Text(), nullable=True),
        sa.Column("record_status", sa.Text(), nullable=False),
        sa.Column("source_recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_recorded_at_authority_status", sa.Text(), nullable=False),
        sa.Column("member_sort_key", sa.Text(), nullable=False),
        sa.Column("member_hash", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["basis_id"],
            ["actual_harvest_validation_lineage_basis.id"],
            name="fk_actual_harvest_validation_basis_member_basis",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "basis_id",
            "source_system",
            "external_revision_id",
            name="uq_actual_harvest_validation_basis_member_key",
        ),
        sa.CheckConstraint(
            _sha_check("canonical_record_hash"),
            name="ck_actual_harvest_validation_basis_member_record_hash",
        ),
        sa.CheckConstraint(
            _sha_check("member_hash"), name="ck_actual_harvest_validation_basis_member_hash"
        ),
    )
    op.create_index(
        "ix_actual_harvest_validation_basis_member_sort",
        "actual_harvest_validation_lineage_basis_member",
        ["basis_id", "member_sort_key"],
    )
    _create_mapping_registry_immutability_guards()


def downgrade() -> None:
    _drop_mapping_registry_immutability_guards()
    op.drop_index(
        "ix_actual_harvest_validation_basis_member_sort",
        table_name="actual_harvest_validation_lineage_basis_member",
    )
    op.drop_table("actual_harvest_validation_lineage_basis_member")
    op.drop_table("actual_harvest_validation_lineage_basis")
    op.drop_table("actual_harvest_validation_lineage_edge")
    op.drop_table("actual_harvest_validation_lineage_node")
    op.drop_index(
        "ix_actual_harvest_validation_error_page", table_name="actual_harvest_validation_error"
    )
    op.drop_table("actual_harvest_validation_error")
    op.drop_index(
        "ix_actual_harvest_validation_record_page", table_name="actual_harvest_validation_record"
    )
    op.drop_table("actual_harvest_validation_record")
    op.drop_table("actual_harvest_validation_result")
    op.drop_table("actual_harvest_mapping_snapshot")
    op.drop_table("actual_harvest_validation_attempt")
    op.drop_index(
        "uq_actual_harvest_validation_run_current", table_name="actual_harvest_validation_run"
    )
    op.drop_index(
        "ix_actual_harvest_validation_run_current", table_name="actual_harvest_validation_run"
    )
    op.drop_table("actual_harvest_validation_run")
    op.drop_index(
        "ix_actual_harvest_mapping_entry_lookup", table_name="actual_harvest_mapping_registry_entry"
    )
    op.drop_table("actual_harvest_mapping_registry_entry")
    op.drop_table("actual_harvest_mapping_policy_registry")
