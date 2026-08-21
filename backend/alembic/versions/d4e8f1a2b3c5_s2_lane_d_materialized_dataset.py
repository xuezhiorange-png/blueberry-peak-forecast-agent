"""Create append-only S2 Lane D materialized dataset tables.

Revision ID: d4e8f1a2b3c5
Revises: 8c6aead9f8e9
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d4e8f1a2b3c5"
down_revision = "8c6aead9f8e9"
branch_labels = None
depends_on = None

PARTITION_NAME_VALUES = ("TRAIN", "VALIDATION", "TEST")
QUALITY_GATE_STATUS_VALUES = ("ACCEPTED", "REJECTED")
REBUILD_HASH_REPLAY_STATUS_VALUES = ("PASS", "FAIL", "NOT_RUN")


def _sqlite_bigint() -> sa.types.TypeEngine:
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def _sha256_hex_check(column: str, *, nullable: bool = False) -> str:
    expression = column
    for character in "0123456789abcdef":
        expression = f"replace({expression}, '{character}', '')"
    valid = f"length({column}) = 64 AND lower({column}) = {column} AND length({expression}) = 0"
    return f"{column} IS NULL OR ({valid})" if nullable else valid


def _enum_check(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


def _create_lane_d_immutability_guard(table_name: str, message: str) -> None:
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


def _drop_lane_d_immutability_guard(table_name: str) -> None:
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
        "s2_materialized_dataset",
        sa.Column("id", _sqlite_bigint(), primary_key=True, autoincrement=True),
        sa.Column("dataset_id", sa.Text(), nullable=False),
        sa.Column("dataset_version", sa.Text(), nullable=False),
        sa.Column("materialized_dataset_identity_sha256", sa.Text(), nullable=False),
        sa.Column("source_cohort_id", sa.Text(), nullable=False),
        sa.Column("source_cohort_manifest_sha256", sa.Text(), nullable=False),
        sa.Column("raw_policy_version", sa.Text(), nullable=False),
        sa.Column("cleaning_policy_version", sa.Text(), nullable=False),
        sa.Column("correction_policy_version", sa.Text(), nullable=False),
        sa.Column("exclusion_policy_version", sa.Text(), nullable=False),
        sa.Column("visibility_policy_version", sa.Text(), nullable=False),
        sa.Column("revision_winner_policy_version", sa.Text(), nullable=False),
        sa.Column("cleaned_dataset_version_identity", sa.Text(), nullable=False),
        sa.Column("builder_version", sa.Text(), nullable=False),
        sa.Column("dataset_schema_version", sa.Text(), nullable=False),
        sa.Column("lineage_complete", sa.Boolean(), nullable=False),
        sa.Column("quality_gate_status", sa.Text(), nullable=False),
        sa.Column("build_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("build_completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("upstream_snapshot_sha256", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "materialized_dataset_identity_sha256",
            name="uq_s2_materialized_dataset_identity",
        ),
        sa.UniqueConstraint(
            "dataset_id",
            "dataset_version",
            name="uq_s2_materialized_dataset_version",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("materialized_dataset_identity_sha256"),
            name="ck_s2_materialized_dataset_identity",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("source_cohort_manifest_sha256"),
            name="ck_s2_materialized_dataset_cohort_manifest",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("upstream_snapshot_sha256"),
            name="ck_s2_materialized_dataset_upstream_snapshot",
        ),
        sa.CheckConstraint(
            _enum_check("quality_gate_status", QUALITY_GATE_STATUS_VALUES),
            name="ck_s2_materialized_dataset_quality_gate_status",
        ),
    )

    op.create_table(
        "s2_materialized_materializable_row",
        sa.Column("id", _sqlite_bigint(), primary_key=True, autoincrement=True),
        sa.Column(
            "materialized_dataset_id",
            _sqlite_bigint(),
            sa.ForeignKey("s2_materialized_dataset.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("row_sort_key", sa.Integer(), nullable=False),
        sa.Column("season", sa.Text(), nullable=False),
        sa.Column("farm", sa.Text(), nullable=False),
        sa.Column("subfarm", sa.Text(), nullable=False),
        sa.Column("variety", sa.Text(), nullable=False),
        sa.Column("harvest_business_date", sa.Date(), nullable=False),
        sa.Column("actual_harvest_quantity_kg", sa.Numeric(18, 6), nullable=False),
        sa.Column("source_row_identity", sa.Text(), nullable=False),
        sa.Column("cleaned_row_identity", sa.Text(), nullable=False),
        sa.Column("pit_visibility_identity", sa.Text(), nullable=False),
        sa.Column("revision_winner_identity", sa.Text(), nullable=False),
        sa.UniqueConstraint(
            "materialized_dataset_id",
            "row_sort_key",
            name="uq_s2_materialized_materializable_row_sort",
        ),
        sa.UniqueConstraint(
            "materialized_dataset_id",
            "cleaned_row_identity",
            name="uq_s2_materialized_materializable_row_identity",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("source_row_identity"),
            name="ck_s2_materialized_row_source_identity",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("cleaned_row_identity"),
            name="ck_s2_materialized_row_cleaned_identity",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("pit_visibility_identity"),
            name="ck_s2_materialized_row_pit_identity",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("revision_winner_identity"),
            name="ck_s2_materialized_row_revision_identity",
        ),
    )

    op.create_table(
        "s2_materialized_partition",
        sa.Column("id", _sqlite_bigint(), primary_key=True, autoincrement=True),
        sa.Column(
            "materialized_dataset_id",
            _sqlite_bigint(),
            sa.ForeignKey("s2_materialized_dataset.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("partition_name", sa.Text(), nullable=False),
        sa.Column("partition_start_date", sa.Date(), nullable=False),
        sa.Column("partition_end_date", sa.Date(), nullable=False),
        sa.Column("partition_date_field", sa.Text(), nullable=False),
        sa.Column("target_decision", sa.Text(), nullable=False),
        sa.Column("canonical_grain", sa.Text(), nullable=False),
        sa.Column("split_policy_version", sa.Text(), nullable=False),
        sa.Column("manifest_schema_version", sa.Text(), nullable=False),
        sa.Column("materialized_partition_schema_version", sa.Text(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("byte_count", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.Text(), nullable=False),
        sa.Column("partition_identity_sha256", sa.Text(), nullable=False),
        sa.Column("manifest_sha256", sa.Text(), nullable=False),
        sa.Column("content_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("lineage_complete", sa.Boolean(), nullable=False),
        sa.Column("quality_gate_status", sa.Text(), nullable=False),
        sa.Column("rebuild_hash_replay_status", sa.Text(), nullable=False),
        sa.UniqueConstraint(
            "materialized_dataset_id",
            "partition_name",
            name="uq_s2_materialized_partition_name",
        ),
        sa.UniqueConstraint(
            "manifest_sha256",
            name="uq_s2_materialized_partition_manifest_hash",
        ),
        sa.CheckConstraint(
            _enum_check("partition_name", PARTITION_NAME_VALUES),
            name="ck_s2_materialized_partition_name",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("content_sha256"),
            name="ck_s2_materialized_partition_content_sha256",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("partition_identity_sha256"),
            name="ck_s2_materialized_partition_identity_sha256",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("manifest_sha256"),
            name="ck_s2_materialized_partition_manifest_sha256",
        ),
        sa.CheckConstraint(
            _enum_check("quality_gate_status", QUALITY_GATE_STATUS_VALUES),
            name="ck_s2_materialized_partition_quality_gate_status",
        ),
        sa.CheckConstraint(
            _enum_check("rebuild_hash_replay_status", REBUILD_HASH_REPLAY_STATUS_VALUES),
            name="ck_s2_materialized_partition_rebuild_status",
        ),
        sa.CheckConstraint("row_count >= 0", name="ck_s2_materialized_partition_row_count"),
        sa.CheckConstraint("byte_count >= 0", name="ck_s2_materialized_partition_byte_count"),
    )

    for table_name in (
        "s2_materialized_dataset",
        "s2_materialized_materializable_row",
        "s2_materialized_partition",
    ):
        _create_lane_d_immutability_guard(
            table_name,
            f"{table_name} is append-only",
        )


def downgrade() -> None:
    for table_name in (
        "s2_materialized_partition",
        "s2_materialized_materializable_row",
        "s2_materialized_dataset",
    ):
        _drop_lane_d_immutability_guard(table_name)
    op.drop_table("s2_materialized_partition")
    op.drop_table("s2_materialized_materializable_row")
    op.drop_table("s2_materialized_dataset")
