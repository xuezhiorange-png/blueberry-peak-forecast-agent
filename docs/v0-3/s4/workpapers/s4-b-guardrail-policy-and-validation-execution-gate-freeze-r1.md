# S4-B workpaper — guardrail policy and VALIDATION execution gate

## Scope

This workpaper records the S4-B policy overlay required before any candidate
run. It is not a candidate execution record. No candidate, model, parameter,
training, TEST, or validation evaluation was executed.

```text
TASK_ID=V0_3_S4_B_GUARDRAIL_POLICY_AND_VALIDATION_EXECUTION_GATE_FREEZE_R1
BASE_MAIN_SHA=2d2b6a63a84e23e91e14f1929ad953fac4f87b0d
PR582_MERGE_IN_BASE=true
S4_A_EXPERIMENT_PLAN_HASH_BOUND=9e223a02a1b38c028c230a45eb1fa8323f3c2247bb85e7b439f3351e51042500
GUARDRAIL_POLICY_VERSION=v0.3-s4-guardrail-policy-v1
GUARDRAIL_POLICY_HASH=74ecd47339572955e654cf61c38ee6b0546ba51a36e67f80f6ad4dd4519f1ff8
GUARDRAIL_POLICY_HASH_REPLAY=PASS
OLD_GUARDRAIL_POLICY_HASH=0a910697cf5588383e117df8a22e3826b0d21b9dda38cef490698ad89560a27f
OLD_GUARDRAIL_POLICY_HASH_INVALIDATED_BY_CORRECTION=true
```

The policy hash is generated from the complete policy preimage in the new pure
deterministic S4 module with the existing repository canonical JSON/SHA-256
implementation. The preimage rejects native floats and binds the S4-A plan
identity, exact candidate registry, all comparison rules, data-quality gates,
budget rules, multiple-comparison boundary, TEST boundary, and frozen
execution state.

Metric identity is part of the executable gate. `daily_wape` is required for
the primary comparison; each lower-is-better guardrail must carry its own exact
metric name; P80 and P90 coverage observations must be named
`P80_COVERAGE` and `P90_COVERAGE`; and coverage/data-quality observations must
be named `coverage_ratio`, `valid_included_canonical_group_coverage`, and
`missing_data_proportion`. Any candidate/incumbent mismatch is
`BLOCKED / METRIC_IDENTITY_MISMATCH`.

## Accepted comparison policy

The primary selection metric is `daily_wape`, lower-is-better, with zero
tolerance and a strict candidate improvement requirement:

```text
candidate_daily_wape < incumbent_daily_wape => PASS
candidate_daily_wape = incumbent_daily_wape => FAIL / NOT_IMPROVED
candidate_daily_wape > incumbent_daily_wape => FAIL
missing or NOT_COMPUTABLE => BLOCKED
```

The incumbent is `V0_2_CURRENT_MODEL`. Farm-total VALIDATION baseline results
are not an S4 incumbent comparison.

The four error guardrails are `daily_mae`,
`cumulative_absolute_error_kg`,
`single_day_peak_quantity_absolute_error_kg_q`, and
`sustained_7day_quantity_absolute_error_kg_q`. Each is lower-is-better with
zero tolerance: equality and improvement pass; regression fails; missing or
non-computable evidence blocks.

For verified true upper quantiles, S4-B compares distance to nominal rather
than raw coverage direction:

```text
P80 distance = abs(P80 upper coverage - Decimal("0.80"))
P90 distance = abs(P90 upper coverage - Decimal("0.90"))
candidate distance <= incumbent distance => PASS
farther distance => FAIL
missing or NOT_COMPUTABLE => BLOCKED
```

These transforms are guardrail comparisons only; they do not create new S3
metric IDs. All arithmetic is Decimal-only.

## S1 coverage and data-quality binding

The accepted S1 policy is reused without new thresholds:

```text
S1_MINIMUM_COVERAGE_STATUS=PASS
MINIMUM_COVERAGE_THRESHOLD_VALUE=0.900000
MINIMUM_COVERAGE_OPERATOR=GREATER_THAN_OR_EQUAL
DATA_QUALITY_THRESHOLD_PRIMARY_VALID_COVERAGE_THRESHOLD=1.000000
DATA_QUALITY_THRESHOLD_MISSING_PROPORTION_THRESHOLD=0.000000
NO_SILENT_EXCLUSION=true
```

`MIN_COMPARABLE_ROWS_FOR_REPORTING=10` remains a reporting-sample rule. A
required breakdown cell below 10 rows is retained as `INSUFFICIENT_SAMPLE`
and blocks the complete guardrail decision; it is not silently passed or
failed based on a numeric value.

The coverage evidence must contain all six independently identified axes:

```text
REQUIRED_BREAKDOWN_AXES=forecast_horizon_days,farm_business_key,subfarm_business_key,variety_business_key,season_business_key,model_identity
REQUIRED_BREAKDOWN_AXIS_COUNT=6
```

Empty, missing, unknown, duplicate, or conflicting axes, empty axis cells,
below-minimum cells, and non-computed cells fail closed.

## Paired evaluation and budget accounting

Every future candidate invocation must contain exactly one paired incumbent /
candidate comparison with the same TRAIN identity, VALIDATION identity,
labels, exclusions, cutoff, horizons, metric contract, and business grains.
The incumbent reference is not a separate invocation and consumes no separate
budget unit.

The shared comparison identity set is mandatory and must be canonical,
lowercase SHA-256: `train_dataset_identity`,
`validation_dataset_identity`, `actual_label_set_identity`,
`exclusion_policy_identity`, `cutoff_policy_identity`,
`forecast_horizon_set_identity`, `metric_contract_identity`,
`business_grain_set_identity`, and `common_comparable_set_identity`.
The metric-contract identity is the accepted S1 owner-decision identity
`e3ff3221338863aa9128890c23e463e7a3868cd8dfc3e1b2c30c503c351a3acd`.

```text
PAIRED_COMPARISON_REQUIRED=true
UNPAIRED_CANDIDATE_SCORE_ALLOWED=false
COMMON_COMPARABLE_SET_REQUIRED=true
SAME_ACTUAL_LABEL_ROWS_REQUIRED=true
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
MAX_VALIDATION_EVALUATIONS=32
MAX_RUNS_PER_CANDIDATE=4
ACTUAL_VALIDATION_EVALUATION_COUNT=0
CURRENT_LEDGER_ROW_COUNT=0
```

The gate requires exact S4-A plan and S4-B policy identities, registered
candidate identity, ordinal/count reconciliation, all paired dataset/policy
identities, metric contract, TEST seal, frozen execution manifest, parameter
manifest, code commit, seed, and evaluation identity. Unknown candidates, hash
mismatches, exhausted budgets, TEST access, missing or malformed identities,
missing manifests, native-float policy payloads, and retry identity reuse are
rejected. A retry must use a new evaluation ID, reference an existing prior
evaluation, consume the next ordinal, and never overwrite a ledger row.

## Fail-closed decision precedence

```text
required evidence missing / NOT_COMPUTABLE / INSUFFICIENT_SAMPLE => BLOCKED
else any required guardrail FAIL => FAIL
else all required guardrails PASS => PASS and candidate_eligible=true
```

Partial PASS is forbidden. The focused test suite covers better, equal,
smallest Decimal regression, missing evidence, non-computable evidence,
insufficient samples, P80/P90 distance rules, Decimal-only behavior, policy
hash replay/mutation, every requested gate rejection, and complete PASS
aggregation.

## Multiple comparison and TEST boundary

The S4-A policy remains `HOLM_BONFERRONI_OVER_PREDECLARED_PRIMARY_METRIC_COMPARISONS`.
S4-B records the future boundary only: the candidate set is predeclared as
eight, adjustment occurs after candidate results and before final selection,
uses VALIDATION only, and never uses TEST. The primary comparison p-value
protocol remains `NOT_YET_FROZEN_FOR_FINAL_SELECTION`; no p-values are
invented here. This does not authorize Candidate 01 metric execution, but it
does prevent final selected-candidate issuance until separately accepted.

```text
TEST_ACCESS_CURRENTLY_AUTHORIZED=false
TEST_EVALUATION_AUTHORIZED=false
TEST_REMAINS_SEALED=true
SELECTED_CANDIDATE_ID=NOT_ISSUED
SELECTED_CANDIDATE_COUNT=0
MODEL_APPROVED_FOR_PILOT=false
```

## Candidate 01 and non-execution evidence

```text
CANDIDATE_01_EXECUTION_GATE_INFRA_IMPLEMENTED=true
CANDIDATE_01_PARAMETER_MANIFEST_FROZEN=false
CANDIDATE_01_EXECUTION_AUTHORIZED=false
CANDIDATE_01_RUN_COUNT=0
S4_CANDIDATE_EXPERIMENT_EXECUTED=false
S4_MODEL_CHANGE_AUTHORIZED=false
S4_PARAMETER_CHANGE_AUTHORIZED=false
S4_ALLOWLIST_EXPANSION_AUTHORIZED=false
S4_METRIC_EXECUTION_PERFORMED=false
S4_METRIC_RESULT_ISSUED=false
MIGRATION_REQUIRED=false
```

The eight-candidate registry, S4-A plan hash, and S4-A budget are unchanged.
No S4-B action reopens S3, releases V0.3, or authorizes a candidate run.
