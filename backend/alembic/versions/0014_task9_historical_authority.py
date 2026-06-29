# ruff: noqa: E501
"""Task 9 historical authority PostgreSQL schema.

Revision ID: 0014_task9_historical_authority
Revises: 0013_rolling_backtest_orch
Create Date: 2026-06-30
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014_task9_historical_authority"
down_revision: str | None = "0013_rolling_backtest_orch"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _execute(sql: str) -> None:
    op.execute(sql)


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    _execute(
        """
        CREATE TABLE task9_holiday_calendar_version (
            id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
            season_id BIGINT NOT NULL REFERENCES dim_season(id) ON DELETE RESTRICT,
            calendar_code TEXT NOT NULL,
            lifecycle_timezone_name TEXT NOT NULL,
            calendar_version TEXT NOT NULL,
            revision INTEGER NOT NULL
                CONSTRAINT ck_task9_holiday_calendar_version_revision CHECK (revision > 0),
            region_scope TEXT,
            calendar_hash TEXT NOT NULL
                CONSTRAINT ck_task9_holiday_calendar_version_calendar_hash_sha256
                CHECK (calendar_hash ~ '^[0-9a-f]{64}$'),
            available_at_local_date DATE NOT NULL,
            consumable_from_local_date DATE,
            consumable_to_local_date DATE,
            consumability_range DATERANGE GENERATED ALWAYS AS (
                daterange(
                    COALESCE(consumable_from_local_date, 'infinity'::date),
                    CASE
                        WHEN consumable_to_local_date IS NULL THEN 'infinity'::date
                        ELSE consumable_to_local_date
                    END,
                    '[)'
                )
            ) STORED,
            status TEXT NOT NULL
                CONSTRAINT ck_task9_holiday_calendar_version_status
                CHECK (status IN ('draft', 'active', 'superseded', 'retired', 'cancelled')),
            status_changed_at TIMESTAMPTZ NOT NULL,
            superseded_by_id BIGINT NULL
                CONSTRAINT fk_task9_holiday_calendar_version_superseded_by
                REFERENCES task9_holiday_calendar_version(id) ON DELETE RESTRICT,
            source_system TEXT NOT NULL,
            source_record_key TEXT NOT NULL,
            source_version TEXT NOT NULL,
            row_hash TEXT NOT NULL
                CONSTRAINT ck_task9_holiday_calendar_version_row_hash_sha256
                CHECK (row_hash ~ '^[0-9a-f]{64}$'),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_task9_holiday_calendar_version_business_revision UNIQUE (
                season_id,
                calendar_code,
                lifecycle_timezone_name,
                calendar_version,
                revision
            ),
            CONSTRAINT ck_task9_holiday_calendar_version_timezone_non_blank
                CHECK (btrim(lifecycle_timezone_name) <> ''),
            CONSTRAINT ck_task9_holiday_calendar_version_self_ref
                CHECK (superseded_by_id IS NULL OR superseded_by_id <> id),
            CONSTRAINT ck_task9_holiday_calendar_version_superseded
                CHECK (
                    (status = 'superseded' AND superseded_by_id IS NOT NULL)
                    OR (status <> 'superseded' AND superseded_by_id IS NULL)
                ),
            CONSTRAINT ck_task9_holiday_calendar_version_lifecycle_projection
                CHECK (
                    (
                        status IN ('draft', 'cancelled')
                        AND consumable_from_local_date IS NULL
                        AND consumable_to_local_date IS NULL
                    )
                    OR (
                        status = 'active'
                        AND consumable_from_local_date IS NOT NULL
                        AND consumable_to_local_date IS NULL
                    )
                    OR (
                        status IN ('superseded', 'retired')
                        AND consumable_from_local_date IS NOT NULL
                        AND consumable_to_local_date IS NOT NULL
                    )
                ),
            CONSTRAINT ck_task9_holiday_calendar_version_consumable_from
                CHECK (
                    consumable_from_local_date IS NULL
                    OR consumable_from_local_date >= available_at_local_date
                ),
            CONSTRAINT ck_task9_holiday_calendar_version_consumable_to
                CHECK (
                    consumable_to_local_date IS NULL
                    OR consumable_to_local_date > consumable_from_local_date
                )
        )
        """
    )
    _execute(
        """
        CREATE TABLE task9_holiday_calendar_date (
            id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
            holiday_calendar_version_id BIGINT NOT NULL
                CONSTRAINT fk_task9_holiday_calendar_date_parent
                REFERENCES task9_holiday_calendar_version(id) ON DELETE RESTRICT,
            holiday_date DATE NOT NULL,
            holiday_code TEXT NOT NULL,
            holiday_name TEXT NOT NULL,
            CONSTRAINT uq_task9_holiday_calendar_date_business_key
                UNIQUE (holiday_calendar_version_id, holiday_date, holiday_code)
        )
        """
    )
    _execute(
        """
        CREATE TABLE task9_weather_rule_config_version (
            id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
            rule_code TEXT NOT NULL,
            lifecycle_timezone_name TEXT NOT NULL,
            rule_version TEXT NOT NULL,
            revision INTEGER NOT NULL
                CONSTRAINT ck_task9_weather_rule_config_version_revision CHECK (revision > 0),
            combination_method TEXT NOT NULL,
            minimum_ratio NUMERIC(12, 6) NOT NULL
                CONSTRAINT ck_task9_weather_rule_config_version_minimum_ratio
                CHECK (minimum_ratio >= 0 AND minimum_ratio <= 1),
            maximum_ratio NUMERIC(12, 6) NOT NULL
                CONSTRAINT ck_task9_weather_rule_config_version_maximum_ratio
                CHECK (maximum_ratio >= 0 AND maximum_ratio <= 1),
            required_feature_ids JSONB NOT NULL,
            feature_rules_json JSONB NOT NULL,
            missing_feature_policy TEXT NOT NULL
                CONSTRAINT ck_task9_weather_rule_config_version_missing_feature_policy
                CHECK (missing_feature_policy = 'BLOCK'),
            config_hash TEXT NOT NULL
                CONSTRAINT ck_task9_weather_rule_config_version_config_hash_sha256
                CHECK (config_hash ~ '^[0-9a-f]{64}$'),
            available_at_local_date DATE NOT NULL,
            consumable_from_local_date DATE,
            consumable_to_local_date DATE,
            consumability_range DATERANGE GENERATED ALWAYS AS (
                daterange(
                    COALESCE(consumable_from_local_date, 'infinity'::date),
                    CASE
                        WHEN consumable_to_local_date IS NULL THEN 'infinity'::date
                        ELSE consumable_to_local_date
                    END,
                    '[)'
                )
            ) STORED,
            effective_from DATE NOT NULL,
            effective_to DATE,
            effective_to_exclusive DATE GENERATED ALWAYS AS (
                CASE
                    WHEN effective_to IS NULL THEN 'infinity'::date
                    ELSE effective_to + 1
                END
            ) STORED,
            effective_range DATERANGE GENERATED ALWAYS AS (
                daterange(
                    effective_from,
                    CASE
                        WHEN effective_to IS NULL THEN 'infinity'::date
                        ELSE effective_to + 1
                    END,
                    '[)'
                )
            ) STORED,
            status TEXT NOT NULL
                CONSTRAINT ck_task9_weather_rule_config_version_status
                CHECK (status IN ('draft', 'active', 'superseded', 'retired', 'cancelled')),
            status_changed_at TIMESTAMPTZ NOT NULL,
            superseded_by_id BIGINT NULL
                CONSTRAINT fk_task9_weather_rule_config_version_superseded_by
                REFERENCES task9_weather_rule_config_version(id) ON DELETE RESTRICT,
            source_system TEXT NOT NULL,
            source_record_key TEXT NOT NULL,
            source_version TEXT NOT NULL,
            row_hash TEXT NOT NULL
                CONSTRAINT ck_task9_weather_rule_config_version_row_hash_sha256
                CHECK (row_hash ~ '^[0-9a-f]{64}$'),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_task9_weather_rule_config_version_business_revision UNIQUE (
                rule_code,
                lifecycle_timezone_name,
                rule_version,
                revision
            ),
            CONSTRAINT ck_task9_weather_rule_config_version_timezone_non_blank
                CHECK (btrim(lifecycle_timezone_name) <> ''),
            CONSTRAINT ck_task9_weather_rule_config_version_ratio_bounds
                CHECK (maximum_ratio >= minimum_ratio),
            CONSTRAINT ck_task9_weather_rule_config_version_effective_range
                CHECK (
                    effective_to IS NULL
                    OR (effective_to >= effective_from AND effective_to < 'infinity'::date)
                ),
            CONSTRAINT ck_task9_weather_rule_config_version_self_ref
                CHECK (superseded_by_id IS NULL OR superseded_by_id <> id),
            CONSTRAINT ck_task9_weather_rule_config_version_superseded
                CHECK (
                    (status = 'superseded' AND superseded_by_id IS NOT NULL)
                    OR (status <> 'superseded' AND superseded_by_id IS NULL)
                ),
            CONSTRAINT ck_task9_weather_rule_config_version_lifecycle_projection
                CHECK (
                    (
                        status IN ('draft', 'cancelled')
                        AND consumable_from_local_date IS NULL
                        AND consumable_to_local_date IS NULL
                    )
                    OR (
                        status = 'active'
                        AND consumable_from_local_date IS NOT NULL
                        AND consumable_to_local_date IS NULL
                    )
                    OR (
                        status IN ('superseded', 'retired')
                        AND consumable_from_local_date IS NOT NULL
                        AND consumable_to_local_date IS NOT NULL
                    )
                ),
            CONSTRAINT ck_task9_weather_rule_config_version_consumable_from
                CHECK (
                    consumable_from_local_date IS NULL
                    OR consumable_from_local_date >= available_at_local_date
                ),
            CONSTRAINT ck_task9_weather_rule_config_version_consumable_to
                CHECK (
                    consumable_to_local_date IS NULL
                    OR consumable_to_local_date > consumable_from_local_date
                )
        )
        """
    )
    _execute(
        """
        CREATE TABLE task9_run_parameter_package (
            id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
            season_id BIGINT NOT NULL REFERENCES dim_season(id) ON DELETE RESTRICT,
            destination_factory_id BIGINT NOT NULL REFERENCES dim_factory(id) ON DELETE RESTRICT,
            farm_scope_key TEXT NOT NULL,
            package_version TEXT NOT NULL,
            revision INTEGER NOT NULL
                CONSTRAINT ck_task9_run_parameter_package_revision CHECK (revision > 0),
            farm_timezone TEXT NOT NULL,
            destination_factory_timezone TEXT NOT NULL,
            harvest_bucket_anchor_local_time TIME NOT NULL,
            harvest_to_arrival_lag_days INTEGER NOT NULL
                CONSTRAINT ck_task9_run_parameter_package_arrival_lag_non_negative
                CHECK (harvest_to_arrival_lag_days >= 0),
            holiday_calendar_version_id BIGINT NOT NULL
                CONSTRAINT fk_task9_run_parameter_package_holiday
                REFERENCES task9_holiday_calendar_version(id) ON DELETE RESTRICT,
            weather_rule_config_version_id BIGINT NOT NULL
                CONSTRAINT fk_task9_run_parameter_package_weather
                REFERENCES task9_weather_rule_config_version(id) ON DELETE RESTRICT,
            available_at_local_date DATE NOT NULL,
            consumable_from_local_date DATE,
            consumable_to_local_date DATE,
            consumability_range DATERANGE GENERATED ALWAYS AS (
                daterange(
                    COALESCE(consumable_from_local_date, 'infinity'::date),
                    CASE
                        WHEN consumable_to_local_date IS NULL THEN 'infinity'::date
                        ELSE consumable_to_local_date
                    END,
                    '[)'
                )
            ) STORED,
            effective_from DATE NOT NULL,
            effective_to DATE,
            effective_to_exclusive DATE GENERATED ALWAYS AS (
                CASE
                    WHEN effective_to IS NULL THEN 'infinity'::date
                    ELSE effective_to + 1
                END
            ) STORED,
            effective_range DATERANGE GENERATED ALWAYS AS (
                daterange(
                    effective_from,
                    CASE
                        WHEN effective_to IS NULL THEN 'infinity'::date
                        ELSE effective_to + 1
                    END,
                    '[)'
                )
            ) STORED,
            status TEXT NOT NULL
                CONSTRAINT ck_task9_run_parameter_package_status
                CHECK (status IN ('draft', 'active', 'superseded', 'retired', 'cancelled')),
            status_changed_at TIMESTAMPTZ NOT NULL,
            superseded_by_id BIGINT NULL
                CONSTRAINT fk_task9_run_parameter_package_superseded_by
                REFERENCES task9_run_parameter_package(id) ON DELETE RESTRICT,
            source_system TEXT NOT NULL,
            source_record_key TEXT NOT NULL,
            source_version TEXT NOT NULL,
            row_hash TEXT NOT NULL
                CONSTRAINT ck_task9_run_parameter_package_row_hash_sha256
                CHECK (row_hash ~ '^[0-9a-f]{64}$'),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_task9_run_parameter_package_business_revision UNIQUE (
                season_id,
                destination_factory_id,
                farm_scope_key,
                package_version,
                revision
            ),
            CONSTRAINT ck_task9_run_parameter_package_farm_timezone_non_blank
                CHECK (btrim(farm_timezone) <> ''),
            CONSTRAINT ck_task9_run_parameter_package_factory_timezone_non_blank
                CHECK (btrim(destination_factory_timezone) <> ''),
            CONSTRAINT ck_task9_run_parameter_package_effective_range
                CHECK (
                    effective_to IS NULL
                    OR (effective_to >= effective_from AND effective_to < 'infinity'::date)
                ),
            CONSTRAINT ck_task9_run_parameter_package_self_ref
                CHECK (superseded_by_id IS NULL OR superseded_by_id <> id),
            CONSTRAINT ck_task9_run_parameter_package_superseded
                CHECK (
                    (status = 'superseded' AND superseded_by_id IS NOT NULL)
                    OR (status <> 'superseded' AND superseded_by_id IS NULL)
                ),
            CONSTRAINT ck_task9_run_parameter_package_lifecycle_projection
                CHECK (
                    (
                        status IN ('draft', 'cancelled')
                        AND consumable_from_local_date IS NULL
                        AND consumable_to_local_date IS NULL
                    )
                    OR (
                        status = 'active'
                        AND consumable_from_local_date IS NOT NULL
                        AND consumable_to_local_date IS NULL
                    )
                    OR (
                        status IN ('superseded', 'retired')
                        AND consumable_from_local_date IS NOT NULL
                        AND consumable_to_local_date IS NOT NULL
                    )
                ),
            CONSTRAINT ck_task9_run_parameter_package_consumable_from
                CHECK (
                    consumable_from_local_date IS NULL
                    OR consumable_from_local_date >= available_at_local_date
                ),
            CONSTRAINT ck_task9_run_parameter_package_consumable_to
                CHECK (
                    consumable_to_local_date IS NULL
                    OR consumable_to_local_date > consumable_from_local_date
                )
        )
        """
    )
    _execute(
        """
        CREATE TABLE task9_capacity_pool_definition (
            id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
            season_id BIGINT NOT NULL REFERENCES dim_season(id) ON DELETE RESTRICT,
            destination_factory_id BIGINT NOT NULL REFERENCES dim_factory(id) ON DELETE RESTRICT,
            capacity_pool_code TEXT NOT NULL,
            capacity_pool_version TEXT NOT NULL,
            revision INTEGER NOT NULL
                CONSTRAINT ck_task9_capacity_pool_definition_revision CHECK (revision > 0),
            capacity_pool_grain TEXT NOT NULL
                CONSTRAINT ck_task9_capacity_pool_definition_grain
                CHECK (capacity_pool_grain IN ('FARM', 'SUBFARM', 'SUBFARM_VARIETY')),
            capacity_input_mode TEXT NOT NULL
                CONSTRAINT ck_task9_capacity_pool_definition_mode
                CHECK (capacity_input_mode IN ('LABOR_DERIVED', 'DIRECT_CAPACITY')),
            effective_from DATE NOT NULL,
            effective_to DATE,
            effective_to_exclusive DATE GENERATED ALWAYS AS (
                CASE
                    WHEN effective_to IS NULL THEN 'infinity'::date
                    ELSE effective_to + 1
                END
            ) STORED,
            effective_range DATERANGE GENERATED ALWAYS AS (
                daterange(
                    effective_from,
                    CASE
                        WHEN effective_to IS NULL THEN 'infinity'::date
                        ELSE effective_to + 1
                    END,
                    '[)'
                )
            ) STORED,
            available_at_local_date DATE NOT NULL,
            consumable_from_local_date DATE,
            consumable_to_local_date DATE,
            consumable_from_key DATE GENERATED ALWAYS AS (
                COALESCE(consumable_from_local_date, 'infinity'::date)
            ) STORED,
            consumable_to_key DATE GENERATED ALWAYS AS (
                COALESCE(consumable_to_local_date, 'infinity'::date)
            ) STORED,
            consumability_range DATERANGE GENERATED ALWAYS AS (
                daterange(
                    COALESCE(consumable_from_local_date, 'infinity'::date),
                    CASE
                        WHEN consumable_to_local_date IS NULL THEN 'infinity'::date
                        ELSE consumable_to_local_date
                    END,
                    '[)'
                )
            ) STORED,
            status TEXT NOT NULL
                CONSTRAINT ck_task9_capacity_pool_definition_status
                CHECK (status IN ('draft', 'active', 'superseded', 'retired', 'cancelled')),
            status_changed_at TIMESTAMPTZ NOT NULL,
            source_system TEXT NOT NULL,
            source_record_key TEXT NOT NULL,
            source_version TEXT NOT NULL,
            row_hash TEXT NOT NULL
                CONSTRAINT ck_task9_capacity_pool_definition_row_hash_sha256
                CHECK (row_hash ~ '^[0-9a-f]{64}$'),
            superseded_by_id BIGINT NULL
                CONSTRAINT fk_task9_capacity_pool_definition_superseded_by
                REFERENCES task9_capacity_pool_definition(id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_task9_capacity_pool_definition_business_revision UNIQUE (
                season_id,
                destination_factory_id,
                capacity_pool_code,
                capacity_pool_version,
                revision
            ),
            CONSTRAINT uq_task9_capacity_pool_definition_effective_binding UNIQUE (
                id,
                season_id,
                destination_factory_id,
                effective_from,
                effective_to_exclusive
            ),
            CONSTRAINT uq_task9_capacity_pool_definition_lifecycle_binding UNIQUE (
                id,
                status,
                consumable_from_key,
                consumable_to_key
            ),
            CONSTRAINT ck_task9_capacity_pool_definition_effective_range
                CHECK (
                    effective_to IS NULL
                    OR (effective_to >= effective_from AND effective_to < 'infinity'::date)
                ),
            CONSTRAINT ck_task9_capacity_pool_definition_self_ref
                CHECK (superseded_by_id IS NULL OR superseded_by_id <> id),
            CONSTRAINT ck_task9_capacity_pool_definition_superseded
                CHECK (
                    (status = 'superseded' AND superseded_by_id IS NOT NULL)
                    OR (status <> 'superseded' AND superseded_by_id IS NULL)
                ),
            CONSTRAINT ck_task9_capacity_pool_definition_lifecycle_projection
                CHECK (
                    (
                        status IN ('draft', 'cancelled')
                        AND consumable_from_local_date IS NULL
                        AND consumable_to_local_date IS NULL
                    )
                    OR (
                        status = 'active'
                        AND consumable_from_local_date IS NOT NULL
                        AND consumable_to_local_date IS NULL
                    )
                    OR (
                        status IN ('superseded', 'retired')
                        AND consumable_from_local_date IS NOT NULL
                        AND consumable_to_local_date IS NOT NULL
                    )
                ),
            CONSTRAINT ck_task9_capacity_pool_definition_consumable_from
                CHECK (
                    consumable_from_local_date IS NULL
                    OR consumable_from_local_date >= available_at_local_date
                ),
            CONSTRAINT ck_task9_capacity_pool_definition_consumable_to
                CHECK (
                    consumable_to_local_date IS NULL
                    OR consumable_to_local_date > consumable_from_local_date
                )
        )
        """
    )
    _execute(
        """
        CREATE TABLE task9_capacity_pool_member (
            id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
            capacity_pool_definition_id BIGINT NOT NULL
                CONSTRAINT fk_task9_capacity_pool_member_parent
                REFERENCES task9_capacity_pool_definition(id) ON DELETE RESTRICT,
            season_id BIGINT NOT NULL REFERENCES dim_season(id) ON DELETE RESTRICT,
            destination_factory_id BIGINT NOT NULL REFERENCES dim_factory(id) ON DELETE RESTRICT,
            farm_id BIGINT NOT NULL REFERENCES dim_farm(id) ON DELETE RESTRICT,
            subfarm_id BIGINT REFERENCES dim_subfarm(id) ON DELETE RESTRICT,
            normalized_subfarm_id BIGINT GENERATED ALWAYS AS (COALESCE(subfarm_id, 0)) STORED,
            variety_id BIGINT NOT NULL REFERENCES dim_variety(id) ON DELETE RESTRICT,
            effective_from DATE NOT NULL,
            effective_to DATE,
            effective_to_exclusive DATE GENERATED ALWAYS AS (
                CASE
                    WHEN effective_to IS NULL THEN 'infinity'::date
                    ELSE effective_to + 1
                END
            ) STORED,
            effective_range DATERANGE GENERATED ALWAYS AS (
                daterange(
                    effective_from,
                    CASE
                        WHEN effective_to IS NULL THEN 'infinity'::date
                        ELSE effective_to + 1
                    END,
                    '[)'
                )
            ) STORED,
            status TEXT NOT NULL
                CONSTRAINT ck_task9_capacity_pool_member_status
                CHECK (status IN ('draft', 'active', 'superseded', 'retired', 'cancelled')),
            consumable_from_key DATE NOT NULL,
            consumable_to_key DATE NOT NULL,
            consumability_range DATERANGE GENERATED ALWAYS AS (
                daterange(consumable_from_key, consumable_to_key, '[)')
            ) STORED,
            row_hash TEXT NOT NULL
                CONSTRAINT ck_task9_capacity_pool_member_row_hash_sha256
                CHECK (row_hash ~ '^[0-9a-f]{64}$'),
            CONSTRAINT uq_task9_capacity_pool_member_business_key
                UNIQUE NULLS NOT DISTINCT (
                    capacity_pool_definition_id,
                    farm_id,
                    subfarm_id,
                    variety_id
                ),
            CONSTRAINT ck_task9_capacity_pool_member_farm_positive CHECK (farm_id > 0),
            CONSTRAINT ck_task9_capacity_pool_member_subfarm_positive
                CHECK (subfarm_id IS NULL OR subfarm_id > 0),
            CONSTRAINT ck_task9_capacity_pool_member_variety_positive CHECK (variety_id > 0),
            CONSTRAINT ck_task9_capacity_pool_member_effective_range
                CHECK (
                    effective_to IS NULL
                    OR (effective_to >= effective_from AND effective_to < 'infinity'::date)
                ),
            CONSTRAINT fk_task9_capacity_pool_member_effective_binding
                FOREIGN KEY (
                    capacity_pool_definition_id,
                    season_id,
                    destination_factory_id,
                    effective_from,
                    effective_to_exclusive
                )
                REFERENCES task9_capacity_pool_definition (
                    id,
                    season_id,
                    destination_factory_id,
                    effective_from,
                    effective_to_exclusive
                )
                ON DELETE RESTRICT
                ON UPDATE RESTRICT,
            CONSTRAINT fk_task9_capacity_pool_member_lifecycle_binding
                FOREIGN KEY (
                    capacity_pool_definition_id,
                    status,
                    consumable_from_key,
                    consumable_to_key
                )
                REFERENCES task9_capacity_pool_definition (
                    id,
                    status,
                    consumable_from_key,
                    consumable_to_key
                )
                ON DELETE RESTRICT
                ON UPDATE CASCADE
        )
        """
    )
    _execute(
        """
        CREATE TABLE task9_daily_capacity_authority (
            id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
            capacity_pool_definition_id BIGINT NOT NULL
                CONSTRAINT fk_task9_daily_capacity_authority_parent
                REFERENCES task9_capacity_pool_definition(id) ON DELETE RESTRICT,
            capacity_date DATE NOT NULL,
            daily_capacity_revision INTEGER NOT NULL
                CONSTRAINT ck_task9_daily_capacity_authority_revision CHECK (daily_capacity_revision > 0),
            planned_picker_count NUMERIC(18, 3),
            kg_per_person_per_day NUMERIC(18, 3),
            direct_nominal_capacity_kg_per_day NUMERIC(18, 3),
            labor_availability_ratio NUMERIC(12, 6) NOT NULL
                CONSTRAINT ck_task9_daily_capacity_authority_labor_ratio
                CHECK (labor_availability_ratio >= 0 AND labor_availability_ratio <= 1),
            operational_efficiency_ratio NUMERIC(12, 6) NOT NULL
                CONSTRAINT ck_task9_daily_capacity_authority_operational_ratio
                CHECK (operational_efficiency_ratio >= 0 AND operational_efficiency_ratio <= 1),
            available_at_local_date DATE NOT NULL,
            consumable_from_local_date DATE,
            consumable_to_local_date DATE,
            consumability_range DATERANGE GENERATED ALWAYS AS (
                daterange(
                    COALESCE(consumable_from_local_date, 'infinity'::date),
                    CASE
                        WHEN consumable_to_local_date IS NULL THEN 'infinity'::date
                        ELSE consumable_to_local_date
                    END,
                    '[)'
                )
            ) STORED,
            status TEXT NOT NULL
                CONSTRAINT ck_task9_daily_capacity_authority_status
                CHECK (status IN ('draft', 'active', 'superseded', 'retired', 'cancelled')),
            status_changed_at TIMESTAMPTZ NOT NULL,
            superseded_by_id BIGINT NULL
                CONSTRAINT fk_task9_daily_capacity_authority_superseded_by
                REFERENCES task9_daily_capacity_authority(id) ON DELETE RESTRICT,
            source_system TEXT NOT NULL,
            source_record_key TEXT NOT NULL,
            source_version TEXT NOT NULL,
            row_hash TEXT NOT NULL
                CONSTRAINT ck_task9_daily_capacity_authority_row_hash_sha256
                CHECK (row_hash ~ '^[0-9a-f]{64}$'),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_task9_daily_capacity_authority_business_revision UNIQUE (
                capacity_pool_definition_id,
                capacity_date,
                daily_capacity_revision
            ),
            CONSTRAINT ck_task9_daily_capacity_authority_self_ref
                CHECK (superseded_by_id IS NULL OR superseded_by_id <> id),
            CONSTRAINT ck_task9_daily_capacity_authority_superseded
                CHECK (
                    (status = 'superseded' AND superseded_by_id IS NOT NULL)
                    OR (status <> 'superseded' AND superseded_by_id IS NULL)
                ),
            CONSTRAINT ck_task9_daily_capacity_authority_mode_fields
                CHECK (
                    (
                        planned_picker_count IS NOT NULL
                        AND kg_per_person_per_day IS NOT NULL
                        AND direct_nominal_capacity_kg_per_day IS NULL
                    )
                    OR (
                        direct_nominal_capacity_kg_per_day IS NOT NULL
                        AND planned_picker_count IS NULL
                        AND kg_per_person_per_day IS NULL
                    )
                ),
            CONSTRAINT ck_task9_daily_capacity_authority_lifecycle_projection
                CHECK (
                    (
                        status IN ('draft', 'cancelled')
                        AND consumable_from_local_date IS NULL
                        AND consumable_to_local_date IS NULL
                    )
                    OR (
                        status = 'active'
                        AND consumable_from_local_date IS NOT NULL
                        AND consumable_to_local_date IS NULL
                    )
                    OR (
                        status IN ('superseded', 'retired')
                        AND consumable_from_local_date IS NOT NULL
                        AND consumable_to_local_date IS NOT NULL
                    )
                ),
            CONSTRAINT ck_task9_daily_capacity_authority_consumable_from
                CHECK (
                    consumable_from_local_date IS NULL
                    OR consumable_from_local_date >= available_at_local_date
                ),
            CONSTRAINT ck_task9_daily_capacity_authority_consumable_to
                CHECK (
                    consumable_to_local_date IS NULL
                    OR consumable_to_local_date > consumable_from_local_date
                )
        )
        """
    )
    _execute(
        """
        CREATE TABLE task9_initial_inventory_snapshot (
            id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
            season_id BIGINT NOT NULL REFERENCES dim_season(id) ON DELETE RESTRICT,
            destination_factory_id BIGINT NOT NULL REFERENCES dim_factory(id) ON DELETE RESTRICT,
            opening_state_date DATE NOT NULL,
            snapshot_version TEXT NOT NULL,
            revision INTEGER NOT NULL
                CONSTRAINT ck_task9_initial_inventory_snapshot_revision CHECK (revision > 0),
            initial_opening_mature_inventory_kg NUMERIC(18, 6) NOT NULL
                CONSTRAINT ck_task9_initial_inventory_snapshot_opening_non_negative
                CHECK (initial_opening_mature_inventory_kg >= 0),
            available_at_local_date DATE NOT NULL,
            consumable_from_local_date DATE,
            consumable_to_local_date DATE,
            consumability_range DATERANGE GENERATED ALWAYS AS (
                daterange(
                    COALESCE(consumable_from_local_date, 'infinity'::date),
                    CASE
                        WHEN consumable_to_local_date IS NULL THEN 'infinity'::date
                        ELSE consumable_to_local_date
                    END,
                    '[)'
                )
            ) STORED,
            status TEXT NOT NULL
                CONSTRAINT ck_task9_initial_inventory_snapshot_status
                CHECK (status IN ('draft', 'active', 'superseded', 'retired', 'cancelled')),
            status_changed_at TIMESTAMPTZ NOT NULL,
            superseded_by_id BIGINT NULL
                CONSTRAINT fk_task9_initial_inventory_snapshot_superseded_by
                REFERENCES task9_initial_inventory_snapshot(id) ON DELETE RESTRICT,
            source_system TEXT NOT NULL,
            source_record_key TEXT NOT NULL,
            source_version TEXT NOT NULL,
            row_hash TEXT NOT NULL
                CONSTRAINT ck_task9_initial_inventory_snapshot_row_hash_sha256
                CHECK (row_hash ~ '^[0-9a-f]{64}$'),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_task9_initial_inventory_snapshot_business_revision UNIQUE (
                season_id,
                destination_factory_id,
                opening_state_date,
                snapshot_version,
                revision
            ),
            CONSTRAINT ck_task9_initial_inventory_snapshot_self_ref
                CHECK (superseded_by_id IS NULL OR superseded_by_id <> id),
            CONSTRAINT ck_task9_initial_inventory_snapshot_superseded
                CHECK (
                    (status = 'superseded' AND superseded_by_id IS NOT NULL)
                    OR (status <> 'superseded' AND superseded_by_id IS NULL)
                ),
            CONSTRAINT ck_task9_initial_inventory_snapshot_lifecycle_projection
                CHECK (
                    (
                        status IN ('draft', 'cancelled')
                        AND consumable_from_local_date IS NULL
                        AND consumable_to_local_date IS NULL
                    )
                    OR (
                        status = 'active'
                        AND consumable_from_local_date IS NOT NULL
                        AND consumable_to_local_date IS NULL
                    )
                    OR (
                        status IN ('superseded', 'retired')
                        AND consumable_from_local_date IS NOT NULL
                        AND consumable_to_local_date IS NOT NULL
                    )
                ),
            CONSTRAINT ck_task9_initial_inventory_snapshot_consumable_from
                CHECK (
                    consumable_from_local_date IS NULL
                    OR consumable_from_local_date >= available_at_local_date
                ),
            CONSTRAINT ck_task9_initial_inventory_snapshot_consumable_to
                CHECK (
                    consumable_to_local_date IS NULL
                    OR consumable_to_local_date > consumable_from_local_date
                )
        )
        """
    )
    _execute(
        """
        CREATE TABLE task9_initial_inventory_cohort (
            id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
            initial_inventory_snapshot_id BIGINT NOT NULL
                CONSTRAINT fk_task9_initial_inventory_cohort_parent
                REFERENCES task9_initial_inventory_snapshot(id) ON DELETE RESTRICT,
            stable_cohort_key TEXT NOT NULL,
            forecast_quantile TEXT NOT NULL
                CONSTRAINT ck_task9_initial_inventory_cohort_quantile
                CHECK (forecast_quantile IN ('P50', 'P80', 'P90')),
            cohort_date DATE NOT NULL,
            farm_id BIGINT NOT NULL REFERENCES dim_farm(id) ON DELETE RESTRICT,
            subfarm_id BIGINT REFERENCES dim_subfarm(id) ON DELETE RESTRICT,
            variety_id BIGINT NOT NULL REFERENCES dim_variety(id) ON DELETE RESTRICT,
            remaining_quantity_kg NUMERIC(18, 6) NOT NULL
                CONSTRAINT ck_task9_initial_inventory_cohort_remaining_non_negative
                CHECK (remaining_quantity_kg >= 0),
            row_hash TEXT NOT NULL
                CONSTRAINT ck_task9_initial_inventory_cohort_row_hash_sha256
                CHECK (row_hash ~ '^[0-9a-f]{64}$'),
            CONSTRAINT uq_task9_initial_inventory_cohort_stable_key
                UNIQUE (initial_inventory_snapshot_id, stable_cohort_key)
        )
        """
    )
    _execute(
        """
        CREATE TABLE task9_mature_inventory_loss_authority (
            id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
            season_id BIGINT NOT NULL REFERENCES dim_season(id) ON DELETE RESTRICT,
            destination_factory_id BIGINT NOT NULL REFERENCES dim_factory(id) ON DELETE RESTRICT,
            state_date DATE NOT NULL,
            capacity_pool_code TEXT NOT NULL,
            forecast_quantile TEXT NOT NULL
                CONSTRAINT ck_task9_mature_inventory_loss_authority_quantile
                CHECK (forecast_quantile IN ('P50', 'P80', 'P90')),
            loss_version TEXT NOT NULL,
            revision INTEGER NOT NULL
                CONSTRAINT ck_task9_mature_inventory_loss_authority_revision CHECK (revision > 0),
            mature_inventory_loss_quantity_kg NUMERIC(18, 6) NOT NULL
                CONSTRAINT ck_task9_mature_inventory_loss_authority_quantity_non_negative
                CHECK (mature_inventory_loss_quantity_kg >= 0),
            available_at_local_date DATE NOT NULL,
            consumable_from_local_date DATE,
            consumable_to_local_date DATE,
            consumability_range DATERANGE GENERATED ALWAYS AS (
                daterange(
                    COALESCE(consumable_from_local_date, 'infinity'::date),
                    CASE
                        WHEN consumable_to_local_date IS NULL THEN 'infinity'::date
                        ELSE consumable_to_local_date
                    END,
                    '[)'
                )
            ) STORED,
            status TEXT NOT NULL
                CONSTRAINT ck_task9_mature_inventory_loss_authority_status
                CHECK (status IN ('draft', 'active', 'superseded', 'retired', 'cancelled')),
            status_changed_at TIMESTAMPTZ NOT NULL,
            superseded_by_id BIGINT NULL
                CONSTRAINT fk_task9_mature_inventory_loss_authority_superseded_by
                REFERENCES task9_mature_inventory_loss_authority(id) ON DELETE RESTRICT,
            source_system TEXT NOT NULL,
            source_record_key TEXT NOT NULL,
            source_version TEXT NOT NULL,
            row_hash TEXT NOT NULL
                CONSTRAINT ck_task9_mature_inventory_loss_authority_row_hash_sha256
                CHECK (row_hash ~ '^[0-9a-f]{64}$'),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_task9_mature_inventory_loss_authority_business_revision UNIQUE (
                season_id,
                destination_factory_id,
                state_date,
                capacity_pool_code,
                forecast_quantile,
                loss_version,
                revision
            ),
            CONSTRAINT ck_task9_mature_inventory_loss_authority_self_ref
                CHECK (superseded_by_id IS NULL OR superseded_by_id <> id),
            CONSTRAINT ck_task9_mature_inventory_loss_authority_superseded
                CHECK (
                    (status = 'superseded' AND superseded_by_id IS NOT NULL)
                    OR (status <> 'superseded' AND superseded_by_id IS NULL)
                ),
            CONSTRAINT ck_task9_mature_inventory_loss_authority_lifecycle_projection
                CHECK (
                    (
                        status IN ('draft', 'cancelled')
                        AND consumable_from_local_date IS NULL
                        AND consumable_to_local_date IS NULL
                    )
                    OR (
                        status = 'active'
                        AND consumable_from_local_date IS NOT NULL
                        AND consumable_to_local_date IS NULL
                    )
                    OR (
                        status IN ('superseded', 'retired')
                        AND consumable_from_local_date IS NOT NULL
                        AND consumable_to_local_date IS NOT NULL
                    )
                ),
            CONSTRAINT ck_task9_mature_inventory_loss_authority_consumable_from
                CHECK (
                    consumable_from_local_date IS NULL
                    OR consumable_from_local_date >= available_at_local_date
                ),
            CONSTRAINT ck_task9_mature_inventory_loss_authority_consumable_to
                CHECK (
                    consumable_to_local_date IS NULL
                    OR consumable_to_local_date > consumable_from_local_date
                )
        )
        """
    )
    _execute(
        """
        CREATE TABLE task9_authority_lifecycle_event (
            id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
            authority_family TEXT NOT NULL
                CONSTRAINT ck_task9_authority_lifecycle_event_family
                CHECK (
                    authority_family IN (
                        'capacity_pool_definition',
                        'daily_capacity',
                        'run_parameter_package',
                        'holiday_calendar_version',
                        'weather_rule_config_version',
                        'initial_inventory_snapshot',
                        'mature_inventory_loss_authority'
                    )
                ),
            authority_stable_key TEXT NOT NULL,
            authority_business_version TEXT NOT NULL,
            authority_revision INTEGER NOT NULL
                CONSTRAINT ck_task9_authority_lifecycle_event_revision_positive
                CHECK (authority_revision > 0),
            business_row_hash TEXT NOT NULL
                CONSTRAINT ck_task9_authority_lifecycle_event_business_row_hash_sha256
                CHECK (business_row_hash ~ '^[0-9a-f]{64}$'),
            transition_sequence INTEGER NOT NULL
                CONSTRAINT ck_task9_authority_lifecycle_event_transition_sequence_positive
                CHECK (transition_sequence >= 1),
            old_status TEXT
                CONSTRAINT ck_task9_authority_lifecycle_event_old_status
                CHECK (
                    old_status IS NULL
                    OR old_status IN ('draft', 'active', 'superseded', 'retired', 'cancelled')
                ),
            new_status TEXT NOT NULL
                CONSTRAINT ck_task9_authority_lifecycle_event_new_status
                CHECK (new_status IN ('draft', 'active', 'superseded', 'retired', 'cancelled')),
            old_consumable_from_local_date DATE,
            old_consumable_to_local_date DATE,
            new_consumable_from_local_date DATE,
            new_consumable_to_local_date DATE,
            superseded_by_authority_stable_key TEXT,
            superseded_by_authority_business_version TEXT,
            superseded_by_authority_revision INTEGER
                CONSTRAINT ck_task9_lifecycle_event_repl_rev_positive
                CHECK (superseded_by_authority_revision IS NULL OR superseded_by_authority_revision > 0),
            transitioned_at TIMESTAMPTZ NOT NULL,
            source_system TEXT NOT NULL,
            source_record_key TEXT NOT NULL,
            lifecycle_event_hash TEXT NOT NULL
                CONSTRAINT ck_task9_authority_lifecycle_event_hash_sha256
                CHECK (lifecycle_event_hash ~ '^[0-9a-f]{64}$'),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_task9_authority_lifecycle_event_identity_sequence UNIQUE (
                authority_family,
                authority_stable_key,
                authority_business_version,
                authority_revision,
                transition_sequence
            ),
            CONSTRAINT uq_task9_authority_lifecycle_event_identity_hash UNIQUE (
                authority_family,
                authority_stable_key,
                authority_business_version,
                authority_revision,
                lifecycle_event_hash
            ),
            CONSTRAINT ck_task9_authority_lifecycle_event_replacement_all_or_none
                CHECK (
                    (
                        superseded_by_authority_stable_key IS NULL
                        AND superseded_by_authority_business_version IS NULL
                        AND superseded_by_authority_revision IS NULL
                    )
                    OR (
                        superseded_by_authority_stable_key IS NOT NULL
                        AND superseded_by_authority_business_version IS NOT NULL
                        AND superseded_by_authority_revision IS NOT NULL
                    )
                ),
            CONSTRAINT ck_task9_lifecycle_event_superseded_repl
                CHECK (
                    (
                        new_status = 'superseded'
                        AND superseded_by_authority_stable_key IS NOT NULL
                    )
                    OR (
                        new_status <> 'superseded'
                        AND superseded_by_authority_stable_key IS NULL
                    )
                )
        )
        """
    )

    _execute(
        "CREATE INDEX ix_task9_capacity_pool_def_available ON task9_capacity_pool_definition(available_at_local_date)"
    )
    _execute(
        "CREATE INDEX ix_task9_daily_capacity_available ON task9_daily_capacity_authority(available_at_local_date)"
    )
    _execute(
        "CREATE INDEX ix_task9_run_parameter_package_available ON task9_run_parameter_package(available_at_local_date)"
    )
    _execute(
        "CREATE INDEX ix_task9_holiday_calendar_available ON task9_holiday_calendar_version(available_at_local_date)"
    )
    _execute(
        "CREATE INDEX ix_task9_weather_rule_available ON task9_weather_rule_config_version(available_at_local_date)"
    )
    _execute(
        "CREATE INDEX ix_task9_initial_inventory_available ON task9_initial_inventory_snapshot(available_at_local_date)"
    )
    _execute(
        "CREATE INDEX ix_task9_mature_loss_available ON task9_mature_inventory_loss_authority(available_at_local_date)"
    )
    _execute(
        "CREATE UNIQUE INDEX uq_task9_daily_capacity_one_active ON task9_daily_capacity_authority(capacity_pool_definition_id, capacity_date) WHERE (status = 'active')"
    )
    _execute(
        "CREATE UNIQUE INDEX uq_task9_initial_inventory_one_active ON task9_initial_inventory_snapshot(season_id, destination_factory_id, opening_state_date) WHERE (status = 'active')"
    )
    _execute(
        "CREATE UNIQUE INDEX uq_task9_mature_loss_one_active ON task9_mature_inventory_loss_authority(season_id, destination_factory_id, state_date, capacity_pool_code, forecast_quantile) WHERE (status = 'active')"
    )
    _execute(
        "CREATE UNIQUE INDEX uq_task9_holiday_calendar_one_active ON task9_holiday_calendar_version(season_id, calendar_code, lifecycle_timezone_name) WHERE (status = 'active')"
    )
    _execute(
        "CREATE UNIQUE INDEX uq_task9_weather_rule_one_active ON task9_weather_rule_config_version(rule_code, lifecycle_timezone_name) WHERE (status = 'active')"
    )
    _execute(
        "CREATE INDEX ix_task9_authority_lifecycle_event_identity_sequence ON task9_authority_lifecycle_event(authority_family, authority_stable_key, authority_business_version, authority_revision, transition_sequence)"
    )
    _execute(
        "CREATE INDEX ix_task9_authority_lifecycle_event_source_record ON task9_authority_lifecycle_event(source_system, source_record_key)"
    )

    _execute(
        """
        ALTER TABLE task9_capacity_pool_definition
        ADD CONSTRAINT ex_task9_capacity_pool_definition_combined_overlap
        EXCLUDE USING gist (
            season_id WITH =,
            destination_factory_id WITH =,
            capacity_pool_code WITH =,
            effective_range WITH &&,
            consumability_range WITH &&
        )
        """
    )
    _execute(
        """
        ALTER TABLE task9_capacity_pool_member
        ADD CONSTRAINT ex_task9_capacity_pool_member_combined_overlap
        EXCLUDE USING gist (
            season_id WITH =,
            destination_factory_id WITH =,
            farm_id WITH =,
            normalized_subfarm_id WITH =,
            variety_id WITH =,
            effective_range WITH &&,
            consumability_range WITH &&
        )
        """
    )
    _execute(
        """
        ALTER TABLE task9_run_parameter_package
        ADD CONSTRAINT ex_task9_run_parameter_package_combined_overlap
        EXCLUDE USING gist (
            season_id WITH =,
            destination_factory_id WITH =,
            farm_scope_key WITH =,
            effective_range WITH &&,
            consumability_range WITH &&
        )
        """
    )
    _execute(
        """
        ALTER TABLE task9_daily_capacity_authority
        ADD CONSTRAINT ex_task9_daily_capacity_consumability_overlap
        EXCLUDE USING gist (
            capacity_pool_definition_id WITH =,
            capacity_date WITH =,
            consumability_range WITH &&
        )
        """
    )
    _execute(
        """
        ALTER TABLE task9_holiday_calendar_version
        ADD CONSTRAINT ex_task9_holiday_calendar_consumability_overlap
        EXCLUDE USING gist (
            season_id WITH =,
            calendar_code WITH =,
            lifecycle_timezone_name WITH =,
            consumability_range WITH &&
        )
        """
    )
    _execute(
        """
        ALTER TABLE task9_weather_rule_config_version
        ADD CONSTRAINT ex_task9_weather_rule_combined_overlap
        EXCLUDE USING gist (
            rule_code WITH =,
            lifecycle_timezone_name WITH =,
            effective_range WITH &&,
            consumability_range WITH &&
        )
        """
    )
    _execute(
        """
        ALTER TABLE task9_initial_inventory_snapshot
        ADD CONSTRAINT ex_task9_initial_inventory_consumability_overlap
        EXCLUDE USING gist (
            season_id WITH =,
            destination_factory_id WITH =,
            opening_state_date WITH =,
            consumability_range WITH &&
        )
        """
    )
    _execute(
        """
        ALTER TABLE task9_mature_inventory_loss_authority
        ADD CONSTRAINT ex_task9_mature_loss_consumability_overlap
        EXCLUDE USING gist (
            season_id WITH =,
            destination_factory_id WITH =,
            state_date WITH =,
            capacity_pool_code WITH =,
            forecast_quantile WITH =,
            consumability_range WITH &&
        )
        """
    )


def downgrade() -> None:
    for table_name, constraint_name in (
        ("task9_mature_inventory_loss_authority", "ex_task9_mature_loss_consumability_overlap"),
        ("task9_initial_inventory_snapshot", "ex_task9_initial_inventory_consumability_overlap"),
        ("task9_weather_rule_config_version", "ex_task9_weather_rule_combined_overlap"),
        ("task9_holiday_calendar_version", "ex_task9_holiday_calendar_consumability_overlap"),
        ("task9_daily_capacity_authority", "ex_task9_daily_capacity_consumability_overlap"),
        ("task9_run_parameter_package", "ex_task9_run_parameter_package_combined_overlap"),
        ("task9_capacity_pool_member", "ex_task9_capacity_pool_member_combined_overlap"),
        ("task9_capacity_pool_definition", "ex_task9_capacity_pool_definition_combined_overlap"),
    ):
        op.drop_constraint(constraint_name, table_name, type_="exclude")

    for index_name, table_name in (
        ("ix_task9_authority_lifecycle_event_source_record", "task9_authority_lifecycle_event"),
        ("ix_task9_authority_lifecycle_event_identity_sequence", "task9_authority_lifecycle_event"),
        ("uq_task9_weather_rule_one_active", "task9_weather_rule_config_version"),
        ("uq_task9_holiday_calendar_one_active", "task9_holiday_calendar_version"),
        ("uq_task9_mature_loss_one_active", "task9_mature_inventory_loss_authority"),
        ("uq_task9_initial_inventory_one_active", "task9_initial_inventory_snapshot"),
        ("uq_task9_daily_capacity_one_active", "task9_daily_capacity_authority"),
        ("ix_task9_mature_loss_available", "task9_mature_inventory_loss_authority"),
        ("ix_task9_initial_inventory_available", "task9_initial_inventory_snapshot"),
        ("ix_task9_weather_rule_available", "task9_weather_rule_config_version"),
        ("ix_task9_holiday_calendar_available", "task9_holiday_calendar_version"),
        ("ix_task9_run_parameter_package_available", "task9_run_parameter_package"),
        ("ix_task9_daily_capacity_available", "task9_daily_capacity_authority"),
        ("ix_task9_capacity_pool_def_available", "task9_capacity_pool_definition"),
    ):
        op.drop_index(index_name, table_name=table_name)

    op.drop_table("task9_authority_lifecycle_event")
    op.drop_table("task9_mature_inventory_loss_authority")
    op.drop_table("task9_initial_inventory_cohort")
    op.drop_table("task9_initial_inventory_snapshot")
    op.drop_table("task9_daily_capacity_authority")
    op.drop_table("task9_capacity_pool_member")
    op.drop_table("task9_capacity_pool_definition")
    op.drop_table("task9_run_parameter_package")
    op.drop_table("task9_weather_rule_config_version")
    op.drop_table("task9_holiday_calendar_date")
    op.drop_table("task9_holiday_calendar_version")
