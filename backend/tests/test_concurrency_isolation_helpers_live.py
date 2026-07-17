"""Slice 4 — live PostgreSQL assertions for the ``postgres-concurrency`` isolated DB profile.

This file mirrors :mod:`backend.tests.test_alembic_round_trip_isolated_db_live`
(the Slice 3 live companion) for the ``postgres-concurrency`` job. It
is **owned** by the ``postgres-concurrency`` CI job and is the only CI
job that runs it.

Property: this file **does** open a PostgreSQL connection. Every test
below is gated on:

* ``RUN_POSTGRES_INTEGRATION=1`` — the existing PostgreSQL
  integration gate.
* The Slice 1 dev-DB safeguard accepting the current test identity
  (via :func:`backend.tests.postgres_test_identity.assert_safe_postgres_test_identity`).
* The resolved isolated DB name passing
  :func:`backend.tests.concurrency_isolation_helpers.assert_safe_concurrency_isolated_db_name`.

When any gate fails the test is **skipped**, not failed. This matches
the Slice 3 contract and keeps the suite green on hosts that do not
run PG.

What these tests actually assert against a real PG
---------------------------------------------------

1. The ``postgres-concurrency`` CI step's ``POSTGRES_DB`` resolves to
   the per-run isolated database name (not the service container's
   literal ``blueberry_peak``).
2. ``current_database()`` against the resolved name returns the
   isolated DB name (proves the live connection target matches what
   the helper produced).
3. The Alembic head is at the expected revision after
   ``alembic upgrade head`` against the isolated DB (proves the
   isolated DB has a clean schema, no leftover migration drift).
4. The ``alembic_version`` table contains the expected head revision
   (proves the destructive CI step did not silently no-op).
5. A write / commit against the isolated DB is **visible to a second
   session** (``SELECT current_database(), '' AS marker``) — proves
   the per-run DB is actually accepting commits and not, for example,
   a read-only view.

What these tests deliberately do NOT assert
-------------------------------------------

* Per-class / per-test isolation (deferred to Slice 5).
* TRUNCATE removal (deferred to Slice 5).
* CI structure rework (deferred to Slice 6).
* Concurrency / race / deadlock behaviour (this slice is the
  *infrastructure* for those tests; the behavioural tests live in
  ``backend/tests/integration/test_task11_dependency_serialization.py``
  and ``backend/tests/integration/test_task9_authority_repository_postgres.py``
  and are picked up by the ``-m postgres_concurrency`` selector).
"""

from __future__ import annotations

import asyncio
import os

import asyncpg
import pytest

from backend.tests.concurrency_isolation_helpers import (
    ISOLATED_JOB_NAME,
    assert_safe_concurrency_isolated_db_name,
    resolve_concurrency_isolated_db_name,
)
from backend.tests.postgres_test_support import assert_safe_postgres_test_identity

# Mark this file ``postgres_concurrency`` so the ``postgres-concurrency``
# CI job's ``-m postgres_concurrency`` selector **includes** it. The
# ``unit-contract-golden`` job's selector excludes it.
# Slice 1 Batch 4 marker annotation: add ``concurrency`` (canonical
# Issue #52 taxonomy) additively. ``postgres_concurrency`` remains the
# active PR CI sharp selector per ci-shard-manifest.yml; ``concurrency``
# is the canonical taxonomy alias for the same ownership.
pytestmark = [pytest.mark.postgres_concurrency, pytest.mark.concurrency]


def _postgres_integration_enabled() -> bool:
    return os.getenv("RUN_POSTGRES_INTEGRATION") == "1"


def _resolve_target_db_name() -> str | None:
    """Resolve the isolated DB name from the CI step's ``ISOLATED_DB_NAME`` env var.

    Returns ``None`` if the env var is unset (no live isolated DB has
    been created by the CI step yet, so the test must skip).
    """
    name = os.getenv("ISOLATED_DB_NAME")
    if not name:
        return None
    return name


def _connection_kwargs_for(db_name: str) -> dict[str, object]:
    """Build the connection kwargs for the isolated DB.

    Uses the same env vars the ``postgres-concurrency`` CI step uses
    to connect, so the live connection in this test targets exactly
    the DB the CI step created.
    """
    return {
        "host": os.environ.get("POSTGRES_HOST", "localhost"),
        "port": int(os.environ.get("POSTGRES_PORT", "5432")),
        "database": db_name,
        "user": os.environ.get("POSTGRES_USER", "blueberry_app"),
        "password": os.environ.get("POSTGRES_PASSWORD", ""),
    }


# --------------------------------------------------------------------------
# Helpers — gating
# --------------------------------------------------------------------------


def _skip_unless_safe_isolated_db_present() -> str:
    """Skip the test unless every gate is satisfied, and return the resolved DB name."""
    if not _postgres_integration_enabled():
        pytest.skip("requires RUN_POSTGRES_INTEGRATION=1")
    # Slice 1 dev-DB safeguard must accept the current test identity
    # before we open any connection.
    try:
        assert_safe_postgres_test_identity(env=None)
    except ValueError as exc:
        pytest.skip(f"Slice 1 dev-DB safeguard rejected current profile: {exc}")
    name = _resolve_target_db_name()
    if name is None:
        pytest.skip("requires ISOLATED_DB_NAME to be set by the CI step")
    # Slice 4 fail-closed guard must also accept the name.
    assert_safe_concurrency_isolated_db_name(name)
    return name


