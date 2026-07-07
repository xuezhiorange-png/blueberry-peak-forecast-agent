# [TASK-011-INFRA][Batch 2] CI de-duplication and PR workflow split — design freeze

**Status**: design-only freeze. No code changes. No CI workflow changes. No production semantics changes.

**Parent**: Issue #23 (umbrella). **Sub-issue**: Issue #50 (per spec literal mapping; see §16 for clarity on the PR #47 / Issue #50 mapping).

This document is a **binding contract** for the future Batch 2 implementation PR. It does NOT authorize implementation. Implementation requires separate Charles authorization.

---

## §1 Purpose

The current PR CI workflow executes the same pytest tests multiple times through overlapping command patterns:

- `pytest -m "not integration"`
- `pytest -m integration`
- full `pytest` (or equivalent in workflow step)

For a typical PR, this causes **every non-integration test to run twice** and **every integration test to run at least twice**, plus the full `pytest` call runs all of them a third time. This inflates PR CI runtime and wastes CI minutes.

Issue #50 (Batch 2, the CI de-duplication tracking issue per spec) defines the deduplicated PR CI layout that solves this.

This Batch 2 PR is **design-only**; implementation is a separate Draft PR.

---

## §2 Scope (binding for Batch 2 implementation)

### 2.1 Goals (must achieve)

- Each pytest test node is executed **at most once** in the deduplicated PR CI matrix.
- PR CI runtime is reduced versus the current overlapping pattern.
- `full pytest` (or equivalent all-tests sweep) **does not run on PR** events; it runs only as a canary on `main` push / nightly schedule / manual `workflow_dispatch`.
- The dev-DB safeguard from PR #47 (Issue #23 sub-area 1 / Batch 1) is preserved and respected.

### 2.2 Non-goals (must not change)

- Production semantics — no change to TASK-011 evaluation / mask / canonical / hash / key / audit logic.
- Migration semantics — no Alembic schema changes.
- Test semantics — no test class additions, modifications, or reclassifications.
- Backend code — `backend/app/**` is forbidden to modify.
- Database isolation mechanics — deferred to Issue #51 / Batch 3.
- Marker taxonomy overhaul (beyond what is required for the CI split) — deferred to Issue #52 / Batch 4.
- Fixture refactor — deferred to Issue #53 / Batch 5.
- CI performance & diagnostics beyond what's required for the CI split — deferred to Issue #54 / Batch 6.

---

## §3 Target PR CI job layout (binding)

### 3.1 Required PR CI jobs (8 jobs)

| # | Job | Purpose | Events |
|---|-----|---------|--------|
| 1 | `static` | Linting, formatting, type-checking, security scanning | `pull_request` |
| 2 | `unit-contract-golden` | Pure unit tests, contract tests, golden tests (no DB) | `pull_request` |
| 3 | `postgres-migration` | Alembic / migration round-trip tests | `pull_request` |
| 4 | `postgres-domain-1` | Domain layer integration tests (slice 1) | `pull_request` |
| 5 | `postgres-domain-2` | Domain layer integration tests (slice 2) | `pull_request` |
| 6 | `postgres-task11` | Task 11 evaluation / mask tests | `pull_request` |
| 7 | `postgres-concurrency` | Concurrency / real-commit tests | `pull_request` |
| 8 | `compose-smoke` | Docker Compose smoke test (port 55432 + DB connectivity) | `pull_request` |
| 9 (canary) | `full-suite-canary` | Full pytest run | `push` to main, `schedule` (nightly), `workflow_dispatch` |

### 3.2 Single-execution rule (hard constraint)

Each test node across the entire pytest test suite MUST be executed **at most once** in the deduplicated PR CI matrix. Overlapping execution is explicitly forbidden.

This means:

- No PR CI job may invoke `pytest` with `-m "not integration"` AND another PR CI job invoke `pytest` with full run that re-includes non-integration tests.
- No test class may run in two different jobs in PR CI.
- Migration tests run **only** in `postgres-migration` (not in domain / task11 / concurrency jobs).
- Task 11 evaluation / mask tests run **only** in `postgres-task11`.

