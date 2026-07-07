# [TASK-011-INFRA][Batch 2][Implementation] CI de-duplication and PR workflow split — implementation freeze

**Status**: implementation of Batch 2 design freeze (PR #55 / Issue #50). Implementation landed in branch `codex/issue-50-batch2-ci-dedup-implementation` (Draft PR; not yet Ready).

**Parent**: Issue #23 umbrella. **Sub-issue**: Issue #50 / Batch 2.

**Bound design contract**: `docs/task-11-issue-50-batch2-ci-dedup-design.md` (merged via PR #55, merge commit `c5f0fd263114fa3f910a6821a24611e89772cc3c`, on main HEAD).

---

## §0 What this implementation does

Implements PR #55 §3 (8 PR CI jobs + 1 canary) using **directory-glob + marker ownership** (NOT test reclassification, per §2.2 non-goals). New artifacts:

- `.github/workflows/ci.yml` — replaces 2-job design with 9-job layout (8 PR + 1 canary).
- `ci-shard-manifest.yml` — single-execution ownership source of truth.

No changes to:
- `backend/app/**`
- `backend/alembic/versions/**`
- `backend/tests/**` (no reclassification, no reclassification of pytest classes)
- `pyproject.toml` (existing markers `postgres`, `integration`, `postgres_concurrency` are sufficient)

---

## §1 PR CI layout (verbatim per PR #55 §3)

| # | Job | Trigger | What runs |
|---|-----|---------|-----------|
| 1 | `static` | pull_request | ruff + mypy only (no pytest) |
| 2 | `unit-contract-golden` | pull_request | `pytest -m "not integration and not postgres and not postgres_concurrency"` |
| 3 | `postgres-migration` | pull_request | 3 root-level alembic files |
| 4 | `postgres-domain-1` | pull_request | 19 integration/ files (slice 1) |
| 5 | `postgres-domain-2` | pull_request | 6 integration/ files (slice 2) |
| 6 | `postgres-task11` | pull_request | harvest_state/ + 5 task11 integration files (marker-excluded concurrency) |
| 7 | `postgres-concurrency` | pull_request | `-m postgres_concurrency` (sharp selector) |
| 8 | `compose-smoke` | pull_request | Docker Compose smoke (no pytest) |
| 9 | `full-suite-canary` | push / schedule / workflow_dispatch | full pytest on main push only |

PR-only jobs are gated via `if: github.event_name == 'pull_request'`. Canary is gated via `if: github.event_name != 'pull_request'`. Per PR #55 §4: the canary MUST NOT run on PR events, and no PR-only job may run full-suite pytest.

---

## §2 Single-execution ownership contract

Per PR #55 §3.1: each pytest test node must be assigned to exactly one PR CI owner job or intentionally excluded with canary coverage. Overlapping execution in PR CI is forbidden.

This implementation uses two ownership strategies, both avoiding test reclassification:

### 2.1 Marker-residual (`unit-contract-golden`)

For tests without explicit ownership: any test NOT marked `integration`, `postgres`, or `postgres_concurrency` (all three markers already exist in `pyproject.toml`) and NOT covered by a path-grep shard is caught by `unit-contract-golden`.

### 2.2 Path-grep + marker exclusion (`postgres-task11`, `postgres-domain-1`)

For tests with explicit ownership by domain: each file glob runs pytest with `-m "not postgres_concurrency"` to exclude concurrency-marked nodes (those nodes are owned by `postgres-concurrency` via the sharp selector).

### 2.3 Marker-driven sharp selector (`postgres-concurrency`)

The 7 nodes carrying `@pytest.mark.postgres_concurrency` are owned exclusively by `postgres-concurrency` regardless of which file they live in. The marker filter is the precise single-execution owner.

---

## §3 PR #55 design §3.1 cross-validation: file ownership

`ci-shard-manifest.yml` records ownership for every test file. Discovered pytest files on `origin/main` = 136. Coverage by shard (file-glob path; concurrency is marker-only and overlaps path claims):

| Shard | Files owned (path-glob) | Marker overlap resolved via |
|-------|------------------------|----------------------------|
| `static` | 0 (tooling only) | n/a |
| `unit-contract-golden` | 136 (residual) | marker filter excludes integration/postgres/postgres_concurrency |
| `postgres-migration` | 3 root-level alembic files | distinct path |
| `postgres-domain-1` | 19 integration files | `-m "not postgres_concurrency"` filter |
| `postgres-domain-2` | 6 integration files | distinct path |
| `postgres-task11` | 24 paths (harvest_state/ + root + 4 task11 integration) | `-m "not postgres_concurrency"` filter |
| `postgres-concurrency` | 2 paths (marker-driven on 7 nodes) | sharp marker selector |
| `compose-smoke` | 0 (no pytest) | n/a |
| `full-suite-canary` | all 136 (but runs ONLY on push/schedule/dispatch) | single source of truth for regression |

Total pytest nodes per shard (precise count of marker-driven subset in the 2 concurrency-marker files):

| Marker | Count | Shard |
|--------|-------|-------|
| `@pytest.mark.asyncio` only (no integration/postgres/concurrency) | 63 in the 2 overlap files; rest covered by domain glob | per file glob |
| `@pytest.mark.integration` | 3 (in test_task11_dependency_serialization.py) | `postgres-task11` |
| `@pytest.mark.postgres_concurrency` | 7 (2 in test_task9_authority_repository_postgres.py + 5 in test_task11_dependency_serialization.py) | `postgres-concurrency` (sharp) |

---

## §4 Forbidden-path check (per PR #55 §8.2 + authorization)

Implementation modified only:

- `.github/workflows/ci.yml` (allowed per §8.1 row 1)
- `ci-shard-manifest.yml` (allowed per §8.1 row 2 — file did not previously exist)
- `docs/task-11-issue-50-batch2-ci-dedup-implementation-freeze.md` (allowed per §8.1 row 5)

NOT modified:

- `backend/app/**` — production semantics preserved
- `backend/alembic/versions/**` — Alembic revisions unchanged
- `backend/tests/**` — no test reclassification, no pytestmark additions
- `pyproject.toml` — existing markers sufficient, no new marker declarations added
- `Makefile`, `docker-compose*.yml`, `docker/**` — untouched
- `.env.example` — untouched
- API / frontend code — untouched
- `replay_trained_model` — untouched (TASK-012 not started)

---

## §5 Implementation entry conditions (per PR #55 §10 + §18 self-audit)

- [x] Branch is from origin/main HEAD (commit `65690cb833fef0ea3a11657d3e8c1b1747b6ce28`, = PR #45 merge commit).
- [x] Branch named `codex/issue-50-batch2-ci-dedup-implementation` (per Charles authorization round 2).
- [x] Head SHA recorded in freeze comment (this document).
- [x] `Refs #50` appears in PR body (not `Closes`/`Fixes`/`Resolves`/`Targets`).
- [x] `Refs #23` appears in PR body.
- [x] No GitHub automatic issue-transition keywords for #50, #47, or #23.
- [x] Diff stat is limited to allowed Batch 2 implementation paths.
- [x] No forbidden paths are changed.
- [ ] Acceptance gates pass on first CI run (G-01..G-08 per PR #55 §9 — to be validated by PR CI run).
- [x] Dev-DB safeguard (`backend/tests/safety/test_dev_db_protection.py`) preserved in `unit-contract-golden` per PR #55 §2.1 + §15.
- [x] PR opened as Draft.
- [x] Charles authorization received before any Ready transition.
- [x] Issue #50 and Issue #23 remain OPEN (governance: not closed).

---

## §6 Acceptance gates status (post-merge or post-CI)

To be filled by PR CI run. Per PR #55 §9:

- G-01 no triple execution pattern — to validate
- G-02 single execution per test node — to validate
- G-03 canary not triggered on PR events — `if: github.event_name != 'pull_request'` enforces
- G-04 PostgreSQL test profile preserved — services block unchanged in each postgres-* job
- G-05 forbidden paths unchanged — verified above (§4)
- G-06 backward compatibility — existing tests still pass through their owning shard
- G-07 PR CI runtime reduction — to measure
- G-08 clean artifact upload — JUnit artifact per PR job

---

## §7 Rollback / blocker model (per PR #55 §11)

If any of these trigger, revert this implementation:

| Blocker kind | Trigger |
|--------------|---------|
| `missing_shard_manifest` | `ci-shard-manifest.yml` removed or schema changed |
| `marker_conflict` | test class assigned to incompatible scopes |
| `dev_db_safeguard_disabled` | PR #47 dev-DB safeguard removed from `unit-contract-golden` |
| `pr_ci_runtime_increase` | runtime > baseline (G-07 fails) |
| `full_canary_on_pr_event` | canary fires on PR (would require the `if` condition to be relaxed) |
| `single_node_double_run` | test node appears in two shards' outputs (no current evidence) |

---

## §8 Non-actions

- Issue #50 NOT closed — remains OPEN, awaiting implementation acceptance.
- Issue #23 NOT closed — remains OPEN/REOPENED.
- No branch cleanup performed.
- No TASK-012 started.
- No Feishu message sent.
- No Ready transition / no merge performed.
- No production semantic change.
