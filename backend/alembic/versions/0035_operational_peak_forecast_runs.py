"""Immutable persisted runs for the V0.5-S6 operational peak product."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0035_operational_peak_forecast_runs"
down_revision = "0034_area_forecast_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    number = sa.Numeric().with_variant(sa.Text(), "sqlite")
    document = sa.JSON().with_variant(JSONB(), "postgresql")
    op.create_table(
        "operational_peak_forecast_run",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "completed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("execution_hash", sa.Text(), nullable=False),
        sa.Column("request_hash", sa.Text(), nullable=False),
        sa.Column("request_snapshot", document, nullable=False),
        sa.Column("result_metadata", document, nullable=False),
        sa.Column("authority_hash", sa.Text(), nullable=False),
        sa.Column("policy_version", sa.Text(), nullable=False),
        sa.Column("baseline_id", sa.Text(), nullable=False),
        sa.Column("base_id", sa.Text(), nullable=False),
        sa.Column("canonical_base_name", sa.Text(), nullable=False),
        sa.Column("productive_area_mu", number, nullable=False),
        sa.Column("target_season", sa.Text(), nullable=False),
        sa.Column("origin_date", sa.Date(), nullable=False),
        sa.Column("business_season_start", sa.Date(), nullable=False),
        sa.Column("business_season_end", sa.Date(), nullable=False),
        sa.Column("weather_used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("result_hash", sa.Text(), nullable=False),
        sa.Column("daily_row_count", sa.Integer(), nullable=False),
        sa.Column("forecast_7d", document, nullable=False),
        sa.Column("forecast_15d", document, nullable=False),
        sa.Column("remaining_business_window", document, nullable=False),
        sa.Column(
            "rerun_of_run_id",
            sa.Integer(),
            sa.ForeignKey("operational_peak_forecast_run.id"),
            nullable=True,
        ),
        sa.CheckConstraint("status = 'completed'", name="ck_operational_peak_run_completed"),
        sa.CheckConstraint("daily_row_count >= 1", name="ck_operational_peak_run_count"),
        sa.CheckConstraint(
            "business_season_end >= business_season_start",
            name="ck_operational_peak_run_window",
        ),
        sa.CheckConstraint(
            "rerun_of_run_id IS NULL OR rerun_of_run_id < id",
            name="ck_operational_peak_run_lineage",
        ),
        sa.UniqueConstraint("execution_hash", name="uq_operational_peak_execution"),
    )
    for name, columns in (
        ("ix_operational_peak_result_hash", ["result_hash"]),
        ("ix_operational_peak_history", ["created_at", "id"]),
        ("ix_operational_peak_base_season", ["base_id", "target_season"]),
    ):
        op.create_index(name, "operational_peak_forecast_run", columns)

    op.create_table(
        "operational_peak_forecast_daily",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "run_id",
            sa.Integer(),
            sa.ForeignKey("operational_peak_forecast_run.id"),
            nullable=False,
        ),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("forecast_date", sa.Date(), nullable=False),
        sa.Column("predicted_kg", number, nullable=False),
        sa.Column("kg_per_mu", number, nullable=False),
        sa.Column("business_season_day_index", sa.Integer(), nullable=False),
        sa.Column("reference_bin", sa.Integer(), nullable=False),
        sa.UniqueConstraint("run_id", "row_index", name="uq_operational_peak_daily_index"),
        sa.UniqueConstraint("run_id", "forecast_date", name="uq_operational_peak_daily_date"),
        sa.CheckConstraint("row_index >= 0", name="ck_operational_peak_daily_index"),
        sa.CheckConstraint(
            "CAST(predicted_kg AS NUMERIC) >= 0",
            name="ck_operational_peak_daily_quantity",
        ),
        sa.CheckConstraint(
            "CAST(kg_per_mu AS NUMERIC) >= 0",
            name="ck_operational_peak_daily_kg_per_mu",
        ),
    )

    for table in ("operational_peak_forecast_run", "operational_peak_forecast_daily"):
        if op.get_bind().dialect.name == "postgresql":
            op.execute(f"""CREATE FUNCTION {table}_immutable() RETURNS trigger
                LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'operational peak forecast runs are immutable'; END; $$""")
            op.execute(
                f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
                f"FOR EACH ROW EXECUTE FUNCTION {table}_immutable()"
            )
        else:
            for action in ("UPDATE", "DELETE"):
                op.execute(
                    f"CREATE TRIGGER {table}_{action.lower()} BEFORE {action} ON {table} "
                    "BEGIN SELECT RAISE(ABORT, 'operational peak forecast runs are immutable'); END"
                )

    if op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION operational_peak_daily_insert_guard() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM operational_peak_forecast_run p WHERE p.id=NEW.run_id
            AND NEW.row_index < p.daily_row_count
            AND NEW.forecast_date = p.origin_date + NEW.row_index + 1) THEN
            RAISE EXCEPTION 'daily row outside immutable operational peak run calendar';
          END IF;
          RETURN NEW;
        END; $$""")
        op.execute("""CREATE TRIGGER operational_peak_daily_insert_guard
            BEFORE INSERT ON operational_peak_forecast_daily
            FOR EACH ROW EXECUTE FUNCTION operational_peak_daily_insert_guard()""")
    else:
        op.execute("""CREATE TRIGGER operational_peak_daily_insert_guard
        BEFORE INSERT ON operational_peak_forecast_daily
        WHEN NOT EXISTS (SELECT 1 FROM operational_peak_forecast_run p WHERE p.id=NEW.run_id
          AND NEW.row_index < p.daily_row_count
          AND NEW.forecast_date = date(p.origin_date, '+' || (NEW.row_index + 1) || ' days'))
        BEGIN SELECT RAISE(ABORT,
        'daily row outside immutable operational peak run calendar'); END""")


def downgrade() -> None:
    if (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM operational_peak_forecast_run"))
        .scalar()
    ):
        raise RuntimeError("OPERATIONAL_PEAK_DATA_PREVENTS_DOWNGRADE")
    for table in ("operational_peak_forecast_daily", "operational_peak_forecast_run"):
        op.drop_table(table)
        if op.get_bind().dialect.name == "postgresql":
            op.execute(f"DROP FUNCTION {table}_immutable()")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION IF EXISTS operational_peak_daily_insert_guard()")
