# S1-REMAINING-05 Threshold, Metric, Split, and Holdout Decision Readiness

## 1. Scope and authority

TASK_ID=S1-REMAINING-05
TASK_CLASS=DOCS_ONLY_DECISION_AND_POLICY_READINESS
BASE_MAIN_SHA=0ed98ee8fa51601f939315a6cfc08e2b690e1bc1
CURRENT_MAIN_REVALIDATED_SHA=e77aff78f74740dde0d9b0e612e661afb0e6e0db
READINESS_PACKAGE_ONLY=true
NO_STEP_IMPLIES_THE_NEXT=true

This package prepares decision and policy readiness for threshold, metric,
split, and holdout work. The minimum-coverage policy is now issued and
independently reviewed, and its standalone canonical gate is closed by the
post-PR #219 closeout. This package still does not accept a metric contract,
accept a split, decide holdout feasibility, accept custody, complete
Remaining-05, or authorize any later S1/S2 task.

The authoritative runtime registry remains canonical; this closeout changes
only the standalone minimum-coverage row:

| State | Value |
| --- | --- |
| CANONICAL_GATE_COUNT | 17 |
| CURRENT_CANONICAL_GATE_PASS_COUNT | 1 |
| CURRENT_CANONICAL_GATE_BLOCKED_COUNT | 16 |
| CANONICAL_GATE_STATUS_CHANGED | true |
| CANONICAL_ACCEPTANCE_RECORD_CHANGED | true |
| V0_3_S1_COMPLETE | false |
| V0_3_S1_ACCEPTED | false |
| S1_REMAINING_06_AUTHORIZED | false |
| V0_3_S2_AUTHORIZED | false |
| V0_3_S2_STARTED | false |

CURRENT_CANONICAL_GATE_PASS_COUNT=1
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=16

Authoritative inputs reviewed:

- docs/v0-3/s1/s1-acceptance-package.md
- docs/v0-3/s1/split-holdout-and-custody-contract.md
- docs/v0-3/s1/metric-coverage-and-quality-contract.md
- docs/v0-3/s1/workpapers/canonical-acceptance-gate-current-main-reconciliation.md
- docs/v0-3/s1/evidence/s1-acceptance-record.json
- docs/v0-3/s1/evidence/source-cohort-manifest-candidate.json
- docs/v0-3/s1/evidence/data-custody-evidence-status.md
- docs/v0-3/s1/evidence/source-002-custody-record.json
- docs/v0-3/s1/evidence/threshold-decision-evidence-status.md
- docs/v0-3/s1/evidence/holdout-feasibility-evidence-status.md
- docs/forecast-quality/s3-quality-metrics-contract.md

## 2. Current decision state

| Domain | Current state | What this package does | What it does not do |
| --- | --- | --- | --- |
| Minimum coverage | ISSUED_AND_INDEPENDENTLY_REVIEWED / gate PASS | Binds the owner policy, SHA, independent review, and exact-head CI | Does not execute coverage or close any downstream gate |
| Data quality thresholds | DECISION_REQUIRED / gate BLOCKED | Enumerates the required policy dimensions | Does not derive policy from Source 002 statistics |
| Metric contract | PREPARED_NOT_ACCEPTED / gate BLOCKED | Binds the current version and canonical metric registry | Does not execute metrics or issue results |
| Split policy | CANDIDATE_NOT_ACCEPTED / gate BLOCKED | Provides a versioned time-ordered candidate and partition purposes | Does not materialize any rowset or authorize TEST access |
| Holdout feasibility | NOT_EVALUATED / gate BLOCKED | Provides feasibility criteria and conditional usage rules | Does not access or materialize external holdout data |
| Data custody | ISSUED_FOR_INDEPENDENT_REVIEW / gate BLOCKED | Reuses the existing custody identity and hash | Does not accept custody |

## 3. Minimum coverage decision closeout

The S1 minimum-coverage threshold is now issued and independently reviewed.
The only numeric value that remains a reporting-floor fact is:

MIN_COMPARABLE_ROWS_FOR_REPORTING=10
MIN_COMPARABLE_ROWS_IS_S3_REPORTING_FLOOR=true
MIN_COMPARABLE_ROWS_IS_S1_MINIMUM_COVERAGE_THRESHOLD=false

The value 10 is not copied into the S1 threshold. The model-validation owner
decision is bound by:

