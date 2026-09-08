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
GUARDRAIL_POLICY_HASH=0a910697cf5588383e117df8a22e3826b0d21b9dda38cef490698ad89560a27f
GUARDRAIL_POLICY_HASH_REPLAY=PASS
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

## Paired comparison and budget

Each future candidate evaluation is one paired comparison between
`V0_2_CURRENT_MODEL` and exactly one frozen candidate/run identity. It must use
the same TRAIN identity, VALIDATION identity, labels, exclusions, cutoff,
horizons, metric contract, and business grains. The Farm-total VALIDATION
baseline is not the S4 incumbent.

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
```

S4-A's budget remains 32 total evaluations and four runs per candidate. The
S4-B gate checks the plan hash, guardrail-policy hash, exact candidate
registration, candidate ordinal and counts, global count, dataset identities,
metric contract, TEST seal, execution manifest, parameter manifest, code
commit, seed, and evaluation identity. A retry must use a new evaluation ID
and reference `retry_of_evaluation_id`; no ledger row is overwritten.

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
