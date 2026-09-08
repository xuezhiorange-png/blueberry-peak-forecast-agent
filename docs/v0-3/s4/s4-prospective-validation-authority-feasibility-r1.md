# S4 prospective VALIDATION authority feasibility R1

## Decision scope

This artifact answers an authority question only. It does not execute an S4
candidate, consume a validation evaluation, redefine S1, access TEST, or issue
an experiment-plan amendment.

```text
TASK_ID=V0_3_S4_VALIDATION_AUTHORITY_FEASIBILITY_AND_PROSPECTIVE_AMENDMENT_DECISION_R1
BASE_MAIN_SHA=29277d99b867e8dafdcf05ad149e88922442642b
PR584_MERGE_IN_BASE=true
CORRECTION_TASK_ID=V0_3_S4_VALIDATION_AUTHORITY_FEASIBILITY_AND_PROSPECTIVE_AMENDMENT_DECISION_R1_CORRECTION_R1
PREVIOUS_HEAD_SHA=73ac069a5859f68443b979dfd2bbe8b21b575fec
CORRECTION_SCANNER_FREEZE_HEAD=ab8427535fe1ebd50b8a7302a08c144bd4386b10
```

The initial implementation commit is
`dc1a532811d921a6bb83c7b6cee81cee277e0d0f`; the corrected scanner freeze is
`ab8427535fe1ebd50b8a7302a08c144bd4386b10`.
The machine-readable result is recorded in
`docs/v0-3/s4/evidence/s4-prospective-validation-authority-feasibility-r1.json`.

## Frozen S1 authority remains unchanged

```text
SPLIT_POLICY_VERSION=v0-3-s1-time-ordered-split-policy-v1
SPLIT_MANIFEST_VERSION=v0-3-s1-time-ordered-split-manifest-v1
SPLIT_MANIFEST_SHA256=f2c4b32b60c94fa2887fbe80c7a25f0fc5a54528585342e49a288cbf07ea9a5f
TRAIN_INTERVAL=2025-08-05..2026-01-30
VALIDATION_INTERVAL=2026-01-31..2026-03-09
TEST_INTERVAL=2026-03-10..2026-04-16
REQUESTED_HORIZONS_DAYS=7,14,21
NO_OVERLAP=true
NO_GAPS=true
```

The historical S1 VALIDATION interval is not silently replaced by a later
cohort. The current S4-A and S4-B authorities remain bound to:

```text
EXPERIMENT_PLAN_HASH=9e223a02a1b38c028c230a45eb1fa8323f3c2247bb85e7b439f3351e51042500
GUARDRAIL_POLICY_HASH=74ecd47339572955e654cf61c38ee6b0546ba51a36e67f80f6ad4dd4519f1ff8
CANDIDATE_01_PARAMETER_MANIFEST_HASH=eba8af27f926635d654aa4c5331f323a9e4edfa399659e1917b729ac6550910b
```

## Historical paired-comparison disposition

The historical incumbent daily forecast authority for the frozen VALIDATION
interval was not durably retained. Therefore the lawful state is terminal
`NOT_COMPUTABLE`, not PASS, FAIL, or a recovery queue:

```text
HISTORICAL_INCUMBENT_FORECAST_DAILY_AUTHORITY_AVAILABLE=false
HISTORICAL_PIT_NOT_COMPUTABLE=true
HISTORICAL_PIT_REASON=HISTORICAL_INCUMBENT_DAILY_FORECAST_AUTHORITY_NOT_DURABLY_RETAINED
FROZEN_S1_VALIDATION_PAIRED_S4_EXECUTABLE=false
FROZEN_S1_VALIDATION_EXECUTION_STATUS=NOT_COMPUTABLE_DUE_TO_HISTORICAL_INCUMBENT_AUTHORITY
HISTORICAL_FORECAST_RECOVERY_PERFORMED=false
HISTORICAL_FORECAST_VALUES_SYNTHESIZED=false
REPLAY_IDENTITIES_REINTERPRETED_AS_FORECAST_VALUES=false
```

No historical forecast values are reconstructed or derived from actual labels.

## Prospective scanner contract

The new scanner is read-only. It uses the existing production retention owner
and reader:

```text
AUTHORITY_OWNER=forecast_authority_capture
PIT_READER=backend.app.forecast_authority.retention.load_pit_visible_forecast_authority
REQUIRED_AUTHORITY_SCOPE=PRODUCTION
REQUIRED_AUTHORITY_STATUS=CAPTURED
LABEL_VISIBILITY_REQUIRED=AS_OF_EVALUATION
NEW_LABEL_SNAPSHOT_CREATED=false
INCUMBENT_MODEL_ID=V0_2_CURRENT_MODEL
INCUMBENT_MODEL_IDENTITY_EXACT_BINDING_ENFORCED=true
OTHER_PRODUCTION_MODEL_REJECTED=true
```

The scanner rejects missing, ambiguous, post-cutoff, hash-invalid, incomplete,
synthetic, test-only, and business-grain-incompatible authority. It uses the
repository-owned `expected_forecast_target_date` and `horizon_window_dates`
functions for horizons 7, 14, and 21. A prospective target must satisfy:

```text
POST_TEST_TARGET_DATE_REQUIRED=true
TARGET_DATE_MINIMUM=2026-04-17
SPARSE_HORIZON_ROWS_ARE_NOT_COMPLETE_DAILY_CURVE=true
TEST_ACCESS=false
TEST_SNAPSHOT_HEADER_GATE_ENFORCED=true
TEST_OVERLAPPING_SNAPSHOT_REJECTED_BEFORE_CHILD_LOAD=true
TEST_CHILD_ROW_QUERY_REMOVED=true
TEST_CHILD_ROW_QUERY_COUNT=0
```

Existing I7 snapshot identities are round-tripped with the production helpers:
request identity, instance identity, winner manifest, label-row set,
exclusion manifest, and snapshot hash. Only exact season/farm/subfarm/variety
and target-date keys are paired. The scanner does not calculate candidate
metrics or write a validation ledger event.

The proposed forecast-authority, actual-label, business-grain, horizon, and
common-comparable hashes are emitted only when real durable rows were read. A
blocked live store therefore produces `null`, never a placeholder hash.

Current S4-B coverage requirements remain:

```text
MINIMUM_COVERAGE_THRESHOLD=0.900000
VALID_INCLUDED_CANONICAL_GROUP_COVERAGE_THRESHOLD=1.000000
MISSING_DATA_PROPORTION_THRESHOLD=0.000000
REQUIRED_BREAKDOWN_AXIS_COUNT=6
MIN_COMPARABLE_ROWS_FOR_REPORTING=10
```

## Single live scan

After corrected scanner validation and exact-head CI, one and only one
corrected live scan was attempted with the frozen repository identity. It was
not replaced by a fixture or a local synthetic database.

```text
EXECUTION_MAIN_SHA=29277d99b867e8dafdcf05ad149e88922442642b
SCANNER_COMMIT_SHA=ab8427535fe1ebd50b8a7302a08c144bd4386b10
CORRECTION_SCANNER_EXACT_HEAD_CI_RUN=34185669069
CORRECTION_SCANNER_EXACT_HEAD_CI=SUCCESS
CORRECTION_LIVE_SCAN_COUNT=1
LIVE_PROSPECTIVE_SCAN_STATUS=BLOCKED
LIVE_PROSPECTIVE_SCAN_BLOCK_REASON=POSTGRESQL_AUTHORITY_STORE_UNAVAILABLE
LIVE_PROSPECTIVE_SCAN_COUNTS_OBSERVED=false
```

Because the authority store was unavailable, the sanitized runner payload
contains zero counts for safety. Those zeros are not a finding that the
production store contains no authority. The result is an environment-blocked
feasibility determination:

```text
PROSPECTIVE_VALIDATION_EXTENSION_FEASIBILITY_DETERMINED=false
PROSPECTIVE_VALIDATION_EXTENSION_FEASIBLE=false
PROSPECTIVE_VALIDATION_EXTENSION_BLOCK_REASON=POSTGRESQL_AUTHORITY_STORE_UNAVAILABLE
S4_PLAN_AMENDMENT_REQUIRED=false
PROSPECTIVE_SPLIT_AMENDMENT_REQUIRED=false
AMENDMENT_ISSUED_IN_THIS_TASK=false
NEXT_ALLOWED_TASK=COORDINATOR_REVIEW_OF_BLOCKED_LIVE_PROSPECTIVE_SCAN
```

No new S4 plan version or prospective split is issued by this task. If a
future controlled read-only scan reaches the authority store and demonstrates
post-TEST complete pairing, a separate task must version the cohort and amend
the experiment plan before any candidate execution. That future amendment is
not implied here.

## Budget and TEST boundaries

```text
CANDIDATE_01_RUN_COUNT=0
ACTUAL_VALIDATION_EVALUATION_COUNT=0
CURRENT_LEDGER_ROW_COUNT=0
REMAINING_GLOBAL_VALIDATION_BUDGET=32
S4_CANDIDATE_EXPERIMENT_EXECUTED=false
CANDIDATE_01_EXECUTION_AUTHORIZED=false
TEST_EVALUATION_AUTHORIZED=false
TEST_REMAINS_SEALED=true
TEST_ROWS_SELECTED=false
TEST_LABELS_LOADED=false
TEST_FORECASTS_LOADED=false
```

The scanner performs no writes and creates no `EVALUATION_STARTED` event.
Candidate metrics, model changes, parameter changes, training, and split
mutation were not performed.

## Validation record

```text
FOCUSED_TESTS=40 passed
S4_AND_RETENTION_REGRESSION=157 passed, 1 skipped
EVIDENCE_TEST_COUNT_MATCHES_EXECUTION=true
RUFF_RESULT=PASS
MYPY_RESULT=PASS
MIGRATION_REQUIRED=false
MODEL_CHANGED=false
PARAMETERS_CHANGED=false
CANDIDATE_EXECUTED=false
```

The final stop gate is:

```text
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
FINAL_STOP_GATE=COORDINATOR_PR585_CORRECTION_R1_REVIEW
```
