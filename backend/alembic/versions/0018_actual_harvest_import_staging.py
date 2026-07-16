"""Create append-only actual-harvest staging tables.

Revision ID: 0018_actual_harvest_import_staging
Revises: 0017_core_forecast_run_persistence
"""

from __future__ import annotations

from collections.abc import Iterable

import sqlalchemy as sa
from alembic import op

revision = "0018_actual_harvest_import_staging"
down_revision = "0017_core_forecast_run_persistence"
branch_labels = None
depends_on = None

IMPORT_CHANNEL_VALUES = ("api", "csv", "xlsx")
PHYSICAL_EVENT_VALUES = ("FARM_PICK",)
QUANTITY_BASIS_VALUES = ("OBSERVED_WEIGHT",)
QUANTITY_UNIT_VALUES = ("KG",)
MISSING_RECORD_SEMANTICS_VALUES = ("UNKNOWN_NOT_ZERO",)

RECORD_STATUS_VALUES = (
    "ACTIVE",
    "CORRECTED",
    "VOID",
    "FINALIZED",
)

SOURCE_RECORDED_AT_AUTHORITY_VALUES = (
    "TRUSTED_SOURCE_TIMESTAMP",
    "USER_ASSERTED_UNVERIFIED",
    "MISSING",
    "CONFLICTING",
)

