# [TASK-011-INFRA][Batch 4] Pytest marker taxonomy — design freeze

## Status

Design-only freeze. This document does not implement marker changes, does not modify tests, does not modify CI workflows, and does not modify production semantics.

Batch 4 implementation requires a separate Charles authorization round after this design PR is reviewed.

## Issue mapping

- Refs #52
- Refs #23

Issue #52 remains open until a separate implementation PR is authorized, merged, verified, and separately closed.
Issue #23 remains open as the umbrella TASK-011-INFRA issue.

This design uses only non-closing references.

## Baseline

Current baseline for this design is main at:

```text
b6433877cf1bf2d18df5e3256730a64562149649
```

Relevant completed prerequisites:

- Batch 1 / PR #47: local PostgreSQL test harness and dev-DB safeguard.
- Batch 2 / PR #57 and PR #58: deduplicated PR CI layout and format baseline normalization.
- Batch 3 / PR #59 through PR #65: PostgreSQL database isolation strategy and as-built implementation record.

Current `pyproject.toml` registers only these pytest markers:

```text
postgres
integration
postgres_concurrency
```

Issue #52 requires the explicit taxonomy to include:

```text
unit
contract
golden
postgres
migration
concurrency
e2e
slow
task8
task9
task10
task11
```

## Problem statement

Batch 2 introduced a deduplicated PR CI layout with explicit shard ownership. Batch 3 added isolated DB profiles for migration and concurrency workloads. The remaining marker problem is that marker semantics are still partial:

- `integration` is broad and is not enough to describe execution ownership.
- `postgres_concurrency` is an execution-specific sharp selector, but it is not part of the final Issue #52 taxonomy name set.
- `postgres` exists but is not consistently used across PostgreSQL tests.
- task-domain labels such as `task8`, `task9`, `task10`, and `task11` are not registered.
- unit / contract / golden / e2e / slow markers are not registered.

The goal of Batch 4 is to define a deterministic marker taxonomy before any implementation touches tests or CI ownership.

## Design principles

1. Additive migration first. Batch 4 should add markers and documentation without removing legacy markers until CI ownership is proven stable.
2. Single-execution remains authoritative. A test node may carry multiple semantic markers, but it must map to exactly one PR CI owner.
3. Execution markers and semantic markers are separate dimensions.
4. Existing Batch 2 CI commands must not be casually rewritten in the first taxonomy implementation.
5. Production semantics are out of scope.
6. Test behavior changes are out of scope unless explicitly authorized in the implementation round.
7. Marker names must be stable, documented, and grep-auditable.

## Marker dimensions

### Execution markers

Execution markers affect CI ownership, resource profile, or runtime profile.

| Marker | Meaning | CI ownership implication |
|---|---|---|
| `unit` | Tests that do not require PostgreSQL or external services. | Eligible for `unit-contract-golden`. |
| `postgres` | Tests requiring PostgreSQL. | Eligible for a postgres shard. |
| `migration` | Alembic or migration round-trip tests. | Owned by `postgres-migration`. |
| `concurrency` | Tests requiring real commits, concurrent transactions, or cross-session visibility. | Owned by `postgres-concurrency`. |
| `e2e` | End-to-end production-shaped tests. | Requires explicit owner; canary-only if too broad for PR CI. |
| `slow` | Long-running tests whose expected runtime is greater than 30 seconds. | Requires explicit owner and may be excluded from fast PR shards only if canary coverage is documented. |

### Assertion-style markers

Assertion-style markers describe what kind of test the node is, but do not by themselves choose a database profile.

| Marker | Meaning |
|---|---|
| `contract` | Contract tests against deterministic service-layer, API, or CLI output. |
| `golden` | Golden or snapshot tests with stored expected outputs or hashes. |

### Task-domain markers

Task-domain markers describe the product area under test. They must not override execution ownership.

| Marker | Meaning |
|---|---|
| `task8` | Natural maturity curve tests. |
| `task9` | Harvest capacity / authority / mature inventory tests. |
| `task10` | Residual model tests. |
| `task11` | Evaluation, mask, canonicalization, hash, key, audit, and infrastructure tests related to Task 11. |

## Legacy marker compatibility

The current codebase uses these legacy markers:

| Legacy marker | Compatibility rule |
|---|---|
| `integration` | Keep registered during migration. It remains a broad service/external-dependency indicator and may coexist with `postgres`, `e2e`, or task-domain markers. |
| `postgres_concurrency` | Keep as a temporary alias for the current Batch 2 CI selector. Batch 4 implementation should introduce `concurrency` while preserving `postgres_concurrency` until CI is updated or an alias strategy is proven. |

Recommended first implementation behavior:

- Register all Issue #52 markers in `pyproject.toml`.
- Keep `integration` and `postgres_concurrency` registered.
- Add documentation that `postgres_concurrency` is a legacy compatibility marker.
- Do not remove or rename existing marker usage in the first implementation unless the shard manifest proves no duplicate or missing test nodes.

## CI ownership precedence

When a test node carries multiple markers, CI ownership is resolved by precedence:

