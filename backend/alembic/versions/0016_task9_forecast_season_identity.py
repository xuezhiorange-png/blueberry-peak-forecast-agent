"""Persist Task 9 v2 forecast-season identity.

Revision ID: 0016_task9_forecast_season_identity
Revises: 0015_task11_phase3_schema_gap
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_task9_forecast_season_identity"
down_revision: str | None = "0015_task11_phase3_schema_gap"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "harvest_state_run"


def _forecast_season_column() -> sa.Column[int]:
    return sa.Column("forecast_season_id", sa.BigInteger(), nullable=True)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(_TABLE, recreate="always") as batch_op:
            batch_op.add_column(_forecast_season_column())
            batch_op.create_foreign_key(
                "fk_harvest_state_run_forecast_season_id",
                "dim_season",
                ["forecast_season_id"],
                ["id"],
                ondelete="RESTRICT",
            )
            batch_op.create_check_constraint(
                "ck_harvest_state_run_forecast_season_positive",
                "forecast_season_id IS NULL OR forecast_season_id > 0",
            )
            batch_op.create_check_constraint(
                "ck_harvest_state_run_v2_forecast_season_required",
                "result_hash_schema_version != 'task9a-result-hash-v2' "
                "OR forecast_season_id IS NOT NULL",
            )
    else:
        op.add_column(_TABLE, _forecast_season_column())
        op.create_foreign_key(
            "fk_harvest_state_run_forecast_season_id",
            _TABLE,
            "dim_season",
            ["forecast_season_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_check_constraint(
            "ck_harvest_state_run_forecast_season_positive",
            _TABLE,
            "forecast_season_id IS NULL OR forecast_season_id > 0",
        )
        op.create_check_constraint(
            "ck_harvest_state_run_v2_forecast_season_required",
            _TABLE,
            "result_hash_schema_version != 'task9a-result-hash-v2' "
            "OR forecast_season_id IS NOT NULL",
        )

    op.create_index(
        "ix_harvest_state_run_forecast_season_scope",
        _TABLE,
        [
            "forecast_season_id",
            "status",
            "destination_factory_id",
            "as_of_date",
            "forecast_end_date",
        ],
    )


def downgrade() -> None:
    bind = op.get_bind()
    v2_count = bind.execute(
        sa.text(
            "SELECT count(*) FROM harvest_state_run "
            "WHERE forecast_season_id IS NOT NULL "
            "OR result_hash_schema_version = 'task9a-result-hash-v2'"
        )
    ).scalar_one()
    if int(v2_count) != 0:
        raise RuntimeError("refuse to downgrade: Task 9 v2 forecast-season authority data exists")

    op.drop_index("ix_harvest_state_run_forecast_season_scope", table_name=_TABLE)
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(_TABLE, recreate="always") as batch_op:
            batch_op.drop_constraint(
                "ck_harvest_state_run_v2_forecast_season_required",
                type_="check",
            )
            batch_op.drop_constraint(
                "ck_harvest_state_run_forecast_season_positive",
                type_="check",
            )
            batch_op.drop_constraint(
                "fk_harvest_state_run_forecast_season_id",
                type_="foreignkey",
            )
            batch_op.drop_column("forecast_season_id")
    else:
        op.drop_constraint(
            "ck_harvest_state_run_v2_forecast_season_required",
            _TABLE,
            type_="check",
        )
        op.drop_constraint(
            "ck_harvest_state_run_forecast_season_positive",
            _TABLE,
            type_="check",
        )
        op.drop_constraint(
            "fk_harvest_state_run_forecast_season_id",
            _TABLE,
            type_="foreignkey",
        )
        op.drop_column(_TABLE, "forecast_season_id")
