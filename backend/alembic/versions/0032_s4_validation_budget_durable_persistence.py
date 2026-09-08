"""Persist the canonical S4 validation-budget authority and event ledger."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0032_s4_validation_budget_durable_persistence"
down_revision = "0031_forecast_authority_task10_extension"
branch_labels = None
depends_on = None

_AUTHORITY = "s4_validation_budget_authority"
_EVENT = "s4_validation_event"
_AUTHORITY_KEY = "V0_3_S4_VALIDATION_BUDGET"
_GENESIS = "0" * 64


def _bigint(bind: sa.engine.Connection) -> sa.types.TypeEngine[Any]:
    return sa.Integer() if bind.dialect.name == "sqlite" else sa.BigInteger()


def _json(bind: sa.engine.Connection) -> sa.types.TypeEngine[Any]:
    return sa.JSON() if bind.dialect.name == "sqlite" else postgresql.JSONB()


def _sha(bind: sa.engine.Connection, column: str, name: str) -> sa.CheckConstraint:
    if bind.dialect.name == "sqlite":
        return sa.CheckConstraint(
            f"length({column}) = 64 AND lower({column}) = {column} "
            f"AND {column} NOT GLOB '*[^0-9a-f]*'",
            name=name,
        )
    return sa.CheckConstraint(
        f"{column} ~ '^[0-9a-f]{{64}}$'",
        name=name,
    )


def _json_object(bind: sa.engine.Connection, column: str, name: str) -> sa.CheckConstraint:
    expression = (
        f"json_type({column}) = 'object'"
        if bind.dialect.name == "sqlite"
        else f"jsonb_typeof({column}) = 'object'"
    )
    return sa.CheckConstraint(expression, name=name)


def _create_immutability_guard(bind: sa.engine.Connection) -> None:
    if bind.dialect.name == "sqlite":
        op.execute(
            f"""
            CREATE TRIGGER s4_validation_event_immutable_update
            BEFORE UPDATE ON {_EVENT}
            BEGIN
                SELECT RAISE(ABORT, 's4 validation event is immutable');
            END
            """
        )
        op.execute(
            f"""
            CREATE TRIGGER s4_validation_event_immutable_delete
            BEFORE DELETE ON {_EVENT}
            BEGIN
                SELECT RAISE(ABORT, 's4 validation event is immutable');
            END
            """
        )
        return

    op.execute(
        """
        CREATE OR REPLACE FUNCTION s4_validation_event_immutable()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 's4 validation event is immutable'
                USING ERRCODE = '23514';
        END;
        $$;
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER s4_validation_event_immutable
        BEFORE UPDATE OR DELETE ON {_EVENT}
        FOR EACH ROW EXECUTE FUNCTION s4_validation_event_immutable()
        """
    )


def _drop_immutability_guard(bind: sa.engine.Connection) -> None:
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS s4_validation_event_immutable_update")
        op.execute("DROP TRIGGER IF EXISTS s4_validation_event_immutable_delete")
        return
    op.execute(f"DROP TRIGGER IF EXISTS s4_validation_event_immutable ON {_EVENT}")
    op.execute("DROP FUNCTION IF EXISTS s4_validation_event_immutable()")


def upgrade() -> None:
    bind = op.get_bind()
    bigint = _bigint(bind)
    json_type = _json(bind)
    true_value = "1" if bind.dialect.name == "sqlite" else "TRUE"
    false_value = "0" if bind.dialect.name == "sqlite" else "FALSE"

    op.create_table(
        _AUTHORITY,
        sa.Column("authority_key", sa.Text(), primary_key=True),
        sa.Column("authority_version", bigint, nullable=False),
        sa.Column("accepted_event_count", bigint, nullable=False),
        sa.Column("accepted_started_count", bigint, nullable=False),
        sa.Column("accepted_head_event_hash", sa.Text(), nullable=False),
        sa.Column("accepted_last_global_evaluation_ordinal", bigint, nullable=False),
        sa.Column("legacy_reconciled_validation_debit", bigint, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "authority_version >= 0",
            name="ck_s4_validation_budget_authority_version_nonnegative",
        ),
        sa.CheckConstraint(
            "accepted_event_count >= 0",
            name="ck_s4_validation_budget_authority_event_count_nonnegative",
        ),
        sa.CheckConstraint(
            "accepted_started_count >= 0",
            name="ck_s4_validation_budget_authority_started_count_nonnegative",
        ),
        sa.CheckConstraint(
            "accepted_started_count <= accepted_event_count",
            name="ck_s4_validation_budget_authority_started_le_events",
        ),
        sa.CheckConstraint(
            "accepted_last_global_evaluation_ordinal >= 0",
            name="ck_s4_validation_budget_authority_last_ordinal_nonnegative",
        ),
        sa.CheckConstraint(
            "legacy_reconciled_validation_debit = 4",
            name="ck_s4_validation_budget_authority_legacy_debit",
        ),
        sa.CheckConstraint(
            "legacy_reconciled_validation_debit + accepted_started_count <= 32",
            name="ck_s4_validation_budget_authority_effective_budget",
        ),
        _sha(bind, "accepted_head_event_hash", "ck_s4_validation_budget_authority_head_hash"),
    )

    op.create_table(
        _EVENT,
        sa.Column("authority_key", sa.Text(), nullable=False),
        sa.Column("event_sequence", bigint, nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("evaluation_id", sa.Text(), nullable=False),
        sa.Column("candidate_id", sa.Text(), nullable=False),
        sa.Column("candidate_run_ordinal", sa.Integer(), nullable=True),
        sa.Column("global_evaluation_ordinal", bigint, nullable=True),
        sa.Column("invocation_type", sa.Text(), nullable=True),
        sa.Column("counted_toward_budget", sa.Boolean(), nullable=True),
        sa.Column("budget_count_reason", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_status", sa.Text(), nullable=True),
        sa.Column("metric_result_status", sa.Text(), nullable=True),
        sa.Column("event_payload", json_type, nullable=False),
        sa.Column("previous_event_hash", sa.Text(), nullable=False),
        sa.Column("event_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "authority_key",
            "event_sequence",
            name="pk_s4_validation_event_authority_sequence",
        ),
        sa.ForeignKeyConstraint(
            ["authority_key"],
            [_AUTHORITY + ".authority_key"],
            name="fk_s4_validation_event_authority",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "authority_key",
            "evaluation_id",
            "event_type",
            name="uq_s4_validation_event_evaluation_type",
        ),
        sa.UniqueConstraint("authority_key", "event_hash", name="uq_s4_validation_event_hash"),
        sa.CheckConstraint(
            "event_type IN ('EVALUATION_STARTED', 'EVALUATION_TERMINAL')",
            name="ck_s4_validation_event_type",
        ),
        sa.CheckConstraint("event_sequence > 0", name="ck_s4_validation_event_sequence_positive"),
        sa.CheckConstraint(
            f"(event_type = 'EVALUATION_STARTED' AND "
            "candidate_run_ordinal >= 1 AND candidate_run_ordinal <= 4 AND "
            "global_evaluation_ordinal >= 1 AND invocation_type IS NOT NULL AND "
            f"counted_toward_budget = {true_value} AND "
            "budget_count_reason = 'STARTED_INVOCATION') OR "
            "(event_type = 'EVALUATION_TERMINAL' AND "
            "candidate_run_ordinal IS NULL AND global_evaluation_ordinal IS NULL AND "
            f"invocation_type IS NULL AND counted_toward_budget = {false_value} AND "
            "budget_count_reason IS NULL)",
            name="ck_s4_validation_event_type_specific_fields",
        ),
        _json_object(bind, "event_payload", "ck_s4_validation_event_payload_object"),
        _sha(bind, "previous_event_hash", "ck_s4_validation_event_previous_hash"),
        _sha(bind, "event_hash", "ck_s4_validation_event_hash"),
    )
    op.create_index(
        "uq_s4_validation_event_started_global_ordinal",
        _EVENT,
        ["authority_key", "global_evaluation_ordinal"],
        unique=True,
        postgresql_where=sa.text("event_type = 'EVALUATION_STARTED'"),
        sqlite_where=sa.text("event_type = 'EVALUATION_STARTED'"),
    )
    op.create_index(
        "uq_s4_validation_event_started_candidate_run",
        _EVENT,
        ["authority_key", "candidate_id", "candidate_run_ordinal"],
        unique=True,
        postgresql_where=sa.text("event_type = 'EVALUATION_STARTED'"),
        sqlite_where=sa.text("event_type = 'EVALUATION_STARTED'"),
    )
    op.execute(
        sa.text(
            f"INSERT INTO {_AUTHORITY} "
            "(authority_key, authority_version, accepted_event_count, "
            "accepted_started_count, accepted_head_event_hash, "
            "accepted_last_global_evaluation_ordinal, "
            "legacy_reconciled_validation_debit) VALUES "
            "(:authority_key, 0, 0, 0, :genesis, 0, 4)"
        ).bindparams(authority_key=_AUTHORITY_KEY, genesis=_GENESIS)
    )
    _create_immutability_guard(bind)


def downgrade() -> None:
    bind = op.get_bind()
    _drop_immutability_guard(bind)
    op.drop_index("uq_s4_validation_event_started_candidate_run", table_name=_EVENT)
    op.drop_index("uq_s4_validation_event_started_global_ordinal", table_name=_EVENT)
    op.drop_table(_EVENT)
    op.drop_table(_AUTHORITY)
