"""Add actual-harvest commit manifest for v0.2-S1 atomic commit.

Revision ID: 0020_actual_harvest_commit_manifest
Revises: 0019_actual_harvest_validation_evidence
"""

from __future__ import annotations

from collections.abc import Iterable

import sqlalchemy as sa
from alembic import op

revision = "0020_actual_harvest_commit_manifest"
down_revision = "0019_actual_harvest_validation_evidence"
branch_labels = None
depends_on = None

COMMIT_POLICY_VERSION = "actual-harvest-commit-policy-v1"


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


def _create_commit_manifest_immutability_guard() -> None:
    """Reject UPDATE and DELETE on actual_harvest_commit_manifest."""
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            sa.text(
                """
                CREATE FUNCTION actual_harvest_reject_commit_manifest_mutation()
                RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    IF TG_OP = 'DELETE' THEN
                        RAISE EXCEPTION 'actual-harvest commit manifest is immutable'
                            USING ERRCODE = 'check_violation';
                    END IF;
                    RAISE EXCEPTION 'actual-harvest commit manifest is immutable'
                        USING ERRCODE = 'check_violation';
                END;
                $$;
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_actual_harvest_commit_manifest_immutable
                BEFORE UPDATE OR DELETE
                ON actual_harvest_commit_manifest
                FOR EACH ROW
                EXECUTE FUNCTION actual_harvest_reject_commit_manifest_mutation()
                """
            )
        )
        return

    if dialect == "sqlite":
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_actual_harvest_commit_manifest_immutable_update
                BEFORE UPDATE ON actual_harvest_commit_manifest
                BEGIN
                    SELECT RAISE(ABORT, 'actual-harvest commit manifest is immutable');
                END;
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_actual_harvest_commit_manifest_immutable_delete
                BEFORE DELETE ON actual_harvest_commit_manifest
                BEGIN
                    SELECT RAISE(ABORT, 'actual-harvest commit manifest is immutable');
                END;
                """
            )
        )


def _drop_commit_manifest_immutability_guard() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        for trigger in (
            "trg_actual_harvest_commit_manifest_immutable",
        ):
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger} ON actual_harvest_commit_manifest"))
        op.execute(
            sa.text(
                "DROP FUNCTION IF EXISTS actual_harvest_reject_commit_manifest_mutation()"
            )
        )
        return
    if dialect == "sqlite":
        for trigger in (
            "trg_actual_harvest_commit_manifest_immutable_update",
            "trg_actual_harvest_commit_manifest_immutable_delete",
        ):
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger}"))


def upgrade() -> None:
    op.create_table(
        "actual_harvest_commit_manifest",
        sa.Column("id", _bigint(), primary_key=True, autoincrement=True),
        sa.Column(
            "batch_id",
            _bigint(),
            sa.ForeignKey(
                "actual_harvest_import_batch.id",
                name="fk_actual_harvest_commit_manifest_batch",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column(
            "validation_run_id",
            _bigint(),
            sa.ForeignKey(
                "actual_harvest_validation_run.id",
                name="fk_actual_harvest_commit_manifest_validation_run",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("commit_policy_version", sa.Text(), nullable=False),
        sa.Column(
            "validation_run_instance_identity_hash", sa.Text(), nullable=False
        ),
        sa.Column("commit_manifest_hash", sa.Text(), nullable=False),
        sa.Column("seal_manifest_hash", sa.Text(), nullable=False),
        sa.Column("canonical_batch_hash", sa.Text(), nullable=False),
        sa.Column("record_manifest_hash", sa.Text(), nullable=False),
        sa.Column("validation_result_hash", sa.Text(), nullable=False),
        sa.Column("mapping_snapshot_hash", sa.Text(), nullable=False),
        sa.Column("resolved_identity_snapshot_hash", sa.Text(), nullable=False),
        sa.Column("lineage_graph_hash", sa.Text(), nullable=False),
        sa.Column("committed_lineage_basis_hash", sa.Text(), nullable=False),
        sa.Column("registry_content_hash", sa.Text(), nullable=False),
        sa.Column("source_semantics_attestation_hash", sa.Text(), nullable=False),
        sa.Column("committed_record_count", sa.Integer(), nullable=False),
        sa.Column("committed_by_identity", sa.Text(), nullable=False),
        sa.Column(
            "committed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "batch_id", name="uq_actual_harvest_commit_manifest_batch"
        ),
        sa.UniqueConstraint(
            "validation_run_id",
            name="uq_actual_harvest_commit_manifest_validation_run",
        ),
        sa.UniqueConstraint(
            "commit_manifest_hash", name="uq_actual_harvest_commit_manifest_hash"
        ),
        sa.CheckConstraint(
            "committed_record_count >= 0",
            name="ck_actual_harvest_commit_manifest_count_nonneg",
        ),
        sa.CheckConstraint(
            _sha_check("validation_run_instance_identity_hash"),
            name="ck_actual_harvest_commit_manifest_instance_hash",
        ),
        sa.CheckConstraint(
            _sha_check("commit_manifest_hash"),
            name="ck_actual_harvest_commit_manifest_hash",
        ),
        sa.CheckConstraint(
            _sha_check("seal_manifest_hash"),
            name="ck_actual_harvest_commit_manifest_seal_hash",
        ),
        sa.CheckConstraint(
            _sha_check("canonical_batch_hash"),
            name="ck_actual_harvest_commit_manifest_canonical_batch_hash",
        ),
        sa.CheckConstraint(
            _sha_check("record_manifest_hash"),
            name="ck_actual_harvest_commit_manifest_record_manifest_hash",
        ),
        sa.CheckConstraint(
            _sha_check("validation_result_hash"),
            name="ck_actual_harvest_commit_manifest_validation_result_hash",
        ),
        sa.CheckConstraint(
            _sha_check("mapping_snapshot_hash"),
            name="ck_actual_harvest_commit_manifest_mapping_snapshot_hash",
        ),
        sa.CheckConstraint(
            _sha_check("resolved_identity_snapshot_hash"),
            name="ck_actual_harvest_commit_manifest_resolved_identity_hash",
        ),
        sa.CheckConstraint(
            _sha_check("lineage_graph_hash"),
            name="ck_actual_harvest_commit_manifest_lineage_graph_hash",
        ),
        sa.CheckConstraint(
            _sha_check("committed_lineage_basis_hash"),
            name="ck_actual_harvest_commit_manifest_lineage_basis_hash",
        ),
        sa.CheckConstraint(
            _sha_check("registry_content_hash"),
            name="ck_actual_harvest_commit_manifest_registry_hash",
        ),
        sa.CheckConstraint(
            _sha_check("source_semantics_attestation_hash"),
            name="ck_actual_harvest_commit_manifest_attestation_hash",
        ),
    )

    _create_commit_manifest_immutability_guard()


def downgrade() -> None:
    _drop_commit_manifest_immutability_guard()
    op.drop_table("actual_harvest_commit_manifest")
