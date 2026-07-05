# Task 11 Phase 3.0 — Replay Metadata Schema Gap

Refs: #29 (Phase 3 umbrella), #21 (Task 11 umbrella)

## Status

**Phase:** 3.0 (schema prerequisite only)
**Phase 3 business implementation:** **PAUSED** in this PR
**Branch:** `codex/task-11-phase3-schema-gap`
**Base:** `main` @ `67a595704b8582d9c62ca6d876a5fd8249e5767c`
**Frozen Contract Authority SHA (Phase 3 design):** **NOT ESTABLISHED**
(design contract remains in PR #30; Phase 3.0 is a separate prerequisite tracked here)
**Phase 3.0 schema-gap PR Frozen Authority SHA:** **NOT ESTABLISHED** in this document;
the SHA is the merge commit of the PR carrying this migration, set at merge time.

## Why this PR exists

During Phase 3 reconnaissance (documented in PR #30 review thread), the following
**real DDL gap** was found on `harvest_state_run`:

| Field | Required for Phase 3 | Currently present? |
|---|---|---|
| `forecast_effective_cutoff_at` | replay-cutoff proof for integrity reload | **NO** |
| `replay_executed_at` | physical moment of replay (independent of row update) | **NO** |
| `replay_code_version` | replay runtime identity hash | **NO** |
| `is_replay` | discriminator `historical_observed=false` row marker | **NO** |
| `source_visibility_audit` (support table FK) | per-cutoff-visible-source audit chain | **NO** |

Each field was probed via `rg` and `git grep` against `backend/` and confirmed absent
on **2026-07-05** during Phase 3 design reconnaissance.

### Why existing JSONB fields (`input_snapshot`, `source_ref_catalog`) are insufficient

These three reasons make `input_snapshot`/`source_ref_catalog` unsuitable
for replay-metadata persistence:

1. **Query-by-mode is not possible.** A reviewer asking "list all Phase 3 replay
   runs" cannot filter via `WHERE input_snapshot->>'is_replay' = 'true'` reliably:
   - the JSONB is the *content payload*, not the *row discriminator*;
   - partial-index support for JSONB key existence requires GIN indexes that
     would slow every write;
   - PG `CHECK` constraints do not validate JSONB key/value semantics.
2. **Integrity reload requires SQL primitives.** Fresh-session reload proves
   the replay ran at the claimed `forecast_effective_cutoff_at`; this requires
   a typed column for `CHECK (replay_executed_at <= created_at + interval)` and
   `CHECK (forecast_effective_cutoff_at <= NOW())`. JSONB cannot satisfy these.
3. **`source_ref_catalog` is a hash-keyed snapshot of inputs, not an audit of
   cutoff-visibility decisions.** It records *what references were passed in*;
   it does not record *which of those references were cutoff-visible at the
   replay decision time*. Phase 3 requires the second; this needs a typed
   one-to-many audit table with its own FK and CHECK constraints.

### Why this is Phase 3 **prerequisite**, not Phase 3 implementation

Phase 3 (PR #30) is the design contract for the runtime replay dispatcher,
Task 9 replay authority creation, and Task 10 binding. **None of those can
begin implementation** until `harvest_state_run` has typed replay columns:
without `is_replay`, the dispatcher cannot label a replay-produced `harvest_state_run`;
without `forecast_effective_cutoff_at`, the integrity reload cannot prove the
replay ran at the right historical cutoff; without `replay_code_version`, two
distinct reinstalls producing the same `result_hash` are indistinguishable.

**This PR is therefore a schema prerequisite, not a contract freeze.** It is
fully additive — it does not populate these columns from any runtime, does
not add new logic, and does not modify `historical_observed` behavior.

## Scope (allowed)

Allowed in this PR:

1. **Migration `0015_task11_phase3_schema_gap`** adding:
   - 5 typed columns on `harvest_state_run` (all NULLABLE; existing rows
     remain valid; CHECK constraints only on non-NULL values).
     `replay_executed_at` deliberately carries NO server-side default —
     replay-only metadata must be written explicitly by the Phase 3
     business writer so that non-replay (historical_observed) rows are
     never silently auto-populated;
   - 1 new support table `harvest_state_replay_source_visibility_audit`
     (FK to `harvest_state_run.id`, NULLABLE `harvest_state_run_id`,
     enabling append-only audit of cutoff-visible sources);
   - 1 partial index supporting the `is_replay` discriminator;
   - corresponding `downgrade()` block.

2. **ORM update** adding:
   - 5 typed attributes on `HarvestStateRun` (all nullable);
   - `HarvestStateReplaySourceVisibilityAuditModel` class declaration.

3. **Test updates**:
   - add `harvest_state_replay_source_visibility_audit` to the
     integration truncate set in `backend/tests/integration/conftest.py`;
   - add an alembic round-trip test (`test_alembic_phase3_schema_gap.py`);
   - add constraints check `id ≤ 63` for the new support table;
   - add column-presence-positive tests on the `HarvestStateRun` ORM model;
   - add a "historical_observed still works" PG integration test that loads
     an existing completed `harvest_state_run` and confirms the new columns
     are NULL without affecting the load.

4. **Documentation**:
   - this design contract document.

## Explicit non-scope (forbidden in this PR)

- ❌ No `retrospective_replay` runner / dispatcher implementation.
- ❌ No call into `run_harvest_state_model` / `execute_harvest_state_run`
  from any new code path.
- ❌ No Task 10 replay binding (no residual_model changes).
- ❌ No evaluation / metrics / exports / CLI / API / frontend.
- ❌ No Task 12 / Task 13 surface.
- ❌ No production scheduling / drift monitoring / alerting.
- ❌ No new Task 8 / Task 9 / Task 10 business semantics.
- ❌ No CWD loosening of cutoff visibility / ambiguity blockers / authority-chain.
- ❌ No `READY_FOR_REVIEW` or `MERGE` on this PR.
- ❌ No closure of Issue #21 / #29.
- ❌ No new branch of work in PR #30 (which remains Draft / phase-3 business-paused).

## Schema gap as a 1-row decision table

| # | Decision | Choice | Rationale | Schema delta |
|---|---|---|---|---|
| 1 | replay discriminator | typed BOOLEAN column `is_replay` on `harvest_state_run` | SQL-native; check-friendly; indexable | +1 NULLABLE BOOLEAN |
| 2 | replay cutoff proof | typed `TIMESTAMPTZ` column `forecast_effective_cutoff_at` | matches existing `forecast_cutoff_at` shape | +1 NULLABLE TIMESTAMPTZ |
| 3 | replay execution moment | typed `TIMESTAMPTZ` column `replay_executed_at`, **NO server-side default** | independent of row `updated_at` lifecycle; explicit-write-only | +1 NULLABLE TIMESTAMPTZ |
| 4 | replay runtime identity | `TEXT` column `replay_code_version`, nullable | allows NULL until Phase 3 populates it | +1 NULLABLE TEXT |
| 5 | cutoff-visible-source audit | support table `harvest_state_replay_source_visibility_audit` (1-N to `harvest_state_run`) | JSONB not query/query-by-mode friendly | +1 table; +1 NULL FK; +9 typed cols |

## Constraint semantics explained

| Constraint | Column | Semantics |
|---|---|---|
| `is_replay IS NULL OR is_replay IN (FALSE, TRUE)` | `is_replay` | boolean domain |
| `forecast_effective_cutoff_at IS NULL OR (forecast_effective_cutoff_at <= now() + interval '1 hour')` | `forecast_effective_cutoff_at` | historical cutoff already passed; small clock-skew tolerance |
| `replay_executed_at IS NULL OR replay_executed_at <= now() + interval '1 hour'` | `replay_executed_at` | moment cannot be in the future |
| `ck_harvest_state_run_replay_metadata_coupling`<br/>`((is_replay IS NULL OR is_replay = FALSE) AND forecast_effective_cutoff_at IS NULL AND replay_executed_at IS NULL AND replay_code_version IS NULL AND replay_run_correlation_id IS NULL) OR (is_replay = TRUE AND forecast_effective_cutoff_at IS NOT NULL AND replay_executed_at IS NOT NULL AND replay_code_version IS NOT NULL AND replay_run_correlation_id IS NOT NULL)` | composite | strict replay-vs-historical_observed partition: historical_observed rows MUST carry NO replay metadata; replay rows MUST carry ALL four replay-metadata fields |

Constraint coupling invariants (replay-only fields must agree with the
discriminator): enforced via a single PG `CHECK` constraint
(`ck_harvest_state_run_replay_metadata_coupling`) on the same table —
single source of truth, not application-layer cross-checks. `replay_executed_at`
has no server-side default so non-replay rows cannot be silently auto-populated;
the CHECK rejects the only way a non-replay row could carry a timestamp
(otherwise, `replay_executed_at` defaults to `now()` and the composite
constraint would auto-pass).

## Replay source visibility audit schema

```text
harvest_state_replay_source_visibility_audit
├─ id BIGINT PK
├─ harvest_state_run_id BIGINT FK→harvest_state_run.id (NULL when run gone)
├─ source_role TEXT NOT NULL
├─ source_type TEXT NOT NULL
├─ source_visibility_source TEXT NOT NULL
├─ forecast_cutoff_at TIMESTAMPTZ NOT NULL
├─ visibility_passed BOOLEAN NOT NULL
├─ rejection_blocker_code TEXT NULL
├─ semantic_identity_hash TEXT CHECK ~ '^[0-9a-f]{64}$'
├─ captured_at TIMESTAMPTZ NOT NULL DEFAULT now()
```

Indexes:
- `ix_hsrpsva_harvest_state_run_id` on `harvest_state_run_id`
- `ix_hsrpsva_source_role` on `source_role`

## Phase 3.0 deliverable checklist

- [ ] `0015_task11_phase3_schema_gap.py` authored
- [ ] `0015_task11_phase3_schema_gap.py` registered in alembic chain
  via `down_revision = "0014_task9_historical_authority"`
- [ ] `HarvestStateRun` ORM gained 5 nullable columns
- [ ] `HarvestStateReplaySourceVisibilityAuditModel` declared
- [ ] Integration conftest master-data list includes new table
- [ ] Alembic round-trip test (`upgrade` / `downgrade`) added
- [ ] ORM column-presence test added
- [ ] PG constraint check (`len(name) <= 63`) added for new table
- [ ] historical_observed compatibility test added
- [ ] Fresh-session reload test added
- [ ] All Ruff / Mypy / Unit / PG gates green
- [ ] `LOCAL_HEAD == REMOTE_HEAD` verified
- [ ] Draft PR opened (NOT Ready; NOT merged)

## Phase Approval Readiness (per TASK-XXX pattern)

| Phase | Status | Rationale |
|---|---|---|
| Phase 2 | DONE | merged to main as PR #28 @ `67a595704b8582d9c62ca6d876a5fd8249e5767c` |
| Phase 3.0 (this PR) | DRAFT | schema-gap additive only, no business logic |
| Phase 3.1 (business) | NOT STARTED | paused; waits on Phase 3.0 merge + frozen design contract |

## Provenance / governance chain — untouched

- `Issue #21` (Task 11 umbrella): OPEN, untouched.
- `Issue #29` (Phase 3 umbrella): OPEN, untouched.
- `PR #28` (Phase 2 historical_resolution): MERGED at `67a5957f`, untouched.
- `PR #30` (Phase 3 design): OPEN / Draft / head `ed7c2a7f`, untouched.
- `Issue #27`: CLOSED / completed (Phase 2 closeout).
- TASK-XXX prior rows in `docs/TASK_BACKLOG.md`: read-only here.

## Final State (this PR — to be filled at close)

- code changed: NO (purely additive DDL + ORM, no behavioural change)
- tests changed: YES (new alembic round-trip + column-presence + constraint tests)
- migration: YES (`0015_task11_phase3_schema_gap`, additive)
- commit: pending
- push: pending
- LOCAL_HEAD == REMOTE_HEAD: pending verification after push
