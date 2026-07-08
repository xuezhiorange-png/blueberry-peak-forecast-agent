# TASK-009A Design Ratification — Deterministic Harvest Capacity and Mature Inventory State

Status: design-only ratification / no implementation mutation  
Base commit: `8de9994af7a3dcc2d4af216449f3c3b0e4a090bc`  
Branch: `codex/task-009a-recreate-design-freeze`

## 1. Purpose

This document freezes the TASK-009A design contract after the TASK-011-INFRA closeout. Earlier audit notes said TASK-009A was absent from `main`, but current `main` contains `backend/app/harvest_state/**`, Task 9A output schemas, service orchestration, persistence, canonical hashing, and tests. Therefore this is **not** a from-zero recreate contract.

The correct governance action is to ratify the already-present Task 9A contract and define the deterministic completion criteria for any follow-up fixes.

## 2. Current repository facts

Current `main` contains these Task 9A / harvest-state surfaces:

- `backend/app/harvest_state/service.py`
- `backend/app/harvest_state/application.py`
- `backend/app/harvest_state/persistence.py`
- `backend/app/harvest_state/capacity.py`
- `backend/app/harvest_state/canonical.py`
- `backend/app/harvest_state/weather.py`
- `backend/app/harvest_state/provenance.py`
- `backend/app/harvest_state/schemas.py`
- `backend/app/models/harvest_state.py`
- `backend/app/repositories/harvest_state.py`
- `backend/tests/harvest_state/**`
- `backend/tests/integration/test_harvest_state_persistence.py`
- `backend/tests/test_harvest_state_alembic.py`

Current implementation already includes:

- Task 9A request normalization and validation.
- Deterministic capacity-pool membership hashing.
- Task 8 source-reference and verification checks.
- Weather efficiency application.
- Holiday and time-zone handling.
- Stable cohort-key generation.
- Mature-inventory opening state, Task 8 cohort injection, harvest allocation, loss allocation, and future-arrival scheduling.
- Canonical output hashing and persistence idempotency checks.
- Load-time integrity checks against canonical payload and normalized child rows.

## 3. Design scope

TASK-009A scope is deterministic state generation and durable persistence for:

1. Harvest capacity state by date, capacity pool, and forecast quantile.
2. Mature inventory state by date, cohort, farm/subfarm/variety, and forecast quantile.
3. Cohort transitions from opening inventory and Task 8 maturity predictions through harvested, carried, loss, and future-arrival states.
4. Arrival schedule after harvest-to-arrival lag and time-zone conversion.
5. Result-hash based idempotent persistence and conflict detection.

## 4. Explicit non-goals

This design does not authorize:

- Alembic schema changes.
- Production API route changes.
- Frontend work.
- TASK-010 residual model work.
- TASK-011 infra changes.
- TASK-012 replay / agent workflow work.
- Randomized test ordering.
- Timing-dependent concurrency assertions.
- Changes to Task 8 natural maturity semantics.

## 5. Domain model

A Task 9A run produces either a completed output or a blocked output.

Completed output must contain:

- non-empty `daily_pool_state_rows`
- non-empty `daily_member_state_rows`
- non-empty `cohort_transition_rows`
- optional `future_arrival_schedule`
- resolved parameter snapshot
- source reference catalog
- mass-balance and continuity result
- canonical `config_hash`
- canonical `result_hash`

Blocked output must contain:

- blockers
- empty pool/member/cohort/future rows
- canonical input snapshot
- canonical `config_hash`
- canonical `result_hash`

## 6. Deterministic capacity state contract

For each forecast date, capacity pool, and quantile:

1. Resolve nominal capacity from one of two modes:
   - `LABOR_DERIVED`: `planned_picker_count * kg_per_person_per_day`
   - `DIRECT_CAPACITY`: `direct_nominal_capacity_kg_per_day`
2. Apply `labor_availability_ratio`.
3. Apply weather harvest-efficiency ratio from the configured deterministic weather rule.
4. Apply `operational_efficiency_ratio`.
5. Apply holiday / calendar metadata as an auditable parameter flag.
6. Produce `resolved_effective_capacity_kg_per_day` using Decimal-only arithmetic and canonical quantization.

The same canonical input must always produce byte-identical canonical output and identical `result_hash`.

## 7. Deterministic mature inventory state contract

For each date and forecast quantile:

1. Opening mature inventory is seeded from initial inventory cohorts.
2. Task 8 maturity predictions create deterministic source-linked cohorts.
3. Cohorts are assigned stable cohort keys derived from source identity, cohort date, farm/subfarm/variety, capacity pool identity, membership hash, and destination factory.
4. Harvest allocation is FIFO against available mature inventory.
5. Remaining mature inventory carries forward deterministically.
6. Loss inputs are allocated deterministically and must not exceed available mature inventory under the chosen allocation contract.
7. Future arrival schedule is generated from harvested cohorts through the harvest-to-arrival lag and timezone conversion contract.

## 8. Persistence and idempotency contract

Persistence must obey these rules:

1. Validate the Task 9A output contract before writing.
2. Recompute and validate `result_hash` from the canonical Task 9A payload before writing.
3. Compute `canonical_payload_hash` from the canonical storage payload.
4. If a run already exists with the same `result_hash` and identical canonical payload, return the existing run idempotently.
5. If a run already exists with the same `result_hash` but different canonical payload or different canonical payload hash, raise a hash-conflict error.
6. During concurrent insertion, only one canonical payload may win for a given `result_hash`.
7. After an integrity error, reload by `result_hash`; if the persisted payload matches, return it idempotently; if it differs, raise a deterministic conflict.
8. Load operations must validate row counts and normalized child rows against the canonical output.

## 9. Historical flake and required test shape

The historical failing test name was:

```text
backend/tests/integration/test_harvest_state_persistence.py::test_concurrent_same_hash_different_payload_conflicts
```

The flaky shape was mixing two separate contracts:

- concurrent idempotent save of the same canonical output;
- conflict behavior for same `result_hash` with different canonical payload.

The deterministic replacement shape must be:

1. `test_concurrent_same_payload_save_creates_one_run`
   - run concurrent saves of the exact same completed output;
   - assert both operations resolve to the same persisted run or equivalent idempotent result;
   - assert exactly one row exists for the `result_hash`;
   - do not assert a timing-dependent winner.

2. `test_existing_same_hash_different_payload_raises_conflict`
   - deterministically insert or persist one payload first;
   - attempt to persist a different canonical payload with the same `result_hash`;
   - assert `HarvestStateHashConflictError`;
   - do not combine the conflict branch with concurrent winner timing.

3. Optional PostgreSQL race regression:
   - if kept, it must branch on the final persisted canonical payload;
   - if original output won, saving the same output again must be idempotent success;
   - if conflicting payload won, saving the original output must raise conflict;
   - the test must never require the conflict payload to win.

## 10. Acceptance gates

A future implementation/fix PR is acceptable only if:

- no Alembic migration files are changed;
- no frontend files are changed;
- no TASK-010/011/012 files are changed except documentation references;
- deterministic unit tests cover canonical output hash stability;
- persistence tests cover idempotent same-output save;
- persistence tests cover same-hash different-payload conflict;
- PostgreSQL integration tests avoid timing-dependent winner assertions;
- load-time integrity checks continue to verify canonical payload hash, row counts, and normalized child rows;
- all PR CI jobs pass;
- post-merge `main` CI passes before any closeout issue mutation.

## 11. Allowed follow-up files

A narrow follow-up fix should be limited to some subset of:

- `backend/tests/integration/test_harvest_state_persistence.py`
- `backend/tests/harvest_state/test_persistence.py`
- `backend/app/harvest_state/persistence.py` only if the deterministic conflict contract cannot be proven by tests alone
- this document, only for clarifying the frozen contract

## 12. Forbidden follow-up files

A TASK-009A fix must not touch:

- `backend/alembic/versions/**`
- `frontend/**`
- `.github/workflows/**`
- `backend/app/residual_model/**`
- `backend/app/agent/**`
- TASK-011 infrastructure docs except references
- dependency lock / constraints files

## 13. Governance

This PR is design-only. It does not implement or fix domain logic. It does not close any issue. It does not authorize Ready transition or merge. Ready transition and merge each require separate Charles authorization.

If implementation remains necessary after review, the next authorized round should be:

```text
TASK009A_DETERMINISTIC_PERSISTENCE_FIX_SLICE
```

with the smallest possible scope: split/replace the flaky persistence test shape first; only change production persistence code if the deterministic tests expose a real contract gap.
