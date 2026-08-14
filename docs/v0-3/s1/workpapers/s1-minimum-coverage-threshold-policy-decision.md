# S1 Minimum Coverage Threshold Policy Decision — Owner Binding R1

## Current result

```text
TASK=V0_3_S1_MINIMUM_COVERAGE_THRESHOLD_POLICY_DECISION_OWNER_BINDING_R1
RESULT=POLICY_DECISION_ISSUED_AND_INDEPENDENTLY_REVIEWED
BASE_MAIN_SHA=b96fc39fcee50c2447e7bcc90580745b090d8646
GATE_ID=S1-MINIMUM-COVERAGE
DECISION_ID=S1_MINIMUM_COVERAGE_THRESHOLD_POLICY
OWNER_ROLE=model_validation_owner_role
OWNER_IDENTITY=xuezhiorange-png
OWNER_DECISION_SOURCE=github-issue-220-comment-5294054162
```

This revision binds the explicit owner decision recorded in Issue #220. The
policy is issued and the exact-head independent review recorded on PR #219
passed. The policy therefore satisfies the evidence and review requirements
for the standalone S1 minimum-coverage gate. The canonical S1 acceptance
package remains blocked because the other required gates remain unresolved.

## Governing authority

`S1-REMAINING-05` requires an external, versioned owner decision covering threshold identity/version, unit, application grain and scope, denominator definition, failure semantics, horizon variation, partition variation, provenance, and independent review.

The S3 contract supplies the adopted coverage measure:

```text
THRESHOLD_MEASURE=S3_COVERAGE_RATIO
THRESHOLD_MEASURE_FORMULA=s2_comparable_binding_row_count / s2_total_binding_row_count
S3_MIN_COMPARABLE_ROWS_FOR_REPORTING=10
S3_REPORTING_FLOOR_IS_S1_THRESHOLD=false
```

The reporting floor `10` remains separate S3 reporting/sample-size semantics. It is not promoted into the S1 minimum-coverage threshold.

## Issued owner decision

```text
OWNER_IDENTITY=xuezhiorange-png
OWNER_ROLE_ATTESTATION=I_AM_ACTING_AS_MODEL_VALIDATION_OWNER_ROLE
OWNER_PROVENANCE=AUTHENTICATED_REPOSITORY_OWNER_EXPLICIT_INTERACTIVE_APPROVAL_2026-08-14
DECIDED_AT=2026-08-14T21:46:00+08:00

POLICY_VERSION=v0-3-s1-minimum-coverage-threshold-v1
THRESHOLD_VALUE=0.900000
THRESHOLD_OPERATOR=GREATER_THAN_OR_EQUAL
THRESHOLD_UNIT=RATIO_0_TO_1
APPLICATION_GRAIN=EVALUATION_PARTITION_X_FORECAST_HORIZON_X_SEASON_X_FARM_X_SUBFARM_X_VARIETY_X_MODEL_IDENTITY
APPLICATION_SCOPE=ALL_GOVERNED_S1_EVALUATION_PARTITIONS_AND_REQUIRED_S3_BREAKDOWN_CELLS
DENOMINATOR_DEFINITION=COUNT_ALL_S2_BINDING_ROWS_IN_EXACT_APPLICATION_CELL
ZERO_DENOMINATOR_SEMANTICS=FAIL_CLOSED_NO_PERCENTAGE_S1_MINIMUM_COVERAGE_GATE_NOT_PASS
BELOW_THRESHOLD_SEMANTICS=FAIL_S1_MINIMUM_COVERAGE_GATE_WITH_BELOW_MINIMUM
THRESHOLD_VARIES_BY_HORIZON=false
HORIZON_POLICY=SAME_0.900000_THRESHOLD_FOR_7_14_21
THRESHOLD_VARIES_BY_PARTITION=false
PARTITION_POLICY=SAME_0.900000_THRESHOLD_FOR_TRAIN_VALIDATION_TEST_EVALUATED_INDEPENDENTLY
```

The threshold is evaluated independently for each governed application cell. A cell passes the coverage policy only when its S3 `coverage_ratio` is greater than or equal to `0.900000`. A zero denominator never produces an artificial percentage and fails closed for this gate. A non-zero denominator with coverage below `0.900000` fails the S1 minimum-coverage gate with `BELOW_MINIMUM` semantics.

The same threshold applies to horizons 7, 14, and 21 days, and to TRAIN, VALIDATION, and TEST partitions when those partitions are separately authorized and evaluated. This policy definition does not itself authorize TEST access.

## Historical correction and current authority

