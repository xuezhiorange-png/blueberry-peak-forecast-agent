"""PostgreSQL migration acceptance for the V0.2-S2 projection."""

from __future__ import annotations

import os
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
            "0023_historical_backtest_binding"
        )
        table_names = {
            row["tablename"]
            for row in await conn.fetch(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            )
        }
        assert {
            "rolling_backtest_manifest",
            "rolling_backtest_binding_row",
            "rolling_backtest_run",
        } <= table_names
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
    finally:
        await conn.close()

    # The job owns an isolated database. Round-trip the exact new revision
    # only in that database; no application or business data is opened.
    command.downgrade(_alembic_config(), "0022_finalized_at_lineage_basis_member")
    command.upgrade(_alembic_config(), "head")

    conn = await asyncpg.connect(url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == (
            "0023_historical_backtest_binding"
        )
    finally:
        await conn.close()
