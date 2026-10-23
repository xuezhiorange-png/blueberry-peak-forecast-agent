"""Immutable research-shadow rolling runs and daily rows (no actuals table)."""

import sqlalchemy as sa
from alembic import op

revision = "0041_rolling_shadow_forecast"
down_revision = "d7766e57d4c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rolling_forecast_run",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("principal_id", sa.String(200), nullable=False),
        sa.Column("context_reference", sa.String(200), nullable=False),
        sa.Column("base_id", sa.String(200), nullable=False),
        sa.Column("target_season", sa.String(9), nullable=False),
        sa.Column("origin_date", sa.Date(), nullable=False),
        sa.Column("origin_cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("result_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "rerun_of_run_id",
            sa.Integer(),
            sa.ForeignKey("rolling_forecast_run.id", ondelete="RESTRICT"),
        ),
        sa.UniqueConstraint("principal_id", "input_hash", name="uq_rolling_run_idempotency"),
        sa.CheckConstraint(
            "status IN ('COMPUTED','PARTIAL','BLOCKED')", name="ck_rolling_run_status"
        ),
    )
    op.create_index(
        "ix_rolling_run_discovery",
        "rolling_forecast_run",
        ["principal_id", "base_id", "target_season", "origin_date"],
    )
    # SQLite TEXT prevents binary float round trips; PostgreSQL uses NUMERIC.
    quantity = sa.Text() if op.get_bind().dialect.name == "sqlite" else sa.Numeric()
    op.create_table(
        "rolling_forecast_daily",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "run_id",
            sa.Integer(),
            sa.ForeignKey("rolling_forecast_run.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("model", sa.String(2), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("quantity_kg", quantity, nullable=False),
        sa.UniqueConstraint("run_id", "model", "target_date", name="uq_rolling_daily_target"),
        sa.CheckConstraint("model IN ('M0','M1')", name="ck_rolling_daily_model"),
        sa.CheckConstraint("quantity_kg >= 0", name="ck_rolling_daily_nonnegative"),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION rolling_shadow_append_only() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Rolling forecast is immutable'; END $$""")
        for table in ("rolling_forecast_run", "rolling_forecast_daily"):
            op.execute(
                f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION rolling_shadow_append_only()"
            )
    else:
        for table in ("rolling_forecast_run", "rolling_forecast_daily"):
            for action in ("UPDATE", "DELETE"):
                op.execute(
                    f"CREATE TRIGGER {table}_{action.lower()} BEFORE {action} ON {table} "
                    "BEGIN SELECT RAISE(ABORT, 'Rolling forecast is immutable'); END"
                )


def downgrade() -> None:
    op.drop_table("rolling_forecast_daily")
    op.drop_table("rolling_forecast_run")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION rolling_shadow_append_only()")
