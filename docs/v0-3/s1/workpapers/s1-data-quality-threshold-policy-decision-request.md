# V0.3-S1 Data-Quality Threshold Policy Decision Request

```text
TASK_ID=V0_3_S1_DATA_QUALITY_THRESHOLD_POLICY_OWNER_BINDING_R1
TASK_CLASS=DOCS_ONLY_OWNER_DECISION_BINDING
CURRENT_MAIN_SHA=7fd2c15f91f6dfad94178595845df389017d02b3
DECISION_ID=S1_DATA_QUALITY_THRESHOLD_POLICY
OWNER_ROLE=data_quality_owner_role
CURRENT_STATUS=OWNER_DECISION_ISSUED
OWNER_DECISION_REQUEST_PREPARED=true
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
POLICY_INDEPENDENTLY_REVIEWED=false
EXTERNAL_DECISION_REQUIRED=false
CAN_BE_INFERRED=false
CANDIDATE_VALUE=null
ACCEPTED_VALUE=null
BLOCK_REASON=OWNER_DECISION_BOUND_PENDING_EXACT_HEAD_INDEPENDENT_REVIEW
```

## 1. Scope and authority boundary

This workpaper binds the authenticated repository-owner decision recorded in
PR #222 comment `5301040523` to the existing data-quality policy request. It
does not independently review the policy, accept the canonical gate, or change
any canonical runtime status. The owner decision remains attributable to
`xuezhiorange-png` acting as `data_quality_owner_role`.

The request is deliberately fail-closed:

```text
S1_DATA_QUALITY_THRESHOLDS_GATE_PASS=false
S1_REMAINING_05_COMPLETE=false
S1_OVERALL_ACCEPTANCE=false
```

No policy value is inferred from Source 002 statistics, fixtures, test data,
code behavior, or historical performance. Source 002 raw and row-level data
are outside this task.

## 2. Issued owner decision binding

The owner decision was fetched from the PR issue comment and replayed using
the repository decision-payload hashing rule. The payload below is the exact
uppercase-key payload used for the SHA-256 replay; the self-referential hash is
stored outside the payload.

