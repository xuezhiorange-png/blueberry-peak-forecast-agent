# V0.3-S1 Data-Quality Threshold Policy Decision Request

```text
TASK_ID=V0_3_S1_DATA_QUALITY_THRESHOLD_POLICY_DECISION_READINESS
TASK_CLASS=DOCS_ONLY_EXTERNAL_OWNER_DECISION_READINESS
CURRENT_MAIN_SHA=7fd2c15f91f6dfad94178595845df389017d02b3
DECISION_ID=S1_DATA_QUALITY_THRESHOLD_POLICY
OWNER_ROLE=data_quality_owner_role
CURRENT_STATUS=OWNER_DECISION_REQUIRED
OWNER_DECISION_REQUEST_PREPARED=true
OWNER_DECISION_ISSUED=false
POLICY_INDEPENDENTLY_REVIEWED=false
EXTERNAL_DECISION_REQUIRED=true
CAN_BE_INFERRED=false
CANDIDATE_VALUE=null
ACCEPTED_VALUE=null
BLOCK_REASON=NO_APPROVED_VERSIONED_DATA_QUALITY_THRESHOLD_POLICY
```

## 1. Scope and authority boundary

This workpaper prepares a decision request for the S1 data-quality threshold
gate. It does not select a policy value, issue an owner decision, or change a
canonical gate status. The required decision authority is
`data_quality_owner_role`; the request must be completed by that authority and
then independently reviewed.

The request is deliberately fail-closed:

```text
S1_DATA_QUALITY_THRESHOLDS_GATE_PASS=false
S1_REMAINING_05_COMPLETE=false
S1_OVERALL_ACCEPTANCE=false
```

No value is inferred from Source 002 statistics, fixtures, test data, code
behavior, or historical performance. Source 002 raw and row-level data are
outside this task.

## 2. Required owner decision dimensions

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

## 3. Common fields that must be frozen in the owner payload

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

## 4. Minimum-coverage boundary

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

## 5. Owner signature template

The following is a template only. Placeholder values remain unresolved until
the data-quality owner supplies and signs the policy.

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

## 6. Current governance state and remaining blockers

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

## 7. Validation and next action

The companion JSON is the machine-readable source for this request. The
readiness invariants are:

```text
OWNER_DECISION_REQUEST_PREPARED=true
OWNER_DECISION_ISSUED=false
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
NEXT_GATE=S1_DATA_QUALITY_THRESHOLD_OWNER_DECISION
NEXT_GATE_AUTHORIZED=false
NEXT_RECOMMENDED_ACTION=OBTAIN_DATA_QUALITY_OWNER_DECISION
NO_STEP_IMPLIES_THE_NEXT=true
```

The next action requires a separate owner decision. This package does not
issue that decision, perform independent review, or authorize Remaining-06 or
V0.3-S2.
