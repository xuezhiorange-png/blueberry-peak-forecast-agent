"""Add the V0.2-S2 historical binding projection to rolling backtest.

Legacy ``rolling_backtest_run`` rows remain valid because every S2-only
column is nullable and all S2 constraints are conditional on the explicit
contract discriminator.  The migration does not backfill or reclassify old
runs.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0023_historical_backtest_binding"
down_revision = "0022_finalized_at_lineage_basis_member"
branch_labels = None
depends_on = None

_S2_VERSION = "v0.2-s2-historical-binding-v1"


def _json_type(is_sqlite: bool) -> sa.types.TypeEngine[object]:
    return sa.JSON() if is_sqlite else postgresql.JSONB(astext_type=sa.Text())


def _sha256_check(column_name: str) -> str:
    stripped = column_name
    for char in "0123456789abcdef":
        stripped = f"replace({stripped}, '{char}', '')"
    return (
        f"length({column_name}) = 64 and lower({column_name}) = {column_name} and {stripped} = ''"
    )


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    json_type = _json_type(is_sqlite)

    with op.batch_alter_table(
        "rolling_backtest_run",
        recreate="always" if is_sqlite else "auto",
    ) as batch_op:
        batch_op.add_column(sa.Column("s2_contract_version", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("s2_node_count", sa.BigInteger(), nullable=True))
        batch_op.add_column(sa.Column("backtest_request_payload", json_type, nullable=True))
        batch_op.add_column(sa.Column("backtest_request_hash", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("instance_hash", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("forecast_cutoff_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "label_observation_cutoff_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )
        batch_op.add_column(sa.Column("label_visibility_mode", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("master_identity_resolver_version", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("mapping_policy_version", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("resolved_identity_snapshot_hash", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("authority_selection_policy_version", sa.Text(), nullable=True)
        )
        batch_op.create_unique_constraint(
            "uq_rolling_backtest_run_request_hash", ["backtest_request_hash"]
        )
        batch_op.create_check_constraint(
            "ck_rolling_backtest_run_s2_contract_version",
            f"s2_contract_version IS NULL OR s2_contract_version = '{_S2_VERSION}'",
        )
        batch_op.create_check_constraint(
            "ck_rolling_backtest_run_s2_required_fields",
            "s2_contract_version IS NULL OR "
            "(s2_node_count = 1 AND backtest_request_payload IS NOT NULL AND "
            "backtest_request_hash IS NOT NULL AND "
            "instance_hash IS NOT NULL AND forecast_cutoff_at IS NOT NULL AND "
            "label_visibility_mode IS NOT NULL AND "
            "master_identity_resolver_version IS NOT NULL AND "
            "mapping_policy_version IS NOT NULL AND "
            "resolved_identity_snapshot_hash IS NOT NULL AND "
            "authority_selection_policy_version IS NOT NULL)",
        )
        batch_op.create_check_constraint(
            "ck_rolling_backtest_run_s2_visibility_cutoff",
            "label_visibility_mode IS NULL OR "
            "(label_visibility_mode = 'AS_OF_EVALUATION' AND "
            "label_observation_cutoff_at IS NOT NULL) OR "
            "(label_visibility_mode = 'FINAL_ADJUDICATED' AND "
            "label_observation_cutoff_at IS NULL)",
        )

    op.create_table(
        "rolling_backtest_manifest",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "rolling_run_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "rolling_backtest_run.id",
                name="fk_rolling_backtest_manifest_run_id",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("manifest_schema_version", sa.Text(), nullable=False),
        sa.Column("request_hash", sa.Text(), nullable=False),
        sa.Column("instance_hash", sa.Text(), nullable=False),
        sa.Column("coverage_manifest_payload", json_type, nullable=False),
        sa.Column("exclusion_manifest_payload", json_type, nullable=False),
        sa.Column("authority_reference_payload", json_type, nullable=False),
        sa.Column("manifest_hash", sa.Text(), nullable=False),
        sa.Column(
            "sealed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rolling_backtest_manifest"),
        sa.UniqueConstraint("rolling_run_id", name="uq_rolling_backtest_manifest_run_id"),
        sa.UniqueConstraint("manifest_hash", name="uq_rolling_backtest_manifest_hash"),
        sa.CheckConstraint(
            _sha256_check("request_hash"),
            name="ck_rolling_backtest_manifest_request_hash_sha256",
        ),
        sa.CheckConstraint(
            _sha256_check("instance_hash"),
            name="ck_rolling_backtest_manifest_instance_hash_sha256",
        ),
        sa.CheckConstraint(
            _sha256_check("manifest_hash"),
            name="ck_rolling_backtest_manifest_hash_sha256",
        ),
    )
    op.create_index(
        "ix_rolling_backtest_manifest_run_id",
        "rolling_backtest_manifest",
        ["rolling_run_id"],
    )

    op.create_table(
        "rolling_backtest_binding_row",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "rolling_run_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "rolling_backtest_run.id",
                name="fk_rolling_backtest_binding_row_run_id",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column(
            "rolling_node_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "rolling_backtest_node.id",
                name="fk_rolling_backtest_binding_row_node_id",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("forecast_cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "label_observation_cutoff_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("label_visibility_mode", sa.Text(), nullable=False),
        sa.Column("physical_alignment_status", sa.Text(), nullable=False),
        sa.Column("row_status", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.Text(), nullable=True),
        sa.Column("forecast_row_identity_hash", sa.Text(), nullable=False),
        sa.Column("actual_label_row_identity_hash", sa.Text(), nullable=True),
        sa.Column("forecast_value_kg", sa.Numeric(20, 6), nullable=False),
        sa.Column("actual_value_kg", sa.Numeric(20, 6), nullable=True),
        sa.Column("canonical_payload", json_type, nullable=False),
        sa.Column("binding_key_hash", sa.Text(), nullable=False),
        sa.Column("binding_row_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rolling_backtest_binding_row"),
        sa.UniqueConstraint(
            "rolling_run_id",
            "binding_key_hash",
            name="uq_rolling_backtest_binding_row_key",
        ),
        sa.UniqueConstraint(
            "rolling_run_id",
            "binding_row_hash",
            name="uq_rolling_backtest_binding_row_identity",
        ),
        sa.CheckConstraint(
            _sha256_check("binding_key_hash"),
            name="ck_rolling_backtest_binding_row_key_sha256",
        ),
        sa.CheckConstraint(
            _sha256_check("binding_row_hash"),
            name="ck_rolling_backtest_binding_row_hash_sha256",
        ),
        sa.CheckConstraint(
            "horizon_days in (7, 14, 21)",
            name="ck_rolling_backtest_binding_row_horizon",
        ),
        sa.CheckConstraint(
            "row_status in ('COMPARABLE', 'EXCLUDED', 'NOT_COMPUTABLE')",
            name="ck_rolling_backtest_binding_row_status",
        ),
        sa.CheckConstraint(
            "physical_alignment_status <> ''",
            name="ck_rolling_backtest_binding_row_physical_alignment",
        ),
        sa.CheckConstraint(
            "(row_status = 'COMPARABLE' AND actual_value_kg IS NOT NULL) OR "
            "(row_status <> 'COMPARABLE' AND reason_code IS NOT NULL)",
            name="ck_rolling_backtest_binding_row_semantics",
        ),
    )
    op.create_index(
        "ix_rolling_backtest_binding_row_run_id",
        "rolling_backtest_binding_row",
        ["rolling_run_id"],
    )
    op.create_index(
        "ix_rolling_backtest_binding_row_node_id",
        "rolling_backtest_binding_row",
        ["rolling_node_id"],
    )

    if not is_sqlite:
        op.execute(
            """
            CREATE OR REPLACE FUNCTION rolling_backtest_s2_immutable_row()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'rolling-backtest S2 evidence row is immutable'
                    USING ERRCODE = 'check_violation';
            END;
            $$;
            """
        )
        for table in ("rolling_backtest_manifest", "rolling_backtest_binding_row"):
            op.execute(
                f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION rolling_backtest_s2_immutable_row()"
            )
        op.execute(
            """
            CREATE OR REPLACE FUNCTION rolling_backtest_s2_binding_insert_guard()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM rolling_backtest_manifest
                    WHERE rolling_run_id = NEW.rolling_run_id
                ) THEN
                    RAISE EXCEPTION 'rolling-backtest S2 binding row cannot be inserted '
                        'after manifest seal'
                        USING ERRCODE = 'check_violation';
                END IF;
                RETURN NEW;
            END;
            $$;
            """
        )
        op.execute(
            "CREATE TRIGGER rolling_backtest_binding_row_sealed_insert_guard "
            "BEFORE INSERT ON rolling_backtest_binding_row FOR EACH ROW "
            "EXECUTE FUNCTION rolling_backtest_s2_binding_insert_guard()"
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    if not is_sqlite:
        for table in ("rolling_backtest_manifest", "rolling_backtest_binding_row"):
            op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}")
        op.execute(
            "DROP TRIGGER IF EXISTS rolling_backtest_binding_row_sealed_insert_guard "
            "ON rolling_backtest_binding_row"
        )
        op.execute("DROP FUNCTION IF EXISTS rolling_backtest_s2_binding_insert_guard()")
        op.execute("DROP FUNCTION IF EXISTS rolling_backtest_s2_immutable_row()")

    op.drop_index(
        "ix_rolling_backtest_binding_row_node_id",
        table_name="rolling_backtest_binding_row",
    )
    op.drop_index(
        "ix_rolling_backtest_binding_row_run_id",
        table_name="rolling_backtest_binding_row",
    )
    op.drop_table("rolling_backtest_binding_row")
    op.drop_index("ix_rolling_backtest_manifest_run_id", table_name="rolling_backtest_manifest")
    op.drop_table("rolling_backtest_manifest")

    with op.batch_alter_table(
        "rolling_backtest_run",
        recreate="always" if is_sqlite else "auto",
    ) as batch_op:
        batch_op.drop_constraint("uq_rolling_backtest_run_request_hash", type_="unique")
        batch_op.drop_constraint("ck_rolling_backtest_run_s2_visibility_cutoff", type_="check")
        batch_op.drop_constraint("ck_rolling_backtest_run_s2_required_fields", type_="check")
        batch_op.drop_constraint("ck_rolling_backtest_run_s2_contract_version", type_="check")
        for column in (
            "authority_selection_policy_version",
            "resolved_identity_snapshot_hash",
            "mapping_policy_version",
            "master_identity_resolver_version",
            "label_visibility_mode",
            "label_observation_cutoff_at",
            "forecast_cutoff_at",
            "instance_hash",
            "backtest_request_hash",
            "backtest_request_payload",
            "s2_node_count",
            "s2_contract_version",
        ):
            batch_op.drop_column(column)