1. `POLICY_VERSION=v0-3-s1-minimum-coverage-threshold-v1`;
2. `THRESHOLD_VALUE=0.900000`, operator `GREATER_THAN_OR_EQUAL`, unit
   `RATIO_0_TO_1`;
3. the governed application grain and scope;
4. the exact-cell denominator and fail-closed zero-denominator semantics;
5. the common 7/14/21-day horizon policy and independent TRAIN/VALIDATION/TEST
   partition policy; and
6. owner decision SHA, independent review, and exact-head CI provenance.

| Field | Value |
| --- | --- |
| DECISION_ID | S1_MINIMUM_COVERAGE_THRESHOLD_POLICY |
| CURRENT_STATUS | CLOSED_BY_INDEPENDENT_REVIEW |
| CANDIDATE_VALUE | 0.900000 |
| ACCEPTED_VALUE | 0.900000 |
| EXTERNAL_DECISION_REQUIRED | false |
| CAN_BE_INFERRED | false |
| CAN_BE_DECIDED_IN_CURRENT_TASK | false |
| BLOCK_REASON | NONE |
| OWNER_DECISION_SHA256 | `a9361145eaa04e93e6b7bc3a4e4faa7a42c542b29de4978988658f53fa11f692` |
| INDEPENDENT_REVIEW_ID | `4937929668` |
| INDEPENDENT_REVIEWED_HEAD | `5775e908cfe072fa962c99e822901b7157128418` |
| EXACT_HEAD_CI_RUN_ID | `31806575112` |
| EXACT_HEAD_CI_CONCLUSION | `success` |

No row count, farm count, subfarm count, variety count, or observed fixture
distribution was treated as threshold authority. The minimum-coverage gate
is the only Task05 domain closed by this closeout.

## 4. Data-quality threshold decision request

No approved, versioned S1 data-quality policy is present. The decision owner
is data_quality_owner_role. The decision must cover:

- missing-day policy;
- missing-data proportion threshold;
- duplicate/conflicting-record policy;
- invalid canonical-grain identity policy;
- unmapped identity/date handling;
- revision/void consistency requirement;
- completeness requirement;
- source-row lineage requirement; and
- canonical-group coverage requirement.

| Field | Value |
| --- | --- |
| DECISION_ID | S1_DATA_QUALITY_THRESHOLD_POLICY |
| CURRENT_STATUS | DECISION_REQUIRED |
| CANDIDATE_VALUE | null |
| ACCEPTED_VALUE | null |
| EXTERNAL_DECISION_REQUIRED | true |
| CAN_BE_INFERRED | false |
| CAN_BE_DECIDED_IN_CURRENT_TASK | false |
| BLOCK_REASON | NO_APPROVED_VERSIONED_DATA_QUALITY_THRESHOLD_POLICY |

The package deliberately contains no proposed numeric quality threshold and
does not infer policy from Source 002 aggregate statistics.

## Remaining-05 completion boundary

```text
S1_REMAINING_05_COMPLETE=false
REMAINING_BLOCKERS=(
  DATA_QUALITY_THRESHOLD,
  SOURCE_COHORT,
  SOURCE_INCLUSION,
  SOURCE_VISIBILITY,
  SOURCE_CUSTODY,
  METRIC_CONTRACT_FREEZE,
  TIME_ORDERED_SPLIT_FREEZE,
  HOLDOUT_FEASIBILITY,
  FINAL_INDEPENDENT_S1_ACCEPTANCE
)
```

The minimum-coverage row is not included in this remaining-blocker list
because its standalone gate is closed. The listed items were re-read after
the PR #219 merge and remain unresolved; no downstream gate is promoted by
this closeout.

## 5. Metric contract freeze readiness

The current contract identity is:

V0_3_METRIC_CONTRACT_VERSION=v0.3-metric-contract-v1
CURRENT_METRIC_EXECUTION_STATUS=NOT_EXECUTED
CURRENT_METRIC_RESULT_STATUS=NOT_ISSUED
METRIC_REGISTRY_BOUND=true
S1_METRIC_CONTRACT_CANONICAL_GATE_PASS=false

The machine-readable registry in the companion JSON binds these 22 canonical
S3 metric identities:

