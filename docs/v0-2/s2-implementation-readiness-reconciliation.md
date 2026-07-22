# V0.2-S2 Implementation Readiness Reconciliation

## Document status

```text
V0_2_S2_SCOPE_RECONCILIATION=true
V0_2_EXECUTION_PATH_DRIFT_CONFIRMED=true
V0_2_S2_GATE_CLASSIFICATION_CORRECTED=true
VERSION=0.2.0
VERSION_NAME=FORECAST_QUALITY_TRIAL
V0_2_TOTAL_SLICES=5
NO_ADDITIONAL_SLICE_WITHOUT_VERSION_REPLAN=true
NO_STEP_IMPLIES_THE_NEXT=true
```

This document is a forward-looking scope and readiness correction. It does not rewrite or invalidate the historical Q2A-Q2F design and audit records.

## V0.2 authority and slices

`docs/v0-2/development-plan.md` is the highest authority for V0.2 scope and delivery order.

```text
S1=ACTUAL_HARVEST_ATOMIC_COMMIT
S2=POINT_IN_TIME_ACTUAL_LABELS_AND_HISTORICAL_BACKTEST
S3=FORECAST_QUALITY_METRICS_AND_ONE_NAIVE_BASELINE
S4=FRONTEND_APPLICATION_API
S5=TWO_PAGE_RESPONSIVE_FRONTEND_AND_BROWSER_E2E
```

The Q2 work is part of V0.2-S2. No additional slice is introduced by this reconciliation.

## Current implementation state

```text
V0_2_S1_COMPLETE=true

S2_ACTUAL_HARVEST_IMPORT_IMPLEMENTED=true
S2_ACTUAL_HARVEST_VALIDATION_IMPLEMENTED=true
S2_ACTUAL_HARVEST_COMMIT_IMPLEMENTED=true
S2_REVISION_WINNER_IMPLEMENTED=true
S2_POINT_IN_TIME_LABEL_SNAPSHOT_IMPLEMENTED=true

S2_FORECAST_LABEL_BINDING_IMPLEMENTED=false
S2_HISTORICAL_BACKTEST_RUNNER_IMPLEMENTED=false
S2_BACKTEST_MANIFEST_IMPLEMENTED=false
S2_7_14_21_DAY_BINDINGS_IMPLEMENTED=false
```

The implemented label and lineage foundations do not constitute a historical backtest runner. Forecast binding, comparison-ready horizons, and immutable backtest manifests remain unimplemented.

## Gate classification

The following concerns are not coding prerequisites for implementing a fail-closed synthetic-capable S2 runner:

```text
REAL_DATA_NOT_VERIFIED=REAL_DATA_EXECUTION_AND_RELEASE_ACCEPTANCE_GATE
MISSING_SOURCE_OWNER=REAL_DATA_APPROVAL_GATE
MISSING_EXTERNAL_BUSINESS_ATTESTATION=REAL_DATA_ACCEPTANCE_GATE
PHYSICAL_TARGET_EQUIVALENCE_NOT_YET_VERIFIED=REAL_DATA_COMPARABILITY_GATE
QUANTILE_SEMANTICS_NOT_VERIFIED=S3_INTERVAL_AND_COVERAGE_METRIC_GATE
```

This reclassification does not approve real-data execution or release. It separates implementation eligibility from the evidence gates that must remain closed until governed evidence exists.

```text
EXTERNAL_ATTESTATION_REQUIRED_FOR_RUNNER_IMPLEMENTATION=false
EXTERNAL_ATTESTATION_REQUIRED_FOR_SYNTHETIC_ACCEPTANCE=false
EXTERNAL_ATTESTATION_REQUIRED_FOR_REAL_DATA_ACCEPTANCE=true

REAL_DATA_REQUIRED_FOR_RUNNER_IMPLEMENTATION=false
REAL_DATA_REQUIRED_FOR_RELEASE_ACCEPTANCE=true
```

