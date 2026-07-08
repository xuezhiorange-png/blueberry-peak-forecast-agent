"""Live PG assertion for the Slice 3 isolated database profile.

This module is the *live* companion to
:mod:`backend.tests.test_alembic_round_trip_isolated`. Where that file
asserts the *helper contract* (the pure name resolver / guard), this
file asserts what actually happened on the wire once the
``postgres-migration`` GitHub Actions job finished its
``alembic upgrade head`` / ``downgrade 0010_harvest_state_persistence`` /
``upgrade head`` round-trip.

CI ownership (Slice 3 contract):

* This file is marked ``pytest.mark.postgres`` (see ``pytestmark``).
  The ``unit-contract-golden`` job's
  ``-m "not integration and not postgres and not postgres_concurrency"``
  selector therefore **excludes** it. Running it on the
  unit-contract shard would be a mistake, not a feature: there is no
  live PostgreSQL in that job.
* This file is **owned** by the ``postgres-migration`` job, which
  lists it explicitly in its ``pytest`` invocation in
  ``.github/workflows/ci.yml`` (the ``-m`` selector does not apply to
  hand-listed files). It is the only CI job that runs these tests.
* This file is intentionally **not** placed under
  ``backend/tests/integration/`` to avoid being collected by any
  future integration-shard wiring.

Local-development contract:

* On hosts without a live PostgreSQL reachable through the
  ``POSTGRES_HOST`` / ``POSTGRES_PORT`` / ``POSTGRES_USER`` /
  ``POSTGRES_PASSWORD`` / ``ISOLATED_DB_NAME`` env vars, every test
  in this file ``pytest.skip``s. We do **not** fall back to the dev
  database; the dev-DB safeguard
  (:mod:`backend.tests.postgres_test_support`) is the only authority
  on which databases may be contacted from tests, and a missing
  ``ISOLATED_DB_NAME`` is treated as a contract violation, not a
  license to improvise.
* Connection parameters come from environment variables only; no
  password / token / ``DATABASE_URL`` value is ever printed or
  formatted into an error message.

Async / event-loop contract:

* The asyncpg connection and its query are executed inside the
  *same* async function and the *same* event loop. We do **not**
  open the connection in one helper, hand the (still-pending)
  coroutine to the test, and ``await`` it from a separate event
  loop — asyncpg connections are bound to the loop that opened
  them, and the previous attempt at that pattern raised
  ``AttributeError: 'coroutine' object has no attribute 'fetchval'``
  in CI. Each test creates a fresh connection, runs exactly one
  query, and closes the connection in the same async function
  before ``asyncio.run`` returns.

Head revision discovery:

* The expected head revision is **not** hard-coded. It is resolved at
  collection time via Alembic's own
  :class:`alembic.script.ScriptDirectory`, using the same
  ``backend/alembic.ini`` that the CI round-trip step uses. This keeps
  the test in sync with whatever head the migration chain is at.
"""

from __future__ import annotations

import asyncio
import os

import pytest

# ---------------------------------------------------------------------------
# Marker / module-level guard
# ---------------------------------------------------------------------------

# Mark this file ``postgres`` so ``unit-contract-golden`` excludes it.
# The ``postgres-migration`` job lists the file explicitly in its
# ``pytest`` invocation, so the marker is not a no-op for that job.
# Slice 1 Batch 4 marker annotation: add ``migration`` (canonical
# Issue #52 taxonomy) additively. Ownership remains ``postgres-migration``
# per ci-shard-manifest.yml.
pytestmark = [pytest.mark.postgres, pytest.mark.migration]


# ---------------------------------------------------------------------------
# Live-env introspection
# ---------------------------------------------------------------------------


def _required_live_env() -> dict[str, str]:
    """Return the live PG env this test file requires, or skip if absent.

    Every key must be present and non-empty. We never synthesise a
    ``localhost`` default for any of them — that would silently route
    a test command at a dev / cluster-default database, which the
    slice-1 safeguard forbids.
    """

    required = (
        "ISOLATED_DB_NAME",
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
    )
    env = {key: os.environ.get(key, "") for key in required}
    missing = [key for key, value in env.items() if not value]
    if missing:
        pytest.skip(
            f"Slice 3 live PG test requires env vars {missing!r}; "
            "this host is not running the postgres-migration job"
        )
    return env


def _expected_head_revision() -> str:
    """Return the current head revision of the project, resolved via Alembic.

    Resolved from ``backend/alembic.ini`` so the value tracks the
    migration chain automatically. No hard-coded revision string
    appears in this file.
    """

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    ini_path = os.path.join("backend", "alembic.ini")
    if not os.path.isfile(ini_path):
        pytest.skip(f"Alembic config not found at {ini_path!r}")
    cfg = Config(ini_path)
    try:
        script_dir = ScriptDirectory.from_config(cfg)
    except Exception as exc:  # pragma: no cover - defensive
        pytest.skip(f"Could not load Alembic script directory: {exc!r}")
    head = script_dir.get_current_head()
    if not head:
        pytest.skip("Alembic script directory reports no current head")
    return head