BATCH_STATUS_VALUES = (
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

BATCH_SEAL_STATUS_VALUES = (
    "UNSEALED",
    "SEALED",
)


def _sqlite_bigint() -> sa.types.TypeEngine:
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def _quoted_values(values: Iterable[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _enum_check(column: str, values: Iterable[str]) -> str:
    return f"{column} IN ({_quoted_values(values)})"


def _sha256_hex_check(column: str, *, nullable: bool) -> str:
    expression = column
    for character in "0123456789abcdef":
        expression = f"replace({expression}, '{character}', '')"
    valid = f"length({column}) = 64 AND lower({column}) = {column} AND length({expression}) = 0"
    return f"{column} IS NULL OR ({valid})" if nullable else valid


def upgrade() -> None:
    op.create_table(
        "actual_harvest_import_batch",
        sa.Column("id", _sqlite_bigint(), primary_key=True, autoincrement=True),
        sa.Column("import_id", sa.Text(), nullable=False),
        sa.Column("import_channel", sa.Text(), nullable=False),
        sa.Column("source_system", sa.Text(), nullable=False),
        sa.Column("source_dataset", sa.Text(), nullable=False),
        sa.Column("source_version", sa.Text(), nullable=False),
        sa.Column("external_batch_id", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("import_received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_by_identity", sa.Text(), nullable=False),
        sa.Column("expected_record_count_or_null", sa.Integer(), nullable=True),
        sa.Column("uploaded_record_count", sa.Integer(), nullable=False),
        sa.Column("sealed_record_count_or_null", sa.Integer(), nullable=True),
        sa.Column("sealed_at_or_null", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sealed_by_identity_or_null", sa.Text(), nullable=True),
        sa.Column("seal_status", sa.Text(), nullable=False),
        sa.Column("server_raw_payload_hash_or_null", sa.Text(), nullable=True),
        sa.Column("canonical_batch_hash_or_null", sa.Text(), nullable=True),
        sa.Column("seal_manifest_hash_or_null", sa.Text(), nullable=True),
        sa.Column("source_file_name_or_null", sa.Text(), nullable=True),
        sa.Column("source_file_hash_or_null", sa.Text(), nullable=True),
        sa.Column("raw_payload_hash", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("mapping_policy_version", sa.Text(), nullable=False),
        sa.Column("validation_policy_version", sa.Text(), nullable=False),
        sa.Column("source_semantics_attestation_version", sa.Text(), nullable=False),
        sa.Column("source_semantics_physical_event", sa.Text(), nullable=False),
        sa.Column("source_semantics_quantity_basis", sa.Text(), nullable=False),
        sa.Column("source_semantics_quantity_unit", sa.Text(), nullable=False),
        sa.Column("source_semantics_missing_record_semantics", sa.Text(), nullable=False),
        sa.Column("source_semantics_attestation_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("valid_record_count", sa.Integer(), nullable=False),
        sa.Column("invalid_record_count", sa.Integer(), nullable=False),
        sa.Column("committed_record_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("validated_at_or_null", sa.DateTime(timezone=True), nullable=True),
        sa.Column("committed_at_or_null", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("import_id", name="uq_actual_harvest_import_batch_import_id"),
        sa.UniqueConstraint(
            "source_system",
            "external_batch_id",
            name="uq_actual_harvest_import_batch_source_external",
        ),
        sa.UniqueConstraint(
            "source_system",
            "idempotency_key",
            name="uq_actual_harvest_import_batch_source_idempotency",
        ),
        sa.UniqueConstraint(
            "id",
            "source_system",
            "external_batch_id",
            name="uq_actual_harvest_import_batch_composite_parent",
        ),
        sa.CheckConstraint(
            "length(trim(import_id)) > 0",
            name="ck_actual_harvest_batch_import_id_nonempty",
        ),
        sa.CheckConstraint(
            _enum_check("import_channel", IMPORT_CHANNEL_VALUES),
            name="ck_actual_harvest_batch_import_channel",
        ),
        sa.CheckConstraint(
            _enum_check("seal_status", BATCH_SEAL_STATUS_VALUES),
            name="ck_actual_harvest_batch_seal_status",
        ),
        sa.CheckConstraint(
            _enum_check("status", BATCH_STATUS_VALUES),
            name="ck_actual_harvest_batch_status",
        ),
        sa.CheckConstraint(
            "(expected_record_count_or_null IS NULL OR expected_record_count_or_null >= 0) "
            "AND uploaded_record_count >= 0 "
            "AND (sealed_record_count_or_null IS NULL OR sealed_record_count_or_null >= 0) "
            "AND record_count >= 0 AND valid_record_count >= 0 "
            "AND invalid_record_count >= 0 AND committed_record_count >= 0",
            name="ck_actual_harvest_batch_counts_nonnegative",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("server_raw_payload_hash_or_null", nullable=True),
            name="ck_actual_harvest_batch_server_raw_hash",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("canonical_batch_hash_or_null", nullable=True),
            name="ck_actual_harvest_batch_canonical_hash",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("seal_manifest_hash_or_null", nullable=True),
            name="ck_actual_harvest_batch_seal_manifest_hash",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("source_file_hash_or_null", nullable=True),
            name="ck_actual_harvest_batch_source_file_hash",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("raw_payload_hash", nullable=False),
            name="ck_actual_harvest_batch_raw_payload_hash",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("source_semantics_attestation_hash", nullable=False),
            name="ck_actual_harvest_batch_attestation_hash",
        ),
        sa.CheckConstraint(
            _enum_check(
                "source_semantics_physical_event",
                PHYSICAL_EVENT_VALUES,
            ),
            name="ck_actual_harvest_batch_physical_event",
        ),
        sa.CheckConstraint(
            _enum_check(
                "source_semantics_quantity_basis",
                QUANTITY_BASIS_VALUES,
            ),
            name="ck_actual_harvest_batch_quantity_basis",
        ),
        sa.CheckConstraint(
            _enum_check(
                "source_semantics_quantity_unit",
                QUANTITY_UNIT_VALUES,
            ),
            name="ck_actual_harvest_batch_quantity_unit",
        ),
        sa.CheckConstraint(
            _enum_check(
                "source_semantics_missing_record_semantics",
                MISSING_RECORD_SEMANTICS_VALUES,
            ),
            name="ck_actual_harvest_batch_missing_record_semantics",
        ),
        sa.Index(
            "ix_actual_harvest_import_batch_idempotency",
            "source_system",
            "idempotency_key",
        ),
    )

    op.create_table(
        "actual_harvest_import_record",
        sa.Column("id", _sqlite_bigint(), primary_key=True, autoincrement=True),
        sa.Column("batch_id", _sqlite_bigint(), nullable=False),
        sa.Column("external_logical_record_id", sa.Text(), nullable=False),
        sa.Column("external_revision_id", sa.Text(), nullable=False),
        sa.Column("source_system", sa.Text(), nullable=False),
        sa.Column("external_batch_id", sa.Text(), nullable=False),
        sa.Column("harvest_business_date", sa.Date(), nullable=False),
        sa.Column("farm_code", sa.Text(), nullable=False),
        sa.Column("subfarm_or_plot_code", sa.Text(), nullable=False),
        sa.Column("variety_code", sa.Text(), nullable=False),
        sa.Column("actual_harvest_quantity_kg", sa.Numeric(18, 6), nullable=False),
        sa.Column("source_recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_recorded_at_authority_status", sa.Text(), nullable=False),
        sa.Column(
            "source_recorded_at_authority_reference_or_null",
            sa.Text(),
            nullable=True,
        ),
        sa.Column("import_received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("record_status", sa.Text(), nullable=False),
        sa.Column("supersedes_external_revision_id", sa.Text(), nullable=True),
        sa.Column("season_code", sa.Text(), nullable=True),
        sa.Column("farm_timezone", sa.Text(), nullable=True),
        sa.Column("revised_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_row_number", sa.Integer(), nullable=True),
        sa.Column("source_sheet_name", sa.Text(), nullable=True),
        sa.Column("source_note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["batch_id", "source_system", "external_batch_id"],
            [
                "actual_harvest_import_batch.id",
                "actual_harvest_import_batch.source_system",
                "actual_harvest_import_batch.external_batch_id",
            ],
            name="fk_actual_harvest_record_batch_identity",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "source_system",
            "external_revision_id",
            name="uq_actual_harvest_record_source_revision",
        ),
        sa.UniqueConstraint(
            "source_system",
            "external_logical_record_id",
            "revision_number",
            name="uq_actual_harvest_record_source_logical_revision",
        ),
        sa.UniqueConstraint(
            "batch_id",
            "source_row_number",
            name="uq_actual_harvest_record_batch_row",
        ),
        sa.CheckConstraint(
            "actual_harvest_quantity_kg >= 0",
            name="ck_actual_harvest_record_quantity_nonnegative",
        ),
        sa.CheckConstraint(
            "revision_number >= 1",
            name="ck_actual_harvest_record_revision_positive",
        ),
        sa.CheckConstraint(
            "source_row_number IS NULL OR source_row_number >= 1",
            name="ck_actual_harvest_record_source_row_positive",
        ),
        sa.CheckConstraint(
            _enum_check(
                "source_recorded_at_authority_status",
                SOURCE_RECORDED_AT_AUTHORITY_VALUES,
            ),
            name="ck_actual_harvest_record_source_time_status",
        ),
        sa.CheckConstraint(
            _enum_check("record_status", RECORD_STATUS_VALUES),
            name="ck_actual_harvest_record_status",
        ),
        sa.Index("ix_actual_harvest_record_batch_id", "batch_id"),
        sa.Index(
            "ix_actual_harvest_record_source_logical",
            "source_system",
            "external_logical_record_id",
            "revision_number",
        ),
    )


def downgrade() -> None:
    op.drop_table("actual_harvest_import_record")
    op.drop_table("actual_harvest_import_batch")