| Metric identity group | Canonical IDs |
| --- | --- |
| Daily point metrics | daily_mae, daily_wape, daily_smape, daily_mape, daily_bias_kg, daily_relative_bias, daily_absolute_error_sum_kg |
| Cumulative season metrics | cumulative_signed_error_kg, cumulative_absolute_error_kg, cumulative_signed_relative_error, cumulative_absolute_relative_error |
| Single-day peak metrics | single_day_peak_date_signed_error_days_q, single_day_peak_date_absolute_error_days_q, single_day_peak_quantity_signed_error_kg_q, single_day_peak_quantity_absolute_error_kg_q |
| Sustained seven-day peak metrics | sustained_7day_start_date_signed_error_days_q, sustained_7day_start_date_absolute_error_days_q, sustained_7day_quantity_signed_error_kg_q, sustained_7day_quantity_absolute_error_kg_q |
| Quantile coverage metrics | P50_UPPER_COVERAGE, P80_UPPER_COVERAGE, P90_UPPER_COVERAGE |

The registry preserves the existing planning crosswalk:

| Planning identity | S3 binding |
| --- | --- |
| P80_COVERAGE | P80_UPPER_COVERAGE |
| P90_COVERAGE | P90_UPPER_COVERAGE |
| P80_UPPER_QUANTILE_SPREAD | planning alias only; formula P80-P50 |
| P90_UPPER_QUANTILE_SPREAD | planning alias only; formula P90-P50 |
| BASELINE_P80 / BASELINE_P90 | status fields, not canonical metric IDs |
| QUANTILE_CALIBRATION | status field over verified quantile semantics |
| SINGLE_DAY_PEAK | S3 section 9.1 field set |
| SUSTAINED_7DAY_PEAK | S3 section 9.2 field set |
| ROLLING_COMPARISON | S3 section 16.5 comparison-group field set |

P80_UPPER_QUANTILE_SPREAD and P90_UPPER_QUANTILE_SPREAD are not prediction
interval widths. No metric is executed by this package.

| Field | Value |
| --- | --- |
| DECISION_ID | S1_METRIC_CONTRACT_FREEZE_AND_ACCEPTANCE |
| CURRENT_STATUS | PREPARED_NOT_ACCEPTED |
| ACCEPTED_VALUE | null |
| EXTERNAL_DECISION_REQUIRED | true |
| CAN_BE_INFERRED | false |
| CAN_BE_DECIDED_IN_CURRENT_TASK | false |
| BLOCK_REASON | UPSTREAM_SOURCE_TARGET_ROWSET_THRESHOLD_AND_DATA_QUALITY_PREREQUISITES_NOT_ACCEPTED |

## 6. Candidate time-ordered split policy

SPLIT_POLICY_VERSION_CANDIDATE=v0-3-s1-time-ordered-split-policy-v1
SPLIT_POLICY_STATUS=CANDIDATE_NOT_ACCEPTED
TRAIN_POLICY_DEFINED=true
VALIDATION_POLICY_DEFINED=true
TEST_POLICY_DEFINED=true
REQUIRED_DATASET_SPLITS=TRAIN,VALIDATION,TEST
EXTERNAL_HOLDOUT_POLICY=CONDITIONAL_ON_S1_FEASIBILITY_GATE
RANDOM_ADJACENT_DATE_SPLIT_ALLOWED=false
TEST_SEAL_IS_NOT_TEST_ACCESS_AUTHORIZATION=true
TEST_ACCESS_CURRENTLY_AUTHORIZED=false

Candidate rules:

- use complete time intervals or complete seasons;
- do not use adjacent-date random splitting as the primary evaluation method;
- do not expose future labels or future source revisions at an earlier cutoff;
- bind source lineage, mapping identity, visibility identity,
  inclusion/exclusion identity, revision/winner disposition, custody identity,
  and requested horizons;
- freeze the manifest identity and hash, blocking on source, mapping, revision,
  or custody drift;
- keep TRAIN, VALIDATION, and TEST purposes distinct;
- seal TEST before candidate tuning, while treating the seal separately from
  access authorization; and
- do not materialize any TRAIN, VALIDATION, TEST, or external-holdout rowset
  in this task.

| Partition | Purpose | Access in this task |
| --- | --- | --- |
| TRAIN | candidate fitting only | not authorized |
| VALIDATION | candidate selection and validation only | not authorized |
| TEST | sealed final evaluation only | not authorized |

The historical Task03 candidate is not mutated. Task05 only references:

