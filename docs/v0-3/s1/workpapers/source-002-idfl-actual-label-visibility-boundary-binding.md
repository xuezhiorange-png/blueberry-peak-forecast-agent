# V0.3-S1 Source 002 IDFL Actual-Label Visibility Boundary Binding

## 1. Scope and authorization

This docs-only artifact binds one schema-required actual-label visibility
boundary for Source 002. It is issued for independent review and resolves only
`SOURCE_002_IDFL_ACTUAL_LABEL_VISIBILITY_BOUNDARY_NOT_BOUND`.

```text
ARTIFACT_ID=V0_3_S1_SOURCE_002_IDFL_ACTUAL_LABEL_VISIBILITY_BOUNDARY_BINDING
ARTIFACT_VERSION=source-002-idfl-actual-label-visibility-boundary-binding-v1
ARTIFACT_STATUS=ISSUED_FOR_INDEPENDENT_REVIEW
TASK=SOURCE_002_IDFL_ACTUAL_LABEL_VISIBILITY_BOUNDARY_BINDING
TASK_CLASS=DOCS_ONLY_GOVERNED_ACTUAL_LABEL_VISIBILITY_BINDING
BASE_MAIN_SHA=6b0f018d25fda9be4da6d6a830b4a9723dea9308

SOURCE_SYSTEM=扫码称重系统
SOURCE_DATASET=田间商品果每日采摘净重汇总
SOURCE_VERSION=scan-weight-export:v0_3_s1:002
SOURCE_SNAPSHOT_REFERENCE=snapshot:v0_3_s1:002
LABEL_MODE=IMMUTABLE_DAILY_FINAL_LABEL
LABEL_MODE_VERSION=IDFL_V1
```

The task did not read the Source 002 workbook, raw rows, production database,
test data, or holdout data. It did not execute metrics, backtests, or model
training.

## 2. Visibility contract authority

The current-main governing contract is
`docs/v0-3/s1/visibility-inclusion-revision-contract.md` with Git blob
`00ef71da7660f308c2b0d49a8698a1044a814d87`. It separates the
`FORECAST_INPUT` and `ACTUAL_LABEL` visibility domains. For the Source 002
`IMMUTABLE_DAILY_FINAL_LABEL / IDFL_V1` mode, label-side point-in-time replay,
record-level lifecycle fields, source availability, source-recorded-at, label
observation cutoff, revision winner, and finalized-at are not required for
label eligibility. Source-object completeness authority and source-object-bound
row lineage remain required, and forecast-side point-in-time authority remains
independent.

The accepted IDFL mode authority is
`docs/v0-3/s1/workpapers/immutable-daily-final-label-contract-acceptance-decision.md`,
blob `fe2b09fe9ecf1e0737c34040687097aefd90ffc5`. It records
`DECISION_ID=V0_3_S1_IDFL_V1_ATOMIC_CROSS_CONTRACT_ACCEPTANCE` and
`DECISION=ACCEPT`, with mode provenance from PR 180, head
`5added25cbc9be4d35a4517ebff8c34c2144e1a3`, and merge
`6fc689f57fc7f5da7a0c5726472245fd66bc2c9c`.

## 3. Source-specific reconciliation and forecast-input separation

The Source 002 reconciliation package
`docs/v0-3/s1/workpapers/source-002-idfl-v1-source-specific-eligibility-package.md`
has blob `26855ef8949c64ff24b79a64cc696a96997c6114`. It confirms that IDFL
label-side PIT replay and source availability are not required for this label
representation, while source-specific eligibility and the full S1 visibility
gate remain unclosed. This package is not Source Authority acceptance.

The independent forecast-input policy is
`docs/v0-3/s1/evidence/forecast-input-pit-visibility-policy-v1.json`, blob
`b421df123296f2964203339a9c7b9c107d7db0d2`, policy
`v0-3-s1-forecast-input-pit-visibility-v1`. Its predicate is
`SOURCE_AVAILABLE_AT <= FORECAST_CUTOFF_AT`. It is not reused for the Source
002 actual-label domain:

```text
FORECAST_INPUT_VISIBILITY_POLICY_REUSED_FOR_ACTUAL_LABEL=false
FORECAST_INPUT_VISIBILITY_DOMAIN_SEPARATE=true
FORECAST_INPUT_VISIBILITY_POLICY_CHANGED=false
FORECAST_TARGET_INTERVAL_CONTRACT_CHANGED=false
```

## 4. Formal literal and schema validation

This task binds the following exact literal; the wording is intentionally not
rephrased:

```text
ACTUAL_LABEL_VISIBILITY_POLICY_VERSION=source-002-idfl-actual-label-visibility-boundary-v1
LABEL_VISIBILITY_AUTHORITY=NOT_POINT_IN_TIME_REPLAYABLE
VISIBILITY_BOUNDARY_SCOPE=SOURCE_002_ACTUAL_LABEL_IDFL_V1_ONLY
VISIBILITY_BOUNDARY=NOT_POINT_IN_TIME_REPLAYABLE_FOR_IDFL_LABEL_SIDE; SOURCE_OBJECT_COMPLETENESS_AUTHORITY_REQUIRED; SOURCE_OBJECT_BOUND_ROW_LINEAGE_REQUIRED; FORECAST_INPUT_VISIBILITY_DOMAIN_SEPARATE
ACTUAL_LABEL_VISIBILITY_BOUNDARY_STATUS=BOUND_FOR_INDEPENDENT_REVIEW
VISIBILITY_BOUNDARY_SCHEMA_VALIDATION=PASS
VISIBILITY_BOUNDARY_NON_EMPTY=true
```

