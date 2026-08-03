"""PostgreSQL migration acceptance for the V0.2-S2 projection."""

from __future__ import annotations

import asyncio
import os
from datetime import time
from pathlib import Path

import asyncpg
import pytest
from alembic import command
from alembic.config import Config

pytestmark = [pytest.mark.postgres, pytest.mark.migration]


def _live_env() -> dict[str, str]:
    keys = (
        "ISOLATED_DB_NAME",
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
    )
    values = {key: os.environ.get(key, "") for key in keys}
    missing = [key for key, value in values.items() if not value]
    if missing:
        pytest.skip(f"isolated PostgreSQL migration environment is unavailable: {missing}")
    return values


def _alembic_config() -> Config:
    return Config(str(Path("backend") / "alembic.ini"))


@pytest.mark.asyncio
async def test_historical_backtest_migration_round_trip_preserves_legacy_rows() -> None:
    env = _live_env()
    url = (
        f"postgresql://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}"
        f"@{env['POSTGRES_HOST']}:{env['POSTGRES_PORT']}/{env['ISOLATED_DB_NAME']}"
    )
    conn = await asyncpg.connect(url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == (
            "0028_quality_child_hash_scope"
        )
        table_names = {
            row["tablename"]
            for row in await conn.fetch(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            )
        }
        assert {
            "core_forecast_code_authority",
            "rolling_backtest_manifest",
            "rolling_backtest_binding_row",
            "rolling_backtest_run",
        } <= table_names
        core_authority_columns = {
            row["column_name"]
            for row in await conn.fetch(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'core_forecast_code_authority'
                """
            )
        }
        assert {
            "source_commit_sha",
            "build_artifact_hash",
            "config_bundle_hash",
            "available_at",
            "canonical_payload",
            "authority_hash",
        } <= core_authority_columns
        core_run_authority_columns = {
            row["column_name"]
            for row in await conn.fetch(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'core_forecast_run'
                  AND column_name IN (
                      'code_authority_id', 'code_authority_hash',
                      'code_authority_available_at'
                  )
                """
            )
        }
        assert core_run_authority_columns == {
            "code_authority_id",
            "code_authority_hash",
            "code_authority_available_at",
        }
        nullable = {
            row["column_name"]: row["is_nullable"]
            for row in await conn.fetch(
                """
                SELECT column_name, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'rolling_backtest_run'
                  AND column_name IN (
                      's2_contract_version', 's2_node_count',
                      'backtest_request_hash', 'label_visibility_mode'
                  )
                """
            )
        }
        assert nullable == {
            "s2_contract_version": "YES",
            "s2_node_count": "YES",
            "backtest_request_hash": "YES",
            "label_visibility_mode": "YES",
        }
        legacy_run_id = await conn.fetchval(
            """
            INSERT INTO rolling_backtest_run (
                run_signature, config_hash, execution_mode,
                rolling_schema_version, canonical_serialization_version,
                availability_registry_version, node_calendar_version,
                forecast_horizon_policy_version, upstream_selection_policy_version,
                metric_policy_version, calendar_phase_policy_version,
                cutoff_policy_version, cutoff_timezone, cutoff_local_time,
                status, expected_node_count, canonical_payload,
                canonical_payload_hash
            ) VALUES (
                $1, $2, 'historical_observed',
                'legacy-rolling-v1', 'legacy-canonical-v1',
                'legacy-availability-v1', 'legacy-calendar-v1',
                'legacy-horizon-v1', 'legacy-selection-v1',
                'legacy-metric-v1', 'legacy-phase-v1',
                'legacy-cutoff-v1', 'UTC', $3,
                'completed', 1, '{}'::jsonb, $4
            )
            RETURNING id
            """,
            "a" * 64,
            "b" * 64,
            time(4, 0),
            "c" * 64,
        )
        assert legacy_run_id is not None
    finally:
        await conn.close()

    # The job owns an isolated database. Round-trip the exact new revision
    # only in that database; no application or business data is opened.
    await asyncio.to_thread(
        command.downgrade,
        _alembic_config(),
        "0022_finalized_at_lineage_basis_member",
    )
    await asyncio.to_thread(command.upgrade, _alembic_config(), "head")

    conn = await asyncpg.connect(url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == (
            "0028_quality_child_hash_scope"
        )
        preserved = await conn.fetchrow(
            """
            SELECT s2_contract_version, s2_node_count, backtest_request_hash
            FROM rolling_backtest_run
            WHERE id = $1
            """,
            legacy_run_id,
        )
        assert preserved is not None
        assert preserved["s2_contract_version"] is None
        assert preserved["s2_node_count"] is None
        assert preserved["backtest_request_hash"] is None
    finally:
        await conn.close()
