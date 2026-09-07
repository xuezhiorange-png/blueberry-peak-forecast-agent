"""Retain complete prospective forecast authority for future PIT replay."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0030_prospective_forecast_authority_retention"
down_revision = "c1d4e8f2a9b3"
branch_labels = None
depends_on = None

_PARENT = "forecast_authority_capture"
_DAILY = "forecast_authority_daily"
_SCHEMA_VERSION = "v0.3-s3-prospective-forecast-authority-v1"


def _bigint(bind: sa.engine.Connection) -> sa.types.TypeEngine[Any]:
    return sa.Integer() if bind.dialect.name == "sqlite" else sa.BigInteger()


def _json(bind: sa.engine.Connection) -> sa.types.TypeEngine[Any]:
    return sa.JSON() if bind.dialect.name == "sqlite" else postgresql.JSONB()


def _sha(bind: sa.engine.Connection, column: str, name: str) -> sa.CheckConstraint:
    if bind.dialect.name == "sqlite":
        return sa.CheckConstraint(
            f"length({column}) = 64 AND {column} NOT GLOB '*[^0-9a-f]*'",
            name=name,
        )
    return sa.CheckConstraint(
        f"{column} ~ '^[0-9a-f]{{64}}$'",
        name=name,
    )


def _create_immutability_guards(bind: sa.engine.Connection) -> None:
    if bind.dialect.name == "sqlite":
        op.execute(
            f"""
            CREATE TRIGGER forecast_authority_capture_immutable_update
            BEFORE UPDATE ON {_PARENT}
            BEGIN
                SELECT RAISE(ABORT, 'forecast authority capture is immutable');
            END
            """
        )
        op.execute(
            f"""
            CREATE TRIGGER forecast_authority_capture_immutable_delete
            BEFORE DELETE ON {_PARENT}
            BEGIN
                SELECT RAISE(ABORT, 'forecast authority capture is immutable');
            END
            """
        )
        op.execute(
            f"""
            CREATE TRIGGER forecast_authority_daily_immutable_update
            BEFORE UPDATE ON {_DAILY}
            BEGIN
                SELECT RAISE(ABORT, 'forecast authority daily row is immutable');
            END
            """
        )
        op.execute(
            f"""
            CREATE TRIGGER forecast_authority_daily_immutable_delete
            BEFORE DELETE ON {_DAILY}
            BEGIN
                SELECT RAISE(ABORT, 'forecast authority daily row is immutable');
            END
            """
        )
        return

    op.execute(
        """
        CREATE OR REPLACE FUNCTION forecast_authority_retention_immutable()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'forecast authority retention is immutable'
                USING ERRCODE = '23514';
        END;
        $$;
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER forecast_authority_capture_immutable
        BEFORE UPDATE OR DELETE ON {_PARENT}
        FOR EACH ROW EXECUTE FUNCTION forecast_authority_retention_immutable()
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER forecast_authority_daily_immutable
        BEFORE UPDATE OR DELETE ON {_DAILY}
        FOR EACH ROW EXECUTE FUNCTION forecast_authority_retention_immutable()
        """
    )


def _drop_immutability_guards(bind: sa.engine.Connection) -> None:
    if bind.dialect.name == "sqlite":
        for trigger in (
            "forecast_authority_capture_immutable_update",
            "forecast_authority_capture_immutable_delete",
            "forecast_authority_daily_immutable_update",
            "forecast_authority_daily_immutable_delete",
        ):
            op.execute(f"DROP TRIGGER IF EXISTS {trigger}")
        return

    op.execute(f"DROP TRIGGER IF EXISTS forecast_authority_capture_immutable ON {_PARENT}")
    op.execute(f"DROP TRIGGER IF EXISTS forecast_authority_daily_immutable ON {_DAILY}")
    op.execute("DROP FUNCTION IF EXISTS forecast_authority_retention_immutable()")


def upgrade() -> None:
    bind = op.get_bind()
    bigint = _bigint(bind)
    json_type = _json(bind)

    parent_columns = [
        sa.Column("id", bigint, primary_key=True, autoincrement=True),
        sa.Column("authority_schema_version", sa.Text(), nullable=False),
        sa.Column("authority_scope", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("forecast_identity", sa.Text(), nullable=False),
        sa.Column("forecast_cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("forecast_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("forecast_available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("core_forecast_run_id", bigint, nullable=False),
        sa.Column("code_authority_id", bigint, nullable=False),
        sa.Column("code_authority_hash", sa.Text(), nullable=False),
        sa.Column("code_authority_available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("forecast_season_id", bigint, nullable=False),
        sa.Column("destination_factory_id", bigint, nullable=False),
        sa.Column("business_grain_hash", sa.Text(), nullable=False),
        sa.Column("business_grain_snapshot", json_type, nullable=False),
        sa.Column("plan_id", bigint, nullable=False),
        sa.Column("plan_version", sa.Integer(), nullable=False),
        sa.Column("plan_row_hash", sa.Text(), nullable=False),
        sa.Column("plan_authority_hash", sa.Text(), nullable=False),
        sa.Column("plan_snapshot", json_type, nullable=False),
        sa.Column("location_reference_id", bigint, nullable=False),
        sa.Column("weather_mapping_id", bigint, nullable=True),
        sa.Column("base_temperature_search_run_id", bigint, nullable=True),
        sa.Column("weather_authority_hash", sa.Text(), nullable=False),
        sa.Column("weather_snapshot", json_type, nullable=False),
        sa.Column("task8_forecast_run_id", bigint, nullable=False),
        sa.Column("task8_model_run_id", bigint, nullable=False),
        sa.Column("task8_artifact_id", bigint, nullable=False),
        sa.Column("task8_model_version", sa.Text(), nullable=False),
        sa.Column("task8_config_hash", sa.Text(), nullable=False),
        sa.Column("task8_artifact_hash", sa.Text(), nullable=False),
        sa.Column("task8_authority_hash", sa.Text(), nullable=False),
        sa.Column("task8_snapshot", json_type, nullable=False),
        sa.Column("task9_run_id", bigint, nullable=False),
        sa.Column("task9_result_hash", sa.Text(), nullable=False),
        sa.Column("task9_authority_hash", sa.Text(), nullable=False),
        sa.Column("task9_snapshot", json_type, nullable=False),
        sa.Column("task10_training_run_id", bigint, nullable=False),
        sa.Column("task10_training_signature", sa.Text(), nullable=False),
        sa.Column("task10_prediction_run_id", bigint, nullable=False),
        sa.Column("task10_prediction_input_signature", sa.Text(), nullable=False),
        sa.Column("task10_prediction_hash", sa.Text(), nullable=False),
        sa.Column("task10_binding_id", bigint, nullable=False),
        sa.Column("task10_binding_hash", sa.Text(), nullable=False),
        sa.Column("task10_authority_hash", sa.Text(), nullable=False),
        sa.Column("task10_snapshot", json_type, nullable=False),
        sa.Column("core_authority_hash", sa.Text(), nullable=False),
        sa.Column("core_snapshot", json_type, nullable=False),
        sa.Column("governance_snapshot", json_type, nullable=False),
        sa.Column("source_lineage_hash", sa.Text(), nullable=False),
        sa.Column("task8_daily_artifact_hash", sa.Text(), nullable=False),
        sa.Column("daily_row_count", bigint, nullable=False),
        sa.Column("canonical_payload", json_type, nullable=False),
        sa.Column("authority_identity_hash", sa.Text(), nullable=False),
        sa.Column("authority_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["core_forecast_run_id"],
            ["core_forecast_run.id"],
            name="fk_forecast_authority_capture_core_run_id",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            f"authority_schema_version = '{_SCHEMA_VERSION}'",
            name="ck_forecast_authority_capture_schema_version",
        ),
        sa.CheckConstraint(
            "authority_scope = 'PRODUCTION'",
            name="ck_forecast_authority_capture_production_scope",
        ),
        sa.CheckConstraint("status = 'CAPTURED'", name="ck_forecast_authority_capture_status"),
        sa.CheckConstraint(
            "daily_row_count > 0",
            name="ck_forecast_authority_capture_daily_count",
        ),
        sa.CheckConstraint(
            "task8_forecast_run_id > 0 AND task8_model_run_id > 0 AND task8_artifact_id > 0",
            name="ck_forecast_authority_capture_task8_ids",
        ),
        sa.CheckConstraint(
            "task9_run_id > 0 AND task10_training_run_id > 0 "
            "AND task10_prediction_run_id > 0 AND task10_binding_id > 0",
            name="ck_forecast_authority_capture_downstream_ids",
        ),
        sa.CheckConstraint("plan_id > 0", name="ck_forecast_authority_capture_plan_id"),
        sa.UniqueConstraint(
            "forecast_identity",
            name="uq_forecast_authority_capture_forecast_identity",
        ),
        sa.UniqueConstraint("core_forecast_run_id", name="uq_forecast_authority_capture_core_run"),
        sa.UniqueConstraint("authority_hash", name="uq_forecast_authority_capture_authority_hash"),
    ]
    for column, name in (
        ("forecast_identity", "ck_forecast_authority_capture_forecast_identity"),
        ("authority_identity_hash", "ck_forecast_authority_capture_authority_identity_hash"),
        ("business_grain_hash", "ck_forecast_authority_capture_business_grain_hash"),
        ("plan_row_hash", "ck_forecast_authority_capture_plan_row_hash"),
        ("plan_authority_hash", "ck_forecast_authority_capture_plan_authority_hash"),
        ("weather_authority_hash", "ck_forecast_authority_capture_weather_authority_hash"),
        ("code_authority_hash", "ck_forecast_authority_capture_code_authority_hash"),
        ("task8_config_hash", "ck_forecast_authority_capture_task8_config_hash"),
        ("task8_artifact_hash", "ck_forecast_authority_capture_task8_artifact_hash"),
        ("task8_authority_hash", "ck_forecast_authority_capture_task8_authority_hash"),
        ("task9_result_hash", "ck_forecast_authority_capture_task9_result_hash"),
        ("task9_authority_hash", "ck_forecast_authority_capture_task9_authority_hash"),
        (
            "task10_training_signature",
            "ck_forecast_authority_capture_task10_training_signature",
        ),
        (
            "task10_prediction_input_signature",
            "ck_forecast_authority_capture_task10_input_hash",
        ),
        ("task10_prediction_hash", "ck_forecast_authority_capture_task10_prediction_hash"),
        ("task10_binding_hash", "ck_forecast_authority_capture_task10_binding_hash"),
        ("task10_authority_hash", "ck_forecast_authority_capture_task10_authority_hash"),
        ("core_authority_hash", "ck_forecast_authority_capture_core_authority_hash"),
        ("source_lineage_hash", "ck_forecast_authority_capture_source_lineage_hash"),
        ("task8_daily_artifact_hash", "ck_forecast_authority_capture_daily_artifact_hash"),
        ("authority_hash", "ck_forecast_authority_capture_hash"),
    ):
        parent_columns.append(_sha(bind, column, name))
    op.create_table(_PARENT, *parent_columns)
    op.create_index(
        "ix_forecast_authority_capture_cutoff",
        _PARENT,
        ["forecast_cutoff_at"],
    )
    op.create_index(
        "ix_forecast_authority_capture_task8_run",
        _PARENT,
        ["task8_forecast_run_id"],
    )
    op.create_index(
        "ix_forecast_authority_capture_task10_prediction",
        _PARENT,
        ["task10_prediction_run_id"],
    )

    daily_columns = [
        sa.Column("id", bigint, primary_key=True, autoincrement=True),
        sa.Column("forecast_authority_capture_id", bigint, nullable=False),
        sa.Column("source_daily_prediction_id", bigint, nullable=False),
        sa.Column("forecast_run_id", bigint, nullable=False),
        sa.Column("prediction_date", sa.Date(), nullable=False),
        sa.Column("phenology_coordinate_day", sa.Numeric(12, 6), nullable=False),
        sa.Column("p50_kg", sa.Numeric(18, 6), nullable=False),
        sa.Column("p80_kg", sa.Numeric(18, 6), nullable=False),
        sa.Column("p90_kg", sa.Numeric(18, 6), nullable=False),
        sa.Column("cumulative_p50_kg", sa.Numeric(18, 6), nullable=False),
        sa.Column("cumulative_p80_kg", sa.Numeric(18, 6), nullable=False),
        sa.Column("cumulative_p90_kg", sa.Numeric(18, 6), nullable=False),
        sa.Column("curve_share", sa.Numeric(12, 10), nullable=False),
        sa.Column("confidence_level", sa.Text(), nullable=False),
        sa.Column("quality_flags", json_type, nullable=False),
        sa.Column("source_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("canonical_payload", json_type, nullable=False),
        sa.Column("row_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["forecast_authority_capture_id"],
            [f"{_PARENT}.id"],
            name="fk_forecast_authority_daily_capture_id",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "forecast_authority_capture_id",
            "prediction_date",
            name="uq_forecast_authority_daily_capture_date",
        ),
        sa.CheckConstraint(
            "p50_kg >= 0 AND p80_kg >= 0 AND p90_kg >= 0",
            name="ck_forecast_authority_daily_quantities_nonnegative",
        ),
        sa.CheckConstraint(
            "p50_kg <= p80_kg AND p80_kg <= p90_kg",
            name="ck_forecast_authority_daily_quantile_order",
        ),
        sa.CheckConstraint(
            "forecast_authority_capture_id > 0",
            name="ck_forecast_authority_daily_capture_positive",
        ),
        _sha(bind, "row_hash", "ck_forecast_authority_daily_row_hash"),
    ]
    op.create_table(_DAILY, *daily_columns)
    op.create_index(
        "ix_forecast_authority_daily_capture_date",
        _DAILY,
        ["forecast_authority_capture_id", "prediction_date"],
    )
    _create_immutability_guards(bind)


def downgrade() -> None:
    bind = op.get_bind()
    _drop_immutability_guards(bind)
    op.drop_index("ix_forecast_authority_daily_capture_date", table_name=_DAILY)
    op.drop_table(_DAILY)
    op.drop_index("ix_forecast_authority_capture_task10_prediction", table_name=_PARENT)
    op.drop_index("ix_forecast_authority_capture_task8_run", table_name=_PARENT)
    op.drop_index("ix_forecast_authority_capture_cutoff", table_name=_PARENT)
    op.drop_table(_PARENT)
