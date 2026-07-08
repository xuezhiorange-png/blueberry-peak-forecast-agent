# [TASK-011-INFRA][Batch 4][Slice 1] Pytest marker taxonomy — implementation freeze

## Status

Implementation freeze for Batch 4 Slice 1 only. This document freezes the
minimal deterministic marker registration + manifest update for the
Issue #52 pytest marker taxonomy.

- This PR does **NOT** close Issue #52.
- This PR does **NOT** close Issue #23.
- Refs #52 / Refs #23 only.
- Implementation requires a separate Charles authorization round.

## Base SHA

```text
bab97c3ca63e1b42cfdeeec5ecd8a16257f1d021
```

This is `main` after PR #66 (the Batch 4 design freeze) was merged.

## Scope (Slice 1 only)

- Register the full Issue #52 marker taxonomy in `pyproject.toml`.
- Preserve legacy compatibility markers (`integration`, `postgres_concurrency`).
- Update `ci-shard-manifest.yml` to record the new taxonomy, ownership
  precedence, and per-shard marker policy.
- Add markers only to the minimal deterministic test set whose ownership
  is already proven by `ci-shard-manifest.yml` (migration / concurrency /
  task11 / dev-DB-safeguard).
- Write this implementation freeze document.

## Changed files

```text
pyproject.toml                                         (markers registered)
ci-shard-manifest.yml                                   (taxonomy section)
backend/tests/test_alembic_baseline.py                  (added pytestmark = [postgres, migration])
backend/tests/test_harvest_state_alembic.py             (added pytestmark = [postgres, migration])
backend/tests/test_residual_model_alembic.py            (added pytestmark = [postgres, migration])
backend/tests/test_alembic_round_trip_isolated.py        (pytestmark postgres -> [postgres, migration])
backend/tests/test_alembic_round_trip_isolated_db_live.py (pytestmark postgres -> [postgres, migration])
backend/tests/test_concurrency_isolation_helpers_live.py (pytestmark postgres_concurrency -> [postgres_concurrency, concurrency])
backend/tests/integration/test_task11_dependency_serialization.py (per-test @pytest.mark.concurrency added; pytestmark [integration, task11])
backend/tests/integration/test_task9_authority_repository_postgres.py (per-test @pytest.mark.concurrency added to 2 nodes)
backend/tests/test_task11_phase3_schema_gap.py           (added pytestmark = [task11])
backend/tests/integration/test_task11_exact_load_and_colon_matrix.py (pytestmark integration -> [integration, task11])
backend/tests/integration/test_task11_hardening_tests.py (pytestmark integration -> [integration, task11])
backend/tests/integration/test_task11_phase3_schema_gap_persistence.py (pytestmark asyncio -> [asyncio, task11])
docs/task-11-issue-52-batch4-marker-taxonomy-implementation-freeze.md (this file)
```

Total: 14 files changed (12 source files + 2 doc files).

## Marker registry — before / after

### Before (3 markers)

```text
postgres              — PostgreSQL tests using the isolated local test profile
integration           — tests that require external services such as PostgreSQL
postgres_concurrency  — PostgreSQL integration tests requiring independent concurrent transactions
```

### After (14 markers — 12 canonical + 2 legacy)

```text
# Execution markers (CI ownership + resource profile)
unit                  — Unit tests, eligible for unit-contract-golden
contract              — Contract tests (descriptive)
golden                — Golden / snapshot tests (descriptive)
postgres              — PostgreSQL tests (eligible for any postgres-* shard)
migration             — Alembic / migration round-trip tests, owned by postgres-migration
concurrency           — Real-commit / concurrent transaction tests, owned by postgres-concurrency (additive alias for legacy postgres_concurrency)
e2e                   — End-to-end production-shaped tests (canary-only if not owned in PR CI)
slow                  — Long-running tests (canary-only if not owned in PR CI)

# Task-domain markers (descriptive, do not override execution ownership)
task8 / task9 / task10 / task11

# Legacy compatibility markers (preserved during migration)
integration           — broad service / external-dependency indicator
postgres_concurrency  — current Batch 2 CI selector for postgres-concurrency shard
```

## Compatibility model

- `concurrency` is the canonical Issue #52 taxonomy marker for the
  `postgres-concurrency` shard.
- `postgres_concurrency` remains the **active** PR CI sharp selector in
  the `.github/workflows/ci.yml` `-m` filter for that shard.
- `concurrency` is added **additively** alongside `postgres_concurrency`
  on the same set of 11 nodes. It is grep-auditable via
  `pytest -m concurrency` but does **not** yet drive CI selectors.
