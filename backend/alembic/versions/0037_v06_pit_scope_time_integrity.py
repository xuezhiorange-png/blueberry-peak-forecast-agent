"""Close V0.6-S1 PIT scope and timestamp integrity gaps."""

import re

from alembic import op

revision = "0037_v06_pit_scope_time_integrity"
down_revision = "0036_v06_pit_data_foundation"
branch_labels = None
depends_on = None

_CHECK_CONSTRAINTS = (
    ("area_revision", "ck_area_revision_recorded_known", "recorded_at <= known_at"),
    (
        "weather_forecast_snapshot",
        "ck_weather_forecast_issued_fetched",
        "issued_at <= fetched_at",
    ),
    (
        "weather_forecast_snapshot",
        "ck_weather_forecast_fetched_known",
        "fetched_at <= known_at",
    ),
    (
        "realized_weather_observation",
        "ck_realized_weather_observation_known",
        "observation_time <= known_at",
    ),
    (
        "realized_weather_observation",
        "ck_realized_weather_recorded_known",
        "recorded_at <= known_at",
    ),
    ("phenology_observation", "ck_phenology_observed_known", "observed_at <= known_at"),
    ("phenology_observation", "ck_phenology_recorded_known", "recorded_at <= known_at"),
    (
        "forecast_run_snapshot",
        "ck_forecast_snapshot_created_order",
        "forecast_created_at <= created_at",
    ),
)


def _sqlite_trigger_name(constraint_name: str) -> str:
    return f"{constraint_name}_insert"


def _sqlite_expression(expression: str) -> str:
    columns = (
        "forecast_created_at",
        "recorded_at",
        "observed_at",
        "observation_time",
        "issued_at",
        "fetched_at",
        "known_at",
        "created_at",
    )
    for column in columns:
        expression = re.sub(rf"\b{re.escape(column)}\b", f"NEW.{column}", expression)
    return expression


def _upgrade_sqlite() -> None:
    for table, constraint_name, expression in _CHECK_CONSTRAINTS:
        trigger = _sqlite_trigger_name(constraint_name)
        sqlite_expression = _sqlite_expression(expression)
        op.execute(
            f"""CREATE TRIGGER {trigger}
            BEFORE INSERT ON {table}
            WHEN NOT ({sqlite_expression})
            BEGIN
                SELECT RAISE(ABORT, 'V0.6 PIT timestamp order violation');
            END"""
        )


def _downgrade_sqlite() -> None:
    for _, constraint_name, _ in reversed(_CHECK_CONSTRAINTS):
        op.execute(f"DROP TRIGGER IF EXISTS {_sqlite_trigger_name(constraint_name)}")


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        _upgrade_sqlite()
        return
    for table, constraint_name, expression in _CHECK_CONSTRAINTS:
        op.create_check_constraint(constraint_name, table, expression)


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        _downgrade_sqlite()
        return
    for table, constraint_name, _ in reversed(_CHECK_CONSTRAINTS):
        op.drop_constraint(constraint_name, table, type_="check")