### 3.3 What PR CI MUST NOT include

- `pytest` (full sweep)
- `pytest -m integration` (without marker subset)
- `pytest -m "not integration"` (without marker subset)
- Any pytest invocation that re-runs tests already covered by another PR CI job

---

## §4 Full-suite canary gating (binding)

### 4.1 Allowed canary triggers

The `full-suite-canary` job runs **only** on:

- `push` to the `main` branch.
- `schedule` (nightly cron run — exact cron expression to be set by the implementation PR within an allowed window).
- `workflow_dispatch` (manual trigger).

### 4.2 Forbidden canary triggers

The `full-suite-canary` job MUST NOT run on:

- `pull_request` (any branch).
- `pull_request_review`.
- `pull_request_target`.
- Any other PR-related event.

---

## §5 Marker & shard dependency contract

The deduplicated PR CI matrix relies on accurate pytest markers to assign each test class to exactly one CI job. The current marker taxonomy (post-Batch 1 / PR #47) provides only the `postgres` marker.

For Batch 2 implementation:

- The implementation PR MAY introduce minimal additional markers (`unit` / `contract` / `golden` / `migration` / `concurrency` / `e2e` etc.) **only to the extent required** for the CI split.
- Marker taxonomy overhaul (full marker registry, dedicated marker taxonomy PR) is **deferred to Issue #52 / Batch 4**. Batch 2 only adds minimal markers needed for the job split; it must NOT do a full taxonomy pass.
- `ci-shard-manifest.yml` MUST be updated to register which tests each job owns. This is a binding contract for the implementation PR.

---

## §6 Boundaries vs Batch 3 / 4 / 5 / 6

### 6.1 Batch 3 (Issue #51 — PostgreSQL database isolation)

Batch 2 may need transaction vs migration vs concurrency vs concurrency-test class bucket logic (to map isolation requirements to job types). **This is allowed** in Batch 2's allowed paths.

Batch 2 MUST NOT:

- Implement migration-only-isolated schemas.
- Implement serialized-execution orchestration beyond what the CI split requires.
- Modify PR #24's `postgres_transactional` / `postgres_real_commit` classification.

### 6.2 Batch 4 (Issue #52 — marker taxonomy)

Batch 2's allowed marker declarations are minimal, scoped to the CI split. The full marker taxonomy overhaul (canonical marker registry, exclusivity rules, documentation standard) is Batch 4. Any marker naming convention introduced in Batch 2 must be compatible with Batch 4's forthcoming taxonomy.

### 6.3 Batch 5 (Issue #53 — fixture refactor)

Batch 2 does not move or refactor test fixtures. If a fixture needs to be scoped per CI job, the implementation may add a conftest-level decision in `tests/conftest.py`-adjacent areas, but must not refactor existing fixtures.

### 6.4 Batch 6 (Issue #54 — CI performance & diagnostics)

Batch 2 may incidentally enable some diagnostics (e.g. JUnit XML upload per job) as required for CI split. The full diagnostics overhaul (cancellation, durations, random seed, etc.) is Batch 6.

---

## §7 Production semantics prohibition

The Batch 2 design and any future implementation MUST NOT:

- Modify TASK-011 evaluation logic in `backend/app/rolling_backtest/`.
- Modify TASK-011 mask / canonical / hash / key / audit semantics.
- Modify Alembic migrations.
- Modify the JSON / CSV / manifest / audit output format introduced by Phase 4c.

Any change to production semantics will require a separate Issue + PR. Batch 2 is strictly CI structure-only.

---

## §8 Allowed paths / Forbidden paths (binding for implementation)

### 8.1 Allowed paths (Batch 2 implementation can modify)

| Path | Purpose |
|------|---------|
| `.github/workflows/**` | YAML re-definition for the new job layout |
| `ci-shard-manifest.yml` | Manifest registering which tests each job owns |
| `backend/pyproject.toml` | MAY adjust `[tool.pytest.ini_options].markers` IF AND ONLY IF needed for CI split (minimal markers only) |
| `docs/task-11-ci-architecture*.md` | New architecture documentation |
| `docs/task-11-issue-50-*.md` | Implementation journal |
| `docs/task-11-issue-50-batch2-ci-dedup-design.md` | THIS design freeze document (already added in this PR) |

### 8.2 Forbidden paths (Batch 2 implementation MUST NOT modify)

| Path | Reason |
|------|--------|
| `backend/app/**` | Production semantics protection |
| `backend/alembic/versions/**` | Migration semantics protection |
| `backend/tests/integration/**` (other than minimal marker additions) | Test semantics protection |
| `backend/tests/conftest.py` (other than minimal marker-only edits) | Test isolation boundary protection |
| `backend/scripts/**` | Operational scripts (dev-DB safeguard) protection |
| `backend/app/rolling_backtest/service.py` | Phase 4c-1 service-layer implementation protection |
| `backend/app/rolling_backtest/cli.py` | Phase 4c-2 CLI protection |
| `backend/app/rolling_backtest/export.py` | Phase 4c-2 export protection |

These forbidden paths are CI structure changes only — anything else requires separate authorization.

---

## §9 Acceptance gates (implementation must pass all)

| # | Gate | Measurement |
|---|------|-------------|
| G-01 | **No triple execution**: zero PR CI run executes `pytest -m "not integration"` + `pytest -m integration` + `full pytest` simultaneously | Count pytest invocations per CI run; assert count = 1 (or per-job count, but not per-PY-test type triple) |
| G-02 | **Single execution per test node**: each pytest node-id appears at most once across all PR CI jobs | Aggregate `pytest --collect-only` output across jobs; verify uniqueness |
| G-03 | **`full-suite-canary` gating**: `full-suite-canary` job is NOT triggered on `pull_request` events | Inspect workflow YAML after merge; verify `on:` block excludes `pull_request` |
| G-04 | **Postgres-test profile preservation**: `pytest -m postgres` invocations still use the dev-DB safeguard from PR #47 / Issue #23 Batch 1 | Inspect new pytest invocations; verify `postgres_test_db.sh` is invoked |
| G-05 | **Forbidden paths unchanged**: `backend/app/**`, `backend/alembic/versions/**`, production semantics all preserved | `git diff` against the implementation PR head; forbidden paths have zero changes |
| G-06 | **Backward compatibility**: existing test classes continue to run (no test dropout) | Run existing pytest suite once after merge; compare pass count vs pre-Batch-2 baseline |
| G-07 | **CI runtime reduction**: PR CI median runtime reduces vs current PR CI baseline | Compare median CI time before/after for similar-size PRs |
| G-08 | **Clean artifact upload**: each PR CI job uploads its JUnit XML even on failure | Inspect CI workflow YAML for `actions/upload-artifact` per job |

---

## §10 Future implementation PR requirements

When Charles authorizes Batch 2 implementation, the implementation PR must:

1. Be opened as **Draft** with explicit head SHA preserved.
2. Branch from the post-#66-merge main, not from any side branch.
3. Carry forward `Refs #50` (and  for actual mapping) and `Refs #23`.
4. NOT use `auto-closes #50`, `auto-closes #47`, `addresses #23`, `addresses #47`, `addresses #23`, or `addresses #47`.
5. Carry a freeze comment at the implementation head before any Ready transition.
6. Implement the 8 jobs (§3.1) and the single-execution rule (§3.2).
7. Implement the full-suite canary gating (§4).
8. Update `ci-shard-manifest.yml` (§5).
9. Update `README.md` and `docs/task-11-ci-architecture*.md` to reflect the new CI matrix.

The implementation PR must pass all acceptance gates (§9) and Charles's separate review before Ready transition.

---

## §11 Rollback / blocker model

### 11.1 Rollback triggers (any of these → revert the implementation PR)

- G-01 through G-04 fails on the first full-suite-canary run after merge.
- A test class is observed running more than once across PR CI jobs.
- The `full-suite-canary` job is observed firing on `pull_request` events.
- The dev-DB safeguard from PR #47 / Issue #23 Batch 1 is observed disabled.

### 11.2 Named blocker kinds (defer Ready transition)

| Blocker kind | Symptom | Recovery action |
|--------------|---------|-----------------|
| `missing_shard_manifest` | `ci-shard-manifest.yml` not updated | Implementation PR adds manifest before Ready |
| `marker_conflict` | A test class is double-marked across Batch 2 and Batch 4 scopes | Implementation PR refines marker assignments |
| `dev_db_safeguard_disabled` | `postgres_test_db.sh` invocation removed | Implementation PR reinvokes safeguard |
| `pr_ci_runtime_increase` | Median runtime increased > 5% vs baseline | Implementation PR re-architects job split |
| `full_canary_on_pr_event` | Canary fires on PR | Implementation PR fixes `on:` block |
| `single_node_double_run` | A test node runs twice in PR CI | Implementation PR fixes shard manifest |

### 11.3 Acceptance of revert by Charles

In the event of any rollback trigger, the implementation PR is reverted via `git revert` (not closed) and a new tracking issue is opened to address the underlying cause.

---

## §12 Risk register

| # | Risk | Likelihood | Impact | Mitigation | Owner |
|---|------|------------|--------|------------|-------|
| R-01 | Existing test classes lack required markers | Medium | High | Implementation PR either adds markers OR shards via conftest-level logic | Implementation PR author |
| R-02 | CI runtime inadvertently increases due to artifact upload overhead | Low | Medium | G-07 measures runtime; canary compares before/after | Batch 2 implementation |
| R-03 | `ci-shard-manifest.yml` becomes stale relative to new tests | Low | Low | Mention test-class-to-job mapping at each test (best-effort) | Test author discipline |
| R-04 | Canary-spawn-jobs accidentally fire on forks | Low | High | Verify `if: github.event_name == 'push' && github.ref == 'refs/heads/main'` | Implementation PR author |
| R-05 | Migration tests fail in matrix-split due to per-job isolated DB schema | Medium | Medium | Each job uses its own test DB schema; CI composition via separate `compose-smoke` Postgres instance | Implementation PR author |

---

## §13 Test catalog (placeholder for implementation)

The implementation PR must populate this section with concrete test names per job target. Below is the placeholder structure:

### Job 1 — `static`

- Backend lint (Ruff)
- Frontend lint (Ruff)
- Type check (Mypy on `backend/app/`)
- Format check (Ruff format --check)
- Security scan (if applicable)

### Job 2 — `unit-contract-golden`

- `tests/backend/test_<unit_only>`
- `tests/backend/test_<contract>`
- `tests/backend/test_<golden>`

### Job 3 — `postgres-migration`

- `tests/backend/migrations/test_<alembic_up>`
- `tests/backend/migrations/test_<alembic_down>`

### Job 4 — `postgres-domain-1`

- `tests/backend/integration/test_domain_<slice_1>` (no concurrency, no real-commit)

### Job 5 — `postgres-domain-2`

- `tests/backend/integration/test_domain_<slice_2>`

### Job 6 — `postgres-task11`

- `tests/backend/integration/test_task11_<evaluation>`
- `tests/backend/integration/test_task11_<mask>`

### Job 7 — `postgres-concurrency`

- `tests/backend/integration/test_<concurrency>`
- `tests/backend/integration/test_<real_commit>`

### Job 8 — `compose-smoke`

- DB health check (`pg_isready`)
- Smoke test of port 55432 / db `blueberry_peak_test`

(These are PLACEHOLDERS; the actual test names are filled in by the implementation PR based on the existing pytest test corpus.)

---

## §14 Open questions (frozen at design stage)

These will be resolved at the implementation PR stage:

1. **Q-A**: Exact cron expression for nightly canary. Options: `0 2 * * *` (daily 2am UTC), `0 2 * * 0` (weekly Sunday 2am UTC), or manual-only (no cron). Implementation PR author chooses; Charles reviews.
2. **Q-B**: How to shard `unit-contract-golden` if test corpus grows large. Implementation may introduce `pytest -k <pattern>` filters; Charles reviews at implementation.
3. **Q-C**: Whether `compose-smoke` should run in parallel with other jobs or sequentially. Implementation PR author chooses.
4. **Q-D**: What is the exact deadline for the canary's "stale PR workflow" cleanup. Implementation PR author handles.

---

## §15 Glossary & references

- **PR CI**: GitHub Actions workflows triggered by `pull_request` events.
- **Canary**: A targeted job that runs the full pytest test suite on `main` push / nightly / manual `workflow_dispatch`.
- **Shard**: A subset of tests assigned to a specific job.
- **Dev-DB safeguard**: The PR #47 / Issue #23 Batch 1 mechanism that prevents `make test-pg` / `pytest -m postgres` from connecting to a non-test database.
- **Production semantics**: Behavior of TASK-011 evaluation, mask, canonical, hash, key, audit in `backend/app/rolling_backtest/` — protected from modification.

References:

- `docs/task-11-infra-test-environment.md` (Issue #23 Batch 1 / PR #47)
- `backend/scripts/postgres_test_db.sh` (dev-DB safeguard from PR #47)
- `backend/tests/safety/test_dev_db_protection.py` (Batch 1 safety tests)
- `Makefile` (one-command contract from PR #47)
- `docker-compose.test.yml` (test profile from PR #47)

---

## §16 Issue number mapping clarification (admin)

This design PR addresses the **CI de-duplication and PR workflow split** sub-area of Issue #23.

- **Issue #50** is the Batch 2 tracking issue (per spec).
- **PR #47** was the Batch 1 (Local PostgreSQL one-command test environment) implementation and is already merged (merge commit `41425234ad0664d678594473e792d4b909e44818`).
- **PR #47** is reference context only, not the Batch 2 tracking issue.

This design PR references `Refs #50` (the Batch 2 tracking issue) and `Refs #23` (the umbrella). PR #47 is mentioned as historical context within the design document body text only, and is not used as a `Refs #` keyword in the PR body.

---

## §17 Definitions (binding)

- **Implementation PR**: A future PR with concrete code changes, opened as Draft, based on the post-#66-merge main, carrying this design's `Refs #` and freeze comment.
- **Freeze comment**: A comment posted on the implementation PR head commit, summarizing the binding contract that the implementation honors.
- **Backward compatibility**: Existing tests continue to pass after the implementation PR is merged. No test class is added, removed, or reclassified.

---

## §18 Self-audit checklist (for the implementation PR author)

- [ ] Branch is from post-#66-merge main.
- [ ] Head SHA recorded in freeze comment.
- [ ] `Refs #50` (and  per actual GitHub mapping) in PR body.
- [ ] `Refs #23` in PR body.
- [ ] NO `auto-closes #50` / `auto-closes #47` / `auto-closes #23` in PR body.
- [ ] NO `addresses #50` / `addresses #47` / `addresses #23` in PR body.
- [ ] NO `addresses #50` / `addresses #47` / `addresses #23` in PR body.
- [ ] Diff stat: only changes in `.github/workflows/**`, `ci-shard-manifest.yml`, `backend/pyproject.toml` (markers only), `docs/**`.
- [ ] No changes in forbidden paths (§8.2).
- [ ] Acceptance gates (§9) all PASS.
- [ ] Dev-DB safeguard (§1 / §6 / §11.1) preserved.
- [ ] PR opened as Draft.
- [ ] Charles's separate authorization received before any Ready transition.

---

🤖 This design freeze document was generated by the bot following Charles's explicit authorization. It is a design-only freeze. No implementation was performed. No CI workflow was modified. No production code was modified. Implementation requires separate Charles authorization per the §10 future implementation PR requirements.