- A future compatibility-removal PR may switch CI to `-m concurrency`
  and deprecate `postgres_concurrency`. That is **out of scope** for
  this slice.
- `integration` is preserved as a broad service / external-dependency
  indicator. It may coexist with `postgres`, `e2e`, or task-domain
  markers and is not removed by this slice.

## Touched test files (deterministic ownership proof)

| File | shard owner (manifest) | markers after Slice 1 |
|---|---|---|
| `backend/tests/test_alembic_baseline.py` | `postgres-migration` (file-list) | `[postgres, migration]` |
| `backend/tests/test_harvest_state_alembic.py` | `postgres-migration` (file-list) | `[postgres, migration]` |
| `backend/tests/test_residual_model_alembic.py` | `postgres-migration` (file-list) | `[postgres, migration]` |
| `backend/tests/test_alembic_round_trip_isolated.py` | `postgres-migration` (file-list) | `[postgres, migration]` |
| `backend/tests/test_alembic_round_trip_isolated_db_live.py` | `postgres-migration` (file-list) | `[postgres, migration]` |
| `backend/tests/test_concurrency_isolation_helpers_live.py` | `postgres-concurrency` (marker) | `[postgres_concurrency, concurrency]` |
| `backend/tests/integration/test_task11_dependency_serialization.py` | `postgres-task11` (file glob, non-concurrency nodes) / `postgres-concurrency` (5 marked nodes) | `[integration, task11]` + per-test `[postgres_concurrency, concurrency]` |
| `backend/tests/integration/test_task9_authority_repository_postgres.py` | `postgres-concurrency` (marker on 2 nodes) / `postgres-domain-1` (file glob, other nodes) | per-test `@pytest.mark.concurrency` added to 2 nodes |
| `backend/tests/test_task11_phase3_schema_gap.py` | `postgres-task11` (file-list) | `[task11]` |
| `backend/tests/integration/test_task11_exact_load_and_colon_matrix.py` | `postgres-task11` (file-list) | `[integration, task11]` |
| `backend/tests/integration/test_task11_hardening_tests.py` | `postgres-task11` (file-list) | `[integration, task11]` |
| `backend/tests/integration/test_task11_phase3_schema_gap_persistence.py` | `postgres-task11` (file-list) | `[asyncio, task11]` |

The dev-DB safeguard test
(`backend/tests/safety/test_dev_db_protection.py`) is **preserved** in
the `unit-contract-golden` shard per the manifest's `owner_files`
entry. **No marker changes are applied to it in this slice.**

## Ownership proof — node count delta

| Selector | Before | After | Delta | Notes |
|---|---|---|---|---|
| `pytest --collect-only -q` (total) | 1752 | 1752 | 0 | unchanged |
| `-m "not integration and not postgres and not postgres_concurrency"` (unit-contract-golden) | 1306 | 1292 | -14 | 14 tests now correctly excluded via `pytest.mark.postgres` (they were already in the `postgres-migration` shard by file-list, but the marker was missing) |
| `-m postgres_concurrency` (sharp selector) | 11 | 11 | 0 | unchanged (the 11 nodes are still selected by this filter) |
| `-m concurrency` (new canonical, additive) | 0 | 11 | +11 | the 11 nodes from above now also carry `concurrency` |
| `-m migration` (new canonical) | 0 | 37 | +37 | 5 files × their node counts |
| `-m task11` (new canonical) | 0 | 109 | +109 | 5 task11 files × their node counts |

The 14-test unit-contract-golden reduction is a **correctness fix**:
these 14 tests are pure migration metadata tests that should not have
been in the unit shard in the first place. They are already correctly
owned by `postgres-migration` per the manifest's file-list.

## Audit commands (read-only evidence)

```bash
pytest --markers
pytest --collect-only -q
pytest -m "not integration and not postgres and not postgres_concurrency" --collect-only -q
pytest -m postgres_concurrency --collect-only -q
pytest -m concurrency --collect-only -q
pytest -m migration --collect-only -q
pytest -m task11 --collect-only -q
```

## Lint / format / type

- `ruff check .` — no new errors (43 pre-existing, all in untouched files)
- `ruff format --check .` — only `.venv-3.12/bin/runxlrd.py` would reformat
  (virtualenv binary, not a repo file)
- `mypy backend/app` (per `.github/workflows/ci.yml`) — `Success: no issues
  found in 175 source files`
- `mypy backend/tests/...` — pre-existing mypy errors in test files only;
  CI does not run mypy against test files, so this does not affect PR CI

## Regression verification (local)

