# [TASK-011-INFRA][Batch 3][Slice 6] Batch 3 implementation record

## Status

This document is the Slice 6 as-built implementation record for Issue #51.

It is documentation-only. It does not modify production code, tests, Alembic migrations, pytest markers, or CI workflow files.

## Issue mapping

- Refs #51
- Refs #23

Issue #51 remains open until Charles separately authorizes final closeout after this documentation PR is merged.
Issue #23 remains open as the umbrella TASK-011-INFRA issue.

## Source of truth

This record summarizes the implemented Batch 3 slices that landed on `main` through PR #59 through PR #64.

Current Batch 3 terminal main SHA at the time of this record:

```text
14b891ccf7fd537aa33bc13dc543b19f656b6b68
```

## Slice inventory

| Slice | PR | Title | Merge SHA | Status | Closeout record |
|---|---:|---|---|---|---|
| Slice 1 | #59 | PostgreSQL test identity baseline | `bd883d7885c66b18eb18fe8e56b419ecbac0e7f4` | Complete | Issue #51 comment `4902518002` |
| Slice 2 | #60 | Transactional PostgreSQL test isolation | `e5a616e3ef851bd69727fae7c5989fc04d4361aa` | Complete | Not confirmed on Issue #51; tracked here as known record gap |
| Slice 2 hotfix | #61 | Fix dim_season rollback probe schema | `cbd7930da58a79d19804316d8dcd3b3ba766f955` | Complete | Covered as part of Slice 2 implementation history |
| Slice 3 | #62 | postgres-migration isolated DB profile | `4311b301b73ecc938f92b2f38d37784afa04a075` | Complete | Issue #51 comment `4905813173` |
| Slice 4 | #63 | postgres-concurrency isolated DB profile | `5838f9e6c613a24289de4fbde47b1c4521c93f97` | Complete | GitHub closeout write was blocked by platform write guard; tracked here as known exception |
| Slice 5 | #64 | ordinary integration savepoint rollback isolation | `14b891ccf7fd537aa33bc13dc543b19f656b6b68` | Complete | Issue #51 comment `4910637552` |

## CI evidence summary

| Slice | PR CI | Main push CI | Notes |
|---|---|---|---|
| Slice 1 | `28853697874` completed / success | `28857032765` completed / success | Main canary passed after merge. |
| Slice 2 | PR #60 CI green before merge | PR #60 main canary exposed the `dim_season` probe mismatch | Fixed by Slice 2 hotfix PR #61. |
| Slice 2 hotfix | Hotfix PR CI green before merge | Main canary passed after merge | Corrected the rollback probe schema. |
| Slice 3 | `28877022654` completed / success | `28879391581` completed / success | Migration isolated DB profile preserved. |
| Slice 4 | PR #63 CI completed / success | `28906555487` completed / success | Concurrency isolated DB profile preserved. |
| Slice 5 | `28909973836` completed / success | `28910455004` completed / success | Main push ran `full-suite-canary`; PR-only jobs skipped as expected. |

## Delivered behavior by slice

### Slice 1 — dev-DB safeguard baseline

Delivered a fail-closed PostgreSQL test identity baseline in `backend/tests/postgres_test_support.py`, plus safety tests and documentation.

As-built responsibilities:

- Resolve PostgreSQL test identity from environment.
- Reject development-like database names, unsafe ports, production-like app environments, and unsafe URLs.
- Keep error messages secret-safe.
- Provide the guard used by later isolated database helpers.

### Slice 2 — opt-in transaction / savepoint / rollback fixture

Delivered the opt-in ordinary integration-test isolation path:

- `backend/tests/integration/_txn_isolation.py`
- `transactional_pg_session` fixture in `backend/tests/integration/conftest.py`
- Fixture-contract tests for rollback, commit-does-not-leak behavior, savepoint restart, and dev-DB safeguard integration.

Slice 2 did not remove the existing whole-database `TRUNCATE` autouse fixture. That was intentionally deferred to Slice 5.

### Slice 2 hotfix — rollback probe schema correction

Corrected the Slice 2 rollback probe to match the actual `dim_season` schema after main canary found a nonexistent-column failure.

### Slice 3 — migration isolated database profile

Delivered an isolated database profile for the destructive Alembic migration round-trip.

As-built responsibilities:

- Resolve a per-run `postgres_migration` isolated database name.
- Route the name through the Slice 1 fail-closed guard.
- Create the isolated database before migration tests.
- Run destructive Alembic upgrade / downgrade / upgrade against the isolated database.
- Drop the isolated database in best-effort cleanup without masking upstream failures.

### Slice 4 — concurrency isolated database profile

Delivered an isolated database profile for concurrency and real-commit tests.

As-built responsibilities:

- Reuse the Slice 3 isolated DB resolver / guard primitives for the canonical `postgres_concurrency` job.
- Prove the concurrency job uses a different isolated DB name from migration.
- Prove committed writes are visible to fresh sessions inside the isolated DB.
- Preserve separation from domain, task11, migration, compose-smoke, and full-suite-canary jobs.

