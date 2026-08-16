# S1 Acceptance Package

## Acceptance identity and current state

```text
ACCEPTANCE_PACKAGE_ID=V0_3_S1_ACCEPTANCE_PACKAGE
SLICE=V0.3-S1
CANONICAL_GATE_COUNT=17
CURRENT_CANONICAL_GATE_PASS_COUNT=3
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=14
SOURCE_AUTHORITY_ACCEPTED=true
SOURCE_COHORT_ACCEPTED=false
Q2C_ACCEPTED=false
CURRENT_V0_3_S1_COMPLETE=false
CURRENT_V0_3_S1_ACCEPTANCE_STATUS=BLOCKED
V0_3_S1_ACCEPTED=false
SLICE_S1_COMPLETE=BLOCKED
CURRENT_ACCEPTANCE_RECORD_STATUS=BLOCKED
CURRENT_INDEPENDENT_REVIEW_STATUS=NOT_STARTED
S1_INDEPENDENT_REVIEW=BLOCKED
```

This is the single runtime gate registry for S1. Every row uses the same
runtime field set; there is no separate initial-status authority. Fourteen
required rows remain blocked because source cohort evidence, policy, and final
independent review are not present; Source Authority is accepted by the PR #238
exact-head reviewed attestation closeout. The standalone
`S1-MINIMUM-COVERAGE` and `S1-DATA-QUALITY-THRESHOLDS` rows are now `PASS` and bind the independently reviewed
owner decision hash; no row-level data is issued by this package.

```text
COMPLETION_GATE_REGISTRY_IS_AUTHORITATIVE=true
LEGACY_COMPLETION_BOOLEANS_DERIVED_ONLY=true
LEGACY_COMPLETION_BOOLEANS_MAY_OVERRIDE_GATE_STATUS=false
```

## Runtime gate field set

```text
gate_id
gate_class
required_or_conditional
owner_role
authoritative_artifact
artifact_identity
artifact_hash_or_status
metric_contract_version
acceptance_threshold_source
acceptance_threshold
allowed_not_applicable_condition
status
block_reason
reviewer_role
reviewer
reviewed_at
notes
```

The `status` field is the only runtime status field and `block_reason` is the
only runtime blocking-reason field. All seventeen S1 decision gates are
`required`; the holdout-feasibility gate is a required feasibility decision and
is not the future external-holdout materialization gate.

For `S1-HOLDOUT-FEASIBILITY`, a reviewed `FEASIBLE` decision or a reviewed
`NOT_FEASIBLE` decision can both close this required S1 decision gate as
`PASS`. Neither outcome materializes an external holdout. A future
external-holdout materialization gate is conditional and is outside this
package; it is not permitted to turn this required feasibility gate into
`NOT_APPLICABLE`.

## Canonical gate registry