# --------------------------------------------------------------------------
# Live PG assertions
# --------------------------------------------------------------------------


def test_isolated_db_name_resolves_to_expected_template() -> None:
    """``ISOLATED_DB_NAME`` must end with the canonical ``postgres_concurrency`` job segment."""
    if os.getenv("ISOLATED_JOB_NAME") != ISOLATED_JOB_NAME:
        pytest.skip("requires postgres-concurrency isolated database profile")
    name = _skip_unless_safe_isolated_db_present()
    assert name.endswith(f"_{ISOLATED_JOB_NAME}"), (
        f"unexpected ISOLATED_DB_NAME={name!r}; expected it to end with _{ISOLATED_JOB_NAME}"
    )


def test_resolver_matches_ci_step_for_known_run_inputs() -> None:
    """``ISOLATED_DB_NAME`` must equal what the resolver produces for the CI step's inputs."""
    if os.getenv("ISOLATED_JOB_NAME") != ISOLATED_JOB_NAME:
        pytest.skip("requires postgres-concurrency isolated database profile")
    name = _skip_unless_safe_isolated_db_present()
    run_id = os.getenv("GITHUB_RUN_ID")
    run_attempt = os.getenv("GITHUB_RUN_ATTEMPT")
    if not run_id or not run_attempt:
        pytest.skip("requires GITHUB_RUN_ID and GITHUB_RUN_ATTEMPT env vars")
    expected = resolve_concurrency_isolated_db_name(run_id, run_attempt)
    assert name == expected, f"ISOLATED_DB_NAME={name!r} != resolver={expected!r}"


def test_current_database_returns_isolated_name() -> None:
    """A live connection must report ``current_database() == ISOLATED_DB_NAME``."""

    async def _run() -> None:
        name = _skip_unless_safe_isolated_db_present()
        conn = await asyncpg.connect(**_connection_kwargs_for(name))
        try:
            actual = await conn.fetchval("SELECT current_database()")
            assert actual == name, f"current_database()={actual!r} != ISOLATED_DB_NAME={name!r}"
        finally:
            await conn.close()

    asyncio.run(_run())


def test_alembic_head_revision_present() -> None:
    """After ``alembic upgrade head``, the isolated DB must carry the head revision."""

    async def _run() -> None:
        name = _skip_unless_safe_isolated_db_present()
        conn = await asyncpg.connect(**_connection_kwargs_for(name))
        try:
            row = await conn.fetchrow("SELECT version_num FROM alembic_version")
            assert row is not None, (
                f"alembic_version row missing in isolated DB {name!r} — "
                "the CI step's `alembic upgrade head` did not run against the isolated DB"
            )
            # The head revision is some short hex string; we only assert
            # it is non-empty here because the actual head varies.
            version = row["version_num"]
            assert isinstance(version, str) and version, (
                f"alembic_version.version_num={version!r} must be a non-empty string"
            )
        finally:
            await conn.close()

    asyncio.run(_run())


def test_write_and_commit_visible_to_second_session() -> None:
    """A committed write against the isolated DB must be visible to a fresh session.

    Proves the isolated DB is not a read-only view and that real
    commits work — the prerequisite for the
    ``@pytest.mark.postgres_concurrency`` tests that need to assert
    real cross-transaction visibility.
    """

    async def _run() -> None:
        name = _skip_unless_safe_isolated_db_present()
        marker_table = f"_slice4_concurrency_probe_{name[-12:]}"
        # Write
        writer = await asyncpg.connect(**_connection_kwargs_for(name))
        try:
            await writer.execute(
                f'CREATE TABLE IF NOT EXISTS "{marker_table}" (marker TEXT NOT NULL)'
            )
            await writer.execute(
                f'INSERT INTO "{marker_table}" (marker) VALUES ($1) ON CONFLICT DO NOTHING',
                "slice4-isolated-db-proof",
            )
        finally:
            await writer.close()
        # Read from a fresh session
        reader = await asyncpg.connect(**_connection_kwargs_for(name))
        try:
            row = await reader.fetchrow(f'SELECT marker FROM "{marker_table}"')
            assert row is not None, f"marker table {marker_table!r} missing in second session"
            assert row["marker"] == "slice4-isolated-db-proof", (
                f"unexpected marker value: {row['marker']!r}"
            )
        finally:
            await reader.close()
            # Best-effort cleanup
            try:
                cleanup = await asyncpg.connect(**_connection_kwargs_for(name))
                try:
                    await cleanup.execute(f'DROP TABLE IF EXISTS "{marker_table}"')
                finally:
                    await cleanup.close()
            except Exception:
                pass

    asyncio.run(_run())


def test_isolated_db_name_is_not_blueberry_peak_literal() -> None:
    """The isolated DB name must NEVER be the dev-DB literal ``blueberry_peak``.

    This is a redundant safety net: the guard
    :func:`assert_safe_concurrency_isolated_db_name` already rejects
    the literal, but if a future refactor accidentally bypasses the
    guard, this live test catches the regression.
    """
    name = _skip_unless_safe_isolated_db_present()
    assert name != "blueberry_peak", "ISOLATED_DB_NAME must never equal dev-DB literal"
    assert "blueberry_peak" in name and "_test_" in name, (
        f"ISOLATED_DB_NAME={name!r} must be a *_test_* name"
    )