The schema at
`docs/v0-3/s1/schemas/business-source-attestation.schema.json` (blob
`a8e53f6f8c571d481bba54585de175d2060dd93c`) requires `visibility_boundary` as
a non-empty string. The literal passes that type and minimum-length check.

The literal means that the governed IDFL actual-label representation does not
provide or require historical label-side PIT replay, and that label eligibility
depends on source-object completeness authority and source-object-bound row
lineage. It does not create source-recorded-at, source-available-at,
finalized-at, label-observation-cutoff, historical replay, completeness, or
acceptance authority.

```text
SOURCE_COMPLETENESS_AUTHORITY_REQUIRED=true
SOURCE_COMPLETENESS_ISSUED=false
SOURCE_COMPLETE_THROUGH_BUSINESS_DATE=NOT_ISSUED
COVERAGE_END_PROMOTED_TO_COMPLETENESS_WATERMARK=false
VISIBILITY_BOUNDARY_PROVES_SOURCE_COMPLETENESS=false
VISIBILITY_BOUNDARY_PROVES_HISTORICAL_LABEL_VISIBILITY=false
VISIBILITY_BOUNDARY_IS_COMPLETENESS_WATERMARK=false
SOURCE_OBJECT_BOUND_ROW_LINEAGE_ISSUED_BY_THIS_TASK=false
```

## 5. Deterministic binding hash

The JSON artifact contains a stable `binding_payload` consisting only of
source identity, accepted IDFL authority, the actual-label boundary, the
forecast-input domain separation, and immutable authority references. It
excludes timestamp, branch name, PR state, local paths, credentials, private
locators, personal identity, CI state, and mutable completeness state.

```text
BINDING_CANONICALIZATION=UTF8_JSON_SORT_KEYS_RECURSIVELY_COMPACT_SEPARATORS_ENSURE_ASCII_FALSE
ACTUAL_LABEL_VISIBILITY_BOUNDARY_BINDING_SHA256=29409533a6338dfea460d272f681dd41789d446c8f3252757d41bed280a67729
ACTUAL_LABEL_VISIBILITY_BOUNDARY_BINDING_HASH_REPLAY=PASS
```

## 6. Hard-blocker reconciliation

The previous current-main closure-readiness state had six hard blockers. This
artifact resolves only the actual-label visibility-boundary binding for
independent review. The five remaining blockers are unchanged:

```text
PREVIOUS_HARD_BLOCKER_COUNT=6
RESOLVED_BLOCKER=SOURCE_002_IDFL_ACTUAL_LABEL_VISIBILITY_BOUNDARY_NOT_BOUND
REMAINING_HARD_BLOCKER_COUNT_AFTER_THIS_BINDING=5
REMAINING_HARD_BLOCKERS=(
TOP_LEVEL_CORRECTION_RULE_NOT_BOUND
TOP_LEVEL_VOID_RULE_NOT_BOUND
TOP_LEVEL_FINAL_CONFIRMATION_RULE_NOT_BOUND
SOURCE_COMPLETENESS_DECLARATION_AND_WATERMARK_NOT_ISSUED
FINAL_SOURCE_OWNER_ATTESTATION_EVENT_AND_INDEPENDENT_ACCEPTANCE_NOT_ISSUED
)
```

No completeness declaration, watermark, final Source Owner Attestation,
Source Authority acceptance, or Source Cohort acceptance is issued here.

## 7. Canonical state and stop boundary

No canonical artifact was modified and no gate state changed:

```text
CURRENT_CANONICAL_GATE_PASS_COUNT=2
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=15
CANONICAL_GATE_STATUS_CHANGED=false
CANONICAL_ACCEPTANCE_RECORD_CHANGED=false
SOURCE_AUTHORITY_ACCEPTED=false
SOURCE_COHORT_ACCEPTED=false
FINAL_ATTESTATION_SCHEMA_READY=false
FINAL_ATTESTATION_ISSUANCE_READY=false
FINAL_ATTESTATION_ISSUED=false

ACTUAL_LABEL_VISIBILITY_BINDING_AUTHORIZED=true
CORRECTION_RULE_BINDING_AUTHORIZED=false
VOID_RULE_BINDING_AUTHORIZED=false
FINAL_CONFIRMATION_RULE_BINDING_AUTHORIZED=false
SOURCE_COMPLETENESS_ISSUANCE_AUTHORIZED=false
FINAL_SOURCE_OWNER_ATTESTATION_AUTHORIZED=false
SOURCE_AUTHORITY_ACCEPTANCE_AUTHORIZED=false
SOURCE_COHORT_ACCEPTANCE_AUTHORIZED=false
CANONICAL_GATE_MUTATION_AUTHORIZED=false
S1_REMAINING_06_AUTHORIZED=false
V0_3_S2_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

The next permitted action is
`RUN_SOURCE_002_IDFL_ACTUAL_LABEL_VISIBILITY_BOUNDARY_EXACT_HEAD_INDEPENDENT_REVIEW`.
This package stops before independent review, Ready, Merge, completeness
issuance, final attestation, Source Authority/Cohort acceptance, Remaining-06,
or V0.3-S2.
