"""Add immutable actual-harvest label snapshot for V0.2-S2 / Q2A-I7.

Frozen contract:
- docs/forecast-quality/q2a-i7-label-snapshot-and-revision-winner-contract.md §17
- Revision: 0021_actual_harvest_label_snapshot
- Down revision: 0020_actual_harvest_commit_manifest
- Four logical tables: actual_harvest_label_snapshot,
  actual_harvest_label_snapshot_winner,
  actual_harvest_label_snapshot_label,
  actual_harvest_label_snapshot_exclusion.
- All four tables reject UPDATE and DELETE via PostgreSQL + SQLite
  immutability triggers (SQLSTATE 23514 / SQLITE_CONSTRAINT_TRIGGER).
- All foreign keys use ON DELETE RESTRICT.
- Caller-owned single transaction creation; the migration itself only
  creates the DDL; the per-snapshot insert lives in
  ``backend.app.actual_harvest_labels.service``.
"""

from __future__ import annotations

from collections.abc import Iterable

import sqlalchemy as sa
from alembic import op

revision = "0021_actual_harvest_label_snapshot"
down_revision = "0020_actual_harvest_commit_manifest"
branch_labels = None
depends_on = None


SNAPSHOT_POLICY_VERSION = "actual-harvest-label-snapshot-policy-v1"
WINNER_POLICY_VERSION = "actual-harvest-label-winner-policy-v1"
AGGREGATION_POLICY_VERSION = "actual-harvest-label-aggregation-policy-v1"
REQUEST_HASH_POLICY_VERSION = "actual-harvest-label-request-hash-v1"
INSTANCE_HASH_POLICY_VERSION = "actual-harvest-label-instance-hash-v1"
SNAPSHOT_HASH_POLICY_VERSION = "actual-harvest-label-snapshot-hash-v1"


def _bigint() -> sa.types.TypeEngine:
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def _utc_datetime() -> sa.types.TypeEngine:
    return sa.DateTime(timezone=True)


def _enum_check(column: str, values: Iterable[str]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


def _sha256_hex_check(column: str, *, nullable: bool) -> str:
    expression = column
    for character in "0123456789abcdef":
        expression = f"replace({expression}, '{character}', '')"
    valid = f"length({column}) = 64 AND lower({column}) = {column} AND length({expression}) = 0"
    return f"{column} IS NULL OR ({valid})" if nullable else valid


VISIBILITY_MODE_VALUES = ("AS_OF_EVALUATION", "FINAL_ADJUDICATED")
RECORD_STATUS_VALUES = ("ACTIVE", "CORRECTED", "VOID", "FINALIZED")
EFFECTIVE_STATUS_VALUES = ("ACTIVE", "FINALIZED")
SOURCE_AUTHORITY_VALUES = (
    "TRUSTED_SOURCE_TIMESTAMP",
    "USER_ASSERTED_UNVERIFIED",
    "MISSING",
    "CONFLICTING",
)


def _create_label_snapshot_immutability_triggers() -> None:
    """Reject UPDATE and DELETE on the four I7 tables.

    PostgreSQL raises SQLSTATE 23514 with the exact server message
    ``actual-harvest label snapshot row is immutable``. SQLite triggers
    raise ABORT with the same message string so the contract asserts
    match across both dialects.
    """

    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            sa.text(
                """
                CREATE FUNCTION actual_harvest_reject_label_snapshot_mutation()
                RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    RAISE EXCEPTION 'actual-harvest label snapshot row is immutable'
                        USING ERRCODE = '23514';
                END;
                $$
                """
            )
        )
        for table in (
            "actual_harvest_label_snapshot",
            "actual_harvest_label_snapshot_winner",
            "actual_harvest_label_snapshot_label",
            "actual_harvest_label_snapshot_exclusion",
        ):
            op.execute(
                sa.text(
                    f"""
                    CREATE TRIGGER trg_{table}_immutable
                    BEFORE UPDATE OR DELETE
                    ON {table}
                    FOR EACH ROW
                    EXECUTE FUNCTION actual_harvest_reject_label_snapshot_mutation()
                    """
                )
            )
        return

    if dialect == "sqlite":
        for table in (
            "actual_harvest_label_snapshot",
            "actual_harvest_label_snapshot_winner",
            "actual_harvest_label_snapshot_label",
            "actual_harvest_label_snapshot_exclusion",
        ):
            op.execute(
                sa.text(
                    f"""
                    CREATE TRIGGER trg_{table}_immutable_update
                    BEFORE UPDATE ON {table}
                    BEGIN
                        SELECT RAISE(ABORT, 'actual-harvest label snapshot row is immutable');
                    END
                    """
                )
            )
            op.execute(
                sa.text(
                    f"""
                    CREATE TRIGGER trg_{table}_immutable_delete
                    BEFORE DELETE ON {table}
                    BEGIN
                        SELECT RAISE(ABORT, 'actual-harvest label snapshot row is immutable');
                    END
                    """
                )
            )


