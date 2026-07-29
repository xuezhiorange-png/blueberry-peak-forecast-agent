"""Enable the V0.2-S3 Round C comparison contract.

0024 deliberately created an empty comparison table as a Round B placeholder.
This migration refuses to reinterpret any pre-existing comparison row, then
replaces that placeholder with the v2 relational projections and database
guards required by Round C.
"""

# The PostgreSQL trigger bodies are kept readable as SQL; their long
# projection predicates are intentionally not wrapped into Python strings.
# ruff: noqa: E501

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0025_s3_model_baseline_comparison"
down_revision = "0024_s3_forecast_quality_persistence"
branch_labels = None
depends_on = None

V1 = "v0.2-s3-quality-persistence-v1"
V2 = "v0.2-s3-quality-persistence-v2"
POLICY = "v0.2-s3-comparison-policy-v1"
RESULT_SCHEMA = "v0.2-s3-comparison-result-v1"
RESULT_SET_V1 = "v0.2-s3-comparison-result-set-v1"
RESULT_SET_V2 = "v0.2-s3-comparison-result-set-v2"
MEMBER_SET_SCHEMA = "v0.2-s3-comparison-baseline-member-set-v1"

METRIC_STATUS_VALUES = (
    "COMPUTED",
    "COMPARED",
    "NOT_COMPUTABLE",
    "NOT_VERIFIED",
    "INSUFFICIENT_SAMPLE",
)
REASON_CODE_VALUES = (
    "NONE",
    "NO_MAPE_ELIGIBLE_ROWS",
    "MAPE_DENOMINATOR_ZERO",
    "WAPE_DENOMINATOR_ZERO",
    "RELATIVE_BIAS_DENOMINATOR_ZERO",
    "NO_COMPLETE_7DAY_WINDOW",
    "QUANTILE_SEMANTICS_NOT_VERIFIED",
    "BELOW_MINIMUM",
    "BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED",
    "COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING",
    "SIGNED_DIRECTION_ONLY",
    "PREDICTION_INTERVAL_LOWER_BOUND_UNAVAILABLE",
    "NO_PRIOR_SEASON_ANALOG_DAY",
    "NO_PRIOR_SEASON_ANALOG_ACTUAL",
    "BASELINE_SOURCE_NOT_VISIBLE_AT_CURRENT_FORECAST_CUTOFF",
    "NO_S2_BINDING_ROWS",
)
FROZEN_LIMITATION_VALUES = (
    "BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED",
    "PREDICTION_INTERVAL_LOWER_BOUND_UNAVAILABLE",
)
COMPARISON_NAMES = (
    "daily_mae_delta",
    "daily_wape_delta",
    "daily_smape_delta",
    "daily_mape_delta",
    "absolute_bias_magnitude_delta",
    "signed_bias_delta",
    "p80_coverage_delta",
    "p90_coverage_delta",
    "baseline_p80_p90_peak_comparison",
    "interval_width_delta",
)
AXES = (
    "forecast_horizon_days",
    "farm_business_key",
    "subfarm_business_key",
    "variety_business_key",
    "season_business_key",
    "model_identity",
)
DAILY_KEY = (
    "current_target_date",
    "current_forecast_cutoff_at",
    "farm_business_key",
    "subfarm_business_key",
    "variety_business_key",
    "metric_policy_version",
    "baseline_policy_version",
)
MEMBER_KEYS = (
    "comparison_daily_key",
    "baseline_request_hash",
    "baseline_result_hash",
    "baseline_source_snapshot_identity",
    "baseline_source_snapshot_hash",
    "baseline_source_row_set_hash",
    "visibility_manifest_hash",
    "baseline_policy_version",
)


def _json_type(is_sqlite: bool) -> Any:
    return sa.JSON() if is_sqlite else postgresql.JSONB(astext_type=sa.Text())


def _bigint(is_sqlite: bool) -> Any:
    return sa.Integer() if is_sqlite else sa.BigInteger()


def _sha(column: str, name: str) -> sa.CheckConstraint:
    stripped = column
    for char in "0123456789abcdef":
        stripped = f"replace({stripped}, '{char}', '')"
    return sa.CheckConstraint(
        f"length({column}) = 64 AND lower({column}) = {column} AND {stripped} = ''",
        name=name,
    )


