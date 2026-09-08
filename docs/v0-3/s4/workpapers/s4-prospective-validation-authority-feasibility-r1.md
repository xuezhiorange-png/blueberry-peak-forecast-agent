# S4 prospective validation authority feasibility workpaper R1

## Purpose and boundary

This workpaper records the feasibility decision for a lawful post-TEST S4
paired comparison. It is not an S4 candidate execution record. No candidate
was run, no model or parameter was changed, no validation budget was consumed,
and TEST remained sealed.

```text
TASK_ID=V0_3_S4_VALIDATION_AUTHORITY_FEASIBILITY_AND_PROSPECTIVE_AMENDMENT_DECISION_R1
BASE_MAIN_SHA=29277d99b867e8dafdcf05ad149e88922442642b
PR584_MERGE_IN_BASE=true
IMPLEMENTATION_COMMIT=dc1a532811d921a6bb83c7b6cee81cee277e0d0f
```

## Authority reconciliation

### Frozen S1

The accepted S1 policy and manifest were re-bound from current `main`:

```text
SPLIT_POLICY_VERSION=v0-3-s1-time-ordered-split-policy-v1
SPLIT_MANIFEST_VERSION=v0-3-s1-time-ordered-split-manifest-v1
SPLIT_MANIFEST_SHA256=f2c4b32b60c94fa2887fbe80c7a25f0fc5a54528585342e49a288cbf07ea9a5f
TRAIN_INTERVAL=2025-08-05..2026-01-30
VALIDATION_INTERVAL=2026-01-31..2026-03-09
TEST_INTERVAL=2026-03-10..2026-04-16
REQUESTED_HORIZONS_DAYS=7,14,21
```

The frozen VALIDATION interval cannot become a prospective interval by
reinterpretation. Its incumbent daily forecast authority is absent, so the
lawful historical state remains:

```text
FROZEN_S1_VALIDATION_PAIRED_S4_EXECUTABLE=false
FROZEN_S1_VALIDATION_EXECUTION_STATUS=NOT_COMPUTABLE_DUE_TO_HISTORICAL_INCUMBENT_AUTHORITY
HISTORICAL_INCUMBENT_FORECAST_DAILY_AUTHORITY_AVAILABLE=false
HISTORICAL_PIT_NOT_COMPUTABLE=true
HISTORICAL_PIT_REASON=HISTORICAL_INCUMBENT_DAILY_FORECAST_AUTHORITY_NOT_DURABLY_RETAINED
```

### S4 bindings

The scanner does not mutate the frozen plan or guardrail policy:

```text
EXPERIMENT_PLAN_VERSION=v0.3-experiment-plan-v1
EXPERIMENT_PLAN_HASH=9e223a02a1b38c028c230a45eb1fa8323f3c2247bb85e7b439f3351e51042500
GUARDRAIL_POLICY_VERSION=v0.3-s4-guardrail-policy-v1
GUARDRAIL_POLICY_HASH=74ecd47339572955e654cf61c38ee6b0546ba51a36e67f80f6ad4dd4519f1ff8
CANDIDATE_01_PARAMETER_MANIFEST_HASH=eba8af27f926635d654aa4c5331f323a9e4edfa399659e1917b729ac6550910b
```

### Prospective authority source

The production retention owner is already implemented and verified by S3.
This task uses it as a read source only:

```text
PROSPECTIVE_FORECAST_AUTHORITY_RETENTION_AVAILABLE=true
PROSPECTIVE_FORECAST_AUTHORITY_CAPTURE_IMPLEMENTED=true
PROSPECTIVE_FORECAST_AUTHORITY_CAPTURE_VERIFIED=true
FUTURE_LEGAL_PIT_REPLAY_SUPPORTED=true
AUTHORITY_SCOPE=PRODUCTION
AUTHORITY_STATUS=CAPTURED
PIT_READER=backend.app.forecast_authority.retention.load_pit_visible_forecast_authority
```

Production captures are checked for their canonical identity fields, business
grain snapshot, model identity, source lineage, daily-artifact identity, and
complete daily curve. The scanner calls the exact PIT reader with the
authority's lawful availability boundary. Synthetic, fixture, CI, demo, or
test authority is not promotable.

Actuals are read only from existing immutable I7 `AS_OF_EVALUATION` snapshots.
The scanner round-trips I7 request, instance, winner, label-row, exclusion,
and snapshot identities. It does not create a new snapshot and does not use a
`FINAL_ADJUDICATED` snapshot as a silent substitute.

