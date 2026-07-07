"""Slice 2 — minimum verification tests for the transactional_pg_session
fixture.

These tests prove the four acceptance gates from
``docs/task-11-issue-51-batch3-slice2-txn-isolation-design.md``:

- G-01: rollback after test body — writes inside the test are
  invisible to a fresh connection after teardown.
- G-02: ``commit()`` inside the test does not leak — even when the
  test body calls ``await session.commit()`` and re-opens a
  savepoint, the outer transaction is rolled back at teardown.
- G-03: savepoint restarts after ``commit()`` — the test can
  continue writing and reading after ``commit()``.
- G-04: Slice 1 dev-DB safeguard still active — the fixture raises
  (or rejects) unsafe identity inputs before any connection is
  acquired.

The tests use the existing ``dim_season`` lookup table (a small,
append-only PG table) to avoid introducing new schema. They do not
depend on Task 8 / 9 / 10 domain semantics, migration behavior, or
concurrency primitives.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from backend.app.db.session import AsyncSessionMaker

pytestmark = pytest.mark.integration


def _pg_enabled() -> bool:
    return os.getenv("RUN_POSTGRES_INTEGRATION") == "1"


def _pg_skip() -> None:
    if not _pg_enabled():
        pytest.skip("set RUN_POSTGRES_INTEGRATION=1 when PostgreSQL is available")


# A trivial ``code`` is used so the test does not collide with
# any real production data; Slice 1's TRUNCATE clears master data
# between tests, and Slice 2's transactional fixture reverts on
# teardown, so we are safe to use a deterministic value.
#
# Note: ``dim_season`` schema (per migration 0002_master_data.py) only
# exposes ``id`` / ``code`` (unique) / ``start_date`` / ``end_date``.
# There is no ``season_code`` or ``display_name`` column — the
# earlier version of this test file used non-existent columns, which
# caused ``asyncpg.UndefinedColumnError`` in CI. This hotfix pins the
# probes to the real schema and keeps the same rollback semantics.
_SLICE2_SEASON_CODE = "S2-TXN-ISOLATION-PROBE"

# Use fixed, low-side-effect date values for the ``start_date`` /
# ``end_date`` NOT NULL columns. The fixture's outer transaction is
# rolled back, so the rows never escape the test.
_SLICE2_SEASON_START = "2026-01-01"
_SLICE2_SEASON_END = "2026-12-31"


@pytest.mark.asyncio
async def test_outer_txn_rolls_back_inner_writes(
    transactional_pg_session,
) -> None:
    """G-01: writes inside the test are invisible after teardown."""
    _pg_skip()

    # Insert inside the transactional session.
    await transactional_pg_session.execute(
        text(
            "INSERT INTO dim_season (code, start_date, end_date) "
            "VALUES (:code, :start_date, :end_date) "
            "ON CONFLICT (code) DO NOTHING"
        ),
        {
            "code": _SLICE2_SEASON_CODE,
            "start_date": _SLICE2_SEASON_START,
            "end_date": _SLICE2_SEASON_END,
        },
    )
    await transactional_pg_session.flush()

    # Sanity check: the row is visible inside the same test.
    result = await transactional_pg_session.execute(
        text("SELECT COUNT(*) FROM dim_season WHERE code = :code"),
        {"code": _SLICE2_SEASON_CODE},
    )
    assert int(result.scalar_one()) == 1

    # Test body ends here. The fixture rolls back the outer
    # transaction at teardown. A fresh session opened after
    # teardown must NOT see the row.
    # (The fresh session is opened in a separate `async with`
    # block AFTER the fixture's ``yield`` has returned, which
    # happens at the next ``await`` on the fixture boundary. We
    # use a deferred open: the open+query runs in a callback
    # after the fixture's teardown by reading from a separate
    # ``async with AsyncSessionMaker()`` block *before* the test
    # function returns, so the fixture's rollback has not yet
    # run. We need to assert the row is GONE after the test
    # returns; pytest calls the fixture's teardown before the
    # next test's setup, so the assertion below is moved into a
    # second test that uses the same fixture but does no writes
    # — see ``test_commit_inside_test_does_not_leak`` for the
    # equivalent pattern.)

    # The fixture's outer transaction is still active at this
    # point. We do NOT call commit() here; the assertion that
    # the row is rolled back is made by the next test, which
    # opens a fresh session AFTER the previous fixture's
    # teardown has run.


@pytest.mark.asyncio
async def test_commit_inside_test_does_not_leak(
    transactional_pg_session,
) -> None:
    """G-02: ``commit()`` inside the test does not escape the outer txn."""
    _pg_skip()

    # First insert a row (this one WILL be rolled back when the
    # previous test's fixture tears down). For this test, we use
    # a fresh row and explicitly call commit() to prove the
    # savepoint release does not commit the outer transaction.
    probe_code = f"{_SLICE2_SEASON_CODE}-G02"

    await transactional_pg_session.execute(
        text(
            "INSERT INTO dim_season (code, start_date, end_date) "
            "VALUES (:code, :start_date, :end_date) "
            "ON CONFLICT (code) DO NOTHING"
        ),
        {
            "code": probe_code,
            "start_date": _SLICE2_SEASON_START,
            "end_date": _SLICE2_SEASON_END,
        },
    )
    await transactional_pg_session.commit()

    # After commit(), a fresh write re-opens a new savepoint.
    probe_code_after = f"{_SLICE2_SEASON_CODE}-G02-AFTER"
    await transactional_pg_session.execute(
        text(
            "INSERT INTO dim_season (code, start_date, end_date) "
            "VALUES (:code, :start_date, :end_date) "
            "ON CONFLICT (code) DO NOTHING"
        ),
        {
            "code": probe_code_after,
            "start_date": _SLICE2_SEASON_START,
            "end_date": _SLICE2_SEASON_END,
        },
    )

    # Inside the test, both rows are visible.
    result = await transactional_pg_session.execute(
        text("SELECT COUNT(*) FROM dim_season WHERE code IN (:a, :b)"),
        {"a": probe_code, "b": probe_code_after},
    )
    assert int(result.scalar_one()) == 2

    # Fixture teardown rolls back the outer transaction. The
    # next test (no writes) reads from a fresh session and
    # verifies NEITHER row is present.
    # The cross-test readback is asserted in
    # ``test_rollback_visible_to_fresh_session_after_teardown``.


@pytest.mark.asyncio
async def test_savepoint_restart_after_commit(
    transactional_pg_session,
) -> None:
    """G-03: after ``commit()``, the savepoint re-opens on next write."""
    _pg_skip()

    probe_code = f"{_SLICE2_SEASON_CODE}-G03"

    # Write 1
    await transactional_pg_session.execute(
        text(
            "INSERT INTO dim_season (code, start_date, end_date) "
            "VALUES (:code, :start_date, :end_date) "
            "ON CONFLICT (code) DO NOTHING"
        ),
        {
            "code": probe_code,
            "start_date": _SLICE2_SEASON_START,
            "end_date": _SLICE2_SEASON_END,
        },
    )

    # Commit releases the current savepoint
    await transactional_pg_session.commit()

    # Write 2: must succeed because SQLAlchemy re-opens a
    # new savepoint for the next ORM write. We bump
    # ``end_date`` by one day inside the new savepoint.
    await transactional_pg_session.execute(
        text("UPDATE dim_season SET end_date = :end_date WHERE code = :code"),
        {"code": probe_code, "end_date": "2027-01-01"},
    )

    # Read back to confirm the second write took effect inside
    # the new savepoint.
    result = await transactional_pg_session.execute(
        text("SELECT end_date FROM dim_season WHERE code = :code"),
        {"code": probe_code},
    )
    assert result.scalar_one() == "2027-01-01"

    # Fixture teardown will roll back BOTH writes.


@pytest.mark.asyncio
async def test_rollback_visible_to_fresh_session_after_teardown() -> None:
    """G-01/G-02 cross-test readback: a fresh session must NOT see
    rows written by the previous transactional tests, because the
    fixture's outer transaction was rolled back at teardown.

    This test does NOT use the ``transactional_pg_session`` fixture
    itself (it is the cross-fixture readback). It opens a fresh
    session via ``AsyncSessionMaker`` and asserts that the probe
    rows from the previous three tests are absent.
    """
    _pg_skip()

    async with AsyncSessionMaker() as session:
        result = await session.execute(
            text("SELECT code FROM dim_season WHERE code LIKE :pattern"),
            {"pattern": f"{_SLICE2_SEASON_CODE}%"},
        )
        codes = {row[0] for row in result.all()}

    assert codes == set(), (
        f"transactional_pg_session failed to roll back: "
        f"rows leaked into a fresh session: {sorted(codes)}"
    )


@pytest.mark.asyncio
async def test_dev_db_safeguard_still_active() -> None:
    """G-04: the Slice 1 dev-DB safeguard still rejects unsafe inputs.

    The fixture calls ``assert_safe_postgres_test_identity`` before
    opening the engine connection. This test directly invokes the
    safeguard with an obviously unsafe DATABASE_URL to prove the
    safeguard itself still raises (i.e. the safeguard logic is
    intact and not bypassed by the fixture's import path).
    """
    from backend.tests.postgres_test_support import (
        assert_safe_postgres_test_identity,
    )

    unsafe_env = {
        "DATABASE_URL": "postgresql://postgres:postgres@localhost:5432/blueberry_peak",
        "APP_ENV": "test",
        "PGPORT": "5432",
    }
    with pytest.raises(ValueError, match="dev-DB"):
        assert_safe_postgres_test_identity(env=unsafe_env)
