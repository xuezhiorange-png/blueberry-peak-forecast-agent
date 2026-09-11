"""Separate empirical authority/forecast records; no fake Task8 foreign keys."""

import sqlalchemy as sa
from alembic import op

revision = "0033_empirical_maturity_authority"
down_revision = "0032_s4_validation_budget_durable_persistence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "empirical_maturity_authority",
        sa.Column("authority_hash", sa.String(64), primary_key=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "empirical_forecast_run",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "authority_hash",
            sa.String(64),
            sa.ForeignKey("empirical_maturity_authority.authority_hash"),
            nullable=False,
        ),
        sa.Column(
            "task9_run_id", sa.BigInteger(), sa.ForeignKey("harvest_state_run.id"), nullable=False
        ),
        sa.Column("result_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    for table in ("empirical_maturity_authority", "empirical_forecast_run"):
        if op.get_bind().dialect.name == "postgresql":
            op.execute(f"""CREATE FUNCTION {table}_immutable() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'empirical evidence is immutable'; END; $$""")
            op.execute(
                f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
                f"FOR EACH ROW EXECUTE FUNCTION {table}_immutable()"
            )
        else:
            for action in ("UPDATE", "DELETE"):
                op.execute(
                    f"CREATE TRIGGER {table}_{action.lower()} BEFORE {action} ON {table} "
                    "BEGIN SELECT RAISE(ABORT, 'empirical evidence is immutable'); END"
                )


def downgrade() -> None:
    for table in ("empirical_forecast_run", "empirical_maturity_authority"):
        op.drop_table(table)
        if op.get_bind().dialect.name == "postgresql":
            op.execute(f"DROP FUNCTION {table}_immutable()")
