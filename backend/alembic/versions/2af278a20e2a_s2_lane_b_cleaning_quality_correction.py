"""Create append-only S2 Lane B cleaned dataset, quality, and ledger tables.

Revision ID: 2af278a20e2a
Revises: 0029_s2_lane_a_raw_ingestion_lineage
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "2af278a20e2a"
down_revision = "0029_s2_lane_a_raw_ingestion_lineage"
branch_labels = None
depends_on = None

QUANTITY_PRESENCE_VALUES = ("KNOWN", "UNKNOWN_NOT_ZERO")
FINDING_SEVERITY_VALUES = ("ERROR", "WARNING")
FINDING_CODE_VALUES = (
    "MISSING_QUANTITY_UNKNOWN_NOT_ZERO",
    "DUPLICATE_CANONICAL_GRAIN",
)
EXCLUSION_CODE_VALUES = ("BUSINESS_EXCLUSION", "QUALITY_BLOCKED")


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


def _create_lane_b_immutability_guard(table_name: str, message: str) -> None:
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


def _drop_lane_b_immutability_guard(table_name: str) -> None:
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
        "s2_cleaned_dataset_version",
        sa.Column("id", _sqlite_bigint(), primary_key=True, autoincrement=True),
        sa.Column("cleaned_dataset_version_identity_hash", sa.Text(), nullable=False),
        sa.Column("cleaned_dataset_version_content_hash", sa.Text(), nullable=False),
        sa.Column("source_cohort_id", sa.Text(), nullable=False),
        sa.Column("mapping_registry_hash", sa.Text(), nullable=False),
        sa.Column("cleaning_policy_version", sa.Text(), nullable=False),
        sa.Column("quality_policy_version", sa.Text(), nullable=False),
        sa.Column("correction_policy_version", sa.Text(), nullable=False),
        sa.Column("exclusion_policy_version", sa.Text(), nullable=False),
        sa.Column("cleaned_schema_version", sa.Text(), nullable=False),
        sa.Column("quality_report_identity_hash", sa.Text(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("excluded_row_count", sa.Integer(), nullable=False),
        sa.Column("unknown_quantity_row_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "cleaned_dataset_version_identity_hash",
            name="uq_s2_cleaned_dataset_version_identity",
        ),
        sa.UniqueConstraint(
            "cleaned_dataset_version_content_hash",
            name="uq_s2_cleaned_dataset_version_content",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("cleaned_dataset_version_identity_hash"),
            name="ck_s2_cleaned_dataset_version_identity_hash",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("cleaned_dataset_version_content_hash"),
            name="ck_s2_cleaned_dataset_version_content_hash",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("mapping_registry_hash"),
            name="ck_s2_cleaned_dataset_mapping_registry_hash",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("quality_report_identity_hash"),
            name="ck_s2_cleaned_dataset_quality_report_hash",
        ),
    )

    op.create_table(
        "s2_cleaned_row",
        sa.Column("id", _sqlite_bigint(), primary_key=True, autoincrement=True),
        sa.Column("cleaned_dataset_version_id", _sqlite_bigint(), nullable=False),
        sa.Column("cleaned_row_identity_hash", sa.Text(), nullable=False),
        sa.Column("cleaned_row_content_hash", sa.Text(), nullable=False),
        sa.Column("source_row_identity_hash", sa.Text(), nullable=False),
        sa.Column("season_business_key", sa.Text(), nullable=False),
        sa.Column("farm_business_key", sa.Text(), nullable=False),
        sa.Column("subfarm_business_key", sa.Text(), nullable=False),
        sa.Column("variety_business_key", sa.Text(), nullable=False),
        sa.Column("harvest_business_date", sa.Date(), nullable=False),
        sa.Column("cleaning_projection_version", sa.Text(), nullable=False),
        sa.Column("cleaned_row_schema_version", sa.Text(), nullable=False),
        sa.Column("cleaning_policy_version", sa.Text(), nullable=False),
        sa.Column("correction_policy_version", sa.Text(), nullable=False),
        sa.Column("exclusion_policy_version", sa.Text(), nullable=False),
        sa.Column("source_actual_harvest_quantity_kg", sa.Numeric(18, 6), nullable=True),
        sa.Column("effective_actual_harvest_quantity_kg", sa.Numeric(18, 6), nullable=True),
        sa.Column("quantity_presence_status", sa.Text(), nullable=False),
        sa.Column("is_excluded", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["cleaned_dataset_version_id"],
            ["s2_cleaned_dataset_version.id"],
            name="fk_s2_cleaned_row_dataset_version",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "cleaned_dataset_version_id",
            "cleaned_row_identity_hash",
            name="uq_s2_cleaned_row_identity",
        ),
        sa.UniqueConstraint(
            "cleaned_dataset_version_id",
            "season_business_key",
            "farm_business_key",
            "subfarm_business_key",
            "variety_business_key",
            "harvest_business_date",
            name="uq_s2_cleaned_row_grain",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("cleaned_row_identity_hash"),
            name="ck_s2_cleaned_row_identity",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("cleaned_row_content_hash"),
            name="ck_s2_cleaned_row_content",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("source_row_identity_hash"),
            name="ck_s2_cleaned_row_source",
        ),
        sa.CheckConstraint(
            _enum_check("quantity_presence_status", QUANTITY_PRESENCE_VALUES),
            name="ck_s2_cleaned_row_quantity_presence",
        ),
        sa.CheckConstraint(
            (
                "(quantity_presence_status = 'UNKNOWN_NOT_ZERO' "
                "AND effective_actual_harvest_quantity_kg IS NULL) "
                "OR quantity_presence_status = 'KNOWN'"
            ),
            name="ck_s2_cleaned_row_unknown_not_zero",
        ),
    )

    op.create_table(
        "s2_quality_finding",
        sa.Column("id", _sqlite_bigint(), primary_key=True, autoincrement=True),
        sa.Column("cleaned_dataset_version_id", _sqlite_bigint(), nullable=False),
        sa.Column("quality_finding_identity_hash", sa.Text(), nullable=False),
        sa.Column("source_row_identity_hash", sa.Text(), nullable=False),
        sa.Column("cleaned_row_identity_hash", sa.Text(), nullable=True),
        sa.Column("quality_rule_id", sa.Text(), nullable=False),
        sa.Column("quality_rule_version", sa.Text(), nullable=False),
        sa.Column("observed_field", sa.Text(), nullable=False),
        sa.Column("finding_code", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("normalized_observed_value_identity", sa.Text(), nullable=False),
        sa.Column("rule_definition_hash", sa.Text(), nullable=False),
        sa.Column("validation_run_identity", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["cleaned_dataset_version_id"],
            ["s2_cleaned_dataset_version.id"],
            name="fk_s2_quality_finding_dataset_version",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "cleaned_dataset_version_id",
            "quality_finding_identity_hash",
            name="uq_s2_quality_finding_identity",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("quality_finding_identity_hash"),
            name="ck_s2_quality_finding_identity",
        ),
        sa.CheckConstraint(
            _enum_check("severity", FINDING_SEVERITY_VALUES),
            name="ck_s2_quality_finding_severity",
        ),
        sa.CheckConstraint(
            _enum_check("finding_code", FINDING_CODE_VALUES),
            name="ck_s2_quality_finding_code",
        ),
    )

    op.create_table(
        "s2_correction_ledger_entry",
        sa.Column("id", _sqlite_bigint(), primary_key=True, autoincrement=True),
        sa.Column("cleaned_dataset_version_id", _sqlite_bigint(), nullable=False),
        sa.Column("correction_ledger_entry_identity_hash", sa.Text(), nullable=False),
        sa.Column("source_row_identity_hash", sa.Text(), nullable=False),
        sa.Column("correction_event_id", sa.Text(), nullable=False),
        sa.Column("field_name", sa.Text(), nullable=False),
        sa.Column("correction_policy_version", sa.Text(), nullable=False),
        sa.Column("correction_schema_version", sa.Text(), nullable=False),
        sa.Column("quality_finding_identity_hash", sa.Text(), nullable=True),
        sa.Column("original_value_digest", sa.Text(), nullable=False),
        sa.Column("corrected_value_digest", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("manual_actor_or_authority_reference", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["cleaned_dataset_version_id"],
            ["s2_cleaned_dataset_version.id"],
            name="fk_s2_correction_ledger_dataset_version",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "cleaned_dataset_version_id",
            "correction_ledger_entry_identity_hash",
            name="uq_s2_correction_ledger_identity",
        ),
        sa.UniqueConstraint(
            "cleaned_dataset_version_id",
            "correction_event_id",
            name="uq_s2_correction_ledger_event",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("correction_ledger_entry_identity_hash"),
            name="ck_s2_correction_ledger_identity",
        ),
    )

    op.create_table(
        "s2_exclusion_ledger_entry",
        sa.Column("id", _sqlite_bigint(), primary_key=True, autoincrement=True),
        sa.Column("cleaned_dataset_version_id", _sqlite_bigint(), nullable=False),
        sa.Column("exclusion_ledger_entry_identity_hash", sa.Text(), nullable=False),
        sa.Column("source_row_identity_hash", sa.Text(), nullable=False),
        sa.Column("exclusion_event_id", sa.Text(), nullable=False),
        sa.Column("exclusion_code", sa.Text(), nullable=False),
        sa.Column("exclusion_policy_version", sa.Text(), nullable=False),
        sa.Column("exclusion_schema_version", sa.Text(), nullable=False),
        sa.Column("quality_finding_identity_hash", sa.Text(), nullable=True),
        sa.Column("exclusion_reason_reference", sa.Text(), nullable=False),
        sa.Column("decision_authority_reference", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["cleaned_dataset_version_id"],
            ["s2_cleaned_dataset_version.id"],
            name="fk_s2_exclusion_ledger_dataset_version",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "cleaned_dataset_version_id",
            "exclusion_ledger_entry_identity_hash",
            name="uq_s2_exclusion_ledger_identity",
        ),
        sa.UniqueConstraint(
            "cleaned_dataset_version_id",
            "source_row_identity_hash",
            name="uq_s2_exclusion_ledger_row",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("exclusion_ledger_entry_identity_hash"),
            name="ck_s2_exclusion_ledger_identity",
        ),
        sa.CheckConstraint(
            _enum_check("exclusion_code", EXCLUSION_CODE_VALUES),
            name="ck_s2_exclusion_ledger_code",
        ),
    )

    for table_name, message in (
        ("s2_cleaned_dataset_version", "s2 cleaned dataset version is immutable"),
        ("s2_cleaned_row", "s2 cleaned row is immutable"),
        ("s2_quality_finding", "s2 quality finding is immutable"),
        ("s2_correction_ledger_entry", "s2 correction ledger entry is immutable"),
        ("s2_exclusion_ledger_entry", "s2 exclusion ledger entry is immutable"),
    ):
        _create_lane_b_immutability_guard(table_name, message)


def downgrade() -> None:
    for table_name in (
        "s2_exclusion_ledger_entry",
        "s2_correction_ledger_entry",
        "s2_quality_finding",
        "s2_cleaned_row",
        "s2_cleaned_dataset_version",
    ):
        _drop_lane_b_immutability_guard(table_name)
    op.drop_table("s2_exclusion_ledger_entry")
    op.drop_table("s2_correction_ledger_entry")
    op.drop_table("s2_quality_finding")
    op.drop_table("s2_cleaned_row")
    op.drop_table("s2_cleaned_dataset_version")
