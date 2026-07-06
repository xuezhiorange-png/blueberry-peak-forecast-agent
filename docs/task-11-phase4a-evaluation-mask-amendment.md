# TASK-011 Phase 4a — Design Amendment: Evaluation Materialization and Mask Foundation

> **Status:** Design-only. **Not** implementation. **Not** migration. **Not** tests. **Not** production code.
> This document is the design amendment for Phase 4a, proposed per Issue #33 split decision (Option C) and
> detailed in Issue #34. No code change accompanies this PR.

---

## 1. Baseline and governance

- **main SHA**: `455831ffc84e98528a6430df3c65e17b69d80969`
- **PR #30**: MERGED (merge commit `455831ffc84e98528a6430df3c65e17b69d80969`, merged head `0d6ba008e1823a9eea54d65a2ce7731bccde1f93`)
- **Post-merge main CI**: Run `28765452327`, completed / success
- **Issue #21**: OPEN (TASK-011 umbrella)
- **Issue #29**: CLOSED / COMPLETED (stateReason=completed, closedAt=2026-07-06T03:42:11Z)
- **Issue #33**: OPEN (Phase 4 planning; split decision comment `4888970615`)
- **Issue #34**: OPEN (Phase 4a design planning issue)
- **Frozen Authority Base SHA**: `7340ec51865645a2c06b2d2e1e54d24cd457c831`
- **Frozen Amendment Content SHA**: `f2896ae475d4e007fb2e54ad07f294e718d1e171`

> **This document is design-only.** It does not authorize implementation, migration, test code, or production code.
> It does not authorize branch deletion, Issue closure, or any push to main.

---

## 2. Phase 4a scope boundary

### 2.1 In scope

- Evaluation readiness detection.
- Evaluation status state wiring:
  - `not_ready`
  - `pending`
  - `running`
  - `completed`
  - `blocked`
  - `failed`
- Task 3 actual build resolver (consumer only; reads existing Task 3 actual-build authority / materialization).
- `evaluation_available_at` (timestamp).
- `actual_source_cutoff` (per-snapshot, not per-row).
- Internal evaluation materialization service skeleton.
- Evaluation DAG extension:
  - wait for evaluation readiness
  - resolve Task 3 actual build
  - materialize evaluation rows
  - materialize evaluation mask
  - finalize evaluation snapshot
- Evaluation row persistence / reload integrity.
- Evaluation mask persistence / reload integrity.
- Deterministic `evaluation_mask_hash`.
- **Forecast hash immutability** across evaluation materialization.
- Ordered row set parity between structural and corrected paths as **assertion-only** (metric computation deferred to Phase 4b).
- Missing actual handling:
  - `true_zero` only when Task 3 coverage proves complete coverage
  - otherwise `excluded` or `blocked`
- No `current/latest` fallback allowed.
- PostgreSQL integrity tests for evaluation materialization and mask (DESIGN ONLY; no test code in this PR).
- Unit / golden tests for deterministic mask and forecast-hash immutability (DESIGN ONLY).

### 2.2 Out of scope

- Metric formula implementations beyond minimal placeholders needed for mask integrity.
- WMAPE / MAE / cumulative relative error / pinball loss / empirical coverage.
- Peak date error / peak magnitude error / interval width / quantile crossing / correction magnitude distribution.
- Scoped metrics (per-node / per-season / per-factory / per-horizon / per-calendar-phase / per-mode).
- Versioned calendar phase config.
- CLI.
- Deterministic JSON / CSV export.
- Public service layer beyond the internal Phase 4a materialization skeleton.
- Task 12 API / UI.
- Task 13 Agent.
- Task 14 production scheduling / drift monitoring / alerting.
- cron / Celery / Kubernetes scheduling.
- New model code.
- Task 8 / Task 9 / Task 10 semantic changes.
- Task 10 `replay_trained_model` (deferred to a later independent design decision).
- Branch creation (other than this design branch).
- PR creation (other than this design PR).
- Implementation before design amendment review and separate bucket-level authorization.

---

## 3. Evaluation domain model

Evaluation happens after forecast snapshot finalization.

### 3.1 Invariants

1. **Evaluation must not mutate forecast snapshot rows.** The forecast snapshot is the upstream source of truth
   and is preserved verbatim.
2. **Evaluation must not mutate forecast hashes.** The forecast snapshot hash computed at finalization time
   must remain identical before and after any evaluation re-run on the same input.
