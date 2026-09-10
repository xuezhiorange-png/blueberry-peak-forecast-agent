# S4 C04 exhausted closure and evidence hardening R4

## Closure disposition

R4 accepts the R3 provenance blocker as final for the current immutable R1
evidence. Four real C04 validation runs already exist and the per-candidate
run budget is exhausted. R4 does not attempt to restore eligibility, reopen
the R1 evidence, or promote the R2 governance-only readjudication.

```text
C04_REAL_VALIDATION_RUN_COUNT=4
C04_MAX_RUNS_PER_CANDIDATE=4
C04_RUN_BUDGET_EXHAUSTED=true
C04_SELECTION_ELIGIBILITY=NOT_PROVEN
C04_SELECTION_AUTHORITY=false
C04_FINAL_STATUS=EXHAUSTED_EVIDENCE_INSUFFICIENT
```

The R2 PASS/FAIL/FAIL/PASS result is retained as
`R2_PROVISIONAL_READJUDICATION` with `NON_AUTHORITATIVE=true`. Its observed
best run remains an observation only:

```text
C04_BEST_OBSERVED_RUN_ORDINAL=1
C04_BEST_OBSERVED_MULTIPLIER=3.802757
C04_BEST_OBSERVED_DAILY_WAPE=0.725160
C04_BEST_OBSERVED_DAILY_MAE=893.149826
BEST_OBSERVED_IS_SELECTION_WINNER=false
BEST_OBSERVED_IS_TEST_ELIGIBLE=false
BEST_OBSERVED_IS_FINAL_MODEL=false
```

## Future evidence contract

R3 showed that the frozen R1 artifact contains compact axis summaries but not
the cell-level provenance required to replay V4. R4 adds a reusable canonical
serializer and parser in `backend.app.s4_experiment` for future real S4
validation evidence. The serializer persists coverage scalars, the six
required axes, every cell identity, comparable-row count, metric status, and
the derived reporting disposition. It also persists the explicit
`no_silent_exclusion` fact. A summary is retained only as a summary and is
never accepted as cell evidence.

```text
FUTURE_EVIDENCE_SCHEMA_VERSION=v0.3-s4-selection-evidence-v1
SUMMARY_IS_CELL_EVIDENCE=false
WRITE_TIME_SCHEMA_VALIDATION=true
WRITE_TIME_BLOCK_REASON=SELECTION_EVIDENCE_PROVENANCE_INCOMPLETE
```

The C04 controlled runner now serializes its candidate and incumbent coverage
evidence through this contract. `write_evidence` validates the complete
selection payload before writing. Compact payloads, missing cells, missing
comparable rows, missing metric status, or missing no-silent-exclusion proof
fail closed before a selection artifact is written.

The local round-trip tests cover:

```text
LocalMetricSet-derived coverage evidence
  -> canonical serializer
  -> canonical JSON
  -> canonical parser
  -> CoverageQualityEvidence
```

They verify axis count, cell count, cell identities, comparable rows, metric
statuses, no-silent-exclusion, reporting disposition, and deterministic hash
replay. No real VALIDATION rows are used by these tests.

## Non-execution and budget boundary

R4 performed no validation reread, scoring, durable execution, STARTED event,
or terminal event. The durable facts remain unchanged:

```text
LEGACY_RECONCILED_VALIDATION_DEBIT=4
CANONICAL_STARTED_COUNT=4
C04_CANONICAL_STARTED_COUNT=4
EFFECTIVE_CONSUMED=8
REMAINING=24
R4_BUDGET_DELTA=0
TEST_ACCESS_REQUESTED=false
TEST_BYTES_READ=false
TEST_EVALUATION_PERFORMED=false
TEST_REMAINS_SEALED=true
```

V1, V2, V3, and V4 policy identities are unchanged. R4 is evidence-persistence
hardening only; it does not create V5 or issue a selection, TEST authorization,
final model decision, Ready state, or Merge.

```text
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
FINAL_STOP_GATE=COORDINATOR_V0_3_S4_C04_CLOSURE_R4_REVIEW
```
