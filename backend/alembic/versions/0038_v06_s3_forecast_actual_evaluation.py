"""V0.6-S3 immutable forecast versus actual evaluation authority."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0038_v06_s3_forecast_actual_evaluation"
down_revision = "0037_v06_pit_scope_time_integrity"
branch_labels = None
depends_on = None

_IMMUTABLE_TABLES = ("forecast_evaluation", "forecast_evaluation_daily")


def _document() -> sa.types.TypeEngine[object]:
    return sa.JSON().with_variant(JSONB(), "postgresql")


def _number() -> sa.types.TypeEngine[object]:
    return sa.Numeric().with_variant(sa.Text(), "sqlite")


def _create_immutability_guards() -> None:
    dialect = op.get_bind().dialect.name
    for table in _IMMUTABLE_TABLES:
        if dialect == "postgresql":
            function = f"v06_{table}_immutable"
            op.execute(
                f"""CREATE FUNCTION {function}() RETURNS trigger
                LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'V0.6 S3 evaluation is immutable'; END; $$"""
            )
            op.execute(
                f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
                f"FOR EACH ROW EXECUTE FUNCTION {function}()"
            )
        else:
            for action in ("update", "delete"):
                op.execute(
                    f"CREATE TRIGGER {table}_{action}_immutable "
                    f"BEFORE {action.upper()} ON {table} "
                    "BEGIN SELECT RAISE(ABORT, 'V0.6 S3 evaluation is immutable'); END"
                )


def _drop_immutability_guards() -> None:
    dialect = op.get_bind().dialect.name
    for table in reversed(_IMMUTABLE_TABLES):
        if dialect == "postgresql":
            op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}")
            op.execute(f"DROP FUNCTION IF EXISTS v06_{table}_immutable()")
        else:
            op.execute(f"DROP TRIGGER IF EXISTS {table}_update_immutable")
            op.execute(f"DROP TRIGGER IF EXISTS {table}_delete_immutable")


def upgrade() -> None:
    document = _document()
    number = _number()
    timestamp = sa.DateTime(timezone=True)

    op.create_table(
        "forecast_evaluation",
        sa.Column("evaluation_id", sa.Text(), primary_key=True),
        sa.Column(
            "forecast_run_id",
            sa.Text(),
            sa.ForeignKey("forecast_run_snapshot.forecast_run_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("base_id", sa.Text(), nullable=False),
        sa.Column("target_season", sa.Text(), nullable=False),
        sa.Column("evaluation_mode", sa.Text(), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=True),
        sa.Column("evaluation_created_at", timestamp, nullable=False),
        sa.Column("forecast_input_hash", sa.Text(), nullable=False),
        sa.Column("forecast_result_hash", sa.Text(), nullable=False),
        sa.Column("actual_authority_ids", document, nullable=False),
        sa.Column("actual_authority_hashes", document, nullable=False),
        sa.Column("realized_weather_authority_ids", document, nullable=False),
        sa.Column("realized_weather_authority_hashes", document, nullable=False),
        sa.Column("evaluated_start_date", sa.Date(), nullable=False),
        sa.Column("evaluated_end_date", sa.Date(), nullable=False),
        sa.Column("actual_coverage_status", sa.Text(), nullable=False),
        sa.Column("season_total_metrics", document, nullable=False),
        sa.Column("daily_metrics", document, nullable=False),
        sa.Column("single_day_peak_metrics", document, nullable=False),
        sa.Column("rolling_7day_peak_metrics", document, nullable=False),
        sa.Column("weather_metrics", document, nullable=False),
        sa.Column("warnings", document, nullable=False),
        sa.Column("evaluation_payload_json", document, nullable=False),
        sa.Column("evaluation_identity_hash", sa.Text(), nullable=False),
        sa.Column("evaluation_payload_hash", sa.Text(), nullable=False),
        sa.Column("evaluation_result_hash", sa.Text(), nullable=False),
        sa.Column("daily_row_count", sa.Integer(), nullable=False),
        sa.Column("created_at", timestamp, nullable=False),
        sa.UniqueConstraint("evaluation_identity_hash", name="uq_forecast_evaluation_identity"),
        sa.CheckConstraint(
            "evaluation_mode IN ('FULL_AVAILABLE_RANGE', 'AS_OF_DATE')",
            name="ck_forecast_evaluation_mode",
        ),
        sa.CheckConstraint(
            "actual_coverage_status IN ('COMPLETE', 'PARTIAL', 'EMPTY')",
            name="ck_forecast_evaluation_coverage",
        ),
        sa.CheckConstraint("daily_row_count >= 1", name="ck_forecast_evaluation_daily_count"),
    )
    op.create_index(
        "ix_forecast_evaluation_forecast",
        "forecast_evaluation",
        ["forecast_run_id", "evaluation_created_at"],
    )
    op.create_index(
        "ix_forecast_evaluation_base_season",
        "forecast_evaluation",
        ["base_id", "target_season"],
    )

    op.create_table(
        "forecast_evaluation_daily",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "evaluation_id",
            sa.Text(),
            sa.ForeignKey("forecast_evaluation.evaluation_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("evaluation_date", sa.Date(), nullable=False),
        sa.Column("predicted_quantity_kg", number, nullable=False),
        sa.Column("actual_quantity_kg", number, nullable=True),
        sa.Column("actual_status", sa.Text(), nullable=False),
        sa.Column("actual_revision_id", sa.Text(), nullable=True),
        sa.Column("actual_source_hash", sa.Text(), nullable=True),
        sa.Column("error_kg", number, nullable=True),
        sa.Column("absolute_error_kg", number, nullable=True),
        sa.Column("evaluation_as_of", sa.Date(), nullable=True),
        sa.Column("row_hash", sa.Text(), nullable=False),
        sa.UniqueConstraint(
            "evaluation_id", "row_index", name="uq_forecast_evaluation_daily_index"
        ),
        sa.UniqueConstraint(
            "evaluation_id", "evaluation_date", name="uq_forecast_evaluation_daily_date"
        ),
        sa.CheckConstraint("row_index >= 0", name="ck_forecast_evaluation_daily_index"),
        sa.CheckConstraint(
            "actual_status IN ('CONFIRMED_QUANTITY', 'CONFIRMED_ZERO', 'MISSING')",
            name="ck_forecast_evaluation_daily_status",
        ),
        sa.CheckConstraint(
            "CAST(predicted_quantity_kg AS NUMERIC) >= 0",
            name="ck_forecast_evaluation_daily_prediction",
        ),
        sa.CheckConstraint(
            "actual_quantity_kg IS NULL OR CAST(actual_quantity_kg AS NUMERIC) >= 0",
            name="ck_forecast_evaluation_daily_actual",
        ),
    )
    op.create_index(
        "ix_forecast_evaluation_daily_date",
        "forecast_evaluation_daily",
        ["evaluation_id", "evaluation_date"],
    )
    _create_immutability_guards()


def downgrade() -> None:
    bind = op.get_bind()
    for table in _IMMUTABLE_TABLES:
        if bind.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar():
            raise RuntimeError("V06_S3_EVALUATION_DATA_PREVENTS_DOWNGRADE")
    _drop_immutability_guards()
    op.drop_index("ix_forecast_evaluation_daily_date", table_name="forecast_evaluation_daily")
    op.drop_table("forecast_evaluation_daily")
    op.drop_index("ix_forecast_evaluation_base_season", table_name="forecast_evaluation")
    op.drop_index("ix_forecast_evaluation_forecast", table_name="forecast_evaluation")
    op.drop_table("forecast_evaluation")