3. **Evaluation has its own status lifecycle** decoupled from forecast status. Evaluation status is independent
   of forecast status; a successful forecast does not imply successful evaluation.

### 3.2 Evaluation status lifecycle

The evaluation status state machine is:

| From state | To state | Trigger |
|---|---|---|
| (initial) | `not_ready` | Snapshot finalized; required Task 3 actuals not yet available |
| `not_ready` | `pending` | Task 3 actuals become available for at least one node |
| `pending` | `running` | Evaluation DAG starts materialization |
| `running` | `completed` | All evaluation rows materialized; `evaluation_mask_hash` computed; reload integrity verified |
| `running` | `blocked` | Coverage or external dependency blocks materialization |
| `running` | `failed` | Materialization error or invariant violation |
| `failed` / `blocked` | `pending` | Operator / scheduler re-arms evaluation (re-run) |

Allowed statuses: `not_ready` / `pending` / `running` / `completed` / `blocked` / `failed`.

---

## 4. Task 3 actual authority resolver

### 4.1 Design contract

- Phase 4a **consumes** the existing Task 3 actual-build authority / materialization.
- Phase 4a **must not change Task 3 semantics.** No new Task 3 columns, no new Task 3 binding, no Task 3 schema migration.
- The Task 3 actual build snapshot reader is wired as a read-only dependency.

### 4.2 Required inputs

- `evaluation_available_at` — earliest timestamp at which Task 3 actuals are available for the relevant nodes.
- `actual_source_cutoff` — per-snapshot cutoff timestamp (NOT per-row).

### 4.3 Forbidden behavior

- **No `current/latest` fallback.** Any code path that uses `now()` / `datetime.now()` / `datetime.utcnow()` /
  `time.time()` / "latest" / "current" data as a substitute for Task 3 actual authority is a stop condition
  (`CURRENT-DATA-FALLBACK`).
- The actual source must come from the Task 3 actual-build snapshot reader, and only from that reader.

---

## 5. Evaluation materialization contract

### 5.1 Evaluation row identity

- An evaluation row is identified by the tuple: `(forecast_output_id, node_id, evaluation_as_of_date)`.
- `forecast_output_id` is a foreign reference to the immutable forecast output row.
- `node_id` is the per-node dimension (e.g., a factory / processing line).
- `evaluation_as_of_date` is the date the actual value is being compared against.

### 5.2 Relationship to rolling run / attempt / node / forecast output

- Each evaluation row is scoped to exactly one rolling run (or retrospective replay run) and one attempt.
- Each evaluation row points to one forecast output row (which itself points to a forecast snapshot).
- The forecast snapshot is preserved; only the evaluation row is new.

### 5.3 Idempotency and retry behavior

- Evaluation materialization is **idempotent** for a given `(rolling_run_id, attempt, evaluation_as_of_date)` triple.
- A re-run with the same inputs MUST produce the same `evaluation_mask_hash`.
- The idempotency key is composed of the rolling run id, attempt number, and evaluation_as_of_date set.

### 5.4 Reload integrity

- After persistence, evaluation rows must be re-readable with identical content under snapshot isolation.
- Reload integrity is verified by:
  1. Reading back the persisted evaluation rows.
  2. Comparing to the in-memory representation used during materialization.
  3. Verifying the row count and per-row fields match.
- Reload integrity failure is a stop condition (`EVALUATION-HASH-INCONSISTENCY`).

### 5.5 Structural vs corrected alignment

- The structural and corrected forecast paths both produce evaluation rows for the same ordered row set.
- The **ordered row set parity** is verified as an **assertion-only** check during evaluation materialization.
- Metric computation on these rows is **deferred to Phase 4b**; this design does not implement any metric formula.

---

## 6. Evaluation mask contract

### 6.1 Inclusion / exclusion mask

- Each evaluation row has a corresponding mask entry.
- Allowed mask states:
  - `included` — the row is part of the evaluation result.
  - `excluded` — the row is excluded (e.g., actual is missing, coverage incomplete).
  - `blocked` — the row is blocked by an external condition (e.g., upstream dependency failed).
  - `true_zero` — the row's actual value is provably zero (Task 3 coverage is complete and the actual is zero).

### 6.2 Allowed exclusion reasons

- `ACTUAL_MISSING` — Task 3 actual is not present for the relevant node/date.
- `COVERAGE_INCOMPLETE` — Task 3 actual coverage is not provably complete for the relevant node/date.
- `FORECAST_HASH_MISMATCH` — forecast snapshot hash changed since the row was generated (a stop condition, not a routine exclusion).
- `UPSTREAM_BLOCKED` — upstream DAG node failed.

