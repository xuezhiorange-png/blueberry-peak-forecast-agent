"""Persist immutable Trial Forecast creation-time evidence."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0027_s5_a2_forecast_evidence_persistence"
down_revision = "0026_s5_round_a2_policy_and_trial_resource_binding"
branch_labels = None
depends_on = None

_EVIDENCE_SCHEMA_VERSION = "v0.2-trial-forecast-evidence-v1"


def _bigint(bind: sa.engine.Connection) -> sa.types.TypeEngine:
    return sa.Integer() if bind.dialect.name == "sqlite" else sa.BigInteger()


def _sha(column: str, name: str) -> sa.CheckConstraint:
    stripped = column
    for character in "0123456789abcdef":
        stripped = f"replace({stripped}, '{character}', '')"
    return sa.CheckConstraint(
        f"length({column}) = 64 AND lower({column}) = {column} AND {stripped} = ''",
        name=name,
    )


def _non_empty(column: str, name: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(f"length(trim({column})) > 0", name=name)


def _create_immutability_guards(bind: sa.engine.Connection) -> None:
    if bind.dialect.name == "sqlite":
        op.execute(
            """
            CREATE TRIGGER trial_forecast_evidence_immutable_update
            BEFORE UPDATE ON trial_forecast_evidence
            BEGIN
                SELECT RAISE(ABORT, 'trial forecast evidence is immutable');
            END
            """
        )
        op.execute(
            """
            CREATE TRIGGER trial_forecast_evidence_immutable_delete
            BEFORE DELETE ON trial_forecast_evidence
            BEGIN
                SELECT RAISE(ABORT, 'trial forecast evidence is immutable');
            END
            """
        )
        return

    op.execute(
        """
        CREATE OR REPLACE FUNCTION trial_forecast_evidence_immutable()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'trial forecast evidence is immutable'
                USING ERRCODE = '23514';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trial_forecast_evidence_immutable
        BEFORE UPDATE OR DELETE ON trial_forecast_evidence
        FOR EACH ROW EXECUTE FUNCTION trial_forecast_evidence_immutable()
        """
    )


def _drop_immutability_guards(bind: sa.engine.Connection) -> None:
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS trial_forecast_evidence_immutable_update")
        op.execute("DROP TRIGGER IF EXISTS trial_forecast_evidence_immutable_delete")
        return

    op.execute(
        "DROP TRIGGER IF EXISTS trial_forecast_evidence_immutable ON trial_forecast_evidence"
    )
    op.execute("DROP FUNCTION IF EXISTS trial_forecast_evidence_immutable()")


def upgrade() -> None:
    bind = op.get_bind()
    bigint = _bigint(bind)
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

    op.create_table(
        "trial_forecast_evidence",
        sa.Column("id", bigint, primary_key=True, autoincrement=True),
        sa.Column("evidence_schema_version", sa.Text(), nullable=False),
        sa.Column(
            "public_forecast_id",
            sa.Text(),
            sa.ForeignKey(
                "core_forecast_run.request_hash",
                name="fk_trial_forecast_evidence_public_forecast",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("forecast_input_authority_hash", sa.Text(), nullable=False),
        sa.Column("authority_available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("farm_business_key", sa.Text(), nullable=False),
        sa.Column("subfarm_business_key_or_null", sa.Text(), nullable=True),
        sa.Column("season_business_key", sa.Text(), nullable=False),
        sa.Column("variety_business_key", sa.Text(), nullable=False),
        sa.Column("destination_factory_business_key", sa.Text(), nullable=False),
        sa.Column("plan_version", sa.Text(), nullable=False),
        sa.Column("plan_row_hash", sa.Text(), nullable=False),
        sa.Column("planting_area_mu", sa.Numeric(24, 6), nullable=False),
        sa.Column("business_scope_hash", sa.Text(), nullable=False),
        sa.Column("canonical_payload", json_type, nullable=False),
        sa.Column("forecast_evidence_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"evidence_schema_version = '{_EVIDENCE_SCHEMA_VERSION}'",
            name="ck_trial_forecast_evidence_schema_version",
        ),
        _sha("public_forecast_id", "ck_trial_forecast_evidence_public_id"),
        _sha("forecast_input_authority_hash", "ck_trial_forecast_evidence_authority_hash"),
        _sha("plan_row_hash", "ck_trial_forecast_evidence_plan_row_hash"),
        _sha("business_scope_hash", "ck_trial_forecast_evidence_scope_hash"),
        _sha("forecast_evidence_hash", "ck_trial_forecast_evidence_evidence_hash"),
        sa.CheckConstraint("id > 0", name="ck_trial_forecast_evidence_id_positive"),
        _non_empty("farm_business_key", "ck_trial_forecast_evidence_farm_nonempty"),
        sa.CheckConstraint(
            "subfarm_business_key_or_null IS NULL OR "
            "length(trim(subfarm_business_key_or_null)) > 0",
            name="ck_trial_forecast_evidence_subfarm_nonempty",
        ),
        _non_empty("season_business_key", "ck_trial_forecast_evidence_season_nonempty"),
        _non_empty("variety_business_key", "ck_trial_forecast_evidence_variety_nonempty"),
        _non_empty(
            "destination_factory_business_key",
            "ck_trial_forecast_evidence_factory_nonempty",
        ),
        _non_empty("plan_version", "ck_trial_forecast_evidence_plan_version_nonempty"),
        sa.CheckConstraint(
            "planting_area_mu >= 0",
            name="ck_trial_forecast_evidence_planting_area_nonnegative",
        ),
        sa.UniqueConstraint(
            "public_forecast_id",
            name="uq_trial_forecast_evidence_public_forecast_id",
        ),
        sa.UniqueConstraint(
            "forecast_evidence_hash",
            name="uq_trial_forecast_evidence_evidence_hash",
        ),
    )
    op.create_index(
        "ix_trial_forecast_evidence_business_scope_hash",
        "trial_forecast_evidence",
        ["business_scope_hash"],
    )
    op.create_index(
        "ix_trial_forecast_evidence_authority_hash",
        "trial_forecast_evidence",
        ["forecast_input_authority_hash"],
    )
    op.create_index(
        "ix_trial_forecast_evidence_plan_row_hash",
        "trial_forecast_evidence",
        ["plan_row_hash"],
    )
    _create_immutability_guards(bind)


def downgrade() -> None:
    bind = op.get_bind()
    _drop_immutability_guards(bind)
    op.drop_index(
        "ix_trial_forecast_evidence_plan_row_hash",
        table_name="trial_forecast_evidence",
    )
    op.drop_index(
        "ix_trial_forecast_evidence_authority_hash",
        table_name="trial_forecast_evidence",
    )
    op.drop_index(
        "ix_trial_forecast_evidence_business_scope_hash",
        table_name="trial_forecast_evidence",
    )
    op.drop_table("trial_forecast_evidence")
