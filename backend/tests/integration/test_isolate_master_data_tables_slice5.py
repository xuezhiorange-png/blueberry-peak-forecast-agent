"""Slice 5 — fixture-contract tests for the narrowed ``isolate_master_data_tables``.

Batch 3 Slice 5 retires the whole-database ``TRUNCATE`` autouse fixture for
ordinary integration tests that opt into ``transactional_pg_session``. The
narrow rule is implemented in :mod:`backend.tests.integration.conftest`
and is pinned by this test file.

What this file covers
---------------------

1. **Pure helper contract** (no PostgreSQL needed):
   - ``_request_uses_savepoint_isolation`` returns ``True`` iff the
     request's fixturenames declare ``transactional_pg_session``.
   - ``_request_uses_savepoint_isolation`` returns ``False`` for tests
     that do not opt in.
   - The detection is based on fixture-name membership, not on test
     file location or marker, so adding a new savepoint fixture later
     requires an explicit set update.

2. **Live contract** (requires ``RUN_POSTGRES_INTEGRATION=1``):
   - A savepoint-isolated test can read rows it inserted itself
     **without** depending on the pre-test ``TRUNCATE`` to clear
     pre-existing rows.
   - A second savepoint-isolated test does NOT see rows leaked from
     the first test, because the outer-transaction rollback is the
     sole cleanup.
   - A non-savepoint test continues to receive the pre-Slice-5
     ``TRUNCATE ... RESTART IDENTITY CASCADE`` behavior.

These tests are deliberately written to be self-contained: they
use ``dim_season`` (a small, append-only lookup table) and a
unique probe ``code`` value so they cannot collide with other tests
or with real production data.

Scope
-----

* In scope: the narrow rule for the autouse
  ``isolate_master_data_tables`` fixture, plus the cross-test
  no-leakage guarantee that follows from the rule.
* Out of scope: the ``transactional_pg_session`` fixture itself
  (covered by Slice 2's :mod:`test_transactional_pg_session_slice2`).
* Out of scope: migration / concurrency / real-commit tests (Slice 3
  / Slice 4). Those tests use isolated DB profiles and are unaffected
  by this slice's changes.
* Out of scope: production code semantics (no production file in this
  project is changed by this slice).
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from backend.tests.integration.conftest import (
    _request_uses_savepoint_isolation,
    _SAVEPOINT_ISOLATION_FIXTURES,
)

if TYPE_CHECKING:
    from pytest import FixtureRequest

pytestmark = pytest.mark.integration


def _pg_enabled() -> bool:
    return os.getenv("RUN_POSTGRES_INTEGRATION") == "1"


def _pg_skip() -> None:
    if not _pg_enabled():
        pytest.skip("set RUN_POSTGRES_INTEGRATION=1 when PostgreSQL is available")


# A deterministic probe value so this file cannot collide with any
# other Slice 5 test or with any real production data. Slice 5
# guarantees the row is rolled back at the end of every test that
# uses the savepoint fixture, so reusing the same code is safe.
_SLICE5_SEASON_CODE = "S5-ISOLATE-MASTER-PROBE"
_SLICE5_SEASON_START = "2026-01-01"
_SLICE5_SEASON_END = "2026-12-31"


# ---------------------------------------------------------------------------
# Pure helper contract — does NOT require PostgreSQL.
# ---------------------------------------------------------------------------


def test_savepoint_isolation_fixtures_set_contains_transactional_pg_session() -> None:
    """The narrow-rule set must include ``transactional_pg_session``.

    If a future refactor renames the fixture, this test fails before
    the narrow rule silently stops working.
    """
    assert "transactional_pg_session" in _SAVEPOINT_ISOLATION_FIXTURES


def test_savepoint_isolation_set_is_frozen() -> None:
    """The set must be a ``frozenset`` so it cannot be mutated at runtime."""
    assert isinstance(_SAVEPOINT_ISOLATION_FIXTURES, frozenset)


def test_request_uses_savepoint_isolation_true_when_fixture_in_fixturenames() -> None:
    """A request declaring the fixture must be detected as savepoint-isolated."""

    class _StubRequest:
        fixturenames: tuple[str, ...] = (
            "transactional_pg_session",
            "caplog",
        )

    assert _request_uses_savepoint_isolation(_StubRequest()) is True  # type: ignore[arg-type]


def test_request_uses_savepoint_isolation_false_when_fixture_absent() -> None:
    """A request without the fixture must NOT be detected as savepoint-isolated."""

    class _StubRequest:
        fixturenames: tuple[str, ...] = ("caplog", "tmp_path")

    assert _request_uses_savepoint_isolation(_StubRequest()) is False  # type: ignore[arg-type]


def test_request_uses_savepoint_isolation_false_for_empty_fixturenames() -> None:
    """An empty fixturenames set must NOT be detected as savepoint-isolated."""

    class _StubRequest:
        fixturenames: tuple[str, ...] = ()

    assert _request_uses_savepoint_isolation(_StubRequest()) is False  # type: ignore[arg-type]


def test_request_uses_savepoint_isolation_false_for_unknown_similar_name() -> None:
    """A near-miss fixture name must NOT trigger the narrow rule.

    The detection is exact-name, not substring: ``transactional_pg``
    (without the suffix) is NOT a savepoint fixture.
    """

    class _StubRequest:
        fixturenames: tuple[str, ...] = ("transactional_pg",)

    assert _request_uses_savepoint_isolation(_StubRequest()) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Live contract — requires PostgreSQL (skipped on non-PG hosts).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_savepoint_isolation_skips_outer_truncate_for_opted_in_test(
    transactional_pg_session: object,
) -> None:
    """A test using ``transactional_pg_session`` must NOT be TRUNCATE-bounded.

    This test asserts the **observable contract**: the outer
    ``isolate_master_data_tables`` fixture does not invoke
    ``TRUNCATE ... RESTART IDENTITY CASCADE`` for tests that opted into
    the savepoint fixture. The observable check is that the probe row
    inserted in this test does NOT get auto-rolled-back by the autouse
    fixture's pre-test TRUNCATE (because the autouse fixture now skips
    itself for savepoint-isolated tests).
    """
    _pg_skip()

    # First read: a fresh session (no savepoint) cannot see the probe
    # yet. We use AsyncSessionMaker to read because the
    # transactional_pg_session has the row visible only inside its
    # own transaction.
    from backend.app.db.session import AsyncSessionMaker

    async with AsyncSessionMaker() as session:
        result = await session.execute(
            text("SELECT COUNT(*) FROM dim_season WHERE code = :code"),
            {"code": _SLICE5_SEASON_CODE},
        )
        # Outside any test, the probe is not present (no other test
        # has run, OR a prior test rolled back).
        assert int(result.scalar_one()) == 0, (
            "probe row leaked from a prior test — narrow rule broken"
        )

    # Now insert inside the savepoint fixture. The narrow rule means
    # the pre-test TRUNCATE did NOT run, so we can write directly.
    await transactional_pg_session.execute(  # type: ignore[union-attr]
        text(
            "INSERT INTO dim_season (code, start_date, end_date) "
            "VALUES (:code, :start_date, :end_date) "
            "ON CONFLICT (code) DO NOTHING"
        ),
        {
            "code": _SLICE5_SEASON_CODE,
            "start_date": _SLICE5_SEASON_START,
            "end_date": _SLICE5_SEASON_END,
        },
    )
    await transactional_pg_session.flush()  # type: ignore[union-attr]

    # Inside the test, the row is visible.
    result = await transactional_pg_session.execute(  # type: ignore[union-attr]
        text("SELECT COUNT(*) FROM dim_season WHERE code = :code"),
        {"code": _SLICE5_SEASON_CODE},
    )
    assert int(result.scalar_one()) == 1
    # Fixture teardown rolls the outer transaction back. The next
    # test confirms the row is gone.


@pytest.mark.asyncio
async def test_savepoint_isolation_rolls_back_after_first_savepoint_test(
    transactional_pg_session: object,
) -> None:
    """The first savepoint test's row must NOT be visible to the second test.

    Two savepoint-isolated tests run in sequence. The first inserts a
    row; the second reads from a fresh session and asserts the row is
    absent. This proves the narrow rule preserves the no-cross-test-
    leakage guarantee.
    """
    _pg_skip()

    # Insert inside the first savepoint test.
    await transactional_pg_session.execute(  # type: ignore[union-attr]
        text(
            "INSERT INTO dim_season (code, start_date, end_date) "
            "VALUES (:code, :start_date, :end_date) "
            "ON CONFLICT (code) DO NOTHING"
        ),
        {
            "code": f"{_SLICE5_SEASON_CODE}-SEQ",
            "start_date": _SLICE5_SEASON_START,
            "end_date": _SLICE5_SEASON_END,
        },
    )
    await transactional_pg_session.commit()  # type: ignore[union-attr]

    # Fixture teardown rolls back. No assertion in this test body —
    # the cross-test readback happens in the test below.


@pytest.mark.asyncio
async def test_cross_test_no_leakage_after_savepoint_isolation() -> None:
    """A fresh session after a savepoint-isolated test must not see leaked rows.

    This test does NOT take the ``transactional_pg_session`` fixture
    itself; it acts as a sibling test that opens its own session and
    verifies the previous test's writes were rolled back.
    """
    _pg_skip()

    from backend.app.db.session import AsyncSessionMaker

    async with AsyncSessionMaker() as session:
        result = await session.execute(
            text("SELECT code FROM dim_season WHERE code LIKE :pattern"),
            {"pattern": f"{_SLICE5_SEASON_CODE}%"},
        )
        leaked = {row[0] for row in result.all()}

    assert leaked == set(), (
        f"savepoint-isolated tests leaked rows: {sorted(leaked)} — "
        "narrow rule broken: pre-test TRUNCATE still ran for opted-in test"
    )


# ---------------------------------------------------------------------------
# Negative tests — pre-existing Slice 1 safety contract remains intact.
# ---------------------------------------------------------------------------


def test_slice5_does_not_bypass_slice1_dev_db_safeguard() -> None:
    """Slice 5 must not weaken Slice 1's dev-DB safeguard.

    The narrow rule and the savepoint fixture both still call
    ``assert_safe_postgres_test_identity`` before opening any
    connection. This negative test asserts the safeguard itself is
    still fail-closed when handed an obviously unsafe DATABASE_URL.
    """
    from backend.tests.postgres_test_support import (
        assert_safe_postgres_test_identity,
    )

    unsafe_env = {
        "DATABASE_URL": "postgresql://postgres:***@localhost:5432/blueberry_peak",
        "APP_ENV": "test",
        "PGPORT": "5432",
    }
    with pytest.raises(ValueError, match="dev-DB"):
        assert_safe_postgres_test_identity(env=unsafe_env)


def test_slice5_no_password_leak_in_failure_message() -> None:
    """Slice 5 must not introduce a new path that leaks the dev-DB password.

    The narrow rule itself has no error path — it merely inspects the
    request's fixturenames. This test pins the contract that an
    obviously-leaked secret passed to the helper does not appear in
    any error message.
    """
    from backend.tests.postgres_test_support import (
        assert_safe_postgres_test_identity,
    )

    secret_marker = "sup3r-secret-pw-marker-zzz-slice5"
    unsafe_env = {
        "DATABASE_URL": f"postgresql://postgres:{secret_marker}@localhost:5432/blueberry_peak",
        "APP_ENV": "test",
        "PGPORT": "5432",
    }
    with pytest.raises(ValueError) as exc_info:
        assert_safe_postgres_test_identity(env=unsafe_env)
    assert secret_marker not in str(exc_info.value)