# S4-C01 controlled validation workpaper

## Decision

Candidate 01 was frozen, but its controlled VALIDATION execution was stopped
at preflight. The stop happened before the first `EVALUATION_STARTED` event
because the current durable S3 closeout says that the historical incumbent
daily forecast authority was not durably retained. No historical forecast,
paired identity, label hash, metric, or result was synthesized.

```text
TASK_ID=V0_3_S4_C01_PARAMETER_CALIBRATION_MANIFEST_AND_CONTROLLED_VALIDATION_R1
BASE_MAIN_SHA=39f63206a07b70e08b2602fca61f4d077b2ed362
PR_NUMBER=584
PR_STATE=DRAFT
PR583_MERGE_IN_BASE=true
EXPERIMENT_PLAN_HASH=9e223a02a1b38c028c230a45eb1fa8323f3c2247bb85e7b439f3351e51042500
GUARDRAIL_POLICY_HASH=74ecd47339572955e654cf61c38ee6b0546ba51a36e67f80f6ad4dd4519f1ff8
CANDIDATE_01_PARAMETER_MANIFEST_VERSION=v0.3-s4-c01-parameter-manifest-v1
CANDIDATE_01_PARAMETER_MANIFEST_HASH=eba8af27f926635d654aa4c5331f323a9e4edfa399659e1917b729ac6550910b
CANDIDATE_01_FREEZE_COMMIT_SHA=33511af91e558f355991189cc551e85c2fae32a6
PHASE_A_FORMAT_CORRECTION_COMMIT_SHA=45bf4519ea0baae858d67b38624467fd388cbe4f
PHASE_A_EXACT_HEAD_CI_RUN=34178189758
PHASE_A_EXACT_HEAD_CI=SUCCESS
```

## Frozen manifest

The incumbent authority is `configs/maturity_curve.yaml`:

```text
INCUMBENT_CONFIG_FILE_SHA256=fc023976a228c36556ed5f7ababe722a3dd8a558ed11e0473eb415b52dd69ace
INCUMBENT_CONFIG_HASH=3571477d5822f57cd2c424620915560e22481f48983b397a1f1b8934e1a7612c
model_family=shared_spline_partial_pooling
random_seed=20260624
curve.spline_degree=3
curve.spline_knot_count=6
curve.ridge_alpha=0.10
pooling.full_pooling_sample_target=4
```

Only these paths are allowlisted:

```text
curve.spline_knot_count
curve.ridge_alpha
```

The exact finite run neighborhood is:

| Run | Knot count | Ridge alpha | Seed | Parameter manifest hash |
| ---: | ---: | ---: | ---: | --- |
| 1 | 5 | 0.10 | 20260624 | `fbf5335e98981a7161e16230495760c46a02b96ac0151b557e999428380273ec` |
| 2 | 7 | 0.10 | 20260624 | `811cb73f3471ab7b9743e31b1d0458009d5c4d5348a2dd722e54fd1af45dc754` |
| 3 | 6 | 0.05 | 20260624 | `924b520bceac3a577f447ebda7247cd4083f522075293a97260a2f716509c529` |
| 4 | 6 | 0.20 | 20260624 | `3706c05b1ff5128d69ff8bece5a5c17808ff25354e0d2ca83e7a2ad9deb3df38` |

`UNAUTHORIZED_PARAMETER_DIFF_COUNT=0` and `NATIVE_FLOAT_ALLOWED=false` were
verified by the manifest tests. The complete canonical snapshots and candidate
config hashes are in the machine-readable manifest evidence.

## Authority preflight

The runner was invoked from the clean Phase A control head with the required
main and runner identities. It read the current S3 closeout authority and
found:

```text
PAIRING_AUTHORITY_RESOLUTION_STATUS=BLOCKED
FIRST_NON_DERIVABLE_AUTHORITY=HISTORICAL_INCUMBENT_DAILY_FORECAST_AUTHORITY
CANDIDATE_01_EXECUTION_PREFLIGHT=BLOCKED
CANDIDATE_01_EXECUTION_BLOCK_REASON=HISTORICAL_INCUMBENT_DAILY_FORECAST_AUTHORITY_NOT_DURABLY_RETAINED
```

This is the accepted S3 historical terminal state, not an invitation to
reopen S3 recovery. The Candidate 01 runner therefore did not resolve
placeholder train/validation/label identities and did not enter model fitting
or paired validation evaluation.

## Ledger and budget result

The durable JSONL artifact is intentionally empty: there are no fake rows and
no `EVALUATION_STARTED` or `EVALUATION_TERMINAL` events.