## Prospective cohort rule

Only target dates strictly greater than the sealed TEST end are eligible:

```text
POST_TEST_TARGET_DATE_REQUIRED=true
TARGET_DATE_MINIMUM=2026-04-17
TEST_ACCESS=false
```

Canonical target dates are obtained from the existing S3 window functions for
horizons 7, 14, and 21. The scanner requires the retained daily curve to cover
the largest requested horizon. It pairs labels only by exact semantic key:

```text
SEASON_X_FARM_X_SUBFARM_X_VARIETY_X_HARVEST_BUSINESS_DATE
```

Missing, duplicate, ambiguous, or mismatched grain/horizon bindings are not
repaired with positional or latest-row fallback.

The proposed identities are hashes over actual durable projections:

```text
PROPOSED_FORECAST_AUTHORITY_SET_HASH
PROPOSED_ACTUAL_LABEL_SET_HASH
PROPOSED_BUSINESS_GRAIN_SET_HASH
PROPOSED_HORIZON_SET_HASH
PROPOSED_COMMON_COMPARABLE_SET_HASH
```

They remain unissued proposals. A missing live authority store yields null
hashes rather than `sha256("label")`, `sha256("validation")`, or other
placeholder identities.

## Live execution result

Exactly one read-only scan was attempted after Phase A tests passed:

```text
EXECUTION_MAIN_SHA=29277d99b867e8dafdcf05ad149e88922442642b
SCANNER_COMMIT_SHA=dc1a532811d921a6bb83c7b6cee81cee277e0d0f
LIVE_PROSPECTIVE_SCAN_STATUS=BLOCKED
LIVE_PROSPECTIVE_SCAN_BLOCK_REASON=POSTGRESQL_AUTHORITY_STORE_UNAVAILABLE
LIVE_PROSPECTIVE_SCAN_COUNTS_OBSERVED=false
```

The runner's aggregate fallback fields are intentionally sanitized zeros; they
do not prove that the unavailable store is empty:

```text
PROSPECTIVE_FORECAST_CAPTURE_COUNT=0
POST_TEST_FORECAST_CAPTURE_COUNT=0
PIT_READABLE_FORECAST_COUNT=0
ELIGIBLE_LABEL_SNAPSHOT_COUNT=0
PROSPECTIVE_COMMON_COMPARABLE_ROW_COUNT=0
PROSPECTIVE_COVERAGE_RATIO=null
PROPOSED_*_HASH=null
```

Accordingly, the prospective feasibility question was not determined in this
environment. It is not classified as `NO_PROSPECTIVE_AUTHORITY`, because that
would require a successful authority-store read. It is classified as
environment-blocked:

```text
PROSPECTIVE_VALIDATION_EXTENSION_FEASIBILITY_DETERMINED=false
PROSPECTIVE_VALIDATION_EXTENSION_FEASIBLE=false
PROSPECTIVE_VALIDATION_EXTENSION_BLOCK_REASON=POSTGRESQL_AUTHORITY_STORE_UNAVAILABLE
S4_PLAN_AMENDMENT_REQUIRED=false
PROSPECTIVE_SPLIT_AMENDMENT_REQUIRED=false
NEXT_ALLOWED_TASK=COORDINATOR_REVIEW_OF_BLOCKED_LIVE_PROSPECTIVE_SCAN
```

No amendment is issued in this PR. If a future authorized run can read the
store and proves a complete post-TEST paired set, the next task must version a
new prospective split and amend the experiment plan before candidate
execution. That is a separate authorization boundary.

## Non-consumption proof

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
WRITES_PERFORMED=0
EVALUATION_LEDGER_EVENTS_CREATED=0
```

## Verification

```text
FOCUSED_TESTS=27 passed
S4_AND_RETENTION_REGRESSION=141 passed, 1 skipped
RUFF_RESULT=PASS
MYPY_RESULT=PASS
MIGRATION_REQUIRED=false
MODEL_CHANGED=false
PARAMETERS_CHANGED=false
CANDIDATE_EXECUTED=false
```

Final gate:

```text
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
FINAL_STOP_GATE=COORDINATOR_V0_3_S4_PROSPECTIVE_VALIDATION_FEASIBILITY_REVIEW
```