### Slice 5 — ordinary integration savepoint rollback isolation narrowing

Delivered the narrowed cleanup rule for ordinary integration tests that explicitly opt into `transactional_pg_session`.

As-built responsibilities:

- Add `_SAVEPOINT_ISOLATION_FIXTURES` and `_request_uses_savepoint_isolation()` to `backend/tests/integration/conftest.py`.
- Skip whole-database `TRUNCATE` only for tests that declare a savepoint-isolation fixture.
- Preserve the existing `TRUNCATE` behavior for non-savepoint tests.
- Add fixture-contract tests proving no cross-test leakage under the savepoint path.
- Preserve Slice 1 dev-DB safeguards and Slice 3 / Slice 4 isolated DB profiles.

## Acceptance gate status

| Gate | Requirement | Status | Evidence / residual |
|---|---|---|---|
| G-01 | Normal integration tests prove rollback isolation. | Closed | Slice 2 introduced `transactional_pg_session`; Slice 5 narrowed TRUNCATE for opted-in tests and added fixture-contract tests. |
| G-02 | Migration tests prove isolated schema or isolated database behavior. | Closed | Slice 3 bound destructive Alembic migration tests to a per-run isolated database profile. |
| G-03 | Concurrency / real-commit tests prove no cross-test leakage. | Closed | Slice 4 bound concurrency / real-commit tests to a distinct per-run isolated database profile. |
| G-04 | Dev-DB safeguard remains fail-closed. | Closed | Slice 1 guard preserved and reused through Slice 3 / Slice 4 helpers; Slice 5 kept negative safeguard coverage. |
| G-05 | Whole-database `TRUNCATE` is not the default cleanup pattern. | Partially closed | Savepoint-isolated tests no longer use TRUNCATE. Non-opted-in integration tests still keep the pre-Slice-5 TRUNCATE path by design. |
| G-06 | Worker identity appears in PostgreSQL test logs. | Open residual | Not implemented / not verified in Batch 3 Slice 1-5. This remains a documented residual, not implemented in this docs-only Slice 6. |
| G-07 | Batch 2 CI split can consume the isolation classes without overlapping commands. | Partially closed | PR-event split and main-push canary behavior are working; Slice 3 / Slice 4 isolated DB jobs coexist with the split. Full marker-to-isolation mapping remains incomplete. |

## Known residuals and exceptions

### Slice 2 closeout record gap

A Slice 2 closeout comment is not confirmed on Issue #51. Slice 2 and its hotfix are implemented and merged; the missing closeout comment is a record gap, not an implementation blocker.

This Slice 6 record does not repost Slice 2 closeout. A retroactive GitHub comment requires separate Charles authorization.

### Slice 4 closeout write-guard exception

Slice 4 is implemented and merged. A prior attempt to write the closeout comment was blocked by the platform write guard. This record treats that as a known governance exception.

This Slice 6 record does not retry the Slice 4 closeout comment. A retry requires separate Charles authorization.

### Slice 5 closeout scrape discrepancy

Slice 5 closeout is recorded as Issue #51 comment `4910637552`. Some HTML scrape attempts did not show this comment; the connector comment read returned it, and this record treats the connector-read comment as authoritative.

### Worker identity logs

The design freeze listed worker identity in PostgreSQL test logs as G-06 and a P1 blocker. Batch 3 Slice 1-5 did not implement or verify worker identity logs as a universal requirement.

This Slice 6 PR documents the residual only. It does not modify `.github/workflows/**`, pytest markers, or test fixtures.

### Marker-to-isolation mapping

The current marker taxonomy remains incomplete:

- `integration` is broadly used.
- `postgres_concurrency` is used for concurrency-specific tests.
- `postgres` is registered but not consistently used across all PostgreSQL tests.

Full marker taxonomy cleanup is outside this docs-only Slice 6 and remains separate future work.

## Issue closeout policy

Issue #51 may be considered for closeout only after:

1. this Slice 6 documentation PR is merged;
2. main post-merge CI is green;
3. Charles separately authorizes Issue #51 closeout;
4. any final closeout comment or known write-guard exception is explicitly recorded.

Issue #23 must remain open as the umbrella TASK-011-INFRA issue until all umbrella sub-areas are complete.

## Explicit out of scope for Slice 6

This Slice 6 implementation record does not authorize or perform:

- `.github/workflows/**` changes;
- `backend/app/**` changes;
- `backend/alembic/versions/**` changes;
- production semantic changes;
- test marker or pytest config changes;
- CI diagnostics implementation;
- marker taxonomy cleanup;
- fixture refactor;
- new PostgreSQL helper behavior;
- Issue #51 close;
- Issue #23 close;
- retroactive GitHub closeout comments.

## Final status

```text
TASK-011 Batch 3 Slice 6: docs-only implementation record
Issue #51: remains OPEN pending separate Charles closeout authorization
Issue #23: remains OPEN as umbrella
```
