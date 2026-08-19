# S1 Split Policy Canonical Acceptance Closeout R1

## 1. Scope and authority

```text
ARTIFACT_ID=V0_3_S1_SPLIT_POLICY_CANONICAL_ACCEPTANCE_CLOSEOUT
ARTIFACT_VERSION=s1-split-policy-canonical-acceptance-closeout-v1
ARTIFACT_STATUS=CLOSED_FOR_SPLIT_POLICY_ONLY
TASK_ID=S1_SPLIT_POLICY_CANONICAL_CLOSEOUT_R1
TASK_CLASS=DOCS_ONLY_CANONICAL_GATE_ACCEPTANCE_CLOSEOUT
TARGET_GATE_ID=S1-SPLIT-POLICY
AUTHORITY_SCOPE=S1_SPLIT_POLICY_ONLY
BASE_MAIN_SHA=f6c031f4d4993ae9ea1e190b42614caf47eba84c
BASE_MAIN_TREE_SHA=58d5270fe3192b95f1acd37c7cc83b592e5f79bb
AUTHORIZATION_COMMENT_ID=5340788044
```

This closeout executes exactly one canonical transition:
`S1-SPLIT-POLICY` from `BLOCKED/SPLIT_POLICY_NOT_FROZEN` to
`PASS/NONE`. It does not close Holdout Feasibility or the final S1
Independent Review, mark S1 complete, authorize S2, access TEST or external
holdout data, or perform metrics, backtests, or model training.

## 2. Pre-closeout canonical state

```text
CANONICAL_GATE_COUNT=17
PRE_CLOSEOUT_PASS_COUNT=14
PRE_CLOSEOUT_BLOCKED_COUNT=3
ROOT_STATUS=BLOCKED
S1-SPLIT-POLICY=BLOCKED/SPLIT_POLICY_NOT_FROZEN
```

The precondition was checked against the exact current-main acceptance record.
No other gate row was eligible for mutation under this authorization.

## 3. Reviewed source and independent-review provenance

```text
SOURCE_PR_NUMBER=261
SOURCE_PR_HEAD_SHA=6ffb02dac35a80ab21e097e58138fd399a05d90d
SOURCE_PR_HEAD_TREE_SHA=58d5270fe3192b95f1acd37c7cc83b592e5f79bb
SOURCE_PR_MERGE_SHA=f6c031f4d4993ae9ea1e190b42614caf47eba84c
SOURCE_PR_MERGE_TREE_SHA=58d5270fe3192b95f1acd37c7cc83b592e5f79bb
SOURCE_EXACT_HEAD_CI_RUN_ID=32231959159
SOURCE_EXACT_HEAD_CI_RUN_ATTEMPT=2
SOURCE_EXACT_HEAD_CI_RESULT=completed/success
SOURCE_INDEPENDENT_REVIEW_ID=4970920987
SOURCE_INDEPENDENT_REVIEW_GRAPHQL_ID=PRR_kwDOS_gTTs8AAAABKEo8Gw
SOURCE_INDEPENDENT_REVIEW_RESULT=PASS
SOURCE_REVIEWED_HEAD_SHA=6ffb02dac35a80ab21e097e58138fd399a05d90d
SOURCE_REVIEWED_HEAD_TREE_SHA=58d5270fe3192b95f1acd37c7cc83b592e5f79bb
SOURCE_REVIEW_SUBMITTED_AT=2026-08-19T10:04:03Z
SOURCE_REVIEW_BLOCKER_COUNT=0
OWNER_SPLIT_POLICY_DECISION_COMMENT_ID=5336738442
OWNER_SPLIT_MEMBERSHIP_DECISION_COMMENT_ID=5337704077
```

The source review validated only the split-manifest and TEST-custody
formalization package. It did not perform this new canonical closeout; a
separate exact-head closeout review is required later.

## 4. Reviewed split evidence

```text
SPLIT_POLICY_VERSION=v0-3-s1-time-ordered-split-policy-v1
SPLIT_MANIFEST_VERSION=v0-3-s1-time-ordered-split-manifest-v1
SPLIT_MANIFEST_SHA256=f2c4b32b60c94fa2887fbe80c7a25f0fc5a54528585342e49a288cbf07ea9a5f
PARTITION_ORDER=TRAIN,VALIDATION,TEST
BOUNDARIES=BOTH_ENDS_INCLUSIVE
OVERLAP=false
GAPS=false
REQUESTED_HORIZONS_DAYS=7,14,21
```