```text
OWNER_DECISION_COMMENT_FETCH=PASS
OWNER_DECISION_HASH_REPLAY=PASS
OWNER_DECISION_BINDING=PASS
OWNER_DECISION_SOURCE=PR_222_COMMENT_5301040523
OWNER_DECISION_COMMENT_ID=5301040523

DECISION_ID=S1_DATA_QUALITY_THRESHOLD_POLICY
OWNER_IDENTITY=xuezhiorange-png
OWNER_ROLE_ATTESTATION=I_AM_ACTING_AS_DATA_QUALITY_OWNER_ROLE
OWNER_PROVENANCE=AUTHENTICATED_REPOSITORY_OWNER_EXPLICIT_INTERACTIVE_APPROVAL_2026-08-15
DECIDED_AT=2026-08-15T14:54:00+08:00
POLICY_VERSION=v0-3-s1-data-quality-threshold-policy-v1
DATA_QUALITY_MEASURE=VALID_INCLUDED_CANONICAL_GROUP_COVERAGE
THRESHOLD_VALUE=1.000000
THRESHOLD_OPERATOR=GREATER_THAN_OR_EQUAL
THRESHOLD_UNIT=RATIO_0_TO_1
APPLICATION_GRAIN=SEASON_X_FARM_X_SUBFARM_X_VARIETY_X_HARVEST_BUSINESS_DATE
APPLICATION_SCOPE=ALL_GOVERNED_S1_ACTUAL_HARVEST_LABEL_ROWS_AND_INCLUDED_CANONICAL_DAILY_GROUPS_AFTER_VERSIONED_EXCLUSIONS
MISSING_DAY_POLICY=BLOCK_UNLESS_EXPLICIT_VERSIONED_EXCLUSION_OR_ACCEPTED_SOURCE_POLICY_PROVES_DAY_NOT_EXPECTED
MISSING_DATA_PROPORTION_THRESHOLD=0.000000
MISSING_DATA_PROPORTION_OPERATOR=LESS_THAN_OR_EQUAL
MISSING_DATA_PROPORTION_UNIT=RATIO_0_TO_1
MISSING_DATA_DENOMINATOR=COUNT_ALL_REQUIRED_EXPECTED_DATA_QUALITY_ELEMENTS_WITHIN_EXACT_APPLICATION_CELL_AFTER_VERSIONED_EXCLUSIONS
DUPLICATE_RECORD_POLICY=DEDUPLICATE_ONLY_WHEN_SAME_SOURCE_ROW_EVIDENCE_IDENTITY_AND_IDENTICAL_PAYLOAD_PROVE_TECHNICAL_DUPLICATION_OTHERWISE_BLOCK
CONFLICTING_RECORD_POLICY=BLOCK_NO_IMPLICIT_WINNER
INVALID_CANONICAL_GRAIN_POLICY=BLOCK
UNMAPPED_IDENTITY_POLICY=EXCLUDE_ONLY_BY_VERSIONED_REASON_CODED_EXCLUSION_MANIFEST_OTHERWISE_BLOCK
UNMAPPED_DATE_POLICY=EXCLUDE_ONLY_BY_VERSIONED_REASON_CODED_EXCLUSION_MANIFEST_OTHERWISE_BLOCK_NO_AUTO_ASSIGNMENT
REVISION_CONSISTENCY_POLICY=REQUIRE_ACCEPTED_SOURCE_POLICY_AND_DETERMINISTIC_LINEAGE_WHERE_REVISION_MODEL_APPLIES_IDFL_MAY_USE_SOURCE_OBJECT_BOUND_LINEAGE_ONLY_WHEN_FORMALLY_ACCEPTED
VOID_CANCELLATION_POLICY=FOLLOW_ACCEPTED_VERSIONED_SOURCE_POLICY_UNRESOLVED_APPLICABLE_VOID_OR_CANCELLATION_BLOCKS_FORMALLY_NOT_APPLICABLE_REQUIRES_PROVENANCE
WINNER_SELECTION_REQUIREMENT=EXACTLY_ONE_GOVERNED_WINNER_WHERE_REVISION_MODEL_APPLIES_IDFL_HAS_NO_WINNER_ALGORITHM_AND_UNEXPLAINED_CONFLICTS_BLOCK
COMPLETENESS_POLICY=EVERY_INCLUDED_BUSINESS_DATE_MUST_BE_COVERED_BY_SOURCE_OBJECT_COMPLETENESS_AUTHORITY_AND_REQUIRED_FIELDS_LINEAGE_AND_QUANTITY_EVIDENCE_MUST_BE_COMPLETE
SOURCE_ROW_LINEAGE_REQUIRED=true
SOURCE_ROW_LINEAGE_FAILURE_SEMANTICS=BLOCK
CANONICAL_GROUP_COVERAGE_POLICY=VALID_INCLUDED_CANONICAL_GROUP_COVERAGE_MUST_EQUAL_1_000000_AFTER_ONLY_VERSIONED_REASON_CODED_EXCLUSIONS
FAILURE_SEMANTICS=FAIL_CLOSED_BLOCK_AFFECTED_ROW_OR_GROUP_AND_BLOCK_DATA_QUALITY_GATE_WHILE_ANY_INCLUDED_REQUIRED_ROW_OR_GROUP_REMAINS_INVALID_MISSING_OR_UNEXPLAINED
EXCLUSION_SEMANTICS=ONLY_VERSIONED_REASON_CODED_EXCLUSIONS_WITH_MANIFEST_COUNTS_PROVENANCE_AND_RECONCILIATION_EXCLUSIONS_NEVER_COUNT_AS_PASS
THRESHOLD_VARIES_BY_HORIZON=false
HORIZON_POLICY=SAME_DATA_QUALITY_POLICY_FOR_ALL_HORIZONS_SOURCE_DATA_QUALITY_IS_HORIZON_INVARIANT
THRESHOLD_VARIES_BY_PARTITION=false
PARTITION_POLICY=SAME_DATA_QUALITY_POLICY_FOR_TRAIN_VALIDATION_TEST_WITH_EACH_PARTITION_EVALUATED_INDEPENDENTLY_AFTER_SPLIT_MATERIALIZATION
MINIMUM_COVERAGE_POLICY_IS_DATA_QUALITY_POLICY=false
S3_REPORTING_FLOOR_IS_DATA_QUALITY_THRESHOLD=false
SOURCE_002_STATISTICS_USED_TO_INFER_DATA_QUALITY_POLICY=false
OWNER_DECISION_FINAL=true
OWNER_DECISION_READY_FOR_INDEPENDENT_REVIEW=true
OWNER_DECISION_SHA256=11e810f4385965f173c6a269d08a1469f6eb4f6173610d272b4ecc09b2171969
```

