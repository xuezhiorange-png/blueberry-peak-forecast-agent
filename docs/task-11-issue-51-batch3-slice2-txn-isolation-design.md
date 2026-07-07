# Task 11 Batch 3 Slice 2 — Transactional PostgreSQL Test Isolation

## Baseline

- main HEAD: `bd883d7885c66b18eb18fe8e56b419ecbac0e7f4`
- PR #59: merged
- main CI: `28857032765` / completed / success
- Issue #51: open
- Issue #23: open / reopened

## Status

Design-only freeze for Slice 2. This document does not implement
migration isolation, concurrency isolation, TRUNCATE full removal,
CI workflow changes, production code changes, Alembic migration
changes, or frontend changes.

## Issue mapping

- Refs #51
- Refs #23

Issue #51 remains OPEN because Slice 3 / Slice 4 / Slice 5 are not
authorized as part of this slice. Issue #23 remains OPEN as the
umbrella TASK-011-INFRA issue.

## Scope

This slice introduces an **opt-in** transaction + savepoint + rollback
fixture for normal PostgreSQL integration tests.

The fixture is opt-in: existing integration tests that depend on the
current whole-database TRUNCATE behavior (`isolate_master_data_tables`
in `backend/tests/integration/conftest.py`) are NOT migrated by this
slice. Only one representative integration test is migrated.

## Non-goals

- No migration isolation (Slice 3 territory).
- No concurrency isolation (Slice 4 territory).
- No TRUNCATE full removal (Slice 5 territory). The existing
  `isolate_master_data_tables` autouse fixture is preserved unchanged.
- No CI workflow changes.
- No production code changes (`backend/app/**`).
- No Alembic migration changes.
- No frontend changes.
- No Task 8 / Task 9 / Task 10 production semantic changes.
- No full marker taxonomy cleanup (Slice 4 territory).
- No batch migration of the 29 existing integration test files
  to the new fixture.

## Fixture Contract

The new opt-in fixture is named `transactional_pg_session` and lives
in `backend/tests/integration/conftest.py`. It is built on top of
`backend.tests.integration._txn_isolation.transactional_async_session`,
an async context manager that:

- **Outer transaction ownership** — a dedicated
  :class:`AsyncConnection` is acquired from the engine pool; a single
  outer transaction is opened on that connection for the entire test
  body. The connection is returned to the pool at teardown.

- **Nested savepoint behavior** — the :class:`AsyncSession` yielded to
  the test is bound to a nested savepoint (SQLAlchemy 2.0
  `join_transaction_mode="create_savepoint"`). A new savepoint is
  opened lazily before every ORM write, so a test may freely call
  `session.add(...)`, `session.execute(insert(...))`,
  `session.flush()`, etc., without manually managing savepoints.

- **Rollback after each test** — the outer transaction is rolled back
  unconditionally on teardown. Every write the test performed
  (including writes that passed through `session.commit()` and
  released a savepoint) is reverted. The next test starts from a
  clean database state without any TRUNCATE.

- **Behavior when a test calls `await session.commit()`** —
  `commit()` only releases the current savepoint; the outer
  transaction is not committed. After commit, a subsequent ORM write
  re-opens a fresh savepoint, so test code can interleave commit()
  with further writes if the application layer demands it. None of
  these writes survive teardown.

- **dev-DB safeguard integration** — the fixture calls
  `assert_safe_postgres_test_identity()` from
  `backend.tests.postgres_test_support` (Slice 1) before opening the
  outer transaction. Unsafe `DATABASE_URL`, forbidden port, dev DB
  name, or production-like `APP_ENV` causes the fixture to raise
  rather than connect. The Slice 1 27-test
  `test_dev_db_safeguard_slice1.py` suite remains the authoritative
  regression test for this property.

- **xdist / worker safety assumption** — the fixture is function-scope
  and uses a fresh `AsyncConnection` per test. With pytest-xdist each
  worker process has its own engine pool, so no cross-worker
  contention on the outer transaction. The fixture logs the resolved
  `PostgresTestIdentity.worker_id` in test output for traceability.

- **Failure handling** — if the test body raises, the savepoint is
  released, the outer transaction is rolled back, the session is
  closed, and the connection is returned to the pool. Exceptions are
  re-raised after cleanup; the fixture never swallows test failures.

## Opt-in Migration

Only one representative integration test is migrated in this slice:

- `backend/tests/integration/test_health_ready_postgres.py`

This test is selected because it is:

- Non-migration (does not exercise Alembic upgrade / downgrade).
- Non-concurrency (does not open parallel sessions or
  `with_for_update()`).
- Non-stateful (no cross-test shared fixtures, no module-level
  monkeypatching).
- Already a PG-dependent integration test under
  `RUN_POSTGRES_INTEGRATION=1`.

The migration changes the test's body to take the new
`transactional_pg_session` fixture as a parameter and perform a
minimal direct-database round-trip (insert a row into a tiny lookup
table, read it back) so the new fixture is exercised end-to-end. The
test continues to assert the original HTTP `/health/ready` contract.

The 28 other integration test files in
`backend/tests/integration/` are NOT migrated in this slice. They
keep the existing `isolate_master_data_tables` autouse TRUNCATE
fixture.

## Deferred Work

- Slice 3: migration isolation (isolated database or isolated schema
  for Alembic upgrade / downgrade tests).
- Slice 4: concurrency isolation (serialized CI job + worker identity
  for real-commit / `with_for_update()` tests).
- Slice 5: TRUNCATE full removal (move the remaining
  `_truncate_master_data` paths to schema / database drop).
- CI workflow changes (out of scope for all of Batch 3 Slices 2 / 3
  / 4 / 5).
- Marker taxonomy cleanup (`@pytest.mark.postgres` / `migration` /
  `concurrency` etc., Batch 3 Slice 4 territory).

## Verification

The following commands are run in order. Every command must exit 0
with all tests passing.

```bash
# 1. Targeted: new minimum verification test
python3.12 -m pytest \
    backend/tests/integration/test_transactional_pg_session_slice2.py -q

# 2. Targeted: migrated representative test
python3.12 -m pytest \
    backend/tests/integration/test_health_ready_postgres.py -q

# 3. Regression: Slice 1 dev-DB safeguard still active
python3.12 -m pytest \
    backend/tests/safety/test_dev_db_safeguard_slice1.py -q

# 4. Broader: existing PG integration conftest suite
RUN_POSTGRES_INTEGRATION=1 \
    python3.12 -m pytest backend/tests/integration -q

# 5. Static checks
ruff check .
ruff format --check .
mypy backend
```

Acceptance gates:

- G-01: `test_outer_txn_rolls_back_inner_writes` proves rollback
  isolation.
- G-02: `test_commit_inside_test_does_not_leak` proves
  `session.commit()` inside the test does not escape the outer
  transaction.
- G-03: `test_savepoint_restart_after_commit` proves the savepoint
  re-opens on subsequent writes after a `commit()`.
- G-04: `test_dev_db_safeguard_still_active` proves the Slice 1
  identity validation runs before any connection is acquired.
- G-05: the migrated `test_health_ready_postgres.py` test still
  asserts the original `/health/ready` 200 contract under the new
  fixture.
- G-06: ruff / ruff format --check / mypy pass on the allowed file
  set.
- G-07: `isolate_master_data_tables` TRUNCATE behavior is unchanged
  for non-migrated tests (no other integration test sees a behavior
  change because of this slice).