The prior unauthorized head also contained the numeric value `0.900000`. That earlier occurrence remains non-authoritative and must not be cited as precedent.

```text
PREVIOUS_UNAUTHORIZED_THRESHOLD_VALUE=0.900000
PREVIOUS_VALUE_HAS_AUTHORITY=false
CURRENT_0_900000_IS_NEW_OWNER_DECISION=true
CURRENT_0_900000_AUTHORITY_SOURCE=github-issue-220-comment-5294054162
OWNER_DECISION_SUPERSEDES_WITHDRAWN_PR219_VALUE=true
```

The current owner independently selected the same numeric value after the correction restored the external owner-decision boundary. Authority therefore comes only from the new owner decision source, not from the withdrawn earlier head.

## Rationale

The `0.900000` threshold is a policy choice, not an empirical inference from Source 002. It permits at most 10% of binding rows in an application cell to be non-comparable while requiring the large majority of the governed rowset to remain usable for evaluation. Applying one threshold across horizons and partitions prevents the threshold itself from being tuned to a favorable horizon or evaluation partition.

```text
SOURCE_002_STATISTICS_USED_TO_INFER_THRESHOLD=false
THRESHOLD_TUNED_ON_TEST=false
TEST_DATA_ACCESS=false
```

## Decision identity

The canonical owner-decision payload is serialized as UTF-8 JSON with sorted keys and compact separators `,` and `:` and is SHA-256 bound as:

```text
OWNER_DECISION_SHA256=a9361145eaa04e93e6b7bc3a4e4faa7a42c542b29de4978988658f53fa11f692
```

This identity binds the owner, provenance, timestamp, policy version, threshold measure and value, application semantics, denominator/failure behavior, horizon/partition policies, and the explicit distinction between the S3 reporting floor and the S1 threshold.

## Independent review and exact-head CI

```text
INDEPENDENT_REVIEW_ID=4937929668
INDEPENDENT_REVIEWED_HEAD=5775e908cfe072fa962c99e822901b7157128418
INDEPENDENT_REVIEW_RESULT=PASS
OWNER_DECISION_PAYLOAD_BINDING=PASS
OWNER_DECISION_HASH_REPLAY=PASS
OWNER_DECISION_SHA256=a9361145eaa04e93e6b7bc3a4e4faa7a42c542b29de4978988658f53fa11f692
EXACT_HEAD_CI_RUN_ID=31806575112
EXACT_HEAD_CI_HEAD_SHA=5775e908cfe072fa962c99e822901b7157128418
EXACT_HEAD_CI_STATUS=completed
EXACT_HEAD_CI_CONCLUSION=success
```

The review is bound to the merged PR #219 head and independently replayed the
owner decision payload/hash. It closes only `S1-MINIMUM-COVERAGE`; it does not
accept the metric contract, source cohort, data quality policy, split policy,
holdout feasibility, or the overall S1 package.

## Independent rules that remain unchanged

Nothing in this decision weakens existing S2/S3 rules. In particular:

- S2 row-status semantics remain authoritative;
- S3 structural duplicate failures remain fail-closed;
- exact actual-pair requirements for quantile coverage remain intact;
- P50/P80/P90 semantic-verification gates remain intact;
- complete daily-rowset requirements for cumulative and peak/window metrics remain intact;
- complete seven-day-window requirements remain intact;
- `MIN_COMPARABLE_ROWS_FOR_REPORTING=10` remains an S3 reporting-floor rule only; and
- TEST access remains separately gated.

## Current gate boundary

```text
POLICY_DECISION_ISSUED=true
POLICY_INDEPENDENTLY_REVIEWED=true
S1_MINIMUM_COVERAGE_GATE_PASS=true
CANONICAL_ACCEPTANCE_RECORD_CHANGED=true
SOURCE_002_RAW_READ=false
SOURCE_002_ROW_LEVEL_READ=false
BACKTEST_EXECUTED=false
MODEL_TRAINING_EXECUTED=false
TEST_DATA_ACCESS=false
S1_REMAINING_06_AUTHORIZED=false
V0_3_S2_AUTHORIZED=false
```

The owner-decision and independent-review requirements are closed for this
policy. The canonical acceptance record separately records the standalone gate
as `PASS`; the overall S1 package remains `BLOCKED` until all other required
gates and the final independent S1 review are complete.

```text
NEXT_GATE=S1_REMAINING_05_DOWNSTREAM_RECONCILIATION
NEXT_GATE_AUTHORIZED=false
READY_AUTHORIZED=true
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```
