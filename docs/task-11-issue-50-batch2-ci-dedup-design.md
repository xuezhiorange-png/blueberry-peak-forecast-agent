# [TASK-011-INFRA][Batch 2] CI de-duplication and PR workflow split — design freeze

**Status**: design-only freeze. No code changes. No CI workflow changes. No production semantics changes.

**Parent**: Issue #23 umbrella. **Sub-issue**: Issue #50 per Batch 2 mapping.

This document is a binding contract for the future Batch 2 implementation PR. It does not authorize implementation. Implementation requires separate Charles authorization.

---

## §1 Purpose

The current PR CI workflow executes the same pytest tests multiple times through overlapping command patterns:

- `pytest -m "not integration"`
- `pytest -m integration`
- full `pytest` or equivalent workflow step

This inflates PR CI runtime and wastes CI minutes. Issue #50 defines the deduplicated PR CI layout for Batch 2.

This PR is design-only. Implementation must happen in a separate Draft PR.

---

## §2 Scope

### 2.1 Goals

- Each pytest test node is executed at most once in the deduplicated PR CI matrix.
- PR CI runtime is reduced versus the current overlapping pattern.
- `full pytest` does not run on PR events; it runs only as canary on main push, nightly schedule, or manual `workflow_dispatch`.
- The dev-DB safeguard from PR #47 / Issue #23 Batch 1 is preserved.

### 2.2 Non-goals

- No production semantic change to TASK-011 evaluation, mask, canonical, hash, key, or audit logic.
- No Alembic schema change.
- No test class additions, modifications, or reclassification.
- No `backend/app/**` modification.
- Database isolation mechanics are deferred to Issue #51 / Batch 3.
- Marker taxonomy overhaul is deferred to Issue #52 / Batch 4.
- Fixture refactor is deferred to Issue #53 / Batch 5.
- CI performance and diagnostics beyond the required split are deferred to Issue #54 / Batch 6.

---

## §3 Target PR CI job layout

| # | Job | Purpose | Events |
|---|-----|---------|--------|
| 1 | `static` | linting, formatting, type-checking, security scanning | `pull_request` |
| 2 | `unit-contract-golden` | pure unit, contract, and golden tests | `pull_request` |
| 3 | `postgres-migration` | Alembic and migration round-trip tests | `pull_request` |
| 4 | `postgres-domain-1` | domain integration tests, slice 1 | `pull_request` |
| 5 | `postgres-domain-2` | domain integration tests, slice 2 | `pull_request` |
| 6 | `postgres-task11` | Task 11 evaluation and mask tests | `pull_request` |
| 7 | `postgres-concurrency` | concurrency and real-commit tests | `pull_request` |
| 8 | `compose-smoke` | Docker Compose smoke test on port 55432 | `pull_request` |
| 9 | `full-suite-canary` | full pytest run | main push, schedule, workflow_dispatch |

### 3.1 Single-execution rule

Each test node across the pytest corpus must be assigned to exactly one PR CI owner job or intentionally excluded from PR CI with documented canary coverage. Overlapping execution in PR CI is forbidden.

Required consequences:

- No PR CI job may run an all-tests sweep that re-includes tests already owned by another PR job.
- No test class may run in two PR jobs.
- Migration tests run only in `postgres-migration`.
- Task 11 evaluation and mask tests run only in `postgres-task11`.

### 3.2 PR CI must not include

- Full-suite pytest sweep on PR events.
- Unscoped `pytest -m integration` on PR events.
- Unscoped `pytest -m "not integration"` on PR events.
- Any pytest invocation that re-runs test nodes already covered by another PR job.

---

## §4 Full-suite canary gating

The `full-suite-canary` job runs only on:

- push to `main`
- nightly schedule
- manual `workflow_dispatch`

The canary must not run on PR-related events.

---

## §5 Marker and shard dependency contract

Batch 2 implementation may introduce only the minimal markers needed for the CI split. Full marker taxonomy remains Batch 4 scope.

The implementation PR must update `ci-shard-manifest.yml` to register which tests each PR job owns. That manifest is the source of truth for single-execution review.

---