### 6.3 True zero vs excluded vs blocked

- `true_zero` is **only** set when Task 3 coverage is provably complete and the actual value is zero.
- `excluded` is set when actual is missing or coverage is incomplete.
- `blocked` is set when an upstream dependency failed.
- The state machine for these is enforced at materialization time; no post-hoc state changes are allowed.

### 6.4 Deterministic ordering

- The mask ordering is canonical: rows are sorted by `(node_id, evaluation_as_of_date, forecast_output_id)`.
- The same ordering is used for both the structural and corrected paths.

### 6.5 Deterministic `evaluation_mask_hash`

- `evaluation_mask_hash` is computed deterministically from:
  - The canonical ordered list of mask entries.
  - For each entry: `node_id`, `evaluation_as_of_date`, `forecast_output_id`, `mask_state`, `exclusion_reason` (if any).
- The hash is a SHA-256 of the canonical JSON encoding of the ordered list.
- Hash canonicalization rules:
  - All keys sorted alphabetically.
  - All string values UTF-8 encoded.
  - All timestamps in UTC ISO-8601 Z form.
  - All numeric values as strings (no float ambiguity).
  - No trailing whitespace or newlines.

### 6.6 Immutability rules after materialization

- Once `evaluation_mask_hash` is computed and the evaluation snapshot is finalized, the mask is **immutable**.
- No re-run may mutate an existing finalized mask entry; a re-run with the same inputs must produce the same hash.
- If a re-run needs to update a finalized row, the previous snapshot must be deprecated and a new snapshot created.

---

## 7. Persistence and migration assessment

### 7.1 Pre-implementation inspection requirement

Before any implementation work begins on Phase 4a, the implementer must:

1. Inspect the existing schema for any tables that can host evaluation rows, mask, and hash.
2. Inspect the existing Task 3 actual-build materialization tables.
3. Inspect the existing forecast snapshot tables.
4. Document the exact reuse strategy.

### 7.2 Migration policy

- If existing tables are sufficient for evaluation rows, mask, and hash, **no migration is required** for Phase 4a.
- If a new table, column, or index is required, the design amendment must document the exact proposed schema
  (table name, columns, types, constraints, indexes), but **the migration is NOT created in this PR**.
- Any schema gap is a stop condition (`SCHEMA-GAP`) and must be raised to Charles before any migration is created.

### 7.3 Forbidden in this PR

- No Alembic migration file in this PR.
- No SQL DDL in this PR.
- No new binding, Pydantic model, or SQLAlchemy model in this PR.

---

## 8. Stop conditions

Work must halt and return to planning if any of the following are detected:

- **SCHEMA-GAP** — required column / table / index is not in the frozen design contract or existing schema.
- **SCOPE-GAP** — implementation requires Phase 4b, Phase 4c, Task 10 model-policy work, or Task 12+ feature work.
- **BINDING-CONTRACT-GAP** — Pydantic / SQLAlchemy / Alembic binding diverges from the frozen contract.
- **REPLAY-SEMANTIC-GAP** — replay behavior would change under evaluation materialization.
- **CURRENT-DATA-FALLBACK** — any code path uses `now()`, `datetime.now()`, `datetime.utcnow()`, `time.time()`,
  "latest", or "current" data as a substitute for Task 3 actual authority.
- **EVALUATION-HASH-INCONSISTENCY** — `evaluation_mask_hash` differs across reload / re-run for identical inputs.
- **MASK-ROWSET-MISMATCH** — structural and corrected ordered row sets diverge.
- **FORECAST-HASH-MUTATION** — forecast snapshot hash changes after evaluation materialization.
- **ACTUAL-COVERAGE-AMBIGUITY** — Task 3 coverage is neither provably complete nor provably incomplete.
- **METRIC-SCOPE-LEAKAGE** — any metric formula beyond the minimal placeholders for mask integrity is implemented.
- **PHASE-3.1-VIOLATION** — frozen Phase 3.1 invariants are broken.

---

## 9. Proposed implementation buckets

> **🚨 These buckets are proposed, NOT authorized.**
> Each bucket requires explicit Charles authorization before implementation.

