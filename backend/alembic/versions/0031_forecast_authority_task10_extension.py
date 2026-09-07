"""Split immutable base forecast authority from the later Task 10 extension."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0031_forecast_authority_task10_extension"
down_revision = "0030_prospective_forecast_authority_retention"
branch_labels = None
depends_on = None

_PARENT = "forecast_authority_capture"
_EXTENSION = "forecast_authority_task10_extension"
_SCHEMA_VERSION = "v0.3-s3-prospective-forecast-authority-v1"
_BASE_STAGE = "BASE_FORECAST"
_COMPLETE_STAGE = "TASK10_COMPLETE"


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


def _parent_stage_check() -> str:
    return (
        "(capture_stage = 'BASE_FORECAST' "
        "AND task10_training_run_id IS NULL "
        "AND task10_training_signature IS NULL "
        "AND task10_prediction_run_id IS NULL "
        "AND task10_prediction_input_signature IS NULL "
        "AND task10_prediction_hash IS NULL "
        "AND task10_binding_id IS NULL "
        "AND task10_binding_hash IS NULL "
        "AND task10_authority_hash IS NULL "
        "AND task10_snapshot IS NULL) "
        "OR (capture_stage = 'TASK10_COMPLETE' "
        "AND task10_training_run_id > 0 "
        "AND task10_training_signature IS NOT NULL "
        "AND task10_prediction_run_id > 0 "
        "AND task10_prediction_input_signature IS NOT NULL "
        "AND task10_prediction_hash IS NOT NULL "
        "AND task10_binding_id > 0 "
        "AND task10_binding_hash IS NOT NULL "
        "AND task10_authority_hash IS NOT NULL "
        "AND task10_snapshot IS NOT NULL)"
    )


def _create_extension_immutability_guard(bind: sa.engine.Connection) -> None:
    if bind.dialect.name == "sqlite":
        op.execute(
            f"""
            CREATE TRIGGER forecast_authority_task10_extension_immutable_update
            BEFORE UPDATE ON {_EXTENSION}
            BEGIN
                SELECT RAISE(ABORT, 'forecast authority Task 10 extension is immutable');
            END
            """
        )
        op.execute(
            f"""
            CREATE TRIGGER forecast_authority_task10_extension_immutable_delete
            BEFORE DELETE ON {_EXTENSION}
            BEGIN
                SELECT RAISE(ABORT, 'forecast authority Task 10 extension is immutable');
            END
            """
        )
        return

    op.execute(
        f"""
        CREATE TRIGGER forecast_authority_task10_extension_immutable
        BEFORE UPDATE OR DELETE ON {_EXTENSION}
        FOR EACH ROW EXECUTE FUNCTION forecast_authority_retention_immutable()
        """
    )


def _drop_extension_immutability_guard(bind: sa.engine.Connection) -> None:
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS forecast_authority_task10_extension_immutable_update")
        op.execute("DROP TRIGGER IF EXISTS forecast_authority_task10_extension_immutable_delete")
        return
    op.execute(
        f"DROP TRIGGER IF EXISTS forecast_authority_task10_extension_immutable ON {_EXTENSION}"
    )


def _drop_parent_daily_immutability_guards(bind: sa.engine.Connection) -> None:
    """Temporarily detach 0030 guards while the parent schema is altered."""

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
    op.execute(
        "DROP TRIGGER IF EXISTS forecast_authority_daily_immutable ON forecast_authority_daily"
    )


def _create_parent_daily_immutability_guards(bind: sa.engine.Connection) -> None:
    """Restore the 0030 guards after the parent table transition."""

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
            """
            CREATE TRIGGER forecast_authority_daily_immutable_update
            BEFORE UPDATE ON forecast_authority_daily
            BEGIN
                SELECT RAISE(ABORT, 'forecast authority daily row is immutable');
            END
            """
        )
        op.execute(
            """
            CREATE TRIGGER forecast_authority_daily_immutable_delete
            BEFORE DELETE ON forecast_authority_daily
            BEGIN
                SELECT RAISE(ABORT, 'forecast authority daily row is immutable');
            END
            """
        )
        return

    op.execute(
        f"""
        CREATE TRIGGER forecast_authority_capture_immutable
        BEFORE UPDATE OR DELETE ON {_PARENT}
        FOR EACH ROW EXECUTE FUNCTION forecast_authority_retention_immutable()
        """
    )
    op.execute(
        """
        CREATE TRIGGER forecast_authority_daily_immutable
        BEFORE UPDATE OR DELETE ON forecast_authority_daily
        FOR EACH ROW EXECUTE FUNCTION forecast_authority_retention_immutable()
        """
    )


def _alter_parent_for_postgresql(
    bind: sa.engine.Connection,
    bigint: sa.types.TypeEngine[Any],
    json_type: sa.types.TypeEngine[Any],
) -> None:
    """Alter the parent in place so the retained daily FK stays attached."""

    op.alter_column(_PARENT, "capture_stage", server_default=None)
    for column, column_type in (
        ("task10_training_run_id", bigint),
        ("task10_prediction_run_id", bigint),
        ("task10_binding_id", bigint),
        ("task10_training_signature", sa.Text()),
        ("task10_prediction_input_signature", sa.Text()),
        ("task10_prediction_hash", sa.Text()),
        ("task10_binding_hash", sa.Text()),
        ("task10_authority_hash", sa.Text()),
        ("task10_snapshot", json_type),
    ):
        op.alter_column(
            _PARENT,
            column,
            existing_type=column_type,
            nullable=True,
        )
    op.drop_constraint("ck_forecast_authority_capture_downstream_ids", _PARENT, type_="check")
    op.create_check_constraint(
        "ck_forecast_authority_capture_stage",
        _PARENT,
        "capture_stage IN ('BASE_FORECAST', 'TASK10_COMPLETE')",
    )
    op.create_check_constraint(
        "ck_forecast_authority_capture_task9_ids",
        _PARENT,
        "task9_run_id > 0",
    )
    op.create_check_constraint(
        "ck_forecast_authority_capture_task10_stage_payload",
        _PARENT,
        _parent_stage_check(),
    )


def _downgrade_parent_for_postgresql(
    bind: sa.engine.Connection,
    bigint: sa.types.TypeEngine[Any],
    json_type: sa.types.TypeEngine[Any],
) -> None:
    """Reverse the parent transition without recreating its referenced PK."""

    op.drop_constraint(
        "ck_forecast_authority_capture_task10_stage_payload",
        _PARENT,
        type_="check",
    )
    op.drop_constraint("ck_forecast_authority_capture_task9_ids", _PARENT, type_="check")
    op.drop_constraint("ck_forecast_authority_capture_stage", _PARENT, type_="check")
    op.create_check_constraint(
        "ck_forecast_authority_capture_downstream_ids",
        _PARENT,
        "task9_run_id > 0 AND task10_training_run_id > 0 "
        "AND task10_prediction_run_id > 0 AND task10_binding_id > 0",
    )
    for column, column_type in (
        ("task10_training_run_id", bigint),
        ("task10_prediction_run_id", bigint),
        ("task10_binding_id", bigint),
        ("task10_training_signature", sa.Text()),
        ("task10_prediction_input_signature", sa.Text()),
        ("task10_prediction_hash", sa.Text()),
        ("task10_binding_hash", sa.Text()),
        ("task10_authority_hash", sa.Text()),
        ("task10_snapshot", json_type),
    ):
        op.alter_column(
            _PARENT,
            column,
            existing_type=column_type,
            nullable=False,
        )
    op.drop_column(_PARENT, "capture_stage")


def upgrade() -> None:
    bind = op.get_bind()
    bigint = _bigint(bind)
    json_type = _json(bind)

    # PostgreSQL cannot recreate a referenced parent primary key while the
    # daily table's foreign key still depends on it.  Detach the immutable
    # guards for the short schema-transition window and restore them after
    # the in-place (PostgreSQL) or batch (SQLite) alteration.
    _drop_parent_daily_immutability_guards(bind)

    op.add_column(
        _PARENT,
        sa.Column(
            "capture_stage",
            sa.Text(),
            nullable=False,
            server_default=sa.text(f"'{_BASE_STAGE}'"),
        ),
    )
    # Rows written by revision 0030 already contain a complete Task 10 chain.
    # Preserve those rows as the legacy complete stage before installing the
    # nullable base-stage contract.
    op.execute(
        sa.text(
            f"UPDATE {_PARENT} SET capture_stage = :complete "
            "WHERE task10_training_run_id IS NOT NULL"
        ).bindparams(complete=_COMPLETE_STAGE)
    )

    if bind.dialect.name == "postgresql":
        _alter_parent_for_postgresql(bind, bigint, json_type)
    else:
        with op.batch_alter_table(_PARENT, recreate="always") as batch:
            batch.alter_column("capture_stage", server_default=None)
            for column, column_type in (
                ("task10_training_run_id", bigint),
                ("task10_prediction_run_id", bigint),
                ("task10_binding_id", bigint),
                ("task10_training_signature", sa.Text()),
                ("task10_prediction_input_signature", sa.Text()),
                ("task10_prediction_hash", sa.Text()),
                ("task10_binding_hash", sa.Text()),
                ("task10_authority_hash", sa.Text()),
                ("task10_snapshot", json_type),
            ):
                batch.alter_column(
                    column,
                    existing_type=column_type,
                    nullable=True,
                )
            batch.drop_constraint("ck_forecast_authority_capture_downstream_ids", type_="check")
            batch.create_check_constraint(
                "ck_forecast_authority_capture_stage",
                "capture_stage IN ('BASE_FORECAST', 'TASK10_COMPLETE')",
            )
            batch.create_check_constraint(
                "ck_forecast_authority_capture_task9_ids",
                "task9_run_id > 0",
            )
            batch.create_check_constraint(
                "ck_forecast_authority_capture_task10_stage_payload",
                _parent_stage_check(),
            )

    extension_columns = [
        sa.Column("id", bigint, primary_key=True, autoincrement=True),
        sa.Column("forecast_authority_capture_id", bigint, nullable=False),
        sa.Column("task10_training_run_id", bigint, nullable=False),
        sa.Column("task10_training_signature", sa.Text(), nullable=False),
        sa.Column("task10_prediction_run_id", bigint, nullable=False),
        sa.Column("task10_prediction_input_signature", sa.Text(), nullable=False),
        sa.Column("task10_prediction_hash", sa.Text(), nullable=False),
        sa.Column("task10_binding_id", bigint, nullable=False),
        sa.Column("task10_binding_hash", sa.Text(), nullable=False),
        sa.Column("task10_authority_hash", sa.Text(), nullable=False),
        sa.Column("task10_snapshot", json_type, nullable=False),
        sa.Column("base_authority_hash", sa.Text(), nullable=False),
        sa.Column("canonical_payload", json_type, nullable=False),
        sa.Column("extension_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["forecast_authority_capture_id"],
            [f"{_PARENT}.id"],
            name="fk_forecast_authority_task10_extension_capture_id",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "forecast_authority_capture_id",
            name="uq_forecast_authority_task10_extension_capture",
        ),
        sa.CheckConstraint(
            "forecast_authority_capture_id > 0",
            name="ck_forecast_authority_task10_extension_capture_positive",
        ),
        sa.CheckConstraint(
            "task10_training_run_id > 0 AND task10_prediction_run_id > 0 AND task10_binding_id > 0",
            name="ck_forecast_authority_task10_extension_ids",
        ),
        sa.CheckConstraint(
            "task10_snapshot IS NOT NULL AND canonical_payload IS NOT NULL",
            name="ck_forecast_authority_task10_extension_payload_present",
        ),
        _sha(
            bind,
            "task10_training_signature",
            "ck_forecast_authority_task10_extension_training_signature",
        ),
        _sha(
            bind,
            "task10_prediction_input_signature",
            "ck_forecast_authority_task10_extension_input_signature",
        ),
        _sha(
            bind,
            "task10_prediction_hash",
            "ck_forecast_authority_task10_extension_prediction_hash",
        ),
        _sha(
            bind,
            "task10_binding_hash",
            "ck_forecast_authority_task10_extension_binding_hash",
        ),
        _sha(
            bind,
            "task10_authority_hash",
            "ck_forecast_authority_task10_extension_authority_hash",
        ),
        _sha(
            bind,
            "base_authority_hash",
            "ck_forecast_authority_task10_extension_base_hash",
        ),
        _sha(bind, "extension_hash", "ck_forecast_authority_task10_extension_hash"),
    ]
    op.create_table(_EXTENSION, *extension_columns)
    op.create_index(
        "ix_forecast_authority_task10_extension_prediction",
        _EXTENSION,
        ["task10_prediction_run_id"],
    )
    _create_parent_daily_immutability_guards(bind)
    _create_extension_immutability_guard(bind)


def downgrade() -> None:
    bind = op.get_bind()
    _drop_extension_immutability_guard(bind)
    op.drop_index(
        "ix_forecast_authority_task10_extension_prediction",
        table_name=_EXTENSION,
    )
    op.drop_table(_EXTENSION)

    _drop_parent_daily_immutability_guards(bind)
    bigint = _bigint(bind)
    json_type = _json(bind)
    if bind.dialect.name == "postgresql":
        _downgrade_parent_for_postgresql(bind, bigint, json_type)
    else:
        with op.batch_alter_table(_PARENT, recreate="always") as batch:
            batch.drop_constraint(
                "ck_forecast_authority_capture_task10_stage_payload", type_="check"
            )
            batch.drop_constraint("ck_forecast_authority_capture_task9_ids", type_="check")
            batch.drop_constraint("ck_forecast_authority_capture_stage", type_="check")
            batch.create_check_constraint(
                "ck_forecast_authority_capture_downstream_ids",
                "task9_run_id > 0 AND task10_training_run_id > 0 "
                "AND task10_prediction_run_id > 0 AND task10_binding_id > 0",
            )
            for column, column_type in (
                ("task10_training_run_id", bigint),
                ("task10_prediction_run_id", bigint),
                ("task10_binding_id", bigint),
                ("task10_training_signature", sa.Text()),
                ("task10_prediction_input_signature", sa.Text()),
                ("task10_prediction_hash", sa.Text()),
                ("task10_binding_hash", sa.Text()),
                ("task10_authority_hash", sa.Text()),
                ("task10_snapshot", json_type),
            ):
                batch.alter_column(
                    column,
                    existing_type=column_type,
                    nullable=False,
                )
            batch.drop_column("capture_stage")
    _create_parent_daily_immutability_guards(bind)