SOURCE_COHORT_CANDIDATE_REFERENCE=docs/v0-3/s1/evidence/source-cohort-manifest-candidate.json
HISTORICAL_TASK03_SPLIT_POLICY_VERSION=null
SPLIT_POLICY_VERSION_CANDIDATE=v0-3-s1-time-ordered-split-policy-v1

The split candidate remains blocked because source cohort, inclusion, visibility,
metric, and custody prerequisites are not accepted.

| Field | Value |
| --- | --- |
| DECISION_ID | S1_SPLIT_POLICY_FREEZE_AND_ACCEPTANCE |
| CURRENT_STATUS | CANDIDATE_NOT_ACCEPTED |
| CANDIDATE_VALUE | v0-3-s1-time-ordered-split-policy-v1 |
| ACCEPTED_VALUE | null |
| EXTERNAL_DECISION_REQUIRED | true |
| CAN_BE_INFERRED | false |
| CAN_BE_DECIDED_IN_CURRENT_TASK | false |
| BLOCK_REASON | SOURCE_COHORT_VISIBILITY_METRIC_CUSTODY_AND_THRESHOLD_PREREQUISITES_NOT_ACCEPTED |

## 7. Holdout feasibility criteria

The current decision remains:

CURRENT_S1_HOLDOUT_FEASIBILITY_DECISION=NOT_EVALUATED
CURRENT_S1_HOLDOUT_FEASIBILITY_REVIEWED=false
EXTERNAL_HOLDOUT_DATA_ACCESS=false

The feasibility decision requires:

1. an independent source cohort, farm, or season boundary;
2. proof that the boundary was not used for candidate tuning;
3. canonical-grain coverage meeting an approved threshold;
4. an independent custody record;
5. a frozen split identity; and
6. a satisfied leakage boundary.

If reviewed FEASIBLE, external holdout is FINAL_GENERALIZATION_ONLY and is not
permitted for tuning, feature selection, or threshold selection. If reviewed
NOT_FEASIBLE, the decision must record the reason and may close the required
feasibility gate without materializing an external holdout. Neither conditional
outcome is selected here.

| Field | Value |
| --- | --- |
| DECISION_ID | S1_HOLDOUT_FEASIBILITY_DECISION |
| CURRENT_STATUS | NOT_EVALUATED |
| CANDIDATE_VALUE | CRITERIA_PREPARED_NO_OUTCOME_SELECTED |
| ACCEPTED_VALUE | null |
| EXTERNAL_DECISION_REQUIRED | true |
| CAN_BE_INFERRED | false |
| CAN_BE_DECIDED_IN_CURRENT_TASK | false |
| BLOCK_REASON | SOURCE_COHORT_COVERAGE_CUSTODY_SPLIT_AND_INDEPENDENT_REVIEW_PREREQUISITES_NOT_ACCEPTED |

## 8. Custody binding

Task05 reuses the existing artifact without accepting it:

CUSTODY_RECORD_REFERENCE=source-002-custody-record-v1
CUSTODY_RECORD_HASH=99edffb9d076e9ab938a9021e1950a7d909dd7303e6d4677a46a5c1b8db8dde6
EXTERNAL_OBJECT_BINDING_HASH=1d64cc5e4e1e06fb40065e3e8a0dfc3da56d20afb04300db4c5c58d5c5243ece
CUSTODY_RECORD_STATUS=ISSUED_FOR_INDEPENDENT_REVIEW
S1_DATA_CUSTODY_ACCEPTED=false

The custody identity is bound for future split/holdout artifacts. No new
storage locator, credential, source row, or custody decision is created.

| Field | Value |
| --- | --- |
| DECISION_ID | S1_TASK05_CUSTODY_ARTIFACT_BINDING_REVIEW |
| CURRENT_STATUS | ISSUED_FOR_INDEPENDENT_REVIEW |
| CANDIDATE_VALUE | BIND_EXISTING_CUSTODY_RECORD_IDENTITY_AND_HASH |
| ACCEPTED_VALUE | null |
| EXTERNAL_DECISION_REQUIRED | true |
| CAN_BE_INFERRED | false |
| CAN_BE_DECIDED_IN_CURRENT_TASK | false |
| BLOCK_REASON | CUSTODY_RECORD_ACCEPTANCE_REVIEW_NOT_COMPLETED |

## 9. Decision matrix summary