1. `concurrency` or legacy `postgres_concurrency` → `postgres-concurrency`.
2. `migration` → `postgres-migration`.
3. `postgres` + `task11` → `postgres-task11`, unless rule 1 or 2 applies.
4. `postgres` + non-task11 domain files → `postgres-domain-1` or `postgres-domain-2`, as listed in `ci-shard-manifest.yml`.
5. `unit`, `contract`, or `golden` without `postgres`, `migration`, `concurrency`, or `e2e` → `unit-contract-golden`.
6. `slow` does not choose ownership by itself; it adds runtime policy and must be paired with an owning marker or file path.
7. `e2e` must have an explicit owner in `ci-shard-manifest.yml`; otherwise it is a blocker.

The sharp selector rule from Batch 2 remains active: concurrency ownership wins over file-path ownership.

## Required implementation artifacts

A future Batch 4 implementation PR should update, at minimum:

- `pyproject.toml` — register the full taxonomy plus compatibility markers.
- `ci-shard-manifest.yml` — record marker ownership, precedence, and any canary-only exclusions.
- Selected `backend/tests/**` files — add markers only where ownership is clear and deterministic.
- A Batch 4 implementation freeze document under `docs/`.

A future implementation PR may update `.github/workflows/ci.yml` only if the manifest proves the current Batch 2 selectors cannot express the taxonomy without duplicate execution. Workflow changes should be treated as high-risk and separately justified.

## Design-only allowed paths

This design PR may change only:

```text
docs/task-11-issue-52-batch4-marker-taxonomy-design.md
```

If a task backlog status update is later desired, it requires separate authorization or a separate docs-only follow-up.

## Implementation allowed paths

A future implementation PR may touch only the minimum required subset of:

```text
pyproject.toml
ci-shard-manifest.yml
backend/tests/**
docs/task-11-issue-52-batch4-marker-taxonomy-implementation-freeze.md
.github/workflows/ci.yml  # only if explicitly justified
```

## Forbidden paths and actions

Unless separately authorized, Batch 4 must not touch:

```text
backend/app/**
backend/alembic/versions/**
frontend/**
docker-compose*.yml
Makefile
uv.lock
.env.example
replay_trained_model
```

Forbidden actions:

- Production semantic changes.
- Database schema changes.
- Alembic migration changes.
- Task 8 / Task 9 / Task 10 / Task 11 business logic changes.
- Closing Issue #23.
- Closing Issue #52 from a design-only PR.
- Removing legacy markers before compatibility is proven.

## Acceptance gates for implementation

G-01: All required markers are registered in `pyproject.toml`.

G-02: Legacy markers remain registered until a compatibility migration is complete.

G-03: `ci-shard-manifest.yml` defines ownership precedence and maps every touched marker to one PR CI owner or a documented canary-only path.

G-04: No test node is intentionally executed by more than one PR CI job.

G-05: No test node is accidentally dropped from PR CI unless explicitly documented as canary-only.

G-06: Existing Batch 2 PR job layout remains green after marker changes.

G-07: Main-push `full-suite-canary` remains green after merge.

G-08: Dev-DB safeguard tests remain in PR CI.

G-09: PostgreSQL migration and concurrency jobs keep isolated DB behavior from Batch 3.

G-10: No production code or migration files are changed.

## Audit commands for implementation

The implementation PR should include read-only evidence equivalent to:

```bash
pytest --markers
pytest --collect-only -q
pytest -m "not integration and not postgres and not postgres_concurrency" --collect-only -q
pytest -m postgres_concurrency --collect-only -q
```

If the implementation introduces `concurrency` as the new canonical marker while retaining `postgres_concurrency`, the audit must also include:

```bash
pytest -m concurrency --collect-only -q
```

The final implementation report must compare node ownership before and after marker changes.

## Migration plan

Recommended slices:

1. Register marker taxonomy and update documentation.
2. Update `ci-shard-manifest.yml` with marker precedence and compatibility rules.
3. Add markers to the smallest deterministic set of tests first: migration, concurrency, task11, and dev-DB safeguard tests.
4. Run PR CI and check for duplicate or missing nodes.
5. Expand markers to broader unit / contract / golden / task-domain tests only after the first set is stable.
6. Defer removal of `postgres_concurrency` until a separate compatibility-removal PR.

## Rollback model

Rollback must be simple:

- Revert marker registration changes in `pyproject.toml`.
- Revert marker additions in `backend/tests/**`.
- Revert manifest changes in `ci-shard-manifest.yml`.
- Keep Batch 2 CI split and Batch 3 isolation intact.

The rollback must not require production code changes.

## Open questions

1. Should `concurrency` become the canonical marker while `postgres_concurrency` remains an alias, or should `postgres_concurrency` remain the CI selector until a later cleanup?
2. Should `integration` remain a broad marker indefinitely, or become a legacy compatibility marker after explicit `postgres` / `e2e` / task-domain labels are complete?
3. Should task-domain markers drive CI ownership, or stay purely descriptive while execution markers drive jobs?
4. Should `slow` tests be allowed in PR CI, or should some be canary-only with explicit manifest entries?
5. Should Batch 4 be implemented in one PR or split into registration / manifest / test marking slices?

## Self-audit checklist for this design PR

- [ ] Design-only.
- [ ] No `pyproject.toml` changes.
- [ ] No `backend/tests/**` changes.
- [ ] No `.github/workflows/**` changes.
- [ ] No `ci-shard-manifest.yml` changes.
- [ ] No production code changes.
- [ ] Issue #52 remains open.
- [ ] Issue #23 remains open.
- [ ] Uses only non-closing references.