def _in(column: str, values: tuple[str, ...], name: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(
        f"{column} IN ({', '.join(repr(value) for value in values)})",
        name=name,
    )


def _axes_check(is_sqlite: bool) -> sa.CheckConstraint:
    if is_sqlite:
        expression = "json_type(normalized_breakdown_identity) = 'object'"
    else:
        expected = ", ".join(repr(value) for value in AXES)
        expression = (
            "jsonb_typeof(normalized_breakdown_identity) = 'object' "
            f"AND normalized_breakdown_identity ?& ARRAY[{expected}]::text[] "
            f"AND (normalized_breakdown_identity - ARRAY[{expected}]::text[]) = '{{}}'::jsonb"
        )
    return sa.CheckConstraint(expression, name="ck_model_baseline_comparison_six_axis_identity")


def _member_shape_check(is_sqlite: bool) -> sa.CheckConstraint:
    if is_sqlite:
        expression = (
            "json_type(baseline_member_identity_set) = 'array' "
            "AND json_array_length(baseline_member_identity_set) > 0"
        )
    else:
        expression = (
            "jsonb_typeof(baseline_member_identity_set) = 'array' "
            "AND jsonb_array_length(baseline_member_identity_set) > 0"
        )
    return sa.CheckConstraint(
        expression,
        name="ck_model_baseline_comparison_baseline_member_set_array",
    )


def _create_v2_comparison_table(is_sqlite: bool) -> None:
    json_type = _json_type(is_sqlite)
    bigint = _bigint(is_sqlite)
    op.create_table(
        "model_baseline_comparison",
        sa.Column("id", bigint, primary_key=True, autoincrement=True),
        sa.Column(
            "quality_evaluation_run_id",
            bigint,
            sa.ForeignKey(
                "quality_evaluation_run.id",
                name="fk_model_baseline_comparison_run",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("comparison_key_hash", sa.Text(), nullable=False),
        sa.Column("comparison_policy_version", sa.Text(), nullable=False),
        sa.Column("comparison_name", sa.Text(), nullable=False),
        sa.Column("comparison_availability", sa.Text(), nullable=False),
        sa.Column("metric_status", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.Text(), nullable=False),
        sa.Column("external_blocker", sa.Text(), nullable=True),
        sa.Column("frozen_limitation", sa.Text(), nullable=True),
        sa.Column("model_identity", sa.Text(), nullable=False),
        sa.Column("baseline_member_identity_set", json_type, nullable=False),
        sa.Column("baseline_member_set_hash", sa.Text(), nullable=False),
        sa.Column("normalized_breakdown_identity", json_type, nullable=False),
        sa.Column("forecast_horizon_days", sa.Integer(), nullable=False),
        sa.Column("model_value", sa.Numeric(20, 6), nullable=True),
        sa.Column("baseline_value", sa.Numeric(20, 6), nullable=True),
        sa.Column("delta_value", sa.Numeric(20, 6), nullable=True),
        sa.Column("model_input_row_count", bigint, nullable=False),
        sa.Column("baseline_input_row_count", bigint, nullable=False),
        sa.Column("common_comparable_row_count", bigint, nullable=False),
        sa.Column("model_only_row_count", bigint, nullable=False),
        sa.Column("baseline_only_row_count", bigint, nullable=False),
        sa.Column("excluded_row_count", bigint, nullable=False),
        sa.Column("not_computable_row_count", bigint, nullable=False),
        sa.Column("canonical_payload", json_type, nullable=False),
        sa.Column("canonical_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "quality_evaluation_run_id",
            "comparison_key_hash",
            name="uq_model_baseline_comparison_run_key",
        ),
        sa.UniqueConstraint(
            "quality_evaluation_run_id",
            "canonical_hash",
            name="uq_model_baseline_comparison_run_canonical_hash",
        ),
        _sha("comparison_key_hash", "ck_model_baseline_comparison_key_sha256"),
        _sha(
            "baseline_member_set_hash",
            "ck_model_baseline_comparison_baseline_member_set_hash_sha256",
        ),
        _sha("canonical_hash", "ck_model_baseline_comparison_canonical_sha256"),
        sa.CheckConstraint(
            "schema_version = 'v0.2-s3-quality-persistence-v2'",
            name="ck_model_baseline_comparison_schema_version_v2",
        ),
        sa.CheckConstraint(
            "comparison_policy_version = 'v0.2-s3-comparison-policy-v1'",
            name="ck_model_baseline_comparison_policy_version_v2",
        ),
        _in(
            "comparison_name",
            COMPARISON_NAMES,
            "ck_model_baseline_comparison_name_vocabulary",
        ),
        sa.CheckConstraint(
            "comparison_availability IN ('AVAILABLE', 'BLOCKED')",
            name="ck_model_baseline_comparison_availability_vocabulary",
        ),
        _in(
            "metric_status",
            METRIC_STATUS_VALUES,
            "ck_model_baseline_comparison_metric_status_vocabulary",
        ),
        _in(
            "reason_code",
            REASON_CODE_VALUES,
            "ck_model_baseline_comparison_reason_code_vocabulary",
        ),
        sa.CheckConstraint(
            "forecast_horizon_days > 0",
            name="ck_model_baseline_comparison_forecast_horizon_positive",
        ),
        sa.CheckConstraint(
            "model_input_row_count >= 0 AND baseline_input_row_count >= 0 "
            "AND common_comparable_row_count >= 0 AND model_only_row_count >= 0 "
            "AND baseline_only_row_count >= 0 AND excluded_row_count >= 0 "
            "AND not_computable_row_count >= 0",
            name="ck_model_baseline_comparison_counters_nonnegative",
        ),
        sa.CheckConstraint(
            "common_comparable_row_count <= model_input_row_count "
            "AND common_comparable_row_count <= baseline_input_row_count",
            name="ck_model_baseline_comparison_counter_bounds",
        ),
        _member_shape_check(is_sqlite),
        sa.CheckConstraint(
            "json_type(baseline_member_identity_set) IS NOT NULL"
            if is_sqlite
            else "jsonb_typeof(baseline_member_identity_set) = 'array'",
            name="ck_model_baseline_comparison_baseline_member_set_nonempty",
        ),
        sa.CheckConstraint(
            "json_type(normalized_breakdown_identity) IS NOT NULL"
            if is_sqlite
            else "jsonb_typeof(normalized_breakdown_identity) = 'object'",
            name="ck_model_baseline_comparison_baseline_member_shape",
        ),
        _axes_check(is_sqlite),
        sa.CheckConstraint(
            "normalized_breakdown_identity IS NOT NULL",
            name="ck_model_baseline_comparison_identity_projection",
        ),
        sa.CheckConstraint(
            "normalized_breakdown_identity->>'model_identity' = model_identity"
            if not is_sqlite
            else "json_extract(normalized_breakdown_identity, '$.model_identity') = model_identity",
            name="ck_model_baseline_comparison_model_identity_projection",
        ),
        sa.CheckConstraint(
            "(normalized_breakdown_identity->>'forecast_horizon_days')::integer = "
            "forecast_horizon_days"
            if not is_sqlite
            else "CAST(json_extract(normalized_breakdown_identity, "
            "'$.forecast_horizon_days') AS INTEGER) = forecast_horizon_days",
            name="ck_model_baseline_comparison_horizon_projection",
        ),
        sa.CheckConstraint(
            "external_blocker IS NULL",
            name="ck_model_baseline_comparison_external_blocker_vocabulary",
        ),
        _in(
            "frozen_limitation",
            FROZEN_LIMITATION_VALUES,
            "ck_model_baseline_comparison_frozen_limitation_vocabulary",
        ),
        sa.CheckConstraint(
            "(comparison_availability = 'AVAILABLE' AND external_blocker IS NULL "
            "AND frozen_limitation IS NULL) OR "
            "(comparison_availability = 'BLOCKED' AND external_blocker IS NULL "
            "AND frozen_limitation = reason_code)",
            name="ck_model_baseline_comparison_blocker_limitation_consistency",
        ),
        sa.CheckConstraint(
            "(metric_status = 'NOT_COMPUTABLE' AND model_value IS NULL "
            "AND baseline_value IS NULL AND delta_value IS NULL) OR "
            "(metric_status <> 'NOT_COMPUTABLE' AND model_value IS NOT NULL "
            "AND baseline_value IS NOT NULL AND delta_value IS NOT NULL)",
            name="ck_model_baseline_comparison_conditional_values",
        ),
    )
    op.create_index(
        "ix_model_baseline_comparison_run_id",
        "model_baseline_comparison",
        ["quality_evaluation_run_id"],
    )


def _create_legacy_comparison_table(is_sqlite: bool) -> None:
    json_type = _json_type(is_sqlite)
    bigint = _bigint(is_sqlite)
    op.create_table(
        "model_baseline_comparison",
        sa.Column("id", bigint, primary_key=True, autoincrement=True),
        sa.Column(
            "quality_evaluation_run_id",
            bigint,
            sa.ForeignKey(
                "quality_evaluation_run.id",
                name="fk_model_baseline_comparison_run",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column(
            "naive_baseline_run_id",
            bigint,
            sa.ForeignKey(
                "naive_baseline_run.id",
                name="fk_model_baseline_comparison_baseline",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("comparison_key_hash", sa.Text(), nullable=False),
        sa.Column("model_identity", json_type, nullable=False),
        sa.Column("comparison_policy_version", sa.Text(), nullable=False),
        sa.Column("comparison_status", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.Text(), nullable=False),
        sa.Column("canonical_payload", json_type, nullable=False),
        sa.Column("canonical_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "quality_evaluation_run_id",
            "comparison_key_hash",
            name="uq_model_baseline_comparison_run_key",
        ),
        sa.UniqueConstraint("canonical_hash", name="uq_model_baseline_comparison_canonical_hash"),
        _sha("comparison_key_hash", "ck_model_baseline_comparison_key_sha256"),
        _sha("canonical_hash", "ck_model_baseline_comparison_canonical_sha256"),
    )
    op.create_index(
        "ix_model_baseline_comparison_run_id",
        "model_baseline_comparison",
        ["quality_evaluation_run_id"],
    )


def _add_run_and_manifest_columns(is_sqlite: bool) -> None:
    op.add_column(
        "quality_evaluation_run",
        sa.Column("comparison_policy_version", sa.Text(), nullable=True),
    )
    if not is_sqlite:
        op.create_check_constraint(
            "ck_quality_evaluation_run_comparison_policy_version",
            "quality_evaluation_run",
            "(schema_version = 'v0.2-s3-quality-persistence-v1' AND "
            "comparison_policy_version IS NULL) OR "
            "(schema_version = 'v0.2-s3-quality-persistence-v2' AND "
            "comparison_policy_version = 'v0.2-s3-comparison-policy-v1')",
        )
    op.add_column(
        "quality_evaluation_manifest",
        sa.Column("comparison_policy_version", sa.Text(), nullable=True),
    )
    op.add_column(
        "quality_evaluation_manifest",
        sa.Column("comparison_result_schema_version", sa.Text(), nullable=True),
    )
    op.add_column(
        "quality_evaluation_manifest",
        sa.Column(
            "comparison_result_set_schema_version",
            sa.Text(),
            nullable=False,
            server_default=sa.text(f"'{RESULT_SET_V1}'"),
        ),
    )
    op.add_column(
        "quality_evaluation_manifest",
        sa.Column(
            "comparison_cell_count",
            _bigint(is_sqlite),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "quality_evaluation_manifest",
        sa.Column(
            "comparison_result_count",
            _bigint(is_sqlite),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    if not is_sqlite:
        op.alter_column(
            "quality_evaluation_manifest",
            "comparison_result_set_schema_version",
            server_default=None,
        )
        op.alter_column("quality_evaluation_manifest", "comparison_cell_count", server_default=None)
        op.alter_column(
            "quality_evaluation_manifest", "comparison_result_count", server_default=None
        )
    if is_sqlite:
        # SQLite cannot add named CHECK constraints with ALTER TABLE.  The
        # portable migration contract is exercised by the table/column
        # round-trip; PostgreSQL remains the authority for these checks and
        # triggers.
        return
    op.create_check_constraint(
        "ck_quality_manifest_comparison_versions",
        "quality_evaluation_manifest",
        "(schema_version = 'v0.2-s3-quality-persistence-v1' AND comparison_policy_version IS NULL AND comparison_result_schema_version IS NULL AND comparison_result_set_schema_version = 'v0.2-s3-comparison-result-set-v1') OR (schema_version = 'v0.2-s3-quality-persistence-v2' AND comparison_policy_version = 'v0.2-s3-comparison-policy-v1' AND comparison_result_schema_version = 'v0.2-s3-comparison-result-v1' AND comparison_result_set_schema_version = 'v0.2-s3-comparison-result-set-v2')",
    )
    op.create_check_constraint(
        "ck_quality_manifest_comparison_counts_nonnegative",
        "quality_evaluation_manifest",
        "comparison_cell_count >= 0 AND comparison_result_count >= 0",
    )
    op.create_check_constraint(
        "ck_quality_manifest_comparison_count_closure",
        "quality_evaluation_manifest",
        "(schema_version = 'v0.2-s3-quality-persistence-v1' AND "
        "comparison_cell_count = 0 AND comparison_result_count = 0) OR "
        "(schema_version = 'v0.2-s3-quality-persistence-v2' AND "
        "comparison_result_count = comparison_cell_count * 10)",
    )
    op.create_check_constraint(
        "ck_quality_manifest_v1_comparison_projection",
        "quality_evaluation_manifest",
        "schema_version <> 'v0.2-s3-quality-persistence-v1' OR "
        "(comparison_policy_version IS NULL AND comparison_result_schema_version IS NULL "
        "AND comparison_result_set_schema_version = 'v0.2-s3-comparison-result-set-v1' "
        "AND comparison_cell_count = 0 AND comparison_result_count = 0)",
    )
    op.create_check_constraint(
        "ck_quality_manifest_v2_comparison_projection",
        "quality_evaluation_manifest",
        "schema_version <> 'v0.2-s3-quality-persistence-v2' OR "
        "(comparison_policy_version = 'v0.2-s3-comparison-policy-v1' AND "
        "comparison_result_schema_version = 'v0.2-s3-comparison-result-v1' AND "
        "comparison_result_set_schema_version = 'v0.2-s3-comparison-result-set-v2')",
    )


def _widen_run_schema_version(is_sqlite: bool) -> None:
    expression = (
        "schema_version IN ('v0.2-s3-quality-persistence-v1', 'v0.2-s3-quality-persistence-v2')"
    )
    if is_sqlite:
        with op.batch_alter_table("quality_evaluation_run", recreate="always") as batch:
            batch.drop_constraint("ck_quality_evaluation_run_schema_version", type_="check")
            batch.create_check_constraint("ck_quality_evaluation_run_schema_version", expression)
    else:
        op.drop_constraint(
            "ck_quality_evaluation_run_schema_version",
            "quality_evaluation_run",
            type_="check",
        )
        op.create_check_constraint(
            "ck_quality_evaluation_run_schema_version",
            "quality_evaluation_run",
            expression,
        )


def _restore_legacy_run_schema_version(is_sqlite: bool) -> None:
    expression = "schema_version = 'v0.2-s3-quality-persistence-v1'"
    if is_sqlite:
        with op.batch_alter_table("quality_evaluation_run", recreate="always") as batch:
            batch.drop_constraint("ck_quality_evaluation_run_schema_version", type_="check")
            batch.create_check_constraint("ck_quality_evaluation_run_schema_version", expression)
    else:
        op.drop_constraint(
            "ck_quality_evaluation_run_schema_version",
            "quality_evaluation_run",
            type_="check",
        )
        op.create_check_constraint(
            "ck_quality_evaluation_run_schema_version",
            "quality_evaluation_run",
            expression,
        )


def _create_postgresql_guards() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION quality_canonical_jsonb(value jsonb) RETURNS text
        LANGUAGE plpgsql IMMUTABLE STRICT AS $$
        DECLARE
            result text;
        BEGIN
            CASE jsonb_typeof(value)
                WHEN 'object' THEN
                    SELECT coalesce(
                        '{' || string_agg(
                            to_jsonb(item_key)::text || ':' ||
                            quality_canonical_jsonb(item_value),
                            ',' ORDER BY item_key
                        ) || '}', '{}'
                    )
                    INTO result
                    FROM jsonb_each(value) AS item(item_key, item_value);
                WHEN 'array' THEN
                    SELECT coalesce(
                        '[' || string_agg(
                            quality_canonical_jsonb(item_value),
                            ',' ORDER BY item_index
                        ) || ']', '[]'
                    )
                    INTO result
                    FROM jsonb_array_elements(value) WITH ORDINALITY
                        AS item(item_value, item_index);
                ELSE
                    result := value::text;
            END CASE;
            RETURN result;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION quality_comparison_member_set_guard() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            member jsonb;
            daily_key jsonb;
            sorted_members jsonb;
            computed_hash text;
            computed_key_hash text;
            computed_canonical_hash text;
            match_count bigint;
            member_count bigint;
            expected_member_keys text[] := ARRAY[
                'comparison_daily_key', 'baseline_request_hash',
                'baseline_result_hash', 'baseline_source_snapshot_identity',
                'baseline_source_snapshot_hash', 'baseline_source_row_set_hash',
                'visibility_manifest_hash', 'baseline_policy_version'
            ];
            expected_daily_keys text[] := ARRAY[
                'current_target_date', 'current_forecast_cutoff_at',
                'farm_business_key', 'subfarm_business_key', 'variety_business_key',
                'metric_policy_version', 'baseline_policy_version'
            ];
        BEGIN
            IF jsonb_typeof(NEW.baseline_member_identity_set) <> 'array'
               OR jsonb_array_length(NEW.baseline_member_identity_set) = 0 THEN
                RAISE EXCEPTION 'baseline member set must be a nonempty array';
            END IF;
            SELECT jsonb_agg(
                item ORDER BY quality_canonical_jsonb(item->'comparison_daily_key')
            )
            INTO sorted_members
            FROM jsonb_array_elements(NEW.baseline_member_identity_set) AS item;
            IF NEW.baseline_member_identity_set <> sorted_members THEN
                RAISE EXCEPTION 'baseline member order is not canonical';
            END IF;
            SELECT count(*) INTO member_count
            FROM jsonb_array_elements(NEW.baseline_member_identity_set) AS item;
            IF member_count <> (SELECT count(DISTINCT item->'comparison_daily_key')
                                FROM jsonb_array_elements(NEW.baseline_member_identity_set) AS item) THEN
                RAISE EXCEPTION 'duplicate baseline member';
            END IF;
            FOR member IN SELECT value FROM jsonb_array_elements(NEW.baseline_member_identity_set) AS value LOOP
                IF jsonb_typeof(member) <> 'object'
                   OR (SELECT array_agg(key ORDER BY key) FROM jsonb_object_keys(member) AS key)
                      <> (SELECT array_agg(key ORDER BY key) FROM unnest(expected_member_keys) AS key) THEN
                    RAISE EXCEPTION 'baseline member shape mismatch';
                END IF;
                daily_key := member->'comparison_daily_key';
                IF jsonb_typeof(daily_key) <> 'object'
                   OR (SELECT array_agg(key ORDER BY key) FROM jsonb_object_keys(daily_key) AS key)
                      <> (SELECT array_agg(key ORDER BY key) FROM unnest(expected_daily_keys) AS key) THEN
                    RAISE EXCEPTION 'baseline daily key shape mismatch';
                END IF;
                SELECT count(*) INTO match_count
                FROM naive_baseline_run AS baseline
                WHERE baseline.quality_evaluation_run_id = NEW.quality_evaluation_run_id
                  AND baseline.baseline_request_hash = member->>'baseline_request_hash'
                  AND baseline.baseline_result_hash = member->>'baseline_result_hash'
                  AND baseline.baseline_source_snapshot_identity = member->>'baseline_source_snapshot_identity'
                  AND baseline.baseline_source_snapshot_hash = member->>'baseline_source_snapshot_hash'
                  AND baseline.baseline_source_row_set_hash = member->>'baseline_source_row_set_hash'
                  AND baseline.visibility_manifest_hash = member->>'visibility_manifest_hash'
                  AND baseline.baseline_policy_version = member->>'baseline_policy_version'
                  AND baseline.canonical_payload->'request'->>'current_target_date' = daily_key->>'current_target_date'
                  AND baseline.canonical_payload->'request'->>'current_forecast_cutoff_at' = daily_key->>'current_forecast_cutoff_at'
                  AND baseline.canonical_payload->'request'->>'farm_business_key' = daily_key->>'farm_business_key'
                  AND baseline.canonical_payload->'request'->>'subfarm_business_key' = daily_key->>'subfarm_business_key'
                  AND baseline.canonical_payload->'request'->>'variety_business_key' = daily_key->>'variety_business_key'
                  AND baseline.canonical_payload->'request'->>'metric_policy_version' = daily_key->>'metric_policy_version'
                  AND baseline.canonical_payload->'request'->>'baseline_policy_version' = daily_key->>'baseline_policy_version';
                IF match_count <> 1 THEN
                    RAISE EXCEPTION 'baseline member absent, foreign, or projection mismatch';
                END IF;
            END LOOP;
            computed_hash := encode(
                    digest(
                        quality_canonical_jsonb(jsonb_build_object(
                            'members', sorted_members,
                            'schema_version', 'v0.2-s3-comparison-baseline-member-set-v1'
                        )),
                    'sha256'
                ),
                'hex'
            );
            IF computed_hash <> NEW.baseline_member_set_hash THEN
                RAISE EXCEPTION 'baseline member set hash mismatch';
            END IF;
            computed_key_hash := encode(
                digest(
                    quality_canonical_jsonb(jsonb_build_object(
                        'comparison_result_schema_version',
                            'v0.2-s3-comparison-result-v1',
                        'comparison_policy_version', NEW.comparison_policy_version,
                        'comparison_name', NEW.comparison_name,
                        'baseline_member_set_hash', NEW.baseline_member_set_hash,
                        'normalized_breakdown_identity',
                            NEW.normalized_breakdown_identity
                    )),
                    'sha256'
                ),
                'hex'
            );
            IF computed_key_hash <> NEW.comparison_key_hash THEN
                RAISE EXCEPTION 'comparison key hash mismatch';
            END IF;
            computed_canonical_hash := encode(
                digest(quality_canonical_jsonb(NEW.canonical_payload), 'sha256'),
                'hex'
            );
            IF computed_canonical_hash <> NEW.canonical_hash THEN
                RAISE EXCEPTION 'comparison canonical hash mismatch';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION quality_manifest_comparison_contract_guard()
        RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            actual_count bigint;
            actual_cells bigint;
            rebuilt_records jsonb;
            rebuilt_result_set_hash text;
            rebuilt_records_payload jsonb;
            projection_record RECORD;
            proj_payload jsonb;
            proj_payload_key_array text[];
            proj_payload_key_count bigint;
            expected_payload_key_array text[];
            proj_rebuilt_canonical_hash text;
            proj_baseline_value_numeric numeric;
            proj_model_value_numeric numeric;
            proj_delta_value_numeric numeric;
            proj_baseline_value_str text;
            proj_model_value_str text;
            proj_delta_value_str text;
            proj_baseline_member_set_sorted jsonb;
            proj_member_set_hash_input jsonb;
            proj_member_set_rebuilt text;
            proj_baseline_member_identity_set jsonb;
            proj_normalized_breakdown_identity jsonb;
            proj_comparison_key_hash_input jsonb;
            proj_comparison_key_hash_rebuilt text;
            proj_child_status text;
            proj_child_availability text;
            proj_child_reason text;
            proj_child_name text;
            proj_child_blocker_null boolean;
            proj_child_limitation_null boolean;
            proj_child_limitation text;
            proj_child_values_all_null boolean;
            proj_child_values_all_nonnull boolean;
        BEGIN
            IF NEW.schema_version = 'v0.2-s3-quality-persistence-v2' THEN
                -- Brief §6: lock the parent run row before any other work.
                PERFORM 1 FROM quality_evaluation_run
                    WHERE id = NEW.quality_evaluation_run_id
                    FOR UPDATE;

                -- Brief §2: rebuild the comparison result-set hash from the
                -- child canonical_hash values sorted ascending (the
                -- application canonical-sort oracle).
                SELECT coalesce(
                    jsonb_agg(child.canonical_hash ORDER BY child.canonical_hash),
                    '[]'::jsonb
                )
                INTO rebuilt_records
                FROM model_baseline_comparison AS child
                WHERE child.quality_evaluation_run_id = NEW.quality_evaluation_run_id;

                rebuilt_records_payload := jsonb_build_object(
                    'record_count', jsonb_array_length(rebuilt_records),
                    'records', rebuilt_records,
                    'schema_version', 'v0.2-s3-comparison-result-set-v2'
                );
                rebuilt_result_set_hash := encode(
                    digest(quality_canonical_jsonb(rebuilt_records_payload), 'sha256'),
                    'hex'
                );
                IF rebuilt_result_set_hash <> NEW.comparison_result_set_hash THEN
                    RAISE EXCEPTION
                        'comparison result-set hash drift: stored=% rebuilt=%',
                        NEW.comparison_result_set_hash, rebuilt_result_set_hash;
                END IF;

                SELECT count(*) INTO actual_count
                    FROM model_baseline_comparison
                    WHERE quality_evaluation_run_id = NEW.quality_evaluation_run_id;
                actual_cells := actual_count;

                FOR projection_record IN
                    SELECT
                        id,
                        canonical_payload,
                        canonical_hash,
                        comparison_key_hash,
                        comparison_policy_version,
                        comparison_name,
                        comparison_availability,
                        metric_status,
                        reason_code,
                        external_blocker,
                        frozen_limitation,
                        model_identity,
                        baseline_member_identity_set,
                        baseline_member_set_hash,
                        normalized_breakdown_identity,
                        forecast_horizon_days,
                        model_value,
                        baseline_value,
                        delta_value,
                        model_input_row_count,
                        baseline_input_row_count,
                        common_comparable_row_count,
                        model_only_row_count,
                        baseline_only_row_count,
                        excluded_row_count,
                        not_computable_row_count
                    FROM model_baseline_comparison
                    WHERE quality_evaluation_run_id = NEW.quality_evaluation_run_id
                    ORDER BY id
                LOOP
                    proj_payload := projection_record.canonical_payload;

                    -- Brief §4: order-independent exact key set (27 keys).
                    SELECT array_agg(key ORDER BY key)
                        INTO proj_payload_key_array
                        FROM jsonb_object_keys(proj_payload) AS key;
                    SELECT count(*) INTO proj_payload_key_count
                        FROM unnest(proj_payload_key_array) AS k;
                    IF proj_payload_key_count <> 27 THEN
                        RAISE EXCEPTION
                            'canonical_payload root key count drift: expected=27 actual=%',
                            proj_payload_key_count;
                    END IF;
                    expected_payload_key_array := ARRAY[
                        'baseline_input_row_count',
                        'baseline_member_identity_set',
                        'baseline_member_set_hash',
                        'baseline_only_row_count',
                        'baseline_value',
                        'canonical_hash',
                        'canonical_payload',
                        'common_comparable_row_count',
                        'comparison_availability',
                        'comparison_key_hash',
                        'comparison_name',
                        'comparison_policy_version',
                        'delta_value',
                        'excluded_row_count',
                        'external_blocker',
                        'forecast_horizon_days',
                        'frozen_limitation',
                        'metric_status',
                        'model_identity',
                        'model_input_row_count',
                        'model_only_row_count',
                        'model_value',
                        'normalized_breakdown_identity',
                        'not_computable_row_count',
                        'persistence_schema_version',
                        'reason_code',
                        'schema_version'
                    ];
                    IF proj_payload_key_array <> expected_payload_key_array THEN
                        RAISE EXCEPTION
                            'canonical_payload root key set drift';
                    END IF;

                    IF proj_payload->'canonical_payload' IS NULL
                       OR jsonb_typeof(proj_payload->'canonical_payload') <> 'object'
                       OR proj_payload->'canonical_payload' <> '{}'::jsonb THEN
                        RAISE EXCEPTION
                            'canonical_payload.canonical_payload must equal {}';
                    END IF;
                    IF proj_payload->>'canonical_hash' IS NULL
                       OR proj_payload->>'canonical_hash' <> '' THEN
                        RAISE EXCEPTION
                            'canonical_payload.canonical_hash must equal ""';
                    END IF;

                    proj_rebuilt_canonical_hash := encode(
                        digest(quality_canonical_jsonb(proj_payload), 'sha256'),
                        'hex'
                    );
                    IF proj_rebuilt_canonical_hash <> projection_record.canonical_hash THEN
                        RAISE EXCEPTION
                            'canonical_hash drift: stored=% rebuilt=%',
                            projection_record.canonical_hash, proj_rebuilt_canonical_hash;
                    END IF;

                    IF proj_payload->>'schema_version'
                       IS DISTINCT FROM 'v0.2-s3-comparison-result-v1' THEN
                        RAISE EXCEPTION 'canonical_payload.schema_version must be v0.2-s3-comparison-result-v1';
                    END IF;
                    IF proj_payload->>'persistence_schema_version'
                       IS DISTINCT FROM 'v0.2-s3-quality-persistence-v2' THEN
                        RAISE EXCEPTION 'canonical_payload.persistence_schema_version must be v0.2-s3-quality-persistence-v2';
                    END IF;
                    IF proj_payload->>'comparison_policy_version'
                       IS DISTINCT FROM projection_record.comparison_policy_version THEN
                        RAISE EXCEPTION 'comparison_policy_version projection drift';
                    END IF;
                    IF proj_payload->>'comparison_name'
                       IS DISTINCT FROM projection_record.comparison_name THEN
                        RAISE EXCEPTION 'comparison_name projection drift';
                    END IF;
                    IF proj_payload->>'comparison_availability'
                       IS DISTINCT FROM projection_record.comparison_availability THEN
                        RAISE EXCEPTION 'comparison_availability projection drift';
                    END IF;
                    IF proj_payload->>'metric_status'
                       IS DISTINCT FROM projection_record.metric_status THEN
                        RAISE EXCEPTION 'metric_status projection drift';
                    END IF;
                    IF proj_payload->>'reason_code'
                       IS DISTINCT FROM projection_record.reason_code THEN
                        RAISE EXCEPTION 'reason_code projection drift';
                    END IF;
                    IF proj_payload->>'model_identity'
                       IS DISTINCT FROM projection_record.model_identity THEN
                        RAISE EXCEPTION 'model_identity projection drift';
                    END IF;
                    IF proj_payload->>'forecast_horizon_days'
                       IS DISTINCT FROM projection_record.forecast_horizon_days::text THEN
                        RAISE EXCEPTION 'forecast_horizon_days projection drift';
                    END IF;
                    IF (proj_payload->>'frozen_limitation') IS DISTINCT FROM
                       (CASE WHEN projection_record.frozen_limitation IS NULL
                             THEN NULL ELSE projection_record.frozen_limitation END) THEN
                        RAISE EXCEPTION 'frozen_limitation projection drift';
                    END IF;
                    IF (proj_payload->>'external_blocker') IS DISTINCT FROM
                       (CASE WHEN projection_record.external_blocker IS NULL
                             THEN NULL ELSE projection_record.external_blocker END) THEN
                        RAISE EXCEPTION 'external_blocker projection drift';
                    END IF;

                    IF projection_record.model_value IS NULL THEN
                        IF proj_payload->>'model_value' IS NOT NULL THEN
                            RAISE EXCEPTION 'model_value null/non-null drift';
                        END IF;
                    ELSE
                        proj_model_value_numeric := projection_record.model_value;
                        proj_model_value_str := to_char(proj_model_value_numeric, 'FM0.000000');
                        IF proj_model_value_str IS DISTINCT FROM proj_payload->>'model_value' THEN
                            RAISE EXCEPTION 'model_value six-decimal projection drift';
                        END IF;
                    END IF;
                    IF projection_record.baseline_value IS NULL THEN
                        IF proj_payload->>'baseline_value' IS NOT NULL THEN
                            RAISE EXCEPTION 'baseline_value null/non-null drift';
                        END IF;
                    ELSE
                        proj_baseline_value_numeric := projection_record.baseline_value;
                        proj_baseline_value_str := to_char(proj_baseline_value_numeric, 'FM0.000000');
                        IF proj_baseline_value_str IS DISTINCT FROM proj_payload->>'baseline_value' THEN
                            RAISE EXCEPTION 'baseline_value six-decimal projection drift';
                        END IF;
                    END IF;
                    IF projection_record.delta_value IS NULL THEN
                        IF proj_payload->>'delta_value' IS NOT NULL THEN
                            RAISE EXCEPTION 'delta_value null/non-null drift';
                        END IF;
                    ELSE
                        proj_delta_value_numeric := projection_record.delta_value;
                        proj_delta_value_str := to_char(proj_delta_value_numeric, 'FM0.000000');
                        IF proj_delta_value_str IS DISTINCT FROM proj_payload->>'delta_value' THEN
                            RAISE EXCEPTION 'delta_value six-decimal projection drift';
                        END IF;
                    END IF;

                    IF (proj_payload->>'model_input_row_count')::bigint
                       IS DISTINCT FROM projection_record.model_input_row_count THEN
                        RAISE EXCEPTION 'model_input_row_count projection drift';
                    END IF;
                    IF (proj_payload->>'baseline_input_row_count')::bigint
                       IS DISTINCT FROM projection_record.baseline_input_row_count THEN
                        RAISE EXCEPTION 'baseline_input_row_count projection drift';
                    END IF;
                    IF (proj_payload->>'common_comparable_row_count')::bigint
                       IS DISTINCT FROM projection_record.common_comparable_row_count THEN
                        RAISE EXCEPTION 'common_comparable_row_count projection drift';
                    END IF;
                    IF (proj_payload->>'model_only_row_count')::bigint
                       IS DISTINCT FROM projection_record.model_only_row_count THEN
                        RAISE EXCEPTION 'model_only_row_count projection drift';
                    END IF;
                    IF (proj_payload->>'baseline_only_row_count')::bigint
                       IS DISTINCT FROM projection_record.baseline_only_row_count THEN
                        RAISE EXCEPTION 'baseline_only_row_count projection drift';
                    END IF;
                    IF (proj_payload->>'excluded_row_count')::bigint
                       IS DISTINCT FROM projection_record.excluded_row_count THEN
                        RAISE EXCEPTION 'excluded_row_count projection drift';
                    END IF;
                    IF (proj_payload->>'not_computable_row_count')::bigint
                       IS DISTINCT FROM projection_record.not_computable_row_count THEN
                        RAISE EXCEPTION 'not_computable_row_count projection drift';
                    END IF;

                    IF projection_record.model_value IS NOT NULL
                       AND projection_record.baseline_value IS NOT NULL
                       AND projection_record.delta_value IS NOT NULL THEN
                        proj_delta_value_numeric :=
                            projection_record.model_value - projection_record.baseline_value;
                        proj_delta_value_str := to_char(proj_delta_value_numeric, 'FM0.000000');
                        IF proj_delta_value_str IS DISTINCT FROM
                           to_char(projection_record.delta_value, 'FM0.000000') THEN
                            RAISE EXCEPTION
                                'delta != model - baseline: model=% baseline=% delta=%',
                                projection_record.model_value,
                                projection_record.baseline_value,
                                projection_record.delta_value;
                        END IF;
                    END IF;

                    proj_baseline_member_identity_set :=
                        projection_record.baseline_member_identity_set;
                    WITH member_daily_keys AS (
                        SELECT
                            elem->'comparison_daily_key' AS daily_key,
                            elem
                        FROM jsonb_array_elements(proj_baseline_member_identity_set)
                            AS elem
                    ),
                    sorted_members AS (
                        SELECT jsonb_agg(elem ORDER BY
                            quality_canonical_jsonb(elem->'comparison_daily_key'))
                            AS sorted_set
                        FROM member_daily_keys
                    )
                    SELECT sorted_set INTO proj_baseline_member_set_sorted FROM sorted_members;
                    proj_member_set_hash_input := jsonb_build_object(
                        'members', proj_baseline_member_set_sorted,
                        'schema_version', 'v0.2-s3-comparison-baseline-member-set-v1'
                    );
                    proj_member_set_rebuilt := encode(
                        digest(quality_canonical_jsonb(proj_member_set_hash_input), 'sha256'),
                        'hex'
                    );
                    IF proj_member_set_rebuilt <> projection_record.baseline_member_set_hash THEN
                        RAISE EXCEPTION
                            'baseline_member_set_hash drift: stored=% rebuilt=%',
                            projection_record.baseline_member_set_hash, proj_member_set_rebuilt;
                    END IF;

                    proj_normalized_breakdown_identity :=
                        projection_record.normalized_breakdown_identity;
                    IF proj_normalized_breakdown_identity IS NULL
                       OR jsonb_typeof(proj_normalized_breakdown_identity) <> 'object' THEN
                        RAISE EXCEPTION 'normalized_breakdown_identity must be a jsonb object';
                    END IF;
                    IF (proj_normalized_breakdown_identity->>'model_identity')
                       IS DISTINCT FROM projection_record.model_identity THEN
                        RAISE EXCEPTION
                            'normalized_breakdown_identity.model_identity mismatch';
                    END IF;
                    IF (proj_normalized_breakdown_identity->>'forecast_horizon_days')::integer
                       IS DISTINCT FROM projection_record.forecast_horizon_days THEN
                        RAISE EXCEPTION
                            'normalized_breakdown_identity.forecast_horizon_days mismatch';
                    END IF;
                    proj_comparison_key_hash_input := jsonb_build_object(
                        'comparison_result_schema_version',
                            'v0.2-s3-comparison-result-v1',
                        'comparison_policy_version',
                            projection_record.comparison_policy_version,
                        'comparison_name',
                            projection_record.comparison_name,
                        'baseline_member_set_hash',
                            projection_record.baseline_member_set_hash,
                        'normalized_breakdown_identity',
                            proj_normalized_breakdown_identity
                    );
                    proj_comparison_key_hash_rebuilt := encode(
                        digest(quality_canonical_jsonb(proj_comparison_key_hash_input),
                            'sha256'),
                        'hex'
                    );
                    IF proj_comparison_key_hash_rebuilt
                       <> projection_record.comparison_key_hash THEN
                        RAISE EXCEPTION
                            'comparison_key_hash drift: stored=% rebuilt=%',
                            projection_record.comparison_key_hash,
                            proj_comparison_key_hash_rebuilt;
                    END IF;

                    proj_child_status := projection_record.metric_status;
                    proj_child_availability := projection_record.comparison_availability;
                    proj_child_reason := projection_record.reason_code;
                    proj_child_name := projection_record.comparison_name;
                    proj_child_blocker_null :=
                        projection_record.external_blocker IS NULL;
                    proj_child_limitation_null :=
                        projection_record.frozen_limitation IS NULL;
                    proj_child_limitation := projection_record.frozen_limitation;
                    proj_child_values_all_null :=
                        projection_record.model_value IS NULL
                        AND projection_record.baseline_value IS NULL
                        AND projection_record.delta_value IS NULL;
                    proj_child_values_all_nonnull :=
                        projection_record.model_value IS NOT NULL
                        AND projection_record.baseline_value IS NOT NULL
                        AND projection_record.delta_value IS NOT NULL;

                    IF proj_child_availability = 'AVAILABLE' THEN
                        IF NOT proj_child_blocker_null THEN
                            RAISE EXCEPTION
                                'AVAILABLE comparison has non-null external_blocker';
                        END IF;
                        IF NOT proj_child_limitation_null THEN
                            RAISE EXCEPTION
                                'AVAILABLE comparison has non-null frozen_limitation';
                        END IF;
                        IF proj_child_status = 'COMPUTED' THEN
                            IF NOT proj_child_values_all_nonnull THEN
                                RAISE EXCEPTION
                                    'AVAILABLE+COMPUTED comparison has null numeric';
                            END IF;
                            IF proj_child_reason <> 'NONE' THEN
                                RAISE EXCEPTION
                                    'AVAILABLE+COMPUTED comparison has reason_code <> NONE';
                            END IF;
                            IF proj_child_name NOT IN (
                                'daily_mae_delta',
                                'daily_wape_delta',
                                'daily_smape_delta',
                                'daily_mape_delta',
                                'absolute_bias_magnitude_delta'
                            ) THEN
                                RAISE EXCEPTION
                                    'AVAILABLE+COMPUTED comparison has unknown name';
                            END IF;
                        ELSIF proj_child_status = 'COMPARED' THEN
                            IF NOT proj_child_values_all_nonnull THEN
                                RAISE EXCEPTION
                                    'AVAILABLE+COMPARED comparison has null numeric';
                            END IF;
                            IF proj_child_reason <> 'SIGNED_DIRECTION_ONLY' THEN
                                RAISE EXCEPTION
                                    'AVAILABLE+COMPARED comparison has reason_code <> SIGNED_DIRECTION_ONLY';
                            END IF;
                            IF proj_child_name <> 'signed_bias_delta' THEN
                                RAISE EXCEPTION
                                    'AVAILABLE+COMPARED comparison has name <> signed_bias_delta';
                            END IF;
                        ELSIF proj_child_status = 'INSUFFICIENT_SAMPLE' THEN
                            IF NOT proj_child_values_all_nonnull THEN
                                RAISE EXCEPTION
                                    'AVAILABLE+INSUFFICIENT_SAMPLE comparison has null numeric';
                            END IF;
                            IF proj_child_reason <> 'BELOW_MINIMUM' THEN
                                RAISE EXCEPTION
                                    'AVAILABLE+INSUFFICIENT_SAMPLE comparison has reason_code <> BELOW_MINIMUM';
                            END IF;
                            IF proj_child_name NOT IN (
                                'daily_mae_delta',
                                'daily_wape_delta',
                                'daily_smape_delta',
                                'daily_mape_delta',
                                'signed_bias_delta',
                                'absolute_bias_magnitude_delta'
                            ) THEN
                                RAISE EXCEPTION
                                    'AVAILABLE+INSUFFICIENT_SAMPLE comparison has unknown name';
                            END IF;
                        ELSIF proj_child_status = 'NOT_COMPUTABLE' THEN
                            IF NOT proj_child_values_all_null THEN
                                RAISE EXCEPTION
                                    'AVAILABLE+NOT_COMPUTABLE comparison has non-null numeric';
                            END IF;
                            IF proj_child_reason NOT IN (
                                'NO_S2_BINDING_ROWS',
                                'WAPE_DENOMINATOR_ZERO',
                                'NO_MAPE_ELIGIBLE_ROWS'
                            ) THEN
                                RAISE EXCEPTION
                                    'AVAILABLE+NOT_COMPUTABLE comparison has unsupported reason_code';
                            END IF;
                            IF proj_child_reason = 'WAPE_DENOMINATOR_ZERO'
                               AND proj_child_name <> 'daily_wape_delta' THEN
                                RAISE EXCEPTION
                                    'WAPE_DENOMINATOR_ZERO only allowed for daily_wape_delta';
                            END IF;
                            IF proj_child_reason = 'NO_MAPE_ELIGIBLE_ROWS'
                               AND proj_child_name <> 'daily_mape_delta' THEN
                                RAISE EXCEPTION
                                    'NO_MAPE_ELIGIBLE_ROWS only allowed for daily_mape_delta';
                            END IF;
                            IF proj_child_reason = 'NO_S2_BINDING_ROWS'
                               AND proj_child_name NOT IN (
                                   'daily_mae_delta',
                                   'daily_wape_delta',
                                   'daily_smape_delta',
                                   'daily_mape_delta',
                                   'signed_bias_delta',
                                   'absolute_bias_magnitude_delta'
                               ) THEN
                                RAISE EXCEPTION
                                    'NO_S2_BINDING_ROWS has unknown name';
                            END IF;
                        ELSE
                            RAISE EXCEPTION
                                'AVAILABLE comparison has unknown metric_status';
                        END IF;
                    ELSIF proj_child_availability = 'BLOCKED' THEN
                        IF NOT proj_child_blocker_null THEN
                            RAISE EXCEPTION
                                'BLOCKED comparison has non-null external_blocker';
                        END IF;
                        IF proj_child_limitation <> proj_child_reason THEN
                            RAISE EXCEPTION
                                'BLOCKED comparison limitation != reason_code';
                        END IF;
                        IF proj_child_status <> 'NOT_COMPUTABLE' THEN
                            RAISE EXCEPTION
                                'BLOCKED comparison has non-NOT_COMPUTABLE status';
                        END IF;
                        IF NOT proj_child_values_all_null THEN
                            RAISE EXCEPTION
                                'BLOCKED comparison has non-null numeric';
                        END IF;
                        IF proj_child_name = 'p80_coverage_delta'
                           OR proj_child_name = 'p90_coverage_delta'
                           OR proj_child_name = 'baseline_p80_p90_peak_comparison' THEN
                            IF proj_child_reason
                               <> 'BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED' THEN
                                RAISE EXCEPTION
                                    'BLOCKED coverage name requires BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED';
                            END IF;
                        ELSIF proj_child_name = 'interval_width_delta' THEN
                            IF proj_child_reason
                               <> 'PREDICTION_INTERVAL_LOWER_BOUND_UNAVAILABLE' THEN
                                RAISE EXCEPTION
                                    'BLOCKED interval_width_delta requires PREDICTION_INTERVAL_LOWER_BOUND_UNAVAILABLE';
                            END IF;
                        ELSE
                            RAISE EXCEPTION
                                'BLOCKED comparison has unsupported name=%',
                                proj_child_name;
                        END IF;
                    ELSE
                        RAISE EXCEPTION
                            'unknown comparison_availability value: %',
                            proj_child_availability;
                    END IF;
                END LOOP;

            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_quality_comparison_member_set_guard
        BEFORE INSERT ON model_baseline_comparison
        FOR EACH ROW EXECUTE FUNCTION quality_comparison_member_set_guard()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_quality_manifest_comparison_contract_guard
        BEFORE INSERT ON quality_evaluation_manifest
        FOR EACH ROW EXECUTE FUNCTION quality_manifest_comparison_contract_guard()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_quality_model_baseline_comparison_immutable
        BEFORE UPDATE OR DELETE ON model_baseline_comparison
        FOR EACH ROW EXECUTE FUNCTION quality_evaluation_immutable_row()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_quality_model_baseline_comparison_manifest_insert_guard
        BEFORE INSERT ON model_baseline_comparison
        FOR EACH ROW EXECUTE FUNCTION quality_evaluation_child_insert_guard()
        """
    )


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    count = bind.execute(sa.text("SELECT count(*) FROM model_baseline_comparison")).scalar_one()
    if count != 0:
        raise RuntimeError("0025 upgrade rejected: pre-0025 comparison rows exist")
    _add_run_and_manifest_columns(is_sqlite)
    _widen_run_schema_version(is_sqlite)
    # The 0024 placeholder is empty by contract. On PostgreSQL perform the
    # explicit legacy FK/column removal before recreating the v2 table. SQLite
    # uses the same empty-table replacement because it cannot drop all of the
    # old constraints portably through ALTER TABLE.
    if not is_sqlite:
        op.drop_constraint(
            "fk_model_baseline_comparison_baseline",
            "model_baseline_comparison",
            type_="foreignkey",
        )
        op.drop_column("model_baseline_comparison", "naive_baseline_run_id")
    op.drop_index("ix_model_baseline_comparison_run_id", table_name="model_baseline_comparison")
    op.drop_table("model_baseline_comparison")
    _create_v2_comparison_table(is_sqlite)
    if not is_sqlite:
        _create_postgresql_guards()


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    v2_runs = bind.execute(
        sa.text(
            "SELECT count(*) FROM quality_evaluation_run "
            "WHERE schema_version = 'v0.2-s3-quality-persistence-v2'"
        )
    ).scalar_one()
    comparison_rows = bind.execute(
        sa.text("SELECT count(*) FROM model_baseline_comparison")
    ).scalar_one()
    if v2_runs or comparison_rows:
        raise RuntimeError("0025 downgrade rejected: v2 data exists")
    if not is_sqlite:
        op.execute(
            "DROP TRIGGER IF EXISTS trg_quality_comparison_member_set_guard "
            "ON model_baseline_comparison"
        )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_quality_manifest_comparison_contract_guard "
            "ON quality_evaluation_manifest"
        )
        op.execute("DROP FUNCTION IF EXISTS quality_comparison_member_set_guard()")
        op.execute("DROP FUNCTION IF EXISTS quality_manifest_comparison_contract_guard()")
        op.execute("DROP FUNCTION IF EXISTS quality_canonical_jsonb(jsonb)")
    op.drop_index("ix_model_baseline_comparison_run_id", table_name="model_baseline_comparison")
    op.drop_table("model_baseline_comparison")
    _create_legacy_comparison_table(is_sqlite)
    if not is_sqlite:
        for name in (
            "ck_quality_manifest_v2_comparison_projection",
            "ck_quality_manifest_v1_comparison_projection",
            "ck_quality_manifest_comparison_count_closure",
            "ck_quality_manifest_comparison_counts_nonnegative",
            "ck_quality_manifest_comparison_versions",
        ):
            op.drop_constraint(name, "quality_evaluation_manifest", type_="check")
    for column in (
        "comparison_result_count",
        "comparison_cell_count",
        "comparison_result_set_schema_version",
        "comparison_result_schema_version",
        "comparison_policy_version",
    ):
        op.drop_column("quality_evaluation_manifest", column)
    if not is_sqlite:
        op.drop_constraint(
            "ck_quality_evaluation_run_comparison_policy_version",
            "quality_evaluation_run",
            type_="check",
        )
    op.drop_column("quality_evaluation_run", "comparison_policy_version")
    _restore_legacy_run_schema_version(is_sqlite)
