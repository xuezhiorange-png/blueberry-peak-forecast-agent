"""Create append-only S2 Lane C PIT visibility and revision-winner tables.

Revision ID: 8c6aead9f8e9
Revises: 2af278a20e2a
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "8c6aead9f8e9"
down_revision = "2af278a20e2a"
branch_labels = None
depends_on = None

PIT_VISIBILITY_BLOCK_REASON_VALUES = (
    "SOURCE_AVAILABLE_MISSING",
    "SOURCE_AVAILABLE_AFTER_CUTOFF",
    "SOURCE_CANCELLED",
    "CONTRADICTORY_TIMESTAMPS",
    "NAIVE_TIMESTAMP",
    "INDETERMINATE_VISIBILITY",
)
REVISION_WINNER_BLOCK_REASON_VALUES = (
    "NOT_APPLICABLE_FOR_IDFL_LABEL_SIDE",
    "NO_VISIBLE_CANDIDATE_AT_CUTOFF",
    "MULTIPLE_VISIBLE_TERMINALS",
    "DUPLICATE_REVISION_CANDIDATE_IDENTITY",
    "CONTRADICTORY_EVIDENCE",
    "NO_WINNER",
)
REVISION_WINNER_MODE_VALUES = ("IDFL_LABEL_SIDE", "REPLAY_REVISION_GRAPH")


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


def _create_lane_c_immutability_guard(table_name: str, message: str) -> None:
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


def _drop_lane_c_immutability_guard(table_name: str) -> None:
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
        "s2_pit_visibility_decision",
        sa.Column("id", _sqlite_bigint(), primary_key=True, autoincrement=True),
        sa.Column("source_row_identity_hash", sa.Text(), nullable=False),
        sa.Column("source_system", sa.Text(), nullable=False),
        sa.Column("external_logical_record_id", sa.Text(), nullable=False),
        sa.Column("external_revision_id", sa.Text(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("raw_source_artifact_identity_hash", sa.Text(), nullable=False),
        sa.Column("raw_import_batch_identity_hash", sa.Text(), nullable=False),
        sa.Column("source_recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_available_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_revised_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("forecast_cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("visibility_policy_version", sa.Text(), nullable=False),
        sa.Column("visibility_schema_version", sa.Text(), nullable=False),
        sa.Column("forecast_cutoff_identity_version", sa.Text(), nullable=False),
        sa.Column("revision_winner_policy_version", sa.Text(), nullable=False),
        sa.Column("revision_schema_version", sa.Text(), nullable=False),
        sa.Column("eligible", sa.Boolean(), nullable=False),
        sa.Column("blocked", sa.Boolean(), nullable=False),
        sa.Column("block_reason", sa.Text(), nullable=True),
        sa.Column("content_sha256", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("content_sha256", name="uq_s2_pit_visibility_decision_content"),
        sa.CheckConstraint(
            _sha256_hex_check("source_row_identity_hash"),
            name="ck_s2_pit_visibility_source_row_identity_hash",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("raw_source_artifact_identity_hash"),
            name="ck_s2_pit_visibility_raw_source_artifact_hash",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("raw_import_batch_identity_hash"),
            name="ck_s2_pit_visibility_raw_import_batch_hash",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("content_sha256"),
            name="ck_s2_pit_visibility_content_sha256",
        ),
        sa.CheckConstraint("revision_number >= 1", name="ck_s2_pit_visibility_revision_number"),
        sa.CheckConstraint(
            (
                "block_reason IS NULL OR "
                f"{_enum_check('block_reason', PIT_VISIBILITY_BLOCK_REASON_VALUES)}"
            ),
            name="ck_s2_pit_visibility_block_reason",
        ),
    )

    op.create_table(
        "s2_revision_winner_decision",
        sa.Column("id", _sqlite_bigint(), primary_key=True, autoincrement=True),
        sa.Column("source_system", sa.Text(), nullable=False),
        sa.Column("external_logical_record_id", sa.Text(), nullable=False),
        sa.Column("forecast_cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("visibility_policy_version", sa.Text(), nullable=False),
        sa.Column("visibility_schema_version", sa.Text(), nullable=False),
        sa.Column("forecast_cutoff_identity_version", sa.Text(), nullable=False),
        sa.Column("revision_winner_policy_version", sa.Text(), nullable=False),
        sa.Column("revision_schema_version", sa.Text(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("revision_winner_required", sa.Boolean(), nullable=False),
        sa.Column("winner_manifest_required", sa.Boolean(), nullable=False),
        sa.Column("winner_source_row_identity_hash", sa.Text(), nullable=True),
        sa.Column("winner_source_system", sa.Text(), nullable=True),
        sa.Column("winner_external_logical_record_id", sa.Text(), nullable=True),
        sa.Column("winner_external_revision_id", sa.Text(), nullable=True),
        sa.Column("winner_revision_number", sa.Integer(), nullable=True),
        sa.Column("winner_raw_source_artifact_identity_hash", sa.Text(), nullable=True),
        sa.Column("winner_raw_import_batch_identity_hash", sa.Text(), nullable=True),
        sa.Column("blocked", sa.Boolean(), nullable=False),
        sa.Column("no_winner_reason", sa.Text(), nullable=True),
        sa.Column("ordered_candidate_identities_json", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("content_sha256", name="uq_s2_revision_winner_decision_content"),
        sa.CheckConstraint(
            _sha256_hex_check("content_sha256"),
            name="ck_s2_revision_winner_content_sha256",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("winner_source_row_identity_hash", nullable=True),
            name="ck_s2_revision_winner_winner_identity_hash",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("winner_raw_source_artifact_identity_hash", nullable=True),
            name="ck_s2_revision_winner_winner_artifact_hash",
        ),
        sa.CheckConstraint(
            _sha256_hex_check("winner_raw_import_batch_identity_hash", nullable=True),
            name="ck_s2_revision_winner_winner_batch_hash",
        ),
        sa.CheckConstraint(
            _enum_check("mode", REVISION_WINNER_MODE_VALUES),
            name="ck_s2_revision_winner_mode",
        ),
        sa.CheckConstraint(
            (
                "no_winner_reason IS NULL OR "
                f"{_enum_check('no_winner_reason', REVISION_WINNER_BLOCK_REASON_VALUES)}"
            ),
            name="ck_s2_revision_winner_no_winner_reason",
        ),
        sa.CheckConstraint(
            (
                "(winner_source_row_identity_hash IS NULL "
                "AND winner_source_system IS NULL "
                "AND winner_external_logical_record_id IS NULL "
                "AND winner_external_revision_id IS NULL "
                "AND winner_revision_number IS NULL "
                "AND winner_raw_source_artifact_identity_hash IS NULL "
                "AND winner_raw_import_batch_identity_hash IS NULL) "
                "OR (winner_source_row_identity_hash IS NOT NULL "
                "AND winner_source_system IS NOT NULL "
                "AND winner_external_logical_record_id IS NOT NULL "
                "AND winner_external_revision_id IS NOT NULL "
                "AND winner_revision_number IS NOT NULL "
                "AND winner_raw_source_artifact_identity_hash IS NOT NULL "
                "AND winner_raw_import_batch_identity_hash IS NOT NULL "
                "AND winner_revision_number >= 1)"
            ),
            name="ck_s2_revision_winner_winner_identity_presence",
        ),
    )

    for table_name, message in (
        ("s2_pit_visibility_decision", "s2 pit visibility decision is immutable"),
        ("s2_revision_winner_decision", "s2 revision winner decision is immutable"),
    ):
        _create_lane_c_immutability_guard(table_name, message)


def downgrade() -> None:
    for table_name in (
        "s2_revision_winner_decision",
        "s2_pit_visibility_decision",
    ):
        _drop_lane_c_immutability_guard(table_name)
    op.drop_table("s2_revision_winner_decision")
    op.drop_table("s2_pit_visibility_decision")