| gate_id | gate_class | required_or_conditional | owner_role | authoritative_artifact | artifact_identity | artifact_hash_or_status | metric_contract_version | acceptance_threshold_source | acceptance_threshold | allowed_not_applicable_condition | status | block_reason | reviewer_role | reviewer | reviewed_at | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `S1-Q2C-TARGET` | business | required | business_data_owner_role | business source attestation | `BUSINESS_ATTESTATION_REQUIRED` | `BLOCKED_NO_EXTERNAL_ATTESTATION` | `NOT_APPLICABLE_FOR_THIS_GATE` | Q2C contract | `Q2C_OUTCOME_CLOSED` | `NEVER` | `BLOCKED` | `MISSING_BUSINESS_ATTESTATION` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | Six Q2C dimensions remain unclosed. |
| `S1-SOURCE-AUTHORITY` | source | required | source_governance_owner_role | Source002 final Source Owner Attestation | `source-002-final-source-owner-attestation-v1` | `2c7bd156da2eb3d7c2cb5906e23cb3d380f709b43e39e1c6a6ce38f5587971e1` | `NOT_APPLICABLE_FOR_THIS_GATE` | source authority contract | `OWNER_ROLE_AND_ATTESTED_VERSION_PRESENT` | `NEVER` | `PASS` | `NONE` | independent S1 reviewer | `github-review-4946622009` | `2026-08-16T16:17:55Z` | PR #238 exact-head independent acceptance and CI 31955752008 verified the final Source Owner Attestation; this closes Source Authority only. |
| `S1-SOURCE-COHORT` | source | required | data_governance_owner_role | source cohort manifest | `COHORT_MANIFEST_REQUIRED` | `BLOCKED_NO_SOURCE_COHORT` | `NOT_APPLICABLE_FOR_THIS_GATE` | source cohort contract | `MANIFEST_HASH_AND_SCOPE_PRESENT` | `NEVER` | `BLOCKED` | `SOURCE_COHORT_NOT_FROZEN` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | S1 identity is separate from S2 rowsets. |
| `S1-PHYSICAL-MEANING` | business | required | business_data_owner_role | physical measurement attestation | `PHYSICAL_MEANING_REQUIRED` | `BLOCKED_NO_MEASUREMENT_EVIDENCE` | `NOT_APPLICABLE_FOR_THIS_GATE` | Q2C physical dimensions | `EVENT_AND_MARKETABILITY_BOUNDARY_EVIDENCED` | `NEVER` | `BLOCKED` | `MISSING_MEASUREMENT_BOUNDARY` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | Farm-pick versus marketability remains unresolved. |
| `S1-UNIT-AND-TIME-BASIS` | business | required | business_data_owner_role | physical and time attestation | `UNIT_TIME_BASIS_REQUIRED` | `BLOCKED_NO_UNIT_TIME_EVIDENCE` | `NOT_APPLICABLE_FOR_THIS_GATE` | Q2C physical and time dimensions | `KG_AND_FARM_LOCAL_DATE_BOUND` | `NEVER` | `BLOCKED` | `UNIT_OR_TIME_AUTHORITY_MISSING` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | No unit or timezone is inferred. |
| `S1-CANONICAL-GRAIN` | source | required | source_governance_owner_role | source and mapping manifest | `CANONICAL_GRAIN_REQUIRED` | `BLOCKED_NO_MAPPING_EVIDENCE` | `NOT_APPLICABLE_FOR_THIS_GATE` | Q2A/I7 and Q2C | `CANONICAL_GRAIN_AND_MAPPING_BOUND` | `NEVER` | `BLOCKED` | `GRAIN_OR_DATE_AUTHORITY_MISSING` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | Plot support remains false. |
| `S1-VISIBILITY` | data | required | data_governance_owner_role | visibility and snapshot manifest | `VISIBILITY_MANIFEST_REQUIRED` | `BLOCKED_NO_VISIBILITY_EVIDENCE` | `NOT_APPLICABLE_FOR_THIS_GATE` | Q2A/I7 contract | `SOURCE_CLASS_CUTOFF_RULES_EVIDENCED` | `NEVER` | `BLOCKED` | `HISTORICAL_VISIBILITY_NOT_RECONSTRUCTABLE` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | No current-state fallback is allowed. |
| `S1-REVISION-WINNER` | data | required | data_governance_owner_role | revision lineage and winner manifest | `WINNER_MANIFEST_REQUIRED` | `BLOCKED_NO_REVISION_EVIDENCE` | `NOT_APPLICABLE_FOR_THIS_GATE` | Q2A/I7 contract | `ONE_VALID_WINNER_PER_KEY` | `NEVER` | `BLOCKED` | `REVISION_WINNER_NOT_VERIFIED` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | Lineage cannot be inferred from import order. |
| `S1-INCLUSION-EXCLUSION` | data | required | data_quality_owner_role | inclusion and exclusion manifest | `EXCLUSION_MANIFEST_REQUIRED` | `BLOCKED_NO_COHORT_EVIDENCE` | `NOT_APPLICABLE_FOR_THIS_GATE` | Q2A/I7 and Q2C | `REASONS_AND_COUNTS_RECONCILED` | `NEVER` | `BLOCKED` | `INCLUSION_POLICY_NOT_FROZEN` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | Unknown is not zero. |
| `S1-MISSING-CORRECTION-CANCELLATION` | data | required | data_quality_owner_role | correction, missing-day, and cancellation policy | `MISSING_CORRECTION_CANCELLATION_REQUIRED` | `BLOCKED_NO_SOURCE_POLICY` | `NOT_APPLICABLE_FOR_THIS_GATE` | Q2A/I7 contract | `LATE_ENTRY_REVISION_VOID_RULES_PRESENT` | `NEVER` | `BLOCKED` | `REVISION_POLICY_NOT_FROZEN` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | Delayed, corrected, and void records need authority. |
| `S1-SPLIT-POLICY` | evaluation | required | model_validation_owner_role | split policy and custody record | `SPLIT_POLICY_REQUIRED` | `BLOCKED_NO_SOURCE_COHORT` | `PENDING_S1_METRIC_CONTRACT_FREEZE` | split contract | `TIME_ORDERED_SPLITS_AND_NO_LEAKAGE` | `NEVER` | `BLOCKED` | `SPLIT_POLICY_NOT_FROZEN` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | No TEST or holdout is accessed. |
| `S1-METRIC-CONTRACT` | metrics | required | model_validation_owner_role | S1 metric contract and S3 binding | `METRIC_CONTRACT_REQUIRED` | `BLOCKED_NO_ACCEPTED_SOURCE` | `PENDING_S1_METRIC_CONTRACT_FREEZE` | S3 contract | `ALL_CANONICAL_METRIC_IDS_AND_STATES_BOUND` | `NEVER` | `BLOCKED` | `METRIC_CONTRACT_NOT_ACCEPTED` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | Quantile and baseline gates remain fail-closed. |
| `S1-MINIMUM-COVERAGE` | metrics | required | model_validation_owner_role | coverage threshold decision record | `v0-3-s1-minimum-coverage-threshold-v1` | `a9361145eaa04e93e6b7bc3a4e4faa7a42c542b29de4978988658f53fa11f692` | `v0.3-metric-contract-v1` | S3 contract and independently reviewed owner decision `4937929668` | `S3_COVERAGE_RATIO_GREATER_THAN_OR_EQUAL_0.900000_PER_APPLICATION_CELL` | `NEVER` | `PASS` | `NONE` | independent S1 reviewer | `github-review-4937929668` | `2026-08-14T14:04:08Z` | Owner decision payload/hash and exact-head CI were independently reviewed on PR #219 head `5775e908cfe072fa962c99e822901b7157128418`; S3 reporting floor 10 is not the S1 threshold. |
| `S1-DATA-QUALITY-THRESHOLDS` | data | required | data_quality_owner_role | `v0-3-s1-data-quality-threshold-policy-v1` | `v0-3-s1-data-quality-threshold-policy-v1` | `11e810f4385965f173c6a269d08a1469f6eb4f6173610d272b4ecc09b2171969` | `v0.3-metric-contract-v1` | reviewed versioned data-quality owner policy | `VALID_INCLUDED_CANONICAL_GROUP_COVERAGE_GREATER_THAN_OR_EQUAL_1.000000_PER_APPLICATION_CELL` | `NEVER` | `PASS` | `NONE` | independent S1 reviewer | `github-review-4943327077` | `2026-08-15T08:09:57Z` | Owner decision comment `5301040523` and exact-head CI `31872490353` are bound; this accepts the policy only, not data execution or any other gate. |
| `S1-DATA-CUSTODY` | governance | required | data_governance_owner_role | versioned custody record | `CUSTODY_RECORD_REQUIRED` | `BLOCKED_NO_GOVERNED_CUSTODY_RECORD` | `NOT_APPLICABLE_FOR_THIS_GATE` | source custody contract | `ACCESS_RETENTION_WITHDRAWAL_VOID_EVIDENCED` | `NEVER` | `BLOCKED` | `SOURCE_CUSTODY_NOT_VERIFIED` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | Policy identities and hashes only. |
| `S1-HOLDOUT-FEASIBILITY` | evaluation | required | model_validation_owner_role | external holdout feasibility record | `HOLDOUT_FEASIBILITY_REQUIRED` | `BLOCKED_NO_COHORT_FEASIBILITY_EVIDENCE` | `PENDING_S1_METRIC_CONTRACT_FREEZE` | split contract | `REVIEWED_FEASIBLE_OR_REVIEWED_NOT_FEASIBLE` | `NEVER` | `BLOCKED` | `FEASIBILITY_NOT_YET_ACCEPTED` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | This gate is required; it is not materialization. |
| `S1-INDEPENDENT-REVIEW` | governance | required | independent_reviewer_role | complete S1 acceptance record | `ACCEPTANCE_RECORD_REQUIRED` | `BLOCKED_NO_INDEPENDENT_REVIEW` | `NOT_APPLICABLE_FOR_THIS_GATE` | S1 package | `ALL_REQUIRED_GATES_CLOSED` | `NEVER` | `BLOCKED` | `NOT_YET_INDEPENDENTLY_REVIEWED` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | Review cannot be self-attested. |

## Acceptance calculation

```text
COMPLETION_RULE=ALL_17_REQUIRED_GATE_ROWS_STATUS_PASS
CURRENT_REQUIRED_GATE_PASS_COUNT=3
CURRENT_REQUIRED_GATE_BLOCKED_COUNT=14
CURRENT_SOURCE_AUTHORITY_ACCEPTED=true
CURRENT_SOURCE_COHORT_ACCEPTED=false
CURRENT_Q2C_ACCEPTED=false
CURRENT_REQUIRED_GATE_BLOCKED=true
CURRENT_ACCEPTANCE_RESULT=BLOCKED
CURRENT_S1_ACCEPTED=false
CURRENT_S2_AUTHORIZATION=false
```

The current package records the minimum-coverage and data-quality policy gates
as closed, but it cannot issue a target, source cohort, split, holdout
feasibility decision, metric-contract acceptance, or custody acceptance. Source
Authority is already accepted; all downstream and unrelated gates remain fail-closed. A
future accepted record must preserve prior evidence identities and record the
final independent S1 reviewer and review time.

The JSON schema in this directory requires exactly these seventeen canonical
gate IDs once each. A required gate cannot be `NOT_APPLICABLE`; only a future
conditional gate outside this package could use that state after reviewed
evidence.
