# S1-REMAINING-05 Threshold, Metric, Split, and Holdout Decision Readiness

## 1. Scope and authority

TASK_ID=S1-REMAINING-05
TASK_CLASS=DOCS_ONLY_DECISION_AND_POLICY_READINESS
BASE_MAIN_SHA=0ed98ee8fa51601f939315a6cfc08e2b690e1bc1
HISTORICAL_CURRENT_MAIN_REVALIDATED_SHA=74a42136b29d6c43780f92c84e59fd6f8ac26558
CURRENT_MAIN_REVALIDATED_SHA=4a5ae07ad9ed1f580c3e7627ded3acc719ba6bb2
CURRENT_MAIN_REVALIDATED_TREE_SHA=12f8f1e7d8b1d821d98cbea3354eafc1ecd2937c
READINESS_PACKAGE_ONLY=true
NO_STEP_IMPLIES_THE_NEXT=true

This package prepares decision and policy readiness for threshold, metric,
split, and holdout work. PR #219 issued and independently reviewed the
minimum-coverage policy; PR #221 closed the standalone canonical
S1-MINIMUM-COVERAGE gate; this package retains the historical readiness
snapshot while the current-main owner-binding namespace below records the
separately verified 13 PASS / 4 BLOCKED runtime. The metric owner decision is
bound for review, but this package still does not close the metric gate, accept
a split, decide holdout feasibility, accept custody, complete Remaining-05, or
authorize any later S1/S2 task.

The original package snapshot is retained as historical provenance; it is not
the current-main state:

| State | Value |
| --- | --- |
| HISTORICAL_CANONICAL_GATE_COUNT | 17 |
| HISTORICAL_CURRENT_CANONICAL_GATE_PASS_COUNT | 2 |
| HISTORICAL_CURRENT_CANONICAL_GATE_BLOCKED_COUNT | 15 |
| CANONICAL_GATE_STATUS_CHANGED | true |
| CANONICAL_ACCEPTANCE_RECORD_CHANGED | true |
| V0_3_S1_COMPLETE | false |
| V0_3_S1_ACCEPTED | false |
| S1_REMAINING_06_AUTHORIZED | false |
| V0_3_S2_AUTHORIZED | false |
| V0_3_S2_STARTED | false |

### Current-main owner-binding runtime (read-only)

CURRENT_MAIN_SHA=4a5ae07ad9ed1f580c3e7627ded3acc719ba6bb2
CURRENT_MAIN_TREE_SHA=12f8f1e7d8b1d821d98cbea3354eafc1ecd2937c
CANONICAL_GATE_COUNT=17
CURRENT_CANONICAL_GATE_PASS_COUNT=13
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=4
S1-METRIC-CONTRACT=BLOCKED/METRIC_CONTRACT_NOT_ACCEPTED
S1-DATA-CUSTODY=PASS/NONE
CANONICAL_GATE_STATUS_MUTATION_BY_THIS_PACKAGE=false
CANONICAL_ACCEPTANCE_RECORD_CHANGED_BY_THIS_PACKAGE=false

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
| Data quality thresholds | ISSUED_AND_INDEPENDENTLY_REVIEWED / gate PASS | Binds the authenticated owner policy, SHA, review, and exact-head CI | Does not execute Source 002 or claim a data-quality measurement result |
| Metric contract | OWNER_DECISION_ISSUED_REVIEW_REQUIRED / gate BLOCKED | Binds the authenticated owner decision, current version, and canonical metric registry | Does not execute metrics, issue results, or close the canonical gate |
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
is the only Task05 domain closed by the PR #221 canonical closeout.

## 4. Data-quality threshold owner decision closeout