# ---------------------------------------------------------------------------
# Async helpers — connect, query, close, all in the same coroutine.
# ---------------------------------------------------------------------------


async def _fetch_current_database(asyncpg, env: dict[str, str], database: str) -> str:
    """Open a connection, run ``SELECT current_database()``, and close.

    The connection and the query live in the *same* event loop and
    the *same* coroutine. This is the asyncpg-correct pattern: an
    asyncpg connection is bound to the loop that opened it, and the
    connection object only exposes ``fetchval`` / ``execute`` / etc.
    *after* the ``await asyncpg.connect(...)`` call has actually
    resolved.
    """

    port = int(env["POSTGRES_PORT"])
    conn = await asyncpg.connect(
        host=env["POSTGRES_HOST"],
        port=port,
        database=database,
        user=env["POSTGRES_USER"],
        password=env["POSTGRES_PASSWORD"],
    )
    try:
        return await conn.fetchval("SELECT current_database()")
    finally:
        await conn.close()


async def _fetch_alembic_version(asyncpg, env: dict[str, str], database: str) -> str | None:
    """Open a connection, query ``alembic_version``, and close.

    Same single-coroutine pattern as :func:`_fetch_current_database`.
    Returns the ``version_num`` column, or ``None`` if the
    ``alembic_version`` table is present but empty (treated as a
    contract violation by the caller).
    """

    port = int(env["POSTGRES_PORT"])
    conn = await asyncpg.connect(
        host=env["POSTGRES_HOST"],
        port=port,
        database=database,
        user=env["POSTGRES_USER"],
        password=env["POSTGRES_PASSWORD"],
    )
    try:
        return await conn.fetchval("SELECT version_num FROM alembic_version")
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Live assertions
# ---------------------------------------------------------------------------


def test_live_current_database_matches_isolated_db_name() -> None:
    """``SELECT current_database()`` must equal the resolved isolated name.

    The CI step ``Resolve isolated test database name`` writes the
    name to ``$GITHUB_ENV``. If anything between that step and the
    pytest step silently re-pointed the connection at a different
    database (the dev / production / cluster-default path that
    slice-1 is meant to block), this assertion fails loud.
    """

    env = _required_live_env()
    expected_db = env["ISOLATED_DB_NAME"]

    # Import asyncpg lazily: we don't want a missing optional dep to
    # mask the ``pytest.skip`` path above. The test infra already
    # requires asyncpg (it is in ``backend/app/``'s dependency
    # graph), so the import should succeed in CI; the try/except
    # keeps local dev running if a user has stripped optional deps.
    try:
        import asyncpg  # type: ignore[import-not-found]
    except ImportError:  # pragma: no cover - optional dep
        pytest.skip("asyncpg is not installed in this environment")

    actual_db = asyncio.run(_fetch_current_database(asyncpg, env, database=expected_db))

    assert actual_db == expected_db, (
        "current_database() did not match ISOLATED_DB_NAME — "
        "the pytest step is bound to a different database than the "
        "CI round-trip step"
    )


def test_live_alembic_version_equals_current_head() -> None:
    """``alembic_version.version_num`` must equal the Alembic head.

    The CI round-trip is the authoritative proof of upgrade; this
    assertion catches the case where the round-trip's
    ``downgrade 0010_harvest_state_persistence`` /
    ``upgrade head`` chain ended in a state that does not match the
    project head (for example because a future downgrade
    accidentally downgraded past head, or because an env var caused
    the second ``upgrade head`` to bind to the wrong database).
    """

    env = _required_live_env()
    expected_head = _expected_head_revision()
    expected_db = env["ISOLATED_DB_NAME"]

    try:
        import asyncpg  # type: ignore[import-not-found]
    except ImportError:  # pragma: no cover - optional dep
        pytest.skip("asyncpg is not installed in this environment")

    actual_version = asyncio.run(_fetch_alembic_version(asyncpg, env, database=expected_db))

    assert actual_version is not None, (
        "alembic_version table is empty — the CI round-trip did not "
        "leave the isolated database at any revision"
    )
    assert actual_version == expected_head, (
        f"alembic_version.version_num={actual_version!r} does not "
        f"match the project head {expected_head!r}"
    )


__all__ = [
    "test_live_current_database_matches_isolated_db_name",
    "test_live_alembic_version_equals_current_head",
]
