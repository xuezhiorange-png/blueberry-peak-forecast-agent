"""V0.6-S1 append-only point-in-time forecast data foundation."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0036_v06_pit_data_foundation"
down_revision = "0035_operational_peak_forecast_runs"
branch_labels = None
depends_on = None

_IMMUTABLE_TABLES = (
    "area_revision",
    "weather_forecast_snapshot",
    "realized_weather_observation",
    "phenology_observation",
    "forecast_run_snapshot",
    "forecast_run_snapshot_daily",
)


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
                BEGIN RAISE EXCEPTION 'V0.6 PIT record is immutable'; END; $$"""
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
                    "BEGIN SELECT RAISE(ABORT, 'V0.6 PIT record is immutable'); END"
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
        "area_revision",
        sa.Column("area_revision_id", sa.Text(), primary_key=True),
        sa.Column("base_id", sa.Text(), nullable=False),
        sa.Column("season", sa.Text(), nullable=False),
        sa.Column("area_mu", number, nullable=False),
        sa.Column("area_type", sa.Text(), nullable=False),
        sa.Column("effective_from", timestamp, nullable=False),
        sa.Column("effective_to", timestamp, nullable=True),
        sa.Column("recorded_at", timestamp, nullable=False),
        sa.Column("known_at", timestamp, nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_reference", sa.Text(), nullable=False),
        sa.Column("basis", sa.Text(), nullable=False),
        sa.Column(
            "supersedes_revision_id",
            sa.Text(),
            sa.ForeignKey("area_revision.area_revision_id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.CheckConstraint("CAST(area_mu AS NUMERIC) > 0", name="ck_area_revision_positive"),
        sa.CheckConstraint(
            "area_type IN ("
            "'REFERENCE_AREA', 'ACTUAL_PRODUCTIVE_AREA', 'PLANTED_AREA', 'PLANNED_AREA'"
            ")",
            name="ck_area_revision_type",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_area_revision_effective_range",
        ),
        sa.UniqueConstraint("payload_hash", name="uq_area_revision_payload_hash"),
    )
    op.create_index(
        "ix_area_revision_base_season_known",
        "area_revision",
        ["base_id", "season", "known_at"],
    )

    op.create_table(
        "weather_forecast_snapshot",
        sa.Column("weather_snapshot_id", sa.Text(), primary_key=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("base_id", sa.Text(), nullable=True),
        sa.Column("location_id", sa.Text(), nullable=True),
        sa.Column("issued_at", timestamp, nullable=False),
        sa.Column("fetched_at", timestamp, nullable=False),
        sa.Column("known_at", timestamp, nullable=False),
        sa.Column("valid_at", timestamp, nullable=False),
        sa.Column("forecast_horizon_hours", sa.Integer(), nullable=False),
        sa.Column("temperature_min", number, nullable=True),
        sa.Column("temperature_max", number, nullable=True),
        sa.Column("temperature_mean", number, nullable=True),
        sa.Column("precipitation", number, nullable=True),
        sa.Column("relative_humidity", number, nullable=True),
        sa.Column("solar_radiation", number, nullable=True),
        sa.Column("wind_speed", number, nullable=True),
        sa.Column("raw_payload_reference", sa.Text(), nullable=True),
        sa.Column("raw_payload_hash", sa.Text(), nullable=False),
        sa.Column("normalized_payload_hash", sa.Text(), nullable=False),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "forecast_horizon_hours >= 0",
            name="ck_weather_forecast_horizon_nonnegative",
        ),
        sa.CheckConstraint("issued_at <= known_at", name="ck_weather_forecast_issued_known"),
        sa.CheckConstraint(
            "base_id IS NOT NULL OR location_id IS NOT NULL",
            name="ck_weather_forecast_scope",
        ),
        sa.UniqueConstraint(
            "raw_payload_hash",
            "normalized_payload_hash",
            name="uq_weather_forecast_payload",
        ),
    )
    op.create_index(
        "ix_weather_forecast_scope_valid",
        "weather_forecast_snapshot",
        ["base_id", "valid_at"],
    )
    op.create_index("ix_weather_forecast_known", "weather_forecast_snapshot", ["known_at"])

    op.create_table(
        "realized_weather_observation",
        sa.Column("weather_observation_id", sa.Text(), primary_key=True),
        sa.Column("base_id", sa.Text(), nullable=True),
        sa.Column("location_id", sa.Text(), nullable=True),
        sa.Column("observation_time", timestamp, nullable=False),
        sa.Column("temperature", number, nullable=True),
        sa.Column("precipitation", number, nullable=True),
        sa.Column("humidity", number, nullable=True),
        sa.Column("solar_radiation", number, nullable=True),
        sa.Column("wind", number, nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_reference", sa.Text(), nullable=False),
        sa.Column("recorded_at", timestamp, nullable=False),
        sa.Column("known_at", timestamp, nullable=False),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "base_id IS NOT NULL OR location_id IS NOT NULL",
            name="ck_realized_weather_scope",
        ),
        sa.UniqueConstraint("payload_hash", name="uq_realized_weather_payload_hash"),
    )
    op.create_index(
        "ix_realized_weather_scope_time",
        "realized_weather_observation",
        ["base_id", "location_id", "observation_time"],
    )
    op.create_index("ix_realized_weather_known", "realized_weather_observation", ["known_at"])

    op.create_table(
        "phenology_observation",
        sa.Column("observation_id", sa.Text(), primary_key=True),
        sa.Column("base_id", sa.Text(), nullable=False),
        sa.Column("farm_id", sa.Text(), nullable=True),
        sa.Column("season", sa.Text(), nullable=False),
        sa.Column("phenology_stage", sa.Text(), nullable=False),
        sa.Column("observed_at", timestamp, nullable=False),
        sa.Column("recorded_at", timestamp, nullable=False),
        sa.Column("known_at", timestamp, nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_reference", sa.Text(), nullable=False),
        sa.Column("quality_status", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.UniqueConstraint("payload_hash", name="uq_phenology_observation_payload_hash"),
    )
    op.create_index(
        "ix_phenology_base_season_known",
        "phenology_observation",
        ["base_id", "season", "known_at"],
    )

    op.create_table(
        "forecast_run_snapshot",
        sa.Column("forecast_run_id", sa.Text(), primary_key=True),
        sa.Column("forecast_created_at", timestamp, nullable=False),
        sa.Column("base_id", sa.Text(), nullable=False),
        sa.Column("target_season", sa.Text(), nullable=False),
        sa.Column("forecast_start_date", sa.Date(), nullable=False),
        sa.Column("forecast_end_date", sa.Date(), nullable=False),
        sa.Column("target_area_mu", number, nullable=False),
        sa.Column("forecast_mode", sa.Text(), nullable=False),
        sa.Column("model_status", sa.Text(), nullable=False),
        sa.Column("total_model_id", sa.Text(), nullable=False),
        sa.Column("temporal_model_id", sa.Text(), nullable=False),
        sa.Column("model_artifact_hashes", document, nullable=False),
        sa.Column("prior_history_season", sa.Text(), nullable=True),
        sa.Column("prior_history_quantity_kg", number, nullable=True),
        sa.Column("prior_history_coverage_status", sa.Text(), nullable=True),
        sa.Column("prior_history_source_hash", sa.Text(), nullable=True),
        sa.Column("prior_history_identity_mapping_hash", sa.Text(), nullable=True),
        sa.Column(
            "area_revision_id",
            sa.Text(),
            sa.ForeignKey("area_revision.area_revision_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("weather_snapshot_ids", document, nullable=False),
        sa.Column("phenology_observation_ids", document, nullable=False),
        sa.Column("input_snapshot_json", document, nullable=False),
        sa.Column("input_snapshot_hash", sa.Text(), nullable=False),
        sa.Column("predicted_season_total_kg", number, nullable=False),
        sa.Column("single_day_peak", document, nullable=False),
        sa.Column("rolling_7day_peak", document, nullable=False),
        sa.Column("result_hash", sa.Text(), nullable=False),
        sa.Column("warnings", document, nullable=False),
        sa.Column("daily_row_count", sa.Integer(), nullable=False),
        sa.Column("created_at", timestamp, nullable=False),
        sa.CheckConstraint(
            "forecast_end_date >= forecast_start_date",
            name="ck_forecast_snapshot_window",
        ),
        sa.CheckConstraint(
            "CAST(target_area_mu AS NUMERIC) > 0",
            name="ck_forecast_snapshot_area",
        ),
        sa.CheckConstraint("daily_row_count >= 1", name="ck_forecast_snapshot_daily_count"),
        sa.CheckConstraint("model_status <> ''", name="ck_forecast_snapshot_model_status"),
    )
    op.create_index(
        "ix_forecast_snapshot_base_season",
        "forecast_run_snapshot",
        ["base_id", "target_season"],
    )
    op.create_index(
        "ix_forecast_snapshot_created",
        "forecast_run_snapshot",
        ["forecast_created_at", "forecast_run_id"],
    )

    op.create_table(
        "forecast_run_snapshot_daily",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "forecast_run_id",
            sa.Text(),
            sa.ForeignKey("forecast_run_snapshot.forecast_run_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("forecast_date", sa.Date(), nullable=False),
        sa.Column("predicted_quantity_kg", number, nullable=False),
        sa.Column("normalized_share", number, nullable=False),
        sa.UniqueConstraint(
            "forecast_run_id",
            "row_index",
            name="uq_forecast_snapshot_daily_index",
        ),
        sa.UniqueConstraint(
            "forecast_run_id",
            "forecast_date",
            name="uq_forecast_snapshot_daily_date",
        ),
        sa.CheckConstraint("row_index >= 0", name="ck_forecast_snapshot_daily_index"),
        sa.CheckConstraint(
            "CAST(predicted_quantity_kg AS NUMERIC) >= 0",
            name="ck_forecast_snapshot_daily_quantity",
        ),
        sa.CheckConstraint(
            "CAST(normalized_share AS NUMERIC) >= 0",
            name="ck_forecast_snapshot_daily_share",
        ),
    )

    _create_immutability_guards()


def downgrade() -> None:
    bind = op.get_bind()
    for table in _IMMUTABLE_TABLES:
        if bind.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar():
            raise RuntimeError("V06_PIT_DATA_PREVENTS_DOWNGRADE")

    _drop_immutability_guards()
    for table in (
        "forecast_run_snapshot_daily",
        "forecast_run_snapshot",
        "phenology_observation",
        "realized_weather_observation",
        "weather_forecast_snapshot",
        "area_revision",
    ):
        op.drop_table(table)
