"""Create append-only S2 Lane A raw ingestion and lineage tables.

Revision ID: 0029_s2_lane_a_raw_ingestion_lineage
Revises: 0028_quality_child_hash_scope
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0029_s2_lane_a_raw_ingestion_lineage"
down_revision = "0028_quality_child_hash_scope"
branch_labels = None
depends_on = None


def _sqlite_bigint() -> sa.types.TypeEngine:
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def _sha256_hex_check(column: str, *, nullable: bool = False) -> str:
    expression = column
    for character in "0123456789abcdef":
        expression = f"replace({expression}, '{character}', '')"
    valid = f"length({column}) = 64 AND lower({column}) = {column} AND length({expression}) = 0"
    return f"{column} IS NULL OR ({valid})" if nullable else valid


def _create_lane_a_immutability_guard(table_name: str, message: str) -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        function_name = f"s2_reject_{table_name}_mutation"
        op.execute(
            sa.text(
                f"""
                CREATE FUNCTION {function_name}()
                RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    RAISE EXCEPTION '{message}'
                        USING ERRCODE = '23514';
                END;
                $$;
                """
            )
        )
        op.execute(
            sa.text(
                f"""
                CREATE TRIGGER trg_{table_name}_immutable
                BEFORE UPDATE OR DELETE
                ON {table_name}
                FOR EACH ROW
                EXECUTE FUNCTION {function_name}()
                """
            )
        )
        return

    if dialect == "sqlite":
        op.execute(
            sa.text(
                f"""
                CREATE TRIGGER trg_{table_name}_immutable_update
                BEFORE UPDATE ON {table_name}
                BEGIN
                    SELECT RAISE(ABORT, '{message}');
                END;
                """
            )
        )
        op.execute(
            sa.text(
                f"""
                CREATE TRIGGER trg_{table_name}_immutable_delete
                BEFORE DELETE ON {table_name}
                BEGIN
                    SELECT RAISE(ABORT, '{message}');
                END;
                """
            )
        )


def _drop_lane_a_immutability_guard(table_name: str) -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS trg_{table_name}_immutable ON {table_name}"))
        op.execute(sa.text(f"DROP FUNCTION IF EXISTS s2_reject_{table_name}_mutation()"))
        return
    if dialect == "sqlite":
        for trigger in (
            f"trg_{table_name}_immutable_update",
            f"trg_{table_name}_immutable_delete",
        ):
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger}"))


def upgrade() -> None:
    op.create_table(
        "s2_raw_source_artifact",
        sa.Column("id", _sqlite_bigint(), primary_key=True, autoincrement=True),
        sa.Column("source_artifact_identity_hash", sa.Text(), nullable=False),
        sa.Column("source_artifact_sha256", sa.Text(), nullable=False),
        sa.Column("source_system", sa.Text(), nullable=False),
        sa.Column("source_dataset", sa.Text(), nullable=False),
        sa.Column("source_version", sa.Text(), nullable=False),
        sa.Column("source_snapshot_reference", sa.Text(), nullable=False),
        sa.Column("source_object_identity", sa.Text(), nullable=False),
        sa.Column("source_artifact_sequence", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("mapping_policy_version", sa.Text(), nullable=False),
        sa.Column("source_artifact_identity_version", sa.Text(), nullable=False),
        sa.Column("source_owner_attestation", sa.Text(), nullable=False),
        sa.Column("cohort_manifest_reference", sa.Text(), nullable=False),
        sa.Column("custody_record_reference", sa.Text(), nullable=False),
        sa.Column("storage_locator_hash", sa.Text(), nullable=False),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "source_artifact_sequence >= 1",
            name="ck_s2_raw_source_artifact_sequence_positive",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("source_artifact_identity_hash"),
            name="ck_s2_raw_source_artifact_identity_hash",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("source_artifact_sha256"),
            name="ck_s2_raw_source_artifact_sha256",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("storage_locator_hash"),
            name="ck_s2_raw_source_artifact_storage_locator_hash",
        ),
        sa.UniqueConstraint(
            "source_artifact_identity_hash",
            name="uq_s2_raw_source_artifact_identity_hash",
        ),
    )

    op.create_table(
        "s2_raw_import_batch",
        sa.Column("id", _sqlite_bigint(), primary_key=True, autoincrement=True),
        sa.Column("raw_import_batch_identity_hash", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.Text(), nullable=False),
        sa.Column("raw_source_artifact_identity_hash", sa.Text(), nullable=False),
        sa.Column("external_batch_id", sa.Text(), nullable=False),
        sa.Column("source_system", sa.Text(), nullable=False),
        sa.Column("source_dataset", sa.Text(), nullable=False),
        sa.Column("raw_payload_hash", sa.Text(), nullable=False),
        sa.Column("import_policy_version", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("mapping_policy_version", sa.Text(), nullable=False),
        sa.Column("validation_policy_version", sa.Text(), nullable=False),
        sa.Column("source_cohort_id", sa.Text(), nullable=False),
        sa.Column("import_request_identity", sa.Text(), nullable=False),
        sa.Column("source_row_count", sa.Integer(), nullable=False),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("source_row_count >= 0", name="ck_s2_raw_import_batch_row_count"),
        sa.CheckConstraint(
            _sha256_hex_check("raw_import_batch_identity_hash"),
            name="ck_s2_raw_import_batch_identity_hash",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("content_sha256"),
            name="ck_s2_raw_import_batch_content_sha256",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("raw_source_artifact_identity_hash"),
            name="ck_s2_raw_import_batch_source_artifact_hash",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("raw_payload_hash"),
            name="ck_s2_raw_import_batch_raw_payload_hash",
        ),
        sa.ForeignKeyConstraint(
            ["raw_source_artifact_identity_hash"],
            ["s2_raw_source_artifact.source_artifact_identity_hash"],
            name="fk_s2_raw_import_batch_source_artifact",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "raw_import_batch_identity_hash",
            name="uq_s2_raw_import_batch_identity_hash",
        ),
        sa.UniqueConstraint(
            "raw_source_artifact_identity_hash",
            "source_system",
            "external_batch_id",
            name="uq_s2_raw_import_batch_external_identity",
        ),
    )

    op.create_table(
        "s2_source_row_lineage",
        sa.Column("id", _sqlite_bigint(), primary_key=True, autoincrement=True),
        sa.Column("source_row_identity_hash", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.Text(), nullable=False),
        sa.Column("raw_source_artifact_identity_hash", sa.Text(), nullable=False),
        sa.Column("raw_import_batch_identity_hash", sa.Text(), nullable=False),
        sa.Column("external_logical_record_id", sa.Text(), nullable=False),
        sa.Column("external_revision_id", sa.Text(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("source_system", sa.Text(), nullable=False),
        sa.Column("source_version", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("source_row_identity_version", sa.Text(), nullable=False),
        sa.Column("source_sheet_name", sa.Text(), nullable=True),
        sa.Column("source_row_number", sa.Integer(), nullable=True),
        sa.Column("source_column_mapping_snapshot_hash", sa.Text(), nullable=False),
        sa.Column(
            "winner_selection_blocked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "revision_number >= 1",
            name="ck_s2_source_row_lineage_revision_positive",
        ),
        sa.CheckConstraint(
            "source_row_number IS NULL OR source_row_number >= 1",
            name="ck_s2_source_row_lineage_row_number_positive",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("source_row_identity_hash"),
            name="ck_s2_source_row_lineage_identity_hash",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("content_sha256"),
            name="ck_s2_source_row_lineage_content_sha256",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("source_column_mapping_snapshot_hash"),
            name="ck_s2_source_row_lineage_mapping_snapshot_hash",
        ),
        sa.ForeignKeyConstraint(
            ["raw_source_artifact_identity_hash"],
            ["s2_raw_source_artifact.source_artifact_identity_hash"],
            name="fk_s2_source_row_lineage_source_artifact",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["raw_import_batch_identity_hash"],
            ["s2_raw_import_batch.raw_import_batch_identity_hash"],
            name="fk_s2_source_row_lineage_import_batch",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "source_row_identity_hash",
            name="uq_s2_source_row_lineage_identity_hash",
        ),
    )

    for table_name, message in (
        ("s2_raw_source_artifact", "s2 raw source artifact is immutable"),
        ("s2_raw_import_batch", "s2 raw import batch is immutable"),
        ("s2_source_row_lineage", "s2 source row lineage is immutable"),
    ):
        _create_lane_a_immutability_guard(table_name, message)


def downgrade() -> None:
    for table_name in (
        "s2_source_row_lineage",
        "s2_raw_import_batch",
        "s2_raw_source_artifact",
    ):
        _drop_lane_a_immutability_guard(table_name)
    op.drop_table("s2_source_row_lineage")
    op.drop_table("s2_raw_import_batch")
    op.drop_table("s2_raw_source_artifact")
