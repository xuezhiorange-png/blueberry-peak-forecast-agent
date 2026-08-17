# Source002 Physical Meaning and Unit/Time Basis Canonical Closeout

## Machine-readable identity

```text
ARTIFACT_ID=V0_3_S1_SOURCE_002_PHYSICAL_UNIT_TIME_CANONICAL_ACCEPTANCE_CLOSEOUT
ARTIFACT_VERSION=source-002-physical-unit-time-canonical-acceptance-closeout-v1
ARTIFACT_STATUS=CLOSED_FOR_PHYSICAL_MEANING_AND_UNIT_TIME_BASIS_ONLY
TASK_ID=S1_REMAINING_02_PHYSICAL_UNIT_TIME_CANONICAL_CLOSEOUT
TASK_CLASS=DOCS_ONLY_GATE_LOCAL_CANONICAL_ACCEPTANCE_CLOSEOUT
BASE_MAIN_SHA=1ee6da741fe13e163b53c26b2a6705ac8eb28a72
AUDITED_MAIN_SHA=1ee6da741fe13e163b53c26b2a6705ac8eb28a72
CANONICAL_GATE_COUNT=17
CURRENT_CANONICAL_GATE_PASS_COUNT=7
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=10
```

This closeout is limited to the two authorized canonical rows. It records the
PR #245 exact-head independent review, successful exact-head CI, and merged
current-main commit for the already-issued Physical Meaning and Unit/Time
Basis attestations. It does not constitute overall S1 acceptance and does not
authorize any downstream gate or V0.3-S2.

## PR245 review and merge binding

```text
PR245_NUMBER=245
PR245_REVIEWED_HEAD_SHA=7acea813d3f0ae17579da325dfa2f38c7ea9d0c8
PR245_MERGE_SHA=1ee6da741fe13e163b53c26b2a6705ac8eb28a72
PR245_INDEPENDENT_REVIEW_NUMERIC_ID=4949133128
PR245_INDEPENDENT_REVIEW_GRAPHQL_ID=PRR_kwDOS_gTTs8AAAABJv3HSA
PR245_REVIEW_SUBMITTED_AT=2026-08-17T06:58:24Z
PR245_REVIEW_RESULT=PASS
PR245_PHYSICAL_MEANING_REVIEW_RESULT=PASS
PR245_UNIT_TIME_BASIS_REVIEW_RESULT=PASS
PR245_P0_FINDINGS=0
PR245_P1_FINDINGS=0
PR245_P2_FINDINGS=0
PR245_EXACT_HEAD_CI_RUN_ID=32002755230
PR245_EXACT_HEAD_CI_RUN_NUMBER=1308
PR245_EXACT_HEAD_CI_STATUS=completed
PR245_EXACT_HEAD_CI_CONCLUSION=success
PR245_MERGED=true
```

The reviewed head is the PR #245 head and the merge SHA is the audited
current-main SHA. The independent review closed the two gate-local evidence
packages; it did not perform the final independent S1 review.

## Authorized gate transitions

| Gate | Previous status | Previous block reason | Current status | Current block reason | Scope |
| --- | --- | --- | --- | --- | --- |
| `S1-PHYSICAL-MEANING` | `BLOCKED` | `MISSING_MEASUREMENT_BOUNDARY` | `PASS` | `NONE` | Physical Meaning only |
| `S1-UNIT-AND-TIME-BASIS` | `BLOCKED` | `UNIT_OR_TIME_AUTHORITY_MISSING` | `PASS` | `NONE` | Unit and Time Basis only |

The Physical Meaning attestation is
`source-002-physical-meaning-attestation-v1` with hash
`1cacd18aa17797ba229b0198240ef41e753cb9db2763fd7681828e7a77ff3944`.
The Unit/Time Basis attestation is
`source-002-unit-time-basis-attestation-v1` with hash
`d6a58c61a8e0f789e928ef26e864a7e995c50a891b3452c7dc6a6fc6645f17ee`.
Both hashes and their reviewed exact-head provenance are unchanged.

The physical closeout binds the governed field scan-weigh event, recorded
marketable net weight, KG, and marketability/sorting boundary. The unit/time
closeout binds KG representation, farm-local `HARVEST_BUSINESS_DATE`, and
`Asia/Shanghai`. These are acceptance facts for the two target rows only.

