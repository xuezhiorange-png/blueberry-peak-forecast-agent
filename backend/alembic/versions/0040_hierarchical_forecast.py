# ruff: noqa: E501
"""Append-only deterministic hierarchy reconciliation over saved Base forecasts.

SQL trigger definitions are intentionally kept verbatim on single lines.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0040_hierarchical_forecast"
down_revision = "0039_v06_s4_prospective_validation"
branch_labels = None
depends_on = None

TABLES = (
    "hierarchical_forecast_run",
    "hierarchical_forecast_daily",
    "hierarchical_forecast_source",
)


def upgrade() -> None:
    document = sa.JSON().with_variant(JSONB(), "postgresql")
    number = sa.Numeric().with_variant(sa.Text(), "sqlite")
    text_fields = (
        "status",
        "execution_hash",
        "reconciliation_policy_version",
        "hierarchy_contract_version",
        "hierarchy_authority_hash",
        "source_authority_hash",
        "target_entity_type",
        "target_entity_id",
        "target_entity_label",
        "target_season",
        "baseline_id",
        "source_policy_version",
        "quantile_or_point_label",
        "scenario_id",
        "child_base_ids_hash",
        "missing_base_ids_hash",
        "source_run_ids_hash",
        "source_result_hashes_hash",
        "result_hash",
    )
    op.create_table(
        TABLES[0],
        sa.Column("id", sa.Integer(), primary_key=True),
        *[sa.Column(name, sa.Text(), nullable=False) for name in text_fields],
        *[
            sa.Column(name, sa.DateTime(timezone=True), nullable=False)
            for name in ("created_at", "completed_at")
        ],
        *[
            sa.Column(name, sa.Date(), nullable=False)
            for name in ("origin_date", "business_season_start", "business_season_end")
        ],
        *[
            sa.Column(name, document, nullable=False)
            for name in ("hierarchy_snapshot", "request_snapshot", "result_metadata")
        ],
        *[
            sa.Column(name, sa.Integer(), nullable=False)
            for name in ("child_expected_count", "child_included_count", "daily_row_count")
        ],
        sa.Column("weather_used", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("execution_hash", name="uq_hierarchical_execution"),
        sa.CheckConstraint(
            "child_included_count > 0 AND child_expected_count >= child_included_count",
            name="ck_hierarchical_counts",
        ),
        sa.CheckConstraint(
            "(status = 'COMPLETE' AND child_expected_count = child_included_count AND daily_row_count >= 1) OR (status = 'INCOMPLETE_CHILD_COVERAGE' AND child_included_count < child_expected_count AND daily_row_count = 0)",
            name="ck_hierarchical_status",
        ),
        sa.CheckConstraint(
            "target_entity_type IN ('REGION', 'COMPANY')", name="ck_hierarchical_target"
        ),
        sa.CheckConstraint(
            "business_season_end >= business_season_start", name="ck_hierarchical_window"
        ),
    )
    op.create_index("ix_hierarchical_history", TABLES[0], ["created_at", "id"])
    op.create_index(
        "ix_hierarchical_target",
        TABLES[0],
        ["target_entity_type", "target_entity_id", "target_season"],
    )
    op.create_table(
        TABLES[1],
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey(f"{TABLES[0]}.id"), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("forecast_date", sa.Date(), nullable=False),
        sa.Column("predicted_kg", number, nullable=False),
        sa.UniqueConstraint("run_id", "row_index", name="uq_hierarchical_daily_index"),
        sa.UniqueConstraint("run_id", "forecast_date", name="uq_hierarchical_daily_date"),
        sa.CheckConstraint("row_index >= 0", name="ck_hierarchical_daily_index"),
        sa.CheckConstraint(
            "CAST(predicted_kg AS NUMERIC) >= 0", name="ck_hierarchical_daily_quantity"
        ),
    )
    op.create_table(
        TABLES[2],
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "hierarchical_run_id", sa.Integer(), sa.ForeignKey(f"{TABLES[0]}.id"), nullable=False
        ),
        sa.Column(
            "source_operational_peak_run_id",
            sa.Integer(),
            sa.ForeignKey("operational_peak_forecast_run.id"),
            nullable=False,
        ),
        *[
            sa.Column(name, sa.Text(), nullable=False)
            for name in ("base_id", "source_execution_hash", "source_result_hash")
        ],
        sa.UniqueConstraint("hierarchical_run_id", "base_id", name="uq_hierarchical_source_base"),
        sa.UniqueConstraint(
            "hierarchical_run_id",
            "source_operational_peak_run_id",
            name="uq_hierarchical_source_run",
        ),
    )
    pg = op.get_bind().dialect.name == "postgresql"
    for table in TABLES:
        if pg:
            op.execute(
                f"CREATE FUNCTION {table}_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'hierarchical forecasts are immutable'; END; $$"
            )
            op.execute(
                f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION {table}_immutable()"
            )
        else:
            for action in ("UPDATE", "DELETE"):
                op.execute(
                    f"CREATE TRIGGER {table}_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'hierarchical forecasts are immutable'); END"
                )
    daily_guard = (
        "EXISTS (SELECT 1 FROM hierarchical_forecast_run p WHERE p.id=NEW.run_id AND p.status='COMPLETE' AND NEW.row_index < p.daily_row_count AND NEW.forecast_date = "
        + (
            "p.origin_date + NEW.row_index + 1"
            if pg
            else "date(p.origin_date, '+' || (NEW.row_index+1) || ' days')"
        )
        + ")"
    )
    source_guard = "EXISTS (SELECT 1 FROM hierarchical_forecast_run p JOIN operational_peak_forecast_run s ON s.id=NEW.source_operational_peak_run_id WHERE p.id=NEW.hierarchical_run_id AND s.base_id=NEW.base_id AND s.execution_hash=NEW.source_execution_hash AND s.result_hash=NEW.source_result_hash AND (SELECT COUNT(*) FROM hierarchical_forecast_source x WHERE x.hierarchical_run_id=p.id) < p.child_included_count)"
    for table, guard in ((TABLES[1], daily_guard), (TABLES[2], source_guard)):
        name = f"{table}_insert_guard"
        if pg:
            op.execute(
                f"CREATE FUNCTION {name}() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NOT ({guard}) THEN RAISE EXCEPTION 'hierarchical child outside immutable parent contract'; END IF; RETURN NEW; END; $$"
            )
            op.execute(
                f"CREATE TRIGGER {name} BEFORE INSERT ON {table} FOR EACH ROW EXECUTE FUNCTION {name}()"
            )
        else:
            op.execute(
                f"CREATE TRIGGER {name} BEFORE INSERT ON {table} WHEN NOT ({guard}) BEGIN SELECT RAISE(ABORT, 'hierarchical child outside immutable parent contract'); END"
            )


def downgrade() -> None:
    if (
        op.get_bind()
        .execute(sa.text("SELECT COUNT(*) FROM hierarchical_forecast_run"))
        .scalar_one()
    ):
        raise RuntimeError("HIERARCHICAL_FORECAST_DATA_PREVENTS_DOWNGRADE")
    for table in reversed(TABLES):
        op.drop_table(table)
        if op.get_bind().dialect.name == "postgresql":
            op.execute(f"DROP FUNCTION {table}_immutable()")
            if table != TABLES[0]:
                op.execute(f"DROP FUNCTION {table}_insert_guard()")