The authenticated repository owner issued a versioned S1 data-quality policy.
The decision owner is `data_quality_owner_role`; the owner payload was
replayed and independently reviewed on its exact reviewed head. The policy
closes only the standalone data-quality canonical gate; it does not execute
Source 002 or close downstream gates.
The bound decision covers:

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
| CURRENT_STATUS | ISSUED_AND_INDEPENDENTLY_REVIEWED |
| CANDIDATE_VALUE | null |
| ACCEPTED_VALUE | null |
| EXTERNAL_DECISION_REQUIRED | false |
| CAN_BE_INFERRED | false |
| CAN_BE_DECIDED_IN_CURRENT_TASK | false |
| BLOCK_REASON | NONE |

```text
DATA_QUALITY_OWNER_DECISION_REQUEST_PREPARED=true
OWNER_DECISION_ISSUED=true
OWNER_DECISION_SOURCE=PR_222_COMMENT_5301040523
OWNER_DECISION_COMMENT_ID=5301040523
OWNER_IDENTITY=xuezhiorange-png
OWNER_ROLE_ATTESTATION=I_AM_ACTING_AS_DATA_QUALITY_OWNER_ROLE
OWNER_PROVENANCE=AUTHENTICATED_REPOSITORY_OWNER_EXPLICIT_INTERACTIVE_APPROVAL_2026-08-15
DECIDED_AT=2026-08-15T14:54:00+08:00
POLICY_VERSION=v0-3-s1-data-quality-threshold-policy-v1
OWNER_DECISION_SHA256=11e810f4385965f173c6a269d08a1469f6eb4f6173610d272b4ecc09b2171969
OWNER_DECISION_HASH_REPLAY=PASS
OWNER_DECISION_BINDING=PASS
S1_DATA_QUALITY_THRESHOLDS_GATE_PASS=true
OWNER_DECISION_REQUEST_ARTIFACT=docs/v0-3/s1/evidence/s1-data-quality-threshold-policy-decision-request.json
OWNER_DECISION_REQUEST_WORKPAPER=docs/v0-3/s1/workpapers/s1-data-quality-threshold-policy-decision-request.md
OWNER_DECISION_CANONICAL_ARTIFACT=docs/v0-3/s1/evidence/s1-data-quality-threshold-policy-decision.json
POLICY_INDEPENDENTLY_REVIEWED=true
INDEPENDENT_REVIEW_ID=4943327077
INDEPENDENT_REVIEWED_HEAD=a7bdff6101d724d3413b0fa3d097c240b236326f
INDEPENDENT_REVIEW_RESULT=PASS
EXACT_HEAD_CI_RUN_ID=31872490353
EXACT_HEAD_CI_CONCLUSION=success
```

The machine-readable request artifact contains the exact issued owner payload
and its canonical SHA-256 binding. The data-quality policy is independently
reviewed and its standalone gate is PASS. The policy is not inferred from
Source 002 aggregate statistics, and no Source 002 execution is implied.

## Remaining-05 completion boundary

