"""Add A2_S policy authority and Trial resource bindings."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0026_s5_round_a2_policy_and_trial_resource_binding"
down_revision = "0025_s3_model_baseline_comparison"
branch_labels = None
depends_on = None


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


def _create_binding_immutability_guard(bind: sa.engine.Connection) -> None:
    if bind.dialect.name == "sqlite":
        op.execute(
            """
            CREATE TRIGGER trial_resource_binding_identity_immutable
            BEFORE UPDATE OF resource_kind, public_resource_id, owner_identity,
                business_scope_hash, parent_forecast_public_id, parent_import_id
            ON trial_resource_binding
            BEGIN
                SELECT RAISE(ABORT, 'trial resource binding identity is immutable');
            END
            """
        )
        return
    op.execute(
        """
        CREATE OR REPLACE FUNCTION trial_resource_binding_identity_immutable()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.resource_kind IS DISTINCT FROM OLD.resource_kind
                OR NEW.public_resource_id IS DISTINCT FROM OLD.public_resource_id
                OR NEW.owner_identity IS DISTINCT FROM OLD.owner_identity
                OR NEW.business_scope_hash IS DISTINCT FROM OLD.business_scope_hash
                OR NEW.parent_forecast_public_id IS DISTINCT FROM OLD.parent_forecast_public_id
                OR NEW.parent_import_id IS DISTINCT FROM OLD.parent_import_id
            THEN
                RAISE EXCEPTION 'trial resource binding identity is immutable'
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trial_resource_binding_identity_immutable
        BEFORE UPDATE ON trial_resource_binding
        FOR EACH ROW EXECUTE FUNCTION trial_resource_binding_identity_immutable()
        """
    )


def _drop_binding_immutability_guard(bind: sa.engine.Connection) -> None:
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS trial_resource_binding_identity_immutable")
        return
    op.execute(
        "DROP TRIGGER IF EXISTS trial_resource_binding_identity_immutable ON trial_resource_binding"
    )
    op.execute("DROP FUNCTION IF EXISTS trial_resource_binding_identity_immutable()")


def upgrade() -> None:
    bind = op.get_bind()
    bigint = _bigint(bind)

    op.create_table(
        "core_forecast_marketable_policy",
        sa.Column("id", bigint, primary_key=True, autoincrement=True),
        sa.Column("public_policy_hash", sa.Text(), nullable=False),
        sa.Column("policy_version", sa.Text(), nullable=False),
        sa.Column(
            "season_id",
            bigint,
            sa.ForeignKey("dim_season.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "factory_id",
            bigint,
            sa.ForeignKey("dim_factory.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("source_system", sa.Text(), nullable=False),
        sa.Column("source_record_key", sa.Text(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("row_set_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        _sha("public_policy_hash", "ck_core_forecast_policy_public_hash"),
        _sha("row_set_hash", "ck_core_forecast_policy_row_set_hash"),
        sa.CheckConstraint("id > 0", name="ck_core_forecast_policy_id_positive"),
        _non_empty("policy_version", "ck_core_forecast_policy_version_nonempty"),
        _non_empty("source_system", "ck_core_forecast_policy_source_nonempty"),
        _non_empty("source_record_key", "ck_core_forecast_policy_record_key_nonempty"),
        sa.CheckConstraint("season_id > 0", name="ck_core_forecast_policy_season_positive"),
        sa.CheckConstraint("factory_id > 0", name="ck_core_forecast_policy_factory_positive"),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_core_forecast_policy_date_range",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'RETIRED')",
            name="ck_core_forecast_policy_status",
        ),
        sa.UniqueConstraint("public_policy_hash", name="uq_core_forecast_policy_public_hash"),
    )
    op.create_table(
        "core_forecast_marketable_policy_entry",
        sa.Column("id", bigint, primary_key=True, autoincrement=True),
        sa.Column(
            "policy_id",
            bigint,
            sa.ForeignKey("core_forecast_marketable_policy.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "farm_id",
            bigint,
            sa.ForeignKey("dim_farm.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "subfarm_id",
            bigint,
            sa.ForeignKey("dim_subfarm.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "variety_id",
            bigint,
            sa.ForeignKey("dim_variety.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("sorting_retention_rate", sa.Numeric(24, 6), nullable=False),
        sa.Column("postharvest_retention_rate", sa.Numeric(24, 6), nullable=False),
        sa.Column("source_version", sa.Text(), nullable=False),
        sa.Column("row_hash", sa.Text(), nullable=False),
        _sha("row_hash", "ck_core_forecast_policy_entry_row_hash"),
        sa.CheckConstraint("id > 0", name="ck_core_forecast_policy_entry_id_positive"),
        _non_empty("source_version", "ck_core_forecast_policy_entry_source_version"),
        sa.CheckConstraint("policy_id > 0", name="ck_core_forecast_policy_entry_policy_positive"),
        sa.CheckConstraint("farm_id > 0", name="ck_core_forecast_policy_entry_farm_positive"),
        sa.CheckConstraint("subfarm_id > 0", name="ck_core_forecast_policy_entry_subfarm_positive"),
        sa.CheckConstraint("variety_id > 0", name="ck_core_forecast_policy_entry_variety_positive"),
        sa.CheckConstraint(
            "sorting_retention_rate >= 0 AND sorting_retention_rate <= 1",
            name="ck_core_forecast_policy_entry_sorting_rate",
        ),
        sa.CheckConstraint(
            "postharvest_retention_rate >= 0 AND postharvest_retention_rate <= 1",
            name="ck_core_forecast_policy_entry_postharvest_rate",
        ),
        sa.UniqueConstraint(
            "policy_id",
            "farm_id",
            "subfarm_id",
            "variety_id",
            name="uq_core_forecast_policy_entry_scope",
        ),
        sa.UniqueConstraint("row_hash", name="uq_core_forecast_policy_entry_row_hash"),
    )
    op.create_table(
        "trial_resource_binding",
        sa.Column("id", bigint, primary_key=True, autoincrement=True),
        sa.Column("resource_kind", sa.Text(), nullable=False),
        sa.Column("public_resource_id", sa.Text(), nullable=False),
        sa.Column("owner_identity", sa.Text(), nullable=False),
        sa.Column("business_scope_hash", sa.Text(), nullable=False),
        sa.Column("parent_forecast_public_id", sa.Text(), nullable=True),
        sa.Column(
            "parent_import_id",
            sa.Text(),
            sa.ForeignKey("actual_harvest_import_batch.import_id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        _sha("public_resource_id", "ck_trial_binding_public_resource_id"),
        _sha("business_scope_hash", "ck_trial_binding_scope_hash"),
        _sha("parent_forecast_public_id", "ck_trial_binding_parent_forecast_id"),
        sa.CheckConstraint("id > 0", name="ck_trial_binding_id_positive"),
        sa.CheckConstraint(
            "resource_kind IN ('FORECAST', 'QUALITY_REPORT')",
            name="ck_trial_binding_resource_kind",
        ),
        _non_empty("owner_identity", "ck_trial_binding_owner_nonempty"),
        sa.CheckConstraint(
            "parent_import_id IS NULL OR length(trim(parent_import_id)) > 0",
            name="ck_trial_binding_parent_import_nonempty",
        ),
        sa.CheckConstraint(
            "(resource_kind = 'FORECAST' AND parent_forecast_public_id IS NULL "
            "AND parent_import_id IS NULL) OR "
            "(resource_kind = 'QUALITY_REPORT' AND parent_forecast_public_id IS NOT NULL "
            "AND parent_import_id IS NOT NULL)",
            name="ck_trial_binding_parent_coupling",
        ),
        sa.UniqueConstraint(
            "resource_kind",
            "public_resource_id",
            name="uq_trial_binding_resource_identity",
        ),
    )

    op.create_index(
        "ix_core_forecast_policy_season_factory_status",
        "core_forecast_marketable_policy",
        ["season_id", "factory_id", "status"],
    )
    op.create_index(
        "ix_core_forecast_policy_available_at",
        "core_forecast_marketable_policy",
        ["available_at"],
    )
    op.create_index(
        "ix_core_forecast_policy_effective_range",
        "core_forecast_marketable_policy",
        ["effective_from", "effective_to"],
    )
    op.create_index(
        "ix_core_forecast_policy_entry_policy_id",
        "core_forecast_marketable_policy_entry",
        ["policy_id"],
    )
    op.create_index(
        "ix_core_forecast_policy_entry_scope",
        "core_forecast_marketable_policy_entry",
        ["farm_id", "subfarm_id", "variety_id"],
    )
    op.create_index(
        "ix_trial_binding_scoped_resource",
        "trial_resource_binding",
        ["resource_kind", "public_resource_id", "owner_identity"],
    )
    op.create_index(
        "ix_trial_binding_owner_kind", "trial_resource_binding", ["owner_identity", "resource_kind"]
    )
    op.create_index(
        "ix_trial_binding_parent_forecast", "trial_resource_binding", ["parent_forecast_public_id"]
    )
    op.create_index(
        "ix_trial_binding_parent_import", "trial_resource_binding", ["parent_import_id"]
    )
    _create_binding_immutability_guard(bind)


def downgrade() -> None:
    bind = op.get_bind()
    _drop_binding_immutability_guard(bind)
    for name, table in (
        ("ix_trial_binding_parent_import", "trial_resource_binding"),
        ("ix_trial_binding_parent_forecast", "trial_resource_binding"),
        ("ix_trial_binding_owner_kind", "trial_resource_binding"),
        ("ix_trial_binding_scoped_resource", "trial_resource_binding"),
        ("ix_core_forecast_policy_entry_scope", "core_forecast_marketable_policy_entry"),
        ("ix_core_forecast_policy_entry_policy_id", "core_forecast_marketable_policy_entry"),
        ("ix_core_forecast_policy_effective_range", "core_forecast_marketable_policy"),
        ("ix_core_forecast_policy_available_at", "core_forecast_marketable_policy"),
        ("ix_core_forecast_policy_season_factory_status", "core_forecast_marketable_policy"),
    ):
        op.drop_index(name, table_name=table)
    op.drop_table("trial_resource_binding")
    op.drop_table("core_forecast_marketable_policy_entry")
    op.drop_table("core_forecast_marketable_policy")
