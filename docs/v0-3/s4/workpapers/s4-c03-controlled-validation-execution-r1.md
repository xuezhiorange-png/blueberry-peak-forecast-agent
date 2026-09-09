# S4-C03 controlled validation execution R1

## Outcome

This controlled execution attempt stopped before the first durable
`EVALUATION_STARTED` event. The result is:

```text
RESULT=BLOCKED_BEFORE_VALIDATION_START
BLOCK_REASON=SOURCE_002_FROZEN_OBJECT_UNAVAILABLE_FOR_CONTROLLED_EXECUTION
CANDIDATE_ID=03_phenology_offset
AUTHORIZED_RUNS=1,2,3,4
RUN_VALUES=14,18,24,28
NEW_VALIDATION_SCORING_CALL_COUNT=0
```

The accepted historical SOURCE-002 state remains an input fact from the
merged S2/S3 evidence. It was not re-attested in this attempt because the
official raw bytes were not available to this execution environment.

## Authority discovery and fail-closed boundary

The required frozen object identity is:

```text
SOURCE_002_RAW_OBJECT_BYTE_COUNT=28668416
SOURCE_002_RAW_OBJECT_SHA256=fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a
```

Read-only discovery covered the reasonable user-controlled locations
(`/Users/charles/Documents`, `/Users/charles/Downloads`,
`/Users/charles/Desktop`, and `/tmp`), the repository and unreachable Git
objects, GitHub Actions artifacts, GitHub release assets, repository Actions
secret/variable names, and the governed source-reader configuration. No file
with the required byte count and SHA-256 was found. No authorized
`SOURCE_002_FROZEN_OBJECT_PATH` was configured, and no existing out-of-band
artifact channel was exposed.

The repository's default database settings resolve to the local default
endpoint. That endpoint was deliberately not used as live authority. No
explicit controlled `S4_EXECUTION_DATABASE_URL` or
`S4_BUDGET_DATABASE_URL` was available either. This is not a Docker or
historical-volume recovery attempt; it is an authority-input availability
finding. Without the raw object, the required byte-count/SHA verification and
the governed Lane A → Lane B → Lane C → Lane D rebuild cannot begin. Without
the controlled endpoints, the durable budget precheck cannot be performed.

No substitute workbook, synthetic rows, manual export, TEST reader, alternate
SOURCE-002 parser, or alternate database reader was used.

## Execution and budget boundary

The owner authorization was present for exactly four `NORMAL_RUN` invocations
of Candidate 03, with the sole frozen parameter path
`offset.maximum_abs_shift_days` and values `14,18,24,28`. The attempt did not
reach execution admission:

```text
SOURCE_002_REBUILD_PERFORMED=false
SOURCE_002_REBUILD_PARITY=NOT_RUN
SOURCE_002_ATTESTED=NOT_RUN_IN_THIS_ATTEMPT
C03_EXECUTION_PERFORMED=false
NEW_STARTED_EVENT_ATTEMPTED=false
NEW_STARTED_EVENT_CREATED=false
NEW_VALIDATION_SCORING_CALL_COUNT=0
RUN_LOCAL_REPLAY_USED_AS_C03_SCORER=false
PRODUCTION_MATURITY_SHIFT_MODEL_PATH_USED=false
PAIRING_IDENTITIES_DERIVED=false
METRICS_COMPUTED=false
GUARDRAILS_COMPUTED=false
TEST_ACCESS_REQUESTED=false
TEST_REMAINS_SEALED=true
```

The accepted pre-execution budget expectation remains legacy debit `4`,
canonical STARTED count `0`, effective consumption `4`, and remaining budget
`28`. Because no controlled budget database was available, this attempt did
not claim a live PostgreSQL readback of those counters; it created no event and
performed no scoring call.

## Prohibited downstream actions

No candidate run was retried or substituted. No C01 rerun, C02/C04/C05/C06/C07
or C08 execution, incumbent-config mutation, production model change, TEST
access, package publication, model promotion, pilot, final selection, S3-C
backtest, S3 metrics, or S3-D attribution was performed.

The machine-readable aggregate record is
`docs/v0-3/s4/evidence/s4-c03-controlled-validation-execution-r1.json`.
It contains no raw TRAIN/VALIDATION rows, labels, or predictions.

The final Draft-PR exact-head CI run completed successfully at
`CI_RUN=34294866938` for head `e225fbca964e96d9bad8a4c7de90f09e1dc85a9b`.
The workflow's `postgres-concurrency` job was successful and its
`full-suite-canary` job was skipped by workflow policy. This CI run tested the
document-only blocked record; it did not invoke the controlled C03 runner.

```text
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
FINAL_STOP_GATE=COORDINATOR_C03_CONTROLLED_VALIDATION_EXECUTION_REVIEW
```
