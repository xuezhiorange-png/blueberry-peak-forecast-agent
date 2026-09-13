"""Immutable area-product runs with normalized daily children."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0034_area_forecast_runs"
down_revision = "0033_empirical_maturity_authority"
branch_labels = None
depends_on = None


def upgrade() -> None:
    number = sa.Numeric().with_variant(sa.Text(), "sqlite")
    document = sa.JSON().with_variant(JSONB(), "postgresql")
    op.create_table(
        "area_forecast_run",
        sa.Column("id", sa.Integer(), primary_key=True),
        *[
            sa.Column(name, sa.Text(), nullable=False)
            for name in (
                "status",
                "forecast_policy_version",
                "model_version",
                "request_hash",
                "result_hash",
                "canonical_farm",
                "target_season",
                "total_model",
                "total_model_source_season",
                "authority_hash",
                "shape_hash",
            )
        ],
        *[
            sa.Column(name, sa.DateTime(timezone=True), nullable=False)
            for name in ("created_at", "completed_at")
        ],
        *[
            sa.Column(name, sa.Date(), nullable=False)
            for name in ("season_start", "season_end", "history_cutoff")
        ],
        *[
            sa.Column(name, number, nullable=False)
            for name in (
                "requested_productive_area_mu",
                "predicted_yield_kg_per_mu",
                "predicted_total_kg",
            )
        ],
        sa.Column("request_snapshot", document, nullable=False),
        sa.Column("result_metadata", document, nullable=False),
        sa.Column("daily_row_count", sa.Integer(), nullable=False),
        sa.Column("rerun_of_run_id", sa.Integer(), sa.ForeignKey("area_forecast_run.id")),
        sa.CheckConstraint("status = 'completed'", name="ck_area_run_completed"),
        sa.CheckConstraint("daily_row_count >= 7", name="ck_area_run_count"),
        sa.CheckConstraint("season_end >= season_start", name="ck_area_run_window"),
        sa.CheckConstraint(
            "rerun_of_run_id IS NULL OR rerun_of_run_id < id", name="ck_area_run_lineage"
        ),
        sa.UniqueConstraint("request_hash", name="uq_area_run_execution"),
    )
    for name, columns in (
        ("ix_area_run_result_hash", ["result_hash"]),
        ("ix_area_run_history", ["created_at", "id"]),
        ("ix_area_run_farm_season", ["canonical_farm", "target_season"]),
    ):
        op.create_index(name, "area_forecast_run", columns)
    op.create_table(
        "area_forecast_daily_row",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("area_forecast_run.id"), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("predicted_kg", number, nullable=False),
        sa.Column("share", number, nullable=False),
        sa.Column("share_text", sa.Text(), nullable=False),
        sa.UniqueConstraint("run_id", "row_index", name="uq_area_daily_index"),
        sa.UniqueConstraint("run_id", "date", name="uq_area_daily_date"),
        sa.CheckConstraint("row_index >= 0", name="ck_area_daily_index"),
        sa.CheckConstraint("CAST(predicted_kg AS NUMERIC) >= 0", name="ck_area_daily_quantity"),
        sa.CheckConstraint("CAST(share AS NUMERIC) >= 0", name="ck_area_daily_share"),
    )
    for table in ("area_forecast_run", "area_forecast_daily_row"):
        if op.get_bind().dialect.name == "postgresql":
            op.execute(f"""CREATE FUNCTION {table}_immutable() RETURNS trigger
                LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'area forecast runs are immutable'; END; $$""")
            op.execute(
                f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
                f"FOR EACH ROW EXECUTE FUNCTION {table}_immutable()"
            )
        else:
            for action in ("UPDATE", "DELETE"):
                op.execute(
                    f"CREATE TRIGGER {table}_{action.lower()} BEFORE {action} ON {table} "
                    "BEGIN SELECT RAISE(ABORT, 'area forecast runs are immutable'); END"
                )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION area_daily_insert_guard() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM area_forecast_run p WHERE p.id=NEW.run_id
            AND NEW.row_index < p.daily_row_count
            AND NEW.date = p.season_start + NEW.row_index) THEN
            RAISE EXCEPTION 'daily row outside immutable run calendar';
          END IF;
          RETURN NEW;
        END; $$""")
        op.execute("""CREATE TRIGGER area_daily_insert_guard
            BEFORE INSERT ON area_forecast_daily_row
            FOR EACH ROW EXECUTE FUNCTION area_daily_insert_guard()""")
    else:
        op.execute("""CREATE TRIGGER area_daily_insert_guard
        BEFORE INSERT ON area_forecast_daily_row
        WHEN NOT EXISTS (SELECT 1 FROM area_forecast_run p WHERE p.id=NEW.run_id
          AND NEW.row_index < p.daily_row_count
          AND NEW.date = date(p.season_start, '+' || NEW.row_index || ' days'))
        BEGIN SELECT RAISE(ABORT, 'daily row outside immutable run calendar'); END""")


def downgrade() -> None:
    if op.get_bind().execute(sa.text("SELECT count(*) FROM area_forecast_run")).scalar():
        raise RuntimeError("AREA_RUN_DATA_PREVENTS_DOWNGRADE")
    for table in ("area_forecast_daily_row", "area_forecast_run"):
        op.drop_table(table)
        if op.get_bind().dialect.name == "postgresql":
            op.execute(f"DROP FUNCTION {table}_immutable()")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION IF EXISTS area_daily_insert_guard()")