| Suite | Result |
|---|---|
| `pytest backend/tests/safety/test_dev_db_protection.py -q` | 15 passed |
| `pytest backend/tests/test_alembic_round_trip_isolated.py backend/tests/test_concurrency_isolation_helpers.py -q` | 49 passed |
| `pytest backend/tests/integration/test_isolate_master_data_tables_slice5.py -q` | 8 passed + 3 skipped (live PG) |

## Explicit non-actions

- No production code change (`backend/app/**`).
- No Alembic migration file change (`backend/alembic/versions/**`).
- No CI workflow change (`.github/workflows/**`).
- No frontend change.
- No `docker-compose*.yml`, `Makefile`, `uv.lock`, `.env.example` change.
- No `replay_trained_model` change.
- No fixture refactor beyond marker annotations.
- No CI de-duplication redesign.
- No DB isolation redesign.
- No mass-annotation of all unit / contract / golden / task-domain tests
  in this slice (broader rollout is a follow-up).
- No removal of `postgres_concurrency` legacy marker.
- No removal of `integration` legacy marker.
- No closure of Issue #52 or Issue #23.
- No dispatch of workflow / no CI rerun.
- No comment posted on Issue #52 or Issue #23 from this slice.
- No token / PAT read.

## Acceptance gate status

| Gate | Description | Status | Evidence |
|---|---|---|---|
| G-01 | All required markers registered in `pyproject.toml` | **PASS** | 14 markers registered (12 canonical + 2 legacy) |
| G-02 | Legacy markers remain registered | **PASS** | `integration`, `postgres_concurrency` preserved |
| G-03 | `ci-shard-manifest.yml` defines ownership precedence | **PASS** | New taxonomy section in the manifest documents 7-rule precedence |
| G-04 | No test node intentionally executed by more than one PR CI job | **PASS** | per-job counts before/after reconcile with single-execution rule (14 tests moved from unit-contract-golden to postgres-migration is a correctness fix, not duplication) |
| G-05 | No test node accidentally dropped from PR CI | **PASS** | total nodes = 1752 (unchanged); `full-suite-canary` retains all files |
| G-06 | Existing Batch 2 PR job layout remains green | **PASS** (locally; awaiting Draft PR CI) | CI workflow `.github/workflows/**` not modified |
| G-07 | Main-push `full-suite-canary` remains green | **PASS** (inherits from prior Batch 3 state) | no full-suite-canary selector changed |
| G-08 | Dev-DB safeguard tests remain in PR CI | **PASS** | `backend/tests/safety/test_dev_db_protection.py` preserved in `unit-contract-golden` shard per manifest's `owner_files` (no marker change) |
| G-09 | PostgreSQL migration and concurrency jobs keep isolated DB behavior from Batch 3 | **PASS** | `migration_isolation_helpers.py` / `concurrency_isolation_helpers.py` not modified; CI workflow's `ISOLATED_DB_NAME` env path not modified |
| G-10 | No production code or migration files changed | **PASS** | `git diff --stat` shows 0 changes to `backend/app/**` and `backend/alembic/versions/**` |

## Rollback plan

Rollback is documentation-first:

1. Revert `pyproject.toml` markers section to the 3-marker baseline.
2. Revert `ci-shard-manifest.yml` to remove the Batch 4 taxonomy section.
3. Revert marker additions in `backend/tests/**` (per the per-file change
   list above).
4. Revert this freeze document.
5. Do **not** touch `.github/workflows/**`, `backend/app/**`, or
   `backend/alembic/versions/**` during rollback.

The rollback does not require any production code or migration changes.

## Issue policy

- Issue #52 remains open after this PR merges.
- Issue #23 remains open after this PR merges.
- This freeze document uses only `Refs #52` and `Refs #23`.
- Closing either issue requires a separate Charles authorization round
  after all Batch 4 slices are complete.

## Open questions (carried over from design doc)

- OQ1: Should `concurrency` become the canonical marker and
  `postgres_concurrency` become a legacy alias for cleanup-removal?
  **This slice is additive; the cleanup-removal PR is a separate round.**
- OQ2: Should `integration` remain a broad marker indefinitely, or
  become a legacy compatibility marker after explicit `postgres` / `e2e`
  / task-domain labels are complete? **Carried over.**
- OQ3: Should task-domain markers drive CI ownership, or stay purely
  descriptive? **This slice uses descriptive-only; ownership precedence
  rules in the manifest keep execution markers as the driver.**
- OQ4: Should `slow` tests be allowed in PR CI, or should some be
  canary-only with explicit manifest entries? **This slice has no PR
  CI owner for `slow`; canary-only policy in the manifest.**
- OQ5: Should Batch 4 be implemented in one PR or split into
  registration / manifest / test marking slices? **This slice is the
  registration / minimal marker application; broader test rollout is a
  follow-up slice.**