The code block above is a human-readable binding summary. The machine-readable
artifact contains the exact payload and the authoritative SHA-256. The data-
quality gate remains blocked pending exact-head independent review; the issued
policy is not yet a canonical acceptance.

## 3. Required owner decision dimensions

The owner must explicitly decide every dimension below. If a dimension does
not apply, the owner must write `NOT_APPLICABLE_WITH_REASON`; it may not be
silently omitted.

| Dimension | Required owner decision | Required boundary |
| --- | --- | --- |
| `MISSING_DAY_POLICY` | How an expected but absent governed day is classified | Owner must select `BLOCK`, `EXCLUDE`, `OTHER`, or an explicit `NOT_APPLICABLE_WITH_REASON` |
| `MISSING_DATA_PROPORTION_POLICY` | Whether partial missingness is allowed and how it is measured | Owner must provide numerator/denominator, threshold, operator, unit, grain, scope, and failure semantics |
| `DUPLICATE_CONFLICT_POLICY` | Disposition of exact duplicates, same-key different payloads, and conflicting revisions | Owner must define fail/resolve/exclude semantics for each case |
| `INVALID_CANONICAL_GRAIN_IDENTITY_POLICY` | Disposition of invalid farm/subfarm/variety/date or other grain identity | Owner must define the identity validation and failure outcome |
| `UNMAPPED_IDENTITY_OR_DATE_POLICY` | Disposition of unmapped identity or indeterminate local date/date basis | Owner must define mapping, fail-closed, and exclusion behavior |
| `REVISION_VOID_CONSISTENCY_POLICY` | Revision lineage, winner, void/cancel, and corrected-record consistency | Owner must define the valid-winner requirement and failure outcome |
| `COMPLETENESS_POLICY` | What complete means at the approved date universe and application grain | Owner must define daily/rowset completeness and incomplete-rowset semantics |
| `SOURCE_ROW_LINEAGE_POLICY` | Whether every governed row must trace to source-row identity | Owner must set lineage requiredness and lineage-failure semantics |
| `CANONICAL_GROUP_COVERAGE_POLICY` | Required coverage of canonical application groups/cells | Owner must define numerator, denominator, grain, scope, and relation to minimum coverage |

## 4. Common fields that must be frozen in the owner payload

The versioned policy record must contain the following fields. The values are
not supplied by this workpaper:

| Field | Owner entry |
| --- | --- |
| `DECISION_ID` | `S1_DATA_QUALITY_THRESHOLD_POLICY` |
| `POLICY_VERSION` | `<required versioned policy identity>` |
| `OWNER_IDENTITY` | `<required>` |
| `OWNER_ROLE_ATTESTATION` | `I_AM_ACTING_AS_DATA_QUALITY_OWNER_ROLE` |
| `OWNER_PROVENANCE` | `<required>` |
| `DECIDED_AT` | `<required ISO-8601>` |
| `APPLICATION_GRAIN` | `<required>` |
| `APPLICATION_SCOPE` | `<required>` |
| `FAILURE_SEMANTICS` | `<required>` |
| `EXCLUSION_SEMANTICS` | `<required>` |
| `THRESHOLD_VALUE` | `<required or explicit NONE>` |
| `THRESHOLD_OPERATOR` | `<required if threshold exists; otherwise NOT_APPLICABLE_WITH_REASON>` |
| `THRESHOLD_UNIT` | `<required if threshold exists; otherwise NOT_APPLICABLE_WITH_REASON>` |
| `THRESHOLD_VARIES_BY_HORIZON` | `<required true or false>` |
| `HORIZON_POLICY` | `<required or NOT_APPLICABLE_WITH_REASON>` |
| `THRESHOLD_VARIES_BY_PARTITION` | `<required true or false>` |
| `PARTITION_POLICY` | `<required or NOT_APPLICABLE_WITH_REASON>` |
| `INDEPENDENT_REVIEW_REQUIRED` | `true` |

## 5. Minimum-coverage boundary

The separately accepted S1 minimum-coverage policy is
`coverage_ratio >= 0.900000`. It is not a data-quality policy and must not be
copied into the data-quality decision. Likewise,
`MIN_COMPARABLE_ROWS_FOR_REPORTING=10` is an S3 reporting floor, not an S1
data-quality threshold.

```text
MINIMUM_COVERAGE_POLICY_IS_DATA_QUALITY_POLICY=false
S3_REPORTING_FLOOR_IS_DATA_QUALITY_THRESHOLD=false
SOURCE_002_STATISTICS_USED_TO_INFER_DATA_QUALITY_POLICY=false
```

