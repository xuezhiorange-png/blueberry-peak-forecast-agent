"""Migration graph and real PostgreSQL additive schema acceptance."""

import asyncio
import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from backend.tests.alembic_head import assert_unique_head, unique_head


@pytest.mark.postgres
async def test_m06_m07_real_downgrade_upgrade_preserves_historical_rows(
    pg_auth, synthetic_authority
):
    from backend.tests.forecast_intelligence.conftest import seed_sources

    _, factory, _, _, database = pg_auth
    await seed_sources(factory, synthetic_authority)
    async with factory() as db:
        before = list(
            (
                await db.execute(
                    text("SELECT id, result_hash FROM operational_peak_forecast_run ORDER BY id")
                )
            ).all()
        )
    environment = dict(os.environ, APP_ENV="test", POSTGRES_DB=database)
    for direction, revision in (("downgrade", "0040_hierarchical_forecast"), ("upgrade", "head")):
        result = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, "-m", "alembic", "-c", "backend/alembic.ini", direction, revision],
            env=environment,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        async with factory() as db:
            after = list(
                (
                    await db.execute(
                        text(
                            "SELECT id, result_hash FROM operational_peak_forecast_run ORDER BY id"
                        )
                    )
                ).all()
            )
            assert before == after
            actual = await db.scalar(text("SELECT version_num FROM alembic_version"))
            assert actual == (
                "0040_hierarchical_forecast" if direction == "downgrade" else unique_head()
            )


def test_m01_m02_m03_unique_head_and_historical_parent():
    migration = importlib.import_module("backend.alembic.versions.d7766e57d4c8_local_auth")
    assert migration.down_revision == "0040_hierarchical_forecast"
    config = Config("backend/alembic.ini")
    script = ScriptDirectory.from_config(config)
    assert migration.revision in {
        item.revision for item in script.iterate_revisions(unique_head(), "base")
    }


def synthetic_script(tmp_path: Path, *, branch: bool) -> ScriptDirectory:
    versions = tmp_path / "versions"
    versions.mkdir()
    revisions = [
        ("0040_hierarchical_forecast", None),
        ("synthetic_auth", "0040_hierarchical_forecast"),
        ("synthetic_future", "synthetic_auth"),
    ]
    if branch:
        revisions.append(("synthetic_fork", "0040_hierarchical_forecast"))
    for revision, parent in revisions:
        (versions / (revision + ".py")).write_text(
            f"revision={revision!r}\ndown_revision={parent!r}\nbranch_labels=None\ndepends_on=None\n"
        )
    config = Config()
    config.set_main_option("script_location", str(tmp_path))
    return ScriptDirectory.from_config(config)


def test_m09_multiple_heads_rejected(tmp_path):
    with pytest.raises(AssertionError, match="exactly one"):
        assert_unique_head(synthetic_script(tmp_path, branch=True))


def test_m10_future_valid_head_preserves_0040(tmp_path):
    assert assert_unique_head(synthetic_script(tmp_path, branch=False)) == "synthetic_future"


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_m04_m05_real_upgrade_auth_tables_and_constraints(pg_auth):
    _, factory, _, account, _ = pg_auth
    async with factory() as db:
        assert await db.scalar(text("SELECT version_num FROM alembic_version")) == unique_head()
        tables = set(
            (
                await db.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))
            ).all()
        )
        assert {"auth_account", "auth_session", "auth_resource_grant", "auth_audit_event"} <= tables
        assert {"hierarchical_forecast_run", "operational_peak_forecast_run"} <= tables
    async with factory() as db:
        with pytest.raises(DBAPIError):
            await db.execute(
                text("UPDATE auth_account SET principal_id=:new WHERE account_id=:id"),
                {"new": "00000000-0000-0000-0000-000000000001", "id": account.account_id},
            )
    async with factory() as db:
        with pytest.raises(DBAPIError):
            await db.execute(
                text("DELETE FROM auth_account WHERE account_id=:id"), {"id": account.account_id}
            )
    async with factory() as db:
        assert (
            await db.scalar(
                text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_name='auth_account' AND column_name='auth_revision'"
                )
            )
            == "bigint"
        )


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_append_only_audit(pg_auth):
    _, factory, client, _, _ = pg_auth
    from backend.tests.local_auth.conftest import login

    assert (await login(client)).status_code == 200
    async with factory() as db:
        assert await db.scalar(text("SELECT count(*) FROM auth_audit_event")) > 0
        with pytest.raises(DBAPIError):
            await db.execute(text("DELETE FROM auth_audit_event"))
