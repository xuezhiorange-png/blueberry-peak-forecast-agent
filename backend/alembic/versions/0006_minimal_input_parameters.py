"""Create task 5 minimal input and parameter inference tables.

Revision ID: 0006_minimal_input_parameters
Revises: 0005_baseline_backtest
Create Date: 2026-06-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_minimal_input_parameters"
down_revision: str | None = "0005_baseline_backtest"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dim_agro_climate_zone",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("country", sa.Text(), nullable=False),
        sa.Column("province", sa.Text(), nullable=False),
        sa.Column("prefecture", sa.Text(), nullable=True),
        sa.Column("county", sa.Text(), nullable=True),
        sa.Column("centroid_latitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("centroid_longitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("min_altitude_m", sa.Numeric(8, 2), nullable=True),
        sa.Column("max_altitude_m", sa.Numeric(8, 2), nullable=True),
        sa.Column("zone_version", sa.Text(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.Column("source_version", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "centroid_latitude >= -90 and centroid_latitude <= 90",
            name="ck_dim_agro_climate_zone_latitude_range",
        ),
        sa.CheckConstraint(
            "centroid_longitude >= -180 and centroid_longitude <= 180",
            name="ck_dim_agro_climate_zone_longitude_range",
        ),
        sa.CheckConstraint(
            "min_altitude_m is null or max_altitude_m is null or min_altitude_m <= max_altitude_m",
            name="ck_dim_agro_climate_zone_altitude_range",
        ),
        sa.CheckConstraint(
            "valid_to is null or valid_to >= valid_from",
            name="ck_dim_agro_climate_zone_valid_range",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_dim_agro_climate_zone"),
        sa.UniqueConstraint(
            "code",
            "zone_version",
            name="uq_dim_agro_climate_zone_code_version",
        ),
    )

    op.create_table(
        "climate_zone_import_run",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("file_sha256", sa.Text(), nullable=False),
        sa.Column("zone_version", sa.Text(), nullable=True),
        sa.Column("source_name", sa.Text(), nullable=True),
        sa.Column("source_version", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("row_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("valid_row_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("invalid_row_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("inserted_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("skipped_count", sa.BigInteger(), server_default="0", nullable=False),
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
            "status in ('running', 'completed', 'failed')",
            name="ck_climate_zone_import_run_status",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_climate_zone_import_run"),
    )

    op.create_table(
        "location_reference",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("farm_id", sa.BigInteger(), nullable=True),
        sa.Column("subfarm_id", sa.BigInteger(), nullable=True),
        sa.Column("farm_code", sa.Text(), nullable=True),
        sa.Column("farm_name", sa.Text(), nullable=True),
        sa.Column("subfarm_name", sa.Text(), nullable=True),
        sa.Column("address_raw", sa.Text(), nullable=True),
        sa.Column("address_normalized", sa.Text(), nullable=False),
        sa.Column("province", sa.Text(), nullable=True),
        sa.Column("prefecture", sa.Text(), nullable=True),
        sa.Column("county", sa.Text(), nullable=True),
        sa.Column("township", sa.Text(), nullable=True),
        sa.Column("village", sa.Text(), nullable=True),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("altitude_m", sa.Numeric(8, 2), nullable=True),
        sa.Column("climate_zone_id", sa.BigInteger(), nullable=True),
        sa.Column("location_source", sa.Text(), nullable=False),
        sa.Column("source_version", sa.Text(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("source_row_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "latitude >= -90 and latitude <= 90",
            name="ck_location_reference_latitude_range",
        ),
        sa.CheckConstraint(
            "longitude >= -180 and longitude <= 180",
            name="ck_location_reference_longitude_range",
        ),
        sa.CheckConstraint(
            "valid_to is null or valid_to >= valid_from",
            name="ck_location_reference_valid_range",
        ),
        sa.ForeignKeyConstraint(
            ["farm_id"],
            ["dim_farm.id"],
            name="fk_location_reference_farm_id_dim_farm",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["subfarm_id"],
            ["dim_subfarm.id"],
            name="fk_location_reference_subfarm_id_dim_subfarm",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["climate_zone_id"],
            ["dim_agro_climate_zone.id"],
            name="fk_location_reference_climate_zone_id_dim_agro_climate_zone",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_location_reference"),
        sa.UniqueConstraint(
            "source_version",
            "source_row_hash",
            name="uq_location_reference_source_version_row_hash",
        ),
    )
    op.create_index(
        "ix_location_reference_address_normalized",
        "location_reference",
        ["address_normalized"],
    )
    op.create_index(
        "ix_location_reference_climate_zone_id",
        "location_reference",
        ["climate_zone_id"],
    )

    op.create_table(
        "parameter_library_version",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("version_code", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.Column("source_file_sha256", sa.Text(), nullable=True),
        sa.Column("config_hash", sa.Text(), nullable=False),
        sa.Column("record_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status in ('draft', 'active', 'retired', 'failed')",
            name="ck_parameter_library_version_status",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_parameter_library_version"),
        sa.UniqueConstraint(
            "version_code",
            name="uq_parameter_library_version_version_code",
        ),
    )
    op.create_index(
        "ux_parameter_library_version_active",
        "parameter_library_version",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "parameter_observation",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("library_version_id", sa.BigInteger(), nullable=False),
        sa.Column("parameter_type", sa.Text(), nullable=False),
        sa.Column("variety_id", sa.BigInteger(), nullable=False),
        sa.Column("farm_id", sa.BigInteger(), nullable=True),
        sa.Column("subfarm_id", sa.BigInteger(), nullable=True),
        sa.Column("location_reference_id", sa.BigInteger(), nullable=True),
        sa.Column("climate_zone_id", sa.BigInteger(), nullable=True),
        sa.Column("season_id", sa.BigInteger(), nullable=True),
        sa.Column("province", sa.Text(), nullable=True),
        sa.Column("prefecture", sa.Text(), nullable=True),
        sa.Column("county", sa.Text(), nullable=True),
        sa.Column("township", sa.Text(), nullable=True),
        sa.Column("altitude_m", sa.Numeric(8, 2), nullable=True),
        sa.Column("scalar_value", sa.Numeric(18, 6), nullable=False),
        sa.Column("unit", sa.Text(), nullable=False),
        sa.Column("sample_weight", sa.Numeric(18, 6), nullable=False),
        sa.Column("source_level", sa.Text(), nullable=False),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.Column("source_version", sa.Text(), nullable=False),
        sa.Column("historical_mape", sa.Numeric(12, 10), nullable=True),
        sa.Column("date_mae_days", sa.Numeric(12, 6), nullable=True),
        sa.Column("p90_coverage", sa.Numeric(12, 10), nullable=True),
        sa.Column("available_at", sa.Date(), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("source_row_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "parameter_type in ("
            "'yield_kg_per_mu',"
            " 'marketable_rate',"
            " 'first_harvest_offset_days',"
            " 'maturity_peak_offset_days',"
            " 'maturity_width_days',"
            " 'maturity_skewness',"
            " 'harvest_realization_rate'"
            ")",
            name="ck_parameter_observation_parameter_type",
        ),
        sa.CheckConstraint(
            "parameter_type != 'yield_kg_per_mu' or scalar_value > 0",
            name="ck_parameter_observation_yield_positive",
        ),
        sa.CheckConstraint(
            "parameter_type != 'marketable_rate' or (scalar_value >= 0 and scalar_value <= 1)",
            name="ck_parameter_observation_marketable_rate_range",
        ),
        sa.CheckConstraint(
            "parameter_type != 'harvest_realization_rate' "
            "or (scalar_value >= 0 and scalar_value <= 1)",
            name="ck_parameter_observation_harvest_realization_rate_range",
        ),
        sa.CheckConstraint(
            "parameter_type != 'maturity_width_days' or scalar_value > 0",
            name="ck_parameter_observation_width_positive",
        ),
        sa.CheckConstraint(
            "sample_weight > 0",
            name="ck_parameter_observation_sample_weight_positive",
        ),
        sa.CheckConstraint(
            "valid_to is null or valid_to >= valid_from",
            name="ck_parameter_observation_valid_range",
        ),
        sa.ForeignKeyConstraint(
            ["library_version_id"],
            ["parameter_library_version.id"],
            name="fk_param_obs_lib_ver_id_param_lib_ver",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["variety_id"],
            ["dim_variety.id"],
            name="fk_parameter_observation_variety_id_dim_variety",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["farm_id"],
            ["dim_farm.id"],
            name="fk_parameter_observation_farm_id_dim_farm",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["subfarm_id"],
            ["dim_subfarm.id"],
            name="fk_parameter_observation_subfarm_id_dim_subfarm",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["location_reference_id"],
            ["location_reference.id"],
            name="fk_param_obs_loc_ref_id_location_ref",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["climate_zone_id"],
            ["dim_agro_climate_zone.id"],
            name="fk_parameter_observation_climate_zone_id_dim_agro_climate_zone",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["season_id"],
            ["dim_season.id"],
            name="fk_parameter_observation_season_id_dim_season",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_parameter_observation"),
        sa.UniqueConstraint(
            "library_version_id",
            "source_row_hash",
            name="uq_parameter_observation_library_row_hash",
        ),
    )
    op.create_index(
        "ix_parameter_observation_variety_id",
        "parameter_observation",
        ["variety_id"],
    )
    op.create_index(
        "ix_parameter_observation_parameter_type",
        "parameter_observation",
        ["parameter_type"],
    )
    op.create_index(
        "ix_parameter_observation_climate_zone_id",
        "parameter_observation",
        ["climate_zone_id"],
    )

    op.create_table(
        "minimal_forecast_task",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("input_payload", postgresql.JSONB(), nullable=False),
        sa.Column("normalized_input", postgresql.JSONB(), nullable=False),
        sa.Column("input_hash", sa.Text(), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status in ('created', 'resolving_location', 'inferring_parameters', "
            "'parameters_ready', 'failed')",
            name="ck_minimal_forecast_task_status",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_minimal_forecast_task"),
        sa.UniqueConstraint(
            "input_hash",
            "as_of_date",
            name="uq_minimal_forecast_task_input_hash_as_of",
        ),
    )

    op.create_table(
        "parameter_inference_run",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("input_hash", sa.Text(), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("resolver_version", sa.Text(), nullable=False),
        sa.Column("library_version_id", sa.BigInteger(), nullable=False),
        sa.Column("config_hash", sa.Text(), nullable=False),
        sa.Column("source_signature", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status in ('running', 'completed', 'failed')",
            name="ck_parameter_inference_run_status",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["minimal_forecast_task.id"],
            name="fk_parameter_inference_run_task_id_minimal_forecast_task",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["library_version_id"],
            ["parameter_library_version.id"],
            name="fk_param_infer_run_lib_ver_id_param_lib_ver",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_parameter_inference_run"),
    )
    op.create_index(
        "ux_parameter_inference_run_active_or_completed",
        "parameter_inference_run",
        [
            "input_hash",
            "as_of_date",
            "resolver_version",
            "library_version_id",
            "config_hash",
        ],
        unique=True,
        postgresql_where=sa.text("status in ('running', 'completed')"),
    )

    op.create_table(
        "parameter_inference_result",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("variety_id", sa.BigInteger(), nullable=False),
        sa.Column("parameter_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("p50_value", sa.Numeric(18, 6), nullable=True),
        sa.Column("p80_lower", sa.Numeric(18, 6), nullable=True),
        sa.Column("p80_upper", sa.Numeric(18, 6), nullable=True),
        sa.Column("unit", sa.Text(), nullable=False),
        sa.Column("source_level", sa.Text(), nullable=True),
        sa.Column("confidence_level", sa.Text(), nullable=True),
        sa.Column("confidence_score", sa.Numeric(12, 10), nullable=True),
        sa.Column("sample_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("season_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("farm_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("source_observation_ids", postgresql.JSONB(), nullable=False),
        sa.Column("source_metadata", postgresql.JSONB(), nullable=False),
        sa.Column("uncertainty_metadata", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status in ('available', 'unavailable')",
            name="ck_parameter_inference_result_status",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["parameter_inference_run.id"],
            name="fk_parameter_inference_result_run_id_parameter_inference_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["variety_id"],
            ["dim_variety.id"],
            name="fk_parameter_inference_result_variety_id_dim_variety",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_parameter_inference_result"),
        sa.UniqueConstraint(
            "run_id",
            "variety_id",
            "parameter_type",
            name="uq_parameter_inference_result_run_variety_parameter",
        ),
    )


def downgrade() -> None:
    op.drop_table("parameter_inference_result")
    op.drop_index(
        "ux_parameter_inference_run_active_or_completed",
        table_name="parameter_inference_run",
    )
    op.drop_table("parameter_inference_run")
    op.drop_table("minimal_forecast_task")
    op.drop_index(
        "ix_parameter_observation_climate_zone_id",
        table_name="parameter_observation",
    )
    op.drop_index(
        "ix_parameter_observation_parameter_type",
        table_name="parameter_observation",
    )
    op.drop_index(
        "ix_parameter_observation_variety_id",
        table_name="parameter_observation",
    )
    op.drop_table("parameter_observation")
    op.drop_index(
        "ux_parameter_library_version_active",
        table_name="parameter_library_version",
    )
    op.drop_table("parameter_library_version")
    op.drop_index(
        "ix_location_reference_climate_zone_id",
        table_name="location_reference",
    )
    op.drop_index(
        "ix_location_reference_address_normalized",
        table_name="location_reference",
    )
    op.drop_table("location_reference")
    op.drop_table("climate_zone_import_run")
    op.drop_table("dim_agro_climate_zone")