```text
MAX_VALIDATION_EVALUATIONS=32
MAX_RUNS_PER_CANDIDATE=4
PLANNED_TOTAL_RUN_COUNT=32
CANDIDATE_01_RUN_COUNT=0
ACTUAL_VALIDATION_EVALUATION_COUNT=0
REMAINING_GLOBAL_VALIDATION_BUDGET=32
CURRENT_LEDGER_ROW_COUNT=0
CURRENT_EXPERIMENT_BUDGET_EVALUATION_STATUS=NOT_EVALUATED
JOURNAL_EVENT_COUNT=0
NO_VALIDATION_EVALUATION_STARTED=true
AUTOMATIC_RETRY_AUTHORIZED=false
MANUAL_RETRY_AUTHORIZED=false
OPERATOR_RERUN_AUTHORIZED=false
```

All four runs are `NOT_STARTED`; all guardrail statuses and daily WAPE values
are `NOT_ISSUED`. There is no best observed run, no result hash, no selection,
and no p-value result. `NOT_EVALUATED` is retained rather than misreported as
a budget PASS.

## Pairing identity boundary

The S4-B metric-contract identity is independently known from the current
repository:

```text
METRIC_CONTRACT_VERSION=v0.3-metric-contract-v1
METRIC_CONTRACT_IDENTITY=e3ff3221338863aa9128890c23e463e7a3868cd8dfc3e1b2c30c503c351a3acd
```

All other required pairing identities remain `NOT_RESOLVED` because the first
required incumbent forecast authority is unavailable. No arbitrary SHA-256
values are placed in the evidence. The machine-readable result records the
identity source/status for every required field.

## Boundaries

```text
VALIDATION_EXECUTION_PERFORMED=false
S4_CANDIDATE_EXPERIMENT_EXECUTED=false
S4_METRIC_EXECUTION_PERFORMED=false
PRODUCTION_PARAMETER_CHANGE_AUTHORIZED=false
S4_MODEL_CHANGE_AUTHORIZED=false
TEST_ACCESS_CURRENTLY_AUTHORIZED=false
TEST_EVALUATION_AUTHORIZED=false
TEST_REMAINS_SEALED=true
SELECTED_CANDIDATE_ID=NOT_ISSUED
MODEL_APPROVED_FOR_PILOT=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
FINAL_STOP_GATE=COORDINATOR_V0_3_S4_C01_CONTROLLED_VALIDATION_REVIEW
```

This workpaper does not claim candidate failure, candidate improvement,
historical S3 recovery, TEST access, production promotion, or V0.3 release.

## Correction R1: content-level manifest enforcement

Correction R1 makes the existing manifest executable only under its exact
frozen content. The control plane now independently derives each run's
authorized parameter delta from its full snapshot, recomputes its candidate
config hash and per-run parameter-manifest hash, verifies the bound incumbent
file/hash identities, and verifies the complete manifest hash. Derived config,
preflight, and gate-request entry points all invoke this validation before any
execution decision. Hostile tests cover all four run-value mutations, forged
hashes, incumbent identity drift, seed drift, delta/content disagreement, and
top-level manifest mutation.

The prior Phase A CI head remains historical context. The correction freeze
head is the executable Phase A authority for the preflight below:

```text
CORRECTION_TASK_ID=V0_3_S4_C01_PARAMETER_CALIBRATION_MANIFEST_AND_CONTROLLED_VALIDATION_R1_CORRECTION_R1
PREVIOUS_PHASE_A_CI_HEAD=45bf4519ea0baae858d67b38624467fd388cbe4f
NEW_PHASE_A_CORRECTION_FREEZE_HEAD=f29410c6ab9d1add2cdb8969a90b013aa3905753
NEW_PHASE_A_EXACT_HEAD_CI_RUN=34180407000
NEW_PHASE_A_EXACT_HEAD_CI_HEAD_SHA=f29410c6ab9d1add2cdb8969a90b013aa3905753
NEW_PHASE_A_EXACT_HEAD_CI=SUCCESS
CORRECTION_R1_CONTENT_VALIDATION_ENFORCED=true
```

The corrected official preflight was then run once, with the exact frozen
manifest and the clean correction head. The result remains the accepted
historical-authority stop:

```text
PAIRING_AUTHORITY_RESOLUTION_STATUS=BLOCKED
FIRST_NON_DERIVABLE_AUTHORITY=HISTORICAL_INCUMBENT_DAILY_FORECAST_AUTHORITY
CANDIDATE_01_EXECUTION_PREFLIGHT=BLOCKED
CANDIDATE_01_EXECUTION_BLOCK_REASON=HISTORICAL_INCUMBENT_DAILY_FORECAST_AUTHORITY_NOT_DURABLY_RETAINED
CANDIDATE_01_EXECUTION_ADAPTER_USED=false
CANDIDATE_01_EXECUTION_REACHED=false
NO_VALIDATION_EVALUATION_STARTED=true
CANDIDATE_01_RUN_COUNT=0
ACTUAL_VALIDATION_EVALUATION_COUNT=0
CURRENT_LEDGER_ROW_COUNT=0
JOURNAL_EVENT_COUNT=0
REMAINING_GLOBAL_VALIDATION_BUDGET=32
TEST_REMAINS_SEALED=true
```

No speculative execution adapter was added, no candidate evaluation was
started, and no validation or TEST data was accessed.
