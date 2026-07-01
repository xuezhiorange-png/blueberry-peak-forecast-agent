# Task 11 Infrastructure — PostgreSQL Test Environment and CI Plan

Status: **IMPLEMENTATION PLANNING / DRAFT PR**  
Issue: **#23**  
Base: `main@36791884768473c976b7e7a12a5bb3587501c4ec`  
Branch: `codex/issue-23-postgres-test-infra`

## 1. Purpose

This change set improves local PostgreSQL integration-test ergonomics, database isolation, and CI execution without changing any Task 8, Task 9, Task 10, or Task 11 business semantics.

The work starts only after PR #22 has merged and must remain in a separate branch and pull request.

## 2. Hard scope boundary

Allowed:

- isolated local PostgreSQL test environment;
- deterministic one-command test startup and teardown;
- PostgreSQL integration-test fixture isolation;
- migration/concurrency/real-commit test isolation;
- CI workflow separation and scheduling;
- JUnit/test artifact reporting;
- test-infrastructure documentation.

Not allowed:

- Task 11 execution orchestration;
- Task 9 or Task 10 service wiring;
- forecast, evaluation, metrics, export, API, CLI, or frontend work;
- business-model, authority, canonical-hash, persistence, or migration semantics changes;
- changes to frozen P0-6 through P0-7E contracts;
- weakening, skipping, or xfail-marking existing tests to obtain a green build.

## 3. Local PostgreSQL test environment

Add an isolated test service using `docker-compose.test.yml` or an equivalent dedicated Compose profile.

Required defaults:

```text
service: postgres-test
database: blueberry_peak_test
host port: 55432
container port: 5432
APP_ENV: test
PostgreSQL: 16
```

The test environment must not reuse the normal development database, port, or persistent volume.

Required commands must support:

```text
start test database
wait until healthy
run migrations
run PostgreSQL integration tests
stop and remove the isolated environment
```

A failed test command must still execute deterministic teardown.

## 4. Database safety guard

Integration-test fixtures must fail closed unless all required safety conditions are satisfied.

At minimum verify:

- `APP_ENV == test`;
- configured database name is exactly the dedicated test database;
- the connection does not target the normal development database;
- destructive reset operations cannot run against a non-test database;
- test configuration is explicit rather than inferred from an unrelated timestamp, path, or hostname.

## 5. Isolation strategy

### 5.1 Normal integration tests

Use transaction plus savepoint rollback where the tested behavior permits it.

Goals:

- no whole-database `TRUNCATE` before and after every test;
- deterministic cleanup;
- lower runtime and lock contention;
- no cross-test state leakage.

Fixtures must support async SQLAlchemy sessions and nested transaction restart where application code calls `commit()`.

### 5.2 Migration, concurrency, and real-commit tests

Tests that cannot run safely inside rollback isolation must use an explicitly isolated strategy, such as:

- a dedicated temporary schema;
- a dedicated temporary database;
- or serialized execution against the dedicated test database with targeted cleanup.

These tests must be marked and separated from normal rollback-isolated integration tests.

### 5.3 Destructive cleanup

A full-database reset may be used only for the narrow class of tests that requires it and only after the database safety guard succeeds.

The current global hard-coded table list and automatic full `TRUNCATE ... CASCADE` around every integration test must be removed or reduced to the explicitly isolated test class.

## 6. Pytest contracts

The implementation must define stable markers for the isolation classes. Exact names may be finalized during implementation, but the semantics must distinguish:

```text
normal PostgreSQL integration test
migration test
concurrency test
real-commit test
```

The default non-integration suite must remain PostgreSQL-independent.

The integration command must remain explicit and must not silently skip because of an accidental environment mismatch.

## 7. CI execution model

The CI design must preserve fast pull-request feedback while making the full PostgreSQL suite observable and reproducible.

Required triggers for the PostgreSQL workflow or job set:

- pull request;
- push to `main`;
- nightly schedule;
- manual `workflow_dispatch`.

Required CI evidence:

- PostgreSQL readiness check;
- Alembic upgrade/downgrade/upgrade verification;
- normal rollback-isolated integration tests;
- isolated migration/concurrency/real-commit tests;
- JUnit XML artifacts;
- failed-test summary;
- deterministic teardown.

Avoid executing the identical full integration suite twice in one workflow unless the two executions prove different contracts.

## 8. Expected implementation surfaces

Likely files include:

```text
docker-compose.test.yml
.github/workflows/ci.yml and/or a dedicated integration workflow
backend/tests/integration/conftest.py
pyproject.toml marker registration
scripts or Makefile targets for one-command local execution
documentation for local test usage
```

The actual diff must remain limited to infrastructure and tests. No production business module should change.

## 9. Acceptance gates

### Local

- isolated PostgreSQL starts on port `55432`;
- test database is `blueberry_peak_test`;
- migrations reach head;
- normal integration tests pass with rollback isolation;
- migration/concurrency/real-commit tests pass with explicit isolation;
- teardown removes the isolated environment;
- the development database is untouched.

### Static and regression

- `docker compose -f docker-compose.test.yml config` passes;
- Ruff passes;
- Ruff format check passes;
- Mypy passes;
- non-integration pytest passes;
- PostgreSQL integration pytest passes;
- full pytest passes;
- existing Task 11 Foundation and Task 9 authority tests remain unchanged and green.

### CI

- pull-request CI is green;
- `main` push execution is configured;
- nightly execution is configured;
- manual dispatch is configured;
- PostgreSQL artifacts and failure summaries are available.

## 10. Delivery policy

- PR remains Draft during implementation;
- no merge until independent engineering review;
- use fix-forward commits;
- do not amend, rebase, squash, or force-push reviewed checkpoints;
- eventual merge method is decided at final review;
- Issue #21 remains open and is not implemented in this PR.