## Fail-closed runner behavior

The runner may be implemented without approved real data, but it must not claim a real-data result. The following outcomes are explicit blocked, excluded, or not-computable states:

```text
NO_APPROVED_REAL_DATA
NO_LABEL_ROWS_AT_REQUESTED_CUTOFF
PHYSICAL_TARGET_ALIGNMENT_UNVERIFIED
INSUFFICIENT_COVERAGE
QUANTILE_METRIC_NOT_COMPUTABLE
```

The runner must not:

- substitute receipt or arrival data for `FARM_PICK`;
- substitute Task 9 model output for an actual label;
- fill missing dates with zero;
- assume harvested and actual are equivalent without evidence;
- select a latest model, parameter, or label by fallback;
- emit a real quality conclusion without approved evidence.

## Next S2 implementation scope

The next independently authorized implementation round, if separately approved, is limited to the V0.2-S2 historical backtest runner:

```text
BacktestRequest contract
BacktestRun identity
forecast_cutoff_at
label_observation_cutoff_at
label_visibility_mode

historical forecast authority bundle
forecast code/model/parameter/data identities
Task 9 and Task 10 authority binding
I7 immutable label snapshot binding

forecast-label grain alignment
physical-alignment status
7/14/21-day horizon binding rows
coverage and exclusion manifest

immutable backtest manifest
deterministic request and instance hashes
idempotent replay
evidence drift rejection
PostgreSQL persistence and concurrency acceptance
synthetic deterministic E2E fixture
```

This list is a scope boundary, not implementation authorization.

## S3 exclusion

S2 produces comparison-ready binding rows, coverage, exclusions, and manifest evidence only. The following remain V0.2-S3 and are excluded from the S2 runner:

```text
daily MAE
daily WAPE
daily sMAPE
daily MAPE
daily bias
daily relative bias
peak quality metrics
P80/P90 coverage
pinball loss
interval width
naive baseline
quality report
```

S2 must not compute or publish these metrics. Metric semantics and the one naive baseline belong to `S3=FORECAST_QUALITY_METRICS_AND_ONE_NAIVE_BASELINE`.

## Q2G status

```text
Q2G_A_STATUS=PAUSED
OUTBOUND_ATTESTATION_REQUEST_AUTHORIZED=false
SOURCE_OWNER_CONTACT_AUTHORIZED=false
Q2G_MAY_RESUME_ONLY_FOR=REAL_DATA_ACCEPTANCE_PREPARATION
```

Q2G is not a prerequisite chain for S2 runner implementation. It may resume only for preparation of real-data acceptance, under a separate authorization.

## Corrected readiness gate

```text
S2_RUNNER_IMPLEMENTATION_ELIGIBILITY=ELIGIBLE_AFTER_SCOPE_RECONCILIATION_ACCEPTANCE

Q2B_IMPLEMENTATION_AUTHORIZED=false
BACKTEST_EXECUTION_AUTHORIZED=false
REAL_DATA_BACKTEST_AUTHORIZED=false
DATA_IMPORT_AUTHORIZED=false

NEXT_GATE_AFTER_RECONCILIATION=SEPARATE_V0_2_S2_BACKTEST_RUNNER_IMPLEMENTATION_AUTHORIZATION
```

Eligibility after acceptance means the scope blocker has been classified correctly. It does not authorize implementation, synthetic acceptance, real-data execution, release, or any later slice.

## Governance and exclusions

```text
PRODUCTION_CODE_CHANGED=false
TEST_CODE_CHANGED=false
SCHEMA_CHANGED=false
MIGRATION_CHANGED=false
BACKTEST_EXECUTED=false
DATA_IMPORTED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
ISSUE102_CLOSE=false
NO_STEP_IMPLIES_THE_NEXT=true
```

This document makes no claim that a source owner has been identified, that an external business attestation exists, or that real labels are approved for backtesting.
