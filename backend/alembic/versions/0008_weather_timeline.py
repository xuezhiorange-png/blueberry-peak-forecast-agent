"""Create task 7 weather and phenology timeline tables.

Revision ID: 0008_weather_timeline
Revises: 0007_prod_plan_phenology
Create Date: 2026-06-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_weather_timeline"
down_revision: str | None = "0007_prod_plan_phenology"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "weather_source_location",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("provider_code", sa.Text(), nullable=False),
        sa.Column("external_location_id", sa.Text(), nullable=False),
        sa.Column("location_type", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("altitude_m", sa.Numeric(8, 2), nullable=True),
        sa.Column("timezone_name", sa.Text(), nullable=False),
        sa.Column("grid_resolution", sa.Text(), nullable=True),
        sa.Column("source_version", sa.Text(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("row_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "location_type in ('station', 'grid')",
            name="ck_weather_src_loc_type",
        ),
        sa.CheckConstraint(
            "latitude >= -90 and latitude <= 90",
            name="ck_weather_src_loc_latitude",
        ),
        sa.CheckConstraint(
            "longitude >= -180 and longitude <= 180",
            name="ck_weather_src_loc_longitude",
        ),
        sa.CheckConstraint(
            "valid_to is null or valid_to >= valid_from",
            name="ck_weather_src_loc_valid_range",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider_code",
            "external_location_id",
            "source_version",
            name="uq_weather_src_loc_provider_ext_ver",
        ),
        sa.UniqueConstraint("row_hash", name="uq_weather_src_loc_row_hash"),
    )
    op.create_index(
        "ix_weather_src_loc_provider",
        "weather_source_location",
        ["provider_code"],
    )
    op.create_index(
        "ix_weather_src_loc_type",
        "weather_source_location",
        ["location_type"],
    )

    op.create_table(
        "weather_daily_observation",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("weather_source_location_id", sa.BigInteger(), nullable=False),
        sa.Column("observation_date", sa.Date(), nullable=False),
        sa.Column("temperature_min_c", sa.Numeric(12, 6), nullable=False),
        sa.Column("temperature_max_c", sa.Numeric(12, 6), nullable=False),
        sa.Column("temperature_mean_c", sa.Numeric(12, 6), nullable=True),
        sa.Column("temperature_mean_source", sa.Text(), nullable=False),
        sa.Column("precipitation_mm", sa.Numeric(12, 6), nullable=False),
        sa.Column("solar_radiation_mj_m2", sa.Numeric(12, 6), nullable=True),
        sa.Column("provider_code", sa.Text(), nullable=False),
        sa.Column("source_version", sa.Text(), nullable=False),
        sa.Column("available_at", sa.Date(), nullable=False),
        sa.Column("quality_code", sa.Text(), nullable=True),
        sa.Column("quality_flags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_file_sha256", sa.Text(), nullable=True),
        sa.Column("source_row_number", sa.BigInteger(), nullable=True),
        sa.Column("row_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "temperature_max_c >= temperature_min_c",
            name="ck_weather_daily_obs_temp_range",
        ),
        sa.CheckConstraint(
            "temperature_mean_c is null or "
            "(temperature_mean_c >= temperature_min_c "
            "and temperature_mean_c <= temperature_max_c)",
            name="ck_weather_daily_obs_mean_range",
        ),
        sa.CheckConstraint(
            "temperature_mean_source in ('provided', 'derived')",
            name="ck_weather_daily_obs_mean_source",
        ),
        sa.CheckConstraint(
            "precipitation_mm >= 0",
            name="ck_weather_daily_obs_precip_non_negative",
        ),
        sa.CheckConstraint(
            "solar_radiation_mj_m2 is null or solar_radiation_mj_m2 >= 0",
            name="ck_weather_daily_obs_solar_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["weather_source_location_id"],
            ["weather_source_location.id"],
            name="fk_weather_daily_obs_src_loc_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("row_hash", name="uq_weather_daily_obs_row_hash"),
    )
    op.create_index(
        "ix_weather_daily_obs_source_loc_id",
        "weather_daily_observation",
        ["weather_source_location_id"],
    )
    op.create_index(
        "ix_weather_daily_obs_obs_date",
        "weather_daily_observation",
        ["observation_date"],
    )
    op.create_index(
        "ix_weather_daily_obs_available_at",
        "weather_daily_observation",
        ["available_at"],
    )

    op.create_table(
        "weather_import_run",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("import_type", sa.Text(), nullable=False),
        sa.Column("provider_code", sa.Text(), nullable=True),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("file_sha256", sa.Text(), nullable=False),
        sa.Column("source_version", sa.Text(), nullable=True),
        sa.Column("dry_run", sa.Boolean(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("row_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("inserted_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("skipped_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("duplicate_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("rejected_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("invalid_date_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("invalid_numeric_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("unknown_location_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("conflict_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("report_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "import_type in ('location', 'observation', 'mapping')",
            name="ck_weather_import_run_type",
        ),
        sa.CheckConstraint(
            "status in ('running', 'completed', 'failed')",
            name="ck_weather_import_run_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "location_weather_mapping",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("location_reference_id", sa.BigInteger(), nullable=False),
        sa.Column("weather_source_location_id", sa.BigInteger(), nullable=False),
        sa.Column("mapping_method", sa.Text(), nullable=False),
        sa.Column("distance_km", sa.Numeric(12, 6), nullable=False),
        sa.Column("altitude_difference_m", sa.Numeric(12, 6), nullable=True),
        sa.Column("mapping_score", sa.Numeric(12, 6), nullable=False),
        sa.Column("confidence_level", sa.Text(), nullable=False),
        sa.Column("mapping_version", sa.Text(), nullable=False),
        sa.Column("config_hash", sa.Text(), nullable=False),
        sa.Column("available_at", sa.Date(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("row_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "mapping_method in ('explicit', 'nearest_station', 'nearest_grid')",
            name="ck_location_weather_mapping_method",
        ),
        sa.CheckConstraint(
            "distance_km >= 0",
            name="ck_location_weather_mapping_distance",
        ),
        sa.CheckConstraint(
            "mapping_score >= 0",
            name="ck_location_weather_mapping_score",
        ),
        sa.CheckConstraint(
            "valid_to is null or valid_to >= valid_from",
            name="ck_location_weather_mapping_valid_range",
        ),
        sa.ForeignKeyConstraint(
            ["location_reference_id"],
            ["location_reference.id"],
            name="fk_loc_weather_mapping_loc_ref_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["weather_source_location_id"],
            ["weather_source_location.id"],
            name="fk_loc_weather_mapping_src_loc_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("row_hash", name="uq_location_weather_mapping_row_hash"),
    )
    op.create_index(
        "ix_loc_weather_mapping_loc_ref_id",
        "location_weather_mapping",
        ["location_reference_id"],
    )
    op.create_index(
        "ix_loc_weather_mapping_src_loc_id",
        "location_weather_mapping",
        ["weather_source_location_id"],
    )
    op.create_index(
        "ix_loc_weather_mapping_available_at",
        "location_weather_mapping",
        ["available_at"],
    )

    op.create_table(
        "base_temperature_search_run",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("scope_type", sa.Text(), nullable=False),
        sa.Column("variety_id", sa.BigInteger(), nullable=True),
        sa.Column("climate_zone_id", sa.BigInteger(), nullable=True),
        sa.Column("training_cutoff", sa.Date(), nullable=False),
        sa.Column("anchor_event", sa.Text(), nullable=False),
        sa.Column("target_event", sa.Text(), nullable=False),
        sa.Column(
            "candidate_temperatures",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("selected_base_temperature", sa.Numeric(12, 6), nullable=True),
        sa.Column("scoring_method", sa.Text(), nullable=False),
        sa.Column("selected_score", sa.Numeric(12, 6), nullable=True),
        sa.Column("sample_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("distinct_season_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("training_sample_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("candidate_scores", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("config_hash", sa.Text(), nullable=False),
        sa.Column("feature_version", sa.Text(), nullable=False),
        sa.Column("source_signature", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("blockers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("input_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status in ('running', 'completed', 'failed', 'unavailable')",
            name="ck_base_temp_search_run_status",
        ),
        sa.ForeignKeyConstraint(
            ["variety_id"],
            ["dim_variety.id"],
            name="fk_base_temp_search_run_variety_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["climate_zone_id"],
            ["dim_agro_climate_zone.id"],
            name="fk_base_temp_search_run_zone_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_base_temp_search_run_active_or_done",
        "base_temperature_search_run",
        ["source_signature"],
        unique=True,
        postgresql_where=sa.text("status in ('running', 'completed', 'unavailable')"),
    )
    op.create_index(
        "ix_base_temp_search_run_variety_id",
        "base_temperature_search_run",
        ["variety_id"],
    )
    op.create_index(
        "ix_base_temp_search_run_zone_id",
        "base_temperature_search_run",
        ["climate_zone_id"],
    )

    op.create_table(
        "weather_feature_run",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("feature_version", sa.Text(), nullable=False),
        sa.Column("config_hash", sa.Text(), nullable=False),
        sa.Column("mapping_version", sa.Text(), nullable=False),
        sa.Column("weather_source_version", sa.Text(), nullable=False),
        sa.Column("base_temperature_search_run_id", sa.BigInteger(), nullable=True),
        sa.Column("plan_id", sa.BigInteger(), nullable=False),
        sa.Column("location_reference_id", sa.BigInteger(), nullable=False),
        sa.Column("location_weather_mapping_id", sa.BigInteger(), nullable=False),
        sa.Column("weather_source_location_id", sa.BigInteger(), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("feature_date", sa.Date(), nullable=False),
        sa.Column("source_signature", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("input_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("window_features", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("timeline_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "weather_observation_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("blockers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status in ('running', 'completed', 'failed', 'unavailable')",
            name="ck_weather_feature_run_status",
        ),
        sa.ForeignKeyConstraint(
            ["base_temperature_search_run_id"],
            ["base_temperature_search_run.id"],
            name="fk_weather_feature_run_base_temp_run_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["farm_season_variety_plan.id"],
            name="fk_weather_feature_run_plan_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["location_reference_id"],
            ["location_reference.id"],
            name="fk_weather_feature_run_loc_ref_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["location_weather_mapping_id"],
            ["location_weather_mapping.id"],
            name="fk_weather_feature_run_mapping_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["weather_source_location_id"],
            ["weather_source_location.id"],
            name="fk_weather_feature_run_src_loc_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_weather_feature_run_active_or_done",
        "weather_feature_run",
        ["source_signature"],
        unique=True,
        postgresql_where=sa.text("status in ('running', 'completed', 'unavailable')"),
    )
    op.create_index(
        "ix_weather_feature_run_plan_id",
        "weather_feature_run",
        ["plan_id"],
    )
    op.create_index(
        "ix_weather_feature_run_feature_date",
        "weather_feature_run",
        ["feature_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_weather_feature_run_feature_date", table_name="weather_feature_run")
    op.drop_index("ix_weather_feature_run_plan_id", table_name="weather_feature_run")
    op.drop_index("ux_weather_feature_run_active_or_done", table_name="weather_feature_run")
    op.drop_table("weather_feature_run")

    op.drop_index("ix_base_temp_search_run_zone_id", table_name="base_temperature_search_run")
    op.drop_index("ix_base_temp_search_run_variety_id", table_name="base_temperature_search_run")
    op.drop_index(
        "ux_base_temp_search_run_active_or_done",
        table_name="base_temperature_search_run",
    )
    op.drop_table("base_temperature_search_run")

    op.drop_index("ix_loc_weather_mapping_available_at", table_name="location_weather_mapping")
    op.drop_index("ix_loc_weather_mapping_src_loc_id", table_name="location_weather_mapping")
    op.drop_index("ix_loc_weather_mapping_loc_ref_id", table_name="location_weather_mapping")
    op.drop_table("location_weather_mapping")

    op.drop_table("weather_import_run")

    op.drop_index("ix_weather_daily_obs_available_at", table_name="weather_daily_observation")
    op.drop_index("ix_weather_daily_obs_obs_date", table_name="weather_daily_observation")
    op.drop_index("ix_weather_daily_obs_source_loc_id", table_name="weather_daily_observation")
    op.drop_table("weather_daily_observation")

    op.drop_index("ix_weather_src_loc_type", table_name="weather_source_location")
    op.drop_index("ix_weather_src_loc_provider", table_name="weather_source_location")
    op.drop_table("weather_source_location")
