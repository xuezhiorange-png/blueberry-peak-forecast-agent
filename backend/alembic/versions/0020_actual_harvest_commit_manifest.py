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
    """Reject UPDATE and DELETE on actual_harvest_commit_manifest.

    The PostgreSQL trigger raises SQLSTATE 23514 (check_violation) and
    the exact server message 'actual-harvest commit manifest is immutable'
    so the B8 contract test can assert both the SQLSTATE and the full
    server message.
    """
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            sa.text(
                """
                CREATE FUNCTION actual_harvest_reject_commit_manifest_mutation()
                RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    RAISE EXCEPTION 'actual-harvest commit manifest is immutable'
                        USING ERRCODE = '23514';
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
        for trigger in ("trg_actual_harvest_commit_manifest_immutable",):
            op.execute(
                sa.text(f"DROP TRIGGER IF EXISTS {trigger} ON actual_harvest_commit_manifest")
            )
        op.execute(
            sa.text("DROP FUNCTION IF EXISTS actual_harvest_reject_commit_manifest_mutation()")
        )
        return
    if dialect == "sqlite":
        for trigger in (
            "trg_actual_harvest_commit_manifest_immutable_update",
            "trg_actual_harvest_commit_manifest_immutable_delete",
        ):
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger}"))


# Statuses under which an import record is sealed and must be immutable.
# Any batch in one of these states makes the child records
# append-only (no UPDATE/DELETE permitted) — even if the trigger is
# bypassed in application code, the database refuses.
_SEALED_BATCH_STATUSES: tuple[str, ...] = (
    "SEALED",
    "VALIDATING",
    "VALIDATED",
    "COMMITTED",
)


def _create_import_record_immutability_guard() -> None:
    """Reject UPDATE and DELETE on actual_harvest_import_record when the
    parent batch is sealed (status in
    {SEALED, VALIDATING, VALIDATED, COMMITTED}).

    The UPLOADING stage is the only state in which writes are still
    permitted. The trigger inspects BOTH OLD and NEW batch_id on
    UPDATE so a malicious caller cannot evade the protection by
    mutating batch_id itself (the OLD row is sealed → reject).
    """
    dialect = op.get_bind().dialect.name
    sealed_list = ", ".join(f"'{status}'" for status in _SEALED_BATCH_STATUSES)

    if dialect == "postgresql":
        op.execute(
            sa.text(
                f"""
                CREATE FUNCTION actual_harvest_reject_sealed_record_mutation()
                RETURNS trigger LANGUAGE plpgsql AS $$
                DECLARE
                    old_status text;
                    new_status text;
                BEGIN
                    SELECT status INTO old_status
                        FROM actual_harvest_import_batch
                        WHERE id = OLD.batch_id;
                    IF old_status IN ({sealed_list}) THEN
                        RAISE EXCEPTION 'actual-harvest import record is immutable after seal'
                            USING ERRCODE = '23514';
                    END IF;
                    IF NEW.batch_id IS DISTINCT FROM OLD.batch_id THEN
                        SELECT status INTO new_status
                            FROM actual_harvest_import_batch
                            WHERE id = NEW.batch_id;
                        IF new_status IN ({sealed_list}) THEN
                            RAISE EXCEPTION 'actual-harvest import record is immutable after seal'
                                USING ERRCODE = '23514';
                        END IF;
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
                CREATE TRIGGER trg_actual_harvest_import_record_sealed_update
                BEFORE UPDATE
                ON actual_harvest_import_record
                FOR EACH ROW
                EXECUTE FUNCTION actual_harvest_reject_sealed_record_mutation()
                """
            )
        )
        op.execute(
            sa.text(
                f"""
                CREATE FUNCTION actual_harvest_reject_sealed_record_delete()
                RETURNS trigger LANGUAGE plpgsql AS $$
                DECLARE
                    parent_status text;
                BEGIN
                    SELECT status INTO parent_status
                        FROM actual_harvest_import_batch
                        WHERE id = OLD.batch_id;
                    IF parent_status IN ({sealed_list}) THEN
                        RAISE EXCEPTION 'actual-harvest import record is immutable after seal'
                            USING ERRCODE = '23514';
                    END IF;
                    RETURN OLD;
                END;
                $$;
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_actual_harvest_import_record_sealed_delete
                BEFORE DELETE
                ON actual_harvest_import_record
                FOR EACH ROW
                EXECUTE FUNCTION actual_harvest_reject_sealed_record_delete()
                """
            )
        )
        return

    if dialect == "sqlite":
        sealed_csv = ",".join(f"'{s}'" for s in _SEALED_BATCH_STATUSES)
        # SQLite's WHEN clause can reference OLD/NEW columns but does
        # not let the inner SELECT reference the mutating table
        # ('actual_harvest_import_record'). However, the parent batch
        # table IS a different table, so the subquery is allowed.
        op.execute(
            sa.text(
                f"""
                CREATE TRIGGER trg_actual_harvest_import_record_sealed_update
                BEFORE UPDATE ON actual_harvest_import_record
                FOR EACH ROW
                WHEN OLD.batch_id IN (
                    SELECT id FROM actual_harvest_import_batch
                    WHERE status IN ({sealed_csv})
                )
                BEGIN
                    SELECT RAISE(ABORT, 'actual-harvest import record is immutable after seal');
                END;
                """
            )
        )
        op.execute(
            sa.text(
                f"""
                CREATE TRIGGER trg_actual_harvest_import_record_sealed_delete
                BEFORE DELETE ON actual_harvest_import_record
                FOR EACH ROW
                WHEN OLD.batch_id IN (
                    SELECT id FROM actual_harvest_import_batch
                    WHERE status IN ({sealed_csv})
                )
                BEGIN
                    SELECT RAISE(ABORT, 'actual-harvest import record is immutable after seal');
                END;
                """
            )
        )


def _drop_import_record_immutability_guard() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        for trigger in (
            "trg_actual_harvest_import_record_sealed_update",
            "trg_actual_harvest_import_record_sealed_delete",
        ):
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger} ON actual_harvest_import_record"))
        op.execute(
            sa.text("DROP FUNCTION IF EXISTS actual_harvest_reject_sealed_record_mutation()")
        )
        op.execute(sa.text("DROP FUNCTION IF EXISTS actual_harvest_reject_sealed_record_delete()"))
        return
    if dialect == "sqlite":
        for trigger in (
            "trg_actual_harvest_import_record_sealed_update",
            "trg_actual_harvest_import_record_sealed_delete",
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
        sa.Column("validation_run_instance_identity_hash", sa.Text(), nullable=False),
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
        sa.UniqueConstraint("batch_id", name="uq_actual_harvest_commit_manifest_batch"),
        sa.UniqueConstraint(
            "validation_run_id",
            name="uq_actual_harvest_commit_manifest_validation_run",
        ),
        sa.UniqueConstraint("commit_manifest_hash", name="uq_actual_harvest_commit_manifest_hash"),
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
    _create_import_record_immutability_guard()


def downgrade() -> None:
    # Order matters: drop record triggers first (they reference the
    # batch table), then commit-manifest trigger/function, then the
    # manifest table itself.
    _drop_import_record_immutability_guard()
    _drop_commit_manifest_immutability_guard()
    op.drop_table("actual_harvest_commit_manifest")
