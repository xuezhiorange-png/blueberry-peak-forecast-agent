# S1 Data-Quality Threshold Policy Decision

## Accepted policy boundary

```text
TASK=V0_3_S1_DATA_QUALITY_CANONICAL_ACCEPTANCE_CLOSEOUT
TASK_CLASS=DOCS_ONLY_CANONICAL_GATE_ACCEPTANCE_CLOSEOUT
BASE_MAIN_SHA=74a42136b29d6c43780f92c84e59fd6f8ac26558
GATE_ID=S1-DATA-QUALITY-THRESHOLDS
DECISION_ID=S1_DATA_QUALITY_THRESHOLD_POLICY
POLICY_VERSION=v0-3-s1-data-quality-threshold-policy-v1
OWNER_DECISION_SOURCE=PR_222_COMMENT_5301040523
OWNER_DECISION_COMMENT_ID=5301040523
OWNER_IDENTITY=xuezhiorange-png
OWNER_ROLE_ATTESTATION=I_AM_ACTING_AS_DATA_QUALITY_OWNER_ROLE
OWNER_PROVENANCE=AUTHENTICATED_REPOSITORY_OWNER_EXPLICIT_INTERACTIVE_APPROVAL_2026-08-15
DECIDED_AT=2026-08-15T14:54:00+08:00
OWNER_DECISION_SHA256=11e810f4385965f173c6a269d08a1469f6eb4f6173610d272b4ecc09b2171969
```

The canonical decision record binds the exact owner payload from PR #222
comment `5301040523`. Its SHA-256 was replayed with UTF-8, recursively sorted
JSON keys, compact `,`/`:` separators, and the existing owner-payload scope.
The payload is not reinterpreted or supplemented by this closeout.

## Policy contents

```text
DATA_QUALITY_MEASURE=VALID_INCLUDED_CANONICAL_GROUP_COVERAGE
THRESHOLD_VALUE=1.000000
THRESHOLD_OPERATOR=GREATER_THAN_OR_EQUAL
THRESHOLD_UNIT=RATIO_0_TO_1
APPLICATION_GRAIN=SEASON_X_FARM_X_SUBFARM_X_VARIETY_X_HARVEST_BUSINESS_DATE
APPLICATION_SCOPE=ALL_GOVERNED_S1_ACTUAL_HARVEST_LABEL_ROWS_AND_INCLUDED_CANONICAL_DAILY_GROUPS_AFTER_VERSIONED_EXCLUSIONS
MISSING_DATA_PROPORTION_THRESHOLD=0.000000
MISSING_DATA_PROPORTION_OPERATOR=LESS_THAN_OR_EQUAL
MISSING_DATA_PROPORTION_UNIT=RATIO_0_TO_1
SOURCE_ROW_LINEAGE_REQUIRED=true
THRESHOLD_VARIES_BY_HORIZON=false
THRESHOLD_VARIES_BY_PARTITION=false
MINIMUM_COVERAGE_POLICY_IS_DATA_QUALITY_POLICY=false
S3_REPORTING_FLOOR_IS_DATA_QUALITY_THRESHOLD=false
SOURCE_002_STATISTICS_USED_TO_INFER_DATA_QUALITY_POLICY=false
```

The full field-level payload, including missing-day, duplicate/conflict,
canonical-grain, unmapped identity/date, revision/void, completeness, lineage,
exclusion, horizon, and partition semantics, is stored in the companion JSON
artifact without wording changes.

## Review and exact-head evidence

```text
OWNER_DECISION_HASH_REPLAY=PASS
OWNER_DECISION_PAYLOAD_BINDING=PASS
POLICY_INDEPENDENTLY_REVIEWED=true
INDEPENDENT_REVIEW_ID=4943327077
INDEPENDENT_REVIEWED_HEAD=a7bdff6101d724d3413b0fa3d097c240b236326f
INDEPENDENT_REVIEW_RESULT=PASS
INDEPENDENT_REVIEWED_AT=2026-08-15T08:09:57Z
EXACT_HEAD_CI_RUN_ID=31872490353
EXACT_HEAD_CI_HEAD_SHA=a7bdff6101d724d3413b0fa3d097c240b236326f
EXACT_HEAD_CI_STATUS=completed
EXACT_HEAD_CI_CONCLUSION=success
```

## Canonical gate effect

This closeout changes exactly one runtime gate:

```text
S1-DATA-QUALITY-THRESHOLDS=PASS
CURRENT_CANONICAL_GATE_PASS_COUNT=2
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=15
```

`PASS` means the versioned data-quality policy is issued, payload-bound, and
independently reviewed. It does not mean Source 002 has been executed against
the policy or that any data-quality result has passed. Metric execution,
Source 002 reads, backtest, model training, and TEST access remain outside
this closeout.

The remaining canonical gates and the overall S1 state remain blocked:

```text
S1_REMAINING_05_COMPLETE=false
S1_OVERALL_ACCEPTANCE=false
S1_REMAINING_06_AUTHORIZED=false
V0_3_S2_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

The next separately authorized scope is downstream Remaining-05
reconciliation, beginning with `SOURCE_COHORT`; this artifact does not start
that work.