def _drop_label_snapshot_immutability_triggers() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        for table in (
            "actual_harvest_label_snapshot",
            "actual_harvest_label_snapshot_winner",
            "actual_harvest_label_snapshot_label",
            "actual_harvest_label_snapshot_exclusion",
        ):
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS trg_{table}_immutable ON {table}"))
        op.execute(
            sa.text("DROP FUNCTION IF EXISTS actual_harvest_reject_label_snapshot_mutation()")
        )
        return
    if dialect == "sqlite":
        for table in (
            "actual_harvest_label_snapshot",
            "actual_harvest_label_snapshot_winner",
            "actual_harvest_label_snapshot_label",
            "actual_harvest_label_snapshot_exclusion",
        ):
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS trg_{table}_immutable_update"))
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS trg_{table}_immutable_delete"))


def upgrade() -> None:
    op.create_table(
        "actual_harvest_label_snapshot",
        sa.Column("id", _bigint(), primary_key=True, autoincrement=True),
        sa.Column("snapshot_idempotency_key", sa.Text(), nullable=False),
        sa.Column("source_system", sa.Text(), nullable=False),
        sa.Column("visibility_mode", sa.Text(), nullable=False),
        sa.Column("label_observation_cutoff_at_or_null", _utc_datetime(), nullable=True),
        sa.Column("harvest_date_start", sa.Date(), nullable=False),
        sa.Column("harvest_date_end", sa.Date(), nullable=False),
        sa.Column("season_business_keys", sa.Text(), nullable=False),
        sa.Column("farm_business_keys_or_empty_for_all", sa.Text(), nullable=False),
        sa.Column("variety_business_keys_or_empty_for_all", sa.Text(), nullable=False),
        sa.Column("snapshot_policy_version", sa.Text(), nullable=False),
        sa.Column("winner_policy_version", sa.Text(), nullable=False),
        sa.Column("aggregation_policy_version", sa.Text(), nullable=False),
        sa.Column("snapshot_request_identity_hash", sa.Text(), nullable=False),
        sa.Column("snapshot_instance_identity_hash", sa.Text(), nullable=False),
        sa.Column("source_commit_manifest_set_hash", sa.Text(), nullable=False),
        sa.Column("winner_manifest_hash", sa.Text(), nullable=False),
        sa.Column("label_row_set_hash", sa.Text(), nullable=False),
        sa.Column("exclusion_manifest_hash", sa.Text(), nullable=False),
        sa.Column("label_snapshot_hash", sa.Text(), nullable=False),
        sa.Column("source_manifest_count", sa.Integer(), nullable=False),
        sa.Column("winner_count", sa.Integer(), nullable=False),
        sa.Column("label_row_count", sa.Integer(), nullable=False),
        sa.Column("exclusion_row_count", sa.Integer(), nullable=False),
        sa.Column("snapshot_executed_at", _utc_datetime(), nullable=False),
        sa.Column("created_by_identity", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            _utc_datetime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "source_system",
            "snapshot_idempotency_key",
            name="uq_actual_harvest_label_snapshot_idempotency",
        ),
        sa.CheckConstraint(
            _enum_check("visibility_mode", VISIBILITY_MODE_VALUES),
            name="ck_actual_harvest_label_snapshot_visibility_mode",
        ),
        sa.CheckConstraint(
            "harvest_date_start <= harvest_date_end",
            name="ck_actual_harvest_label_snapshot_date_range",
        ),
        sa.CheckConstraint(
            "(visibility_mode = 'AS_OF_EVALUATION' "
            "AND label_observation_cutoff_at_or_null IS NOT NULL) "
            "OR (visibility_mode = 'FINAL_ADJUDICATED' "
            "AND label_observation_cutoff_at_or_null IS NULL)",
            name="ck_actual_harvest_label_snapshot_cutoff_binding",
        ),
        sa.CheckConstraint(
            "source_manifest_count >= 0 "
            "AND winner_count >= 0 "
            "AND label_row_count >= 0 "
            "AND exclusion_row_count >= 0",
            name="ck_actual_harvest_label_snapshot_counts_nonneg",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("snapshot_request_identity_hash", nullable=False),
            name="ck_actual_harvest_label_snapshot_request_hash",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("snapshot_instance_identity_hash", nullable=False),
            name="ck_actual_harvest_label_snapshot_instance_hash",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("source_commit_manifest_set_hash", nullable=False),
            name="ck_actual_harvest_label_snapshot_manifest_set_hash",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("winner_manifest_hash", nullable=False),
            name="ck_actual_harvest_label_snapshot_winner_hash",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("label_row_set_hash", nullable=False),
            name="ck_actual_harvest_label_snapshot_label_row_hash",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("exclusion_manifest_hash", nullable=False),
            name="ck_actual_harvest_label_snapshot_exclusion_hash",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("label_snapshot_hash", nullable=False),
            name="ck_actual_harvest_label_snapshot_hash",
        ),
    )
    op.create_index(
        "ix_actual_harvest_label_snapshot_idempotency",
        "actual_harvest_label_snapshot",
        ["source_system", "snapshot_idempotency_key"],
    )
    op.create_index(
        "ix_actual_harvest_label_snapshot_executed_at",
        "actual_harvest_label_snapshot",
        ["snapshot_executed_at"],
    )

    op.create_table(
        "actual_harvest_label_snapshot_winner",
        sa.Column("id", _bigint(), primary_key=True, autoincrement=True),
        sa.Column(
            "snapshot_id",
            _bigint(),
            sa.ForeignKey(
                "actual_harvest_label_snapshot.id",
                name="fk_actual_harvest_label_snapshot_winner_snapshot",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("source_system", sa.Text(), nullable=False),
        sa.Column("external_logical_record_id", sa.Text(), nullable=False),
        sa.Column("external_revision_id", sa.Text(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("canonical_record_hash", sa.Text(), nullable=False),
        sa.Column("record_status", sa.Text(), nullable=False),
        sa.Column("effective_status", sa.Text(), nullable=False),
        sa.Column("finalized_at_or_null", _utc_datetime(), nullable=True),
        sa.Column("source_recorded_at_or_null", _utc_datetime(), nullable=True),
        sa.Column("source_recorded_at_authority_status", sa.Text(), nullable=False),
        sa.Column("harvest_business_date", sa.Date(), nullable=False),
        sa.Column(
            "actual_harvest_quantity_kg",
            sa.Numeric(18, 6, asdecimal=True),
            nullable=False,
        ),
        sa.Column("commit_manifest_hash", sa.Text(), nullable=False),
        sa.Column("season_business_key", sa.Text(), nullable=False),
        sa.Column("farm_business_key", sa.Text(), nullable=False),
        sa.Column("subfarm_business_key", sa.Text(), nullable=False),
        sa.Column("variety_business_key", sa.Text(), nullable=False),
        sa.Column(
            "season_id",
            _bigint(),
            sa.ForeignKey(
                "dim_season.id",
                name="fk_actual_harvest_label_snapshot_winner_season",
                ondelete="RESTRICT",
            ),
            nullable=True,
        ),
        sa.Column(
            "farm_id",
            _bigint(),
            sa.ForeignKey(
                "dim_farm.id",
                name="fk_actual_harvest_label_snapshot_winner_farm",
                ondelete="RESTRICT",
            ),
            nullable=True,
        ),
        sa.Column(
            "subfarm_id",
            _bigint(),
            sa.ForeignKey(
                "dim_subfarm.id",
                name="fk_actual_harvest_label_snapshot_winner_subfarm",
                ondelete="RESTRICT",
            ),
            nullable=True,
        ),
        sa.Column(
            "variety_id",
            _bigint(),
            sa.ForeignKey(
                "dim_variety.id",
                name="fk_actual_harvest_label_snapshot_winner_variety",
                ondelete="RESTRICT",
            ),
            nullable=True,
        ),
        sa.Column("mapping_registry_version", sa.Text(), nullable=False),
        sa.Column("mapping_policy_version", sa.Text(), nullable=False),
        sa.Column("season_resolver_version", sa.Text(), nullable=False),
        sa.Column("mapping_registry_entry_hash", sa.Text(), nullable=True),
        sa.Column("resolved_master_business_key", sa.Text(), nullable=False),
        sa.Column("resolved_master_parent_business_key", sa.Text(), nullable=True),
        sa.Column("resolved_master_record_hash", sa.Text(), nullable=False),
        sa.Column("mapping_snapshot_hash", sa.Text(), nullable=False),
        sa.Column("resolved_identity_snapshot_hash", sa.Text(), nullable=False),
        sa.Column("registry_content_hash", sa.Text(), nullable=False),
        sa.Column("winner_row_hash", sa.Text(), nullable=False),
        sa.Column("winner_sort_key", sa.Text(), nullable=False),
        sa.UniqueConstraint(
            "snapshot_id",
            "source_system",
            "external_revision_id",
            name="uq_actual_harvest_label_snapshot_winner_revision",
        ),
        sa.CheckConstraint(
            "actual_harvest_quantity_kg >= 0",
            name="ck_actual_harvest_label_snapshot_winner_quantity_nonneg",
        ),
        sa.CheckConstraint(
            _enum_check("record_status", RECORD_STATUS_VALUES),
            name="ck_actual_harvest_label_snapshot_winner_record_status",
        ),
        sa.CheckConstraint(
            _enum_check("effective_status", EFFECTIVE_STATUS_VALUES),
            name="ck_actual_harvest_label_snapshot_winner_effective_status",
        ),
        sa.CheckConstraint(
            _enum_check("source_recorded_at_authority_status", SOURCE_AUTHORITY_VALUES),
            name="ck_actual_harvest_label_snapshot_winner_authority",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("canonical_record_hash", nullable=False),
            name="ck_actual_harvest_label_snapshot_winner_canonical_record_hash",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("commit_manifest_hash", nullable=False),
            name="ck_actual_harvest_label_snapshot_winner_commit_manifest_hash",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("mapping_registry_entry_hash", nullable=True),
            name="ck_actual_harvest_label_snapshot_winner_registry_entry_hash",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("resolved_master_record_hash", nullable=False),
            name="ck_actual_harvest_label_snapshot_winner_resolved_master_hash",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("mapping_snapshot_hash", nullable=False),
            name="ck_actual_harvest_label_snapshot_winner_mapping_snapshot_hash",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("resolved_identity_snapshot_hash", nullable=False),
            name="ck_actual_harvest_label_snapshot_winner_resolved_identity_hash",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("registry_content_hash", nullable=False),
            name="ck_actual_harvest_label_snapshot_winner_registry_content_hash",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("winner_row_hash", nullable=False),
            name="ck_actual_harvest_label_snapshot_winner_row_hash",
        ),
    )
    op.create_index(
        "ix_actual_harvest_label_snapshot_winner_sort",
        "actual_harvest_label_snapshot_winner",
        ["snapshot_id", "winner_sort_key"],
    )
    op.create_index(
        "ix_actual_harvest_label_snapshot_winner_logical",
        "actual_harvest_label_snapshot_winner",
        ["snapshot_id", "source_system", "external_logical_record_id"],
    )

    op.create_table(
        "actual_harvest_label_snapshot_label",
        sa.Column("id", _bigint(), primary_key=True, autoincrement=True),
        sa.Column(
            "snapshot_id",
            _bigint(),
            sa.ForeignKey(
                "actual_harvest_label_snapshot.id",
                name="fk_actual_harvest_label_snapshot_label_snapshot",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("season_business_key", sa.Text(), nullable=False),
        sa.Column("farm_business_key", sa.Text(), nullable=False),
        sa.Column("subfarm_business_key", sa.Text(), nullable=False),
        sa.Column("variety_business_key", sa.Text(), nullable=False),
        sa.Column("harvest_business_date", sa.Date(), nullable=False),
        sa.Column(
            "exact_decimal_quantity_sum_kg",
            sa.Numeric(18, 6, asdecimal=True),
            nullable=False,
        ),
        sa.Column("contributing_winner_count", sa.Integer(), nullable=False),
        sa.Column("contributing_winner_hashes", sa.Text(), nullable=False),
        sa.Column("label_row_hash", sa.Text(), nullable=False),
        sa.Column("label_sort_key", sa.Text(), nullable=False),
        sa.UniqueConstraint(
            "snapshot_id",
            "season_business_key",
            "farm_business_key",
            "subfarm_business_key",
            "variety_business_key",
            "harvest_business_date",
            name="uq_actual_harvest_label_snapshot_label_grain",
        ),
        sa.CheckConstraint(
            "exact_decimal_quantity_sum_kg >= 0",
            name="ck_actual_harvest_label_snapshot_label_sum_nonneg",
        ),
        sa.CheckConstraint(
            "contributing_winner_count >= 0",
            name="ck_actual_harvest_label_snapshot_label_count_nonneg",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("label_row_hash", nullable=False),
            name="ck_actual_harvest_label_snapshot_label_row_hash",
        ),
    )
    op.create_index(
        "ix_actual_harvest_label_snapshot_label_sort",
        "actual_harvest_label_snapshot_label",
        ["snapshot_id", "label_sort_key"],
    )

    op.create_table(
        "actual_harvest_label_snapshot_exclusion",
        sa.Column("id", _bigint(), primary_key=True, autoincrement=True),
        sa.Column(
            "snapshot_id",
            _bigint(),
            sa.ForeignKey(
                "actual_harvest_label_snapshot.id",
                name="fk_actual_harvest_label_snapshot_exclusion_snapshot",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("exclusion_category", sa.Text(), nullable=False),
        sa.Column("source_system", sa.Text(), nullable=False),
        sa.Column("external_logical_record_id_or_null", sa.Text(), nullable=True),
        sa.Column("external_revision_id_or_null", sa.Text(), nullable=True),
        sa.Column("harvest_business_date_or_null", sa.Date(), nullable=True),
        sa.Column("exclusion_row_hash", sa.Text(), nullable=False),
        sa.Column("exclusion_details", sa.Text(), nullable=False),
        sa.Column("exclusion_sort_key", sa.Text(), nullable=False),
        sa.UniqueConstraint(
            "snapshot_id",
            "exclusion_category",
            "source_system",
            "external_logical_record_id_or_null",
            "external_revision_id_or_null",
            "harvest_business_date_or_null",
            name="uq_actual_harvest_label_snapshot_exclusion_row",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("exclusion_row_hash", nullable=False),
            name="ck_actual_harvest_label_snapshot_exclusion_row_hash",
        ),
    )
    op.create_index(
        "ix_actual_harvest_label_snapshot_exclusion_sort",
        "actual_harvest_label_snapshot_exclusion",
        ["snapshot_id", "exclusion_sort_key"],
    )

    _create_label_snapshot_immutability_triggers()


def downgrade() -> None:
    _drop_label_snapshot_immutability_triggers()
    op.drop_table("actual_harvest_label_snapshot_exclusion")
    op.drop_table("actual_harvest_label_snapshot_label")
    op.drop_table("actual_harvest_label_snapshot_winner")
    op.drop_table("actual_harvest_label_snapshot")