# S4 C04 evidence-bound readjudication correction R3

## Scope

R3 corrects the provenance boundary of the R2 governance readjudication. It
does not change the V4 selection policy and does not execute a validation
candidate. The readjudication entry point now loads the immutable R1 evidence
file, verifies its exact SHA-256 digest, and extracts scalar run and incumbent
metrics from that file.

```text
READJUDICATION_INPUT_SOURCE=docs/v0-3/s4/evidence/s4-c04-controlled-real-validation-r1.json
R1_EVIDENCE_SHA256=78b1489b28fe0056e1c7fd88165f927c04d16bf1083926048ba4c36e3c1498b3
R1_EVIDENCE_IMMUTABLE=true
```

## Evidence sufficiency result

The frozen R1 JSON contains axis-level summary counts such as `cell_count`,
`below_minimum_cell_count`, and `non_computed_cell_count`. It does not contain
the required per-cell records. In particular, it does not provide cell
identities, cell comparable-row counts, cell metric statuses, or an explicit
`no_silent_exclusion` value. A global `coverage_ratio=1.000000` cannot prove
those facts and is not used as a substitute.

```text
REAL_R1_BREAKDOWN_CELL_EVIDENCE_AVAILABLE=false
BLOCKER=R1_BREAKDOWN_CELL_EVIDENCE_INSUFFICIENT_FOR_V4_READJUDICATION
SYNTHETIC_COVERAGE_USED=false
V4_EVALUATOR_CALLED=false
```

Because the required cell evidence is absent, the evidence-bound entry point
returns the following fail-closed result rather than issuing a V4 eligibility
decision:

```text
RUN_1_V4_ELIGIBILITY=NOT_PROVEN
RUN_2_V4_ELIGIBILITY=NOT_PROVEN
RUN_3_V4_ELIGIBILITY=NOT_PROVEN
RUN_4_V4_ELIGIBILITY=NOT_PROVEN
C04_BEST_VALIDATION_RUN=NONE
C04_VALIDATION_OUTCOME=BLOCKED_EVIDENCE_INSUFFICIENT
```

The R2 result remains preserved as provisional historical governance evidence;
it is not overwritten or promoted by R3. R3 does not claim that the R2 PASS,
FAIL, FAIL, PASS statuses have been proven from the available R1 breakdown
evidence.

## Non-execution and budget invariants

The parser imports no validation loader, scorer, or durable execution adapter.
Tests explicitly guard those boundaries. No validation rows were reread, no
scorer was called, and no event was created:

```text
VALIDATION_DATA_REREAD=false
SCORER_CALLED=false
DURABLE_EXECUTION_CALLED=false
NEW_VALIDATION_EXECUTION=false
NEW_VALIDATION_SCORING=false
NEW_STARTED_EVENT_COUNT=0
NEW_TERMINAL_EVENT_COUNT=0
```

The already-consumed R1 budget remains unchanged:

```text
CANONICAL_STARTED_COUNT=4
C04_CANONICAL_STARTED_COUNT=4
EFFECTIVE_CONSUMED=8
REMAINING=24
R3_BUDGET_DELTA=0
TEST_ACCESS_REQUESTED=false
TEST_BYTES_READ=false
TEST_EVALUATION_PERFORMED=false
TEST_REMAINS_SEALED=true
```

This correction stops at the coordinator review gate. Supplying a future
immutable evidence revision with actual per-cell breakdown records would be a
separate governance decision; R3 does not reconstruct or supplement R1.
