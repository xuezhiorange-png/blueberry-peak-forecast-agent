# [TASK-011-INFRA][Batch 3] PostgreSQL database isolation strategy — design freeze

## Status

Design-only freeze. This document does not implement database isolation, does not modify tests, does not modify CI workflows, and does not modify production semantics.

## Issue mapping
- Refs #51
- Refs #23

Issue #51 remains OPEN because implementation requires separate Charles authorization.
Issue #23 remains OPEN as the umbrella TASK-011-INFRA issue.

## Prior batch context
Batch 1 / PR #47 completed the local PostgreSQL one-command test environment.
Batch 2 design / PR #55 froze the CI de-duplication and PR workflow split design contract and was merged into `main` as:

```text
c5f0fd263114fa3f910a6821a24611e89772cc3c
```

Issue #50 remains OPEN for future Batch 2 implementation.

## Purpose
Define the PostgreSQL database isolation strategy for normal integration tests, migration tests, concurrency tests, and real-commit tests before any implementation starts.

## Non-goals
- No Batch 2 CI implementation.
- No Batch 4 marker taxonomy implementation.
- No Batch 5 fixture refactor.
- No Batch 6 CI performance / diagnostics implementation.
- No production semantic changes.
- No Task 8 / Task 9 / Task 10 behavior changes.
- No Alembic business schema changes.
- No ".github/workflows/**" changes in this design PR.
- No "backend/app/**" changes in this design PR.
- No "backend/tests/**" changes in this design PR.
- No "backend/alembic/versions/**" changes in this design PR.

## Isolation model overview
Batch 3 separates tests into three isolation classes:

1. Normal PostgreSQL integration tests.
2. Migration / Alembic tests.
3. Concurrency and real-commit tests.

Each class must have an explicit isolation boundary, cleanup model, worker identity rule, and CI compatibility rule.

### Normal integration tests
Normal integration tests should use transaction + savepoint + rollback.

Required properties:

- each test starts from a deterministic database state;
- writes are rolled back;
- no whole-database "TRUNCATE" before or after every test;
- no cross-test leakage;
- compatible with pytest parallelism only when worker identity is explicit;
- compatible with the Batch 1 dev-DB safeguard.

### Migration tests
Migration tests require stronger isolation than normal integration tests.

Allowed strategies:

1. isolated database per migration test group;
2. isolated schema per migration test group;
3. serialized migration test execution.

Migration tests must not run concurrently against the same schema unless the design proves that they are non-mutating.

### Concurrency and real-commit tests
Concurrency and real-commit tests cannot rely only on transaction rollback.

Required properties:

- isolated database or isolated schema;
- serialized execution unless worker-specific isolation is proven;
- explicit worker identity in logs;
- explicit cleanup after commit;
- no shared mutable test state across workers.

## Transaction / savepoint / rollback strategy
Normal tests use:

1. open outer transaction;
2. open nested savepoint;
3. allow application code to commit inside the nested boundary only where safe;
4. restart savepoint when required;
5. rollback outer transaction at test end.

The implementation must reject hidden commits that escape the isolation boundary.

## Isolated schema vs isolated database decision matrix
Use isolated schema when:

- migrations are not being tested directly;
- DDL side effects are controlled;
- search_path can be made deterministic;
- all test code respects schema-qualified or search_path-bound access.

Use isolated database when:

- Alembic upgrade / downgrade is under test;
- extensions, global objects, or schema lifecycle are mutated;
- concurrent writers may commit;
- the test must prove full deployment behavior.

## Worker identity and parallelism model
Every PostgreSQL test run must expose:

- pytest worker id;
- database name;
- schema name if applicable;
- app environment;
- PostgreSQL port;
- migration head / revision if applicable.

Parallel tests must not share the same mutable schema unless they are read-only.

## Alembic migration safety
Migration tests must verify:

- upgrade from base to head;
- downgrade / rollback only if supported by the project contract;
- repeated upgrade is idempotent where expected;
- migration tests never target the development database;
- migration tests never rely on state created by a previous test.

## Deterministic cleanup model
Cleanup must be deterministic and scoped.

Forbidden default pattern:

```text
TRUNCATE every table before and after every test
```

Allowed cleanup patterns:

- transaction rollback for normal tests;
- schema drop for isolated-schema tests;
- database drop for isolated-database tests;
- explicit committed-row cleanup for narrow real-commit tests.

Cleanup must fail closed if target database / schema does not match the test profile.

## Dev-DB safeguard preservation
Batch 1 introduced protection against connecting test commands to the development database.

Batch 3 must preserve and extend that safeguard:

- reject development DB name;
- reject development port;
- reject production-like "APP_ENV";
- reject unsafe "DATABASE_URL";
- log resolved test DB identity;
- never silently fall back to development defaults.

## CI compatibility with future Batch 2 split
Batch 3 must be compatible with the future Batch 2 PR CI job layout:

- "postgres-migration"
- "postgres-domain-1"
- "postgres-domain-2"
- "postgres-task11"
- "postgres-concurrency"

The isolation strategy must allow these jobs to run without duplicating test commands or leaking database state.

## Future implementation allowed paths
A future implementation PR may touch only the minimum necessary subset of:

- "backend/tests/conftest.py"
- "backend/tests/postgres_test_support.py"
- "backend/tests/db/**"
- "backend/tests/safety/**"
- "backend/scripts/**"
- "Makefile"
- "docker-compose.test.yml"
- "pyproject.toml" only for marker or pytest configuration required by isolation
- documentation under "docs/**"

Any other path requires explicit Charles authorization.

## Future implementation forbidden paths
A future implementation PR must not touch:

- Task 8 / Task 9 / Task 10 production semantics;
- "backend/app/**" unless a separately authorized test-support seam is required;
- "backend/alembic/versions/**" unless a separately authorized migration-test fixture is required;
- frontend / API / agent surfaces;
- CI workflow files unless Batch 2 implementation has explicitly authorized CI split work.

## Acceptance gates
- G-01: normal integration tests prove rollback isolation.
- G-02: migration tests prove isolated schema or isolated database behavior.
- G-03: concurrency / real-commit tests prove no cross-test leakage.
- G-04: dev-DB safeguard remains fail-closed.
- G-05: whole-database "TRUNCATE" is not the default cleanup pattern.
- G-06: worker identity appears in PostgreSQL test logs.
- G-07: future Batch 2 CI split can consume the isolation classes without overlapping commands.

## Rollback plan
Rollback must be documentation-first for the design PR.

For a future implementation PR:

1. disable new isolation fixture path;
2. restore previous PostgreSQL test fixture behavior;
3. preserve dev-DB safeguard;
4. preserve one-command test harness;
5. leave clear diagnostic logs explaining which isolation path was active.

## Blocker taxonomy
P0 blockers:

- risk of test command touching development database;
- cross-test data leakage;
- migration tests sharing mutable database state unsafely;
- real-commit tests not isolated;
- hidden whole-database destructive cleanup;
- CI split incompatible with isolation classes.

P1 blockers:

- missing worker identity logs;
- missing cleanup assertion;
- incomplete marker-to-isolation mapping;
- ambiguous schema vs database selection.

P2 follow-ups:

- performance optimization;
- fixture ergonomics;
- additional diagnostics;
- optional local developer shortcuts.

## Risk register
- R-01: isolated database per worker may slow CI.
- R-02: isolated schema may fail for migrations that assume public schema.
- R-03: transaction rollback may not catch application-level commits.
- R-04: concurrency tests may be flaky without serialization.
- R-05: marker taxonomy may need Batch 4 coordination.
- R-06: Batch 2 CI split may expose missing isolation boundaries.

## Open questions
- OQ1: Should migration tests use isolated database by default, with isolated schema only for non-migration integration tests?
- OQ2: Should concurrency tests run in a dedicated serialized CI job?
- OQ3: Should worker identity be enforced by fixture assertion or only logged?
- OQ4: Should the removal of default whole-database "TRUNCATE" happen in one implementation PR or in staged slices?

## Self-audit checklist
- [ ] Design-only document.
- [ ] No production code changes.
- [ ] No test changes.
- [ ] No CI workflow changes.
- [ ] No Alembic migration changes.
- [ ] Issue #51 remains OPEN.
- [ ] Issue #23 remains OPEN.
- [ ] Issue #50 remains OPEN.

## Appendix A — Batch 3 as-built implementation record

Batch 3 was implemented in staged slices after this design freeze. The as-built evidence is recorded in:

```text
docs/task-11-issue-51-batch3-implementation-record.md
```

Summary:

- Slice 1 / PR #59: dev-DB safeguard baseline, merged as `bd883d7885c66b18eb18fe8e56b419ecbac0e7f4`.
- Slice 2 / PR #60: opt-in transaction + savepoint + rollback fixture, merged as `e5a616e3ef851bd69727fae7c5989fc04d4361aa`.
- Slice 2 hotfix / PR #61: rollback probe schema correction, merged as `cbd7930da58a79d19804316d8dcd3b3ba766f955`.
- Slice 3 / PR #62: `postgres-migration` isolated database profile, merged as `4311b301b73ecc938f92b2f38d37784afa04a075`.
- Slice 4 / PR #63: `postgres-concurrency` isolated database profile, merged as `5838f9e6c613a24289de4fbde47b1c4521c93f97`.
- Slice 5 / PR #64: ordinary integration savepoint rollback isolation narrowing, merged as `14b891ccf7fd537aa33bc13dc543b19f656b6b68`.

As-built acceptance status:

- G-01: closed by Slice 2 + Slice 5.
- G-02: closed by Slice 3.
- G-03: closed by Slice 4.
- G-04: closed by Slice 1 and preserved through later slices.
- G-05: partially closed; savepoint-isolated tests no longer use default TRUNCATE, while non-opted-in tests intentionally retain the legacy TRUNCATE path.
- G-06: open residual; worker identity logs were not implemented or verified across all PostgreSQL test paths.
- G-07: partially closed; the CI split consumes the migration and concurrency isolation classes, but full marker-to-isolation mapping remains incomplete.

This appendix is documentation-only. It does not reinterpret the original design freeze as authorizing CI diagnostics, marker taxonomy cleanup, fixture refactor, production semantics, Alembic migration changes, or Issue closeout.
