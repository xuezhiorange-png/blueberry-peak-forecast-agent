# V0.3 S4-B guardrail and VALIDATION execution policy

This document freezes the common S4 candidate comparison policy and the
fail-closed preflight required before a candidate may consume a VALIDATION
budget unit. It is a separately versioned S4-B overlay; it does not modify the
S4-A experiment plan or its canonical hash.

## Authority and current state

```text
TASK_ID=V0_3_S4_B_GUARDRAIL_POLICY_AND_VALIDATION_EXECUTION_GATE_FREEZE_R1
BASE_MAIN_SHA=2d2b6a63a84e23e91e14f1929ad953fac4f87b0d
PR582_MERGE_IN_BASE=true
CURRENT_V0_3_S3_COMPLETE=true
S4_IMPLEMENTATION_STARTED=true
CURRENT_EXPERIMENT_PLAN_FROZEN=true
CURRENT_CANDIDATE_REGISTRY_FROZEN=true
EXPERIMENT_PLAN_VERSION=v0.3-experiment-plan-v1
S4_A_EXPERIMENT_PLAN_HASH_BOUND=9e223a02a1b38c028c230a45eb1fa8323f3c2247bb85e7b439f3351e51042500
GUARDRAIL_POLICY_VERSION=v0.3-s4-guardrail-policy-v1
GUARDRAIL_POLICY_HASH=74ecd47339572955e654cf61c38ee6b0546ba51a36e67f80f6ad4dd4519f1ff8
GUARDRAIL_POLICY_HASH_REPLAY=PASS
OLD_GUARDRAIL_POLICY_HASH=0a910697cf5588383e117df8a22e3826b0d21b9dda38cef490698ad89560a27f
OLD_GUARDRAIL_POLICY_HASH_INVALIDATED_BY_CORRECTION=true
```

The policy hash is SHA-256 over the complete canonical policy preimage
implemented by `backend/app/s4_experiment.py`, using the repository's existing
canonical JSON serializer: UTF-8, sorted object keys, compact separators,
`ensure_ascii=false`, and Decimal serialization without native floats. The
preimage binds the S4-A plan hash, the complete frozen candidate registry,
guardrail rules, coverage/data-quality gates, pairing invariants, budget
counting, fail-closed aggregation, multiple-comparison boundary, TEST
boundary, and the pre-execution state.

The S4-A plan remains unchanged:

```text
S4_A_PLAN_MUTATION_PERFORMED=false
EXPERIMENT_PLAN_HASH_RECOMPUTED=false
CANDIDATE_REGISTRY_CHANGED=false
MAX_VALIDATION_EVALUATIONS=32
MAX_RUNS_PER_CANDIDATE=4
ACTUAL_VALIDATION_EVALUATION_COUNT=0
CURRENT_LEDGER_ROW_COUNT=0
```

Metric evidence is identity-bound before any comparison result is emitted. The
primary metric must be `daily_wape`; the four lower-is-better guardrails must
use their exact metric names; P80/P90 observations must use `P80_COVERAGE` /
`P90_COVERAGE`; and the three coverage/data-quality observations must use
`coverage_ratio`, `valid_included_canonical_group_coverage`, and
`missing_data_proportion`, respectively. A candidate/incumbent identity
mismatch is `BLOCKED / METRIC_IDENTITY_MISMATCH` and can never become `PASS`
or `FAIL`.

## Primary metric and error guardrails

The primary selection metric is `daily_wape`, and it is lower-is-better. A
candidate is selection-eligible only when its paired VALIDATION value is
strictly less than the incumbent value. Equality is `NOT_IMPROVED` and is not
eligible; a worse value is `FAIL`; missing or non-computable evidence is
`BLOCKED`. Tolerance is exactly zero.

The lower-is-better non-regression guardrails are:

```text
daily_mae
cumulative_absolute_error_kg
single_day_peak_quantity_absolute_error_kg_q
sustained_7day_quantity_absolute_error_kg_q
```