| Decision ID | Gate | Current status | Owner | External decision | Candidate / accepted value | Remaining blocker |
| --- | --- | --- | --- | --- | --- | --- |
| S1_MINIMUM_COVERAGE_THRESHOLD_POLICY | S1-MINIMUM-COVERAGE | CLOSED_BY_INDEPENDENT_REVIEW | model_validation_owner_role | no | 0.900000 / 0.900000 | closed by owner decision, review `4937929668`, and exact-head CI `31806575112` |
| S1_DATA_QUALITY_THRESHOLD_POLICY | S1-DATA-QUALITY-THRESHOLDS | DECISION_REQUIRED | data_quality_owner_role | yes | null / null | no approved quality policy |
| S1_METRIC_CONTRACT_FREEZE_AND_ACCEPTANCE | S1-METRIC-CONTRACT | PREPARED_NOT_ACCEPTED | model_validation_owner_role | yes | registry candidate / null | upstream prerequisites |
| S1_SPLIT_POLICY_FREEZE_AND_ACCEPTANCE | S1-SPLIT-POLICY | CANDIDATE_NOT_ACCEPTED | model_validation_owner_role | yes | v1 candidate / null | cohort, visibility, metric, custody |
| S1_HOLDOUT_FEASIBILITY_DECISION | S1-HOLDOUT-FEASIBILITY | NOT_EVALUATED | model_validation_owner_role | yes | criteria only / null | upstream evidence and review |
| S1_TASK05_CUSTODY_ARTIFACT_BINDING_REVIEW | S1-DATA-CUSTODY | ISSUED_FOR_INDEPENDENT_REVIEW | data_governance_owner_role | yes | existing identity / null | custody review not complete |

UNAUTHORIZED_THRESHOLD_VALUE_COUNT=0. The S1 value `0.900000` is authorized
only by the versioned owner decision and its independent review. The separate
S3 reporting floor 10 remains excluded from S1 threshold semantics.

## 10. Dependency order

Task05 does not authorize execution of the following queue. It records the
dependency order for later separately authorized work:

1. resolve and independently review the S1 data-quality threshold policy;
2. complete source cohort, inclusion, visibility prerequisites, and custody
   review;
3. freeze and independently review the metric contract;
4. freeze and independently review the time-ordered split policy;
5. evaluate holdout feasibility after cohort, threshold, split, and custody
   prerequisites are accepted; and
6. only after all canonical gates are otherwise closed, run final independent
   S1 acceptance review.

## 11. Safety and non-acceptance boundary

SOURCE_002_RAW_READ=false
SOURCE_002_ROW_LEVEL_READ=false
REAL_BUSINESS_DATA_READ=false
PRODUCTION_DATABASE_READ=false
TEST_DATA_ACCESS=false
EXTERNAL_HOLDOUT_DATA_ACCESS=false
BACKTEST_EXECUTED=false
MODEL_TRAINING_EXECUTED=false
METRIC_EXECUTION_PERFORMED=false
PRODUCTION_CODE_CHANGED=false
TEST_CODE_CHANGED=false
DATABASE_SCHEMA_CHANGED=false
MIGRATION_CREATED=false
MODEL_CHANGED=false
S1_REMAINING_06_AUTHORIZED=false
V0_3_S2_AUTHORIZED=false
V0_3_S2_STARTED=false

This package does not issue any threshold, metric result, split manifest,
holdout outcome, custody acceptance, canonical gate PASS, S1 acceptance, or S2
authorization.

## 12. Validation targets

The companion JSON is required to satisfy:

JSON_SYNTAX=PASS
DECISION_ID_UNIQUE=true
UNAUTHORIZED_THRESHOLD_VALUE_COUNT=0
S3_REPORTING_FLOOR_MISUSED_AS_S1_THRESHOLD=false
RANDOM_ADJACENT_DATE_SPLIT_ALLOWED=false
TEST_ACCESS_CURRENTLY_AUTHORIZED=false
EXTERNAL_HOLDOUT_DATA_ACCESS=false
METRIC_EXECUTION_PERFORMED=false
SOURCE_002_RAW_READ=false
CANONICAL_ACCEPTANCE_RECORD_CHANGED=true
JSON_MARKDOWN_CONSISTENCY=PASS

## 13. Next action

NEXT_RECOMMENDED_ACTION=REVALIDATE_REMAINING_05_AFTER_MINIMUM_COVERAGE_GATE_CLOSEOUT
STOPPED_AFTER_S1_REMAINING_05_DECISION_READINESS_DRAFT_PR=true