- **7.1 Evaluation state / DAG contract** — implement evaluation status enum / state machine; evaluation DAG node set, ordering, and readiness detection input contract.
- **7.2 Task 3 actual authority resolver** — wire Task 3 actual build snapshot reader; derive `evaluation_available_at` and `actual_source_cutoff`.
- **7.3 Evaluation materialization persistence / reload integrity** — persist evaluation rows; assert reload integrity; assert forecast-hash immutability so no forecast row mutates during evaluation materialization.
- **7.4 Evaluation mask persistence + `evaluation_mask_hash`** — persist inclusion / exclusion mask; compute deterministic `evaluation_mask_hash`; verify reload integrity for mask.
- **7.5 Missing actual and true-zero coverage policy** — verify Task 3 coverage; distinguish `true_zero` (coverage complete) from `excluded` / `blocked` (coverage incomplete); prohibit `current/latest` fallback.
- **7.6 Forecast-hash immutability and evaluation retry/idempotency** — define idempotency keys for evaluation materialization; ensure re-run safety; keep `evaluation_mask_hash` stable for identical inputs; guarantee forecast snapshot is untouched by evaluation re-runs.
- **7.7 PostgreSQL integration tests** — round-trip evaluation rows; round-trip mask + `evaluation_mask_hash`; reload integrity; snapshot isolation under concurrent re-run.
- **7.8 Golden tests and governance closeout** — golden fixtures for evaluation rows + mask; forecast-hash immutability golden test; governance closeout comment under the established GitHub governance protocol.

---

## 10. Test strategy (design only)

> This section is a design plan. **No test code is in this PR.**

### 10.1 Unit test plan

- Evaluation status state machine transitions.
- Mask state transitions (`included` / `excluded` / `blocked` / `true_zero`).
- `evaluation_mask_hash` determinism for identical inputs.
- True-zero coverage detection logic.
- Idempotency key generation.

### 10.2 Golden test plan

- Golden output fixtures for evaluation rows + mask per node / per attempt.
- Forecast-hash immutability golden test (forecast hash unchanged after evaluation materialization).
- `evaluation_mask_hash` golden test (regression against known fixture).

### 10.3 PostgreSQL integration test plan

- Round-trip evaluation rows: write, read, compare.
- Round-trip mask + `evaluation_mask_hash`: write, read, hash recompute, compare.
- Reload integrity: read-after-write under snapshot isolation.
- Concurrent re-run: two re-runs with same inputs produce same hash.

### 10.4 Reload integrity test plan

- After materialization, re-read all evaluation rows from PostgreSQL.
- Compare row count and per-row fields against in-memory representation.
- Fail test on any divergence.

### 10.5 Hash immutability test plan

- Compute `evaluation_mask_hash` twice for the same input.
- Assert hash equality.
- Re-run materialization with same inputs.
- Assert hash unchanged.

### 10.6 No-current/latest-fallback test plan

- Grep / static analysis: ensure no `now()` / `datetime.now()` / `datetime.utcnow()` / `time.time()` /
  "latest" / "current" data is used in evaluation materialization code path.
- Test fixture: a "missing actual" scenario where `now()` would naturally be the wrong answer;
  assert the system returns `excluded` / `blocked`, not a current-data value.

---

## 11. Frozen content SHA procedure

After this design-only PR is reviewed and accepted:

1. Compute the design amendment **Content SHA** from the final merged `docs/task-11-phase4a-evaluation-mask-amendment.md`.
2. Record the Content SHA in the design closeout comment and in the next planning issue.
3. **Do not confuse** the design amendment Content SHA with the implementation head SHA.
4. The design amendment Content SHA becomes the **frozen reference** for the next implementation phase.
5. Implementation cannot start until Charles explicitly authorizes it after design review.

---

## 12. Non-authorization statement

> **This document does not authorize implementation.**
> **This PR does not authorize implementation.**
> **This PR does not authorize migrations.**
> **This PR does not authorize test code execution.**
> **This PR does not authorize production code changes.**
> **This PR does not authorize Issue #21 / #29 / #33 / #34 closure.**
> **This PR must remain Draft until Charles explicitly authorizes Ready for review.**

---

## Refs

- **Issue #21** — TASK-011 umbrella, OPEN.
- **Issue #29** — Phase 3.1, CLOSED / COMPLETED.
- **Issue #33** — Phase 4 planning, OPEN; split decision comment `4888970615`.
- **Issue #34** — Phase 4a design planning issue, OPEN.
- **PR #30** — Phase 3.1 implementation, MERGED.
- `docs/TASK_BACKLOG.md`