The exact reviewed intervals and logical-rowset identities are:

| Partition | Interval | Logical rowset SHA-256 | Replay |
| --- | --- | --- | --- |
| TRAIN | `2025-08-05..2026-01-30` | `aedf0495d59578f2ba90265c4f5f50360d6d8d9fede7a1a1d2524a7278a4bcee` | PASS |
| VALIDATION | `2026-01-31..2026-03-09` | `389691f6da7e82c7e31efd7cfee4eb629778845e0055694f591f985d2d312cb4` | PASS |
| TEST | `2026-03-10..2026-04-16` | `a96534bacb4b77d8851644569c348179376b7b42102296a97f4279eabbde0f73` | PASS |

The four governed SHA-256 identities are the TRAIN logical rowset,
VALIDATION logical rowset, TEST logical rowset, and split manifest hashes
listed above. The manifest hash is the governance identity; it is not a
materialized TEST-data content hash.

## 5. Why the split threshold is satisfied

`TIME_ORDERED_SPLITS_AND_NO_LEAKAGE` is satisfied by the reviewed partition
order, non-overlapping inclusive intervals, no-gap assertion, requested
horizon binding, and independent replay of all four identities. The TEST
interval is the latest interval and its membership is sealed before candidate
tuning. This proves the split-policy evidence threshold only. It does not
materialize any partition or grant access to any partition.

## 6. Point-in-time cutoff semantics

```text
AUTHORITY=EXACT_FORECAST_CUTOFF_AT
INPUT_KNOWN_AT_REQUIREMENT=KNOWN_AT_LESS_THAN_OR_EQUAL_TO_EXACT_FORECAST_CUTOFF_AT
INPUT_SOURCE_AVAILABLE_AT_REQUIREMENT=SOURCE_AVAILABLE_AT_LESS_THAN_OR_EQUAL_TO_EXACT_FORECAST_CUTOFF_AT
TIMESTAMP_IDENTITY=TIMEZONE_AWARE_CANONICAL_UTC
TARGET_RELATION=FORECAST_CUTOFF_AT_STRICTLY_BEFORE_FORECAST_TARGET_DATE_OR_WINDOW_END
DRIFT_SEMANTICS=FAIL_CLOSED_OR_NEW_IDENTITY_NO_SILENT_SUBSTITUTION
```

These semantics bind the reviewed split identity to the repository's existing
point-in-time authority. They do not assert that forecast execution or metric
evaluation has occurred.

## 7. TEST seal and data-access boundary

```text
TEST_SEAL_IS_NOT_TEST_ACCESS_AUTHORIZATION=true
TEST_CUSTODY_RECORD_ACCEPTED=false
TEST_CUSTODY_ACCEPTANCE_AUTHORIZED=false
TEST_DATA_ACCESS=false
SOURCE_002_RAW_READ=false
SOURCE_002_ROW_LEVEL_READ=false
TRAIN_ROWSET_MATERIALIZED=false
VALIDATION_ROWSET_MATERIALIZED=false
TEST_ROWSET_MATERIALIZED=false
EXTERNAL_HOLDOUT_ACCESS=false
```

TEST is sealed as reviewed membership evidence, but access remains
unauthorized. No TEST, Source002 raw/row-level, or external holdout data was
read, and no TRAIN, VALIDATION, or TEST rowset was materialized.

## 8. Canonical transition and mutation accounting

```text
PREVIOUS_STATUS=BLOCKED
PREVIOUS_BLOCK_REASON=SPLIT_POLICY_NOT_FROZEN
NEW_STATUS=PASS
NEW_BLOCK_REASON=NONE
ACCEPTANCE_THRESHOLD=TIME_ORDERED_SPLITS_AND_NO_LEAKAGE
SPLIT_POLICY_STATUS=PASS
SPLIT_POLICY_BLOCK_REASON=NONE
TARGET_GATE_STATUS_MUTATION_COUNT=1
TARGET_GATE_BLOCK_REASON_MUTATION_COUNT=1
OTHER_GATE_STATUS_MUTATION_COUNT=0
OTHER_GATE_BLOCK_REASON_MUTATION_COUNT=0
```

