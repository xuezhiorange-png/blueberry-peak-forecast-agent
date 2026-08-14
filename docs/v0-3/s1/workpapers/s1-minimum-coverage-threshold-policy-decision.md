# S1 Minimum Coverage Threshold Policy Decision Correction R1

## Current result

```text
TASK=V0_3_S1_MINIMUM_COVERAGE_THRESHOLD_POLICY_DECISION_CORRECTION_R1
RESULT=OWNER_DECISION_REQUIRED
BASE_MAIN_SHA=b96fc39fcee50c2447e7bcc90580745b090d8646
GATE_ID=S1-MINIMUM-COVERAGE
OWNER_ROLE=model_validation_owner_role
```

This correction withdraws the unauthorized numeric threshold and related owner-dependent policy choices introduced by the prior head. The repository may prepare the decision request and preserve authoritative context, but it may not choose the S1 minimum-coverage threshold on behalf of `model_validation_owner_role`.

## Governing authority

`S1-REMAINING-05` states that the S1 minimum-coverage decision is external, cannot be inferred, and must provide a versioned owner decision covering threshold identity/version, unit, application grain and scope, denominator definition, failure semantics, horizon variation, partition variation, provenance, and independent-review identity.

```text
DECISION_ID=S1_MINIMUM_COVERAGE_THRESHOLD_POLICY
CURRENT_STATUS=OWNER_DECISION_REQUIRED
EXTERNAL_DECISION_REQUIRED=true
CAN_BE_INFERRED=false
CANDIDATE_VALUE=null
ACCEPTED_VALUE=null
```

The S3 contract supplies context only:

```text
S3_COVERAGE_RATIO_FORMULA=s2_comparable_binding_row_count / s2_total_binding_row_count
S3_MIN_COMPARABLE_ROWS_FOR_REPORTING=10
S3_REPORTING_FLOOR_IS_S1_THRESHOLD=false
```

Neither the S3 reporting floor nor Source 002 statistics can be promoted into S1 threshold authority.

## Withdrawn unauthorized choices

The prior head introduced `THRESHOLD_VALUE=0.900000` and also decided that one threshold would apply uniformly across horizons and TRAIN/VALIDATION/TEST. Those choices have no recorded `model_validation_owner_role` provenance and are withdrawn.

```text
PREVIOUS_UNAUTHORIZED_THRESHOLD_VALUE=0.900000
PREVIOUS_VALUE_HAS_AUTHORITY=false
PREVIOUS_VALUE_MUST_NOT_BE_REUSED=true
PREVIOUS_HORIZON_UNIFORMITY_DECISION_WITHDRAWN=true
PREVIOUS_PARTITION_UNIFORMITY_DECISION_WITHDRAWN=true
```

No downstream task may cite the withdrawn value or its associated policy choices as evidence, candidate authority, default behavior, or historical acceptance precedent.

## Owner decision request

The following fields remain explicitly unresolved until the authorized owner issues them:

```text
THRESHOLD_VALUE=null
THRESHOLD_OPERATOR=null
THRESHOLD_UNIT=null
APPLICATION_GRAIN=null
APPLICATION_SCOPE=null
DENOMINATOR_DEFINITION=null
FAILURE_SEMANTICS=null
THRESHOLD_VARIES_BY_HORIZON=null
THRESHOLD_VARIES_BY_PARTITION=null
OWNER_PROVENANCE=null
```

The owner decision must bind all of those fields together with a policy version and provenance. It must explicitly state whether the existing S3 `coverage_ratio` is adopted as the S1 threshold measure or whether another governed coverage measure is selected. That adoption cannot be inferred by this correction task.

The owner decision must also specify how a zero denominator is handled and how `BELOW_MINIMUM` affects S1 acceptance/release eligibility. The correction task does not choose those semantics.

## Independent rules that remain unchanged

Nothing in this correction weakens existing S2/S3 rules. In particular:

- S2 row-status semantics remain authoritative;
- S3 structural duplicate failures remain fail-closed;
- exact actual-pair requirements for quantile coverage remain intact;
- P50/P80/P90 semantic-verification gates remain intact;
- complete daily-rowset requirements for cumulative and peak/window metrics remain intact;
- complete seven-day-window requirements remain intact; and
- `MIN_COMPARABLE_ROWS_FOR_REPORTING=10` remains an S3 reporting-floor rule only.

## Decision-request identity

The corrected owner-decision request payload is SHA-256 bound as:

```text
OWNER_DECISION_REQUEST_SHA256=c16d48616e35a9f808c360bc3a5e1cda0d28f61ff63b50ec27d85f00843408ae
```

This hash binds the unresolved decision fields, owner role, external-decision requirement, authoritative S3 context, and forbidden inference rules. It does not bind or imply a threshold value.

## Current gate boundary

```text
POLICY_DECISION_ISSUED=false
POLICY_INDEPENDENTLY_REVIEWED=false
S1_MINIMUM_COVERAGE_GATE_PASS=false
CANONICAL_ACCEPTANCE_RECORD_CHANGED=false
SOURCE_002_RAW_READ=false
SOURCE_002_ROW_LEVEL_READ=false
BACKTEST_EXECUTED=false
MODEL_TRAINING_EXECUTED=false
TEST_DATA_ACCESS=false
S1_REMAINING_06_AUTHORIZED=false
V0_3_S2_AUTHORIZED=false
```

The corrected PR now represents an owner-decision request, not an issued threshold policy.

```text
NEXT_GATE=S1_MINIMUM_COVERAGE_THRESHOLD_OWNER_DECISION
NEXT_GATE_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```