## §6 Boundaries vs Batch 3 / 4 / 5 / 6

- Batch 3 / Issue #51 owns PostgreSQL database isolation beyond what is required for CI job ownership.
- Batch 4 / Issue #52 owns full marker taxonomy.
- Batch 5 / Issue #53 owns fixture refactor.
- Batch 6 / Issue #54 owns broader CI performance and diagnostics.

Batch 2 must not implement those sibling scopes.

---

## §7 Production semantics prohibition

Batch 2 design and implementation must not modify:

- `backend/app/rolling_backtest/**` semantics
- TASK-011 mask, canonical, hash, key, and audit behavior
- Alembic migrations
- JSON, CSV, manifest, or audit output semantics introduced by Phase 4c

Any production semantic change requires separate authorization.

---

## §8 Allowed paths and forbidden paths

### 8.1 Allowed paths for future implementation

| Path | Purpose |
|------|---------|
| `.github/workflows/**` | workflow job layout |
| `ci-shard-manifest.yml` | test ownership manifest |
| `backend/pyproject.toml` | minimal pytest marker declarations only, if required |
| `docs/task-11-ci-architecture*.md` | CI architecture documentation |
| `docs/task-11-issue-50-*.md` | Batch 2 documentation and journal |
| `docs/task-11-issue-50-batch2-ci-dedup-design.md` | this design document |

### 8.2 Forbidden paths for future implementation

| Path | Reason |
|------|--------|
| `backend/app/**` | production semantics protection |
| `backend/alembic/versions/**` | migration semantics protection |
| `backend/tests/integration/**` except minimal marker additions | test semantics protection |
| `backend/tests/conftest.py` except minimal marker-only edits | test isolation boundary |
| `backend/scripts/**` | dev-DB safeguard protection |
| `backend/app/rolling_backtest/service.py` | Phase 4c service layer protection |
| `backend/app/rolling_backtest/cli.py` | Phase 4c CLI protection |
| `backend/app/rolling_backtest/export.py` | Phase 4c export protection |

---

## §9 Acceptance gates

| # | Gate | Measurement |
|---|------|-------------|
| G-01 | no triple execution pattern | inspect CI commands and job ownership |
| G-02 | single execution per test node | aggregate node ownership and verify uniqueness |
| G-03 | canary not triggered on PR events | inspect workflow event rules |
| G-04 | PostgreSQL test profile preserved | verify safeguarded Postgres runner usage |
| G-05 | forbidden paths unchanged | compare implementation PR diff |
| G-06 | backward compatibility | existing tests continue to pass |
| G-07 | PR CI runtime reduction | compare baseline and post-change PR CI runtime |
| G-08 | clean artifact upload | JUnit artifacts uploaded per PR CI job |

All gates must pass before any Ready transition of the implementation PR.

---

## §10 Future implementation PR requirements

When Charles authorizes Batch 2 implementation, the implementation PR must:

1. Be opened as Draft with explicit head SHA preserved.
2. Branch from the authorized main base, not from a side branch.
3. Carry forward only `Refs #50` and `Refs #23`. Do not use GitHub automatic issue-transition keywords.
4. Avoid GitHub automatic issue-transition keywords for #50, #47, or #23.
5. Carry a freeze comment at the implementation head before any Ready transition.
6. Implement the 8 PR CI jobs and the single-execution rule.
7. Implement the full-suite canary gating.
8. Update `ci-shard-manifest.yml`.
9. Update README and CI architecture documentation as needed.

The implementation PR must pass all acceptance gates and Charles review before Ready transition.

---

## §11 Rollback and blocker model

Rollback triggers for the future implementation include:

- acceptance gates G-01 through G-04 fail on first post-merge canary
- a test node is observed running more than once across PR CI jobs
- canary fires on a PR event
- dev-DB safeguard from PR #47 / Issue #23 Batch 1 is disabled

Named blocker kinds:

| Blocker kind | Symptom | Recovery action |
|--------------|---------|-----------------|
| `missing_shard_manifest` | `ci-shard-manifest.yml` not updated | add manifest before Ready |
| `marker_conflict` | test class assigned to incompatible scopes | refine marker assignment |
| `dev_db_safeguard_disabled` | safeguarded runner removed | reinstate safeguard usage |
| `pr_ci_runtime_increase` | runtime increased beyond allowed threshold | re-architect job split |
| `full_canary_on_pr_event` | canary fires on PR | correct event rules |
| `single_node_double_run` | test node runs twice | correct shard manifest |

---

## §12 Risk register

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|------------|--------|------------|
| R-01 | existing tests lack required markers | medium | high | add minimal markers or explicit manifest ownership |
| R-02 | artifact upload overhead increases runtime | low | medium | measure runtime gate G-07 |
| R-03 | shard manifest becomes stale | low | medium | require manifest updates with test ownership changes |
| R-04 | canary event rules accidentally include PR events | low | high | gate G-03 review |
| R-05 | migration tests need stronger DB isolation | medium | medium | defer durable isolation mechanics to Batch 3 |

---

## §13 Test catalog placeholder

Future implementation must replace this placeholder with concrete test ownership per job:

- `static`: lint, format, type-check, security checks
- `unit-contract-golden`: pure unit, contract, and golden tests
- `postgres-migration`: Alembic and migration tests
- `postgres-domain-1`: domain integration slice 1
- `postgres-domain-2`: domain integration slice 2
- `postgres-task11`: Task 11 evaluation and mask tests
- `postgres-concurrency`: concurrency and real-commit tests
- `compose-smoke`: Docker Compose smoke validation

---

## §14 Open questions frozen at design stage

- Exact nightly canary cron expression.
- How to shard `unit-contract-golden` if the test corpus grows.
- Whether `compose-smoke` should run in parallel or sequentially.
- Deadline for stale PR workflow cleanup.

These are implementation-stage decisions and require Charles review.

---

## §15 Glossary and references

- **PR CI**: GitHub Actions workflows triggered by PR events.
- **Canary**: full-suite run on main push, schedule, or manual dispatch.
- **Shard**: subset of tests assigned to a specific job.
- **Dev-DB safeguard**: PR #47 / Issue #23 Batch 1 mechanism that prevents test commands from connecting to a non-test database.
- **Production semantics**: TASK-011 evaluation, mask, canonical, hash, key, and audit behavior.

References:

- `docs/task-11-infra-test-environment.md`
- `backend/scripts/postgres_test_db.sh`
- `backend/tests/safety/test_dev_db_protection.py`
- `Makefile`
- `docker-compose.test.yml`

---

## §16 Issue number mapping clarification

This design PR addresses the CI de-duplication and PR workflow split sub-area of Issue #23.

- Issue #50 is the Batch 2 tracking issue.
- PR #47 was the Batch 1 local PostgreSQL test harness implementation and is already merged.
- PR #47 is historical reference context only, not the Batch 2 tracking issue.

This design PR references `Refs #50` and `Refs #23`. PR #47 is mentioned only as historical context in prose.

---

## §17 Definitions

- **Implementation PR**: future Draft PR with concrete CI changes, based on an authorized main base, carrying this design's references and freeze comment.
- **Freeze comment**: comment posted on the implementation PR head commit summarizing the binding contract.
- **Backward compatibility**: existing tests continue to pass; no test class is added, removed, or reclassified except minimal marker ownership needed for the CI split.

---

## §18 Self-audit checklist for implementation PR author

- [ ] Branch is from the authorized main base.
- [ ] Head SHA is recorded in freeze comment.
- [ ] `Refs #50` appears in PR body.
- [ ] `Refs #23` appears in PR body.
- [ ] No GitHub automatic issue-transition keywords for #50, #47, or #23 in PR body or commit messages.
- [ ] Diff stat is limited to allowed Batch 2 implementation paths.
- [ ] No forbidden paths are changed.
- [ ] Acceptance gates all pass.
- [ ] Dev-DB safeguard is preserved.
- [ ] PR is opened as Draft.
- [ ] Charles authorization is received before any Ready transition.

---

This design freeze document was generated under Charles authorization. It is design-only. No implementation was performed. No CI workflow was modified. No production code was modified. Implementation requires separate Charles authorization.