## Mutation accounting

```text
TARGET_GATE_STATUS_MUTATION_COUNT=2
TARGET_GATE_BLOCK_REASON_MUTATION_COUNT=2
OTHER_GATE_STATUS_MUTATION_COUNT=0
OTHER_GATE_BLOCK_REASON_MUTATION_COUNT=0
EXACTLY_TWO_TARGET_GATES_CHANGED=true
DOWNSTREAM_GATE_ACCEPTANCE_IMPLIED=false
```

The canonical acceptance record still contains exactly 17 unique required gate
IDs. The current status is seven `PASS` and ten `BLOCKED`. The ten remaining
blocked rows are:

```text
S1-CANONICAL-GRAIN
S1-VISIBILITY
S1-REVISION-WINNER
S1-INCLUSION-EXCLUSION
S1-MISSING-CORRECTION-CANCELLATION
S1-SPLIT-POLICY
S1-METRIC-CONTRACT
S1-DATA-CUSTODY
S1-HOLDOUT-FEASIBILITY
S1-INDEPENDENT-REVIEW
```

Source Authority, Source Cohort, and Q2C remain accepted upstream bindings;
Canonical Grain remains false. `V0_3_S1_COMPLETE=false` and
`V0_3_S1_ACCEPTED=false` remain unchanged.

## Stale current-state reconciliation

The closeout reconciles 15 stale pre-closeout current-state literals across the
authorized current-state mirrors. All 15 were resolved to the PR245-reviewed
and merged current state. Historical pre-closeout snapshots remain only where
their sections are explicitly identified as historical provenance.

```text
CURRENT_STATE_STALE_LITERAL_FOUND=15
CURRENT_STATE_STALE_LITERAL_RESOLVED=15
CURRENT_STATE_STALE_LITERAL_REMAINING=0
HISTORICAL_PRE_CLOSEOUT_TEXT_PRESERVED_ONLY_WHEN_EXPLICITLY_HISTORICAL=true
```

## Validation evidence

```text
JSON_SYNTAX=PASS
ACCEPTANCE_RECORD_SCHEMA_VALIDATION=PASS
CANONICAL_GATE_COUNT_VALIDATION=PASS
CANONICAL_GATE_ID_UNIQUENESS=PASS
TARGET_GATE_STATUS_MUTATION_VALIDATION=PASS
TARGET_GATE_BLOCK_REASON_MUTATION_VALIDATION=PASS
OTHER_GATE_STATUS_MUTATION_COUNT=PASS
OTHER_GATE_BLOCK_REASON_MUTATION_COUNT=PASS
PHYSICAL_MEANING_ATTESTATION_HASH_PARITY=PASS
UNIT_TIME_BASIS_ATTESTATION_HASH_PARITY=PASS
PR245_REVIEW_BINDING=PASS
PR245_EXACT_HEAD_CI_BINDING=PASS
PR245_MERGE_BINDING=PASS
CURRENT_STATE_STALE_LITERAL_SCAN=PASS
PROTECTED_ATTESTATION_HASHES_UNCHANGED=PASS
DATA_SAFETY_BOUNDARY=PASS
GIT_DIFF_CHECK=PASS
```

Validation used Git-tracked governance artifacts and the acceptance schema. No
Source002 raw workbook, row-level business data, TEST data, external holdout,
production database, model training, backtest, metric execution, or
production-code change was performed.

## Authorization boundary

```text
PHYSICAL_MEANING_GATE_LOCAL_CLOSEOUT_AUTHORIZED=true
UNIT_TIME_BASIS_GATE_LOCAL_CLOSEOUT_AUTHORIZED=true
CANONICAL_GATE_STATUS_MUTATION_AUTHORIZED=true
SOURCE_AUTHORITY_ACCEPTANCE_PERFORMED=false
SOURCE_COHORT_ACCEPTANCE_PERFORMED=false
INDEPENDENT_S1_REVIEW_PERFORMED=false
READY_PERFORMED=false
MERGE_PERFORMED=false
S1_REMAINING_06_AUTHORIZED=false
V0_3_S2_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

No independent S1 review, Ready, Merge, downstream gate acceptance, or S2
authorization is performed by this closeout.