Only `S1-SPLIT-POLICY` changes. The acceptance record and package mirror this
single transition; the PR261 formalization artifacts and global current-main
reconciliation artifacts are not changed.

## 9. Current-main versus branch-candidate state

```text
CURRENT_MAIN_CANONICAL_GATE_COUNT=17
CURRENT_MAIN_CANONICAL_GATE_PASS_COUNT=14
CURRENT_MAIN_CANONICAL_GATE_BLOCKED_COUNT=3
PR_BRANCH_CANDIDATE_CANONICAL_GATE_COUNT=17
PR_BRANCH_CANDIDATE_CANONICAL_GATE_PASS_COUNT=15
PR_BRANCH_CANDIDATE_CANONICAL_GATE_BLOCKED_COUNT=2
ROOT_STATUS=BLOCKED
ALL_17_REQUIRED_GATES_PASS=false
V0_3_S1_COMPLETE=false
V0_3_S1_ACCEPTED=false
V0_3_S2_AUTHORIZED=false
```

The two and only two remaining blocked gates are:

```text
S1-HOLDOUT-FEASIBILITY=BLOCKED/FEASIBILITY_NOT_YET_ACCEPTED
S1-INDEPENDENT-REVIEW=BLOCKED/NOT_YET_INDEPENDENTLY_REVIEWED
```

Holdout Feasibility remains a separate required decision gate and is not
external-holdout materialization. The final S1 Independent Review remains a
separate, not-yet-performed review. S1 therefore remains blocked overall.

## 10. Runtime and downstream boundaries

```text
PRODUCTION_CODE_CHANGED=false
TEST_CODE_CHANGED=false
DATABASE_SCHEMA_CHANGED=false
MIGRATION_CREATED=false
METRIC_EXECUTION_PERFORMED=false
BACKTEST_EXECUTED=false
MODEL_TRAINING_EXECUTED=false
HOLDOUT_FEASIBILITY_CLOSEOUT_PERFORMED=false
S1_INDEPENDENT_REVIEW_CLOSEOUT_PERFORMED=false
FINAL_V0_3_S1_ACCEPTANCE_PERFORMED=false
V0_3_S2_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
HOLDOUT_FEASIBILITY_DECISION_AUTHORIZED=false
FINAL_S1_INDEPENDENT_REVIEW_AUTHORIZED=false
TEST_CUSTODY_ACCEPTANCE_AUTHORIZED=false
TEST_DATA_ACCESS_AUTHORIZED=false
NEXT_GATE_AUTHORIZED=false
```

No metric result, backtest, model-training result, or final acceptance is
created by this closeout.

## 11. Validation and hard stop

```text
JSON_SYNTAX=PASS
S1_ACCEPTANCE_RECORD_SCHEMA_VALIDATION=PASS
CANONICAL_GATE_COUNT=17
UNIQUE_GATE_ID_COUNT=17
MISSING_GATE_COUNT=0
DUPLICATE_GATE_COUNT=0
PASS_COUNT=15
BLOCKED_COUNT=2
ACCEPTANCE_RECORD_PACKAGE_PARITY=PASS
CLOSEOUT_JSON_MARKDOWN_PARITY=PASS
GLOBAL_RECONCILIATION_ARTIFACTS_UNCHANGED=true
SOURCE_FORMALIZATION_ARTIFACTS_UNCHANGED=true
GIT_DIFF_CHECK=PASS
```

The closeout creates exactly the four authorized changed files:

```text
docs/v0-3/s1/evidence/s1-acceptance-record.json
docs/v0-3/s1/s1-acceptance-package.md
docs/v0-3/s1/evidence/s1-split-policy-canonical-acceptance-closeout.json
docs/v0-3/s1/workpapers/s1-split-policy-canonical-acceptance-closeout.md
```

```text
INDEPENDENT_CLOSEOUT_REVIEW_PERFORMED=false
READY_PERFORMED=false
MERGE_PERFORMED=false
NEXT_GATE_STARTED=false
V0_3_S1_ACCEPTED=false
V0_3_S2_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

This implementation stops after commit, push, Draft PR creation, and CI
discovery. It does not perform the new independent closeout review, mark the
PR Ready, merge the PR, close Holdout Feasibility, perform final S1 review, or
authorize V0.3-S2.