For each, candidate value less than or equal to incumbent is `PASS`, a higher
value is `FAIL`, and missing or non-computable evidence is `BLOCKED`. No
absolute kilogram threshold is invented.

## Quantile coverage guardrails

The current P50/P80/P90 semantics remain bound to the accepted S3-B verified
claim: all three are verified true upper quantiles. S4-B does not add new S3
metric IDs. It only compares calibration distance for the two coverage
guardrails:

```text
P80_CALIBRATION_DISTANCE = abs(P80_UPPER_COVERAGE - Decimal("0.80"))
P90_CALIBRATION_DISTANCE = abs(P90_UPPER_COVERAGE - Decimal("0.90"))
```

Candidate distance less than or equal to incumbent distance is `PASS`; farther
distance is `FAIL`; missing or non-computable evidence is `BLOCKED`. All
arithmetic is Decimal-only and native floats are rejected.

## Coverage and data-quality gate

S4-B reuses the accepted S1 policy:

```text
S1_MINIMUM_COVERAGE_STATUS=PASS
MINIMUM_COVERAGE_THRESHOLD_VALUE=0.900000
MINIMUM_COVERAGE_OPERATOR=GREATER_THAN_OR_EQUAL
DATA_QUALITY_THRESHOLD_PRIMARY_VALID_COVERAGE_THRESHOLD=1.000000
DATA_QUALITY_THRESHOLD_MISSING_PROPORTION_THRESHOLD=0.000000
NO_SILENT_EXCLUSION=true
MIN_COMPARABLE_ROWS_FOR_REPORTING=10
```

The 10-row rule is a reporting-sample rule, not a model-performance
threshold. A required breakdown cell below 10 rows is retained as
`INSUFFICIENT_SAMPLE` and produces `GUARDRAIL_DECISION_STATUS=BLOCKED`; it
cannot silently become `PASS` or `FAIL` from a numeric metric.

Coverage evidence must independently contain exactly these six required axes:

```text
REQUIRED_BREAKDOWN_AXES=forecast_horizon_days,farm_business_key,subfarm_business_key,variety_business_key,season_business_key,model_identity
REQUIRED_BREAKDOWN_AXIS_COUNT=6
```

Empty evidence, a missing required axis, an unknown or duplicate axis,
conflicting axis evidence, empty required-axis cells, a below-minimum cell, or
a non-computed cell is `BLOCKED`. The six-axis requirement is distinct from
the 10-row reporting floor.

## Paired comparison and budget

Each future candidate evaluation is one paired comparison between
`V0_2_CURRENT_MODEL` and exactly one frozen candidate/run identity. It must use
the same TRAIN identity, VALIDATION identity, labels, exclusions, cutoff,
horizons, metric contract, and business grains. The Farm-total VALIDATION
baseline is not the S4 incumbent.

The gate requires these immutable, canonical lowercase SHA-256 identities:

```text
train_dataset_identity
validation_dataset_identity
actual_label_set_identity
exclusion_policy_identity
cutoff_policy_identity
forecast_horizon_set_identity
metric_contract_identity
business_grain_set_identity
common_comparable_set_identity
```

Missing, malformed, or mismatched identities fail closed. The metric contract
identity is bound to the accepted S1 owner-decision identity
`e3ff3221338863aa9128890c23e463e7a3868cd8dfc3e1b2c30c503c351a3acd`.

The paired incumbent reference is part of the same candidate invocation:

```text
PAIRED_COMPARISON_REQUIRED=true
UNPAIRED_CANDIDATE_SCORE_ALLOWED=false
COMMON_COMPARABLE_SET_REQUIRED=true
SAME_ACTUAL_LABEL_ROWS_REQUIRED=true
PAIRED_INCUMBENT_REFERENCE_IS_NOT_SEPARATELY_TRIGGERABLE=true
SEPARATE_INCUMBENT_ONLY_VALIDATION_INVOCATION_ALLOWED=false
ONE_CANDIDATE_RUN_ONE_LEDGER_ROW=true
ONE_CANDIDATE_RUN_CONSUMES_ONE_VALIDATION_EVALUATION=true
SAME_TRAIN_DATASET_REQUIRED=true
SAME_VALIDATION_DATASET_REQUIRED=true
SAME_LABELS_REQUIRED=true
SAME_EXCLUSION_POLICY_REQUIRED=true
SAME_CUTOFF_POLICY_REQUIRED=true
SAME_FORECAST_HORIZONS_REQUIRED=true
SAME_METRICS_REQUIRED=true
SAME_BUSINESS_GRAINS_REQUIRED=true
RUN_ORDINAL_COUNT_RECONCILIATION_REQUIRED=true
CANDIDATE_RUN_ORDINAL=candidate_actual_run_count+1
RETRY_COUNTS_AS_NEW_CANDIDATE_RUN=true
RETRY_REQUIRES_PARENT_IN_PRIOR_LEDGER=true
PRIOR_LEDGER_ROWS_ARE_IMMUTABLE=true
```

S4-A's budget remains 32 total evaluations and four runs per candidate. The
S4-B gate checks the plan hash, guardrail-policy hash, exact candidate
registration, candidate ordinal/count reconciliation, global count, all paired
dataset/policy identities, metric contract, TEST seal, execution manifest,
parameter manifest, code commit, seed, and evaluation identity. A retry must
use a new evaluation ID, reference an existing prior invocation through
`retry_of_evaluation_id`, consume the next run ordinal, and never overwrite a
ledger row.

## Fail-closed aggregation

The policy evaluates all required guardrails and applies this precedence:

```text
if any required evidence is missing, NOT_COMPUTABLE, or INSUFFICIENT_SAMPLE:
    GUARDRAIL_DECISION_STATUS=BLOCKED
elif any guardrail fails:
    GUARDRAIL_DECISION_STATUS=FAIL
else:
    GUARDRAIL_DECISION_STATUS=PASS
```

There is no partial `PASS`. Every required guardrail must pass for
`candidate_eligible=true`.

## Multiple comparisons and TEST boundary

The existing S4-A adjustment remains:

```text
MULTIPLE_COMPARISON_ADJUSTMENT=HOLM_BONFERRONI_OVER_PREDECLARED_PRIMARY_METRIC_COMPARISONS
HOLM_ADJUSTMENT_REQUIRES_PREDECLARED_CANDIDATE_SET=true
HOLM_ADJUSTMENT_CANDIDATE_SET_COUNT=8
HOLM_ADJUSTMENT_AFTER_CANDIDATE_RESULTS=true
HOLM_ADJUSTMENT_BEFORE_FINAL_SELECTION=true
HOLM_ADJUSTMENT_USES_VALIDATION_ONLY=true
HOLM_ADJUSTMENT_MUST_NOT_USE_TEST=true
PRIMARY_COMPARISON_PVALUE_PROTOCOL_STATUS=NOT_YET_FROZEN_FOR_FINAL_SELECTION
```

S4-B does not generate p-values or select a candidate. TEST remains sealed:

```text
TEST_ACCESS_CURRENTLY_AUTHORIZED=false
TEST_EVALUATION_AUTHORIZED=false
TEST_REMAINS_SEALED=true
SELECTED_CANDIDATE_ID=NOT_ISSUED
SELECTED_CANDIDATE_COUNT=0
MODEL_APPROVED_FOR_PILOT=false
```

## Candidate 01 boundary

Candidate `01_parameter_calibration` remains registered but is not authorized
to execute. S4-B implements only the gate infrastructure:

```text
CANDIDATE_01_EXECUTION_GATE_INFRA_IMPLEMENTED=true
CANDIDATE_01_PARAMETER_MANIFEST_FROZEN=false
CANDIDATE_01_EXECUTION_AUTHORIZED=false
CANDIDATE_01_RUN_COUNT=0
S4_CANDIDATE_EXPERIMENT_EXECUTED=false
S4_MODEL_CHANGE_AUTHORIZED=false
S4_PARAMETER_CHANGE_AUTHORIZED=false
```

No parameter values, candidate manifest, model run, training, TEST read, or
VALIDATION evaluation is created by S4-B.