```text
S1_REMAINING_05_COMPLETE=false
REMAINING_BLOCKERS=(
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
the PR #221 canonical closeout, following the PR #219 policy merge, and
remain unresolved; no downstream gate is promoted by this package.

## 5. Metric contract freeze readiness

The current contract identity is:

V0_3_METRIC_CONTRACT_VERSION=v0.3-metric-contract-v1
METRIC_CONTRACT_AUTHORITY=docs/forecast-quality/s3-quality-metrics-contract.md
METRIC_REGISTRY_COUNT=22
CURRENT_STATUS=OWNER_DECISION_ISSUED_REVIEW_REQUIRED
EXTERNAL_DECISION_REQUIRED=false
ACCEPTED_VALUE=v0.3-metric-contract-v1
OWNER_DECISION_ISSUED=true
OWNER_DECISION_COMMENT_ID=5330399072
OWNER_DECISION_SHA256=e3ff3221338863aa9128890c23e463e7a3868cd8dfc3e1b2c30c503c351a3acd
OWNER_DECISION_HASH_REPLAY=PASS
OWNER_DECISION_PAYLOAD_BINDING=PASS
OWNER_DECISION_BINDING=PASS
POLICY_INDEPENDENTLY_REVIEWED=false
CURRENT_METRIC_EXECUTION_STATUS=NOT_EXECUTED
CURRENT_METRIC_RESULT_STATUS=NOT_ISSUED
CURRENT_S3_DAILY_ROWSET_CONTRACT_STATUS=NOT_AVAILABLE_FROM_CURRENT_S2_BINDING
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
CURRENT_P50_SEMANTICS_VERIFIED=false
CURRENT_P80_SEMANTICS_VERIFIED=false
CURRENT_P90_SEMANTICS_VERIFIED=false
METRIC_REGISTRY_BOUND=true
S1_METRIC_CONTRACT_CANONICAL_GATE_PASS=false
S1-METRIC-CONTRACT=BLOCKED
BLOCK_REASON=METRIC_CONTRACT_NOT_ACCEPTED
CANONICAL_GATE_COUNT=17
CURRENT_CANONICAL_GATE_PASS_COUNT=13
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=4

The owner decision source is `PR_256_COMMENT_5330399072` from
`xuezhiorange-png`, acting under `model_validation_owner_role`. It freezes
the prepared contract definition, canonical identities, formulas/policies,
and planning crosswalk only. The accepted contract version is not a metric
result and does not change the canonical gate.

OWNER_DECISION_SOURCE=PR_256_COMMENT_5330399072
OWNER_IDENTITY=xuezhiorange-png
OWNER_ROLE=model_validation_owner_role
OWNER_ROLE_ATTESTATION=I_AM_ACTING_AS_MODEL_VALIDATION_OWNER_ROLE
OWNER_PROVENANCE=AUTHENTICATED_REPOSITORY_OWNER_EXPLICIT_INTERACTIVE_APPROVAL_2026-08-18
DECIDED_AT=2026-08-18T23:23:00+08:00

The binding uses the existing Data Quality owner-decision convention:
UTF-8, uppercase-as-issued payload keys, sorted JSON keys, compact `,` and
`:` separators, SHA-256, and exclusion of the self-referential hash field.
The exact payload and replay record are in the companion binding artifact:

```text
OWNER_DECISION_HASH_REPLAY=PASS
OWNER_DECISION_PAYLOAD_BINDING=PASS
OWNER_DECISION_BINDING=PASS
OWNER_DECISION_SHA256=e3ff3221338863aa9128890c23e463e7a3868cd8dfc3e1b2c30c503c351a3acd
```

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
| CURRENT_STATUS | OWNER_DECISION_ISSUED_REVIEW_REQUIRED |
| ACCEPTED_VALUE | v0.3-metric-contract-v1 |
| EXTERNAL_DECISION_REQUIRED | false |
| CAN_BE_INFERRED | false |
| CAN_BE_DECIDED_IN_CURRENT_TASK | false |
| BLOCK_REASON | METRIC_CONTRACT_NOT_ACCEPTED |
| DEPENDENCY_BLOCK_REASON | UPSTREAM_SOURCE_TARGET_ROWSET_THRESHOLD_AND_DATA_QUALITY_PREREQUISITES_NOT_ACCEPTED |
| OWNER_DECISION_ISSUED | true |
| OWNER_DECISION_COMMENT_ID | 5330399072 |
| OWNER_DECISION_SHA256 | `e3ff3221338863aa9128890c23e463e7a3868cd8dfc3e1b2c30c503c351a3acd` |
| OWNER_DECISION_HASH_REPLAY | PASS |
| OWNER_DECISION_PAYLOAD_BINDING | PASS |
| OWNER_DECISION_BINDING | PASS |
| POLICY_INDEPENDENTLY_REVIEWED | false |

The owner decision does not make `S1-METRIC-CONTRACT` PASS. Independent review
is still required, and this task stops before that review, Ready, Merge, any
metric execution, or any downstream gate.

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
| S1_DATA_QUALITY_THRESHOLD_POLICY | S1-DATA-QUALITY-THRESHOLDS | ISSUED_AND_INDEPENDENTLY_REVIEWED | data_quality_owner_role | no | policy version / accepted policy | closed by owner decision SHA `11e810f4385965f173c6a269d08a1469f6eb4f6173610d272b4ecc09b2171969`, review `4943327077`, and exact-head CI `31872490353` |
| S1_METRIC_CONTRACT_FREEZE_AND_ACCEPTANCE | S1-METRIC-CONTRACT | OWNER_DECISION_ISSUED_REVIEW_REQUIRED | model_validation_owner_role | no | registry / v0.3-metric-contract-v1 | canonical gate remains blocked pending independent review |
| S1_SPLIT_POLICY_FREEZE_AND_ACCEPTANCE | S1-SPLIT-POLICY | CANDIDATE_NOT_ACCEPTED | model_validation_owner_role | yes | v1 candidate / null | cohort, visibility, metric, custody |
| S1_HOLDOUT_FEASIBILITY_DECISION | S1-HOLDOUT-FEASIBILITY | NOT_EVALUATED | model_validation_owner_role | yes | criteria only / null | upstream evidence and review |
| S1_TASK05_CUSTODY_ARTIFACT_BINDING_REVIEW | S1-DATA-CUSTODY | ISSUED_FOR_INDEPENDENT_REVIEW | data_governance_owner_role | yes | existing identity / null | custody review not complete |

UNAUTHORIZED_THRESHOLD_VALUE_COUNT=0. The S1 value `0.900000` is authorized
only by the versioned owner decision and its independent review. The separate
S3 reporting floor 10 remains excluded from S1 threshold semantics.

## 10. Dependency order

Task05 does not authorize execution of the following queue. It records the
dependency order for later separately authorized work:

1. complete source cohort, inclusion, visibility prerequisites, and custody
   review;
2. freeze and independently review the metric contract;
3. freeze and independently review the time-ordered split policy;
4. evaluate holdout feasibility after cohort, threshold, split, and custody
   prerequisites are accepted; and
5. only after all canonical gates are otherwise closed, run final independent
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
CURRENT_METRIC_RESULT_STATUS=NOT_ISSUED
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
CURRENT_P50_SEMANTICS_VERIFIED=false
CURRENT_P80_SEMANTICS_VERIFIED=false
CURRENT_P90_SEMANTICS_VERIFIED=false
PRODUCTION_CODE_CHANGED=false
TEST_CODE_CHANGED=false
DATABASE_SCHEMA_CHANGED=false
MIGRATION_CREATED=false
MODEL_CHANGED=false
S1_REMAINING_06_AUTHORIZED=false
V0_3_S2_AUTHORIZED=false
V0_3_S2_STARTED=false

This package does not execute the accepted threshold against data or issue any
metric result, split manifest, holdout outcome, custody acceptance, S1
acceptance, or S2 authorization. The standalone data-quality policy gate is
already recorded as PASS in the canonical acceptance record.

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
CANONICAL_ACCEPTANCE_RECORD_CHANGED=false
CANONICAL_GATE_STATUS_MUTATION_COUNT=0
CANONICAL_GATE_BLOCK_REASON_MUTATION_COUNT=0
OWNER_DECISION_HASH_REPLAY=PASS
OWNER_DECISION_PAYLOAD_BINDING=PASS
OWNER_DECISION_BINDING=PASS
CANONICAL_GATE_COUNT=17
CURRENT_CANONICAL_GATE_PASS_COUNT=13
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=4
JSON_MARKDOWN_CONSISTENCY=PASS

## 13. Next action

NEXT_RECOMMENDED_ACTION=REVALIDATE_REMAINING_05_AFTER_DATA_QUALITY_GATE_CLOSEOUT
STOPPED_AFTER_S1_REMAINING_05_DECISION_READINESS_DRAFT_PR=true
