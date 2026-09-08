# S4 validation-budget durable persistence implementation R1

TASK_ID=V0_3_S4_VALIDATION_BUDGET_DURABLE_PERSISTENCE_IMPLEMENTATION_R1
SOURCE_CONTRACT_PR=588
SOURCE_CONTRACT_MERGE_SHA=4953f68182b08f5e10d9e6235bb191cbb1c08ec4
SOURCE_CONTRACT_REVISION=R3
SOURCE_CONTRACT_HASH=a7c7c5eac5550f531836968b5001bfd487218960f31e56ad5a1c5c175169410f
IMPLEMENTATION_STATUS=IMPLEMENTED_PENDING_REVIEW

## Scope

This change implements the persistence primitive frozen by the merged R3
contract. PostgreSQL is the canonical validation-budget authority. The new
repository is deliberately separate from the existing candidate execution
adapter, and no candidate runner is connected to it in this task.

The implementation adds one singleton authority row and one append-only event
ledger. The migration bootstraps the empty canonical ledger with the frozen
legacy debit of four, without creating four fabricated historical events.

## Durable state

```text
AUTHORITY_KEY=V0_3_S4_VALIDATION_BUDGET
MAX_VALIDATION_EVALUATIONS=32
MAX_RUNS_PER_CANDIDATE=4
LEGACY_RECONCILED_VALIDATION_DEBIT=4
BOOTSTRAP_AUTHORITY_VERSION=0
BOOTSTRAP_CANONICAL_EVENT_COUNT=0
BOOTSTRAP_CANONICAL_STARTED_COUNT=0
BOOTSTRAP_EFFECTIVE_CONSUMED=4
BOOTSTRAP_REMAINING=28
LEGACY_FAKE_ROWS_CREATED=false
GENESIS_EVENT_HASH=0000000000000000000000000000000000000000000000000000000000000000
```

The accepted head is a monotonic mutable row. Accepted event rows are
immutable. Every STARTED or TERMINAL append inserts the event and advances the
head in one transaction using an expected-state compare-and-swap update.
Candidate run ordinals are counted from durable STARTED rows; global ordinals
are derived from the accepted head and cannot be caller-selected with a jump.

## Canonical event and projection contract

`event_payload` stores the repository-canonical event body and is the sole
semantic input to the event hash. The hash preimage is:

```text
SHA256(canonical_json({event_type, canonical_event_body, previous_event_hash}))
```

Typed columns are validated projections of that stored body before commit and
again during verified readback. A projection mismatch fails closed with
`VALIDATION_EVENT_PROJECTION_MISMATCH`; no typed column overrides the body and
the body does not override a mismatched column.

The two allowed event types are `EVALUATION_STARTED` and
`EVALUATION_TERMINAL`. STARTED events count toward the budget and require
candidate run ordinal 1..4 plus a positive global ordinal. Terminal events
bind to exactly one STARTED event with the same authority and evaluation ID,
carry the matching candidate ID, explicitly carry
`counted_toward_budget=false`, and never consume additional budget.

The reader verifies the authority counters, row count, event sequence, stored
body projections, event hashes, previous-hash chain, STARTED count, last global
ordinal, and final accepted head before calculating:

```text
effective = 4 + accepted_started_count
remaining = 32 - effective
```

Tail truncation, head/counter regression, hash corruption, orphan or duplicate
terminal events, and stale CAS state are rejected with stable reason codes.

## Database safeguards

Migration `0032_s4_validation_budget_durable_persistence` creates:

- `s4_validation_budget_authority`, with non-negative counter/effective-budget
  checks and the fixed legacy debit;
- `s4_validation_event`, with the composite authority/sequence primary key,
  authority foreign key, event/evaluation uniqueness, SHA-256 checks, event
  type checks, and STARTED-only partial unique indexes;
- SQLite and PostgreSQL equivalents of the event immutability guard.

The partial candidate-run uniqueness includes `candidate_id`, so run ordinal 1
may be used independently by different candidates. The authority row remains
mutable only through the repository's locked expected-state transition.

## Validation record

Local validation completed before opening the Draft PR:

```text
FOCUSED_PERSISTENCE_TESTS=39 passed
EXISTING_S4_EXPERIMENT_TESTS=141 passed
COMBINED_S4_TESTS=180 passed
RUFF=PASS
RUFF_FORMAT=PASS
MYPY_BACKEND_APP=PASS
SQLITE_MIGRATION_BOOTSTRAP=PASS
SQLITE_MIGRATION_ROUND_TRIP=PASS
ALEMBIC_HEAD_COUNT=1
ALEMBIC_HEAD=0032_s4_validation_budget_durable_persistence
EXISTING_MIGRATION_HEAD_CONTRACTS_RECONCILED=true
```

The existing migration-contract tests that asserted the former `0031` head
were updated to assert the new single live head. This is a test-contract
reconciliation required by adding a real Alembic revision; it does not alter
the historical migration files or any production business behavior.

The development environment has no PostgreSQL endpoint or local PostgreSQL
server. The real transaction/locking/concurrency test is included in the
isolated `postgres-concurrency` PR-CI job and is required for acceptance; the
local result is intentionally not represented as a PostgreSQL pass.

## Explicit boundaries

```text
POSTGRESQL_CANONICAL_AUTHORITY=true
EVENT_AND_HEAD_SAME_TRANSACTION=true
COMPARE_AND_SWAP_IMPLEMENTED=true
CONCURRENT_WRITER_FAILS_CLOSED=true
EVENT_IMMUTABILITY_DB_ENFORCED=true
TAIL_TRUNCATION_DETECTION_IMPLEMENTED=true
CANONICAL_EVENT_BODY_SINGLE_SOURCE_OF_TRUTH=true
TYPED_PROJECTION_VALIDATION_BEFORE_COMMIT=true
TYPED_PROJECTION_VALIDATION_ON_READBACK=true
HASH_REPLAY_USES_STORED_BODY=true
JSONL_BUDGET_AUTHORITY=false
RUNNER_INTEGRATION_IMPLEMENTED=false
CANDIDATE_01_EXECUTION_PERFORMED=false
CANDIDATE_02_EXECUTION_PERFORMED=false
NEW_VALIDATION_SCORING_CALL_COUNT=0
TEST_EVALUATION_PERFORMED=false
TEST_REMAINS_SEALED=true
PR587_MUTATION_PERFORMED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

The implementation does not authorize or perform candidate execution,
validation scoring, TEST evaluation, model/parameter changes, or integration
with PR #587's runner. Those remain separate coordinator decisions.

FINAL_STOP_GATE=COORDINATOR_S4_DURABLE_PERSISTENCE_IMPLEMENTATION_REVIEW