The data-quality policy requires its own version, owner provenance,
application scope, threshold semantics, and independent review.

## 6. Owner signature template

The following is the original request template retained for provenance. The
issued owner payload is bound in Section 2; these placeholders are not used as
the issued authority.

```text
DECISION_ID=S1_DATA_QUALITY_THRESHOLD_POLICY
OWNER_IDENTITY=<required>
OWNER_ROLE_ATTESTATION=I_AM_ACTING_AS_DATA_QUALITY_OWNER_ROLE
OWNER_PROVENANCE=<required>
DECIDED_AT=<required ISO-8601>
POLICY_VERSION=<required>

MISSING_DAY_POLICY=<required>
MISSING_DATA_PROPORTION_THRESHOLD=<required or explicit NONE>
MISSING_DATA_PROPORTION_OPERATOR=<required if threshold exists>
MISSING_DATA_PROPORTION_UNIT=<required if threshold exists>
MISSING_DATA_DENOMINATOR=<required>

DUPLICATE_RECORD_POLICY=<required>
CONFLICTING_RECORD_POLICY=<required>
INVALID_CANONICAL_GRAIN_POLICY=<required>
UNMAPPED_IDENTITY_POLICY=<required>
UNMAPPED_DATE_POLICY=<required>
REVISION_CONSISTENCY_POLICY=<required>
VOID_CANCELLATION_POLICY=<required>
WINNER_SELECTION_REQUIREMENT=<required>
COMPLETENESS_POLICY=<required>
SOURCE_ROW_LINEAGE_REQUIRED=<required true or false>
SOURCE_ROW_LINEAGE_FAILURE_SEMANTICS=<required>
CANONICAL_GROUP_COVERAGE_POLICY=<required>

APPLICATION_GRAIN=<required>
APPLICATION_SCOPE=<required>
FAILURE_SEMANTICS=<required>
EXCLUSION_SEMANTICS=<required>
THRESHOLD_VARIES_BY_HORIZON=<required true or false>
HORIZON_POLICY=<required>
THRESHOLD_VARIES_BY_PARTITION=<required true or false>
PARTITION_POLICY=<required>

OWNER_DECISION_FINAL=<required: true only after owner decision>
OWNER_DECISION_READY_FOR_INDEPENDENT_REVIEW=<required: true only after owner decision>
```

## 7. Current governance state and remaining blockers

```text
CANONICAL_GATE_COUNT=17
CURRENT_CANONICAL_GATE_PASS_COUNT=1
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=16
S1_DATA_QUALITY_THRESHOLDS_GATE_PASS=false
S1_REMAINING_05_COMPLETE=false
S1_OVERALL_ACCEPTANCE=false

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

S1_REMAINING_06_AUTHORIZED=false
V0_3_S2_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
```

Preparing this request does not delete `DATA_QUALITY_THRESHOLD` from the
remaining-blocker list and does not promote any downstream gate.

## 8. Validation and next action

The companion JSON is the machine-readable source for this request. The
readiness invariants are:

```text
OWNER_DECISION_REQUEST_PREPARED=true
OWNER_DECISION_ISSUED=true
POLICY_INDEPENDENTLY_REVIEWED=false
CANDIDATE_VALUE=null
ACCEPTED_VALUE=null
UNAUTHORIZED_POLICY_VALUE_COUNT=0
SOURCE_002_RAW_READ=false
SOURCE_002_ROW_LEVEL_READ=false
BACKTEST_EXECUTED=false
MODEL_TRAINING_EXECUTED=false
TEST_DATA_ACCESS=false
METRIC_EXECUTION=false
CANONICAL_GATE_STATUS_CHANGED=false
CANONICAL_ACCEPTANCE_RECORD_CHANGED=false
```

```text
NEXT_GATE=S1_DATA_QUALITY_THRESHOLD_POLICY_EXACT_HEAD_INDEPENDENT_REVIEW
NEXT_GATE_AUTHORIZED=false
NEXT_RECOMMENDED_ACTION=RUN_PR222_DATA_QUALITY_OWNER_BINDING_EXACT_HEAD_INDEPENDENT_REVIEW
NO_STEP_IMPLIES_THE_NEXT=true
```

The owner decision is issued and bound, but it still requires exact-head
independent review. This package does not accept the canonical gate, authorize
Remaining-06, or authorize V0.3-S2.
