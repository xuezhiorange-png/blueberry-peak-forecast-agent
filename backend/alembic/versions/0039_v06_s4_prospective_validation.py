"""V0.6-S4 prospective eligibility and weather-value authorities."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0039_v06_s4_prospective_validation"
down_revision = "0038_v06_s3_forecast_actual_evaluation"
branch_labels = None
depends_on = None

_IMMUTABLE_TABLES = (
    "prospective_validation_run",
    "weather_incremental_value_assessment",
)


def _document() -> sa.types.TypeEngine[object]:
    return sa.JSON().with_variant(JSONB(), "postgresql")


def _create_immutability_guards() -> None:
    dialect = op.get_bind().dialect.name
    for table in _IMMUTABLE_TABLES:
        if dialect == "postgresql":
            function = f"v06_{table}_immutable"
            op.execute(
                f"""CREATE FUNCTION {function}() RETURNS trigger
                LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'V0.6 S4 assessment is immutable'; END; $$"""
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
                    "BEGIN SELECT RAISE(ABORT, 'V0.6 S4 assessment is immutable'); END"
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


def _conclusion(name: str) -> sa.sql.elements.TextClause:
    return sa.text(
        f"{name} IN ('INCONCLUSIVE', 'NOT_DEMONSTRATED', 'SUPPORTED_BY_CURRENT_EVIDENCE')"
    )


def _recommendation(name: str) -> sa.sql.elements.TextClause:
    return sa.text(
        f"{name} IN ("
        "'PROCEED_TO_CONTROLLED_EXPERIMENT', "
        "'DO_NOT_PROCEED_YET', 'INSUFFICIENT_EVIDENCE')"
    )


def upgrade() -> None:
    document = _document()
    timestamp = sa.DateTime(timezone=True)

    op.create_table(
        "prospective_validation_run",
        sa.Column("validation_run_id", sa.Text(), primary_key=True),
        sa.Column("created_at", timestamp, nullable=False),
        sa.Column("policy_version", sa.Text(), nullable=False),
        sa.Column("model_a_identity", sa.Text(), nullable=False),
        sa.Column("model_a_hash", sa.Text(), nullable=False),
        sa.Column("eligible_forecast_run_ids", document, nullable=False),
        sa.Column("s3_evaluation_ids", document, nullable=False),
        sa.Column("eligibility_registry_json", document, nullable=False),
        sa.Column("sample_scope", document, nullable=False),
        sa.Column("coverage_summary", document, nullable=False),
        sa.Column("baseline_metrics", document, nullable=False),
        sa.Column("weather_quality_metrics", document, nullable=False),
        sa.Column("weather_incremental_metrics", document, nullable=False),
        sa.Column("evidence_sufficiency", document, nullable=False),
        sa.Column("weather_snapshot_authority_hashes", document, nullable=False),
        sa.Column("weather_incremental_value_conclusion", sa.Text(), nullable=False),
        sa.Column("v0_7_recommendation", sa.Text(), nullable=False),
        sa.Column("warnings", document, nullable=False),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.Column("result_hash", sa.Text(), nullable=False),
        sa.UniqueConstraint("payload_hash", name="uq_prospective_validation_payload"),
        sa.CheckConstraint(
            _conclusion("weather_incremental_value_conclusion"),
            name="ck_prospective_validation_conclusion",
        ),
        sa.CheckConstraint(
            _recommendation("v0_7_recommendation"),
            name="ck_prospective_validation_recommendation",
        ),
    )
    op.create_index(
        "ix_prospective_validation_created",
        "prospective_validation_run",
        ["created_at", "validation_run_id"],
    )

    op.create_table(
        "weather_incremental_value_assessment",
        sa.Column("assessment_id", sa.Text(), primary_key=True),
        sa.Column(
            "validation_run_id",
            sa.Text(),
            sa.ForeignKey("prospective_validation_run.validation_run_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", timestamp, nullable=False),
        sa.Column("policy_version", sa.Text(), nullable=False),
        sa.Column("model_a_identity", sa.Text(), nullable=False),
        sa.Column("model_a_hash", sa.Text(), nullable=False),
        sa.Column("weather_snapshot_authority_hashes", document, nullable=False),
        sa.Column("sample_scope", document, nullable=False),
        sa.Column("coverage_summary", document, nullable=False),
        sa.Column("baseline_metrics", document, nullable=False),
        sa.Column("weather_quality_metrics", document, nullable=False),
        sa.Column("weather_incremental_metrics", document, nullable=False),
        sa.Column("evidence_sufficiency", document, nullable=False),
        sa.Column("weather_incremental_value_conclusion", sa.Text(), nullable=False),
        sa.Column("v0_7_recommendation", sa.Text(), nullable=False),
        sa.Column("warnings", document, nullable=False),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.Column("result_hash", sa.Text(), nullable=False),
        sa.UniqueConstraint("payload_hash", name="uq_weather_incremental_payload"),
        sa.CheckConstraint(
            _conclusion("weather_incremental_value_conclusion"),
            name="ck_weather_incremental_conclusion",
        ),
        sa.CheckConstraint(
            _recommendation("v0_7_recommendation"),
            name="ck_weather_incremental_recommendation",
        ),
    )
    op.create_index(
        "ix_weather_incremental_validation",
        "weather_incremental_value_assessment",
        ["validation_run_id", "created_at"],
    )
    _create_immutability_guards()


def downgrade() -> None:
    bind = op.get_bind()
    for table in _IMMUTABLE_TABLES:
        if bind.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar():
            raise RuntimeError("V06_S4_ASSESSMENT_DATA_PREVENTS_DOWNGRADE")
    _drop_immutability_guards()
    op.drop_index(
        "ix_weather_incremental_validation", table_name="weather_incremental_value_assessment"
    )
    op.drop_table("weather_incremental_value_assessment")
    op.drop_index("ix_prospective_validation_created", table_name="prospective_validation_run")
    op.drop_table("prospective_validation_run")
